#!/usr/bin/env python3
"""Generate podcast RSS feeds from the IIMS podcast archive.

Standard library only: no pip install needed.

Writes one feed.xml at repo root containing every episode, plus one
feeds/<category>.xml per IIMS podcast category (discovered from the site's
podcast_category sitemap).
"""

import email.utils
import re
import sys
import urllib.request
from datetime import datetime, timezone
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin

SITE = "https://www.iims.org.uk/podcasts/"
CATEGORIES_SITEMAP = "https://www.iims.org.uk/podcast_category-sitemap.xml"
ARCHIVE_TITLE = "IIMS Podcasts"
DESCRIPTION = (
    "Audio podcasts from the International Institute of Marine Surveying (IIMS). "
    "Unofficial feed generated from iims.org.uk/podcasts."
)
LANGUAGE = "en-gb"
AUTHOR = "IIMS"
ITUNES_CATEGORY = "Education"

# Series within the episode list. There is no series taxonomy on the site,
# so membership is derived from the episode title (case-insensitive matching).
SERIES = [
    {
        "slug": "small-craft-news-bulletin",
        "title": "IIMS Small Craft News Bulletin Podcast",
        "all_terms": ("small craft", "podcast"),
        "any_terms": (),
    },
    {
        "slug": "cargo-commercial-news-bulletin",
        "title": "IIMS Cargo & Commercial News Bulletin Podcast",
        "all_terms": ("podcast",),
        "any_terms": ("cargo", "commercial"),
    },
]

# Public base URL of this GitHub Pages site.
PAGES_BASE = "https://patrick-schweizer.github.io/marine-podcasts"

OUTPUT = Path(__file__).resolve().parent.parent / "feed.xml"
FEEDS_DIR = Path(__file__).resolve().parent.parent / "feeds"
USER_AGENT = "Mozilla/5.0 (compatible; iims-feed-generator/1.0; personal use)"
TIMEOUT = 30

# Archive pagination appears as "Page 1 of 13"; we discover it, but cap defensively.
MAX_PAGES_CAP = 50


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return resp.read().decode("utf-8", errors="replace")


def head_size(url: str) -> int:
    """Best-effort Content-Length for the enclosure (0 if unknown)."""
    try:
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT}, method="HEAD")
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return int(resp.headers.get("Content-Length") or 0)
    except Exception:
        return 0


class LinkCollector(HTMLParser):
    """Collects hrefs and the text of headings/meta, kept minimal."""

    def __init__(self):
        super().__init__()
        self.links = []
        self.meta = {}
        self.h1_parts = []
        self._in_h1 = False
        self._active_h1_parts = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "a" and a.get("href"):
            self.links.append(a["href"])
        elif tag == "meta" and a.get("property"):
            self.meta[a["property"]] = a.get("content", "")
        elif tag == "time" and a.get("datetime"):
            self.meta.setdefault("time:datetime", a["datetime"])
        elif tag == "h1":
            self._in_h1 = True
            self._active_h1_parts = []

    def handle_endtag(self, tag):
        if tag == "h1" and self._in_h1:
            self._in_h1 = False
            text = "".join(self._active_h1_parts or []).strip()
            if text:
                self.h1_parts.append(text)
            self._active_h1_parts = None

    def handle_data(self, data):
        if self._in_h1 and self._active_h1_parts is not None:
            self._active_h1_parts.append(data)


def parse(html: str) -> LinkCollector:
    p = LinkCollector()
    p.feed(html)
    p.close()
    return p


def episode_urls_from_archive(html: str) -> list[str]:
    p = parse(html)
    urls = []
    for href in p.links:
        absolute = urljoin(SITE, href)
        # Episode pages live directly under /podcasts/<slug>/
        m = re.match(r"^https://www\.iims\.org\.uk/podcasts/([^/?#]+)/?$", absolute)
        if not m:
            continue
        if absolute not in urls:
            urls.append(absolute)
    return urls


def last_page_number(html: str) -> int:
    m = re.search(r"Page \d+ of (\d+)", html)
    return int(m.group(1)) if m else 1


def discover_categories() -> list[dict]:
    """Category archives, discovered from the site's podcast_category sitemap."""
    try:
        xml = fetch(CATEGORIES_SITEMAP)
    except Exception as exc:
        print(f"Could not fetch category sitemap ({exc}); generating the combined feed only.", file=sys.stderr)
        return []
    categories = []
    seen = set()
    for m in re.finditer(r"<loc>(https://www\.iims\.org\.uk/podcast_category/([^/<]+)/)</loc>", xml):
        url, slug = m.group(1), m.group(2)
        if slug not in seen:
            seen.add(slug)
            categories.append({"slug": slug, "url": url})
    return categories


AUDIO_EXTENSIONS = ("mp3", "m4a", "aac", "ogg", "wav")
MIME_TYPES = {
    "mp3": "audio/mpeg",
    "m4a": "audio/mp4",
    "aac": "audio/aac",
    "ogg": "audio/ogg",
    "wav": "audio/wav",
}


def audio_mime(url: str) -> str:
    ext = url.rsplit(".", 1)[-1].lower()
    return MIME_TYPES.get(ext, "audio/mpeg")


def extract_audio(html: str) -> str | None:
    # Audio files live on the site's S3 buckets, as .mp3 or .m4a.
    exts = "|".join(AUDIO_EXTENSIONS)
    m = re.search(rf'https://[^"\'>\s]+\.({exts})\b', html, re.I)
    return unescape(m.group(0)) if m else None


def extract_title(html: str, url: str) -> str:
    p = parse(html)
    og = p.meta.get("og:title")
    if og:
        title = re.sub(r"\s*-\s*The International Institute.*$", "", unescape(og)).strip()
        if title:
            return title
    m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    if m:
        # Strip the trailing " - The International Institute of Marine Surveying (IIMS)"
        return re.sub(r"\s*-\s*The International Institute.*$", "", unescape(m.group(1))).strip()
    return url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title()


def extract_pubdate(html: str) -> datetime | None:
    p = parse(html)
    for key in ("article:published_time", "article:modified_time", "time:datetime"):
        value = p.meta.get(key)
        if not value:
            continue
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def extract_duration_seconds(html: str) -> int | None:
    # Pages state e.g. "Approx. 24 minutes" or "Runtime approx. 23 minutes".
    m = re.search(r"approx\.?\s*(\d+)\s*(minutes?|mins?)", html, re.I)
    if not m:
        m = re.search(r"(\d+)\s*(minutes?|mins?)", html, re.I)
    if m:
        return int(m.group(1)) * 60
    hms = re.search(r"\b(\d+):(\d{2}):(\d{2})\b", html)
    if hms:
        h, mn, s = (int(g) for g in hms.groups())
        return h * 3600 + mn * 60 + s
    return None


def extract_section_title(html: str, fallback: str) -> str:
    p = parse(html)
    og = p.meta.get("og:title")
    if og:
        # "Train as you Travel Archives - The International Institute of ..."
        return re.sub(r"\s+Archives?\s*-.*$", "", unescape(og)).strip() or fallback
    return fallback


def iso_duration(seconds: int) -> str:
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    out = "PT"
    if h:
        out += f"{h}H"
    if m:
        out += f"{m}M"
    if s or out == "PT":
        out += f"{s}S"
    return out


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def get_episode(url: str, cache: dict) -> dict | None:
    """Fetch and parse an episode page once, even if listed in several archives."""
    if url in cache:
        return cache[url]
    try:
        html = fetch(url)
        audio = extract_audio(html)
        if not audio:
            print(f"  no audio file found, skipping: {url}", file=sys.stderr)
            cache[url] = None
            return None
        cache[url] = {
            "url": url,
            "audio": audio,
            "title": extract_title(html, url),
            "pubdate": extract_pubdate(html),
            "duration": extract_duration_seconds(html),
        }
    except Exception as exc:  # keep going on single-page failures
        print(f"  error fetching {url}: {exc}", file=sys.stderr)
        cache[url] = None
    return cache[url]


def series_match(title: str, series: dict) -> bool:
    t = title.lower()
    return all(term in t for term in series["all_terms"]) and (
        not series["any_terms"] or any(term in t for term in series["any_terms"])
    )


def newest_first(episodes: list[dict]) -> list[dict]:
    return sorted(
        episodes,
        key=lambda e: e["pubdate"] or datetime(1970, 1, 1, tzinfo=timezone.utc),
        reverse=True,
    )


def collect_section(section_url: str, cache: dict) -> tuple[list[dict], str]:
    """Crawl one paginated archive (the main list or a category) for episodes."""
    first = fetch(section_url)
    pages = min(last_page_number(first), MAX_PAGES_CAP)
    section_title = extract_section_title(first, section_url.rstrip("/").rsplit("/", 1)[-1].replace("-", " ").title())
    print(f"Archive {section_url}: {pages} page(s)")

    episode_urls: list[str] = []
    for n in range(2, pages + 1):
        page_url = f"{section_url.rstrip('/')}/page/{n}/"
        try:
            episode_urls.extend(episode_urls_from_archive(fetch(page_url)))
        except Exception as exc:
            print(f"  error fetching {page_url}: {exc}", file=sys.stderr)
    episode_urls.extend(episode_urls_from_archive(first))
    episode_urls = [u for u in dict.fromkeys(episode_urls) if u != SITE]

    episodes = []
    for i, url in enumerate(episode_urls, 1):
        ep = get_episode(url, cache)
        if ep:
            episodes.append(ep)
            print(f"  [{i}] {ep['title']}")
    return newest_first(episodes), section_title


def build_feed(channel_title: str, self_url: str, description: str, episodes: list[dict]) -> str:
    now = email.utils.format_datetime(datetime.now(timezone.utc))
    items = []
    for ep in episodes:
        pub = email.utils.format_datetime(ep["pubdate"]) if ep["pubdate"] else now
        duration = iso_duration(ep["duration"]) if ep["duration"] else ""
        items.append(
            f"""    <item>
      <title>{esc(ep["title"])}</title>
      <link>{esc(ep["url"])}</link>
      <guid isPermaLink="true">{esc(ep["url"])}</guid>
      <pubDate>{pub}</pubDate>
      <itunes:author>{esc(AUTHOR)}</itunes:author>
      {f"<itunes:duration>{duration}</itunes:duration>" if duration else ""}
      <enclosure url="{esc(ep["audio"])}" length="{head_size(ep["audio"])}" type="{audio_mime(ep["audio"])}"/>
    </item>"""
        )

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{esc(channel_title)}</title>
    <link>{esc(SITE)}</link>
    <description>{esc(description)}</description>
    <language>{LANGUAGE}</language>
    <itunes:author>{esc(AUTHOR)}</itunes:author>
    <itunes:explicit>false</itunes:explicit>
    <itunes:category text="{ITUNES_CATEGORY}"/>
    <atom:link href="{esc(self_url)}" rel="self" type="application/rss+xml"/>
    <lastBuildDate>{now}</lastBuildDate>
{chr(10).join(items)}
  </channel>
</rss>
"""


def write_feed(path: Path, channel_title: str, self_url: str, description: str, episodes: list[dict]) -> None:
    if not episodes:
        if path.exists():
            print(f"Skipping {path.name}: no episodes found, keeping the existing feed.", file=sys.stderr)
        else:
            print(f"Skipping {path.name}: no episodes found.", file=sys.stderr)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_feed(channel_title, self_url, description, episodes), encoding="utf-8")
    print(f"Wrote {path} with {len(episodes)} episodes")


def main() -> None:
    cache: dict = {}

    all_episodes, _ = collect_section(SITE, cache)
    if not all_episodes:
        print("No episodes found; refusing to overwrite an existing feed with an empty one.", file=sys.stderr)
        sys.exit(1)
    write_feed(OUTPUT, ARCHIVE_TITLE, f"{PAGES_BASE}/feed.xml", DESCRIPTION, all_episodes)

    categorized: set[str] = set()
    for cat in discover_categories():
        print(f"Category: {cat['slug']}")
        episodes, section_title = collect_section(cat["url"], cache)
        categorized.update(ep["url"] for ep in episodes)
        feed_path = FEEDS_DIR / f"{cat['slug']}.xml"
        write_feed(
            feed_path,
            f"IIMS Podcasts — {section_title}",
            f"{PAGES_BASE}/feeds/{cat['slug']}.xml",
            f"{section_title} audio podcasts from the International Institute of Marine Surveying (IIMS). "
            "Unofficial feed generated from iims.org.uk/podcasts.",
            episodes,
        )

    uncategorised = [ep for ep in all_episodes if ep["url"] not in categorized]
    print(
        f"Done: {len(all_episodes)} episodes total, "
        f"{len(uncategorised)} not in any category (combined feed only)."
    )

    for series in SERIES:
        episodes = [ep for ep in all_episodes if series_match(ep["title"], series)]
        write_feed(
            FEEDS_DIR / f"{series['slug']}.xml",
            series["title"],
            f"{PAGES_BASE}/feeds/{series['slug']}.xml",
            f"{series['title']} — audio podcasts from the International Institute of "
            "Marine Surveying (IIMS). Unofficial feed generated from iims.org.uk/podcasts.",
            episodes,
        )


if __name__ == "__main__":
    main()
