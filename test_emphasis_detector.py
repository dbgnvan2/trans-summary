import pytest
from emphasis_detector import EmphasisDetector


@pytest.fixture
def detector():
    return EmphasisDetector()


@pytest.mark.parametrize("text", [
    "I think that's an extraordinarily important insight",
    "very important things happen in this other child relationship",
    "that's a real important concept",
    "just to emphasize this groupiness",
    "So just to emphasize",
    "That's the key note, I think you recognize",
    "the key thing about emotional objectivity that I want to emphasize",
])
def test_tier1_matches(detector, text):
    """Test Tier 1: Explicit Emphasis Statements (95%+ confidence)"""
    matches = detector.detect(text)
    assert len(matches) > 0, f"Failed to match Tier 1: {text}"
    assert matches[0].tier == "1", f"Incorrect tier for: {text}"


@pytest.mark.parametrize("text", [
    "I don't have to sell that point of view to anybody",
    "of course, was Bowen's insight at NIH",
    "This, I think, is identical what family systems theory tries to enable people to do",
    "This is one of my favorite quotes of all",
    "It's one of my favorite quotes from Bowen",
    "that's the pride and joy of all",
    "So just to review some points about the emotional system",
    "just to summarize these three systems",
])
def test_tier2_matches(detector, text):
    """Test Tier 2: Meta-Commentary Patterns (80-95% confidence)"""
    matches = detector.detect(text)
    assert len(matches) > 0, f"Failed to match Tier 2: {text}"
    assert matches[0].tier == "2", f"Incorrect tier for: {text}"


@pytest.mark.parametrize("text", [
    "Quote Murray Bowen,",
    "Another Bowen quote,",
    "you know, whose quote this is, of course, Murray Bowen",
    "Murray Bowen, we live our lives in networks of emotional forces",
])
def test_tier3_matches(detector, text):
    """Test Tier 3: Bowen Reference Detection"""
    matches = detector.detect(text)
    assert len(matches) > 0, f"Failed to match Tier 3: {text}"
    assert matches[0].tier == "Bowen", f"Incorrect tier for: {text}"


@pytest.mark.parametrize("text", [
    "I think we should move on",  # Casual I think
    "Next slide, please",  # Procedural
    "I remember when",  # Anecdote
    "you know",  # Filler
    "Thank you for coming",  # Appreciation
    "I appreciate your time",  # Appreciation
    "Let's move to the next topic",  # Procedural
    "I mean, it's okay",  # Filler
])
def test_exclusions(detector, text):
    """Test patterns that should be EXCLUDED (False Positives)"""
    matches = detector.detect(text)
    assert len(matches) == 0, f"Should NOT match: {text}"
