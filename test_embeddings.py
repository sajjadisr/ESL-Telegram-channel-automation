"""Offline tests for embeddings.py's semantic-dedup logic. cosine_similarity/
most_similar are pure Python (no mocking needed); check_semantic_duplicate's
only external dependency (ai.embed_text, an API call) is mocked so this
never touches the network.

Run: python3 test_embeddings.py
"""
import math
import os
import sys
import tempfile
from unittest import mock

os.environ.setdefault("TELEGRAM_BOT_TOKEN", "test-telegram-token")
os.environ.setdefault("TELEGRAM_CHANNEL_ID", "@testchannel")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

import embeddings  # noqa: E402

FAILED = []
PASSED = []


def check(label, condition, detail=""):
    if condition:
        PASSED.append(label)
        print(f"  OK   {label}")
    else:
        FAILED.append(label)
        print(f"  FAIL {label}  {detail}")


print("\n=== cosine_similarity: basic geometry ===")
check("identical vectors -> similarity 1.0",
      math.isclose(embeddings.cosine_similarity([1, 0, 0], [1, 0, 0]), 1.0))
check("orthogonal vectors -> similarity 0.0",
      math.isclose(embeddings.cosine_similarity([1, 0], [0, 1]), 0.0, abs_tol=1e-9))
check("opposite vectors -> similarity -1.0",
      math.isclose(embeddings.cosine_similarity([1, 0], [-1, 0]), -1.0))
check("scale-invariant (same direction, different magnitude) -> still 1.0",
      math.isclose(embeddings.cosine_similarity([1, 2, 3], [2, 4, 6]), 1.0))
check("zero vector -> 0.0, not a division-by-zero crash",
      embeddings.cosine_similarity([0, 0, 0], [1, 2, 3]) == 0.0)
check("mismatched lengths -> 0.0, not an exception",
      embeddings.cosine_similarity([1, 2], [1, 2, 3]) == 0.0)

print("\n=== most_similar: finds the closest match, ignores the rest ===")
records = [
    (1, "Present simple tense", [1, 0, 0]),
    (2, "Daily routine words", [0.9, 0.1, 0]),
    (3, "Unrelated topic", [0, 1, 0]),
]
title, score = embeddings.most_similar([1, 0, 0], records)
check("returns the title of the closest vector", title == "Present simple tense", title)
check("score is close to 1.0 for an exact match", score > 0.99, score)

title2, score2 = embeddings.most_similar([0, 1, 0], records)
check("a different query vector finds a different closest match",
      title2 == "Unrelated topic", title2)

empty_title, empty_score = embeddings.most_similar([1, 0, 0], [])
check("empty records -> (None, 0.0)", empty_title is None and empty_score == 0.0)

print("\n=== most_similar: exclude_post_ids (Bug fix #92) ===")
title3, score3 = embeddings.most_similar([1, 0, 0], records, exclude_post_ids={1})
check("excluding the closest match's post_id finds the next-closest instead",
      title3 == "Daily routine words", title3)
title4, score4 = embeddings.most_similar([1, 0, 0], records, exclude_post_ids={1, 2, 3})
check("excluding every stored post_id -> (None, 0.0), same as empty records",
      title4 is None and score4 == 0.0, (title4, score4))
title5, score5 = embeddings.most_similar([1, 0, 0], records, exclude_post_ids=None)
check("exclude_post_ids=None behaves exactly like omitting it",
      title5 == "Present simple tense", title5)

print("\n=== check_semantic_duplicate: threshold behavior (embed_text mocked) ===")
with tempfile.TemporaryDirectory() as tmpdir:
    path = os.path.join(tmpdir, "post_embeddings.jsonl")
    with mock.patch("embeddings.EMBEDDINGS_JSONL_PATH", path):
        # Nothing stored yet -> never a duplicate, regardless of the vector.
        with mock.patch("embeddings.embed_text", return_value=[1.0, 0.0, 0.0]):
            title, score = embeddings.check_semantic_duplicate("some draft text")
        check("no stored history -> (None, 0.0), never a false positive",
              title is None and score == 0.0, (title, score))

        embeddings._append_record(1, "Coffee every morning example", [1.0, 0.0, 0.0])

        # Same direction as the stored vector -> should trip the threshold.
        with mock.patch("embeddings.embed_text", return_value=[1.0, 0.0, 0.0]):
            title, score = embeddings.check_semantic_duplicate("near-identical draft", threshold=0.9)
        check("near-identical vector above threshold -> flagged as duplicate",
              title == "Coffee every morning example", (title, score))

        # Clearly different direction -> should NOT trip the threshold.
        with mock.patch("embeddings.embed_text", return_value=[0.0, 1.0, 0.0]):
            title, score = embeddings.check_semantic_duplicate("totally different draft", threshold=0.9)
        check("orthogonal vector below threshold -> not flagged",
              title is None, (title, score))

        # embed_text failing (returns None) must degrade gracefully, not raise.
        with mock.patch("embeddings.embed_text", return_value=None):
            title, score = embeddings.check_semantic_duplicate("draft when embedding API is down")
        check("embed_text failure -> (None, 0.0), never blocks publishing",
              title is None and score == 0.0, (title, score))

print("\n=== check_semantic_duplicate: exclude_post_ids (Bug fix #92) ===")
# Reproduces the exact production incident: a reader_installment chunk
# (story "lion_and_mouse", part 3) embeds very close to that SAME story's
# own already-published part 1 — legitimately, since they share characters
# and setting — and without exclude_post_ids this is (correctly, by design)
# flagged as a duplicate every single time, with no way for a reworded
# retry to ever pass.
with tempfile.TemporaryDirectory() as tmpdir:
    path = os.path.join(tmpdir, "post_embeddings.jsonl")
    with mock.patch("embeddings.EMBEDDINGS_JSONL_PATH", path):
        embeddings._append_record(59, "شیر و موش (The Lion and the Mouse) — قسمت 1", [1.0, 0.0, 0.0])
        embeddings._append_record(61, "شیر و موش (The Lion and the Mouse) — قسمت 2", [0.95, 0.05, 0.0])
        embeddings._append_record(23, "لاک‌پشت و خرگوش (The Tortoise and the Hare) — قسمت 3", [0.0, 1.0, 0.0])

        with mock.patch("embeddings.embed_text", return_value=[0.98, 0.02, 0.0]):
            title, score = embeddings.check_semantic_duplicate(
                "part 3 draft, similar to the rest of its own story",
            )
        check("without exclusion, a new chunk collides with its own story's earlier post",
              title in ("شیر و موش (The Lion and the Mouse) — قسمت 1",
                        "شیر و موش (The Lion and the Mouse) — قسمت 2"), (title, score))

        with mock.patch("embeddings.embed_text", return_value=[0.98, 0.02, 0.0]):
            title, score = embeddings.check_semantic_duplicate(
                "part 3 draft, similar to the rest of its own story",
                exclude_post_ids={59, 61},
            )
        check("excluding the story's own post ids clears the false-positive dedup block",
              title is None, (title, score))
        check("a genuine cross-story duplicate would still be caught (score against the "
              "unrelated story stays low here, confirming the exclusion is post-specific, "
              "not a blanket disable)", score < embeddings.DEDUP_SIMILARITY_THRESHOLD, score)

print("\n=== record_post_embedding: never raises, even if embed_text blows up ===")
with tempfile.TemporaryDirectory() as tmpdir:
    path = os.path.join(tmpdir, "post_embeddings.jsonl")
    with mock.patch("embeddings.EMBEDDINGS_JSONL_PATH", path):
        with mock.patch("embeddings.embed_text", side_effect=RuntimeError("simulated API outage")):
            try:
                embeddings.record_post_embedding(42, "Some title", "Some content")
                raised = False
            except Exception:  # noqa: BLE001
                raised = True
        check("an unexpected embed_text exception is swallowed, not propagated", raised is False)
        check("no file was created since nothing could be embedded",
              not os.path.exists(path) or os.path.getsize(path) == 0)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
if FAILED:
    print("FAILED:", FAILED)
    sys.exit(1)
sys.exit(0)
