"""R4 (review D-09): repo-owned CSS is not HTML-escaped inside <style>.

Autoescape turned 'Georgia' into &#39;Georgia&#39;, which ends the CSS
declaration early and drops the body font in the webpage, simple page and PDF.

Spec: docs/plan_review_fixes_2026-10-04.md#R4
"""
import pytest

import html_generator


@pytest.mark.parametrize("template_name", ["webpage.html", "simple_webpage.html", "pdf.html"])
def test_r4a_css_not_escaped(template_name):
    assert "'Georgia'" in html_generator.COMMON_CSS  # the CSS this test guards
    html = html_generator.template_env.get_template(template_name).render(
        common_css=html_generator.COMMON_CSS,
        webpage_css=html_generator.WEBPAGE_CSS,
        pdf_css=html_generator.PDF_CSS,
        meta={},
    )
    assert "font-family: 'Georgia', serif;" in html
    assert "&#39;" not in html.split("</style>")[0]
