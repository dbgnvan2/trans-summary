"""Review 2026-07-18 batch 4 — release-gate observability & correctness:
- M8: a NON-blocking "could-not-verify" (ERROR in an advisory check) must be visible in
  the gate's log, not ship silently as a clean ALLOW_WITH_WARNINGS.
- L1: the entity-consistency name regex must not join proper names across a newline
  (which fabricated near-duplicate 'clashes').
"""
import logging

import config
import release_gate as rg


def test_m8_gate_surfaces_nonblocking_error(caplog):
    def advisory_error(base_name, logger):
        return rg.Verdict("fake_advisory", rg.Status.ERROR, "could not verify X")

    checks = [("fake_advisory", advisory_error)]
    with caplog.at_level(logging.INFO):
        decision = rg.run_gate("somebase", logger=logging.getLogger("m8-test"), checks=checks)

    # a non-hard-blocking check's ERROR ships as ALLOW_WITH_WARNINGS ...
    assert decision.decision == rg.Decision.ALLOW_WITH_WARNINGS
    # ... but is now VISIBLE: the summary line counts errors, and a per-error line names it
    assert "error(s)" in caplog.text
    assert "UNVERIFIED" in caplog.text
    assert "fake_advisory" in caplog.text


def test_l1_names_not_joined_across_newlines(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    base = "sample"
    proj = tmp_path / base
    proj.mkdir()
    suffixes = config.GATE_CONSISTENCY_ARTIFACT_SUFFIXES
    (proj / f"{base}{suffixes[0]}").write_text(
        "Differentiation Process anchors the model.\n", encoding="utf-8")
    # 'Differentiation' and 'Processes' on ADJACENT lines must NOT be joined into a
    # name — under the old \s+ regex they became "Differentiation Processes", a false
    # near-duplicate of "Differentiation Process" -> a spurious WARN.
    (proj / f"{base}{suffixes[1]}").write_text(
        "This theme concerns Differentiation\nProcesses in the family.\n", encoding="utf-8")

    v = rg.check_entity_consistency(base, None)
    assert v.status == rg.Status.PASS, f"false clash from cross-newline join: {v.detail} {v.items}"
