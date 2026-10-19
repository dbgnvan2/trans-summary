"""Abstract generation retries (with corrective feedback) until it passes the
gate's faithfulness + entity checks — so an unfaithful abstract is caught and
fixed at generation time, not only at publish. Since RS.6 a retry revises the
flagged sentences of the previous draft (``_revise_flagged``); these loop tests
stub it to hand off to their fake ``generate_abstract``."""

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
    monkeypatch.setattr(ep, "get_anthropic_client", lambda *a, **k: object())
    monkeypatch.setattr(ep, "_revise_flagged",
                        lambda what, draft, claims, **k: ep.abstract_pipeline.generate_abstract(
                            None, None, feedback_claims=claims))
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


def test_r11a_all_attempts_fail_returns_false_and_keeps_least_bad_draft(monkeypatch, tmp_path):
    """Plan R11: an abstract that never passes faithfulness fails the stage; the
    least-bad draft is still saved for editing."""
    base, proj = _setup(monkeypatch, tmp_path)
    texts = iter(["draft-1", "draft-2-best", "draft-3"])
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract",
                        lambda ai, client, model=None, system=None, feedback_claims=None: next(texts))
    # 3 issues, then 1 issue (best), then 2 issues
    seq = iter([("fail", ["a", "b", "c"]), ("fail", ["a"]), ("fail", ["a", "b"])])
    monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: next(seq))

    assert ep.generate_structured_abstract(base, logger=_log()) is False
    saved = (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").read_text(encoding="utf-8")
    assert saved == "draft-2-best"  # kept the draft with the fewest issues


def test_r11b_unavailable_check_generates_once_and_succeeds(monkeypatch, tmp_path):
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
                        lambda b, l=None, suffixes=None: rg.Verdict("faithfulness", rg.Status.PASS, ""))
    monkeypatch.setattr(rg, "check_entity_grounding",
                        lambda b, l=None: rg.Verdict("entity_grounding", rg.Status.PASS, ""))
    assert ep._abstract_gate_precheck("b")[0] == "pass"

    # fail -> issues include the specific unfaithful claim
    monkeypatch.setattr(rg, "check_faithfulness",
                        lambda b, l=None, suffixes=None: rg.Verdict("faithfulness", rg.Status.FAIL, "d",
                                                     items=[{"unfaithful": ["claim X"]}]))
    status, issues = ep._abstract_gate_precheck("b")
    assert status == "fail" and "claim X" in issues

    # ERROR (no key / disabled) -> unavailable
    monkeypatch.setattr(rg, "check_faithfulness",
                        lambda b, l=None, suffixes=None: rg.Verdict("faithfulness", rg.Status.ERROR, "no key"))
    assert ep._abstract_gate_precheck("b")[0] == "unavailable"


def test_aq4_failed_later_attempt_keeps_the_best_draft(monkeypatch, tmp_path):
    """AQ review: generation can now fail outright (every retry over the word limit).
    On a later attempt the best earlier draft is kept and the stage fails; before, the
    exception left the last written draft in the file."""
    base, proj = _setup(monkeypatch, tmp_path)
    texts = iter(["draft-1-best", "draft-2"])

    def generate(ai, client, model=None, system=None, feedback_claims=None):
        try:
            return next(texts)
        except StopIteration:
            raise ValueError("Response text too long: 265 words (expected <= 249)")
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract", generate)
    seq = iter([("fail", ["a"]), ("fail", ["a", "b"])])
    monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: next(seq))

    assert ep.generate_structured_abstract(base, logger=_log()) is False
    saved = (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").read_text(encoding="utf-8")
    assert saved == "draft-1-best"


def test_aq4_final_message_names_the_failed_attempt(monkeypatch, tmp_path, caplog):
    """AQ review: the closing error gives the attempt that could not be generated and
    why, not "after 3 attempts" and a faithfulness reason."""
    base, proj = _setup(monkeypatch, tmp_path)
    texts = iter(["draft-1"])

    def generate(*a, **k):
        try:
            return next(texts)
        except StopIteration:
            raise ValueError("Response text too long: 265 words (expected <= 249)")
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract", generate)
    monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: ("fail", ["a"]))
    with caplog.at_level(logging.ERROR):
        assert ep.generate_structured_abstract(base, logger=_log()) is False
    final = caplog.records[-1].getMessage()
    assert "attempt 2/3 could not be generated" in final and "too long" in final
    assert "after 3 attempt" not in final


def test_aq4_failed_first_attempt_fails_the_stage(monkeypatch, tmp_path, caplog):
    base, proj = _setup(monkeypatch, tmp_path)

    def generate(*a, **k):
        raise ValueError("Response text too long: 265 words (expected <= 249)")
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract", generate)
    with caplog.at_level(logging.ERROR):
        assert ep.generate_structured_abstract(base, logger=_log()) is False
    assert not (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").exists()
    # no draft to keep: the error itself is reported, not a kept-draft message
    assert any("Error generating structured abstract" in r.getMessage() for r in caplog.records)
    assert not any("kept the" in r.getMessage() for r in caplog.records)


def test_rs6d_abstract_retry_revises_previous_draft(monkeypatch, tmp_path):
    """RS.6 (docs/plan_run_safe_2026-10-14.md): try 2 revises try 1's flagged sentences."""
    base, proj = _setup(monkeypatch, tmp_path)
    generated, revised = [], []
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract",
                        lambda ai, client, model=None, system=None, feedback_claims=None:
                        generated.append(feedback_claims) or "draft one")
    monkeypatch.setattr(ep, "_revise_flagged",
                        lambda what, draft, claims, **k: revised.append((what, draft, claims, k))
                        or " draft two \n")
    seq = iter([("fail", ["claim X is unsupported"]), ("pass", [])])
    monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: next(seq))

    assert ep.generate_structured_abstract(base, logger=_log(), model="m") is True
    assert generated == [None]
    what, draft, claims, k = revised[0]
    assert (what, draft, claims) == ("abstract", "draft one", ["claim X is unsupported"])
    assert k["max_words"] == config.ABSTRACT_HARD_MAX_WORDS - 1 and k["word_limits"] == "soft"
    assert k["model"] == "m" and k["system"] == [{"type": "text", "text": "sys"}]
    saved = (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").read_text(encoding="utf-8")
    assert saved == "draft two"


def test_rs1h_abstract_stage_log_names_a_kept_length_miss(monkeypatch, tmp_path, caplog):
    base, proj = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract",
                        lambda *a, **k: " ".join(["word"] * 265))
    monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: ("pass", []))
    with caplog.at_level(logging.WARNING, logger="test_abstract_retry"):
        assert ep.generate_structured_abstract(base, logger=_log()) is True
    assert any("265 words" in r.getMessage() for r in caplog.records)


def test_sc2d_abstract_tie_keeps_the_later_draft(monkeypatch, tmp_path):
    """SC2 (docs/plan_summary_closing_2026-10-18.md): on a tie in flagged issues the
    later draft is kept, as in the summary loop; fewer issues still win."""
    for counts, expected in (((1, 1, 1), "draft-3"), ((2, 1, 1), "draft-3"),
                             ((1, 2, 2), "draft-1")):
        base, proj = _setup(monkeypatch, tmp_path / "-".join(map(str, counts)))
        texts = iter(["draft-1", "draft-2", "draft-3"])
        monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract",
                            lambda *a, **k: next(texts))
        seq = iter([("fail", [f"issue {i}" for i in range(n)]) for n in counts])
        monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: next(seq))
        assert ep.generate_structured_abstract(base, logger=_log()) is False
        saved = (proj / f"{base}{config.SUFFIX_ABSTRACT_GEN}").read_text(encoding="utf-8")
        assert saved == expected, counts


def test_sc3b_abstract_last_try_wording(monkeypatch, tmp_path, caplog):
    """SC3: the last try's warning says no attempts are left, not that it is revising."""
    base, _ = _setup(monkeypatch, tmp_path)
    texts = iter(["draft-1", "draft-2", "draft-3"])
    monkeypatch.setattr(ep.abstract_pipeline, "generate_abstract", lambda *a, **k: next(texts))
    seq = iter([("fail", ["issue a"]), ("fail", ["issue b"]), ("fail", ["issue c"])])
    monkeypatch.setattr(ep, "_abstract_gate_precheck", lambda b, logger=None: next(seq))
    with caplog.at_level(logging.WARNING, logger="test_abstract_retry"):
        assert ep.generate_structured_abstract(base, logger=_log()) is False
    tries = [r.getMessage() for r in caplog.records if "not faithful" in r.getMessage()]
    assert len(tries) == 3
    assert all("revising the flagged sentences" in t for t in tries[:2])
    assert "attempt 3/3" in tries[2] and "no attempts left" in tries[2]
    assert "revising" not in tries[2]
