"""Search-grounded fact-finding for content that needs checking against the
real world, not generation from a model's memory — the general-purpose
version of the fix idiom_proverb_bridge specifically needed.

Context: CONTENT_PIPELINE_CHANGES.md shipped 5 idiom<->proverb pairings
hand-picked by a prior session, with an explicit note to "please
sanity-check with a native speaker before this goes live." That check
never happened, and hand-picking a fixed list doesn't scale past whatever
one session had time to pick anyway. ai.generate_grounded_json (Google
Search grounding — a genuinely independent source, not the same model
family reviewing itself) is the actual fix, and it isn't idiom-specific:
any format that needs "is this real / is this accurate" can call it the
same way. find_persian_proverb_equivalent below is the first concrete use;
textbook_vs_real or a future format could add their own without touching
this module's shape.
"""

from ai import generate_grounded_json

# Below this confidence, a candidate is stored for a human glance (tagged
# fa_equivalent_needs_review in topics.json by scripts/enrich_idiom_
# proverbs.py) but never made eligible for idiom_proverb_bridge —
# topic_selection._eligible's required_tags check fails closed on anything
# not explicitly tagged has_fa_equivalent, so "found something, not sure
# enough" can never silently go live.
MIN_CONFIDENCE_TO_AUTO_PUBLISH = "high"
_CONFIDENCE_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}


def find_persian_proverb_equivalent(idiom_text):
    """Search-grounded lookup: is there a well-known Persian proverb/idiom
    that's a genuine equivalent of the English idiom `idiom_text`?

    Returns a dict {"fa_equivalent": str, "source": str, "confidence":
    "high"|"medium"|"low"|"none"}, or None if the call itself failed
    outright (network/API failure after retries — see
    ai.generate_grounded_json). confidence == "none" is a valid, useful
    answer ("searched, found nothing convincing"), not a failure — it's
    what should happen for idioms that genuinely have no good Persian
    equivalent, and it must be distinguishable from "the call broke"."""
    prompt = f"""You are researching a Persian (Farsi) proverb or idiom that is a genuine, well-known equivalent of the English idiom "{idiom_text}".

Use Google Search to check this against real sources (e.g. bilingual proverb dictionaries, Wikiquote's Persian proverbs page, reputable language-learning sites) — do not rely on your own memory alone, and do not invent a pairing if you can't find a real match.

Respond with ONLY a JSON object, no markdown fences, no extra text, in exactly this shape:
{{"fa_equivalent": "the Persian proverb/idiom text in Persian script, or empty string if none found", "source": "a short description of where you found this (e.g. a dictionary or page name), or empty string", "confidence": "high" | "medium" | "low" | "none"}}

Use "high" only if you found this in what looks like a real reference source and a native Persian speaker would immediately recognize it. Use "none" if you found nothing convincing — an empty, honest answer is much better than a confident wrong one."""
    return generate_grounded_json(prompt, fallback=None)


def meets_publish_threshold(result):
    """True if `result` (find_persian_proverb_equivalent's return value) is
    confident enough to write into topics.json as a live, has_fa_equivalent
    pairing rather than a needs-review candidate."""
    if not result:
        return False
    confidence = (result.get("confidence") or "none").lower()
    fa_equivalent = (result.get("fa_equivalent") or "").strip()
    return bool(fa_equivalent) and _CONFIDENCE_RANK.get(confidence, 0) >= _CONFIDENCE_RANK[MIN_CONFIDENCE_TO_AUTO_PUBLISH]
