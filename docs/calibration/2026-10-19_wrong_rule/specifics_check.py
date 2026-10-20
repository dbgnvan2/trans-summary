"""Deterministic test of two WRONG detectors on hand-labelled flagged claims. No API calls.

Q  invented quote: a quoted passage of 4+ words whose words are not in the transcript
   (the release gate's own matcher, validation_pipeline.quote_is_verbatim_for_gate).
F  invented specific: a number, number word, year, month, weekday, or capitalised word
   (not sentence-initial) in the claim that appears nowhere in the transcript or the
   talk's file name.

Usage: python specifics_check.py   (reads cases.json, writes specifics_results.json)
"""
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
sys.path.insert(0, str(REPO))
import validation_pipeline as vp  # noqa: E402

cases = json.loads((HERE / "cases.json").read_text())["cases"]

NUM_WORDS = set("""one two three four five six seven eight nine ten eleven twelve thirteen
fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty fifty sixty seventy
eighty ninety hundred thousand million twenties thirties forties fifties sixties seventies
eighties nineties first second third fourth fifth sixth seventh eighth ninth tenth once twice
half dozen""".split())
TIME_WORDS = set("""january february march april may june july august september october
november december monday tuesday wednesday thursday friday saturday sunday""".split())
# Capitalised words that carry no new fact (pronoun, titles, sentence glue after a colon/dash).
CAP_SKIP = {"I", "He", "She", "They", "His", "Her", "Their", "The", "A", "An", "This", "That",
            "It", "In", "On", "At", "As", "But", "And", "Or", "If", "When", "What", "Dr", "Mr",
            "Mrs", "Ms", "Kerr's", "Q&A"}
SUFFIXES = ("'s", "’s", "ian", "ean", "an", "ese", "ish", "s")
QUOTE_RE = re.compile(r'["“]([^"”]+)["”]')


def norm(text):
    return re.sub(r"[^a-z0-9 ]+", " ", text.lower().replace("’", "'"))


NUM_VALUE = {w: str(i) for i, w in enumerate("""zero one two three four five six seven eight
nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen
twenty""".split())}
NUM_VALUE.update({"thirty": "30", "forty": "40", "fifty": "50", "sixty": "60", "seventy": "70",
                  "eighty": "80", "ninety": "90", "hundred": "100", "thousand": "1000"})
VALUE_NUM = {v: k for k, v in NUM_VALUE.items()}


def present(word, hay):
    w = word.lower().strip("'’.,;:")
    # A number written as a word in one text and as digits in the other is the same fact.
    alt = NUM_VALUE.get(w) or VALUE_NUM.get(w.replace(",", ""))
    if alt and re.search(rf"\b{re.escape(alt)}\b", hay):
        return True
    if re.search(rf"\b{re.escape(w)}\b", hay):
        return True
    for suf in SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 4:
            stem = w[: -len(suf)]
            if re.search(rf"\b{re.escape(stem)}", hay):
                return True
    return False


def specifics(claim):
    out = []
    body = QUOTE_RE.sub(" ", claim)  # quoted words are the quote check's job
    sentences = re.split(r"(?<=[.!?:;—–-])\s+", body)
    for s in sentences:
        # Hyphenated compounds ("Aristarchus-to-Copernicus") are checked part by part.
        toks = re.findall(r"[A-Za-z][A-Za-z'’&]*|\d[\d,.]*", s)
        for i, t in enumerate(toks):
            low = t.lower()
            if t[0].isdigit():
                out.append(t.rstrip(".,"))
            elif low in NUM_WORDS or low in TIME_WORDS:
                out.append(t)
            elif i > 0 and t[0].isupper() and t not in CAP_SKIP:
                out.append(t)
    return out


results = []
for c in cases:
    transcript = Path(c["transcript"]).read_text(encoding="utf-8")
    hay = norm(transcript + " " + Path(c["transcript"]).name)
    missing = [w for w in specifics(c["claim"]) if not present(w, hay)]
    bad_quotes = []
    for q in QUOTE_RE.findall(c["claim"]):
        if len(q.split()) >= 4:
            ok, ends, cov = vp.quote_is_verbatim_for_gate(q, transcript)
            if not ok:
                bad_quotes.append({"quote": q, "ends": round(ends, 2), "coverage": round(cov, 2)})
    results.append({**{k: c[k] for k in ("id", "label", "type", "borderline", "talk", "claim")},
                    "missing_specifics": missing, "bad_quotes": bad_quotes,
                    "flag_F": bool(missing), "flag_Q": bool(bad_quotes)})

(HERE / "specifics_results.json").write_text(json.dumps(results, indent=1))
for r in sorted(results, key=lambda r: (r["label"], r["id"])):
    mark = ("F" if r["flag_F"] else "-") + ("Q" if r["flag_Q"] else "-")
    print(f'{r["label"][:5]:5} {r["type"]:3} {r["id"]:7} {mark}  miss={r["missing_specifics"]} '
          f'q={[b["quote"][:30] for b in r["bad_quotes"]]}  | {r["claim"][:70]}')
for lab in ("WRONG", "NOT QUITE RIGHT"):
    rs = [r for r in results if r["label"] == lab]
    print(lab, "flagged by F or Q:", sum(r["flag_F"] or r["flag_Q"] for r in rs), "of", len(rs))
