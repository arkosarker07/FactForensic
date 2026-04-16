import time
import feedparser
import requests
from datetime import datetime, timedelta, timezone as dt_timezone
from urllib.parse import urlparse
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
    # Sports
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
    "bowling coach",
    "spin bowling",
    "batting",
    "wicket",
    "innings",
    "knicks",
    "bulls",
    "lakers",
    "rapinoe",
    "mcmahon",
    "broadcaster",
    "slam dunk",
    "playoffs",
    "world cup qualif",
    # Crypto / Finance fluff
    "bitcoin",
    "crypto",
    "blockchain",
    "nft",
    # Entertainment / Lifestyle
    "recipe",
    "movie",
    "celebrity",
    "fashion",
    "entertainment",
    "horoscope",
    "lifestyle",
    "travel",
    "food",
    "health tips",
    # Sports streaming
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
    # Weather
    "weather",
    "thundershower",
    "heatwave",
    "heat wave",
    "temperature forecast",
    "rainfall forecast",
    "met office",
    # Education / Academia (not political)
    "accreditation",
    "university ranking",
    "campus",
    "music education",
    # Misc fluff
    "podcast",
    "live blog",
    "live updates",
    "thread",
    "explainer",
    "deals",
    "shopping",
    "review",
    "fine paper",
]

# URL path segments that indicate non-political content
URL_PATH_BLOCKLIST = [
    "/sport/",
    "/sports/",
    "/entertainment/",
    "/lifestyle/",
    "/features/panorama/",
    "/features/beyond-",
    "/weather/",
    "/food/",
    "/travel/",
    "/health/",
    "/shopping/",
    "/style/",
    "/education/",
    "/power-energy/",
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
    "policy",
    "law",
    "human rights",
    "budget",
    "court",
    "justice",
    "senate",
    "congress",
    "supreme court",
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
    "policy",
    "law",
    "human rights",
    "justice",
    "supreme court",
    "high court",
    "bgb",
    "rab",
    "police",
]

WORLD_FEEDS = [
    (
        "BBC News",
        "Center",
        "https://news.google.com/rss/search?q=site:bbc.com/news/world&hl=en-US&gl=US&ceid=US:en",
    ),
    (
        "Al Jazeera",
        "Left",
        "https://news.google.com/rss/search?q=site:aljazeera.com+world&hl=en-US&gl=US&ceid=US:en",
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
    (
        "Google Top World",
        "Mixed",
        "https://news.google.com/news/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en",
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
        import os

        os.environ["DJANGO_ALLOW_ASYNC_UNSAFE"] = "true"
        self.stdout.write(f"\n[START] {timezone.now().strftime('%Y-%m-%d %H:%M')}")

        # Initialize browser state for both automated and single-use scrapes
        self._browser = None
        self._playwright_ctx = None
        self._p = None

        try:
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
        finally:
            self._close_playwright()

        self.stdout.write(f"\n[DONE] {timezone.now().strftime('%Y-%m-%d %H:%M')}")

    # Main pipeline

    def process_feeds(self, feeds, category, limit, bd_filter, relevance_keywords):
        cutoff = datetime.now(dt_timezone.utc) - timedelta(hours=24)
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
                self.stdout.write("  |- 0 entries")
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

                # STRICT FILTERING: Must contain relevance keywords
                # BD needs >=2 to filter fluff but not starve the pipeline
                min_score = 2 if bd_filter else 1
                if score < min_score:
                    continue

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

            # STRICT FILTERING: Reject generic category/thread pages
            # And reject URLs whose path indicates non-political content
            if self._is_category_page(real_url):
                self.stdout.write("  |- [SKIP] Category/index page, not an article\n")
                continue

            if any(seg in real_url.lower() for seg in URL_PATH_BLOCKLIST):
                self.stdout.write(
                    "  |- [SKIP] URL path indicates non-political content\n"
                )
                continue

            body = self.scrape(real_url)

            if not body:
                self.stdout.write("  |- [FAIL] Scrape failed, trying next candidate\n")
                continue

            self.stdout.write(f"  |- [OK] Scraped ({len(body):,} chars)")

            # Get objectivity score from Groq
            from pages.utils import get_groq_objectivity_score, get_hf_bias

            obj_score = get_groq_objectivity_score(body)
            self.stdout.write(f"  |- [GROQ] Objectivity score: {obj_score}")

            # Run HF bias model on article text; fall back to source bias
            source_bias = item.get("bias", "Center")
            try:
                hf_label = get_hf_bias(body[:2000])
                bias_label = hf_label if hf_label else source_bias
                self.stdout.write(f"  |- [HF]   Bias: {bias_label}")
            except Exception as e:
                bias_label = source_bias
                self.stdout.write(f"  |- [HF]   Failed ({e}), using source bias: {bias_label}")

            if "left" in bias_label.lower():
                bias_score_val = -1.0
            elif "right" in bias_label.lower():
                bias_score_val = 1.0
            else:
                bias_score_val = 0.0

            GeopoliticalNews.objects.create(
                url=item["url"][:800],
                title=item["title"][:500],
                source_name=item["source_name"][:255],
                content=body,
                category=category,
                published_at=item["published_at"],
                objectivity_score=obj_score,
                bias_score=bias_score_val,
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

    # Category page detector

    def _is_category_page(self, url):
        """
        Detect if a URL is a category/index page rather than an article.
        Checks the last path segment for article-like patterns (slugs, IDs).
        """
        parsed = urlparse(url)
        path = parsed.path.rstrip("/")
        segments = [s for s in path.split("/") if s]

        # Root or single-segment paths are always category pages (e.g., /news)
        if len(segments) <= 1:
            return True

        last = segments[-1]

        # Explicit non-article page types
        NON_ARTICLE_PATHS = [
            "/where/",
            "/live/",
            "/video/",
            "/audio/",
            "/podcast/",
            "/live-blog/",
        ]
        if any(p in url.lower() for p in NON_ARTICLE_PATHS):
            return True

        # Article slugs almost always contain hyphens (trump-files-emergency-motion)
        # OR are long alphanumeric IDs (e9956423cd796c1dbdbb42e)
        if "-" in last or len(last) > 8:
            return False  # Looks like an article

        # 2 segments where last is a short word without hyphens = category
        # e.g., /world/middleeast or /news/asia
        if len(segments) == 2:
            return True

        # 3+ segments with a non-slug last segment = likely a category index
        return True

    # Scraper

    def scrape(self, url):
        """
        Fetch and extract full article text.
        Strategy: trafilatura first, then newspaper3k fallback.
        Returns clean text or None if content is insufficient.
        """
        MIN_TEXT_LEN = 150

        # ── Attempt 1: trafilatura ──
        try:
            downloaded = trafilatura.fetch_url(url)
            if downloaded:
                text = trafilatura.extract(
                    downloaded,
                    include_comments=False,
                    include_tables=False,
                    no_fallback=False,
                    favor_recall=True,
                )
                if text and len(text.strip()) > MIN_TEXT_LEN:
                    return text.strip()
        except Exception as e:
            self.stderr.write(f"  trafilatura failed: {url[:60]} — {e}")

        # ── Attempt 2: Playwright fallback (for 401s and Cloudflare) ──
        try:
            # Ensure the browser instance is launched
            self._launch_playwright()
            text = self.scrape_with_playwright(url)
            if text and len(text.strip()) > MIN_TEXT_LEN:
                return text.strip()
        except Exception as e:
            self.stderr.write(f"  Playwright fallback failed: {url[:60]} — {e}")

        # ── Attempt 3: newspaper3k fallback ──
        try:
            config = Config()
            config.browser_user_agent = HEADERS["User-Agent"]
            config.request_timeout = 15
            article = Article(url, config=config)
            article.download()
            article.parse()
            text = article.text.strip()
            if len(text) > MIN_TEXT_LEN:
                return text
        except Exception as e:
            self.stderr.write(f"  newspaper3k failed: {url[:60]} — {e}")

        return None

    # Ranking

    def rank_by_importance(self, candidates):
        import re

        now = datetime.now(dt_timezone.utc)

        # 0. Deduplicate by decoded URL to prevent the same article appearing multiple times
        seen_urls = set()
        deduped = []
        for c in candidates:
            url_key = c["url"].split("?")[0].rstrip("/").lower()
            if url_key not in seen_urls:
                seen_urls.add(url_key)
                deduped.append(c)
        candidates = deduped

        # 1. Generate clean token sets for Jaccard Similarity clustering
        for c in candidates:
            # clean title: lowercase, drop punctuation, drop small words
            words = re.findall(r"\b[a-z]{4,}\b", c["title"].lower())
            c["tokens"] = set(words)

        # 2. Cluster candidates using generic Jaccard Similarity (>= 30% overlap)
        clusters = []
        candidate_to_cluster = {}  # map candidate index -> cluster index
        for idx, c in enumerate(candidates):
            assigned = False
            for ci, cluster in enumerate(clusters):
                # Check overlap with cluster center (first item in cluster)
                center_tokens = cluster[0]["tokens"]
                union_len = len(c["tokens"].union(center_tokens))
                if union_len == 0:
                    continue
                intersection_len = len(c["tokens"].intersection(center_tokens))
                jaccard = intersection_len / union_len

                # If 30% similar, consider it the same story being reported across sites
                if jaccard >= 0.30:
                    cluster.append(c)
                    candidate_to_cluster[idx] = ci
                    assigned = True
                    break

            if not assigned:
                candidate_to_cluster[idx] = len(clusters)
                clusters.append([c])

        # 3. Assess Source Count and Final Scores
        for cluster in clusters:
            # Count unique sources in this cluster (not duplicate entries)
            unique_sources = set(c["source_name"] for c in cluster)
            source_count = len(unique_sources)
            for c in cluster:
                c["source_count"] = source_count

                age_hours = (now - c["published_at"]).total_seconds() / 3600
                if age_hours <= 2:
                    recency = 5
                elif age_hours <= 4:
                    recency = 2
                else:
                    recency = 0

                c["final_score"] = (source_count * 5) + (c["score"] * 2) + recency

        # 4. Sort candidates
        candidates.sort(key=lambda x: x["final_score"], reverse=True)

        # 5. Deduplicate so we only fetch 1 representative per cluster
        # Pick the highest-scored article from each cluster
        seen_cluster_ids = set()
        unique = []
        for idx, c in enumerate(candidates):
            # Look up which cluster this candidate belongs to
            orig_idx = deduped.index(c) if c in deduped else idx
            cluster_id = candidate_to_cluster.get(orig_idx)
            if cluster_id is not None and cluster_id not in seen_cluster_ids:
                seen_cluster_ids.add(cluster_id)
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
        if not hasattr(self, "_browser"):
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
        import re

        title_lower = title.lower()
        summary_lower = summary.lower()
        score = 0
        for kw in keywords:
            # Need to escape kw to avoid regex errors, and ensure \b doesn't break on hyphens
            kw_escaped = re.escape(kw)
            pattern = rf"(?:\b|\s){kw_escaped}(?:\b|\s)"

            if re.search(pattern, title_lower):
                score += 2
            elif re.search(pattern, summary_lower):
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
