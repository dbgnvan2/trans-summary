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
    other FAIL/WARN ship as ALLOW_WITH_WARNINGS. The elected hard blocker is
    ``entity_grounding`` (fabricated names).
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


def _source_with_metadata(base_name: str) -> Optional[str]:
    """The source transcript plus the recording's catalogue metadata (title,
    presenter, date, year from the filename).

    The abstract legitimately states these facts/names — the generation prompt
    supplies them — even though they aren't spoken in the transcript (a presenter
    rarely says their own name 'Michael Kerr'; the year comes from the filename).
    So entity-grounding and faithfulness must treat them as part of the source,
    or they FALSE-BLOCK publication. Low risk: only these known catalogue facts
    become grounded/entailed; a truly fabricated name or claim still won't match.
    (P20: re-run the faithfulness calibration on this change.)
    """
    transcript = _load_source_transcript(base_name)
    if not transcript or not transcript.strip():
        return transcript
    try:
        from transcript_utils import parse_filename_metadata
        meta = parse_filename_metadata(base_name)
        meta_lines = [f"{k.capitalize()}: {meta[k]}"
                      for k in ("title", "presenter", "date", "year") if meta.get(k)]
        if meta_lines:
            return ("Recording metadata (from the catalogue entry): "
                    + "; ".join(meta_lines) + "\n\n" + transcript)
    except Exception:  # metadata is best-effort; the transcript alone still verifies
        pass
    return transcript


def check_entity_grounding(base_name: str, logger=None) -> Verdict:
    """FAIL if any narrative artifact contains a multi-word proper name absent
    from the source transcript (the fabricated-name class — a real run shipped
    'Luciano Malorni' into the published HTML). This is the elected hard blocker.
    Missing source -> ERROR (can't verify -> block), not a silent pass."""
    import abstract_validation

    # Source includes the filename metadata so the presenter's own name / the
    # year (which the abstract legitimately states) aren't flagged as fabricated.
    transcript = _source_with_metadata(base_name)
    if not transcript or not transcript.strip():
        # Missing OR present-but-empty/truncated source is "cannot verify" (F6),
        # not a definitive FAIL asserting the names are fabricated. ERROR -> block.
        return Verdict("entity_grounding", Status.ERROR,
                       "source transcript missing or empty — cannot verify names")
    offending = {}
    for suffix in config.GATE_ENTITY_ARTIFACT_SUFFIXES:
        path = config.PROJECTS_DIR / base_name / f"{base_name}{suffix}"
        if not path.exists():
            continue
        names = abstract_validation.find_ungrounded_names(
            path.read_text(encoding="utf-8"), transcript
        )
        if names:
            offending[suffix.strip(" -").removesuffix(".md")] = names
    if offending:
        flat = sorted({n for names in offending.values() for n in names})
        arts = ", ".join(offending.keys())
        # Actionable message naming the artifact + the unverified name(s) — renders
        # as "entity_grounding: check failed in <artifact>: name(s) not in source:
        # <names> — regenerate and try again".
        return Verdict("entity_grounding", Status.FAIL,
                       f"check failed in {arts}: name(s) not in source: "
                       f"{', '.join(flat)} — regenerate and try again",
                       items=[{"artifact": k, "names": v} for k, v in offending.items()])
    return Verdict("entity_grounding", Status.PASS, "all proper names grounded")


# --------------------------------------------------------------------------- M4.A
def check_verbatim_quotes(base_name: str, logger=None) -> Verdict:
    """WARN if any Bowen/emphasis quote is not verbatim-locatable in the source
    (head- AND tail-matched, so a fabricated tail is caught)."""
    import transcript_utils as tu
    import validation_pipeline as vp

    transcript = _load_source_transcript(base_name)
    if transcript is None:
        return Verdict("verbatim_quotes", Status.ERROR, "source transcript missing")
    problems = []
    for concept, quote, _ts in tu.load_bowen_references(base_name):
        if vp._emphasis_quote_found_ratio(quote, transcript) < config.EMPHASIS_QUOTE_PARTIAL_RATIO:
            problems.append({"type": "bowen", "label": concept, "quote": quote[:60]})
    for label, quote, _ts in tu.load_emphasis_items(base_name):
        if vp._emphasis_quote_found_ratio(quote, transcript) < config.EMPHASIS_QUOTE_PARTIAL_RATIO:
            problems.append({"type": "emphasis", "label": label, "quote": quote[:60]})
    if problems:
        return Verdict("verbatim_quotes", Status.WARN,
                       f"{len(problems)} quote(s) not verbatim-locatable", items=problems)
    return Verdict("verbatim_quotes", Status.PASS, "all quotes verbatim")


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
        found = set(re.findall(r"\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b",
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


def _judge_cached(fjudge, artifact_text: str, source: str, client, logger):
    import hashlib

    key = (hashlib.sha256(artifact_text.encode("utf-8")).hexdigest(),
           hashlib.sha256(source.encode("utf-8")).hexdigest())
    cached = _FAITHFULNESS_CACHE.get(key)
    if cached is not None:
        return cached
    result = fjudge.judge_artifact(artifact_text, source, client, logger=logger)
    if result.status != fjudge.ERROR:  # never cache a transient failure (P1)
        _FAITHFULNESS_CACHE[key] = result
    return result


def check_faithfulness(base_name: str, logger=None) -> Verdict:
    """Claim-level semantic faithfulness of the NARRATIVE artifacts (M2). Each
    artifact's claims must be entailed by the source; a contradicted/unsupported
    claim -> FAIL (fluent hallucination). The judge fails closed: no source / no
    API key / judge error -> ERROR (blocks). Disabled by default until the M2.B
    gold-set calibration clears thresholds (`config.FAITHFULNESS_JUDGE_ENABLED`),
    in which state it is a PASS no-op so the deterministic gate is unaffected."""
    if not getattr(config, "FAITHFULNESS_JUDGE_ENABLED", False):
        return Verdict("faithfulness", Status.PASS,
                       "faithfulness judge disabled (awaiting M2.B calibration)")
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
                       "faithfulness judge (fail closed)")
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    proj = config.PROJECTS_DIR / base_name
    fails, errors = [], []
    judged = 0
    for suffix in config.FAITHFULNESS_ARTIFACT_SUFFIXES:
        path = proj / f"{base_name}{suffix}"
        if not path.exists():
            continue
        judged += 1
        result = _judge_cached(
            fjudge, path.read_text(encoding="utf-8"), transcript, client, logger)
        art = suffix.strip(" -")
        if result.status == fjudge.FAIL:
            fails.append({"artifact": art, "detail": result.detail,
                          "unfaithful": [c.claim for c in result.unfaithful]})
        elif result.status == fjudge.ERROR:
            errors.append({"artifact": art, "detail": result.detail})
    if judged == 0:
        # "nothing to judge" is NOT "all faithful": a run with no narrative artifact
        # present cannot silently clear the faithfulness gate (P7 pass-on-empty).
        return Verdict("faithfulness", Status.ERROR,
                       "no narrative artifact present to verify faithfulness")
    if fails:
        # include any co-occurring ERRORs in items so the manifest isn't lossy.
        # Actionable message naming the artifact(s) — rendered as
        # "faithfulness: check failed in <artifact> — regenerate and try again".
        arts = ", ".join(f["artifact"].removesuffix(".md") for f in fails)
        return Verdict("faithfulness", Status.FAIL,
                       f"check failed in {arts} — regenerate and try again",
                       items=fails + errors)
    if errors:
        return Verdict("faithfulness", Status.ERROR,
                       f"{len(errors)} of {judged} artifact(s) could not be verified",
                       items=errors)
    return Verdict("faithfulness", Status.PASS,
                   f"all narrative claims entailed by source ({judged} artifact(s) judged)")


# --------------------------------------------------------------------------- theme grounding
# suffix -> theme kind for the M3 codec.
_THEME_KIND = {
    config.SUFFIX_STRUCTURAL_THEMES: "structural",
    config.SUFFIX_INTERPRETIVE_THEMES: "interpretive",
}
_THEME_JUDGE_CACHE: dict = {}


def _judge_theme_cached(fjudge, text: str, source: str, kind: str, client, logger):
    import hashlib

    key = (hashlib.sha256(text.encode("utf-8")).hexdigest(),
           hashlib.sha256(source.encode("utf-8")).hexdigest(), kind)
    cached = _THEME_JUDGE_CACHE.get(key)
    if cached is not None:
        return cached
    result = fjudge.judge_themes_artifact(text, source, kind, client, logger=logger)
    if result.status != fjudge.ERROR:  # never cache a transient failure (P1)
        _THEME_JUDGE_CACHE[key] = result
    return result


def check_theme_grounding(base_name: str, logger=None) -> Verdict:
    """Interpretive GROUNDING of the theme artifacts (structural + interpretive): a
    theme must be a reasonable interpretation of content actually in the source; a
    theme built on fabricated subject matter -> FAIL. This is the theme counterpart
    of the faithfulness judge (which is source-ENTAILMENT and wrong for interpretive
    content). Fails closed (no source / no key / judge error -> ERROR). Disabled by
    default (a PASS no-op) until its gold-set calibration clears
    (`config.THEME_JUDGE_ENABLED`)."""
    if not getattr(config, "THEME_JUDGE_ENABLED", False):
        return Verdict("theme_grounding", Status.PASS,
                       "theme grounding judge disabled (awaiting calibration)")
    import faithfulness_judge as fjudge
    from transcript_utils import resolve_anthropic_key

    transcript = _load_source_transcript(base_name)
    if not transcript or not transcript.strip():
        return Verdict("theme_grounding", Status.ERROR,
                       "source transcript missing or empty — cannot verify themes")
    api_key = resolve_anthropic_key()
    if not api_key:
        return Verdict("theme_grounding", Status.ERROR,
                       "no Anthropic API key — cannot run theme judge (fail closed)")
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)
    proj = config.PROJECTS_DIR / base_name
    fails, errors = [], []
    judged = 0
    for suffix, kind in _THEME_KIND.items():
        path = proj / f"{base_name}{suffix}"
        if not path.exists():
            continue
        judged += 1
        result = _judge_theme_cached(
            fjudge, path.read_text(encoding="utf-8"), transcript, kind, client, logger)
        art = suffix.strip(" -")
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
                       f"theme(s)", items=fails + errors)
    if errors:
        return Verdict("theme_grounding", Status.ERROR,
                       f"{len(errors)} of {judged} theme artifact(s) could not be verified",
                       items=errors)
    return Verdict("theme_grounding", Status.PASS,
                   f"all themes grounded ({judged} artifact(s) judged)")


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


# Ordered registry. entity_grounding is the only hard blocker (config policy);
# the rest are advisory verdicts recorded in the manifest.
DEFAULT_CHECKS: list = [
    ("entity_grounding", check_entity_grounding),
    ("artifact_contracts", check_artifact_contracts),
    ("faithfulness", check_faithfulness),
    ("theme_grounding", check_theme_grounding),
    ("required_artifacts", check_required_artifacts),
    ("verbatim_quotes", check_verbatim_quotes),
    ("timestamp_citations", check_timestamp_citations),
    ("entity_consistency", check_entity_consistency),
]


def run_gate(base_name: str, logger=None, checks: Optional[list] = None) -> GateDecision:
    """Run all checks and return the aggregate publish decision."""
    checks = DEFAULT_CHECKS if checks is None else checks
    verdicts = [_safe(name, fn, base_name, logger) for name, fn in checks]
    decision = decide(verdicts)
    if logger:
        logger.info("Release gate for %s: %s (%d verdict(s), %d blocker(s))",
                    base_name, decision.decision.value, len(verdicts), len(decision.blockers))
        for v in decision.blockers:
            logger.error("  BLOCKER [%s] %s: %s", v.status.value, v.check, v.detail)
    return decision


# ============================================================================
# M7 — run manifest + exit code
# ============================================================================
# Artifacts recorded in the manifest (present / bytes / hash). Ordered.
_MANIFEST_SUFFIXES = [
    config.SUFFIX_FORMATTED, config.SUFFIX_STRUCTURAL_THEMES,
    config.SUFFIX_INTERPRETIVE_THEMES, config.SUFFIX_TOPICS, config.SUFFIX_KEY_TERMS,
    config.SUFFIX_BOWEN, config.SUFFIX_EMPHASIS_SCORED, config.SUFFIX_ABSTRACT_GEN,
    config.SUFFIX_OVERVIEW, config.SUFFIX_BLOG, config.SUFFIX_WEBPAGE, config.SUFFIX_PDF,
]


def _sha256(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


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
            "models": {
                "default": config.DEFAULT_MODEL,
                "aux": getattr(config, "AUX_MODEL", None),
                "validation": getattr(config, "VALIDATION_MODEL", None),
            },
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
    from datetime import datetime

    decision = run_gate(base_name, logger)
    generated_at = datetime.now().isoformat(timespec="seconds")
    _update_block_marker(base_name, decision, generated_at)
    if decision.decision is Decision.BLOCK:
        _quarantine_stale_bundle(base_name, logger)
        if logger:
            logger.error("Release gate BLOCKED publication of %s — skipping bundle.", base_name)
    # After any quarantine, so the recorded artifact state matches what remains.
    write_manifest(base_name, decision, generated_at, logger)
    return decision.allowed


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
