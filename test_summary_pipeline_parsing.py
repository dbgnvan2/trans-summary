from summary_pipeline import parse_topics_with_details, parse_themes
import sys
import os
from unittest.mock import patch
import pytest

# Ensure project root is in path
sys.path.append(os.getcwd())


@pytest.fixture
def dummy_transcript():
    return "## Section 1\nContent."


@patch('summary_pipeline.extract_key_points')
def test_parse_topics_standard(mock_extract, dummy_transcript):
    """Test parsing of standard topic format."""
    mock_extract.return_value = ["Point 1", "Point 2"]

    markdown = """
### Topic One
Description of topic one.
*_(~25% of transcript; Sections 1-5)_*

### Topic Two
Description of topic two.
*_(~10% of transcript; Sections 6)_*
"""
    topics = parse_topics_with_details(markdown, dummy_transcript)

    assert len(topics) == 2
    # Topics are sorted by percentage descending
    assert topics[0]['name'] == "Topic One"
    assert topics[0]['percentage'] == 25
    assert topics[0]['sections'] == "1-5"

    assert topics[1]['name'] == "Topic Two"
    assert topics[1]['percentage'] == 10


@patch('summary_pipeline.extract_key_points')
def test_parse_topics_variations(mock_extract, dummy_transcript):
    """Test parsing of topics with formatting variations (spaces, brackets)."""
    mock_extract.return_value = []

    markdown = """
### Topic Spaces
Description with spaces.
   _ (~15% of transcript; Section 10) _

### Topic Brackets
Description with brackets.
[~20% of transcript; Sections 11, 12]

### Topic No Metadata (Should Skip)
Description without metadata line.
"""
    topics = parse_topics_with_details(markdown, dummy_transcript)

    assert len(topics) == 2

    # Sorted by percentage: 20% (Brackets) then 15% (Spaces)
    assert topics[0]['name'] == "Topic Brackets"
    assert topics[0]['percentage'] == 20
    assert topics[0]['sections'] == "11, 12"

    assert topics[1]['name'] == "Topic Spaces"
    assert topics[1]['percentage'] == 15
    assert topics[1]['sections'] == "10"


@patch('summary_pipeline.extract_key_points')
def test_parse_topics_low_percentage(mock_extract, dummy_transcript):
    """Test that topics with less than 5% coverage are filtered out."""
    mock_extract.return_value = []
    markdown = """
### Small Topic
Description.
*_(~4% of transcript; Sections 1)_*
"""
    topics = parse_topics_with_details(markdown, dummy_transcript)
    assert len(topics) == 0, "Should filter out topics < 5%"


def test_parse_themes_standard():
    """Test parsing of standard numbered themes."""
    markdown = """
1. **Theme One**: Description one.
*Source Sections: 1, 2*

2. **Theme Two**: Description two.
*Source Sections: 3*
"""
    themes = parse_themes(markdown)
    assert len(themes) == 2
    assert themes[0]['name'] == "Theme One"
    assert themes[0]['sections'] == "1, 2"
    assert themes[1]['name'] == "Theme Two"


def test_parse_themes_variations():
    """Test parsing of themes with formatting variations."""
    markdown = """
1. Theme No Bold: Description.
- Source Sections: 1

2. **Theme Separator**: Description
   Source Sections: 2, 3
"""
    themes = parse_themes(markdown)
    assert len(themes) == 2
    assert themes[0]['name'] == "Theme No Bold"
    assert themes[0]['sections'] == "1"
    assert themes[1]['name'] == "Theme Separator"
    assert themes[1]['sections'] == "2, 3"


def test_parse_themes_header_format():
    """Test parsing of themes using the new ### header format."""
    markdown = """
### Theme Header
Description.
*Source Sections: 1-5*
"""
    themes = parse_themes(markdown)
    assert len(themes) == 1
    assert themes[0]['name'] == "Theme Header"
    assert themes[0]['sections'] == "1-5"
