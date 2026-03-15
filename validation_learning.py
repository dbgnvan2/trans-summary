"""Persistent learning helpers for initial transcript validation."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import config


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _clean_term(value: str) -> str:
    return " ".join((value or "").split()).strip()


def _memory_path() -> Path:
    return config.LOGS_DIR / config.VALIDATION_MEMORY_FILENAME


def _approved_terms_path() -> Path:
    return config.VALIDATION_APPROVED_TERMS_PATH


def load_approved_terms(path: Path | None = None) -> set[str]:
    """Load approved terms/phrases from the configured file."""
    target = path or _approved_terms_path()
    if not target.exists():
        return set()

    approved: set[str] = set()
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "=" in stripped:
            _, correct = stripped.split("=", 1)
            approved.add(_normalize_text(correct))
        else:
            approved.add(_normalize_text(stripped))
    return approved


def load_validation_aliases(path: Path | None = None) -> dict[str, str]:
    """Load deterministic alias corrections from the approved terms file."""
    target = path or _approved_terms_path()
    if not target.exists():
        return {}

    aliases: dict[str, str] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        wrong, correct = stripped.split("=", 1)
        wrong = _clean_term(wrong)
        correct = _clean_term(correct)
        if not wrong or not correct:
            continue
        aliases[wrong] = correct
    return aliases


def append_approved_terms(terms: list[str], path: Path | None = None) -> int:
    """Append newly approved terms/phrases to the configured file."""
    cleaned_terms = []
    existing = load_approved_terms(path)
    for term in terms:
        stripped = _clean_term(term)
        normalized = _normalize_text(stripped)
        if not stripped or not normalized or normalized in existing:
            continue
        existing.add(normalized)
        cleaned_terms.append(stripped)

    if not cleaned_terms:
        return 0

    target = path or _approved_terms_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for term in cleaned_terms:
            handle.write(term + "\n")
    return len(cleaned_terms)


def append_validation_aliases(
    aliases: list[tuple[str, str]],
    path: Path | None = None,
) -> int:
    """Append new wrong=correct alias pairs to the approved terms file."""
    target = path or _approved_terms_path()
    existing_aliases = {
        _normalize_text(wrong): _normalize_text(correct)
        for wrong, correct in load_validation_aliases(target).items()
    }

    cleaned_aliases: list[tuple[str, str]] = []
    for wrong, correct in aliases:
        wrong_clean = _clean_term(wrong)
        correct_clean = _clean_term(correct)
        wrong_norm = _normalize_text(wrong_clean)
        correct_norm = _normalize_text(correct_clean)
        if (
            not wrong_clean
            or not correct_clean
            or not wrong_norm
            or not correct_norm
            or wrong_norm == correct_norm
        ):
            continue
        if existing_aliases.get(wrong_norm) == correct_norm:
            continue
        existing_aliases[wrong_norm] = correct_norm
        cleaned_aliases.append((wrong_clean, correct_clean))

    if not cleaned_aliases:
        return 0

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        for wrong, correct in cleaned_aliases:
            handle.write(f"{wrong} = {correct}\n")
    return len(cleaned_aliases)


def replace_alias_occurrences(content: str, wrong: str, correct: str) -> tuple[str, int]:
    """Apply a deterministic alias replacement across the transcript."""
    wrong_clean = _clean_term(wrong)
    if not wrong_clean:
        return content, 0

    pattern = re.compile(rf"(?<!\w){re.escape(wrong_clean)}(?!\w)", flags=re.IGNORECASE)
    return pattern.subn(correct, content)


@dataclass
class FilteredFindings:
    findings: list[dict[str, Any]]
    suppressed_by_memory: int
    suppressed_by_approved_terms: int
    injected_aliases: int
    suppressed_by_error_type: int


class ValidationLearningMemory:
    """Stores repeatedly rejected suggestion pairs and suppresses them on future runs."""

    def __init__(
        self,
        path: Path | None = None,
        promotion_threshold: int = config.VALIDATION_MEMORY_PROMOTION_THRESHOLD,
        logger: logging.Logger | None = None,
    ):
        self.path = path or _memory_path()
        self.promotion_threshold = max(1, promotion_threshold)
        self.logger = logger or logging.getLogger(__name__)
        self.blocked_pairs: dict[str, dict[str, Any]] = {}
        self.pending_rejections: dict[str, dict[str, Any]] = {}
        self.promoted_this_run = 0
        self._dirty = False
        self._load()

    def _pair_key(self, original: str, suggestion: str) -> str:
        return f"{_normalize_text(original)}->{_normalize_text(suggestion)}"

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            blocked = payload.get("blocked_pairs", {})
            pending = payload.get("pending_rejections", {})
            if isinstance(blocked, dict):
                self.blocked_pairs = blocked
            if isinstance(pending, dict):
                self.pending_rejections = pending
        except Exception:
            self.logger.warning("Validation memory load failed: %s", self.path)

    def is_blocked(self, original: str, suggestion: str | None) -> bool:
        if not suggestion:
            return False
        return self._pair_key(original, suggestion) in self.blocked_pairs

    def record_rejection(
        self,
        original: str,
        suggestion: str | None,
        reason: str = "",
        source: str = "gui_review",
    ) -> None:
        if not suggestion:
            return

        original_norm = _normalize_text(original)
        suggestion_norm = _normalize_text(suggestion)
        if not original_norm or not suggestion_norm or original_norm == suggestion_norm:
            return

        key = f"{original_norm}->{suggestion_norm}"
        if key in self.blocked_pairs:
            entry = self.blocked_pairs[key]
            entry["count"] = int(entry.get("count", 0)) + 1
            entry["last_reason"] = reason
            entry["last_source"] = source
            entry["last_seen"] = datetime.utcnow().isoformat()
            self._dirty = True
            return

        entry = self.pending_rejections.get(key)
        if not isinstance(entry, dict):
            entry = {
                "original": original_norm,
                "suggestion": suggestion_norm,
                "count": 0,
                "first_reason": reason,
                "first_source": source,
            }
            self.pending_rejections[key] = entry

        entry["count"] = int(entry.get("count", 0)) + 1
        entry["last_reason"] = reason
        entry["last_source"] = source
        entry["last_seen"] = datetime.utcnow().isoformat()
        self._dirty = True

        if int(entry["count"]) >= self.promotion_threshold:
            self.blocked_pairs[key] = {
                "original": original_norm,
                "suggestion": suggestion_norm,
                "count": int(entry["count"]),
                "promoted_reason": reason,
                "promoted_source": source,
                "promoted_at": datetime.utcnow().isoformat(),
            }
            self.pending_rejections.pop(key, None)
            self.promoted_this_run += 1

    def save(self) -> None:
        if not self._dirty:
            return
        payload = {
            "blocked_pairs": self.blocked_pairs,
            "pending_rejections": self.pending_rejections,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def filter_validation_findings(
    findings: list[dict[str, Any]],
    transcript_text: str = "",
    logger: logging.Logger | None = None,
) -> FilteredFindings:
    """Inject deterministic aliases, then suppress findings by memory or approved terms."""
    approved_terms = load_approved_terms()
    aliases = load_validation_aliases()
    memory = ValidationLearningMemory(logger=logger)

    combined_findings = list(findings)
    injected_aliases = 0
    seen_pairs = {
        (
            _normalize_text(item.get("original_text", "")),
            _normalize_text(item.get("suggested_correction", "")),
        )
        for item in combined_findings
    }

    for wrong, correct in aliases.items():
        if not transcript_text:
            break
        pattern = re.compile(rf"(?<!\w){re.escape(wrong)}(?!\w)", flags=re.IGNORECASE)
        if not pattern.search(transcript_text):
            continue
        pair = (_normalize_text(wrong), _normalize_text(correct))
        if pair in seen_pairs:
            continue
        combined_findings.append(
            {
                "error_type": "alias",
                "original_text": wrong,
                "suggested_correction": correct,
                "confidence": "high",
                "reasoning": (
                    f"Deterministic alias from {Path(_approved_terms_path()).name}: "
                    f"{wrong} = {correct}"
                ),
            }
        )
        seen_pairs.add(pair)
        injected_aliases += 1

    filtered: list[dict[str, Any]] = []
    suppressed_by_memory = 0
    suppressed_by_approved_terms = 0
    suppressed_by_error_type = 0

    for finding in combined_findings:
        error_type = finding.get("error_type", "")
        original = finding.get("original_text", "")
        suggestion = finding.get("suggested_correction", "")
        if error_type and error_type not in config.VALIDATION_ERROR_TYPES:
            suppressed_by_error_type += 1
            continue
        if _normalize_text(original) in approved_terms:
            suppressed_by_approved_terms += 1
            continue
        if memory.is_blocked(original, suggestion):
            suppressed_by_memory += 1
            continue
        filtered.append(finding)

    if logger and (
        suppressed_by_memory
        or suppressed_by_approved_terms
        or injected_aliases
        or suppressed_by_error_type
    ):
        logger.info(
            "Validation learning: %d alias finding(s) injected, %d finding(s) suppressed via memory, %d via approved terms, %d via disallowed error type.",
            injected_aliases,
            suppressed_by_memory,
            suppressed_by_approved_terms,
            suppressed_by_error_type,
        )

    return FilteredFindings(
        findings=filtered,
        suppressed_by_memory=suppressed_by_memory,
        suppressed_by_approved_terms=suppressed_by_approved_terms,
        injected_aliases=injected_aliases,
        suppressed_by_error_type=suppressed_by_error_type,
    )


def record_validation_rejections(
    findings: list[dict[str, Any]],
    logger: logging.Logger | None = None,
) -> int:
    """Persist rejected findings to learning memory."""
    memory = ValidationLearningMemory(logger=logger)
    for finding in findings:
        memory.record_rejection(
            finding.get("original_text", ""),
            finding.get("suggested_correction", ""),
            reason=finding.get("reasoning", ""),
            source="gui_review",
        )
    memory.save()
    if logger and memory.promoted_this_run:
        logger.info(
            "Validation memory promoted %d blocked pair(s) this run.",
            memory.promoted_this_run,
        )
    return memory.promoted_this_run
