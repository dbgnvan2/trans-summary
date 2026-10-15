#!/usr/bin/env python3
"""HN measurement: which names does the entity check flag on real generated text?

Run it once with the old code (a worktree at the parent commit) and once with the
new code; `--compare` then lists every name only one of them flags. No API calls.

Inputs are the end-to-end run folders (public talks only). Three sets:
  same   each overview/blog/summary/abstract against its own talk's source, as the
         gate checks it (formatted transcript + filename metadata values).
  cross  each artifact against ANOTHER talk's source (+ its own metadata values):
         its headings' words are mostly absent there, so this shows what the check
         does with headings it cannot ground, and whether real names of people in
         the talk (absent from the other talk) are still flagged.
  probe  the headings flagged in runs 9-10 and made-up names, each added as a
         heading (and a prose sentence) to a real overview, against its own source.
  names  real names spoken in the three talks (people, places, organisations),
         each as a heading checked against a source that lacks it: which would
         still be flagged.
  pairs  made-up people: 98 popular US given names of recent decades x the 50
         most common US surnames, each as "## Notes From <given> <surname>",
         against a source that lacks them (review, learning-qa). Reported as counts.

Usage:
  python measure_heading_names.py --runs <dir>/e2e_run1 ... --out new.json
  python measure_heading_names.py --compare old.json new.json

Spec: docs/plan_heading_names_2026-10-14.md#HN.3
"""
import argparse
import json
import re
import sys
from pathlib import Path

SUFFIXES = (" - overview.md", " - blog.md", " - summary-generated.md", " - abstract-generated.md")
# Flagged as names in e2e runs 9 and 10 (logs); all are generated headings or a date.
LOGGED = ["Closing Advice", "Multigenerational Roots", "Patterns Identified",
          "Swapping One Culprit", "Replacing One Culprit", "Final Reflections",
          "Hurtful Remark"]
# Made-up people (none occurs in the three talks). The last two are built from
# English words that are not given names: the known residual of HN.1 in headings.
MADE_UP = ["How Jane Doerfler Changed Family Therapy", "Luciano Malorni and the Tumor",
           "Notes From Sarah Miller", "What Robert Feldstein Found",
           "Insights From Hannah Okafor", "The Work of Tomasz Wierzbicki",
           "José García On Systems", "Lessons From Gilbert Walker", "Grace Hall Speaks"]
# Popular US given names of recent decades and the most common US surnames (public
# facts, written out here; not taken from the lists the check uses).
GIVEN = ("Liam Noah Oliver Elijah James William Benjamin Lucas Henry Theodore Jack Levi "
         "Alexander Jackson Mateo Daniel Michael Mason Sebastian Ethan Logan Owen Samuel "
         "Jacob Asher Aiden John Joseph Wyatt David Leo Luke Julian Hudson Grayson Matthew "
         "Ezra Gabriel Carter Isaac Jayden Luca Anthony Dylan Lincoln Thomas Maverick Elias "
         "Josiah Charles Olivia Emma Charlotte Amelia Sophia Mia Isabella Ava Evelyn Luna "
         "Harper Sofia Camila Eleanor Elizabeth Violet Scarlett Emily Hazel Lily Gianna "
         "Aurora Penelope Aria Nora Chloe Ellie Mila Avery Layla Abigail Ella Isla Eliana "
         "Nova Madison Zoe Ivy Grace Lucy Willow Emilia Riley Naomi Victoria Stella Elena "
         "Hannah").split()
SURNAMES = ("Smith Johnson Williams Brown Jones Garcia Miller Davis Rodriguez Martinez "
            "Hernandez Lopez Gonzalez Wilson Anderson Thomas Taylor Moore Jackson Martin Lee "
            "Perez Thompson White Harris Sanchez Clark Ramirez Lewis Robinson Walker Young "
            "Allen King Wright Scott Torres Nguyen Hill Flores Green Adams Nelson Baker Hall "
            "Rivera Campbell Mitchell Carter Roberts").split()
# Real names from the three public talks (the cross-talk prose flags).
REAL = ["Robert Weinberg", "Dennis Noble", "Conrad Waddington", "Karl Popper", "Nick Sheff",
        "Mina Bissell", "David Sheff", "San Francisco", "Janice Norton", "Vicki Sheff",
        "Carolyn Jacobs", "Paul Davies", "Ben Kerman", "Hampshire College", "Los Angeles",
        "New York", "Alcoholics Anonymous", "Amy Post", "Ford Doolittle", "Marta Bertolaso",
        "Narcotics Anonymous", "Judith Wallerstein", "Aaron Antonovsky", "Mississippi Delta",
        "Berkeley Lab", "Georgetown University", "Kathy Jablonski", "Karen Sheff",
        "Murray Bowen", "Michael Kerr", "Kathleen Kerr"]


def load(code_dir):
    sys.path.insert(0, str(code_dir))
    import abstract_validation  # noqa: E402
    import release_gate  # noqa: E402
    return abstract_validation, release_gate


def _run_number(run):
    m = re.search(r"(\d+)$", run.name)
    return (int(m.group(1)) if m else 0, run.name)


def talks(run_dirs):
    """{talk: {"sources": {run: formatted transcript}, "arts": [(run, suffix, text)]}}.
    Runs are taken in run-number order, so the result does not depend on the order
    they are given in."""
    out = {}
    for run in sorted(run_dirs, key=_run_number):
        for proj in sorted((run / "projects").glob("*")):
            base = proj.name
            fmt = proj / f"{base} - formatted.md"
            if not fmt.exists():
                continue
            entry = out.setdefault(base, {"sources": {}, "arts": []})
            entry["sources"][run.name] = fmt.read_text(encoding="utf-8")
            for suffix in SUFFIXES:
                art = proj / f"{base}{suffix}"
                if art.exists():
                    entry["arts"].append((run.name, suffix.strip(" -"),
                                          art.read_text(encoding="utf-8")))
    return out


def _source(entry, run):
    """The talk's transcript from ``run`` (what the gate used for that run), else
    from the lowest-numbered run that has it."""
    return entry["sources"].get(run) or next(iter(entry["sources"].values()))


def measure(run_dirs, code_dir):
    av, rg = load(code_dir)
    data = talks(run_dirs)
    result = {"same": {}, "cross": {}, "probe": {}, "names": {}, "pairs": {}}
    for given in GIVEN:
        for surname in SURNAMES:
            result["pairs"][f"{given} {surname}"] = av.find_ungrounded_names(
                f"## Notes From {given} {surname}\n\nA line.\n", "An unrelated talk.")
    for name in REAL:
        result["names"][name] = av.find_ungrounded_names(f"## {name}\n\nA line.\n",
                                                         "An unrelated talk.")
    for base, entry in data.items():
        values = rg._filename_metadata_values(base)
        for run, kind, text in entry["arts"]:
            key = f"{run} | {base[:28]} | {kind}"
            own = f"{_source(entry, run)}\n{values}"
            result["same"][key] = av.find_ungrounded_names(text, own)
            for other, oentry in data.items():
                if other == base:
                    continue
                src = f"{_source(oentry, run)}\n{values}"
                result["cross"][f"{key} vs {other[:20]}"] = av.find_ungrounded_names(text, src)
        last_run, _, overview = [a for a in entry["arts"] if a[1] == "overview.md"][-1]
        own = f"{_source(entry, last_run)}\n{values}"
        for heading in LOGGED + MADE_UP:
            as_heading = overview + f"\n\n## {heading}\n\nA closing line.\n"
            result["probe"][f"{base[:28]} | heading | {heading}"] = \
                av.find_ungrounded_names(as_heading, own)
        for sentence in ("On June 25, 2021, the talk began.", "In June, the group met.",
                         "On Friday, June 25, the talk began.", "June Carter spoke next.",
                         "April Smith asked a question."):
            result["probe"][f"{base[:28]} | prose | {sentence}"] = \
                av.find_ungrounded_names(overview + f"\n\n{sentence}\n", own)
    return result


def compare(old_path, new_path):
    old = json.loads(Path(old_path).read_text())
    new = json.loads(Path(new_path).read_text())
    print(f"old: {old.get('command', '?')}")
    print(f"new: {new.get('command', '?')}")
    pairs_old = sum(bool(v) for v in old["pairs"].values())
    pairs_new = sum(bool(v) for v in new["pairs"].values())
    missed = sorted(k for k, v in new["pairs"].items() if not v and old["pairs"][k])
    print(f"== pairs: {len(new['pairs'])} made-up people as headings; flagged "
          f"old={pairs_old} new={pairs_new}; flagged by old, not by new: {len(missed)}")
    by_given = {}
    for k in missed:
        by_given.setdefault(k.split()[0], []).append(k.split()[1])
    for given, surnames in sorted(by_given.items()):
        print(f"     {given}: {' '.join(surnames)}")
    for part in ("same", "cross", "probe", "names"):  # pairs: counts above
        o_total = sum(len(v) for v in old[part].values())
        n_total = sum(len(v) for v in new[part].values())
        print(f"== {part}: {len(old[part])} checks; names flagged old={o_total} new={n_total}")
        dropped, added = {}, {}
        for key in old[part]:
            for name in set(old[part][key]) - set(new[part].get(key, [])):
                dropped.setdefault(name, []).append(key)
            for name in set(new[part].get(key, [])) - set(old[part][key]):
                added.setdefault(name, []).append(key)
        print(f"   no longer flagged ({len(dropped)} distinct):")
        for name in sorted(dropped):
            print(f"     {name!r}  x{len(dropped[name])}")
        print(f"   newly flagged ({len(added)} distinct):")
        for name in sorted(added):
            print(f"     {name!r}  x{len(added[name])}")
        if part in ("probe", "names"):
            print("   probe results (new code):")
            for key, names in new[part].items():
                print(f"     {key}: {names}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", nargs="*", type=Path, default=[])
    ap.add_argument("--code", type=Path, default=Path(__file__).resolve().parents[3],
                    help="repo checkout whose code is measured")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--compare", nargs=2)
    args = ap.parse_args()
    if args.compare:
        compare(*args.compare)
        return
    args.runs = [r for r in args.runs if r.is_dir()]  # a shell glob also matches run logs
    result = measure(args.runs, args.code)
    result["command"] = (f"code={args.code.resolve().name} runs="
                         + ",".join(r.name for r in sorted(args.runs, key=_run_number)))
    args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
