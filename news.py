"""Real news, re-leveled (news_relevel format).

RSS, not an API — see config.py's comment next to NEWS_FEEDS for why:
no credential to expire, get rate-limited, or need billing attention. The
only failure mode is "is the internet reachable", which every other step
in this pipeline already depends on too.

Pulls from several long-running BBC topic feeds rather than one, so a
single feed being briefly down doesn't stall the day's post — the fetcher
just tries the rest. From whatever comes back:

- Dedup: skip anything whose link/GUID is in the rolling "seen" set kept
  in memory.json (same file that already tracks avoid/covered topics).
- Tone filter: a plain keyword denylist (config.NEWS_DENYLIST_KEYWORDS) —
  a mechanical filter the admin controls and can edit, not an editorial
  call made in code.
- Simplicity filter: prefer shorter, more concrete summaries over long
  analysis/opinion pieces, since those re-level more cleanly at A1/A2.

fetch_news_item() never raises out to the caller — a feed hiccup degrades
to "no news today" (main.py falls back to DEFAULT_EXTRA_SLOT_FORMAT), not
a broken run.
"""

import re

try:
    import feedparser
except ImportError:  # pragma: no cover - see requirements.txt
    feedparser = None

from config import NEWS_FEEDS, NEWS_DENYLIST_KEYWORDS, NEWS_SEEN_MAX

NEWS_SEEN_KEY = "news_seen_links"


def _seen_links(memory):
    return memory.setdefault(NEWS_SEEN_KEY, [])


def _mark_seen(memory, link):
    seen = _seen_links(memory)
    seen.append(link)
    # Trim from the front so the set stays a rolling window, not an
    # ever-growing list inside memory.json.
    if len(seen) > NEWS_SEEN_MAX:
        del seen[: len(seen) - NEWS_SEEN_MAX]


def _is_denylisted(text):
    lowered = text.lower()
    return any(word in lowered for word in NEWS_DENYLIST_KEYWORDS)


def _clean_summary(raw_summary):
    """RSS summaries are frequently HTML — strip tags before showing the
    model anything, since our own prompts are HTML-formatted and a stray
    <a href=...> from a feed would confuse that."""
    return re.sub(r"<[^>]+>", "", raw_summary or "").strip()


def fetch_news_item(memory):
    """Returns {'title', 'summary', 'link', 'source'} or None (empty/failed
    feeds, or everything filtered out). Marks the chosen item as seen in
    memory (caller is responsible for eventually saving memory.json, same
    as every other memory-mutating helper in this codebase)."""
    if feedparser is None:
        print("news.fetch_news_item: feedparser not installed, skipping.")
        return None

    seen = set(_seen_links(memory))
    candidates = []

    for feed_url in NEWS_FEEDS:
        try:
            parsed = feedparser.parse(feed_url)
        except Exception as exc:  # noqa: BLE001 — one bad feed must not sink the rest
            print(f"news.fetch_news_item: feed failed ({feed_url}):", exc)
            continue

        for entry in getattr(parsed, "entries", [])[:20]:
            link = entry.get("link") or entry.get("id")
            title = (entry.get("title") or "").strip()
            if not link or not title or link in seen:
                continue

            summary = _clean_summary(entry.get("summary", ""))
            if _is_denylisted(f"{title} {summary}"):
                continue

            candidates.append({
                "title": title,
                "summary": summary or title,
                "link": link,
                "source": feed_url,
            })

    if not candidates:
        return None

    # Simplicity filter: shorter, more concrete summaries first.
    candidates.sort(key=lambda c: len(c["summary"]))
    chosen = candidates[0]
    _mark_seen(memory, chosen["link"])
    return chosen
