from summary_pipeline import parse_topics_with_details, parse_themes
from transcript_utils import is_scaffolding_theme_name
import sys
import os
from pathlib import Path
from unittest.mock import patch
import pytest

# Ensure project root is in path
sys.path.append(os.getcwd())

FIXTURES = Path(__file__).parent / "tests" / "fixtures"


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


# The theme tests below run against the REAL producer format on real fixtures.
# The prior synthetic tests asserted LEGACY fallback formats the extraction never
# writes (`### Theme Header`, `N. **Theme**:`) — `test_parse_themes_header_format`
# specifically certified the A1 `###`-as-theme bug (capturing scaffolding as a
# theme). They passed only via dead fallback paths and masked a re-drift
# (TEST_VALIDITY_REPORT §3 / TODO A1–A3); replaced with real-artifact tests.
def test_parse_themes_real_structural_format():
    """parse_themes reads the REAL bold-numbered `**N. Title**` structural format
    (3 themes on the real KCFC file) via the preferred path — not scaffolding."""
    text = (FIXTURES / "kcfc_structural-themes.md").read_text(encoding="utf-8")
    themes = parse_themes(text)
    assert len(themes) == 3, [t["name"] for t in themes]
    assert not any(is_scaffolding_theme_name(t["name"]) for t in themes)
    assert "Over-Functioning" in themes[0]["name"]


def test_parse_themes_real_interpretive_format():
    """The same real path parses all 7 interpretive themes — the A2 regression
    (7 collapsed to 2 scaffolding blobs) must not recur."""
    text = (FIXTURES / "kcfc_interpretive-themes.md").read_text(encoding="utf-8")
    themes = parse_themes(text)
    assert len(themes) == 7, [t["name"] for t in themes]
    assert not any(is_scaffolding_theme_name(t["name"]) for t in themes)


def test_parse_themes_empty_on_scaffolding_only():
    """A scaffolding-only input yields ZERO themes (never captures a section header
    like '### Structural Themes (3 total)' as a theme — the A1 bug)."""
    scaffolding = "## Structural Themes (3 total)\n\n---\n\n### Summary Paragraph\nx\n"
    assert parse_themes(scaffolding) == []
