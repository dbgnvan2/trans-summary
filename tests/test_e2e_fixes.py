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
    assert data["include_qa_note"] is False and data["qa_topics"] == []


def test_e2e1_qa_note_threshold_is_decided_in_code():
    at = json.loads(_input(config.ABSTRACT_QA_NOTE_MIN_PCT).to_json())
    above = json.loads(_input(config.ABSTRACT_QA_NOTE_MIN_PCT + 1).to_json())
    assert at["include_qa_note"] is False
    assert above["include_qa_note"] is True and above["qa_topics"] == ["q one"]


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
    assert av.QA_OPTIONAL_THRESHOLD == config.ABSTRACT_QA_OPTIONAL_PCT
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
