#!/usr/bin/env python3
"""
CLI wrapper for generating a PDF from a transcript.

Usage:
    python transcript_to_pdf.py "Title - Presenter - Date"
"""

import argparse
import sys
from pipeline import generate_pdf

def main():
    """
    Main function to handle command-line execution of the PDF generation process.
    """
    parser = argparse.ArgumentParser(
        description="Generate a PDF for a transcript using the core pipeline."
    )
    parser.add_argument(
        "base_name",
        help="Base name of the transcript (e.g., 'Title - Presenter - Date')"
    )

    args = parser.parse_args()

    print(f"Starting PDF generation for: {args.base_name}")
    
    success = generate_pdf(args.base_name)

    if success:
        print("\nPDF generation completed successfully.")
        return 0
    else:
        print("\nPDF generation failed. Check the logs for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
