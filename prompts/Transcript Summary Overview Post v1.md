# OVERVIEW POST GENERATION (GEO-OPTIMIZED)

You are writing a single overview post that orients a new reader to a
transcript and is engineered for retrieval by AI search engines (Perplexity,
ChatGPT search, Google AI Overviews, Claude). This is NOT a thematic essay
and NOT a lens-driven post — it is an orientation-and-reference document.

## Inputs

Focus Keyword: {{focus_keyword}}
Target Audience: {{target_audience}}
Target Word Count: {{target_word_count}}

Source Metadata:
- Title: {{title}}
- Presenter: {{presenter}}
- Date: {{date}}

Source Artifacts:

ABSTRACT:
{{abstract}}

STRUCTURAL THEMES:
{{structural_themes}}

TOPICS:
{{topics}}

KEY TERMS:
{{key_terms}}

## Writing rules (GEO)

These rules are non-negotiable. Each maps to a known AI-search retrieval
signal.

1. **Definitional opener (entity-first).** The first sentence after the H1
   MUST be a declarative definition of the form:
   `<Title> is a <talk/lecture/conversation/presentation> by <Presenter>
   (<Date>) about <subject in 6-12 words>.`
   No hook, no rhetorical question, no quote. Pure declaration.
2. **TL;DR above the fold.** Immediately after the opener, include a `## TL;DR`
   section with 40-60 words of prose followed by a 3-bullet "Key facts" list.
   Each bullet must be a single citable factual atom — no compound sentences.
3. **Question-shaped H2s.** Section headings are phrased as natural-language
   queries (see structure below). This matches how AI search engines rewrite
   user queries and dramatically increases retrieval probability.
4. **Atomic, citable statements.** Body sentences are short, declarative,
   and self-contained. Named entities (people, concepts, dates) appear on
   the same line as the claim — do NOT chain pronouns across sentences.
5. **Explicit attribution.** The presenter's name, the date, and the source
   title each appear at least twice in the body so that any retrieved snippet
   carries provenance.
6. **Named-entity surfacing.** Key terms appear as **bold** on first mention
   in prose, then again in the "Key terms and definitions" section as a
   definition list (one sentence per term).
7. **FAQ block.** End with `## Frequently asked questions` containing 4-6
   `### Question` / answer pairs. Questions must be ones a real reader would
   type into a search engine. Answers are 2-4 sentences, declarative, with
   the named entities present.
8. **Stay grounded.** No invented claims. Every assertion must be traceable
   to the source artifacts above. If a fact is not in the artifacts, do not
   state it.
9. **Focus keyword placement.** Include `{{focus_keyword}}` naturally in:
   the title, the definitional opener, and at least one H2.
10. **Word count target.** Aim for {{target_word_count}} words total.

## Output format (Markdown with YAML frontmatter)

The very first characters of your output MUST be the YAML frontmatter
fenced block, followed immediately by the H1, definitional opener, and the
sections below — in this exact order.

```yaml
slug: "<kebab-case slug derived from title>"
meta_description: "<155 chars max, declarative, contains focus keyword>"
focus_keyword: "{{focus_keyword}}"
target_audience: "{{target_audience}}"
process_stage: "overview_post"
schema_type: "Article"
author: "{{presenter}}"
date_published: "{{date}}"
source_title: "{{title}}"
faq:
  - q: "<question 1, matches FAQ section ### Q1>"
    a: "<answer 1, 2-4 sentences>"
  - q: "<question 2>"
    a: "<answer 2>"
  - q: "<question 3>"
    a: "<answer 3>"
  - q: "<question 4>"
    a: "<answer 4>"
```

# {{title}}

<Definitional opener sentence per rule 1.>

## TL;DR

<40-60 word prose summary. Plain declarative sentences. Contains focus
keyword once.>

- <Key fact 1: single citable atomic statement with named entity.>
- <Key fact 2: single citable atomic statement with named entity.>
- <Key fact 3: single citable atomic statement with named entity.>

## What is this transcript about?

<2-3 short paragraphs anchored on the ABSTRACT input. Repeat presenter name
and date at least once. Use atomic sentences.>

## Why does this matter?

<2-3 short paragraphs anchored on STRUCTURAL THEMES + ABSTRACT. State the
stakes for the target audience in concrete terms — what changes for a
reader who understands this material vs. one who does not.>

## What are the key topics discussed?

<Render each topic from TOPICS as a sub-paragraph. Pattern per topic:
**<Topic name>.** <1-2 sentences describing what is said about it in the
source.> Do not invent topics; use only those present in the TOPICS input.>

## Key terms and definitions

<Definition list rendered from KEY TERMS. Format:

**<Term>** — <one-sentence definition grounded in source.>

Repeat for each term in KEY TERMS, in the order they appear there.>

## Key takeaways

- <Takeaway 1: atomic, citable, contains a named entity.>
- <Takeaway 2: atomic, citable, contains a named entity.>
- <Takeaway 3: atomic, citable, contains a named entity.>
- <Takeaway 4 (optional): atomic, citable.>
- <Takeaway 5 (optional): atomic, citable.>

## Frequently asked questions

### <Question 1, matches faq[0].q in frontmatter exactly>

<Answer 1, 2-4 sentences, matches faq[0].a in frontmatter in substance.>

### <Question 2>

<Answer 2.>

### <Question 3>

<Answer 3.>

### <Question 4>

<Answer 4.>

<Include up to two more Q/A pairs if the source supports them. Mirror each
one in the frontmatter `faq:` list.>
