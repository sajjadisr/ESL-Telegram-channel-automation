"""Sequential A/B testing (Weakness 6 — "there is almost no experimentation"),
scoped to what's actually a valid test design on this channel.

Read this before reaching for a multi-armed bandit: this channel is a
single broadcast surface (one Telegram channel, mirrored to Eitaa/Bale) —
there is no per-user targeting available to a bot on any of the three
platforms, so every subscriber sees the same variant on a given post. That
rules out both a live bandit (which needs to route different users to
different arms in real time) and a classic per-user A/B split. The only
test design that's actually valid here is a SEQUENTIAL A/B test:
alternate variants post-by-post, and compare the metric once each variant
has enough samples. That also happens to be the cheapest design to reason
about at this channel's volume — roughly one quiz and one vote_poll per
week, so "enough samples" is already a matter of months, not hours.

Experiments only ever apply to quiz/vote_poll formats, because those are
the only formats with a measurable outcome (a poll vote tally) in this
pipeline — see analytics.py's docstring for why text/image posts can't be
scored at all. Only one experiment is active at a time, kept simple on
purpose: this project has no dashboard, so a human (the admin, via the
weekly report) reads the result and decides whether to adopt a variant —
nothing here auto-adopts a winner.
"""

from config import EXPERIMENTS_PATH
from memory import load_json, save_json


def get_active_experiment():
    experiments = load_json(EXPERIMENTS_PATH, [])
    for exp in experiments:
        if exp.get("active"):
            return exp
    return None


def _variant_counts(exp_id, variants):
    """Reads assigned_variants fresh from disk by id, rather than trusting
    whatever `exp` dict the caller happens to be holding — a caller that
    calls assign_variant() then record_assignment() then assign_variant()
    again in the same process (or holds an exp object loaded before
    another process's record_assignment ran) would otherwise see stale
    counts and keep picking the same variant."""
    experiments = load_json(EXPERIMENTS_PATH, [])
    assigned = []
    for exp in experiments:
        if exp.get("id") == exp_id:
            assigned = exp.get("assigned_variants", [])
            break
    counts = {v["label"]: 0 for v in variants}
    for label in assigned:
        if label in counts:
            counts[label] += 1
    return counts


def assign_variant(exp):
    """Whichever variant has been used fewest times so far gets this slot
    (ties broken by declaration order) — keeps the split as close to even
    as possible without needing randomness, which buys nothing here since
    there's no per-user population to randomize over in the first place."""
    counts = _variant_counts(exp["id"], exp["variants"])
    order = [v["label"] for v in exp["variants"]]
    return min(order, key=lambda label: (counts[label], order.index(label)))


def variant_prompt_note(exp, variant_label):
    for v in exp["variants"]:
        if v["label"] == variant_label:
            return v.get("prompt_note", "")
    return ""


def record_assignment(exp_id, variant_label):
    """Persists which variant this post used, so summarize_results below
    can report a real per-variant sample count even before analytics.json
    has the outcome (the poll hasn't closed yet when this is called)."""
    experiments = load_json(EXPERIMENTS_PATH, [])
    for exp in experiments:
        if exp.get("id") == exp_id:
            exp.setdefault("assigned_variants", []).append(variant_label)
            break
    save_json(EXPERIMENTS_PATH, experiments)


def summarize_results(exp, analytics):
    """Mean vote_count and mean reward_score per variant, joined from
    analytics.json entries tagged with this experiment's id. Used by
    weekly_strategy.py to tell the admin when there's enough data to read
    a result — reporting only; see module docstring on why nothing here
    auto-adopts a variant."""
    rows = [e for e in analytics if e.get("experiment_id") == exp["id"]]
    summary = {}
    for v in exp["variants"]:
        label = v["label"]
        matching = [r for r in rows if r.get("variant_label") == label]
        votes = [r["vote_count"] for r in matching if r.get("vote_count") is not None]
        scores = [r["reward_score"] for r in matching if r.get("reward_score") is not None]
        summary[label] = {
            "n": len(matching),
            "avg_votes": round(sum(votes) / len(votes), 1) if votes else None,
            "avg_score": round(sum(scores) / len(scores), 3) if scores else None,
        }
    return summary
