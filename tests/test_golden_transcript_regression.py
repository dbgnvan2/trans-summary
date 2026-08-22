"""Golden-transcript regression harness (offline, zero API spend).

Item #2 — the pipeline had NO end-to-end regression baseline: the only
end-to-end test is the LIVE gold-set calibration (``test_faithfulness_calibration.py``),
which is API-gated and skipped in a normal ``pytest`` run. That leaves the
deterministic validation layer — claim extraction, the fabricated-name detector,
the artifact codecs, and the cross-artifact consistency check — unprotected
against silent drift.

This harness reuses the three existing golden fixtures (``dave_g_test2``,
``roots_bowen_test``, ``where_roots/…``): complete real transcripts plus their
known-good artifacts. It runs the deterministic layer END-TO-END over each one
(transcript → claims → codec → consistency → gate) and asserts the results are
both *correct* (the load-bearing invariants — a known fabrication is still
flagged, clean abstracts stay clean) and *stable* (the deterministic fingerprints
— claim/codec-item counts — don't move).

The exact counts below are the POINT of a regression harness: a change to any
of them means the deterministic layer moved, and the ``GOLDEN`` table must be
updated deliberately (and re-reviewed), not silently. No LLM, no API key, no
network — it runs on every normal ``pytest`` invocation.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import abstract_validation as av
import artifact_contracts as ac
import config
import faithfulness_judge as fj
import release_gate as rg
import transcript_validate_consistency as tvc

FIX = Path(__file__).parent / "fixtures"
WR = FIX / "where_roots" / "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"
WR_BASE = WR.name

# (transcript_rel, abstract_rel) for the two bare-named fixtures; where_roots is
# prefixed and handled separately (its name is the full `WR_BASE`).
_GOLDEN = {
    "dave_g": {
        "dir": FIX / "dave_g_test2",
        "transcript": "formatted.md",
        "abstract": "abstract-generated.md",
        "claims": 5,
        "claim_anchors": ["nubbin of self"],
        "ungrounded": [],  # a clean abstract: no fabricated proper name
        "artifacts": {
            "structural-themes.md": ("themes", "structural", 3),
            "interpretive-themes.md": ("themes", "interpretive", 7),
            "topics.md": ("topics", None, 6),
            "key-terms.md": ("key_terms", None, 10),
            "bowen-references.md": ("bowen", None, 0),
            "emphasis-scored.md": ("emphasis", None, 10),
        },
    },
    "roots_bowen": {
        "dir": FIX / "roots_bowen_test",
        "transcript": "formatted.md",
        "abstract": "abstract-generated.md",
        "claims": 6,
        "claim_anchors": ["differentiation of self"],
        "ungrounded": [],
        "artifacts": {
            "structural-themes.md": ("themes", "structural", 3),
            "interpretive-themes.md": ("themes", "interpretive", 7),
            "topics.md": ("topics", None, 7),
            "key-terms.md": ("key_terms", None, 10),
            "bowen-references.md": ("bowen", None, 1),
            "emphasis-scored.md": ("emphasis", None, 9),
        },
    },
    "where_roots": {
        "dir": WR,
        "prefixed": True,  # files are named "<base> - <artifact>.md"
        "transcript": "formatted.md",
        "abstract": "abstract-generated.md",
        "claims": 11,
        "claim_anchors": ["Luciano Malorni"],
        "ungrounded": ["Luciano Malorni"],  # the REAL fabrication shipped in prod
        "artifacts": {
            # this fixture is a partial folder (no themes/topics) — only assert what exists
            "key-terms.md": ("key_terms", None, 10),
            "bowen-references.md": ("bowen", None, 4),
            "emphasis-scored.md": ("emphasis", None, 32),
        },
    },
}


def _resolve(fixture: str, rel: str) -> Path:
    """Path to a fixture file, applying a '<dir-name> - ' prefix for prefixed fixtures."""
    g = _GOLDEN[fixture]
    return g["dir"] / (f"{g['dir'].name} - {rel}" if g.get("prefixed") else rel)


def _read(fixture: str, rel: str) -> str:
    return _resolve(fixture, rel).read_text(encoding="utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Load-bearing invariant: the deterministic fabricated-name detector still flags
# the known fabrication (and does not false-flag the clean abstracts).
# ---------------------------------------------------------------------------
def test_golden_fabrication_detector_flags_known_fabrication():
    """``abstract_validation.find_ungrounded_names`` is the OFFLINE engine behind
    the gate's hard ``entity_grounding`` blocker. It must still catch the real
    'Luciano Malorni' fabrication in the where_roots abstract, and return nothing
    for the two clean abstracts — a drift here is a silent gate-bypass regression."""
    for fixture in _GOLDEN:
        abstract = _read(fixture, _GOLDEN[fixture]["abstract"])
        transcript = _read(fixture, _GOLDEN[fixture]["transcript"])
        assert av.find_ungrounded_names(abstract, transcript) == _GOLDEN[fixture]["ungrounded"], fixture


# ---------------------------------------------------------------------------
# Deterministic claim extraction is stable and finds the right anchors.
# ---------------------------------------------------------------------------
def test_golden_abstract_claim_extraction_is_stable():
    for fixture, g in _GOLDEN.items():
        claims = fj.extract_claims(_read(fixture, g["abstract"]))
        assert len(claims) == g["claims"], f"{fixture}: claims={len(claims)}"
        joined = " ".join(claims)
        for anchor in g["claim_anchors"]:
            assert anchor.lower() in joined.lower(), f"{fixture}: anchor {anchor!r} missing"


# ---------------------------------------------------------------------------
# The artifact codecs parse each golden artifact to the same, known item count.
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("fixture", sorted(_GOLDEN))
def test_golden_artifact_codecs_parse_to_stable_counts(fixture):
    g = _GOLDEN[fixture]
    for rel, (kind, parse_kind, expected) in g["artifacts"].items():
        text = _read(fixture, rel)
        obj = (ac.codec(kind).parse_markdown(text, parse_kind) if parse_kind
               else ac.codec(kind).parse_markdown(text))
        got = len(obj["items"])
        assert got == expected, f"{fixture}/{rel}: parsed {got} items, golden {expected}"


# ---------------------------------------------------------------------------
# End-to-end: the REAL release gate, run offline over the one complete,
# properly-named fixture, BLOCKs the known fabrication and names it.
# ---------------------------------------------------------------------------
def test_golden_gate_blocks_known_fabrication_end_to_end(monkeypatch):
    """Run the actual ``release_gate.run_gate`` over the where_roots golden
    transcript. The deterministic ``entity_grounding`` check (the elected hard
    blocker) must BLOCK on 'Luciano Malorni'."""
    monkeypatch.setattr(config, "PROJECTS_DIR", FIX / "where_roots")
    # Enforce offline-ness HERE, not just via the suite-wide conftest: the judges
    # ship ARMED (config.FAITHFULNESS_JUDGE_ENABLED=True) and a real key resolves on
    # this machine, so if the ambient conftest fixture were bypassed (e.g.
    # `cd tests && pytest`), the gate would construct a live Anthropic client and
    # this test would still PASS while spending API — silently. Make the opt-out loud
    # and self-contained (the inverse of the conftest's "loud opt-in" rule).
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", False)
    monkeypatch.setattr(config, "THEME_JUDGE_ENABLED", False)
    import transcript_utils
    monkeypatch.setattr(transcript_utils, "resolve_anthropic_key", lambda: None)

    decision = rg.run_gate(WR_BASE)
    assert decision.decision == rg.Decision.BLOCK
    assert any(b.check == "entity_grounding" for b in decision.blockers)
    blocker = next(b for b in decision.blockers if b.check == "entity_grounding")
    assert "Luciano Malorni" in blocker.detail


# ---------------------------------------------------------------------------
# The new cross-artifact consistency check runs clean on the complete fixture.
# ---------------------------------------------------------------------------
def test_golden_consistency_check_passes_on_complete_fixture():
    """The complete where_roots fixture has a populated bowen-references.md, so the
    cross-artifact consistency check must NOT report a sparsity FAIL against it."""
    fails, _warns, _info = tvc.run(WR)
    assert fails == [], f"unexpected consistency FAILs: {fails}"


def test_golden_sources_and_abstracts_exist():
    """Guard the harness itself: every golden source/abstract must be on disk."""
    for fixture, g in _GOLDEN.items():
        assert _resolve(fixture, g["transcript"]).exists(), fixture
        assert _resolve(fixture, g["abstract"]).exists(), fixture


def test_golden_fixture_json_sources_match_harness():
    """The judge gold-set JSON references the SAME transcripts this harness does —
    the two golden baselines must not drift apart."""
    gold = json.loads((FIX / "faithfulness_gold" / "gold.json").read_text(encoding="utf-8"))
    for rel in gold["sources"].values():
        assert (FIX / rel).exists(), f"gold source missing: {rel}"
