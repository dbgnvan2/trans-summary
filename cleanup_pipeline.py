"""
Pipeline module for cleaning up source and intermediate files.
"""

import shutil
import re
from pathlib import Path
import config
from transcript_utils import setup_logging

def move_to_processed(file_path: Path, processed_dir: Path, logger=None) -> Path:
    """
    Move a file to the processed directory, handling naming conflicts.
    """
    if not file_path.exists():
        if logger:
            logger.warning(f"File to move not found: {file_path}")
        return None

    dest_path = processed_dir / file_path.name
    
    # Handle duplicates by appending counter
    counter = 1
    stem = dest_path.stem
    suffix = dest_path.suffix
    while dest_path.exists():
        dest_path = processed_dir / f"{stem}_{counter}{suffix}"
        counter += 1
        
    try:
        shutil.move(str(file_path), str(dest_path))
        if logger:
            logger.info(f"Moved {file_path.name} -> {dest_path.name}")
        return dest_path
    except Exception as e:
        if logger:
            logger.error(f"Failed to move {file_path.name}: {e}")
        return None

def cleanup_transcript_files(base_name: str, logger=None) -> bool:
    """
    Clean up source directory for a given transcript base name.
    
    1. Move original source file to processed/
    2. Move final validated file to processed/
    3. Delete intermediate version files (_v1, _v2...)
    """
    if logger is None:
        logger = setup_logging('cleanup_transcript')
        
    source_dir = config.SOURCE_DIR
    processed_dir = config.PROCESSED_DIR
    processed_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Starting cleanup for: {base_name}")
    
    # 1. Identify files
    # Original file pattern: "Title - Presenter - Date.txt"
    original_file = source_dir / f"{base_name}.txt"
    
    # Validated file pattern: "Title - Presenter - Date_validated.txt"
    validated_file = source_dir / f"{base_name}_validated.txt"
    
    # Intermediate files pattern: "Title..._vN.txt"
    # We use glob to find them
    # Escape glob special characters in base_name if any (brackets etc)
    # Using simple iteration is safer than complex globs if filenames have special chars
    
    intermediate_files = []
    for f in source_dir.glob(f"*.txt"):
        if f.name.startswith(base_name):
            # Check for _vN pattern
            if re.search(r'_v\d+\.txt$', f.name):
                intermediate_files.append(f)
    
    # 2. Move critical files
    moved_count = 0
    if original_file.exists():
        if move_to_processed(original_file, processed_dir, logger):
            moved_count += 1
    else:
        logger.warning(f"Original source file not found: {original_file.name}")

    if validated_file.exists():
        if move_to_processed(validated_file, processed_dir, logger):
            moved_count += 1
    else:
        logger.info(f"No validated file found to move.")

    # 3. Delete intermediate files
    deleted_count = 0
    for f in intermediate_files:
        try:
            f.unlink()
            logger.info(f"Deleted intermediate file: {f.name}")
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete {f.name}: {e}")

    logger.info(f"Cleanup complete. Moved {moved_count} files, deleted {deleted_count} files.")
    return True