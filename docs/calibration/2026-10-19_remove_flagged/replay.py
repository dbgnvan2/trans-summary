"""RM0 replay: remove flagged sentences from the WO6 drafts with a scratch prototype and
check the deletion-only invariant (no API calls). Measurement only."""
import json, re, sys
from pathlib import Path
REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))
import faithfulness_judge as fj

def remove(text, sentences):
    out, removed = text, []
    for s in sentences:
        if s not in out:
            continue
        removed.append(s)
        # sentence plus the space after it, or before it at a line end
        out = re.sub(re.escape(s) + r"[ \t]+", "", out)
        out = re.sub(r"[ \t]*" + re.escape(s), "", out)
    # drop bullet lines left with no text
    out = "\n".join(l for l in out.split("\n") if not re.fullmatch(r"\s*(?:[-*+]|\d+[.)])\s*", l))
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out, removed

d = json.load(open(REPO / "docs/calibration/2026-10-19_outside_facts/results.json"))
runs = next(v for v in d.values() if isinstance(v, list))
for r in runs:
    draft = r.get("draft") or ""
    claims = r.get("claims") or []
    flagged = [fj._claim_body(c["claim"]) for c in claims if c.get("label") != "entailed"]
    if not flagged:
        continue
    before = fj.extract_claims(draft)
    cleaned, removed = remove(draft, flagged)
    after = fj.extract_claims(cleaned)
    expect = [c for c in before if fj._claim_body(c) not in removed]
    print(f"{r['talk'][:40]} k={r['k']}: flagged {len(flagged)}, removed {len(removed)}, "
          f"words {len(draft.split())}->{len(cleaned.split())}, invariant {'ok' if after == expect else 'BROKEN'}")
    if after != expect:
        print("  extra:", [c[:80] for c in after if c not in expect][:3])
        print("  missing:", [c[:80] for c in expect if c not in after][:3])
