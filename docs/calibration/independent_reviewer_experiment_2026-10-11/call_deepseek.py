"""Throwaway: send each batch to DeepSeek twice; key via global-api-config."""
import importlib.util, json, sys, time
from pathlib import Path
import requests
S = Path(sys.argv[1]); MODEL = sys.argv[2]; RUNS = int(sys.argv[3])
spec = importlib.util.spec_from_file_location(
    "llm_providers", Path.home() / "ProjectsLocal/global-api-config/llm_providers.py")
lp = importlib.util.module_from_spec(spec); sys.modules["llm_providers"] = lp; spec.loader.exec_module(lp)
prov = lp.get_provider("deepseek")
assert prov.dialect == "openai" and prov.api_key
instr = (S / "instructions.txt").read_text()
batches = json.loads((S / "inputs.json").read_text())
out = []
for run in range(RUNS):
    for b in batches:
        claims = "\n".join(f"{i+1}. {c}" for i, c in enumerate(b["claims"]))
        content = f"{instr}\n\n=== SOURCE TRANSCRIPT ===\n{b['source']}\n\n=== CLAIMS ({len(b['claims'])}) ===\n{claims}\n"
        body = {"model": MODEL, "messages": [{"role": "user", "content": content}],
                "max_tokens": 32000, "temperature": 0}
        for attempt in range(3):
            t = time.time()
            try:
                r = requests.post(prov.base_url + "/chat/completions", json=body, timeout=300,
                                  headers={"Authorization": "Bearer " + prov.api_key})
                if r.status_code in (429, 500, 502, 503, 504):
                    raise RuntimeError(f"HTTP {r.status_code}")
                r.raise_for_status(); j = r.json(); break
            except Exception as e:
                print("retry", b["id"], type(e).__name__, str(e)[:120], flush=True); time.sleep(5 * (attempt + 1))
        else:
            out.append({"run": run, "id": b["id"], "error": "failed"}); continue
        ch = j["choices"][0]
        out.append({"run": run, "id": b["id"], "finish": ch.get("finish_reason"),
                    "text": ch["message"].get("content"), "usage": j.get("usage"),
                    "secs": round(time.time() - t, 1)})
        print(run, b["id"], ch.get("finish_reason"), j.get("usage", {}).get("total_tokens"), round(time.time() - t, 1), flush=True)
(S / f"raw_{MODEL}.json").write_text(json.dumps(out, indent=1))
