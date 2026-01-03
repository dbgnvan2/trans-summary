from html_generator import _generate_simple_html_page, _highlight_html_content


def test_highlight_html_content_basic():
    formatted_html = "<p>This is a test of the highlighting system.</p>"

    # Mock data
    bowen_refs = [("Concept A", "test of the")]
    emphasis_items = [("Item 1", "highlighting system")]

    # Updated signature: 3 args
    highlighted = _highlight_html_content(formatted_html, bowen_refs, emphasis_items)

    # Check for Bowen mark
    assert '<mark class="bowen-ref" title="Bowen Reference: Concept A">' in highlighted
    assert ">test of the</mark>" in highlighted

    # Check for Emphasis mark
    assert '<mark class="emphasis" title="Emphasized: Item 1">' in highlighted
    assert ">highlighting system</mark>" in highlighted


def test_highlight_html_content_exact_word_match():
    formatted_html = "<p>Word match test.</p>"
    emphasis_items = [("Target", "match")]

    # Updated signature: 3 args
    highlighted = _highlight_html_content(formatted_html, [], emphasis_items)

    assert (
        '<mark class="emphasis" title="Emphasized: Target">match</mark>' in highlighted
    )


def test_generate_simple_html_page_structure():
    base_name = "Test Title - Test Author - 2025-01-01"
    formatted_content = "<p>Content</p>"

    # Mock metadata dict
    metadata = {
        "abstract": "Abstract text",
        "topics": "Topics text",
        "themes": "Themes text",
        "key_terms": [
            {"name": "Term1", "definition": "Def1"},
            {"name": "Term2", "definition": "Def2"},
        ],
    }
    summary = "Summary text"
    bowen_refs = [("Ref1", "Quote1")]
    emphasis_items = [("Emp1", "Quote2")]

    html = _generate_simple_html_page(
        base_name,
        formatted_content,
        metadata,
        summary,
        bowen_refs,
        emphasis_items,
    )

    assert "<title>Test Title</title>" in html
    assert "<h1>Test Title</h1>" in html
    assert "Test Author" in html
    assert "2025-01-01" in html
    assert "<p>Content</p>" in html
    assert "<strong>Term1</strong>" in html
    assert "Abstract text" in html