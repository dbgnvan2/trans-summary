# Published Themes section: the model's closing notes shown inside the last theme (TD) — 2026-10-13

Status: **built 2026-10-13** at the user's request ("fix the published page display
too"). Follows TE (`docs/calibration_theme_evidence_2026-10-13.md`), which fixed the
same problem on the judge side.

## Problem

`transcript_utils.theme_display_blocks` publishes each theme's block. The last theme
block runs to the end of the file, so the model's closing notes were published as
part of theme 3. The notes are "Summary paragraph", "Rationale and coverage summary"
and "Why these themes were chosen and how well they cover the presentation". They
explain the model's choice of themes, note overlaps between them, and add caveats
about the source, which is not content for readers. Example from the Why Families
page: "Two caveats on the source: this is an interview or podcast rather than a
lecture…".

## Decision

One helper, `transcript_utils._theme_own_text_report`, decides which part of a theme
block belongs to the theme. Both the published page (`theme_display_blocks`) and the
judge's parser (`parse_theme_blocks_with_evidence`) use it through
`_accepted_theme_blocks`, so both list the same themes with the same text, and a theme
needs a description in its own text.
- **Document-level tail:** a tail of document-level fields
  (`config.THEME_DOCUMENT_LEVEL_LABELS`) is cut.
- **Document-level field inside a theme:** if theme fields follow it, only that field
  is dropped.
- **Last theme only:**
  - a heading after its final field ends the theme;
  - when the final field is a theme-level meta field (Lens fuel value, Coverage /
    role, Nested under…, one paragraph in every real file), later prose paragraphs are
    an unlabeled closing note ("These seven themes break the three structural
    anchors…") and are dropped;
  - a Description or Key evidence field keeps all its paragraphs (list items, quotes,
    a second paragraph);
  - a `---` rule is not a note.
- **Reporting:** the parser doesn't log. The release gate reports what was left out
  once per theme file (`trimmed_theme_notes`), as it does for unclassified fields.
- **The notes are not shown anywhere else.** This follows D1, which limited the Themes
  section to the themes themselves.
- **One list:** `THEME_JUDGE_META_LABELS` is built from `THEME_DOCUMENT_LEVEL_LABELS`,
  so each label is written once.

## UI contract (ui-regression standard)

- **Unchanged:** every theme's title, number, Description, Key evidence, Coverage /
  role, Lens fuel value and "Nested under" fields stay on the page.
- **Removed:** only the notes after the last theme's own fields.

Checked on every real theme file:
- 262 themes in 65 files under `~/projects`, `~/transcripts`, the CrucialX9 KCFC and
  BTA folders, and `tests/fixtures`;
- 8 themes changed, each the last theme of its file: 5 real themes and 3 fixture copies.
  Why Families interpretive theme 7 lost an unlabeled note; the other 7 lost labelled
  notes;
- each lost only the trailing notes, and its new text is a prefix of the old text;
- no theme count changed;
- the judge's input (names, descriptions, evidence) is identical to the committed code
  on all 65 files, so no new calibration is needed. The helpers are in the judge cache
  key.

Where themes are published: the full page, the simple page and the PDF all build the
Themes section through `html_generator._extract_webpage_metadata` →
`_themes_markdown` → `theme_display_blocks`. The DOC/PDF bundle has no Themes section
(`config.BUNDLE_SECTIONS`).

## Criteria and tests (`tests/test_theme_display_td.py`)

| ID | Criterion | Test | Status |
|---|---|---|---|
| TD1 | The notes don't appear in the page's Themes markdown or HTML, for the three real files (Why Families, Beautiful Boy, triangles lecture). | `test_td1_trailing_notes_not_published` | done |
| TD1.b | An unlabeled closing note (Why Families interpretive) is not published. | `test_td1_unlabeled_closing_note_not_published` | done |
| TD1.a | UI contract: the last theme keeps its title (rendered as "3. …"), Description, Key evidence and Coverage / role. | `test_td1_last_theme_keeps_its_own_fields` | done |
| TD2 | No published theme keeps a document-level field. The tail cut keeps a prefix. A document-level field inside a theme drops only that field. A multi-paragraph Description or Key evidence is kept. A `---` rule is not a note. A legacy H3 closing heading is not published. | `test_td2_no_document_field_remains_in_any_fixture`, `test_td2_tail_cut_keeps_a_prefix`, `test_td2_document_label_inside_a_theme_drops_only_that_field`, `test_td2_multi_paragraph_last_field_is_kept`, `test_td2_rule_lines_are_not_closing_notes`, `test_td2_h3_trailing_heading_not_published` | done |
| TD3 | The page and the judge list the same themes, and the judge reads the published text. The document-level labels are non-evidence and are in the judge cache key. | `test_td3_page_and_judge_list_the_same_themes`, `test_td3_judge_reads_the_published_text`, `test_td3_document_labels_are_non_evidence`, `tests/test_judge_disk_cache_h2.py::test_r9a_vocabulary_change_changes_key[THEME_DOCUMENT_LEVEL_LABELS]` | done |
| TD3.a | The gate reports what was left out once per file. | `test_td4_gate_reports_left_out_notes_once` | done |
| TD4 | Before/after on all real theme files: only those 8 themes change, by removal at the end; judge input unchanged. | Not code-testable (files outside the repo); measured as above | done |

## Known limit

An unlabeled closing note after a last field that is Description or Key evidence is
kept, as part of that field. It can't be told apart from a second paragraph of the
field. No real file has this shape.

## Not changed

- Pages already published keep the notes until they are rebuilt with "8. Full
  Web/PDF" / "8b. Simple Web".
- The affected projects are Why Families 2026-09-13 (both theme files), Beautiful Boy
  (2 copies) and "This is a test".
- Adjacent, not changed: the overview and blog prompts still receive the raw themes
  files, notes included.
