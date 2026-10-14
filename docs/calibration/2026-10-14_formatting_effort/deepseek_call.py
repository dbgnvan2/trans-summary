"""Send a prepared formatting prompt to DeepSeek (OpenAI dialect) through the shared
key module (~/ProjectsLocal/global-api-config/llm_providers.py). Runs under the system
Python (the project venv has no `requests`). Saves the reply text and usage JSON.

Usage: python3 deepseek_call.py MODEL PROMPT_FILE OUT_PREFIX
Public talks only.
"""
import json
import sys
import time

sys.path.insert(0, "/Users/davemini2/ProjectsLocal/global-api-config")
import llm_providers as lp  # noqa: E402
import requests  # noqa: E402

MAX_TOKENS = 64000  # the request states its own limit; the API rejects a value it cannot take


def main():
    model, prompt_file, prefix = sys.argv[1], sys.argv[2], sys.argv[3]
    p = lp.get_provider("deepseek")
    prompt = open(prompt_file, encoding="utf-8").read()
    body = {"model": model, "max_tokens": MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}]}
    t0 = time.time()
    last = None
    for attempt in range(3):  # timeout + retry + backoff (P5)
        try:
            r = requests.post(f"{p.base_url.rstrip('/')}/chat/completions",
                              headers={"Authorization": f"Bearer {p.api_key}",
                                       "Content-Type": "application/json"},
                              json=body, timeout=(15, 1800))
            if r.status_code in (429, 500, 502, 503, 504):
                last = f"HTTP {r.status_code}: {r.text[:300]}"
                time.sleep(10 * (attempt + 1))
                continue
            if r.status_code != 200:
                last = f"HTTP {r.status_code}: {r.text[:500]}"
                break
            data = r.json()
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
            open(prefix + ".txt", "w", encoding="utf-8").write(text)
            json.dump({"seconds": round(time.time() - t0, 1),
                       "finish_reason": choice.get("finish_reason"),
                       "usage": data.get("usage"), "model": data.get("model")},
                      open(prefix + ".json", "w"), indent=2)
            print(prefix, "ok", choice.get("finish_reason"), data.get("usage"), flush=True)
            return 0
        except (requests.RequestException, ValueError, KeyError) as e:  # incl. a dropped stream
            last = f"{type(e).__name__}: {e}"
            time.sleep(10 * (attempt + 1))
    json.dump({"seconds": round(time.time() - t0, 1), "error": last},
              open(prefix + ".json", "w"), indent=2)
    print(prefix, "FAILED", last, flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())
