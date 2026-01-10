import unittest
import sys
import os

# Ensure project root is in path
sys.path.append(os.getcwd())

import summary_validation
import abstract_validation

class MockInput:
    """Mock input object for validation functions."""
    def __init__(self, target_word_count=500):
        self.target_word_count = target_word_count
        # Minimal attributes required for coverage validation (mocking as passed)
        self.metadata = {"speaker": "Dr. Test"}
        self.opening = type('obj', (object,), {'stated_purpose': 'Purpose', 'word_allocation': 50})
        self.body = type('obj', (object,), {'topics': [], 'word_allocation': 300})
        self.qa = type('obj', (object,), {'include': False, 'percentage': 0, 'word_allocation': 0})
        self.closing = type('obj', (object,), {'conclusion': 'Conclusion', 'word_allocation': 50})
        # For Abstract
        self.topics = []
        self.themes = []
        self.opening_purpose = "Purpose"
        self.closing_conclusion = "Conclusion"
        self.qa_percentage = 0
        self.qa_topics = []

class TestValidationWarnings(unittest.TestCase):

    def test_summary_too_long_warning(self):
        """Test that a summary exceeding max length passes with a warning."""
        target_count = 100
        # Create a summary that is definitely too long (> 1.2 * 100 = 120 words)
        # 150 words
        long_summary = "word " * 150
        
        # Valid structure (3 paragraphs) to avoid other errors
        long_summary = f"{'word ' * 50}\n\n{'word ' * 50}\n\n{'word ' * 50}"

        structural = summary_validation.validate_structural(long_summary, target_count)
        
        # Should be valid (no fatal errors)
        self.assertTrue(structural['valid'], "Summary should pass structural validation despite length")
        
        # Should have 0 fatal issues
        self.assertEqual(len(structural['issues']), 0)
        
        # Should have at least 1 warning about length
        self.assertTrue(any("Too long" in w for w in structural['warnings']),
                        f"Expected length warning, got: {structural['warnings']}")

        def test_summary_evaluative_warning(self):
            """Test that a summary with evaluative language passes with a warning."""
            # "excellent" is in config.EVALUATIVE_TERMS
            summary = "This is an excellent point.\n\nNext paragraph.\n\nFinal paragraph."
            target_count = 10  # Low count, but length is just a warning now
            
            structural = summary_validation.validate_structural(summary, target_count)
            
            self.assertTrue(structural['valid'], "Summary should pass despite evaluative language")
            self.assertTrue(any("Evaluative language check" in w for w in structural['warnings']),
                            f"Expected evaluative warning, got: {structural['warnings']}")
    def test_summary_fatal_error(self):
        """Test that a summary with prohibited content still fails."""
        # "Section 1" is prohibited
        summary = "Section 1 says hello.\n\nPara 2.\n\nPara 3."
        target_count = 10
        
        structural = summary_validation.validate_structural(summary, target_count)
        
        self.assertFalse(structural['valid'], "Summary should FAIL due to section reference")
        self.assertTrue(any("Contains section references" in i for i in structural['issues']),
                        f"Expected fatal issue, got: {structural['issues']}")

    def test_abstract_too_long_warning(self):
        """Test that an abstract exceeding max length passes with a warning."""
        target_count = 100
        # 150 words
        long_abstract = "word " * 150
        
        structural = abstract_validation.validate_structural(long_abstract, target_count)
        
        self.assertTrue(structural['valid'], "Abstract should pass structural validation despite length")
        self.assertEqual(len(structural['issues']), 0)
        self.assertTrue(any("Too long" in w for w in structural['warnings']),
                        f"Expected length warning, got: {structural['warnings']}")

    def test_abstract_evaluative_warning(self):
        """Test that an abstract with evaluative language passes with a warning."""
        abstract = "This is an excellent abstract."
        target_count = 10
        
        structural = abstract_validation.validate_structural(abstract, target_count)
        
        self.assertTrue(structural['valid'], "Abstract should pass despite evaluative language")
        self.assertTrue(any("Evaluative language check" in w for w in structural['warnings']),
                        f"Expected evaluative warning, got: {structural['warnings']}")

    def test_summary_proportionality_warning(self):
        """Test that a summary with bad proportionality passes with a warning."""
        # Mock inputs
        class MockObj:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)
                
        mock_input = MockInput(target_word_count=100)
        # Force a proportionality mismatch by having sections but mismatched word counts
        # We need to mock the structure expected by check_proportionality
        
        # Instead of mocking deeply nested internals, let's use the validate_summary_coverage directly 
        # but with a summary that we know will fail proportionality but pass coverage.
        
        # Actually, it's easier to mock check_proportionality's return value since we're testing validate_summary_coverage logic
        with unittest.mock.patch('summary_validation.check_proportionality') as mock_prop:
            mock_prop.return_value = {
                "proportionality_ok": False,
                "total_words": 100,
                "target_words": 100,
                "total_deviation": 0,
                "sections": [{"within_tolerance": False, "deviation": 0.9, "name": "Body", "expected": 50, "actual": 100}]
            }
            
            # Use a mock summary text
            summary = "Summary text."
            
            # Mock generate_coverage_items to return all covered items so coverage passes
            with unittest.mock.patch('summary_validation.generate_coverage_items') as mock_items:
                # Create a covered required item
                item = summary_validation.CoverageItem("cat", "Label", True, [], "src", 10)
                item.covered = True
                mock_items.return_value = [item]
                
                result = summary_validation.validate_summary_coverage(summary, mock_input)
                
                self.assertTrue(result['passed'], "Summary should pass despite proportionality failure")
                self.assertFalse(result['proportionality_passed'], "Proportionality should be False")
                self.assertIn("proportionality deviations", result['summary'])

if __name__ == '__main__':
    unittest.main()
