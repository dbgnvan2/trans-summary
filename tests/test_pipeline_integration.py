import inspect

import pipeline


def test_pipeline_exports_html_generator_functions():
    """Verify that pipeline.py re-exports the functions moved to html_generator.py."""
    assert hasattr(pipeline, "generate_webpage"), "pipeline.generate_webpage missing"
    assert hasattr(pipeline, "generate_simple_webpage"), (
        "pipeline.generate_simple_webpage missing"
    )
    assert hasattr(pipeline, "generate_pdf"), "pipeline.generate_pdf missing"

    # verify they are functions
    assert inspect.isfunction(pipeline.generate_webpage)
    assert inspect.isfunction(pipeline.generate_simple_webpage)
    assert inspect.isfunction(pipeline.generate_pdf)
