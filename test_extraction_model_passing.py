import extraction_pipeline
import unittest
from unittest.mock import MagicMock, patch
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())


class TestExtractionModelPassing(unittest.TestCase):
    def setUp(self):
        self.base_name = "Test_Transcript"
        self.test_model = "test-model-v1"
        self.mock_logger = MagicMock()

    @patch('extraction_pipeline.summary_pipeline.generate_summary')
    @patch('extraction_pipeline.summary_pipeline.prepare_summary_input')
    @patch('extraction_pipeline.extract_section')
    @patch('extraction_pipeline.strip_yaml_frontmatter')
    @patch('extraction_pipeline.validate_input_file')
    @patch('extraction_pipeline.parse_filename_metadata')
    @patch('extraction_pipeline.config.PROJECTS_DIR')
    @patch('extraction_pipeline.anthropic.Anthropic')
    @patch('os.getenv')
    def test_generate_structured_summary_passes_model(
        self, mock_getenv, mock_anthropic, mock_projects_dir,
        mock_parse_metadata, mock_validate, mock_strip_yaml,
        mock_extract_section, mock_prepare_input, mock_generate_summary
    ):
        # Setup mocks
        mock_getenv.return_value = "fake-key"
        mock_parse_metadata.return_value = {"stem": self.base_name}

        # Mock file operations
        mock_file = MagicMock()
        mock_file.read_text.return_value = "fake content"
        # When config.PROJECTS_DIR / base_name / filename is called
        mock_projects_dir.__truediv__.return_value.__truediv__.return_value = mock_file

        mock_strip_yaml.return_value = "cleaned content"
        mock_extract_section.return_value = "section content"

        # Run function
        extraction_pipeline.generate_structured_summary(
            self.base_name,
            logger=self.mock_logger,
            model=self.test_model
        )

        # Verify model passed to generate_summary
        self.assertTrue(mock_generate_summary.called)
        call_kwargs = mock_generate_summary.call_args.kwargs
        self.assertEqual(call_kwargs.get('model'), self.test_model)

    @patch('extraction_pipeline.abstract_pipeline.generate_abstract')
    @patch('extraction_pipeline.abstract_pipeline.prepare_abstract_input')
    @patch('extraction_pipeline.extract_section')
    @patch('extraction_pipeline.strip_yaml_frontmatter')
    @patch('extraction_pipeline.validate_input_file')
    @patch('extraction_pipeline.parse_filename_metadata')
    @patch('extraction_pipeline.config.PROJECTS_DIR')
    @patch('extraction_pipeline.anthropic.Anthropic')
    @patch('os.getenv')
    def test_generate_structured_abstract_passes_model(
        self, mock_getenv, mock_anthropic, mock_projects_dir,
        mock_parse_metadata, mock_validate, mock_strip_yaml,
        mock_extract_section, mock_prepare_input, mock_generate_abstract
    ):
        # Setup mocks
        mock_getenv.return_value = "fake-key"
        mock_parse_metadata.return_value = {"stem": self.base_name}

        mock_file = MagicMock()
        mock_file.read_text.return_value = "fake content"
        mock_projects_dir.__truediv__.return_value.__truediv__.return_value = mock_file

        mock_strip_yaml.return_value = "cleaned content"
        # We need extract_section to return something for Topics and Key Themes
        mock_extract_section.return_value = "section content"

        # Mock abstract input to have topics (required check in pipeline)
        mock_input = MagicMock()
        mock_input.topics = ["Topic 1"]
        mock_prepare_input.return_value = mock_input

        # Run function
        extraction_pipeline.generate_structured_abstract(
            self.base_name,
            logger=self.mock_logger,
            model=self.test_model
        )

        # Verify model passed to generate_abstract
        self.assertTrue(mock_generate_abstract.called)
        call_kwargs = mock_generate_abstract.call_args.kwargs
        self.assertEqual(call_kwargs.get('model'), self.test_model)


if __name__ == '__main__':
    unittest.main()
