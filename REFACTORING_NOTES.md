# Code Refactoring: Centralized Markdown Extraction

## Problem

Multiple scripts had hardcoded regex patterns for extracting sections from markdown files. When the format changed (e.g., `## Topics` vs `## **Topics**`), we had to hunt down and fix patterns in multiple files, leading to fragility and maintenance issues.

## Solution

Centralized all markdown extraction patterns in `transcript_utils.py` with flexible regex patterns that handle format variations.

## New Utility Functions

### `extract_section(content, section_name, allow_bold=True)`

Extracts any markdown section by name, handling both:

- `## Section Name` (plain)
- `## **Section Name**` (with bold markers)

**Example:**

```python
from transcript_utils import extract_section

topics = extract_section(content, "Topics")  # Works for both formats
themes = extract_section(content, "Key Themes")
abstract = extract_section(content, "Abstract")
```

### `extract_bowen_references(content)`

Extracts Bowen reference quotes in blockquote format:

```markdown
> **Concept:** "Quote text"
```

Returns: `[(concept, quote), ...]`

### `extract_emphasis_items(content)`

Extracts emphasized item quotes in blockquote format.

Returns: `[(item, quote), ...]`

### `strip_yaml_frontmatter(content)`

Removes YAML frontmatter from markdown content.

## Files Updated

### `transcript_utils.py`

- Added centralized extraction functions
- Flexible regex patterns with `\*{0,2}` to match 0-2 asterisks
- Single source of truth for all extraction patterns

### `transcript_to_pdf.py`

- Imports: `extract_section`, `extract_bowen_references`, `extract_emphasis_items`, `strip_yaml_frontmatter`
- Replaced local extraction functions with calls to centralized utils
- Renamed wrappers: `load_bowen_references()`, `load_emphasis_items()`

### `transcript_to_simple_webpage.py`

- Same refactoring as PDF generation
- Now uses centralized extraction functions
- Simplified `extract_abstract()` to use `extract_section()`

## Benefits

1. **Single Source of Truth**: All extraction patterns defined once in `transcript_utils.py`
2. **Format Flexibility**: Automatically handles variations in markdown formatting
3. **Easier Maintenance**: Update patterns in one place instead of hunting across files
4. **Less Fragile**: Regex patterns handle both `## Section` and `## **Section**` formats
5. **Consistent Behavior**: All scripts extract content the same way

## Testing

All scripts tested and verified working:

- ✅ `transcript_to_pdf.py` - Generates PDF with TOC and correct sections
- ✅ `transcript_to_simple_webpage.py` - Generates HTML with proper extraction
- ✅ `transcript_validate_webpage.py` - Correctly counts 9 Bowen + 17 emphasis marks

## Future Improvements

Consider adding to `transcript_utils.py`:

- `extract_key_terms()` - Centralize term extraction
- `extract_all_metadata()` - One function to extract all sections
- Configuration file for section names and patterns
- Schema validation for extracted content
