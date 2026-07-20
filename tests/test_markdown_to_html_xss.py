"""H13 (review 2026-07-18): markdown_to_html must escape untrusted HTML.

Its output feeds abstract_html / summary_html / topics_html / themes_html /
formatted_content, all LLM-generated from the transcript, and every bundle template
renders them with {{ ...|safe }}. Without escaping, a <script>/onerror payload in the
transcript or a model response is stored XSS that executes when the shared HTML/PDF
bundle is opened. Escaping must not break the markdown features that already work.
"""
from transcript_utils import markdown_to_html


def test_script_tag_is_neutralized():
    out = markdown_to_html("<script>alert('pwned')</script>")
    assert "<script>" not in out
    assert "&lt;script&gt;" in out


def test_img_onerror_is_neutralized():
    out = markdown_to_html("caption <img src=x onerror=alert(1)> end")
    assert "<img" not in out
    assert "&lt;img" in out


def test_markdown_still_renders_after_escaping():
    assert markdown_to_html("# Title") == "<h1>Title</h1>"
    assert "<strong>bold</strong>" in markdown_to_html("a **bold** b")
    assert "<em>italic</em>" in markdown_to_html("a *italic* b")


def test_ampersand_is_escaped_not_dropped():
    out = markdown_to_html("AT&T and R&D budgets")
    assert "&amp;" in out
