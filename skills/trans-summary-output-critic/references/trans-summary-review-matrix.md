# trans-summary Prompt Review Matrix

This matrix reflects current pipeline behavior in code.

## Core outputs to review
- Formatting prompt -> ` - formatted.md`
- Header validation prompt -> ` - header-validation.md`
- Topics prompt -> ` - topics.md`
- Structural themes prompt -> ` - structural-themes.md`
- Interpretive themes prompt -> ` - interpretive-themes.md`
- Lens generation prompt -> ` - lenses-ranked.md`
- Theme/lens validation prompt -> lens output quality + regeneration behavior
- Key terms prompt -> ` - key-terms.md`
- Blog prompt -> ` - blog.md`
- Abstract generation prompt -> ` - abstract-generated.md`
- Validation coverage prompt -> ` - abstract-validation.txt` (and ` - summary-validation.txt` when structured summary is used)
- Emphasis prompt -> ` - emphasis-scored.md` (or legacy ` - emphasis-items.md`)
- Bowen extraction/filter prompts -> ` - bowen-references.md`

## Optional / non-default in current flow
- Structured summary prompt (`Summary Generation Prompt v1.md`) -> ` - summary-generated.md` only when structured summary path is enabled.
- Voice audit prompt may run without saving ` - voice-audit.json`; treat as blog-quality audit unless explicit save-report is required.

## Excluded from default reviewer scope
- `problematic_header_terms_v2.md` (support list, not a direct output artifact)

## Human-level confirm/deny focus
- Theme quality: real recurring process vs generic abstractions.
- Lens quality: transcript-specific fit, ranking rationale, non-overlap.
- Blog quality: fidelity, uncertainty calibration, no overclaims.
- Quote extraction quality: grounding and salience.
