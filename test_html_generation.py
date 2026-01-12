"""
Test script for html_generator.py with Jinja2 templates.
Verifies that all three generation functions work correctly after refactoring.
"""

import sys
from pathlib import Path

# Test data
TEST_BASE_NAME = "Test Presentation - Dr. Smith - 2024-01-15.txt"
TEST_FORMATTED_CONTENT = """
<p><strong>Speaker:</strong> Hello everyone, this is a test transcript.</p>
<p>We'll discuss some important concepts today, including <em>differentiation of self</em>
and <em>emotional systems</em>.</p>
<p>The family system operates as an emotional unit with complex interconnections.</p>
"""

TEST_METADATA = {
    "abstract": "This is a test abstract discussing Bowen Family Systems Theory concepts.",
    "topics": """
- Differentiation of self
- Emotional systems
- Family dynamics
""",
    "themes": """
- Systems thinking
- Emotional process
- Relationship patterns
""",
    "key_terms": [
        {
            "name": "Differentiation of Self",
            "definition": "The ability to separate thinking from feeling and to resist being overwhelmed by emotional reactivity."
        },
        {
            "name": "Emotional System",
            "definition": "The network of emotional functioning that governs relationships."
        }
    ]
}

TEST_SUMMARY = """
# Test Summary

This is a comprehensive test of the HTML generation system after refactoring to use Jinja2 templates.

## Key Points

1. Templates successfully separated from Python code
2. CSS extracted to separate files
3. All generation functions maintained
"""

TEST_BOWEN_REFS = [
    ("Differentiation of Self", "The ability to separate thinking from feeling and to resist being overwhelmed"),
    ("Emotional System", "The network of emotional functioning that governs relationships")
]

TEST_EMPHASIS_ITEMS = [
    ("Important Concept (95%)", "family system operates as an emotional unit"),
    ("Key Theme (88%)", "important concepts today")
]


def test_imports():
    """Test that all required modules can be imported."""
    print("Testing imports...")
    try:
        from html_generator import (
            generate_webpage,
            generate_simple_webpage,
            generate_pdf,
            _highlight_html_content,
            _generate_html_page,
            _generate_simple_html_page,
            _generate_pdf_html
        )
        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_template_files_exist():
    """Test that all template files exist."""
    print("\nTesting template files...")

    templates_dir = Path(__file__).parent / "templates"
    styles_dir = templates_dir / "styles"

    required_files = [
        templates_dir / "base.html",
        templates_dir / "webpage.html",
        templates_dir / "simple_webpage.html",
        templates_dir / "pdf.html",
        styles_dir / "common.css",
        styles_dir / "webpage.css",
        styles_dir / "pdf.css"
    ]

    all_exist = True
    for file_path in required_files:
        if file_path.exists():
            print(f"✓ Found: {file_path.relative_to(Path.cwd())}")
        else:
            print(f"✗ Missing: {file_path.relative_to(Path.cwd())}")
            all_exist = False

    return all_exist


def test_webpage_generation():
    """Test webpage generation with sidebar."""
    print("\nTesting webpage generation...")
    try:
        from html_generator import _generate_html_page

        html = _generate_html_page(
            TEST_BASE_NAME,
            TEST_FORMATTED_CONTENT,
            TEST_METADATA,
            TEST_SUMMARY,
            TEST_BOWEN_REFS,
            TEST_EMPHASIS_ITEMS
        )

        # Verify key elements are present
        checks = [
            ("<html", "HTML tag"),
            ("<head>", "Head section"),
            ("<body>", "Body section"),
            ("Test Presentation", "Title"),
            ("Dr. Smith", "Author"),
            ("2024-01-15", "Date"),
            ("<aside class=\"sidebar\">", "Sidebar"),
            ("<main class=\"main-content\">", "Main content"),
            ("Differentiation of Self", "Key term"),
            ("mark class=\"bowen-ref\"", "Bowen reference highlighting"),
            ("mark class=\"emphasis", "Emphasis highlighting"),
        ]

        passed = 0
        failed = 0
        for check_str, description in checks:
            if check_str in html:
                print(f"  ✓ {description}")
                passed += 1
            else:
                print(f"  ✗ Missing: {description}")
                failed += 1

        if failed == 0:
            print(f"✓ Webpage generation successful ({passed}/{passed} checks passed)")
            return True
        else:
            print(f"✗ Webpage generation incomplete ({passed}/{passed + failed} checks passed)")
            return False

    except Exception as e:
        print(f"✗ Webpage generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_simple_webpage_generation():
    """Test simple webpage generation without sidebar."""
    print("\nTesting simple webpage generation...")
    try:
        from html_generator import _generate_simple_html_page

        html = _generate_simple_html_page(
            TEST_BASE_NAME,
            TEST_FORMATTED_CONTENT,
            TEST_METADATA,
            TEST_SUMMARY,
            TEST_BOWEN_REFS,
            TEST_EMPHASIS_ITEMS
        )

        # Verify key elements are present
        checks = [
            ("<html", "HTML tag"),
            ("<header>", "Header section"),
            ("Test Presentation", "Title"),
            ("<section class=\"section\">", "Section"),
            ("Differentiation of Self", "Key term"),
            ("mark class=\"bowen-ref\"", "Bowen reference highlighting"),
        ]

        # Verify sidebar is NOT present
        if "<aside class=\"sidebar\">" in html:
            print("  ✗ Sidebar should not be present in simple webpage")
            return False

        passed = 0
        failed = 0
        for check_str, description in checks:
            if check_str in html:
                print(f"  ✓ {description}")
                passed += 1
            else:
                print(f"  ✗ Missing: {description}")
                failed += 1

        if failed == 0:
            print(f"✓ Simple webpage generation successful ({passed}/{passed} checks passed)")
            return True
        else:
            print(f"✗ Simple webpage generation incomplete ({passed}/{passed + failed} checks passed)")
            return False

    except Exception as e:
        print(f"✗ Simple webpage generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_pdf_generation():
    """Test PDF HTML generation."""
    print("\nTesting PDF HTML generation...")
    try:
        from html_generator import _generate_pdf_html

        html = _generate_pdf_html(
            TEST_BASE_NAME,
            TEST_FORMATTED_CONTENT,
            TEST_METADATA,
            TEST_SUMMARY,
            TEST_BOWEN_REFS,
            TEST_EMPHASIS_ITEMS
        )

        # Verify key elements are present
        checks = [
            ("<html", "HTML tag"),
            ("<div class=\"cover\">", "Cover page"),
            ("<div class=\"toc\">", "Table of contents"),
            ("Test Presentation", "Title"),
            ("<div class=\"section\">", "Section dividers"),
            ("@page", "Page rules for printing"),
            ("mark class=\"bowen-ref\"", "Bowen reference highlighting"),
        ]

        passed = 0
        failed = 0
        for check_str, description in checks:
            if check_str in html:
                print(f"  ✓ {description}")
                passed += 1
            else:
                print(f"  ✗ Missing: {description}")
                failed += 1

        if failed == 0:
            print(f"✓ PDF HTML generation successful ({passed}/{passed} checks passed)")
            return True
        else:
            print(f"✗ PDF HTML generation incomplete ({passed}/{passed + failed} checks passed)")
            return False

    except Exception as e:
        print(f"✗ PDF HTML generation failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_highlighting_logic():
    """Test that the highlighting logic still works correctly."""
    print("\nTesting highlighting logic...")
    try:
        from html_generator import _highlight_html_content

        # Use more context for better matching
        test_html = """<p>This discusses differentiation of self and emotional systems in the context of family therapy.</p>"""

        result = _highlight_html_content(
            test_html,
            [("Differentiation of Self", "differentiation of self and emotional systems")],
            [("Key Concept (92%)", "discusses differentiation of self")]
        )

        # Check that both types of highlighting are present
        # Note: The logic may merge overlapping highlights into single mark elements
        checks = [
            ("bowen-ref", "Bowen highlighting added (may be merged with emphasis)"),
            ("mark class=\"emphasis", "Emphasis highlighting added"),
            ("Differentiation of Self", "Bowen reference label present"),
        ]

        passed = 0
        failed = 0
        for check_str, description in checks:
            if check_str in result:
                print(f"  ✓ {description}")
                passed += 1
            else:
                print(f"  ✗ {description}")
                failed += 1

        if failed == 0:
            print(f"✓ Highlighting logic working ({passed}/{passed} checks passed)")
            return True
        else:
            # Show debug info on failure
            print(f"  Debug: Result contains: {result[:200]}...")
            print(f"✗ Highlighting logic incomplete ({passed}/{passed + failed} checks passed)")
            return False

    except Exception as e:
        print(f"✗ Highlighting logic failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 70)
    print("HTML GENERATOR TEMPLATE REFACTORING TEST SUITE")
    print("=" * 70)

    tests = [
        ("Import Test", test_imports),
        ("Template Files", test_template_files_exist),
        ("Webpage Generation", test_webpage_generation),
        ("Simple Webpage Generation", test_simple_webpage_generation),
        ("PDF HTML Generation", test_pdf_generation),
        ("Highlighting Logic", test_highlighting_logic),
    ]

    results = []
    for test_name, test_func in tests:
        result = test_func()
        results.append((test_name, result))

    # Summary
    print("\n" + "=" * 70)
    print("TEST SUMMARY")
    print("=" * 70)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")

    print(f"\nTotal: {passed}/{total} tests passed")

    if passed == total:
        print("\n🎉 All tests passed! Template refactoring successful.")
        return 0
    else:
        print(f"\n❌ {total - passed} test(s) failed. Please review errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
