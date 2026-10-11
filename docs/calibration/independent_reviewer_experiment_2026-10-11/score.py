import json, re, sys
from pathlib import Path
import faithfulness_judge as fj
from validation_pipeline import quote_is_verbatim_for_gate
S = Path(sys.argv[1])
batches = {b["id"]: b for b in json.loads((S / "inputs.json").read_text())}
r8 = json.loads((S / "raw_8k.json").read_text()); r32 = json.loads((S / "raw_32k.json").read_text())
runs = [[x for x in r8 if x["run"] == 0]] + [[x for x in r32 if x["run"] == k] for k in (0, 1)]
norm = lambda t: re.sub(r"[^a-z0-9 ]", " ", (t or "").lower()).split()
def absent(el, src):
    w = norm(el); s = " " + " ".join(norm(src)) + " "
    return bool(w) and (" " + " ".join(w) + " ") not in s
def judge(run):
    out = {}
    for x in run:
        b = batches[x["id"]]; arr = fj._extract_json_array(x["text"]); assert len(arr) == len(b["claims"]), x["id"]
        res = []
        for item in sorted(arr, key=lambda a: a["index"]):
            lab = item["label"]; rule = lab
            if lab == "contradicted":
                q = item.get("source_quote")
                if not (q and quote_is_verbatim_for_gate(q, b["source"])[0]): rule = "dropped"
            elif lab == "unsupported":
                if not absent(item.get("unsupported_element"), b["source"]): rule = "dropped"
            res.append({"raw": lab, "rule": rule, "item": item})
        out[x["id"]] = res
    return out
J = [judge(r) for r in runs]
unf = lambda l: l in ("contradicted", "unsupported")
claude = json.loads(Path("docs/calibration/2026-10-10_sonnet55_default.json").read_text())
crows = [{r["id"]: r for r in run["faithfulness"]["rows"]} for run in claude["runs"]]
print("=== GOLD (public, 23 cases; 14 unfaithful) ===")
for name, key in (("raw", "raw"), ("with quote rule", "rule")):
    for i, j in enumerate(J):
        tp = fp = fn = 0
        for sid in [k for k in j if k.startswith("gold:")]:
            b = batches[sid]
            for t, r in zip(b["truth"], j[sid]):
                p = unf(r[key]); tt = unf(t)
                tp += p and tt; fp += p and not tt; fn += tt and not p
        print(f"DeepSeek run {i+1} {name:16} recall={tp/(tp+fn):.2f} precision={(tp/(tp+fp) if tp+fp else 1):.2f}  (tp={tp} fp={fp} fn={fn})")
ids = [(sid, cid, t, idx) for sid in batches if sid.startswith("gold:") for idx, (cid, t) in enumerate(zip(batches[sid]["case_ids"], batches[sid]["truth"]))]
print("\nPer case (truth | Claude 3 runs | DeepSeek raw 3 runs | DeepSeek with rule 3 runs):")
for sid, cid, t, idx in ids:
    c = ["U" if unf(cr[cid]["pred"]) else "e" for cr in crows]
    dr = ["U" if unf(j[sid][idx]["raw"]) else "e" for j in J]
    du = ["U" if unf(j[sid][idx]["rule"]) else ("d" if j[sid][idx]["rule"] == "dropped" else "e") for j in J]
    flag = ""
    if unf(t) and "e" in c and "U" in du: flag = "  <-- DeepSeek catches a Claude miss"
    if not unf(t) and "U" in du: flag = "  <-- DeepSeek false alarm"
    if unf(t) and "e" in "".join(du) and "e" not in c: flag += "  (DeepSeek misses, Claude catches)"
    print(f"{cid:6} {t[:12]:12} C:{''.join(c)} D:{''.join(dr)} R:{''.join(du)}{flag}  {batches[sid]['claims'][idx][:60]}")
print("\n=== REAL ABSTRACTS (claims flagged) ===")
cl = {a["artifact"]: a for a in claude["runs"][0]["real_abstracts"]}
for rid in ("real:roots_bowen", "real:where_roots"):
    b = batches[rid]; nm = rid.split(":")[1]
    print(f"{nm}: Claude run1 {cl[nm]['status']} flagged={len(cl[nm]['flagged'])}")
    for i, j in enumerate(J):
        fl = [(r["rule"], r["item"].get("unsupported_element") or r["item"].get("source_quote"), b["claims"][k][:70]) for k, r in enumerate(j[rid]) if unf(r["raw"])]
        print(f"  DeepSeek run {i+1}: raw flagged {len(fl)}")
        for rule, anchor, cl_ in fl: print(f"     [{rule}] {cl_}  | anchor: {str(anchor)[:60]}")
tok = sum((x.get("usage") or {}).get("total_tokens", 0) for x in r8 + r32)
print("\ntotal tokens all calls:", tok)
