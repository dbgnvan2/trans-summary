"""D2 — only PASS verdicts are kept in the cross-process judge cache. A FAIL is
re-judged on the next gate run instead of being replayed from disk ("sticky FAIL");
a FAIL left on disk by an older version is ignored (dirty state, P8). Once a key has
been judged FAIL, a later PASS is not stored either, so one lucky PASS from a judge
without temperature cannot become permanent (sweep finding 1).

Spec: docs/plan_todo_triage_2026-10-11.md#D2
"""
import json

import config
import faithfulness_judge as fj
import release_gate as rg


def _result(status, unfaithful=()):
    return fj.FaithfulnessResult(status=status, detail=status,
                                 claims=[fj.ClaimVerdict(c, "unsupported") for c in unfaithful])


def _cold(monkeypatch):
    monkeypatch.setattr(rg, "_FAITHFULNESS_CACHE", {})
    monkeypatch.setattr(rg, "_THEME_JUDGE_CACHE", {})


def test_d2_fail_is_not_persisted_and_is_rejudged(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    _cold(monkeypatch)
    # after the FAIL the key is flagged, so the re-run needs two PASSes in a row
    results = [_result(fj.FAIL, ["fabricated claim"]), _result(fj.PASS), _result(fj.PASS)]
    monkeypatch.setattr(fj, "judge_artifact", lambda a, s, c, logger=None: results.pop(0))
    assert rg._judge_cached(fj, "art", "src", object(), None).status == fj.FAIL
    assert all(v.get("status") != fj.FAIL for v in rg._load_judge_disk_cache().values())
    _cold(monkeypatch)  # a later gate run in a new process
    assert rg._judge_cached(fj, "art", "src", object(), None).status == fj.PASS
    assert results == []  # judged again (twice) on the re-run


def test_d2_fail_left_on_disk_is_ignored(tmp_path, monkeypatch):
    """Dirty state (P8): a FAIL stored by an older version is not replayed."""
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    _cold(monkeypatch)
    monkeypatch.setattr(rg, "_judge_logic_version", lambda _i: "fixed")
    import hashlib
    a = hashlib.sha256(b"art").hexdigest()
    s = hashlib.sha256(b"src").hexdigest()
    key = f"{a}:{s}:{config.FAITHFULNESS_JUDGE_MODEL}:fixed"
    (tmp_path / "gate_judge_cache.json").write_text(json.dumps(
        {key: _result(fj.FAIL, ["old false flag"]).to_dict()}), encoding="utf-8")
    calls = []
    monkeypatch.setattr(fj, "judge_artifact",
                        lambda a, s, c, logger=None: calls.append(1) or _result(fj.PASS))
    assert rg._judge_cached(fj, "art", "src", object(), None).status == fj.PASS
    assert calls == [1, 1]  # an old FAIL counts as flagged: two PASSes needed (re-check 2)
    # ... and the old FAIL entry is not overwritten by a PASS (re-check 1)
    assert all(v.get("status") != fj.PASS for v in rg._load_judge_disk_cache().values())


def test_d2_pass_is_still_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    _cold(monkeypatch)
    calls = []
    monkeypatch.setattr(fj, "judge_artifact",
                        lambda a, s, c, logger=None: calls.append(1) or _result(fj.PASS))
    rg._judge_cached(fj, "art", "src", object(), None)
    _cold(monkeypatch)
    rg._judge_cached(fj, "art", "src", object(), None)
    assert calls == [1]


def test_d2_theme_fail_is_not_persisted(tmp_path, monkeypatch):
    """P5 sibling: the theme judge cache follows the same rule."""
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    _cold(monkeypatch)
    calls = []
    monkeypatch.setattr(fj, "judge_themes_artifact",
                        lambda t, s, k, c, logger=None: calls.append(1) or _result(fj.FAIL, ["x"]))
    rg._judge_theme_cached(fj, "themes", "src", "structural", object(), None)
    _cold(monkeypatch)
    rg._judge_theme_cached(fj, "themes", "src", "structural", object(), None)
    assert calls == [1, 1]


def test_d2_blog_grounding_with_ungrounded_label_not_persisted(tmp_path, monkeypatch):
    """P5 sibling: blog grounding labels are stored only when every claim is grounded."""
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rg, "_BLOG_GROUNDING_CACHE", {})
    monkeypatch.setattr(fj, "judge_themes", lambda items, s, c, logger=None: [
        fj.ClaimVerdict(i["name"], "ungrounded" if "bad" in i["name"] else "grounded") for i in items])
    rg._judge_blog_grounding_cached(fj, ["good claim", "bad claim"], "src", object(), None)
    assert not any("labels" in v for v in rg._load_judge_disk_cache().values())
    rg._judge_blog_grounding_cached(fj, ["good claim"], "src", object(), None)
    assert sum("labels" in v for v in rg._load_judge_disk_cache().values()) == 1


def test_d2_pass_after_a_fail_is_not_persisted(tmp_path, monkeypatch):
    """Sweep finding 1: FAIL, then a lucky PASS — the next process re-judges."""
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    # run 1 FAIL; run 2 PASS then PASS (two in a row) -> PASS, not stored;
    # run 3 judged again: PASS then FAIL -> FAIL
    results = [_result(fj.FAIL, ["x"]), _result(fj.PASS), _result(fj.PASS),
               _result(fj.PASS), _result(fj.FAIL, ["x"])]
    monkeypatch.setattr(fj, "judge_artifact", lambda a, s, c, logger=None: results.pop(0))
    statuses = []
    for _ in range(3):
        _cold(monkeypatch)
        statuses.append(rg._judge_cached(fj, "art", "src", object(), None).status)
    assert statuses == [fj.FAIL, fj.PASS, fj.FAIL] and results == []


def test_d2_flagged_needs_two_passes_in_a_row(tmp_path, monkeypatch):
    """Re-check 2: after a FAIL, one lucky PASS does not pass the run."""
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    results = [_result(fj.FAIL, ["x"]), _result(fj.PASS), _result(fj.FAIL, ["x"])]
    monkeypatch.setattr(fj, "judge_artifact", lambda a, s, c, logger=None: results.pop(0))
    _cold(monkeypatch)
    rg._judge_cached(fj, "art", "src", object(), None)
    _cold(monkeypatch)
    assert rg._judge_cached(fj, "art", "src", object(), None).status == fj.FAIL
    assert results == []


def test_d2_theme_pass_after_a_fail_is_not_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    # FAIL; then PASS+PASS (flagged -> confirmed, not stored); then judged again
    results = [_result(fj.FAIL, ["x"]), _result(fj.PASS), _result(fj.PASS),
               _result(fj.PASS), _result(fj.PASS)]
    monkeypatch.setattr(fj, "judge_themes_artifact",
                        lambda t, s, k, c, logger=None: results.pop(0))
    for _ in range(3):
        _cold(monkeypatch)
        rg._judge_theme_cached(fj, "themes", "src", "structural", object(), None)
    assert results == []


def test_d2_blog_pass_after_a_flag_is_not_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    labels = [["ungrounded"], ["grounded"], ["grounded"]]
    calls = []

    def fake(items, s, c, logger=None):
        calls.append(1)
        return [fj.ClaimVerdict(i["name"], lab) for i, lab in zip(items, labels.pop(0))]
    monkeypatch.setattr(fj, "judge_themes", fake)
    for _ in range(3):
        monkeypatch.setattr(rg, "_BLOG_GROUNDING_CACHE", {})
        rg._judge_blog_grounding_cached(fj, ["a claim"], "src", object(), None)
    assert len(calls) == 3
