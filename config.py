"""
Configuration for the transcript processing pipeline.
This module holds global variables for directory paths, which can be
updated by the GUI at runtime.

REFACTOR NOTE: This file now uses a Singleton pattern for settings.
Direct access to variables (e.g. config.SOURCE_DIR) is proxied to the singleton instance
to maintain backward compatibility while enabling safer state management.
"""

import json
import logging
import os
import sys
import uuid
from pathlib import Path
from typing import List, Union

import model_specs  # ADDED: Import model_specs

DEFAULT_VALIDATION_APPROVED_TERMS_FILENAME = "approve_terms.txt"


class ProjectSettings:
    """
    Singleton class to manage project settings and paths.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ProjectSettings, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if getattr(self, "_initialized", False):
            return

        # Default initialization
        self.TRANSCRIPTS_BASE = Path(os.getenv("TRANSCRIPTS_DIR", "."))
        self._update_derived_paths()

        # Initialize model variables
        self.DEFAULT_MODEL = "claude-sonnet-4-6"  # Primary generation model
        self.AUX_MODEL = "claude-haiku-4-5-20251001"      # Low-cost default for validation/light analysis
        self.FORMATTING_MODEL = "claude-haiku-4-5-20251001"  # Haiku sufficient for structural formatting
        self.VALIDATION_MODEL = "claude-haiku-4-5-20251001" # Cheaper model for validation
        
        self.runtime_settings = {}
        self._load_runtime_settings()

        self._initialized = True

    def _runtime_settings_path(self) -> Path:
        return self.LOGS_DIR / "runtime_settings.json"

    def _load_runtime_settings(self):
        """Load persisted runtime UI settings into the settings object."""
        path = self._runtime_settings_path()
        if not path.exists():
            self.runtime_settings = {}
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            logging.getLogger(__name__).warning(
                "runtime_settings.json unreadable (%s) — resetting to empty settings", e)
            self.runtime_settings = {}
            return

        # A valid-JSON NON-object (null / [] / 5 / "x" — e.g. a truncated write that
        # lands on `null`, or a hand-edit) parses cleanly but is not a settings dict.
        # Calling .get() on it below would raise AttributeError, and because the
        # singleton is built at module import (`settings = ProjectSettings()`), that
        # exception escapes `import config` and takes down the GUI and every pipeline
        # stage. Reset to {} instead of crashing (review C1 / P8 corrupt-state).
        if not isinstance(data, dict):
            logging.getLogger(__name__).warning(
                "runtime_settings.json is not a JSON object (got %s) — resetting to empty settings",
                type(data).__name__)
            self.runtime_settings = {}
            return
        self.runtime_settings = data

        default_source_dir = self.runtime_settings.get("default_source_dir")
        if default_source_dir and Path(default_source_dir).exists():
            self.set_source_dir_and_infer_base(default_source_dir)

        processed_dir = self.runtime_settings.get("default_processed_dir")
        if processed_dir and Path(processed_dir).exists():
            self.PROCESSED_DIR = Path(processed_dir)

        projects_dir = self.runtime_settings.get("default_projects_dir")
        if projects_dir and Path(projects_dir).exists():
            self.PROJECTS_DIR = Path(projects_dir)

        terms_path = self.runtime_settings.get("validation_approved_terms_path")
        if terms_path:
            self.VALIDATION_APPROVED_TERMS_PATH = Path(terms_path)

    def _save_runtime_settings(self):
        """Persist the current runtime settings dictionary to a file, ATOMICALLY.

        Write to a temp file in the same directory, then os.replace() it over the
        target — os.replace is atomic on POSIX and Windows, so a crash / disk-full /
        concurrent write can never leave a half-written file that the loader would then
        discard as corrupt, zeroing the user's settings (review H3 / P8). A leftover
        temp file from a failed write is cleaned up rather than left behind.
        """
        path = self._runtime_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self.runtime_settings, indent=2, sort_keys=True)
        # uuid in the temp name so two concurrent saves (across processes OR threads)
        # never collide on the same temp file (review sweep #3a).
        tmp = path.with_name(f"{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            tmp.write_text(data, encoding="utf-8")
            os.replace(tmp, path)
        finally:
            if tmp.exists():
                try:
                    tmp.unlink()
                except OSError:
                    pass


    def _update_derived_paths(self):
        """Update paths derived from TRANSCRIPTS_BASE."""
        self.SOURCE_DIR = self.TRANSCRIPTS_BASE / "source"
        self.PROCESSED_DIR = self.TRANSCRIPTS_BASE / "processed"
        self.PROJECTS_DIR = self.TRANSCRIPTS_BASE / "projects"
        self.PROMPTS_DIR = Path(__file__).parent / "prompts"
        self.LOGS_DIR = Path(__file__).parent / "logs"
        current_terms_path = getattr(self, "VALIDATION_APPROVED_TERMS_PATH", None)
        if current_terms_path is None:
            self.VALIDATION_APPROVED_TERMS_PATH = (
                self.TRANSCRIPTS_BASE / DEFAULT_VALIDATION_APPROVED_TERMS_FILENAME
            )

    def set_transcripts_base(self, path: Union[str, Path]):
        """Update the base directory for transcripts and all related paths."""
        self.TRANSCRIPTS_BASE = Path(path)
        self._update_derived_paths()

    def set_source_dir_and_infer_base(self, path: Union[str, Path]):
        """Set the source directory directly and infer the base from its parent."""
        self.SOURCE_DIR = Path(path)
        self.TRANSCRIPTS_BASE = self.SOURCE_DIR.parent
        self.PROMPTS_DIR = Path(__file__).parent / "prompts"
        self.LOGS_DIR = Path(__file__).parent / "logs"
        self.VALIDATION_APPROVED_TERMS_PATH = (
            self.TRANSCRIPTS_BASE / DEFAULT_VALIDATION_APPROVED_TERMS_FILENAME
        )
        # Use saved overrides if present, otherwise derive from base
        processed_override = self.runtime_settings.get("default_processed_dir")
        self.PROCESSED_DIR = Path(processed_override) if processed_override else self.TRANSCRIPTS_BASE / "processed"
        projects_override = self.runtime_settings.get("default_projects_dir")
        self.PROJECTS_DIR = Path(projects_override) if projects_override else self.TRANSCRIPTS_BASE / "projects"

    def set_validation_approved_terms_path(self, path: Union[str, Path, None]):
        """Set the active validation approved-terms file."""
        if path is None:
            new_path = self.TRANSCRIPTS_BASE / DEFAULT_VALIDATION_APPROVED_TERMS_FILENAME
            self.VALIDATION_APPROVED_TERMS_PATH = new_path
            self.runtime_settings.pop("validation_approved_terms_path", None)
        else:
            self.VALIDATION_APPROVED_TERMS_PATH = Path(path)
            self.runtime_settings["validation_approved_terms_path"] = str(path)
        self._save_runtime_settings()

    def set_default_source_dir(self, path: Union[str, Path, None]):
        """Save or clear the default source directory.

        Invariant: the auto-load default is always present in the favorites list
        (so it shows with a ★). Every path that sets a default goes through here,
        so favorites can't drift from the default (FD.4)."""
        if path:
            self.runtime_settings["default_source_dir"] = str(path)
            favs = self.runtime_settings.setdefault("source_dir_favorites", [])
            if str(path) not in favs:
                favs.append(str(path))
        else:
            self.runtime_settings.pop("default_source_dir", None)
        self._save_runtime_settings()

    def get_source_dir_favorites(self):
        """Return the saved list of favorite source directories (a copy)."""
        return list(self.runtime_settings.get("source_dir_favorites", []))

    def add_source_dir_favorite(self, path):
        """Add a source directory to the favorites list (dedup, order-preserving)."""
        path = str(path)
        favs = self.runtime_settings.setdefault("source_dir_favorites", [])
        if path not in favs:
            favs.append(path)
            self._save_runtime_settings()

    def remove_source_dir_favorite(self, path):
        """Remove a source directory from favorites; if it was the auto-load
        default, clear that too so a removed favorite can't still load on start."""
        path = str(path)
        favs = self.runtime_settings.get("source_dir_favorites", [])
        if path in favs:
            favs.remove(path)
            if self.runtime_settings.get("default_source_dir") == path:
                self.runtime_settings.pop("default_source_dir", None)
            self._save_runtime_settings()

    def set_default_processed_dir(self, path: Union[str, Path, None]):
        """Save or clear the default processed directory."""
        if path:
            self.PROCESSED_DIR = Path(path)
            self.runtime_settings["default_processed_dir"] = str(path)
        else:
            self.runtime_settings.pop("default_processed_dir", None)
            self.PROCESSED_DIR = self.TRANSCRIPTS_BASE / "processed"
        self._save_runtime_settings()

    def set_default_projects_dir(self, path: Union[str, Path, None]):
        """Save or clear the default projects directory."""
        if path:
            self.PROJECTS_DIR = Path(path)
            self.runtime_settings["default_projects_dir"] = str(path)
        else:
            self.runtime_settings.pop("default_projects_dir", None)
            self.PROJECTS_DIR = self.TRANSCRIPTS_BASE / "projects"
        self._save_runtime_settings()

    def save_stage_selection(self, name: str, stages, include_bowen_core: bool = True,
                              include_emphasis_core: bool = True):
        """Save a named stage selection (stage keys + core modifier flags)."""
        selections = self.runtime_settings.setdefault("stage_selections", {})
        selections[name] = {
            "stages": list(stages),
            "include_bowen_core": include_bowen_core,
            "include_emphasis_core": include_emphasis_core,
        }
        self._save_runtime_settings()

    def delete_stage_selection(self, name: str):
        """Delete a named stage selection, clearing the default pointer if it pointed here."""
        selections = self.runtime_settings.get("stage_selections", {})
        selections.pop(name, None)
        if self.runtime_settings.get("default_stage_selection") == name:
            self.runtime_settings.pop("default_stage_selection", None)
        self._save_runtime_settings()

    def get_stage_selections(self) -> dict:
        """Return all saved stage selections, keyed by name."""
        return self.runtime_settings.get("stage_selections", {})

    def set_default_stage_selection(self, name: Union[str, None]):
        """Save or clear the default stage selection name."""
        if name:
            self.runtime_settings["default_stage_selection"] = name
        else:
            self.runtime_settings.pop("default_stage_selection", None)
        self._save_runtime_settings()

    def get_default_stage_selection(self):
        """Return the default stage selection name, or None if unset."""
        return self.runtime_settings.get("default_stage_selection")

    # ADDED: Methods to dynamically get and set model names
    def get_all_model_names(self) -> list[str]:
        """Returns a list of all model names from model_specs.PRICING."""
        return sorted(model_specs.PRICING.keys())

    def set_default_model(self, model_name: str):
        if model_name in model_specs.PRICING:
            self.DEFAULT_MODEL = model_name
        else:
            raise ValueError(
                f"Model '{model_name}' not found in model_specs.PRICING.")

    def set_aux_model(self, model_name: str):
        if model_name in model_specs.PRICING:
            self.AUX_MODEL = model_name
        else:
            raise ValueError(
                f"Model '{model_name}' not found in model_specs.PRICING.")

    def set_formatting_model(self, model_name: str):
        if model_name in model_specs.PRICING:
            self.FORMATTING_MODEL = model_name
        else:
            raise ValueError(
                f"Model '{model_name}' not found in model_specs.PRICING.")


# Initialize the singleton
settings = ProjectSettings()

# ============================================================================
# BACKWARD COMPATIBILITY PROXIES
# ============================================================================
# These properties allow existing code to continue using `config.SOURCE_DIR`
# while actually reading from the singleton `settings` object.


def __getattr__(name):
    # Only proxy for non-existent attributes to allow direct access to
    # attributes already defined on the module (like SUFFIX_FORMATTED)
    # and to the model variables.
    # ADDED explicit check for model variables
    if name in ["DEFAULT_MODEL", "AUX_MODEL", "FORMATTING_MODEL", "VALIDATION_MODEL"]:
        return getattr(settings, name)
    if hasattr(settings, name):
        return getattr(settings, name)
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")


# Explicitly define for static analysis tools (optional but good practice)
TRANSCRIPTS_BASE = settings.TRANSCRIPTS_BASE
SOURCE_DIR = settings.SOURCE_DIR
PROCESSED_DIR = settings.PROCESSED_DIR
PROJECTS_DIR = settings.PROJECTS_DIR
PROMPTS_DIR = settings.PROMPTS_DIR
LOGS_DIR = settings.LOGS_DIR
VALIDATION_APPROVED_TERMS_PATH = settings.VALIDATION_APPROVED_TERMS_PATH

# ADDED: Expose model variables as globals for backward compatibility and direct access
DEFAULT_MODEL = settings.DEFAULT_MODEL
AUX_MODEL = settings.AUX_MODEL
FORMATTING_MODEL = settings.FORMATTING_MODEL
VALIDATION_MODEL = settings.VALIDATION_MODEL


def set_transcripts_base(path: Union[str, Path]):
    """Global function to update the singleton settings."""
    settings.set_transcripts_base(path)
    # Update module-level globals to reflect the change for code that imported them directly
    # (Note: Code that did `from config import SOURCE_DIR` will still have the OLD value.
    # This is why `import config; config.SOURCE_DIR` is preferred.)
    global TRANSCRIPTS_BASE, SOURCE_DIR, PROCESSED_DIR, PROJECTS_DIR, VALIDATION_APPROVED_TERMS_PATH
    # ADDED: Make model variables global
    global DEFAULT_MODEL, AUX_MODEL, FORMATTING_MODEL
    TRANSCRIPTS_BASE = settings.TRANSCRIPTS_BASE
    SOURCE_DIR = settings.SOURCE_DIR
    PROCESSED_DIR = settings.PROCESSED_DIR
    PROJECTS_DIR = settings.PROJECTS_DIR
    VALIDATION_APPROVED_TERMS_PATH = settings.VALIDATION_APPROVED_TERMS_PATH
    # Update global model variables from settings object
    DEFAULT_MODEL = settings.DEFAULT_MODEL
    AUX_MODEL = settings.AUX_MODEL
    FORMATTING_MODEL = settings.FORMATTING_MODEL


def set_source_dir_and_infer_base(path: Union[str, Path]):
    """Global function to update the source directory directly."""
    settings.set_source_dir_and_infer_base(path)
    global TRANSCRIPTS_BASE, SOURCE_DIR, PROCESSED_DIR, PROJECTS_DIR, VALIDATION_APPROVED_TERMS_PATH
    TRANSCRIPTS_BASE = settings.TRANSCRIPTS_BASE
    SOURCE_DIR = settings.SOURCE_DIR
    PROCESSED_DIR = settings.PROCESSED_DIR
    PROJECTS_DIR = settings.PROJECTS_DIR
    VALIDATION_APPROVED_TERMS_PATH = settings.VALIDATION_APPROVED_TERMS_PATH


def set_validation_approved_terms_path(path: Union[str, Path, None]):
    """Global function to update the active validation approved-terms file."""
    settings.set_validation_approved_terms_path(path)
    global VALIDATION_APPROVED_TERMS_PATH
    VALIDATION_APPROVED_TERMS_PATH = settings.VALIDATION_APPROVED_TERMS_PATH


def set_default_source_dir(path: Union[str, Path, None]):
    """Global function to save or clear the default source directory."""
    settings.set_default_source_dir(path)


def get_source_dir_favorites():
    """Global function to retrieve the favorite source directories list."""
    return settings.get_source_dir_favorites()


def add_source_dir_favorite(path):
    """Global function to add a source directory to favorites."""
    settings.add_source_dir_favorite(path)


def remove_source_dir_favorite(path):
    """Global function to remove a source directory from favorites."""
    settings.remove_source_dir_favorite(path)


def set_default_processed_dir(path: Union[str, Path, None]):
    """Global function to save or clear the default processed directory."""
    settings.set_default_processed_dir(path)
    global PROCESSED_DIR
    PROCESSED_DIR = settings.PROCESSED_DIR


def set_default_projects_dir(path: Union[str, Path, None]):
    """Global function to save or clear the default projects directory."""
    settings.set_default_projects_dir(path)
    global PROJECTS_DIR
    PROJECTS_DIR = settings.PROJECTS_DIR


def save_stage_selection(name: str, stages, include_bowen_core: bool = True,
                          include_emphasis_core: bool = True):
    """Global function to save a named stage selection."""
    settings.save_stage_selection(name, stages, include_bowen_core, include_emphasis_core)


def delete_stage_selection(name: str):
    """Global function to delete a named stage selection."""
    settings.delete_stage_selection(name)


def get_stage_selections():
    """Global function to retrieve all saved stage selections."""
    return settings.get_stage_selections()


def set_default_stage_selection(name: Union[str, None]):
    """Global function to save or clear the default stage selection."""
    settings.set_default_stage_selection(name)


def get_default_stage_selection():
    """Global function to retrieve the default stage selection name."""
    return settings.get_default_stage_selection()


# ============================================================================
# CONSTANTS (Stateless)
# ============================================================================

# File Suffixes
SUFFIX_FORMATTED = " - formatted.md"
SUFFIX_YAML = " - yaml.md"
SUFFIX_STRUCTURAL_THEMES = " - structural-themes.md"
SUFFIX_INTERPRETIVE_THEMES = " - interpretive-themes.md"
SUFFIX_TOPICS = " - topics.md"
SUFFIX_LENSES = " - lenses-ranked.md"
SUFFIX_KEY_TERMS = " - key-terms.md"
SUFFIX_BOWEN = " - bowen-references.md"
SUFFIX_EMPHASIS = " - emphasis-items.md"
SUFFIX_EMPHASIS_SCORED = " - emphasis-scored.md"
SUFFIX_ABSTRACT_INIT = " - abstract-initial.md"
SUFFIX_SUMMARY_INIT = " - summary-initial.md"
SUFFIX_SUMMARY_GEN = " - summary-generated.md"
SUFFIX_SUMMARY_VAL = " - summary-validation.txt"
SUFFIX_ABSTRACT_GEN = " - abstract-generated.md"
SUFFIX_ABSTRACT_VAL = " - abstract-validation.txt"
SUFFIX_KEY_TERMS_VAL = " - key-terms-validation.md"
SUFFIX_TOPICS_VAL = " - topics-validation.md"
SUFFIX_BLOG = " - blog.md"
SUFFIX_OVERVIEW = " - overview.md"
SUFFIX_WEBPAGE = ".html"
SUFFIX_WEBPAGE_SIMPLE = " - simple.html"
SUFFIX_PDF = ".pdf"
SUFFIX_HEADER_VAL_REPORT = " - header-validation.md"
SUFFIX_VOICE_AUDIT = " - voice-audit.json"
SUFFIX_RUN_MANIFEST = " - run-manifest.json"
SUFFIX_PUBLISH_BLOCKED = " - PUBLISH-BLOCKED.txt"
SUFFIX_ZIP = ".zip"
# MD-collection bundle export (docs/spec_bundle_export_2026-07-16.md). Distinct
# from SUFFIX_PDF/SUFFIX_WEBPAGE so the plain-concatenation bundle never clobbers
# the designed web/pdf artifacts.
SUFFIX_BUNDLE_DOCX = " - bundle.docx"
SUFFIX_BUNDLE_PDF = " - bundle.pdf"
# Published bundle artifacts a BLOCK must not leave on disk as if current (M1.B.2/F4).
PUBLISHED_BUNDLE_SUFFIXES = [
    SUFFIX_WEBPAGE, SUFFIX_WEBPAGE_SIMPLE, SUFFIX_PDF, SUFFIX_ZIP,
    SUFFIX_BUNDLE_DOCX, SUFFIX_BUNDLE_PDF,
]

# Ordered sections for the MD-collection bundle export (SR-adjacent; see
# docs/spec_bundle_export_2026-07-16.md#BE.2). Each entry names the config
# suffix attr of a per-run MD artifact, a human heading, and whether it is
# required. Kept as data (editorial content in config, not code) so the section
# set/order/titles are editable without touching the exporter. `required`
# sections that are absent make the bundle fail; optional ones are skipped with
# an "N of M" log line (P2).
# Each section has a stable `key` (used as the dialog checkbox id), a `heading`,
# and `suffix_attrs`: an ordered candidate list -- the first artifact that exists
# AND is non-empty is used (so the transcript is the Formatted OR YAML file,
# whichever is present). strip_frontmatter is set only where a candidate carries
# YAML frontmatter (harmless on the formatted file, which has none).
BUNDLE_SECTIONS = [
    # Abstract goes FIRST and on its own page (page_break_after) when present.
    {"key": "abstract", "heading": "Abstract",
     "suffix_attrs": ["SUFFIX_ABSTRACT_GEN"], "required": False,
     "page_break_after": True},
    {"key": "transcript", "heading": "Transcript (Format/YAML)",
     "suffix_attrs": ["SUFFIX_FORMATTED", "SUFFIX_YAML"],
     "required": True, "strip_frontmatter": True},
    {"key": "topics", "heading": "Topics",
     "suffix_attrs": ["SUFFIX_TOPICS"], "required": False},
    {"key": "emphasis", "heading": "Emphasis",
     "suffix_attrs": ["SUFFIX_EMPHASIS_SCORED"], "required": False},
    {"key": "bowen", "heading": "Bowen References",
     "suffix_attrs": ["SUFFIX_BOWEN"], "required": False},
]
# Default format for the bundle run-stage and the post-run dialog's initial
# selection. "pdf" works out of the box (WeasyPrint); "docx" needs pandoc.
BUNDLE_DEFAULT_FORMAT = "pdf"

# ============================================================================
# RELEASE GATE POLICY (M1.B — spec_unattended_robustness_2026-07-15.md)
# ============================================================================
# Which check FAILs block publication vs. warn-and-ship. Elected 2026-07-15
# (conservative net): a fabricated/ungrounded entity blocks; a transient ERROR
# blocks (fail-closed — an unverified run must not publish, P1); everything else
# WARNs until proven necessary. Flip a check into GATE_BLOCKING_CHECKS to make it
# a hard blocker.
#   artifact_contracts (M3, added 2026-07-15): a structured artifact that violates
#   its schema is producer/consumer format drift (P19). U4 requires drift to be a
#   HARD error, not a silent zero, so it blocks — a legitimately-empty artifact
#   validates as an empty object and does not trip it.
#   faithfulness (M2, added 2026-07-15): an unentailed claim in a narrative artifact
#   is a fluent hallucination (U2). Blocks when enabled; a PASS no-op while
#   FAITHFULNESS_JUDGE_ENABLED is False (awaiting M2.B calibration), so it does not
#   affect the deterministic gate until turned on.
#   theme_grounding (2026-07-15): an ungrounded theme (built on fabricated subject
#   matter) is a hallucination in a published artifact (U2). Blocks when enabled; a
#   PASS no-op while THEME_JUDGE_ENABLED is False, so it does not affect the gate
#   until armed.
GATE_BLOCKING_CHECKS = {"entity_grounding", "artifact_contracts", "faithfulness",
                        "theme_grounding"}
GATE_ERROR_BLOCKS = True
# Artifacts whose proper names must be grounded in the source for the BLOCKING
# entity check (M4.C). Scoped to the ABSTRACT only, on purpose: the name detector
# was calibrated on abstract prose (0 false positives across 3 real runs, and it
# catches the shipped 'Luciano Malorni'). Synthesized artifacts (blog, themes,
# topics, key-terms) carry Title-Case HEADINGS and CONCEPT phrases the detector
# can't tell from names ("Key Takeaways", "Role Absorption") — scanning them as a
# BLOCKER would false-BLOCK good runs (a hard stop). Grounding those needs the
# semantic judge (M2, deferred), not this lexical detector.
GATE_ENTITY_ARTIFACT_SUFFIXES = [
    SUFFIX_ABSTRACT_GEN,
]
# Broader set for the WARN-only cross-artifact consistency check (M4.D). A false
# positive here is advisory noise, not a hard stop, so it can safely scan the
# synthesized artifacts the BLOCKER above must avoid.
GATE_CONSISTENCY_ARTIFACT_SUFFIXES = [
    SUFFIX_ABSTRACT_GEN,
    SUFFIX_OVERVIEW,
    SUFFIX_BLOG,
    SUFFIX_STRUCTURAL_THEMES,
    SUFFIX_INTERPRETIVE_THEMES,
    SUFFIX_TOPICS,
    SUFFIX_KEY_TERMS,
]
# Artifacts a complete run is expected to have (M5.B). A missing/empty one is a
# WARN (named) — not a hard block, per the elected entity-only blocking policy;
# a missing SOURCE still hard-blocks via entity_grounding's ERROR (can't verify).
# Flip "required_artifacts" into GATE_BLOCKING_CHECKS to make completeness a gate.
GATE_REQUIRED_ARTIFACT_SUFFIXES = [
    SUFFIX_FORMATTED,
    SUFFIX_ABSTRACT_GEN,
    SUFFIX_TOPICS,
    SUFFIX_STRUCTURAL_THEMES,
    SUFFIX_INTERPRETIVE_THEMES,
    SUFFIX_KEY_TERMS,
]

# ============================================================================
# M2 — SEMANTIC FAITHFULNESS JUDGE (spec_unattended_robustness_2026-07-15.md §M2)
# ============================================================================
# Claim-level entailment check for NARRATIVE artifacts — catches a fluent
# hallucination the lexical checks can't. Gated behind an enable flag (strict mode)
# until calibrated on the gold set; when enabled, an unentailed claim FAILs and the
# judge's own error is ERROR (both blocking per U2 — see GATE_BLOCKING_CHECKS).
# ARMED 2026-07-15. Calibrated on REAL prose artifacts (not just isolated claims —
# the P10 fix): claim-level gold recall/precision 1.0; the 3 real abstracts judged
# correctly (roots_bowen PASS; where_roots FAIL naming the real 'Luciano Malorni'
# fabrication; dave_g FAIL on a genuine over-reach); an injected fabrication caught.
# Scoped to PROSE only (themes excluded — interpretive by design). Policy: Hard BLOCK
# (user-elected) — any unentailed claim OR a judge error blocks publish (fail-closed).
# The unit suite forces this OFF via a conftest autouse fixture (deterministic +
# offline); the enabled path is exercised with a mocked judge. Requires a resolvable
# Anthropic key (env or the shared ~/.config/llm/keys.json store).
FAITHFULNESS_JUDGE_ENABLED = True
# Judge model: PINNED to the explicit version the judge was CALIBRATED on — NOT
# aliased to DEFAULT_MODEL. A central DEFAULT_MODEL bump must not silently move the
# armed judge onto an un-recalibrated model (P6: the arming decision trusts a
# calibration artifact tied to this exact model). When changing it, re-run
# tests/test_faithfulness_calibration.py and confirm the bars still pass.
FAITHFULNESS_JUDGE_MODEL = "claude-sonnet-4-6"
FAITHFULNESS_JUDGE_MAX_TOKENS = 4096
# A claim shorter than this carries no verifiable assertion (heading fragments,
# stray tokens) and is skipped by claim extraction (unless it states a concrete
# specific — a number or a proper noun).
FAITHFULNESS_MIN_CLAIM_CHARS = 25
# Structured-artifact SCAFFOLDING / META field labels whose line is NOT a claim
# about the source and must be skipped by claim extraction (esp. the themes
# artifacts). These are the model's own meta-commentary or document boilerplate,
# not assertions about the transcript, so judging them for source-faithfulness
# produces false "unsupported" verdicts (e.g. a "Coverage / role: ~55-60%"
# estimate). Editorial list -> config, not code (rule 9). Matched case-insensitively
# against the text before the first colon on a line.
FAITHFULNESS_SKIP_LINE_LABELS = [
    "document", "prompt version used", "date processed", "source document",
    "coverage", "coverage / role", "key evidence", "nested under structural themes",
    "nested under", "lens fuel value", "lens fuel", "status",
]
# GENERIC scaffolding field-labels that legitimately PREFIX real content on a line
# ("Description: <claim>") and should be STRIPPED so the claim itself is judged.
# Unlike FAITHFULNESS_SKIP_LINE_LABELS (which drops the whole line), these keep the
# remainder. ONLY generic labels that prefix a full sentence belong here — NEVER a
# proper noun, a number, or an attribution/citation label ("reference", "source"):
# a prefix like "Stanford study:" or "2019 report:" must NOT be stripped, or the
# fabricated attribution rides through the armed faithfulness judge UNJUDGED (gate
# bypass; see faithfulness_judge.extract_claims / review H11 / P7 / P20). Editorial
# list -> config, not code (rule 9). Matched case-insensitively on the text before
# the first colon.
FAITHFULNESS_STRIP_LINE_LABEL_PREFIXES = [
    "description", "summary", "note", "notes", "overview", "context",
    "background", "example", "explanation", "detail", "details", "point",
    "takeaway", "rationale", "reason", "purpose", "clarification", "caveat",
    "definition", "observation",
]
# Narrative artifacts the judge audits: PROSE SUMMARIES that must stay faithful to
# the source. Themes are DELIBERATELY EXCLUDED — a real-artifact smoke test
# (2026-07-15) showed structural/interpretive themes are interpretive BY DESIGN
# (they name patterns and apply theoretical frames like "Bowen theory" that aren't
# literally in the transcript), so a source-ENTAILMENT check false-flags ~30/40 of
# their claims as "unsupported". Themes are instead covered by a DIFFERENT check —
# the theme GROUNDING judge below ("is this a reasonable interpretation of real
# content?" not "is it stated?"). Spec §M2.A lists themes; this split is the
# finding-driven correction.
FAITHFULNESS_ARTIFACT_SUFFIXES = [
    SUFFIX_ABSTRACT_GEN,
    SUFFIX_SUMMARY_GEN,
    SUFFIX_OVERVIEW,
    SUFFIX_BLOG,
]
# M2.B gold-set gate: the judge ships only if it clears these on the curated set.
# Recall on the dangerous class (contradicted+unsupported) is the load-bearing bar —
# the judge must almost never wave a fabrication through.
FAITHFULNESS_MIN_RECALL_UNFAITHFUL = 0.90
FAITHFULNESS_MIN_PRECISION_UNFAITHFUL = 0.70

# ---- Theme GROUNDING judge (interpretive artifacts) ----
# A separate judge for structural/interpretive THEMES: it asks whether a theme is a
# GROUNDED interpretation (its subject matter appears in / follows from the source),
# NOT whether it is literally stated — so it passes legitimate interpretation and
# FAILs a theme built on fabricated subject matter. Same fail-closed/Hard-BLOCK
# posture as the faithfulness judge; pinned to the calibrated model.
# ARMED 2026-07-15. Calibrated on REAL theme artifacts (the production extraction
# path): all 20 real themes -> grounded; all 8 curated fabricated/contradicting themes
# -> ungrounded (recall 1.0 / precision 1.0). Same fail-closed Hard-BLOCK posture as
# the faithfulness judge; forced OFF in the unit suite via the root-conftest fixture.
THEME_JUDGE_ENABLED = True
THEME_JUDGE_MODEL = "claude-sonnet-4-6"
THEME_ARTIFACT_SUFFIXES = [
    SUFFIX_STRUCTURAL_THEMES,
    SUFFIX_INTERPRETIVE_THEMES,
]
# The theme judge ships only if it clears these on the curated theme gold set
# (recall on the UNGROUNDED class is load-bearing — a fabricated theme must not pass).
THEME_JUDGE_MIN_RECALL_UNGROUNDED = 0.90
THEME_JUDGE_MIN_PRECISION_UNGROUNDED = 0.70

# Distinct sentinel for a TRANSIENT/config failure of opening-purpose extraction
# (no API key, prompt file missing, API error) — must NOT be confused with a
# genuine "speaker did not state a purpose" (which demotes the check to optional).
# A transient failure keeps the purpose check REQUIRED so validation can't silently
# pass on an unverified purpose (A10/P1). Compared by-value; keep stable.
PURPOSE_EXTRACTION_FAILED = "Speaker's purpose UNDETERMINED - extraction failed (retryable)"

# Conclusion-indicator phrases for extract_closing_conclusion (editorial — rule #9:
# content, not code). Each is a regex fragment matched (case-insensitively) against
# the closing sections' text. NOTE: this list is deliberately narrow — a real closing
# that uses none of these phrases returns "No explicit conclusion stated" (a recall
# gap tracked in TODO.md, not a correctness bug).
ABSTRACT_CONCLUSION_PATTERNS = [
    r"I think we can safely say[^.]+\.",
    r"in conclusion[^.]+\.",
    r"to conclude[^.]+\.",
    r"the answer[^.]+\.",
    r"I conclude[^.]+\.",
    r"this suggests[^.]+\.",
]

# Theme-artifact scaffolding labels (editorial — rule #9: content, not code).
# Section headers/roll-ups that appear in structural/interpretive theme files but
# are NOT themes. Compared case-insensitively against a candidate theme name.
# Used by transcript_utils.is_scaffolding_theme_name. See TODO.md A1/A2/A3.
THEME_SCAFFOLDING_LABELS = frozenset(
    {"summary paragraph", "summary", "conclusion"}
)

# Validation learning artifacts
VALIDATION_MEMORY_FILENAME = "validation_memory.json"
VALIDATION_APPROVED_TERMS_FILENAME = DEFAULT_VALIDATION_APPROVED_TERMS_FILENAME
VALIDATION_MEMORY_PROMOTION_THRESHOLD = 3

# Model variables live on ProjectSettings (DEFAULT_MODEL / AUX_MODEL /
# FORMATTING_MODEL / VALIDATION_MODEL, set in __init__) and are proxied as module
# globals. See __init__ for the current default values — they are NOT duplicated
# here (the old inline "Defaults:" list had drifted from the code; review M5/L4).

# Default Summary Word Count
# Set to 650 - Claude 3.7 Sonnet tends to generate slightly more
# Typically results in 700-900 word summaries
DEFAULT_SUMMARY_WORD_COUNT = 650

# Token Limits
# Sized from observed peak output tokens on 10K+ word transcripts:
#   Formatting:  ~14,400 observed → 20,000 (safe headroom for very long transcripts)
#   Extraction:  ~5,200 observed  →  8,192
#   Summary/Abstract: ~3,300 observed → 4,096 (650-word target ≈ 900 tokens)
#   Validation/Audit: ~2,300 observed → 4,096
MAX_TOKENS_FORMATTING = 20000
MAX_TOKENS_SUMMARY = 4096
MAX_TOKENS_EXTRACTION = 8192
MAX_TOKENS_AUDIT = 4096
MAX_TOKENS_HEADER_VALIDATION = 4096
MAX_TOKENS_VALIDATION_VERIFY = 4096
MAX_TOKENS_REVIEW_SEMANTIC = 8192
MAX_TOKENS_MODEL_PROBE = 32
MAX_CONTEXT_TOKENS = 200000

# Model output caps for known low-limit models.
MODEL_OUTPUT_TOKEN_LIMITS = {
    "claude-3-5-haiku-20241022": 8192,
}

# Temperature Settings
TEMP_STRICT = 0.0
TEMP_ANALYSIS = 0.2
TEMP_BALANCED = 0.3
TEMP_CREATIVE = 0.4

# Timeouts (seconds)
TIMEOUT_FORMATTING = 1200  # 20 minutes
TIMEOUT_SUMMARY = 900  # 15 minutes
TIMEOUT_DEFAULT = 300  # 5 minutes

# Prompt Filenames
PROMPT_FORMATTING_HEADER_VALIDATION_FILENAME = (
    "Transcript Formatting Headers Validation Prompt 12.md"
)
PROMPT_FORMATTING_FILENAME = "Transcript Formatting Prompt v12-Lite.md"
PROMPT_EXTRACTS_FILENAME = "Transcript Summary Key Items v1.md"
PROMPT_TOPICS_FILENAME = "Transcript Summary - Topics v1.md"
PROMPT_STRUCTURAL_THEMES_FILENAME = "Transcript Summary - Structural Themes v2.md"
PROMPT_INTERPRETIVE_THEMES_FILENAME = "Transcript Summary - Interpretive Themes v1.md"
PROMPT_LENS_GENERATION_FILENAME = "Transcript Summary - Lens Generation v1.md"
PROMPT_THEME_LENS_VALIDATION_FILENAME = "Transcript Summary - Theme Lens Validation v1.md"
PROMPT_KEY_TERMS_FILENAME = "Transcript Summary Key Terms v1.md"
PROMPT_BLOG_FILENAME = "Transcript Summary Blog Post v1.md"
PROMPT_OVERVIEW_FILENAME = "Transcript Summary Overview Post v1.md"
PROMPT_ABSTRACT_VALIDATION_FILENAME = "abstract_quality_assessment_prompt_v2.md"
PROMPT_VOICE_AUDIT_FILENAME = "Transcript Voice Audit Prompt v1.md"
PROMPT_STRUCTURED_SUMMARY_FILENAME = "Summary Generation Prompt v1.md"
PROMPT_STRUCTURED_ABSTRACT_FILENAME = "Abstract Generation Prompt v1.md"
PROMPT_VALIDATION_COVERAGE_FILENAME = "Validation Coverage Prompt v1.md"
PROMPT_PROBLEMATIC_HEADER_TERMS_FILENAME = "problematic_header_terms_v2.md"
PROMPT_EMPHASIS_SCORING_FILENAME = "emphasis_dedection_v3_production.md"
PROMPT_BOWEN_EXTRACTION_FILENAME = "bowen_reference_extraction_v1.md"
PROMPT_BOWEN_FILTER_FILENAME = "bowen_reference_filter_v1.md"

# Validation Settings
VALIDATION_MISMATCH_RATIO = 0.015  # 1.5% tolerance
VALIDATION_LOOKAHEAD_WINDOW = 10

# Minimum Generation Lengths
MIN_EXTRACTS_PERCENT = 0.04  # 4% of transcript word count
TARGET_EXTRACTS_PERCENT = 0.07  # 7% target for generation guidance
MIN_EXTRACTS_WORDS_FLOOR = 150
MIN_TRANSCRIPT_WORDS_FOR_FLOOR = 1000
MIN_EXTRACTS_WORDS_ABSOLUTE = 50
MIN_EXTRACTS_CHARS = 500
MIN_KEY_TERMS_CHARS = 100
MIN_BLOG_CHARS = 1000
MIN_ABSTRACT_VALIDATION_CHARS = 50

# Abstract Settings
ABSTRACT_TARGET_PERCENT = 0.03  # 3% of transcript word count
ABSTRACT_MIN_WORDS = 150
ABSTRACT_MAX_WORDS = 230        # target ceiling — keeps abstracts well under the hard max
ABSTRACT_HARD_MAX_WORDS = 250   # abstracts must be < this; validation flags >= as too long
# Abstract generation retries: regenerate (with corrective feedback) up to this
# many times to get a version that passes the gate's faithfulness + entity checks
# at generation time, instead of only discovering an unfaithful abstract at publish.
ABSTRACT_MAX_ATTEMPTS = 3


def abstract_target_word_count(transcript_words: int) -> int:
    """Single source for the abstract target length: ABSTRACT_TARGET_PERCENT of
    the transcript, floored at ABSTRACT_MIN_WORDS and capped at ABSTRACT_MAX_WORDS
    so generated abstracts stay under ABSTRACT_HARD_MAX_WORDS (< 250 words)."""
    return min(
        max(int(transcript_words * ABSTRACT_TARGET_PERCENT), ABSTRACT_MIN_WORDS),
        ABSTRACT_MAX_WORDS,
    )

# Summary Structure Allocations
SUMMARY_OPENING_PCT = 0.14
SUMMARY_CLOSING_PCT = 0.06
SUMMARY_QA_PCT = 0.10

# Validation Thresholds
TRANSCRIPT_MIN_WORDS = 1500
BLOG_MIN_WORDS = 800
OVERVIEW_MIN_WORDS = 800
EVALUATIVE_TERMS = ["valuable", "insightful", "excellent"]

# Token Estimation & Safety
CHARS_PER_TOKEN = 4
TOKEN_BUDGET_SAFETY_MARGIN = 0.8
TOKEN_USAGE_WARNING_THRESHOLD = 0.9

# Fuzzy Matching Settings
FUZZY_MATCH_THRESHOLD = 0.85
FUZZY_MATCH_EARLY_STOP = 0.98
FUZZY_MATCH_PREFIX_LEN = 20
# Cheap grounding pre-filter: fraction of a needle's distinct words that must appear
# ANYWHERE in the haystack before the O(haystack x needle) sliding-window scan runs.
# An ungrounded quote (hallucinated / heavily paraphrased) shares few words with the
# transcript, so it can never reach FUZZY_MATCH_THRESHOLD anyway — this short-circuits
# it in O(haystack) instead of scanning every window with no early stop. Kept safely
# below FUZZY_MATCH_THRESHOLD so it can never drop a quote that would actually match
# (review H10 / P9).
FUZZY_MATCH_PREFILTER_MIN_COVERAGE = 0.5

# Anthropic beta header for prompt caching — single source of truth for the value
# duplicated across transcript_utils call sites (review L6 / P4).
ANTHROPIC_CACHE_BETA_HEADER = "prompt-caching-2024-07-31"

# Emphasis-quote grounding: match BOTH the head and tail of each quote (not just
# the opening words), so a quote whose first words are verbatim but whose
# remainder is fabricated is flagged rather than silently accepted. A quote is
# "found" only if BOTH ends clear EMPHASIS_QUOTE_FOUND_RATIO; below
# EMPHASIS_QUOTE_PARTIAL_RATIO on either end it is reported NOT FOUND.
EMPHASIS_HEADTAIL_WORDS = 12
EMPHASIS_QUOTE_FOUND_RATIO = 0.95
EMPHASIS_QUOTE_PARTIAL_RATIO = 0.80

# Key-terms definition grounding: the definition is a synthesized paraphrase, so
# it is checked for topical keyword overlap, never verbatim. Global overlap with
# the whole transcript barely discriminates (almost any on-topic text scores
# high), so a definition that describes the WRONG concept still passed. We also
# require LOCAL grounding: the definition's keywords must overlap the transcript
# window around where the term actually appears. Calibrated on real runs: valid
# definitions score >=0.54 locally, a swapped/off-topic definition <=0.13.
KEY_TERMS_LOCAL_WINDOW_WORDS = 140
KEY_TERMS_DEF_LOCAL_MIN = 0.30
# Tier thresholds for validate_key_terms_fidelity (term-grounding / def-support).
KEY_TERMS_TERM_FAIL_BELOW = 0.50
KEY_TERMS_EXACT_TERM_MIN = 0.90
KEY_TERMS_EXACT_DEF_MIN = 0.50
KEY_TERMS_PARTIAL_TERM_MIN = 0.80
KEY_TERMS_PARTIAL_DEF_MIN = 0.35

# Abstract proper-name grounding (advisory): a multi-word Title-Case name in the
# abstract is flagged when none of its significant tokens appears in the source
# transcript. Fuzzy matching spares ASR spelling normalizations (e.g.
# "Bertoloso" -> "Bertolaso") while catching a fabricated name whose tokens are
# absent (verified on a real run: the hallucinated "Luciano Malorni").
ABSTRACT_NAME_TOKEN_MIN_LEN = 4
ABSTRACT_NAME_FUZZY_MIN = 0.80

# ============================================================================
# VALIDATION V2 SETTINGS
# ============================================================================

# Chunked Processing
VALIDATION_CHUNK_SIZE = 1500           # WORDS per chunk (not tokens)
VALIDATION_CHUNK_OVERLAP = 200         # WORDS overlap

# Context Requirements
VALIDATION_MIN_CONTEXT_WORDS = 5       # Min words for unique context
VALIDATION_MAX_CONTEXT_WORDS = 30      # Max words to include
VALIDATION_MIN_UNIQUE_WORDS = 7        # Threshold for ambiguous matches

# Fuzzy Matching Thresholds (V2)
VALIDATION_FUZZY_AUTO_APPLY = 0.95     # 95% similarity for auto-apply
VALIDATION_FUZZY_REVIEW = 0.90         # 90% for manual review
# Before a correction is written, the target span must actually match the
# correction's original_text at least this closely (recomputed on the real span,
# not trusting the fuzzy matcher's returned span). Below this the correction is
# SKIPPED, not applied — a mis-located span must never overwrite good text.
VALIDATION_MIN_APPLY_SIMILARITY = 0.90
VALIDATION_FUZZY_REJECT = 0.85         # < 85% reject
VALIDATION_FUZZY_HALLUCINATION = 0.85  # Hallucination detection threshold

# Confidence Filtering
VALIDATION_AUTO_APPLY_CONFIDENCE = {'high'}
VALIDATION_REVIEW_CONFIDENCE = {'medium'}
VALIDATION_SKIP_CONFIDENCE = {'low'}

# Iteration Control
VALIDATION_MAX_ITERATIONS = 5
VALIDATION_STALL_THRESHOLD = 0.20      # Stop if < 20% improvement
VALIDATION_MAX_STALLED_ITERATIONS = 2

# Error Types
VALIDATION_ERROR_TYPES = {
    'spelling', 'homophone', 'proper_noun', 'word_boundary', 'alias'
}

# Logging
VALIDATION_VERBOSE_LOGGING = True
VALIDATION_SAVE_REVIEW_FILE = True


# ============================================================================
# CONFIGURATION VALIDATION
# ============================================================================

class ValidationResult:
    """Stores validation results with errors and warnings."""

    def __init__(self):
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def add_error(self, message: str):
        """Add a critical error that prevents operation."""
        self.errors.append(message)

    def add_warning(self, message: str):
        """Add a warning that should be reviewed but doesn't prevent operation."""
        self.warnings.append(message)

    def is_valid(self) -> bool:
        """Returns True if no errors (warnings are allowed)."""
        return len(self.errors) == 0

    def format_report(self) -> str:
        """Format a human-readable validation report."""
        lines = []

        if self.errors:
            lines.append("=" * 70)
            lines.append("❌ CONFIGURATION ERRORS")
            lines.append("=" * 70)
            for i, error in enumerate(self.errors, 1):
                lines.append(f"{i}. {error}")
            lines.append("")

        if self.warnings:
            lines.append("=" * 70)
            lines.append("⚠️  CONFIGURATION WARNINGS")
            lines.append("=" * 70)
            for i, warning in enumerate(self.warnings, 1):
                lines.append(f"{i}. {warning}")
            lines.append("")

        if not self.errors and not self.warnings:
            lines.append("✅ Configuration validation passed - no issues found.")

        return "\n".join(lines)


def validate_configuration(verbose: bool = True, auto_fix: bool = False) -> ValidationResult:
    """
    Validates all configuration settings for correctness and consistency.

    Args:
        verbose: If True, print validation report to stdout
        auto_fix: If True, attempt to fix issues (e.g., create missing directories)

    Returns:
        ValidationResult with any errors and warnings found

    Raises:
        SystemExit: If critical errors found and not in test mode
    """
    result = ValidationResult()

    # ========================================================================
    # 1. VALIDATE DIRECTORY PATHS
    # ========================================================================

    # Check TRANSCRIPTS_BASE exists or is creatable
    if not settings.TRANSCRIPTS_BASE.exists():
        if auto_fix:
            try:
                settings.TRANSCRIPTS_BASE.mkdir(parents=True, exist_ok=True)
                result.add_warning(f"Created TRANSCRIPTS_BASE directory: {settings.TRANSCRIPTS_BASE}")
            except Exception as e:
                result.add_error(
                    f"TRANSCRIPTS_BASE does not exist and cannot be created: {settings.TRANSCRIPTS_BASE}\n"
                    f"  Error: {e}\n"
                    f"  Fix: Set TRANSCRIPTS_DIR environment variable or ensure directory is writable"
                )
        else:
            result.add_error(
                f"TRANSCRIPTS_BASE directory does not exist: {settings.TRANSCRIPTS_BASE}\n"
                f"  Fix: Create directory or set TRANSCRIPTS_DIR environment variable\n"
                f"  Example: export TRANSCRIPTS_DIR=/path/to/transcripts"
            )
    elif not settings.TRANSCRIPTS_BASE.is_dir():
        result.add_error(
            f"TRANSCRIPTS_BASE exists but is not a directory: {settings.TRANSCRIPTS_BASE}\n"
            f"  Fix: Remove file and create directory, or choose different location"
        )
    elif not os.access(settings.TRANSCRIPTS_BASE, os.W_OK):
        result.add_warning(
            f"TRANSCRIPTS_BASE is not writable: {settings.TRANSCRIPTS_BASE}\n"
            f"  This may cause issues when creating processed files\n"
            f"  Fix: chmod +w {settings.TRANSCRIPTS_BASE}"
        )

    # Check derived directories
    derived_dirs = {
        "SOURCE_DIR": settings.SOURCE_DIR,
        "PROCESSED_DIR": settings.PROCESSED_DIR,
        "PROJECTS_DIR": settings.PROJECTS_DIR,
    }

    for name, path in derived_dirs.items():
        if not path.exists():
            if auto_fix:
                try:
                    path.mkdir(parents=True, exist_ok=True)
                    result.add_warning(f"Created {name}: {path}")
                except Exception as e:
                    result.add_error(
                        f"{name} does not exist and cannot be created: {path}\n"
                        f"  Error: {e}\n"
                        f"  Fix: Ensure parent directory {settings.TRANSCRIPTS_BASE} is writable"
                    )
            else:
                result.add_warning(
                    f"{name} does not exist: {path}\n"
                    f"  Will be created automatically when needed\n"
                    f"  Or run: validate_configuration(auto_fix=True)"
                )

    # Check PROMPTS_DIR exists
    if not settings.PROMPTS_DIR.exists():
        result.add_error(
            f"PROMPTS_DIR does not exist: {settings.PROMPTS_DIR}\n"
            f"  This directory should contain prompt template files\n"
            f"  Fix: Create directory and add prompt files\n"
            f"  Expected location: {Path(__file__).parent / 'prompts'}"
        )
    elif not settings.PROMPTS_DIR.is_dir():
        result.add_error(
            f"PROMPTS_DIR exists but is not a directory: {settings.PROMPTS_DIR}\n"
            f"  Fix: Remove file and create directory with prompt files"
        )

    # Check LOGS_DIR is writable
    if not settings.LOGS_DIR.exists():
        if auto_fix:
            try:
                settings.LOGS_DIR.mkdir(parents=True, exist_ok=True)
                result.add_warning(f"Created LOGS_DIR: {settings.LOGS_DIR}")
            except Exception as e:
                result.add_error(
                    f"LOGS_DIR does not exist and cannot be created: {settings.LOGS_DIR}\n"
                    f"  Error: {e}\n"
                    f"  Fix: Ensure application directory is writable"
                )
    elif not os.access(settings.LOGS_DIR, os.W_OK):
        result.add_error(
            f"LOGS_DIR is not writable: {settings.LOGS_DIR}\n"
            f"  Logging will fail without write access\n"
            f"  Fix: chmod +w {settings.LOGS_DIR}"
        )

    # ========================================================================
    # 2. VALIDATE MODEL NAMES
    # ========================================================================

    models_to_check = {
        "DEFAULT_MODEL": settings.DEFAULT_MODEL,
        "AUX_MODEL": settings.AUX_MODEL,
        "FORMATTING_MODEL": settings.FORMATTING_MODEL,
        "VALIDATION_MODEL": settings.VALIDATION_MODEL,
    }

    available_models = sorted(model_specs.PRICING.keys())

    for model_var, model_name in models_to_check.items():
        if model_name not in model_specs.PRICING:
            result.add_error(
                f"{model_var} specifies unknown model: '{model_name}'\n"
                f"  Available models: {', '.join(available_models[:5])}...\n"
                f"  Fix: Update config.py or set via settings.set_{model_var.lower()}()\n"
                f"  Example: settings.set_default_model('claude-sonnet-4-20250514')"
            )

    # ========================================================================
    # 3. VALIDATE NUMERIC RANGES
    # ========================================================================

    # Token limits (must be positive)
    token_limits = {
        "MAX_TOKENS_FORMATTING": MAX_TOKENS_FORMATTING,
        "MAX_TOKENS_SUMMARY": MAX_TOKENS_SUMMARY,
        "MAX_TOKENS_EXTRACTION": MAX_TOKENS_EXTRACTION,
        "MAX_TOKENS_AUDIT": MAX_TOKENS_AUDIT,
        "MAX_TOKENS_HEADER_VALIDATION": MAX_TOKENS_HEADER_VALIDATION,
        "MAX_TOKENS_VALIDATION_VERIFY": MAX_TOKENS_VALIDATION_VERIFY,
        "MAX_TOKENS_REVIEW_SEMANTIC": MAX_TOKENS_REVIEW_SEMANTIC,
        "MAX_TOKENS_MODEL_PROBE": MAX_TOKENS_MODEL_PROBE,
    }

    for name, value in token_limits.items():
        if not isinstance(value, int) or value <= 0:
            result.add_error(
                f"{name} must be a positive integer, got: {value}\n"
                f"  Fix: Set to reasonable token limit (e.g., 8192, 32000)"
            )
        elif value > 200000:  # Claude's max context
            result.add_warning(
                f"{name} exceeds Claude's maximum context window (200,000): {value}\n"
                f"  This may cause API errors\n"
                f"  Fix: Reduce to ≤ 200000"
            )

    # Temperatures (must be 0.0 to 1.0)
    temperatures = {
        "TEMP_STRICT": TEMP_STRICT,
        "TEMP_ANALYSIS": TEMP_ANALYSIS,
        "TEMP_BALANCED": TEMP_BALANCED,
        "TEMP_CREATIVE": TEMP_CREATIVE,
    }

    for name, value in temperatures.items():
        if not isinstance(value, (int, float)) or not (0.0 <= value <= 1.0):
            result.add_error(
                f"{name} must be between 0.0 and 1.0, got: {value}\n"
                f"  0.0 = deterministic, 1.0 = maximum creativity\n"
                f"  Fix: Set to value in range [0.0, 1.0]"
            )

    # Timeouts (must be positive)
    timeouts = {
        "TIMEOUT_FORMATTING": TIMEOUT_FORMATTING,
        "TIMEOUT_SUMMARY": TIMEOUT_SUMMARY,
        "TIMEOUT_DEFAULT": TIMEOUT_DEFAULT,
    }

    for name, value in timeouts.items():
        if not isinstance(value, (int, float)) or value <= 0:
            result.add_error(
                f"{name} must be a positive number (seconds), got: {value}\n"
                f"  Fix: Set to reasonable timeout (e.g., 300 for 5 minutes)"
            )
        elif value < 10:
            result.add_warning(
                f"{name} is very short: {value} seconds\n"
                f"  May cause premature timeouts for long operations\n"
                f"  Consider: Increase to ≥ 60 seconds"
            )

    # Percentages (must be 0.0 to 1.0)
    percentages = {
        "MIN_EXTRACTS_PERCENT": MIN_EXTRACTS_PERCENT,
        "TARGET_EXTRACTS_PERCENT": TARGET_EXTRACTS_PERCENT,
        "ABSTRACT_TARGET_PERCENT": ABSTRACT_TARGET_PERCENT,
        "SUMMARY_OPENING_PCT": SUMMARY_OPENING_PCT,
        "SUMMARY_CLOSING_PCT": SUMMARY_CLOSING_PCT,
        "SUMMARY_QA_PCT": SUMMARY_QA_PCT,
        "TOKEN_BUDGET_SAFETY_MARGIN": TOKEN_BUDGET_SAFETY_MARGIN,
        "TOKEN_USAGE_WARNING_THRESHOLD": TOKEN_USAGE_WARNING_THRESHOLD,
        "FUZZY_MATCH_THRESHOLD": FUZZY_MATCH_THRESHOLD,
        "FUZZY_MATCH_EARLY_STOP": FUZZY_MATCH_EARLY_STOP,
        "VALIDATION_FUZZY_AUTO_APPLY": VALIDATION_FUZZY_AUTO_APPLY,
        "VALIDATION_FUZZY_REVIEW": VALIDATION_FUZZY_REVIEW,
        "VALIDATION_FUZZY_REJECT": VALIDATION_FUZZY_REJECT,
        "VALIDATION_FUZZY_HALLUCINATION": VALIDATION_FUZZY_HALLUCINATION,
        "VALIDATION_MISMATCH_RATIO": VALIDATION_MISMATCH_RATIO,
        "VALIDATION_STALL_THRESHOLD": VALIDATION_STALL_THRESHOLD,
    }

    for name, value in percentages.items():
        if not isinstance(value, (int, float)) or not (0.0 <= value <= 1.0):
            result.add_error(
                f"{name} must be between 0.0 and 1.0, got: {value}\n"
                f"  This represents a percentage or ratio\n"
                f"  Fix: Set to value in range [0.0, 1.0]"
            )

    # Word counts (must be positive integers)
    word_counts = {
        "DEFAULT_SUMMARY_WORD_COUNT": DEFAULT_SUMMARY_WORD_COUNT,
        "MIN_EXTRACTS_WORDS_FLOOR": MIN_EXTRACTS_WORDS_FLOOR,
        "MIN_TRANSCRIPT_WORDS_FOR_FLOOR": MIN_TRANSCRIPT_WORDS_FOR_FLOOR,
        "MIN_EXTRACTS_WORDS_ABSOLUTE": MIN_EXTRACTS_WORDS_ABSOLUTE,
        "ABSTRACT_MIN_WORDS": ABSTRACT_MIN_WORDS,
        "TRANSCRIPT_MIN_WORDS": TRANSCRIPT_MIN_WORDS,
        "BLOG_MIN_WORDS": BLOG_MIN_WORDS,
        "OVERVIEW_MIN_WORDS": OVERVIEW_MIN_WORDS,
        "VALIDATION_CHUNK_SIZE": VALIDATION_CHUNK_SIZE,
        "VALIDATION_CHUNK_OVERLAP": VALIDATION_CHUNK_OVERLAP,
        "VALIDATION_MIN_CONTEXT_WORDS": VALIDATION_MIN_CONTEXT_WORDS,
        "VALIDATION_MAX_CONTEXT_WORDS": VALIDATION_MAX_CONTEXT_WORDS,
        "VALIDATION_MIN_UNIQUE_WORDS": VALIDATION_MIN_UNIQUE_WORDS,
    }

    for name, value in word_counts.items():
        if not isinstance(value, int) or value <= 0:
            result.add_error(
                f"{name} must be a positive integer, got: {value}\n"
                f"  Fix: Set to reasonable word count (e.g., 100, 500, 1500)"
            )

    # Character counts (must be positive integers)
    char_counts = {
        "MIN_EXTRACTS_CHARS": MIN_EXTRACTS_CHARS,
        "MIN_KEY_TERMS_CHARS": MIN_KEY_TERMS_CHARS,
        "MIN_BLOG_CHARS": MIN_BLOG_CHARS,
        "MIN_ABSTRACT_VALIDATION_CHARS": MIN_ABSTRACT_VALIDATION_CHARS,
        "CHARS_PER_TOKEN": CHARS_PER_TOKEN,
        "VALIDATION_FUZZY_PREFIX_LEN": FUZZY_MATCH_PREFIX_LEN,
    }

    for name, value in char_counts.items():
        if not isinstance(value, int) or value <= 0:
            result.add_error(
                f"{name} must be a positive integer, got: {value}\n"
                f"  Fix: Set to reasonable character count"
            )

    # Iteration controls
    if not isinstance(VALIDATION_MAX_ITERATIONS, int) or VALIDATION_MAX_ITERATIONS <= 0:
        result.add_error(
            f"VALIDATION_MAX_ITERATIONS must be positive integer, got: {VALIDATION_MAX_ITERATIONS}\n"
            f"  Fix: Set to reasonable iteration limit (e.g., 3, 5, 10)"
        )

    if not isinstance(VALIDATION_MAX_STALLED_ITERATIONS, int) or VALIDATION_MAX_STALLED_ITERATIONS <= 0:
        result.add_error(
            f"VALIDATION_MAX_STALLED_ITERATIONS must be positive integer, got: {VALIDATION_MAX_STALLED_ITERATIONS}\n"
            f"  Fix: Set to reasonable iteration limit (e.g., 2, 3)"
        )

    if not isinstance(VALIDATION_LOOKAHEAD_WINDOW, int) or VALIDATION_LOOKAHEAD_WINDOW <= 0:
        result.add_error(
            f"VALIDATION_LOOKAHEAD_WINDOW must be positive integer, got: {VALIDATION_LOOKAHEAD_WINDOW}\n"
            f"  Fix: Set to reasonable window size (e.g., 5, 10, 20)"
        )

    # ========================================================================
    # 4. VALIDATE PROMPT FILES
    # ========================================================================

    if settings.PROMPTS_DIR.exists():
        prompt_files = {
            "PROMPT_FORMATTING_HEADER_VALIDATION_FILENAME": PROMPT_FORMATTING_HEADER_VALIDATION_FILENAME,
            "PROMPT_FORMATTING_FILENAME": PROMPT_FORMATTING_FILENAME,
            "PROMPT_EXTRACTS_FILENAME": PROMPT_EXTRACTS_FILENAME,
            "PROMPT_TOPICS_FILENAME": PROMPT_TOPICS_FILENAME,
            "PROMPT_STRUCTURAL_THEMES_FILENAME": PROMPT_STRUCTURAL_THEMES_FILENAME,
            "PROMPT_INTERPRETIVE_THEMES_FILENAME": PROMPT_INTERPRETIVE_THEMES_FILENAME,
            "PROMPT_LENS_GENERATION_FILENAME": PROMPT_LENS_GENERATION_FILENAME,
            "PROMPT_THEME_LENS_VALIDATION_FILENAME": PROMPT_THEME_LENS_VALIDATION_FILENAME,
            "PROMPT_KEY_TERMS_FILENAME": PROMPT_KEY_TERMS_FILENAME,
            "PROMPT_BLOG_FILENAME": PROMPT_BLOG_FILENAME,
            "PROMPT_OVERVIEW_FILENAME": PROMPT_OVERVIEW_FILENAME,
            "PROMPT_ABSTRACT_VALIDATION_FILENAME": PROMPT_ABSTRACT_VALIDATION_FILENAME,
            "PROMPT_VOICE_AUDIT_FILENAME": PROMPT_VOICE_AUDIT_FILENAME,
            "PROMPT_STRUCTURED_SUMMARY_FILENAME": PROMPT_STRUCTURED_SUMMARY_FILENAME,
            "PROMPT_STRUCTURED_ABSTRACT_FILENAME": PROMPT_STRUCTURED_ABSTRACT_FILENAME,
            "PROMPT_VALIDATION_COVERAGE_FILENAME": PROMPT_VALIDATION_COVERAGE_FILENAME,
        "PROMPT_PROBLEMATIC_HEADER_TERMS_FILENAME": PROMPT_PROBLEMATIC_HEADER_TERMS_FILENAME,
        "PROMPT_EMPHASIS_SCORING_FILENAME": PROMPT_EMPHASIS_SCORING_FILENAME,
        "PROMPT_BOWEN_EXTRACTION_FILENAME": PROMPT_BOWEN_EXTRACTION_FILENAME,
        "PROMPT_BOWEN_FILTER_FILENAME": PROMPT_BOWEN_FILTER_FILENAME,
        }

        missing_prompts = []
        for name, filename in prompt_files.items():
            prompt_path = settings.PROMPTS_DIR / filename
            if not prompt_path.exists():
                missing_prompts.append(f"  - {name}: {filename}")

        if missing_prompts:
            result.add_warning(
                f"Missing {len(missing_prompts)} prompt file(s) in {settings.PROMPTS_DIR}:\n" +
                "\n".join(missing_prompts) +
                "\n  These files are required for transcript processing\n"
                f"  Fix: Add prompt files to {settings.PROMPTS_DIR}"
            )

    # ========================================================================
    # 5. VALIDATE LOGICAL CONSISTENCY
    # ========================================================================

    # Check chunk overlap < chunk size
    if VALIDATION_CHUNK_OVERLAP >= VALIDATION_CHUNK_SIZE:
        result.add_error(
            f"VALIDATION_CHUNK_OVERLAP ({VALIDATION_CHUNK_OVERLAP}) must be < "
            f"VALIDATION_CHUNK_SIZE ({VALIDATION_CHUNK_SIZE})\n"
            f"  Otherwise chunks will overlap completely\n"
            f"  Fix: Set overlap to < 50% of chunk size"
        )

    # Check min < max context words
    if VALIDATION_MIN_CONTEXT_WORDS >= VALIDATION_MAX_CONTEXT_WORDS:
        result.add_error(
            f"VALIDATION_MIN_CONTEXT_WORDS ({VALIDATION_MIN_CONTEXT_WORDS}) must be < "
            f"VALIDATION_MAX_CONTEXT_WORDS ({VALIDATION_MAX_CONTEXT_WORDS})\n"
            f"  Fix: Set min < max"
        )

    # Check fuzzy match thresholds are ordered correctly
    if not (VALIDATION_FUZZY_REJECT <= VALIDATION_FUZZY_REVIEW <= VALIDATION_FUZZY_AUTO_APPLY):
        result.add_error(
            f"Fuzzy match thresholds must be ordered: "
            f"REJECT ({VALIDATION_FUZZY_REJECT}) ≤ "
            f"REVIEW ({VALIDATION_FUZZY_REVIEW}) ≤ "
            f"AUTO_APPLY ({VALIDATION_FUZZY_AUTO_APPLY})\n"
            f"  Fix: Ensure thresholds increase from reject to auto-apply"
        )

    # Check summary structure allocations sum to reasonable amount
    summary_total = SUMMARY_OPENING_PCT + SUMMARY_CLOSING_PCT + SUMMARY_QA_PCT
    if summary_total > 0.5:
        result.add_warning(
            f"Summary structure allocations sum to {summary_total:.1%} of content\n"
            f"  OPENING: {SUMMARY_OPENING_PCT:.1%}, "
            f"CLOSING: {SUMMARY_CLOSING_PCT:.1%}, "
            f"QA: {SUMMARY_QA_PCT:.1%}\n"
            f"  This leaves < 50% for main content\n"
            f"  Consider: Reduce allocations"
        )

    # ========================================================================
    # 6. VALIDATE CONFIDENCE SETS
    # ========================================================================

    if not isinstance(VALIDATION_AUTO_APPLY_CONFIDENCE, set):
        result.add_error(
            f"VALIDATION_AUTO_APPLY_CONFIDENCE must be a set, got: {type(VALIDATION_AUTO_APPLY_CONFIDENCE)}\n"
            f"  Fix: Use set syntax, e.g., {{'high', 'medium'}}"
        )

    if not isinstance(VALIDATION_REVIEW_CONFIDENCE, set):
        result.add_error(
            f"VALIDATION_REVIEW_CONFIDENCE must be a set, got: {type(VALIDATION_REVIEW_CONFIDENCE)}\n"
            f"  Fix: Use set syntax, e.g., {{'medium'}}"
        )

    if not isinstance(VALIDATION_SKIP_CONFIDENCE, set):
        result.add_error(
            f"VALIDATION_SKIP_CONFIDENCE must be a set, got: {type(VALIDATION_SKIP_CONFIDENCE)}\n"
            f"  Fix: Use set syntax, e.g., {{'low'}}"
        )

    # ========================================================================
    # 7. VALIDATE ERROR TYPES SET
    # ========================================================================

    if not isinstance(VALIDATION_ERROR_TYPES, set):
        result.add_error(
            f"VALIDATION_ERROR_TYPES must be a set, got: {type(VALIDATION_ERROR_TYPES)}\n"
            f"  Fix: Use set syntax"
        )
    elif not VALIDATION_ERROR_TYPES:
        result.add_warning(
            "VALIDATION_ERROR_TYPES is empty\n"
            "  Consider: Add error types like {'homophone', 'proper_noun', 'spelling'}"
        )

    # ========================================================================
    # OUTPUT RESULTS
    # ========================================================================

    if verbose:
        print(result.format_report())

    return result


def validate_or_exit(verbose: bool = True, auto_fix: bool = False):
    """
    Validate configuration and exit with error code if validation fails.

    This function is intended to be called at application startup to ensure
    configuration is valid before proceeding with operations.

    Args:
        verbose: If True, print validation report
        auto_fix: If True, attempt to fix issues automatically
    """
    result = validate_configuration(verbose=verbose, auto_fix=auto_fix)

    if not result.is_valid():
        print("\n" + "=" * 70)
        print("❌ CRITICAL: Configuration validation failed")
        print("=" * 70)
        print("The application cannot start with invalid configuration.")
        print("Please fix the errors above and try again.")
        print("=" * 70)
        sys.exit(1)
    elif result.warnings and verbose:
        print("\n⚠️  Configuration has warnings but is usable.")
        print("Consider addressing warnings for optimal operation.\n")
