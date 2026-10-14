"""Scored emphasis at effort low / medium vs the high-effort outputs already saved.
Usage: python emphasis_effort.py <run3 projects dir> <ref dir1> [<ref dir2> ...] --reps N
Public talks only."""
import json, re, sys, time, logging
from pathlib import Path
sys.path.insert(0, "/Users/davemini2/ProjectsLocal/Projects/trans-summary")
import config, transcript_utils as tu
from transcript_utils import (call_claude_with_retry, create_system_message_with_cache,
                              get_anthropic_client, parse_scored_emphasis_output)

args = sys.argv[1:]
reps = int(args[args.index("--reps") + 1]); args = args[:args.index("--reps")]
proj_root, ref_roots = Path(args[0]), [Path(a) for a in args[1:]]
levels = ["low", "medium"]
template = (config.PROMPTS_DIR / config.PROMPT_EMPHASIS_SCORING_FILENAME).read_text(encoding="utf-8")
client = get_anthropic_client()
log = logging.getLogger("emph"); logging.basicConfig(level=logging.ERROR)
norm = lambda s: re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", s.lower().replace("’", "'"))).strip()
toks = lambda s: set(norm(s).split())

def overlap(a, b):
    """Share of a's quotes that match some quote in b (token overlap >= 0.6 of the shorter)."""
    if not a: return 0.0
    hit = 0
    for qa in a:
        ta = toks(qa)
        if any(len(ta & tb) / max(1, min(len(ta), len(tb))) >= 0.6 for tb in map(toks, b)):
            hit += 1
    return hit / len(a)

def quotes_from_md(path):
    return [i["quote"] for i in parse_scored_emphasis_output(path.read_text(encoding="utf-8"))]

rows = []
for proj in sorted(p for p in proj_root.iterdir() if p.is_dir()):
    name = proj.name
    yaml = next(proj.glob("* - yaml.md"))
    transcript = yaml.read_text(encoding="utf-8")
    ntrans = norm(transcript)
    refs = [quotes_from_md(f) for r in ref_roots for f in (r / name).glob("* - emphasis-scored.md")]
    base = (f"high-vs-high overlap {sum(overlap(a,b) for a in refs for b in refs if a is not b)/max(1,len(refs)*(len(refs)-1)):.2f}"
            if len(refs) > 1 else "")
    print(f"\n== {name[:40]}  words={len(transcript.split())}  high refs={len(refs)} "
          f"(items {[len(r) for r in refs]}) {base}", flush=True)
    system = create_system_message_with_cache(transcript)
    for level in levels:
        for rep in range(reps):
            t0 = time.monotonic()
            try:
                msg = call_claude_with_retry(client, model="claude-sonnet-5-5",
                    messages=[{"role": "user", "content": template}], system=system,
                    max_tokens=config.MAX_TOKENS_EXTRACTION, temperature=config.TEMP_STRICT,
                    stream=True, min_length=100, timeout=config.TIMEOUT_SUMMARY, logger=log,
                    effort=level, max_retries=1)
                text = tu.response_text(msg); out = msg.usage.output_tokens; status = "ok"
            except Exception as e:
                text, out, status = "", None, type(e).__name__
            items = parse_scored_emphasis_output(text)
            q = [i["quote"] for i in items]
            verb = sum(1 for x in q if norm(x) and norm(x) in ntrans) / max(1, len(q))
            ov = sum(overlap(q, r) for r in refs) / len(refs) if refs else float("nan")
            rov = sum(overlap(r, q) for r in refs) / len(refs) if refs else float("nan")
            scores = [i.get("score", 0) for i in items]
            print(f"  {level:6} #{rep}  {status:22} out_tokens={out}  items={len(items)}  verbatim={verb:.2f}  "
                  f"in_high={ov:.2f}  high_found={rov:.2f}  mean_score={sum(scores)/max(1,len(scores)):.0f}  "
                  f"{time.monotonic()-t0:.0f}s", flush=True)
            (proj_root.parent / f"emph_{level}_{rep}_{name[:20]}.md").write_text(text, encoding="utf-8")
