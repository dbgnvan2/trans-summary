"""H2 (review 2026-07-18): the judge memo must survive across subprocesses so the CLI
orchestrator (which runs each publish step in its own process) doesn't re-run the armed
judge N times per publish. A disk memo keyed on content+model+prompt-version backs the
in-memory cache; a transient ERROR is never persisted (P1); corrupt cache -> empty (P8).
"""
import config
import faithfulness_judge as fj
import release_gate as rg


def _result(status, detail="", unfaithful=None):
    claims = [fj.ClaimVerdict(claim=c, label="unsupported") for c in (unfaithful or [])]
    return fj.FaithfulnessResult(status=status, detail=detail, claims=claims)


def test_h2_verdict_survives_cold_memory_via_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rg, "_FAITHFULNESS_CACHE", {})
    calls = {"n": 0}

    def fake_judge(art, src, client, logger=None):
        calls["n"] += 1
        return _result(fj.PASS)

    monkeypatch.setattr(fj, "judge_artifact", fake_judge)
    r1 = rg._judge_cached(fj, "abstract text", "source text", object(), None)
    assert r1.status == fj.PASS and calls["n"] == 1

    # simulate a SEPARATE subprocess: the in-memory memo is cold
    monkeypatch.setattr(rg, "_FAITHFULNESS_CACHE", {})
    r2 = rg._judge_cached(fj, "abstract text", "source text", object(), None)
    assert r2.status == fj.PASS
    assert calls["n"] == 1, "cold-memory call must hit the DISK cache, not re-judge"


def test_h2_error_is_never_persisted(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rg, "_FAITHFULNESS_CACHE", {})
    monkeypatch.setattr(fj, "judge_artifact", lambda a, s, c, logger=None: _result(fj.ERROR, "no key"))
    rg._judge_cached(fj, "a", "s", object(), None)
    assert rg._load_judge_disk_cache() == {}, "a transient ERROR must not be cached (P1)"


def test_h2_corrupt_or_nondict_cache_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    (tmp_path / "gate_judge_cache.json").write_text("{ not valid json", encoding="utf-8")
    assert rg._load_judge_disk_cache() == {}
    (tmp_path / "gate_judge_cache.json").write_text("[]", encoding="utf-8")
    assert rg._load_judge_disk_cache() == {}


def test_h2_fail_verdict_roundtrips_its_unfaithful_claims(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rg, "_FAITHFULNESS_CACHE", {})
    monkeypatch.setattr(
        fj, "judge_artifact",
        lambda a, s, c, logger=None: _result(fj.FAIL, "1 unfaithful", ["fabricated claim"]))
    rg._judge_cached(fj, "art", "src", object(), None)

    monkeypatch.setattr(rg, "_FAITHFULNESS_CACHE", {})

    def _boom(*a, **k):
        raise AssertionError("cold-memory call must read disk, not re-judge")

    monkeypatch.setattr(fj, "judge_artifact", _boom)
    r = rg._judge_cached(fj, "art", "src", object(), None)
    assert r.status == fj.FAIL
    assert [c.claim for c in r.unfaithful] == ["fabricated claim"]


def test_h2_logic_version_change_invalidates_cached_pass(tmp_path, monkeypatch):
    """A change to the judge LOGIC (JUDGE_LOGIC_VERSION / extraction config) must
    invalidate a persisted PASS so a stricter judge can't serve a laxer cached verdict
    on the armed gate (H2 finding 1 — a fail-open)."""
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rg, "_FAITHFULNESS_CACHE", {})
    calls = {"n": 0}

    def fake(a, s, c, logger=None):
        calls["n"] += 1
        return _result(fj.PASS)

    monkeypatch.setattr(fj, "judge_artifact", fake)
    rg._judge_cached(fj, "art", "src", object(), None)
    assert calls["n"] == 1

    # bump the logic version -> cold memory must NOT reuse the now-stale disk PASS
    monkeypatch.setattr(rg, "_FAITHFULNESS_CACHE", {})
    monkeypatch.setattr(config, "JUDGE_LOGIC_VERSION", "bumped-different-version")
    rg._judge_cached(fj, "art", "src", object(), None)
    assert calls["n"] == 2, "logic-version change must force a re-judge, not serve stale PASS"


def test_h2_routing_code_change_invalidates_by_construction(monkeypatch):
    """The routing ALGORITHM (margin-vs-second heuristic vs structural all-anchored) is
    folded into the cache key as its source, so a code-only routing change invalidates a
    cached verdict even if the developer forgets to bump JUDGE_LOGIC_VERSION (P6/P4)."""
    import inspect as inspect_mod

    real_getsource = inspect_mod.getsource
    before = rg._judge_logic_version("instructions")
    # simulate a routing-code edit: the function source text changes
    monkeypatch.setattr(
        inspect_mod, "getsource",
        lambda fn: real_getsource(fn) + "\n# simulated routing-code change")
    after = rg._judge_logic_version("instructions")
    assert before != after, "routing-code change must change the cache key (by construction)"


def test_h2_theme_judge_also_persists_to_disk(tmp_path, monkeypatch):
    """The theme judge (the other armed hard blocker) gets the same cross-process disk
    memo (H2 finding 2 / P5)."""
    monkeypatch.setattr(config, "LOGS_DIR", tmp_path)
    monkeypatch.setattr(rg, "_THEME_JUDGE_CACHE", {})
    calls = {"n": 0}

    def fake(text, source, kind, client, logger=None):
        calls["n"] += 1
        return _result(fj.PASS)

    monkeypatch.setattr(fj, "judge_themes_artifact", fake)
    rg._judge_theme_cached(fj, "themes md", "source text", "structural", object(), None)
    assert calls["n"] == 1
    monkeypatch.setattr(rg, "_THEME_JUDGE_CACHE", {})  # cold memory (separate subprocess)
    rg._judge_theme_cached(fj, "themes md", "source text", "structural", object(), None)
    assert calls["n"] == 1, "theme judge cold-memory call must hit the DISK cache"
