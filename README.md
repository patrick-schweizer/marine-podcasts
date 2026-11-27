# IIMS Podcast Feeds

Unofficial RSS podcast feeds generated from the
[IIMS podcast archive](https://www.iims.org.uk/podcasts/).

One feed per IIMS podcast category, plus a combined feed with everything.
Categories are discovered automatically from the site's `podcast_category`
sitemap, so new ones appear without code changes.

**Combined feed (all episodes):**
`https://patrick-schweizer.github.io/marine-podcasts/feed.xml`

**Category feeds:**
- News Bulletins: `https://patrick-schweizer.github.io/marine-podcasts/feeds/news-bulletin-podcasts.xml`
- Train as you Travel: `https://patrick-schweizer.github.io/marine-podcasts/feeds/train-as-you-travel.xml`

An up-to-date list is also served at
`https://patrick-schweizer.github.io/marine-podcasts/` (index.html).

A GitHub Action regenerates all feeds daily at 06:00 UTC (and on demand via
the **Run workflow** button on the Actions tab). All audio is hosted by IIMS;
this repository only publishes an index of it.

## Setup

1. Enable GitHub Pages: **Settings → Pages → Build and deployment → Source:
   Deploy from a branch**, branch `main`, folder `/ (root)`.
2. Run the workflow once so `feed.xml` and `feeds/*.xml` exist before adding
   the URLs to your podcast app (Apple Podcasts, Pocket Casts, Overcast,
   AntennaPod, ...).

## Notes

- Episodes whose publish date cannot be discovered are sorted last and get
  the build date; most pages expose `article:published_time`, which the
  script reads.
- MP3 file sizes are fetched with a HEAD request for the `<enclosure
  length>`; if the server refuses, it falls back to `0`, which most podcast
  apps tolerate.
- Members-only episodes have no public MP3 URL and are skipped.
- The generator is an unofficial scraper: if IIMS changes their site layout,
  the script may need a small tweak. Check the failed workflow run's logs to
  see where it stopped.
