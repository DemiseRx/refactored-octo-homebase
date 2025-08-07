import unittest
import os
import sys

# Add src directory to path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src import higgs_formatter

class TestHiggsFormatter(unittest.TestCase):

    def test_extract_speakers(self):
        """Test the extraction of unique speaker tags."""
        text = "[narrator] He saw [John]. [John] said hello. [Sarah] waved."
        speakers = higgs_formatter.extract_speakers(text)
        self.assertEqual(speakers, ['narrator', 'John', 'Sarah'])

    def test_extract_speakers_no_tags(self):
        """Test with text that contains no speaker tags."""
        text = "This is a sentence with no tags."
        speakers = higgs_formatter.extract_speakers(text)
        self.assertEqual(speakers, [])

    def test_normalize_speaker_names_simple(self):
        """Test simple speaker name normalization."""
        text = "[Mr. Smith] Hello. [Smith] Hi."
        speakers = ['Mr. Smith', 'Smith']
        normalized_text, final_speakers = higgs_formatter.normalize_speaker_names(text, speakers)
        self.assertIn("[Mr. Smith] Hi.", normalized_text)
        self.assertEqual(final_speakers, ['Mr. Smith'])

    def test_normalize_speaker_names_no_change(self):
        """Test that names that shouldn't be normalized are not."""
        text = "[John] Hello. [Sarah] Hi."
        speakers = ['John', 'Sarah']
        normalized_text, final_speakers = higgs_formatter.normalize_speaker_names(text, speakers)
        self.assertEqual(text, normalized_text)
        self.assertEqual(speakers, final_speakers)

    def test_format_for_higgs(self):
        """Test the full formatting pipeline."""
        chunks = [
            "[narrator] The scene is a park. [Mr. Smith] \"A lovely day.\"",
            "[Smith] \"Indeed.\" [Jane] \"Hello, Mr. Smith.\"",
            "[Jane Doe] Hi Jane."
        ]
        final_text, unique_speakers = higgs_formatter.format_for_higgs(chunks)

        # Check that the normalization happened correctly
        self.assertNotIn("[Smith]", final_text)
        self.assertIn("[Mr. Smith] \"Indeed.\"", final_text)
        self.assertNotIn("[Jane]", final_text)
        self.assertIn("[Jane Doe] Hi Jane.", final_text)

        # Check the final list of unique speakers
        # The order might be tricky, so let's check with a set
        self.assertIn('narrator', unique_speakers)
        self.assertIn('Mr. Smith', unique_speakers)
        self.assertIn('Jane Doe', unique_speakers)
        self.assertEqual(len(unique_speakers), 3)

if __name__ == '__main__':
    unittest.main(verbosity=2)
