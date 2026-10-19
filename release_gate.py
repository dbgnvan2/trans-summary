"""M1 — fail-closed release gate (spec_unattended_robustness_2026-07-15.md).

Turns the advisory validators into a single publish decision. Every check returns
a typed ``Verdict`` (PASS / WARN / FAIL / ERROR); ``run_gate`` aggregates them via
the ``config`` policy table into a ``GateDecision`` (ALLOW / ALLOW_WITH_WARNINGS /
BLOCK). The publish path consults the decision and refuses to write a bundle on
BLOCK (M1.B.2, wired separately).

Key invariants:
  * A check that raises becomes an ERROR verdict — it is never silently skipped
    (M1.C). ERROR blocks by default (a run we couldn't verify must not ship, P1).
  * A FAIL blocks only if its check is in ``config.GATE_BLOCKING_CHECKS``; all
    other FAIL/WARN ship as ALLOW_WITH_WARNINGS. The hard blockers are enumerated
    in ``config.GATE_BLOCKING_CHECKS`` (never re-listed here, so the two cannot
    drift).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

import config


class Status(str, Enum):
    PASS = "PASS"
    WARN = "WARN"
    FAIL = "FAIL"
    ERROR = "ERROR"  # could-not-verify (transient/tooling) — distinct from FAIL


class Decision(str, Enum):
    ALLOW = "ALLOW"
    ALLOW_WITH_WARNINGS = "ALLOW_WITH_WARNINGS"
    BLOCK = "BLOCK"


@dataclass
class Verdict:
    check: str
    status: Status
    detail: str = ""
    items: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"check": self.check, "status": self.status.value,
                "detail": self.detail, "items": self.items}


@dataclass
class GateDecision:
    decision: Decision
    verdicts: list = field(default_factory=list)
    blockers: list = field(default_factory=list)

    @property
    def allowed(self) -> bool:
        return self.decision is not Decision.BLOCK

    def to_dict(self) -> dict:
        return {"decision": self.decision.value,
                "verdicts": [v.to_dict() for v in self.verdicts],
                "blockers": [v.to_dict() for v in self.blockers]}


CheckFn = Callable[[str, object], Verdict]


def _is_blocking(v: Verdict) -> bool:
    # Only a BLOCKING check blocks — for a FAIL *or* an ERROR (can't-verify). An
    # ERROR in an ADVISORY check (a tooling bug in a WARN check) must NOT become a
    # publication hard-stop (F3); it ships as a warning. Missing/unverifiable
    # source still blocks because the blocking entity_grounding check ERRORs on it.
    if v.check not in config.GATE_BLOCKING_CHECKS:
        return False
    if v.status is Status.FAIL:
        return True
    if v.status is Status.ERROR and config.GATE_ERROR_BLOCKS:
        return True
    return False


def decide(verdicts: list) -> GateDecision:
    """Apply the config policy to a set of verdicts."""
    blockers = [v for v in verdicts if _is_blocking(v)]
    if blockers:
        return GateDecision(Decision.BLOCK, verdicts, blockers)
    if any(v.status is not Status.PASS for v in verdicts):
        return GateDecision(Decision.ALLOW_WITH_WARNINGS, verdicts, [])
    return GateDecision(Decision.ALLOW, verdicts, [])


def _safe(name: str, check_fn: CheckFn, base_name: str, logger) -> Verdict:
    """Run a check; convert any exception into an ERROR verdict (M1.C) so a
    crashing check blocks (fail-closed) instead of vanishing."""
    try:
        v = check_fn(base_name, logger)
        return v if v is not None else Verdict(name, Status.ERROR, "check returned None")
    except Exception as e:  # noqa: BLE001 — a check must never take down the gate
        if logger:
            logger.error("Gate check %r raised: %s", name, e, exc_info=True)
        return Verdict(name, Status.ERROR, f"check raised: {type(e).__name__}: {e}")


# --------------------------------------------------------------------------- M4.C
def _load_source_transcript(base_name: str) -> Optional[str]:
    """The source text names are grounded against: the formatted transcript, or
    the YAML transcript (frontmatter stripped) when formatted is absent — the
    same fallback ``generate_webpage`` uses, so the gate can still verify a run
    that only has the YAML artifact."""
    proj = config.PROJECTS_DIR / base_name
    formatted = proj / f"{base_name}{config.SUFFIX_FORMATTED}"
    if formatted.exists():
        return formatted.read_text(encoding="utf-8")
    yaml_path = proj / f"{base_name}{config.SUFFIX_YAML}"
    if yaml_path.exists():
        from transcript_utils import strip_yaml_frontmatter
        return strip_yaml_frontmatter(yaml_path.read_text(encoding="utf-8"))
    return None


def _filename_metadata_values(base_name: str) -> str:
    """The recording's catalogue metadata VALUES (title, presenter, date, year
    from the filename) as a plain space-joined string — NO labels or framing
    words.

    For LEXICAL grounding (entity_grounding). A framing sentence would make words
    like 'recording'/'presenter'/'title' grounded source tokens, letting a
    fabricated name that shares one of them ('Presenter Insurance') pass the hard
    blocker (P7) — so ground on values only. The abstract legitimately states
    these facts (the prompt supplies them) though a speaker rarely utters their
    own name / the year, so they must count as grounded or we FALSE-BLOCK.
    """
    try:
        from transcript_utils import parse_filename_metadata
        meta = parse_filename_metadata(base_name)
        return " ".join(str(meta[k]) for k in ("title", "presenter", "date", "year")
                        if meta.get(k))
    except Exception:  # best-effort; transcript alone still verifies
        return ""


def _source_with_metadata(base_name: str) -> Optional[str]:
    """Transcript plus a LABELED catalogue-metadata framing block — for the LLM
    faithfulness judge, which benefits from the labels and is not fooled by
    framing words (unlike the lexical entity check, which must use
    ``_filename_metadata_values``). See that function for the rationale.
    (P20: re-run the faithfulness calibration on this change.)
    """
    return with_recording_metadata(base_name, _load_source_transcript(base_name))


def with_recording_metadata(base_name: str, transcript: Optional[str]) -> Optional[str]:
    """``transcript`` with the labeled catalogue-metadata block for ``base_name``
    prepended (unchanged when empty). When the transcript has no speaker labels,
    config.UNLABELED_SPEAKERS_NOTE is added too, so the judge knows it cannot tell
    which participant said a passage (SA). Shared by the gate and
    judge_recalibration --prose-real, so calibration judges what the gate judges.

    Spec:  docs/plan_todo_triage_2026-10-11.md#Q5,
           docs/plan_speaker_attribution_2026-10-12.md#SA2
    Tests: tests/test_judge_recalibration_jc.py::test_q5_prose_real_source_has_metadata,
           tests/test_speaker_attribution_sa.py::test_sa2_note_added_only_without_labels
    """
    if not transcript or not transcript.strip():
        return transcript
    from transcript_utils import has_speaker_labels, parse_filename_metadata
    header = []
    try:
        meta = parse_filename_metadata(base_name)
        meta_lines = [f"{k.capitalize()}: {meta[k]}"
                      for k in ("title", "presenter", "date", "year") if meta.get(k)]
        if meta_lines:
            header.append("Recording metadata (from the catalogue entry): "
                          + "; ".join(meta_lines))
    except Exception:  # metadata is best-effort; the transcript alone still verifies
        pass
    if not has_speaker_labels(transcript):
        header.append(config.UNLABELED_SPEAKERS_NOTE)
    return "\n".join(header) + "\n\n" + transcript if header else transcript


def _speaker_note_suffix(source: Optional[str]) -> str:
    """Verdict-detail text recording that the judge was told the transcript has no
    speaker labels, so a PASS that relied on the SA rule is visible (SA review, P2).

    Spec:  docs/plan_speaker_attribution_2026-10-12.md#SA2
    Tests: tests/test_speaker_attribution_sa.py::test_sa2_pass_detail_records_note
    """
    if source and config.UNLABELED_SPEAKERS_NOTE in source:
        return "; source has no speaker labels (judge told)"
    return ""


def check_entity_grounding(base_name: str, logger=None, suffixes=None) -> Verdict:
    """FAIL if any narrative artifact contains a multi-word proper name absent
    from the source transcript (the fabricated-name class — a real run shipped
    'Luciano Malorni' into the published HTML). This is the elected hard blocker.
    Missing source -> ERROR (can't verify -> block), not a silent pass."""
    import abstract_validation

    transcript = _load_source_transcript(base_name)
    if not transcript or not transcript.strip():
        # Missing OR present-but-empty/truncated source is "cannot verify" (F6),
        # not a definitive FAIL asserting the names are fabricated. ERROR -> block.
        return Verdict("entity_grounding", Status.ERROR,
                       "source transcript missing or empty — cannot verify names")
    # Ground against the transcript + the metadata VALUES ONLY (not a framing
    # sentence, whose words would falsely ground names — F1/P7), so the
    # presenter's own name / the year aren't flagged as fabricated.
    values = _filename_metadata_values(base_name)
    source = f"{transcript}\n{values}" if values else transcript
    offending = {}
    excused: list = []  # heading phrases not in the source that do not look like names (HN.1)
    for suffix in (suffixes if suffixes is not None else config.GATE_ENTITY_ARTIFACT_SUFFIXES):
        path = config.PROJECTS_DIR / base_name / f"{base_name}{suffix}"
        if not path.exists():
            continue
        names = abstract_validation.find_ungrounded_names(
            path.read_text(encoding="utf-8"), source, excused=excused
        )
        if names:
            offending[suffix.strip(" -").removesuffix(".md")] = names
    note = _excused_note(excused, logger)
    if offending:
        flat = sorted({n for names in offending.values() for n in names})
        arts = ", ".join(offending.keys())
        # Actionable message naming the artifact + the unverified name(s) — renders
        # as "entity_grounding: check failed in <artifact>: name(s) not in source:
        # <names> — regenerate and try again".
        return Verdict("entity_grounding", Status.FAIL,
                       f"check failed in {arts}: name(s) not in source: "
                       f"{', '.join(flat)} — regenerate and try again{note}",
                       items=[{"artifact": k, "names": v} for k, v in offending.items()])
    return Verdict("entity_grounding", Status.PASS, f"all proper names grounded{note}")


def _excused_note(excused: list, logger=None) -> str:
    """Name the heading phrases the name check did not count as names (HN.1, P2):
    logged and returned as a suffix for the verdict detail ("" when there are none)."""
    if not excused:
        return ""
    if logger:
        logger.info("Name check: %d heading phrase(s) not in the source were not counted "
                    "as names: %s", len(excused), ", ".join(excused))
    return (f"; {len(excused)} heading phrase(s) not in the source and not counted as "
            f"names: {', '.join(excused)}")


# --------------------------------------------------------------------------- source fidelity
def _raw_source_candidates(base_name: str) -> list:
    """Raw transcript files that may be this project's source: the project's own
    raw-source copy (written at format validation) if present, otherwise
    ``<base_name>.txt`` in the project folder and .txt files in SOURCE_DIR /
    PROCESSED_DIR whose cleaned name is ``base_name``
    (covers ``_vN`` / ``_validated`` versions and ``- Processed`` renames)."""
    from transcript_utils import clean_project_name

    proj = config.PROJECTS_DIR / base_name
    copy = proj / f"{base_name}{config.SUFFIX_RAW_SOURCE}"
    if copy.exists():
        return [copy]
    found = []
    in_project = proj / f"{base_name}.txt"
    if in_project.exists():
        found.append(in_project)
    for folder in (getattr(config, "SOURCE_DIR", None), getattr(config, "PROCESSED_DIR", None)):
        if not folder or not Path(folder).is_dir():
            continue
        for f in sorted(Path(folder).glob("*.txt")):
            stem = re.sub(r" - Processed(?: \(\d+\))?$", "", f.stem)
            if clean_project_name(stem) == base_name:
                found.append(f)
    return found


def _match_raw_source(base_name: str, formatted: str, candidates: list) -> tuple:
    """``(path, outcome)`` for the raw source the formatted transcript is judged
    against: the first candidate it matches, else the one with the fewest errors.
    ``source_fidelity`` and ``source_completeness`` both use it, so they name the
    same file."""
    import format_review
    import formatting_pipeline as fp
    import pattern_sets

    best = None
    for path in candidates:
        raw = pattern_sets.effective_raw(base_name, path.read_text(encoding="utf-8-sig"))
        outcome = fp.verify_source_fidelity(
            raw, formatted, approvals=format_review.load_approvals(base_name, raw))
        if outcome["passed"]:
            return path, outcome
        if best is None or len(outcome["errors"]) < len(best[1]["errors"]):
            best = (path, outcome)
    return best


def check_source_fidelity(base_name: str, logger=None) -> Verdict:
    """FAIL unless the formatted transcript — the text every other check treats as
    ground truth — matches its raw source transcript: word-level comparison,
    heading contract, and heading timestamps. Raw source not found -> ERROR
    (cannot verify -> block)."""
    formatted = _load_source_transcript(base_name)
    if not formatted or not formatted.strip():
        return Verdict("source_fidelity", Status.ERROR, "formatted transcript missing or empty")
    # The package ships the YAML transcript when present, but everything here is
    # verified against the formatted transcript: they must be the same text.
    proj = config.PROJECTS_DIR / base_name
    yaml_path = proj / f"{base_name}{config.SUFFIX_YAML}"
    formatted_path = proj / f"{base_name}{config.SUFFIX_FORMATTED}"
    if yaml_path.exists() and formatted_path.exists():
        from transcript_utils import strip_yaml_frontmatter
        yaml_body = strip_yaml_frontmatter(yaml_path.read_text(encoding="utf-8")).strip()
        if yaml_body != formatted.strip():
            return Verdict("source_fidelity", Status.FAIL,
                           "YAML transcript body differs from the formatted transcript "
                           "(stale YAML) — re-run the add-YAML step")
    candidates = _raw_source_candidates(base_name)
    if not candidates:
        return Verdict("source_fidelity", Status.ERROR,
                       "raw source transcript not found (no project raw-source copy and no "
                       "matching file in source/processed) — cannot verify the formatted "
                       "transcript; re-run format validation")
    path, outcome = _match_raw_source(base_name, formatted, candidates)
    if outcome["passed"]:
        return Verdict("source_fidelity", Status.PASS,
                       f"formatted transcript matches raw source {path.name} "
                       f"({outcome['comparison']['mismatch_count']} differing words)")
    return Verdict("source_fidelity", Status.FAIL,
                   f"formatted transcript does not match raw source {path.name}: "
                   f"{outcome['errors'][0]} — re-run formatting",
                   items=outcome["errors"][:20])


def check_source_completeness(base_name: str, logger=None) -> Verdict:
    """WARN when the transcription tool's header says the raw transcript is incomplete.

    Reads the raw source ``source_fidelity`` judges the formatted transcript against.
    With several candidate files and no formatted transcript to choose between them,
    it reads them all and warns if any is incomplete. Advisory (not in
    ``config.GATE_BLOCKING_CHECKS``): the outputs are incomplete, not wrong, so the
    verdict records the missing time ranges and publication goes on. No raw source
    -> ERROR, which does not block an advisory check; ``source_fidelity`` blocks on it.

    Purpose: Surface a partly transcribed talk in the gate report (P2).
    Spec:    docs/plan_incomplete_transcript_2026-10-19.md#IT3
    Tests:   tests/test_source_completeness_it.py::test_it3a_gate_warns_with_missing_ranges,
             ::test_it3d_incomplete_source_allows_with_warnings,
             ::test_it3a_reads_the_source_fidelity_matched
    """
    import source_completeness as sc

    candidates = _raw_source_candidates(base_name)
    if not candidates:
        return Verdict("source_completeness", Status.ERROR,
                       "raw source transcript not found — completeness not checked")
    formatted = _load_source_transcript(base_name)
    if len(candidates) > 1 and formatted and formatted.strip():
        candidates = [_match_raw_source(base_name, formatted, candidates)[0]]
    incomplete, headed = [], 0
    for path in candidates:
        c = sc.read_file(path)
        headed += c.has_header
        if c.incomplete:
            incomplete.append((path, c))
    if incomplete:
        path, c = incomplete[0]
        detail = sc.incomplete_message(c, path.name)
        if len(incomplete) > 1:
            detail += f" ({len(incomplete)} source files report this.)"
        return Verdict("source_completeness", Status.WARN, detail,
                       items=[sc.gate_item(c, p.name) for p, c in incomplete])
    if headed:
        return Verdict("source_completeness", Status.PASS,
                       f"no known incomplete-transcript warning in the transcription "
                       f"tool's header ({headed} source file(s))")
    return Verdict("source_completeness", Status.PASS,
                   "no transcription-tool header; completeness not stated")


# --------------------------------------------------------------------------- M4.A
def check_verbatim_quotes(base_name: str, logger=None) -> Verdict:
    """FAIL if any Bowen/emphasis quote is not verbatim in the source. Two tests:
    the fuzzy head/tail match (>= EMPHASIS_QUOTE_PARTIAL_RATIO) AND whole-quote
    word coverage (>= QUOTE_MIN_WORD_COVERAGE). The coverage test catches an
    altered or negated middle, which the head/tail probes cannot see. Filler words
    and stutters are ignored on both sides (author decision 2a, 2026-10-09). A
    scored-emphasis file with content that parses to no items is ERROR."""
    import transcript_utils as tu
    import validation_pipeline as vp

    transcript = _load_source_transcript(base_name)
    if transcript is None:
        return Verdict("verbatim_quotes", Status.ERROR, "source transcript missing")
    problems = []
    emphasis = tu.load_emphasis_items(base_name)
    if not emphasis:
        scored = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_EMPHASIS_SCORED}"
        body = tu.strip_yaml_frontmatter(scored.read_text(encoding="utf-8")) if scored.exists() else ""
        if body.strip():
            # Content that parses to nothing is format drift, not "all verbatim" (P19).
            return Verdict("verbatim_quotes", Status.ERROR,
                           "emphasis artifact has content but parsed to no items")
    items = ([("bowen", c, q) for c, q, _ts in tu.load_bowen_references(base_name)]
             + [("emphasis", lab, q) for lab, q, _ts in emphasis])
    for kind, label, quote in items:
        ok, ends, coverage = vp.quote_is_verbatim_for_gate(quote, transcript)
        if not ok:
            problems.append({"type": kind, "label": label, "quote": quote[:60],
                             "match": round(ends, 3), "word_coverage": round(coverage, 3)})
    if problems:
        return Verdict("verbatim_quotes", Status.FAIL,
                       f"{len(problems)} quote(s) not verbatim in the source — regenerate",
                       items=problems)
    return Verdict("verbatim_quotes", Status.PASS, f"all {len(items)} quotes verbatim")


def _lens_titles(base_name: str) -> list:
    """The project's own lens titles (generated content labels, like theme names),
    so a blog headline taken from one ("The Hidden Debt Inside Every Family") is
    not reported as an invented name or an unsupported claim (RF.N)."""
    path = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_LENSES}"
    if not path.exists():
        return []
    from transcript_utils import extract_lens_titles
    return extract_lens_titles(path.read_text(encoding="utf-8"))


def _is_lens_title_fragment(claim: str, titles: list) -> bool:
    norm = " ".join(claim.lower().split()).strip(" .:-")
    return bool(norm) and any(norm in " ".join(t.lower().split()) for t in titles)


_BLOG_GROUNDING_CACHE: dict = {}


def _judge_blog_grounding_cached(fjudge, claims: list, source: str, client, logger) -> dict:
    """{claim: label} from the theme-grounding judge, cached in memory and on disk
    like the other judges (sweep: one verdict per blog per source, not a new paid
    and possibly different verdict per gate run). Errors raise and are not cached."""
    import hashlib

    c = hashlib.sha256("\n".join(claims).encode("utf-8")).hexdigest()
    s = hashlib.sha256(source.encode("utf-8")).hexdigest()
    mem_key = (c, s)
    if mem_key in _BLOG_GROUNDING_CACHE:
        return _BLOG_GROUNDING_CACHE[mem_key]
    disk_key = (f"blog-grounding:{c}:{s}:{config.THEME_JUDGE_MODEL}:"
                f"{_judge_logic_version(fjudge._THEME_JUDGE_INSTRUCTIONS)}")
    disk = _load_judge_disk_cache().get(disk_key)
    # D2: only an all-grounded result is kept on disk, so a false flag is re-judged
    # on the next run instead of replayed (an older stored flag is ignored).
    if (isinstance(disk, dict) and isinstance(disk.get("labels"), dict)
            and all(v == fjudge.GROUNDED for v in disk["labels"].values())):
        _BLOG_GROUNDING_CACHE[mem_key] = disk["labels"]
        return disk["labels"]
    verdicts = fjudge.judge_themes([{"name": x, "description": ""} for x in claims],
                                   source, client, logger=logger)
    labels = {v.claim: v.label for v in verdicts}
    _BLOG_GROUNDING_CACHE[mem_key] = labels
    _persist_judge_outcome(disk_key, all(v == fjudge.GROUNDED for v in labels.values()),
                           {"status": "grounding", "labels": labels}, logger)
    return labels


def blog_ungrounded_claims(base_name: str, logger=None, minor: Optional[list] = None) -> tuple:
    """Two-stage blog check (RF.N.1). Returns ``(status, ungrounded, detail)``:
    "pass", "warn" (ungrounded claims/names listed), "missing" (no blog), or
    "error" (could not verify; ``ungrounded`` then holds only the name hits, which
    need no judge — never unassessed claims, so they are not fed back as if wrong).

    1. Names: proper names not in the source, metadata or lens titles.
    2. Claims the entailment judge rejects as UNSUPPORTED (lens-title fragments
       dropped) are re-judged by the theme GROUNDING judge, which accepts a fair
       interpretation of real content but rejects fabricated specifics. A claim is
       ungrounded only if both reject it ("N1 wins"). A CONTRADICTED claim is never
       overridden. With THEME_JUDGE_ENABLED off there is no second stage.

    Claims the severity step judged NOT QUITE RIGHT are not ungrounded: they are
    logged by name and, when ``minor`` is a list, appended to it (JS2.e).

    Purpose: Judge the interpretive blog as interpretation, not as a fact sheet.
    Spec:    docs/plan_run_fixes_2026-10-09.md#RF.N.1
    Tests:   tests/test_run_fixes_rf.py::test_rfn1_interpretive_claim_accepted_by_grounding_judge
    """
    import abstract_validation

    path = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_BLOG}"
    if not path.exists():
        return "missing", [], "no blog present"
    transcript = _load_source_transcript(base_name)
    if not transcript or not transcript.strip():
        return "error", [], "source transcript missing — blog not verified"
    text = path.read_text(encoding="utf-8")
    titles = _lens_titles(base_name)
    values = _filename_metadata_values(base_name)
    name_source = "\n".join(x for x in (transcript, values, *titles) if x)
    excused: list = []
    names = [f"the name '{n}' does not appear in the source"
             for n in abstract_validation.find_ungrounded_names(text, name_source,
                                                                excused=excused)]
    excused_note = _excused_note(excused, logger)
    if not getattr(config, "FAITHFULNESS_JUDGE_ENABLED", False):
        return "error", names, ("claims not verified (faithfulness judge disabled)"
                                + (f"; {len(names)} name(s) not in source" if names else "")
                                + excused_note)
    faith = check_faithfulness(base_name, logger, suffixes=[config.SUFFIX_BLOG])
    if faith.status is Status.ERROR:
        return "error", names, f"claims not verified: {faith.detail}{excused_note}"
    contradicted = [c for item in (faith.items or []) for c in item.get("contradicted", [])]
    rejected = [c for item in (faith.items or []) for c in item.get("unfaithful", [])
                if c not in contradicted and not _is_lens_title_fragment(c, titles)]
    accepted_as_interpretation = 0
    ungrounded = names + contradicted
    if rejected:
        if not getattr(config, "THEME_JUDGE_ENABLED", False):
            ungrounded += rejected
        else:
            try:
                import faithfulness_judge as fjudge
                from transcript_utils import get_anthropic_client, resolve_anthropic_key
                key = resolve_anthropic_key()
                if not key:
                    return "error", names, f"claims not verified: no Anthropic API key{excused_note}"
                labels = _judge_blog_grounding_cached(
                    fjudge, rejected, transcript, get_anthropic_client(key), logger)
                for claim in rejected:
                    if labels.get(claim) == fjudge.GROUNDED:
                        accepted_as_interpretation += 1
                    else:
                        ungrounded.append(claim)
            except Exception as e:  # noqa: BLE001 — cannot verify: report, do not pass
                if logger:
                    logger.warning("Blog grounding judge failed: %s", e)
                return "error", names, (f"claims not verified: grounding judge "
                                        f"{type(e).__name__}{excused_note}")
    # JS2.e: claims the severity step judged NOT QUITE RIGHT are named, not dropped.
    nqr = log_not_quite_right(faith, "blog", logger)
    if minor is not None:
        minor.extend(nqr)
    note = (f"; {accepted_as_interpretation} claim(s) accepted as interpretation"
            if accepted_as_interpretation else "") + (
            f"; {len(nqr)} claim(s) not quite right (a warning, not a fault)"
            if nqr else "") + excused_note
    if ungrounded:
        return "warn", ungrounded, f"{len(ungrounded)} blog claim(s) not grounded in the source{note}"
    if nqr:
        return "pass", [], f"no wrong blog claims{note}"
    return "pass", [], f"all blog claims entailed or grounded{note}"


def check_blog_faithfulness(base_name: str, logger=None) -> Verdict:
    """ADVISORY: the blog's claims (RF.N). Ungrounded claims or no blog -> WARN;
    could not verify -> ERROR (reported as UNVERIFIED). Never a publication blocker:
    not in GATE_BLOCKING_CHECKS (author decision 2026-10-10)."""
    minor: list = []
    status, ungrounded, detail = blog_ungrounded_claims(base_name, logger, minor=minor)
    if status == "pass" and minor:
        # JS2.e: NOT QUITE RIGHT claims only -> WARN naming them, as check_faithfulness.
        return Verdict("blog_faithfulness", Status.WARN, detail,
                       items=[{"artifact": "blog", "not_quite_right": minor}])
    if status == "pass":
        return Verdict("blog_faithfulness", Status.PASS, detail)
    if status == "error":
        return Verdict("blog_faithfulness", Status.ERROR, detail, items=ungrounded)
    return Verdict("blog_faithfulness", Status.WARN, detail, items=ungrounded)


# --------------------------------------------------------------- R15 validator gates
def check_topics_grounding(base_name: str, logger=None) -> Verdict:
    """FAIL if any topic grades FAIL against the transcript (the
    validate_topics_lightweight test, run live). No topics artifact -> PASS
    (nothing published); a non-empty artifact that parses to nothing -> ERROR.

    Purpose: Gate publication on the topics validator (plan R15).
    Spec:    docs/plan_review_fixes_2026-10-04.md#R15
    Tests:   tests/test_release_gate.py::test_r15c_topics_fail_blocks
    """
    import validation_pipeline as vp

    topics_file = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_TOPICS}"
    if not topics_file.exists():
        return Verdict("topics_grounding", Status.PASS, "no topics artifact")
    transcript = _load_source_transcript(base_name)
    if transcript is None:
        return Verdict("topics_grounding", Status.ERROR, "source transcript missing")
    topics = vp._load_topics_for_validation(base_name, transcript)
    if not topics:
        if topics_file.read_text(encoding="utf-8").strip():
            return Verdict("topics_grounding", Status.ERROR,
                           "topics artifact has content but parsed to no topics")
        return Verdict("topics_grounding", Status.PASS, "topics artifact empty")
    rows = vp._grade_topics(topics, transcript, vp._extract_transcript_sections(transcript))
    failed = [{"topic": r[0], "title": round(r[1], 2), "description": round(r[2], 2)}
              for r in rows if r[4] == "FAIL"]
    if failed:
        return Verdict("topics_grounding", Status.FAIL,
                       f"{len(failed)} of {len(rows)} topic(s) not grounded in the transcript",
                       items=failed)
    return Verdict("topics_grounding", Status.PASS, f"all {len(rows)} topic(s) grounded")


def check_summary_coverage(base_name: str, logger=None) -> Verdict:
    """Summary coverage verdict (required topic / closing items, decision 3a).
    Uses the stored verdict when its key matches the current inputs; otherwise
    runs the validation now (which stores a fresh verdict). No summary -> PASS.

    Purpose: Gate publication on summary coverage (plan R15).
    Spec:    docs/plan_review_fixes_2026-10-04.md#R15
    Tests:   tests/test_release_gate.py::test_r15c_summary_stale_verdict_revalidated
    """
    import validation_pipeline as vp

    if vp.summary_coverage_key(base_name) is None:
        return Verdict("summary_coverage", Status.PASS, "no structured summary")
    verdict = vp.stored_summary_coverage_verdict(base_name)
    if verdict is None:
        vp.validate_summary_coverage(base_name, logger=logger)
        verdict = vp.stored_summary_coverage_verdict(base_name)
    if verdict is None:
        return Verdict("summary_coverage", Status.ERROR,
                       "summary coverage could not be verified — see the summary "
                       "validation report and retry")
    status = {"PASS": Status.PASS, "FAIL": Status.FAIL}.get(verdict.get("status"), Status.ERROR)
    detail = verdict.get("detail") or "summary coverage"
    if status is Status.FAIL:
        detail = f"{detail} — see the summary validation report"
    return Verdict("summary_coverage", status, detail)


# --------------------------------------------------------------------------- M4.B
def _timestamp_blocks(transcript: str) -> list:
    """[(seconds, text)] for each [HH:MM:SS] marker and the text until the next."""
    parts = re.split(r"\[(\d{2}):(\d{2}):(\d{2})\]", transcript)
    blocks = []
    # parts = [pre, h,m,s, text, h,m,s, text, ...]
    for i in range(1, len(parts), 4):
        h, m, s = int(parts[i]), int(parts[i + 1]), int(parts[i + 2])
        blocks.append((h * 3600 + m * 60 + s, parts[i + 3]))
    return blocks


def check_timestamp_citations(base_name: str, logger=None) -> Verdict:
    """WARN when an emphasis quote's stored timestamp does not point near where
    the quote actually occurs (F6: several were tagged to the wrong block)."""
    import transcript_utils as tu

    transcript = _load_source_transcript(base_name)
    if transcript is None:
        return Verdict("timestamp_citations", Status.ERROR, "source transcript missing")
    blocks = _timestamp_blocks(transcript)
    if not blocks:
        return Verdict("timestamp_citations", Status.PASS, "no timestamps in source")
    secs = [b[0] for b in blocks]
    problems = []
    for label, quote, ts in tu.load_emphasis_items(base_name):
        if not ts:
            continue
        try:
            h, m, s = (int(x) for x in ts.split(":"))
        except ValueError:
            continue
        want = h * 3600 + m * 60 + s
        # find the block covering `want`
        idx = max((i for i, sec in enumerate(secs) if sec <= want), default=0)
        head = tu.normalize_text(" ".join(quote.split()[:8]), aggressive=True)
        # accept the claimed block or its immediate neighbours (marker granularity)
        window = " ".join(blocks[j][1] for j in range(max(0, idx - 1), min(len(blocks), idx + 2)))
        if head and head not in tu.normalize_text(window, aggressive=True):
            problems.append({"label": label, "timestamp": ts, "quote": quote[:60]})
    if problems:
        return Verdict("timestamp_citations", Status.WARN,
                       f"{len(problems)} emphasis timestamp(s) don't match the quote's location",
                       items=problems)
    return Verdict("timestamp_citations", Status.PASS, "timestamps consistent")


# --------------------------------------------------------------------------- M4.D
def check_entity_consistency(base_name: str, logger=None) -> Verdict:
    """WARN when the same entity is spelled differently across artifacts
    (F7: Bertoloso / Bertolaso / Luciano Malorni for one unnamed person)."""
    from difflib import SequenceMatcher

    names_by_artifact = {}
    for suffix in config.GATE_CONSISTENCY_ARTIFACT_SUFFIXES:
        path = config.PROJECTS_DIR / base_name / f"{base_name}{suffix}"
        if not path.exists():
            continue
        # [ \t]+ (not \s+) between name words: \s+ spans newlines, joining the last
        # word of one line with the first of the next into a bogus "name" and
        # corrupting near-duplicate detection (review L1; matches the entity_grounding
        # choice).
        found = set(re.findall(r"\b[A-Z][a-z]+(?:[ \t]+[A-Z][a-z]+)+\b",
                                path.read_text(encoding="utf-8")))
        if found:
            names_by_artifact[suffix.strip(" -")] = found
    all_names = sorted({n for s in names_by_artifact.values() for n in s})
    clashes = []
    for i, a in enumerate(all_names):
        for b in all_names[i + 1:]:
            if a != b and SequenceMatcher(None, a.lower(), b.lower()).ratio() >= 0.8:
                clashes.append([a, b])
    if clashes:
        return Verdict("entity_consistency", Status.WARN,
                       f"{len(clashes)} near-duplicate name spelling(s) across artifacts",
                       items=clashes)
    return Verdict("entity_consistency", Status.PASS, "names consistent across artifacts")


# --------------------------------------------------------------------------- M3.C
# Structured boundaries validated on read at the gate. Extended one artifact at a
# time as each is wired behind the codec (M3 staging). Each entry is
# (schema-key, path-suffix, extra parse args).
_CONTRACT_ARTIFACTS: list = [
    ("bowen", config.SUFFIX_BOWEN, ()),
    ("emphasis", config.SUFFIX_EMPHASIS_SCORED, ()),
    ("key_terms", config.SUFFIX_KEY_TERMS, ()),
    ("topics", config.SUFFIX_TOPICS, ()),
    # themes: the codec migration shim now reads BOTH the `**N.**` and legacy
    # `### N.` real formats (verified 0 false-reject across every structural +
    # interpretive artifact on the drive), so both are safe as hard blockers.
    ("themes", config.SUFFIX_STRUCTURAL_THEMES, ("structural",)),
    ("themes", config.SUFFIX_INTERPRETIVE_THEMES, ("interpretive",)),
]


def check_artifact_contracts(base_name: str, logger=None) -> Verdict:
    """ERROR if any structured artifact on disk fails its schema contract — a
    corrupted / old-format / drifted artifact is a loud, publish-blocking failure,
    never a silent zero (P19, U4). A legitimately-empty artifact (bare header, no
    body) validates as an empty object and passes."""
    import artifact_contracts as ac

    proj = config.PROJECTS_DIR / base_name
    problems = []
    for key, suffix, args in _CONTRACT_ARTIFACTS:
        path = proj / f"{base_name}{suffix}"
        if not path.exists():
            continue
        try:
            ac.codec(key).parse_markdown(path.read_text(encoding="utf-8"), *args)
        except ac.SchemaError as e:
            problems.append({"artifact": key, "error": str(e)})
    if problems:
        return Verdict("artifact_contracts", Status.ERROR,
                       f"{len(problems)} structured artifact(s) violate their schema "
                       f"contract (P19 drift)", items=problems)
    return Verdict("artifact_contracts", Status.PASS,
                   "all structured artifacts conform to their schema")


# --------------------------------------------------------------------------- M2
# Process-lifetime memo of judge verdicts keyed on (artifact-sha, source-sha). The
# publish path calls the gate once per entry point (webpage/pdf/package), so an
# un-memoized LLM judge would re-run ~N calls per publish; caching by content dedupes
# them. A transient ERROR is NOT cached (P1) so a retry can still succeed.
_FAITHFULNESS_CACHE: dict = {}
_JUDGE_DISK_CACHE_MAX = 2000  # bound growth; keep the most-recent entries


def _judge_disk_cache_path():
    return config.LOGS_DIR / "gate_judge_cache.json"


def _load_judge_disk_cache() -> dict:
    """Load the cross-process judge memo; corrupt / non-dict content -> empty (P8)."""
    import json
    try:
        data = json.loads(_judge_disk_cache_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _store_judge_disk_cache(disk_key: str, verdict_dict: dict, logger=None):
    import json
    import os
    try:
        cache = _load_judge_disk_cache()
        cache[disk_key] = verdict_dict
        if len(cache) > _JUDGE_DISK_CACHE_MAX:  # keep the most-recent inserts
            cache = dict(list(cache.items())[-_JUDGE_DISK_CACHE_MAX:])
        path = _judge_disk_cache_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
        tmp.write_text(json.dumps(cache), encoding="utf-8")
        os.replace(tmp, path)
    except OSError as e:  # caching is best-effort — never break the gate on it
        if logger:
            logger.warning("could not persist judge cache: %s", e)


_FLAGGED_MARKER = {"status": "flagged"}


def _is_flagged(entry) -> bool:
    """A disk entry that is not a clean PASS: the D2 "flagged" marker, a FAIL written
    by older code, or blog-grounding labels that are not all grounded (re-check 1)."""
    if entry is None or not isinstance(entry, dict):
        return False
    if entry.get("status") == "PASS":
        return False
    if entry.get("status") == "grounding" and isinstance(entry.get("labels"), dict):
        return not all(v == "grounded" for v in entry["labels"].values())
    return True


def _key_without_version(disk_key: str) -> str:
    """The disk key minus its trailing judge-logic-version segment: content, kind and
    model. Every judge key ends in ``:<_judge_logic_version>``."""
    return disk_key.rsplit(":", 1)[0]


def _flag_identity(disk_key: str) -> str:
    """What a D2 flag is tied to: the key without its logic version AND without its
    source sha. Every judge key ends ``…:<artifact-sha>:<source-sha>:<model>:<version>``.
    A change to the judge's source text (the SA unlabeled-speakers note, a metadata
    edit) must not clear a flag on an unchanged artifact (SA review, P6). Ignoring the
    source can only keep a flag, never drop one."""
    parts = disk_key.split(":")
    if len(parts) < 4:
        return _key_without_version(disk_key)
    return ":".join(parts[:-3] + [parts[-2]])


def _flagged_any_version(disk_key: str) -> bool:
    """True when this artifact was judged FAIL under ANY logic version or source text
    (a prompt edit, JUDGE_LOGIC_VERSION bump or source-text change re-keys the cache;
    the flag must survive it — Q6 and SA reviews). Scans the bounded cache
    (<= _JUDGE_DISK_CACHE_MAX entries).

    Spec:  docs/plan_todo_triage_2026-10-11.md#D2,
           docs/plan_speaker_attribution_2026-10-12.md#SA6
    Tests: tests/test_judge_cache_pass_only_d2.py::test_d2_flag_survives_a_logic_version_bump,
           tests/test_speaker_attribution_sa.py::test_sa6_flag_survives_source_note
    """
    ident = _flag_identity(disk_key)
    return any(_flag_identity(k) == ident and _is_flagged(v)
               for k, v in _load_judge_disk_cache().items())


def _persist_judge_outcome(disk_key: str, passed: bool, record: dict, logger=None):
    """D2: keep only a clean PASS on disk. A FAIL is not stored as a verdict (it is
    re-judged next run) but leaves a "flagged" marker; once a key is flagged (marker,
    or an old FAIL entry), a later PASS is not stored either, so every run re-judges
    it. Without this, a judge with no temperature could fail a real fabrication, pass
    it on a re-run, and that one PASS would be replayed for good (sweep finding 1).

    Spec:  docs/plan_todo_triage_2026-10-11.md#D2
    Tests: tests/test_judge_cache_pass_only_d2.py::test_d2_pass_after_a_fail_is_not_persisted
    """
    if not passed:
        _store_judge_disk_cache(disk_key, dict(_FLAGGED_MARKER), logger)
    elif not _flagged_any_version(disk_key):
        _store_judge_disk_cache(disk_key, record, logger)


def _judge_flag_aware(disk_key: str, fjudge, judge, logger=None):
    """``judge()`` once; for a key judged FAIL before, a PASS counts only when a second
    judgement also passes, so re-running the gate until one PASS comes up does not
    publish a flagged artifact (D2 re-check 2). Returns the deciding result.

    Spec:  docs/plan_todo_triage_2026-10-11.md#D2
    Tests: tests/test_judge_cache_pass_only_d2.py::test_d2_flagged_needs_two_passes_in_a_row
    """
    result = judge()
    if result.status == fjudge.PASS and _flagged_any_version(disk_key):
        second = judge()
        if second.status != fjudge.PASS:
            if logger:
                logger.warning("Judged FAIL before; this PASS was not confirmed by a "
                               "second judgement (%s).", second.status)
            return second
        result.detail = f"{result.detail}; confirmed by a second judgement (judged FAIL before)"
    return result


def _judge_input_functions() -> list:
    """Functions whose code decides what the judges see (claims, theme text).
    Hashed into the judge cache key so editing any of them invalidates cached
    verdicts without a manual JUDGE_LOGIC_VERSION bump (review F4, plan R9)."""
    import abstract_validation as av
    import faithfulness_judge as fjudge
    import transcript_utils as tu

    return [
        fjudge.extract_claims, fjudge._split_sentences, fjudge._is_claim,
        fjudge._name_shaped_bold_labels, fjudge._parse_judge_response,
        fjudge.with_theme_evidence, fjudge.build_theme_judge_prompt,
        fjudge._stem, fjudge.judge_claims_chunked, fjudge.judge_artifact,
        fjudge.judge_claims_confirmed,
        fjudge._should_chunk, fjudge.judge_claims, fjudge.build_judge_prompt,
        fjudge._cached_judge_content,
        fjudge._clean_claim_line, fjudge._mark_question_answers, fjudge._claim_body,
        fjudge.instructions_for,
        # JS: the severity step decides which confirmed flags fail.
        fjudge.classify_severity, fjudge.judge_severity, fjudge.build_severity_prompt,
        fjudge._parse_severity_response, fjudge._severity_objects,
        fjudge._evidence_in_source, fjudge._folded_words,
        av._strip_scaffolding, av._strip_front_matter, av._strip_fenced_block,
        av.scaffolding_name_spans, av.find_ungrounded_names,
        # HN: which heading runs count as names (re-emitted to the judge as claims).
        av.looks_like_name, av._english_word, av._base_forms, av._word_list,
        tu.parse_theme_blocks_with_evidence, tu._theme_blocks,
        tu._extract_theme_description, tu._extract_theme_evidence,
        tu._theme_body, tu._is_theme_block,
        tu._theme_own_text_report, tu._theme_own_text, tu._accepted_theme_blocks,
        tu._candidate_theme_blocks,  # TD: what part of a block is the theme
        # SA: what the judge is told about speaker labels.
        tu.has_speaker_labels, with_recording_metadata,
    ]


def _judge_input_patterns() -> list:
    """Module-level regex patterns read by ``_judge_input_functions``."""
    import abstract_validation as av
    import faithfulness_judge as fjudge
    import transcript_utils as tu

    patterns = [av._NAME_SPAN, av._INLINE_BOLD_LABEL, av._YAML_LINE,
                fjudge._SENTENCE_SPLIT, fjudge._NAME_SHAPE, fjudge._SCAFFOLDING_LABEL_RE,
                tu._BOLD_THEME_RE, tu._H3_THEME_RE, tu._LIST_THEME_RE, tu._THEME_FIELD_RE,
                tu._LINE_START_LABEL_RE, fjudge._QA_MARK, fjudge._QA_INSERT_AT,
                fjudge._SEVERITY_OBJECT_RE]
    # SA: the label threshold and the note text change what the judge is told.
    patterns += [str(config.SPEAKER_LABEL_MIN_TURNS), config.UNLABELED_SPEAKERS_NOTE]
    # HN: the name check's vocabularies decide which heading runs are re-emitted.
    patterns += [config.NAME_CHECK_WORD_PREFIXES, config.NAME_CHECK_MONTHS,
                 config.NAME_CHECK_WEEKDAYS, str(config.NAME_CHECK_GIVEN_NAME_MIN_LEN),
                 _name_list_digest()]
    return [repr(getattr(p, "pattern", p)) for p in patterns]


def _name_list_digest() -> str:
    """SHA-256 of the name check's three word lists (HN), so editing a list changes
    the judge cache key. A missing file hashes as its path and "missing"."""
    import hashlib
    h = hashlib.sha256()
    for path in (config.NAME_CHECK_ENGLISH_WORDS_PATH, config.NAME_CHECK_FIRST_NAMES_PATH,
                 config.NAME_CHECK_SURNAMES_PATH):
        try:
            h.update(Path(path).read_bytes())
        except OSError:
            h.update(f"{path}: missing".encode("utf-8"))
    return h.hexdigest()


def _severity_prompt_text(fjudge) -> str:
    """The severity prompt for the cache key; a missing file keys as "missing" (the
    step then keeps every flag WRONG, so nothing laxer can be cached)."""
    try:
        return fjudge.severity_instructions()
    except OSError:
        return "severity prompt missing"


def _judge_logic_version(instructions: str) -> str:
    """Version tag folded into the disk-cache key. Captures the judge's PROMPT text, the
    claim-extraction config, AND config.JUDGE_LOGIC_VERSION (bumped on any judge CODE
    change) — so a stricter judge can NEVER serve a laxer cached PASS on the armed gate
    (H2 finding 1, a fail-open). Over-invalidation just triggers a safe re-judge."""
    import hashlib
    import inspect
    import faithfulness_judge as fjudge
    material = "|".join([
        config.JUDGE_LOGIC_VERSION,
        fjudge._SPEAKER_RULE,  # SA: added for unlabeled transcripts only
        # The effort judges run at changes their verdicts (MV.6 sweep, P20/P6).
        str(config.JUDGE_EFFORT),
        instructions,
        repr(sorted(config.FAITHFULNESS_STRIP_LINE_LABEL_PREFIXES)),
        repr(sorted(config.FAITHFULNESS_SKIP_LINE_LABELS)),
        str(config.FAITHFULNESS_MIN_CLAIM_CHARS),
        # The chunked-routing strategy changes WHICH source context each claim is
        # judged against, so its thresholds must invalidate a cached PASS too — else a
        # future tune serves a stale verdict (H2 fail-open) unless the developer
        # remembers to bump JUDGE_LOGIC_VERSION by hand (P6/P4).
        str(config.FAITHFULNESS_CONFIRM_MODE),  # CF: confirmed vs first-pass verdicts
        # JS3.a: the severity step decides which flags fail, so its mode, policy text
        # and evidence threshold re-key the cache (its code is in _judge_input_functions).
        str(config.FAITHFULNESS_SEVERITY_MODE),
        _severity_prompt_text(fjudge),
        str(config.FAITHFULNESS_SEVERITY_EVIDENCE_MIN_WORDS),
        str(config.FAITHFULNESS_SEVERITY_EVIDENCE_PART_MIN_WORDS),
        str(config.FAITHFULNESS_SEVERITY_EVIDENCE_MIN_SHARED_WORDS),
        # Which claims fail (FaithfulnessResult.unfaithful) and which severity types
        # are valid are code and a module constant, not config (learning-qa F5).
        inspect.getsource(fjudge.FaithfulnessResult),
        repr(sorted((k, sorted(v)) for k, v in fjudge._SEVERITY_TYPES.items())),
        str(config.FAITHFULNESS_JUDGE_MIN_CHUNK_SOURCE_WORDS),
        str(config.FAITHFULNESS_JUDGE_ROUTE_MIN_OVERLAP),
        str(config.VALIDATION_CHUNK_SIZE),
        str(config.VALIDATION_CHUNK_OVERLAP),
        # The routing ALGORITHM itself (e.g. the earlier margin-vs-second heuristic vs
        # the current structural "all source-anchored words in one window") changes the
        # source context a claim is judged against but is NOT a config constant, so a
        # code-only change would otherwise escape the manual JUDGE_LOGIC_VERSION bump
        # and serve a stale verdict. Hash the routing function AND its behaviour-
        # determining helpers (word windowing, the significance filter, the stopword
        # set) so routing-code changes invalidate by construction (P6/P4). NOTE: these
        # read the on-disk source, so after editing faithfulness_judge.py you MUST
        # restart any long-lived process (Tk GUI) before judging, or the key can drift
        # ahead of the still-in-memory code (P16).
        inspect.getsource(fjudge.route_claims_to_chunks),
        inspect.getsource(fjudge.chunk_source),
        inspect.getsource(fjudge._significant_words),
        repr(sorted(fjudge._STOP_WORDS)),
        # The code that decides WHAT is judged (review F4, plan R9): claim
        # extraction, the scaffolding strip it shares with the entity check, the
        # theme parser/evidence fields, and their vocabularies.
        *(inspect.getsource(fn) for fn in _judge_input_functions()),
        # ...and the module-level patterns / thresholds those functions read,
        # which getsource does not capture (sweep finding).
        *_judge_input_patterns(),
        str(config.ABSTRACT_NAME_TOKEN_MIN_LEN),
        str(config.ABSTRACT_NAME_FUZZY_MIN),
        repr(fjudge._ROUTING_SUFFIXES),
        repr(sorted(config.FAITHFULNESS_HEADING_MONTH_WORDS)),
        repr(sorted(config.FAITHFULNESS_GENERIC_HEADINGS)),
        repr(sorted(config.BOWEN_CONCEPT_LABELS)),
        repr(sorted(config.SCAFFOLDING_HEADING_PHRASES)),
        repr(sorted(config.THEME_JUDGE_META_LABELS)),
        repr(sorted(config.THEME_EVIDENCE_LABELS)),
        repr(sorted(config.THEME_DOCUMENT_LEVEL_LABELS)),  # TD: decides the theme's own text
    ])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]


def _disk_cached_verdict(disk_key: str, fjudge):
    """Reconstruct a persisted PASS verdict from disk, or None. A FAIL or ERROR is
    never replayed (D2: a FAIL stored by an older version is re-judged).

    Spec:  docs/plan_todo_triage_2026-10-11.md#D2
    Tests: tests/test_judge_cache_pass_only_d2.py::test_d2_fail_left_on_disk_is_ignored
    """
    disk = _load_judge_disk_cache().get(disk_key)
    if isinstance(disk, dict) and disk.get("status") == fjudge.PASS:
        return fjudge.FaithfulnessResult(
            status=disk["status"],
            detail=disk.get("detail", ""),
            # JS3.b: a PASS with NOT QUITE RIGHT claims is replayed with them.
            claims=[fjudge.ClaimVerdict(**c) for c in
                    disk.get("unfaithful", []) + disk.get("not_quite_right", [])],
            overturned=disk.get("overturned", []),
            judged=int(disk.get("claims_judged") or 0),
        )
    return None


def _judge_cached(fjudge, artifact_text: str, source: str, client, logger):
    import hashlib

    a = hashlib.sha256(artifact_text.encode("utf-8")).hexdigest()
    s = hashlib.sha256(source.encode("utf-8")).hexdigest()
    mem_key = (a, s)
    cached = _FAITHFULNESS_CACHE.get(mem_key)
    if cached is not None:
        return cached

    # Cross-process memo (review H2): the CLI orchestrator runs each publish step
    # (webpage/pdf/package) as a SEPARATE subprocess, so the in-memory cache above is
    # cold each time and the armed judge re-runs ~N calls per publish. A disk memo keyed
    # on (artifact-sha, source-sha, judge-model, judge-LOGIC-version) lets a later
    # subprocess reuse the verdict; the logic version invalidates it on any prompt /
    # extraction-config / judge-code change (H2 finding 1). Only PASS is stored: ERROR
    # is transient (P1) and a FAIL is re-judged on the next run, so a false flag is
    # not replayed until the artifact changes (D2).
    disk_key = f"{a}:{s}:{config.FAITHFULNESS_JUDGE_MODEL}:{_judge_logic_version(fjudge._JUDGE_INSTRUCTIONS)}"
    result = _disk_cached_verdict(disk_key, fjudge)
    if result is not None:
        _FAITHFULNESS_CACHE[mem_key] = result
        return result

    result = _judge_flag_aware(
        disk_key, fjudge,
        lambda: fjudge.judge_artifact(artifact_text, source, client, logger=logger), logger)
    failing = list(getattr(result, "unfaithful", []))
    if (result.status == fjudge.FAIL and failing
            and all(getattr(c, "severity_undecided", False) for c in failing)):
        # Every failing claim is WRONG only because a severity vote failed: transient
        # (P1). Not cached in memory and no flagged marker, so the next run asks again.
        if logger:
            logger.warning("Faithfulness FAIL rests only on severity votes that failed; "
                           "not cached, re-judged next run.")
        return result
    if result.status != fjudge.ERROR:  # never cache a transient failure (P1)
        _FAITHFULNESS_CACHE[mem_key] = result
        _persist_judge_outcome(disk_key, result.status == fjudge.PASS, result.to_dict(), logger)
    return result


def _wrong_records(result) -> list:
    """The failing claims of a judge result, as report items: the claim, its first-pass
    label, the severity type (W1-W4) and evidence, why it stayed WRONG when the step
    could not decide, and whether it was undecided (learning-qa F2)."""
    return [{"claim": c.claim, "label": getattr(c, "label", ""),
             "type": getattr(c, "severity_type", ""), "evidence": getattr(c, "evidence", ""),
             "note": getattr(c, "severity_note", ""),
             "undecided": getattr(c, "severity_undecided", False)}
            for c in getattr(result, "unfaithful", [])]


def log_not_quite_right(faith, what: str, logger) -> list:
    """Name, in one warning, the claims of a faithfulness verdict that the severity
    step judged NOT QUITE RIGHT. They pass and are not revised (decision JS0.d), but
    they are listed in full, never dropped (P2). Returns the records.

    Spec:  docs/plan_judge_severity_2026-10-19.md#JS2.c
    Tests: tests/test_judge_severity_js.py::test_js2c_precheck_ignores_nqr,
           tests/test_judge_severity_js.py::test_js2e_blog_nqr_named_and_warned
    """
    minor = [c for item in (faith.items or []) if isinstance(item, dict)
             for c in item.get("not_quite_right", [])]
    if minor and logger:
        logger.warning("%d claim(s) in the %s are not quite right (a warning, not a fault; "
                       "kept as written): %s", len(minor), what,
                       "; ".join(f"[{c.get('type') or '?'}] {c.get('claim', '')}"
                                 for c in minor))
    return minor


def _not_quite_right_records(result) -> list:
    """The NOT QUITE RIGHT claims of a judge result, as report items: the claim, its
    type (N1-N3), the source words it rests on, and the first-pass label (JS2.b)."""
    return [{"claim": c.claim, "type": c.severity_type, "evidence": c.evidence,
             "first_label": c.label} for c in getattr(result, "not_quite_right", [])]


def _score_record(art: str, result) -> dict:
    """The % score of one judged artifact: claims judged, claims flagged (a confirmed
    flag, WRONG or NOT QUITE RIGHT) and the share not flagged. ``score_pct`` is None
    when no claim count is known.

    Spec:  docs/plan_warn_only_2026-10-19.md#WO3
    Tests: tests/test_faithfulness_warn_only_wo.py::test_wo3_score_in_detail_and_items
    """
    judged = int(getattr(result, "judged", 0) or 0)
    flagged = len(getattr(result, "unfaithful", [])) + len(getattr(result, "not_quite_right", []))
    known = judged > 0 and judged >= flagged
    supported = judged - flagged if known else None
    return {"artifact": art, "claims_judged": judged, "flagged": flagged,
            "supported": supported,
            "score_pct": round(100 * supported / judged) if known else None}


def _score_text(scores: list) -> str:
    """"summary 90% (27 of 30 claims supported); abstract 100% (8 of 8 ...)"."""
    parts = []
    for s in scores:
        name = s["artifact"].removesuffix(".md")
        if s["score_pct"] is not None:
            parts.append(f"{name} {s['score_pct']}% ({s['supported']} of "
                         f"{s['claims_judged']} claims supported)")
        elif s["flagged"]:
            parts.append(f"{name}: {s['flagged']} claim(s) flagged, claim count not known")
        else:
            parts.append(f"{name}: no claims to check")
    return "; ".join(parts)


def flagged_claim_lines(v: Verdict) -> list:
    """One line per flagged claim in a faithfulness verdict, for the run log: the
    claims are listed as warnings, not only counted (WO5, P2).

    Spec:  docs/plan_warn_only_2026-10-19.md#WO5
    Tests: tests/test_faithfulness_warn_only_wo.py::test_wo5_gui_lists_flagged_claims_on_allow
    """
    lines = []
    for item in (v.items or []):
        if not isinstance(item, dict):
            continue
        art = str(item.get("artifact", "")).removesuffix(".md")
        for c in item.get("wrong", []) or []:
            lines.append(f"[{art}] wrong: {c.get('claim', '')}")
        for c in item.get("not_quite_right", []) or []:
            lines.append(f"[{art}] not quite right: {c.get('claim', '')}")
    return lines


def verdict_warning_lines(decision: "GateDecision") -> list:
    """The run-log lines for every verdict that is not a PASS and does not block: a
    WARN, or a FAIL/ERROR from a check that does not block (e.g. faithfulness since
    2026-10-19), each followed by its flagged claims. An ERROR is tagged UNVERIFIED
    (review M8). ``run_gate`` logs these lines for every caller.

    Spec:  docs/plan_warn_only_2026-10-19.md#WO5
    Tests: tests/test_faithfulness_warn_only_wo.py::test_wo5_gui_lists_flagged_claims_on_allow
    """
    lines = []
    for v in decision.verdicts:
        if v.status is Status.PASS or v in decision.blockers:
            continue
        tag = {Status.WARN: "WARN", Status.ERROR: "UNVERIFIED, not blocking"}.get(
            v.status, f"{v.status.value}, not blocking")
        lines.append(f"[{tag}] {v.check}: {v.detail}")
        lines.extend(f"  - {line}" for line in flagged_claim_lines(v))
    return lines


def check_faithfulness(base_name: str, logger=None, suffixes: Optional[list] = None) -> Verdict:
    """Claim-level semantic faithfulness of the NARRATIVE artifacts (M2). Each
    artifact's claims are judged against the source, and the detail gives each
    artifact's score: the % of its claims not flagged. A flagged claim (WRONG or NOT
    QUITE RIGHT) is a WARN, listed in full, and publication goes on: the user decided
    on 2026-10-19 that faithfulness warns and never blocks (``faithfulness`` is not in
    ``config.GATE_BLOCKING_CHECKS``). No source / no API key / judge error -> ERROR,
    which is reported as "could not verify" and does not block either. Runs when
    `config.FAITHFULNESS_JUDGE_ENABLED` is True; when it is False it is a PASS no-op.
    The unit suite forces it off (root conftest).

    ``suffixes`` limits which artifacts are judged (default: all of
    ``config.FAITHFULNESS_ARTIFACT_SUFFIXES``). The abstract regeneration precheck
    passes the abstract suffix ONLY, so a sibling artifact's unfaithful claim isn't
    blamed on the abstract (review M2); the publish gate always judges the full set.
    The flagged claims stay in ``items`` under "unfaithful", which generation reads to
    revise them.

    Spec:  docs/plan_warn_only_2026-10-19.md#WO2, #WO3
    Tests: tests/test_faithfulness_warn_only_wo.py::test_wo2_wrong_claim_warns_and_gate_allows,
           tests/test_faithfulness_warn_only_wo.py::test_wo3_score_in_detail_and_items
    """
    if not getattr(config, "FAITHFULNESS_JUDGE_ENABLED", False):
        return Verdict("faithfulness", Status.PASS,
                       "faithfulness judge disabled (FAITHFULNESS_JUDGE_ENABLED is False)")
    import faithfulness_judge as fjudge
    from transcript_utils import resolve_anthropic_key

    # Source includes the filename metadata (title/presenter/date/year) so a
    # legitimate metadata-derived fact ("In this 2021 webinar…") isn't judged as
    # fabricated. Shared with entity_grounding via _source_with_metadata.
    transcript = _source_with_metadata(base_name)
    if not transcript or not transcript.strip():
        return Verdict("faithfulness", Status.ERROR,
                       "source transcript missing or empty — cannot verify faithfulness")
    api_key = resolve_anthropic_key()
    if not api_key:
        return Verdict("faithfulness", Status.ERROR,
                       "no Anthropic API key (env or shared keys file) — cannot run "
                       "faithfulness judge")
    from transcript_utils import get_anthropic_client

    client = get_anthropic_client(api_key)
    proj = config.PROJECTS_DIR / base_name
    fails, errors, overturned, minor, scores = [], [], [], [], []
    judged = 0
    for suffix in (suffixes if suffixes is not None else config.FAITHFULNESS_ARTIFACT_SUFFIXES):
        path = proj / f"{base_name}{suffix}"
        if not path.exists():
            continue
        judged += 1
        result = _judge_cached(
            fjudge, path.read_text(encoding="utf-8"), transcript, client, logger)
        art = suffix.strip(" -")
        if getattr(result, "overturned", None):
            overturned.append({"artifact": art, "overturned": result.overturned})
        nqr = _not_quite_right_records(result)
        if result.status == fjudge.ERROR:
            errors.append({"artifact": art, "detail": result.detail})
            continue
        scores.append(_score_record(art, result))
        if result.status == fjudge.FAIL:
            fails.append({"artifact": art, "detail": result.detail,
                          "unfaithful": [c.claim for c in result.unfaithful],
                          "contradicted": [c.claim for c in result.unfaithful
                                           if getattr(c, "label", None) == fjudge.CONTRADICTED],
                          "wrong": _wrong_records(result),
                          "not_quite_right": nqr,
                          "overturned": getattr(result, "overturned", [])})
        elif nqr:
            minor.append({"artifact": art, "not_quite_right": nqr})
    if judged == 0:
        # "nothing to judge" is NOT "all faithful": a run with no narrative artifact
        # present cannot silently clear the faithfulness gate (P7 pass-on-empty).
        return Verdict("faithfulness", Status.ERROR,
                       "no narrative artifact present to verify faithfulness")
    # CF.2: first-pass flags that were not confirmed are recorded, not dropped (P2).
    # A flagged artifact's record already holds its own overturned flags.
    flagged_arts = {f["artifact"] for f in fails}
    extra_over = [o for o in overturned if o["artifact"] not in flagged_arts]
    n_over = sum(len(o["overturned"]) for o in overturned)
    n_wrong = sum(len(f["unfaithful"]) for f in fails)
    n_minor = (sum(len(f["not_quite_right"]) for f in fails)
               + sum(len(m["not_quite_right"]) for m in minor))
    kinds = " and ".join(k for k in (f"{n_wrong} wrong" if n_wrong else "",
                                     f"{n_minor} not quite right" if n_minor else "") if k)
    tail = ((f"; {n_over} first-pass flag(s) not confirmed" if n_over else "")
            + _speaker_note_suffix(transcript))
    score_txt = _score_text(scores)
    items = fails + errors + minor + extra_over + scores
    if errors:
        return Verdict("faithfulness", Status.ERROR,
                       f"{len(errors)} of {judged} artifact(s) could not be verified"
                       + (f"; {kinds} claim(s) flagged" if kinds else "")
                       + (f"; {score_txt}" if score_txt else "") + tail,
                       items=items)
    if kinds:
        arts = ", ".join(sorted({f["artifact"].removesuffix(".md") for f in fails}
                                | {m["artifact"].removesuffix(".md") for m in minor}))
        return Verdict("faithfulness", Status.WARN,
                       f"{kinds} claim(s) flagged in {arts} (a warning; publication goes "
                       f"on): {score_txt}{tail}",
                       items=items)
    return Verdict("faithfulness", Status.PASS,
                   f"all narrative claims entailed by source: {score_txt}{tail}",
                   items=extra_over + scores)


# --------------------------------------------------------------------------- topics / key terms
_TOPIC_META_LINE = re.compile(r"^[\W_]*~?\d+\s*%\s+of\s+transcript", re.IGNORECASE)


def topics_terms_as_claims(markdown: str) -> str:
    """Turn a topics or key-terms artifact (``### Title`` + prose) into one claim
    per line, each prefixed with its title so the judge knows what it is about
    ("Catatonia: A psychiatric state described ..."). Coverage/section metadata
    lines ("(~20% of transcript; Sections 1-2)") are dropped — they are not
    claims about the source."""
    import faithfulness_judge as fjudge

    lines_out: list = []
    title = None
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line or line == "---":
            continue
        if line.startswith("###"):
            title = line.lstrip("#").strip()
            continue
        if line.startswith("#") or _TOPIC_META_LINE.match(line):
            continue
        text = line.replace("**", "").replace("__", "").strip("*_ ").strip()
        if not text:
            continue
        for sentence in fjudge._split_sentences(text):
            sentence = sentence.strip()
            if sentence:
                lines_out.append(f"{title}: {sentence}" if title else sentence)
    return "\n".join(lines_out)


def check_topic_term_faithfulness(base_name: str, logger=None) -> Verdict:
    """Claim-level faithfulness of topic descriptions and key-term definitions.
    Both are model-written prose that the keyword-overlap validators cannot
    check (fabricated statements score like true ones). Same judge, source and
    fail-closed rules as ``check_faithfulness``; no topics/key-terms artifact at
    all -> ERROR (nothing verified is not "all faithful")."""
    if not getattr(config, "FAITHFULNESS_JUDGE_ENABLED", False):
        return Verdict("topic_term_faithfulness", Status.PASS,
                       "faithfulness judge disabled (FAITHFULNESS_JUDGE_ENABLED is False)")
    import faithfulness_judge as fjudge
    from transcript_utils import resolve_anthropic_key

    transcript = _source_with_metadata(base_name)
    if not transcript or not transcript.strip():
        return Verdict("topic_term_faithfulness", Status.ERROR,
                       "source transcript missing or empty — cannot verify")
    api_key = resolve_anthropic_key()
    if not api_key:
        return Verdict("topic_term_faithfulness", Status.ERROR,
                       "no Anthropic API key — cannot run faithfulness judge (fail closed)")
    from transcript_utils import get_anthropic_client

    client = get_anthropic_client(api_key)
    proj = config.PROJECTS_DIR / base_name
    fails, errors, overturned, minor = [], [], [], []
    judged = 0
    for suffix in config.TOPIC_TERM_FAITHFULNESS_SUFFIXES:
        path = proj / f"{base_name}{suffix}"
        if not path.exists():
            continue
        claims_text = topics_terms_as_claims(path.read_text(encoding="utf-8"))
        art = suffix.strip(" -").removesuffix(".md")
        if not claims_text.strip():
            errors.append({"artifact": art, "detail": "no claims parsed from artifact"})
            continue
        judged += 1
        result = _judge_cached(fjudge, claims_text, transcript, client, logger)
        if getattr(result, "overturned", None):
            overturned.append({"artifact": art, "overturned": result.overturned})
        nqr = _not_quite_right_records(result)
        if result.status == fjudge.FAIL:
            fails.append({"artifact": art, "detail": result.detail,
                          "unfaithful": [c.claim for c in result.unfaithful],
                          "wrong": _wrong_records(result),
                          "not_quite_right": nqr,
                          "overturned": getattr(result, "overturned", [])})
        elif result.status == fjudge.ERROR:
            errors.append({"artifact": art, "detail": result.detail})
        elif nqr:
            minor.append({"artifact": art, "not_quite_right": nqr})
    if fails:
        arts = ", ".join(f["artifact"] for f in fails)
        failed = {f["artifact"] for f in fails}
        return Verdict("topic_term_faithfulness", Status.FAIL,
                       f"check failed in {arts} — regenerate and try again",
                       items=fails + errors + minor
                       + [o for o in overturned if o["artifact"] not in failed])
    if errors or judged == 0:
        return Verdict("topic_term_faithfulness", Status.ERROR,
                       "topics/key-terms could not be verified" if errors
                       else "no topics or key-terms artifact present to verify",
                       items=errors + minor + overturned)
    # CF.2: first-pass flags that were not confirmed are recorded, not dropped (P2).
    n_over = sum(len(o["overturned"]) for o in overturned)
    if minor:
        # JS2.e: only NOT QUITE RIGHT claims -> WARN, listed (this check is advisory).
        n_minor = sum(len(m["not_quite_right"]) for m in minor)
        return Verdict("topic_term_faithfulness", Status.WARN,
                       f"no wrong claims; {n_minor} topic/key-term claim(s) not quite right "
                       f"({judged} artifact(s) judged)"
                       + (f"; {n_over} first-pass flag(s) not confirmed" if n_over else "")
                       + _speaker_note_suffix(transcript),
                       items=minor + overturned)
    return Verdict("topic_term_faithfulness", Status.PASS,
                   f"all topic/key-term claims entailed by source ({judged} artifact(s) judged)"
                   + (f"; {n_over} first-pass flag(s) not confirmed" if n_over else "")
                   + _speaker_note_suffix(transcript),
                   items=overturned)


# --------------------------------------------------------------------------- theme grounding
# suffix -> theme kind for the M3 codec.
_THEME_KIND = {
    config.SUFFIX_STRUCTURAL_THEMES: "structural",
    config.SUFFIX_INTERPRETIVE_THEMES: "interpretive",
}
_THEME_JUDGE_CACHE: dict = {}


def _judge_theme_cached(fjudge, text: str, source: str, kind: str, client, logger):
    import hashlib

    a = hashlib.sha256(text.encode("utf-8")).hexdigest()
    s = hashlib.sha256(source.encode("utf-8")).hexdigest()
    mem_key = (a, s, kind)
    cached = _THEME_JUDGE_CACHE.get(mem_key)
    if cached is not None:
        return cached
    # Same cross-process disk memo as the faithfulness judge (H2 finding 2 / P5): the
    # theme judge is the OTHER armed hard blocker and pays the identical per-subprocess
    # cold-memo cost. Keyed on the theme prompt + kind + logic version; only PASS is
    # stored on disk (D2).
    disk_key = f"theme:{kind}:{a}:{s}:{config.THEME_JUDGE_MODEL}:{_judge_logic_version(fjudge._THEME_JUDGE_INSTRUCTIONS)}"
    result = _disk_cached_verdict(disk_key, fjudge)
    if result is not None:
        _THEME_JUDGE_CACHE[mem_key] = result
        return result
    result = _judge_flag_aware(
        disk_key, fjudge,
        lambda: fjudge.judge_themes_artifact(text, source, kind, client, logger=logger), logger)
    if result.status != fjudge.ERROR:  # never cache a transient failure (P1)
        _THEME_JUDGE_CACHE[mem_key] = result
        _persist_judge_outcome(disk_key, result.status == fjudge.PASS, result.to_dict(), logger)
    return result


def check_theme_grounding(base_name: str, logger=None) -> Verdict:
    """Interpretive GROUNDING of the theme artifacts (structural + interpretive): a
    theme must be a reasonable interpretation of content actually in the source; a
    theme built on fabricated subject matter -> FAIL. This is the theme counterpart
    of the faithfulness judge (which is source-ENTAILMENT and wrong for interpretive
    content). Fails closed (no source / no key / judge error -> ERROR). Runs when
    `config.THEME_JUDGE_ENABLED` is True (armed 2026-07-15 after its gold-set
    calibration; config.py holds the current value and calibration record). When the
    flag is False it is a PASS no-op; the unit suite forces it off (root conftest)."""
    if not getattr(config, "THEME_JUDGE_ENABLED", False):
        return Verdict("theme_grounding", Status.PASS,
                       "theme grounding judge disabled (THEME_JUDGE_ENABLED is False)")
    import faithfulness_judge as fjudge
    import transcript_utils as tu
    from transcript_utils import resolve_anthropic_key

    transcript = _load_source_transcript(base_name)
    if not transcript or not transcript.strip():
        return Verdict("theme_grounding", Status.ERROR,
                       "source transcript missing or empty — cannot verify themes")
    api_key = resolve_anthropic_key()
    if not api_key:
        return Verdict("theme_grounding", Status.ERROR,
                       "no Anthropic API key — cannot run theme judge (fail closed)")
    from transcript_utils import get_anthropic_client

    client = get_anthropic_client(api_key)
    proj = config.PROJECTS_DIR / base_name
    fails, errors, unclassified = [], [], []
    judged = 0
    for suffix, kind in _THEME_KIND.items():
        path = proj / f"{base_name}{suffix}"
        if not path.exists():
            continue
        judged += 1
        text = path.read_text(encoding="utf-8")
        result = _judge_theme_cached(fjudge, text, transcript, kind, client, logger)
        art = suffix.strip(" -")
        # TE: fields that are neither evidence nor known meta are sent to the judge as
        # evidence (fail closed); say so once per file, with the theme names (P2).
        # TD: what was left out of a theme (the model's closing notes) — once per file.
        trimmed = tu.trimmed_theme_notes(text)
        if trimmed and logger:
            logger.info("%s: left out of the published and judged themes: %s", art,
                        "; ".join(f"{note} ({name})" for name, note in trimmed))
        odd = tu.unclassified_theme_fields(text)
        if odd:
            unclassified.append({"artifact": art, "unclassified_fields":
                                 [f"{name}: {label}" for name, label in odd]})
            if logger:
                logger.warning("%s: %d theme field(s) are neither evidence nor a known meta "
                               "label and were sent to the theme judge as evidence: %s. "
                               "Classify them in config (THEME_EVIDENCE_LABELS / "
                               "THEME_JUDGE_META_LABELS).", art, len(odd),
                               "; ".join(f"{label} ({name})" for name, label in odd))
        if result.status == fjudge.FAIL:
            fails.append({"artifact": art, "detail": result.detail,
                          "ungrounded": [c.claim for c in result.unfaithful]})
        elif result.status == fjudge.ERROR:
            errors.append({"artifact": art, "detail": result.detail})
    if judged == 0:
        return Verdict("theme_grounding", Status.PASS, "no theme artifacts present")
    if fails:
        return Verdict("theme_grounding", Status.FAIL,
                       f"{len(fails)} of {judged} theme artifact(s) contain ungrounded "
                       f"theme(s)", items=fails + errors + unclassified)
    if errors:
        return Verdict("theme_grounding", Status.ERROR,
                       f"{len(errors)} of {judged} theme artifact(s) could not be verified",
                       items=errors + unclassified)
    return Verdict("theme_grounding", Status.PASS,
                   f"all themes grounded ({judged} artifact(s) judged)"
                   + (f"; {sum(len(u['unclassified_fields']) for u in unclassified)} "
                      "unclassified theme field(s) sent as evidence" if unclassified else ""),
                   items=unclassified)


def check_required_artifacts(base_name: str, logger=None) -> Verdict:
    """WARN (named) if a required artifact is missing or empty — publishing an
    incomplete bundle unattended is a silent drop (P2/M5.B). Advisory by policy;
    a missing SOURCE additionally hard-blocks via entity_grounding's ERROR."""
    proj = config.PROJECTS_DIR / base_name
    missing = []
    for suffix in config.GATE_REQUIRED_ARTIFACT_SUFFIXES:
        f = proj / f"{base_name}{suffix}"
        try:
            present = f.exists() and f.read_text(encoding="utf-8", errors="ignore").strip()
        except OSError:
            present = False
        if not present:
            missing.append(suffix.strip(" -") or suffix.strip())
    if missing:
        return Verdict("required_artifacts", Status.WARN,
                       f"missing or empty required artifact(s): {missing}", items=missing)
    return Verdict("required_artifacts", Status.PASS, "all required artifacts present")


def check_consistency(base_name: str, logger=None) -> Verdict:
    """Cross-artifact consistency. Flags the error class per-artifact
    validators miss because every artifact is checked against the transcript but
    never against each other, nor against the transcript's domain density — e.g.
    empty Bowen references on a talk that recounts Bowen the person. Deterministic,
    no API call.

    Hard blocker for its FAIL findings (in ``config.GATE_BLOCKING_CHECKS``): an
    empty bowen-references.md while the transcript or abstract recounts Bowen the
    person >= BOWEN_PERSON_MIN_MARKERS times is a dropped recollection — a lost
    signal, not a cosmetic gap. Its heuristic WARNs (orphan key-term, topic
    coverage, the fuzzy specific-recollection drop) remain advisory."""
    from transcript_validate_consistency import resolve_transcript, run as consistency_run

    proj = config.PROJECTS_DIR / base_name
    # A missing/unresolvable source is "cannot verify" (ERROR -> block), not a
    # definitive inconsistency — mirror check_entity_grounding so the blocker's
    # FAIL set is exactly "definitive inconsistency" and a source-resolution
    # failure never blocks as a misclassified FAIL.
    transcript_path = resolve_transcript(proj)
    if transcript_path is None:
        return Verdict("consistency", Status.ERROR,
                       "source transcript missing — cannot verify consistency")
    if not transcript_path.read_text(encoding="utf-8", errors="replace").strip():
        return Verdict("consistency", Status.ERROR,
                       "source transcript empty — cannot verify consistency")
    fails, warns, _info = consistency_run(proj)
    if fails:
        return Verdict("consistency", Status.FAIL,
                       f"{len(fails)} cross-artifact inconsistency(ies): {fails[0]}",
                       items=fails)
    if warns:
        return Verdict("consistency", Status.WARN,
                       f"{len(warns)} cross-artifact warning(s)", items=warns)
    return Verdict("consistency", Status.PASS, "artifacts mutually consistent")


# Ordered registry. Which checks are hard blockers is config policy
# (config.GATE_BLOCKING_CHECKS — not enumerated here so this comment can't drift); the
# rest are advisory verdicts recorded in the manifest.
DEFAULT_CHECKS: list = [
    ("source_fidelity", check_source_fidelity),
    ("source_completeness", check_source_completeness),
    ("entity_grounding", check_entity_grounding),
    ("artifact_contracts", check_artifact_contracts),
    ("faithfulness", check_faithfulness),
    ("blog_faithfulness", check_blog_faithfulness),
    ("topic_term_faithfulness", check_topic_term_faithfulness),
    ("theme_grounding", check_theme_grounding),
    ("required_artifacts", check_required_artifacts),
    ("verbatim_quotes", check_verbatim_quotes),
    ("topics_grounding", check_topics_grounding),
    ("summary_coverage", check_summary_coverage),
    ("timestamp_citations", check_timestamp_citations),
    ("entity_consistency", check_entity_consistency),
    ("consistency", check_consistency),
]


def run_gate(base_name: str, logger=None, checks: Optional[list] = None) -> GateDecision:
    """Run all checks and return the aggregate publish decision."""
    checks = DEFAULT_CHECKS if checks is None else checks
    verdicts = [_safe(name, fn, base_name, logger) for name, fn in checks]
    decision = decide(verdicts)
    if logger:
        n_err = sum(1 for v in verdicts if v.status == Status.ERROR)
        n_warn = sum(1 for v in verdicts if v.status == Status.WARN)
        logger.info(
            "Release gate for %s: %s (%d verdict(s), %d blocker(s), %d error(s), %d warn(s))",
            base_name, decision.decision.value, len(verdicts), len(decision.blockers),
            n_err, n_warn)
        for v in decision.blockers:
            logger.error("  BLOCKER [%s] %s: %s", v.status.value, v.check, v.detail)
        # Every verdict that is not a PASS and does not block, with its flagged claims:
        # a non-blocking "could-not-verify" (ERROR, review M8) and the faithfulness
        # warnings (WO5). Logged here so every caller (GUI, html_generator, packaging,
        # bundle export, CLI) prints them, not only the run manifest.
        for line in verdict_warning_lines(decision):
            logger.warning("  %s", line)
    return decision


# ============================================================================
# M7 — run manifest + exit code
# ============================================================================
# Artifacts recorded in the manifest (present / bytes / hash). Ordered.
_MANIFEST_SUFFIXES = [
    config.SUFFIX_FORMATTED, config.SUFFIX_STRUCTURAL_THEMES,
    config.SUFFIX_INTERPRETIVE_THEMES, config.SUFFIX_TOPICS, config.SUFFIX_KEY_TERMS,
    config.SUFFIX_BOWEN, config.SUFFIX_EMPHASIS_SCORED, config.SUFFIX_ABSTRACT_GEN,
    config.SUFFIX_OVERVIEW, config.SUFFIX_BLOG, config.SUFFIX_WEBPAGE,
    config.SUFFIX_WEBPAGE_SIMPLE, config.SUFFIX_PDF,
]


def _sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


_CODE_REVISION_CACHE: Optional[str] = None


def _models_stamp() -> dict:
    """The models the run used, from the GUI selection (config.settings), for the run
    manifest (T5: it recorded the start-up model, not the one chosen in the GUI)."""
    s = config.settings
    return {"default": s.DEFAULT_MODEL, "aux": s.AUX_MODEL,
            "formatting": s.FORMATTING_MODEL, "validation": s.VALIDATION_MODEL}


def _code_revision() -> str:
    """Short git revision of the running code, best-effort ('unknown' if git is
    unavailable). Only a successful lookup is cached, so a transient failure retries
    (review M9; same cache discipline as the L9 fix)."""
    global _CODE_REVISION_CACHE
    if _CODE_REVISION_CACHE is not None:
        return _CODE_REVISION_CACHE
    try:
        import subprocess
        rev = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent, text=True,
            stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "unknown"
    _CODE_REVISION_CACHE = rev
    return rev


def build_manifest(base_name: str, decision: GateDecision, generated_at: str) -> dict:
    """Assemble the machine-readable run manifest (M7.A). ``generated_at`` is
    passed in (not sampled here) so the manifest is deterministic in tests."""
    proj = config.PROJECTS_DIR / base_name
    artifacts = {}
    for suffix in _MANIFEST_SUFFIXES:
        path = proj / f"{base_name}{suffix}"
        key = suffix.strip(" -") or suffix.strip()
        if path.exists():
            data = path.read_bytes()
            artifacts[key] = {"present": True, "bytes": len(data), "sha256": _sha256(data)}
        else:
            artifacts[key] = {"present": False}

    formatted = proj / f"{base_name}{config.SUFFIX_FORMATTED}"
    source_sha = _sha256(formatted.read_bytes()) if formatted.exists() else None
    return {
        "base_name": base_name,
        "generated_at": generated_at,
        "publish_decision": decision.decision.value,
        "gate": decision.to_dict(),
        "artifacts": artifacts,
        "provenance": {
            "source_sha256": source_sha,
            # Stamp the code + policy that produced this decision so it can be traced
            # back to a git revision and the exact gate policy in force (review M9).
            "code_revision": _code_revision(),
            "gate_policy": {
                "blocking_checks": sorted(config.GATE_BLOCKING_CHECKS),
                "error_blocks": config.GATE_ERROR_BLOCKS,
            },
            "models": _models_stamp(),
        },
    }


def write_manifest(base_name: str, decision: GateDecision, generated_at: str,
                   logger=None) -> Optional[Path]:
    """Write the manifest JSON next to the artifacts; return its path (M7.A), or
    None if the project directory doesn't exist."""
    import json

    manifest = build_manifest(base_name, decision, generated_at)
    path = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_RUN_MANIFEST}"
    if not path.parent.exists():
        # No project dir (e.g. wrong PROJECTS_DIR) — the decision still stands;
        # don't crash trying to write the manifest into a nonexistent directory.
        if logger:
            logger.error("Cannot write run manifest — project directory missing: %s",
                         path.parent)
        return None
    path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if logger:
        logger.info("Run manifest written: %s (publish_decision=%s)",
                    path.name, decision.decision.value)
    return path


def _update_block_marker(base_name: str, decision: GateDecision, when: str = "") -> None:
    """Write a PUBLISH-BLOCKED marker on BLOCK; clear a stale one otherwise (P8)."""
    marker = config.PROJECTS_DIR / base_name / f"{base_name}{config.SUFFIX_PUBLISH_BLOCKED}"
    if not marker.parent.exists():
        return  # nothing to publish (no project dir) — best-effort marker, don't crash
    if decision.decision is Decision.BLOCK:
        reasons = "\n".join(f"[{v.status.value}] {v.check}: {v.detail}" for v in decision.blockers)
        stamp = f" at {when}" if when else ""
        marker.write_text(f"Publication BLOCKED for {base_name}{stamp}\n\n{reasons}\n",
                          encoding="utf-8")
    elif marker.exists():
        marker.unlink()


def _quarantine_stale_bundle(base_name: str, logger=None) -> list:
    """On BLOCK, move any EXISTING published bundle aside to ``*.blocked-stale``
    (F4): otherwise a prior ALLOW run's webpage/pdf/zip stays on disk and a
    downstream deploy/rsync serves it as if it were the current, gated output.
    Quarantine (not delete) so a false BLOCK is recoverable — the detector is not
    perfect (single-word/acronym names slip through; concept labels can misfire)."""
    proj = config.PROJECTS_DIR / base_name
    moved = []
    for suffix in config.PUBLISHED_BUNDLE_SUFFIXES:
        f = proj / f"{base_name}{suffix}"
        if f.exists():
            f.replace(f.with_name(f.name + ".blocked-stale"))
            moved.append(f.name)
    if moved and logger:
        logger.warning("Gate BLOCK: quarantined %d stale bundle file(s) so they "
                       "can't ship as current: %s", len(moved), moved)
    return moved


def publish_allowed(base_name: str, logger=None) -> bool:
    """Publish-path guard (M1.B.2): run the gate; on BLOCK drop a marker, move any
    stale bundle aside, and return False so the caller writes NO bundle. On allow,
    clear a stale marker. Writes the run manifest tied to THIS decision (F5), so a
    gated publish always leaves a manifest reflecting the decision that gated —
    not a separate, later gate run.

    Note: each publish entry point (webpage/pdf/package) calls this, so the gate
    runs a few times per publish; the gate is deterministic on the same input
    artifacts, so the decision is identical. The manifest is a snapshot at gate
    time — bundle files written *after* the guard aren't all captured; a single
    orchestrator-level ``gate_and_report`` call (future wiring) would be exact."""
    decision = run_gate(base_name, logger)
    record_decision(base_name, decision, logger)
    return decision.allowed


def record_decision(base_name: str, decision: GateDecision, logger=None) -> None:
    """Apply a gate decision's side effects: marker, stale-bundle quarantine on
    BLOCK, and the run manifest.

    Purpose: Let a caller that already ran ``run_gate`` (the GUI webpdf stage)
             record the decision without losing the F4 quarantine / marker /
             manifest that ``publish_allowed`` performs (review G1).
    Spec:    docs/plan_review_fixes_2026-10-04.md#R1
    Tests:   tests/test_ts_gui_web_generation.py::test_r1a_gui_block_quarantines_stale_bundle
    """
    from datetime import datetime

    generated_at = datetime.now().isoformat(timespec="seconds")
    _update_block_marker(base_name, decision, generated_at)
    if decision.decision is Decision.BLOCK:
        _quarantine_stale_bundle(base_name, logger)
        if logger:
            logger.error("Release gate BLOCKED publication of %s — skipping bundle.", base_name)
    # After any quarantine, so the recorded artifact state matches what remains.
    write_manifest(base_name, decision, generated_at, logger)


def gate_and_report(base_name: str, generated_at: str, logger=None) -> GateDecision:
    """Run the gate, write the manifest, and on BLOCK drop a PUBLISH-BLOCKED
    marker so an operator/cron sees the refusal without parsing logs."""
    decision = run_gate(base_name, logger)
    write_manifest(base_name, decision, generated_at, logger)
    _update_block_marker(base_name, decision, generated_at)
    return decision


def _candidate_projects_dirs(override=None) -> list:
    """Where to look for a run's project folder, in priority order. An explicit
    override wins; otherwise the configured PROJECTS_DIR, then PROCESSED_DIR/projects
    (real runs live under the processed-transcripts folder even when only
    default_processed_dir — not default_projects_dir — is set in runtime settings)."""
    if override:
        return [Path(override)]
    cands = [config.PROJECTS_DIR]
    processed_projects = config.PROCESSED_DIR / "projects"
    if processed_projects not in cands:
        cands.append(processed_projects)
    return cands


def main(argv) -> int:
    """CLI: python release_gate.py "<base_name>" ["<projects_dir>"]

    Exit 0 on ALLOW/ALLOW_WITH_WARNINGS, 1 on BLOCK (M7.B), 2 on a usage/config
    error. Auto-discovers the run under the configured PROJECTS_DIR or
    PROCESSED_DIR/projects; pass a projects folder as the 2nd argument to override."""
    import logging
    from datetime import datetime

    if len(argv) < 2:
        print('usage: python release_gate.py "<base_name>" ["<projects_dir>"]')
        return 2
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    override = argv[2] if len(argv) >= 3 else None
    candidates = _candidate_projects_dirs(override)
    resolved = next((c for c in candidates if (c / argv[1]).exists()), None)
    if resolved is None:
        looked = "\n  ".join(str(c / argv[1]) for c in candidates)
        print(f"ERROR: project directory not found. Looked in:\n  {looked}\n"
              f"Pass the projects folder as the 2nd argument, e.g.:\n"
              f'  python release_gate.py "{argv[1]}" "/path/to/projects"')
        return 2
    config.PROJECTS_DIR = resolved
    print(f"Using projects dir: {resolved}")
    decision = gate_and_report(argv[1], datetime.now().isoformat(timespec="seconds"),
                               logging.getLogger("release_gate"))
    print(f"publish_decision={decision.decision.value}")
    return 1 if decision.decision is Decision.BLOCK else 0


if __name__ == "__main__":
    import sys
    sys.exit(main(sys.argv))
