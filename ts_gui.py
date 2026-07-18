#!/usr/bin/env python3
"""
Transcript Processor GUI Application
A graphical interface for the transcript processing pipeline.
"""

import io
import os
import re
import resource
import shutil
import subprocess
import threading
import tkinter as tk
from contextlib import redirect_stdout
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk

import analyze_token_usage
import cleanup_pipeline
import config
import pipeline
import transcript_config_check
import transcript_cost_estimator
import transcript_initial_validation
import transcript_initial_validation_v2  # ADDED V2 module
import transcript_validate_headers
import transcript_validate_webpage
from transcript_utils import clean_project_name, parse_filename_metadata
from validation_learning import (
    append_approved_terms,
    append_validation_aliases,
    is_weak_dictionary_pair,
    record_validation_rejections,
)

INIT_VAL_FILTER_VERSION = "compact-v3"
_GIT_REVISION_CACHE = None

# Spec: docs/spec_stage_selection_2026-07-12.md#SS.5
# Fixed pipeline execution order for the 13 selectable stages. Also drives
# checkbox layout in setup_ui() and the run order in _run_selected_stages().
STAGE_DEFINITIONS = [
    ("init_val", "0. Init Val"),
    ("format", "1. Format"),
    ("val_headers", "2. Val Headers"),
    ("yaml", "3. YAML"),
    ("topics", "T. Topics"),
    ("core", "4. Core (ST/IT/T/KT/L)"),
    ("structured_summary", "Structured Summary"),
    ("gen_abstract", "5. Gen Abstract"),
    ("val_abstract", "6. Val Abstract"),
    ("blog", "7. Blog (Lens #1)"),
    ("overview", "7b. Overview Post"),
    # bowen_emphasis runs BEFORE webpdf: (1) web/pdf fail-closes on a release-gate
    # BLOCK, and halting there must not skip this independent extraction; (2)
    # generate_pdf/generate_webpage highlight Bowen/Emphasis, so extracting first
    # means the rendered artifacts reflect the current run. Spec: SR.6
    ("bowen_emphasis", "Bowen + Emphasis"),
    ("webpdf", "8. Full Web/PDF"),
    ("package", "Package"),
    ("bundle", "Bundle (DOC/PDF)"),
]

# Spec: docs/spec_stage_selection_2026-07-12.md#SS.6 / §2.1
# {stage_key: [group, ...]} where each group is a list of
# (producing_stage_key, artifact_suffix_attr) pairs. A group is satisfied if
# ANY pair in it is satisfied; a stage's prerequisites are satisfied only if
# EVERY group is satisfied. artifact_suffix_attr is a config.py attribute
# name (e.g. "SUFFIX_FORMATTED"), resolved via _stage_artifact_path().
STAGE_DEPENDENCIES = {
    "init_val": [],
    "format": [],
    "val_headers": [[("format", "SUFFIX_FORMATTED")]],
    "yaml": [[("format", "SUFFIX_FORMATTED")]],
    "topics": [[("yaml", "SUFFIX_YAML")]],
    "core": [[("yaml", "SUFFIX_YAML")]],
    "structured_summary": [[("topics", "SUFFIX_TOPICS"), ("core", "SUFFIX_TOPICS")]],
    # Abstract needs Topics only (its prompt never uses Interpretive Themes);
    # satisfiable by the standalone `topics` stage OR `core` (both write
    # SUFFIX_TOPICS). Spec: docs/spec_lean_abstract_2026-07-13.md#LA.5
    "gen_abstract": [
        [("topics", "SUFFIX_TOPICS"), ("core", "SUFFIX_TOPICS")],
    ],
    "val_abstract": [[("gen_abstract", "SUFFIX_ABSTRACT_GEN")]],
    "blog": [
        [("core", "SUFFIX_STRUCTURAL_THEMES")],
        [("core", "SUFFIX_INTERPRETIVE_THEMES")],
    ],
    "overview": [
        [("core", "SUFFIX_ABSTRACT_INIT"), ("gen_abstract", "SUFFIX_ABSTRACT_GEN")],
        [("core", "SUFFIX_STRUCTURAL_THEMES")],
        [("core", "SUFFIX_TOPICS")],
        [("core", "SUFFIX_KEY_TERMS")],
    ],
    "webpdf": [[("format", "SUFFIX_FORMATTED"), ("yaml", "SUFFIX_YAML")]],
    # Bowen/Emphasis extract from the validated derived transcript, never the
    # raw source. Require a formatted/yaml artifact (selected or already on
    # disk) so a selective re-run can't run extraction on an unvalidated raw
    # file (P13). Mirrors webpdf/package. Spec: spec_selective_rerun_2026-07-16.md#SR.4
    "bowen_emphasis": [[("format", "SUFFIX_FORMATTED"), ("yaml", "SUFFIX_YAML")]],
    "package": [[("format", "SUFFIX_FORMATTED"), ("yaml", "SUFFIX_YAML")]],
    # Bundle needs at least the (required) YAML transcript section on disk.
    "bundle": [[("format", "SUFFIX_FORMATTED"), ("yaml", "SUFFIX_YAML")]],
}

# Spec: docs/spec_stage_selection_2026-07-12.md#SS.15
# Human-readable label for each artifact_suffix_attr used in the pre-flight
# blocking message (e.g. "Topics" for SUFFIX_TOPICS). Kept as data so the
# validator's message text and any consumer of it never drift.
ARTIFACT_LABELS = {
    "SUFFIX_FORMATTED": "Formatted Transcript",
    "SUFFIX_YAML": "YAML",
    "SUFFIX_TOPICS": "Topics",
    "SUFFIX_INTERPRETIVE_THEMES": "Interpretive Themes",
    "SUFFIX_STRUCTURAL_THEMES": "Structural Themes",
    "SUFFIX_KEY_TERMS": "Key Terms",
    "SUFFIX_ABSTRACT_GEN": "Generated Abstract",
    "SUFFIX_ABSTRACT_INIT": "Initial Abstract",
}

def _bundle_output_suffix_attrs():
    """Config suffix attr(s) the bundle run-stage writes, derived from
    config.BUNDLE_DEFAULT_FORMAT so STAGE_OUTPUTS['bundle'] and _run_stage_bundle
    stay one decision (P4/P19)."""
    return {
        "pdf": ["SUFFIX_BUNDLE_PDF"],
        "docx": ["SUFFIX_BUNDLE_DOCX"],
        "both": ["SUFFIX_BUNDLE_DOCX", "SUFFIX_BUNDLE_PDF"],
    }.get(getattr(config, "BUNDLE_DEFAULT_FORMAT", "pdf"), ["SUFFIX_BUNDLE_PDF"])


# Spec: docs/spec_selective_rerun_2026-07-16.md#SR.1 (selective re-run)
# {stage_key: [artifact_suffix_attr, ...]} -- the artifact(s) each stage WRITES,
# kept as data (config attr names, resolved via _stage_artifact_path) so the
# selective-run status report reads exactly what the producer writes and can
# never drift (P19). Used at run start to report whether a checked stage will
# generate fresh output or REGENERATE (overwrite) existing output, and which
# unchecked prerequisites are being reused from disk.
#
# "Exists" for a stage = ALL of its listed outputs are present (user's chosen
# rule: a partially-completed stage is treated as not-done so it re-runs).
#
# `init_val` is intentionally absent: its product is the *_validated source
# transcript (written next to the source, not a project-dir artifact), so it has
# no on-disk artifact here and is always reported as "will generate".
STAGE_OUTPUTS = {
    "format": ["SUFFIX_FORMATTED"],
    "val_headers": ["SUFFIX_HEADER_VAL_REPORT"],
    "yaml": ["SUFFIX_YAML"],
    "topics": ["SUFFIX_TOPICS"],
    "core": [
        "SUFFIX_STRUCTURAL_THEMES", "SUFFIX_INTERPRETIVE_THEMES",
        "SUFFIX_TOPICS", "SUFFIX_KEY_TERMS", "SUFFIX_LENSES",
    ],
    "structured_summary": ["SUFFIX_SUMMARY_GEN"],
    "gen_abstract": ["SUFFIX_ABSTRACT_GEN"],
    "val_abstract": ["SUFFIX_ABSTRACT_VAL"],
    "blog": ["SUFFIX_BLOG"],
    "overview": ["SUFFIX_OVERVIEW"],
    # The webpdf stage runner writes only .html + .pdf; the simple webpage is a
    # separate standalone tool and is not produced here (P19: match the writer).
    "webpdf": ["SUFFIX_WEBPAGE", "SUFFIX_PDF"],
    "bowen_emphasis": ["SUFFIX_BOWEN", "SUFFIX_EMPHASIS_SCORED"],
    "package": ["SUFFIX_ZIP"],
    # Derived from BUNDLE_DEFAULT_FORMAT (not a second literal) so the "exists"
    # status can't drift from what _run_stage_bundle actually writes (P19/P4).
    "bundle": _bundle_output_suffix_attrs(),
}


def _current_git_revision():
    """Return the short git revision for the current repo, if available."""
    global _GIT_REVISION_CACHE
    if _GIT_REVISION_CACHE is not None:
        return _GIT_REVISION_CACHE
    try:
        revision = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        revision = "unknown"
    _GIT_REVISION_CACHE = revision
    return revision


def _extract_compact_terms(original_text, suggested_text):
    """Reduce a context-heavy finding to the changed lexical span."""
    original_tokens = original_text.split()
    suggested_tokens = suggested_text.split()

    if not original_tokens or not suggested_tokens:
        return original_text.strip(), suggested_text.strip()

    matcher = SequenceMatcher(a=original_tokens, b=suggested_tokens)
    original_changed = []
    suggested_changed = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            continue
        original_changed.extend(original_tokens[i1:i2])
        suggested_changed.extend(suggested_tokens[j1:j2])

    compact_original = " ".join(original_changed).strip()
    compact_suggested = " ".join(suggested_changed).strip()

    if compact_original and compact_suggested:
        return compact_original, compact_suggested

    return original_text.strip(), suggested_text.strip()


def _build_full_correction_text(original_text, compact_original, compact_suggested):
    """Rebuild the full replacement string from a compact lexical edit."""
    if not compact_original or compact_original == original_text:
        return compact_suggested

    if compact_original in original_text:
        return original_text.replace(compact_original, compact_suggested, 1)

    return compact_suggested


def _build_context_phrase(original_text, compact_original, window_words=4):
    """Build a short context snippet around the changed term."""
    words = original_text.split()
    target_words = compact_original.split()
    if not words or not target_words:
        return original_text.strip()

    for start in range(0, len(words) - len(target_words) + 1):
        if words[start:start + len(target_words)] == target_words:
            snippet_start = max(0, start - window_words)
            snippet_end = min(len(words), start + len(target_words) + window_words)
            return " ".join(words[snippet_start:snippet_end])

    return original_text.strip()


def _is_simple_dictionary_candidate(finding, compact_original, compact_suggested):
    """Keep only compact lexical replacements suitable for the dictionary."""
    original_text = finding.get("original_text", "").strip()
    suggested_text = finding.get("suggested_correction", "").strip()
    error_type = finding.get("error_type", "")

    if not original_text or not suggested_text or not compact_original or not compact_suggested:
        return False

    if _build_full_correction_text(original_text, compact_original, compact_suggested) != suggested_text:
        return False

    original_count = len(compact_original.split())
    suggested_count = len(compact_suggested.split())

    if error_type == "word_boundary":
        return original_count <= 2 and suggested_count <= 2

    return original_count == 1 and suggested_count == 1


def _prepare_review_finding(finding):
    """Attach compact display terms used by the simplified review dialog."""
    original_text = finding.get("original_text", "")
    suggested_text = finding.get("suggested_correction", "")

    compact_original, compact_suggested = _extract_compact_terms(
        original_text,
        suggested_text,
    )

    if not _is_simple_dictionary_candidate(finding, compact_original, compact_suggested):
        return None
    if is_weak_dictionary_pair(compact_original, compact_suggested):
        return None

    prepared = finding.copy()
    prepared["display_original"] = compact_original
    prepared["display_suggested"] = compact_suggested
    prepared["context_phrase"] = _build_context_phrase(original_text, compact_original)
    return prepared


def _prepare_review_findings(findings):
    """Build the compact review list while suppressing weak and duplicate pairs."""
    prepared_findings = []
    seen_pairs = set()
    omitted_count = 0

    for finding in findings:
        prepared = _prepare_review_finding(finding)
        if not prepared:
            omitted_count += 1
            continue

        pair_key = (
            prepared["display_original"].strip().lower(),
            prepared["display_suggested"].strip().lower(),
        )
        if pair_key in seen_pairs:
            omitted_count += 1
            continue

        seen_pairs.add(pair_key)
        prepared_findings.append(prepared)

    return prepared_findings, omitted_count


def _collect_validation_review_actions(item_vars):
    """Split reviewed items into corrections, rejections, approved terms, and aliases."""
    final_corrections = []
    rejected_findings = []
    approved_terms = []
    aliases = []

    for item in item_vars:
        apply_selected = bool(item["apply"].get())
        compact_original = item["display_original"]
        correction_text = item["correction"].get().strip()
        original_finding = item["original_finding"]
        full_suggestion = _build_full_correction_text(
            original_finding.get("original_text", ""),
            compact_original,
            correction_text,
        )

        if apply_selected:
            correction = original_finding.copy()
            correction["suggested_correction"] = full_suggestion
            final_corrections.append(correction)

            if compact_original and correction_text and compact_original != correction_text:
                aliases.append((compact_original, correction_text))
                approved_terms.append(correction_text)
            continue

        rejection = original_finding.copy()
        rejection["suggested_correction"] = full_suggestion
        rejected_findings.append(rejection)

    return final_corrections, rejected_findings, approved_terms, aliases


def _find_existing_validation_versions(file_path):
    """Return existing vN files for a selected base transcript."""
    if not file_path:
        return []

    stem = file_path.stem
    if re.search(r"_v\d+$", stem) or stem.endswith("_validated"):
        return []

    parent = file_path.parent
    suffix = file_path.suffix
    versions = []
    for candidate in parent.glob(f"{stem}_v*{suffix}"):
        match = re.search(rf"^{re.escape(stem)}_v(\d+)$", candidate.stem)
        if match:
            versions.append((int(match.group(1)), candidate))

    versions.sort(key=lambda item: item[0])
    return [path for _, path in versions]


class GuiLoggerAdapter:
    """Adapts pipeline logging calls to the GUI log window."""

    def __init__(self, gui):
        self.gui = gui
        self.name = "GuiLogger"

    def info(self, msg, *args, **kwargs):
        self.gui.log(str(msg) % args if args else str(msg))

    def warning(self, msg, *args, **kwargs):
        self.gui.log(f"⚠️ {str(msg) % args if args else str(msg)}")

    def error(self, msg, *args, **kwargs):
        text = str(msg) % args if args else str(msg)
        prefix = "" if text.strip().startswith("❌") else "❌ "
        
        if kwargs.get("exc_info"):
            import traceback
            exc_text = traceback.format_exc()
            text += f"\n{exc_text}"

        self.gui.log(f"{prefix}{text}")

    def debug(self, msg, *args, **kwargs):
        self.gui.log(f"🔍 {str(msg) % args if args else str(msg)}")
        # Also print to console for dev access
        print(f"DEBUG: {str(msg) % args if args else str(msg)}")


class ValidationReviewDialog(tk.Toplevel):
    """Dialog to review, edit, and accept/reject validation findings."""

    def __init__(self, parent, findings, apply_callback):
        super().__init__(parent)
        self.title(f"Review Transcript Corrections [{INIT_VAL_FILTER_VERSION}]")
        self.geometry("1000x700")
        self.apply_callback = apply_callback
        self.findings, self.skipped_findings = _prepare_review_findings(findings)

        # Main container
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Instructions
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text=f"Found {len(self.findings)} dictionary candidates.", font=(
            "", 12, "bold")).pack(anchor="w")
        ttk.Label(header_frame, text="Checked items create dictionary entries in the form Wrong >>> Correct. Uncheck only the few you want to reject.").pack(
            anchor="w")
        ttk.Label(
            header_frame,
            text=f"Filter build: {INIT_VAL_FILTER_VERSION} | Terms file: {config.VALIDATION_APPROVED_TERMS_PATH}",
            wraplength=940,
        ).pack(anchor="w")
        if self.skipped_findings:
            ttk.Label(
                header_frame,
                text=f"Omitted {self.skipped_findings} broad or non-lexical suggestions.",
            ).pack(anchor="w")

        columns_frame = ttk.Frame(main_frame)
        columns_frame.pack(fill=tk.X, pady=(0, 4))
        ttk.Label(columns_frame, text="", width=4).grid(row=0, column=0, sticky="w")
        ttk.Label(columns_frame, text="Type", width=14).grid(row=0, column=1, sticky="w")
        ttk.Label(columns_frame, text="Wrong", width=16).grid(row=0, column=2, sticky="w")
        ttk.Label(columns_frame, text="", width=4).grid(row=0, column=3, sticky="w")
        ttk.Label(columns_frame, text="Correct", width=16).grid(row=0, column=4, sticky="w")
        ttk.Label(columns_frame, text="Context phrase").grid(row=0, column=5, sticky="w", padx=(8, 0))

        # Scrollable Canvas for items
        canvas_frame = ttk.Frame(main_frame)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(canvas_frame)
        scrollbar = ttk.Scrollbar(
            canvas_frame, orient="vertical", command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(
                scrollregion=self.canvas.bbox("all"))
        )

        self.canvas.create_window(
            (0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # Bind mousewheel to this specific dialog to avoid global binding issues
        self.bind("<MouseWheel>", self._on_mousewheel)

        # Populate items
        self.item_vars = []

        for i, finding in enumerate(self.findings):
            self._create_item_row(i, finding)

        # Buttons
        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(
            side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Apply & Finalize", command=lambda: self.on_apply(
            finalize=True)).pack(side=tk.RIGHT, padx=5)
        ttk.Button(btn_frame, text="Apply & Run Again", command=lambda: self.on_apply(
            finalize=False)).pack(side=tk.RIGHT, padx=5)

    def _on_mousewheel(self, event):
        """Handle mouse wheel scrolling for the canvas."""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def _create_item_row(self, index, prepared):
        frame = ttk.Frame(self.scrollable_frame)
        frame.pack(fill=tk.X, expand=True, padx=5, pady=2)
        frame.columnconfigure(5, weight=1)

        apply_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(frame, variable=apply_var).grid(
            row=0, column=0, sticky="w", padx=(0, 8)
        )
        ttk.Label(
            frame,
            text=f"{index + 1}. {prepared.get('error_type', 'unknown')}",
            width=14,
        ).grid(row=0, column=1, sticky="w", padx=(0, 8))
        ttk.Label(
            frame,
            text=prepared.get("display_original", ""),
            width=16,
        ).grid(row=0, column=2, sticky="w", padx=(0, 8))
        ttk.Label(frame, text=">>>").grid(row=0, column=3, sticky="w", padx=(0, 8))

        correction_var = tk.StringVar(value=prepared.get("display_suggested", ""))
        ttk.Entry(frame, textvariable=correction_var, width=24).grid(
            row=0, column=4, sticky="w"
        )
        ttk.Label(
            frame,
            text=prepared.get("context_phrase", ""),
            wraplength=380,
        ).grid(
            row=0,
            column=5,
            sticky="w",
            padx=(8, 0),
        )

        self.item_vars.append({
            'apply': apply_var,
            'correction': correction_var,
            'display_original': prepared.get("display_original", ""),
            'original_finding': prepared,
        })

    def on_apply(self, finalize=False):
        actions = _collect_validation_review_actions(self.item_vars)
        self.apply_callback(*actions, finalize)
        self.destroy()


class TranscriptProcessorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(f"Transcript Processor [{_current_git_revision()} {INIT_VAL_FILTER_VERSION}]")
        self.root.geometry("900x950")

        self.selected_file = None
        self.base_name = None
        self.formatted_file = None
        self.processing = False

        # Create logger adapter
        self.logger = GuiLoggerAdapter(self)
        self.make_dir_default_var = tk.BooleanVar(value=False)
        self.include_emphasis_core = tk.BooleanVar(value=True)
        self.include_bowen_core = tk.BooleanVar(value=True)
        self.selected_file_label_var = tk.StringVar(value="No file selected.")

        # Spec: docs/spec_stage_selection_2026-07-12.md#SS.8
        self.stage_vars = {key: tk.BooleanVar(value=False) for key, _ in STAGE_DEFINITIONS}
        self.active_selection_var = tk.StringVar(value="(none)")

        # ADDED: StringVars for model selection
        self.model_vars = {
            "DEFAULT_MODEL": tk.StringVar(value=config.settings.DEFAULT_MODEL),
            "AUX_MODEL": tk.StringVar(value=config.settings.AUX_MODEL),
            "FORMATTING_MODEL": tk.StringVar(value=config.settings.FORMATTING_MODEL),
        }
        self.terms_file_var = tk.StringVar()

        self.setup_ui()
        self.update_dir_label()
        self.update_terms_file_label()
        self.refresh_file_list()
        self.update_button_states()
        self._apply_default_stage_selection()
        self.log(
            "GUI started: commit=%s filter=%s default_terms=%s",
            _current_git_revision(),
            INIT_VAL_FILTER_VERSION,
            config.VALIDATION_APPROVED_TERMS_PATH,
        )

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        # Only the PanedWindow row grows with the window
        main_frame.rowconfigure(2, weight=1)

        # Row 0: Directory selection
        dir_frame = ttk.Frame(main_frame)
        dir_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        self.dir_label = ttk.Label(dir_frame, text="Source Directory: ")
        self.dir_label.pack(side=tk.LEFT, padx=(0, 10))
        dir_btn = ttk.Button(dir_frame, text="Set Directory",
                             command=self.select_transcripts_directory)
        dir_btn.pack(side=tk.LEFT)
        self.make_default_chk = ttk.Checkbutton(
            dir_frame, text="Make Default", variable=self.make_dir_default_var,
            command=self._on_make_default_toggled,
        )
        self.make_default_chk.pack(side=tk.LEFT, padx=(5, 0))
        ttk.Button(dir_frame, text="Folder Defaults...", command=self.open_folder_defaults_dialog).pack(
            side=tk.LEFT, padx=(10, 0)
        )

        # Row 1: Model Selection (fixed height, above the resizable panes)
        model_selection_frame = ttk.LabelFrame(main_frame, text="Model Selection", padding="10")
        model_selection_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        model_selection_frame.columnconfigure(1, weight=1)

        all_model_names = config.settings.get_all_model_names()

        # Default Model
        ttk.Label(model_selection_frame, text="Default Model:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.default_model_cb = ttk.Combobox(
            model_selection_frame,
            textvariable=self.model_vars["DEFAULT_MODEL"],
            values=all_model_names,
            state="readonly"
        )
        self.default_model_cb.grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.default_model_cb.bind("<<ComboboxSelected>>", lambda event: self._on_model_selected("DEFAULT_MODEL"))

        # Auxiliary Model
        ttk.Label(model_selection_frame, text="Auxiliary Model:").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.aux_model_cb = ttk.Combobox(
            model_selection_frame,
            textvariable=self.model_vars["AUX_MODEL"],
            values=all_model_names,
            state="readonly"
        )
        self.aux_model_cb.grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.aux_model_cb.bind("<<ComboboxSelected>>", lambda event: self._on_model_selected("AUX_MODEL"))

        # Formatting Model
        ttk.Label(model_selection_frame, text="Formatting Model:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.formatting_model_cb = ttk.Combobox(
            model_selection_frame,
            textvariable=self.model_vars["FORMATTING_MODEL"],
            values=all_model_names,
            state="readonly"
        )
        self.formatting_model_cb.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.formatting_model_cb.bind("<<ComboboxSelected>>", lambda event: self._on_model_selected("FORMATTING_MODEL"))

        # Validation Mode (V1/V2)
        self.validation_mode_var = tk.StringVar(value="v2")
        val_frame = ttk.Frame(model_selection_frame)
        val_frame.grid(row=3, column=0, columnspan=2, sticky=tk.W, padx=5, pady=(5, 0))
        ttk.Label(val_frame, text="Validation Mode:").pack(side=tk.LEFT)
        ttk.Radiobutton(val_frame, text="V2 (Chunked/Safe)", variable=self.validation_mode_var, value="v2").pack(side=tk.LEFT, padx=5)
        ttk.Radiobutton(val_frame, text="V1 (Legacy)", variable=self.validation_mode_var, value="v1").pack(side=tk.LEFT, padx=5)

        terms_frame = ttk.Frame(model_selection_frame)
        terms_frame.grid(row=4, column=0, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=(8, 0))
        terms_frame.columnconfigure(1, weight=1)
        ttk.Label(terms_frame, text="Terms File:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        ttk.Label(terms_frame, textvariable=self.terms_file_var).grid(row=0, column=1, sticky=(tk.W, tk.E))
        ttk.Button(terms_frame, text="Choose...", command=self.select_validation_terms_file).grid(
            row=0, column=2, sticky=tk.E, padx=(8, 4)
        )
        ttk.Button(terms_frame, text="Default", command=self.reset_validation_terms_file).grid(
            row=0, column=3, sticky=tk.E
        )

        # Row 2: PanedWindow — all three text panes are drag-resizable
        paned = ttk.PanedWindow(main_frame, orient=tk.VERTICAL)
        paned.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))

        # Pane 1: Source File List
        file_outer_frame = ttk.LabelFrame(paned, text="Select Source File", padding="10")
        file_outer_frame.rowconfigure(1, weight=1)
        file_outer_frame.columnconfigure(0, weight=1)
        paned.add(file_outer_frame, weight=1)

        file_header = ttk.Frame(file_outer_frame)
        file_header.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E))
        file_header.columnconfigure(0, weight=1)

        refresh_btn = ttk.Button(file_header, text="Refresh List", command=self.refresh_file_list)
        refresh_btn.pack(side=tk.RIGHT, anchor=tk.NE)

        list_frame = ttk.Frame(file_outer_frame)
        list_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.file_listbox = tk.Listbox(list_frame, height=6, yscrollcommand=scrollbar.set)
        self.file_listbox.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

        # Pane 2: File Status
        status_frame = ttk.LabelFrame(paned, text="File Status", padding="10")
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(1, weight=1)
        paned.add(status_frame, weight=1)

        status_top_frame = ttk.Frame(status_frame)
        status_top_frame.grid(row=0, column=0, sticky=(tk.W, tk.E))
        status_top_frame.columnconfigure(0, weight=1)

        self.selected_file_status_label = ttk.Label(status_top_frame, textvariable=self.selected_file_label_var, font=('sans', 10, 'bold'))
        self.selected_file_status_label.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))

        status_refresh_btn = ttk.Button(status_top_frame, text="Refresh", command=self.check_file_status)
        status_refresh_btn.grid(row=0, column=1, sticky=tk.NE)

        self.status_text = tk.Text(status_frame, height=8, wrap=tk.WORD, font=('Courier', 10))
        self.status_text.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Pane 3: Processing Log
        log_frame = ttk.LabelFrame(paned, text="Processing Log", padding="10")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        paned.add(log_frame, weight=2)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, font=('Courier', 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Row 3: Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        # Row 4: Stage Selection Checkboxes
        # Spec: docs/spec_stage_selection_2026-07-12.md#SS.7
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=4, column=0, sticky=(tk.W, tk.E))

        STAGE_COLUMNS = 5
        self.stage_checkbuttons = {}
        for idx, (key, label) in enumerate(STAGE_DEFINITIONS):
            row, col = divmod(idx, STAGE_COLUMNS)
            chk = ttk.Checkbutton(button_frame, text=label, variable=self.stage_vars[key])
            chk.grid(row=row, column=col, padx=(0, 5), pady=2, sticky=tk.W)
            self.stage_checkbuttons[key] = chk

        modifier_row = (len(STAGE_DEFINITIONS) - 1) // STAGE_COLUMNS + 1

        self.core_emphasis_chk = ttk.Checkbutton(
            button_frame,
            text="Include Emphasis in Core",
            variable=self.include_emphasis_core,
        )
        self.core_emphasis_chk.grid(row=modifier_row, column=0, padx=(0, 5), pady=2, sticky=tk.W)

        self.core_bowen_chk = ttk.Checkbutton(
            button_frame,
            text="Include Bowen in Core",
            variable=self.include_bowen_core,
        )
        self.core_bowen_chk.grid(row=modifier_row, column=1, padx=(0, 5), pady=2, sticky=tk.W)

        # Utility buttons row
        utility_row = modifier_row + 1
        self.cost_btn = ttk.Button(
            button_frame, text="Est. Cost", command=self.do_estimate_cost, state=tk.DISABLED)
        self.cost_btn.grid(row=utility_row, column=0, padx=(0, 5), pady=2)

        self.config_btn = ttk.Button(
            button_frame, text="Config Check", command=self.do_config_check)
        self.config_btn.grid(row=utility_row, column=1, padx=(0, 5), pady=2)

        self.clean_logs_btn = ttk.Button(
            button_frame, text="Clean Logs...", command=self.do_clean_logs)
        self.clean_logs_btn.grid(row=utility_row, column=2, padx=(0, 5), pady=2)

        self.clear_btn = ttk.Button(
            button_frame, text="Clear Log", command=self.clear_log)
        self.clear_btn.grid(row=utility_row, column=3, padx=(0, 5), pady=2)

        self.cleanup_btn = ttk.Button(
            button_frame, text="Cleanup Source", command=self.do_cleanup, state=tk.DISABLED)
        self.cleanup_btn.grid(row=utility_row, column=4, padx=(0, 5), pady=2)

        # Row 5: Run Selected / Manage Selections
        # Spec: docs/spec_stage_selection_2026-07-12.md#SS.9
        run_frame = ttk.Frame(main_frame)
        run_frame.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=(8, 0))

        self.run_selected_btn = ttk.Button(
            run_frame, text="▶ Run Selected", command=self.do_run_selected, state=tk.DISABLED)
        self.run_selected_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.manage_selections_btn = ttk.Button(
            run_frame, text="Manage Selections...", command=self.open_selection_manager_dialog)
        self.manage_selections_btn.pack(side=tk.LEFT, padx=(0, 5))

        self.bundle_btn = ttk.Button(
            run_frame, text="Create Bundle (DOC/PDF)...", command=self.open_bundle_dialog)
        self.bundle_btn.pack(side=tk.LEFT, padx=(0, 5))

        ttk.Label(run_frame, text="Active selection:").pack(side=tk.LEFT, padx=(10, 5))
        ttk.Label(run_frame, textvariable=self.active_selection_var).pack(side=tk.LEFT)

        self.status_label = ttk.Label(
            main_frame, text="Ready", foreground="green")
        self.status_label.grid(row=6, column=0, pady=(5, 0), sticky=tk.W)

        # Memory Usage Label
        self.memory_label = ttk.Label(
            main_frame, text="Mem: -- MB", foreground="gray")
        self.memory_label.grid(row=6, column=0, pady=(5, 0), sticky=tk.E)

        # Start memory monitoring
        self.monitor_memory()

    def monitor_memory(self):
        """Periodically check and display memory usage."""
        try:
            # On macOS, ru_maxrss is in bytes. On Linux, it's in KB.
            # Python docs say: "ru_maxrss: maximum resident set size"
            # Since user is on Darwin (macOS), standard getrusage behavior applies.
            # However, Python's resource module documentation says:
            # "On OS X, ru_maxrss is in bytes."
            usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            usage_mb = usage / (1024 * 1024)  # Bytes -> MB
            
            self.memory_label.config(text=f"Mem: {usage_mb:.1f} MB")
            
            # Check for high memory usage (e.g., > 2 GB)
            if usage_mb > 2000:
                self.memory_label.config(foreground="red")
            else:
                self.memory_label.config(foreground="gray")
                
        except Exception:
            self.memory_label.config(text="Mem: N/A")
            
        # Update every 2 seconds
        self.root.after(2000, self.monitor_memory)

    # ADDED: Callback for model selection
    def _on_model_selected(self, model_type: str):
        selected_model = self.model_vars[model_type].get()
        try:
            if model_type == "DEFAULT_MODEL":
                config.settings.set_default_model(selected_model)
            elif model_type == "AUX_MODEL":
                config.settings.set_aux_model(selected_model)
            elif model_type == "FORMATTING_MODEL":
                config.settings.set_formatting_model(selected_model)
            self.log(f"Model for {model_type} updated to: {selected_model}")
        except ValueError as e:
            self.log(f"❌ Error updating model for {model_type}: {e}")
            messagebox.showerror("Model Selection Error", str(e))
            # Revert the combobox to the previous valid selection
            if model_type == "DEFAULT_MODEL":
                self.model_vars[model_type].set(config.settings.DEFAULT_MODEL)
            elif model_type == "AUX_MODEL":
                self.model_vars[model_type].set(config.settings.AUX_MODEL)
            elif model_type == "FORMATTING_MODEL":
                self.model_vars[model_type].set(config.settings.FORMATTING_MODEL)

    def do_cleanup(self):
        """Cleanup source files (move original/validated to processed, delete versions)."""
        if not self.base_name:
            return
            
        if not messagebox.askokcancel(
            "Confirm Cleanup", 
            f"This will:\n1. Move '{self.base_name}.txt' and validated copy to 'processed/'\n2. DELETE all intermediate '_vN' files.\n\nAre you sure?"
        ):
            return

        self.log("STEP: Cleaning up source files...")
        self.run_task_in_thread(self._run_cleanup)

    def _run_cleanup(self):
        if cleanup_pipeline.cleanup_transcript_files(self.base_name, self.logger):
            self.log("✅ Cleanup complete.")
            # Refresh to show files moved/deleted
            self.root.after(0, self.refresh_file_list)
            # Clear selection as the file might have moved
            self.root.after(0, lambda: self.status_text.delete(1.0, tk.END))
            self.selected_file = None
            self.base_name = None
            return True
        return False

    def select_transcripts_directory(self):
        dir_path = filedialog.askdirectory(
            title="Select Directory Containing Source Files")
        if dir_path:
            # Set the directory for the current session
            config.set_source_dir_and_infer_base(dir_path)

            # If "Make Default" is already checked, persist the newly-chosen dir
            # as the default. If it's unchecked, leave any existing default alone
            # (changing dirs for one session must not silently wipe a saved
            # default; the user clears it by unchecking the box or via the
            # Folder Defaults dialog).
            if self.make_dir_default_var.get():
                config.set_default_source_dir(dir_path)
                self.log(f"✅ Saved {dir_path} as new default source directory.")

            # Update UI
            self.update_dir_label()
            self.update_terms_file_label()
            self.refresh_file_list()
            self.log(
                "Switched source directory to %s; Base path inferred as %s. Reset validation terms file.",
                config.SOURCE_DIR,
                config.TRANSCRIPTS_BASE,
            )

    def _on_make_default_toggled(self):
        """Persist (or clear) the CURRENT source dir as the startup default when
        the 'Make Default' box is toggled -- so checking it AFTER Set Directory
        works, not only when checked before picking a folder.

        Spec: docs/spec_folder_defaults_2026-07-16.md#FD.1
        """
        if self.make_dir_default_var.get():
            # set_default_source_dir keeps the invariant "default is a favorite"
            # (FD.4), so no separate add is needed here.
            config.set_default_source_dir(str(config.SOURCE_DIR))
            self.log("✅ Saved %s as default source directory (loads on next start) "
                     "and added it to Folder Defaults.", config.SOURCE_DIR)
        else:
            config.set_default_source_dir(None)
            self.log("Cleared default source directory.")

    def _load_favorite_source_dir(self, path):
        """Switch the session to a favorite source directory (does not change
        which one auto-loads on start). Spec: FD.5."""
        config.set_source_dir_and_infer_base(path)
        self.update_dir_label()
        self.update_terms_file_label()
        self.refresh_file_list()
        self.log("Loaded source directory from Folder Defaults: %s", path)

    def _remove_favorite_source_dir(self, path):
        """Remove a favorite from the Folder Defaults list. Spec: FD.5."""
        config.remove_source_dir_favorite(path)
        # Removing the entry that was the auto-load default clears the default
        # (config), so re-sync the main-window "Make Default" checkbox (F3).
        self._sync_make_default_checkbox()
        self.log("Removed from Folder Defaults: %s", path)

    def _sync_make_default_checkbox(self):
        """Reflect whether the current source dir IS the saved startup default,
        so the box shows the real state on load and after a dir change."""
        saved = config.settings.runtime_settings.get("default_source_dir")
        self.make_dir_default_var.set(bool(saved) and saved == str(config.SOURCE_DIR))

    def update_dir_label(self):
        self.dir_label.config(
            text=f"Source Directory: {config.SOURCE_DIR}")
        self._sync_make_default_checkbox()

    def open_folder_defaults_dialog(self):
        dlg = tk.Toplevel(self.root)
        dlg.title("Folder Defaults")
        dlg.resizable(True, False)
        dlg.grab_set()

        path_labels = {}

        def dir_label(key):
            val = {"source": config.SOURCE_DIR, "processed": config.PROCESSED_DIR, "projects": config.PROJECTS_DIR}[key]
            rt_key = {"source": "default_source_dir", "processed": "default_processed_dir", "projects": "default_projects_dir"}[key]
            suffix = " (saved)" if config.settings.runtime_settings.get(rt_key) else " (derived)"
            return str(val) + suffix

        def terms_label():
            saved = config.settings.runtime_settings.get("validation_approved_terms_path")
            suffix = " (saved)" if saved else " (default)"
            return str(config.VALIDATION_APPROVED_TERMS_PATH) + suffix

        def refresh_labels():
            for key, lbl in path_labels.items():
                lbl.config(text=terms_label() if key == "terms" else dir_label(key))

        def browse(key):
            if key == "terms":
                chosen = filedialog.askopenfilename(
                    title="Select Approved Terms File",
                    initialdir=str(config.TRANSCRIPTS_BASE),
                    filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
                    parent=dlg,
                )
                if not chosen:
                    return
                config.set_validation_approved_terms_path(chosen)
                self.update_terms_file_label()
            else:
                initial = {"source": config.SOURCE_DIR, "processed": config.PROCESSED_DIR, "projects": config.PROJECTS_DIR}[key]
                chosen = filedialog.askdirectory(
                    title=f"Select {key.title()} Folder",
                    initialdir=str(initial),
                    parent=dlg,
                )
                if not chosen:
                    return
                if key == "source":
                    config.set_source_dir_and_infer_base(chosen)
                    config.set_default_source_dir(chosen)
                    self.update_dir_label()
                    self.update_terms_file_label()
                    self.refresh_file_list()
                elif key == "processed":
                    config.set_default_processed_dir(chosen)
                elif key == "projects":
                    config.set_default_projects_dir(chosen)
            refresh_labels()
            self.log("Set default %s to: %s", key, chosen)

        def reset(key):
            if key == "terms":
                config.set_validation_approved_terms_path(None)
                self.update_terms_file_label()
            elif key == "source":
                config.set_default_source_dir(None)
            elif key == "processed":
                config.set_default_processed_dir(None)
            elif key == "projects":
                config.set_default_projects_dir(None)
            refresh_labels()
            self.log("Reset %s to default.", key)

        frame = ttk.Frame(dlg, padding="12")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        dlg.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        rows = [
            ("Source Directory", "source"),
            ("Processed Directory", "processed"),
            ("Projects Directory", "projects"),
            ("Approved Terms File", "terms"),
        ]
        for row_idx, (label_text, key) in enumerate(rows):
            ttk.Label(frame, text=label_text + ":").grid(
                row=row_idx, column=0, sticky=tk.W, padx=(0, 8), pady=4
            )
            text = terms_label() if key == "terms" else dir_label(key)
            path_lbl = ttk.Label(frame, text=text, foreground="gray", wraplength=380, anchor=tk.W)
            path_lbl.grid(row=row_idx, column=1, sticky=(tk.W, tk.E), pady=4)
            path_labels[key] = path_lbl
            ttk.Button(frame, text="Browse...", command=lambda k=key: browse(k)).grid(
                row=row_idx, column=2, padx=(8, 4), pady=4
            )
            ttk.Button(frame, text="Reset", command=lambda k=key: reset(k)).grid(
                row=row_idx, column=3, pady=4
            )

        # --- Favorite source directories (FD.5) ---------------------------
        fav_row = len(rows)
        ttk.Separator(frame, orient=tk.HORIZONTAL).grid(
            row=fav_row, column=0, columnspan=4, sticky=(tk.W, tk.E), pady=(10, 4)
        )
        ttk.Label(frame, text="Source folder favorites (Make Default adds here):").grid(
            row=fav_row + 1, column=0, columnspan=4, sticky=tk.W, pady=(0, 4)
        )
        fav_listbox = tk.Listbox(frame, height=5)
        fav_listbox.grid(row=fav_row + 2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=2)

        def refresh_favorites():
            fav_listbox.delete(0, tk.END)
            default_dir = config.settings.runtime_settings.get("default_source_dir")
            for path in config.get_source_dir_favorites():
                marker = "★ " if path == default_dir else "  "
                fav_listbox.insert(tk.END, f"{marker}{path}")

        def _selected_favorite():
            sel = fav_listbox.curselection()
            if not sel:
                return None
            return config.get_source_dir_favorites()[sel[0]]

        def load_favorite():
            path = _selected_favorite()
            if path:
                self._load_favorite_source_dir(path)
                refresh_labels()

        def remove_favorite():
            path = _selected_favorite()
            if path:
                self._remove_favorite_source_dir(path)
                refresh_favorites()
                refresh_labels()

        fav_btns = ttk.Frame(frame)
        fav_btns.grid(row=fav_row + 2, column=3, sticky=(tk.N,), padx=(8, 0))
        ttk.Button(fav_btns, text="Load", command=load_favorite).pack(fill=tk.X, pady=(0, 2))
        ttk.Button(fav_btns, text="Remove", command=remove_favorite).pack(fill=tk.X)
        refresh_favorites()

        ttk.Button(frame, text="Close", command=dlg.destroy).grid(
            row=fav_row + 3, column=0, columnspan=4, pady=(12, 0)
        )

    def update_terms_file_label(self):
        active_path = Path(config.VALIDATION_APPROVED_TERMS_PATH)
        if active_path == config.TRANSCRIPTS_BASE / config.VALIDATION_APPROVED_TERMS_FILENAME:
            display = f"{active_path.name} (default)"
        else:
            display = active_path.name
        self.terms_file_var.set(display)

    def select_validation_terms_file(self):
        file_path = filedialog.askopenfilename(
            title="Select Validation Terms File",
            initialdir=config.TRANSCRIPTS_BASE,
            filetypes=[("Text Files", "*.txt"), ("All Files", "*.*")],
        )
        if file_path:
            config.set_validation_approved_terms_path(file_path)
            self.update_terms_file_label()
            self.log("Using validation terms file: %s", config.VALIDATION_APPROVED_TERMS_PATH)

    def reset_validation_terms_file(self):
        config.set_validation_approved_terms_path(None)
        self.update_terms_file_label()
        self.log("Reset validation terms file to default: %s", config.VALIDATION_APPROVED_TERMS_PATH)

    def refresh_file_list(self):
        self.file_listbox.delete(0, tk.END)
        self.selected_file_label_var.set("No file selected.")
        if not config.SOURCE_DIR.exists():
            self.log("⚠️  Source directory not found: %s\n", config.SOURCE_DIR)
            return
        files = sorted(config.SOURCE_DIR.glob("*.txt"))
        if not files:
            self.log("No .txt files found in source directory: %s\n",
                     config.SOURCE_DIR)
            return
        for file in files:
            self.file_listbox.insert(
                tk.END, f"{file.name} ({file.stat().st_size/1024:.1f} KB)")
        self.log("Found %d source file(s)\n", len(files))
        self.check_file_status()

    def on_file_select(self, event):
        selection = self.file_listbox.curselection()
        if not selection:
            self.selected_file_label_var.set("No file selected.")
            return
        filename = self.file_listbox.get(selection[0]).split(" (")[0]
        self.selected_file_label_var.set(f"Status for: {filename}")

        try:
            parse_filename_metadata(filename)
            self.log(f"✅ Filename format is valid for '{filename}'")
        except ValueError as e:
            self.log(f"❌ Invalid filename format: {e}")
            messagebox.showerror("Invalid Filename", f"The selected file has an invalid name:\n\n{filename}\n\nIt must follow the pattern 'Title - Presenter - Date.ext'.\n\nPlease rename the file and refresh the list.")
            self.selected_file = None
            self.base_name = None
            self.update_button_states()
            self.status_text.delete(1.0, tk.END)
            return

        self.selected_file = config.SOURCE_DIR / filename

        # Get base name using centralized cleaning logic
        self.base_name = clean_project_name(self.selected_file.stem)

        if self.base_name is None: # ADDED check
            return                 # ADDED return
        self.formatted_file = (config.PROJECTS_DIR / self.base_name / \
                               f"{self.base_name}{config.SUFFIX_FORMATTED}")
        self.check_file_status()
        self.update_button_states()

    def check_file_status(self):
        self.status_text.delete(1.0, tk.END)
        if not self.selected_file or self.base_name is None: # MODIFIED check
            return

        base = self.base_name
        project_dir = config.PROJECTS_DIR / base

        # Always check for the base source file (without _validated)
        source_file = config.SOURCE_DIR / f"{base}{self.selected_file.suffix}"
        validated_file = config.SOURCE_DIR / f"{base}_validated{self.selected_file.suffix}"

        checks = [
            ("Source", source_file),
            ("Initial Val", validated_file),
            ("Formatted", project_dir /
             f"{base}{config.SUFFIX_FORMATTED}"),
            ("Header Val", project_dir /
             f"{base}{config.SUFFIX_HEADER_VAL_REPORT}"),
            ("YAML", project_dir / f"{base}{config.SUFFIX_YAML}"),
            ("Structural Themes", project_dir /
             f"{base}{config.SUFFIX_STRUCTURAL_THEMES}"),
            ("Interpretive Themes", project_dir /
             f"{base}{config.SUFFIX_INTERPRETIVE_THEMES}"),
            ("Topics", project_dir / f"{base}{config.SUFFIX_TOPICS}"),
            ("Topics Val", project_dir /
             f"{base}{config.SUFFIX_TOPICS_VAL}"),
            ("Key Terms", project_dir / f"{base}{config.SUFFIX_KEY_TERMS}"),
            ("Key Terms Val", project_dir /
             f"{base}{config.SUFFIX_KEY_TERMS_VAL}"),
            ("Lenses (Ranked)", project_dir / f"{base}{config.SUFFIX_LENSES}"),
            ("Scored Emphasis", project_dir /
             f"{base}{config.SUFFIX_EMPHASIS_SCORED}"),
            ("Bowen References", project_dir /
             f"{base}{config.SUFFIX_BOWEN}"),
            ("Gen Abstract", project_dir /
             f"{base}{config.SUFFIX_ABSTRACT_GEN}"),
            ("Abstracts Val", project_dir /
             f"{base}{config.SUFFIX_ABSTRACT_VAL}"),
            ("Blog", project_dir / f"{base}{config.SUFFIX_BLOG}"),
            ("Overview", project_dir / f"{base}{config.SUFFIX_OVERVIEW}"),
            ("Webpage", project_dir /
             f"{base}{config.SUFFIX_WEBPAGE}"),
            ("Simple Web", project_dir /
             f"{base}{config.SUFFIX_WEBPAGE_SIMPLE}"),
            ("PDF", project_dir / f"{base}{config.SUFFIX_PDF}"),
            ("Package", project_dir / f"{base}.zip"),
        ]

        status_lines = [
            f"{ '✅' if path.exists() else '❌'} {label}" for label, path in checks]
        self.status_text.insert(1.0, "\n".join(status_lines))

    def log(self, message, *args):
        if args:
            try:
                text = str(message) % args
            except TypeError:
                text = f"{message} {args}"
        else:
            text = str(message)
        if threading.current_thread() is threading.main_thread():
            self._append_log_text(text)
        else:
            self.root.after(0, self._append_log_text, text)

    def _append_log_text(self, text: str):
        """Append text to the GUI log safely on the Tk main thread."""
        # Truncate log if it gets too long (prevent memory issues)
        num_lines = int(self.log_text.index('end-1c').split('.')[0])
        if num_lines > 5000:
            self.log_text.delete(1.0, 501.0)
            self.log_text.insert(
                tk.END, "\n... [Older logs truncated to save memory] ...\n")

        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def set_status(self, message, color="black"):
        if threading.current_thread() is threading.main_thread():
            self._apply_status(message, color)
        else:
            self.root.after(0, self._apply_status, message, color)

    def set_final_status(self, message, color="black"):
        """Set a terminal status message that _execute_task will NOT overwrite
        with its generic 'Task completed/failed' text -- so a multi-step task can
        report a specific final message (SB.1)."""
        self._task_set_final_status = True
        self.set_status(message, color)

    def _apply_status(self, message, color="black"):
        """Update status label safely on the Tk main thread. No-ops if the widget
        isn't built yet (e.g. headless test instances constructed via __new__)."""
        if getattr(self, "status_label", None) is None:
            return
        self.status_label.config(text=message, foreground=color)
        self.root.update_idletasks()

    def run_task_in_thread(self, task_function, *args, task_name=None, **kwargs):
        if self.processing:
            self.log("⚠️ A task is already running. Please wait for it to finish.")
            return
        self.processing = True
        self.progress.start()
        # Immediately clear the old status and show the task is running, so the
        # bottom bar updates on click (not only when the task finishes). A
        # multi-stage run overrides this with per-step status right away.
        display = task_name or getattr(task_function, "__name__", "task").lstrip("_").replace("_", " ")
        self.set_status(f"Running {display}…", "blue")
        self.update_button_states()

        thread = threading.Thread(
            target=self._execute_task,
            args=(task_function, task_name) + args,
            kwargs=kwargs
        )
        thread.daemon = True
        thread.start()

    def _execute_task(self, task_function, task_name, *args, **kwargs):
        name = task_name if task_name else task_function.__name__
        # A task may set its own specific terminal message via set_final_status;
        # if it does, don't clobber it with the generic text below (SB.1).
        self._task_set_final_status = False
        try:
            success = task_function(*args, **kwargs)

            # If the task is waiting for a user dialog, don't log completion.
            if success == "WAITING_FOR_USER":
                self.processing = False
                self.progress.stop()
                self.root.after(0, self.update_button_states)
                return

            if success:
                if not self._task_set_final_status:
                    self.set_status("Task completed successfully.", "green")
                self.log("✅ %s completed successfully.", name)
            else:
                if not self._task_set_final_status:
                    self.set_status("Task failed.", "red")
                self.log("❌ %s failed. Check logs for details.", name)
        except Exception as e:
            self.set_status(f"Error: {e}", "red")
            self.log("❌ Error during %s: %s", name, e)
        finally:
            self.processing = False
            self.progress.stop()
            self.root.after(0, self.update_button_states)
            self.root.after(0, self.check_file_status)

    def do_initial_validation(self):
        """Run the initial validation step on the selected transcript."""
        if not self.selected_file:
            return
        existing_versions = _find_existing_validation_versions(self.selected_file)
        if existing_versions:
            version_names = ", ".join(path.name for path in existing_versions[:5])
            if len(existing_versions) > 5:
                version_names += ", ..."
            messagebox.showwarning(
                "Existing Validation Versions",
                "Move or delete the existing Init Val versions and restart from the base file.\n\n"
                f"Found: {version_names}",
            )
            self.log(
                "⚠️ Existing Init Val versions found for %s. Move or delete them and restart.",
                self.selected_file.name,
            )
            return
        self.log("STEP 0: Initial Transcript Validation...")
        self.log(
            "Init Val runtime: commit=%s filter=%s terms=%s source=%s",
            _current_git_revision(),
            INIT_VAL_FILTER_VERSION,
            config.VALIDATION_APPROVED_TERMS_PATH,
            self.selected_file,
        )
        self.run_task_in_thread(self._run_initial_validation)

    def _run_initial_validation(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            self.log("❌ Error: ANTHROPIC_API_KEY not found.")
            return False

        mode = self.validation_mode_var.get()
        self.log(f"Starting Initial Validation (Mode: {mode.upper()})...")

        try:
            findings = []
            file_to_validate = None
            
            if mode == "v2":
                validator = transcript_initial_validation_v2.TranscriptValidatorV2(api_key, self.logger)
                # Use latest version logic (reusing V1's helper for now or just checking path)
                # V2 doesn't have `get_latest_version` explicitly exposed in my previous code, 
                # but we can assume we want to process self.selected_file or its latest variant.
                # Let's use the V1 helper to find the latest file, as it's file-system based.
                v1_validator = transcript_initial_validation.TranscriptValidator(api_key, self.logger)
                file_to_validate = v1_validator.get_latest_version(self.selected_file)
                
                if file_to_validate != self.selected_file:
                     self.log("ℹ️  Auto-detected latest version: %s", file_to_validate.name)

                # V2 Validate (Chunked)
                # Use DEFAULT_MODEL for validation as configured
                findings = validator.validate_chunked(file_to_validate, model=config.settings.DEFAULT_MODEL)
                
            else:
                # Legacy V1
                validator = transcript_initial_validation.TranscriptValidator(api_key, self.logger)
                file_to_validate = validator.get_latest_version(self.selected_file)
                if file_to_validate != self.selected_file:
                    self.log("ℹ️  Auto-detected latest version: %s", file_to_validate.name)
                
                findings = validator.validate(file_to_validate)

            if not findings:
                self.log("✅ No issues found.")
                self.root.after(
                    0, lambda: self._prompt_finalize_no_issues(file_to_validate))
                return "WAITING_FOR_USER"

            self.log("⚠️ Found %d issues.", len(findings))

            # Instead of applying immediately, show the review dialog on main thread
            self.log("Waiting for user review in popup dialog...")
            self.root.after(0, lambda: self.show_validation_dialog(
                findings, file_to_validate))
            return "WAITING_FOR_USER"

        except Exception as e:
            self.log("❌ Validation failed: %s", e)
            import traceback
            traceback.print_exc()
            return False

    def _prompt_finalize_no_issues(self, source_file):
        if messagebox.askyesno("Validation Complete", "No issues found. Create final validated copy?"):
            self.run_task_in_thread(
                self._apply_validation_corrections, [], [], [], [], source_file, True)

    def show_validation_dialog(self, findings, source_file):
        prepared_findings, omitted_count = _prepare_review_findings(findings)

        if findings and not prepared_findings:
            self.log(
                "Found %d issues, but all were filtered as non-lexical suggestions.", len(
                    findings)
            )
            messagebox.showinfo(
                "Validation Notice",
                f"Initial Validation found {len(findings)} potential issues, but all were broad, "
                "sentence-level suggestions not suitable for simple dictionary correction.\n\n"
                "No manual review is needed for these items."
            )
            self._prompt_finalize_no_issues(source_file)
        else:
            ValidationReviewDialog(self.root, findings,
                                   lambda corrections, rejected, approved_terms, aliases, finalize: self._handle_validation_apply(corrections, rejected, approved_terms, aliases, source_file, finalize))

    def _handle_validation_apply(self, corrections, rejected_findings, approved_terms, aliases, source_file, finalize):
        if not corrections and not rejected_findings and not approved_terms and not aliases and not finalize:
            self.log("No corrections selected.")
            return

        msg = (
            f"Applying {len(corrections)} corrections..."
            if corrections
            else "Finalizing file..."
        )
        self.log(msg)

        self.run_task_in_thread(
            self._apply_validation_corrections, corrections, rejected_findings, approved_terms, aliases, source_file, finalize)

    def _apply_validation_corrections(self, corrections, rejected_findings, approved_terms, aliases, source_file, finalize):
        # Determine output filename logic (v1, v2...)
        stem = source_file.stem

        # Strip existing version/validated suffixes to find base
        # e.g. "Name_v1" -> "Name", "Name_validated" -> "Name"
        base_match = re.match(r'^(.*)(_v\d+|_validated)$', stem)
        base_name = base_match.group(1) if base_match else stem

        if finalize:
            new_filename = f"{base_name}_validated{source_file.suffix}"
        else:
            # Determine next version
            # If current is _vN, next is _v(N+1). If current is base, next is _v1.
            version_match = re.search(r'_v(\d+)$', stem)
            if version_match:
                version = int(version_match.group(1)) + 1
            else:
                version = 1
            new_filename = f"{base_name}_v{version}{source_file.suffix}"

        output_path = source_file.parent / new_filename
        api_key = os.getenv("ANTHROPIC_API_KEY")
        mode = self.validation_mode_var.get()

        if rejected_findings:
            promoted = record_validation_rejections(
                rejected_findings, logger=self.logger
            )
            self.log(
                "Recorded %d rejected finding(s) to validation memory%s.",
                len(rejected_findings),
                f"; promoted {promoted} blocked pair(s)" if promoted else "",
            )

        if approved_terms:
            added = append_approved_terms(approved_terms)
            self.log(
                "Added %d approved term(s)/phrase(s) to %s.",
                added,
                config.VALIDATION_APPROVED_TERMS_FILENAME,
            )

        if aliases:
            added_aliases = append_validation_aliases(aliases)
            self.log(
                "Added %d deterministic alias(es) to %s.",
                added_aliases,
                config.VALIDATION_APPROVED_TERMS_FILENAME,
            )

        self.log("🛠️ Writing to -> %s", new_filename)

        if not corrections and finalize:
             # Just copy
             shutil.copy2(source_file, output_path)
             self.log("No corrections to apply. Created copy.")
        else:
            if mode == "v2":
                validator = transcript_initial_validation_v2.TranscriptValidatorV2(api_key, self.logger)
                try:
                    out_path, applied, skipped = validator.apply_corrections_safe(source_file, corrections, output_path)
                    self.log(f"Applied {applied} corrections safely.")
                    if skipped:
                        self.log(f"⚠️ Skipped {len(skipped)} ambiguous corrections (see log for details).")
                except Exception as e:
                    self.log(f"❌ Error applying V2 corrections: {e}")
                    return False
            else:
                # V1 Legacy
                validator = transcript_initial_validation.TranscriptValidator(api_key, self.logger)
                validator.apply_corrections(source_file, corrections, output_path)

        # Update selected file to the new one so next run uses it automatically
        self.selected_file = output_path
        self.base_name = clean_project_name(self.selected_file.stem)

        # Update formatted file path expectation (though format step hasn't run yet)
        self.formatted_file = config.PROJECTS_DIR / self.base_name / \
            f"{self.base_name}{config.SUFFIX_FORMATTED}"

        # Refresh list to show the new file
        self.root.after(0, self.refresh_file_list)
        self.root.after(0, self.check_file_status)

        if not finalize:
            self.log("🔄 Re-running validation on new version...")
            self.root.after(1000, self.do_initial_validation)
        else:
            self.log("✅ Final validated copy created. Ready for processing.")

        return True

    def do_format_validate(self):
        """Run the formatting and format validation steps."""
        if not self.selected_file:
            return
        self.log("STEP 1: Formatting and validating transcript...")
        self.run_task_in_thread(self._run_format_and_validate)

    def _run_format_and_validate(self):
        # Use config.settings.FORMATTING_MODEL
        if not pipeline.format_transcript(self.selected_file.name, logger=self.logger, model=config.settings.FORMATTING_MODEL): # MODIFIED
            return False
        self.log("Format complete. Now validating...")
        if not pipeline.validate_format(self.selected_file.name, logger=self.logger):
            self.log("❌ Validation failed. Please check the logs.")
            return False
        return True

    def do_validate_headers(self):
        """Run the header validation step."""
        if not self.formatted_file or not self.formatted_file.exists():
            messagebox.showwarning(
                "Not Ready", "Please format the transcript first.")
            return
        self.log("STEP 2: Validating Headers...")
        self.run_task_in_thread(self._run_header_validation)

    def _run_header_validation(self):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            self.log("❌ Error: ANTHROPIC_API_KEY not found.")
            return False
        validator = transcript_validate_headers.HeaderValidator(
            api_key, self.logger)
        return validator.run(self.formatted_file, model=config.settings.AUX_MODEL) # MODIFIED

    def do_add_yaml(self):
        """Add YAML front matter to the formatted transcript."""
        if not self.formatted_file or not self.formatted_file.exists():
            messagebox.showwarning(
                "Not Ready", "Please format the transcript first.")
            return
        self.log("STEP 2: Adding YAML Front Matter...")
        self.run_task_in_thread(
            pipeline.add_yaml, self.formatted_file.name, "mp4", self.logger) # No model parameter here

    def _resolve_individual_extraction_input(self):
        """Resolve the best available input for standalone quote extraction."""
        if not self.selected_file or not self.base_name:
            return None, None

        yaml_file = config.PROJECTS_DIR / self.base_name / f"{self.base_name}{config.SUFFIX_YAML}"
        if yaml_file.exists():
            return yaml_file.name, "YAML transcript"

        formatted_file = config.PROJECTS_DIR / self.base_name / f"{self.base_name}{config.SUFFIX_FORMATTED}"
        if formatted_file.exists():
            return formatted_file.name, "formatted transcript"

        if self.selected_file.exists():
            return str(self.selected_file), "selected source text file"

        return None, None

    def _get_bool_var(self, attr_name, default=False):
        """Safely read a Tk boolean variable, tolerating headless test instances."""
        value = getattr(self, attr_name, None)
        if value is None:
            return default
        if hasattr(value, "get"):
            return bool(value.get())
        return bool(value)

    def do_extract_bowen_emphasis(self):
        """Extract Bowen references and scored emphasis together."""
        if not self.base_name:
            return

        input_file, source_label = self._resolve_individual_extraction_input()
        if not input_file:
            messagebox.showwarning(
                "Not Ready", "Please select a transcript file first.")
            return

        self.log(
            "STEP: Extracting Bowen References + Scored Emphasis from %s...",
            source_label,
        )
        self.run_task_in_thread(
            pipeline.extract_bowen_and_emphasis,
            input_file,
            config.settings.DEFAULT_MODEL,
            self.logger,
            task_name="Bowen + Emphasis Extraction",
        )

    def do_summaries(self):
        """Run core extraction: abstract, structural/interpretive themes, topics, terms, lenses."""
        yaml_file = (config.PROJECTS_DIR / self.base_name /
                     f"{self.base_name}{config.SUFFIX_YAML}")
        if not yaml_file.exists():
            if self.formatted_file.exists():
                with open(self.formatted_file, 'r', encoding='utf-8') as f:
                    # A simple check for YAML front matter
                    if not f.read(10).startswith('---'):
                        messagebox.showwarning(
                            "Not Ready", "Please add YAML front matter first.")
                        return
            else:
                messagebox.showwarning(
                    "Not Ready", "Please format and add YAML first.")
                return
        extras = []
        include_bowen = self._get_bool_var("include_bowen_core", default=True)
        include_emphasis = self._get_bool_var("include_emphasis_core", default=True)
        if include_bowen:
            extras.append("Bowen")
        if include_emphasis:
            extras.append("Emphasis")
        extras_text = f" + {'/'.join(extras)}" if extras else ""
        self.log(
            "STEP 4: Core extraction (Abstract + ST/IT/Topics/Terms/Lenses%s)...",
            extras_text,
        )
        self.run_task_in_thread(
            pipeline.summarize_transcript,
            f"{self.base_name}{config.SUFFIX_YAML}",
            config.settings.DEFAULT_MODEL, # MODIFIED
            "Family Systems",
            "General public",
            False,  # skip_extracts_summary
            not include_emphasis,
            not include_bowen,
            True,   # skip_blog
            logger=self.logger,
            task_name="Core Extraction",
        )

    def do_generate_blog(self):
        """Generate a blog post from validated top-ranked lens (#1)."""
        if not self.base_name:
            return
        self.log("STEP 7: Generating Blog Post from Lens #1...")
        self.run_task_in_thread(
            pipeline.summarize_transcript,
            f"{self.base_name}{config.SUFFIX_YAML}",
            config.settings.DEFAULT_MODEL, # MODIFIED
            "Family Systems",
            "General public",
            True,   # skip_extracts_summary
            True,   # skip_emphasis
            True,   # skip_bowen
            False,  # skip_blog
            logger=self.logger,
            task_name="Blog Post (Top Lens)",
        )

    def do_generate_overview(self):
        """Generate a GEO-optimized overview post from upstream artifacts.

        Purpose: Trigger summarize_transcript with skip_overview=False only.
        Spec:    docs/implementation_plan_2026-05-13.md#OV.7
        Tests:   tests/test_overview_post.py
        """
        if not self.base_name:
            return
        self.log("STEP 7b: Generating Overview Post (GEO)...")
        self.run_task_in_thread(
            pipeline.summarize_transcript,
            f"{self.base_name}{config.SUFFIX_YAML}",
            config.settings.DEFAULT_MODEL,
            "Family Systems",
            "General public",
            True,   # skip_extracts_summary
            True,   # skip_emphasis
            True,   # skip_bowen
            True,   # skip_blog
            False,  # skip_overview
            logger=self.logger,
            task_name="Overview Post (GEO)",
        )

    def do_estimate_cost(self):
        """Estimate the token usage and cost for processing the transcript."""
        if not self.selected_file:
            return
        self.log("STEP: Estimating Token Usage and Cost...")
        self.run_task_in_thread(self._run_cost_estimation)

    def _run_cost_estimation(self):
        try:
            estimator = transcript_cost_estimator.CostEstimator(
                self.selected_file, logger=self.logger)
            estimator.run_full_estimation()
            return True
        except Exception as e:
            self.log("❌ Error estimating cost: %s", e)
            return False

    def do_config_check(self):
        """Run a configuration check and log the results."""
        self.log("STEP: Checking Configuration...")
        self.run_task_in_thread(self._run_config_check)

    def _run_config_check(self):
        try:
            f = io.StringIO()
            with redirect_stdout(f):
                transcript_config_check.main()
            self.log(f.getvalue())
            return True
        except Exception as e:
            self.log(f"❌ Error checking config: {e}")
            return False

    def do_extract_emphasis(self):
        """Extract scored emphasis items from the transcript."""
        if not self.base_name:
            return

        input_file, source_label = self._resolve_individual_extraction_input()
        if not input_file:
            messagebox.showwarning(
                "Not Ready", "Please select a transcript file first.")
            return

        self.log("STEP: Extracting Scored Emphasis from %s...", source_label)
        self.run_task_in_thread(
            pipeline.extract_scored_emphasis,
            input_file,
            config.settings.DEFAULT_MODEL,
            self.logger,
            task_name="Emphasis Extraction",
        )

    def do_extract_bowen(self):
        """Extract Bowen references from the transcript."""
        if not self.base_name:
            return

        input_file, source_label = self._resolve_individual_extraction_input()
        if not input_file:
            messagebox.showwarning(
                "Not Ready", "Please select a transcript file first.")
            return

        self.log("STEP: Extracting Bowen References from %s...", source_label)
        self.run_task_in_thread(
            pipeline.extract_bowen_references_from_transcript,
            input_file,
            config.settings.DEFAULT_MODEL,
            self.logger,
            task_name="Bowen Extraction",
        )

    def do_generate_structured_abstract(self):
        """Generate a structured abstract from the transcript."""
        if not self.base_name:
            return
        self.log("STEP 5: Generating Structured Abstract...")
        self.run_task_in_thread(
            pipeline.generate_structured_abstract, self.base_name, self.logger, model=config.settings.AUX_MODEL)

    def do_validate_abstracts(self):
        """Validate the generated abstract for coverage."""
        if not self.base_name:
            return
        self.log("STEP 6: Validating Abstracts (Coverage Check)...")
        # Using the new validation pipeline
        self.run_task_in_thread(
            pipeline.validate_abstract_coverage, self.base_name, self.logger, model=config.settings.DEFAULT_MODEL) # MODIFIED

    def do_generate_web_pdf(self):
        """Generate Webpage and PDF artifacts."""
        if not self.base_name:
            return
        self.log("STEP 8: Creating Web & PDF...")
        self.run_task_in_thread(self._run_web_pdf_generation)

    def _run_web_pdf_generation(self):
        success = True
        self.log("  - Generating full webpage...")
        if not pipeline.generate_webpage(self.base_name):
            self.log("  - Full webpage generation failed.")
            success = False
        self.log("  - Generating PDF...")
        if not pipeline.generate_pdf(self.base_name):
            self.log("  - PDF generation failed.")
            success = False

        self.log("  - Validating full webpage...")
        f = io.StringIO()
        with redirect_stdout(f):
            transcript_validate_webpage.validate_webpage(self.base_name)

        validation_output = f.getvalue()
        self.log(validation_output)
        print(validation_output)
        return success

    def do_package(self):
        """Package all generated artifacts into a ZIP file."""
        if not self.base_name:
            return
        self.log("STEP 9: Packaging Artifacts...")
        self.run_task_in_thread(
            pipeline.package_transcript, self.base_name, self.logger)

    def do_clean_logs(self):
        """Handle log cleanup with user confirmation."""
        if self.processing:
            messagebox.showwarning(
                "Busy", "Cannot clean logs while a process is running.")
            return

        should_archive = messagebox.askyesnocancel(
            "Clean Log Files",
            "Do you want to ARCHIVE old logs before deleting them?\n\n"
            " • Yes: Archive logs to a zip file, then delete originals.\n"
            " • No: Permanently delete logs without archiving.\n"
            " • Cancel: Do nothing.",
            icon='warning'
        )

        if should_archive is True:
            self.log("Archiving log files...")
            self.run_task_in_thread(self._run_archive_logs)
        elif should_archive is False:
            if messagebox.askokcancel("Confirm Permanent Deletion", "This will PERMANENTLY DELETE all log files. This action cannot be undone.\n\nAre you sure?"):
                self.log("Deleting log files...")
                self.run_task_in_thread(self._run_delete_logs)
            else:
                self.log("Log deletion cancelled.")
        else:
            self.log("Log cleanup cancelled.")

    def _run_archive_logs(self):
        """Archive logs to a zip file and remove originals."""
        logs_dir = config.LOGS_DIR
        if not logs_dir.exists():
            self.log(f"Logs directory not found: {logs_dir}")
            return False

        files_to_process = list(logs_dir.glob(
            "*.log")) + list(logs_dir.glob("*.csv"))
        if not files_to_process:
            self.log("No log files found to archive.")
            return True

        archives_dir = logs_dir / "archives"
        archives_dir.mkdir(exist_ok=True)
        zip_base_name = (archives_dir /
                         f"logs_{datetime.now():%Y%m%d_%H%M%S}")

        try:
            shutil.make_archive(str(zip_base_name), 'zip',
                                logs_dir, verbose=True)
            self.log("✅ Archive created: %s.zip", zip_base_name)
            for f in files_to_process:
                f.unlink()
            self.log("✅ Original log files removed.")
            return True
        except Exception as e:
            self.log("❌ Error during archiving: %s", e)
            return False

    def _run_delete_logs(self):
        """Permanently delete log files and token usage CSV."""
        return pipeline.delete_logs(logger=self.logger)

    # ------------------------------------------------------------------
    # Stage-selection execution (Spec: docs/spec_stage_selection_2026-07-12.md)
    # ------------------------------------------------------------------

    def _stage_artifact_path(self, artifact_suffix_attr):
        """Resolve the on-disk path for a stage's produced artifact.

        Purpose: Single shared path-builder used by both the pre-flight
                 dependency validator and the _run_stage_* wrappers, so the
                 validator's notion of "does this artifact exist" can never
                 drift from where a stage actually reads/writes it.
        Spec:    docs/spec_stage_selection_2026-07-12.md#SS.14
        """
        suffix = getattr(config, artifact_suffix_attr)
        return config.PROJECTS_DIR / self.base_name / f"{self.base_name}{suffix}"

    def _stage_outputs_status(self, key):
        """Report a stage's on-disk output status for the selective-run log.

        Purpose: Tell the operator whether a checked stage will generate fresh
                 output or REGENERATE (overwrite) existing output, using the
                 STAGE_OUTPUTS producer map so status can't drift from what the
                 stage actually writes (P19).
        Spec:    docs/spec_selective_rerun_2026-07-16.md#SR.2

        Returns (all_present, present_attrs, missing_attrs). `all_present` is
        True only when EVERY declared output exists (the "all present = exists"
        rule). A stage with no declared outputs (e.g. init_val) returns
        (False, [], []) -- always treated as "will generate".
        """
        attrs = STAGE_OUTPUTS.get(key, [])
        if not attrs:
            return (False, [], [])
        present, missing = [], []
        for attr in attrs:
            if self._stage_artifact_path(attr).exists():
                present.append(attr)
            else:
                missing.append(attr)
        return (len(missing) == 0, present, missing)

    def _log_selective_run_plan(self, selected_keys):
        """Log, per checked stage, generate-vs-regenerate, plus which unchecked
        prerequisites are reused from disk. Spec: SR.5."""
        reused = []
        for key, label in STAGE_DEFINITIONS:
            if key not in selected_keys:
                continue
            all_present, _present, _missing = self._stage_outputs_status(key)
            if all_present:
                self.log("  ↻ %s — output exists, will REGENERATE (overwrite)", label)
            else:
                self.log("  ＋ %s — will generate", label)
            # Prerequisites satisfied from disk (producing stage not selected).
            for group in STAGE_DEPENDENCIES.get(key, []):
                for producing_stage, artifact_attr in group:
                    if producing_stage in selected_keys:
                        continue
                    path = self._stage_artifact_path(artifact_attr)
                    if path.exists() and artifact_attr not in reused:
                        reused.append(artifact_attr)
        if reused:
            names = ", ".join(ARTIFACT_LABELS.get(a, a) for a in reused)
            self.log("  ↺ Reusing existing output from disk: %s", names)

    def _validate_stage_dependencies(self, selected_keys):
        """Check every selected stage's prerequisite groups.

        Purpose: Synchronous pre-flight check that blocks a doomed run
                 before the confirmation dialog / background thread starts.
        Spec:    docs/spec_stage_selection_2026-07-12.md#SS.14

        Returns a list of (stage_label, [missing_group_description, ...])
        for every selected stage with at least one unmet dependency group,
        in STAGE_DEFINITIONS order. A group is satisfied if ANY pair in it
        is satisfied (producing stage also selected, or its artifact exists
        on disk right now); a stage is satisfied only if EVERY group is.
        """
        unmet = []
        for key, label in STAGE_DEFINITIONS:
            if key not in selected_keys:
                continue
            missing_descriptions = []
            for group in STAGE_DEPENDENCIES.get(key, []):
                group_satisfied = False
                for producing_stage, artifact_suffix_attr in group:
                    if producing_stage in selected_keys:
                        group_satisfied = True
                        break
                    if self._stage_artifact_path(artifact_suffix_attr).exists():
                        group_satisfied = True
                        break
                if not group_satisfied:
                    labels = [
                        f'"{ARTIFACT_LABELS.get(attr, attr)}"'
                        for _, attr in group
                    ]
                    missing_descriptions.append(" or ".join(labels))
            if missing_descriptions:
                unmet.append((label, missing_descriptions))
        return unmet

    def _format_preflight_message(self, unmet):
        """Build the exact SS.15 blocking message body from unmet records."""
        lines = ["The following selected stage(s) are missing required prior output:"]
        for stage_label, missing_descriptions in unmet:
            joined = " and ".join(missing_descriptions)
            lines.append(f"  • {stage_label} needs {joined} to have run first")
        lines.append(
            "Check the required stage(s) above, or run them in an earlier session, then retry."
        )
        return "\n".join(lines)

    def do_run_selected(self):
        """Guarded entry point: runs exactly the checked stages, in order.

        Purpose: Data-driven replacement for the old hardcoded do_all_steps.
        Spec:    docs/spec_stage_selection_2026-07-12.md#SS.10
        """
        if not self.selected_file:
            return
        if self.processing:
            self.log("⚠️ Pipeline is already running.")
            return

        selected_keys = [key for key, _ in STAGE_DEFINITIONS if self.stage_vars[key].get()]
        if not selected_keys:
            messagebox.showwarning("No Stages Selected", "Please check at least one stage to run.")
            return

        unmet = self._validate_stage_dependencies(selected_keys)
        if unmet:
            messagebox.showwarning("Missing Prerequisites", self._format_preflight_message(unmet))
            return

        # Init Val is a precondition for `format`, which consumes the raw
        # (unvalidated) transcript. A selective re-run of downstream stages
        # instead reuses already-validated derived artifacts (formatted/yaml),
        # enforced by each stage's own dependency preflight above
        # (`_validate_stage_dependencies`) -- including bowen_emphasis, which now
        # requires a formatted/yaml artifact so it can't read the raw file. So
        # this guard need only fire for `format`, letting the user redo just
        # particular items (e.g. Bowen/Emphasis) without re-running Init Val.
        # Spec: spec_selective_rerun_2026-07-16.md#SR.3
        if (
            "format" in selected_keys
            and "init_val" not in selected_keys
            and "_validated" not in self.selected_file.name
        ):
            messagebox.showwarning(
                "Validation Required",
                "Please run '0. Init Val' and create a final validated copy (ending in '_validated') before running Format.",
            )
            return

        selected_labels = [label for key, label in STAGE_DEFINITIONS if key in selected_keys]
        confirm_text = (
            "This will run the following selected stage(s):\n\n"
            + "\n".join(f"  • {label}" for label in selected_labels)
            + "\n\nContinue?"
        )
        if not messagebox.askyesno("Confirm", confirm_text):
            return

        self.log("▶ STARTING SELECTED STAGES EXECUTION...")
        self.run_task_in_thread(self._run_selected_stages, selected_keys)

    def _run_selected_stages(self, selected_keys):
        """Run every selected stage in STAGE_DEFINITIONS order, halting on first failure.

        Purpose: Data-driven replacement for the old hardcoded _run_all_steps.
        Spec:    docs/spec_stage_selection_2026-07-12.md#SS.11
        """
        start_time = datetime.now()

        # Unconditional cost estimate first (informational, same as old _run_all_steps).
        self.set_status("Estimating cost…", "blue")
        self.log("\n--- STEP 0: Estimating Cost ---")
        if not self._run_cost_estimation():
            self.log("⚠️ Cost estimation failed; continuing with pipeline run.")

        # Selective-run transparency (SR.5): before running, say which checked
        # stages will regenerate existing output vs generate fresh, and which
        # unchecked prerequisites are reused from disk.
        self.log("\n--- Run plan ---")
        self._log_selective_run_plan(selected_keys)

        # Bottom status bar tracks the current major step (SB.1); the final
        # message is set by _execute_task on completion/failure.
        selected_labels = [l for k, l in STAGE_DEFINITIONS if k in selected_keys]
        for idx, (key, label) in enumerate(
            [(k, l) for k, l in STAGE_DEFINITIONS if k in selected_keys], start=1
        ):
            self.set_status(f"Step {idx}/{len(selected_labels)}: {label}…", "blue")
            self.log("\n--- %s ---", label)
            if not self.stage_runners[key]():
                self.set_final_status(f"❌ Failed at: {label}", "red")
                self.log("❌ %s failed. Halting run.", label)
                return False

        self.log("\n--- Token Usage Report ---")
        self.log(analyze_token_usage.generate_usage_report(since_timestamp=start_time))

        self.log("\n✅ SELECTED STAGES COMPLETE!")
        self.set_final_status(
            f"✅ Complete — {len(selected_labels)} stage(s): {selected_labels[-1]}", "green"
        )
        return True

    def _run_stage_yaml(self):
        """Runner for the 'yaml' stage. Spec: docs/spec_stage_selection_2026-07-12.md#SS.12"""
        return pipeline.add_yaml(self.formatted_file.name, "mp4", self.logger)

    def _run_stage_topics(self):
        """Runner for the standalone 'topics' stage.

        Spec:  docs/spec_lean_abstract_2026-07-13.md#LA.3
        Tests: tests/test_lean_abstract.py::test_la3_topics_stage_registered
        """
        self.log("Generating Topics (standalone)...")
        return pipeline.generate_topics(
            f"{self.base_name}{config.SUFFIX_YAML}",
            config.settings.DEFAULT_MODEL,
            self.logger,
        )

    def _run_stage_core(self):
        """Runner for the 'core' stage. Spec: docs/spec_stage_selection_2026-07-12.md#SS.12"""
        include_bowen = self._get_bool_var("include_bowen_core", default=True)
        include_emphasis = self._get_bool_var("include_emphasis_core", default=True)
        extras = []
        if include_bowen:
            extras.append("Bowen")
        if include_emphasis:
            extras.append("Emphasis")
        extras_text = f" + {'/'.join(extras)}" if extras else ""
        self.log("Core Extraction%s...", extras_text)
        return pipeline.summarize_transcript(
            f"{self.base_name}{config.SUFFIX_YAML}",
            config.settings.DEFAULT_MODEL,
            "Family Systems",
            "General public",
            False,  # skip_extracts_summary
            not include_emphasis,
            not include_bowen,
            True,   # skip_blog
            logger=self.logger,
        )

    def _run_stage_structured_summary(self):
        """Runner for the 'structured_summary' stage. Spec: docs/spec_stage_selection_2026-07-12.md#SS.12"""
        return pipeline.generate_structured_summary(
            self.base_name, logger=self.logger, model=config.settings.AUX_MODEL
        )

    def _run_stage_gen_abstract(self):
        """Runner for the 'gen_abstract' stage. Spec: docs/spec_stage_selection_2026-07-12.md#SS.12"""
        return pipeline.generate_structured_abstract(
            self.base_name, self.logger, model=config.settings.AUX_MODEL
        )

    def _run_stage_val_abstract(self):
        """Runner for the 'val_abstract' stage.

        Advisory (parity with `_run_header_validation`): a coverage FAIL is
        written to the report but does NOT halt the run, so downstream-independent
        stages (Bowen/Emphasis, blog, web/pdf) still complete. The true pass/fail
        is preserved by `validate_abstract_coverage` for the release gate and the
        standalone Validate-Abstract action; here we only decide whether to halt.

        Purpose: Run abstract-coverage validation without aborting the pipeline
                 on a content-quality miss.
        Spec:    docs/spec_stage_selection_2026-07-12.md#SS.12
        Tests:   tests/test_ts_gui_run_all.py::test_run_stage_val_abstract_advisory_does_not_halt
        """
        passed = pipeline.validate_abstract_coverage(
            self.base_name, self.logger, model=config.settings.DEFAULT_MODEL
        )
        if not passed:
            # Surface, don't silently drop (P2): the run continues, but say so.
            # `validate_abstract_coverage` returns False for either a content
            # coverage miss OR a could-not-verify (missing abstract / exception,
            # which it logs via logger.error). Don't imply "content miss" — point
            # at both the report and the log so a real error stays discoverable
            # (P14: an error condition must not read as an ordinary content "no").
            self.log(
                "⚠️ Abstract validation did not pass or could not complete — "
                "continuing (advisory). See '%s%s' and the run log for details.",
                self.base_name, config.SUFFIX_ABSTRACT_VAL,
            )
        return True

    def _run_stage_blog(self):
        """Runner for the 'blog' stage. Spec: docs/spec_stage_selection_2026-07-12.md#SS.12"""
        return pipeline.summarize_transcript(
            f"{self.base_name}{config.SUFFIX_YAML}",
            config.settings.DEFAULT_MODEL,
            "Family Systems",
            "General public",
            True,   # skip_extracts_summary
            True,   # skip_emphasis
            True,   # skip_bowen
            False,  # skip_blog
            logger=self.logger,
        )

    def _run_stage_overview(self):
        """Runner for the 'overview' stage. Spec: docs/spec_stage_selection_2026-07-12.md#SS.12"""
        return pipeline.summarize_transcript(
            f"{self.base_name}{config.SUFFIX_YAML}",
            config.settings.DEFAULT_MODEL,
            "Family Systems",
            "General public",
            True,   # skip_extracts_summary
            True,   # skip_emphasis
            True,   # skip_bowen
            True,   # skip_blog
            False,  # skip_overview
            logger=self.logger,
        )

    def _run_stage_bowen_emphasis(self):
        """Runner for the 'bowen_emphasis' stage. Spec: docs/spec_stage_selection_2026-07-12.md#SS.12"""
        input_file, source_label = self._resolve_individual_extraction_input()
        if not input_file:
            self.log("❌ Bowen + Emphasis: no valid input file found.")
            return False
        self.log(
            "Extracting Bowen References + Scored Emphasis from %s...", source_label
        )
        return pipeline.extract_bowen_and_emphasis(
            input_file,
            config.settings.DEFAULT_MODEL,
            self.logger,
        )

    def _run_stage_package(self):
        """Runner for the 'package' stage. Spec: docs/spec_stage_selection_2026-07-12.md#SS.12"""
        return pipeline.package_transcript(self.base_name, self.logger)

    def _run_stage_bundle(self):
        """Runner for the 'bundle' stage: export the MD collection using the
        default format + all configured sections. Spec: spec_bundle_export#BE.10."""
        return pipeline.export_bundle(
            self.base_name, fmt=config.BUNDLE_DEFAULT_FORMAT, logger=self.logger
        )

    def _run_bundle_export(self, selected_keys, fmt):
        """Generate a bundle from a user-selected subset of sections + format on
        a background thread (post-run dialog). Spec: spec_bundle_export#BE.9."""
        if not self.base_name:
            messagebox.showwarning("No Run Selected", "Select or run a transcript first.")
            return
        sections = [s for s in config.BUNDLE_SECTIONS if s["key"] in selected_keys]
        if not sections:
            messagebox.showwarning("No Sections", "Select at least one section to include.")
            return
        self.log("Creating bundle (%s) with %d section(s)...", fmt, len(sections))
        self.run_task_in_thread(
            pipeline.export_bundle, self.base_name, fmt, sections, self.logger,
            task_name=f"bundle export ({fmt})",
        )

    def open_bundle_dialog(self):
        """Post-run dialog: pick which sections to include and the output format,
        then generate. Spec: spec_bundle_export#BE.9."""
        if not self.base_name:
            messagebox.showwarning("No Run Selected", "Select or run a transcript first.")
            return
        dlg = tk.Toplevel(self.root)
        dlg.title("Create Bundle (DOC/PDF)")
        dlg.grab_set()
        frame = ttk.Frame(dlg, padding="12")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        ttk.Label(frame, text="Include sections:").grid(
            row=0, column=0, columnspan=2, sticky=tk.W)
        section_vars = {}
        for i, section in enumerate(config.BUNDLE_SECTIONS):
            var = tk.BooleanVar(value=True)
            section_vars[section["key"]] = var
            ttk.Checkbutton(frame, text=section["heading"], variable=var).grid(
                row=i + 1, column=0, columnspan=2, sticky=tk.W)

        fmt_var = tk.StringVar(value=config.BUNDLE_DEFAULT_FORMAT)
        fmt_row = len(config.BUNDLE_SECTIONS) + 1
        ttk.Label(frame, text="Format:").grid(row=fmt_row, column=0, sticky=tk.W, pady=(8, 0))
        fmt_frame = ttk.Frame(frame)
        fmt_frame.grid(row=fmt_row, column=1, sticky=tk.W, pady=(8, 0))
        for f in ("pdf", "docx", "both"):
            ttk.Radiobutton(fmt_frame, text=f.upper(), variable=fmt_var, value=f).pack(side=tk.LEFT)

        def generate():
            selected = [key for key, v in section_vars.items() if v.get()]
            dlg.destroy()
            self._run_bundle_export(selected, fmt_var.get())

        btns = ttk.Frame(frame)
        btns.grid(row=fmt_row + 1, column=0, columnspan=2, pady=(12, 0))
        ttk.Button(btns, text="Generate", command=generate).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btns, text="Cancel", command=dlg.destroy).pack(side=tk.LEFT)

    @property
    def stage_runners(self):
        """Map every STAGE_DEFINITIONS key to its runner (bound method).

        Purpose: Provide the stage-key → runner mapping. Implemented as a
                 property (not an __init__ dict) so it is reachable on a
                 headlessly-constructed instance without a Tk mainloop; a
                 setter stores an override so tests can inject mock runners.
        Spec:    docs/spec_stage_selection_2026-07-12.md#SS.12
        Tests:   tests/test_ts_gui_run_all.py::test_stage_runners_cover_all_keys
        """
        override = getattr(self, "_stage_runners_override", None)
        if override is not None:
            return override
        return {
            "init_val": self._run_initial_validation_auto,
            "format": self._run_format_and_validate,
            "val_headers": self._run_header_validation,
            "yaml": self._run_stage_yaml,
            "topics": self._run_stage_topics,
            "core": self._run_stage_core,
            "structured_summary": self._run_stage_structured_summary,
            "gen_abstract": self._run_stage_gen_abstract,
            "val_abstract": self._run_stage_val_abstract,
            "blog": self._run_stage_blog,
            "overview": self._run_stage_overview,
            "webpdf": self._run_web_pdf_generation,
            "bowen_emphasis": self._run_stage_bowen_emphasis,
            "package": self._run_stage_package,
            "bundle": self._run_stage_bundle,
        }

    @stage_runners.setter
    def stage_runners(self, value):
        self._stage_runners_override = value

    def _apply_stage_selection(self, name):
        """Load a saved stage selection into the checkboxes and core modifiers.

        Purpose: Apply a saved/default selection; unknown stage keys in the
                 saved data (e.g. from a stale/renamed stage) are ignored
                 rather than raising, so a partially-stale selection still
                 loads whatever keys remain valid.
        Spec:    docs/spec_stage_selection_2026-07-12.md#SS.13
        """
        selection = config.get_stage_selections().get(name)
        if not selection:
            return
        saved_stages = set(selection.get("stages", []))
        known_keys = {key for key, _ in STAGE_DEFINITIONS}
        # P2: surface (don't silently drop) any saved stage key that no longer
        # exists in STAGE_DEFINITIONS (e.g. a stage renamed/removed in a later
        # release). The valid keys still load; the unknown ones are reported.
        unknown_keys = saved_stages - known_keys
        if unknown_keys:
            self.log(
                "⚠️ Selection '%s' references %d unknown stage(s), skipped: %s",
                name,
                len(unknown_keys),
                ", ".join(sorted(unknown_keys)),
            )
        for key, _ in STAGE_DEFINITIONS:
            self.stage_vars[key].set(key in saved_stages)
        self.include_bowen_core.set(selection.get("include_bowen_core", True))
        self.include_emphasis_core.set(selection.get("include_emphasis_core", True))
        self.active_selection_var.set(name)

    def _apply_default_stage_selection(self):
        """Pre-tick the default saved selection at startup; never runs the pipeline.

        Spec: docs/spec_stage_selection_2026-07-12.md#SS.20
        """
        default_name = config.get_default_stage_selection()
        if not default_name:
            return
        if default_name not in config.get_stage_selections():
            return
        self._apply_stage_selection(default_name)

    def open_selection_manager_dialog(self):
        """Manage saved stage selections: load, save, set/clear default, delete.

        Spec: docs/spec_stage_selection_2026-07-12.md#SS.18
        """
        dlg = tk.Toplevel(self.root)
        dlg.title("Manage Selections")
        dlg.resizable(True, True)
        dlg.grab_set()

        frame = ttk.Frame(dlg, padding="12")
        frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        dlg.columnconfigure(0, weight=1)
        dlg.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)

        listbox = tk.Listbox(frame, height=10)
        listbox.grid(row=0, column=0, columnspan=2, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 8))

        def refresh_list():
            listbox.delete(0, tk.END)
            default_name = config.get_default_stage_selection()
            for name in sorted(config.get_stage_selections().keys()):
                prefix = "★ " if name == default_name else ""
                listbox.insert(tk.END, f"{prefix}{name}")

        def selected_name():
            selection = listbox.curselection()
            if not selection:
                return None
            text = listbox.get(selection[0])
            return text[2:] if text.startswith("★ ") else text

        def do_load():
            name = selected_name()
            if not name:
                return
            self._apply_stage_selection(name)
            self.log("Loaded stage selection '%s'.", name)

        def do_save_as():
            name = simpledialog.askstring("Save Current As", "Selection name:", parent=dlg)
            if not name:
                return
            if name in config.get_stage_selections():
                if not messagebox.askyesno(
                    "Overwrite?",
                    f"A selection named '{name}' already exists. Overwrite it?",
                    parent=dlg,
                ):
                    return
            selected_keys = [key for key, _ in STAGE_DEFINITIONS if self.stage_vars[key].get()]
            config.save_stage_selection(
                name,
                selected_keys,
                include_bowen_core=self.include_bowen_core.get(),
                include_emphasis_core=self.include_emphasis_core.get(),
            )
            self.active_selection_var.set(name)
            refresh_list()
            self.log("Saved stage selection '%s'.", name)

        def do_set_default():
            name = selected_name()
            if not name:
                return
            config.set_default_stage_selection(name)
            refresh_list()
            self.log("Set '%s' as default stage selection.", name)

        def do_clear_default():
            config.set_default_stage_selection(None)
            refresh_list()
            self.log("Cleared default stage selection.")

        def do_delete():
            name = selected_name()
            if not name:
                return
            if not messagebox.askyesno(
                "Confirm Delete", f"Delete saved selection '{name}'?", parent=dlg
            ):
                return
            config.delete_stage_selection(name)
            refresh_list()
            self.log("Deleted stage selection '%s'.", name)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, columnspan=2, sticky=(tk.W, tk.E))
        ttk.Button(btn_frame, text="Load", command=do_load).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Save Current As...", command=do_save_as).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(btn_frame, text="Set as Default", command=do_set_default).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(btn_frame, text="Clear Default", command=do_clear_default).pack(
            side=tk.LEFT, padx=(0, 5)
        )
        ttk.Button(btn_frame, text="Delete", command=do_delete).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(btn_frame, text="Close", command=dlg.destroy).pack(side=tk.RIGHT)

        refresh_list()

    def _run_initial_validation_auto(self):
        """Run Init Val without dialogs; auto-apply all findings into a finalized _validated file."""
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            self.log("❌ Error: ANTHROPIC_API_KEY not found.")
            return False

        existing_versions = _find_existing_validation_versions(self.selected_file)
        if existing_versions:
            version_names = ", ".join(path.name for path in existing_versions[:5])
            if len(existing_versions) > 5:
                version_names += ", ..."
            self.log(
                "❌ Existing Init Val versions found for %s. Move or delete them and restart from the base file. Found: %s",
                self.selected_file.name,
                version_names,
            )
            return False

        mode = self.validation_mode_var.get()
        self.log(
            "Init Val runtime: commit=%s filter=%s terms=%s source=%s mode=%s",
            _current_git_revision(),
            INIT_VAL_FILTER_VERSION,
            config.VALIDATION_APPROVED_TERMS_PATH,
            self.selected_file,
            mode,
        )
        try:
            findings = []
            file_to_validate = self.selected_file

            if mode == "v2":
                validator_v2 = transcript_initial_validation_v2.TranscriptValidatorV2(api_key, self.logger)
                validator_v1 = transcript_initial_validation.TranscriptValidator(api_key, self.logger)
                file_to_validate = validator_v1.get_latest_version(self.selected_file)
                findings = validator_v2.validate_chunked(file_to_validate, model=config.settings.DEFAULT_MODEL)
            else:
                validator_v1 = transcript_initial_validation.TranscriptValidator(api_key, self.logger)
                file_to_validate = validator_v1.get_latest_version(self.selected_file)
                findings = validator_v1.validate(file_to_validate, model=config.settings.DEFAULT_MODEL)

            stem = file_to_validate.stem
            base_match = re.match(r'^(.*)(_v\d+|_validated)$', stem)
            base_name = base_match.group(1) if base_match else stem
            output_path = file_to_validate.parent / f"{base_name}_validated{file_to_validate.suffix}"

            if findings:
                self.log("Auto-applying %d validation corrections...", len(findings))
                if mode == "v2":
                    validator_v2 = transcript_initial_validation_v2.TranscriptValidatorV2(api_key, self.logger)
                    _, applied, skipped = validator_v2.apply_corrections_safe(
                        file_to_validate, findings, output_path
                    )
                    self.log("Init Val auto-apply: applied=%d skipped=%d", applied, len(skipped))
                else:
                    validator_v1 = transcript_initial_validation.TranscriptValidator(api_key, self.logger)
                    validator_v1.apply_corrections(file_to_validate, findings, output_path)
            else:
                shutil.copy2(file_to_validate, output_path)
                self.log("No Init Val findings. Created validated copy.")

            self.selected_file = output_path
            self.base_name = clean_project_name(self.selected_file.stem)
            self.formatted_file = (
                config.PROJECTS_DIR / self.base_name / f"{self.base_name}{config.SUFFIX_FORMATTED}"
            )
            return True
        except Exception as e:
            self.log("❌ Initial validation auto failed: %s", e)
            return False

    def update_button_states(self):
        """Enable/disable every stage checkbox and action button.

        Purpose: Extend the enable/disable rule to every stage checkbox and
                 run_selected_btn; "Manage Selections..." stays always
                 enabled.
        Spec:    docs/spec_stage_selection_2026-07-12.md#SS.19
        """
        state = tk.NORMAL if not self.processing and self.selected_file else tk.DISABLED
        for chk in self.stage_checkbuttons.values():
            chk.config(state=state)
        self.run_selected_btn.config(state=state)
        # Manage Selections is always enabled (independent of file selection).
        self.cost_btn.config(state=state)
        self.cleanup_btn.config(state=state) # ADDED
        self.bundle_btn.config(state=state)  # launches a background export -> disable while busy
        # Config check button is always enabled
        self.core_emphasis_chk.config(state=state)
        self.core_bowen_chk.config(state=state)

        # ADDED: Update state of model comboboxes
        model_cb_state = "readonly" if not self.processing else tk.DISABLED
        self.default_model_cb.config(state=model_cb_state)
        self.aux_model_cb.config(state=model_cb_state)
        self.formatting_model_cb.config(state=model_cb_state)


def main():
    """Initialize and run the GUI application."""
    root = tk.Tk()
    TranscriptProcessorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
