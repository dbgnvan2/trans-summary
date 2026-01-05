"""
Test script to verify timestamp removal regex on specific transcript artifacts.
"""

import re


def test_regex_removes_timestamps():
    """Test that the regex correctly removes timestamps including hours."""
    sample = """Unknown Speaker  59:06  
and

Unknown Speaker  59:07  
one or another, automatic responses would kick in automatically to preserve the life of that individual

Unknown Speaker  1:00:00  
Motivation.

Unknown Speaker  1:00:02  
Thank you. We all talk about,"""

    # This regex handles optional seconds part (?::\d+)?
    pattern = r"^\s*(\[[\d:.]+\]\s+[^:]+:|Unknown Speaker|Speaker \d+)\s+\d+:\d+(?::\d+)?"

    cleaned = re.sub(
        pattern,
        "",
        sample,
        flags=re.MULTILINE,
    )

    # Verify complete removal of speaker and timestamp lines
    assert "Unknown Speaker" not in cleaned
    assert "59:06" not in cleaned
    assert "1:00:00" not in cleaned

    # Verify no partial artifacts (like :00 from 1:00:00)
    # The buggy regex would leave :00
    assert ":00" not in cleaned
    assert ":02" not in cleaned

    # Verify content preservation
    assert "and" in cleaned
    assert "one or another" in cleaned
    assert "Motivation." in cleaned
    assert "Thank you. We all talk about," in cleaned
