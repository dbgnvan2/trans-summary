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
import threading
import tkinter as tk
from contextlib import redirect_stdout
from datetime import datetime
from tkinter import filedialog, messagebox, scrolledtext, ttk

import analyze_token_usage
import config
import pipeline
import cleanup_pipeline
import transcript_config_check
import transcript_cost_estimator
import transcript_initial_validation
import transcript_initial_validation_v2  # ADDED V2 module
import transcript_validate_headers
import transcript_validate_webpage
from transcript_utils import clean_project_name


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
        self.gui.log(f"{prefix}{text}")

    def debug(self, msg, *args, **kwargs):
        self.gui.log(f"🔍 {str(msg) % args if args else str(msg)}")
        # Also print to console for dev access
        print(f"DEBUG: {str(msg) % args if args else str(msg)}")


class ValidationReviewDialog(tk.Toplevel):
    """Dialog to review, edit, and accept/reject validation findings."""

    def __init__(self, parent, findings, apply_callback):
        super().__init__(parent)
        self.title("Review Transcript Corrections")
        self.geometry("1000x700")
        self.apply_callback = apply_callback
        self.findings = findings

        # Main container
        main_frame = ttk.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Instructions
        header_frame = ttk.Frame(main_frame)
        header_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(header_frame, text=f"Found {len(findings)} potential errors.", font=(
            "", 12, "bold")).pack(anchor="w")
        ttk.Label(header_frame, text="Review items below. Uncheck to reject. Edit the 'Correction' field to modify.").pack(
            anchor="w")

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

        for i, finding in enumerate(findings):
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

    def _create_item_row(self, index, finding):
        frame = ttk.LabelFrame(
            self.scrollable_frame, text=f"Issue #{index+1}: {finding.get('error_type', 'Unknown')}")
        frame.pack(fill=tk.X, expand=True, padx=5, pady=5)

        # Grid layout for the row
        frame.columnconfigure(1, weight=1)

        # Original
        ttk.Label(frame, text="Original:", font=("", 10, "bold")).grid(
            row=0, column=0, sticky="nw", padx=5, pady=2)
        ttk.Label(frame, text=f"\"{finding.get('original_text', '')}\"", wraplength=800).grid(
            row=0, column=1, sticky="w", padx=5, pady=2)

        # Reasoning
        ttk.Label(frame, text="Reasoning:", font=("", 10, "bold")).grid(
            row=1, column=0, sticky="nw", padx=5, pady=2)
        ttk.Label(frame, text=finding.get('reasoning', ''), wraplength=800).grid(
            row=1, column=1, sticky="w", padx=5, pady=2)

        # Correction (Editable)
        ttk.Label(frame, text="Correction:", font=("", 10, "bold")).grid(
            row=2, column=0, sticky="nw", padx=5, pady=2)

        correction_var = tk.StringVar(
            value=finding.get('suggested_correction', ''))
        entry = ttk.Entry(frame, textvariable=correction_var, width=80)
        entry.grid(row=2, column=1, sticky="w", padx=5, pady=2)

        # Checkbox
        apply_var = tk.BooleanVar(value=True)
        chk = ttk.Checkbutton(
            frame, text="Apply this correction", variable=apply_var)
        chk.grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=5)

        self.item_vars.append({
            'apply': apply_var,
            'correction': correction_var,
            'original_finding': finding
        })

    def on_apply(self, finalize=False):
        final_corrections = []
        for item in self.item_vars:
            if item['apply'].get():
                # Create a correction object based on the edited text
                correction = item['original_finding'].copy()
                correction['suggested_correction'] = item['correction'].get()
                final_corrections.append(correction)

        self.apply_callback(final_corrections, finalize)
        self.destroy()


class TranscriptProcessorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Transcript Processor")
        self.root.geometry("900x950")

        self.selected_file = None
        self.base_name = None
        self.formatted_file = None
        self.processing = False

        # Create logger adapter
        self.logger = GuiLoggerAdapter(self)

        # ADDED: StringVars for model selection
        self.model_vars = {
            "DEFAULT_MODEL": tk.StringVar(value=config.settings.DEFAULT_MODEL),
            "AUX_MODEL": tk.StringVar(value=config.settings.AUX_MODEL),
            "FORMATTING_MODEL": tk.StringVar(value=config.settings.FORMATTING_MODEL),
        }

        self.setup_ui()
        self.update_dir_label()
        self.refresh_file_list()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        
        # Configure row weights for resizing
        # Row 1 (File List): Expand slightly (weight 1)
        main_frame.rowconfigure(1, weight=1)
        # Row 4 (Log): Expand significantly (weight 3)
        main_frame.rowconfigure(4, weight=3)
        # Other rows (0, 2, 3, 5, 6, 7) have default weight 0 (fixed height)

        # Directory selection
        dir_frame = ttk.Frame(main_frame)
        dir_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        self.dir_label = ttk.Label(dir_frame, text="Transcripts Directory: ")
        self.dir_label.pack(side=tk.LEFT, padx=(0, 10))
        dir_btn = ttk.Button(dir_frame, text="Set Directory",
                             command=self.select_transcripts_directory)
        dir_btn.pack(side=tk.LEFT)

        # File selection
        file_frame = ttk.LabelFrame(
            main_frame, text="Select Source File", padding="10")
        file_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        file_frame.columnconfigure(0, weight=1)

        list_frame = ttk.Frame(file_frame)
        list_frame.grid(row=0, column=0, columnspan=2,
                        sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)
        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.file_listbox = tk.Listbox(
            list_frame, height=6, yscrollcommand=scrollbar.set)
        self.file_listbox.grid(
            row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

        refresh_btn = ttk.Button(
            file_frame, text="Refresh List", command=self.refresh_file_list)
        refresh_btn.grid(row=1, column=0, pady=(5, 0), sticky=tk.W)

        # Model Selection Frame - ADDED
        model_selection_frame = ttk.LabelFrame(main_frame, text="Model Selection", padding="10")
        model_selection_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        model_selection_frame.columnconfigure(1, weight=1) # Give the combobox column weight

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


        # Status and Log
        # Shifted row for these frames
        status_frame = ttk.LabelFrame(
            main_frame, text="File Status", padding="10")
        status_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(0, 10)) # MODIFIED row from 2 to 3
        status_frame.columnconfigure(0, weight=1)
        self.status_text = tk.Text(
            status_frame, height=10, wrap=tk.WORD, font=('Courier', 10))
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E))

        log_frame = ttk.LabelFrame(
            main_frame, text="Processing Log", padding="10")
        log_frame.grid(row=4, column=0, sticky=(
            tk.W, tk.E, tk.N, tk.S), pady=(0, 10)) # MODIFIED row from 3 to 4
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=('Courier', 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=5, column=0, sticky=(tk.W, tk.E), pady=(0, 10)) # MODIFIED row from 4 to 5

        # Action Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=6, column=0, sticky=(tk.W, tk.E)) # MODIFIED row from 5 to 6

        # Row 1 (buttons remain in button_frame)
        self.init_val_btn = ttk.Button(
            button_frame, text="0. Init Val", command=self.do_initial_validation, state=tk.DISABLED)
        self.init_val_btn.grid(row=0, column=0, padx=(0, 5), pady=2)

        self.format_btn = ttk.Button(
            button_frame, text="1. Format", command=self.do_format_validate, state=tk.DISABLED)
        self.format_btn.grid(row=0, column=1, padx=(0, 5), pady=2)

        self.headers_btn = ttk.Button(
            button_frame, text="2. Val Headers", command=self.do_validate_headers, state=tk.DISABLED)
        self.headers_btn.grid(row=0, column=2, padx=(0, 5), pady=2)

        self.yaml_btn = ttk.Button(
            button_frame, text="3. YAML", command=self.do_add_yaml, state=tk.DISABLED)
        self.yaml_btn.grid(row=0, column=3, padx=(0, 5), pady=2)

        self.summary_btn = ttk.Button(
            button_frame, text="4. Core (ST/IT/T/KT/L/BR/EM)", command=self.do_summaries, state=tk.DISABLED)
        self.summary_btn.grid(row=0, column=4, padx=(0, 5), pady=2)

        self.cost_btn = ttk.Button(
            button_frame, text="Est. Cost", command=self.do_estimate_cost, state=tk.DISABLED)
        self.cost_btn.grid(row=0, column=5, padx=(0, 5), pady=2)

        # Row 2
        self.gen_abstract_btn = ttk.Button(
            button_frame, text="5. Gen Abstract", command=self.do_generate_structured_abstract, state=tk.DISABLED)
        self.gen_abstract_btn.grid(row=1, column=2, padx=(0, 5), pady=2)

        self.abstracts_btn = ttk.Button(
            button_frame, text="6. Val Abstract", command=self.do_validate_abstracts, state=tk.DISABLED)
        self.abstracts_btn.grid(row=1, column=3, padx=(0, 5), pady=2)

        self.config_btn = ttk.Button(
            button_frame, text="Config Check", command=self.do_config_check)
        self.config_btn.grid(row=1, column=4, padx=(0, 5), pady=2)

        # Row 3
        self.blog_btn = ttk.Button(
            button_frame, text="7. Blog (Lens #1)", command=self.do_generate_blog, state=tk.DISABLED)
        self.blog_btn.grid(row=2, column=0, padx=(0, 5), pady=2)

        self.webpdf_btn = ttk.Button(
            button_frame, text="8. Full Web/PDF", command=self.do_generate_web_pdf, state=tk.DISABLED)
        self.webpdf_btn.grid(row=2, column=1, padx=(0, 5), pady=2)

        self.emphasis_btn = ttk.Button(
            button_frame, text="Emphasis", command=self.do_extract_emphasis, state=tk.DISABLED)
        self.emphasis_btn.grid(row=2, column=2, padx=(0, 5), pady=2)

        self.package_btn = ttk.Button(
            button_frame, text="Package", command=self.do_package, state=tk.DISABLED)
        self.package_btn.grid(row=2, column=3, padx=(0, 5), pady=2)

        self.clean_logs_btn = ttk.Button(
            button_frame, text="Clean Logs...", command=self.do_clean_logs)
        self.clean_logs_btn.grid(row=2, column=4, padx=(0, 5), pady=2)

        self.clear_btn = ttk.Button(
            button_frame, text="Clear Log", command=self.clear_log)
        self.clear_btn.grid(row=2, column=5, padx=(0, 5), pady=2)

        self.do_all_btn = ttk.Button(
            button_frame, text="▶ DO ALL STEPS", command=self.do_all_steps, state=tk.DISABLED)
        self.do_all_btn.grid(row=0, column=6, rowspan=3,
                             padx=(10, 5), sticky=(tk.N, tk.S))

        # Row 3 (Maintenance)
        self.cleanup_btn = ttk.Button(
            button_frame, text="Cleanup Source", command=self.do_cleanup, state=tk.DISABLED)
        self.cleanup_btn.grid(row=3, column=0, padx=(0, 5), pady=2)

        self.status_label = ttk.Label(
            main_frame, text="Ready", foreground="green")
        self.status_label.grid(row=7, column=0, pady=(5, 0), sticky=tk.W) # MODIFIED row from 7 to 8

        # Memory Usage Label
        self.memory_label = ttk.Label(
            main_frame, text="Mem: -- MB", foreground="gray")
        self.memory_label.grid(row=7, column=0, pady=(5, 0), sticky=tk.E)

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
            title="Select Transcripts Directory")
        if dir_path:
            config.set_transcripts_base(dir_path)
            self.update_dir_label()
            self.refresh_file_list()

    def update_dir_label(self):
        self.dir_label.config(
            text=f"Transcripts Directory: {config.TRANSCRIPTS_BASE}")

    def refresh_file_list(self):
        self.file_listbox.delete(0, tk.END)
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

    def on_file_select(self, event):
        selection = self.file_listbox.curselection()
        if not selection:
            return
        filename = self.file_listbox.get(selection[0]).split(" (")[0]
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
            ("All Key Items", project_dir /
             f"{base}{config.SUFFIX_KEY_ITEMS_ALL}"),
            ("TSIT (ST/IT/T/KT)", project_dir / f"{base}{config.SUFFIX_KEY_ITEMS_CLEAN}"),
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

        # Truncate log if it gets too long (prevent memory issues)
        # Check current line count
        num_lines = int(self.log_text.index('end-1c').split('.')[0])
        if num_lines > 5000:
            # Delete first 500 lines
            self.log_text.delete(1.0, 501.0)
            self.log_text.insert(tk.END, "\n... [Older logs truncated to save memory] ...\n")

        self.log_text.insert(tk.END, text + "\n")
        self.log_text.see(tk.END)
        self.root.update()

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def set_status(self, message, color="black"):
        self.status_label.config(text=message, foreground=color)
        self.root.update()

    def run_task_in_thread(self, task_function, *args, task_name=None, **kwargs):
        self.processing = True
        self.progress.start()
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
        try:
            success = task_function(*args, **kwargs)
            if success:
                self.set_status("Task completed successfully.", "green")
                self.log("✅ %s completed successfully.", name)
            else:
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
        self.log("STEP 0: Initial Transcript Validation...")
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
                return True

            self.log("⚠️ Found %d issues.", len(findings))

            # Instead of applying immediately, show the review dialog on main thread
            self.log("Waiting for user review in popup dialog...")
            self.root.after(0, lambda: self.show_validation_dialog(
                findings, file_to_validate))
            return True

        except Exception as e:
            self.log("❌ Validation failed: %s", e)
            import traceback
            traceback.print_exc()
            return False

    def _prompt_finalize_no_issues(self, source_file):
        if messagebox.askyesno("Validation Complete", "No issues found. Create final validated copy?"):
            self.run_task_in_thread(
                self._apply_validation_corrections, [], source_file, True)

    def show_validation_dialog(self, findings, source_file):
        ValidationReviewDialog(self.root, findings,
                               lambda corrections, finalize: self._handle_validation_apply(corrections, source_file, finalize))

    def _handle_validation_apply(self, corrections, source_file, finalize):
        if not corrections and not finalize:
            self.log("No corrections selected.")
            return

        msg = f"Applying {len(corrections)} corrections..." if corrections else "Finalizing file..."
        self.log(msg)

        self.run_task_in_thread(
            self._apply_validation_corrections, corrections, source_file, finalize)

    def _apply_validation_corrections(self, corrections, source_file, finalize):
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
        self.log("STEP 4: Core extraction (Abstract + ST/IT/Topics/Terms/Lenses)...")
        self.run_task_in_thread(
            pipeline.summarize_transcript,
            f"{self.base_name}{config.SUFFIX_YAML}",
            config.settings.DEFAULT_MODEL, # MODIFIED
            "Family Systems",
            "General public",
            False,  # skip_extracts_summary
            False,  # skip_emphasis
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
            False,  # skip_blog
            logger=self.logger,
            task_name="Blog Post (Top Lens)",
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

        # Determine input file (prefer YAML version)
        input_file = f"{self.base_name}{config.SUFFIX_YAML}"
        if not (config.PROJECTS_DIR / self.base_name / input_file).exists():
            input_file = f"{self.base_name}{config.SUFFIX_FORMATTED}"
            if not (config.PROJECTS_DIR / self.base_name / input_file).exists():
                messagebox.showwarning(
                    "Not Ready", "Please format the transcript first.")
                return

        self.log("STEP: Extracting Scored Emphasis...")
        self.run_task_in_thread(
            pipeline.extract_scored_emphasis, input_file, config.settings.DEFAULT_MODEL, self.logger) # MODIFIED

    def do_generate_structured_abstract(self):
        """Generate a structured abstract from the transcript."""
        if not self.base_name:
            return
        self.log("STEP 5: Generating Structured Abstract...")
        self.run_task_in_thread(
            pipeline.generate_structured_abstract, self.base_name, self.logger, model=config.settings.DEFAULT_MODEL)  # Use Sonnet for abstracts

    def do_validate_abstracts(self):
        """Validate the generated abstract for coverage."""
        if not self.base_name:
            return
        self.log("STEP 6: Validating Abstracts (Coverage Check)...")
        # Using the new validation pipeline
        self.run_task_in_thread(
            pipeline.validate_abstract_coverage, self.base_name, self.logger, model=config.settings.AUX_MODEL) # MODIFIED

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

    def do_all_steps(self):
        """Run the entire processing pipeline sequentially."""
        if not self.selected_file:
            return

        # Enforce validation
        if "_validated" not in self.selected_file.name:
            messagebox.showwarning("Validation Required",
                                   "Please run '0. Init Val' and create a final validated copy (ending in '_validated') before running all steps.")
            return

        if not messagebox.askyesno("Confirm", "This will run the entire pipeline from start to finish. Continue?"):
            return
        self.log("▶ STARTING FULL PIPELINE EXECUTION...")
        self.run_task_in_thread(self._run_all_steps)

    def _run_all_steps(self):
        start_time = datetime.now()
        # Step 0: Cost Estimate (informational)
        self.log("\n--- STEP 0: Estimating Cost ---")
        if not self._run_cost_estimation():
            self.log("⚠️ Cost estimation failed; continuing with pipeline run.")

        # Step 1: Format & Validate
        self.log("\n--- STEP 1: Formatting ---")
        # Use config.settings.FORMATTING_MODEL
        if not pipeline.format_transcript(self.selected_file.name, logger=self.logger, model=config.settings.FORMATTING_MODEL): # MODIFIED
            return False

        # Step 1b: Header Validation
        self.log("\n--- STEP 1b: Header Validation ---")
        # Use config.settings.AUX_MODEL
        if not self._run_header_validation(): # Calls _run_header_validation, which uses AUX_MODEL
            self.log("⚠️ Header validation failed or found issues.")

        # Step 2: Add YAML
        self.log("\n--- STEP 2: Adding YAML ---")
        if not pipeline.add_yaml(self.formatted_file.name, "mp4", self.logger):
            return False

        # Step 3: Core Extraction (ST/IT/Topics/Terms/Lenses/Bowen/Emphasis + internal validation)
        self.log("\n--- STEP 3: Core Extraction ---")
        # Core extraction only; blog runs as separate step from validated Lens #1.
        if not pipeline.summarize_transcript(f"{self.base_name}{config.SUFFIX_YAML}",
                                             config.settings.DEFAULT_MODEL, # MODIFIED
                                             "Family Systems", "General public",
                                             False, False, True, logger=self.logger):
            return False

        # Step 4: Generate Abstract
        self.log("\n--- STEP 4: Generate Structured Abstract ---")
        if not pipeline.generate_structured_abstract(self.base_name, self.logger, model=config.settings.DEFAULT_MODEL):  # Use Sonnet for abstracts
            self.log("⚠️ Abstract generation failed or skipped.")

        # Step 5: Validate Abstracts
        self.log("\n--- STEP 5: Validating Abstracts ---")
        pipeline.validate_abstract_coverage(self.base_name, self.logger, model=config.settings.AUX_MODEL) # MODIFIED

        # Step 6: Reserved (separate validation happens inside extraction + abstract validation above)

        # Step 7: Blog from validated lens #1
        self.log("\n--- STEP 7: Blog (Lens #1) ---")
        if not pipeline.summarize_transcript(f"{self.base_name}{config.SUFFIX_YAML}",
                                             config.settings.DEFAULT_MODEL,
                                             "Family Systems", "General public",
                                             True, True, False, logger=self.logger):
            return False

        # Step 8: Full Webpage & PDF
        self.log("\n--- STEP 8: Full Web & PDF ---")
        if not self._run_web_pdf_generation():
            return False

        # Step 9: Package
        self.log("\n--- STEP 9: Packaging ---")
        pipeline.package_transcript(self.base_name, self.logger)

        # Post-run Token Usage Report
        self.log("\n--- Token Usage Report ---")
        self.log(analyze_token_usage.generate_usage_report(
            since_timestamp=start_time))

        self.log("\n✅ FULL PIPELINE COMPLETE!")
        return True

    def update_button_states(self):
        state = tk.NORMAL if not self.processing and self.selected_file else tk.DISABLED
        self.init_val_btn.config(state=state)
        self.format_btn.config(state=state)
        self.headers_btn.config(state=state)
        self.yaml_btn.config(state=state)
        self.summary_btn.config(state=state)
        self.blog_btn.config(state=state)
        self.gen_abstract_btn.config(state=state)
        self.abstracts_btn.config(state=state)
        self.webpdf_btn.config(state=state)
        self.emphasis_btn.config(state=state)
        self.cost_btn.config(state=state)
        self.cleanup_btn.config(state=state) # ADDED
        # Config check button is always enabled
        self.package_btn.config(state=state)
        self.do_all_btn.config(
            state=tk.NORMAL if self.selected_file else tk.DISABLED)
        
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
