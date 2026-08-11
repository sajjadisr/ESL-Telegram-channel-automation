"""Weekly thematic campaigns (Weakness 5 in the audience/engagement review:
"every post lives and dies alone").

A campaign here is not a new content type — it's a *lens* on the existing
schedule: for one calendar week (Saturday-to-Friday, matching
schedule_builder.WEEKDAYS), we pin a single data/topics.json `category` as
the week's theme. That gets us most of "posts support each other" for very
little new machinery:

  - topic_selection.get_next_topic can softly prefer topics in that
    category when a fresh topic is needed, so a week naturally clusters
    around one theme instead of jumping around.
  - every generation prompt can name the week's theme and list what's
    already been posted this week (campaign_context_block), so e.g.
    Wednesday's post can genuinely reference Monday's instead of being
    unrelated.
  - the existing quiz/vote_poll review already pulls the last ~7 posts
    (see database.get_recent_posts) — at ~1 post/day that's almost exactly
    "this week", so the weekly quiz ends up reviewing the week's theme
    close to for free once topics actually cluster by week.

This deliberately does NOT build a full prerequisite graph or a real
spaced-repetition scheduler (the harder version of Weakness 5 described in
the review). At ~1 post/day and a topic pool this size, a rotating weekly
theme captures most of the benefit for a fraction of the complexity, and
the campaign_state.json shape below leaves room to grow into that later
(e.g. a "review_due" list) without a rewrite.
"""

import datetime

import clock

from config import CAMPAIGN_STATE_PATH
from memory import load_json, save_json


def _week_start(today=None):
    """ISO date string for the most recent Saturday (inclusive) — Saturday
    is day 0 in schedule_builder.WEEKDAYS, so a campaign week matches the
    same boundary the format rotation already uses."""
    today = today or clock.today()
    days_since_saturday = (today.weekday() - 5) % 7  # Mon=0 ... Sun=6, Sat=5
    return str(today - datetime.timedelta(days=days_since_saturday))


def _all_topics():
    """Bug fix (#37): this used to be its own separate implementation
    (`load_json(TOPICS_PATH, [])`, no filtering) — a near-duplicate of
    topic_selection._all_topics() that skipped that module's
    _EXCLUDED_TOPICS filter. The two could silently disagree about what
    counts as a real, selectable topic (topic_selection.get_next_topic
    would never select an excluded entry; this module's theme-picking
    counts would still credit it toward a category's "fresh topics
    remaining" tally). Delegating to the one real implementation means
    they can't drift apart again."""
    from topic_selection import _all_topics as _topic_selection_all_topics
    return _topic_selection_all_topics()


def _pick_theme_category(memory, previous_theme=None):
    """Prefer whichever category still has the most never-taught topics —
    picking a theme the channel can actually sustain a week of fresh
    content in — and avoid repeating last week's theme back-to-back when
    an alternative exists."""
    # Local import: topic_selection imports nothing from campaigns, but
    # importing at module load time would still create a needless coupling
    # for a function only called once a week.
    from topic_selection import _topic_history

    history_topics = {e["topic"] for e in _topic_history(memory)}
    counts = {}
    for t in _all_topics():
        if t["topic"] in history_topics:
            continue
        counts[t.get("category", "General")] = counts.get(t.get("category", "General"), 0) + 1

    if not counts:
        return previous_theme  # nothing fresh left anywhere; keep the old theme rather than None

    candidates = sorted(counts, key=lambda c: -counts[c])
    for cat in candidates:
        if cat != previous_theme:
            return cat
    return candidates[0]


def get_or_start_week(memory):
    """Load campaign_state.json, rolling over to a new theme if a new
    campaign week has started. Always returns a state dict; saves it when
    it changes."""
    state = load_json(CAMPAIGN_STATE_PATH, {})
    this_week = _week_start()
    if state.get("week_start") != this_week:
        state = {
            "week_start": this_week,
            "theme_category": _pick_theme_category(memory, state.get("theme_category")),
            "posts_this_week": [],
        }
        save_json(CAMPAIGN_STATE_PATH, state)
    return state


def record_post(state, date_str, format_name, title):
    """Append today's post to the running week so tomorrow's prompt can
    reference it. Safe to call for every format, including pending_manual
    image posts and poll/quiz posts.

    Never raises — same reasoning as analytics.record_text_post's #32 fix:
    this runs right after a real send has already succeeded, so a
    bookkeeping failure here (most plausibly memory.save_json hitting a
    disk issue) must degrade to "this week's campaign log is missing one
    entry" rather than propagate up and make main()'s top-level handler
    falsely tell the admin nothing was published this run.
    """
    try:
        state.setdefault("posts_this_week", []).append(
            {"date": date_str, "format": format_name, "title": title}
        )
        save_json(CAMPAIGN_STATE_PATH, state)
    except Exception as exc:  # noqa: BLE001 — see docstring: must never look like the publish failed
        print(f"campaigns.record_post: failed to record an already-published post ({exc}) — "
              f"the post itself is fine, only this week's campaign log entry was lost.")


def campaign_context_block(state):
    """Persian text block for prompts.py — names the week's theme and
    what's already been posted this week. Empty string (not None) when
    there's nothing to say yet, so callers can splice it straight into an
    f-string without a None check."""
    theme = state.get("theme_category")
    posts = state.get("posts_this_week", [])
    if not theme and not posts:
        return ""
    lines = []
    if theme:
        lines.append(f"محور موضوعی این هفته: {theme}")
    if posts:
        titles = "، ".join(p["title"] for p in posts)
        lines.append(
            "پست‌های همین هفته تا الان (اگه طبیعیه، بهشون اشاره/ارجاع بده تا حس دنباله‌دار بودن هفته حفظ بشه): "
            + titles
        )
    return "\n".join(lines)
