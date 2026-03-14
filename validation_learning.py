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


def _memory_path() -> Path:
    return config.LOGS_DIR / config.VALIDATION_MEMORY_FILENAME


def _approved_terms_path() -> Path:
    return config.TRANSCRIPTS_BASE / config.VALIDATION_APPROVED_TERMS_FILENAME


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
        approved.add(_normalize_text(stripped.split("=", 1)[0]))
    return approved


def append_approved_terms(terms: list[str], path: Path | None = None) -> int:
    """Append newly approved terms/phrases to the configured file."""
    cleaned_terms = []
    existing = load_approved_terms(path)
    for term in terms:
        stripped = " ".join((term or "").split()).strip()
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


@dataclass
class FilteredFindings:
    findings: list[dict[str, Any]]
    suppressed_by_memory: int
    suppressed_by_approved_terms: int


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
    logger: logging.Logger | None = None,
) -> FilteredFindings:
    """Suppress findings that are blocked by memory or approved terms."""
    approved_terms = load_approved_terms()
    memory = ValidationLearningMemory(logger=logger)

    filtered: list[dict[str, Any]] = []
    suppressed_by_memory = 0
    suppressed_by_approved_terms = 0

    for finding in findings:
        original = finding.get("original_text", "")
        suggestion = finding.get("suggested_correction", "")
        if _normalize_text(original) in approved_terms:
            suppressed_by_approved_terms += 1
            continue
        if memory.is_blocked(original, suggestion):
            suppressed_by_memory += 1
            continue
        filtered.append(finding)

    if logger and (suppressed_by_memory or suppressed_by_approved_terms):
        logger.info(
            "Suppressed %d finding(s) via validation memory and %d via approved terms.",
            suppressed_by_memory,
            suppressed_by_approved_terms,
        )

    return FilteredFindings(
        findings=filtered,
        suppressed_by_memory=suppressed_by_memory,
        suppressed_by_approved_terms=suppressed_by_approved_terms,
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
