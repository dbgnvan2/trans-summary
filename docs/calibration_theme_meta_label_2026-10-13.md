# Theme judge meta label "Nested under structural theme(s)" (TM) — 2026-10-13

Approved by the user on 2026-10-13 ("yes, do the theme calibration run").

## Change

`config.THEME_JUDGE_META_LABELS` had "nested under structural themes" but not "nested
under structural theme(s)". The second form is the label the interpretive-themes
prompt names. 21 of the 25 interpretive files found under `~/projects`,
`~/transcripts`, the CrucialX9 KCFC and BTA folders and `tests/fixtures` use it. The theme
judge receives each theme's fields as evidence, except Description and the meta
labels. So for most real files, the list of structural themes a theme was nested
under reached the judge as evidence. The label is now in the set.
`JUDGE_LOGIC_VERSION` is 2026-10-13.

Tests: `tests/test_theme_meta_label_tm.py`:
- the parenthesised label is excluded and Key evidence is kept;
- the older label is still excluded;
- no real fixture sends the field;
- the cache key changes with the label set.

The three tests about the change fail on the old code.

## Measurement (same day, old vs new label set)

Data: `docs/calibration/2026-10-13_theme_meta_label/`. Judge: claude-sonnet-5-5.

| | Old labels | New labels |
|---|---|---|
| Theme gold recall / precision (3 runs) | 1.00 / 1.00 ×3 | 1.00 / 1.00 ×3 |
| Faithfulness gold recall (same runs; unaffected by this change) | 0.92, 0.96, 0.96 | 0.92, 0.96, 0.92 |
| Real abstracts / injected fabrication | 3/3, caught ×3 | 3/3, caught ×3 |
| Real theme files, 6 public talks × 3 runs (fresh cache each check) | 15 PASS, 3 FAIL | 15 PASS, 3 FAIL |

- **Talks checked** (both theme files each): Why Families 2026-09-13, Societal
  Emotional Process, Systems Biology, Where Roots, the Monika Baege interview, and the
  Beautiful Boy review.
- **Left out:** clinical and KCFC case material, and test projects ("public sources
  only").
- **Every verdict was the same with both label sets.**
- **Exit codes:** both gold scripts exited 1 because of one k6 flip per arm (entailed
  in one run, flagged in another), not a failed bar; every bar passed.
- **Run metadata:** both arms record `judge_logic_version` 2026-10-13. The arm is told
  apart by `faithfulness_cache_version`, which hashes the label set.
- **Systems Biology fails in all 6 checks**, on the structural theme "Convergence
  Between Systems Biology and Bowen Family Systems Theory". That file doesn't use the
  label, so this change can't affect it.
  - The theme's evidence is mostly in the talk.
  - Its description adds claims the talk doesn't make ("not as metaphor but as
    genuine structural homology"), and cites a wrong section ("identified patient" is
    in Section 25, not 9).
  - This is a pre-existing finding: that project's structural themes need
    regenerating before it is published (TODO).
- **Cost:** about $3.10.

## Conclusion

Shipped. The judge no longer receives a meta field as evidence, with no change on the
gold set or on 36 real theme checks. The change removes an input the judge should
never have had; it fixes no measured error.
