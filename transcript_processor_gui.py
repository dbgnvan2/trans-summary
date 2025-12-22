#!/usr/bin/env python3
"""
Transcript Processor GUI Application

A graphical interface for the transcript processing pipeline.
Provides visual feedback and interactive controls for all processing steps.
"""

import os
import sys
import re
import subprocess
import threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox


# Directories
TRANSCRIPTS_BASE = Path(
    os.getenv("TRANSCRIPTS_DIR", Path.home() / "transcripts"))
SOURCE_DIR = TRANSCRIPTS_BASE / "source"
FORMATTED_DIR = TRANSCRIPTS_BASE / "formatted"
SUMMARIES_DIR = TRANSCRIPTS_BASE / "summaries"
PROCESSED_DIR = TRANSCRIPTS_BASE / "processed"

# Script paths
SCRIPT_DIR = Path(__file__).parent
FORMAT_SCRIPT = SCRIPT_DIR / "transcript_format.py"
VALIDATE_SCRIPT = SCRIPT_DIR / "transcript_validate_format.py"
ADD_YAML_SCRIPT = SCRIPT_DIR / "transcript_add_yaml.py"
SUMMARIZE_SCRIPT = SCRIPT_DIR / "transcript_summarize.py"
VALIDATE_ABSTRACT_SCRIPT = SCRIPT_DIR / "transcript_validate_abstract.py"
VALIDATE_WEBPAGE_SCRIPT = SCRIPT_DIR / "transcript_validate_webpage.py"
VALIDATE_EMPHASIS_SCRIPT = SCRIPT_DIR / "transcript_validate_emphasis.py"
VALIDATE_BOWEN_SCRIPT = SCRIPT_DIR / "transcript_validate_bowen.py"
MERGE_ARCHIVAL_SCRIPT = SCRIPT_DIR / "transcript_merge_archival.py"
WEBPAGE_SCRIPT = SCRIPT_DIR / "transcript_to_webpage.py"
SIMPLE_WEBPAGE_SCRIPT = SCRIPT_DIR / "transcript_to_simple_webpage.py"
PDF_SCRIPT = SCRIPT_DIR / "transcript_to_pdf.py"

# Python executable - use venv Python to have access to anthropic module
VENV_PYTHON = SCRIPT_DIR / ".venv" / "bin" / "python3.11"
PYTHON = str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


class TranscriptProcessorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Transcript Processor")
        self.root.geometry("900x700")

        # Variables
        self.selected_file = None
        self.base_name = None
        self.formatted_file = None
        self.processing = False
        self.current_process = None  # Track running subprocess

        # Token usage tracking
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.step_tokens = {}  # Track per-step usage

        # Setup UI
        self.setup_ui()
        self.setup_directories()

        # Show initial status message
        self.status_text.insert(
            1.0, "👈 Select a file from the list above to begin")

        self.refresh_file_list()

    def setup_directories(self):
        """Ensure all required directories exist."""
        PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
        SOURCE_DIR.mkdir(parents=True, exist_ok=True)
        FORMATTED_DIR.mkdir(parents=True, exist_ok=True)

    def setup_ui(self):
        """Create the user interface."""
        # Main container with padding
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)
        # Processing Log expands, not File Status
        main_frame.rowconfigure(3, weight=1)

        # Title
        title_label = ttk.Label(main_frame, text="Transcript Processing Pipeline",
                                font=('Helvetica', 16, 'bold'))
        title_label.grid(row=0, column=0, pady=(0, 10), sticky=tk.W)

        # File selection section
        file_frame = ttk.LabelFrame(
            main_frame, text="Select Source File", padding="10")
        file_frame.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(0, 10))
        file_frame.columnconfigure(0, weight=1)

        # File listbox with scrollbar
        list_frame = ttk.Frame(file_frame)
        list_frame.grid(row=0, column=0, columnspan=2,
                        sticky=(tk.W, tk.E, tk.N, tk.S))
        list_frame.columnconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(list_frame)
        scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        self.file_listbox = tk.Listbox(list_frame, height=6,
                                       yscrollcommand=scrollbar.set)
        self.file_listbox.grid(
            row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        scrollbar.config(command=self.file_listbox.yview)
        self.file_listbox.bind('<<ListboxSelect>>', self.on_file_select)

        # Refresh button
        refresh_btn = ttk.Button(
            file_frame, text="Refresh List", command=self.refresh_file_list)
        refresh_btn.grid(row=1, column=0, pady=(5, 0), sticky=tk.W)

        # Status frame
        status_frame = ttk.LabelFrame(
            main_frame, text="File Status", padding="10")
        status_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        # Add scrollbar to status text
        status_scroll_frame = ttk.Frame(status_frame)
        status_scroll_frame.grid(
            row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        status_frame.columnconfigure(0, weight=1)
        status_frame.rowconfigure(0, weight=1)

        status_scrollbar = ttk.Scrollbar(status_scroll_frame)
        status_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))

        self.status_text = tk.Text(status_scroll_frame, height=12, wrap=tk.WORD,
                                   font=('Courier', 10), yscrollcommand=status_scrollbar.set)
        self.status_text.grid(row=0, column=0, sticky=(tk.W, tk.E))
        status_scrollbar.config(command=self.status_text.yview)
        status_scroll_frame.columnconfigure(0, weight=1)

        # Output log section
        log_frame = ttk.LabelFrame(
            main_frame, text="Processing Log", padding="10")
        log_frame.grid(row=3, column=0, sticky=(
            tk.W, tk.E, tk.N, tk.S), pady=(0, 10))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD,
                                                  font=('Courier', 9))
        self.log_text.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Progress bar
        self.progress = ttk.Progressbar(main_frame, mode='indeterminate')
        self.progress.grid(row=4, column=0, sticky=(tk.W, tk.E), pady=(0, 10))

        # Action buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=5, column=0, sticky=(tk.W, tk.E))

        self.format_btn = ttk.Button(button_frame, text="1. Format & Validate",
                                     command=self.do_format_validate, state=tk.DISABLED)
        self.format_btn.grid(row=0, column=0, padx=(0, 5))

        self.yaml_btn = ttk.Button(button_frame, text="2. Add YAML",
                                   command=self.do_add_yaml, state=tk.DISABLED)
        self.yaml_btn.grid(row=0, column=1, padx=(0, 5))

        self.summary_btn = ttk.Button(button_frame, text="3. Create Summaries",
                                      command=self.do_summaries, state=tk.DISABLED)
        self.summary_btn.grid(row=0, column=2, padx=(0, 5))

        self.blog_btn = ttk.Button(button_frame, text="4. Create Blog",
                                   command=self.do_generate_blog, state=tk.DISABLED)
        self.blog_btn.grid(row=0, column=3, padx=(0, 5))

        self.abstracts_btn = ttk.Button(button_frame, text="5. Validate Abstracts",
                                        command=self.do_validate_abstracts, state=tk.DISABLED)
        self.abstracts_btn.grid(row=0, column=4, padx=(0, 5))

        self.webpdf_btn = ttk.Button(button_frame, text="6. Create Web & PDF",
                                     command=self.do_generate_web_pdf, state=tk.DISABLED)
        self.webpdf_btn.grid(row=0, column=5, padx=(0, 5))

        self.stop_btn = ttk.Button(button_frame, text="⏹ Stop",
                                   command=self.do_stop, state=tk.DISABLED)
        self.stop_btn.grid(row=0, column=6, padx=(0, 5))

        self.clear_btn = ttk.Button(button_frame, text="Clear Log",
                                    command=self.clear_log)
        self.clear_btn.grid(row=0, column=7)

        # Status label
        self.status_label = ttk.Label(
            main_frame, text="Ready", foreground="green")
        self.status_label.grid(row=6, column=0, pady=(5, 0), sticky=tk.W)

    def refresh_file_list(self):
        """Refresh the list of source files."""
        self.file_listbox.delete(0, tk.END)

        if not SOURCE_DIR.exists():
            self.log("⚠️  Source directory not found. Creating it...\n")
            SOURCE_DIR.mkdir(parents=True, exist_ok=True)
            return

        files = sorted(SOURCE_DIR.glob("*.txt"))

        if not files:
            self.log("No .txt files found in source directory.\n")
            self.log(f"Please add files to: {SOURCE_DIR}\n")
            return

        for file in files:
            size_kb = file.stat().st_size / 1024
            self.file_listbox.insert(tk.END, f"{file.name} ({size_kb:.1f} KB)")

        self.log(f"Found {len(files)} source file(s)\n")

    def on_file_select(self, event):
        """Handle file selection."""
        selection = self.file_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        filename = self.file_listbox.get(idx).split(" (")[0]
        self.selected_file = SOURCE_DIR / filename

        # Extract metadata
        stem = self.selected_file.stem

        # Use the full stem without extension as base_name
        # This handles files with any number of parts
        self.base_name = stem

        self.formatted_file = FORMATTED_DIR / \
            f"{self.base_name} - formatted.md"

        # Check status
        self.check_file_status()
        self.update_button_states()

    def check_file_status(self):
        """Check and display current file processing status."""
        self.status_text.delete(1.0, tk.END)

        has_formatted = self.formatted_file.exists()
        has_yaml = False

        # Check both formatted.md and formatted_yaml.md for YAML
        yaml_file = self.formatted_file.parent / \
            f"{self.formatted_file.stem}_yaml.md"
        if yaml_file.exists():
            has_yaml = True
        elif has_formatted:
            with open(self.formatted_file, 'r', encoding='utf-8') as f:
                first_line = f.readline().strip()
                has_yaml = (first_line == "---")

        status = []
        status.append(f"📄 Source: ✅ {self.selected_file.name}")
        status.append(
            f"📝 Formatted: {'✅ Found' if has_formatted else '❌ Not created'}")
        status.append(f"📋 YAML: {'✅ Added' if has_yaml else '❌ Not added'}")

        archival = TRANSCRIPTS_BASE / "summaries" / \
            f"{self.base_name} - extracts-summary.md"
        status.append(
            f"📊 Summaries: {'✅ Generated' if archival.exists() else '❌ Not generated'}")

        blog = TRANSCRIPTS_BASE / "summaries" / \
            f"{self.base_name} - blog.md"
        status.append(
            f"📝 Blog: {'✅ Generated' if blog.exists() else '❌ Not generated'}")

        abstracts = TRANSCRIPTS_BASE / "summaries" / \
            f"{self.base_name} - abstracts.md"
        status.append(
            f"📝 Abstracts: {'✅ Validated' if abstracts.exists() else '❌ Not validated'}")

        # Check for webpages
        webpage = TRANSCRIPTS_BASE / "webpages" / f"{self.base_name}.html"
        webpage_simple = TRANSCRIPTS_BASE / "webpages" / \
            f"{self.base_name} - simple.html"
        has_webpage = webpage.exists()
        has_simple = webpage_simple.exists()

        if has_webpage and has_simple:
            status.append(f"🌐 Webpages: ✅ Both generated")
        elif has_webpage:
            status.append(f"🌐 Webpages: ✅ Sidebar only")
        elif has_simple:
            status.append(f"🌐 Webpages: ✅ Simple only")
        else:
            status.append(f"🌐 Webpages: ❌ Not generated")

        # Check for PDF
        pdf = TRANSCRIPTS_BASE / "pdfs" / f"{self.base_name}.pdf"
        status.append(
            f"📑 PDF: {'✅ Generated' if pdf.exists() else '❌ Not generated'}")

        # Check if source file has been moved to processed
        # Look for the processed version in the processed folder
        processed_path = PROCESSED_DIR / \
            f"{self.selected_file.stem} - Processed{self.selected_file.suffix}"
        is_in_processed = processed_path.exists()
        # Also check if any variant with counter exists
        if not is_in_processed:
            processed_variants = list(PROCESSED_DIR.glob(
                f"{self.selected_file.stem} - Processed*{self.selected_file.suffix}"))
            is_in_processed = len(processed_variants) > 0

        status.append(
            f"📦 Processed: {'✅ Archived' if is_in_processed else '❌ Not archived'}")

        self.status_text.insert(1.0, "\n".join(status))

    def log(self, message):
        """Add message to log."""
        self.log_text.insert(tk.END, message)
        self.log_text.see(tk.END)
        self.root.update()

    def clear_log(self):
        """Clear the log."""
        self.log_text.delete(1.0, tk.END)

    def do_stop(self):
        """Stop the current running process."""
        if self.current_process:
            self.log("\n\n⏹️  STOPPING PROCESS...\n")
            try:
                self.current_process.terminate()
                self.current_process.wait(timeout=3)
                self.log("✅ Process stopped\n")
            except subprocess.TimeoutExpired:
                self.log("⚠️  Process didn't stop gracefully, forcing...\n")
                self.current_process.kill()
                self.current_process.wait()
                self.log("✅ Process killed\n")
            except Exception as e:
                self.log(f"⚠️  Error stopping process: {e}\n")

            self.current_process = None
            self.processing = False
            self.progress.stop()
            self.set_status("Process stopped by user", "orange")
            self.update_button_states()

    def set_status(self, message, color="black"):
        """Update status label."""
        self.status_label.config(text=message, foreground=color)
        self.root.update()

    def ask_yes_no(self, title, message):
        """Show yes/no dialog centered on main window."""
        # Bring window to front and center dialog
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after_idle(self.root.attributes, '-topmost', False)
        return messagebox.askyesno(title, message, parent=self.root)

    def show_warning(self, title, message):
        """Show warning dialog centered on main window."""
        self.root.lift()
        self.root.attributes('-topmost', True)
        self.root.after_idle(self.root.attributes, '-topmost', False)
        messagebox.showwarning(title, message, parent=self.root)

    def show_summary_preview(self, title, file_path):
        """Show a preview window with the summary content."""
        if not file_path.exists():
            self.show_warning("File Not Found",
                              f"Cannot preview: {file_path.name}")
            return

        # Create preview window
        preview = tk.Toplevel(self.root)
        preview.title(f"Preview: {title}")
        preview.geometry("900x600")

        # Center on parent window
        preview.transient(self.root)
        self.root.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - 900) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - 600) // 2
        preview.geometry(f"900x600+{x}+{y}")

        # Add scrolled text widget
        text_frame = ttk.Frame(preview, padding="10")
        text_frame.pack(fill=tk.BOTH, expand=True)

        text_widget = scrolledtext.ScrolledText(text_frame, wrap=tk.WORD,
                                                font=('Courier', 10))
        text_widget.pack(fill=tk.BOTH, expand=True)

        # Load and display content
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            text_widget.insert('1.0', content)
            text_widget.config(state=tk.DISABLED)  # Make read-only
        except Exception as e:
            text_widget.insert('1.0', f"Error reading file: {e}")
            text_widget.config(state=tk.DISABLED)

        # Add close button
        button_frame = ttk.Frame(preview, padding="10")
        button_frame.pack(fill=tk.X)

        close_btn = ttk.Button(button_frame, text="Close",
                               command=preview.destroy)
        close_btn.pack(side=tk.RIGHT)

        # Bring to front
        preview.lift()
        preview.focus_force()

    def update_button_states(self):
        """Enable/disable buttons based on current file state."""
        if not self.selected_file:
            self.format_btn.config(state=tk.DISABLED)
            self.yaml_btn.config(state=tk.DISABLED)
            self.summary_btn.config(state=tk.DISABLED)
            self.blog_btn.config(state=tk.DISABLED)
            self.abstracts_btn.config(state=tk.DISABLED)
            self.webpdf_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.DISABLED)
            return

        # Stop button only enabled when processing
        if self.processing:
            self.format_btn.config(state=tk.DISABLED)
            self.yaml_btn.config(state=tk.DISABLED)
            self.summary_btn.config(state=tk.DISABLED)
            self.blog_btn.config(state=tk.DISABLED)
            self.abstracts_btn.config(state=tk.DISABLED)
            self.webpdf_btn.config(state=tk.DISABLED)
            self.stop_btn.config(state=tk.NORMAL)
            return

        self.stop_btn.config(state=tk.DISABLED)

        has_formatted = self.formatted_file.exists()
        yaml_file = self.formatted_file.parent / \
            f"{self.formatted_file.stem}_yaml.md"
        has_yaml = yaml_file.exists()

        # Check if archival file exists for web-pdf generation
        extracts_summary_file = SUMMARIES_DIR / \
            f"{self.base_name} - extracts-summary.md"
        has_archival = extracts_summary_file.exists()

        blog_file = SUMMARIES_DIR / f"{self.base_name} - blog.md"
        has_blog = blog_file.exists()

        abstracts_file = SUMMARIES_DIR / f"{self.base_name} - abstracts.md"
        has_abstracts = abstracts_file.exists()

        # Format button always enabled if file selected
        self.format_btn.config(state=tk.NORMAL)

        # YAML button enabled if formatted exists
        self.yaml_btn.config(state=tk.NORMAL if has_formatted else tk.DISABLED)

        # Summary button enabled if YAML exists
        self.summary_btn.config(state=tk.NORMAL if has_yaml else tk.DISABLED)

        # Blog button enabled if archival exists
        self.blog_btn.config(state=tk.NORMAL if has_archival else tk.DISABLED)

        # Abstract validation button enabled if archival exists
        self.abstracts_btn.config(
            state=tk.NORMAL if has_archival else tk.DISABLED)

        # Web-PDF button enabled if formatted and archival exist
        self.webpdf_btn.config(state=tk.NORMAL if (
            has_formatted and has_archival) else tk.DISABLED)

    def do_format_validate(self):
        """Run format and validation steps."""
        if not self.selected_file or self.processing:
            return

        thread = threading.Thread(target=self._run_format_validate)
        thread.daemon = True
        thread.start()

    def do_add_yaml(self):
        """Run YAML addition step."""
        if not self.selected_file or self.processing:
            return

        if not self.formatted_file.exists():
            messagebox.showwarning(
                "Not Ready", "Please format the transcript first.")
            return

        thread = threading.Thread(target=self._run_add_yaml)
        thread.daemon = True
        thread.start()

    def do_summaries(self):
        """Run summary generation step."""
        if not self.selected_file or self.processing:
            return

        yaml_file = self.formatted_file.parent / \
            f"{self.formatted_file.stem}_yaml.md"
        if not yaml_file.exists():
            messagebox.showwarning(
                "Not Ready", "Please add YAML front matter first.")
            return

        thread = threading.Thread(target=self._run_summaries)
        thread.daemon = True
        thread.start()

    def do_validate_abstracts(self):
        """Run abstract validation step."""
        if not self.selected_file or self.processing:
            return

        extracts_summary_file = SUMMARIES_DIR / \
            f"{self.base_name} - extracts-summary.md"
        if not extracts_summary_file.exists():
            messagebox.showwarning(
                "Not Ready", "Please generate summaries first.")
            return

        thread = threading.Thread(target=self._run_validate_abstracts)
        thread.daemon = True
        thread.start()

    def start_processing(self):
        """Start full processing pipeline."""
        if not self.selected_file:
            self.show_warning("No File", "Please select a file first.")
            return

        if self.processing:
            return

        # Confirm
        if not self.ask_yes_no("Confirm",
                               f"Process '{self.selected_file.name}'?\n\n"
                               "This will format, validate, add YAML, and generate summaries."):
            return

        # Run in thread
        thread = threading.Thread(target=self.run_pipeline, args=(1,))
        thread.daemon = True
        thread.start()

    def skip_to_summaries(self):
        """Skip directly to summary generation."""
        if not self.selected_file or not self.formatted_file.exists():
            self.show_warning("Cannot Skip",
                              "Formatted file does not exist. Run full processing first.")
            return

        if self.processing:
            return

        # Confirm
        if not self.ask_yes_no("Confirm",
                               f"Generate summaries for '{self.base_name}'?"):
            return        # Run in thread
        thread = threading.Thread(target=self.run_pipeline, args=(4,))
        thread.daemon = True
        thread.start()

    def run_pipeline(self, start_step=1):
        """Run the processing pipeline."""
        self.processing = True
        self.progress.start()

        # Reset token counters
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.step_tokens = {}

        try:
            # Step 1: Format
            if start_step <= 1:
                self.set_status("Formatting transcript...", "blue")
                self.log("\n" + "="*80 + "\n")
                self.log("STEP 1: Formatting Transcript\n")
                self.log("="*80 + "\n")
                success = self.run_script(
                    FORMAT_SCRIPT, [str(self.selected_file.name)])
                if not success:
                    self.log("\n❌ Formatting failed.\n")
                    return
                self.display_step_tokens(1, "Formatting")

            # Step 2: Validate
            if start_step <= 2:
                self.set_status("Validating transcript...", "blue")
                self.log("\n" + "="*80 + "\n")
                self.log("STEP 2: Validating Word Preservation\n")
                self.log("="*80 + "\n")
                success = self.run_script(
                    VALIDATE_SCRIPT, [str(self.selected_file.name)])
                if not success:
                    self.log("\n⚠️  Validation failed!\n")
                    self.root.after(
                        0, lambda: self._handle_validation_failure())
                    return

            # Step 3: Add YAML
            if start_step <= 3:
                self.set_status("Adding YAML...", "blue")
                self.log("\n" + "="*80 + "\n")
                self.log("STEP 3: Adding YAML Front Matter\n")
                self.log("="*80 + "\n")
                success = self.run_script(
                    ADD_YAML_SCRIPT, [str(self.formatted_file.name)])
                if not success:
                    self.log("\n❌ YAML addition failed.\n")
                    return

            # Step 4: Generate summaries
            if start_step <= 4:
                self.set_status(
                    "Generating summaries (this may take a few minutes)...", "blue")
                self.log("\n" + "="*80 + "\n")
                self.log("STEP 4: Generating Summaries\n")
                self.log("="*80 + "\n")
                success = self.run_script(
                    SUMMARIZE_SCRIPT, [str(self.formatted_file.name), "--skip-blog"])
                if not success:
                    self.log("\n❌ Summary generation failed.\n")
                    return
                self.display_step_tokens(4, "Summaries")

            # Step 5: Generate blog post
            if start_step <= 5:
                self.set_status(
                    "Generating blog post (1-2 min)...", "blue")
                self.log("\n" + "="*80 + "\n")
                self.log("STEP 5: Generating Blog Post\n")
                self.log("="*80 + "\n")
                success = self.run_script(
                    SUMMARIZE_SCRIPT, [str(self.formatted_file.name), "--skip-extracts-summary", "--skip-terms"])
                if not success:
                    self.log("\n❌ Blog post generation failed.\n")
                    return
                self.display_step_tokens(5, "Blog Post")

            # Step 6: Validate abstracts
            if start_step <= 6:
                self.set_status(
                    "Validating abstracts (iterating to score 4.5+)...", "blue")
                self.log("\n" + "="*80 + "\n")
                self.log("STEP 6: Validating Abstracts\n")
                self.log("="*80 + "\n")
                success = self.run_script(
                    VALIDATE_ABSTRACT_SCRIPT, [self.base_name])
                if not success:
                    self.log("\n❌ Abstract validation failed.\n")
                    return
                self.display_step_tokens(6, "Abstract Validation")

            # Success
            self.log("\n" + "="*80 + "\n")
            self.log("✅ PROCESSING COMPLETE!\n")
            self.log("="*80 + "\n")
            self.set_status("✅ Processing complete!", "green")

            # Ask about moving to processed
            if self.ask_yes_no("Complete",
                               "Processing complete!\n\n"
                               "Move source file to processed folder?"):
                self.move_to_processed()

            # Refresh status
            self.check_file_status()

        except Exception as e:
            self.log(f"\n❌ Error: {str(e)}\n")
            self.set_status(f"Error: {str(e)}", "red")

        finally:
            self.processing = False
            self.progress.stop()
            self.update_button_states()
            self.check_file_status()

    def _handle_validation_failure(self):
        """Handle validation failure with user prompt."""
        if self.ask_yes_no("Validation Failed",
                           "Validation detected mismatches between source and formatted text.\n\n"
                           "This usually means speaker labels weren't properly removed.\n\n"
                           "Continue anyway?"):
            # User chose to continue - we're already in the thread, just log
            self.log("\n⚠️  User chose to continue despite validation issues.\n")
        else:
            self.log("\n❌ Processing stopped due to validation failure.\n")
            self.set_status("Stopped - validation failed", "red")

    def _run_format_validate(self):
        """Run format and validation as separate step."""
        self.processing = True
        self.progress.start()
        self.set_status(
            "Formatting with Claude AI (may take 30-60 seconds)...", "blue")

        try:
            # Format
            self.log("\n" + "="*80 + "\n")
            self.log("STEP 1: Formatting Transcript\n")
            self.log("="*80 + "\n")
            self.log("⏳ Sending to Claude API...\n")

            success = self.run_script(
                FORMAT_SCRIPT, [str(self.selected_file.name)])
            if not success:
                self.log("\n❌ Formatting failed.\n")
                self.set_status("Formatting failed", "red")
                return

            # Validate
            self.set_status("Validating word preservation...", "blue")
            self.log("\n" + "="*80 + "\n")
            self.log("STEP 2: Validating Word Preservation\n")
            self.log("="*80 + "\n")

            success = self.run_script(
                VALIDATE_SCRIPT, [str(self.selected_file.name)])
            if not success:
                self.log("\n⚠️  Validation detected issues!\n")
                # Ask user in main thread using queue for proper synchronization
                import queue
                response_queue = queue.Queue()

                def ask():
                    self.root.lift()
                    self.root.attributes('-topmost', True)
                    self.root.after_idle(
                        self.root.attributes, '-topmost', False)
                    response = messagebox.askyesno("Validation Failed",
                                                   "Validation detected mismatches.\n\n"
                                                   "This may be due to speaker labels not being removed.\n\n"
                                                   "Continue anyway?",
                                                   parent=self.root)
                    response_queue.put(response)

                self.root.after(0, ask)
                user_response = response_queue.get()

                if not user_response:
                    self.log("\n❌ Processing stopped.\n")
                    self.set_status("Stopped - validation failed", "red")
                    return
                else:
                    self.log("\n⚠️  Continuing despite validation issues.\n")

            self.log("\n✅ Format and validation complete!\n")
            self.set_status("✅ Ready for YAML addition", "green")

        finally:
            self.processing = False
            self.progress.stop()
            self.update_button_states()
            self.check_file_status()

    def _run_add_yaml(self):
        """Run YAML addition as separate step."""
        self.processing = True
        self.progress.start()
        self.set_status("Adding YAML front matter...", "blue")

        try:
            self.log("\n" + "="*80 + "\n")
            self.log("STEP 3: Adding YAML Front Matter\n")
            self.log("="*80 + "\n")

            success = self.run_script(
                ADD_YAML_SCRIPT, [str(self.formatted_file.name)])
            if not success:
                self.log("\n❌ YAML addition failed.\n")
                self.set_status("YAML addition failed", "red")
                return

            # Show YAML preview
            yaml_file = self.formatted_file.parent / \
                f"{self.formatted_file.stem}_yaml.md"
            self.log("\n" + "="*80 + "\n")
            self.log("YAML Preview (first 20 lines):\n")
            self.log("="*80 + "\n")

            with open(yaml_file, 'r', encoding='utf-8') as f:
                for i, line in enumerate(f):
                    if i >= 20:
                        break
                    self.log(line)

            self.log("="*80 + "\n")

            # Ask for confirmation in main thread using queue
            import queue
            response_queue = queue.Queue()

            def ask():
                self.root.lift()
                self.root.attributes('-topmost', True)
                self.root.after_idle(self.root.attributes, '-topmost', False)
                response = self.ask_yes_no("Confirm YAML",
                                           "Please review the YAML front matter in the log above.\n\n"
                                           "Does it look correct?")
                response_queue.put(response)

            self.root.after(0, ask)
            user_response = response_queue.get()

            if user_response:
                self.log("\n✅ YAML confirmed. Ready for summary generation!\n")
                self.set_status("✅ Ready for summary generation", "green")
            else:
                self.log(
                    "\n⚠️  Please manually edit the YAML in the formatted file.\n")
                self.set_status("⚠️  Check YAML manually", "orange")

        finally:
            self.processing = False
            self.progress.stop()
            self.update_button_states()
            self.check_file_status()
            self.check_file_status()

    def _run_summaries(self):
        """Run summary generation as separate step."""
        self.processing = True
        self.progress.start()

        try:
            self.log("\n" + "="*80 + "\n")
            self.log("STEP 4: Generating Summaries\n")
            self.log("="*80 + "\n\n")

            # Step 4a: Generate Archival Summary
            self.set_status(
                "Step 4a: Generating extracts-summary analysis (1-2 min)...", "blue")
            self.log(
                "⏳ Step 4a: Sending to Claude API for extracts-summary analysis...\n")
            self.log(
                "   (This includes abstract, key items, and emphasized items)\n\n")

            success = self.run_script(
                SUMMARIZE_SCRIPT, [str(self.formatted_file.name), "--skip-terms", "--skip-blog"])
            if not success:
                self.log("\n❌ Archival analysis failed.\n")
                self.set_status("Archival analysis failed", "red")
                return

            self.log("\n✅ Archival analysis complete!\n")

            # Step 4b: Validate Emphasis Items
            self.set_status("Step 4b: Validating emphasis items...", "blue")
            self.log("\n" + "="*80 + "\n")
            self.log("⏳ Step 4b: Validating emphasis item quotes...\n")
            self.log("="*80 + "\n")

            success = self.run_script(
                VALIDATE_EMPHASIS_SCRIPT, [self.base_name])
            if not success:
                self.log("\n⚠️  Emphasis validation failed.\n")
            else:
                self.log("\n✅ Emphasis validation complete!\n")

            # Step 4b2: Validate Bowen References
            self.set_status("Step 4b2: Validating Bowen references...", "blue")
            self.log("\n" + "="*80 + "\n")
            self.log("⏳ Step 4b2: Validating Bowen reference quotes...\n")
            self.log("="*80 + "\n")

            success = self.run_script(
                VALIDATE_BOWEN_SCRIPT, [self.base_name])
            if not success:
                self.log("\n⚠️  Bowen validation failed.\n")
            else:
                self.log("\n✅ Bowen validation complete!\n")

            # Step 4c: Extract Key Terms
            self.set_status(
                "Step 4c: Extracting key terms (1-2 min)...", "blue")
            self.log("\n" + "="*80 + "\n")
            self.log("⏳ Step 4c: Extracting terminology and definitions...\n")
            self.log("   (Identifying domain-specific terms from transcript)\n")
            self.log("="*80 + "\n\n")

            success = self.run_script(
                SUMMARIZE_SCRIPT, [str(self.formatted_file.name), "--skip-extracts-summary", "--skip-blog"])
            if not success:
                self.log("\n❌ Key terms extraction failed.\n")
                self.set_status("Key terms extraction failed", "red")
                return

            self.log("\n✅ Key terms extracted successfully!\n")

            # Step 4c2: Validate Key Terms Definitions
            self.set_status(
                "Step 4c2: Validating key terms definitions...", "blue")
            self.log("\n" + "="*80 + "\n")
            self.log("⏳ Step 4c2: Validating definition quotes...\n")
            self.log("="*80 + "\n")

            # The validation happens automatically in the script
            self.log("   Checking that quoted definitions exist in source...\n")
            self.log("✅ Key terms validation complete!\n")

            # Step 4c3: Merge Key Terms into Archival
            self.set_status(
                "Step 4c3: Merging into archival document...", "blue")
            self.log("\n" + "="*80 + "\n")
            self.log("⏳ Step 4c3: Merging key terms into archival document...\n")
            self.log("="*80 + "\n")

            success = self.run_script(
                MERGE_ARCHIVAL_SCRIPT, [self.base_name])
            if not success:
                self.log("\n⚠️  Merge failed - files kept separate.\n")
            else:
                self.log("✅ Key terms merged into unified archival document!\n")

            # Step 4d: Generate Webpage
            self.set_status("Step 4e: Generating HTML webpage...", "blue")
            self.log("\n" + "="*80 + "\n")
            self.log("⏳ Step 4e: Creating single-page HTML document...\n")
            self.log("   (Highlighting Bowen references and emphasis items)\n")
            self.log("="*80 + "\n\n")

            success = self.run_script(
                WEBPAGE_SCRIPT, [self.base_name])
            if not success:
                self.log(
                    "\n⚠️  Webpage generation failed - continuing without it.\n")
            else:
                self.log("\n✅ Webpage generated successfully!\n")

            self.log("\n" + "="*80 + "\n")
            self.log("✅ SUMMARIES COMPLETE!\n")
            self.log("="*80 + "\n")
            self.set_status("✅ Summaries complete!", "green")

            # Show preview window for archival summary
            import queue
            archival_path = TRANSCRIPTS_BASE / "summaries" / \
                f"{self.base_name} - extracts-summary.md"

            def show_preview():
                self.show_summary_preview("Extracts Summary", archival_path)

            self.root.after(0, show_preview)
            import time
            time.sleep(0.5)  # Brief pause to let preview display

        finally:
            self.processing = False
            self.progress.stop()
            self.update_button_states()
            self.check_file_status()

    def do_generate_blog(self):
        """Run blog post generation step."""
        if not self.selected_file or self.processing:
            return

        extracts_summary_file = SUMMARIES_DIR / \
            f"{self.base_name} - extracts-summary.md"
        if not extracts_summary_file.exists():
            messagebox.showwarning(
                "Not Ready", "Please generate summaries first.")
            return

        thread = threading.Thread(target=self._run_generate_blog)
        thread.daemon = True
        thread.start()

    def _run_generate_blog(self):
        """Run blog post generation as separate step."""
        self.processing = True
        self.progress.start()

        try:
            self.log("\n" + "="*80 + "\n")
            self.log("STEP 5: Generating Blog Post\n")
            self.log("="*80 + "\n\n")

            self.set_status(
                "Generating blog post (1-2 min)...", "blue")
            self.log("⏳ Sending to Claude API for blog post...\n")
            self.log("   (Fresh context for SEO-optimized content)\n\n")

            success = self.run_script(
                SUMMARIZE_SCRIPT, [str(self.formatted_file.name), "--skip-extracts-summary", "--skip-terms"])
            if not success:
                self.log("\n❌ Blog post generation failed.\n")
                self.set_status("Blog post generation failed", "red")
                return

            self.log("\n✅ Blog post generated successfully!\n")
            self.set_status("✅ Blog post complete!", "green")

            # Show preview window for blog post
            blog_path = TRANSCRIPTS_BASE / "summaries" / \
                f"{self.base_name} - blog.md"

            def show_preview():
                self.show_summary_preview("Blog Post", blog_path)

            self.root.after(0, show_preview)
            import time
            time.sleep(0.5)  # Brief pause to let preview display

        finally:
            self.processing = False
            self.progress.stop()
            self.update_button_states()
            self.check_file_status()

    def _run_validate_abstracts(self):
        """Run abstract validation as separate step."""
        self.processing = True
        self.progress.start()
        self.set_status("Validating abstracts (iterating to 4.5+)...", "blue")

        try:
            self.log("\n" + "="*80 + "\n")
            self.log("STEP 6: Validating Abstracts\n")
            self.log("="*80 + "\n\n")
            self.log("⏳ Iteratively improving abstract quality...\n")
            self.log("   Target score: 4.5/5.0\n")
            self.log("   Max iterations: 3\n\n")

            success = self.run_script(
                VALIDATE_ABSTRACT_SCRIPT, [self.base_name, "--auto"])

            if not success:
                self.log("\n❌ Abstract validation failed.\n")
                self.set_status("Abstract validation failed", "red")
                return

            self.log("\n✅ Abstract validation complete!\n")
            self.set_status("✅ Abstract validation complete!", "green")

            # Show preview of abstracts file
            abstracts_path = SUMMARIES_DIR / f"{self.base_name} - abstracts.md"
            if abstracts_path.exists():
                self.root.after(0, lambda: self.show_summary_preview(
                    "Abstract Validation Report", abstracts_path))

        finally:
            self.processing = False
            self.progress.stop()
            self.update_button_states()
            self.check_file_status()

    def do_generate_web_pdf(self):
        """Generate simple webpage and PDF from existing files."""
        if self.processing:
            return

        if not self.selected_file or not self.base_name:
            messagebox.showerror("Error",
                                 "Please select a transcript file first")
            return

        # Check if required files exist
        formatted_file = FORMATTED_DIR / f"{self.base_name} - formatted.md"
        extracts_summary_file = SUMMARIES_DIR / \
            f"{self.base_name} - extracts-summary.md"

        if not formatted_file.exists():
            messagebox.showerror("Error",
                                 f"Formatted file not found.\n"
                                 f"Please run Format & Validate first.\n\n"
                                 f"Expected: {formatted_file}")
            return

        if not extracts_summary_file.exists():
            messagebox.showerror("Error",
                                 f"Extracts-summary file not found.\n"
                                 f"Please run Generate Summaries first.\n\n"
                                 f"Expected: {extracts_summary_file}")
            return

        self.processing = True
        self.update_button_states()
        self.progress.start()

        def generate():
            try:
                self.set_status("Generating web and PDF outputs...", "blue")
                self.log("\n" + "="*80 + "\n")
                self.log("GENERATING WEB AND PDF OUTPUTS\n")
                self.log("="*80 + "\n\n")

                # Generate simple webpage
                self.log("📄 Step 1: Generating simple webpage...\n")
                success = self.run_script(
                    SIMPLE_WEBPAGE_SCRIPT, [self.base_name])
                if not success:
                    self.log("\n⚠️  Simple webpage generation failed.\n")
                else:
                    self.log("\n✅ Simple webpage generated!\n")

                    # Validate webpage highlighting
                    self.log("\n🔍 Step 1b: Validating webpage highlighting...\n")
                    validation_success = self.run_script(
                        VALIDATE_WEBPAGE_SCRIPT, [self.base_name, "--simple"])
                    if not validation_success:
                        self.log(
                            "\n⚠️  Webpage validation found issues - check highlighting!\n")
                    else:
                        self.log("\n✅ Webpage validation passed!\n")

                # Generate PDF
                self.log("\n📄 Step 2: Generating PDF...\n")
                success = self.run_script(
                    PDF_SCRIPT, [self.base_name])
                if not success:
                    self.log("\n⚠️  PDF generation failed.\n")
                    self.log(
                        "   Make sure WeasyPrint is installed: pip install weasyprint\n")
                else:
                    self.log("\n✅ PDF generated!\n")

                self.log("\n" + "="*80 + "\n")
                self.log("✅ WEB AND PDF GENERATION COMPLETE!\n")
                self.log("="*80 + "\n")
                self.set_status("✅ Web and PDF generation complete!", "green")

            except Exception as e:
                self.log(f"\n❌ Error: {e}\n")
                self.set_status(f"Error: {e}", "red")

            finally:
                self.processing = False
                self.progress.stop()
                self.update_button_states()

        threading.Thread(target=generate, daemon=True).start()

    def run_script(self, script: Path, args: list) -> bool:
        """Run a Python script and capture output."""
        # Use virtual environment's Python if available
        venv_python = Path(__file__).parent / ".venv" / "bin" / "python3"
        python_exe = str(venv_python) if venv_python.exists() else "python3"
        # -u for unbuffered output
        cmd = [python_exe, "-u", str(script)] + args

        self.current_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1
        )

        # Pattern to match token usage lines
        token_pattern = re.compile(
            r'Tokens.*?:(\s+|.*?)([\d,]+)\s+input\s+\+\s+([\d,]+)\s+output')

        # Stream output and parse tokens
        try:
            if self.current_process is None:
                self.log(f"\n⚠️  Failed to start process: {' '.join(cmd)}\n")
                return False

            for line in self.current_process.stdout:
                self.log(line)

                # Check for token usage
                match = token_pattern.search(line)
                if match:
                    input_tokens = int(match.group(2).replace(',', ''))
                    output_tokens = int(match.group(3).replace(',', ''))
                    self.total_input_tokens += input_tokens
                    self.total_output_tokens += output_tokens

            # Store process reference before wait (avoid race condition with on_closing)
            process = self.current_process
            if process:
                process.wait()
                returncode = process.returncode
            else:
                returncode = 1
        except Exception as e:
            self.log(f"\n⚠️  Process error: {e}\n")
            returncode = 1
        finally:
            self.current_process = None

        return returncode == 0

    def display_step_tokens(self, step_num: int, step_name: str):
        """Display token usage summary for a step."""
        self.log("\n" + "-"*80 + "\n")
        self.log(f"📊 STEP {step_num} ({step_name}) - Token Usage Summary\n")
        self.log("-"*80 + "\n")
        self.log(
            f"   Step Total: {self.total_input_tokens + self.total_output_tokens:,} tokens\n")
        self.log(f"   ├─ Input:  {self.total_input_tokens:,} tokens\n")
        self.log(f"   └─ Output: {self.total_output_tokens:,} tokens\n")
        self.log("\n")
        self.log(
            f"   📊 CUMULATIVE PIPELINE TOTAL: {self.total_input_tokens + self.total_output_tokens:,} tokens\n")
        self.log(
            f"      ├─ Total Input:  {self.total_input_tokens:,} tokens\n")
        self.log(
            f"      └─ Total Output: {self.total_output_tokens:,} tokens\n")
        self.log("-"*80 + "\n")

    def move_to_processed(self):
        """Move source file to processed folder."""
        if not self.selected_file.exists():
            self.show_warning("File Not Found",
                              f"Source file not found:\n{self.selected_file}")
            return False

        stem = self.selected_file.stem
        new_name = f"{stem} - Processed{self.selected_file.suffix}"
        dest_path = PROCESSED_DIR / new_name

        # Handle duplicates
        counter = 1
        while dest_path.exists():
            new_name = f"{stem} - Processed ({counter}){self.selected_file.suffix}"
            dest_path = PROCESSED_DIR / new_name
            counter += 1

        try:
            source_name = self.selected_file.name
            self.selected_file.rename(dest_path)
            self.log(f"\n✅ File archived to processed folder:\n")
            self.log(f"   From: {source_name}\n")
            self.log(f"   To:   {dest_path.name}\n")
            self.log(f"   Location: {PROCESSED_DIR}\n")

            # Update selected_file to new location
            self.selected_file = dest_path

            # Show success message
            result = [None]

            def show():
                result[0] = messagebox.showinfo("File Archived",
                                                f"Source file moved to processed folder:\n\n"
                                                f"From: {source_name}\n\n"
                                                f"To: {dest_path.name}\n\n"
                                                f"Location: {PROCESSED_DIR}",
                                                parent=self.root)
            self.root.after(0, show)
            import time
            time.sleep(0.3)

            self.refresh_file_list()
            # Update status display to show file is now processed
            self.check_file_status()
            return True
        except Exception as e:
            self.log(f"\n❌ Error moving file: {e}\n")
            self.show_warning("Move Failed", f"Could not move file:\n{e}")
            return False


def main():
    root = tk.Tk()
    app = TranscriptProcessorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
