from pathlib import Path
from unittest.mock import patch

import config
from validation_pipeline import _parse_key_terms_section, validate_key_terms_fidelity


class _Logger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass


def test_parse_key_terms_section_supports_header_and_bold_formats():
    content = """
## Key Terms

### Differentiation of Self
The ability to separate thinking from feeling.

**Triangle**: A three-person emotional process pattern.
"""
    terms = _parse_key_terms_section(content)
    assert ("Differentiation of Self", "The ability to separate thinking from feeling.") in terms
    assert ("Triangle", "A three-person emotional process pattern.") in terms


def test_validate_key_terms_fidelity_writes_report_and_detects_failures(tmp_path):
    base_name = "Sample - Author - 2025-01-01"
    project_dir = tmp_path / base_name
    project_dir.mkdir(parents=True, exist_ok=True)

    formatted_file = project_dir / f"{base_name}{config.SUFFIX_FORMATTED}"
    formatted_file.write_text(
        "Differentiation of self is the ability to separate thinking from feeling.",
        encoding="utf-8",
    )

    key_terms_file = project_dir / f"{base_name}{config.SUFFIX_KEY_TERMS}"
    key_terms_file.write_text(
        "## Key Terms\n\n### Differentiation of Self\nThe ability to separate thinking from feeling.\n",
        encoding="utf-8",
    )

    with patch.object(config, "PROJECTS_DIR", tmp_path):
        ok = validate_key_terms_fidelity(formatted_file, base_name, _Logger())

    report = project_dir / f"{base_name}{config.SUFFIX_KEY_TERMS_VAL}"
    assert ok is True
    assert report.exists()
    assert "EXACT" in report.read_text(encoding="utf-8")

    key_terms_file.write_text(
        "## Key Terms\n\n### Nuclear Family Emotional Process\nA concept absent from this transcript.\n",
        encoding="utf-8",
    )

    with patch.object(config, "PROJECTS_DIR", tmp_path):
        ok = validate_key_terms_fidelity(formatted_file, base_name, _Logger())

    assert ok is False
    assert "FAIL" in report.read_text(encoding="utf-8")
