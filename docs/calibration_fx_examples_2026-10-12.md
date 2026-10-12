# Judge prompt "entailed" examples from an unrelated subject (FX) — 2026-10-12

Follow-up to Q6 (`docs/calibration_q6_prompt_2026-10-12.md`), approved by the user on
2026-10-12. Judge: claude-sonnet-5-5 with confirmation (CF).

## Change

The faithfulness judge prompt's examples of "entailed" claims came from measured
material. They were replaced with examples of the same type from unrelated subjects:

| Old example | Where it came from | New example |
|---|---|---|
| "connects this history to Bowen theory by introducing the DOS equation" | roots_bowen abstract; gold rb_e1/rb_e2 | "links the town's flood records to its new zoning rules" |
| "It was a logical approach, and it produced genuine discoveries." | Systems Biology blog (`prose_real`) | "This is the part most readers will remember." |
| "The environment is not incidental." | same blog | "Put simply, the town learned to plan ahead." |
| "They are looking at the parts when the explanation lives in the pattern." | same blog | "The lesson is easy to state and hard to live by." |
| "That kind of reckoning is rare in science." | same subject as gold ef1/ef2; follows the blog's passage on a field admitting error | "Few crews keep such tidy logbooks." |

No rule changed. The framing examples keep their types: emphasis, restatement, a
rhetorical flourish, and a remark about a group. `JUDGE_LOGIC_VERSION` is 2026-10-12d.
Tests: `tests/test_judge_prompt_examples_q6.py`. They check that no example:
- uses the gold set's subject words;
- appears in any fixture (20+ characters);
- shares half its content words with any `prose_real` sentence;
- reuses a measured sentence's opening frame or the "admitting error" meaning.

They also check that the framing paragraph keeps four examples.

### Drafts rejected in review

- **Draft 1** ("careful plan… reliable harvest", "weather is not a side detail", "counting
  the bricks when the answer lies in the design", "candour is rare among shipbuilders")
  rewrote the blog sentences slot for slot. The bricks example kept the parts-versus-whole
  meaning, and the Systems Biology transcript itself uses a bricks metaphor.
  Data: `*_draft1*`.
- **Draft 2** (the final set, except "Few crews admit their mistakes so openly.") kept
  the meaning of the old rarity example, a field openly admitting error. Data: `*_draft2*`.

### Calibration harness fix (found while measuring draft 1)

The real-abstract checks judged the roots_bowen and dave_g fixtures (files named
`formatted.md`) without the recording metadata. The gate always adds it
(`release_gate._source_with_metadata`). Without it, draft 1 failed roots_bowen in all 3
runs on "Mike Kerr presents a webinar…". The fixture never names the presenter (only
"Kathy Kerr"), so that rejection was correct for the input given; the current prompt let
the sentence through. Changes:
- `judge_recalibration.REAL_ABSTRACTS` now carries each talk's real base name, which
  matches its source file on the drive;
- `injected_fabrication` uses it;
- `tests/test_faithfulness_calibration.py` uses the same list.

With metadata, the current prompt gets 3/3 ×3 (`real_abs_old.json`).

### Judge reply parser fix (found while measuring the final prompt)

where_roots came back as ERROR (which blocks publication) in 2 of 3 gold runs, and once
in draft 2. The cause, from the captured replies (`where_roots_malformed_replies.json`):
the judge put unescaped double quotes inside a rationale
(`"rationale":"The "June video" detail is absent…"`), so the reply is not valid JSON. The
current prompt's run also had malformed replies, so this is a reply-format issue, not an
effect of the wording.

`faithfulness_judge._extract_json_array` now falls back to reading each verdict object's
index and label when the reply is not valid JSON (`_read_verdict_objects`). Every claim
must still get a valid label, so it still fails closed. Each use is logged as a warning and
counted (`faithfulness_judge.REPLY_REPAIRS`). Review found that a reply with two arrays (a
draft, then a "correction") would have let the later verdict replace a flag. Any repeated
index is now an ERROR, in the JSON path too, where it was silently last-wins before.
Tests: `tests/test_judge_reply_repair.py` (9). The theme and key-terms judges share this
parser and get the same behaviour. Both captured replies now parse, and 8 more
where_roots judgements were all the correct FAIL (`where_roots_after_parser_fix.json`).

## Measurement (same day, current vs final)

Data: `docs/calibration/2026-10-12_fx_entailed_examples/`. Prompt fingerprints: current
`ff237a94655e`, final `316397ff3180`.
- The current prompt's gold run (`gold_prose_old.json`) used the old harness, so no
  metadata for roots_bowen and dave_g. Its real abstracts were re-checked with metadata
  in `real_abs_old.json`.
- The final prompt's runs use the fixed harness.

| | Current prompt (after Q6) | Final examples |
|---|---|---|
| Gold faithfulness recall (3 runs) | 0.86, 1.00, 0.95 | 1.00, 0.95, 0.95 |
| Gold precision | 1.00, 1.00, 0.95 | 1.00, 1.00, 1.00 |
| Themes | 1.00 / 1.00 ×3 | 1.00 / 1.00 ×3 |
| Real abstracts with metadata | 3/3 ×3 (`real_abs_old`) | 3/3 ×3 (`real_abs_new`); in the gold run 2/3, 2/3, 3/3 — where_roots ERROR = malformed reply, fixed above |
| Injected fabrication (with metadata for the final prompt) | caught | caught ×3 |
| Kerr project, 10 fresh checks | 0 FAIL (Q6 run, same prompt, same day) | 0 FAIL (3 first-pass flags overturned) |
| `--prose-real`: sentences not entailed (1 run, of 602) | 48 | 46 |
| Cost | $3.52 | $1.94 + $0.87 Kerr + ~$0.6 checks |

Notes:
- **Gold misses move by single cases in both prompts.** Recall: k4, k5, k6; precision:
  e13 (draft 2 only). k6 is missed in 2 of these 6 runs (current prompt runs 1 and 3).
  This is noise at this sample size, not a difference between the prompts.
- **Real prose: 14 of 602 sentences changed status** (6 to flagged, 8 to entailed), with
  one run per prompt. Prompt effect and run-to-run variance can't be told apart.
  - Newly flagged include two Where Roots blog framing sentences ("Differentiation work
    is not primarily intellectual.", "It is not a matter of learning the right
    concepts…").
  - Newly entailed include several overview sentences about heliocentrism and named
    researchers.
- **Draft 1 showed the old contamination directly:** the blog's own sentence "It was a
  logical approach, and it produced genuine discoveries.", which was the old example,
  was no longer accepted.

## Conclusion

No loss on the gold set, the real abstracts (with the gate's metadata), the injected
fabrication or the Kerr project. Real prose is flagged at a similar rate (46 vs 48), and
no prompt example comes from measured material any more. Shipped, together with the
parser fix.

The Systems Biology blog was in the prompt until today, so it is not held-out material for
framing from before 2026-10-12.

Still open (accepted): k6 and k5, the writer's own framing about a theory, are labelled
unsupported in gold, but have the same shape as framing the prompt calls entailed. That
is a conflict between the rule and the labels, not contamination.

Reproduce, from the checkout being tested (scripts in the data folder):
- `judge_recalibration.py --model claude-sonnet-5-5 --repeats 3 --prose-real --out …`
- `cf6.py out.json logs_dir 10`
- `real_abstracts_meta.py CHECKOUT out.json 3`
- `capture_bad_json.py CHECKOUT out.json 8`
