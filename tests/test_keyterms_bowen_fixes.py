"""Fixes surfaced by comparing the KCFC webcast run (run-log review, round 2):

  - validate_key_terms_fidelity reported exact=0 / all-fail because it required
    the (synthesized) DEFINITION to appear ~verbatim in the transcript. It now
    grounds on the TERM (alias-aware) and checks the definition for topical
    keyword support only.
  - _has_bowen_source_attribution missed possessive attributions with an
    intervening adjective ("Bowen's basic ideas"), so genuine references were
    dropped. The possessive pattern now allows intervening words.
  - a 0-reference Bowen result now writes a drop-diagnostic instead of vanishing.
"""
from unittest.mock import MagicMock

import config
import extraction_pipeline as ep
from validation_pipeline import validate_key_terms_fidelity


def _make_project(tmp_path, monkeypatch, transcript, key_terms_md):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config.settings, "PROJECTS_DIR", tmp_path)
    base = "Sample Title - Author - 2025-01-01"
    proj = tmp_path / base
    proj.mkdir(parents=True, exist_ok=True)
    (proj / f"{base}{config.SUFFIX_FORMATTED}").write_text(transcript, encoding="utf-8")
    (proj / f"{base}{config.SUFFIX_KEY_TERMS}").write_text(key_terms_md, encoding="utf-8")
    return base, proj


# --- Key-terms validator: ground the term, not the verbatim definition -------

def test_key_terms_grounded_term_with_paraphrased_definition_not_failed(tmp_path, monkeypatch):
    transcript = (
        "The speaker discusses differentiation of self throughout the session. "
        "Emotional cutoff comes up repeatedly as a way families manage anxiety. "
        "Differentiation and cutoff are the central ideas here."
    )
    key_terms = (
        "### Differentiation of Self\n"
        "The capacity to maintain a clear sense of self while staying emotionally "
        "connected to one's family; a central idea in the discussion.\n\n"
        "### Emotional Cutoff\n"
        "A way of managing unresolved family attachment by reducing emotional contact.\n"
    )
    base, proj = _make_project(tmp_path, monkeypatch, transcript, key_terms)
    ok = validate_key_terms_fidelity(proj / f"{base}{config.SUFFIX_FORMATTED}", base, MagicMock())
    report = (proj / f"{base}{config.SUFFIX_KEY_TERMS_VAL}").read_text()
    # Real, transcript-grounded terms with paraphrased definitions must NOT fail.
    assert "FAIL" not in report
    assert ok is True


def test_key_terms_alias_pair_grounds_on_either_part(tmp_path, monkeypatch):
    transcript = "Symbiosis is discussed at length as a form of fusion between mother and child."
    key_terms = (
        "### Symbiosis / Symbiotic Relationship\n"
        "An intense emotional fusion between two people who function as one.\n"
    )
    base, proj = _make_project(tmp_path, monkeypatch, transcript, key_terms)
    validate_key_terms_fidelity(proj / f"{base}{config.SUFFIX_FORMATTED}", base, MagicMock())
    report = (proj / f"{base}{config.SUFFIX_KEY_TERMS_VAL}").read_text()
    # "Symbiosis" is present even though the full slash-joined alias string is not.
    assert "FAIL" not in report


def test_key_terms_hallucinated_term_still_fails(tmp_path, monkeypatch):
    """Adversarial (P7): a term absent from the transcript with an off-topic
    definition must be reported FAIL — the relaxed grounding must not rubber-stamp."""
    transcript = "A talk about families, anxiety, and differentiation of self."
    key_terms = (
        "### Quantum Chromodynamics\n"
        "The physical theory describing the strong interaction between quarks and gluons "
        "via the exchange of gluon fields.\n"
    )
    base, proj = _make_project(tmp_path, monkeypatch, transcript, key_terms)
    validate_key_terms_fidelity(proj / f"{base}{config.SUFFIX_FORMATTED}", base, MagicMock())
    report = (proj / f"{base}{config.SUFFIX_KEY_TERMS_VAL}").read_text()
    assert "FAIL" in report


# --- Bowen attribution detector: possessive with intervening adjective --------

def test_bowen_attribution_detects_possessive_with_adjective():
    f = ep._has_bowen_source_attribution
    assert f("It still amazes me that Bowen's basic ideas were pioneering") is True
    assert f("Bowen's very insightful observation about chronic anxiety") is True
    assert f("all Bowen's key points on differentiation") is True
    assert f("Bowen said the family is an emotional unit") is True


def test_bowen_attribution_does_not_overmatch():
    f = ep._has_bowen_source_attribution
    assert f("she was 90 percent wrapped up in her daughter") is False
    assert f("Bowen's daughter drove home from the hospital") is False
    assert f("in Bowen theory terms this is fusion") is False


# --- Bowen drop-diagnostic: a 0-result is inspectable ------------------------

def test_bowen_reference_count_matches_saved_format():
    """The log's 'Found N references' counter must match the format
    _format_bowen_refs actually writes ('### Concept\\n> "quote"'). The old
    '> **' pattern reported 0 even when references were saved."""
    import re

    refs = [
        ("Pseudo-Self / No Self", "Bowen's basic ideas were pioneering", "01:20:09"),
        ("Multigenerational Transmission", "Bowen described the process across generations", None),
    ]
    content = "## Bowen References\n\n" + ep._format_bowen_refs(refs)
    assert len(re.findall(r"^###\s", content, re.MULTILINE)) == 2   # fixed counter
    assert len(re.findall(r"^\s*>\s*\*\*", content, re.MULTILINE)) == 0  # old (buggy) counter


def test_bowen_drop_diagnostic_written(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    monkeypatch.setattr(config.settings, "PROJECTS_DIR", tmp_path)
    base = "Sample Title - Author - 2025-01-01"
    (tmp_path / base).mkdir(parents=True, exist_ok=True)
    transcript = "It still amazes me that Bowen's basic ideas were pioneering. She was wrapped up in her daughter."
    parsed = [
        ("Pseudo-Self", "It still amazes me that Bowen's basic ideas were pioneering"),
        ("Fusion", "She was wrapped up in her daughter"),
    ]
    log = MagicMock()
    ep._write_bowen_drop_diagnostic(parsed, transcript, f"{base}{config.SUFFIX_YAML}", log)
    dbg = tmp_path / base / f"{base} - bowen-references-debug.md"
    assert dbg.exists()
    content = dbg.read_text()
    assert "Names Bowen?" in content
    assert "Pseudo-Self" in content and "Fusion" in content
    log.warning.assert_called()
