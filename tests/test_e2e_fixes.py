"""Fixes for the problems the first end-to-end run found (E2E, 2026-10-13).

E2E1 abstract input figures · E2E2 theme names · E2E3 emphasis token ceiling ·
E2E4 approved-terms file location · E2E5 tests writing the real settings file.
See TODO.md "2026-10-13 — End-to-end run findings (E2E)".
"""
import json
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import abstract_pipeline as ap
import config
import ts_gui
import transcript_utils as tu

ROOT = Path(__file__).resolve().parent.parent


def _input(qa_percentage, qa_topics=("q one",)):
    return ap.AbstractInput(
        metadata={"title": "Talk", "presenter": "A Person", "date": "2021-01-01"},
        topics=[ap.Topic(name="Cancer as a niche problem", percentage=37, sections="6-7, 17-22"),
                ap.Topic(name="Stress and the organism", percentage=23, sections="41-48")],
        themes=[], opening_purpose="o", closing_conclusion=config.NO_CONCLUSION_TEXT,
        qa_percentage=qa_percentage,
        qa_topics=list(qa_topics), target_word_count=200)


# --- E2E1: the abstract model gets no figures the transcript does not state ----------

def test_e2e1_abstract_payload_has_no_figures():
    data = json.loads(_input(qa_percentage=15).to_json())
    text = json.dumps(data)
    assert data["topics"] == ["Cancer as a niche problem", "Stress and the organism"]
    for figure in ("37", "23", "17-22", "41-48", "15"):  # coverage, sections, Q&A share
        assert figure not in text, figure
    assert "qa_percentage" not in data and "percentage" not in text
    assert data["include_qa_note"] is False and "qa_topics" not in data


def test_e2e1_qa_note_threshold_is_decided_in_code():
    at = json.loads(_input(config.ABSTRACT_QA_NOTE_MIN_PCT).to_json())
    above = json.loads(_input(config.ABSTRACT_QA_NOTE_MIN_PCT + 1).to_json())
    assert at["include_qa_note"] is False
    assert above["include_qa_note"] is True and "qa_topics" not in above


def test_e2e1_contract_dict_keeps_the_full_data():
    d = _input(15).to_contract_dict()
    assert d["qa_percentage"] == 15 and d["topics"][0]["percentage"] == 37


def test_e2e1_prompt_matches_the_payload():
    prompt = ap.load_prompt()
    assert "qa_percentage" not in prompt and "include_qa_note" in prompt
    assert "No percentages or proportions" in prompt
    assert "If closing_conclusion is empty, leave this component out" in prompt
    filled = prompt.format(input_json=_input(25).to_json(), target_word_count=200,
                           hard_max_words=250, hard_max_words_minus_one=249)
    assert "{" not in filled.split("Input data:")[0]  # every placeholder filled


@pytest.mark.parametrize("purpose", [config.PURPOSE_MISSING_TEXT, config.PURPOSE_EXTRACTION_FAILED])
def test_e2e1_not_found_texts_reach_the_model_as_empty(purpose):
    """E2E review: the producer never returns "" for a missing conclusion; it returns a
    fixed text, which the model was told to restate. Use the real producer's value."""
    import abstract_pipeline as ap2
    assert ap2.extract_closing_conclusion("## Section 1\nNothing here.", 1) == config.NO_CONCLUSION_TEXT
    inp = _input(10)
    inp.opening_purpose = purpose
    data = json.loads(inp.to_json())
    assert data["closing_conclusion"] == "" and data["opening_purpose"] == ""
    inp.opening_purpose, inp.closing_conclusion = "To show X.", "So the answer is Y."
    data = json.loads(inp.to_json())
    assert data["opening_purpose"] == "To show X." and data["closing_conclusion"] == "So the answer is Y."


def test_e2e1_topics_in_presentation_order():
    """E2E review: self.topics is sorted by coverage; without section numbers the model
    needs them in the order the talk presents them."""
    inp = _input(10)
    inp.topics = [ap.Topic("Late but big", 40, "30-40"), ap.Topic("Early", 20, "2-5"),
                  ap.Topic("Middle", 25, "12, 18"), ap.Topic("Unplaced", 15, "")]
    assert json.loads(inp.to_json())["topics"] == ["Early", "Middle", "Late but big", "Unplaced"]


def test_e2e1_qa_thresholds_are_consistent():
    import abstract_validation as av
    assert av.QA_REQUIRED_THRESHOLD == config.ABSTRACT_QA_REQUIRED_PCT
    # a required Q&A item must be one the generator was told to write
    assert config.ABSTRACT_QA_NOTE_MIN_PCT < config.ABSTRACT_QA_REQUIRED_PCT


# --- E2E2: theme prompts forbid names the transcript does not say --------------------
# The model behaviour is integration-only (measured: docs in TODO E2E); this pins the rule.

@pytest.mark.parametrize("attr", ["PROMPT_STRUCTURAL_THEMES_FILENAME",
                                  "PROMPT_INTERPRETIVE_THEMES_FILENAME"])
def test_e2e2_theme_prompts_have_the_naming_rule(attr):
    text = (config.PROMPTS_DIR / getattr(config, attr)).read_text(encoding="utf-8")
    assert "Use only names the transcript says" in text
    assert "do not add a name from your own knowledge" in text


# --- E2E3: the extraction ceiling covers the measured emphasis reply -----------------

def test_e2e3_extraction_ceiling_above_the_failed_reply(monkeypatch):
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: None))
    req = tu.model_request_params("claude-sonnet-5-5", 0.0, config.MAX_TOKENS_EXTRACTION)
    # Systems Biology's emphasis reply went over 16,192 (8192 + headroom) and failed;
    # the largest successful one was 14,540. Keep clear room above both.
    assert req["max_tokens"] >= 16192 * 1.4
    assert req["max_tokens"] <= 128000  # within the model's output limit


def test_e2e3_ceiling_capped_for_every_model(monkeypatch):
    """E2E review (P5): an older model's 8,192 output limit applies even though it
    does not think, so the raised shared ceiling is not sent raw."""
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: None))
    legacy = "claude-3-5-haiku-20241022"
    assert tu.model_request_params(legacy, 0.0, config.MAX_TOKENS_EXTRACTION)["max_tokens"] == 8192


# --- E2E4: the approved-terms file is found next to the transcripts ------------------

@pytest.fixture
def paths(monkeypatch):
    for name in ("TRANSCRIPTS_BASE", "SOURCE_DIR", "PROCESSED_DIR", "PROJECTS_DIR",
                 "VALIDATION_APPROVED_TERMS_PATH"):
        monkeypatch.setattr(config.settings, name, getattr(config.settings, name))
        monkeypatch.setattr(config, name, getattr(config, name))


def test_e2e4_terms_file_in_the_chosen_source_folder_is_used(paths, tmp_path):
    src = tmp_path / "transcripts"
    src.mkdir()
    (src / "approve_terms.txt").write_text("Bowen\n", encoding="utf-8")
    config.set_source_dir_and_infer_base(src)  # base becomes tmp_path, which has no file
    assert config.VALIDATION_APPROVED_TERMS_PATH == src / "approve_terms.txt"
    config.set_validation_approved_terms_path(None)  # "Reset" uses the same rule
    assert config.VALIDATION_APPROVED_TERMS_PATH == src / "approve_terms.txt"


def test_e2e4_base_file_wins_and_missing_falls_back_to_base(paths, tmp_path):
    src = tmp_path / "source"
    src.mkdir()
    (src / "approve_terms.txt").write_text("a\n", encoding="utf-8")
    (tmp_path / "approve_terms.txt").write_text("b\n", encoding="utf-8")
    config.set_source_dir_and_infer_base(src)
    assert config.VALIDATION_APPROVED_TERMS_PATH == tmp_path / "approve_terms.txt"
    empty = tmp_path / "empty" / "transcripts"
    empty.mkdir(parents=True)
    config.set_source_dir_and_infer_base(empty)
    assert config.VALIDATION_APPROVED_TERMS_PATH == empty.parent / "approve_terms.txt"


def test_e2e4_init_val_warns_when_the_terms_file_is_missing(paths, tmp_path):
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.log = MagicMock()
    gui.terms_file_var = MagicMock()
    config.set_validation_approved_terms_path(tmp_path / "nope.txt")
    gui._warn_if_terms_missing()
    gui.update_terms_file_label()
    assert "Approved-terms file not found" in gui.log.call_args.args[0]
    assert gui.terms_file_var.set.call_args.args[0].endswith("(missing)")
    present = tmp_path / "approve_terms.txt"
    present.write_text("x\n", encoding="utf-8")
    config.set_validation_approved_terms_path(present)
    gui.log.reset_mock()
    gui._warn_if_terms_missing()
    gui.update_terms_file_label()
    gui.log.assert_not_called()
    assert "(missing)" not in gui.terms_file_var.set.call_args.args[0]


def test_e2e4_every_init_val_path_and_startup_warn():
    import inspect
    for name in ("do_initial_validation", "_run_initial_validation_auto", "__init__"):
        assert "self._warn_if_terms_missing()" in inspect.getsource(
            getattr(ts_gui.TranscriptProcessorGUI, name)), name


def test_e2e4_saved_terms_path_wins_at_startup(paths, tmp_path, monkeypatch):
    src = tmp_path / "transcripts"
    src.mkdir()
    (src / "approve_terms.txt").write_text("a\n", encoding="utf-8")
    saved = tmp_path / "my_terms.txt"
    settings_file = tmp_path / "rs.json"
    settings_file.write_text(json.dumps({"default_source_dir": str(src),
                                         "validation_approved_terms_path": str(saved)}),
                             encoding="utf-8")
    monkeypatch.setattr(config.settings, "_runtime_settings_path", lambda: settings_file)
    config.settings._load_runtime_settings()
    assert config.settings.VALIDATION_APPROVED_TERMS_PATH == saved


def test_e2e4_loader_warns_once_for_a_missing_file(tmp_path, caplog):
    import validation_learning as vl
    missing = tmp_path / "gone.txt"
    with caplog.at_level("WARNING", logger="validation_learning"):
        assert vl.load_approved_terms(missing) == set()
        assert vl.load_validation_aliases(missing) == {}
    warned = [r for r in caplog.records if "Approved-terms file not found" in r.getMessage()]
    assert len(warned) == 1 and str(missing) in warned[0].getMessage()


# --- E2E5: changing folders never points the settings file back at the real logs ----

def test_e2e5_folder_change_keeps_the_logs_redirect(paths, tmp_path):
    """conftest redirects LOGS_DIR to tmp_path. Before E2E5, set_transcripts_base and
    set_source_dir_and_infer_base reset it to the real logs/, and the next settings
    save (e.g. choosing a terms file) wrote the real runtime_settings.json."""
    real = (ROOT / "logs" / "runtime_settings.json").resolve()
    config.set_transcripts_base(tmp_path / "base")
    assert config.settings._runtime_settings_path().resolve() != real
    config.set_source_dir_and_infer_base(tmp_path / "base" / "source")
    assert config.settings._runtime_settings_path().parent == tmp_path
    config.set_validation_approved_terms_path(tmp_path / "t.txt")  # saves settings
    assert (tmp_path / "runtime_settings.json").exists()


def test_e2e5_logs_and_prompts_dirs_are_not_reset_by_folder_setters():
    src = (ROOT / "config.py").read_text(encoding="utf-8")
    body = src.split("def _update_derived_paths", 1)[1].split("def set_validation_approved", 1)[0]
    assert not re.search(r"self\.(LOGS_DIR|PROMPTS_DIR)\s*=", body)


# --- E2E6: scored emphasis runs at a fixed, measured thinking level ------------------

def test_e2e6_emphasis_request_uses_the_fixed_effort(monkeypatch, tmp_path):
    """The emphasis call sends config.EMPHASIS_EFFORT through the real request builder,
    whatever the GUI Effort setting is (it was the model default, "high", whose
    thinking ran past a 24,000-token ceiling on long talks)."""
    from types import SimpleNamespace
    import extraction_pipeline as ep
    sent = []
    reply = ('[Explicit - Direct Importance - Rank: 95%] Concept: The family unit\n'
             '"The family is an emotional unit and you cannot understand one person alone."\n'
             '(Section 2)\n')

    class _Client:
        class messages:
            @staticmethod
            def stream(**kw):
                sent.append(kw)
                msg = SimpleNamespace(type="message", role="assistant", stop_reason="end_turn",
                                      stop_details=None, model="m",
                                      content=[SimpleNamespace(type="text", text=reply)],
                                      usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                                                            cache_creation_input_tokens=0,
                                                            cache_read_input_tokens=0))

                class _Ctx:
                    def __enter__(self):
                        return SimpleNamespace(get_final_message=lambda: msg)

                    def __exit__(self, *a):
                        return False
                return _Ctx()

    monkeypatch.setattr(ep, "get_anthropic_client", lambda *a, **k: _Client())
    monkeypatch.setattr(tu, "log_token_usage", lambda *a, **k: None)
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: "max"))
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config.settings, "PROJECTS_DIR", tmp_path)
    base = "Talk - A Person - 2021-01-01"
    (tmp_path / base).mkdir()
    ok = ep.extract_scored_emphasis(f"{base}{config.SUFFIX_YAML}", model="claude-sonnet-5-5",
                                    transcript_text="The family is an emotional unit and you "
                                                    "cannot understand one person alone.")
    assert ok
    assert sent[0]["extra_body"]["output_config"] == {"effort": config.EMPHASIS_EFFORT}
    assert config.EMPHASIS_EFFORT == "medium"


def test_e2e6_cost_estimate_emphasis_row(monkeypatch, tmp_path):
    """The emphasis row is the measured output at EMPHASIS_EFFORT, thinking included,
    whatever the GUI Effort setting (E2E6 review)."""
    import transcript_cost_estimator as tce
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: "max"))
    for words in (500, 20000):
        src = tmp_path / f"Talk - A Person - 2021-01-01-{words}.txt"
        src.write_text("word " * words, encoding="utf-8")
        est = tce.CostEstimator(src)
        est.estimate_summarization_steps()
        row = next(c for c in est.costs if c["step"].startswith("2e. Scored Emphasis"))
        T = est.transcript_tokens
        assert row["output_tokens"] == max(int(T * config.EMPHASIS_OUTPUT_PCT),
                                           config.EMPHASIS_OUTPUT_FLOOR)


# --- TP: generation prompts get the published themes, not the closing notes --------

TRAILING = Path(__file__).parent / "fixtures" / "theme_trailing"
NOTES = ("Summary paragraph", "Rationale and coverage summary", "Why these themes were chosen",
         "These three themes", "These seven themes")


def test_tp1_prompt_text_drops_only_the_notes():
    """Real files whose last theme is followed by the model's notes: the notes are gone,
    every theme keeps its header and every line of its own fields, nothing is added."""
    for f in TRAILING.glob("*.md"):
        text = f.read_text(encoding="utf-8")
        prompt = tu.themes_for_prompt(text)
        blocks = tu.theme_display_blocks(text)
        assert blocks, f.name
        for note in NOTES:
            assert note not in prompt, (f.name, note)
        orig_lines = {ln.strip() for ln in text.splitlines()}
        for number, name, body in blocks:
            assert f"**{number}. {name}**" in prompt
            for ln in body.splitlines():
                assert ln.strip() in orig_lines and ln in prompt, (f.name, ln)
        headers = {f"**{n}. {nm}**" for n, nm, _b in blocks}
        assert all(ln.strip() in orig_lines or ln.strip() in headers or not ln.strip()
                   for ln in prompt.splitlines()), f.name


def test_tp1_unparseable_theme_text_passes_through():
    text = "## Structural Themes\n\n### Frame A\nA structural anchor used throughout.\n"
    assert tu.themes_for_prompt(text) == text


def test_tp1_shared_generator_trims_theme_placeholders(monkeypatch):
    """Lens generation, theme/lens validation and interpretive themes all build their
    prompt in _generate_with_cached_transcript."""
    import extraction_pipeline as ep
    sent = {}
    monkeypatch.setattr(ep, "_load_summary_prompt",
                        lambda name: "S:\n{{structural_themes}}\nI:\n{{interpretive_themes}}\nT:\n{{topics}}")
    monkeypatch.setattr(ep, "_generate_summary_with_claude",
                        lambda prompt, *a, **k: sent.setdefault("prompt", prompt))
    structural = (TRAILING / "why_families_structural-themes.md").read_text(encoding="utf-8")
    interpretive = (TRAILING / "why_families_interpretive-themes.md").read_text(encoding="utf-8")
    topics = "### Topic A\nThese three themes appear in a topic and stay."
    ep._generate_with_cached_transcript("x.md", "claude-sonnet-5-5", MagicMock(), None,
                                        structural_themes=structural,
                                        interpretive_themes=interpretive, topics=topics)
    prompt = sent["prompt"]
    assert "Summary paragraph" not in prompt and "These seven themes" not in prompt
    assert tu.theme_display_blocks(structural)[0][1] in prompt
    assert "These three themes appear in a topic and stay." in prompt  # other keys untouched


# --- SL/SL3: summary length; asked 10% under, accepted 15% under, to 20% over --------

def _words_client(n_words):
    from types import SimpleNamespace
    calls = []
    text = " ".join(["word"] * n_words)
    msg = SimpleNamespace(type="message", role="assistant", stop_reason="end_turn",
                          stop_details=None, model="m",
                          content=[SimpleNamespace(type="text", text=text)],
                          usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                                                cache_creation_input_tokens=0,
                                                cache_read_input_tokens=0))

    class _Stream:
        def __enter__(self):
            return SimpleNamespace(get_final_message=lambda: msg)

        def __exit__(self, *a):
            return False

    class _Client:
        class messages:
            @staticmethod
            def create(**kw):
                calls.append(kw)
                return msg

            @staticmethod
            def stream(**kw):
                calls.append(kw)
                return _Stream()
    return _Client(), calls


def test_sl1_bounds_follow_the_target():
    """Accepted: 15% under (author decision 2026-10-14, SL3; was 10%) to 20% over. The
    prompt still asks for 10% under to 20% over."""
    assert config.summary_word_bounds(650) == (553, 780)
    assert config.summary_word_bounds(750) == (638, 900)
    assert config.summary_prompt_word_range(650) == (585, 780)


@pytest.mark.parametrize("n_words,accepted", [(553, True), (562, True), (580, True),
                                              (780, True), (552, False), (781, False)])
def test_sl1_band_through_the_real_retry(monkeypatch, n_words, accepted):
    """E2E run 5: 587 and 572 words were rejected against a fixed 600-word minimum; run 7:
    every draft at 580 and 562 against 585. The band for the 650 target is 553-780;
    outside it the reply is retried, then fails (hard limits, the helper's default; the
    summary itself uses soft limits, RS.1)."""
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: None))
    monkeypatch.setattr(tu, "log_token_usage", lambda *a, **k: None)
    monkeypatch.setattr("time.sleep", lambda s: None)
    client, calls = _words_client(n_words)
    lo, hi = config.summary_word_bounds(650)
    kw = dict(model="claude-sonnet-5-5", messages=[{"role": "user", "content": "x"}],
              max_tokens=4096, min_words=lo, max_words=hi, max_retries=2)
    if accepted:
        tu.call_claude_with_retry(client, **kw)
        assert len(calls) == 1
    else:
        with pytest.raises(Exception, match="too (short|long)"):
            tu.call_claude_with_retry(client, **kw)
        assert len(calls) == 2  # retried, then failed


def test_sl3_prompt_asks_for_more_than_the_check_accepts(monkeypatch):
    """SL3 measurement (docs/calibration_summary_floor_2026-10-14.md): drafts were longer
    with the asked minimum in the prompt (long talks 539-636) than without (490-608), so
    the prompt asks for 585-780 while 553-780 is accepted."""
    import summary_pipeline as sp
    text = (config.PROMPTS_DIR / "Summary Generation Prompt v1.md").read_text(encoding="utf-8")
    assert "600" not in text and "650-750" not in text and "800" not in text
    assert "rejected" not in text  # the asked range is not what is accepted
    for ph in ("{target_word_count}", "{min_words}", "{max_words}"):
        assert ph in text
    seen = {}

    def fake_call(**kw):
        seen.update(kw)
        raise RuntimeError("stop")
    monkeypatch.setattr(sp, "call_claude_with_retry", fake_call)
    si = sp.prepare_summary_input(
        metadata={"title": "T", "presenter": "P", "date": "2021-01-01"}, topics_markdown=
        "## Topics\n\n### A\nD.\n*_(~50% of transcript; Sections 1-2)_*\n",
        themes_markdown="", transcript="## Section 1\nKerr said things.\n")
    with pytest.raises(RuntimeError):
        sp.generate_summary(si, api_client=object(), model="claude-sonnet-5-5")
    target = si.target_word_count
    assert (seen["min_words"], seen["max_words"]) == config.summary_word_bounds(target)
    prompt = seen["messages"][0]["content"]
    asked_min, asked_max = config.summary_prompt_word_range(target)
    assert f"between {asked_min} and {asked_max} words" in prompt
    assert str(config.summary_word_bounds(target)[0]) not in prompt


def test_sl1_validation_uses_the_same_band():
    from summary_validation import validate_structural
    para = lambda n: " ".join(["word"] * n)  # noqa: E731
    ok = "\n\n".join([para(185)] * 3)        # 555 words
    short = "\n\n".join([para(184)] * 3)     # 552
    long_ = "\n\n".join([para(261)] * 3)     # 783
    warn = lambda s: [w for w in validate_structural(s, 650)["warnings"] if "Length" in w]  # noqa: E731
    assert warn(ok) == []
    assert "Too short" in warn(short)[0] and "Too long" in warn(long_)[0]


def test_sl1_validation_edges_780_781():
    from summary_validation import validate_structural
    body = lambda n: "\n\n".join([" ".join(["word"] * (n // 3))] * 2 + [" ".join(["word"] * (n - 2 * (n // 3)))])  # noqa: E731
    warn = lambda n: [w for w in validate_structural(body(n), 650)["warnings"] if "Length" in w]  # noqa: E731
    assert warn(780) == [] and "Too long" in warn(781)[0]


@pytest.mark.parametrize("advisory", [False, True])
def test_sl2_failed_later_attempt_keeps_the_best_draft(monkeypatch, advisory):
    """SL review: when a later faithfulness attempt fails outright (every retry outside
    the length band), the best earlier draft is written, as on exhausted attempts."""
    import extraction_pipeline as ep
    monkeypatch.setattr(config, "GENERATION_FAITHFULNESS_ATTEMPTS", 3)
    drafts = iter(["draft one", "draft two"])

    def generate(feedback):
        try:
            return next(drafts)
        except StopIteration:
            raise ValueError("Response text too long: 900 words (expected <= 780)")
    written = []
    issues = iter([["claim X", "claim Y"], ["claim X", "claim Y", "claim Z"]])  # draft one: fewer
    ok = ep._generate_until_faithful("summary", "B", " - x.md", MagicMock(), generate,
                                     written.append, precheck=lambda *a: ("fail", next(issues)),
                                     advisory=advisory)
    assert written[-1] == "draft one"
    assert ok is advisory


def test_sl2_first_attempt_failure_still_raises(monkeypatch):
    import extraction_pipeline as ep

    def generate(feedback):
        raise ValueError("Response text too long")
    with pytest.raises(ValueError):
        ep._generate_until_faithful("summary", "B", " - x.md", MagicMock(), generate,
                                    lambda t: None, precheck=lambda *a: ("pass", []))


# --- AQ: the abstract is not given pattern-made Q&A topics ---------------------------

def test_aq1_abstract_payload_has_no_qa_topics():
    """Run 7, Beautiful Boy: the abstract model was given "exploration reading book
    written" as Q&A topics and wrote a sentence from them that the judge rejected on all
    three attempts. The model now describes the Q&A from the transcript."""
    fragments = ["exploration reading book written", "meaning getting high methamphetamines"]
    for pct in (config.ABSTRACT_QA_NOTE_MIN_PCT + 1, 100):
        data = json.loads(_input(pct, qa_topics=fragments).to_json())
        assert data["include_qa_note"] is True and "qa_topics" not in data
        assert not any(f in json.dumps(data) for f in fragments)
    prompt = (config.PROMPTS_DIR / config.PROMPT_STRUCTURED_ABSTRACT_FILENAME).read_text(encoding="utf-8")
    assert "qa_topics" not in prompt and "as the transcript shows it" in prompt


def _qa_item(pct, topics=("exploration reading book written",)):
    import abstract_validation as av
    items = av.generate_coverage_items(_input(pct, qa_topics=topics))
    return [i for i in items if i.category == "qa"]


def test_aq2_qa_coverage_checks_for_a_qa_note():
    import abstract_validation as av
    item = _qa_item(config.ABSTRACT_QA_REQUIRED_PCT)[0]
    assert item.required is True
    # Q&A sentences the model wrote in the AQ measurement, and the old style
    for note in ("The question period addressed detachment as a practice versus differentiation.",
                 "Participants asked about what a higher level of differentiation would look like.",
                 "In the question period, audience members asked about the difference.",
                 "The question-and-answer session addressed the book and its author."):
        assert av.check_keyword_coverage(note, item)[0] is True, note
    # Adversarial (P7): ordinary prose with Q&A-ish words is not a Q&A note (AQ review:
    # the first is from a real abstract with no Q&A note), nor are the old fragments.
    for prose in ("Michael Kerr presents Bowen theory to an audience unfamiliar with the approach.",
                  "The central question is how anxiety moves; the discussion then turns to cancer.",
                  "The talk covers exploration, reading the book he had written, and his son."):
        assert av.check_keyword_coverage(prose, item)[0] is False, prose
    # The item no longer depends on the fragments: present with none of them.
    assert _qa_item(config.ABSTRACT_QA_REQUIRED_PCT, topics=())[0].required is True
    assert _qa_item(config.ABSTRACT_QA_NOTE_MIN_PCT) == []  # not asked for: not checked (RS.5)


@pytest.mark.parametrize("n_words,accepted", [(config.ABSTRACT_HARD_MAX_WORDS - 1, True),
                                              (config.ABSTRACT_HARD_MAX_WORDS, False),
                                              (265, False)])
def test_aq3_abstract_hard_limit_enforced_at_generation(monkeypatch, n_words, accepted):
    """AQ measurement: one Beautiful Boy abstract came out at 265 words and was kept; the
    250-word limit was stated in the prompt and only warned about in validation. A
    reply at or over it is now retried; after the last try the shortest reply is kept
    with a warning (RS.1: a length miss never fails the run)."""
    monkeypatch.setattr(type(config.settings), "EFFORT", property(lambda self: None))
    monkeypatch.setattr(tu, "log_token_usage", lambda *a, **k: None)
    monkeypatch.setattr("time.sleep", lambda s: None)
    client, calls = _words_client(n_words)
    run = lambda: ap.generate_abstract(_input(50), client, model="claude-sonnet-5-5")  # noqa: E731
    if accepted:
        assert len(run().split()) == n_words and len(calls) == 1
    else:
        assert len(run().split()) == n_words  # kept, not failed (RS.1)
        assert len(calls) == config.MAX_RETRIES  # retried first
