from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.management import call_command
from django.conf import settings
import threading
import random

from .models import GeopoliticalNews


def home_view(request):
    world_qs = GeopoliticalNews.objects.filter(category="World").order_by("-published_at")[:11]
    bd_qs = GeopoliticalNews.objects.filter(category="BD").order_by("-published_at")[:11]

    # Inject randomized metrics since models are not added yet
    world_news = []
    for news in world_qs:
        news.random_bias = random.choice(["Left", "Center-Left", "Center", "Center-Right", "Right"])
        news.obj_score = random.randint(55, 98)
        news.score_class = "score-high" if news.obj_score >= 80 else ("score-med" if news.obj_score >= 70 else "score-low")
        world_news.append(news)

    bd_news = []
    for news in bd_qs:
        news.random_bias = random.choice(["Left", "Center-Left", "Center", "Center-Right", "Right"])
        news.obj_score = random.randint(55, 98)
        news.score_class = "score-high" if news.obj_score >= 80 else ("score-med" if news.obj_score >= 70 else "score-low")
        bd_news.append(news)

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
    SKELETON FUNCTION:
    This is where you will load your .joblib or .h5 models from Colab.
    For now, it returns mock data that matches the dashboard UI.
    """
    mock_bias = random.choice(["Left", "Center", "Right", "Center-Left", "Center-Right"])
    mock_obj = random.randint(60, 99)

    return {
        "bias": mock_bias,
        "objectivity": mock_obj,
        "score_class": "score-high" if mock_obj >= 80 else ("score-med" if mock_obj >= 70 else "score-low"),
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

    # ── 1. Fetch the article ──────────────────────────────────────────────────
    try:
        article = get_object_or_404(GeopoliticalNews, id=article_id)
    except Exception:
        return JsonResponse({"error": "Article not found."}, status=404)

    content = (article.content or "").strip()
    if not content:
        return JsonResponse({"error": "This article has no stored content to summarize."}, status=400)

    # ── 2. Check API key ──────────────────────────────────────────────────────
    api_key = getattr(settings, "GEMINI_API_KEY", "")
    if not api_key:
        return JsonResponse(
            {"error": "Gemini API key not configured. Add GEMINI_API_KEY to settings.py."},
            status=500,
        )

    # ── 3. Call Gemini ────────────────────────────────────────────────────────
    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt = (
            "You are a professional news analyst. "
            "Read the following news article and write a clear, neutral, 4-sentence summary. "
            "Focus on: what happened, who is involved, where/when, and the key impact or significance. "
            "Do NOT use bullet points — write it as a single flowing paragraph.\n\n"
            f"ARTICLE:\n{content[:8000]}"  # trim to avoid token limits
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        summary_text = response.text.strip()

        return JsonResponse({"summary": summary_text})

    except Exception as e:
        return JsonResponse({"error": f"AI summarization failed: {str(e)}"}, status=500)


@csrf_exempt
def summarize_text_view(request):
    """
    On-demand AI summarization for the Check Yourself page.
    Accepts raw article text directly in the POST body — no DB lookup needed.
    """
    if request.method != "POST":
        return JsonResponse({"error": "POST only"}, status=405)

    import json
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
            {"error": "Gemini API key not configured. Add GEMINI_API_KEY to settings.py."},
            status=500,
        )

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        prompt = (
            "You are a professional news analyst. "
            "Read the following news article and write a clear, neutral, 4-sentence summary. "
            "Focus on: what happened, who is involved, where/when, and the key impact or significance. "
            "Do NOT use bullet points — write it as a single flowing paragraph.\n\n"
            f"ARTICLE:\n{content[:8000]}"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        summary_text = response.text.strip()

        return JsonResponse({"summary": summary_text})

    except Exception as e:
        return JsonResponse({"error": f"AI summarization failed: {str(e)}"}, status=500)


