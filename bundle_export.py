"""MD-collection bundle export.

Purpose: Package a run's per-stage Markdown artifacts into a single DOCX and/or
         PDF as a plain concatenation with section headers.
Spec:    docs/spec_bundle_export_2026-07-16.md
Tests:   tests/test_bundle_export.py

DOCX is rendered with pandoc (external binary); PDF reuses WeasyPrint via the
project's markdown_to_html so both formats derive from the same combined
Markdown and never drift. Both are gated by the release gate (fail-closed).
"""

import subprocess
from pathlib import Path

import config
import release_gate

# Reference doc with reduced heading sizes for DOCX (main=Heading1, section=
# Heading2). Regenerate with scripts/gen_bundle_reference_docx.py. Optional --
# if absent, pandoc uses its default styles and DOCX still renders.
_BUNDLE_REFERENCE_DOCX = (
    Path(__file__).resolve().parent / "templates" / "styles" / "bundle-reference.docx"
)
from transcript_utils import (
    markdown_to_html,
    setup_logging,
    strip_yaml_frontmatter,
)

# External-call hardening (P5): bound the pandoc subprocess.
PANDOC_TIMEOUT_SECONDS = 120

# Neutral page-break marker inserted by the builder; each renderer translates it
# to its own construct (CSS break for PDF, raw OpenXML for DOCX).
_PAGEBREAK_MARK = "[[[BUNDLE_PAGEBREAK]]]"
_PAGEBREAK_HTML = '<div style="break-after:page"></div>'
_PAGEBREAK_OPENXML = (
    '\n\n```{=openxml}\n<w:p><w:r><w:br w:type="page"/></w:r></w:p>\n```\n\n'
)

# Bundle PDF heading sizes (main = h1 title, section = h2). Reduced ~15-20% from
# the browser defaults for a more compact document. Edit here to retune.
BUNDLE_PDF_CSS = """
body { font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
       font-size: 11pt; line-height: 1.4; }
h1 { font-size: 18pt; margin: 0.5em 0 0.3em; }   /* main heading (title) */
h2 { font-size: 14pt; margin: 0.9em 0 0.3em; }   /* section heading */
h3 { font-size: 12pt; margin: 0.7em 0 0.2em; }
"""


def _build_combined_markdown(base_name, sections=None, logger=None):
    """Concatenate the per-run MD sections in order with headings.

    Spec: docs/spec_bundle_export_2026-07-16.md#BE.2

    `sections` defaults to `config.BUNDLE_SECTIONS`; the post-run dialog passes a
    user-selected subset (BE.9).

    Returns (markdown_text, included, missing_required, missing_optional,
    empty_present) — lists of section headings. Missing REQUIRED sections are
    collected for the caller to fail on; missing OPTIONAL sections are skipped
    and reported (P2 — surface, never silently drop). A section artifact that
    exists but strips to empty is producer/consumer content drift (P19): it is
    NOT shipped as a blank section — it is recorded in empty_present (and, if
    required, also in missing_required so the caller fails).
    """
    if sections is None:
        sections = config.BUNDLE_SECTIONS
    proj = config.PROJECTS_DIR / base_name
    parts = [f"# {base_name}\n"]
    included, missing_required, missing_optional, empty_present = [], [], [], []
    for section in sections:
        heading = section["heading"]
        required = bool(section.get("required"))
        # Use the first candidate artifact that exists AND has content (P19:
        # present-but-empty is not content). "Format or YAML" for the transcript.
        chosen_text, any_existed = None, False
        for attr in section["suffix_attrs"]:
            path = proj / f"{base_name}{getattr(config, attr)}"
            if not path.exists():
                continue
            any_existed = True
            text = path.read_text(encoding="utf-8")
            if section.get("strip_frontmatter"):
                text = strip_yaml_frontmatter(text)
            text = text.strip()
            if text:
                chosen_text = text
                break
        if chosen_text is None:
            if any_existed:
                empty_present.append(heading)
                if required:
                    missing_required.append(heading)
            else:
                (missing_required if required else missing_optional).append(heading)
            continue
        # Section headings are h2 (## ) so they're distinct from the h1 title;
        # the bundle CSS / DOCX reference doc size h1 (main) and h2 (section).
        parts.append(f"\n\n## {heading}\n\n{chosen_text}\n")
        included.append(heading)
        # e.g. the Abstract: keep it on its own page (page break after it).
        if section.get("page_break_after"):
            parts.append(f"\n\n{_PAGEBREAK_MARK}\n\n")
    return "\n".join(parts), included, missing_required, missing_optional, empty_present


def _render_pdf_weasyprint(markdown_text, output_path, logger):
    """Render combined Markdown -> PDF via markdown_to_html + WeasyPrint."""
    try:
        from weasyprint import HTML
    except ModuleNotFoundError:
        logger.error(
            "WeasyPrint is not installed; cannot render bundle PDF. "
            "Install it with `pip install weasyprint`."
        )
        return False
    try:
        md = markdown_text.replace(_PAGEBREAK_MARK, _PAGEBREAK_HTML)
        html_body = markdown_to_html(md)
        # If the markdown renderer HTML-escaped the raw div, restore it.
        html_body = html_body.replace(
            _PAGEBREAK_HTML.replace("<", "&lt;").replace(">", "&gt;"), _PAGEBREAK_HTML
        )
        html_doc = (
            "<html><head><meta charset='utf-8'>"
            f"<style>{BUNDLE_PDF_CSS}</style></head><body>"
            f"{html_body}</body></html>"
        )
        HTML(string=html_doc).write_pdf(str(output_path))
    except Exception as e:  # noqa: BLE001 — surface, don't leave a partial file
        logger.error("Bundle PDF rendering failed: %s", e, exc_info=True)
        if output_path.exists():
            output_path.unlink()
        return False
    logger.info("✓ Bundle PDF written: %s", output_path)
    return True


def _render_docx_pandoc(markdown_text, output_path, logger):
    """Render combined Markdown -> DOCX via pandoc (hardened subprocess)."""
    cmd = ["pandoc", "-f", "markdown", "-t", "docx"]
    if _BUNDLE_REFERENCE_DOCX.exists():
        cmd += ["--reference-doc", str(_BUNDLE_REFERENCE_DOCX)]  # reduced heading sizes
    cmd += ["-o", str(output_path)]
    md = markdown_text.replace(_PAGEBREAK_MARK, _PAGEBREAK_OPENXML)
    try:
        proc = subprocess.run(
            cmd,
            input=md,
            text=True,
            capture_output=True,
            timeout=PANDOC_TIMEOUT_SECONDS,
        )
    except FileNotFoundError:
        logger.error(
            "pandoc is not installed; cannot render bundle DOCX. "
            "Install it (e.g. `brew install pandoc`)."
        )
        return False
    except subprocess.TimeoutExpired:
        logger.error(
            "pandoc timed out after %ds rendering bundle DOCX.",
            PANDOC_TIMEOUT_SECONDS,
        )
        return False
    if proc.returncode != 0:
        logger.error(
            "pandoc failed (exit %d) rendering bundle DOCX: %s",
            proc.returncode, (proc.stderr or "").strip(),
        )
        # Don't leave a partial/empty file behind.
        if output_path.exists():
            output_path.unlink()
        return False
    logger.info("✓ Bundle DOCX written: %s", output_path)
    return True


def export_bundle(base_name, fmt="both", sections=None, logger=None):
    """Export a run's MD collection to DOCX and/or PDF.

    Purpose: Produce a single packaged document from the per-run Markdown files.
    Spec:    docs/spec_bundle_export_2026-07-16.md#BE.1

    Args:
        base_name: run base name (project dir under config.PROJECTS_DIR).
        fmt: "docx" | "pdf" | "both".
        sections: optional subset of config.BUNDLE_SECTIONS (post-run dialog).
    Returns True only if every requested format was produced. Fails closed on a
    release-gate BLOCK.
    """
    if logger is None:
        logger = setup_logging("export_bundle")

    fmt = (fmt or "both").lower()
    if fmt not in ("docx", "pdf", "both"):
        logger.error("export_bundle: invalid fmt %r (expected docx|pdf|both)", fmt)
        return False

    if sections is None:
        sections = config.BUNDLE_SECTIONS
    if not sections:
        logger.error("export_bundle: no sections selected.")
        return False

    if not release_gate.publish_allowed(base_name, logger):
        return False  # fail closed — no bundle on a BLOCK (parity with generate_pdf/package)

    markdown_text, included, missing_required, missing_optional, empty_present = (
        _build_combined_markdown(base_name, sections, logger)
    )

    total = len(sections)
    logger.info(
        "Bundle sections: %d of %d included%s",
        len(included), total,
        f"; skipped optional (absent): {', '.join(missing_optional)}" if missing_optional else "",
    )
    if empty_present:
        # P19: an artifact that exists but is empty is content drift, not content.
        logger.warning(
            "Bundle: %d section(s) present but EMPTY — excluded, not shipped blank: %s",
            len(empty_present), ", ".join(empty_present),
        )

    if missing_required:
        logger.error(
            "Bundle aborted — missing required section(s): %s",
            ", ".join(missing_required),
        )
        return False
    if not included:
        logger.error("Bundle aborted — no sections found to include.")
        return False

    proj = config.PROJECTS_DIR / base_name
    results = {}
    if fmt in ("pdf", "both"):
        results["PDF"] = _render_pdf_weasyprint(
            markdown_text, proj / f"{base_name}{config.SUFFIX_BUNDLE_PDF}", logger
        )
    if fmt in ("docx", "both"):
        results["DOCX"] = _render_docx_pandoc(
            markdown_text, proj / f"{base_name}{config.SUFFIX_BUNDLE_DOCX}", logger
        )

    succeeded = [f for f, r in results.items() if r]
    failed = [f for f, r in results.items() if not r]
    # Surface partial success (P2): don't let a written artifact read as a total
    # failure just because a sibling format failed.
    if succeeded and failed:
        logger.warning(
            "Bundle partial success: %s written, %s failed.",
            "/".join(succeeded), "/".join(failed),
        )
    # True only if every requested format was produced.
    return not failed
