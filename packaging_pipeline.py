"""
Pipeline module for packaging final artifacts.
"""

import zipfile

import config
from transcript_utils import setup_logging


def package_transcript(base_name: str, logger=None) -> bool:
    """
    Package final artifacts (HTML, PDF, Transcript) into a zip file.
    """
    if logger is None:
        logger = setup_logging("package_transcript")

    try:
        files_to_package = []

        project_dir = config.PROJECTS_DIR / base_name

        # 1. Main Webpage
        webpage = project_dir / f"{base_name}{config.SUFFIX_WEBPAGE}"
        if webpage.exists():
            files_to_package.append(webpage)
        else:
            logger.warning(f"Main webpage not found: {webpage}")

        # 2. Simple Webpage
        simple_webpage = project_dir / f"{base_name}{config.SUFFIX_WEBPAGE_SIMPLE}"
        if simple_webpage.exists():
            files_to_package.append(simple_webpage)

        # 3. PDF
        pdf = project_dir / f"{base_name}{config.SUFFIX_PDF}"
        if pdf.exists():
            files_to_package.append(pdf)

        # 4. Processed Transcript (YAML or Formatted)
        yaml_transcript = project_dir / f"{base_name}{config.SUFFIX_YAML}"
        formatted_transcript = project_dir / f"{base_name}{config.SUFFIX_FORMATTED}"

        if yaml_transcript.exists():
            files_to_package.append(yaml_transcript)
        elif formatted_transcript.exists():
            files_to_package.append(formatted_transcript)

        if not files_to_package:
            logger.error("No files found to package.")
            return False

        # Package stays in the project dir
        zip_filename = project_dir / f"{base_name}.zip"

        logger.info(f"Creating package: {zip_filename}")
        with zipfile.ZipFile(zip_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
            for file_path in files_to_package:
                logger.info(f"  Adding: {file_path.name}")
                zipf.write(file_path, arcname=file_path.name)

        logger.info(f"✓ Package created successfully: {zip_filename}")
        return True

    except Exception as e:
        logger.error(f"Error packaging transcript: {e}", exc_info=True)
        return False
