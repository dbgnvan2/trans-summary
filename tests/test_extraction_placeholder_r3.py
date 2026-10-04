"""R3 (review B-05): a resolved {{placeholder}} is not re-appended as context.

Spec: docs/plan_review_fixes_2026-10-04.md#R3
"""
from unittest.mock import MagicMock

import config
import extraction_pipeline


def _run(monkeypatch, template, **replacements):
    captured = {}
    monkeypatch.setattr(extraction_pipeline, "_load_summary_prompt", lambda _n: template)
    monkeypatch.setattr(
        extraction_pipeline, "_generate_summary_with_claude",
        lambda prompt, *_a, **_k: captured.setdefault("prompt", prompt) and "ok",
    )
    extraction_pipeline._generate_with_cached_transcript(
        prompt_filename="dummy.md",
        model=config.DEFAULT_MODEL,
        logger=MagicMock(),
        transcript_system_message=[{"type": "text", "text": "cached"}],
        **replacements,
    )
    return captured["prompt"]


def test_r3a_resolved_placeholder_not_reappended(monkeypatch):
    prompt = _run(monkeypatch, "Themes:\n{{ structural_themes }}\nEnd.",
                  structural_themes="UNIQUE-THEME-TEXT")
    assert prompt.count("UNIQUE-THEME-TEXT") == 1
    assert "## Provided Context" not in prompt


def test_r3b_only_unresolved_placeholder_appended(monkeypatch):
    prompt = _run(monkeypatch, "Themes:\n{{structural_themes}}\n",
                  structural_themes="S-TEXT", interpretive_themes="I-TEXT")
    assert prompt.count("S-TEXT") == 1
    assert "### interpretive_themes" in prompt
    assert "### structural_themes" not in prompt
