#!/usr/bin/env python3
"""
Clean up or archive log files and token usage data to start fresh.

Usage:
    python transcript_clean_logs.py --archive
    python transcript_clean_logs.py --delete
"""

import argparse
import shutil
from datetime import datetime

import config
from transcript_utils import delete_logs as utils_delete_logs


def archive_logs():
    """Archive logs to a zip file in logs/archives/ and remove originals."""
    logs_dir = config.LOGS_DIR
    if not logs_dir.exists():
        print(f"Logs directory not found: {logs_dir}")
        return

    # Identify files to archive
    log_files = list(logs_dir.glob("*.log"))
    csv_file = logs_dir / "token_usage.csv"
    files_to_process = log_files + ([csv_file] if csv_file.exists() else [])

    if not files_to_process:
        print("No log files found to archive.")
        return

    # Create archives directory
    archives_dir = logs_dir / "archives"
    archives_dir.mkdir(exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_base_name = archives_dir / f"logs_{timestamp}"

    print(f"Found {len(files_to_process)} files to archive.")

    # Create a temp dir to build the archive structure
    temp_dir = logs_dir / f"temp_archive_{timestamp}"
    temp_dir.mkdir()

    try:
        # Copy files to temp dir
        for f in files_to_process:
            shutil.copy2(f, temp_dir)

        # Create zip
        shutil.make_archive(str(zip_base_name), "zip", temp_dir)
        print(f"✅ Archive created: {zip_base_name}.zip")

        # Delete originals
        for f in files_to_process:
            f.unlink()
        print("✅ Original log files removed.")

    except Exception as e:
        print(f"❌ Error during archiving: {e}")
    finally:
        # Cleanup temp dir
        if temp_dir.exists():
            shutil.rmtree(temp_dir)


def delete_logs():
    """Permanently delete log files and token usage CSV."""
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
