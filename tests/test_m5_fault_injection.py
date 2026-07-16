"""M5 — fault-injection / edge-case matrix (spec_unattended_robustness_2026-07-15.md).

The acceptance test for the fail-closed net: under adverse inputs and injected
faults the release gate must either produce a definite decision (never crash) and
degrade with a distinct signal, or fail closed (BLOCK) — it must never silently
publish. Uses the real `where_roots` run (its abstract ships the fabricated
'Luciano Malorni') plus synthetic degenerate states.
"""
import json
import logging
import shutil
from pathlib import Path

import pytest

import config
import release_gate as rg
from release_gate import Decision, Status

FX = Path(__file__).parent / "fixtures" / "where_roots"
BASE = "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"
LOG = logging.getLogger("m5")


@pytest.fixture
def cloned_run(tmp_path, monkeypatch):
    dst = tmp_path / "projects"
    shutil.copytree(FX, dst)
    monkeypatch.setattr(config, "PROJECTS_DIR", dst)
    return BASE, dst / BASE


def _mk_project(tmp_path, monkeypatch, formatted="Some transcript text about anxiety.",
                abstract="A short neutral summary of the talk."):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    base = "T - A - 2025-01-01"
    proj = tmp_path / base
    proj.mkdir(parents=True)
    if formatted is not None:
        (proj / f"{base}{config.SUFFIX_FORMATTED}").write_text(formatted)
    if abstract is not None:
        (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").write_text(abstract)
    return base, proj


# ------------------------------------------------------------------ M5.A inputs
@pytest.mark.parametrize("formatted,expect_block", [
    ("", True),                                  # empty source -> ERROR -> BLOCK
    ("   \n\t\n  ", True),                        # whitespace-only -> ERROR -> BLOCK
    ("Short talk about anxiety and family.", False),   # short but present
    ("no section headers here, just prose. " * 80, False),  # malformed (no headers)
    ("word " * 60000, False),                    # very long (real-scale) — must not hang/crash
])
def test_m5a1_input_edge_matrix_never_crashes_decision_definite(
        tmp_path, monkeypatch, formatted, expect_block):
    base, _ = _mk_project(tmp_path, monkeypatch, formatted=formatted)
    d = rg.run_gate(base, LOG)  # must not raise
    assert d.decision in (Decision.BLOCK, Decision.ALLOW, Decision.ALLOW_WITH_WARNINGS)
    assert (d.decision is Decision.BLOCK) is expect_block


# ------------------------------------------------------------------ M5.B partial
def test_m5b1_missing_source_blocks(tmp_path, monkeypatch):
    base, _ = _mk_project(tmp_path, monkeypatch, formatted=None)  # no formatted transcript
    d = rg.run_gate(base, LOG)
    assert d.decision is Decision.BLOCK
    assert any(v.check == "entity_grounding" and v.status is Status.ERROR for v in d.blockers)


def test_m5b1_missing_abstract_warns_names_it_not_block(tmp_path, monkeypatch):
    base, _ = _mk_project(tmp_path, monkeypatch, abstract=None)  # source present, no abstract
    d = rg.run_gate(base, LOG)
    assert d.decision is not Decision.BLOCK  # policy: completeness is WARN, not block
    req = next(v for v in d.verdicts if v.check == "required_artifacts")
    assert req.status is Status.WARN
    assert any("abstract" in m for m in req.items)


def test_m5b1_empty_abstract_is_named_missing(tmp_path, monkeypatch):
    base, proj = _mk_project(tmp_path, monkeypatch)
    (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").write_text("   \n")  # present but empty
    req = rg.check_required_artifacts(base, LOG)
    assert req.status is Status.WARN and any("abstract" in m for m in req.items)


# ------------------------------------------------------------------ M5.C dirty re-run
def test_m5c1_block_then_clean_rerun_reconciles(cloned_run):
    base, proj = cloned_run
    marker = proj / f"{base}{config.SUFFIX_PUBLISH_BLOCKED}"
    webpage = proj / f"{base}{config.SUFFIX_WEBPAGE}"
    webpage.write_text("<html>prior ALLOW bundle</html>")

    # Run 1: fabricated name -> BLOCK -> marker + stale bundle quarantined.
    assert rg.publish_allowed(base, LOG) is False
    assert marker.exists()
    assert not webpage.exists()
    assert webpage.with_name(webpage.name + ".blocked-stale").exists()

    # Run 2 (dirty): fix the abstract -> now clean -> marker cleared, allowed.
    ab = proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}"
    ab.write_text(ab.read_text().replace("Luciano Malorni", "Michael Kerr"))
    assert rg.publish_allowed(base, LOG) is True
    assert not marker.exists()  # stale block signal did not leak into the clean run


def test_m5c1_gate_is_idempotent_same_state(cloned_run):
    base, proj = cloned_run
    d1 = rg.gate_and_report(base, "t1", LOG)
    m1 = json.loads((proj / f"{base}{config.SUFFIX_RUN_MANIFEST}").read_text())
    d2 = rg.gate_and_report(base, "t2", LOG)
    m2 = json.loads((proj / f"{base}{config.SUFFIX_RUN_MANIFEST}").read_text())
    assert d1.decision is d2.decision is Decision.BLOCK
    # Same inputs -> same decision + same artifact hashes (only the timestamp moves).
    m1.pop("generated_at"); m2.pop("generated_at")
    assert m1 == m2


# ------------------------------------------------------------------ M5.D fault injection
def _raise(_b, _l):
    raise TimeoutError("simulated transient (timeout/429/5xx)")


def test_m5d1_fault_in_blocking_check_blocks(cloned_run, monkeypatch):
    base, proj = cloned_run
    webpage = proj / f"{base}{config.SUFFIX_WEBPAGE}"
    webpage.write_text("<html>prior bundle</html>")
    monkeypatch.setattr(config, "GATE_BLOCKING_CHECKS", {"entity_grounding"})
    # Inject a transient fault into the BLOCKING check -> ERROR -> BLOCK -> no publish.
    monkeypatch.setattr(rg, "DEFAULT_CHECKS", [("entity_grounding", _raise)])
    assert rg.publish_allowed(base, LOG) is False
    assert not webpage.exists()  # stale bundle quarantined, none written
    assert (proj / f"{base}{config.SUFFIX_PUBLISH_BLOCKED}").exists()


def test_m5d1_fault_in_advisory_check_does_not_block(cloned_run, monkeypatch):
    base, proj = cloned_run
    ab = proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}"
    ab.write_text(ab.read_text().replace("Luciano Malorni", "Michael Kerr"))  # clean abstract
    monkeypatch.setattr(config, "GATE_BLOCKING_CHECKS", {"entity_grounding"})
    # An advisory check's tooling fault must NOT hard-stop publication (F3).
    monkeypatch.setattr(rg, "DEFAULT_CHECKS", [
        ("entity_grounding", rg.check_entity_grounding),
        ("verbatim_quotes", _raise),
    ])
    d = rg.run_gate(base, LOG)
    assert d.decision is Decision.ALLOW_WITH_WARNINGS
    assert any(v.check == "verbatim_quotes" and v.status is Status.ERROR for v in d.verdicts)
