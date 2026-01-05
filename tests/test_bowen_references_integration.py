import os
from pathlib import Path
import pytest
import shutil
import re

import config
from extraction_pipeline import extract_bowen_references_from_transcript
from transcript_utils import extract_bowen_references, strip_yaml_frontmatter, setup_logging
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
    config.settings.PROMPTS_DIR.mkdir()

    # Create necessary subdirectories within the mock transcripts base
    (config.PROJECTS_DIR).mkdir(exist_ok=True)
    (config.SOURCE_DIR).mkdir(exist_ok=True)
    (config.PROCESSED_DIR).mkdir(exist_ok=True)

    yield tmp_path

    # Restore original config paths
    config.set_transcripts_base(original_transcripts_base)
    config.settings.PROMPTS_DIR = original_prompts_dir


@pytest.fixture
def mock_transcript_file(mock_project_dirs):
    """Create a mock formatted transcript file."""
    base_name = "Test Title - Test Presenter - 2024-01-01"
    formatted_filename = f"{base_name}{config.SUFFIX_YAML}"
    project_dir = config.PROJECTS_DIR / base_name
    project_dir.mkdir(exist_ok=True)
    
    file_path = project_dir / formatted_filename
    file_path.write_text("This is a mock transcript content with some text.\n" \
                         "## Section 1\n" \
                         "Content for section 1.\n" \
                         "## Section 2\n" \
                         "Content for section 2.", encoding="utf-8")
    return formatted_filename, base_name, project_dir


@pytest.fixture
def mock_bowen_prompt_file(mock_project_dirs):
    """Create a mock bowen extraction prompt file."""
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

> **On Triangles and Emotional Forces:** "We live our lives in networks of emotional forces. Follow triangle patterns."

> **On Triangles as Molecules:** "Triangles are the molecules of an emotional system."

> **On Two-Person Systems:** "A two person system is inherently unstable."
"""


@patch('extraction_pipeline._generate_summary_with_claude')
def test_bowen_references_generation_and_extraction(
    mock_generate_summary_with_claude,
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

    # Run the generation pipeline step
    success = extract_bowen_references_from_transcript(
        formatted_filename=formatted_filename,
        logger=logger
    )

    assert success, "Bowen reference extraction should succeed"

    bowen_output_path = project_dir / f"{base_name}{config.SUFFIX_BOWEN}"
    assert bowen_output_path.exists(), "Bowen references output file should exist"

    generated_content = bowen_output_path.read_text(encoding="utf-8")
    
    # Assert that the problematic "## Bowen References" is NOT in the output
    assert "## Bowen References" not in generated_content
    # Assert that the desired LLM-generated header IS in the output
    assert "# Bowen References Extracted from Transcript" in generated_content

    # Assert that the content after the header matches the mock response structure
    expected_content_after_header = MOCK_LLM_BOWEN_RESPONSE.strip()
    # The strip_yaml_frontmatter is usually done by load_bowen_references, but not relevant here
    # Remove the initial blank line before comparing
    cleaned_generated_content = generated_content.strip()

    # Compare without worrying about potential extra newlines or leading/trailing spaces
    assert cleaned_generated_content.startswith("# Bowen References Extracted from Transcript"), \
        "Generated content should start with the LLM-generated header"
    
    # Ensure the full mock response is present as expected
    assert cleaned_generated_content == expected_content_after_header

    # Test extraction using transcript_utils.extract_bowen_references
    # Call load_bowen_references, which internally calls extract_bowen_references
    # on the generated file.
    extracted_references = extract_bowen_references(generated_content)

    expected_references = [
        ("On Triangles and Emotional Forces", "We live our lives in networks of emotional forces. Follow triangle patterns."),
        ("On Triangles as Molecules", "Triangles are the molecules of an emotional system."),
        ("On Two-Person Systems", "A two person system is inherently unstable."),
    ]
    
    assert len(extracted_references) == len(expected_references), \
        f"Expected {len(expected_references)} references, but got {len(extracted_references)}"
    
    for i, (expected_concept, expected_quote) in enumerate(expected_references):
        actual_concept, actual_quote = extracted_references[i]
        assert actual_concept == expected_concept
        assert actual_quote == expected_quote

    logger.info("Test passed: Bowen references generated and extracted correctly.")

