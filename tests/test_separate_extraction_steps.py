from unittest.mock import MagicMock

import config
import extraction_pipeline
import transcript_utils


def test_extract_scored_emphasis_accepts_direct_text_file(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    projects_dir = tmp_path / "projects"
    source_dir.mkdir()
    projects_dir.mkdir()

    source_file = source_dir / "Direct Input_validated.txt"
    source_file.write_text("Transcript text for emphasis extraction.", encoding="utf-8")

    monkeypatch.setattr(config, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(extraction_pipeline, "_load_summary_prompt", lambda _name: "Prompt")
    monkeypatch.setattr(
        extraction_pipeline,
        "_generate_summary_with_claude",
        lambda *_args, **_kwargs: "mock emphasis output",
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "parse_scored_emphasis_output",
        lambda _text: [
            {
                "type": "Primary",
                "category": "Key Idea",
                "score": 95,
                "concept": "Concept A",
                "quote": "Exact quote A",
            }
        ],
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "validate_emphasis_item",
        lambda _item: (True, []),
    )

    ok = extraction_pipeline.extract_scored_emphasis(
        str(source_file),
        logger=MagicMock(),
    )

    assert ok is True
    output_path = projects_dir / "Direct Input" / f"Direct Input{config.SUFFIX_EMPHASIS_SCORED}"
    assert output_path.exists()
    assert "Concept A" in output_path.read_text(encoding="utf-8")


def test_extract_bowen_accepts_direct_text_file(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    projects_dir = tmp_path / "projects"
    source_dir.mkdir()
    projects_dir.mkdir()

    source_file = source_dir / "Bowen Demo_validated.txt"
    source_file.write_text("Murray Bowen said something important.", encoding="utf-8")

    monkeypatch.setattr(config, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(extraction_pipeline, "_load_summary_prompt", lambda _name: "Prompt {{insert_transcript_text_here}}")
    monkeypatch.setattr(
        extraction_pipeline,
        "_generate_summary_with_claude",
        lambda *_args, **_kwargs: "mock bowen output",
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "extract_bowen_references",
        lambda _text: [("Differentiation of Self", "Murray Bowen said something important.")],
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "_filter_bowen_references_semantically",
        lambda refs, *_args, **_kwargs: refs,
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "_rule_filter_bowen_references",
        lambda refs, *_args, **_kwargs: refs,
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "find_text_in_content",
        lambda *_args, **_kwargs: (0, 0, 1.0),
    )

    ok = extraction_pipeline.extract_bowen_references_from_transcript(
        str(source_file),
        logger=MagicMock(),
    )

    assert ok is True
    output_path = projects_dir / "Bowen Demo" / f"Bowen Demo{config.SUFFIX_BOWEN}"
    assert output_path.exists()
    output_text = output_path.read_text(encoding="utf-8")
    assert "## Bowen References" in output_text
    assert "Differentiation of Self" in output_text


def test_parse_scored_emphasis_output_supports_plain_rank_pipe_format():
    content = (
        "Explicit - A14 - Rank: 96% | Concept: Bowen quote on emotional system\n"
        '"This I think is probably one of the most important quotes I found that Bowen ever said."\n'
        "(00:03:22)\n\n"
        "Explicit - A4 - Rank: 95% | Concept: Chronic anxiety and regression\n"
        '"Regression reflects a disturbance in the balance of these life forces."\n'
        "(00:07:00)\n"
    )

    items = transcript_utils.parse_scored_emphasis_output(content)

    assert len(items) == 2
    assert items[0]["type"] == "Explicit"
    assert items[0]["category"] == "A14"
    assert items[0]["score"] == 96
    assert "Bowen quote on emotional system" in items[0]["concept"]
    assert "one of the most important quotes" in items[0]["quote"]


def test_extract_scored_emphasis_succeeds_for_plain_rank_pipe_format(tmp_path, monkeypatch):
    source_dir = tmp_path / "source"
    projects_dir = tmp_path / "projects"
    source_dir.mkdir()
    projects_dir.mkdir()

    source_file = source_dir / "Direct Input_validated.txt"
    source_file.write_text("Transcript text for emphasis extraction.", encoding="utf-8")

    monkeypatch.setattr(config, "PROJECTS_DIR", projects_dir)
    monkeypatch.setattr(extraction_pipeline, "_load_summary_prompt", lambda _name: "Prompt")
    monkeypatch.setattr(
        extraction_pipeline,
        "_generate_summary_with_claude",
        lambda *_args, **_kwargs: (
            "Explicit - A14 - Rank: 96% | Concept: Bowen quote on emotional system\n"
            '"This I think is probably one of the most important quotes I found that Bowen ever said."\n'
            "(00:03:22)\n"
        ),
    )

    ok = extraction_pipeline.extract_scored_emphasis(
        str(source_file),
        logger=MagicMock(),
    )

    assert ok is True
    output_path = projects_dir / "Direct Input" / f"Direct Input{config.SUFFIX_EMPHASIS_SCORED}"
    assert output_path.exists()
    output_text = output_path.read_text(encoding="utf-8")
    assert "Bowen quote on emotional system" in output_text


def test_extract_bowen_and_emphasis_reuses_cached_transcript(monkeypatch):
    logger = MagicMock()
    transcript_text = "Shared transcript text."
    cached_system_message = [{"type": "text", "text": transcript_text}]
    calls = []

    monkeypatch.setattr(
        extraction_pipeline,
        "_load_formatted_transcript",
        lambda filename: calls.append(("load", filename)) or transcript_text,
    )
    monkeypatch.setattr(
        extraction_pipeline,
        "create_system_message_with_cache",
        lambda text: calls.append(("cache", text)) or cached_system_message,
    )

    def _mock_emphasis(filename, model, passed_logger, transcript_system_message):
        calls.append(("emphasis", filename, model, passed_logger, transcript_system_message))
        return True

    def _mock_bowen(
        filename,
        model,
        passed_logger,
        transcript_system_message,
        transcript_text=None,
    ):
        calls.append(
            (
                "bowen",
                filename,
                model,
                passed_logger,
                transcript_system_message,
                transcript_text,
            )
        )
        return True

    monkeypatch.setattr(extraction_pipeline, "extract_scored_emphasis", _mock_emphasis)
    monkeypatch.setattr(
        extraction_pipeline,
        "extract_bowen_references_from_transcript",
        _mock_bowen,
    )

    ok = extraction_pipeline.extract_bowen_and_emphasis(
        "Example - yaml.md",
        logger=logger,
    )

    assert ok is True
    assert calls[0] == ("load", "Example - yaml.md")
    assert calls[1] == ("cache", transcript_text)
    assert calls[2] == (
        "emphasis",
        "Example - yaml.md",
        config.DEFAULT_MODEL,
        logger,
        cached_system_message,
    )
    assert calls[3] == (
        "bowen",
        "Example - yaml.md",
        config.DEFAULT_MODEL,
        logger,
        cached_system_message,
        transcript_text,
    )
