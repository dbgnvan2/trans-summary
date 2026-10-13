"""N1–N5 — small open TODO items fixed 2026-10-12.

Spec: docs/plan_small_fixes_2026-10-12.md
"""
import inspect
import logging
from unittest.mock import MagicMock

import abstract_pipeline as ap
import config
import extraction_pipeline as ep
import transcript_cost_estimator as tce

BASE = "Talk - A Person - 2021-01-01"


def _setup(tmp_path, monkeypatch, response):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(ep, "_load_summary_prompt", lambda _n: "PROMPT")
    monkeypatch.setattr(ep, "_generate_summary_with_claude", lambda *a, **k: response)


def test_n1_short_response_with_no_items_saves_nothing(tmp_path, monkeypatch):
    """A short reply with no scored items ("No emphasis items found.") was saved raw
    and reported as success; the gate then returned ERROR on that file."""
    _setup(tmp_path, monkeypatch, "No emphasis items found in this transcript.")
    logger = MagicMock()
    assert ep.extract_scored_emphasis(f"{BASE} - yaml.md", logger=logger,
                                      transcript_text="[00:00:01] Hello there.\n") is False
    assert not list(tmp_path.rglob("* - emphasis-scored.md"))
    msg = logger.error.call_args.args[0] % logger.error.call_args.args[1:]
    assert "no emphasis items" in msg


def test_n1_short_reply_sets_aside_earlier_file(tmp_path, monkeypatch):
    """Dirty state (P8): an earlier run's emphasis file is not left to be published."""
    _setup(tmp_path, monkeypatch, "None.")
    proj = tmp_path / BASE
    proj.mkdir()
    old = proj / f"{BASE}{config.SUFFIX_EMPHASIS_SCORED}"
    old.write_text("old run", encoding="utf-8")
    assert ep.extract_scored_emphasis(f"{BASE} - yaml.md", logger=MagicMock(),
                                      transcript_text="[00:00:01] Hello.\n") is False
    assert not old.exists()
    assert (proj / f"{old.name}.stale").read_text(encoding="utf-8") == "old run"


def test_n2_themes_validity_uses_the_format_check_parser():
    """Adversarial: a numbered bold list with no Description field (a Rationale list,
    not themes) passed the stage's regex fallback while the format check's parser
    found no themes. The stage now agrees with the format check on every input."""
    import transcript_utils as tu
    list_no_fields = "### Rationale\n\n1. **First reason** matters.\n2. **Second reason** too.\n"
    assert not ep._is_valid_section_content("structural themes", list_no_fields)
    real = "**1. A Title**\n**Description:** Kerr describes the family as a unit.\n"
    assert ep._is_valid_section_content("structural themes", real)
    for text in (list_no_fields, real, "**1. Bare Title**\n", "No themes here.\n"):
        assert ep._is_valid_section_content("interpretive themes", text) == bool(
            tu.parse_bold_numbered_theme_blocks(text)), text


def test_n3_model_defaults_resolve_at_call_time():
    """Function defaults were bound to the model at import, so a caller passing no
    model ignored a model chosen later in the GUI."""
    import abstract_validation
    import formatting_pipeline
    import summary_validation
    import validation_pipeline
    fns = [ep.generate_structured_abstract, ep.extract_scored_emphasis, ep.generate_topics,
           validation_pipeline.validate_headers, validation_pipeline.validate_abstract_coverage,
           abstract_validation.validate_abstract_coverage, summary_validation.validate_summary_coverage,
           formatting_pipeline.format_transcript, ap.generate_abstract]
    for fn in fns:
        assert inspect.signature(fn).parameters["model"].default is None, fn.__name__


def test_n3_default_follows_a_later_model_change(monkeypatch):
    """Dirty state: the model set after import (the GUI's choice) is the one used."""
    import transcript_validate_headers as tvh
    seen = {}
    monkeypatch.setattr(config.settings, "AUX_MODEL", "model-chosen-later")

    def fake_cap(model, *a, **k):
        seen["model"] = model
        raise RuntimeError("stop")
    monkeypatch.setattr(tvh, "cap_max_tokens_for_model", fake_cap)
    v = tvh.HeaderValidator.__new__(tvh.HeaderValidator)
    v.client, v.logger = MagicMock(), logging.getLogger("t")
    v.cached_system_message = [{"text": "x"}]
    try:
        v.validate_batch([{"number": 1, "heading": "X", "content": "text"}])
    except RuntimeError:
        pass
    assert seen.get("model") == "model-chosen-later"


def test_n4_text_before_first_topic_header_is_not_a_topic(caplog):
    text = "## Topics\n\nThese are the main topics.\n\n### Family Systems\nBody.\n\n### Anxiety\nMore.\n"
    with caplog.at_level(logging.INFO):
        names = [t.name for t in ap.parse_topics_from_extraction(text)]
    assert names == ["Family Systems", "Anxiety"]
    assert any("before the first ### header" in r.getMessage() for r in caplog.records)


def test_n5_cost_report_lists_what_it_does_not_estimate(tmp_path):
    transcript = tmp_path / "t.txt"
    transcript.write_text("word " * 2000, encoding="utf-8")
    est = tce.CostEstimator(transcript)
    est.estimate_formatting()
    lines = []
    est._log = lambda msg, *args: lines.append(msg % args if args else msg)
    est.print_report()
    text = "\n".join(lines)
    assert "Not estimated" in text
    for item in config.COST_ESTIMATE_NOT_COVERED:
        assert item in text


def test_n2_topics_validity_uses_the_format_check_parser():
    """N2 review (P5 sibling): topics validity matches the topics format check
    (summary_pipeline.parse_topics_structure), not the three-strategy abstract parser."""
    import summary_pipeline as sp
    headers_only = "### Family Systems\nBody text.\n\n### Anxiety\nMore text.\n"
    assert ap.parse_topics_from_extraction(headers_only)  # the looser parser reads it
    assert not ep._is_valid_section_content("Topics", headers_only)
    for text in (headers_only, "No topics.\n"):
        assert ep._is_valid_section_content("Topics", text) == bool(sp.parse_topics_structure(text))


def test_n2_invalid_section_is_reported():
    """N2 review (P2): a loaded section that fails its check was reused with no
    message. It is now logged as an error naming the section."""
    logger = MagicMock()
    bad = ep._report_invalid_sections(logger, {
        "Structural Themes": "### Rationale\n\n1. **Reason** text.\n",
        "Interpretive Themes": "**1. A Title**\n**Description:** Real theme.\n",
        "Topics": "",
    })
    assert bad == ["Structural Themes"]
    msg = logger.error.call_args.args[0] % logger.error.call_args.args[1:]
    assert "Structural Themes" in msg and "block publish" in msg


def test_n2_legacy_theme_fallback_warns(caplog):
    """N2 review (P19): a legacy fallback that produces themes the format check can't
    read says so."""
    import summary_pipeline as sp
    legacy = "### Family as a Unit\nKerr describes the family as one emotional unit.\n"
    with caplog.at_level(logging.WARNING):
        assert sp.parse_themes(legacy)
        assert ap.parse_themes_from_extraction(legacy)
    msgs = [r.getMessage() for r in caplog.records]
    assert any("summary_pipeline.parse_themes" in m and "legacy" in m for m in msgs)
    assert any("parse_themes_from_extraction" in m and "legacy" in m for m in msgs)
    caplog.clear()
    real = "**1. A Title**\n**Description:** Kerr describes the family as a unit.\n"
    with caplog.at_level(logging.WARNING):
        sp.parse_themes(real)
        ap.parse_themes_from_extraction(real)
    assert not any("legacy" in r.getMessage() for r in caplog.records)


def test_n3_no_function_default_binds_a_model_at_import():
    """N3 review: scan every module so a new import-time model default is caught."""
    import ast
    from pathlib import Path
    root = Path(__file__).resolve().parent.parent
    offenders = []
    for path in root.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in node.args.defaults + node.args.kw_defaults:
                    if d is not None and ast.unparse(d).startswith("config.") \
                            and ast.unparse(d).endswith("_MODEL"):
                        offenders.append(f"{path.name}:{node.name}")
    assert offenders == []


def test_n1_error_shows_the_reply(tmp_path, monkeypatch):
    _setup(tmp_path, monkeypatch, "I cannot find emphasis items.")
    logger = MagicMock()
    ep.extract_scored_emphasis(f"{BASE} - yaml.md", logger=logger,
                               transcript_text="[00:00:01] Hello.\n")
    msg = logger.error.call_args.args[0] % logger.error.call_args.args[1:]
    assert "I cannot find emphasis items." in msg
