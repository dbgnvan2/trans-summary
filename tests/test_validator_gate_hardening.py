"""Regression tests for the validator-gate hardening (real-run audit, 2026-07-15).

Each test pins a fix that closed a false-PASS or a crash found by auditing the
real "Where Roots Bowen Theory Reside in the Brain" run against its source:

  F1  key-terms: a WRONG on-topic definition on a real term scored EXACT because
      def-support measured overlap with the WHOLE transcript. Now also requires
      LOCAL grounding near the term. (validation_pipeline._best_local_grounding)
  F2  emphasis: only the first 15 words of each quote were matched, so a verbatim
      opening + fabricated tail passed silently. Now probes head AND tail and
      returns a real pass/fail. (validation_pipeline.validate_emphasis_items)
  F4  abstract: a fabricated researcher name ("Luciano Malorni") shipped into the
      published HTML; nothing checked name grounding.
      (abstract_validation.find_ungrounded_names)
  F5  bowen: the same quote listed under two concepts was returned twice.
      (transcript_utils.load_bowen_references)
  loggers: five API call sites logged token usage as "unknown_script".

Fixtures are the REAL artifacts (tests/fixtures/where_roots/), not synthetic
idealized input.
"""
import logging
import shutil
from pathlib import Path

import pytest

import config
import transcript_utils as tu
import validation_pipeline as vp
from abstract_validation import find_ungrounded_names

FX = Path(__file__).parent / "fixtures" / "where_roots"
BASE = "Where Roots Bowen Theory Reside in the Brain - Michael Kerr - 2022-02-18_valid"


def _fmt(proj: Path) -> Path:
    return proj / f"{BASE}{config.SUFFIX_FORMATTED}"


@pytest.fixture
def real_run(monkeypatch):
    """Point config.PROJECTS_DIR at the read-only real-artifact fixtures."""
    monkeypatch.setattr(config, "PROJECTS_DIR", FX)
    return BASE, FX / BASE


@pytest.fixture
def cloned_run(tmp_path, monkeypatch):
    """A writable copy of the real run so a test can tamper one artifact."""
    dst_root = tmp_path / "projects"
    shutil.copytree(FX, dst_root)
    monkeypatch.setattr(config, "PROJECTS_DIR", dst_root)
    return BASE, dst_root / BASE


# --------------------------------------------------------------------------- F2
def test_f2_emphasis_valid_real_run_passes(real_run):
    base, proj = real_run
    ok = vp.validate_emphasis_items(_fmt(proj), _fmt(proj), logging.getLogger("t"))
    assert ok is True


def test_f2_emphasis_fabricated_tail_is_flagged(cloned_run, caplog):
    """Verbatim first-15-words + a fabricated tail must be flagged (was silently
    accepted because only the opening 15 words were matched)."""
    base, proj = cloned_run
    scored = proj / f"{base}{config.SUFFIX_EMPHASIS_SCORED}"
    lines = scored.read_text().splitlines()
    for i, line in enumerate(lines):
        if line.startswith('"Einstein had his theory'):
            head = " ".join(line.strip().strip('"').split()[:15])
            lines[i] = ('"' + head + " and this fabricated tail claims vaccines "
                        "cause autism which Bowen never said.\"")
            break
    else:
        pytest.fail("anchor quote not found in fixture")
    scored.write_text("\n".join(lines))

    with caplog.at_level(logging.ERROR):
        ok = vp.validate_emphasis_items(_fmt(proj), _fmt(proj), logging.getLogger("t"))
    assert ok is False
    assert any("NOT FOUND" in r.message for r in caplog.records)


def test_f2_emphasis_missing_artifact_is_benign_true(tmp_path, monkeypatch):
    """No emphasis artifact at all -> benign, returns True (not a drift failure)."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    proj = tmp_path / BASE
    proj.mkdir(parents=True)
    fmt = _fmt(proj)
    fmt.write_text("## Section 1\nSome transcript body.\n")
    ok = vp.validate_emphasis_items(fmt, fmt, logging.getLogger("t"))
    assert ok is True


# --------------------------------------------------------------------------- F1
def _keyterms_report(proj: Path) -> str:
    return (proj / f"{BASE}{config.SUFFIX_KEY_TERMS_VAL}").read_text()


def test_f1_keyterms_real_run_tiers_pinned(cloned_run):
    """Pin the tier outcome on the real artifact: the 8 grounded terms with
    matching definitions are EXACT; the two composite names FAIL on term
    grounding. This pins the 0.50/0.80/0.90/0.35 + local thresholds.

    Uses a writable clone (not the read-only fixture) because the validator
    writes its report next to the artifacts.
    """
    base, proj = cloned_run
    vp.validate_key_terms_fidelity(_fmt(proj), base, logging.getLogger("t"))
    report = _keyterms_report(proj)
    assert "Def Locality" in report  # new column present
    assert report.count("| EXACT ") == 8
    assert report.count("| FAIL ") == 2
    assert "Homeostasis" in report and "EXACT" in report


def test_f1_keyterms_swapped_definition_not_exact(cloned_run, caplog):
    """Adversarial (P7): a real, grounded term ('Homeostasis') given a WRONG
    on-topic definition (describing the reward/salience network, which lives
    elsewhere in the transcript) must NOT validate EXACT — the local-grounding
    check catches it. Previously scored def-support 0.87 -> EXACT."""
    base, proj = cloned_run
    kt = proj / f"{base}{config.SUFFIX_KEY_TERMS}"
    original = kt.read_text()
    swapped = original.replace(
        "The ability of an organism or individual cell to maintain its stable "
        "internal order even in the face of environmental changes that could "
        "threaten it.",
        "A brain network in the prefrontal cortex that Kent Berridge showed "
        "controls dopamine wanting circuits and the executive salience "
        "determination node.",
    )
    assert swapped != original, "fixture definition text changed; update the test"
    kt.write_text(swapped)

    with caplog.at_level(logging.WARNING):
        vp.validate_key_terms_fidelity(_fmt(proj), base, logging.getLogger("t"))
    report = _keyterms_report(proj)
    homeo_row = next(l for l in report.splitlines() if l.startswith("| Homeostasis"))
    assert "EXACT" not in homeo_row
    assert "WEAK" in homeo_row
    assert any("weakly localized" in r.message for r in caplog.records)


def test_f1_keyterms_unlocatable_multiword_term_not_downgraded(tmp_path, monkeypatch, caplog):
    """Regression (P19 #9, learning-qa Finding 1): a real multi-word term that
    `term_ratio` grounds fuzzily but the exact-sequence locator can't pin (e.g.
    the term is singular but the transcript uses the plural) must NOT be demoted
    to WEAK by the local check, and must NOT emit the misleading 'definition may
    not describe this term' warning."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    proj = tmp_path / BASE
    proj.mkdir(parents=True)
    fmt = _fmt(proj)
    fmt.write_text(
        "## Section 1\nThe emotional systems of families shape behavior across "
        "generations. Chronic anxiety flows through the emotional systems and "
        "influences differentiation and reactivity within the family.\n"
    )
    (proj / f"{BASE}{config.SUFFIX_KEY_TERMS}").write_text(
        "### Emotional System\n"
        "The web of relationships through which anxiety and reactivity flow among "
        "family members across generations, shaping behavior and differentiation.\n"
    )
    with caplog.at_level(logging.WARNING):
        vp.validate_key_terms_fidelity(fmt, BASE, logging.getLogger("t"))
    report = _keyterms_report(proj)
    row = next(l for l in report.splitlines() if l.startswith("| Emotional System"))
    assert "WEAK" not in row, f"legit unlocatable term wrongly downgraded: {row}"
    assert not any("weakly localized" in r.message for r in caplog.records)


def test_f1_best_local_grounding_separates_right_from_wrong(real_run):
    """Unit-level: the localized signal itself separates a matching definition
    from a swapped one on the real transcript."""
    base, proj = real_run
    transcript = tu.strip_yaml_frontmatter(_fmt(proj).read_text())
    right = ("The ability of an organism or individual cell to maintain its "
             "stable internal order in the face of environmental changes.")
    wrong = ("A brain network in the prefrontal cortex controlling dopamine "
             "wanting circuits and the executive salience determination node.")
    r = vp._best_local_grounding(right, "Homeostasis", transcript)
    w = vp._best_local_grounding(wrong, "Homeostasis", transcript)
    assert r is not None and w is not None
    assert r >= config.KEY_TERMS_DEF_LOCAL_MIN
    assert w < config.KEY_TERMS_DEF_LOCAL_MIN
    # absent term -> None (never spuriously grounded)
    assert vp._best_local_grounding(right, "Zzzxqq Nonexistent", transcript) is None


# --------------------------------------------------------------------------- F5
def test_f5_bowen_references_deduped(real_run, caplog):
    """The real bowen file lists the [00:58:09] quote twice under two concepts.
    load_bowen_references must return each quote once and surface the drop."""
    base, proj = real_run
    with caplog.at_level(logging.WARNING):
        refs = tu.load_bowen_references(base)
    quotes = [tu.normalize_text(q, aggressive=True) for _c, q, _t in refs]
    assert len(quotes) == len(set(quotes)), "duplicate quote survived dedup"
    assert len(refs) == 4  # 5 listed, one is a duplicate of another
    assert any("duplicate Bowen reference" in r.message for r in caplog.records)
    # The merged entry keeps BOTH concept labels (no concept association lost).
    concepts = [c for c, _q, _t in refs]
    assert any(";" in c for c in concepts), "duplicate concept label was dropped, not merged"


# --------------------------------------------------------------------------- F4
def test_f4_find_ungrounded_names_flags_fabricated(real_run):
    base, proj = real_run
    abstract = (proj / f"{BASE}{config.SUFFIX_ABSTRACT_GEN}").read_text()
    source = (proj / f"{BASE}.txt").read_text()
    assert find_ungrounded_names(abstract, source) == ["Luciano Malorni"]


def test_f4_find_ungrounded_names_spares_grounded_and_spelling_variants():
    source = ("Frank Wilczek wrote about physics. Kent Berridge studied wanting. "
              "And then I was thinking about Bertoloso's dynamic multi-unity idea.")
    # Bertolaso is the corrected spelling of the source's ASR 'Bertoloso' -> spared;
    # Luciano Malorni is fabricated (no token near the source) -> flagged.
    abstract = ("Frank Wilczek and Kent Berridge are cited. Marta Bertolaso offers "
                "a relational view, unlike Luciano Malorni.")
    flagged = find_ungrounded_names(abstract, source)
    assert "Luciano Malorni" in flagged
    assert "Frank Wilczek" not in flagged
    assert "Kent Berridge" not in flagged
    assert "Marta Bertolaso" not in flagged


# ----------------------------------------------------------------- loggers
class _FakeMsg:
    class _Block:
        text = '{"scores": {}}'
    content = [_Block()]


def test_extract_terms_passes_named_logger(monkeypatch):
    import transcript_extract_terms as tet
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return _FakeMsg()

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(tet.anthropic, "Anthropic", lambda **k: object())
    monkeypatch.setattr(tet, "create_system_message_with_cache", lambda *_a, **_k: "sys")
    monkeypatch.setattr(tet, "call_claude_with_retry", fake_call)
    tet.extract_key_terms_with_claude(
        "some transcript text",
        {"author": "A", "date": "2020-01-01", "title": "T", "filename": "f"},
        "prompt {{insert_transcript_text_here}}",
    )
    assert "logger" in captured and captured["logger"] is not None
    assert captured["logger"].name == "transcript_extract_terms"


def test_audit_voice_passes_named_logger(monkeypatch):
    import transcript_audit_voice as tav
    captured = {}

    def fake_call(**kwargs):
        captured.update(kwargs)
        return _FakeMsg()

    monkeypatch.setattr(tav.anthropic, "Anthropic", lambda **k: object())
    monkeypatch.setattr(tav, "load_prompt", lambda: "{{blog_content}}")
    monkeypatch.setattr(tav, "call_claude_with_retry", fake_call)
    try:
        tav.audit_voice("blog text", "test-key")
    except Exception:
        pass  # JSON parsing of the fake response may fail; we only assert the call kwargs
    assert "logger" in captured and captured["logger"] is not None
    assert captured["logger"].name == "transcript_audit_voice"


# ------------------------------------------------------ edge-case robustness
# Each degenerate input must fail closed or degrade with a clear signal — never
# crash and never silently report success on nothing.

def test_edge_emphasis_empty_transcript_fails_closed(tmp_path, monkeypatch, caplog):
    """Present emphasis quotes + an empty transcript -> every quote is NOT FOUND
    and the validator reports failure (not a silent pass)."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    proj = tmp_path / BASE
    proj.mkdir(parents=True)
    fmt = _fmt(proj)
    fmt.write_text("")  # empty transcript
    (proj / f"{BASE}{config.SUFFIX_EMPHASIS_SCORED}").write_text(
        '[Explicit - A1 - Rank: 90% | 00:01:02] Concept: x\n\n'
        '"A quote that cannot possibly be found in an empty transcript."\n'
    )
    with caplog.at_level(logging.ERROR):
        ok = vp.validate_emphasis_items(fmt, fmt, logging.getLogger("t"))
    assert ok is False
    assert any("NOT FOUND" in r.message for r in caplog.records)


def test_edge_keyterms_malformed_file_fails_closed(tmp_path, monkeypatch):
    """A key-terms file with no parseable terms -> validator returns False and
    writes an explicit 'No key terms' report (fail closed, P2)."""
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    proj = tmp_path / BASE
    proj.mkdir(parents=True)
    fmt = _fmt(proj)
    fmt.write_text("## Section 1\nBody text about differentiation.\n")
    (proj / f"{BASE}{config.SUFFIX_KEY_TERMS}").write_text("garbage with no headers at all\n")
    ok = vp.validate_key_terms_fidelity(fmt, BASE, logging.getLogger("t"))
    assert ok is False
    report = (proj / f"{BASE}{config.SUFFIX_KEY_TERMS_VAL}").read_text()
    assert "No key terms" in report


def test_edge_best_local_grounding_degenerate_inputs():
    # Empty transcript -> term cannot be located -> None (never spuriously grounded).
    assert vp._best_local_grounding("some definition", "Term", "") is None
    # Present term + empty definition -> 0.0 (no keywords to ground), not a crash.
    assert vp._best_local_grounding("", "Term", "a b c term d e") == 0.0


def test_edge_find_ungrounded_names_empty_and_nameless():
    assert find_ungrounded_names("", "some source text") == []
    assert find_ungrounded_names("lowercase words only, no proper names here.", "src") == []


def test_edge_bowen_missing_file_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "PROJECTS_DIR", tmp_path)
    (tmp_path / BASE).mkdir(parents=True)
    assert tu.load_bowen_references(BASE) == []


def test_edge_keyterms_dirty_rerun_is_idempotent(cloned_run):
    """Second run over an existing report must reproduce the same result (P8),
    not accumulate or read stale state."""
    base, proj = cloned_run
    vp.validate_key_terms_fidelity(_fmt(proj), base, logging.getLogger("t"))
    first = (proj / f"{base}{config.SUFFIX_KEY_TERMS_VAL}").read_text()
    vp.validate_key_terms_fidelity(_fmt(proj), base, logging.getLogger("t"))
    second = (proj / f"{base}{config.SUFFIX_KEY_TERMS_VAL}").read_text()
    assert first == second
