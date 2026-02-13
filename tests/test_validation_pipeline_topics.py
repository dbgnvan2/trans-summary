from pathlib import Path
from unittest.mock import patch

import config
from validation_pipeline import validate_topics_lightweight


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass


def test_validate_topics_lightweight_pass_and_report(tmp_path):
    base_name = "Topic Test - Author - 2025-01-01"
    project_dir = tmp_path / base_name
    project_dir.mkdir(parents=True, exist_ok=True)

    formatted_file = project_dir / f"{base_name}{config.SUFFIX_FORMATTED}"
    formatted_file.write_text(
        "## Section 1\nDifferentiation of self helps separate thinking from feeling.\n",
        encoding="utf-8",
    )

    topics_file = project_dir / f"{base_name}{config.SUFFIX_TOPICS}"
    topics_file.write_text(
        "## Topics\n\n### Differentiation of Self\nExplains separation of thinking from feeling.\n*_(~30% of transcript; Sections 1)_*\n",
        encoding="utf-8",
    )

    with patch.object(config, "PROJECTS_DIR", tmp_path):
        ok = validate_topics_lightweight(formatted_file, base_name, _Logger())

    report = project_dir / f"{base_name}{config.SUFFIX_TOPICS_VAL}"
    assert ok is True
    assert report.exists()
    report_text = report.read_text(encoding="utf-8")
    assert "Differentiation of Self" in report_text
    assert "FAIL" not in report_text


def test_validate_topics_lightweight_detects_failures(tmp_path):
    base_name = "Topic Fail - Author - 2025-01-01"
    project_dir = tmp_path / base_name
    project_dir.mkdir(parents=True, exist_ok=True)

    formatted_file = project_dir / f"{base_name}{config.SUFFIX_FORMATTED}"
    formatted_file.write_text("## Section 1\nShort content unrelated to topic.\n", encoding="utf-8")

    topics_file = project_dir / f"{base_name}{config.SUFFIX_TOPICS}"
    topics_file.write_text(
        "## Topics\n\n### Multi-generational transmission process model\nHighly specific description absent from transcript body.\n*_(~30% of transcript; Sections 1)_*\n",
        encoding="utf-8",
    )

    with patch.object(config, "PROJECTS_DIR", tmp_path):
        ok = validate_topics_lightweight(formatted_file, base_name, _Logger())

    report = project_dir / f"{base_name}{config.SUFFIX_TOPICS_VAL}"
    assert ok is False
    assert "FAIL" in report.read_text(encoding="utf-8")
