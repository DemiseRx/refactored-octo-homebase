import docx
import re
import logging

def read_file_content(file_path):
    """Reads the content of a .txt or .docx file."""
    logging.info(f"Reading file: {file_path}")
    if file_path.endswith('.docx'):
        try:
            doc = docx.Document(file_path)
            full_text = []
            for para in doc.paragraphs:
                full_text.append(para.text)
            return '\n'.join(full_text)
        except Exception as e:
            logging.exception(f"Error reading .docx file: {file_path}")
            return None
    elif file_path.endswith('.txt'):
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read()
        except Exception as e:
            logging.exception(f"Error reading .txt file: {file_path}")
            return None
    else:
        logging.error(f"Unsupported file type: {file_path}")
        return None

def clean_text(text):
    """Cleans the text by removing double line breaks and standardizing quotes."""
    logging.info("Cleaning text...")
    text = re.sub(r'\n\s*\n', '\n', text)
    text = text.replace('“', '"').replace('”', '"')
    text = text.replace("‘", "'").replace("’", "'")
    return text

def chunk_text(text, chunk_size=1500, overlap=100):
    """Breaks text into manageable chunks with overlap."""
    logging.info(f"Chunking text into ~{chunk_size} word chunks...")
    words = text.split()
    if not words:
        return []

    chunks = []
    start = 0
    while start < len(words):
        end = start + chunk_size
        chunk_words = words[start:end]
        chunks.append(" ".join(chunk_words))

        if end >= len(words):
            break

        start += chunk_size - overlap

    return chunks

def process_file(file_path):
    """Main function to process a file."""
    logging.info(f"Starting to process file: {file_path}")
    content = read_file_content(file_path)
    if content:
        cleaned_content = clean_text(content)
        chunks = chunk_text(cleaned_content)
        logging.info(f"Finished processing file. Created {len(chunks)} chunks.")
        return chunks
    return None
