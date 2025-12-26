#!/usr/bin/env python3
"""
CLI wrapper for generating the main webpage for a transcript.

Usage:
    python transcript_to_webpage.py "Title - Presenter - Date"
"""

import argparse
import sys
from pipeline import generate_webpage

def main():
    """
    Main function to handle command-line execution of the webpage generation process.
    """
    parser = argparse.ArgumentParser(
        description="Generate the main webpage for a transcript using the core pipeline."
    )
    parser.add_argument(
        "base_name",
        help="Base name of the transcript (e.g., 'Title - Presenter - Date')"
    )

    args = parser.parse_args()

    print(f"Starting webpage generation for: {args.base_name}")
    
    success = generate_webpage(args.base_name)

    if success:
        print("\nWebpage generation completed successfully.")
        return 0
    else:
        print("\nWebpage generation failed. Check the logs for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())