---
Prev:
  - "[[- Transcript Summary PROMPTS MOC]]"
Next:
tags:
  - transcript/summary
summary: What is this note for?
---
--- 
# Prompt for Generating Structural Themes

**Version:** 2025-02  
**Purpose:** Extract 2–4 structural (top-level) themes from a Michael Kerr / Bowen theory lecture transcript and supporting sections.  
**Goal:** Produce stable, high-level organizing ideas that answer “What is this talk fundamentally about?” — used for abstracts, framing, metadata, and as anchors for interpretive themes / lenses.

## Prompt Text (copy-paste ready)
```

You are analyzing a complete lecture document containing: abstract, summary, key topics (with %-based coverage), key terms, emphasized items, Bowen references (if present), and the full transcript (including Q&A, personal anecdotes, and clinical examples).

Your task is to generate **2–4 structural themes**. These are the top-level, canonical organizing ideas of the entire presentation.

Definition of structural themes:

- They capture what the talk is fundamentally about at the highest level
- They are mutually exclusive or minimally overlapping
- They are stable across summaries and re-readings
- They span the entire content holistically (not section-specific)
- They answer: “What are the core organizing concepts / theses of this lecture?”
- They should be broad enough to encompass most of the material, yet specific enough to distinguish this talk from others
- Typical count: 2–4 (rarely more than 4 even in dense 60–90 min talks; never force more than 4)

Instructions:

1. Base your analysis on the **entire document**: abstract, summary, key topics (pay attention to high-% coverage), emphasized items, key terms, Bowen references, and the full transcript (including Q&A and personal/clinical stories).
2. Identify the 2–4 most encompassing, high-level ideas that unify the presentation.
3. Avoid:
    - Creating too many themes (inflation weakens focus)
    - Making themes too narrow or section-specific
    - Turning themes into summaries or lists of topics
    - Using overly vague or generic labels (e.g. “Bowen Theory” or “Cancer” alone)
4. For each structural theme, provide:
    - A clear, concise title (ideally 4–10 words)
    - A 2–4 sentence description explaining the theme and why it is central
    - Key supporting evidence (specific sections, pages, quotes, or motifs from the document)
    - Approximate coverage / importance (e.g. “spans ~40% of content via repeated emphasis” or “anchors the entire convergence argument”)

Output format: Present the structural themes in a clean, numbered list or table.

Example output structure:

### Structural Themes (3 total)

1. **Title of Theme 1** Description: 2–4 sentences. Key evidence: Sections X–Y, emphasized items, high-% topics, quotes, etc. Coverage / role: ...
2. **Title of Theme 2** ...
3. **Title of Theme 3** ...

If you identify only 2 very strong themes that fully cover the talk, stop at 2. If the content strongly supports 4 distinct high-level organizers, use 4 — but never exceed 4.

After listing the themes, add one short paragraph summarizing:

- Why these themes were chosen
- How well they cover the full presentation (including Q&A)
- Any notable edge cases or tensions resolved by this set

Do not generate interpretive / mid-level themes, process motifs, or blog lenses at this stage — focus exclusively on structural (top-level) themes.

text

```
## Usage Recommendations

- **Run this prompt first** in your pipeline — before interpretive themes or lenses.
- **Feed the output directly** into the lens-generation prompt (it expects structural themes as one of the inputs).
- **Count guidance reminder**:
  - 60–90 min dense theoretical talks → usually 3–4
  - More clinical / applied talks → often 2–3
  - Very short or focused talks → sometimes only 2

## Optional light variation (for very short transcripts)

If you know in advance the talk is short (<30–40 min), you can add at the beginning:
```

Limit to 2–3 structural themes only — shorter presentations rarely support more.