import subprocess
import sys
import tempfile
import os
import logging

def generate_audio(text_to_speak, output_path):
    """
    Calls the (simulated) Higgs Audio V2 engine to generate audio.

    Args:
        text_to_speak (str): The fully formatted text with speaker tags.
        output_path (str): The path to save the final audio file.

    Returns:
        bool: True if successful, False otherwise.
    """
    with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt', encoding='utf-8') as tmp_file:
        tmp_file.write(text_to_speak)
        input_filepath = tmp_file.name

    try:
        # We assume a fake_higgs.py script exists for simulation purposes.
        # In a real scenario, this would be the path to the Higgs executable or run script.
        higgs_script_path = 'fake_higgs.py'
        command = [sys.executable, higgs_script_path, '--input-file', input_filepath, '--output-file', output_path]

        logging.info(f"Running command: {' '.join(command)}")

        # Using Popen for real-time output streaming
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')

        # Read and report progress line by line
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                logging.info(f"[Higgs]: {output.strip()}")

        return_code = process.poll()
        if return_code != 0:
            logging.error(f"Higgs process exited with error code {return_code}")
            return False

        logging.info("Higgs process finished successfully.")
        return True

    except FileNotFoundError:
        logging.exception(f"Error: Could not find the Higgs script at '{higgs_script_path}'. Make sure it is in the correct location.")
        return False
    except Exception as e:
        logging.exception("An unexpected error occurred during Higgs audio generation.")
        return False
    finally:
        # Clean up the temporary file
        if os.path.exists(input_filepath):
            os.remove(input_filepath)
