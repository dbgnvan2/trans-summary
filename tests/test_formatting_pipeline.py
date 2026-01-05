import unittest

from formatting_pipeline import (
    _generate_yaml_front_matter,
    _normalize_word_for_validation,
    strip_sic_annotations,
)


class TestFormattingPipeline(unittest.TestCase):

    def test_generate_yaml_front_matter(self):
        meta = {
            "title": "Roots of Bowen Theory",
            "presenter": "Dr Michael Kerr",
            "date": "2019-11-15",
            "year": "2019",
            "stem": "Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15"
        }
        source_filename = "Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15.mp4"
        
        yaml_content = _generate_yaml_front_matter(meta, source_filename)
        
        self.assertIn('Title: "Roots of Bowen Theory"', yaml_content)
        self.assertIn('Presenter: "Dr Michael Kerr"', yaml_content)
        self.assertIn('Lecture date: "2019-11-15"', yaml_content)
        self.assertIn('Source recording: "Roots of Bowen Theory - Dr Michael Kerr - 2019-11-15.mp4"', yaml_content)
        self.assertIn('License: "© 2019 Dr Michael Kerr. All rights reserved."', yaml_content)
        self.assertTrue(yaml_content.startswith("---"))
        self.assertIn("---", yaml_content[3:]) # Should end with ---

    def test_strip_sic_annotations(self):
        text = "This is a mispelled [sic] word."
        cleaned, count = strip_sic_annotations(text)
        self.assertEqual(cleaned.strip(), "This is a mispelled word.")
        self.assertEqual(count, 1)

        text_with_comment = "Another errror [sic] (spelling) here."
        cleaned, count = strip_sic_annotations(text_with_comment)
        self.assertEqual(cleaned.strip(), "Another errror here.")
        self.assertEqual(count, 1)

    def test_normalize_word_for_validation(self):
        # Basic lowercasing
        self.assertEqual(_normalize_word_for_validation("Word"), "word")
        
        # Punctuation stripping
        self.assertEqual(_normalize_word_for_validation("word."), "word")
        self.assertEqual(_normalize_word_for_validation("word,"), "word")
        self.assertEqual(_normalize_word_for_validation("?word!"), "word")
        
        # Markdown stripping
        self.assertEqual(_normalize_word_for_validation("**word**"), "word")
        self.assertEqual(_normalize_word_for_validation("*word*"), "word")
        self.assertEqual(_normalize_word_for_validation("__word__"), "word")
        self.assertEqual(_normalize_word_for_validation("`code`"), "code")

if __name__ == '__main__':
    unittest.main()
