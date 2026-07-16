---
name: trans-summary-output-critic
description: Critically review trans-summary artifact folders against the prompt files that generated them. Use when a transcript run completes and the user wants confirm/deny findings, evidence snippets, and human-level judgment questions beyond built-in validators.
---

# Trans Summary Output Critic

## Goal
Deliver token-efficient, prompt-aware quality review for one transcript output folder.

## Workflow
1. Locate run outputs
- Use transcript `base_name` folder in `projects/`, or pass `--project-dir`.

2. Run deterministic review
```bash
python3 scripts/review_outputs.py --repo-root /Users/davemini2/ProjectsLocal/projects/trans-summary --project-dir "<output-folder>" --output /tmp/trans-summary-review.md
```

3. Optional semantic grounding (themes/lenses)
- Uses cached transcript context and a compact API check.
```bash
python3 scripts/review_outputs.py --repo-root /Users/davemini2/ProjectsLocal/projects/trans-summary --project-dir "<output-folder>" --semantic-check --output /tmp/trans-summary-review.md
```

4. Semantic grounding for all generated artifacts
- Uses claim-level checks (grounded/questionable/contradicted) against cached transcript context.
- Enforces fail thresholds: any contradicted claim or grounded < 70%.
```bash
python3 scripts/review_outputs.py --repo-root /Users/davemini2/ProjectsLocal/projects/trans-summary --project-dir "<output-folder>" --semantic-all --output /tmp/trans-summary-review.md
```

## Current assumptions aligned to codebase
- `summary-generated.md` is optional (structured summary path only).
- Voice-audit prompt is evaluated against blog quality; JSON output file is optional unless explicitly saved.
- Emphasis output primarily uses ` - emphasis-scored.md` (fallback ` - emphasis-items.md`).
- Structural and interpretive themes are not required to sum to 100%.
- Problematic header terms prompt is excluded from default review scope.

## Output contract
- Per-prompt status: `CONFIRM`, `UNCLEAR`, `DENY`.
- Evidence snippets and prompt-constraint samples.
- Confirm/deny questions for human-level judgment.
- Optional semantic grounding counts for themes and lenses.

## Guardrails
- Do not claim correctness from format-only checks.
- Treat required missing artifacts as `DENY`.
- Keep evidence compact and avoid full-file dumps.
