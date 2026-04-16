from django.urls import path
from .views import home_view, analyze_view, summarize_view, summarize_text_view, breaking_news_api
from pages.views import trigger_fetch

urlpatterns = [
    path("", home_view, name="home"),
    path("analyze/", analyze_view, name="analyze"),
    path("api/trigger-fetch/", trigger_fetch, name="trigger_fetch"),
    path("api/summarize/<int:article_id>/", summarize_view, name="summarize"),
    path("api/summarize-text/", summarize_text_view, name="summarize_text"),
    path("api/breaking-news/", breaking_news_api, name="breaking_news"),
]
