"""Rule-based aggregate audience profile (Weakness 1 — "the AI has no
mental model of the audience"), built only from data this channel can
actually collect.

Deliberately NOT a per-user model, and deliberately NOT Bayesian/Deep
Knowledge Tracing or clustering: Telegram channels cannot send
non-anonymous polls at all (Telegram rejects the request), so there is no
per-user vote data to trace even in principle, and Eitaa/Bale expose no
user-level data of any kind. Every knowledge-tracing or clustering
approach in the literature assumes a per-user event stream that simply
doesn't exist here. What DOES exist is aggregate quiz signal across the
whole audience per closed poll — so this file maintains one "class
profile" (the shape the informal review sketched directly), updated by
plain rules, not a trained model. That's also the right amount of
machinery for a channel doing a handful of posts a week; a real
BKT/DKT/clustering model needs far more volume than that to beat hand
rules, let alone earn its complexity.
"""

from config import AUDIENCE_PROFILE_PATH, AUDIENCE_WEAK_THRESHOLD, AUDIENCE_STRONG_THRESHOLD
from memory import load_json, save_json

MAX_TRACKED_CATEGORIES = 8
MAX_ACCURACY_HISTORY = 20


def _default_profile():
    return {
        "weak_categories": [],
        "strong_categories": [],
        "quiz_accuracy_history": [],
        "avg_quiz_accuracy": None,
    }


def _bump(tracked_list, item):
    """Move `item` to the front (most-recently-flagged first), capped."""
    if item in tracked_list:
        tracked_list.remove(item)
    tracked_list.insert(0, item)
    del tracked_list[MAX_TRACKED_CATEGORIES:]


def update_from_quiz_result(category, correct_rate):
    """Called from poll_feedback.py right after a quiz is closed and
    tallied. `category` is the topics.json category the quiz was actually
    anchored to at send time (see main.py / campaigns.py) — not derived
    after the fact from the generated question text, since a quiz
    question is free-form Persian and won't reliably match a topics.json
    string. One quiz only has one question, so this attributes the whole
    poll's correct-rate to that one category; a multi-topic review quiz
    is an approximation by nature (see prompts.py's quiz guidance, which
    already draws on several recent posts for one question)."""
    profile = load_json(AUDIENCE_PROFILE_PATH, _default_profile())

    weak = profile.setdefault("weak_categories", [])
    strong = profile.setdefault("strong_categories", [])
    if category:
        if correct_rate <= AUDIENCE_WEAK_THRESHOLD:
            _bump(weak, category)
            if category in strong:
                strong.remove(category)
        elif correct_rate >= AUDIENCE_STRONG_THRESHOLD:
            _bump(strong, category)
            if category in weak:
                weak.remove(category)

    history = profile.setdefault("quiz_accuracy_history", [])
    history.append(correct_rate)
    profile["quiz_accuracy_history"] = history[-MAX_ACCURACY_HISTORY:]
    profile["avg_quiz_accuracy"] = round(
        sum(profile["quiz_accuracy_history"]) / len(profile["quiz_accuracy_history"]), 1
    )

    save_json(AUDIENCE_PROFILE_PATH, profile)
    return profile


def get_profile():
    """Public accessor for other modules (e.g. weekly_strategy.py's admin
    report) — avoids reaching into the private _default_profile() helper."""
    return load_json(AUDIENCE_PROFILE_PATH, _default_profile())


def profile_context_block(strategy=None):
    """Persian text block for prompts.py — the compact 'Audience profile:'
    summary both review documents describe. best_formats is pulled from
    strategy.json (already computed weekly by weekly_strategy.py) instead
    of being duplicated here, so format preference has one source of
    truth."""
    profile = load_json(AUDIENCE_PROFILE_PATH, _default_profile())
    lines = []
    if profile.get("weak_categories"):
        lines.append(
            "دسته‌هایی که این مخاطب توشون ضعیف‌تره (توی محتوای امروز در صورت تناسب بیشتر مرور/تمرین بده): "
            + "، ".join(profile["weak_categories"])
        )
    if profile.get("strong_categories"):
        lines.append(
            "دسته‌هایی که این مخاطب توشون قویه (نیازی به تکرار زیاد نیست): "
            + "، ".join(profile["strong_categories"])
        )
    if profile.get("avg_quiz_accuracy") is not None:
        lines.append(f"میانگین درصد پاسخ درست کوییزهای اخیر: {profile['avg_quiz_accuracy']}٪")
    if strategy and strategy.get("best_formats"):
        lines.append(
            "فرمت‌هایی که این مخاطب طبق بازخورد واقعی بیشتر باهاشون تعامل می‌کنه: "
            + "، ".join(strategy["best_formats"])
        )
    return "\n".join(lines)
