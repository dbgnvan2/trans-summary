---
Prev:
  - "[[- Transcript Summary PROMPTS MOC]]"
  - "[[- AI TL Chatbot PROJECT MOC]]"
Next:
tags:
  - transcript/summary
summary: What is this note for?
---
--- 
# Prompt for Generating Interpretive / Process Themes

**Version:** 2025-02  
**Purpose:** Generate 5–8 mid-level interpretive/process themes (also called "motifs", "thematic tensions", or "conceptual vectors") from a Michael Kerr / Bowen theory lecture transcript and supporting materials.  
**Goal:** These themes serve as "lens fuel" — dynamic, non-exclusive, process-oriented elements that highlight tensions, contrasts, feedback loops, emergent patterns, or recurring conceptual dynamics. They are nested under or derived from the structural themes and provide the raw material for creating diverse blog lenses.

## Prompt Text (copy-paste ready)

You are analyzing a complete lecture document that includes: abstract, summary, key topics (with %-based coverage), structural themes (already identified, 2–4 top-level organizers), key terms, emphasized items, Bowen references (if present), and the full transcript (including Q&A, personal anecdotes, clinical vignettes, and speaker emphasis).

Your task is to generate **5–8 interpretive / process themes** (also called process motifs, thematic tensions, or conceptual vectors).

Definition of interpretive/process themes:

- They are mid-level, dynamic elements — not summaries
- They capture recurring tensions, contrasts, feedback loops, emergent processes, or conceptual vectors operating within the talk
- They are **not** mutually exclusive — overlap and nesting is expected and desirable
- They are often nested inside or flow from the structural themes
- They answer questions like:
    - What underlying dynamics / processes are at work here?
    - What tensions or contrasts keep recurring?
    - What conceptual relationships or feedback loops drive the content?
- They provide the "fuel" for generating diverse, recombined blog lenses
- They are more granular and process-oriented than structural themes, but more synthetic than individual topics or quotes

Count guidance:

- Generate 5–8 themes (default target: 6–7)
- Use 5–6 for shorter or less dense talks
- Use 7–8 for longer, theoretically rich talks with substantial Q&A and layered ideas (typical for most Kerr lectures)

Instructions:

1. Base your analysis on the **entire document**, giving special attention to:
    - emphasized items and repeated motifs
    - high-% key topics
    - Q&A tensions, personal/clinical stories, and speaker excitement
    - contrasts, paradoxes, feedback loops, or emergent patterns
2. Ensure each theme is clearly nested under or strongly related to one or more structural themes (reference which one(s))
3. Avoid:
    - Creating themes that are simply restatements of structural themes
    - Making themes too narrow (e.g. single quote or minor anecdote)
    - Producing more than 8 (inflation reduces discriminability for lenses)
    - Generating summary-like or purely descriptive items
4. For each interpretive theme, provide:
    - A clear, concise title (ideally 5–12 words)
    - A 2–4 sentence description explaining the dynamic/process/tension
    - Which structural theme(s) it nests under or relates to most strongly
    - Key supporting evidence (specific sections, quotes, emphasized items, Q&A moments, etc.)
    - Why this is a useful "lens fuel" element (brief — 1 sentence)

Output format: Use a clean, numbered list or table.

Example structure:

## Interpretive / Process Themes (7 total)

1. **Title of Theme 1** Description: 2–4 sentences explaining the dynamic. Nested under structural theme(s): [list] Key evidence: Sections X–Y, emphasized item Z, Q&A moment A... Lens fuel value: Enables lenses on [practical implication / contrast / application].
2. **Title of Theme 2** ...

After the list, add one short paragraph summarizing:

- How these interpretive themes collectively derive from and enrich the structural themes
- The range of dynamics covered (e.g. biological-family parallels, stress processes, variability, etc.)
- Any notable gaps or edge cases intentionally left for lens-level exploration

Do not generate structural themes (already provided), blog lenses, or full blog posts at this stage — focus exclusively on mid-level interpretive/process themes.
## Usage Recommendations

- **Run order in pipeline**:
  1. Structural themes prompt → produces 2–4 anchors
  2. This interpretive themes prompt → uses structural output as input
  3. Lens generation & ranking prompt → uses both structural and interpretive outputs

- **Typical count in Kerr talks**:
  - Dense interdisciplinary talks (e.g. 2021 Rethinking Cancer) → 7–8
  - More clinically focused public lectures (e.g. 2011 Making a Difference) → 6–7
  - Very short talks → 5–6

- **Most important guardrail**:
  - These are **not** summaries or topic lists
  - They are **dynamic processes/tensions** — look for verbs, contrasts, relationships, feedback, emergence

Give particular weight to dynamics that emerge or are clarified in Q&A sections, personal anecdotes, clinical examples, and moments where the speaker expresses particular excitement or surprise — these frequently reveal the most generative process motifs.
