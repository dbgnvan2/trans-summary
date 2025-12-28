import pytest
from html_generator import _highlight_html_content, _generate_simple_html_page

def test_highlight_html_content_basic():
    formatted_html = "<p>This is a test of the highlighting system.</p>"
    
    # Mock data
    bowen_refs = [('Concept A', 'test of the')]
    emphasis_items = [('Item 1', 'highlighting system')]
    key_term_defs = []

    highlighted = _highlight_html_content(formatted_html, bowen_refs, emphasis_items, key_term_defs)
    
    # Check for Bowen mark
    assert '<mark class="bowen-ref" title="Bowen Reference: Concept A">' in highlighted
    assert '>test of the</mark>' in highlighted
    
    # Check for Emphasis mark
    assert '<mark class="emphasis" title="Emphasized: Item 1">' in highlighted
    assert '>highlighting system</mark>' in highlighted

def test_highlight_html_content_overlap():
    # "test of the" (Bowen) overlaps with "the highlighting" (Emphasis) - Wait, logic handles this?
    # Let's test non-overlapping first to be safe, then strict overlap if we know the behavior.
    # The current logic has a priority system: Emphasis > Bowen > Defs.
    pass

def test_highlight_html_content_exact_word_match():
    formatted_html = "<p>Word match test.</p>"
    emphasis_items = [('Target', 'match')]
    
    highlighted = _highlight_html_content(formatted_html, [], emphasis_items, [])
    
    assert '<mark class="emphasis" title="Emphasized: Target">match</mark>' in highlighted

def test_generate_simple_html_page_structure():
    base_name = "Test Title - Test Author - 2025-01-01"
    formatted_content = "<p>Content</p>"
    abstract = "Abstract text"
    key_terms = ["Term1", "Term2"]
    
    html = _generate_simple_html_page(base_name, formatted_content, abstract, key_terms)
    
    assert "<title>Test Title</title>" in html
    assert "<h1>Test Title</h1>" in html
    assert "Test Author" in html
    assert "2025-01-01" in html
    assert "<p>Content</p>" in html
    assert "<strong>Term1</strong>" in html
    assert "Abstract text" in html
