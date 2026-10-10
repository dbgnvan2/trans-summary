#!/usr/bin/env python3
"""
Clean up or archive log files and token usage data to start fresh.

Usage:
    python transcript_clean_logs.py --archive
    python transcript_clean_logs.py --delete
"""

import argparse

import transcript_utils
from transcript_utils import delete_logs as utils_delete_logs


def archive_logs():
    """Archive logs to a zip file in logs/archives/ and remove originals."""
    transcript_utils.archive_logs()


def delete_logs():
    """Permanently delete log files (token_usage.csv is kept)."""
    confirm = input("Are you sure you want to PERMANENTLY DELETE these files? [y/N]: ")

    if confirm.lower() == "y":
        utils_delete_logs()
    else:
        print("Operation cancelled.")


def main():
    parser = argparse.ArgumentParser(
        description="Clean up or archive log files and token usage data."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--archive",
        action="store_true",
        help="Archive current logs to a zip file in logs/archives/ and delete originals",
    )
    group.add_argument(
        "--delete",
        action="store_true",
        help="Permanently delete current logs without backup",
    )

    args = parser.parse_args()

    if args.archive:
        archive_logs()
    elif args.delete:
        delete_logs()


if __name__ == "__main__":
    main()
