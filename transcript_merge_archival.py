#!/usr/bin/env python3
"""
Merge key terms into topics-themes document.
Inserts key terms section after Key Themes, before Bowen References.

Usage:
    python transcript_merge_archival.py "Title - Presenter - Date"
    
Example:
    python transcript_merge_archival.py "Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15"
"""

import argparse
import os
from pathlib import Path
import config


def merge_key_terms_into_topics_themes(base_name: str) -> bool:
    """Merge key-terms.md into topics-themes.md document."""

    topics_themes_path = config.SUMMARIES_DIR / \
        f"{base_name} - topics-themes.md"
    key_terms_path = config.SUMMARIES_DIR / f"{base_name} - key-terms.md"

    # Check both files exist
    if not topics_themes_path.exists():
        print(f"❌ Topics-Themes file not found: {topics_themes_path}")
        return False

    if not key_terms_path.exists():
        print(f"❌ Key terms file not found: {key_terms_path}")
        return False

    # Read both files
    with open(topics_themes_path, 'r', encoding='utf-8') as f:
        topics_themes_content = f.read()

    with open(key_terms_path, 'r', encoding='utf-8') as f:
        key_terms_content = f.read()

    # Extract just the key terms section (skip YAML front matter and header)
    # Remove the entire "TERMINOLOGY EXTRACTION OUTPUT" section
    if '# TERMINOLOGY EXTRACTION OUTPUT' in key_terms_content:
        # Find the "# Key Terms" heading and start from there
        parts = key_terms_content.split('# Key Terms', 1)
        if len(parts) == 2:
            key_terms_section = '# Key Terms' + parts[1]
        else:
            key_terms_section = key_terms_content
    elif key_terms_content.startswith('---'):
        # Old format: skip YAML front matter
        parts = key_terms_content.split('---\n', 2)
        if len(parts) >= 3:
            key_terms_section = parts[2]
        else:
            key_terms_section = key_terms_content
    else:
        key_terms_section = key_terms_content

    # Find insertion point in topics-themes (after Key Themes, before Bowen References)
    # Look for the "## **Bowen References**" heading
    insertion_marker = "## **Bowen References**"

    if insertion_marker in topics_themes_content:
        # Insert key terms before Bowen References
        parts = topics_themes_content.split(insertion_marker, 1)
        merged_content = (
            parts[0] +
            "\n---\n\n" +
            key_terms_section.strip() +
            "\n\n---\n\n" +
            insertion_marker +
            parts[1]
        )
    else:
        print("⚠️  Could not find insertion point (## **Bowen References**)")
        print("   Appending key terms to end of topics-themes document")
        merged_content = topics_themes_content + "\n\n---\n\n" + key_terms_section

    # Save merged content back to topics-themes file
    with open(topics_themes_path, 'w', encoding='utf-8') as f:
        f.write(merged_content)

    print(f"✅ Key terms merged into topics-themes document")
    print(f"   File: {topics_themes_path}")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Merge key terms into topics-themes document"
    )
    parser.add_argument(
        "base_name",
        help='Base name without suffix (e.g., "Title - Presenter - Date")'
    )

    args = parser.parse_args()

    try:
        success = merge_key_terms_into_topics_themes(args.base_name)
        return 0 if success else 1

    except (OSError, IOError) as e:
        print(f"❌ Error: {e}")
        return 1


if __name__ == "__main__":
    exit(main())
