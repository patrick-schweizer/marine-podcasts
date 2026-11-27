# IIMS Podcast Feeds

Unofficial RSS podcast feeds generated from the
[IIMS podcast archive](https://www.iims.org.uk/podcasts/).

Three feeds, regenerated daily:

- **Small Craft News Bulletin** (monthly series):
  `https://patrick-schweizer.github.io/marine-podcasts/feeds/small-craft-news-bulletin.rss`
- **Cargo & Commercial News Bulletin** (monthly series):
  `https://patrick-schweizer.github.io/marine-podcasts/feeds/cargo-commercial-news-bulletin.rss`
- **Train as you Travel** (IIMS podcast category):
  `https://patrick-schweizer.github.io/marine-podcasts/feeds/train-as-you-travel.rss`

An up-to-date list is also served at
`https://patrick-schweizer.github.io/marine-podcasts/` (index.html).

The site has no series taxonomy, so the two bulletin series are identified by
their episode titles (case-insensitive, tolerant of the site's title
variations). The `news-bulletin-podcasts` category is intentionally not
published as its own feed because its episodes all belong to those two series.
Other IIMS categories are discovered automatically from the site's
`podcast_category` sitemap and get a feed each.

A GitHub Action regenerates all feeds daily at 06:00 UTC (and on demand via
the **Run workflow** button on the Actions tab). All audio is hosted by IIMS;
this repository only publishes an index of it.

## Setup

1. Enable GitHub Pages: **Settings → Pages → Build and deployment → Source:
   Deploy from a branch**, branch `main`, folder `/ (root)`.
2. Run the workflow once so `feeds/*.rss` exist before adding the URLs to
   your podcast app (Apple Podcasts, Pocket Casts, Overcast, AntennaPod, ...).

## Notes

- Episodes whose publish date cannot be discovered are sorted last and get
  the build date; most pages expose `article:published_time`, which the
  script reads.
- Audio files are `.mp3` or `.m4a` on IIMS S3 buckets; the enclosure
  `type` is set accordingly.
- MP3/M4A file sizes are fetched with a HEAD request for the `<enclosure
  length>`; if the server refuses, it falls back to `0`, which most podcast
  apps tolerate.
- Members-only episodes have no public audio URL and are skipped.
- The generator is an unofficial scraper: if IIMS changes their site layout,
  the script may need a small tweak. Check the failed workflow run's logs to
  see where it stopped.
