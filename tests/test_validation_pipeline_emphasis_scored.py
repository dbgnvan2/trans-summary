from pathlib import Path

import config
from validation_pipeline import _extract_emphasis_quotes_from_file


def test_extract_emphasis_quotes_prefers_scored_file(tmp_path):
    stem = "Emphasis-Scored-Test"
    project_dir = tmp_path / stem
    project_dir.mkdir(parents=True, exist_ok=True)

    formatted_file = project_dir / f"{stem}{config.SUFFIX_FORMATTED}"
    formatted_file.write_text("## Section 1\nx\n", encoding="utf-8")

    scored_file = project_dir / f"{stem}{config.SUFFIX_EMPHASIS_SCORED}"
    scored_file.write_text(
        '[A - A1 - Rank: 95%] Concept: Core theoretical foundation\n'
        '"This is an exact quote from the transcript."\n',
        encoding="utf-8",
    )

    quotes = _extract_emphasis_quotes_from_file(formatted_file)

    assert len(quotes) == 1
    assert "Core theoretical foundation" in quotes[0][0]
    assert quotes[0][1] == "This is an exact quote from the transcript."
