import os
from pathlib import Path
import pytest
import shutil
import re

import config
from extraction_pipeline import extract_bowen_references_from_transcript
from transcript_utils import parse_bowen_references_text, strip_yaml_frontmatter, setup_logging
from unittest.mock import patch, MagicMock

# Setup a logger for the test
logger = setup_logging("test_bowen_references_integration")


@pytest.fixture
def mock_project_dirs(tmp_path):
    """Fixture to create mock project directories."""
    # Temporarily override config paths for testing
    original_transcripts_base = config.TRANSCRIPTS_BASE
    original_prompts_dir = config.PROMPTS_DIR

    config.set_transcripts_base(tmp_path)
    config.settings.PROMPTS_DIR = tmp_path / "prompts"
    config.PROMPTS_DIR = tmp_path / "prompts"  # module attr (production read site, config.py:327)
    config.settings.PROMPTS_DIR.mkdir()

    # Create necessary subdirectories within the mock transcripts base
    (config.PROJECTS_DIR).mkdir(exist_ok=True)
    (config.SOURCE_DIR).mkdir(exist_ok=True)
    (config.PROCESSED_DIR).mkdir(exist_ok=True)

    yield tmp_path

    # Restore original config paths
    config.set_transcripts_base(original_transcripts_base)
    config.settings.PROMPTS_DIR = original_prompts_dir
    config.PROMPTS_DIR = original_prompts_dir


@pytest.fixture
def mock_transcript_file(mock_project_dirs):
    """Create a mock formatted transcript file."""
    base_name = "Test Title - Test Presenter - 2024-01-01"
    formatted_filename = f"{base_name}{config.SUFFIX_YAML}"
    project_dir = config.PROJECTS_DIR / base_name
    project_dir.mkdir(exist_ok=True)
    
    file_path = project_dir / formatted_filename
    file_path.write_text(
        "This is a mock transcript content with some text.\n"
        "## Section 1\n"
        "Murray Bowen said we live our lives in networks of emotional forces. Follow triangle patterns.\n"
        "To quote Bowen, triangles are the molecules of an emotional system.\n"
        "## Section 2\n"
        "I remember Murray saying a two person system is inherently unstable.\n",
        encoding="utf-8",
    )
    return formatted_filename, base_name, project_dir


@pytest.fixture
def mock_bowen_prompt_file(mock_project_dirs):
    """Create a mock Bowen extraction prompt file.

    Writes into the redirected ``config.PROMPTS_DIR`` (the tmp dir set by
    ``mock_project_dirs``), so the real repo prompt file is never touched.
    """
    prompt_content = """# BOWEN REFERENCE EXTRACTION
Your task is to extract direct quotes or close paraphrases.
## OUTPUT FORMAT
For each reference found, use the following format exactly:
> **Concept Descriptor:** "Continuous verbatim quote or close paraphrase."
---
TRANSCRIPT:
{{insert_transcript_text_here}}
"""
    prompt_file = config.PROMPTS_DIR / config.PROMPT_BOWEN_EXTRACTION_FILENAME
    prompt_file.write_text(prompt_content, encoding="utf-8")
    return prompt_file


# Mock LLM response for Bowen references
MOCK_LLM_BOWEN_RESPONSE = """
# Bowen References Extracted from Transcript

> **On Triangles and Emotional Forces:** "Murray Bowen said we live our lives in networks of emotional forces. Follow triangle patterns."

> **On Triangles as Molecules:** "To quote Bowen, triangles are the molecules of an emotional system."

> **On Two-Person Systems:** "I remember Murray saying a two person system is inherently unstable."

> **Theory-only mention:** "In Bowen theory terms and not parts and wholes."
"""


@patch("extraction_pipeline._filter_bowen_references_semantically")
@patch('extraction_pipeline._generate_summary_with_claude')
def test_bowen_references_generation_and_extraction(
    mock_generate_summary_with_claude,
    mock_filter_bowen_references_semantically,
    mock_project_dirs,
    mock_transcript_file,
    mock_bowen_prompt_file
):
    """
    Test the full process of generating Bowen references and then extracting them.
    Ensures that the output file structure is correct and parsable.
    """
    formatted_filename, base_name, project_dir = mock_transcript_file
    
    # Configure the mock LLM response
    mock_generate_summary_with_claude.return_value = MOCK_LLM_BOWEN_RESPONSE
    mock_filter_bowen_references_semantically.side_effect = lambda refs, *_: refs

    # Run the generation pipeline step
    success = extract_bowen_references_from_transcript(
        formatted_filename=formatted_filename,
        logger=logger
    )

    assert success, "Bowen reference extraction should succeed"

    bowen_output_path = project_dir / f"{base_name}{config.SUFFIX_BOWEN}"
    assert bowen_output_path.exists(), "Bowen references output file should exist"

    generated_content = bowen_output_path.read_text(encoding="utf-8")
    
    # Current pipeline normalizes output to canonical "## Bowen References" section.
    assert generated_content.strip().startswith("## Bowen References")

    # Re-extract via the REAL consumer for the saved `### Concept\n> "quote"` format
    # (parse_bowen_references_text — extract_bowen_references reads the abandoned
    # single-line `> **Label:** "quote"` shape and mis-reads the concept as '>').
    extracted_references = parse_bowen_references_text(generated_content)

    expected_references = [
        ("On Triangles and Emotional Forces", "Murray Bowen said we live our lives in networks of emotional forces. Follow triangle patterns."),
        ("On Triangles as Molecules", "To quote Bowen, triangles are the molecules of an emotional system."),
        ("On Two-Person Systems", "I remember Murray saying a two person system is inherently unstable."),
    ]

    assert len(extracted_references) == len(expected_references), \
        f"Expected {len(expected_references)} references, but got {len(extracted_references)}"

    for i, (expected_concept, expected_quote) in enumerate(expected_references):
        actual_concept, actual_quote = extracted_references[i][0], extracted_references[i][1]
        assert actual_concept == expected_concept
        assert actual_quote == expected_quote

    logger.info("Test passed: Bowen references generated and extracted correctly.")


@patch("extraction_pipeline._filter_bowen_references_semantically")
@patch("extraction_pipeline._generate_summary_with_claude")
def test_bowen_references_drop_ungrounded_placeholder(
    mock_generate_summary_with_claude,
    mock_filter_bowen_references_semantically,
    mock_project_dirs,
    mock_transcript_file,
    mock_bowen_prompt_file,
):
    """
    Ensure placeholder/non-transcript references are removed before saving.
    """
    formatted_filename, base_name, project_dir = mock_transcript_file
    mock_generate_summary_with_claude.return_value = (
        '> **Placeholder:** "I do not see any input items provided in your message."'
    )
    mock_filter_bowen_references_semantically.return_value = [
        ("Placeholder", "I do not see any input items provided in your message.")
    ]

    success = extract_bowen_references_from_transcript(
        formatted_filename=formatted_filename,
        logger=logger,
    )
    assert success

    bowen_output_path = project_dir / f"{base_name}{config.SUFFIX_BOWEN}"
    generated_content = bowen_output_path.read_text(encoding="utf-8")

    assert "I do not see any input items provided in your message." not in generated_content
    assert generated_content.strip().startswith("## Bowen References")
    # No grounded references should be emitted
    assert '> **' not in generated_content


@patch("extraction_pipeline._filter_bowen_references_semantically")
@patch("extraction_pipeline._generate_summary_with_claude")
def test_bowen_references_fallback_to_primary_when_filter_invalid(
    mock_generate_summary_with_claude,
    mock_filter_bowen_references_semantically,
    mock_project_dirs,
    mock_transcript_file,
    mock_bowen_prompt_file,
):
    """
    If semantic filter returns junk, keep grounded references from primary extraction output.
    """
    formatted_filename, base_name, project_dir = mock_transcript_file
    mock_generate_summary_with_claude.return_value = MOCK_LLM_BOWEN_RESPONSE
    mock_filter_bowen_references_semantically.return_value = [
        ("Placeholder", "I do not see any input items provided in your message.")
    ]

    success = extract_bowen_references_from_transcript(
        formatted_filename=formatted_filename,
        logger=logger,
    )
    assert success

    bowen_output_path = project_dir / f"{base_name}{config.SUFFIX_BOWEN}"
    generated_content = bowen_output_path.read_text(encoding="utf-8")
    extracted = parse_bowen_references_text(generated_content)

    assert len(extracted) == 3
    assert extracted[0][0] == "On Triangles and Emotional Forces"


def test_extract_bowen_references_rejects_prose():
    """The model's "no references" PROSE must not parse into a garbage candidate
    (concept='There are no instances of', quote='Bowen said,') — the shipped bug
    that produced a confusing '0 grounded refs from 1 candidate' diagnostic."""
    from transcript_utils import extract_bowen_references
    prose = '## Bowen References\n\n> There are no instances of "Bowen said," in this transcript.\n'
    assert extract_bowen_references(prose) == []
    prose2 = '## Bowen References\n\nThe input contains only a label and a fragment ("Bowen said,").\n'
    assert extract_bowen_references(prose2) == []


def test_extract_bowen_references_parses_bold_format():
    """The prompt's bold format (`> **Concept:** "quote"`, colon inside or outside
    the bold) still parses correctly after the prose-rejection tightening."""
    from transcript_utils import extract_bowen_references
    content = (
        '## Bowen References\n\n'
        '> **On Triangles:** "Murray Bowen said triangles are molecules of an emotional system."\n'
        '> **On Differentiation**: "Bowen stressed the importance of differentiation of self."\n'
    )
    refs = extract_bowen_references(content)
    assert refs == [
        ("On Triangles", "Murray Bowen said triangles are molecules of an emotional system."),
        ("On Differentiation", "Bowen stressed the importance of differentiation of self."),
    ]


def test_extract_bowen_references_non_bold_fallback():
    """A real reference the model emitted WITHOUT the bold format (`Label: "quote"`)
    must still parse — requiring bold alone silently dropped it (P19)."""
    from transcript_utils import extract_bowen_references
    content = (
        '## Bowen References\n\n'
        '> On Triangles: "Murray Bowen said triangles are molecules of an emotional system."\n'
    )
    refs = extract_bowen_references(content)
    assert refs == [
        ("On Triangles", "Murray Bowen said triangles are molecules of an emotional system."),
    ]


def test_extract_bowen_references_keeps_quote_containing_no():
    """A real quote whose body contains 'there are no ...' must NOT be dropped by
    the 'no references' prose guard (the guard runs only post-parse)."""
    from transcript_utils import extract_bowen_references
    content = (
        '## Bowen References\n\n'
        '> **On Differentiation:** "Bowen said there are no isolated individuals in an emotional system."\n'
    )
    refs = extract_bowen_references(content)
    assert refs == [
        ("On Differentiation", "Bowen said there are no isolated individuals in an emotional system."),
    ]


def test_extract_bowen_references_rejects_prose_colon_quote_without_attribution():
    """Prose with a 'Label: "quote"' shape but NO Bowen attribution must not parse
    into a garbage candidate (structural test, not a keyword blocklist)."""
    from transcript_utils import extract_bowen_references
    prose = '## Bowen References\n\nSummary: "differentiation of self is discussed at length."\n'
    assert extract_bowen_references(prose) == []


def test_extract_bowen_references_long_label_not_dropped():
    """A long non-bold concept label is not silently dropped (no 60-char cap)."""
    from transcript_utils import extract_bowen_references
    content = (
        '## Bowen References\n\n'
        '> On Differentiation of Self in the Context of Family Emotional Process: "Bowen said triangles are molecules."\n'
    )
    refs = extract_bowen_references(content)
    assert refs and refs[0][0].startswith("On Differentiation of Self")


def test_extract_bowen_references_concept_attributed_non_bold():
    """A non-bold ref whose attribution lives in the CONCEPT label (not the quote)
    must parse — quote-only attribution would drop it, contradicting the rule filter."""
    from transcript_utils import extract_bowen_references
    content = '## Bowen References\n\n> Bowen\'s Timeline Prediction: "this would take 20 years."\n'
    refs = extract_bowen_references(content)
    assert refs == [("Bowen's Timeline Prediction", "this would take 20 years.")]


def test_extract_bowen_references_drops_bold_wrapped_no_refs_prose():
    """A bold-wrapped prose 'no references' explanation must be dropped, not parsed
    into a garbage candidate via the bold path."""
    from transcript_utils import extract_bowen_references
    content = '## Bowen References\n\n> **Note:** "There are no explicit references to Bowen in this transcript."\n'
    refs = extract_bowen_references(content)
    assert refs == []


def test_extract_bowen_references_keeps_quote_with_content_negation():
    """A real Bowen-attributed quote whose body contains a content negation
    ('no direct causal link') is a CONTENT fact, not a 'no references found'
    meta-statement — the guard must bind to reference-absence OBJECTS
    (references/instances/quotes), never a free-standing 'direct'/'explicit' (P2)."""
    from transcript_utils import extract_bowen_references
    content = (
        '## Bowen References\n\n'
        '> **On Cancer Etiology:** "Bowen said there is no direct causal link between stress and cancer."\n'
    )
    refs = extract_bowen_references(content)
    assert refs == [
        ("On Cancer Etiology", "Bowen said there is no direct causal link between stress and cancer."),
    ]


def test_extract_bowen_references_keeps_attributed_quote_with_meta_shaped_negation():
    """An ATTRIBUTED quote whose body contains a reference-absence-shaped negation
    ('no instances of ...') is a real recollection, not a meta-statement — the guard
    is INVERTED: keep if Bowen-attributed, drop only an UNATTRIBUTED meta (P2)."""
    from transcript_utils import extract_bowen_references
    content = (
        '## Bowen References\n\n'
        '> **On Emotional Cutoff:** "Bowen said there are no instances of emotional cutoff in this family."\n'
    )
    refs = extract_bowen_references(content)
    assert refs == [
        ("On Emotional Cutoff", "Bowen said there are no instances of emotional cutoff in this family."),
    ]
