---
name: "rca"
description: "Audit csdp sweep/fix history to tell real production faults from churn on tests, style, or repeated edits. Run after csdp once 3+ batches have accumulated since the last audit, or on request."
---

# rca: Review Convergence Audit

Purpose: decide, from measured evidence, whether the csdp sweep/fix cycle is still finding and fixing real faults in production code, or is churning (test tweaks, style, repeated edits to the same code). Diagnostic only. Do not modify source, tests, or docs, and do not push.

("rca" here means review convergence audit, not a single-incident root-cause analysis.)

## Ground rules

- Report only what was measured from git history, test/lint/type output, or recorded findings. If something cannot be determined, write "unknown" and name the missing data. Do not estimate, and do not assign severity without a source-stated severity or a reproducer.
- Cite commit SHAs and file paths for every claim. Read diffs; do not rely on commit messages alone.
- The thresholds below are working heuristics, not validated standards. State them in the report.

## How this relates to csdp

csdp phases: Commit, Sweep (learning-qa agent over `@{upstream}..HEAD`, findings ranked by severity, each real finding fixed with a test), Document (README/CHANGELOG/TODO/specs), Push. csdp does not by itself persist the sweep findings; findings it decides not to fix go to TODO.md with a reason. One csdp run = one batch. Within a batch, fix commits that respond to sweep findings are the iterations.

## When to run

- After a csdp run, if 3 or more batches have been pushed since the last rca ledger entry.
- Immediately, if a single csdp run needed more than 2 sweep rounds, or the same area was fixed in two consecutive batches.
- Whenever the user asks.

If fewer than 3 batches or fewer than 3 fix commits exist in scope, report INSUFFICIENT DATA and stop.

## Procedure

1. **Scope.** Read `.rca/ledger.md` (create the directory and file if absent). Scope = commits since the SHA in the last ledger row; if none, the last 30 commits. Identify batches using dated CHANGELOG entries and push boundaries (`git reflog` / remote refs) where available; otherwise group by date and say so.

2. **Collect findings** in this order, noting which source was used:
   - `.rca/findings.md`, if csdp wrote it (columns: date, SHA range, title, severity as reported by learning-qa, category, fixed Y/N, fix SHA, test file).
   - Otherwise reconstruct from: fix commits and their messages, unfixed items recorded in TODO.md with reasons, and CHANGELOG entries. Mark reconstructed severity as "unstated".

3. **Classify changed lines per fix commit** with `git show --numstat`. Buckets: production source, tests (test dirs, `*test*`, `*spec*`, fixtures, snapshots, mocks), docs/comments, config/build. Record lines added/deleted per bucket.

4. **Reproducer check (fail-before / pass-after).** csdp requires each real fix to ship with a test. For each fix commit that touches both production source and tests: in a temporary git worktree at the parent commit, apply only that commit's test-file changes, run just those tests, and record the result; then run the same tests at the fix commit. Interpret:
   - fails at parent, passes at fix: reproducer confirmed, the fix addressed a real behavioral fault.
   - passes at parent: the test does not detect the fault; the commit is not evidence of a production fault.
   - cannot run (missing runner, environment, or dependencies): "unknown". Do not guess.
   Remove the temporary worktree afterwards.

5. **Test-weakening check.** For every commit touching test files, inspect the diff for removed or loosened assertions, added skip/xfail/only markers, widened tolerances, expected values edited to match new output, and mocks that replace real behavior. List each with SHA and file, and state whether production code changed in the same commit.

6. **Oscillation check.** List files modified in 3 or more fix commits within scope. For those, check whether a hunk added in one commit was removed or reverted in a later one. List each case.

7. **Independent measurements.** Detect test, lint, and type-check commands from project config (package.json, pyproject.toml, Makefile, CI files). Run them at HEAD and, if feasible, at the scope baseline in a temporary worktree. Record pass/fail/error counts. For any currently failing test claimed fixed, run it twice at HEAD with no changes to check flakiness. If no commands are detectable, write "not available".

8. **Deferral trend.** Count findings recorded in TODO.md as intentionally unfixed, per batch. Report whether the count is growing; do not interpret beyond that.

9. **Verdict** using these default rules:
   - **STILL FINDING REAL FAULTS**: at least one fix commit in the last 3 batches has a confirmed reproducer (step 4) in production code. Continue.
   - **CONVERGING**: confirmed-reproducer fixes are decreasing across batches and the step 7 measurements are flat or improving.
   - **CHURNING**: zero confirmed-reproducer fixes in the last 3 batches, AND at least one of: 60% or more of fix-commit changed lines are in tests/docs/config; a test-weakening hit with no production change; an oscillation case; the same finding title or file region recurring.
   - **MIXED / INSUFFICIENT DATA**: anything else. State which evidence is missing (for example, reproducers "unknown").

10. **Report.** Concise prose plus one table (batch, fix SHA, src/test/docs/config lines, finding category, severity source, reproducer result). Include test-weakening hits, oscillation cases, step 7 measurements, deferral trend, the verdict with the rule that triggered it, and a recommendation: stop, continue with an exit criterion, or investigate named commits. Suggest an explicit exit criterion for the next sweep loop (for example: no fix with a confirmed reproducer across 2 consecutive batches, plus a cap on sweep rounds per csdp run).

11. **Ledger.** Append one row to `.rca/ledger.md`: date, HEAD SHA, verdict, batches and fix commits audited. Do not commit it unless the user says to.

## Do not

- Do not fix, refactor, or edit anything during the audit, and do not push.
- Do not call something a real fault without a confirmed reproducer or a source-stated severity.
- Do not run destructive git commands; use temporary worktrees for before/after runs and remove them when done.