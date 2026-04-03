import time
import feedparser
import requests
from collections import defaultdict
from datetime import datetime, timedelta, timezone as dt_timezone
from email.utils import parsedate_to_datetime

from django.core.management.base import BaseCommand
from django.utils import timezone
from pages.models import GeopoliticalNews

# Global Scraper Configs
import trafilatura
from googlenewsdecoder import new_decoderv1
from playwright.sync_api import sync_playwright
from newspaper import Article, Config

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BLOCKLIST = [
    "football",
    "soccer",
    "cricket",
    "ipl",
    "nfl",
    "nba",
    "tennis",
    "golf",
    "rugby",
    "boxing",
    "ufc",
    "wrestling",
    "esports",
    "bitcoin",
    "crypto",
    "blockchain",
    "nft",
    "recipe",
    "movie",
    "celebrity",
    "fashion",
    "entertainment",
    "how to watch",
    "free stream",
    "watch live",
    "transfer",
    "match preview",
    "highlights",
    "score",
    "goal",
    "tournament",
    "league",
    "horoscope",
    "weather",
    "lifestyle",
    "travel",
    "food",
    "health tips",
]

WORLD_RELEVANCE_KEYWORDS = [
    "war",
    "conflict",
    "attack",
    "military",
    "troops",
    "invasion",
    "sanctions",
    "diplomacy",
    "treaty",
    "ceasefire",
    "nuclear",
    "election",
    "president",
    "prime minister",
    "government",
    "parliament",
    "protest",
    "revolution",
    "coup",
    "crisis",
    "refugee",
    "geopolitics",
    "nato",
    "un",
    "security council",
    "foreign policy",
    "trump",
    "putin",
    "xi jinping",
    "zelensky",
    "iran",
    "israel",
    "ukraine",
    "russia",
    "china",
    "usa",
    "middle east",
    "gaza",
    "taiwan",
    "north korea",
]

BD_RELEVANCE_KEYWORDS = [
    "bangladesh",
    "dhaka",
    "yunus",
    "hasina",
    "bnp",
    "jamaat",
    "awami league",
    "election",
    "government",
    "parliament",
    "protest",
    "reform",
    "constitution",
    "interim",
    "political",
    "minister",
    "chittagong",
    "sylhet",
    "rajshahi",
    "khulna",
    "barishal",
    "rangpur",
    "economy",
    "flood",
    "garment",
    "rohingya",
    "myanmar",
    "india-bangladesh",
    "imf",
    "tarek",
    "khaleda",
    "zia",
    "liberation",
    "independence",
    "taka",
    "remittance",
    "export",
    "import",
    "inflation",
    "budget",
    "court",
    "tribunal",
    "commission",
    "military",
    "border",
    "teesta",
    "padma",
    "crisis",
    "strike",
    "hartal",
    "curfew",
    "caretaker",
    "advisor",
]

WORLD_FEEDS = [
    (
        "Reuters",
        "Center",
        "https://news.google.com/rss/search?q=site:reuters.com+world&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "BBC News",
        "Center",
        "https://news.google.com/rss/search?q=site:bbc.com/news/world&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "Al Jazeera",
        "Left",
        "https://news.google.com/rss/search?q=site:aljazeera.com&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "The Guardian",
        "Left",
        "https://news.google.com/rss/search?q=site:theguardian.com/world&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "AP News",
        "Center",
        "https://news.google.com/rss/search?q=site:apnews.com+world&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "Fox News",
        "Right",
        "https://news.google.com/rss/search?q=site:foxnews.com+world&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "Washington Times",
        "Right",
        "https://news.google.com/rss/search?q=site:washingtontimes.com&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "World Politics",
        "Center",
        "https://news.google.com/rss/search?q=world+politics+war+conflict&hl=en-US&gl=US&ceid=US:en",
    ),
]

BD_FEEDS = [
    (
        "Daily Star",
        "Center",
        "https://news.google.com/rss/search?q=site:thedailystar.net&hl=en-BD&gl=BD&ceid=BD:en",
    ),
    (
        "Dhaka Tribune",
        "Center-Left",
        "https://news.google.com/rss/search?q=site:dhakatribune.com&hl=en-BD&gl=BD&ceid=BD:en",
    ),
    (
        "Prothom Alo",
        "Center",
        "https://news.google.com/rss/search?q=site:en.prothomalo.com&hl=en-BD&gl=BD&ceid=BD:en",
    ),
    (
        "bdnews24",
        "Center",
        "https://news.google.com/rss/search?q=site:bdnews24.com&hl=en-BD&gl=BD&ceid=BD:en",
    ),
    (
        "TBS News",
        "Center",
        "https://news.google.com/rss/search?q=site:tbsnews.net+bangladesh&hl=en-BD&gl=BD&ceid=BD:en",
    ),
    (
        "Financial Express",
        "Center",
        "https://news.google.com/rss/search?q=site:thefinancialexpress.com.bd&hl=en-BD&gl=BD&ceid=BD:en",
    ),
    (
        "BBC Bangladesh",
        "Center",
        "https://news.google.com/rss/search?q=bangladesh+site:bbc.com&hl=en-BD&gl=BD&ceid=BD:en",
    ),
    (
        "Reuters BD",
        "Center",
        "https://news.google.com/rss/search?q=bangladesh+site:reuters.com&hl=en-BD&gl=BD&ceid=BD:en",
    ),
    (
        "BD Politics",
        "Center",
        "https://news.google.com/rss/search?q=bangladesh+politics&hl=en-BD&gl=BD&ceid=BD:en",
    ),
    (
        "Al Jazeera BD",
        "Left",
        "https://news.google.com/rss/search?q=bangladesh+site:aljazeera.com&hl=en-BD&gl=BD&ceid=BD:en",
    ),
    (
        "AP Bangladesh",
        "Center",
        "https://news.google.com/rss/search?q=bangladesh+site:apnews.com&hl=en-BD&gl=BD&ceid=BD:en",
    ),
    (
        "New Age BD",
        "Center",
        "https://news.google.com/rss/search?q=site:newagebd.net&hl=en-BD&gl=BD&ceid=BD:en",
    ),
]

BD_FILTER_KEYWORDS = [
    "bangladesh",
    "dhaka",
    "yunus",
    "hasina",
    "bnp",
    "jamaat",
    "chittagong",
    "sylhet",
    "rajshahi",
    "khulna",
    "barishal",
    "rangpur",
    "awami",
    "bangla",
    "tarek",
    "amir",
    "zia",
    "khaleda",
    "rohingya",
    "taka",
    "garment",
    "padma",
    "teesta",
    "cox's bazar",
    "comilla",
    "gazipur",
    "narayanganj",
]


class Command(BaseCommand):
    help = "Fetch top 10 world + top 10 BD news from last 12 hours, ranked by relevance"

    def handle(self, *args, **options):
        self.stdout.write(f"\n[START] {timezone.now().strftime('%Y-%m-%d %H:%M')}")

        # Initialize browser state for both automated and single-use scrapes
        self._browser = None
        self._playwright_ctx = None
        self._p = None

        self.stdout.write("\n=== WORLD NEWS ===")
        self.process_feeds(
            feeds=WORLD_FEEDS,
            category="World",
            limit=10,
            bd_filter=False,
            relevance_keywords=WORLD_RELEVANCE_KEYWORDS,
        )

        self.stdout.write("\n=== BANGLADESH NEWS ===")
        self.process_feeds(
            feeds=BD_FEEDS,
            category="BD",
            limit=10,
            bd_filter=True,
            relevance_keywords=BD_RELEVANCE_KEYWORDS,
        )

        self.stdout.write(f"\n[DONE] {timezone.now().strftime('%Y-%m-%d %H:%M')}")

    # Main pipeline

    def process_feeds(self, feeds, category, limit, bd_filter, relevance_keywords):
        cutoff = datetime.now(dt_timezone.utc) - timedelta(hours=12)
        self.stdout.write(f"  Cutoff: {cutoff.strftime('%b %d %H:%M')} UTC\n")

        candidates = []

        for feed_name, bias, feed_url in feeds:
            self.stdout.write(f"  [{bias:12}] Fetching {feed_name}...")
            try:
                resp = requests.get(feed_url, headers=HEADERS, timeout=10)
                parsed = feedparser.parse(resp.content)
                entries = parsed.entries
            except Exception as e:
                self.stdout.write(f"  [WARN]  Failed: {e}")
                continue

            if not entries:
                self.stdout.write(f"  |- 0 entries")
                continue

            feed_hits = 0
            for entry in entries:
                title = entry.get("title", "").strip()
                url_value = entry.get("link", "").strip()
                summary = entry.get("summary", "")

                if not title or not url_value or title == "[Removed]":
                    continue

                published_at = self.parse_entry_date(entry)
                if published_at and published_at < cutoff:
                    continue

                if bd_filter:
                    combined = (title + " " + summary).lower()
                    if not any(kw in combined for kw in BD_FILTER_KEYWORDS):
                        continue

                if any(blocked in title.lower() for blocked in BLOCKLIST):
                    continue

                if GeopoliticalNews.objects.filter(url=url_value).exists():
                    continue

                score = self.relevance_score(title, summary, relevance_keywords)
                candidates.append(
                    {
                        "title": title,
                        "url": url_value,
                        "published_at": published_at or timezone.now(),
                        "source_name": feed_name,
                        "bias": bias,
                        "summary": summary,
                        "score": score,
                    }
                )
                feed_hits += 1

            self.stdout.write(f"  |- {feed_hits} fresh candidates")

        if not candidates:
            self.stdout.write(f"\n[{category}] No fresh articles found.")
            return

        candidates = self.rank_by_importance(candidates)

        self.stdout.write(
            f"\n  Candidates  : {len(candidates)}"
            f"\n  Top story   : {candidates[0]['title'][:55]}"
            f"\n  Top score   : {candidates[0]['final_score']} "
            f"({candidates[0]['source_count']} sources, {candidates[0]['score']} keywords)\n"
        )

        # Walk ALL candidates in rank order until `limit` are successfully saved.
        # Any article where full text scraping fails is skipped entirely.
        saved = 0
        attempted = 0

        for item in candidates:
            if saved >= limit:
                break

            attempted += 1
            self.stdout.write(
                f"  [score:{item['final_score']:3d} | sources:{item['source_count']} | kw:{item['score']}] "
                f"{item['title'][:50]}..."
            )

            real_url = self.decode_google_news_url(item["url"])
            body = self.scrape(real_url)

            if not body:
                self.stdout.write("  |- [FAIL] Scrape failed, trying next candidate\n")
                continue

            self.stdout.write(f"  |- [OK] Scraped ({len(body):,} chars)")

            GeopoliticalNews.objects.create(
                url=item["url"][:800],
                title=item["title"][:500],
                source_name=item["source_name"][:255],
                content=body,
                category=category,
                published_at=item["published_at"],
            )
            saved += 1
            self.stdout.write(f"  |- [SAVE] Saved: {item['title'][:50]}\n")

            time.sleep(1)

        self.stdout.write(
            f"\n[{category}] {saved} articles saved "
            f"({attempted - saved} skipped, {attempted} attempted).\n"
        )

    #  URL decoder

    def decode_google_news_url(self, url):
        """
        Decode a Google News RSS URL to the real article URL.
        Uses googlenewsdecoder first, falls back to requests redirect follow.
        """
        if "news.google.com" not in url:
            return url

        # Attempt 1: googlenewsdecoder — no HTTP request needed
        try:
            result = new_decoderv1(url)
            if result.get("status") and result.get("decoded_url"):
                decoded = result["decoded_url"]
                self.stdout.write(f"  |- Decoded -> {decoded[:80]}")
                return decoded
        except Exception as e:
            self.stdout.write(f"  |- Decoder failed ({e}), trying redirect...")

        # Attempt 2: follow HTTP redirects
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10, allow_redirects=True)
            final = resp.url
            if "news.google.com" not in final:
                self.stdout.write(f"  |- Redirected -> {final[:80]}")
                return final
        except Exception as e:
            self.stdout.write(f"  |- Redirect failed ({e})")

        return url

    # Scraper

    def scrape(self, url):
        """
        Fetch and extract full article text using trafilatura.
        Returns clean text or None if content is insufficient.
        """
        try:
            downloaded = trafilatura.fetch_url(url)
            if not downloaded:
                return None

            text = trafilatura.extract(
                downloaded,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                favor_recall=True,
            )

            if text and len(text.strip()) > 200:
                return text.strip()
            return None

        except Exception as e:
            self.stderr.write(f"  trafilatura failed: {url[:60]} — {e}")
            return None

    # Ranking

    def rank_by_importance(self, candidates):
        now = datetime.now(dt_timezone.utc)

        title_groups = defaultdict(list)
        for c in candidates:
            fingerprint = " ".join(c["title"].lower().split()[:5])
            title_groups[fingerprint].append(c)

        for c in candidates:
            fingerprint = " ".join(c["title"].lower().split()[:5])
            source_count = len(title_groups[fingerprint])

            age_hours = (now - c["published_at"]).total_seconds() / 3600
            if age_hours <= 2:
                recency = 5
            elif age_hours <= 4:
                recency = 2
            else:
                recency = 0

            c["final_score"] = (source_count * 5) + (c["score"] * 2) + recency
            c["source_count"] = source_count

        candidates.sort(key=lambda x: x["final_score"], reverse=True)

        seen = set()
        unique = []
        for c in candidates:
            fingerprint = " ".join(c["title"].lower().split()[:5])
            if fingerprint not in seen:
                seen.add(fingerprint)
                unique.append(c)

        return unique

    def scrape_full_text(self, url):
        """
        Public helper to scrape a single URL. 
        Handles URL resolution and the browser lifecycle.
        """
        # 1. Resolve URL (follow redirects)
        real_url = self.decode_google_news_url(url)
        
        # 2. Scrape logic
        body = None
        
        # Check if browser state is initialized
        if not hasattr(self, '_browser'):
            self._browser = None
            self._playwright_ctx = None
            self._p = None

        browser_was_open = self._browser is not None
        if not browser_was_open:
            self._launch_playwright()
            
        try:
            # Try Playwright first
            body = self.scrape_with_playwright(real_url)
            
            # If Playwright fails, try newspaper3k
            if not body:
                body = self.scrape_with_newspaper(real_url)
        finally:
            # Only close it if we were the ones who opened it
            if not browser_was_open:
                self._close_playwright()
                
        return body or "Content unavailable (could not scrape this site)."

    # ── Playwright lifecycle ──────────────────────────────────────────────────

    def _launch_playwright(self):
        if self._browser:
            return
        self.stdout.write("  [System] Launching Playwright...")
        self._p = sync_playwright().start()
        self._browser = self._p.chromium.launch(headless=True)
        self._playwright_ctx = self._browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        )

    def _close_playwright(self):
        if self._browser:
            self.stdout.write("  [System] Closing Playwright...")
            self._browser.close()
            self._p.stop()
            self._browser = None
            self._playwright_ctx = None
            self._p = None

    def scrape_with_playwright(self, url):
        """
        Scrape dynamic content using Playwright.
        """
        page = self._playwright_ctx.new_page()
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=30000)
            time.sleep(2)  # Wait for any JS hydration
            content = page.content()
            text = trafilatura.extract(content, favor_recall=True)
            page.close()
            if text and len(text.strip()) > 300:
                return text.strip()
            return None
        except Exception as e:
            self.stdout.write(f"  |- [WARN]  Playwright error: {str(e)[:50]}")
            try:
                page.close()
            except Exception:
                pass
            return None

    def scrape_with_newspaper(self, url):
        """
        Fallback scraper using newspaper3k.
        """
        config = Config()
        config.browser_user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        config.request_timeout = 15
        try:
            article = Article(url, config=config)
            article.download()
            article.parse()
            text = article.text.strip()
            return text if len(text) > 300 else None
        except Exception:
            return None

    def relevance_score(self, title, summary, keywords):
        title_lower = title.lower()
        summary_lower = summary.lower()
        score = 0
        for kw in keywords:
            if kw in title_lower:
                score += 2
            elif kw in summary_lower:
                score += 1
        return score

    def parse_entry_date(self, entry):
        for field in ("published", "updated", "created"):
            raw = entry.get(field)
            if raw:
                try:
                    dt = parsedate_to_datetime(raw)
                    if dt:
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=dt_timezone.utc)
                        return dt.astimezone(dt_timezone.utc)
                except Exception:
                    continue

        for field in ("published_parsed", "updated_parsed"):
            parsed = entry.get(field)
            if parsed and len(parsed) >= 6:
                try:
                    return datetime(*parsed[:6], tzinfo=dt_timezone.utc)
                except Exception:
                    continue
        return None

    def strip_html(self, text):
        from html.parser import HTMLParser
        import html

        class _Stripper(HTMLParser):
            def __init__(self):
                super().__init__()
                self.parts = []

            def handle_data(self, data):
                self.parts.append(data)

        stripper = _Stripper()
        stripper.feed(html.unescape(text))
        return " ".join(stripper.parts).strip()
