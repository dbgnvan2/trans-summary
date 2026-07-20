"""Review 2026-07-18 batch 5 — release-gate manifest & theme-grounding branch:
- M9: the run manifest must stamp the code revision and the gate policy so a publish
  decision can be traced to the code + policy that produced it.
- L18: check_theme_grounding's 'no theme artifacts -> PASS' branch (previously untested,
  asymmetric with faithfulness) is now pinned.
"""
import config
import release_gate as rg


def test_m9_manifest_stamps_code_revision_and_gate_policy(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    (tmp_path / "b").mkdir()
    decision = rg.GateDecision(rg.Decision.ALLOW, [], [])
    prov = rg.build_manifest("b", decision, "2026-07-18T00:00:00")["provenance"]
    assert "code_revision" in prov and isinstance(prov["code_revision"], str)
    assert "gate_policy" in prov
    assert "faithfulness" in prov["gate_policy"]["blocking_checks"]
    assert prov["gate_policy"]["error_blocks"] is True


def test_l18_theme_grounding_passes_when_no_theme_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "THEME_JUDGE_ENABLED", True)
    # key resolver is imported inside the function from transcript_utils
    monkeypatch.setattr("transcript_utils.resolve_anthropic_key", lambda: "sk-test-not-used")
    base = "sample"
    proj = tmp_path / base
    proj.mkdir()
    # a source transcript so we get past the source check, but NO theme artifacts
    (proj / f"{base}{config.SUFFIX_FORMATTED}").write_text(
        "A transcript about families and systems.", encoding="utf-8")

    v = rg.check_theme_grounding(base, None)
    assert v.status == rg.Status.PASS
    assert "no theme artifacts" in v.detail
