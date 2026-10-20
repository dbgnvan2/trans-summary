"""RM0: what share of judge claims appear verbatim in their artifact (no API calls)."""
import collections, json, re, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
import config
import faithfulness_judge as fj

ROOTS = [Path("/Volumes/davemini/Downloads/projects"),
         Path("/Volumes/CrucialX9/1 MY DISK/KCFC ALL/projects"),
         Path("/Users/davemini2/projects")]
SUFFIXES = {"summary": config.SUFFIX_SUMMARY_GEN, "overview": config.SUFFIX_OVERVIEW,
            "abstract": config.SUFFIX_ABSTRACT_GEN}
stats = collections.defaultdict(lambda: collections.Counter())
examples = collections.defaultdict(list)
seen = set()
for root in ROOTS:
    if not root.exists():
        print("missing root", root); continue
    for proj in sorted(p for p in root.iterdir() if p.is_dir()):
        base = proj.name
        src_path = proj / f"{base}{config.SUFFIX_FORMATTED}"
        source = src_path.read_text(encoding="utf-8", errors="replace") if src_path.exists() else None
        for kind, suf in SUFFIXES.items():
            f = proj / f"{base}{suf}"
            if not f.exists():
                continue
            text = f.read_text(encoding="utf-8", errors="replace")
            key = (kind, hash(text))
            if key in seen:
                continue
            seen.add(key)
            claims = fj.extract_claims(text, source)
            st = stats[kind]
            st["files"] += 1
            for c in claims:
                st["claims"] += 1
                c = fj._claim_body(c)
                if c in text:
                    st["verbatim"] += 1
                    if text.count(c) > 1:
                        st["more_than_once"] += 1
                else:
                    st["not_verbatim"] += 1
                    if len(examples[kind]) < 12:
                        examples[kind].append((base[:50], c))
for kind, st in stats.items():
    print(kind, dict(st), f"verbatim {st['verbatim']/max(1,st['claims']):.1%}")
for kind, ex in examples.items():
    print("\n== not verbatim:", kind)
    for b, c in ex:
        print(" ", b, "|", c)
