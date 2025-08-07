# Audiobook Generator Using Higgs Audio V2

This application provides a graphical user interface to convert text documents (`.txt` or `.docx`) into audiobooks. It leverages a local Large Language Model (LLM) for intelligent speaker identification and the Higgs Audio V2 text-to-speech engine for high-quality voice generation.

## Features

- **Easy-to-Use GUI**: A simple interface for selecting files and monitoring the audiobook creation process.
- **Multiple File Types**: Supports both plain text (`.txt`) and Microsoft Word (`.docx`) files.
- **Automatic Speaker Detection**: Uses a local LLM (via LMStudio) to analyze the text and assign dialogue to different speakers.
- **Narrator and Character Voices**: Intelligently separates narration from character speech and thoughts.
- **Real-time Progress**: A detailed console log and progress bar keep you informed of the current status.
- **Higgs Audio V2 Integration**: Formats the text perfectly for use with the Higgs text-to-speech engine.
- **Packaged for Distribution**: Includes a PyInstaller spec file to build a standalone `.exe` for Windows.

---

## 1. Prerequisites

Before you begin, you must have the following software installed and running on your system:

1.  **Python 3.10+**: Make sure Python is installed and accessible from your command line. You can download it from [python.org](https://www.python.org/).
2.  **LMStudio**: This application is required to run the local LLM for speaker detection.
    -   Download and install LMStudio from [lmstudio.ai](https://lmstudio.ai/).
    -   Inside LMStudio, download and **load the `Qwen/Qwen2-7B-Instruct-GGUF` model**.
    -   Go to the "Local Server" tab (the `<->` icon) and start the server. The application expects the server to be running at `http://localhost:1234`.
3.  **FFMPEG**: This is a required dependency for audio processing.
    -   Download FFMPEG from [ffmpeg.org](https://ffmpeg.org/download.html).
    -   Install it and ensure that the `ffmpeg` executable is available in your system's PATH.
4.  **(Optional) Higgs Audio V2**: The application is designed to work with Higgs Audio V2. This project does not include Higgs itself. You must have a working installation of Higgs accessible from your command line. The application currently calls a placeholder script (`fake_higgs.py`); you will need to edit `src/higgs_interface.py` to point to your actual Higgs run command.

---

## 2. Installation & Running from Source

If you want to run the application directly from the source code, follow these steps.

1.  **Clone the repository**:
    ```bash
    git clone <repository_url>
    cd <repository_name>
    ```

2.  **Create a virtual environment** (recommended):
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Run the application**:
    ```bash
    python src/main.py
    ```

---

## 3. How to Use the Application

1.  **Launch the application** by running `python src/main.py` or by double-clicking the built executable.
2.  **Click the "Browse for .txt or .docx file" button** and select the document you want to convert.
3.  **Wait for processing**: The application will automatically begin processing the file. You can monitor the progress in the console (click "Toggle Console" to view). The steps are:
    -   Reading and chunking the file.
    -   Sending chunks to LMStudio for speaker identification.
    -   Formatting the script for the audio engine.
4.  **Generate Audio**: Once the initial processing is complete, the **"Generate Audio"** button will become enabled. Click it to begin audio generation.
5.  **Monitor Audio Generation**: The console will display live logs from the audio generation engine.
6.  **Complete!**: When finished, a "✅ Audio generation complete!" message will appear. The final audio file will be located in the `output` directory inside the project folder.
7.  **Open Output Folder**: Click the "Open Output Folder" button to easily access your generated audiobook file.

---

## 4. Building the Executable (for Windows)

This project is set up to be packaged into a single `.exe` file using PyInstaller.

1.  **Ensure all dependencies are installed**:
    ```bash
    pip install -r requirements.txt
    ```
2.  **Run the PyInstaller build command**:
    ```bash
    pyinstaller build.spec
    ```
3.  **Find the executable**: The process may take a few minutes. Once complete, the standalone executable will be located in the `dist` folder: `dist/AudiobookGenerator.exe`. You can move this file to any location and run it without needing Python or any dependencies installed.

---

## 5. Configuration

-   **LMStudio Endpoint**: The API endpoint for LMStudio is currently hardcoded in `src/llm_interface.py` to `http://localhost:1234/v1/chat/completions`. If your server runs on a different port, you must edit this file.
-   **Higgs Engine Command**: The command to run the audio engine is located in `src/higgs_interface.py`. It currently calls a placeholder script `fake_higgs.py`. You will need to modify the `command` variable in the `generate_audio` function to point to your actual Higgs executable and its required arguments.
