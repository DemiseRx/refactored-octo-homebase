import re
import logging

def extract_speakers(tagged_text):
    """Extracts a list of unique speaker tags from the text."""
    # This regex finds all occurrences of [speaker_name]
    speakers = re.findall(r'\[([^\]]+)\]', tagged_text)
    # Return a list of unique speakers in the order they appeared
    unique_speakers = list(dict.fromkeys(speakers))
    return unique_speakers

def normalize_speaker_names(text, speakers):
    """
    Normalizes speaker names to a consistent format.
    A simple strategy: if one speaker name is a substring of another,
    replace the shorter name with the longer one.
    E.g., "Smith" and "Mr. Smith" -> "Mr. Smith"
    """
    # This is a complex task. For now, we'll implement a basic version.
    # A more advanced implementation might use fuzzy matching or an LLM.
    normalized_text = text
    # Create a copy to iterate over while modifying
    speaker_map = {s: s for s in speakers}

    for i in range(len(speakers)):
        for j in range(i + 1, len(speakers)):
            s1 = speakers[i]
            s2 = speakers[j]
            if s1 in s2: # e.g., "Smith" is in "John Smith"
                speaker_map[s1] = s2
            elif s2 in s1: # e.g., "John Smith" contains "Smith"
                speaker_map[s2] = s1

    # Apply the mapping to the text
    for old_name, new_name in speaker_map.items():
        if old_name != new_name:
            logging.info(f"Normalizing speaker name '{old_name}' to '{new_name}'")
            normalized_text = normalized_text.replace(f'[{old_name}]', f'[{new_name}]')

    return normalized_text, extract_speakers(normalized_text)


def format_for_higgs(tagged_chunks: list[str]):
    """
    Prepares the tagged text for Higgs Audio V2.
    - Concatenates chunks
    - Normalizes speaker names
    - Extracts unique speakers
    """
    logging.info("Starting final formatting for Higgs Audio V2.")
    full_text = "\n".join(tagged_chunks)

    # First pass to get all speakers
    initial_speakers = extract_speakers(full_text)
    logging.info(f"Found {len(initial_speakers)} initial speaker tags.")

    # Normalize names
    normalized_text, final_speakers = normalize_speaker_names(full_text, initial_speakers)
    logging.info(f"After normalization, {len(final_speakers)} unique speakers remain.")

    return normalized_text, final_speakers

if __name__ == '__main__':
    sample_chunks = [
        '[narrator] The scene is a park. [Mr. Smith] "A lovely day."',
        '[Smith] "Indeed." [Jane] "Hello, Mr. Smith."'
    ]

    logging.basicConfig(level=logging.INFO)
    final_text, unique_speakers = format_for_higgs(sample_chunks)

    print("--- Final Text ---")
    print(final_text)
    print("\n--- Unique Speakers ---")
    print(unique_speakers)
    print(f"Found {len(unique_speakers)} unique speakers.")
