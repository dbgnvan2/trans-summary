import unittest
from unittest.mock import MagicMock, patch
import shutil
from pathlib import Path
import tempfile
import os
import sys

# Ensure project root is in path
sys.path.append(os.getcwd())

import cleanup_pipeline

class TestCleanupPipeline(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory structure
        self.test_dir = tempfile.mkdtemp()
        self.source_dir = Path(self.test_dir) / "source"
        self.processed_dir = Path(self.test_dir) / "processed"
        self.source_dir.mkdir()
        self.processed_dir.mkdir()
        
        self.base_name = "Test Title - Dr Test - 2025-01-01"
        self.logger = MagicMock()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch('config.SOURCE_DIR')
    @patch('config.PROCESSED_DIR')
    def test_cleanup_standard_flow(self, mock_processed, mock_source):
        """Test moving original/validated and deleting versions."""
        mock_source.__truediv__.side_effect = lambda x: self.source_dir / x
        mock_source.glob.side_effect = self.source_dir.glob
        mock_processed.__truediv__.side_effect = lambda x: self.processed_dir / x
        mock_processed.mkdir.return_value = None # processed dir already exists in setup

        # Create files
        original = self.source_dir / f"{self.base_name}.txt"
        validated = self.source_dir / f"{self.base_name}_validated.txt"
        v1 = self.source_dir / f"{self.base_name}_v1.txt"
        v2 = self.source_dir / f"{self.base_name}_v2.txt"
        unrelated = self.source_dir / "Unrelated File.txt"

        for f in [original, validated, v1, v2, unrelated]:
            f.touch()

        # Run cleanup
        cleanup_pipeline.cleanup_transcript_files(self.base_name, logger=self.logger)

        # Check moves
        self.assertFalse(original.exists(), "Original file should be moved")
        self.assertFalse(validated.exists(), "Validated file should be moved")
        self.assertTrue((self.processed_dir / original.name).exists(), "Original should be in processed")
        self.assertTrue((self.processed_dir / validated.name).exists(), "Validated should be in processed")

        # Check deletes
        self.assertFalse(v1.exists(), "v1 should be deleted")
        self.assertFalse(v2.exists(), "v2 should be deleted")

        # Check ignored
        self.assertTrue(unrelated.exists(), "Unrelated file should not be touched")

    @patch('config.SOURCE_DIR')
    @patch('config.PROCESSED_DIR')
    def test_cleanup_naming_conflict(self, mock_processed, mock_source):
        """Test handling of duplicate filenames in processed dir."""
        mock_source.__truediv__.side_effect = lambda x: self.source_dir / x
        mock_processed.__truediv__.side_effect = lambda x: self.processed_dir / x
        
        # Setup source
        original = self.source_dir / f"{self.base_name}.txt"
        original.touch()
        
        # Setup existing conflict in processed
        conflict = self.processed_dir / f"{self.base_name}.txt"
        conflict.touch()
        
        cleanup_pipeline.cleanup_transcript_files(self.base_name, logger=self.logger)
        
        # Should have moved to _1
        renamed = self.processed_dir / f"{self.base_name}_1.txt"
        self.assertTrue(renamed.exists(), "File should be renamed on conflict")
        self.assertTrue(conflict.exists(), "Existing file should stay")
        self.assertFalse(original.exists(), "Source file should be gone")

    @patch('config.SOURCE_DIR')
    @patch('config.PROCESSED_DIR')
    def test_cleanup_missing_files(self, mock_processed, mock_source):
        """Test cleanup when some expected files are missing."""
        mock_source.__truediv__.side_effect = lambda x: self.source_dir / x
        mock_source.glob.side_effect = self.source_dir.glob
        
        # Only v1 exists, no original or validated
        v1 = self.source_dir / f"{self.base_name}_v1.txt"
        v1.touch()
        
        cleanup_pipeline.cleanup_transcript_files(self.base_name, logger=self.logger)
        
        self.assertFalse(v1.exists(), "v1 should still be deleted")
        # Should not crash

if __name__ == '__main__':
    unittest.main()
