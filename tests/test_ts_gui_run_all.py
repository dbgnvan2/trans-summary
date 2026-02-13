from pathlib import Path
from unittest.mock import patch, MagicMock

import config
import ts_gui


class _Flag:
    def __init__(self, value=False):
        self._value = value

    def get(self):
        return self._value


def test_run_all_includes_cost_estimation_and_separate_blog_step():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = "Sample Title - Author - 2025-01-01"
    gui.selected_file = Path("/tmp/Sample Title - Author - 2025-01-01_validated.txt")
    gui.formatted_file = Path(
        f"/tmp/{gui.base_name}{config.SUFFIX_FORMATTED}"
    )
    gui.logger = object()
    gui.log = lambda *_args, **_kwargs: None
    gui.include_init_val_do_all = _Flag(False)

    with patch.object(gui, "_run_cost_estimation", return_value=True) as mock_cost, \
         patch.object(gui, "_run_header_validation", return_value=True) as mock_headers, \
         patch.object(gui, "_run_web_pdf_generation", return_value=True) as mock_web_pdf, \
         patch("ts_gui.pipeline.format_transcript", return_value=True) as mock_format, \
         patch("ts_gui.pipeline.validate_format", return_value=True) as mock_validate_format, \
         patch("ts_gui.pipeline.add_yaml", return_value=True) as mock_yaml, \
         patch("ts_gui.pipeline.summarize_transcript", return_value=True) as mock_summarize, \
         patch("ts_gui.pipeline.generate_structured_abstract", return_value=True) as mock_abstract, \
         patch("ts_gui.pipeline.validate_abstract_coverage", return_value=True) as mock_validate_abstract, \
         patch("ts_gui.pipeline.package_transcript", return_value=True) as mock_package, \
         patch("ts_gui.analyze_token_usage.generate_usage_report", return_value="report"):
        ok = gui._run_all_steps()

    assert ok is True
    mock_cost.assert_called_once()
    mock_headers.assert_called_once()
    mock_web_pdf.assert_called_once()
    mock_format.assert_called_once()
    mock_validate_format.assert_called_once()
    mock_yaml.assert_called_once()
    mock_abstract.assert_called_once()
    mock_validate_abstract.assert_called_once()
    mock_package.assert_called_once()

    # Core extraction (skip_blog=True), then separate blog generation (skip_blog=False)
    assert mock_summarize.call_count == 2
    first_call = mock_summarize.call_args_list[0].args
    second_call = mock_summarize.call_args_list[1].args
    assert first_call[4:7] == (False, False, True)
    assert second_call[4:7] == (True, True, False)


def test_run_all_with_init_val_auto_calls_initial_validation():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = "Sample Title - Author - 2025-01-01"
    gui.selected_file = Path("/tmp/Sample Title - Author - 2025-01-01.txt")
    gui.formatted_file = Path(
        f"/tmp/{gui.base_name}{config.SUFFIX_FORMATTED}"
    )
    gui.logger = object()
    gui.log = lambda *_args, **_kwargs: None
    gui.include_init_val_do_all = _Flag(True)

    with patch.object(gui, "_run_initial_validation_auto", return_value=True) as mock_init_auto, \
         patch.object(gui, "_run_cost_estimation", return_value=True), \
         patch.object(gui, "_run_header_validation", return_value=True), \
         patch.object(gui, "_run_web_pdf_generation", return_value=True), \
         patch("ts_gui.pipeline.format_transcript", return_value=True), \
         patch("ts_gui.pipeline.validate_format", return_value=True), \
         patch("ts_gui.pipeline.add_yaml", return_value=True), \
         patch("ts_gui.pipeline.summarize_transcript", return_value=True), \
         patch("ts_gui.pipeline.generate_structured_abstract", return_value=True), \
         patch("ts_gui.pipeline.validate_abstract_coverage", return_value=True), \
         patch("ts_gui.pipeline.package_transcript", return_value=True), \
         patch("ts_gui.analyze_token_usage.generate_usage_report", return_value="report"):
        ok = gui._run_all_steps()

    assert ok is True
    mock_init_auto.assert_called_once()


def test_do_all_steps_does_not_start_when_processing_active():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.selected_file = Path("/tmp/Sample_validated.txt")
    gui.processing = True
    gui.include_init_val_do_all = _Flag(False)
    gui.log = MagicMock()
    gui.run_task_in_thread = MagicMock()

    gui.do_all_steps()

    gui.run_task_in_thread.assert_not_called()
    gui.log.assert_called_with("⚠️ Pipeline is already running.")


def test_run_task_in_thread_rejects_reentry():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.processing = True
    gui.log = MagicMock()
    gui.progress = MagicMock()
    gui.update_button_states = MagicMock()

    gui.run_task_in_thread(lambda: True)

    gui.progress.start.assert_not_called()
    gui.update_button_states.assert_not_called()
    gui.log.assert_called_with("⚠️ A task is already running. Please wait for it to finish.")
