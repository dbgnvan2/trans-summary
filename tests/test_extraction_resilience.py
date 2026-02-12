from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import config
import extraction_pipeline


def test_generate_structured_abstract_falls_back_to_split_files(tmp_path, monkeypatch):
    base_name = "Fallback-Abstract-Test"
    projects_dir = tmp_path / "projects"
    project_dir = projects_dir / base_name
    project_dir.mkdir(parents=True, exist_ok=True)

    formatted_path = project_dir / f"{base_name}{config.SUFFIX_FORMATTED}"
    formatted_path.write_text("## Section 1\nOpening text.\n", encoding="utf-8")

    # Legacy/incomplete All Key Items without required sections.
    all_key_items_path = project_dir / f"{base_name}{config.SUFFIX_KEY_ITEMS_ALL}"
    all_key_items_path.write_text("## Abstract\nLegacy abstract only.\n", encoding="utf-8")

    # Dedicated files with the required content.
    (project_dir / f"{base_name}{config.SUFFIX_TOPICS}").write_text(
        "## Topics\n\n### Topic A\nDescription.\n*_(~25% of transcript; Sections 1)_*\n",
        encoding="utf-8",
    )
    (project_dir / f"{base_name}{config.SUFFIX_INTERPRETIVE_THEMES}").write_text(
        "## Interpretive Themes\n\n### Theme A\nA concise interpretation.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(config, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(extraction_pipeline, "validate_input_file", lambda _p: None)
    monkeypatch.setattr(
        extraction_pipeline, "parse_filename_metadata", lambda _name: {"stem": base_name}
    )
    monkeypatch.setattr(extraction_pipeline.os, "getenv", lambda _k: "fake-key")
    monkeypatch.setattr(extraction_pipeline.anthropic, "Anthropic", lambda **_k: object())

    fake_abstract_input = SimpleNamespace(topics=["Topic A"], themes=["Theme A"])
    monkeypatch.setattr(
        extraction_pipeline.abstract_pipeline,
        "prepare_abstract_input",
        lambda **_kwargs: fake_abstract_input,
    )
    monkeypatch.setattr(
        extraction_pipeline.abstract_pipeline,
        "generate_abstract",
        lambda *_args, **_kwargs: "Generated abstract from fallback content.",
    )

    logger = MagicMock()
    ok = extraction_pipeline.generate_structured_abstract(base_name, logger=logger)

    assert ok is True
    output_path = project_dir / f"{base_name}{config.SUFFIX_ABSTRACT_GEN}"
    assert output_path.exists()
    assert "Generated abstract" in output_path.read_text(encoding="utf-8")


def test_summarize_transcript_blog_recovers_when_lens_missing(tmp_path, monkeypatch):
    stem = "Lens-Recovery-Test"
    projects_dir = tmp_path / "projects"
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    project_dir = projects_dir / stem
    project_dir.mkdir(parents=True, exist_ok=True)

    # Existing All Key Items is incomplete/stale (no ranked lenses).
    (project_dir / f"{stem}{config.SUFFIX_KEY_ITEMS_ALL}").write_text(
        "## Abstract\nLegacy abstract.\n\n## Themes\nLegacy theme.\n",
        encoding="utf-8",
    )
    (project_dir / f"{stem}{config.SUFFIX_STRUCTURAL_THEMES}").write_text(
        "## Structural Themes\n\n### Structure A\nDescription.\n",
        encoding="utf-8",
    )
    (project_dir / f"{stem}{config.SUFFIX_INTERPRETIVE_THEMES}").write_text(
        "## Interpretive Themes\n\n### Interpretation A\nDescription.\n",
        encoding="utf-8",
    )
    (project_dir / f"{stem}{config.SUFFIX_TOPICS}").write_text(
        "## Topics\n\n### Topic A\nDescription.\n*_(~20% of transcript; Sections 1)_*\n",
        encoding="utf-8",
    )
    (project_dir / f"{stem}{config.SUFFIX_KEY_TERMS}").write_text(
        "## Key Terms\n\n### Term A\nDefinition.\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(config, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(config, "SOURCE_DIR", source_dir)
    monkeypatch.setattr(
        extraction_pipeline,
        "_load_formatted_transcript",
        lambda _filename: "## Section 1\nTranscript content.\n",
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "parse_filename_metadata",
        lambda _filename: {
            "stem": stem,
            "title": stem,
            "presenter": "Presenter",
            "author": "Presenter",
            "date": "1980-00-00",
            "filename": _filename,
        },
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "create_system_message_with_cache",
        lambda _text: [{"type": "text", "text": "cached"}],
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "_generate_with_cached_transcript",
        lambda prompt_filename, *_args, **_kwargs: (
            "## Lenses (Ranked)\n\n1. Lens A\nRationale."
            if prompt_filename == config.PROMPT_LENS_GENERATION_FILENAME
            else ""
        ),
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "_validate_themes_and_lenses",
        lambda *_args, **_kwargs: {
            "structural_themes_valid": True,
            "interpretive_themes_valid": True,
            "top_lens": {
                "title": "Lens A",
                "description": "A valid framing.",
                "rationale": "Best fit.",
                "evidence": "Section 1",
                "hooks": ["Hook A"],
            },
        },
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "_load_summary_prompt",
        lambda _name: "Blog prompt for {{top_lens_title}}",
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "_generate_summary_with_claude",
        lambda *_args, **_kwargs: "Generated blog post.",
    )

    logger = MagicMock()
    ok = extraction_pipeline.summarize_transcript(
        formatted_filename=f"{stem}{config.SUFFIX_YAML}",
        model=config.DEFAULT_MODEL,
        focus_keyword="Family Systems",
        target_audience="General public",
        skip_extracts_summary=True,
        skip_emphasis=True,
        skip_blog=False,
        logger=logger,
    )

    assert ok is True
    blog_path = project_dir / f"{stem}{config.SUFFIX_BLOG}"
    assert blog_path.exists()
    assert "Generated blog post." in blog_path.read_text(encoding="utf-8")
