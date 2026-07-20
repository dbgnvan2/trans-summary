"""Review 2026-07-18 batch 8:
- M11: pre-normalized haystack must give identical results (just avoids re-normalizing).
- L8:  explicit script_name attributes token cost; missing logger/name -> 'unknown_script'.
- L16: generate_* refuse a path-traversal base_name before any path access.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import html_generator
import transcript_utils
from transcript_utils import find_text_in_content, normalize_text


# --- M11 ---
def test_m11_prenormalized_haystack_matches_default():
    haystack = "the quick brown fox jumps over the lazy dog. " * 30
    pre = normalize_text(haystack, aggressive=True)
    for needle in ["quick brown fox jumps", "zulu yankee xray victor nothing here"]:
        default = find_text_in_content(needle, haystack, aggressive_normalization=True)
        prenorm = find_text_in_content(needle, haystack, aggressive_normalization=True,
                                       haystack_normalized=pre)
        assert default == prenorm, f"pre-normalized result differs for {needle!r}"


# --- L8 ---
def _ok_response():
    return SimpleNamespace(
        type="message", role="assistant", stop_reason="end_turn",
        content=[SimpleNamespace(type="text", text="x" * 80)],
        usage=SimpleNamespace(input_tokens=1, output_tokens=1,
                              cache_creation_input_tokens=0, cache_read_input_tokens=0),
        model="claude-3-5-haiku-20241022")


def _capture_script(monkeypatch):
    captured = {}
    monkeypatch.setattr(transcript_utils, "log_token_usage",
                        lambda script, model, usage, stop: captured.update(script=script))
    return captured


def test_l8_explicit_script_name_attributes_cost(monkeypatch):
    captured = _capture_script(monkeypatch)
    client = MagicMock()
    client.messages.create.return_value = _ok_response()
    transcript_utils.call_claude_with_retry(
        client=client, model="claude-3-5-haiku-20241022",
        messages=[{"role": "user", "content": "hi"}], max_tokens=64,
        logger=None, script_name="bowen_stage")
    assert captured["script"] == "bowen_stage"


def test_l8_no_logger_falls_back_to_unknown_script(monkeypatch):
    captured = _capture_script(monkeypatch)
    client = MagicMock()
    client.messages.create.return_value = _ok_response()
    transcript_utils.call_claude_with_retry(
        client=client, model="claude-3-5-haiku-20241022",
        messages=[{"role": "user", "content": "hi"}], max_tokens=64, logger=None)
    assert captured["script"] == "unknown_script"


# --- L16 ---
def test_l16_base_name_safety_check():
    assert transcript_utils.base_name_is_safe("Valid Transcript - Kerr - 2022-02-18")
    assert transcript_utils.base_name_is_safe("Systems... Part 2")  # ellipsis ok (no separators)
    for bad in ["../etc/passwd", "a/b", "a\\b", "..", ".", "x\x00y", ""]:
        assert not transcript_utils.base_name_is_safe(bad), bad


def test_l16_all_four_publish_entry_points_reject_unsafe_base_name(monkeypatch):
    import packaging_pipeline

    def _gate_must_not_run(b, l):
        raise AssertionError("unsafe base_name reached publish_allowed")

    monkeypatch.setattr(html_generator.release_gate, "publish_allowed", _gate_must_not_run)
    monkeypatch.setattr(packaging_pipeline.release_gate, "publish_allowed", _gate_must_not_run)
    bad = "../../etc/passwd"
    assert html_generator.generate_webpage(bad) is False
    assert html_generator.generate_simple_webpage(bad) is False
    assert html_generator.generate_pdf(bad) is False
    assert packaging_pipeline.package_transcript(bad) is False
