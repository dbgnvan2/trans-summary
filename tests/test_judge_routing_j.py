"""J1-J3: faithfulness judge routing (docs/plan_judge_routing_fix_2026-10-09.md).

Run 2026-10-08 was blocked partly by claims routed to the wrong transcript window:
"35 years later" went to window 0, the passage is in window 2. These tests pin the
routing rules and that no claim can FAIL on a window alone.
"""
from pathlib import Path

import pytest

import config
import faithfulness_judge as fj
from faithfulness_judge import ClaimVerdict

FIX = Path(__file__).resolve().parent / "fixtures" / "prose_real" / \
    "Why Families Repeat the Same Patterns - Michael Kerr - 2026-09-13"
BASE = FIX.name


def _source():
    return (FIX / f"{BASE} - formatted.md").read_text(encoding="utf-8")


# --- J2: stemming ---------------------------------------------------------------

def test_j2a_stem_variants_match():
    assert fj._significant_words("society societal societies") == {"societ"}
    assert fj._significant_words("family families") == {"famil"}


def test_j2b_adversarial_short_words_not_merged():
    """A stem under 4 letters keeps the word: 'news' must not become 'new'."""
    assert fj._significant_words("news") == {"news"}
    assert fj._significant_words("kerr") == {"kerr"}
    assert fj._significant_words("living") == {"living"}


# --- J1: ambiguous routing goes to the full source ------------------------------

def _chunks(*texts):
    return [" ".join(t.split()) for t in texts]


def test_j1a_multiple_windows_unrouted():
    chunks = _chunks("anxiety rises when distance grows quickly",
                     "anxiety rises when distance grows slowly")
    routed, unrouted = fj.route_claims_to_chunks(
        ["Anxiety rises with distance."], chunks, 0.15)
    assert routed == {} and unrouted == [0]


def test_j1b_only_common_words_unrouted():
    chunks = _chunks("anxiety family system alpha", "anxiety family system beta")
    routed, unrouted = fj.route_claims_to_chunks(
        ["The family system holds anxiety."], chunks, 0.15)
    assert unrouted == [0]


def test_j1c_distinctive_claim_still_routes():
    chunks = _chunks("anxiety family heliocentrism aristarchus",
                     "anxiety family determination salience")
    routed, unrouted = fj.route_claims_to_chunks(
        ["Aristarchus proposed heliocentrism."], chunks, 0.15)
    assert routed == {0: [0]} and unrouted == []


# --- J3: no claim FAILs on a window alone ---------------------------------------

class _Recorder:
    """Stub judge_claims: verdict depends on whether the full source was given."""

    def __init__(self, source, window_label, full_label, raise_on_full=False):
        self.source, self.window_label, self.full_label = source, window_label, full_label
        self.raise_on_full = raise_on_full
        self.calls = []

    def __call__(self, claims, src, client, **_k):
        full = src == self.source
        self.calls.append(("full" if full else "window", list(claims)))
        if full and self.raise_on_full:
            raise RuntimeError("timeout")
        label = self.full_label if full else self.window_label
        return [ClaimVerdict(c, label, "") for c in claims]


@pytest.fixture
def long_source():
    words = [f"filler{i}" for i in range(3500)]
    words[100:103] = ["aristarchus", "proposed", "heliocentrism"]
    return " ".join(words)


CLAIM = "Aristarchus proposed heliocentrism."


def test_j3a_window_fail_is_rejudged_on_full_source(monkeypatch, long_source):
    rec = _Recorder(long_source, fj.UNSUPPORTED, fj.ENTAILED)
    monkeypatch.setattr(fj, "judge_claims", rec)
    v = fj.judge_claims_chunked([CLAIM], long_source, client=None)
    assert v[0].label == fj.ENTAILED
    assert [c[0] for c in rec.calls] == ["window", "full"]


def test_j3b_full_source_fail_stands(monkeypatch, long_source):
    rec = _Recorder(long_source, fj.UNSUPPORTED, fj.CONTRADICTED)
    monkeypatch.setattr(fj, "judge_claims", rec)
    assert fj.judge_claims_chunked([CLAIM], long_source, client=None)[0].label == fj.CONTRADICTED


def test_j3c_window_entailed_not_rejudged(monkeypatch, long_source):
    rec = _Recorder(long_source, fj.ENTAILED, fj.UNSUPPORTED)
    monkeypatch.setattr(fj, "judge_claims", rec)
    assert fj.judge_claims_chunked([CLAIM], long_source, client=None)[0].label == fj.ENTAILED
    assert [c[0] for c in rec.calls] == ["window"]


def test_j3d_rejudge_error_is_error(monkeypatch, long_source):
    """A failed re-check raises, which judge_artifact turns into ERROR — never the
    window's FAIL (P1)."""
    rec = _Recorder(long_source, fj.UNSUPPORTED, fj.ENTAILED, raise_on_full=True)
    monkeypatch.setattr(fj, "judge_claims", rec)
    with pytest.raises(RuntimeError):
        fj.judge_claims_chunked([CLAIM], long_source, client=None)
    monkeypatch.setattr(fj, "extract_claims", lambda *_a, **_k: [CLAIM])
    assert fj.judge_artifact(CLAIM, long_source, client=None).status == fj.ERROR


def test_j1d_real_oct8_false_flags_reach_full_source(monkeypatch):
    """The two false flags of run 2026-10-08 can no longer FAIL on a window: if the
    window rejects them they are re-judged against the full transcript."""
    source = _source()
    assert fj._should_chunk(source)
    claims = [
        "Now, thirty-five years later, chronic anxiety floods into living rooms nightly "
        "through news cycles focused entirely on trauma.",
        "At the widest scale, Kerr applies the same logic to society.",
    ]
    rec = _Recorder(source, fj.UNSUPPORTED, fj.ENTAILED)
    monkeypatch.setattr(fj, "judge_claims", rec)
    verdicts = fj.judge_claims_chunked(claims, source, client=None)
    assert [v.label for v in verdicts] == [fj.ENTAILED, fj.ENTAILED]
    full_calls = [c for kind, c in rec.calls if kind == "full"]
    assert full_calls and set(claims) <= set(full_calls[-1])
    assert config.FAITHFULNESS_JUDGE_MIN_CHUNK_SOURCE_WORDS == 3000  # D1a keeps chunking
