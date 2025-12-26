#!/usr/bin/env python3
"""
CLI wrapper for generating the simple webpage for a transcript.

Usage:
    python transcript_to_simple_webpage.py "Title - Presenter - Date"
"""

import argparse
import sys
from pipeline import generate_simple_webpage

def main():
    """
    Main function to handle command-line execution of the simple webpage generation process.
    """
    parser = argparse.ArgumentParser(
        description="Generate the simple webpage for a transcript using the core pipeline."
    )
    parser.add_argument(
        "base_name",
        help="Base name of the transcript (e.g., 'Title - Presenter - Date')"
    )

    args = parser.parse_args()

    print(f"Starting simple webpage generation for: {args.base_name}")
    
    success = generate_simple_webpage(args.base_name)

    if success:
        print("\nSimple webpage generation completed successfully.")
        return 0
    else:
        print("\nSimple webpage generation failed. Check the logs for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())