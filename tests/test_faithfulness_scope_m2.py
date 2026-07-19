"""M2 (review 2026-07-18): the abstract regeneration precheck must judge the ABSTRACT
only, not every narrative artifact. Otherwise an unfaithful claim in a sibling artifact
(summary/overview/blog already on disk) is blamed on the abstract, burning regeneration
attempts. The publish gate still judges the full set (default).
"""
import types

import config
import release_gate as rg


def test_m2_check_faithfulness_scope_limits_judged_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "FAITHFULNESS_JUDGE_ENABLED", True)
    monkeypatch.setattr("transcript_utils.resolve_anthropic_key", lambda: "sk-test-not-used")

    base = "b"
    proj = tmp_path / base
    proj.mkdir()
    (proj / f"{base}{config.SUFFIX_FORMATTED}").write_text("the source transcript text", encoding="utf-8")
    (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").write_text("abstract body", encoding="utf-8")
    (proj / f"{base}{config.SUFFIX_SUMMARY_GEN}").write_text("summary body", encoding="utf-8")

    judged = []

    def fake_judge(fjudge, text, transcript, client, logger):
        judged.append(text)
        return types.SimpleNamespace(status=fjudge.PASS, detail="", unfaithful=[])

    monkeypatch.setattr(rg, "_judge_cached", fake_judge)

    # scoped to the abstract only -> exactly one artifact judged
    judged.clear()
    rg.check_faithfulness(base, None, suffixes=[config.SUFFIX_ABSTRACT_GEN])
    assert len(judged) == 1 and "abstract body" in judged[0], judged

    # default (publish gate) -> all present narrative artifacts judged
    judged.clear()
    rg.check_faithfulness(base, None)
    assert len(judged) >= 2, judged
