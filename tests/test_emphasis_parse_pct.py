"""M3 (review 2026-07-18): a scored-emphasis header that omits the '%' but carries a
timestamp must still parse the score and preserve the timestamp. Before the fix, the
pattern-1 score class did not exclude '|', so the score group greedily swallowed
'92 | 00:04:09' -> _parse_score averaged the digits (26) and the timestamp was lost.

Also L6: the prompt-caching beta header is single-sourced in config."""
from pathlib import Path

import config
import transcript_utils
from transcript_utils import parse_scored_emphasis_output

_QUOTE = '"A quoted span of emphasized transcript text."'


def test_m3_percentless_header_keeps_score_and_timestamp():
    text = f"[Explicit - A2 - Rank: 92 | 00:04:09] Concept: Differentiation\n{_QUOTE}"
    items = parse_scored_emphasis_output(text)
    assert len(items) == 1, items
    assert items[0]["score"] == 92, f"score should be 92, got {items[0]['score']}"
    assert items[0]["timestamp"] == "00:04:09", items[0]["timestamp"]


def test_m3_percent_terminated_header_still_parses():
    text = f"[Explicit - A2 - Rank: 92% | 00:04:09] Concept: Differentiation\n{_QUOTE}"
    items = parse_scored_emphasis_output(text)
    assert len(items) == 1
    assert items[0]["score"] == 92
    assert items[0]["timestamp"] == "00:04:09"


def test_l6_beta_header_single_sourced():
    assert config.ANTHROPIC_CACHE_BETA_HEADER == "prompt-caching-2024-07-31"
    src = Path(transcript_utils.__file__).read_text(encoding="utf-8")
    assert '"anthropic-beta": "prompt-caching' not in src, (
        "bare prompt-caching beta-header literal is still duplicated in transcript_utils; "
        "use config.ANTHROPIC_CACHE_BETA_HEADER")
