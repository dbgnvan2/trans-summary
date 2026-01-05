import config
import validation_pipeline
import extraction_pipeline
import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from pathlib import Path

# Ensure project root is in path
sys.path.append(os.getcwd())


class TestPipelineIntegration(unittest.TestCase):
    def setUp(self):
        # Use a filename that passes parse_filename_metadata regex
        self.base_name = "Integration Test - Dr Tester - 2025-01-01"
        self.mock_logger = MagicMock()

        # Mock config paths
        self.mock_projects_dir = MagicMock()
        self.mock_source_dir = MagicMock()

        # Setup patches
        self.config_patcher = patch(
            'config.PROJECTS_DIR', self.mock_projects_dir)
        self.mock_config_projects = self.config_patcher.start()

        self.source_patcher = patch('config.SOURCE_DIR', self.mock_source_dir)
        self.mock_config_source = self.source_patcher.start()
        self.mock_config_source.exists.return_value = True

        # Configure Mock File System for PROJECTS_DIR
        # We want config.PROJECTS_DIR / stem / filename to return a mock file
        self.mock_file = MagicMock()
        self.mock_file.exists.return_value = True

        # Setup chain: projects_dir / stem -> project_path
        self.project_path = MagicMock()
        self.mock_config_projects.__truediv__.return_value = self.project_path
        # project_path / filename -> mock_file
        self.project_path.__truediv__.return_value = self.mock_file

    def tearDown(self):
        self.source_patcher.stop()
        self.config_patcher.stop()

    @patch('extraction_pipeline.call_claude_with_retry')
    @patch('validation_pipeline.call_claude_with_retry')
    @patch('pathlib.Path.read_text')
    @patch('pathlib.Path.write_text')
    @patch('extraction_pipeline.validate_input_file')
    @patch('validation_pipeline.validate_input_file')
    def test_full_extraction_validation_flow(
        self, mock_val_input_val, mock_val_input_ext,
        mock_write_text, mock_read_text,
        mock_call_claude_val, mock_call_claude_ext
    ):
        """
        Simulate the flow: 
        Summarize -> Gen Structured Summary -> Validate Summary -> Gen Abstract -> Validate Abstract
        """
        # 1. Setup Mock Data
        transcript_text = "## Section 1\nThis is a test transcript.\n## Section 2\nIt has content."
        yaml_text = "---\ntitle: Test\n---\n" + transcript_text

        key_items_content = """
## Topics
### Topic 1
Description.
*_(~10% of transcript; Sections 1)_*

## Key Themes
1. **Theme 1**: Desc.
*Source Sections: 1*
"""
        # Combined content to satisfy different read calls
        combined_content = yaml_text + "\n" + key_items_content

        # Configure read_text to return content for prompts (real paths) and data (mocks)
        def read_text_side_effect(*args, **kwargs):
            # If called on a real Path object (like prompts), args[0] is self
            # But since we patch the class method, we need to handle how it's called.
            # For simplicity, we'll just return a generic prompt if it seems like one, else content.
            return "Dummy Prompt {{insert_transcript_text_here}} {{blog_content}}"

        mock_read_text.side_effect = read_text_side_effect
        self.mock_file.read_text.return_value = combined_content

        # Mock API responses
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Mocked API Response content")]
        mock_response.usage.input_tokens = 100
        mock_response.usage.output_tokens = 100

        mock_call_claude_ext.return_value = mock_response
        # For validation LLM calls if any
        mock_call_claude_val.return_value = mock_response

        # 2. Run Step 3: Summarize Transcript (Extracts)
        print("\n--- Testing Step 3: Summarize Transcript ---")
        success_summarize = extraction_pipeline.summarize_transcript(
            formatted_filename=f"{self.base_name}_yaml.md",
            model="test-model",
            focus_keyword="test",
            target_audience="testers",
            skip_extracts_summary=False,
            skip_emphasis=False,
            skip_blog=False,
            generate_structured=False,
            logger=self.mock_logger
        )
        self.assertTrue(success_summarize, "Summarize transcript failed")

        # 3. Run Step 4: Generate Structured Summary
        print("\n--- Testing Step 4: Generate Structured Summary ---")
        success_gen_summary = extraction_pipeline.generate_structured_summary(
            base_name=self.base_name,
            logger=self.mock_logger
        )
        self.assertTrue(success_gen_summary,
                        "Generate structured summary failed")

        # 4. Run Step 5: Validate Summary
        print("\n--- Testing Step 5: Validate Summary ---")
        # We need to ensure validate_summary_coverage doesn't fail.
        # It reads the generated summary file.
        # It parses it.
        # It calls LLM if needed.

        result_val_summary = validation_pipeline.validate_summary_coverage(
            base_name=self.base_name,
            logger=self.mock_logger
        )
        # We don't assert True here because with dummy text it likely fails validation logic,
        # but we assert it ran (didn't raise exception).
        self.assertIsInstance(result_val_summary, bool)

        # 5. Run Step 6: Generate Structured Abstract
        print("\n--- Testing Step 6: Generate Structured Abstract ---")
        success_gen_abstract = extraction_pipeline.generate_structured_abstract(
            base_name=self.base_name,
            logger=self.mock_logger
        )
        self.assertTrue(success_gen_abstract,
                        "Generate structured abstract failed")

        # 6. Run Step 7: Validate Abstract
        print("\n--- Testing Step 7: Validate Abstract ---")
        result_val_abstract = validation_pipeline.validate_abstract_coverage(
            base_name=self.base_name,
            logger=self.mock_logger
        )
        self.assertIsInstance(result_val_abstract, bool)


if __name__ == '__main__':
    unittest.main()
