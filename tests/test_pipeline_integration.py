import inspect
import unittest

import pipeline


class TestPipelineIntegration(unittest.TestCase):

    def test_pipeline_exports_html_generator_functions(self):
        """Verify that pipeline.py re-exports the functions moved to html_generator.py."""
        self.assertTrue(hasattr(pipeline, "generate_webpage"), "pipeline.generate_webpage missing")
        self.assertTrue(hasattr(pipeline, "generate_simple_webpage"), (
            "pipeline.generate_simple_webpage missing"
        ))
        self.assertTrue(hasattr(pipeline, "generate_pdf"), "pipeline.generate_pdf missing")

        # verify they are functions
        self.assertTrue(inspect.isfunction(pipeline.generate_webpage))
        self.assertTrue(inspect.isfunction(pipeline.generate_simple_webpage))
        self.assertTrue(inspect.isfunction(pipeline.generate_pdf))

if __name__ == '__main__':
    unittest.main()
