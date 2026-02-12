from pathlib import Path
from unittest.mock import patch

import config
import ts_gui


def test_run_all_includes_cost_estimation_and_separate_blog_step():
    gui = ts_gui.TranscriptProcessorGUI.__new__(ts_gui.TranscriptProcessorGUI)
    gui.base_name = "Sample Title - Author - 2025-01-01"
    gui.selected_file = Path("/tmp/Sample Title - Author - 2025-01-01_validated.txt")
    gui.formatted_file = Path(
        f"/tmp/{gui.base_name}{config.SUFFIX_FORMATTED}"
    )
    gui.logger = object()
    gui.log = lambda *_args, **_kwargs: None

    with patch.object(gui, "_run_cost_estimation", return_value=True) as mock_cost, \
         patch.object(gui, "_run_header_validation", return_value=True) as mock_headers, \
         patch.object(gui, "_run_web_pdf_generation", return_value=True) as mock_web_pdf, \
         patch("ts_gui.pipeline.format_transcript", return_value=True) as mock_format, \
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
