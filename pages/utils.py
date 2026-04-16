import logging
import time
import re
import threading
import json
from groq import Groq
from django.conf import settings

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# HF Bias Detection
# --------------------------------------------------------------------------- #
_hf_client = None


def get_hf_bias(text: str) -> str:
    """
    Get political bias label from HF model (detre/bias_detection).
    Returns 'Left', 'Center', or 'Right'. Falls back to 'Center' on any error.
    """
    global _hf_client
    if _hf_client is None:
        try:
            from gradio_client import Client
            _hf_client = Client("detre/bias_detection", verbose=False)
        except Exception as e:
            logger.error(f"Error initializing HF client: {e}")
            return "Center"
    try:
        result = _hf_client.predict(text=text[:2000], api_name="/predict_bias")
        if isinstance(result, dict):
            bias_label = str(result.get("label", "Center"))
            if bias_label in ["0", "LABEL_0", "Left"]:
                return "Left"
            elif bias_label in ["2", "LABEL_2", "Right"]:
                return "Right"
            else:
                return "Center"
        logger.warning(f"Unexpected HF bias result format: {result}")
        return "Center"
    except Exception as e:
        logger.error(f"Error predicting bias: {e}")
        return "Center"


# --------------------------------------------------------------------------- #
# Simple rate-limiter: Groq free tier = 6000 TPM for llama-3.1-8b-instant.
# Each request uses ~900-1200 tokens. Spacing calls 12s apart gives ~5/min,
# comfortably under the limit even with the largest articles.
# --------------------------------------------------------------------------- #
_groq_lock = threading.Lock()
_groq_last_call_time = 0.0
_GROQ_MIN_INTERVAL = 12  # seconds between consecutive Groq calls


def _groq_rate_limited_sleep():
    """Ensure at least _GROQ_MIN_INTERVAL seconds between consecutive Groq calls."""
    global _groq_last_call_time
    with _groq_lock:
        now = time.monotonic()
        elapsed = now - _groq_last_call_time
        if elapsed < _GROQ_MIN_INTERVAL:
            sleep_for = _GROQ_MIN_INTERVAL - elapsed
            logger.debug(f"Groq rate limiter: sleeping {sleep_for:.1f}s")
            time.sleep(sleep_for)
        _groq_last_call_time = time.monotonic()


def get_groq_objectivity_score(text: str) -> int | None:
    """
    Returns an objectivity score from 0 to 100 using Llama 3.1 8B via Groq.
    Returns None if the call fails.
    """
    api_key = getattr(settings, "GROQ_API_KEY", "")
    if not api_key:
        logger.warning("GROQ_API_KEY is not set in Django settings.")
        return None

    if not text or not text.strip():
        logger.warning("Empty text passed to objectivity scorer.")
        return None

    system_msg = (
        "You are an analytical media critic calculating an Objectivity Score (0-100) using a strict mathematical framework.\n"
        "You MUST return ONLY a valid JSON object: {\"reasoning\": \"brief thought\", \"score\": <integer>}\n\n"
        "SCORING FRAMEWORK:\n"
        "Evaluate the text across these 5 criteria. Start each at 20 points and deduct points ONLY for obvious flaws:\n"
        "1. Emotion & Tone (20 pts): Deduct 1-3 points for slight adjectives. Deduct 5-10 for overt outrage/sensationalism.\n"
        "2. Perspective Balance (20 pts): Deduct 1-2 points if slightly one-sided. Deduct 5+ only if clearly biased.\n"
        "3. Fact vs Opinion (20 pts): Deduct 2-5 points for unverified claims or 'experts say' without names.\n"
        "4. Sourcing Quality (20 pts): Deduct 2-5 points if citing anonymous sources without justification.\n"
        "5. Headline/Framing (20 pts): Deduct 1-4 points if the headline is mildly leading or clickbait.\n\n"
        "RULES:\n"
        "- The 'score' is the SUM of the 5 criteria.\n"
        "- Professional news (AP/Reuters/Guardian) SHOULD score between 80 and 95.\n"
        "- NEVER output generic numbers like 85, 88, 90, 95. Use your exact math (e.g., 93, 86, 91, 78).\n"
        "- Reserve scores below 70 for highly political opinion pieces or extreme bias."
    )

    # Truncate cleanly at sentence boundary
    truncated_text = _truncate_at_sentence(text, max_chars=6000)

    user_msg = (
        "Analyze the following article using the 5 criteria framework.\n"
        "Internally calculate the score for each of the 5 criteria (max 20 each).\n"
        "Sum them up to get the final score.\n"
        "Return ONLY a JSON object in this exact format. Do NOT wrap in markdown:\n"
        '{"reasoning": "c1=18, c2=15, c3=19... [short thought]", "score": <final_sum>}\n\n'
        f"ARTICLE:\n{truncated_text}"
    )

    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": user_msg},
    ]

    for attempt in range(1, 4):  # 3 attempts
        try:
            _groq_rate_limited_sleep()  # enforce spacing BEFORE every call

            client = Groq(api_key=api_key)
            chat_completion = client.chat.completions.create(
                messages=messages,
                model="llama-3.1-8b-instant",
                temperature=0.0,
                top_p=1,
                max_tokens=180,
                response_format={"type": "json_object"},
            )

            response_content = chat_completion.choices[0].message.content.strip()
            logger.debug(f"[Groq raw response] attempt={attempt}: '{response_content}'")

            try:
                data = json.loads(response_content)
                score = data.get("score")
                if score is not None:
                    score = int(score)
            except Exception:
                score = None

            if score is not None:
                score = max(0, min(100, score))
                logger.info(f"Objectivity score: {score}")
                return score
            else:
                logger.warning(
                    f"Invalid JSON or no score found in Groq response: '{response_content}'"
                )

        except Exception as e:
            logger.error(f"Groq API error on attempt {attempt}/3: {e}")
            if attempt < 3:
                # Read the exact wait time from the 429 error, add 2s buffer
                wait = 2 ** attempt  # default fallback: 2s, 4s
                match = re.search(r"Please try again in ([\d.]+)s", str(e))
                if match:
                    wait = float(match.group(1)) + 2
                logger.info(f"Retrying in {wait:.1f}s...")
                time.sleep(wait)

    logger.error("All 3 Groq attempts failed. Returning None.")
    return None


def _truncate_at_sentence(text: str, max_chars: int = 6000) -> str:
    """
    Truncates text to max_chars at the nearest sentence boundary.
    Falls back to hard truncation if no sentence boundary is found.
    """
    if len(text) <= max_chars:
        return text

    truncated = text[:max_chars]
    last_period = truncated.rfind(". ")

    if last_period != -1:
        return truncated[: last_period + 1]

    return truncated  # fallback: hard cut
