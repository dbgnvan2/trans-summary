"""Test the proposed WRONG rule on hand-labelled flagged claims, against the current
severity step's stored verdicts on the same claims.

Proposed rule (review 2026-10-19, B.0; Dave 2026-10-19: invented quotes, reversed story
points and invented facts are WRONG; close-but-not-verbatim is a warning):
  WRONG if  F  an invented specific (specifics_check.py, no API), or
            Q  a quote of 4+ words not in the source (specifics_check.py, no API), or
            J  2 of 3 votes from the narrow prompt "Wrong Check Prompt (test v1).md"
               say W2/W3/W4; a W2/W3 vote counts only when its evidence is found in the
               source (faithfulness_judge._evidence_in_source).
  Otherwise a warning.

Baseline: the current severity step's verdict for the same claim, read from
../2026-10-19_judge_severity/results.json (no API call).

Usage:
  python build_cases.py [EXTRA_DIR ...]
  python specifics_check.py
  python wrong_check.py --dry-run      # baseline + F/Q only, prints the planned calls
  python wrong_check.py                # also runs J: 3 calls per transcript (API cost)
Writes wrong_check_results.json.
"""
import argparse
import collections
import json
import sys
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
import config  # noqa: E402
import faithfulness_judge as fj  # noqa: E402
import release_gate  # noqa: E402

PROMPT = (HERE / "Wrong Check Prompt (test v1).md").read_text(encoding="utf-8").strip()
VOTES = 3
CAL = REPO / "docs/calibration/2026-10-19_judge_severity"


def baseline_verdicts() -> dict:
    """claim text -> list of stored severity labels ('wrong' / 'not_quite_right')."""
    res = json.loads((CAL / "results.json").read_text())
    out = collections.defaultdict(list)
    for run in res["d"]:
        for c in run.get("claims", []):
            if c.get("severity"):
                out[c["claim"].strip()].append(c["severity"])
    for run in res["c"]["runs"]:
        if not isinstance(run, dict):
            continue
        for v in (run.get("injected") or {}).values():
            out[v["claim"].strip()].append(v["severity"])
        for a in run.get("artifacts", []) or []:
            for c in a.get("claims", []):
                if c.get("severity"):
                    out[c["claim"].strip()].append(c["severity"])
    for c in res["f"]["claims"]:
        for r in c.get("runs", []):
            out[c["claim"].strip()].append(r["severity"])
    return out


def lookup(store: dict, claim: str):
    claim = claim.strip()
    if claim in store:
        return store[claim]
    for k, v in store.items():
        if claim[:60] in k or k[:60] in claim:
            return v
    return None


def judge_votes(claims: list, source: str, client) -> list:
    """VOTES independent calls of the narrow prompt; per claim a list of vote dicts."""
    votes = [[] for _ in claims]
    with mock.patch.object(fj, "severity_instructions", lambda: PROMPT):
        for n in range(VOTES):
            try:
                got = fj.judge_severity(claims, [None] * len(claims), source, client)
            except Exception as e:  # noqa: BLE001 — record and go on; the claim gets fewer votes
                print(f"  vote {n + 1} failed: {type(e).__name__}: {e}")
                continue
            for i, v in enumerate(got):
                found = v.evidence and fj._evidence_in_source(v.evidence, source, claims[i])
                counts = v.severity == fj.WRONG and (v.type == "W4" or bool(found))
                votes[i].append({"severity": v.severity, "type": v.type,
                                 "evidence": v.evidence, "evidence_found": bool(found),
                                 "counts_wrong": counts})
    return votes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cases = json.loads((HERE / "cases.json").read_text())["cases"]
    spec = {r["id"]: r for r in json.loads((HERE / "specifics_results.json").read_text())}
    base = baseline_verdicts()

    groups = collections.defaultdict(list)
    for c in cases:
        groups[c["transcript"]].append(c)
    print(f"{len(cases)} claims, {len(groups)} transcripts, {VOTES} calls each "
          f"= {VOTES * len(groups)} calls on {config.FAITHFULNESS_JUDGE_MODEL}")
    total_words = 0
    for path, cs in groups.items():
        words = len(Path(path).read_text(encoding="utf-8").split())
        total_words += words
        print(f"  {Path(path).name[:60]}: {len(cs)} claims, {words} words")
    # Rough: 1.35 tokens per word for the source, plus about 1,500 for prompt and claims.
    print(f"estimated input tokens: {VOTES * (int(total_words * 1.35) + 1500 * len(groups)):,}")

    client = None
    if not args.dry_run:
        from transcript_utils import get_anthropic_client
        client = get_anthropic_client()

    rows = []
    for path, cs in groups.items():
        transcript = Path(path).read_text(encoding="utf-8")
        base_name = Path(path).stem.removesuffix(" - formatted")
        source = release_gate.with_recording_metadata(base_name, transcript)
        votes = judge_votes([c["claim"] for c in cs], source, client) if client else [[] for _ in cs]
        for c, vs in zip(cs, votes):
            s = spec[c["id"]]
            j = sum(v["counts_wrong"] for v in vs) >= 2 if vs else None
            b = lookup(base, c["claim"])
            rows.append({
                "id": c["id"], "talk": c["talk"], "claim": c["claim"],
                "hand": c["label"], "hand_type": c["type"], "borderline": c["borderline"],
                "F": s["flag_F"], "Q": s["flag_Q"], "missing_specifics": s["missing_specifics"],
                "J": j, "votes": vs,
                "proposed_wrong": bool(s["flag_F"] or s["flag_Q"] or j),
                "baseline": b,
                "baseline_wrong": (None if not b else
                                   collections.Counter(b).most_common(1)[0][0] == fj.WRONG),
            })

    (HERE / "wrong_check_results.json").write_text(json.dumps(rows, indent=1))

    def score(key):
        wrong = [r for r in rows if r["hand"] == "WRONG" and r[key] is not None]
        nqr = [r for r in rows if r["hand"] != "WRONG" and r[key] is not None]
        return (sum(r[key] for r in wrong), len(wrong), sum(r[key] for r in nqr), len(nqr))

    print("\nid       hand  type  F Q J  proposed  baseline")
    for r in sorted(rows, key=lambda r: (r["hand"], r["id"])):
        jv = "-" if r["J"] is None else ("W" if r["J"] else ".")
        print(f'{r["id"]:8} {r["hand"][:5]:5} {r["hand_type"]:4} {"F" if r["F"] else "."} '
              f'{"Q" if r["Q"] else "."} {jv}  {"WRONG" if r["proposed_wrong"] else "warn ":8} '
              f'{"-" if r["baseline_wrong"] is None else ("WRONG" if r["baseline_wrong"] else "warn")}'
              f'{"  (borderline)" if r["borderline"] else ""}')
    for key, name in (("proposed_wrong", "proposed rule"), ("baseline_wrong", "current severity step")):
        w, nw, q, nq = score(key)
        print(f"{name:22}: WRONG caught {w}/{nw}; not-quite-right blocked {q}/{nq}")


if __name__ == "__main__":
    main()
