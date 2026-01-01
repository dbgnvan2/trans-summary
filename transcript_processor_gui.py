#!/usr/bin/env python3
"""
Transcript Processor GUI Application
A graphical interface for the transcript processing pipeline.
"""

import os
import sys
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import pipeline
import config
import transcript_validate_webpage
import transcript_validate_headers
import transcript_cost_estimator
import transcript_config_check
import analyze_token_usage
import io
from contextlib import redirect_stdout
import shutil
from datetime import datetime


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
        self.gui.log(f"❌ {str(msg) % args if args else str(msg)}")


class TranscriptProcessorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Transcript Processor")
        self.root.geometry("900x700")

        self.selected_file = None
        self.base_name = None
        self.formatted_file = None
        self.processing = False

        # Create logger adapter
        self.logger = GuiLoggerAdapter(self)

        self.setup_ui()
        self.update_dir_label()
        self.refresh_file_list()

    def setup_ui(self):
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(3, weight=1)

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
        file_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
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

        # Status and Log
        status_frame = ttk.LabelFrame(
            main_frame, text="File Status", padding="10")
        status_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        status_frame.columnconfigure(0, weight=1)
        self.status_text = tk.Text(
            status_frame, height=10, wrap=tk.WORD, font=('Courier', 10))
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E))

        log_frame = ttk.LabelFrame(
            main_frame, text="Processing Log", padding="10")
        log_frame.grid(row=3, column=0, sticky=(
            tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log_text = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, font=('Courier', 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        # Action Buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, sticky=(tk.W, tk.E))

        # Row 1
        self.format_btn = ttk.Button(
            button_frame, text="1. Format", command=self.do_format_validate, state=tk.DISABLED)
        self.format_btn.grid(row=0, column=0, padx=(0, 5), pady=2)

        self.headers_btn = ttk.Button(
            button_frame, text="2. Val Headers", command=self.do_validate_headers, state=tk.DISABLED)
        self.headers_btn.grid(row=0, column=1, padx=(0, 5), pady=2)

        self.yaml_btn = ttk.Button(
            button_frame, text="3. YAML", command=self.do_add_yaml, state=tk.DISABLED)
        self.yaml_btn.grid(row=0, column=2, padx=(0, 5), pady=2)

        self.summary_btn = ttk.Button(
            button_frame, text="4. Key Items", command=self.do_summaries, state=tk.DISABLED)
        self.summary_btn.grid(row=0, column=3, padx=(0, 5), pady=2)

        self.cost_btn = ttk.Button(
            button_frame, text="Est. Cost", command=self.do_estimate_cost, state=tk.DISABLED)
        self.cost_btn.grid(row=0, column=4, padx=(0, 5), pady=2)

        # Row 2
        self.gen_summary_btn = ttk.Button(
            button_frame, text="5. Gen Summary", command=self.do_generate_structured_summary, state=tk.DISABLED)
        self.gen_summary_btn.grid(row=1, column=0, padx=(0, 5), pady=2)

        self.val_summary_btn = ttk.Button(
            button_frame, text="6. Val Summary", command=self.do_validate_summary, state=tk.DISABLED)
        self.val_summary_btn.grid(row=1, column=1, padx=(0, 5), pady=2)

        self.gen_abstract_btn = ttk.Button(
            button_frame, text="7. Gen Abstract", command=self.do_generate_structured_abstract, state=tk.DISABLED)
        self.gen_abstract_btn.grid(row=1, column=2, padx=(0, 5), pady=2)

        self.abstracts_btn = ttk.Button(
            button_frame, text="8. Val Abstract", command=self.do_validate_abstracts, state=tk.DISABLED)
        self.abstracts_btn.grid(row=1, column=3, padx=(0, 5), pady=2)

        self.config_btn = ttk.Button(
            button_frame, text="Config Check", command=self.do_config_check)
        self.config_btn.grid(row=1, column=4, padx=(0, 5), pady=2)

        # Row 3
        self.blog_btn = ttk.Button(
            button_frame, text="9. Blog", command=self.do_generate_blog, state=tk.DISABLED)
        self.blog_btn.grid(row=2, column=0, padx=(0, 5), pady=2)

        self.webpdf_btn = ttk.Button(
            button_frame, text="10. Web/PDF", command=self.do_generate_web_pdf, state=tk.DISABLED)
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

        self.status_label = ttk.Label(
            main_frame, text="Ready", foreground="green")
        self.status_label.grid(row=7, column=0, pady=(5, 0), sticky=tk.W)

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
            self.log(f"⚠️  Source directory not found: {config.SOURCE_DIR}\n")
            return
        files = sorted(config.SOURCE_DIR.glob("*.txt"))
        if not files:
            self.log(
                f"No .txt files found in source directory: {config.SOURCE_DIR}\n")
            return
        for file in files:
            self.file_listbox.insert(
                tk.END, f"{file.name} ({file.stat().st_size/1024:.1f} KB)")
        self.log(f"Found {len(files)} source file(s)\n")

    def on_file_select(self, event):
        selection = self.file_listbox.curselection()
        if not selection:
            return
        filename = self.file_listbox.get(selection[0]).split(" (")[0]
        self.selected_file = config.SOURCE_DIR / filename
        self.base_name = self.selected_file.stem
        self.formatted_file = config.PROJECTS_DIR / self.base_name / \
            f"{self.base_name}{config.SUFFIX_FORMATTED}"
        self.check_file_status()
        self.update_button_states()

    def check_file_status(self):
        self.status_text.delete(1.0, tk.END)
        if not self.selected_file:
            return

        base = self.base_name
        project_dir = config.PROJECTS_DIR / base
        checks = [
            ("Source", self.selected_file),
            ("Formatted", project_dir /
             f"{base}{config.SUFFIX_FORMATTED}"),
            ("Header Val", project_dir /
             f"{base}{config.SUFFIX_HEADER_VAL_REPORT}"),
            ("YAML", project_dir / f"{base}{config.SUFFIX_YAML}"),
            ("Key Items (Raw)", project_dir /
             f"{base}{config.SUFFIX_KEY_ITEMS_ALL}"),
            ("  - Clean T/T/T", project_dir /
             f"{base}{config.SUFFIX_KEY_ITEMS_CLEAN}"),
            ("  - Bowen", project_dir /
             f"{base}{config.SUFFIX_BOWEN}"),
            ("  - Emphasis", project_dir /
             f"{base}{config.SUFFIX_EMPHASIS}"),
            ("  - Scored Emphasis", project_dir /
             f"{base}{config.SUFFIX_EMPHASIS_SCORED}"),
            ("Gen Summary", project_dir /
             f"{base}{config.SUFFIX_SUMMARY_GEN}"),
            ("Summary Val", project_dir /
             f"{base}{config.SUFFIX_SUMMARY_VAL}"),
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
            f"{'✅' if path.exists() else '❌'} {label}" for label, path in checks]
        self.status_text.insert(1.0, "\n".join(status_lines))

    def log(self, message):
        self.log_text.insert(tk.END, str(message) + "\n")
        self.log_text.see(tk.END)
        self.root.update()

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def set_status(self, message, color="black"):
        self.status_label.config(text=message, foreground=color)
        self.root.update()

    def run_task_in_thread(self, task_function, *args, task_name=None):
        self.processing = True
        self.progress.start()
        self.update_button_states()

        thread = threading.Thread(
            target=self._execute_task, args=(task_function, task_name, *args))
        thread.daemon = True
        thread.start()

    def _execute_task(self, task_function, task_name, *args):
        name = task_name if task_name else task_function.__name__
        try:
            success = task_function(*args)
            if success:
                self.set_status(f"Task completed successfully.", "green")
                self.log(f"✅ {name} completed successfully.")
            else:
                self.set_status(f"Task failed.", "red")
                self.log(
                    f"❌ {name} failed. Check logs for details.")
        except Exception as e:
            self.set_status(f"Error: {e}", "red")
            self.log(f"❌ Error during {name}: {e}")
        finally:
            self.processing = False
            self.progress.stop()
            self.root.after(0, self.update_button_states)
            self.root.after(0, self.check_file_status)

    def do_format_validate(self):
        if not self.selected_file:
            return
        self.log("STEP 1: Formatting and validating transcript...")
        self.run_task_in_thread(self._run_format_and_validate)

    def _run_format_and_validate(self):
        if not pipeline.format_transcript(self.selected_file.name, logger=self.logger):
            return False
        self.log("Format complete. Now validating...")
        if not pipeline.validate_format(self.selected_file.name, logger=self.logger):
            self.log("❌ Validation failed. Please check the logs.")
            return False
        return True

    def do_validate_headers(self):
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
        return validator.run(self.formatted_file)

    def do_add_yaml(self):
        if not self.formatted_file or not self.formatted_file.exists():
            messagebox.showwarning(
                "Not Ready", "Please format the transcript first.")
            return
        self.log("STEP 2: Adding YAML Front Matter...")
        self.run_task_in_thread(
            pipeline.add_yaml, self.formatted_file.name, "mp4", self.logger)

    def do_summaries(self):
        yaml_file = config.FORMATTED_DIR / \
            f"{self.base_name}{config.SUFFIX_YAML}"
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
        self.log("STEP 3: Key Items...")
        self.run_task_in_thread(pipeline.summarize_transcript, f"{self.base_name}{config.SUFFIX_YAML}",
                                config.DEFAULT_MODEL, "Family Systems", "General public", False, False, True, False, config.DEFAULT_SUMMARY_WORD_COUNT, self.logger, task_name="Key Item Generation")

    def do_generate_structured_summary(self):
        if not self.base_name:
            return
        self.log("STEP 4: Generating Structured Summary...")
        self.run_task_in_thread(
            pipeline.generate_structured_summary, self.base_name, config.DEFAULT_SUMMARY_WORD_COUNT, self.logger)

    def do_validate_summary(self):
        if not self.base_name:
            return
        self.log("STEP 5: Validating Summary (Coverage & Proportion)...")
        self.run_task_in_thread(
            pipeline.validate_summary_coverage, self.base_name, self.logger)

    def do_generate_blog(self):
        if not self.base_name:
            return
        self.log("STEP 8: Generating Blog Post...")
        self.run_task_in_thread(pipeline.summarize_transcript, f"{self.base_name}{config.SUFFIX_YAML}",
                                config.DEFAULT_MODEL, "Family Systems", "General public", True, True, False, False, config.DEFAULT_SUMMARY_WORD_COUNT, self.logger, task_name="Blog Post generation")

    def do_estimate_cost(self):
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
            self.log(f"❌ Error estimating cost: {e}")
            return False

    def do_config_check(self):
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
            pipeline.extract_scored_emphasis, input_file, config.DEFAULT_MODEL, self.logger)

    def do_generate_structured_abstract(self):
        if not self.base_name:
            return
        self.log("STEP 6: Generating Structured Abstract...")
        self.run_task_in_thread(
            pipeline.generate_structured_abstract, self.base_name, self.logger)

    def do_validate_abstracts(self):
        if not self.base_name:
            return
        self.log("STEP 7: Validating Abstracts (Coverage Check)...")
        # Using the new validation pipeline
        self.run_task_in_thread(
            pipeline.validate_abstract_coverage, self.base_name, self.logger)

    def do_generate_web_pdf(self):
        if not self.base_name:
            return
        self.log("STEP 9: Creating Web & PDF...")
        self.run_task_in_thread(self._run_web_pdf_generation)

    def _run_web_pdf_generation(self):
        success = True
        self.log("  - Generating simple webpage...")
        if not pipeline.generate_simple_webpage(self.base_name):
            self.log("  - Simple webpage generation failed.")
            success = False
        self.log("  - Generating main webpage...")
        if not pipeline.generate_webpage(self.base_name):
            self.log("  - Main webpage generation failed.")
            success = False
        self.log("  - Generating PDF...")
        if not pipeline.generate_pdf(self.base_name):
            self.log("  - PDF generation failed.")
            success = False

        self.log("  - Validating generated webpages...")
        f = io.StringIO()
        with redirect_stdout(f):
            transcript_validate_webpage.validate_webpage(
                self.base_name, simple_mode=False)

        validation_output = f.getvalue()
        self.log(validation_output)
        print(validation_output)
        return success

    def do_package(self):
        if not self.base_name:
            return
        self.log("STEP 11: Packaging Artifacts...")
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
        zip_base_name = archives_dir / \
            f"logs_{datetime.now():%Y%m%d_%H%M%S}"

        try:
            shutil.make_archive(str(zip_base_name), 'zip',
                                logs_dir, verbose=True, logger=self.logger)
            self.log(f"✅ Archive created: {zip_base_name}.zip")
            for f in files_to_process:
                f.unlink()
            self.log("✅ Original log files removed.")
            return True
        except Exception as e:
            self.log(f"❌ Error during archiving: {e}")
            return False

    def _run_delete_logs(self):
        """Permanently delete log files and token usage CSV."""
        return pipeline.delete_logs(logger=self.logger)

    def do_all_steps(self):
        if not self.selected_file:
            return
        if not messagebox.askyesno("Confirm", "This will run the entire pipeline from start to finish. Continue?"):
            return
        self.log("▶ STARTING FULL PIPELINE EXECUTION...")
        self.run_task_in_thread(self._run_all_steps)

    def _run_all_steps(self):
        # Step 1: Format & Validate
        self.log("\n--- STEP 1: Formatting ---")
        if not self._run_format_and_validate():
            return False

        # Step 1b: Header Validation
        self.log("\n--- STEP 1b: Header Validation ---")
        if not self._run_header_validation():
            self.log("⚠️ Header validation failed or found issues.")

        # Step 2: Add YAML
        self.log("\n--- STEP 2: Adding YAML ---")
        if not pipeline.add_yaml(self.formatted_file.name, "mp4", self.logger):
            return False

        # Step 3: Extracts (Summaries)
        self.log("\n--- STEP 3: Extracts & Terms ---")
        # Run all parts (skips=False)
        if not pipeline.summarize_transcript(f"{self.base_name}{config.SUFFIX_YAML}",
                                             config.DEFAULT_MODEL, "Family Systems", "General public",
                                             False, False, False, logger=self.logger):
            return False

        # Step 4: Generate Summary
        self.log("\n--- STEP 4: Generate Structured Summary ---")
        if not pipeline.generate_structured_summary(self.base_name, config.DEFAULT_SUMMARY_WORD_COUNT, self.logger):
            self.log("⚠️ Summary generation failed or skipped.")

        # Step 5: Validate Summary
        self.log("\n--- STEP 5: Validate Summary ---")
        pipeline.validate_summary_coverage(self.base_name, self.logger)

        # Step 6: Generate Abstract
        self.log("\n--- STEP 6: Generate Structured Abstract ---")
        if not pipeline.generate_structured_abstract(self.base_name, self.logger):
            self.log("⚠️ Abstract generation failed or skipped.")

        # Step 7: Validate Abstracts
        self.log("\n--- STEP 7: Validating Abstracts ---")
        pipeline.validate_abstract_coverage(self.base_name, self.logger)

        # Step 8: Blog (Already done in Step 3 if skips=False, but let's be explicit)
        # Actually Step 3 generated Blog too. We can leave it or regenerate.
        # Let's assume Step 3 covered it.

        # Step 9: Web & PDF
        self.log("\n--- STEP 9: Web & PDF ---")
        if not self._run_web_pdf_generation():
            return False

        # Step 10: Package
        self.log("\n--- STEP 10: Packaging ---")
        pipeline.package_transcript(self.base_name, self.logger)

        # Step 11: Token Usage Report
        self.log("\n--- Token Usage Report ---")
        self.log(analyze_token_usage.generate_usage_report())

        self.log("\n✅ FULL PIPELINE COMPLETE!")
        return True

    def update_button_states(self):
        state = tk.NORMAL if not self.processing and self.selected_file else tk.DISABLED
        self.format_btn.config(state=state)
        self.headers_btn.config(state=state)
        self.yaml_btn.config(state=state)
        self.summary_btn.config(state=state)
        self.gen_summary_btn.config(state=state)
        self.val_summary_btn.config(state=state)
        self.blog_btn.config(state=state)
        self.gen_abstract_btn.config(state=state)
        self.abstracts_btn.config(state=state)
        self.webpdf_btn.config(state=state)
        self.emphasis_btn.config(state=state)
        self.cost_btn.config(state=state)
        # Config check button is always enabled
        self.package_btn.config(state=state)
        self.do_all_btn.config(
            state=tk.NORMAL if self.selected_file else tk.DISABLED)


def main():
    root = tk.Tk()
    app = TranscriptProcessorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
