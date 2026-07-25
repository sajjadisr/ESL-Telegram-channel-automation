"""Post-level engagement telemetry and composite reward score (Weakness 4 —
"measuring engagement with a ruler instead of a microscope" — and the
engagement-vs-learning reward function from the review).

Read this before extending the file — the scope here is deliberately
narrower than the review documents proposed, because most of what they
list (views, reaction *type* breakdowns, forwards, dwell time) isn't
actually obtainable through this project's architecture:

  - Telegram: poll/quiz vote tallies ARE reliably available (native
    sendPoll + stopPoll — see telegram_bot.py / poll_feedback.py). Views,
    reactions, and forwards on a channel post are NOT reliably available
    through the plain Bot API without either (a) a long-running process
    to catch message_reaction / message_reaction_count updates, or (b) a
    separate userbot (MTProto/Telethon) session to poll message metadata
    after the fact. This project runs as a once-a-day GitHub Actions job
    with no persistent process — neither is wired up, so those fields are
    left out entirely rather than faked as 0 or None-that-looks-like-data.
  - Eitaa/Bale: channels.py only gets a delivery success/failure signal
    from the send call itself (see broadcast_extra_channels) — neither
    platform's bot API exposes votes, views, or reactions at all. What's
    recorded here for those platforms is delivery health, not engagement,
    and callers must not present it next to Telegram's real numbers as if
    comparable.

Because of that, a numeric engagement/reward score only ever exists for
quiz/vote_poll posts — the only formats that produce a measurable outcome
(a poll vote tally) in this architecture. Text/image posts are logged with
metrics=None on purpose: an honest "no data available", not a bug.
"""

import datetime

from channels import _api_ok
from config import ANALYTICS_PATH, REWARD_WEIGHT_ENGAGEMENT, REWARD_WEIGHT_LEARNING
from memory import load_json, save_json

ROLLING_WINDOW = 8  # how many past same-type polls define "normal" for this channel


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
    """
    if avg_votes:
        engagement = min(vote_count / avg_votes, 2.0) / 2.0  # → [0, 1]
    else:
        engagement = 0.5

    if correct_rate is None:
        return round(engagement, 3)

    learning = correct_rate / 100
    return round(REWARD_WEIGHT_ENGAGEMENT * engagement + REWARD_WEIGHT_LEARNING * learning, 3)


def _summarize_delivery(extra_channel_results):
    """extra_channel_results is whatever channels.broadcast_extra_channels
    returned: {"eitaa": response_or_None, "bale": response_or_None}. This
    is delivery health (did the send succeed), not engagement — see module
    docstring.

    Uses channels._api_ok rather than checking response.ok directly —
    HTTP status alone isn't a reliable success signal on eitaayar.ir (its
    docs are explicit that you also have to check the "ok" field in the
    JSON body; see channels._api_ok's docstring). Checking only response.ok
    here would silently record "delivered" for a send that actually
    failed, which is exactly the failure mode this fix closes."""
    if not extra_channel_results:
        return None
    summary = {}
    for platform, response in extra_channel_results.items():
        verdict = _api_ok(response)
        if response is None:
            summary[platform] = "not_configured_or_failed"
        elif verdict is True:
            summary[platform] = "delivered"
        elif verdict is False:
            summary[platform] = "error"
        else:
            summary[platform] = "unknown"
    return summary


def record_poll_metrics(question, format_name, is_quiz, total_votes, correct_rate=None,
                         experiment_id=None, variant_label=None, extra_channel_delivery=None):
    """Called from poll_feedback.py once a poll/quiz is closed and tallied.

    extra_channel_delivery here is the ALREADY-SUMMARIZED dict (e.g.
    {"eitaa": "delivered"}) that save_pending_poll captured at send time via
    _summarize_delivery — by harvest time (a day or more later, after a
    round-trip through pending_polls.json) the raw response objects
    _summarize_delivery expects no longer exist, only their persisted
    string form. Passing that back through _summarize_delivery would
    silently mis-tag everything as "unknown" since a string has no .ok
    attribute — pass it straight through instead."""
    analytics = load_json(ANALYTICS_PATH, [])
    avg_votes = rolling_avg_votes(analytics, is_quiz)
    score = compute_reward_score(total_votes, avg_votes, correct_rate)

    entry = {
        "date": str(datetime.date.today()),
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
    }
    analytics.append(entry)
    save_json(ANALYTICS_PATH, analytics)
    return entry


def record_text_post(format_name, title, extra_channel_results=None):
    """Text/image posts have no measurable engagement outcome in this
    architecture (see module docstring). Logged anyway so weekly_strategy
    can at least see publishing cadence and Eitaa/Bale delivery health —
    metrics stay explicitly None rather than fabricated."""
    analytics = load_json(ANALYTICS_PATH, [])
    analytics.append({
        "date": str(datetime.date.today()),
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
    })
    save_json(ANALYTICS_PATH, analytics)


def recent_score_summary(analytics=None, limit=10):
    """Average reward_score per format over the last `limit` scored
    (quiz/vote_poll) posts — used by weekly_strategy.py's admin report.
    Returns {} if nothing scored yet."""
    analytics = analytics if analytics is not None else load_json(ANALYTICS_PATH, [])
    scored = [e for e in analytics if e.get("reward_score") is not None][-limit:]
    by_format = {}
    for e in scored:
        by_format.setdefault(e["format"], []).append(e["reward_score"])
    return {
        fmt: round(sum(scores) / len(scores), 3)
        for fmt, scores in by_format.items()
    }
