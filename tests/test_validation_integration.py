import unittest
from unittest.mock import MagicMock, patch
import json
from pathlib import Path
import tempfile
import shutil
import os
import sys

# Ensure project root is in path
sys.path.append(os.getcwd())

import config
from transcript_initial_validation_v2 import TranscriptValidatorV2

class TestValidationIntegration(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.api_key = "dummy_key"
        self.logger = MagicMock()
        self.validator = TranscriptValidatorV2(self.api_key, self.logger)
        
        # Create a sample transcript
        self.transcript_path = Path(self.test_dir) / "sample_integration.txt"
        self.content = (
            "This is a sampl transcript with a few errors. "
            "We want to check if the validater can find them. "
            "The Bowen theory is very interesting."
        )
        with open(self.transcript_path, 'w') as f:
            f.write(self.content)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch('transcript_utils.call_claude_with_retry')
    def test_full_pipeline_mocked(self, mock_call_claude):
        """
        Simulate a full run of validate_chunked -> detect_hallucinations -> apply_corrections.
        """
        # Setup Mock Response
        # We expect 2 chunks roughly given the small size? No, it's 3 sentences. 
        # But let's assume it all fits in one chunk.
        
        mock_findings = [
            {
                "error_type": "spelling",
                "original_text": "sampl transcript",
                "suggested_correction": "sample transcript",
                "confidence": "high",
                "reasoning": "Spelling error"
            },
            {
                "error_type": "spelling",
                "original_text": "validater",
                "suggested_correction": "validator",
                "confidence": "high",
                "reasoning": "Spelling error"
            },
            {
                "error_type": "spelling",
                "original_text": "interesting",
                "suggested_correction": "interesting",
                "confidence": "medium",
                "reasoning": "Spelling error"
            }
        ]
        
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text=json.dumps(mock_findings))]
        mock_message.usage = MagicMock(input_tokens=100, output_tokens=50)
        mock_call_claude.return_value = mock_message

        # 1. Run Validation
        # NOTE: config.VALIDATION_CHUNK_SIZE is likely 3000, so this will be 1 chunk.
        valid_findings = self.validator.validate_chunked(self.transcript_path)
        
        self.assertEqual(len(valid_findings), 3)
        self.assertEqual(valid_findings[0]['suggested_correction'], "sample transcript")

        # 2. Filter (Simulate Logic in run_iterative_validation)
        to_apply = [f for f in valid_findings if f['confidence'] in config.VALIDATION_AUTO_APPLY_CONFIDENCE]
        self.assertEqual(len(to_apply), 2) # Only High is auto-apply in updated V2 config (Medium is review)

        # 3. Apply Corrections
        output_path = self.transcript_path.parent / "sample_integration_v1.txt"
        final_path, applied_count, skipped = self.validator.apply_corrections_safe(
            self.transcript_path, to_apply, output_path
        )

        self.assertEqual(applied_count, 2)
        self.assertEqual(len(skipped), 0)

        # 4. Verify File Content
        with open(final_path, 'r') as f:
            new_content = f.read()
        
        # 'interesting' should NOT be replaced (it was medium confidence)
        # 'sampl' -> 'sample', 'validater' -> 'validator'
        expected_content = (
            "This is a sample transcript with a few errors. "
            "We want to check if the validator can find them. "
            "The Bowen theory is very interesting."
        )
        self.assertEqual(new_content, expected_content)
        
        # 5. Verify Metrics
        summary = self.validator.metrics.calculate_summary()
        self.assertEqual(summary['total_corrections_applied'], 0) # apply_corrections_safe doesn't auto-update metrics unless run via run_iterative
        
        # Manually update metrics to simulate pipeline
        self.validator.metrics.corrections_applied += applied_count
        summary = self.validator.metrics.calculate_summary()
        self.assertEqual(summary['total_corrections_applied'], 2)

    @patch('transcript_utils.call_claude_with_retry')
    def test_chunking_logic(self, mock_call_claude):
        """Test that a long file is actually chunked."""
        # Create a file longer than VALIDATION_CHUNK_SIZE (3000 words)
        # We'll create a smaller chunk size for testing by patching config
        
        with patch('config.VALIDATION_CHUNK_SIZE', 10):
            with patch('config.VALIDATION_CHUNK_OVERLAP', 2):
                long_content = "word " * 25 # 25 words. Chunks: 0-10, 8-18, 16-25 (roughly)
                long_path = Path(self.test_dir) / "long.txt"
                with open(long_path, 'w') as f:
                    f.write(long_content)
                    
                mock_message = MagicMock()
                mock_message.content = [MagicMock(text="[]")] # Return no errors
                mock_message.usage = MagicMock(input_tokens=10, output_tokens=10)
                mock_call_claude.return_value = mock_message
                
                self.validator.validate_chunked(long_path)
                
                # Check how many times API was called
                # 25 words total. Chunk 10. Overlap 2.
                # 1: 0-10
                # 2: 8-18
                # 3: 16-25 (9 words < 30% of 10? No, 90%. So it runs)
                # Actually logic says: if (total - end) < (chunk_size * 0.3): extend.
                # 1: 0-10. Remaining 15. > 3. Next start 8.
                # 2: 8-18. Remaining 7. > 3. Next start 16.
                # 3: 16-26. End=25.
                # Expect 3 calls.
                
                self.assertEqual(mock_call_claude.call_count, 3)

    @patch('transcript_utils.call_claude_with_retry')
    def test_run_iterative_validation_v2_flow(self, mock_call_claude):
        """Test the full iterative loop including parameter passing."""
        # Setup Mock to return empty findings to cause immediate convergence (1 iteration)
        mock_message = MagicMock()
        mock_message.content = [MagicMock(text="[]")] 
        
        # Configure usage mock with explicit integers
        mock_usage = MagicMock()
        mock_usage.input_tokens = 10
        mock_usage.output_tokens = 10
        mock_usage.cache_creation_input_tokens = 0
        mock_usage.cache_read_input_tokens = 0
        mock_message.usage = mock_usage
        
        mock_call_claude.return_value = mock_message
        
        result = self.validator.run_iterative_validation_v2(
            self.transcript_path, 
            max_iterations=1, 
            model="dummy-model"
        )
        
        # Verify result structure
        self.assertIn('metrics', result)
        self.assertIn('total_cost', result['metrics'])
        self.assertEqual(result['metrics']['model_used'], "dummy-model")
        
        # Verify model was passed to API
        call_args = mock_call_claude.call_args
        self.assertEqual(call_args.kwargs['model'], "dummy-model")

if __name__ == '__main__':
    unittest.main()
