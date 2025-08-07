import requests
import json
import logging

# TODO: Make this configurable in the GUI
LMSTUDIO_API_URL = "http://localhost:1234/v1/chat/completions"

def identify_speakers(text_chunk):
    """
    Uses the LMStudio API to identify speakers in a text chunk.
    """
    logging.info("Sending chunk to LMStudio for speaker identification...")
    prompt = f"""\
You are an expert in narrative analysis. Your task is to identify the speaker for each line of dialogue in the following text.
Tag each piece of dialogue with the speaker's name in the format `[SPEAKER_NAME] Dialogue text.`.
If the speaker is the narrator, use the tag `[narrator]`.
If a character is thinking, it's often denoted by italics. Treat thoughts as speech, and tag them with the character's name.
If you cannot determine the speaker, use the tag `[UnknownSpeaker]`.

Here is the text:
---
{text_chunk}
---

Return ONLY the fully tagged text, without any additional commentary.
"""

    headers = {"Content-Type": "application/json"}
    data = {
        "model": "Qwen/Qwen2-7B-Instruct-GGUF", # This should be whatever model the user has loaded
        "messages": [
            {"role": "system", "content": "You are a helpful assistant that identifies speakers in a story."},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
    }

    try:
        response = requests.post(LMSTUDIO_API_URL, headers=headers, data=json.dumps(data))
        response.raise_for_status()  # Raise an exception for bad status codes

        response_json = response.json()
        if 'choices' in response_json and len(response_json['choices']) > 0:
            tagged_text = response_json['choices'][0]['message']['content']
            logging.info("Successfully received speaker-tagged text from LMStudio.")
            return tagged_text.strip()
        else:
            logging.error(f"Invalid response from LMStudio API: {response_json}")
            return None

    except requests.exceptions.RequestException as e:
        logging.exception("Error communicating with LMStudio API.")
        return None

if __name__ == '__main__':
    # Example usage
    sample_text = '''\
The old man sat on the porch. "It's a fine day," he said to himself.
"Indeed it is," a voice replied.
He looked up, surprised. A young woman stood before him. "I'm Sarah," she said.
*I wonder what she wants*, he thought.
The narrator described the scene.
'''
    logging.basicConfig(level=logging.INFO)
    tagged_text = identify_speakers(sample_text)
    if tagged_text:
        print(tagged_text)
