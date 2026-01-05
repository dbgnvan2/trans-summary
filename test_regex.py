import re

# Sample with extra newlines, missing bold, different italics, etc.
sample_topics = """
### Topic One
This is the description for topic one. It has some text.

*_(~25% of transcript; Sections 1-5)_*

###   Topic Two with Spaces  

This is topic two description.
It spans multiple lines.

_ (~15% of transcript; Section 10) _

### Topic Three (No Percentage Match - Should Skip)
Description.
*_(~2% of transcript)_*

### Topic Four - Weird Formatting
Description here.
[~30% of transcript; Sections 20-25]
"""

# Sample themes with missing bold, different numbering
sample_themes = """
1. **Theme One**: Description of theme one.
*Source Sections: 1, 2*

2. Theme Two: Description of theme two without bold.
- Source Sections: 3, 4

3. **Theme Three**:
Description on new line.
*Source Sections: 5*
"""


def test_topics():
    print("Testing Topics Regex...")
    # The regex from abstract_pipeline.py
    pattern = r"###\s+([^\n]+)\s*\n\s*((?:(?!\n###).)+?)\s*\n\s*[\*_\-\s\[\(]+~?(\d+)%[^;\n]+;\s*Sections?\s+([\d\-,\s]+)(?:\)|\])?[\*_\-\s]*"

    matches = re.findall(pattern, sample_topics, re.DOTALL)

    # Verify we found 3 matches (Topic Three should fail due to missing '; Sections')
    assert len(matches) == 3, f"Expected 3 matches, found {len(matches)}"

    # Verify content of matches
    # Match 0: Topic One
    assert matches[0][0].strip() == "Topic One"
    assert matches[0][2] == "25"
    assert matches[0][3] == "1-5"

    # Match 1: Topic Two
    assert matches[1][0].strip() == "Topic Two with Spaces"
    assert "multiple lines" in matches[1][1]
    assert matches[1][2] == "15"
    assert matches[1][3] == "10"

    # Match 2: Topic Four
    assert matches[2][0].strip() == "Topic Four - Weird Formatting"
    assert matches[2][2] == "30"
    assert matches[2][3] == "20-25"


def test_themes():
    print("\nTesting Themes Regex...")
    # The regex from abstract_pipeline.py
    pattern = (
        r"\d+\.\s+(?:\*\*)?(.+?)(?:\*\*)?:\s*(.+?)\s*\n\s*[\*_\-]*\s*Source Sections:"
    )

    matches = re.findall(pattern, sample_themes, re.DOTALL)

    assert len(matches) == 3, f"Expected 3 matches, found {len(matches)}"

    # Theme One
    assert matches[0][0] == "Theme One"
    assert matches[0][1].strip() == "Description of theme one."

    # Theme Two
    assert matches[1][0] == "Theme Two"
    assert matches[1][1].strip() == "Description of theme two without bold."

    # Theme Three
    assert matches[2][0] == "Theme Three"
    assert matches[2][1].strip() == "Description on new line."


def test_topic_missing_semicolon():
    print("\nTesting Topic Missing Semicolon...")
    # The regex from abstract_pipeline.py
    pattern = r"###\s+([^\n]+)\s*\n\s*((?:(?!\n###).)+?)\s*\n\s*[\*_\-\s\[\(]+~?(\d+)%[^;\n]+;\s*Sections?\s+([\d\-,\s]+)(?:\)|\])?[\*_\-\s]*"

    sample = """
### Valid Topic
Description.
*_(~10% of transcript; Sections 1)_*

### Invalid Topic (No Semicolon)
Description.
*_(~10% of transcript Sections 2)_*

### Another Valid Topic
Description.
*_(~10% of transcript; Sections 3)_*
"""
    matches = re.findall(pattern, sample, re.DOTALL)

    # Verify we found 2 matches (Invalid Topic should fail due to missing ';')
    assert len(matches) == 2, f"Expected 2 matches, found {len(matches)}"

    # Verify content of matches
    assert matches[0][0].strip() == "Valid Topic"
    assert matches[1][0].strip() == "Another Valid Topic"
