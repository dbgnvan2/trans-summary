# BLOG POST GENERATION (FROM TOP LENS ONLY)

You are writing a single SEO-ready blog post from the validated top-ranked lens.

Focus Keyword: {{focus_keyword}}
Target Audience: {{target_audience}}

Top Lens (Rank #1):
- Title: {{top_lens_title}}
- Description: {{top_lens_description}}
- Evidence: {{top_lens_evidence}}
- Hooks: {{top_lens_hooks}}
- Rationale: {{top_lens_rationale}}

Rules:
- Use the top lens only as the organizing spine.
- Do not switch to lower-ranked lenses.
- Stay grounded in source material; no invented claims.
- State facts about people and events (who did what, when, what happened next) only as the speaker told them, and attribute them to the speaker ("Kerr recalls…", "Kerr says…").
- Do not add details, outcomes, or motives the transcript does not give.
- Do not make generalisations about "most people" or "most families" unless the speaker makes them.
- Interpretation and figures of speech are allowed only when they are a fair reading of what the speaker said.
- Write in clear educational language.
- Include the focus keyword naturally in title, opening, and one H2.

Output format (Markdown):

```yaml
slug: "[slug]"
meta_description: "[155 chars max]"
focus_keyword: "{{focus_keyword}}"
process_stage: "blog_content_generation_from_top_lens"
```

# [H1 Title]

[Introduction tied to top lens]

## [H2 Section]
[Content]

## [H2 Section]
[Content]

## [H2 Section]
[Content]

## Key Takeaways
- [Point 1]
- [Point 2]
- [Point 3]

## Glossary of Terms
- **[Term]:** [Definition]
