import unittest
import os
import sys
import docx

# Add src directory to path to import modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from src import text_processor

class TestTextProcessor(unittest.TestCase):

    def setUp(self):
        self.fixtures_dir = os.path.join(os.path.dirname(__file__), 'fixtures')
        self.txt_path = os.path.join(self.fixtures_dir, 'sample.txt')
        self.docx_path = os.path.join(self.fixtures_dir, 'sample.docx')

    def test_read_file_content_txt(self):
        """Test reading content from a .txt file."""
        content = text_processor.read_file_content(self.txt_path)
        # The sample file has a trailing newline
        expected_content = "This is a sample text file.\n\nIt has double line breaks, which should be cleaned.\n\nIt also uses “fancy quotes” and ‘single fancy quotes’.\n"
        self.assertEqual(content, expected_content)

    def test_read_file_content_docx(self):
        """Test reading content from a .docx file."""
        content = text_processor.read_file_content(self.docx_path)
        # Based on how create_test_fixtures.py created the docx
        # The python-docx reader joins paragraphs with a single newline.
        expected_content = "This is a sample docx file.\n\nIt has multiple paragraphs."
        self.assertEqual(content, expected_content)

    def test_read_file_non_existent(self):
        """Test reading a non-existent file."""
        content = text_processor.read_file_content('non_existent_file.txt')
        self.assertIsNone(content)

    def test_read_unsupported_file_type(self):
        """Test reading an unsupported file type."""
        content = text_processor.read_file_content('README.md')
        self.assertIsNone(content)

    def test_clean_text(self):
        """Test the text cleaning function."""
        raw_text = "Hello\n\nWorld. These are “fancy” quotes and ‘these’ are ‘single’."
        cleaned_text = text_processor.clean_text(raw_text)
        expected_text = 'Hello\nWorld. These are "fancy" quotes and \'these\' are \'single\'.'
        self.assertEqual(cleaned_text, expected_text)

    def test_chunk_text(self):
        """Test the text chunking function."""
        text = "word " * 50  # 50 words
        chunks = text_processor.chunk_text(text, chunk_size=20, overlap=5)
        self.assertEqual(len(chunks), 3) # 0-20, 15-35, 30-50
        self.assertTrue(chunks[0].startswith("word word"))
        self.assertTrue(chunks[1].count("word") <= 20)

    def test_chunk_text_empty(self):
        """Test chunking empty text."""
        chunks = text_processor.chunk_text("")
        self.assertEqual(len(chunks), 0)

    def test_process_file_pipeline(self):
        """Test the full process_file pipeline for a txt file."""
        chunks = text_processor.process_file(self.txt_path)
        self.assertIsNotNone(chunks)
        self.assertIsInstance(chunks, list)
        self.assertTrue(len(chunks) > 0)
        # Check if cleaning was applied
        self.assertNotIn('\n\n', chunks[0])
        self.assertNotIn('“', chunks[0])

if __name__ == '__main__':
    unittest.main(verbosity=2)
