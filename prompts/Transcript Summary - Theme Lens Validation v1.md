# THEME & LENS VALIDATION

You are validating generated artifacts against the source transcript context.

Validate the following:
1. Structural Themes
2. Interpretive Themes
3. Ranked Lenses

Validation rule:
- `CONFIRM` only if the item is well supported by transcript evidence.
- `DENY` if the item is weak, generic, inflated, or not grounded.

Return JSON only with this schema:

{
  "structural_themes_valid": true,
  "interpretive_themes_valid": true,
  "confirmed_lenses": [
    {
      "rank": 1,
      "title": "Lens title"
    }
  ],
  "denied_lenses": [
    {
      "rank": 4,
      "title": "Lens title",
      "reason": "why denied"
    }
  ],
  "top_lens": {
    "rank": 1,
    "title": "Lens title",
    "description": "2-4 sentence angle",
    "evidence": "section refs / anchor evidence",
    "hooks": ["hook 1", "hook 2"],
    "rationale": "why this should be #1"
  },
  "notes": "short summary"
}

Important constraints:
- `top_lens` must come from confirmed lenses only.
- If no lenses are confirmable, set `top_lens` to `{}`.
- Be strict about transcript grounding.

INPUT STRUCTURAL THEMES:
{{structural_themes}}

INPUT INTERPRETIVE THEMES:
{{interpretive_themes}}

INPUT LENSES:
{{lenses}}
