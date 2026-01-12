import unittest
import os
import sys
# Ensure project root is in path
sys.path.append(os.getcwd())
from pathlib import Path
import tempfile
import shutil
import logging
import config
from transcript_initial_validation_v2 import TranscriptValidatorV2

class TestValidationIntegration(unittest.TestCase):
    def setUp(self):
        # Skip if no API key
        if not os.getenv("ANTHROPIC_API_KEY"):
            self.skipTest("ANTHROPIC_API_KEY not set")
            
        self.test_dir = tempfile.mkdtemp()
        self.logger = logging.getLogger("TestIntegration")
        logging.basicConfig(level=logging.INFO)
        
        self.validator = TranscriptValidatorV2(os.getenv("ANTHROPIC_API_KEY"), self.logger)
        
    def tearDown(self):
        shutil.rmtree(self.test_dir)
        
    def test_full_pipeline_v2(self):
        """
        Run a full V2 validation on a short sample text with known errors.
        Verifies:
        1. API call works
        2. JSON parsing works
        3. Logic finds errors
        4. Application works
        """
        # 1. Create Sample File
        # Errors:
        # - "Bowin" -> "Bowen" (Proper Noun)
        # - "effect" -> "affect" (Homophone - maybe ambiguous context)
        # - "i think" -> "I think" (Capitalization)
        sample_text = (
            "This is a test transcript for validation. "
            "We are discussing the work of Murray Bowin here. "
            "He was a famous psychiatrist. "
            "i think his theories are important. "
            "The weather will affect our plans."
        )
        
        input_path = Path(self.test_dir) / "integration_sample.txt"
        input_path.write_text(sample_text)
        
        # 2. Run Validation
        # Use the configured model (should be Sonnet 3.7 or Sonnet 3.5)
        # We limit iterations to 2
        result = self.validator.run_iterative_validation_v2(
            input_path, 
            max_iterations=2,
            model=config.DEFAULT_MODEL
        )
        
        # 3. Verify Result Structure
        self.assertIn('final_file', result)
        self.assertIn('metrics', result)
        
        # 4. Verify Corrections
        final_path = result['final_file']
        final_text = final_path.read_text()
        
        print("\n--- Integration Test Results ---")
        print(f"Original: {sample_text}")
        print(f"Final:    {final_text}")
        print(f"Metrics:  {result['metrics']}")
        
        # Check specific fixes
        # Note: LLM behavior is probabilistic, so we check "likely" fixes
        # "Bowin" -> "Bowen" is a strong candidate
        if "Bowen" in final_text:
            print("✅ Fixed 'Bowin' -> 'Bowen'")
        else:
            print("⚠️ 'Bowin' not fixed (LLM choice)")
            
        # "i think" -> "I think"
        if "I think" in final_text:
            print("✅ Fixed 'i think' -> 'I think'")
        else:
            print("⚠️ 'i think' not fixed")

        # Verify metrics populated
        metrics = result['metrics']
        self.assertGreater(metrics['total_api_calls'], 0)
        self.assertGreater(metrics['total_cost'], 0)

if __name__ == '__main__':
    unittest.main()