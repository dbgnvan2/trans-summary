"""
Pipeline module for packaging final artifacts.
"""

import zipfile

import config
import release_gate
from transcript_utils import base_name_is_safe, setup_logging


def package_transcript(base_name: str, logger=None) -> bool:
    """
    Package final artifacts (HTML, PDF, Transcript) into a zip file.
    """
    if logger is None:
        logger = setup_logging('package_transcript')

    if not base_name_is_safe(base_name):
        logger.error("Refusing unsafe base_name (path-traversal guard): %r", base_name)
        return False

    if not release_gate.publish_allowed(base_name, logger):
        return False  # M1.B.2 — fail closed: no zip bundle on a BLOCK

    try:
        files_to_package = []

        project_dir = config.PROJECTS_DIR / base_name

        # 1. Main Webpage
        webpage = project_dir / f"{base_name}{config.SUFFIX_WEBPAGE}"
        if webpage.exists():
            files_to_package.append(webpage)
        else:
            logger.warning("Main webpage not found: %s", webpage)

        # 2. Simple Webpage
        simple_webpage = project_dir / \
            f"{base_name}{config.SUFFIX_WEBPAGE_SIMPLE}"
        if simple_webpage.exists():
            # A simple page older than the files it is built from is from an
            # earlier run; shipping it next to a fresh full page would pass old
            # content off as current (RF.E sweep finding).
            newer = [p for p in (
                project_dir / f"{base_name}{config.SUFFIX_WEBPAGE}",
                project_dir / f"{base_name}{config.SUFFIX_YAML}",
                project_dir / f"{base_name}{config.SUFFIX_FORMATTED}")
                if p.exists() and p.stat().st_mtime > simple_webpage.stat().st_mtime]
            if newer:
                logger.warning(
                    "Simple webpage not packaged: older than %s. Run '8b. Simple Web' "
                    "to rebuild it.", newer[0].name)
            else:
                files_to_package.append(simple_webpage)

        # 3. PDF
        pdf = project_dir / f"{base_name}{config.SUFFIX_PDF}"
        if pdf.exists():
            files_to_package.append(pdf)

        # 4. Processed Transcript (YAML or Formatted)
        yaml_transcript = project_dir / \
            f"{base_name}{config.SUFFIX_YAML}"
        formatted_transcript = project_dir / \
            f"{base_name}{config.SUFFIX_FORMATTED}"

        if yaml_transcript.exists():
            files_to_package.append(yaml_transcript)
        elif formatted_transcript.exists():
            files_to_package.append(formatted_transcript)

        if not files_to_package:
            logger.error("No files found to package.")
            return False

        # Package stays in the project dir
        zip_filename = project_dir / f"{base_name}.zip"

        logger.info("Creating package: %s", zip_filename)
        with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in files_to_package:
                logger.info("  Adding: %s", file_path.name)
                zipf.write(file_path, arcname=file_path.name)

        logger.info("✓ Package created successfully: %s", zip_filename)
        return True

    except Exception as e:
        logger.error("Error packaging transcript: %s", e, exc_info=True)
        return False
