"""
Emphasis Detector Module
Identifies emphasized phrases and Bowen references in transcripts using deterministic patterns.

Implements a 3-tier detection system:
- Tier 1: Explicit Emphasis (95%+ confidence)
- Tier 2: Meta-Commentary (80-95% confidence)
- Tier 3: Bowen References

Usage:
    from emphasis_detector import EmphasisDetector
    detector = EmphasisDetector()
    matches = detector.detect(text)
"""

import re
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class EmphasisMatch:
    tier: str  # "1", "2", or "Bowen"
    pattern_name: str
    matched_text: str
    full_sentence: str
    context_before: str
    context_after: str
    start_char: int
    end_char: int


class EmphasisDetector:
    def __init__(self):
        self.compile_patterns()

    def compile_patterns(self):
        """Compile regex patterns for all tiers."""
        # TIER 1: Explicit Emphasis Statements
        self.tier1_patterns = [
            (
                "Direct Importance",
                r"(?:extraordinarily|very|real|really)\s+(?:important|significant|key|critical)\s+(?:insight|concept|point|things|role|idea)",
            ),
            ("Emphasis Directives", r"(?:just to|So|Now)\s+(?:emphasize|stress)"),
            (
                "Explicit Key/Critical",
                r"(?:the\s+key|critical)\s+(?:thing|note|concept|idea|point)\s+(?:is|that|about)",
            ),
        ]

        # TIER 2: Meta-Commentary Patterns
        self.tier2_patterns = [
            (
                "Selling Points",
                r"(?:I\s+don't\s+have\s+to\s+sell|don't\s+need\s+to\s+convince|obviously|clearly)",
            ),
            (
                "Theoretical Attribution",
                r"(?:of\s+course,?\s+was|this\s+was)\s+Bowen'?s\s+(?:insight|idea|concept|discovery)",
            ),
            (
                "Identity/Equivalence",
                r"(?:This,?\s+I\s+think,?\s+is\s+identical|This\s+is\s+the\s+same\s+as|This\s+illustrates)",
            ),
            (
                "Pride/Favorite",
                r"(?:pride\s+and\s+joy|one\s+of\s+my\s+favorite|favorite\s+quote)",
            ),
            (
                "Summary/Review",
                r"(?:just to|So|Now)\s+(?:review|summarize)\s+(?:some\s+)?(?:points?|key|the)",
            ),
        ]

        # TIER 3: Bowen Reference Detection
        self.tier3_patterns = [
            (
                "Direct Bowen Quotes",
                r"(?:Quote|Another)\s+(?:Murray\s+)?Bowen(?:'?s?\s+quote)?|whose\s+quote\s+this\s+is.*Bowen",
            ),
            (
                "Bowen Attribution",
                r"(?:Murray\s+)?Bowen\s+(?:said|wrote|thought|believed|described|called|,)",
            ),
        ]

        # EXCLUSIONS (False Positives)
        self.exclusion_patterns = [
            (
                "Casual I think",
                r"^I\s+think(?!\s+(?:that's|this\s+is)\s+(?:an\s+)?(?:extraordinarily|very|real|really)\s+important)",
            ),
            ("Personal Anecdotes", r"(?:I\s+remember|reminds\s+me|I\s+recall)\s+"),
            (
                "Procedural Statements",
                r"(?:Next\s+slide|Okay,?\s+so|Next\s+one|Let's\s+move)",
            ),
            (
                "Conversational Fillers",
                r"\b(?:you\s+know|of\s+course|I\s+mean)\b(?!.*Bowen)",
            ),
            (
                "Generic Appreciation",
                r"(?:thank\s+you|thanks\s+for|appreciate|good\s+to\s+see)",
            ),
        ]

    def split_sentences(self, text: str) -> List[Tuple[str, int, int]]:
        """
        Split text into sentences while preserving offsets.
        Returns list of (sentence_text, start_offset, end_offset).
        """
        # Heuristic split on .!? followed by space/end, avoiding common abbreviations
        pattern = r'(?<!\bDr)(?<!\bMr)(?<!\bMs)(?<!\bU\.S)(?<!\bvs)(?<=[.!?])\s+(?=[A-Z"\'\(])'

        spans = []
        start = 0
        for match in re.finditer(pattern, text):
            end = match.start()
            spans.append((text[start:end].strip(), start, end))
            start = match.end()

        if start < len(text):
            spans.append((text[start:].strip(), start, len(text)))

        return [s for s in spans if s[0]]

    def detect(self, text: str) -> List[EmphasisMatch]:
        """
        Detect emphasis patterns in text.
        """
        sentences = self.split_sentences(text)
        matches = []

        def is_excluded(sent_text):
            for _, pattern in self.exclusion_patterns:
                if re.search(pattern, sent_text, re.IGNORECASE):
                    return True
            return False

        for i, (sent_text, start, end) in enumerate(sentences):
            if not sent_text:
                continue

            if is_excluded(sent_text):
                continue

            found_match = None

            # Check tiers in order
            for tier, patterns in [
                ("1", self.tier1_patterns),
                ("2", self.tier2_patterns),
                ("Bowen", self.tier3_patterns),
            ]:
                for name, pattern in patterns:
                    m = re.search(pattern, sent_text, re.IGNORECASE)
                    if m:
                        found_match = (tier, name, m.group(0))
                        break
                if found_match:
                    break

            if found_match:
                tier, name, matched_phrase = found_match
                context_before = sentences[i - 1][0] if i > 0 else ""
                context_after = sentences[i + 1][0] if i < len(sentences) - 1 else ""

                matches.append(
                    EmphasisMatch(
                        tier=tier,
                        pattern_name=name,
                        matched_text=matched_phrase,
                        full_sentence=sent_text,
                        context_before=context_before,
                        context_after=context_after,
                        start_char=start,
                        end_char=end,
                    )
                )

        return matches
