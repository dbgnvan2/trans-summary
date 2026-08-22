"""Chunked faithfulness judging (gap #1) — offline tests.

A single batched judge call over a LONG source degrades attention (esp. the middle)
and can near the context limit. These tests lock the deterministic layer of the fix:
source windowing, lexical claim->window routing, the full-source fallback for
summary-level inference claims, and the judge_artifact path selection. The LLM is
mocked (zero API spend); the routing/windowing logic is the deterministic surface.
"""

import config
import faithfulness_judge as fj
from faithfulness_judge import ClaimVerdict


# ---------------------------------------------------------------------------
# chunk_source — word-window splitting
# ---------------------------------------------------------------------------
def test_chunk_source_windows_with_overlap():
    source = " ".join(f"w{i}" for i in range(10))
    chunks = fj.chunk_source(source, chunk_words=4, overlap_words=1)
    assert len(chunks) == 3
    assert chunks[0] == "w0 w1 w2 w3"
    assert chunks[1].startswith("w3")   # overlap carries the boundary word
    assert chunks[-1].endswith("w9")


def test_chunk_source_single_chunk_when_short():
    source = "just a few words here"
    assert fj.chunk_source(source, chunk_words=100, overlap_words=10) == [source]


def test_chunk_source_merges_small_tail_without_stub():
    # 7 words with a 6-word window: the last 1-word remainder is < 30% of the
    # window, so it merges into the prior window rather than forming a stub.
    source = " ".join(f"w{i}" for i in range(7))
    chunks = fj.chunk_source(source, chunk_words=6, overlap_words=1)
    assert len(chunks) == 1
    assert chunks[0].endswith("w6")


def test_chunk_source_reads_config_at_call_time(monkeypatch):
    monkeypatch.setattr(config, "VALIDATION_CHUNK_SIZE", 4)
    monkeypatch.setattr(config, "VALIDATION_CHUNK_OVERLAP", 1)
    source = " ".join(f"w{i}" for i in range(9))
    chunks = fj.chunk_source(source)  # no explicit args -> config at call time
    assert len(chunks) >= 2


# ---------------------------------------------------------------------------
# route_claims_to_chunks — lexical routing + full-source fallback
# ---------------------------------------------------------------------------
def test_route_claims_to_chunks_routes_by_lexical_overlap():
    chunks = ["the family anxiety triangle is central here",
              "the cancer research biology of cells"]
    claims = ["Kerr discusses the family anxiety triangle.",
              "Kerr presents the cancer research on cells."]
    routed, unrouted = fj.route_claims_to_chunks(claims, chunks, min_overlap=0.1, margin=0.0)
    assert routed == {0: [0], 1: [1]}
    assert unrouted == []


def test_route_claims_leaves_summary_inference_claim_unrouted():
    # A claim connecting material spread across the source has NO lexical anchor in
    # any single window -> it must be judged against the FULL source (else a faithful
    # abstraction would be falsely flagged unsupported).
    chunks = ["the family anxiety triangle is central"]
    claims = ["The presenter connects this history to Bowen theory by introducing the equation."]
    routed, unrouted = fj.route_claims_to_chunks(claims, chunks, min_overlap=0.5, margin=0.0)
    assert routed == {}
    assert unrouted == [0]


def test_route_claims_detects_cross_window_spread():
    """A claim whose significant words are spread across >1 window (best does not beat
    second-best by the margin) is a cross-window inference and must NOT be routed to one
    window — routing it would hide its other element(s) and false-BLOCK a faithful
    abstraction (precision)."""
    chunks = ["the family anxiety triangle is central here",
              "the cancer research biology of cells"]
    claim = ["Kerr connects the family anxiety triangle to the cancer research biology."]
    routed, unrouted = fj.route_claims_to_chunks(claim, chunks, min_overlap=0.1, margin=0.2)
    assert routed == {}
    assert unrouted == [0]


# ---------------------------------------------------------------------------
# judge_claims_chunked — bounded per-window calls, original order preserved
# ---------------------------------------------------------------------------
def test_judge_claims_chunked_reassembles_in_original_order(monkeypatch):
    monkeypatch.setattr(config, "VALIDATION_CHUNK_SIZE", 6)
    monkeypatch.setattr(config, "VALIDATION_CHUNK_OVERLAP", 1)
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ROUTE_MIN_OVERLAP", 0.05)

    source = "family anxiety triangle fusion here cancer biology cells research there"
    claims = [
        "The family anxiety triangle is discussed.",
        "The cancer biology research is discussed.",
    ]
    calls = []

    def fake_judge(claims_, source_, client, model=None, logger=None):
        calls.append(source_)
        return [ClaimVerdict(claim=c, label="entailed") for c in claims_]

    monkeypatch.setattr(fj, "judge_claims", fake_judge)
    verdicts = fj.judge_claims_chunked(claims, source, object())

    # original order preserved, all judged, no None
    assert [v.claim for v in verdicts] == claims
    assert all(v.label == "entailed" for v in verdicts)
    # each claim routed to its own window -> 2 bounded calls, none against full source
    assert len(calls) == 2
    assert all(len(c.split()) < len(source.split()) for c in calls)


def test_judge_claims_chunked_falls_back_to_full_source_for_unrouted(monkeypatch):
    monkeypatch.setattr(config, "VALIDATION_CHUNK_SIZE", 6)
    monkeypatch.setattr(config, "VALIDATION_CHUNK_OVERLAP", 1)
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ROUTE_MIN_OVERLAP", 0.9)  # high bar

    source = "family anxiety triangle fusion here cancer biology cells research there"
    claims = ["The presenter connects this history to Bowen theory by introducing the equation."]
    calls = []

    def fake_judge(claims_, source_, client, model=None, logger=None):
        calls.append(source_)
        return [ClaimVerdict(claim=c, label="entailed") for c in claims_]

    monkeypatch.setattr(fj, "judge_claims", fake_judge)
    verdicts = fj.judge_claims_chunked(claims, source, object())

    assert [v.claim for v in verdicts] == claims
    # the low-overlap claim is judged against the FULL source, not a window
    assert calls == [source]


# ---------------------------------------------------------------------------
# judge_artifact path selection — chunked for long, single-call for short
# ---------------------------------------------------------------------------
def test_judge_artifact_uses_chunked_path_for_long_source(monkeypatch):
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_MIN_CHUNK_SOURCE_WORDS", 6)
    monkeypatch.setattr(config, "VALIDATION_CHUNK_SIZE", 4)
    monkeypatch.setattr(config, "VALIDATION_CHUNK_OVERLAP", 1)
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ROUTE_MIN_OVERLAP", 0.05)

    source = "family anxiety triangle fusion cancer biology cells research"
    artifact = ("Kerr discusses the family anxiety triangle. "
                "Kerr presents the cancer biology research.")
    calls = []

    def fake_judge(claims_, source_, client, model=None, logger=None):
        calls.append(source_)
        return [ClaimVerdict(claim=c, label="entailed") for c in claims_]

    monkeypatch.setattr(fj, "judge_claims", fake_judge)
    result = fj.judge_artifact(artifact, source, object())

    assert result.status == fj.PASS
    # long source -> chunked: multiple bounded calls, none against the full source
    assert len(calls) >= 2
    assert all(len(c.split()) < len(source.split()) for c in calls)


def test_judge_artifact_uses_single_call_for_short_source(monkeypatch):
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_MIN_CHUNK_SOURCE_WORDS", 1000)
    source = "family anxiety triangle fusion"
    artifact = "Kerr discusses the family anxiety triangle."
    calls = []

    def fake_judge(claims_, source_, client, model=None, logger=None):
        calls.append(source_)
        return [ClaimVerdict(claim=c, label="entailed") for c in claims_]

    monkeypatch.setattr(fj, "judge_claims", fake_judge)
    result = fj.judge_artifact(artifact, source, object())

    assert result.status == fj.PASS
    # short source -> the unchanged single-call path (one call, full source)
    assert calls == [source]


def test_should_chunk_threshold():
    assert fj._should_chunk(" ".join("x" for _ in range(3000))) is True
    assert fj._should_chunk("short source") is False


def test_judge_claims_chunked_raises_on_reassembly_violation(monkeypatch):
    """Fail-closed reassembly (P2/P14): if a future routing change leaves a claim in
    NEITHER routed nor unrouted (a routing hole), judge_claims_chunked must RAISE
    (-> gate ERROR), not hand back None verdicts that crash downstream with an
    unhandled AttributeError."""
    import pytest

    source = "family anxiety triangle fusion here cancer biology cells research there"
    claims = ["First claim.", "Second claim."]

    def fake_judge(claims_, source_, client, model=None, logger=None):
        return [ClaimVerdict(claim=c, label="entailed") for c in claims_]

    monkeypatch.setattr(fj, "judge_claims", fake_judge)
    # simulate a routing hole: claim index 1 is in neither routed nor unrouted
    monkeypatch.setattr(fj, "route_claims_to_chunks",
                        lambda claims, chunks, min_overlap, margin: ({0: [0]}, []))

    with pytest.raises(ValueError):
        fj.judge_claims_chunked(claims, source, object())
