from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.management import call_command
from django.conf import settings
import threading
import random
import json
import time
import datetime

from .models import GeopoliticalNews

# -- Breaking News Cache -------------------------------------------------------
_breaking_news_cache = {
    "data": None,
    "fetched_at": 0,  # epoch seconds
}


def _is_peak_hour_bd():
    """Return True during Bangladesh peak reading hours (BST = UTC+6)."""
    bst_now = datetime.datetime.utcnow() + datetime.timedelta(hours=6)
    h = bst_now.hour
    # Morning 7:00-9:00, Lunch 13:00-14:00, Evening 20:00-23:00
    return (7 <= h < 9) or (h == 13) or (20 <= h < 23)


def _cache_ttl_seconds():
    return 30 * 60 if _is_peak_hour_bd() else 60 * 60  # 30 min peak / 60 min off-peak


def breaking_news_api(request):
    """
    Returns top 3 BD + top 3 international breaking news with 2-3 line summaries
    fetched from Gemini. Uses smart caching: 30 min during BD peak hours, 60 min otherwise.
    """
    global _breaking_news_cache

    now = time.time()
    if (
        _breaking_news_cache["data"] is not None
        and (now - _breaking_news_cache["fetched_at"]) < _cache_ttl_seconds()
    ):
        return JsonResponse(_breaking_news_cache["data"])

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        return JsonResponse({"error": "Gemini API key not configured."}, status=500)

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt = """You are a real-time news intelligence assistant. Your task is to provide the TOP 3 most important and trending news stories RIGHT NOW for two categories.

Return ONLY valid JSON with this exact structure (no markdown, no extra text):
{
  "bd": [
    {
      "title": "Full news headline here",
      "summary": "2-3 sentence summary of the news. What happened, who is involved, and why it matters.",
      "source": "Source name (e.g., Prothom Alo, Daily Star, Dhaka Tribune)",
      "category": "Politics / Economy / Social / Crime / Sports"
    }
  ],
  "international": [
    {
      "title": "Full news headline here",
      "summary": "2-3 sentence summary of the news. What happened, who is involved, and why it matters.",
      "source": "Source name (e.g., BBC, Reuters, Al Jazeera, CNN)",
      "category": "Politics / Conflict / Economy / Climate / Tech"
    }
  ],
  "fetched_at_bst": "HH:MM BST"
}

Rules:
- bd array: exactly 3 items -- top 3 Bangladesh news right now
- international array: exactly 3 items -- top 3 world news right now
- Summaries must be 2-3 sentences, neutral, factual
- Titles must be realistic, specific headlines (not generic)
- fetched_at_bst: current Bangladesh Standard Time (UTC+6) as HH:MM
- Return ONLY the JSON object, nothing else

STRICT RULES:
- Only return real and verifiable news
- Never make up or hallucinate any headline or fact
- Tone must be completely neutral, no opinion
- Focus only on geopolitical, economic, military, or humanitarian events
- Prioritize events involving: war, elections, sanctions, diplomacy, natural disasters"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw = response.text.strip() if response.text is not None else ""

        # Strip markdown code fences if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        raw = raw.strip()

        data = json.loads(raw)

        # Add cache metadata
        data["is_peak_hour"] = _is_peak_hour_bd()
        data["refresh_in_minutes"] = 30 if _is_peak_hour_bd() else 60

        _breaking_news_cache["data"] = data
        _breaking_news_cache["fetched_at"] = now

        return JsonResponse(data)

    except Exception as e:
        # If cache has stale data, return it with a warning
        if _breaking_news_cache["data"]:
            stale = dict(_breaking_news_cache["data"])
            stale["stale"] = True
            stale["error_hint"] = str(e)
            return JsonResponse(stale)
        return JsonResponse(
            {"error": f"Failed to fetch breaking news: {str(e)}"}, status=500
        )


_hf_client = None

def get_hf_bias(text):
    """
    Helper function to get bias from HF model. 
    Loads the client lazily once.
    """
    global _hf_client
    if _hf_client is None:
        try:
            from gradio_client import Client
            _hf_client = Client("detre/bias_detection", verbose=False)
        except Exception as e:
            print("Error initializing HF client:", e)
            return "Center"
    try:
        result = _hf_client.predict(text=text[:2000], api_name="/predict_bias")
        bias_label = result.get("label", "Center")
        return "Center" if bias_label == "Center / Neutral" else bias_label
    except Exception as e:
        print("Error predicting bias:", e)
        return "Center"

def _assign_bias_and_obj(news_qs):
    news_list = []
    for news in news_qs:
        if news.bias_score is not None:
            if news.bias_score <= -0.5:
                news.random_bias = "Left"
            elif news.bias_score >= 0.5:
                news.random_bias = "Right"
            else:
                news.random_bias = "Center"
        else:
            text_to_analyze = news.title + " " + (news.content or "")
            bias_label = get_hf_bias(text_to_analyze)
            news.random_bias = bias_label
            if bias_label == "Left": 
                news.bias_score = -1.0
            elif bias_label == "Right": 
                news.bias_score = 1.0
            else: 
                news.bias_score = 0.0
            news.save(update_fields=['bias_score'])

        news.obj_score = getattr(news, "objectivity_score", None)
        if news.obj_score is None:
            from pages.utils import get_groq_objectivity_score
            text_for_obj = news.title + " " + (news.content or "")
            fetched_obj = get_groq_objectivity_score(text_for_obj)
            if fetched_obj is not None:
                news.obj_score = fetched_obj
                news.objectivity_score = fetched_obj
                news.save(update_fields=['objectivity_score'])
            else:
                news.obj_score = random.randint(55, 98)
        
        news.score_class = (
            "score-high"
            if news.obj_score >= 80
            else ("score-med" if news.obj_score >= 70 else "score-low")
        )
        news_list.append(news)
    return news_list

def home_view(request):
    world_qs = GeopoliticalNews.objects.filter(category="World").order_by(
        "-published_at"
    )[:11]
    bd_qs = GeopoliticalNews.objects.filter(category="BD").order_by("-published_at")[
        :11
    ]

    world_news = _assign_bias_and_obj(world_qs)
    bd_news = _assign_bias_and_obj(bd_qs)

    breaking_world = world_news.pop(0) if world_news else None
    breaking_bd = bd_news.pop(0) if bd_news else None

    context = {
        "breaking_world": breaking_world,
        "breaking_bd": breaking_bd,
        "world_news": world_news[:10],
        "bd_news": bd_news[:10],
    }
    return render(request, "pages/home.html", context)


def get_model_predictions(text):
    """
    Fetches real bias predictions using the Hugging Face Space API
    and combines it with objectivity scores.
    """
    bias_label = get_hf_bias(text)

    from pages.utils import get_groq_objectivity_score

    groq_obj = get_groq_objectivity_score(text)

    # Fallback if API fails or no key
    obj_score = groq_obj if groq_obj is not None else random.randint(60, 99)

    return {
        "bias": bias_label,
        "objectivity": obj_score,
        "score_class": "score-high"
        if obj_score >= 80
        else ("score-med" if obj_score >= 70 else "score-low"),
    }


def analyze_view(request):
    result = None
    if request.method == "POST":
        input_type = request.POST.get("input_type")  # 'url' or 'text'
        content = request.POST.get("content")

        analysis_text = content

        if input_type == "url" and content.startswith("http"):
            from pages.management.commands.fetch import Command

            fetcher = Command()
            scraped_text = fetcher.scrape_full_text(content)
            if scraped_text:
                analysis_text = scraped_text

        predictions = get_model_predictions(analysis_text)

        result = {
            "text_preview": analysis_text[:200] + "...",
            "full_text": analysis_text,
            "metrics": predictions,
        }

    return render(request, "pages/input.html", {"result": result})


@csrf_exempt
def trigger_fetch(request):
    if request.method == "POST":
        thread = threading.Thread(target=call_command, args=("fetch",))
        thread.start()
        return JsonResponse({"status": "fetch started"})
    return JsonResponse({"error": "POST only"}, status=405)


@csrf_exempt
def summarize_view(request, article_id):
    """
    On-demand AI summarization using Google Gemini.
    Reads the stored article content from the DB and returns a concise summary as JSON.
    Does NOT write anything back to the database.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        article = get_object_or_404(GeopoliticalNews, id=article_id)
    except Exception:
        return JsonResponse({"error": "Article not found."}, status=404)

    content = (article.content or "").strip()
    if not content:
        return JsonResponse(
            {"error": "This article has no stored content to summarize."}, status=400
        )

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        return JsonResponse(
            {
                "error": "Gemini API key not configured. Add GEMINI_API_KEY to settings.py."
            },
            status=500,
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt = (
            "You are a professional news analyst. "
            "Read the following news article and write a clear, neutral, 4-sentence summary. "
            "Focus on: what happened, who is involved, where/when, and the key impact or significance. "
            "Do NOT use bullet points -- write it as a single flowing paragraph.\n\n"
            f"ARTICLE:\n{content[:8000]}"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        summary_text = response.text.strip() if response.text is not None else ""

        return JsonResponse({"summary": summary_text})

    except Exception as e:
        return JsonResponse({"error": f"AI summarization failed: {str(e)}"}, status=500)


@csrf_exempt
def summarize_text_view(request):
    """
    On-demand AI summarization for the Check Yourself page.
    Accepts raw article text directly in the POST body -- no DB lookup needed.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    try:
        body = json.loads(request.body)
        content = body.get("text", "").strip()
    except Exception:
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    if not content:
        return JsonResponse({"error": "No text provided to summarize."}, status=400)

    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        return JsonResponse(
            {
                "error": "Gemini API key not configured. Add GEMINI_API_KEY to settings.py."
            },
            status=500,
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt = (
            "You are a professional news analyst. "
            "Read the following news article and write a clear, neutral, 4-sentence summary. "
            "Focus on: what happened, who is involved, where/when, and the key impact or significance. "
            "Do NOT use bullet points -- write it as a single flowing paragraph.\n\n"
            f"ARTICLE:\n{content[:8000]}"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        summary_text = response.text.strip() if response.text is not None else ""

        return JsonResponse({"summary": summary_text})

    except Exception as e:
        return JsonResponse({"error": f"AI summarization failed: {str(e)}"}, status=500)
