#!/usr/bin/env python3
"""
Review differences between a raw transcript and its formatted version.

Usage:
    python transcript_review_format.py "Title - Presenter - Date"
    python transcript_review_format.py "Title - Presenter - Date" --assign kerr_lectures
    python transcript_review_format.py --list-sets
    python transcript_review_format.py --new-set kerr_lectures

For each difference: [a]ccept the formatted wording, [r]eject it (restore the
raw wording), [e]dit it, or [s]kip for now. Accepted or edited changes can be
saved as a fix in the project's pattern set.
"""
import argparse
import sys

import format_review
import formatting_pipeline as fp
import pattern_sets
from transcript_utils import strip_yaml_frontmatter


def _ask(prompt: str, valid: str, default: str = "", input_fn=input) -> str:
    while True:
        answer = input_fn(prompt).strip().lower() or default
        if answer and answer[0] in valid:
            return answer[0]
        print(f"  Please answer one of: {', '.join(valid)}")


def review(stem: str, input_fn=input, output=print) -> int:
    items = format_review.pending_items(stem)
    record = pattern_sets.load_project_record(stem) or {}
    set_name = record.get("name")
    if not items:
        output("No differences need review.")
        return 0
    output(f"{len(items)} difference(s) need a decision. Pattern set: {set_name or '(none)'}\n")
    decisions = []
    for n, item in enumerate(items, 1):
        output(f"[{n}/{len(items)}] Section {item['section']} — {item['kind']}")
        output(f"   raw:       {item['raw_text'] or '(nothing)'}")
        output(f"   formatted: {item['formatted_text'] or '(nothing)'}")
        output(f"   raw context:       …{item['raw_context']}…")
        output(f"   formatted context: …{item['formatted_context']}…")
        choice = _ask("   [a]ccept / [r]eject / [e]dit / [s]kip? ", "ares", input_fn=input_fn)
        if choice == "s":
            continue
        decision = {"key": item["key"],
                    "action": {"a": "accept", "r": "reject", "e": "edit"}[choice]}
        final_text = item["formatted_text"]
        if choice == "e":
            decision["edit_text"] = input_fn("   new wording: ").strip()
            final_text = decision["edit_text"]
        if choice in "ae" and set_name and item["raw_text"] and final_text:
            if pattern_sets.is_single_word(item["raw_text"]):
                output(f"   Note: '{item['raw_text']}' is a single word; a pattern replaces it "
                       "everywhere in future transcripts. Prefer a phrase if it is a real word.")
            if _ask(f"   Save '{item['raw_text']} = {final_text}' in '{set_name}'? [y/N] ",
                    "yn", "n", input_fn=input_fn) == "y":
                decision["save_pattern"] = True
        decisions.append(decision)
        output("")
    if not decisions:
        output("No decisions made.")
        return 1
    result = format_review.apply_decisions(stem, decisions)
    for error in result["errors"]:
        output(f"  ! {error}")
    for pattern in result["patterns_saved"]:
        output(f"  saved pattern: {pattern}")
    remaining = format_review.pending_items(stem)
    raw = format_review.project_raw(stem)
    formatted = strip_yaml_frontmatter(format_review.formatted_path(stem).read_text(encoding="utf-8"))
    outcome = fp.verify_source_fidelity(raw, formatted,
                                        approvals=format_review.load_approvals(stem, raw))
    if result["changed_text"]:
        output("Formatted transcript updated. Re-run format validation and the add-YAML step.")
    output(f"{len(remaining)} difference(s) still need review. "
           f"Validation {'PASSES' if outcome['passed'] else 'does not pass yet'}.")
    for error in outcome["errors"]:
        output(f"  - {error}")
    return 0 if outcome["passed"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("base_name", nargs="?", help="project name (Title - Presenter - Date)")
    parser.add_argument("--assign", metavar="SET", help="assign a pattern set to the project")
    parser.add_argument("--list-sets", action="store_true", help="list pattern sets")
    parser.add_argument("--new-set", metavar="SET", help="create an empty pattern set")
    args = parser.parse_args(argv)
    if args.list_sets:
        for name in pattern_sets.list_sets():
            print(name)
        return 0
    if args.new_set:
        print(pattern_sets.create_set(args.new_set))
        return 0
    if not args.base_name:
        parser.error("base_name is required")
    if args.assign:
        if args.assign not in pattern_sets.list_sets():
            print(f"No pattern set named {args.assign!r}. Create it with --new-set.")
            return 1
        pattern_sets.assign_to_project(args.base_name, args.assign)
        print(f"Assigned '{args.assign}'. It is applied the next time the project is formatted.")
        return 0
    return review(args.base_name)


if __name__ == "__main__":
    sys.exit(main())
