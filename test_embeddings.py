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
