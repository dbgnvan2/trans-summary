"""M1 — fail-closed release gate.

Verifies the gate BLOCKS the real run whose abstract ships a fabricated name
('Luciano Malorni'), ALLOWs a clean run, and that the policy is honoured: a
blocking-check FAIL blocks, an ERROR blocks (fail-closed), a non-blocking WARN
ships as ALLOW_WITH_WARNINGS.
"""
import json
import logging
import shutil
from pathlib import Path

import pytest

import config
import release_gate as rg
from release_gate import Decision, Status, Verdict

FX = Path(__file__).parent / "fixtures" / "where_roots"
BASE = "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"


@pytest.fixture
def real_run(monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", FX)
    return BASE


@pytest.fixture
def cloned_run(tmp_path, monkeypatch):
    dst = tmp_path / "projects"
    shutil.copytree(FX, dst)
    monkeypatch.setattr(config, "PROJECTS_DIR", dst)
    return BASE, dst / BASE


# --------------------------------------------------------------- M1.A
def test_m1a1_verdict_and_decision_serialize():
    v = Verdict("x", Status.FAIL, "bad", items=[1])
    assert v.to_dict() == {"check": "x", "status": "FAIL", "detail": "bad", "items": [1]}
    d = rg.decide([v])
    assert d.decision is Decision.BLOCK or d.decision is Decision.ALLOW_WITH_WARNINGS
    assert "decision" in d.to_dict()


# --------------------------------------------------------------- M1.B (policy)
def test_m1b1_blocking_fail_blocks_and_nonblocking_fail_warns(monkeypatch):
    monkeypatch.setattr(config, "GATE_BLOCKING_CHECKS", {"entity_grounding"})
    # a FAIL on a blocking check -> BLOCK
    d = rg.decide([Verdict("entity_grounding", Status.FAIL, "fabricated")])
    assert d.decision is Decision.BLOCK
    assert d.blockers and d.blockers[0].check == "entity_grounding"
    # a FAIL on a non-blocking check -> ships with warnings
    d2 = rg.decide([Verdict("verbatim_quotes", Status.FAIL, "drift")])
    assert d2.decision is Decision.ALLOW_WITH_WARNINGS
    # all PASS -> clean ALLOW
    assert rg.decide([Verdict("x", Status.PASS)]).decision is Decision.ALLOW


# --------------------------------------------------------------- M1.C (error fail-closed)
def test_m1c1_error_on_blocking_check_blocks_advisory_error_does_not(monkeypatch):
    monkeypatch.setattr(config, "GATE_ERROR_BLOCKS", True)
    monkeypatch.setattr(config, "GATE_BLOCKING_CHECKS", {"entity_grounding"})

    def boom(_base, _logger):
        raise RuntimeError("dependency down")

    # ERROR on the BLOCKING check -> BLOCK (can't verify -> fail closed).
    d = rg.run_gate("x", logging.getLogger("t"), checks=[("entity_grounding", boom)])
    assert d.decision is Decision.BLOCK
    assert d.blockers[0].status is Status.ERROR
    # ERROR on an ADVISORY check must NOT hard-stop publication (F3).
    d2 = rg.run_gate("x", logging.getLogger("t"), checks=[("timestamp_citations", boom)])
    assert d2.decision is Decision.ALLOW_WITH_WARNINGS
    # a returned-None blocking check is ERROR (not a silent pass) and blocks.
    d3 = rg.run_gate("x", None, checks=[("entity_grounding", lambda b, l: None)])
    assert d3.verdicts[0].status is Status.ERROR and d3.decision is Decision.BLOCK


# --------------------------------------------------------------- M4.C via the gate
def test_m1_real_run_with_fabricated_name_blocks(real_run):
    v = rg.check_entity_grounding(real_run, logging.getLogger("t"))
    assert v.status is Status.FAIL
    assert "Luciano Malorni" in v.detail
    decision = rg.run_gate(real_run, logging.getLogger("t"))
    assert decision.decision is Decision.BLOCK


def test_m1_clean_run_allows(cloned_run):
    """Remove the fabricated name from the abstract -> gate ALLOWs (or warns)."""
    base, proj = cloned_run
    ab = proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}"
    # Replace the fabricated 'Luciano Malorni' with a source-grounded name.
    ab.write_text(ab.read_text().replace("Luciano Malorni", "Michael Kerr"))
    v = rg.check_entity_grounding(base, logging.getLogger("t"))
    assert v.status is Status.PASS, v.detail
    assert rg.run_gate(base, logging.getLogger("t")).decision is not Decision.BLOCK


def test_m4c_blocker_scoped_to_abstract_not_synthesized_headings(cloned_run):
    """The blocker must NOT fire on Title-Case headings/concepts in synthesized
    artifacts ('Key Takeaways', 'Role Absorption') — verified as false positives
    on real runs; blocking them would refuse to publish a good run. Only the
    abstract is scanned (config.GATE_ENTITY_ARTIFACT_SUFFIXES)."""
    base, proj = cloned_run
    ab = proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}"
    ab.write_text(ab.read_text().replace("Luciano Malorni", "Michael Kerr"))  # clean abstract
    themes = proj / f"{base}{config.SUFFIX_STRUCTURAL_THEMES}"
    themes.write_text("## Structural Themes\n\n### Role Absorption\nA synthesized theme title.\n")
    v = rg.check_entity_grounding(base, logging.getLogger("t"))
    assert v.status is Status.PASS, v.detail
    assert rg.run_gate(base, logging.getLogger("t")).decision is not Decision.BLOCK


def test_m1c1_missing_source_is_error_not_pass(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    (tmp_path / BASE).mkdir(parents=True)  # project dir but no formatted transcript
    v = rg.check_entity_grounding(BASE, logging.getLogger("t"))
    assert v.status is Status.ERROR
    assert rg.run_gate(BASE, logging.getLogger("t")).decision is Decision.BLOCK


def test_f6_empty_source_is_error_not_fail(tmp_path, monkeypatch):
    """A present-but-empty source is 'cannot verify' (ERROR->block), not a FAIL
    asserting every artifact name is fabricated."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    proj = tmp_path / BASE
    proj.mkdir(parents=True)
    (proj / f"{BASE}{config.SUFFIX_FORMATTED}").write_text("   \n\n")  # present but empty
    (proj / f"{BASE}{config.SUFFIX_ABSTRACT_GEN}").write_text("Fabricated Personname here.")
    v = rg.check_entity_grounding(BASE, logging.getLogger("t"))
    assert v.status is Status.ERROR


def test_f4_block_quarantines_stale_bundle(cloned_run):
    """On BLOCK, a prior run's published bundle must be moved aside so it can't
    ship as current (F4)."""
    base, proj = cloned_run
    stale = proj / f"{base}{config.SUFFIX_WEBPAGE}"
    stale.write_text("<html>stale bundle from a prior ALLOW run</html>")
    assert rg.publish_allowed(base, logging.getLogger("t")) is False
    assert not stale.exists()
    assert stale.with_name(stale.name + ".blocked-stale").exists()


def test_f2_accented_name_detected(real_run):
    from abstract_validation import find_ungrounded_names
    source = "The talk mentions Kent Berridge and homeostasis repeatedly."
    # José García is fabricated (absent) -> flagged; accents must not hide it.
    assert "José García" in find_ungrounded_names("Work by José García and Kent Berridge.", source)


# --------------------------------------------------------------- M4.A verbatim quotes
def test_m4a_verbatim_quotes_pass_on_real_run(real_run):
    assert rg.check_verbatim_quotes(real_run, logging.getLogger("t")).status is Status.PASS


def test_m4a_fabricated_quote_tail_warns(cloned_run):
    base, proj = cloned_run
    emp = proj / f"{base}{config.SUFFIX_EMPHASIS_SCORED}"
    lines = emp.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith('"Einstein had his theory'):
            head = " ".join(line.strip().strip('"').split()[:15])
            lines[i] = '"' + head + ' and a fabricated tail that appears nowhere in the source at all."'
            break
    emp.write_text("\n".join(lines))
    v = rg.check_verbatim_quotes(base, logging.getLogger("t"))
    assert v.status is Status.WARN
    assert v.items


# --------------------------------------------------------------- M4.B timestamps
def test_m4b_timestamp_drift_warns_on_real_run(real_run):
    # The real emphasis artifact has a known mis-tagged timestamp (F6).
    v = rg.check_timestamp_citations(real_run, logging.getLogger("t"))
    assert v.status is Status.WARN
    assert v.items


# --------------------------------------------------------------- M4.D consistency
def test_m4d_name_spelling_divergence_warns(cloned_run):
    base, proj = cloned_run
    # Introduce a near-duplicate spelling ("Michael Kerrr") in the key-terms
    # artifact; the abstract already says "Michael Kerr" -> cross-artifact clash.
    kt = proj / f"{base}{config.SUFFIX_KEY_TERMS}"
    kt.write_text(kt.read_text() + "\n\n### Note\nMichael Kerrr elaborates further.\n")
    v = rg.check_entity_consistency(base, logging.getLogger("t"))
    assert v.status is Status.WARN
    assert any("Kerr" in "".join(pair) for pair in v.items)


# --------------------------------------------------------------- M3.C gate consumer
def test_m3c_bowen_contract_passes_on_real_run(real_run):
    """The real, well-formed bowen artifact conforms -> PASS (no false drift)."""
    v = rg.check_artifact_contracts(real_run, logging.getLogger("t"))
    assert v.status is Status.PASS


def test_m3c2_drifted_bowen_artifact_blocks(cloned_run):
    """A non-empty bowen artifact whose body no longer parses (format drift) is a
    loud ERROR that BLOCKS publication — not a silent zero (P19, U4)."""
    base, proj = cloned_run
    bowen = proj / f"{base}{config.SUFFIX_BOWEN}"
    # real heading + a concept block with the quote marker stripped: non-empty
    # body, zero parseable references.
    bowen.write_text("## Bowen References\n\n### Some Concept\n"
                     "This lost its quote-block marker and no longer parses.\n")
    v = rg.check_artifact_contracts(base, logging.getLogger("t"))
    assert v.status is Status.ERROR
    # and it blocks through the real policy (artifact_contracts is a hard blocker)
    d = rg.run_gate(base, logging.getLogger("t"),
                    checks=[("artifact_contracts", rg.check_artifact_contracts)])
    assert d.decision is Decision.BLOCK


def test_m3c2_all_headers_no_body_bowen_blocks(cloned_run):
    """All-headers-no-body drift (### concept headers with quote bodies dropped)
    must BLOCK, not read as a benign empty and slip the gate (finding #2)."""
    base, proj = cloned_run
    bowen = proj / f"{base}{config.SUFFIX_BOWEN}"
    bowen.write_text("## Bowen References\n\n### Concept A\n\n### Concept B\n")
    v = rg.check_artifact_contracts(base, logging.getLogger("t"))
    assert v.status is Status.ERROR


def test_m3c_empty_bowen_is_not_drift(cloned_run):
    """A legitimately-empty bowen run (bare header, no references) validates as an
    empty object and PASSES — the empty case must not be mislabeled as drift."""
    base, proj = cloned_run
    (proj / f"{base}{config.SUFFIX_BOWEN}").write_text("## Bowen References\n")
    v = rg.check_artifact_contracts(base, logging.getLogger("t"))
    assert v.status is Status.PASS


# --------------------------------------------------------------- M7 manifest
def test_m7a1_manifest_matches_gate(cloned_run):
    base, proj = cloned_run
    d = rg.gate_and_report(base, "2026-07-15T12:00:00", logging.getLogger("t"))
    assert d.decision is Decision.BLOCK
    manifest = json.loads((proj / f"{base}{config.SUFFIX_RUN_MANIFEST}").read_text())
    assert manifest["publish_decision"] == "BLOCK"
    assert manifest["gate"]["decision"] == "BLOCK"
    assert manifest["artifacts"]["formatted.md"]["present"] is True
    assert manifest["artifacts"]["formatted.md"]["sha256"]
    assert manifest["provenance"]["source_sha256"]
    assert manifest["generated_at"] == "2026-07-15T12:00:00"
    # a BLOCK drops a PUBLISH-BLOCKED marker for an operator/cron
    assert (proj / f"{base}{config.SUFFIX_PUBLISH_BLOCKED}").exists()


def test_write_manifest_missing_project_dir_returns_none(tmp_path, monkeypatch):
    """Regression: write_manifest must not crash when the project dir doesn't
    exist (wrong PROJECTS_DIR) — it caught a real FileNotFoundError."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    decision = rg.GateDecision(Decision.BLOCK, [], [])
    assert rg.write_manifest("No Such Base", decision, "t", logging.getLogger("t")) is None


def test_cli_missing_project_dir_returns_2_not_crash(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    rc = rg.main(["release_gate.py", "Nonexistent Base"])
    assert rc == 2
    assert "not found" in capsys.readouterr().out


def test_cli_projects_dir_arg_points_gate_at_folder(cloned_run):
    base, proj = cloned_run
    rc = rg.main(["release_gate.py", base, str(proj.parent)])
    assert rc == 1  # BLOCK (the real fabricated name)
    assert (proj / f"{base}{config.SUFFIX_RUN_MANIFEST}").exists()


def test_cli_auto_discovers_run_under_processed_dir(cloned_run, monkeypatch):
    """User layout: runs live under PROCESSED_DIR/projects while PROJECTS_DIR
    points at an (empty) default. The CLI must still find the run."""
    base, proj = cloned_run  # proj.parent == <tmp>/projects
    tmp = proj.parent.parent
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp / "unused-default")
    monkeypatch.setattr(config, "PROCESSED_DIR", tmp)  # PROCESSED_DIR/projects == proj.parent
    rc = rg.main(["release_gate.py", base])  # no override arg
    assert rc == 1
    assert (proj / f"{base}{config.SUFFIX_RUN_MANIFEST}").exists()


def test_m7b1_exit_code_reflects_decision(cloned_run):
    base, proj = cloned_run
    assert rg.main(["release_gate.py", base]) == 1  # BLOCK -> nonzero
    ab = proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}"
    ab.write_text(ab.read_text().replace("Luciano Malorni", "Michael Kerr"))
    assert rg.main(["release_gate.py", base]) == 0  # clean -> zero


# --------------------------------------------------------------- M1.B.2 publish guard
def test_m1b2_blocked_run_writes_no_bundle(cloned_run):
    """The publish path must write NO bundle when the gate BLOCKs, and leave a
    PUBLISH-BLOCKED marker instead (real run: fabricated 'Luciano Malorni')."""
    import html_generator

    base, proj = cloned_run
    ok = html_generator.generate_simple_webpage(base)
    assert ok is False
    assert not (proj / f"{base}{config.SUFFIX_WEBPAGE_SIMPLE}").exists()
    assert (proj / f"{base}{config.SUFFIX_PUBLISH_BLOCKED}").exists()


def test_f5_publish_guard_writes_manifest_tied_to_decision(cloned_run):
    """A gated publish leaves a run-manifest reflecting the decision that gated
    (not a separate later gate run)."""
    base, proj = cloned_run
    assert rg.publish_allowed(base, logging.getLogger("t")) is False  # BLOCK (Malorni)
    manifest_path = proj / f"{base}{config.SUFFIX_RUN_MANIFEST}"
    assert manifest_path.exists()
    m = json.loads(manifest_path.read_text())
    assert m["publish_decision"] == "BLOCK"
    assert m["gate"]["blockers"], "the blocking verdict must be recorded in the manifest"


def test_m1b2_publish_allowed_reflects_gate(cloned_run):
    base, proj = cloned_run
    marker = proj / f"{base}{config.SUFFIX_PUBLISH_BLOCKED}"
    assert rg.publish_allowed(base, logging.getLogger("t")) is False
    assert marker.exists()
    # clean the fabricated name -> allowed, marker cleared
    ab = proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}"
    ab.write_text(ab.read_text().replace("Luciano Malorni", "Michael Kerr"))
    assert rg.publish_allowed(base, logging.getLogger("t")) is True
    assert not marker.exists()


def test_m7_clean_rerun_clears_stale_block_marker(cloned_run):
    """P8: a now-clean re-run must clear a prior BLOCK marker, not leave it stale."""
    base, proj = cloned_run
    marker = proj / f"{base}{config.SUFFIX_PUBLISH_BLOCKED}"
    rg.gate_and_report(base, "t1", logging.getLogger("t"))
    assert marker.exists()
    ab = proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}"
    ab.write_text(ab.read_text().replace("Luciano Malorni", "Michael Kerr"))
    rg.gate_and_report(base, "t2", logging.getLogger("t"))
    assert not marker.exists()
