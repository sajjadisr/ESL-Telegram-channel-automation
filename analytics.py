"""Post-level engagement telemetry and composite reward score (Weakness 4 —
"measuring engagement with a ruler instead of a microscope" — and the
engagement-vs-learning reward function from the review).

Updated scope note (previously this said views/forwards were simply
unobtainable — that's no longer the full story):

  - Telegram: poll/quiz vote tallies are available natively (sendPoll +
    stopPoll — see telegram_bot.py / poll_feedback.py), no extra setup
    needed. Views and forwards on an ordinary channel post are NOT
    available through the plain Bot API at all — but they ARE available
    by reading (not incrementing) message metadata through a separate
    MTProto/Telethon userbot session. See engagement_harvest.py for that
    piece: it's optional (silently no-ops until TELETHON_SESSION_STRING is
    configured — scripts/generate_telethon_session.py), but once set up it
    backfills views/forwards for every format, not just polls, which is
    what makes score_entry below able to produce a real reward_score for
    text/image posts too, not just quiz/vote_poll.
  - Eitaa/Bale: channels.py only gets a delivery success/failure signal
    from the send call itself (see broadcast_extra_channels) — neither
    platform's bot API exposes votes, views, or reactions at all, and no
    userbot equivalent exists for either. What's recorded here for those
    platforms is delivery health, not engagement, and callers must not
    present it next to Telegram's real numbers as if comparable.

Until engagement_harvest.py is configured, text/image posts are still
logged with metrics=None (an honest "no data yet", not a bug) and only
quiz/vote_poll produce a reward_score, same as before.
"""

import datetime

import clock

from channels import _api_ok, NOT_CONFIGURED
from config import (
    ANALYTICS_PATH, REWARD_WEIGHT_ENGAGEMENT, REWARD_WEIGHT_LEARNING,
    FORWARD_WEIGHT_MULTIPLIER, ENGAGEMENT_HARVEST_WINDOW_DAYS,
)
from memory import load_json, save_json

ROLLING_WINDOW = 8  # how many past same-type/same-format posts define "normal" for this channel


def _same_type_history(analytics, is_quiz):
    return [
        e for e in analytics
        if e.get("is_quiz") == is_quiz and e.get("vote_count") is not None
    ][-ROLLING_WINDOW:]


def rolling_avg_votes(analytics, is_quiz):
    history = _same_type_history(analytics, is_quiz)
    if not history:
        return None
    return sum(e["vote_count"] for e in history) / len(history)


def compute_reward_score(vote_count, avg_votes, correct_rate=None):
    """Weighted-sum composite score (weights in config.py) balancing
    engagement (this poll's votes vs. this channel's own recent normal —
    not a global benchmark, since we have no way to compare to other
    channels) against learning (quiz correct-rate, when this was a quiz).

    Engagement is normalized against this channel's own rolling average
    and capped at 2x it, so one unusually popular post can't single-
    handedly dominate the score. With no rolling average yet (first polls
    of a given type), engagement is scored neutral (0.5) rather than 0 —
    there's no baseline yet to call it low.

    vote_poll has no correct answer, so it scores on engagement alone,
    regardless of the configured weights.

    Poll-specific (vote_count) path — kept exactly as-is, unchanged
    signature, since poll_feedback.py's harvest-time call already depends
    on it. See _engagement_value/score_entry below for the generalized
    views+forwards version used for every other format.
    """
    if avg_votes:
        engagement = min(vote_count / avg_votes, 2.0) / 2.0  # → [0, 1]
    else:
        engagement = 0.5

    if correct_rate is None:
        return round(engagement, 3)

    learning = correct_rate / 100
    return round(REWARD_WEIGHT_ENGAGEMENT * engagement + REWARD_WEIGHT_LEARNING * learning, 3)


# --- Generalized engagement scoring (views/forwards, any format) -----------
# The poll-only path above (compute_reward_score/rolling_avg_votes) is left
# untouched for backward compatibility with poll_feedback.py's existing,
# working call. Everything below is the views/forwards analog, used once
# engagement_harvest.py has backfilled a message's metrics — see that
# module for the Telethon side of this.

def _engagement_value(entry):
    """A single comparable engagement number for `entry`, or None if
    nothing measurable exists for it yet. vote_count (polls) and
    views+forwards (everything else, once harvested) are different units
    and are never compared to each other directly — every score below is
    always against THIS FORMAT's own rolling average, the same principle
    compute_reward_score already applies per is_quiz for polls.

    Forwards count more than raw views (FORWARD_WEIGHT_MULTIPLIER,
    config.py) — a forward is a subscriber vouching for the post to
    someone else, the actual growth mechanic on a channel with no
    algorithmic feed (telegram-esl-virality-blueprint.md, Part 0), whereas
    a view just means the post appeared in a chat list."""
    if entry.get("vote_count") is not None:
        return entry["vote_count"]
    if entry.get("views") is not None:
        return entry["views"] + (entry.get("forwards") or 0) * FORWARD_WEIGHT_MULTIPLIER
    return None


def rolling_avg_engagement(analytics, format_name, exclude_index=None):
    """Per-format rolling average of _engagement_value — the generalized,
    any-format twin of rolling_avg_votes (which is keyed by is_quiz and
    only ever sees polls). Every format gets its own baseline: an
    illustrated_pun image post and a quiz poll aren't the same unit of
    "popular", so they must never share a baseline."""
    history = [
        e for i, e in enumerate(analytics)
        if e.get("format") == format_name and _engagement_value(e) is not None and i != exclude_index
    ][-ROLLING_WINDOW:]
    if not history:
        return None
    return sum(_engagement_value(e) for e in history) / len(history)


def score_entry(entry, analytics, exclude_index=None):
    """Compute a reward_score for `entry` from its own engagement value
    against this format's rolling average. Returns None if there's
    nothing to score yet (no vote_count and no views). Used both by
    apply_harvested_engagement below and directly by tests."""
    value = _engagement_value(entry)
    if value is None:
        return None
    avg = rolling_avg_engagement(analytics, entry["format"], exclude_index=exclude_index)
    engagement = min(value / avg, 2.0) / 2.0 if avg else 0.5
    correct_rate = entry.get("correct_rate")
    if correct_rate is None:
        return round(engagement, 3)
    learning = correct_rate / 100
    return round(REWARD_WEIGHT_ENGAGEMENT * engagement + REWARD_WEIGHT_LEARNING * learning, 3)


def entries_pending_harvest(analytics=None, window_days=None):
    """message_ids that have been sent but have no views yet, within the
    last `window_days` (config.ENGAGEMENT_HARVEST_WINDOW_DAYS by default)
    — what engagement_harvest.py needs to ask Telethon to look up. Entries
    older than the window just keep whatever reading they last got (see
    config.ENGAGEMENT_HARVEST_WINDOW_DAYS's comment for why that's a
    reasonable place to stop chasing a moving target)."""
    window_days = window_days or ENGAGEMENT_HARVEST_WINDOW_DAYS
    analytics = analytics if analytics is not None else load_json(ANALYTICS_PATH, [])
    cutoff = clock.today() - datetime.timedelta(days=window_days)
    pending = []
    for e in analytics:
        if not e.get("message_id") or e.get("views") is not None:
            continue
        try:
            entry_date = datetime.date.fromisoformat(e.get("date", ""))
        except ValueError:
            continue
        if entry_date >= cutoff:
            pending.append(e["message_id"])
    return pending


def apply_harvested_engagement(updates):
    """updates: {message_id: (views, forwards)} from
    engagement_harvest.harvest_engagement_metrics(). Writes views/forwards
    onto every matching analytics.json entry that doesn't have them yet,
    then computes reward_score for each newly-complete entry — this is the
    first time most text/image formats ever get one (see module
    docstring).

    Baseline is snapshotted per format ONCE up front, from data that
    existed before this harvest run touches anything — so backfilling ten
    posts in one run scores each of them against the same rolling average,
    rather than a baseline that shifts under it post-by-post as earlier
    entries in the same batch get written (which would make the score
    depend on iteration order, not just on the data).

    Returns the number of entries updated (0 if `updates` is empty or
    nothing matched)."""
    if not updates:
        return 0
    analytics = load_json(ANALYTICS_PATH, [])

    formats_touched = {
        e["format"] for e in analytics
        if e.get("message_id") in updates and e.get("views") is None
    }
    baseline = {fmt: rolling_avg_engagement(analytics, fmt) for fmt in formats_touched}

    updated = 0
    for entry in analytics:
        mid = entry.get("message_id")
        if mid not in updates or entry.get("views") is not None:
            continue
        views, forwards = updates[mid]
        entry["views"] = views
        entry["forwards"] = forwards

        value = views + (forwards or 0) * FORWARD_WEIGHT_MULTIPLIER
        avg = baseline.get(entry["format"])
        engagement = min(value / avg, 2.0) / 2.0 if avg else 0.5
        correct_rate = entry.get("correct_rate")
        if correct_rate is None:
            entry["reward_score"] = round(engagement, 3)
        else:
            entry["reward_score"] = round(
                REWARD_WEIGHT_ENGAGEMENT * engagement + REWARD_WEIGHT_LEARNING * (correct_rate / 100), 3
            )
        entry["rolling_avg_engagement_before_this_post"] = round(avg, 3) if avg else None
        updated += 1

    if updated:
        save_json(ANALYTICS_PATH, analytics)
    return updated


def _summarize_delivery(extra_channel_results):
    """extra_channel_results is whatever channels.broadcast_extra_channels
    returned: {"eitaa": response_or_sentinel_or_None, "bale": ...}. This is
    delivery health (did the send succeed), not engagement — see module
    docstring.

    Uses channels._api_ok rather than checking response.ok directly —
    HTTP status alone isn't a reliable success signal on eitaayar.ir (its
    docs are explicit that you also have to check the "ok" field in the
    JSON body; see channels._api_ok's docstring). Checking only response.ok
    here would silently record "delivered" for a send that actually
    failed, which is exactly the failure mode this fix closes.

    Bug fix (#22): "not configured" and "failed" used to both collapse
    into the same ambiguous "not_configured_or_failed" string, because
    both cases used to come back as plain None from channels.py. Now that
    channels.py returns a distinct NOT_CONFIGURED sentinel for "this
    platform was never turned on" (see that module's #15/#16/#22 fixes),
    and only returns bare None after a genuine failure that's already
    been caught and alerted on upstream, these two very different
    situations can finally be told apart here too — which is what lets an
    admin (or a future feature) tell "Eitaa was just never set up" apart
    from "Eitaa is configured but has been failing" using analytics.json
    alone.
    """
    if not extra_channel_results:
        return None
    summary = {}
    for platform, response in extra_channel_results.items():
        if response is NOT_CONFIGURED:
            summary[platform] = "not_configured"
        elif response is None:
            summary[platform] = "error"  # a real failure — already caught + alerted upstream
        elif _api_ok(response) is True:
            summary[platform] = "delivered"
        elif _api_ok(response) is False:
            summary[platform] = "error"
        else:
            summary[platform] = "unknown"
    return summary


def record_poll_metrics(question, format_name, is_quiz, total_votes, correct_rate=None,
                         experiment_id=None, variant_label=None, extra_channel_delivery=None,
                         message_id=None):
    """Called from poll_feedback.py once a poll/quiz is closed and tallied.

    extra_channel_delivery here is the ALREADY-SUMMARIZED dict (e.g.
    {"eitaa": "delivered"}) that save_pending_poll captured at send time via
    _summarize_delivery — by harvest time (a day or more later, after a
    round-trip through pending_polls.json) the raw response objects
    _summarize_delivery expects no longer exist, only their persisted
    string form. Passing that back through _summarize_delivery would
    silently mis-tag everything as "unknown" since a string has no .ok
    attribute — pass it straight through instead.

    message_id (from the same pending_polls.json entry) is stored purely
    for engagement-report completeness/consistency with every other
    format — polls already get their real engagement number (the vote
    tally) at harvest time and don't need engagement_harvest.py at all."""
    analytics = load_json(ANALYTICS_PATH, [])
    avg_votes = rolling_avg_votes(analytics, is_quiz)
    score = compute_reward_score(total_votes, avg_votes, correct_rate)

    entry = {
        "date": clock.today_str(),
        "question": question,
        "format": format_name,
        "is_quiz": is_quiz,
        "vote_count": total_votes,
        "rolling_avg_votes_before_this_post": avg_votes,
        "correct_rate": correct_rate,
        "reward_score": score,
        "experiment_id": experiment_id,
        "variant_label": variant_label,
        "extra_channel_delivery": extra_channel_delivery,
        "message_id": message_id,
        "views": None,
        "forwards": None,
    }
    analytics.append(entry)
    save_json(ANALYTICS_PATH, analytics)
    return entry


def record_text_post(format_name, title, extra_channel_results=None, message_id=None):
    """Text/image posts have no engagement outcome available AT PUBLISH
    TIME in this architecture — metrics stay None here on purpose, exactly
    like before. The difference now: if message_id is set and
    TELETHON_SESSION_STRING is configured, engagement_harvest.py can come
    back later (see that module) and fill views/forwards/reward_score in
    on this same entry via apply_harvested_engagement — so metrics=None
    here means "not known yet", not "will never be known", whenever the
    userbot harvester is set up.

    Never raises: this is called right after a real send has already
    succeeded — a bookkeeping failure here must not be treated the same
    as the publish itself failing. Bug fix (#32): unlike embeddings.
    record_post_embedding (which already made and kept this exact
    promise, wrapped in its own try/except), this had no such guard —
    an exception here (most plausibly memory.save_json hitting a disk
    issue) used to propagate all the way up to main()'s top-level handler,
    which would then tell the admin "the run failed and no post was
    published" — false in exactly this scenario, since the post had
    already gone out; only the bookkeeping failed afterward.
    """
    try:
        analytics = load_json(ANALYTICS_PATH, [])
        analytics.append({
            "date": clock.today_str(),
            "question": title,
            "format": format_name,
            "is_quiz": None,
            "vote_count": None,
            "rolling_avg_votes_before_this_post": None,
            "correct_rate": None,
            "reward_score": None,
            "experiment_id": None,
            "variant_label": None,
            "extra_channel_delivery": _summarize_delivery(extra_channel_results),
            "message_id": message_id,
            "views": None,
            "forwards": None,
        })
        save_json(ANALYTICS_PATH, analytics)
    except Exception as exc:  # noqa: BLE001 — see docstring: must never look like the publish failed
        print(f"analytics.record_text_post: failed to record analytics for an already-published "
              f"post ({exc}) — the post itself is fine, only this bookkeeping was lost.")


def recent_scored_count(analytics=None, limit=10):
    """How many of the last `limit` scored posts overall (any format) have
    a reward_score — used by weekly_strategy.py as a simple "is there
    enough total signal yet" gate before it lets itself reshape
    format_schedule.json. This is deliberately a single pooled-across-
    formats count (a proxy for "has this channel been running long
    enough to have SOME data"), unlike recent_score_summary below, which
    (after bug #81's fix) gives each format its own separate window —
    the two answer different questions on purpose and are no longer the
    same window."""
    analytics = analytics if analytics is not None else load_json(ANALYTICS_PATH, [])
    return len([e for e in analytics if e.get("reward_score") is not None][-limit:])


def recent_score_summary(analytics=None, limit=10):
    """Average reward_score per format, over each format's own last
    `limit` scored posts — used by weekly_strategy.py's admin report AND
    (as of the schedule-weighting split) directly by schedule_builder.py
    to reweight the rotation, no LLM call in between. Returns {} if
    nothing scored yet for any format. Covers every format that has a
    reward_score, which is quiz/vote_poll always, plus anything
    engagement_harvest.py has backfilled.

    Bug fix (#81): this used to take the last `limit` scored entries
    OVERALL — across every format combined — and group THOSE by format.
    That meant a format scored less often or less recently than others
    could be crowded out of the window entirely and vanish from the
    result, even with a long, strong track record of its own — and
    schedule_builder.format_weight treats a format missing from this
    dict identically to one with zero data at all (DEFAULT_WEIGHT).
    Verified this was a real, reproducible gap: 12 historical
    micro_scene entries averaging a strong score, followed by 10 more
    recent quiz entries, used to make micro_scene disappear from the
    summary completely with the default limit=10. Now takes the last
    `limit` scored entries for EACH format independently, so one
    format's recent activity can no longer crowd another out.
    """
    analytics = analytics if analytics is not None else load_json(ANALYTICS_PATH, [])
    scores_by_format = {}
    for e in analytics:
        if e.get("reward_score") is None:
            continue
        scores_by_format.setdefault(e["format"], []).append(e["reward_score"])
    return {
        fmt: round(sum(scores[-limit:]) / len(scores[-limit:]), 3)
        for fmt, scores in scores_by_format.items()
    }
