"""Abstract generation regenerates (with corrective feedback) until it passes the
gate's faithfulness + entity checks — so an unfaithful abstract is caught and
fixed at generation time, not only at publish."""

import logging

import config
import abstract_pipeline as ap
import extraction_pipeline as ep
import release_gate as rg


def _setup(monkeypatch, tmp_path, base="Talk Title - Some Author - 2025-01-01"):
    proj = tmp_path / base
    proj.mkdir(parents=True)
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config, "ABSTRACT_MAX_ATTEMPTS", 3)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    monkeypatch.setattr(ep, "load_project_transcript", lambda *a, **k: "transcript words " * 100)
    monkeypatch.setattr(ep, "_load_section_from_project_file", lambda *a, **k: "- Topic one\n- Topic two")
    monkeypatch.setattr(ep.abstract_pipeline, "parse_topics_from_extraction", lambda *a, **k: ["t1", "t2"])

    class _AI:
        topics = ["t1", "t2"]
        themes = []

    monkeypatch.setattr(ep.abstract_pipeline, "prepare_abstract_input", lambda **k: _AI())
    monkeypatch.setattr(ep, "create_system_message_with_cache",
                        lambda *a, **k: [{"type": "text", "text": "sys"}])
    monkeypatch.setattr(ep.anthropic, "Anthropic", lambda api_key=None: object())
    return base, proj


def _log():
    return logging.getLogger("test_abstract_retry")


def test_passes_on_first_attempt_no_feedback(monkeypatch, tmp_path):
    base, _ = _setup(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract",
                        lambda ai, client, model=None, system=None, feedback_claims=None:
                        (calls.append(feedback_claims) or "abstract text"))
    monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: ("pass", []))

    assert ep.generate_structured_abstract(base, logger=_log()) is True
    assert calls == [None]  # generated once, no feedback


def test_retries_then_passes_feeding_issues_back(monkeypatch, tmp_path):
    base, _ = _setup(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract",
                        lambda ai, client, model=None, system=None, feedback_claims=None:
                        (calls.append(feedback_claims) or "text"))
    seq = iter([("fail", ["claim X is unsupported"]), ("pass", [])])
    monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: next(seq))

    assert ep.generate_structured_abstract(base, logger=_log()) is True
    # second attempt was given the first attempt's failing claim as feedback
    assert calls == [None, ["claim X is unsupported"]]


def test_all_attempts_fail_keeps_least_bad_draft(monkeypatch, tmp_path):
    base, proj = _setup(monkeypatch, tmp_path)
    texts = iter(["draft-1", "draft-2-best", "draft-3"])
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract",
                        lambda ai, client, model=None, system=None, feedback_claims=None: next(texts))
    # 3 issues, then 1 issue (best), then 2 issues
    seq = iter([("fail", ["a", "b", "c"]), ("fail", ["a"]), ("fail", ["a", "b"])])
    monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: next(seq))

    assert ep.generate_structured_abstract(base, logger=_log()) is True
    saved = (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").read_text(encoding="utf-8")
    assert saved == "draft-2-best"  # kept the draft with the fewest issues


def test_unavailable_check_generates_once(monkeypatch, tmp_path):
    base, _ = _setup(monkeypatch, tmp_path)
    calls = []
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract",
                        lambda ai, client, model=None, system=None, feedback_claims=None:
                        (calls.append(1) or "text"))
    monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: ("unavailable", []))

    assert ep.generate_structured_abstract(base, logger=_log()) is True
    assert len(calls) == 1  # no retry when the check can't run


# --- units ------------------------------------------------------------------

def test_generate_abstract_injects_feedback_into_prompt(monkeypatch):
    captured = {}

    def _fake_call(**kwargs):
        captured["prompt"] = kwargs["messages"][0]["content"]

        class _M:
            content = [type("X", (), {"text": "abstract"})()]

        return _M()

    monkeypatch.setattr(ap, "call_claude_with_retry", _fake_call)
    monkeypatch.setattr(ap, "load_prompt", lambda: "Body t={target_word_count} j={input_json}")

    class _AI:
        target_word_count = 200

        def to_json(self):
            return "{}"

    ap.generate_abstract(_AI(), api_client=object(),
                         feedback_claims=["claim X is not supported"])
    assert "CORRECTION REQUIRED" in captured["prompt"]
    assert "claim X is not supported" in captured["prompt"]


def test_gate_precheck_classifies_pass_fail_unavailable(monkeypatch):
    def _fk(**k):
        pass

    # pass
    monkeypatch.setattr(rg, "check_faithfulness",
                        lambda b, l=None: rg.Verdict("faithfulness", rg.Status.PASS, ""))
    monkeypatch.setattr(rg, "check_entity_grounding",
                        lambda b, l=None: rg.Verdict("entity_grounding", rg.Status.PASS, ""))
    assert ep._abstract_gate_precheck("b")[0] == "pass"

    # fail -> issues include the specific unfaithful claim
    monkeypatch.setattr(rg, "check_faithfulness",
                        lambda b, l=None: rg.Verdict("faithfulness", rg.Status.FAIL, "d",
                                                     items=[{"unfaithful": ["claim X"]}]))
    status, issues = ep._abstract_gate_precheck("b")
    assert status == "fail" and "claim X" in issues

    # ERROR (no key / disabled) -> unavailable
    monkeypatch.setattr(rg, "check_faithfulness",
                        lambda b, l=None: rg.Verdict("faithfulness", rg.Status.ERROR, "no key"))
    assert ep._abstract_gate_precheck("b")[0] == "unavailable"
