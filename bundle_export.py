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
from transcript_utils import (
    markdown_to_html,
    setup_logging,
    strip_yaml_frontmatter,
)

# External-call hardening (P5): bound the pandoc subprocess.
PANDOC_TIMEOUT_SECONDS = 120


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
        suffix = getattr(config, section["suffix_attr"])
        heading = section["heading"]
        required = bool(section.get("required"))
        path = proj / f"{base_name}{suffix}"
        if not path.exists():
            (missing_required if required else missing_optional).append(heading)
            continue
        text = path.read_text(encoding="utf-8")
        if section.get("strip_frontmatter"):
            text = strip_yaml_frontmatter(text)
        text = text.strip()
        if not text:
            empty_present.append(heading)
            if required:
                missing_required.append(heading)
            continue
        parts.append(f"\n\n# {heading}\n\n{text}\n")
        included.append(heading)
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
        html_body = markdown_to_html(markdown_text)
        html_doc = (
            "<html><head><meta charset='utf-8'></head><body>"
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
    try:
        proc = subprocess.run(
            ["pandoc", "-f", "markdown", "-t", "docx", "-o", str(output_path)],
            input=markdown_text,
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
    ok = True
    if fmt in ("pdf", "both"):
        ok = _render_pdf_weasyprint(
            markdown_text, proj / f"{base_name}{config.SUFFIX_BUNDLE_PDF}", logger
        ) and ok
    if fmt in ("docx", "both"):
        ok = _render_docx_pandoc(
            markdown_text, proj / f"{base_name}{config.SUFFIX_BUNDLE_DOCX}", logger
        ) and ok
    return ok
