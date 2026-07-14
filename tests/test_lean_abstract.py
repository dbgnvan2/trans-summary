"""
Lean abstract path: standalone Topics stage + Topics-only abstract.

Spec:  docs/spec_lean_abstract_2026-07-13.md (LA.1-LA.5)
Tests: this file

Covers the two changes that let a user produce an abstract (and, separately,
Emphasis + Bowen) without the full monolithic Core stage:
  1. a standalone `generate_topics` / `topics` stage, and
  2. `generate_structured_abstract` requiring Topics only (Interpretive Themes
     is passed into the abstract JSON but never used by the prompt).
"""
from unittest.mock import MagicMock, patch

import pytest

import config
import extraction_pipeline
import ts_gui


class _Flag:
    def __init__(self, value=False):
        self._value = value

    def get(self):
        return self._value

    def set(self, value):
        self._value = value


BASE_NAME = "Sample Title - Author - 2025-01-01"


def _stage_vars(checked_keys):
    checked = set(checked_keys)
    return {key: _Flag(key in checked) for key, _ in ts_gui.STAGE_DEFINITIONS}


def _make_gui(tmp_path, checked_keys=()):
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = BASE_NAME
    gui.selected_file = tmp_path / f"{BASE_NAME}_validated.txt"
    gui.logger = object()
    gui.log = MagicMock()
    gui.processing = False
    gui.stage_vars = _stage_vars(checked_keys)
    gui.active_selection_var = _Flag("(none)")
    return gui


def _write_artifact(tmp_path, suffix_attr):
    suffix = getattr(config, suffix_attr)
    project_dir = tmp_path / BASE_NAME
    project_dir.mkdir(parents=True, exist_ok=True)
    path = project_dir / f"{BASE_NAME}{suffix}"
    path.write_text("", encoding="utf-8")
    return path


@pytest.fixture(autouse=True)
def _scratch_projects_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config.settings, "PROJECTS_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# LA.1 -- standalone Topics generator writes the SUFFIX_TOPICS artifact
# ---------------------------------------------------------------------------

def test_la1_generate_topics_writes_topics_artifact():
    with patch.object(extraction_pipeline, "_load_formatted_transcript", return_value="transcript body"), \
         patch.object(extraction_pipeline, "create_system_message_with_cache", return_value=["SYS"]), \
         patch.object(extraction_pipeline, "_generate_with_cached_transcript", return_value="## Topics\n\n### A\nx") as mock_gen, \
         patch.object(extraction_pipeline, "_save_summary") as mock_save:
        ok = extraction_pipeline.generate_topics("Sample - yaml.md", logger=MagicMock())

    assert ok is True
    # Uses the Topics prompt, not any other extraction prompt.
    assert mock_gen.call_args.args[0] == config.PROMPT_TOPICS_FILENAME
    # Saves to the canonical "topics" artifact slot.
    assert mock_save.call_args.args[2] == "topics"


def test_la1_generate_topics_returns_false_on_error():
    with patch.object(extraction_pipeline, "_load_formatted_transcript", side_effect=OSError("boom")):
        ok = extraction_pipeline.generate_topics("Sample - yaml.md", logger=MagicMock())
    assert ok is False


def test_la_topics_abstract_filesystem_roundtrip(tmp_path):
    """P6/LA.5 contract lock: the Topics artifact that `generate_topics` WRITES
    is the exact file `generate_structured_abstract` later READS. Only the two
    real LLM calls are mocked; _save_summary and _load_section_from_project_file
    hit the real filesystem, so a path/stem-stripping drift between writer and
    reader would fail this test."""
    proj = tmp_path / BASE_NAME
    proj.mkdir(parents=True, exist_ok=True)
    # Real transcript file the topics/abstract steps load.
    (proj / f"{BASE_NAME}{config.SUFFIX_YAML}").write_text("word " * 400, encoding="utf-8")

    distinctive_topics = "## Topics\n\n### Zebra Husbandry Economics\nA uniquely named topic.\n"

    # 1. Topics: mock ONLY the API call; let _save_summary write the real file.
    with patch.object(extraction_pipeline, "_generate_with_cached_transcript", return_value=distinctive_topics), \
         patch.object(extraction_pipeline, "create_system_message_with_cache", return_value=["SYS"]):
        assert extraction_pipeline.generate_topics(f"{BASE_NAME}{config.SUFFIX_YAML}", logger=MagicMock()) is True

    topics_file = proj / f"{BASE_NAME}{config.SUFFIX_TOPICS}"
    assert topics_file.exists(), "generate_topics did not write the topics artifact where expected"

    # 2. Abstract: mock ONLY the API calls; real _load_section_from_project_file
    #    must pick up the topics file just written.
    with patch.object(extraction_pipeline, "create_system_message_with_cache", return_value=["SYS"]), \
         patch.object(extraction_pipeline.anthropic, "Anthropic", return_value=MagicMock()), \
         patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}), \
         patch.object(extraction_pipeline.abstract_pipeline, "extract_opening_purpose", return_value="purpose"), \
         patch.object(extraction_pipeline.abstract_pipeline, "extract_closing_conclusion", return_value="conclusion"), \
         patch.object(extraction_pipeline.abstract_pipeline, "generate_abstract", return_value="ABSTRACT") as mock_abs:
        ok = extraction_pipeline.generate_structured_abstract(BASE_NAME, logger=MagicMock())

    assert ok is True
    # The abstract's parsed topics must derive from the file generate_topics wrote.
    prepared = mock_abs.call_args.args[0]
    assert any("Zebra Husbandry Economics" in t.name for t in prepared.topics), \
        "abstract did not read the Topics artifact written by generate_topics"


# ---------------------------------------------------------------------------
# LA.2 -- abstract requires Topics only; Interpretive Themes optional
# ---------------------------------------------------------------------------

def _patch_abstract_env(tmp_path, topics_section, themes_section):
    """Patch generate_structured_abstract's collaborators. topics_section /
    themes_section are what _load_section_from_project_file returns for the
    Topics and Interpretive-Themes suffixes respectively."""
    def fake_load_section(base_name, suffix, headers):
        if suffix == config.SUFFIX_TOPICS:
            return topics_section
        if suffix == config.SUFFIX_INTERPRETIVE_THEMES:
            return themes_section
        return None

    return (
        patch.object(extraction_pipeline, "load_project_transcript", return_value="word " * 400),
        patch.object(extraction_pipeline, "_load_section_from_project_file", side_effect=fake_load_section),
        patch.object(extraction_pipeline, "create_system_message_with_cache", return_value=["SYS"]),
        patch.object(extraction_pipeline.anthropic, "Anthropic", return_value=MagicMock()),
        patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}),
        # prepare_abstract_input pulls opening/closing from the transcript via
        # their own LLM calls -- stub them so the test stays offline.
        patch.object(extraction_pipeline.abstract_pipeline, "extract_opening_purpose", return_value="purpose"),
        patch.object(extraction_pipeline.abstract_pipeline, "extract_closing_conclusion", return_value="conclusion"),
    )


def test_la2_abstract_succeeds_without_interpretive_themes(tmp_path):
    (tmp_path / BASE_NAME).mkdir(parents=True, exist_ok=True)
    topics = "## Topics\n\n### A\nfoo\n\n### B\nbar"
    patches = _patch_abstract_env(tmp_path, topics_section=topics, themes_section=None)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patch.object(extraction_pipeline.abstract_pipeline, "generate_abstract", return_value="ABSTRACT") as mock_abs:
        ok = extraction_pipeline.generate_structured_abstract(BASE_NAME, logger=MagicMock())

    assert ok is True, "abstract must succeed with Topics present and no Interpretive Themes"
    # themes passed through as empty (parsed to []), abstract still generated.
    prepared = mock_abs.call_args.args[0]
    assert prepared.themes == []
    assert (tmp_path / BASE_NAME / f"{BASE_NAME}{config.SUFFIX_ABSTRACT_GEN}").exists()


def test_la2_abstract_still_fails_without_topics(tmp_path):
    (tmp_path / BASE_NAME).mkdir(parents=True, exist_ok=True)
    patches = _patch_abstract_env(tmp_path, topics_section=None, themes_section="## Interpretive Themes\n\n### T\nx")
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5], patches[6], \
         patch.object(extraction_pipeline.abstract_pipeline, "generate_abstract", return_value="ABSTRACT") as mock_abs:
        ok = extraction_pipeline.generate_structured_abstract(BASE_NAME, logger=MagicMock())

    assert ok is False, "abstract must still fail when Topics is missing"
    mock_abs.assert_not_called()


# ---------------------------------------------------------------------------
# LA.3 / LA.4 -- topics stage registered + its dependency
# ---------------------------------------------------------------------------

def test_la3_topics_stage_registered():
    keys = [k for k, _ in ts_gui.STAGE_DEFINITIONS]
    assert "topics" in keys
    # placed after yaml, before core
    assert keys.index("yaml") < keys.index("topics") < keys.index("core")
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    assert "topics" in gui.stage_runners
    assert gui.stage_runners["topics"].__func__ is ts_gui.TranscriptProcessorGUI._run_stage_topics


def test_la4_topics_depends_on_yaml():
    assert ts_gui.STAGE_DEPENDENCIES["topics"] == [[("yaml", "SUFFIX_YAML")]]


# ---------------------------------------------------------------------------
# LA.5 -- gen_abstract depends on Topics only (topics stage OR core)
# ---------------------------------------------------------------------------

def test_la5_gen_abstract_depends_on_topics_only():
    dep = ts_gui.STAGE_DEPENDENCIES["gen_abstract"]
    assert dep == [[("topics", "SUFFIX_TOPICS"), ("core", "SUFFIX_TOPICS")]]
    # Interpretive Themes is no longer a prerequisite anywhere in this stage's graph.
    flat = [attr for group in dep for _, attr in group]
    assert "SUFFIX_INTERPRETIVE_THEMES" not in flat


def test_la5_preflight_allows_topics_then_abstract(tmp_path):
    """{topics, gen_abstract} selected, with the yaml artifact on disk to
    satisfy topics' own dependency -> whole selection passes pre-flight."""
    _write_artifact(tmp_path, "SUFFIX_YAML")
    gui = _make_gui(tmp_path, checked_keys={"topics", "gen_abstract"})
    unmet = gui._validate_stage_dependencies({"topics", "gen_abstract"})
    assert unmet == [], f"expected no unmet deps, got {unmet}"


def test_la5_preflight_allows_abstract_with_topics_artifact_on_disk(tmp_path):
    """{gen_abstract} alone, with a Topics artifact already on disk from an
    earlier run -> allowed, no core needed."""
    _write_artifact(tmp_path, "SUFFIX_TOPICS")
    gui = _make_gui(tmp_path, checked_keys={"gen_abstract"})
    unmet = gui._validate_stage_dependencies({"gen_abstract"})
    assert unmet == []


def test_la5_preflight_blocks_abstract_without_topics(tmp_path):
    """{gen_abstract} alone, no topics/core selected and no Topics artifact ->
    blocked, and the message names Topics."""
    gui = _make_gui(tmp_path, checked_keys={"gen_abstract"})
    unmet = gui._validate_stage_dependencies({"gen_abstract"})
    assert len(unmet) == 1
    label, descriptions = unmet[0]
    assert label == "5. Gen Abstract"
    assert any("Topics" in d for d in descriptions)
    # Full user-facing message also mentions the prerequisite.
    msg = gui._format_preflight_message(unmet)
    assert "Missing Prerequisites" not in msg  # title is separate; body only here
    assert "Topics" in msg
