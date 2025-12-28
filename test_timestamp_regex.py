"""
Test script to verify timestamp removal regex on specific transcript artifacts.
"""
import re

sample = """Unknown Speaker  59:06  
and

Unknown Speaker  59:07  
one or another, automatic responses would kick in automatically to preserve the life of that individual

Unknown Speaker  1:00:00  
Motivation.

Unknown Speaker  1:00:02  
Thank you. We all talk about,"""


def test_regex():
    print("--- ORIGINAL TEXT ---")
    print(sample)
    print("\n" + "="*40 + "\n")

    print("--- TEST 1: Current Regex (Buggy) ---")
    # This is the current regex in pipeline.py that causes the issue
    # It only matches d:d, so 1:00:00 becomes :00
    buggy_clean = re.sub(
        r'^\s*(\[[\d:.]+\]\s+[^:]+:|Unknown Speaker|Speaker \d+)\s+\d+:\d+', '', sample, flags=re.MULTILINE)
    print(buggy_clean)

    print("\n" + "="*40 + "\n")

    print("--- TEST 2: Fixed Regex ---")
    # This regex handles optional seconds part (?::\d+)?
    fixed_clean = re.sub(
        r'^\s*(\[[\d:.]+\]\s+[^:]+:|Unknown Speaker|Speaker \d+)\s+\d+:\d+(?::\d+)?', '', sample, flags=re.MULTILINE)
    print(fixed_clean)


if __name__ == "__main__":
    test_regex()
