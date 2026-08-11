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

Each feed is fetched with `requests` under an explicit timeout and a
non-default User-Agent (config.NEWS_REQUEST_TIMEOUT / NEWS_USER_AGENT)
before being handed to feedparser — feedparser.parse() has no timeout
parameter of its own, so calling it directly on a URL can hang
indefinitely if a connection stalls rather than actively fails.

fetch_news_item() never raises out to the caller — a feed hiccup degrades
to "no news today" (main.py falls back to DEFAULT_EXTRA_SLOT_FORMAT), not
a broken run. What it can't fix on its own is a *permanent* break (feed
URLs retired/renamed, the whole domain blocked) — left alone, that would
silently degrade forever and nobody would notice. health_alert_needed()
tracks consecutive empty attempts so main.py can raise that to the admin
exactly once per bad streak, instead of every run or never.
"""

import re

try:
    import feedparser
except ImportError:  # pragma: no cover - see requirements.txt
    feedparser = None

try:
    import requests
except ImportError:  # pragma: no cover - see requirements.txt
    requests = None

from config import (
    NEWS_FEEDS, NEWS_DENYLIST_KEYWORDS, NEWS_SEEN_MAX,
    NEWS_REQUEST_TIMEOUT, NEWS_USER_AGENT, NEWS_FAILURE_ALERT_THRESHOLD,
)

NEWS_SEEN_KEY = "news_seen_links"
# Consecutive fetch_news_item() calls in a row that returned nothing at
# all (network failure, parse failure, or every candidate filtered out).
# Reset to 0 the moment any call succeeds.
NEWS_FAILURE_STREAK_KEY = "news_consecutive_failures"
# Whether we've already sent the admin alert for the *current* streak, so
# a broken feed doesn't re-alert every single run once past the threshold.
NEWS_ALERTED_KEY = "news_health_alerted"


# Bug fix (#45): this used to be a plain substring check (`word in
# lowered`), which matches a denylist word anywhere inside a longer,
# unrelated word — verified directly against the real keyword list:
# "war" matched inside software/hardware/award/warning/forward/backward/
# toward/warehouse/warm/reward/wardrobe/awkward/warranty/warp; "dead"
# matched deadline/deadlock/deadpan; "dies" matched studies/bodies/
# ladies/candies/remedies/comedies/tragedies/melodies/parodies; "rape"
# matched grape/grapes/drape/draped. Since NEWS_FEEDS includes BBC's
# technology/science feeds, ordinary headlines like "New software
# update..." or "Study shows..." were being silently discarded as
# violent/distressing content.
#
# Now requires a word boundary before the keyword (so "war" can never
# match while still glued to "soft"/"ware"/etc.), and allows a common
# inflectional suffix (-s/-es/-ed/-ing) after it before the closing
# boundary, so this doesn't just trade false positives for false
# negatives on ordinary inflected forms: "attacked", "bombed", "raped",
# "killing" etc. still match (they wouldn't with a bare \bword\b), while
# "software"/"warehouse"/"studies"/"grape" still correctly don't.
_DENYLIST_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in NEWS_DENYLIST_KEYWORDS) + r")(?:e?[sd]|ing)?\b",
    re.IGNORECASE,
)

# Bug fix (#47): this used to be re.sub(r"<[^>]+>", "", ...) — the same
# any-angle-brackets pattern as channels.py's old _TAG_STRIP (#18),
# capable of eating a literal "<"/">" text span that isn't a tag at all.
# Reusing channels.py's fix directly isn't right here, though: that one
# is deliberately scoped to the small, fixed set of tags THIS PROJECT'S
# OWN generated content uses (Telegram's supported HTML subset) — but
# RSS summaries are arbitrary third-party HTML that can use any real tag
# (<div>, <p>, <ul>, <a href=...>, etc.), so a narrow allowlist would
# leave most of it unstripped. This instead requires the content between
# < and > to actually LOOK LIKE a tag (starts with a letter, optionally
# with a leading "/") rather than matching literally anything — so a
# genuine tag of any name is still stripped, while "5 < x > 1" (next
# character after "<" is a space, not a letter) or "<3" (a digit, not a
# letter) both correctly survive untouched.
_HTML_TAG_LIKE = re.compile(r"</?[a-zA-Z][a-zA-Z0-9]*(?:\s[^<>]*)?>")


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
    return bool(_DENYLIST_PATTERN.search(text))


def _clean_summary(raw_summary):
    """RSS summaries are frequently HTML — strip tags before showing the
    model anything, since our own prompts are HTML-formatted and a stray
    <a href=...> from a feed would confuse that."""
    return _HTML_TAG_LIKE.sub("", raw_summary or "").strip()


def _fetch_feed_entries(feed_url):
    """Fetch and parse one feed. Returns a list of entries, or [] on any
    failure — network error, non-2xx status, or a feed body feedparser
    can't make sense of. Never raises; every failure mode here is exactly
    as recoverable as "this one feed happened to be down", so the caller
    treats it identically to that."""
    if requests is None:
        print("news._fetch_feed_entries: requests not installed, skipping.")
        return []

    try:
        response = requests.get(
            feed_url,
            timeout=NEWS_REQUEST_TIMEOUT,
            headers={"User-Agent": NEWS_USER_AGENT},
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        print(f"news._fetch_feed_entries: request failed ({feed_url}):", exc)
        return []

    try:
        parsed = feedparser.parse(response.content)
    except Exception as exc:  # noqa: BLE001 — a malformed feed must not sink the rest
        print(f"news._fetch_feed_entries: parse failed ({feed_url}):", exc)
        return []

    return getattr(parsed, "entries", [])[:20]


def _record_fetch_outcome(memory, succeeded):
    """Updates the consecutive-failure streak used by health_alert_needed.

    succeeded=True (a real item was found): resets the streak and clears
    the alerted flag, so a later unrelated bad streak can alert again
    instead of staying silenced by an old alert forever.

    succeeded=False (the feeds themselves failed to fetch/parse — see
    _fetch_feed_entries): increments the streak — this is specifically
    what NEWS_FAILURE_ALERT_THRESHOLD exists to catch (a dead/renamed feed
    URL).

    succeeded=None (bug fix #48: feeds fetched fine, but nothing survived
    the seen-link/denylist filters this time — an ordinary, expected dry
    spell, not evidence the feed itself is broken): the streak is left
    exactly as it was, neither incremented nor reset. Previously this case
    didn't exist and was recorded identically to succeeded=False, so a
    harmless dry spell (especially right after #45's denylist fix, which
    now correctly admits more articles and so churns through the
    seen-link window faster) could trigger the same "feed might be dead"
    alert as a genuinely broken feed URL.
    """
    if succeeded is True:
        memory[NEWS_FAILURE_STREAK_KEY] = 0
        memory[NEWS_ALERTED_KEY] = False
    elif succeeded is False:
        memory[NEWS_FAILURE_STREAK_KEY] = memory.get(NEWS_FAILURE_STREAK_KEY, 0) + 1
    # succeeded is None -> no change to the streak either way.


def health_alert_needed(memory):
    """True at most once per bad streak: once consecutive failed attempts
    reach config.NEWS_FAILURE_ALERT_THRESHOLD, and we haven't already
    alerted for this same streak. Marks the streak as alerted as a side
    effect (same "caller saves memory.json eventually" contract as every
    other memory-mutating helper here) so main.py doesn't have to track
    that separately."""
    streak = memory.get(NEWS_FAILURE_STREAK_KEY, 0)
    already_alerted = memory.get(NEWS_ALERTED_KEY, False)
    if streak >= NEWS_FAILURE_ALERT_THRESHOLD and not already_alerted:
        memory[NEWS_ALERTED_KEY] = True
        return True
    return False


def fetch_news_item(memory):
    """Returns {'title', 'summary', 'link', 'source'} or None (empty/failed
    feeds, or everything filtered out). Marks the chosen item as seen in
    memory and updates the health-streak counters (caller is responsible
    for eventually saving memory.json, same as every other memory-mutating
    helper in this codebase)."""
    if feedparser is None:
        print("news.fetch_news_item: feedparser not installed, skipping.")
        _record_fetch_outcome(memory, succeeded=False)
        return None

    seen = set(_seen_links(memory))
    candidates = []

    for feed_url in NEWS_FEEDS:
        for entry in _fetch_feed_entries(feed_url):
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
                "has_real_summary": bool(summary),
                "link": link,
                "source": feed_url,
            })

    if not candidates:
        # Bug fix (#48): this used to call _record_fetch_outcome(succeeded=
        # False) here too — identically to the branch below, where the
        # feeds genuinely failed to fetch/parse. But "fetched fine, just
        # nothing survived the seen-link/denylist filters this time" is a
        # completely normal, expected occurrence (especially right after
        # #45's fix, which now correctly lets more articles through the
        # denylist and so churns through the seen-link window faster) —
        # not the same problem as a feed URL actually going dead, which is
        # what config.py's NEWS_FAILURE_ALERT_THRESHOLD comment says this
        # streak exists to catch. Conflating the two meant a harmless dry
        # spell could trigger the same alert as a genuinely broken feed,
        # sending the admin looking for a dead URL when nothing was
        # actually wrong. Recorded as a distinct, non-alerting outcome
        # instead.
        _record_fetch_outcome(memory, succeeded=None)
        return None

    # Bug fix (#46): sorting by raw summary length alone used to be
    # confounded by the `summary or title` fallback just above — an entry
    # with no genuine RSS summary falls back to its (usually much
    # shorter) title, which then made it look "simplest" and get picked
    # FIRST, systematically favoring the least-informative candidates
    # over genuinely short-but-substantive real summaries. Candidates
    # with a real summary are now preferred as a group; only within that
    # group (or when nothing has a real summary at all) does shorter-first
    # apply.
    candidates.sort(key=lambda c: (not c["has_real_summary"], len(c["summary"])))
    chosen = candidates[0]
    _mark_seen(memory, chosen["link"])
    _record_fetch_outcome(memory, succeeded=True)
    return chosen
