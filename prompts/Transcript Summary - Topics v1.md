# TOPICS EXTRACTION

You are analyzing a full lecture transcript.

Generate the primary topics only.

Requirements:
- Return 5-8 topics.
- Use this exact section header first: `## Topics`
- For each topic, use:
  - `### <Topic Title>`
  - 1-2 sentence description
  - metadata line in this format:
    `*_(~XX% of transcript; Sections X-Y)_*`
- Topics should be concrete content objects (not broad framing themes).
- Avoid structural and interpretive language (for example: avoid naming tensions, paradoxes, motifs as topics).

Output only the Topics section.
