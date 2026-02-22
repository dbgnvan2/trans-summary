#!/usr/bin/env python3
"""Token-efficient reviewer for trans-summary prompt/output alignment."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptRule:
    key: str
    prompt_file: str
    artifact_suffixes: tuple[str, ...]
    kind: str
    optional: bool = False


ACTIVE_PROMPT_RULES: list[PromptRule] = [
    PromptRule("formatting", "Transcript Formatting Prompt v12-Lite.md", (" - formatted.md",), "formatted"),
    PromptRule("header_validation", "Transcript Formatting Headers Validation Prompt 12.md", (" - header-validation.md",), "header_validation"),
    PromptRule("topics", "Transcript Summary - Topics v1.md", (" - topics.md",), "topics"),
    PromptRule("structural", "Transcript Summary - Structural Themes v2.md", (" - structural-themes.md",), "themes"),
    PromptRule("interpretive", "Transcript Summary - Interpretive Themes v1.md", (" - interpretive-themes.md",), "themes"),
    PromptRule("lenses", "Transcript Summary - Lens Generation v1.md", (" - lenses-ranked.md",), "lenses"),
    PromptRule("theme_lens_validation", "Transcript Summary - Theme Lens Validation v1.md", (" - lenses-ranked.md",), "lenses_validation"),
    PromptRule("key_terms", "Transcript Summary Key Terms v1.md", (" - key-terms.md",), "key_terms"),
    PromptRule("blog", "Transcript Summary Blog Post v1.md", (" - blog.md",), "blog"),
    # Not used in your normal Run All flow. Keep as optional.
    PromptRule("summary", "Summary Generation Prompt v1.md", (" - summary-generated.md",), "summary", optional=True),
    PromptRule("abstract", "Abstract Generation Prompt v1.md", (" - abstract-generated.md",), "abstract"),
    # Coverage prompt is used by abstract coverage in normal flow.
    PromptRule("coverage", "Validation Coverage Prompt v1.md", (" - abstract-validation.txt", " - summary-validation.txt"), "coverage"),
    # Voice audit prompt reviews blog style and may not emit a file unless explicitly saved.
    PromptRule("voice_audit", "Transcript Voice Audit Prompt v1.md", (" - blog.md",), "voice_audit_no_file"),
    # Active emphasis output is scored file in current pipeline.
    PromptRule("emphasis", "emphasis_dedection_v3_production.md", (" - emphasis-scored.md", " - emphasis-items.md"), "quoted_items"),
    PromptRule("bowen_extract", "bowen_reference_extraction_v1.md", (" - bowen-references.md",), "quoted_items"),
    PromptRule("bowen_filter", "bowen_reference_filter_v1.md", (" - bowen-references.md",), "quoted_items"),
    PromptRule("error_detection_v1", "transcript_error_detection_prompt.md", tuple(), "initial_validation"),
    PromptRule("error_detection_v2", "transcript_error_detection_prompt_v2.md", tuple(), "initial_validation"),
]


LEGACY_RULES: list[PromptRule] = [
    PromptRule("abstract_quality_legacy", "abstract_quality_assessment_prompt_v2.md", (" - abstract-validation.txt",), "legacy_validation", optional=True),
    PromptRule("key_items_legacy", "Transcript Summary Key Items v1.md", (" - All Key Items.md",), "legacy_cost_only", optional=True),
]


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def strip_yaml_frontmatter(text: str) -> str:
    return re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.DOTALL)


def word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def count_items(text: str) -> int:
    return len(re.findall(r"(?m)^\s*(?:\d+\.|[-*])\s+", text))


def extract_percentages(text: str) -> list[int]:
    vals = []
    for m in re.findall(r"~?(\d{1,3})%", text):
        try:
            vals.append(int(m))
        except ValueError:
            continue
    return vals


def find_constraints(prompt_text: str, limit: int = 8) -> list[str]:
    lines = [ln.strip() for ln in prompt_text.splitlines()]
    keep: list[str] = []
    pattern = re.compile(r"\b(must|required|should|do not|don't|never|exact|strict|format|output|include)\b", re.IGNORECASE)
    for ln in lines:
        if not ln or len(ln) < 12:
            continue
        if pattern.search(ln):
            keep.append(ln)
        if len(keep) >= limit:
            break
    return keep


def pick_evidence(text: str, patterns: list[str], max_lines: int) -> list[str]:
    if not text:
        return []
    out: list[str] = []
    lines = text.splitlines()
    for ln in lines:
        if len(out) >= max_lines:
            break
        for pat in patterns:
            if re.search(pat, ln, re.IGNORECASE):
                out.append(ln.strip())
                break
    return out


def check_markdown_basic(text: str, min_words: int, require_headings: bool = True) -> tuple[list[str], list[str]]:
    checks: list[str] = []
    warnings: list[str] = []
    w = word_count(text)
    checks.append(f"word_count={w}")
    if w < min_words:
        warnings.append(f"Word count below expected floor ({w} < {min_words}).")
    if require_headings and "##" not in text and "###" not in text:
        warnings.append("No markdown headings detected.")
    return checks, warnings


def resolve_artifact(project_dir: Path | None, base_name: str, suffixes: tuple[str, ...]) -> Path | None:
    if project_dir is None or not suffixes:
        return None
    for suffix in suffixes:
        candidate = project_dir / f"{base_name}{suffix}"
        if candidate.exists():
            return candidate
    return project_dir / f"{base_name}{suffixes[0]}"


def extract_candidate_items(text: str, max_items: int = 12) -> list[str]:
    items: list[str] = []
    for ln in text.splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith("### "):
            items.append(s[4:].strip())
        elif re.match(r"^\d+\.\s+\*\*.+\*\*", s):
            cleaned = re.sub(r"^\d+\.\s+\*\*", "", s)
            cleaned = re.sub(r"\*\*.*$", "", cleaned)
            items.append(cleaned.strip())
        elif s.startswith("- **"):
            cleaned = s.replace("- **", "", 1)
            cleaned = cleaned.split("**", 1)[0].strip()
            if cleaned:
                items.append(cleaned)
        if len(items) >= max_items:
            break
    if not items:
        for ln in text.splitlines():
            s = ln.strip()
            if s and len(s) > 12:
                items.append(s[:120])
            if len(items) >= max_items:
                break
    return items


def extract_sentence_claims(text: str, max_claims: int = 6) -> list[str]:
    cleaned = re.sub(r"\s+", " ", strip_yaml_frontmatter(text)).strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    claims: list[str] = []
    for part in parts:
        p = part.strip()
        if len(p) < 40:
            continue
        claims.append(p[:240])
        if len(claims) >= max_claims:
            break
    return claims


def extract_quoted_claims(text: str, max_claims: int = 6) -> list[str]:
    claims = re.findall(r'"([^"]{20,280})"', text)
    return claims[:max_claims]


def extract_claims_for_kind(kind: str, text: str, max_claims: int = 6) -> list[str]:
    if kind in {"topics", "themes", "lenses", "key_terms"}:
        items = extract_candidate_items(text, max_items=max_claims)
        if items:
            return items
    if kind in {"quoted_items"}:
        quotes = extract_quoted_claims(text, max_claims=max_claims)
        if quotes:
            return quotes
    if kind in {"blog", "abstract", "summary", "coverage", "voice_audit_no_file"}:
        return extract_sentence_claims(text, max_claims=max_claims)
    # fallback
    return extract_sentence_claims(text, max_claims=max_claims)


def _build_semantic_model_candidates(ts_config) -> list[str]:
    preferred = os.getenv("REVIEW_SEMANTIC_MODEL", "").strip()
    candidates = [
        preferred,
        getattr(ts_config, "VALIDATION_MODEL", ""),
        getattr(ts_config, "AUX_MODEL", ""),
        # Low-cost defaults first.
        "claude-haiku-4-5-20251001",
        "claude-3-5-haiku",
        "claude-3-haiku-20240307",
        # Reliability fallback if account access is limited.
        "claude-sonnet-4-5-20250929",
    ]
    deduped: list[str] = []
    for name in candidates:
        if name and name not in deduped:
            deduped.append(name)
    return deduped


def _call_with_model_fallback(call_claude_with_retry, model_candidates: list[str], **kwargs):
    errors: list[str] = []
    for model_name in model_candidates:
        try:
            message = call_claude_with_retry(model=model_name, **kwargs)
            return message, model_name
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{model_name}: {exc}")
            continue
    raise RuntimeError("All semantic models failed: " + " | ".join(errors[:4]))


def run_semantic_grounding_check(
    repo_root: Path,
    project_dir: Path | None,
    base_name: str,
    themes_artifact: Path | None,
    lenses_artifact: Path | None,
) -> dict[str, dict]:
    result = {
        "ok": False,
        "error": "",
        "themes": {"questionable": 0, "total": 0, "notes": []},
        "lenses": {"questionable": 0, "total": 0, "notes": []},
    }

    if not project_dir:
        result["error"] = "No project dir provided for semantic check."
        return result

    formatted_path = project_dir / f"{base_name} - formatted.md"
    if not formatted_path.exists():
        result["error"] = "Formatted transcript missing; cannot perform semantic grounding."
        return result

    themes_text = read_text(themes_artifact) if themes_artifact and themes_artifact.exists() else ""
    lenses_text = read_text(lenses_artifact) if lenses_artifact and lenses_artifact.exists() else ""
    themes_items = extract_candidate_items(themes_text, max_items=8)
    lenses_items = extract_candidate_items(lenses_text, max_items=8)

    result["themes"]["total"] = len(themes_items)
    result["lenses"]["total"] = len(lenses_items)

    if not themes_items and not lenses_items:
        result["error"] = "No theme/lens items found for semantic review."
        return result

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        result["error"] = "ANTHROPIC_API_KEY not set; semantic check skipped."
        return result

    try:
        sys.path.insert(0, str(repo_root))
        import anthropic  # type: ignore
        import config as ts_config  # type: ignore
        from transcript_utils import call_claude_with_retry, create_system_message_with_cache  # type: ignore

        transcript_text = strip_yaml_frontmatter(read_text(formatted_path))
        system_msg = create_system_message_with_cache(transcript_text)
        model_candidates = _build_semantic_model_candidates(ts_config)
        used_models: set[str] = set()
        client = anthropic.Anthropic(api_key=api_key)

        def _check_items(label: str, items: list[str]) -> tuple[int, list[str]]:
            if not items:
                return 0, []
            user_prompt = (
                f"Evaluate whether each {label} item is grounded in this transcript.\n"
                "Return strict JSON object with key items.\n"
                "Each item object keys: item, verdict(grounded|questionable), reason(max 10 words).\n"
                "No prose outside JSON.\n\n"
                f"{label.title()} items:\n{json.dumps(items, ensure_ascii=True)}"
            )
            message, used_model = _call_with_model_fallback(
                call_claude_with_retry=call_claude_with_retry,
                model_candidates=model_candidates,
                client=client,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=ts_config.MAX_TOKENS_REVIEW_SEMANTIC,
                temperature=0.0,
                system=system_msg,
                min_length=30,
                suppress_caching_warnings=True,
            )
            used_models.add(used_model)
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
            arr = parsed.get("items", []) if isinstance(parsed, dict) else []
            questionable = 0
            notes: list[str] = []
            for obj in arr:
                if not isinstance(obj, dict):
                    continue
                verdict = str(obj.get("verdict", "")).lower().strip()
                item = str(obj.get("item", "")).strip()
                reason = str(obj.get("reason", "")).strip()
                if verdict == "questionable":
                    questionable += 1
                    notes.append(f"{item}: {reason}")
            return questionable, notes[:4]

        t_q, t_notes = _check_items("themes", themes_items)
        l_q, l_notes = _check_items("lenses", lenses_items)
        result["themes"]["questionable"] = t_q
        result["themes"]["notes"] = t_notes
        result["lenses"]["questionable"] = l_q
        result["lenses"]["notes"] = l_notes
        result["model_used"] = ", ".join(sorted(used_models)) if used_models else ""

        result["ok"] = True
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"Semantic check failed: {exc}"
        return result


def run_semantic_all_check(
    repo_root: Path,
    project_dir: Path | None,
    base_name: str,
    rules: list[PromptRule],
) -> dict:
    result = {"ok": False, "error": "", "items": {}}
    if not project_dir:
        result["error"] = "No project dir provided for semantic-all check."
        return result

    formatted_path = project_dir / f"{base_name} - formatted.md"
    if not formatted_path.exists():
        result["error"] = "Formatted transcript missing; cannot perform semantic-all grounding."
        return result

    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        result["error"] = "ANTHROPIC_API_KEY not set; semantic-all skipped."
        return result

    try:
        sys.path.insert(0, str(repo_root))
        import anthropic  # type: ignore
        import config as ts_config  # type: ignore
        from transcript_utils import call_claude_with_retry, create_system_message_with_cache  # type: ignore

        transcript_text = strip_yaml_frontmatter(read_text(formatted_path))
        system_msg = create_system_message_with_cache(transcript_text)
        client = anthropic.Anthropic(api_key=api_key)
        model_candidates = _build_semantic_model_candidates(ts_config)
        used_models: set[str] = set()

        semantic_kinds = {"topics", "themes", "lenses", "key_terms", "blog", "abstract", "summary", "quoted_items", "coverage", "voice_audit_no_file"}

        for rule in rules:
            if rule.kind not in semantic_kinds:
                continue
            artifact = resolve_artifact(project_dir, base_name, rule.artifact_suffixes)
            if not artifact or not artifact.exists():
                continue
            artifact_text = read_text(artifact)
            claims = extract_claims_for_kind(rule.kind, artifact_text, max_claims=6)
            if not claims:
                result["items"][rule.key] = {
                    "skipped": True,
                    "reason": "No claims extracted for semantic check.",
                    "grounded": 0,
                    "questionable": 0,
                    "contradicted": 0,
                    "total": 0,
                    "grounded_pct": 0,
                    "pass": False,
                }
                continue

            user_prompt = (
                "Evaluate each claim against the transcript context.\n"
                "Return strict JSON with key 'claims'.\n"
                "Each element: claim, verdict(grounded|questionable|contradicted), reason(max 12 words).\n"
                "Be strict. contradicted means conflicts with transcript facts.\n"
                "questionable means weak/insufficient support.\n"
                "No prose outside JSON.\n\n"
                f"Claims:\n{json.dumps(claims, ensure_ascii=True)}"
            )
            message, used_model = _call_with_model_fallback(
                call_claude_with_retry=call_claude_with_retry,
                model_candidates=model_candidates,
                client=client,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=ts_config.MAX_TOKENS_REVIEW_SEMANTIC,
                temperature=0.0,
                system=system_msg,
                min_length=30,
                suppress_caching_warnings=True,
            )
            used_models.add(used_model)
            raw = message.content[0].text.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*", "", raw)
                raw = re.sub(r"\s*```$", "", raw)
            parsed = json.loads(raw)
            arr = parsed.get("claims", []) if isinstance(parsed, dict) else []

            grounded = questionable = contradicted = 0
            notes: list[str] = []
            for obj in arr:
                if not isinstance(obj, dict):
                    continue
                verdict = str(obj.get("verdict", "")).strip().lower()
                claim = str(obj.get("claim", "")).strip()
                reason = str(obj.get("reason", "")).strip()
                if verdict == "grounded":
                    grounded += 1
                elif verdict == "questionable":
                    questionable += 1
                    if claim:
                        notes.append(f"{claim[:90]}: {reason}")
                elif verdict == "contradicted":
                    contradicted += 1
                    if claim:
                        notes.append(f"{claim[:90]}: {reason}")
            total = max(1, len(arr))
            grounded_pct = round((grounded / total) * 100)
            semantic_pass = contradicted == 0 and grounded_pct >= 70
            result["items"][rule.key] = {
                "skipped": False,
                "reason": "",
                "grounded": grounded,
                "questionable": questionable,
                "contradicted": contradicted,
                "total": len(arr),
                "grounded_pct": grounded_pct,
                "pass": semantic_pass,
                "notes": notes[:4],
            }

        result["ok"] = True
        result["model_used"] = ", ".join(sorted(used_models)) if used_models else ""
        return result
    except Exception as exc:  # noqa: BLE001
        result["error"] = f"Semantic-all check failed: {exc}"
        return result


def review_questions_for_kind(kind: str) -> list[str]:
    table: dict[str, list[str]] = {
        "formatted": [
            "Does the formatted transcript preserve meaning and speaker flow without silent omissions?",
            "Do section headers reflect content, not generic placeholders?",
        ],
        "topics": [
            "Are top topics truly dominant in the transcript, not just high-level labels?",
            "Do topic percentages and section refs feel internally consistent?",
        ],
        "themes": [
            "Do these themes describe real recurring patterns in this transcript?",
            "Are any themes generic enough to fit almost any lecture?",
        ],
        "lenses": [
            "Does each lens plausibly fit this specific transcript material?",
            "Are top-ranked lenses evidence-backed and non-redundant?",
        ],
        "key_terms": [
            "Are key terms domain-significant and not generic words?",
            "Are definitions grounded in transcript context rather than outside knowledge?",
        ],
        "summary": [
            "If generated, does summary preserve the transcript's narrative arc and tensions?",
        ],
        "abstract": [
            "Does the abstract capture purpose, method, and major findings succinctly?",
            "Is it faithful without overclaiming confidence?",
        ],
        "blog": [
            "Does blog voice remain faithful to transcript content and uncertainty?",
            "Does it avoid sensationalization or unsupported claims?",
        ],
        "quoted_items": [
            "Are extracted quotes exact or near-exact from transcript text?",
            "Are selected quotes truly central rather than incidental?",
        ],
        "voice_audit_no_file": [
            "Does the blog post appear to match the intended voice-audit criteria?",
            "If strict voice compliance is required, should transcript_audit_voice.py be run with --save-report?",
        ],
        "header_validation": [
            "Do flagged headers represent real semantic drift, not style preferences?",
            "Were high-risk problematic headers actually corrected?",
        ],
        "coverage": [
            "Are reported coverage gaps material to user outcomes?",
            "Do pass/fail calls match transcript salience, not checklist bias?",
        ],
        "initial_validation": [
            "Do initial-validation corrections avoid changing intended meaning?",
        ],
        "legacy_validation": [
            "Is this legacy validation still active in the current execution path?",
        ],
        "legacy_cost_only": [
            "Is this prompt only cost-estimator metadata rather than production output?",
        ],
        "lenses_validation": [
            "If lens validation fails, was regeneration/re-ranking actually applied?",
        ],
    }
    return table.get(kind, ["Does this artifact satisfy its prompt's core intent?"])


def evaluate(
    rule: PromptRule,
    prompt_text: str,
    artifact_path: Path | None,
    max_evidence_lines: int,
    semantic_result: dict[str, dict] | None,
    semantic_all_result: dict | None,
) -> dict:
    result = {
        "prompt": rule.prompt_file,
        "artifact": str(artifact_path) if artifact_path else None,
        "status": "UNCLEAR",
        "checks": [],
        "warnings": [],
        "evidence": [],
        "review_questions": [],
        "constraints": find_constraints(prompt_text),
        "pass_fail": "FAIL",
        "score_pct": 0,
        "verification_method": [],
    }

    if rule.artifact_suffixes and artifact_path is None:
        result["status"] = "UNCLEAR"
        result["warnings"].append("Artifact path not provided; pass --base-name or --project-dir.")
        result["review_questions"].append("Which run folder should be audited for this prompt?")
        result["verification_method"].append("Artifact resolution check")
        return result

    if artifact_path is not None and not artifact_path.exists():
        if rule.optional:
            result["status"] = "UNCLEAR"
            result["warnings"].append("Optional artifact not present in this run.")
        else:
            result["status"] = "DENY"
            result["warnings"].append("Expected artifact is missing.")
        result["review_questions"].append("Was this stage intentionally skipped for this run?")
        result["verification_method"].append("Required artifact presence check")
        return result

    artifact_text = read_text(artifact_path) if artifact_path else ""
    result["verification_method"].append("Artifact presence + content load")

    if rule.kind in {"formatted", "summary", "abstract", "blog", "themes", "topics", "key_terms", "lenses"}:
        floors = {
            "formatted": 200,
            "summary": 500,
            "abstract": 120,
            "blog": 600,
            "themes": 120,
            "topics": 100,
            "key_terms": 80,
            "lenses": 120,
        }
        # Abstract prompt asks for paragraph-only output, so headings are not required.
        require_headings = rule.kind != "abstract"
        checks, warnings = check_markdown_basic(artifact_text, floors[rule.kind], require_headings=require_headings)
        result["checks"].extend(checks)
        result["warnings"].extend(warnings)
        result["verification_method"].append("Length/structure sanity checks")

    if rule.kind == "topics":
        pcts = extract_percentages(artifact_text)
        if pcts:
            total = sum(pcts)
            result["checks"].append(f"percent_total={total}")
            if not (90 <= total <= 110):
                result["warnings"].append("Topic percentage totals look implausible (expected near 100%).")
        else:
            result["warnings"].append("No topic percentages detected.")
        result["verification_method"].append("Topic metadata consistency check")

    # No percentage-total requirement for structural/interpretive themes.

    if rule.kind == "key_terms":
        term_like = len(re.findall(r"(?m)^\s*(?:###|\*\*[^*]+\*\*)", artifact_text))
        result["checks"].append(f"term_entries~={term_like}")
        if term_like < 3:
            result["warnings"].append("Very few key-term entries detected.")
        result["verification_method"].append("Key-term entry density check")

    if rule.kind in {"quoted_items"}:
        quote_lines = len(re.findall(r'"[^"]{8,}"', artifact_text))
        numbered = count_items(artifact_text)
        result["checks"].append(f"quoted_lines~={quote_lines}")
        result["checks"].append(f"list_items~={numbered}")
        if quote_lines == 0 and numbered == 0:
            result["warnings"].append("No quote-like or list items found.")
        result["verification_method"].append("Quote/list extraction shape check")

    if rule.kind == "header_validation":
        if "Batch" not in artifact_text and "Problematic Term" not in artifact_text:
            result["warnings"].append("Header validation report markers not found.")
        result["verification_method"].append("Header-validation marker check")

    if rule.kind == "coverage":
        lowered = artifact_text.lower()
        if "coverage" not in lowered and "missing" not in lowered and "pass" not in lowered and "fail" not in lowered:
            result["warnings"].append("Coverage report may be missing explicit validation findings.")
        result["verification_method"].append("Coverage report signal check")

    if rule.kind in {"voice_audit_no_file", "initial_validation", "legacy_cost_only", "lenses_validation", "legacy_validation"}:
        result["warnings"].append("Needs manual judgment; deterministic auto-check is partial.")
        result["verification_method"].append("Manual-review gating rule")

    if semantic_result and semantic_result.get("ok"):
        if rule.kind == "themes":
            total = semantic_result.get("themes", {}).get("total", 0)
            questionable = semantic_result.get("themes", {}).get("questionable", 0)
            result["checks"].append(f"semantic_theme_questionable={questionable}/{total}")
            for note in semantic_result.get("themes", {}).get("notes", [])[:3]:
                result["warnings"].append(f"Theme grounding concern: {note}")
            result["verification_method"].append("Cached transcript semantic grounding check")
        if rule.kind in {"lenses", "lenses_validation"}:
            total = semantic_result.get("lenses", {}).get("total", 0)
            questionable = semantic_result.get("lenses", {}).get("questionable", 0)
            result["checks"].append(f"semantic_lens_questionable={questionable}/{total}")
            for note in semantic_result.get("lenses", {}).get("notes", [])[:3]:
                result["warnings"].append(f"Lens grounding concern: {note}")
            result["verification_method"].append("Cached transcript semantic grounding check")

    semantic_item = None
    if semantic_all_result and semantic_all_result.get("ok"):
        semantic_item = semantic_all_result.get("items", {}).get(rule.key)
    if semantic_item and not semantic_item.get("skipped", False):
        grounded = semantic_item.get("grounded", 0)
        questionable = semantic_item.get("questionable", 0)
        contradicted = semantic_item.get("contradicted", 0)
        total = semantic_item.get("total", 0)
        grounded_pct = semantic_item.get("grounded_pct", 0)
        result["checks"].append(f"semantic_all_grounded={grounded}/{total}")
        result["checks"].append(f"semantic_all_questionable={questionable}/{total}")
        result["checks"].append(f"semantic_all_contradicted={contradicted}/{total}")
        result["checks"].append(f"semantic_all_pct={grounded_pct}%")
        result["verification_method"].append("Semantic-all claim grounding check")
        if contradicted > 0:
            result["warnings"].append("Semantic-all found contradicted claims.")
        if grounded_pct < 70:
            result["warnings"].append(f"Semantic-all grounded below threshold ({grounded_pct}% < 70%).")
        for note in semantic_item.get("notes", [])[:2]:
            result["warnings"].append(f"Semantic-all note: {note}")

    evidence_patterns = [r"^##", r"^###", r"%", r"missing", r"warning", r"error", r"quote", r"lens", r"theme", r"topic"]
    result["evidence"] = pick_evidence(artifact_text, evidence_patterns, max_evidence_lines)
    result["review_questions"] = review_questions_for_kind(rule.kind)

    missing_hard = any("expected artifact is missing" in w.lower() for w in result["warnings"])
    invalid_hard = any("not valid" in w.lower() for w in result["warnings"])
    semantic_hard = any(
        ("semantic-all found contradicted claims" in w.lower()) or ("semantic-all grounded below threshold" in w.lower())
        for w in result["warnings"]
    )
    if missing_hard or invalid_hard or semantic_hard:
        result["status"] = "DENY"
    elif result["warnings"]:
        result["status"] = "UNCLEAR"
    else:
        result["status"] = "CONFIRM"

    score = 100
    if result["status"] == "DENY":
        # If semantic-all ran, retain an informative non-zero score; otherwise hard-zero.
        if semantic_item and not semantic_item.get("skipped", False):
            score = max(0, int(semantic_item.get("grounded_pct", 0)) - int(semantic_item.get("contradicted", 0)) * 40)
        else:
            score = 0
    else:
        for warning in result["warnings"]:
            w = warning.lower()
            if "manual judgment" in w:
                score -= 30
            elif "grounding concern" in w:
                score -= 20
            elif "below expected floor" in w:
                score -= 15
            else:
                score -= 10
    score = max(0, min(100, score))
    result["score_pct"] = score
    result["pass_fail"] = "PASS" if score >= 70 else "FAIL"

    return result


def render_markdown(base_name: str, project_dir: Path | None, rows: list[dict], semantic_result: dict[str, dict] | None, semantic_all_result: dict | None) -> str:
    lines: list[str] = []
    lines.append(f"# Prompt-vs-Output Review: {base_name}")
    lines.append("")
    lines.append(f"Project directory: `{project_dir}`" if project_dir else "Project directory: `(not provided)`")
    lines.append("")

    if semantic_result is not None:
        lines.append("## Semantic Grounding")
        if semantic_result.get("ok"):
            t = semantic_result.get("themes", {})
            l = semantic_result.get("lenses", {})
            if semantic_result.get("model_used"):
                lines.append(f"- Model used: {semantic_result.get('model_used')}")
            lines.append(f"- Themes questionable: {t.get('questionable', 0)}/{t.get('total', 0)}")
            lines.append(f"- Lenses questionable: {l.get('questionable', 0)}/{l.get('total', 0)}")
        else:
            lines.append(f"- Skipped: {semantic_result.get('error', 'unknown error')}")
        lines.append("")

    if semantic_all_result is not None:
        lines.append("## Semantic-All")
        if semantic_all_result.get("ok"):
            checked = 0
            passed = 0
            if semantic_all_result.get("model_used"):
                lines.append(f"- Model used: {semantic_all_result.get('model_used')}")
            for _k, item in semantic_all_result.get("items", {}).items():
                if item.get("skipped", False):
                    continue
                checked += 1
                if item.get("pass", False):
                    passed += 1
            lines.append(f"- Artifacts semantically checked: {checked}")
            lines.append(f"- Semantic PASS count: {passed}")
            lines.append(f"- Semantic FAIL count: {checked - passed}")
        else:
            lines.append(f"- Skipped: {semantic_all_result.get('error', 'unknown error')}")
        lines.append("")

    lines.append("## Summary")
    p = sum(1 for r in rows if r["pass_fail"] == "PASS")
    f = sum(1 for r in rows if r["pass_fail"] == "FAIL")
    avg = round(sum(r["score_pct"] for r in rows) / max(1, len(rows)))
    lines.append(f"- PASS: {p}")
    lines.append(f"- FAIL: {f}")
    lines.append(f"- Average score: {avg}%")
    lines.append("")

    lines.append("## Findings")
    for row in rows:
        lines.append(f"### {row['prompt']} -> {row['pass_fail']} ({row['score_pct']}%)")
        if row["artifact"]:
            lines.append(f"- Artifact: `{row['artifact']}`")
        if row["verification_method"]:
            lines.append(f"- How verified: {', '.join(row['verification_method'])}")
        if row["checks"]:
            lines.append(f"- Checks: {', '.join(row['checks'])}")
        if row["warnings"]:
            lines.append(f"- Warnings: {' | '.join(row['warnings'])}")
        if row["constraints"]:
            lines.append("- Prompt constraints (sample):")
            for item in row["constraints"][:4]:
                lines.append(f"  - {item}")
        if row["evidence"]:
            lines.append("- Evidence snippets:")
            for item in row["evidence"]:
                lines.append(f"  - {item}")
        if row["review_questions"]:
            lines.append("- Confirm/Deny questions:")
            for item in row["review_questions"][:2]:
                lines.append(f"  - {item}")
        lines.append("")
    return "\n".join(lines)


def resolve_project_dir(repo_root: Path, base_name: str | None, project_dir: str | None) -> Path | None:
    if project_dir:
        return Path(project_dir)
    if base_name:
        return repo_root / "projects" / base_name
    return None


def build_rules(include_legacy: bool, include_optional: bool) -> list[PromptRule]:
    rules = list(ACTIVE_PROMPT_RULES)
    if include_legacy:
        rules.extend(LEGACY_RULES)
    if not include_optional:
        rules = [r for r in rules if not r.optional]
    return rules


def looks_like_transcript_project_folder(folder: Path) -> bool:
    if not folder.is_dir():
        return False
    named_formatted = folder / f"{folder.name} - formatted.md"
    if named_formatted.exists():
        return True
    return any(folder.glob("* - formatted.md"))


def generate_report_for_project(
    repo_root: Path,
    rules: list[PromptRule],
    project_dir: Path,
    base_name: str,
    max_evidence_lines: int,
    semantic_check: bool,
    semantic_all: bool,
) -> str:
    prompt_dir = repo_root / "prompts"

    semantic_result = None
    if semantic_check:
        themes_artifact = resolve_artifact(project_dir, base_name, (" - structural-themes.md",))
        lenses_artifact = resolve_artifact(project_dir, base_name, (" - lenses-ranked.md",))
        semantic_result = run_semantic_grounding_check(
            repo_root=repo_root,
            project_dir=project_dir,
            base_name=base_name,
            themes_artifact=themes_artifact,
            lenses_artifact=lenses_artifact,
        )

    semantic_all_result = None
    if semantic_all:
        semantic_all_result = run_semantic_all_check(
            repo_root=repo_root,
            project_dir=project_dir,
            base_name=base_name,
            rules=rules,
        )

    rows: list[dict] = []
    for rule in rules:
        prompt_path = prompt_dir / rule.prompt_file
        prompt_text = read_text(prompt_path)
        artifact = resolve_artifact(project_dir, base_name, rule.artifact_suffixes)
        rows.append(
            evaluate(
                rule=rule,
                prompt_text=prompt_text,
                artifact_path=artifact,
                max_evidence_lines=max_evidence_lines,
                semantic_result=semantic_result,
                semantic_all_result=semantic_all_result,
            )
        )

    return render_markdown(base_name, project_dir, rows, semantic_result, semantic_all_result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Review trans-summary outputs against prompt intent.")
    parser.add_argument("--repo-root", default="/Users/davemini2/ProjectsLocal/projects/trans-summary", help="Path to trans-summary repository root.")
    parser.add_argument("--base-name", help="Transcript base name (folder name inside projects/).")
    parser.add_argument("--project-dir", help="Direct path to one transcript output folder.")
    parser.add_argument("--include-legacy", action="store_true", help="Include legacy/config-only prompt checks.")
    parser.add_argument("--include-optional", action="store_true", help="Include optional prompts (e.g., structured summary).")
    parser.add_argument("--semantic-check", action="store_true", help="Run cached transcript semantic grounding check for themes/lenses via API.")
    parser.add_argument("--semantic-all", action="store_true", help="Run semantic grounding checks for all generated artifacts (claim-level).")
    parser.add_argument("--max-evidence-lines", type=int, default=3, help="Evidence snippets per prompt item.")
    parser.add_argument("--output", help="Write markdown report to this path.")
    parser.add_argument("--scan-missing-reports", action="store_true", help="Scan transcript project folders and run only where report file is missing.")
    parser.add_argument("--scan-root", default="/Users/davemini2/transcripts/projects", help="Folder containing transcript project subfolders.")
    parser.add_argument("--report-name", default="output-review.md", help="Report filename to create/check inside each project folder during scan mode.")
    parser.add_argument("--dry-run", action="store_true", help="Show folders that would be processed without generating reports.")
    parser.add_argument("--max-folders", type=int, default=0, help="Optional limit for number of folders to process in scan mode (0 = all).")
    args = parser.parse_args()

    repo_root = Path(args.repo_root)
    rules = build_rules(args.include_legacy, args.include_optional)

    if args.scan_missing_reports:
        scan_root = Path(args.scan_root)
        if not scan_root.exists() or not scan_root.is_dir():
            print(f"Scan root not found or not a directory: {scan_root}")
            return 2

        candidates: list[Path] = []
        for p in sorted(scan_root.rglob("*")):
            if not p.is_dir():
                continue
            if not looks_like_transcript_project_folder(p):
                continue
            report_path = p / args.report_name
            if not report_path.exists():
                candidates.append(p)

        if args.max_folders and args.max_folders > 0:
            candidates = candidates[: args.max_folders]

        print(f"Found {len(candidates)} folder(s) missing `{args.report_name}`.")
        if args.dry_run:
            for p in candidates:
                print(f"DRY RUN: would process {p}")
            return 0

        processed = 0
        failed = 0
        for folder in candidates:
            base_name = folder.name
            try:
                report = generate_report_for_project(
                    repo_root=repo_root,
                    rules=rules,
                    project_dir=folder,
                    base_name=base_name,
                    max_evidence_lines=args.max_evidence_lines,
                    semantic_check=args.semantic_check,
                    semantic_all=args.semantic_all,
                )
                out = folder / args.report_name
                out.write_text(report, encoding="utf-8")
                processed += 1
                print(f"Wrote report: {out}")
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"FAILED: {folder} -> {exc}")
        print(f"Done. Processed={processed}, Failed={failed}")
        return 1 if failed else 0

    project_dir = resolve_project_dir(repo_root, args.base_name, args.project_dir)
    base_name = args.base_name or (Path(args.project_dir).name if args.project_dir else "(unspecified)")
    if project_dir is None:
        print("No project directory resolved. Use --project-dir, --base-name, or --scan-missing-reports.")
        return 2

    report = generate_report_for_project(
        repo_root=repo_root,
        rules=rules,
        project_dir=project_dir,
        base_name=base_name,
        max_evidence_lines=args.max_evidence_lines,
        semantic_check=args.semantic_check,
        semantic_all=args.semantic_all,
    )
    if args.output:
        out = Path(args.output)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report, encoding="utf-8")
        print(f"Wrote report: {out}")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
