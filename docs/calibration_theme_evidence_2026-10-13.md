# Theme judge evidence allowlist (TE) — 2026-10-13

Approved by the user on 2026-10-13 ("yes, do the evidence allowlist and calibration").
Follows TM (`docs/calibration_theme_meta_label_2026-10-13.md`), whose review found
the problem.

## Problem

The theme judge received every bold field of a theme block except Description and a
list of meta labels. The last theme in a file runs to the end of the text, so a
document-level paragraph after it ("Summary paragraph", "Rationale and coverage
summary") was sent to the judge as that theme's evidence. The same structure let the
"Nested under structural theme(s)" field through until TM.

## Change

- **What is sent:** `config.THEME_EVIDENCE_LABELS` (`{"key evidence"}`) is what the
  judge receives as evidence.
- **What is skipped:** `config.THEME_JUDGE_META_LABELS` now also lists the
  document-level fields found in real files:
  - "rationale and coverage summary";
  - "summary paragraph";
  - "input note";
  - "presenter";
  - "why these themes were chosen and how well they cover the presentation".
- **Unknown labels:** a field in neither set is still sent and a warning is logged
  (fail closed), so a new evidence field can't be dropped silently.
- **Contract test:** every field the judge reads, in every real theme fixture, must be
  in one of the sets. It scans the parsed theme blocks, so indented list-format fields
  count. Three real affected files are now fixtures (`tests/fixtures/theme_trailing/`),
  so it covers each document-level label. Before TE, it would have caught TM (the
  label was in 7 fixtures) but not TE (no fixture had a trailing field).
- **Reporting:** the release gate reports unclassified fields once per theme file,
  naming the field and the theme, in the run log and in the `theme_grounding`
  verdict. They are still sent to the judge.
- `JUDGE_LOGIC_VERSION` 2026-10-13b; both sets are in the cache key.

Real labels on disk (62 theme files, 253 themes, before the 3 fixture copies TE adds; 65 and
262 with them). Folders scanned: `~/projects`,
`~/transcripts`, the CrucialX9 KCFC and BTA folders, and `tests/fixtures`; script:
`docs/calibration/2026-10-13_theme_evidence/scan_labels.py`.
- Description 250, Key evidence 250;
- Lens fuel value 175, Nested under… 175, Coverage / role 75, processing fields 11;
- the document-level fields above, 1–2 each.

The change alters judge input for one theme in each of 4 files:
- Why Families structural;
- Beautiful Boy structural (two copies);
- "This is a test".

Tests: `tests/test_theme_evidence_te.py`:
- a trailing paragraph is not evidence;
- Key evidence is kept;
- an unknown field is sent and logged;
- every fixture label is classified;
- the two sets don't overlap.

## Measurement (same day, old vs new label sets)

Data: `docs/calibration/2026-10-13_theme_evidence/`. Judge: claude-sonnet-5-5.

| | Old (TM labels) | New (TE) |
|---|---|---|
| Theme gold recall / precision (3 runs) | 1.00/1.00, 1.00/0.93, 1.00/1.00 | 1.00/1.00 ×3 |
| Faithfulness gold recall (unaffected) | 0.92, 0.96, 0.92 | 0.96, 0.96, 1.00 |
| Faithfulness gold precision (unaffected) | 1.00 ×3 | 0.96, 1.00, 1.00 (e13 once, run-to-run variation) |
| Real abstracts / injected fabrication | 3/3, caught ×3 | 3/3, caught ×3 |
| Real theme files, 6 public talks × 3 runs | 15 PASS, 3 FAIL | 15 PASS, 3 FAIL |

- **The old arm's theme miss is run-to-run variation.** It was a dave_g grounded theme
  flagged once, and that theme's input is identical in both arms.
- **The two public talks whose input changed** (Why Families, Beautiful Boy) passed
  every run in both arms.
- **The 3 failures each way are Systems Biology structural theme 2**, the known real
  overreach (TODO).
- **Flips:** 2 per arm. Old: k6 and one theme. New: e13 and k4. No bar failed in any
  run. The recorded exit codes are not the script's own: the old arm's was piped
  through a filter.
- **Cost:** about $3.10.

## Conclusion

Shipped. The judge sees only the theme's evidence. Nothing was lost on gold or on
real checks, and a new field can't be dropped silently.

Not changed: the published page still shows the trailing paragraph inside the last
theme (`theme_display_blocks`). That is a display change, logged in TODO.
