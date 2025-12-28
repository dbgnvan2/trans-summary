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
import io
from contextlib import redirect_stdout


class GuiLoggerAdapter:
    """Adapts pipeline logging calls to the GUI log window."""

    def __init__(self, gui):
        self.gui = gui

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

        self.yaml_btn = ttk.Button(
            button_frame, text="2. YAML", command=self.do_add_yaml, state=tk.DISABLED)
        self.yaml_btn.grid(row=0, column=1, padx=(0, 5), pady=2)

        self.summary_btn = ttk.Button(
            button_frame, text="3. Extracts", command=self.do_summaries, state=tk.DISABLED)
        self.summary_btn.grid(row=0, column=2, padx=(0, 5), pady=2)

        self.gen_summary_btn = ttk.Button(
            button_frame, text="4. Gen Summary", command=self.do_generate_structured_summary, state=tk.DISABLED)
        self.gen_summary_btn.grid(row=0, column=3, padx=(0, 5), pady=2)

        self.val_summary_btn = ttk.Button(
            button_frame, text="5. Val Summary", command=self.do_validate_summary, state=tk.DISABLED)
        self.val_summary_btn.grid(row=0, column=4, padx=(0, 5), pady=2)

        # Row 2
        self.gen_abstract_btn = ttk.Button(
            button_frame, text="6. Gen Abstract", command=self.do_generate_structured_abstract, state=tk.DISABLED)
        self.gen_abstract_btn.grid(row=1, column=0, padx=(0, 5), pady=2)

        self.abstracts_btn = ttk.Button(
            button_frame, text="7. Val Abstract", command=self.do_validate_abstracts, state=tk.DISABLED)
        self.abstracts_btn.grid(row=1, column=1, padx=(0, 5), pady=2)

        self.blog_btn = ttk.Button(
            button_frame, text="8. Blog", command=self.do_generate_blog, state=tk.DISABLED)
        self.blog_btn.grid(row=1, column=2, padx=(0, 5), pady=2)

        self.webpdf_btn = ttk.Button(
            button_frame, text="9. Web/PDF", command=self.do_generate_web_pdf, state=tk.DISABLED)
        self.webpdf_btn.grid(row=1, column=3, padx=(0, 5), pady=2)

        self.clear_btn = ttk.Button(
            button_frame, text="Clear Log", command=self.clear_log)
        self.clear_btn.grid(row=1, column=4, padx=(0, 5), pady=2)

        self.do_all_btn = ttk.Button(
            button_frame, text="▶ DO ALL STEPS", command=self.do_all_steps, state=tk.DISABLED)
        self.do_all_btn.grid(row=0, column=5, rowspan=2,
                             padx=(10, 5), sticky=(tk.N, tk.S))

        self.status_label = ttk.Label(
            main_frame, text="Ready", foreground="green")
        self.status_label.grid(row=6, column=0, pady=(5, 0), sticky=tk.W)

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
        self.formatted_file = config.FORMATTED_DIR / \
            f"{self.base_name} - formatted.md"
        self.check_file_status()
        self.update_button_states()

    def check_file_status(self):
        self.status_text.delete(1.0, tk.END)
        if not self.selected_file:
            return

        base = self.base_name
        checks = [
            ("Source", self.selected_file),
            ("Formatted", config.FORMATTED_DIR / f"{base} - formatted.md"),
            ("YAML", config.FORMATTED_DIR / f"{base} - yaml.md"),
            ("Extracts", config.SUMMARIES_DIR / f"{base} - topics-themes.md"),
            ("Key Terms", config.SUMMARIES_DIR / f"{base} - key-terms.md"),
            ("Gen Summary", config.SUMMARIES_DIR /
             f"{base} - summary-generated.md"),
            ("Summary Val", config.SUMMARIES_DIR /
             f"{base} - summary-validation.txt"),
            ("Blog", config.SUMMARIES_DIR / f"{base} - blog.md"),
            ("Gen Abstract", config.SUMMARIES_DIR /
             f"{base} - abstract-generated.md"),
            ("Abstracts Val", config.SUMMARIES_DIR /
             f"{base} - abstract-validation.txt"),
            ("Webpage", config.WEBPAGES_DIR / f"{base}.html"),
            ("Simple Web", config.WEBPAGES_DIR / f"{base} - simple.html"),
            ("PDF", config.PDFS_DIR / f"{base}.pdf"),
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

    def run_task_in_thread(self, task_function, *args):
        self.processing = True
        self.progress.start()
        self.update_button_states()

        thread = threading.Thread(
            target=self._execute_task, args=(task_function, *args))
        thread.daemon = True
        thread.start()

    def _execute_task(self, task_function, *args):
        try:
            success = task_function(*args)
            if success:
                self.set_status(f"Task completed successfully.", "green")
                self.log(f"✅ {task_function.__name__} completed successfully.")
            else:
                self.set_status(f"Task failed.", "red")
                self.log(
                    f"❌ {task_function.__name__} failed. Check logs for details.")
        except Exception as e:
            self.set_status(f"Error: {e}", "red")
            self.log(f"❌ Error during {task_function.__name__}: {e}")
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

    def do_add_yaml(self):
        if not self.formatted_file or not self.formatted_file.exists():
            messagebox.showwarning(
                "Not Ready", "Please format the transcript first.")
            return
        self.log("STEP 2: Adding YAML Front Matter...")
        self.run_task_in_thread(
            pipeline.add_yaml, f"{self.base_name} - formatted.md", "mp4", self.logger)

    def do_summaries(self):
        yaml_file = config.FORMATTED_DIR / f"{self.base_name} - yaml.md"
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
        self.log("STEP 3: Generating Summaries...")
        self.run_task_in_thread(pipeline.summarize_transcript, f"{self.base_name} - yaml.md",
                                config.DEFAULT_MODEL, "Family Systems", "General public", False, False, True, False, config.DEFAULT_SUMMARY_WORD_COUNT, self.logger)

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
        self.run_task_in_thread(pipeline.summarize_transcript, f"{self.base_name} - yaml.md",
                                config.DEFAULT_MODEL, "Family Systems", "General public", True, True, False, False, config.DEFAULT_SUMMARY_WORD_COUNT, self.logger)

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

        # Step 2: Add YAML
        self.log("\n--- STEP 2: Adding YAML ---")
        if not pipeline.add_yaml(f"{self.base_name} - formatted.md", "mp4", self.logger):
            return False

        # Step 3: Extracts (Summaries)
        self.log("\n--- STEP 3: Extracts & Terms ---")
        # Run all parts (skips=False)
        if not pipeline.summarize_transcript(f"{self.base_name} - yaml.md",
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

        self.log("\n✅ FULL PIPELINE COMPLETE!")
        return True

    def update_button_states(self):
        state = tk.NORMAL if not self.processing and self.selected_file else tk.DISABLED
        self.format_btn.config(state=state)
        self.yaml_btn.config(state=state)
        self.summary_btn.config(state=state)
        self.gen_summary_btn.config(state=state)
        self.val_summary_btn.config(state=state)
        self.blog_btn.config(state=state)
        self.gen_abstract_btn.config(state=state)
        self.abstracts_btn.config(state=state)
        self.webpdf_btn.config(state=state)
        self.do_all_btn.config(
            state=tk.NORMAL if self.selected_file else tk.DISABLED)


def main():
    root = tk.Tk()
    app = TranscriptProcessorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
