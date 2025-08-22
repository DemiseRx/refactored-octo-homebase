"""
Audiobook Generator
====================

This module implements a standalone application for converting text‐based books
into high‑quality audiobooks.  It is designed to run entirely on a local
Windows machine without an internet connection, leveraging a locally hosted
language model (LM Studio) for parsing and a powerful text‑to‑speech engine
(Higgs Audio V2) for audio synthesis.  The user interacts with the program
through a graphical interface built with PySide6.

Key Features
------------

* **Document Import:** The application accepts plain text files (``.txt``) and
  Microsoft Word documents (``.docx``).  When a document is imported the
  program extracts the raw text, normalizes it and identifies chapter
  headings.  Chapters are used as natural boundaries for both language
  processing and audio synthesis.
* **LLM‑Based Parsing:** A locally hosted LLM running in LM Studio is used
  to transform raw text into a structured script suitable for multi‑speaker
  narration.  The LLM is queried via the OpenAI‑compatible API exposed on
  ``localhost:1234``, as described in the LM Studio documentation【387899098358715†L191-L229】.
  The script uses a simple ``Speaker: utterance`` format where each
  dialogue line is attributed to a character and narration is labelled
  ``Narrator``.
* **Speaker Detection & Voice Management:**  After parsing, the program
  extracts a list of unique speakers from the script.  Users can assign
  reference audio files to each speaker so that the Higgs Audio model can
  clone those voices in future runs.  Voice assignments are saved to a
  ``voices.json`` file in the application directory and reloaded for each
  project, providing consistent voices across multiple books.  Higgs Audio V2
  supports reference audio for voice cloning and multi‑speaker dialogue
  generation【975055967064727†L48-L73】.
* **Chunked Text‑to‑Speech:**  To keep memory usage under control and
  maintain natural prosody, long scripts are split into manageable chunks.
  The Deepgram latency guide notes that splitting long outputs by sentence
  rather than in the middle of a sentence produces smoother audio【6123374342497†L402-L415】,
  so this implementation splits at speaker turns or sentence boundaries.
  Each chunk is synthesised separately and concatenated.  A check is made
  before each chapter to ensure at least 2 GB of disk space is available for
  the resulting audio file.
* **User‑Friendly Interface:**  The PySide6 interface offers file selection
  dialogs, an output directory picker, a progress bar, and real‑time logs.
  Users can start the conversion with a single button click.  Errors and
  status updates are clearly reported in the GUI.

Prerequisites
-------------

The application requires Python 3.8 or later.  Additional dependencies are
listed in ``requirements.txt`` and can be installed via ``pip``.  You must
run LM Studio in server mode (Developer → API Server) so that it accepts
requests on ``http://localhost:1234/v1``【387899098358715†L191-L229】.  The Higgs
Audio V2 model weights and tokenizer must be downloaded separately and
accessible to the program; see the Boson AI blog for details on the model
capabilities【667459721059533†L40-L83】.
"""

# ======================================================================
# Logging & diagnostics bootstrap
# ======================================================================

import sys  # required early for logging information
import logging
from logging.handlers import RotatingFileHandler
import time
import platform
from pathlib import Path as _PathForLog

# Set up a rotating log file in the project directory.  This log will
# capture detailed debug information about imports, environment status and
# runtime errors.  It is initialised once on module import.
PROJECT_DIR = _PathForLog(__file__).resolve().parent
LOG_PATH = PROJECT_DIR / "debug.log"

def _init_logging() -> None:
    """Initialise root logger to print to stdout and to a rotating file."""
    logger = logging.getLogger()
    if logger.handlers:
        # Logging already configured
        return
    logger.setLevel(logging.DEBUG)
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG)
    ch_fmt = logging.Formatter("[%(asctime)s][%(levelname)s] %(message)s", "%H:%M:%S")
    ch.setFormatter(ch_fmt)
    logger.addHandler(ch)
    # Rotating file handler (1 MB per file, keep 5 backups)
    fh = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=5, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh_fmt = logging.Formatter(
        "[%(asctime)s][%(levelname)s][%(name)s] %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    fh.setFormatter(fh_fmt)
    logger.addHandler(fh)

_init_logging()
logging.debug("=== audiobook_generator.py loaded ===")
logging.debug("Python %s (%s)", sys.version, sys.executable)
logging.debug("Project directory: %s", PROJECT_DIR)

def try_import(modname: str):
    """
    Attempt to import a module by name.  On success, return (module, None).
    On failure, return (None, exception).  All import attempts are logged.
    """
    try:
        module = __import__(modname)
        logging.debug("Import OK: %s (version: %s)", modname, getattr(module, "__version__", "unknown"))
        return module, None
    except Exception as exc:
        logging.error("Import FAIL: %s", modname, exc_info=True)
        return None, exc
import json
import os
import re
import shutil
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import numpy as np  # type: ignore

import base64  # builtin module used for encoding reference audio

# ----------------------------------------------------------------------
# Third-party imports with diagnostics.
# For each optional dependency, attempt to import it and log the result.
# If the module is unavailable, fall back to None and capture the error.

# Requests (HTTP client)
requests, _ = try_import("requests")

# soundfile for writing WAVs
_sf_mod, _sf_err = try_import("soundfile")
sf = _sf_mod if _sf_mod else None  # type: ignore

# python-docx for reading .docx files
DOCX_OK = True
try:
    from docx import Document  # type: ignore
except Exception:
    DOCX_OK = False
    Document = None  # type: ignore
    logging.error("python-docx import failed", exc_info=True)

# GUI toolkit (PySide6)
PYSIDE_OK = True
try:
    from PySide6.QtCore import QObject, Qt, QThread, Signal
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QFileDialog,
        QFormLayout,
        QHBoxLayout,
        QLabel,
        QLineEdit,
        QListWidget,
        QListWidgetItem,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QProgressBar,
        QSplitter,
        QTableWidget,
        QTableWidgetItem,
        QTextEdit,
        QToolBar,
        QMenuBar,
        QMenu,
        QVBoxLayout,
        QWidget,
    )
except Exception:
    PYSIDE_OK = False
    logging.error("PySide6 import failed", exc_info=True)
    # Define dummy stubs for Qt classes used below so that the module can
    # still be imported without PySide6.  Each stub is a simple object.
    class _Dummy:
        """Fallback type used when PySide6 is not installed."""
        def __init__(self, *args, **kwargs) -> None:
            pass

    QObject = Qt = QThread = Signal = QAction = QApplication = QComboBox = QFileDialog = QFormLayout = QHBoxLayout = QLabel = QLineEdit = QListWidget = QListWidgetItem = QMainWindow = QMessageBox = QPushButton = QProgressBar = QSplitter = QTableWidget = QTableWidgetItem = QTextEdit = QToolBar = QMenuBar = QMenu = QVBoxLayout = QWidget = _Dummy  # type: ignore

# Attempt to import Higgs Audio dependencies.  We defer optional imports
# until runtime, but import the type names here if available.
try:
    from boson_multimodal.serve.serve_engine import HiggsAudioServeEngine, HiggsAudioResponse  # type: ignore
    from boson_multimodal.data_types import ChatMLSample, Message, AudioContent  # type: ignore
except Exception:
    HiggsAudioServeEngine = None  # type: ignore
    HiggsAudioResponse = None  # type: ignore
    ChatMLSample = None  # type: ignore
    Message = None  # type: ignore
    AudioContent = None  # type: ignore

# Import torch and other ML libraries for diagnostics.  These may be None
# if the packages are not installed.
torch, _ = try_import("torch")  # type: ignore
torchaudio, _ = try_import("torchaudio")  # type: ignore
transformers, _ = try_import("transformers")  # type: ignore

# huggingface_hub for downloading models without symlinks (optional)
huggingface_hub, _ = try_import("huggingface_hub")  # type: ignore

###############################################################################
# Diagnostics utilities
###############################################################################

class Diagnostics:
    """Deep diagnostics for the environment and Higgs Audio dependencies.

    This helper gathers detailed information about installed packages,
    hardware (CUDA/GPU), Python environment, and the availability of
    optional dependencies used by this application.  It writes results to
    the debug log and returns a formatted string for display in the GUI
    or command line.  The diagnostics do not load any heavy models but
    validate importability and presence of key classes.
    """

    @staticmethod
    def _vstr(mod: object) -> str:
        """Return a human-readable version string for a module or 'not imported'."""
        if mod is None:
            return "not imported"
        return getattr(mod, "__version__", "no __version__")

    @staticmethod
    def run() -> str:
        lines: List[str] = []
        add = lines.append

        add("=== Diagnostics ===")
        add(f"Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
        add(f"Python: {sys.version}")
        add(f"Interpreter: {sys.executable}")
        add(f"Platform: {platform.platform()}")
        add(f"Working Dir: {os.getcwd()}")
        add(f"Project Dir: {PROJECT_DIR}")
        add(f"Log File: {LOG_PATH}")

        # Core libs
        add("--- Core Packages ---")
        add(f"requests: {Diagnostics._vstr(requests)}")
        add(f"soundfile: {Diagnostics._vstr(sf)}")
        add(f"python-docx: {'OK' if DOCX_OK else 'MISSING'}")
        add(f"PySide6: {'OK' if PYSIDE_OK else 'MISSING'}")
        # numpy imported globally as np
        add(f"numpy: {Diagnostics._vstr(np)}")

        # Torch / CUDA
        add("--- Torch / CUDA ---")
        if torch:
            try:
                add(f"torch: {torch.__version__}")
                add(f"CUDA available: {torch.cuda.is_available()}")
                if torch.cuda.is_available():
                    add(f"CUDA device count: {torch.cuda.device_count()}")
                    try:
                        add(f"CUDA device 0: {torch.cuda.get_device_name(0)}")
                    except Exception as e:
                        add(f"CUDA device 0 name error: {e}")
                else:
                    add("No CUDA; CPU fallback will be used.")
            except Exception as e:
                add(f"Torch diagnostics error: {e}")
                logging.error("Torch diagnostics failed", exc_info=True)
        else:
            add("torch: NOT IMPORTED")

        # torchaudio
        add("--- torchaudio ---")
        if torchaudio:
            try:
                add(f"torchaudio: {torchaudio.__version__}")
                try:
                    backend = torchaudio.get_audio_backend()
                except Exception:
                    backend = "unknown"
                add(f"torchaudio backend: {backend}")
            except Exception as e:
                add(f"torchaudio diagnostics error: {e}")
                logging.error("torchaudio diagnostics failed", exc_info=True)
        else:
            add("torchaudio: NOT IMPORTED")

        # transformers
        add("--- transformers ---")
        if transformers:
            try:
                add(f"transformers: {transformers.__version__}")
            except Exception as e:
                add(f"transformers diagnostics error: {e}")
                logging.error("transformers diagnostics failed", exc_info=True)
        else:
            add("transformers: NOT IMPORTED")

        # Higgs Audio package
        add("--- Higgs Audio (boson_multimodal) ---")
        try:
            # Attempt to import required classes; will raise if missing
            from boson_multimodal.data_types import ChatMLSample, Message, AudioContent  # type: ignore
            from boson_multimodal.serve.serve_engine import HiggsAudioServeEngine, HiggsAudioResponse  # type: ignore
            add("boson_multimodal: OK (imports succeeded)")
            add("Higgs classes present: ChatMLSample, Message, AudioContent, HiggsAudioServeEngine, HiggsAudioResponse")
        except Exception:
            add("boson_multimodal: IMPORT FAILED (see log)")
            logging.error("boson_multimodal import failed", exc_info=True)

        # LM Studio environment
        add("--- LM Studio (parsing) ---")
        add(f"LMSTUDIO_BASE_URL: {os.environ.get('LMSTUDIO_BASE_URL', 'http://localhost:1234/v1')}")
        add(f"LMSTUDIO_API_KEY: {os.environ.get('LMSTUDIO_API_KEY', 'lm-studio')}")

        # File system checks
        add("--- File System ---")
        try:
            add(f"Project exists: {PROJECT_DIR.exists()}")
        except Exception as e:
            add(f"Project dir stat error: {e}")

        result = "\n".join(lines)
        logging.debug(result)
        return result

    # (old optional import block removed; see new diagnostics-based imports at top)


###############################################################################
# Utility classes
###############################################################################


def check_disk_space(path: Path, threshold_bytes: int) -> bool:
    """Return True if the available disk space at ``path`` is greater than
    ``threshold_bytes``.  Uses ``shutil.disk_usage`` to compute free space.
    """
    usage = shutil.disk_usage(path)
    return usage.free >= threshold_bytes


def read_text_from_file(filepath: Path) -> str:
    """Read the contents of a plain text file as a single string.  Files are
    assumed to be encoded in UTF‑8.  Trailing whitespace is stripped.
    """
    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()
    return content.strip()


class DocumentParser:
    """Parses input documents into raw text and chapter segments."""

    def parse(self, filepath: Path) -> Tuple[str, List[Tuple[str, slice]]]:
        """Return a tuple of the full text and a list of chapters.  Each
        chapter is represented by its title and a slice object indicating
        the segment of the full text belonging to that chapter.

        If no chapter headings are found, the entire book is treated as a
        single chapter named "Untitled".
        """
        ext = filepath.suffix.lower()
        if ext == ".docx":
            text = self._read_docx(filepath)
        else:
            text = read_text_from_file(filepath)

        # Normalize line breaks and collapse multiple blank lines
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)

        chapters: List[Tuple[str, slice]] = []
        pattern = re.compile(r"^(chapter\s+|prologue|epilogue|appendix)?\s*([ivxlcdm]+|\d+).*", re.IGNORECASE)
        lines = text.splitlines()
        current_start = 0
        current_title = "Untitled"
        for idx, line in enumerate(lines):
            if pattern.match(line.strip()):
                # Start of a new chapter
                if idx > current_start:
                    chapters.append((current_title, slice(current_start, idx)))
                current_title = line.strip()
                current_start = idx
        # Append the final chapter
        chapters.append((current_title, slice(current_start, len(lines))))

        return text, chapters

    def _read_docx(self, filepath: Path) -> str:
        """Read text from a .docx file using python-docx."""
        if Document is None:
            raise RuntimeError(
                "Reading .docx files requires the 'python-docx' package, which is not installed in this environment. "
                "Please install 'python-docx' to enable .docx support."
            )
        doc = Document(str(filepath))
        parts: List[str] = []
        for para in doc.paragraphs:
            parts.append(para.text)
        return "\n".join(parts)


class LMClient:
    """Client for interacting with a locally hosted LLM via LM Studio.

    The client uses the OpenAI‑compatible chat completions endpoint to
    request structured output.  A system prompt instructs the model to
    produce a script in ``Speaker: utterance`` format and to label
    non‑dialogue narrative text as ``Narrator``.
    """

    def __init__(self, model_name: str = "default") -> None:
        self.base_url = os.environ.get("LMSTUDIO_BASE_URL", "http://localhost:1234/v1")
        self.api_key = os.environ.get("LMSTUDIO_API_KEY", "lm-studio")
        self.model_name = model_name

    def parse_script(self, chapter_text: str) -> str:
        """Return a structured script for the given chapter.  The script is
        returned as a single string with each line prefixed by ``Speaker:``.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a parser AI that formats novels for audiobook narration. "
                    "Identify dialogue and assign each line to the correct speaker. "
                    "Use the format 'Narrator: ...' for narration and descriptions. "
                    "For dialogue, use 'CharacterName: \"Sentence\"'. "
                    "If a chapter heading consists solely of a number, produce 'Narrator: Chapter N'."
                ),
            },
            {"role": "user", "content": chapter_text},
        ]
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        url = f"{self.base_url}/chat/completions"
        try:
            response = requests.post(url, headers={"Authorization": f"Bearer {self.api_key}"}, json=payload, timeout=600)
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Failed to query LM Studio: {exc}") from exc
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        # Remove think block if present
        try:
            import re
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        except Exception:
            pass
        return content

    def parse_paragraph(self, chapter_text: str, paragraph_text: str) -> str:
        """Return a structured script for a target paragraph within a chapter.

        The thinking model requires context to maintain character consistency across
        paragraphs.  This method sends the entire chapter for context along
        with the specific paragraph to be converted.  The model is instructed
        to produce a ``Speaker: utterance`` script only for the target
        paragraph, without including content from adjacent paragraphs.  To
        clearly delineate each chunk, the assistant is asked to include a
        start marker ``[START_CHUNK]`` before the first line and an end
        marker ``[END_CHUNK]`` after the last line.  These markers are
        removed by the caller.
        """
        messages = [
            {
                "role": "system",
                "content": (
                    "You are a parser AI that formats novels for audiobook narration. "
                    "You will be given the full text of a chapter and a specific target paragraph from that chapter. "
                    "Identify dialogue within the target paragraph and assign each line to the correct speaker. "
                    "Use the format 'Narrator: ...' for narration and descriptions. "
                    "For dialogue, use 'CharacterName: \"Sentence\"'. "
                    "Do not summarise or omit any part of the target paragraph. "
                    "Do not generate script for any other paragraphs. "
                    "Before the first line of the script output, write '[START_CHUNK]' on its own line. "
                    "After the last line of the script output, write '[END_CHUNK]' on its own line. "
                    "If the target paragraph is empty or contains only whitespace, just output '[START_CHUNK]' and '[END_CHUNK]' with no script in between."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Context (full chapter):\n" + chapter_text + "\n\n"
                    "Target paragraph:\n" + paragraph_text + "\n"
                ),
            },
        ]
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 4096,
        }
        url = f"{self.base_url}/chat/completions"
        try:
            response = requests.post(url, headers={"Authorization": f"Bearer {self.api_key}"}, json=payload, timeout=600)
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Failed to query LM Studio: {exc}") from exc
        data = response.json()
        content = data["choices"][0]["message"]["content"]
        # Remove any <think>...</think> block from the model output.  The
        # thinking models may include a reflective section wrapped in
        # <think> tags that should not be part of the final script.  Use a
        # non‑greedy regex to strip this section if present.
        try:
            import re
            content = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
        except Exception:
            pass
        # Strip markers and return only the script lines
        lines = [line.strip() for line in content.splitlines()]
        # Remove empty lines at start and end
        while lines and not lines[0]:
            lines = lines[1:]
        while lines and not lines[-1]:
            lines = lines[:-1]
        # Remove markers if present
        if lines and lines[0].startswith("[START_CHUNK]"):
            lines = lines[1:]
        if lines and lines and lines[-1].startswith("[END_CHUNK]"):
            lines = lines[:-1]
        # Return the remaining lines joined by newline.  If no script lines
        # remain (empty paragraph), return an empty string.
        return "\n".join(lines)

    @staticmethod
    def extract_speakers(script: str) -> List[str]:
        """Return a sorted list of unique speaker names found in the script,
        excluding the 'Narrator'.  Speaker names are extracted from the start
        of each line (everything before the first colon).  Empty names are
        ignored.
        """
        names: Set[str] = set()
        for line in script.splitlines():
            if not line.strip():
                continue
            if ":" not in line:
                continue
            name, _ = line.split(":", 1)
            name = name.strip()
            if name.lower() != "narrator" and name:
                names.add(name)
        return sorted(names)


class TTSGenerator:
    """Interface to the Higgs Audio V2 text‑to‑speech engine.

    This class encapsulates the logic for synthesising audio from structured
    scripts.  It accepts a mapping of speaker names to reference audio files
    and uses this mapping to pass appropriate reference clips to the Higgs
    model.  The actual invocation of the model is abstracted into a
    separate method ``_synthesise`` to make the design testable.  This
    implementation provides a stub for synthesis; users should replace
    ``_synthesise`` with a call to the Higgs API or library.
    """

    def __init__(self, voice_mapping: Dict[str, Optional[Path]], narrator_voice: Optional[Path] = None) -> None:
        self.voice_mapping = voice_mapping
        self.narrator_voice = narrator_voice

    def generate_chapter(self, script: str, output_path: Path) -> None:
        """Generate audio for a chapter script and save it to ``output_path``.

        The script is split into small blocks at speaker boundaries.  Each block
        is synthesised separately and appended to the final WAV file.  At
        chapter boundaries, a one second pause of silence is inserted.
        """
        # Prepare output directory
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Remove existing file
        if output_path.exists():
            output_path.unlink()
        # Accumulate audio chunks as (numpy array, sample_rate)
        chunks: List[Tuple[np.ndarray, int]] = []
        block: List[str] = []
        last_speaker: Optional[str] = None
        for line in script.splitlines():
            if not line.strip():
                continue
            if ":" not in line:
                continue
            speaker, content = [part.strip() for part in line.split(":", 1)]
            # Start a new block when the speaker changes
            if last_speaker is not None and speaker != last_speaker:
                # Synthesize previous block
                audio, sr = self._synthesise_block(block, last_speaker)
                chunks.append((audio, sr))
                block = []
            block.append(f"{speaker}: {content}")
            last_speaker = speaker
        # Synthesize final block
        if block and last_speaker:
            audio, sr = self._synthesise_block(block, last_speaker)
            chunks.append((audio, sr))

        # Concatenate audio chunks with small pauses between them
        final_audio: Optional[np.ndarray] = None
        final_sr: int = 24000  # default sample rate for Higgs V2【667459721059533†L70-L78】
        silence = np.zeros(int(0.5 * final_sr), dtype=np.float32)  # half second pause
        for idx, (chunk_audio, sr) in enumerate(chunks):
            if final_audio is None:
                final_audio = chunk_audio
                final_sr = sr
            else:
                # Ensure sample rates match
                if sr != final_sr:
                    raise ValueError(f"Mismatched sample rates: {sr} vs {final_sr}")
                final_audio = np.concatenate((final_audio, silence, chunk_audio))
        if final_audio is None:
            # No audio generated; write empty file
            final_audio = np.zeros(1, dtype=np.float32)
        # Save to WAV
        if sf is None:
            # soundfile is required for writing audio; provide clear error message
            raise RuntimeError(
                "The 'soundfile' package is not available in this environment. "
                "Please install it or run this application in an environment where 'soundfile' is installed."
            )
        sf.write(output_path, final_audio, final_sr)

    def _synthesise_block(self, lines: List[str], speaker: str) -> Tuple[np.ndarray, int]:
        """Generate speech for a contiguous block of dialogue.

        This implementation performs extensive diagnostics and logging before
        attempting to invoke the Higgs Audio V2 model.  It strips the
        ``Speaker:`` prefix from each line, joins the remaining content into
        a single string, constructs a ChatML sample, and then calls the
        Higgs model to synthesise audio.  Voice cloning is supported via
        ``voice_mapping``: if a reference audio clip is configured for the
        given ``speaker``, it is encoded and included in the system message.

        If any of the required dependencies (HiggsAudioServeEngine,
        ChatMLSample, Message, torch) are missing, a detailed diagnostics
        report is included in the raised RuntimeError.
        """
        logging.debug("TTSGenerator._synthesise_block start: speaker=%s, lines=%d", speaker, len(lines))
        # Verify that all Higgs dependencies are available
        missing: List[str] = []
        if HiggsAudioServeEngine is None or ChatMLSample is None or Message is None:
            missing.append("boson_multimodal")
        if torch is None:
            missing.append("torch")
        if missing:
            diag = Diagnostics.run()
            raise RuntimeError(
                "Higgs Audio dependencies missing: " + ", ".join(missing) + "\n" + diag
            )

        # Extract spoken content (remove the speaker prefix) and join lines
        texts: List[str] = []
        for line in lines:
            parts = line.split(":", 1)
            if len(parts) == 2:
                _, content = parts
                texts.append(content.strip())
            else:
                texts.append(line.strip())
        text = "\n".join(texts)
        logging.debug("Synthesis text length: %d characters", len(text))

        # Prepare optional reference audio for voice cloning
        audio_content = None  # type: ignore
        ref_path = self.voice_mapping.get(speaker)
        if ref_path and ref_path.exists():
            try:
                with open(ref_path, "rb") as f:
                    audio_bytes = f.read()
                audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
                audio_content = AudioContent(audio_url="", raw_audio=audio_b64)
                logging.debug(
                    "Loaded reference voice for speaker '%s': %s (%d bytes)",
                    speaker,
                    ref_path,
                    len(audio_bytes),
                )
            except Exception:
                logging.warning(
                    "Failed to load reference audio '%s' for speaker '%s'", ref_path, speaker, exc_info=True
                )
        else:
            logging.debug("No reference voice configured for speaker '%s'", speaker)

        # Construct ChatML messages
        system_content: object
        if audio_content is not None:
            system_content = [audio_content, "Use this reference voice to clone the speaker."]
        else:
            system_content = "Generate expressive and natural speech for the following text."
        messages = [
            Message(role="system", content=system_content),
            Message(role="user", content=text),
        ]
        chat_sample = ChatMLSample(messages=messages)

        # Initialise Higgs engine
        # Download the model and tokenizer locally without symlinks and reuse
        # across synthesis calls.  This avoids symlink privileges on Windows
        # and eliminates repeated downloads.  We also cache the loaded
        # HiggsAudioServeEngine instance keyed by the local paths and device
        # to avoid reinitialisation overhead.
        model_path = os.environ.get("HIGGS_MODEL_PATH", "bosonai/higgs-audio-v2-generation-3B-base")
        tokenizer_path = os.environ.get("HIGGS_AUDIO_TOKENIZER_PATH", "bosonai/higgs-audio-v2-tokenizer")
        device = "cuda" if torch and torch.cuda.is_available() else "cpu"

        # Ensure we have a cache for local downloads and engines on the class
        if not hasattr(self.__class__, "_higgs_local_cache"):
            self.__class__._higgs_local_cache = {}
        if not hasattr(self.__class__, "_higgs_engine_cache"):
            self.__class__._higgs_engine_cache = {}

        cache_key = (model_path, tokenizer_path)
        if cache_key in self.__class__._higgs_local_cache:
            local_model_path, local_tokenizer_path = self.__class__._higgs_local_cache[cache_key]
        else:
            # Determine a local directory for downloads inside the project
            cache_root = PROJECT_DIR / "hf_downloads"
            model_local_dir = cache_root / "model_repo"
            tokenizer_local_dir = cache_root / "tokenizer_repo"
            model_local_dir.mkdir(parents=True, exist_ok=True)
            tokenizer_local_dir.mkdir(parents=True, exist_ok=True)
            # Use snapshot_download from huggingface_hub to download without symlinks
            try:
                from huggingface_hub import snapshot_download  # type: ignore
            except Exception as exc:
                raise RuntimeError(
                    "huggingface_hub is required to download Higgs model and tokenizer locally. "
                    "Please install the 'huggingface_hub' package."
                ) from exc
            try:
                logging.debug(
                    "Downloading Higgs model '%s' to %s (symlinks disabled)",
                    model_path,
                    model_local_dir,
                )
                local_model_path = snapshot_download(
                    repo_id=model_path,
                    local_dir=str(model_local_dir),
                    local_dir_use_symlinks=False,
                )
                logging.debug(
                    "Downloading Higgs tokenizer '%s' to %s (symlinks disabled)",
                    tokenizer_path,
                    tokenizer_local_dir,
                )
                local_tokenizer_path = snapshot_download(
                    repo_id=tokenizer_path,
                    local_dir=str(tokenizer_local_dir),
                    local_dir_use_symlinks=False,
                )
            except Exception:
                logging.error("Failed to download Higgs model/tokenizer", exc_info=True)
                raise
            # Cache the resolved local paths for subsequent calls
            self.__class__._higgs_local_cache[cache_key] = (local_model_path, local_tokenizer_path)

        # Attempt to reuse an existing Higgs engine for the same local paths and device
        engine_key = (local_model_path, local_tokenizer_path, device)
        if engine_key in self.__class__._higgs_engine_cache:
            serve_engine = self.__class__._higgs_engine_cache[engine_key]
        else:
            logging.debug(
                "Initialising HiggsAudioServeEngine: local_model=%s, local_tokenizer=%s, device=%s",
                local_model_path,
                local_tokenizer_path,
                device,
            )
            try:
                serve_engine = HiggsAudioServeEngine(local_model_path, local_tokenizer_path, device=device)
            except Exception:
                logging.error("Failed to initialise HiggsAudioServeEngine", exc_info=True)
                raise
            # Cache the engine for future calls
            self.__class__._higgs_engine_cache[engine_key] = serve_engine

        # Determine token budget; approximate half of input characters
        approx_tokens = max(256, int(len(text) / 2))
        logging.debug(
            "Calling Higgs generate: approx_tokens=%d, temperature=0.3, top_p=0.95, top_k=50",
            approx_tokens,
        )
        try:
            response: HiggsAudioResponse = serve_engine.generate(
                chat_ml_sample=chat_sample,
                max_new_tokens=approx_tokens,
                temperature=0.3,
                top_p=0.95,
                top_k=50,
                force_audio_gen=True,
            )
        except Exception:
            logging.error("Higgs generate() raised an exception", exc_info=True)
            raise

        # Validate response
        if not hasattr(response, "audio") or response.audio is None:
            logging.error("Higgs response contains no audio: %r", response)
            raise RuntimeError("Higgs Audio generation failed to produce audio.")
        if not hasattr(response, "sampling_rate") or response.sampling_rate is None:
            logging.error("Higgs response contains no sampling rate: %r", response)
            raise RuntimeError("Higgs Audio generation failed to produce a sampling rate.")

        try:
            audio_waveform = response.audio.astype(np.float32)
            sample_rate = int(response.sampling_rate)
            logging.debug(
                "Generated audio: shape=%s, sample_rate=%d",
                getattr(audio_waveform, "shape", None),
                sample_rate,
            )
            return audio_waveform, sample_rate
        except Exception:
            logging.error("Failed to extract audio from Higgs response", exc_info=True)
            raise


###############################################################################
# Worker threads for background processing
###############################################################################


class ScriptParsingWorker(QThread):
    """
    Worker that performs all text processing (chapter parsing and LLM script
    generation) first. It does not perform any audio synthesis. When
    completed, it emits a ``scripts_ready`` signal carrying the list of
    parsed chapter scripts.
    """

    progress = Signal(int, str)
    error = Signal(str)
    finished = Signal()
    scripts_ready = Signal(object)  # emits List[Tuple[str, str]]

    def __init__(self, input_path: Path, model_name: str) -> None:
        super().__init__()
        self.input_path = input_path
        self.model_name = model_name
        self._abort = False

    def run(self) -> None:
        try:
            parser = DocumentParser()
            # Start reading document
            self.progress.emit(0, "Reading document...")
            text, chapters = parser.parse(self.input_path)
            if not chapters:
                chapters = [("Untitled", slice(0, len(text)))]
            lm = LMClient(model_name=self.model_name)
            # Prepare to split chapters into paragraphs and compute total paragraphs
            chapters_list: List[Tuple[str, List[str], slice]] = []
            total_paragraphs = 0
            for (title, slc) in chapters:
                chapter_lines = text.splitlines()[slc]
                chapter_text = "\n".join(chapter_lines)
                # Split chapter into paragraphs on blank lines.  Remove empty paragraphs.
                paragraphs = [p.strip() for p in re.split(r"\n\s*\n", chapter_text) if p.strip()]
                chapters_list.append((title, paragraphs, slc))
                total_paragraphs += len(paragraphs) if paragraphs else 1
            # Now process each paragraph and assemble scripts
            scripts: List[Tuple[str, str]] = []
            processed_paragraphs = 0
            for ch_idx, (title, paragraphs, slc) in enumerate(chapters_list, 1):
                if self._abort:
                    self.progress.emit(100, "Operation aborted")
                    return
                # Character and word count for logging
                chapter_lines = text.splitlines()[slc]
                char_count = sum(len(line) for line in chapter_lines)
                word_count = sum(len(line.split()) for line in chapter_lines)
                logging.debug(
                    "Chapter '%s' length: %d characters, %d words", title, char_count, word_count
                )
                # Prepare full chapter text for context
                chapter_text = "\n".join(chapter_lines)
                # If no paragraphs detected (empty chapter), treat entire chapter as one paragraph
                if not paragraphs:
                    paragraphs = [chapter_text]
                script_parts: List[str] = []
                for p_idx, paragraph in enumerate(paragraphs, 1):
                    if self._abort:
                        self.progress.emit(100, "Operation aborted")
                        return
                    # Progress update: compute within 0-50 range based on total paragraphs
                    processed_ratio = processed_paragraphs / total_paragraphs if total_paragraphs else 0
                    self.progress.emit(
                        int(processed_ratio * 50),
                        f"Parsing {title}: paragraph {p_idx}/{len(paragraphs)} ({char_count} chars, {word_count} words)...",
                    )
                    # Parse the paragraph with context
                    try:
                        part_script = lm.parse_paragraph(chapter_text, paragraph)
                    except Exception as exc:
                        raise
                    script_parts.append(part_script)
                    processed_paragraphs += 1
                # After finishing all paragraphs in this chapter, update progress
                processed_ratio = processed_paragraphs / total_paragraphs if total_paragraphs else 1
                self.progress.emit(
                    int(processed_ratio * 50),
                    f"Parsed {title} ({char_count} chars, {word_count} words)"
                )
                # Combine script parts separated by a blank line to preserve paragraph boundaries
                full_script = "\n\n".join([s for s in script_parts if s])
                scripts.append((title, full_script))
            # Parsing complete: indicate 50% progress and prompt user
            self.progress.emit(50, "Text processing complete. Please release LM Studio and click Continue.")
            # Emit parsed scripts for next stage
            self.scripts_ready.emit(scripts)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    def abort(self) -> None:
        self._abort = True


class AudioGenerationWorker(QThread):
    """
    Worker that performs audio synthesis for the list of parsed scripts.
    It starts after text processing is finished and the user has released
    LM Studio to free GPU memory. Progress values run from 50 to 100.
    """

    progress = Signal(int, str)
    error = Signal(str)
    finished = Signal()

    def __init__(self, scripts: List[Tuple[str, str]], output_dir: Path, voices: Dict[str, Optional[Path]]) -> None:
        super().__init__()
        self.scripts = scripts
        self.output_dir = output_dir
        self.voice_mapping = voices
        self._abort = False

    def run(self) -> None:
        try:
            tts = TTSGenerator(self.voice_mapping)
            total = len(self.scripts) if self.scripts else 1
            for idx, (title, script) in enumerate(self.scripts, 1):
                if self._abort:
                    self.progress.emit(100, "Operation aborted")
                    return
                # Determine output filename
                chapter_name = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_") or f"chapter_{idx}"
                out_path = self.output_dir / f"{chapter_name}.wav"
                # Disk space check
                if not check_disk_space(self.output_dir, 2 * 1024 * 1024 * 1024):
                    raise RuntimeError("Not enough disk space for output. At least 2 GB is required.")
                # Progress for synthesis (50-100 range)
                self.progress.emit(
                    50 + int((idx - 1) / total * 50), f"Generating audio for {title}..."
                )
                tts.generate_chapter(script, out_path)
                # Progress update after completion
                self.progress.emit(
                    50 + int(idx / total * 50), f"Completed {title}"
                )
            # All audio generated
            self.progress.emit(100, "All chapters processed")
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.finished.emit()

    def abort(self) -> None:
        self._abort = True


###############################################################################
# Main application window
###############################################################################


class MainWindow(QMainWindow):
    """Main GUI window for the audiobook generator."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Audiobook Generator")
        self.setMinimumSize(800, 600)

        # State
        self.voice_mapping: Dict[str, Optional[Path]] = self._load_voice_mapping()
        # Background workers.  During text processing we use parse_worker,
        # afterwards we run audio_worker.  Only one worker runs at a time.
        self.parse_worker: Optional[ScriptParsingWorker] = None
        self.audio_worker: Optional[AudioGenerationWorker] = None
        self.current_worker: Optional[QThread] = None

        # Widgets
        self.input_edit = QLineEdit()
        self.input_edit.setReadOnly(True)
        self.input_browse = QPushButton("Browse…")
        self.input_browse.clicked.connect(self.browse_input)

        self.output_edit = QLineEdit()
        self.output_edit.setReadOnly(True)
        self.output_browse = QPushButton("Select Folder…")
        self.output_browse.clicked.connect(self.browse_output)

        self.model_combo = QComboBox()
        self.model_combo.addItem("LLM Default", "default")
        self.model_combo.addItem("Qwen-7B-Chat", "TheBloke/Qwen2_5-7B-Instruct-AWQ")
        self.model_combo.addItem("Vicuna-13B-Chat", "vicuna-13b")
        self.model_combo.setCurrentIndex(0)

        self.speaker_table = QTableWidget(0, 2)
        self.speaker_table.setHorizontalHeaderLabels(["Speaker", "Reference Audio"])
        self.speaker_table.horizontalHeader().setStretchLastSection(True)
        self.speaker_table.verticalHeader().setVisible(False)
        self.speaker_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.speaker_table.itemDoubleClicked.connect(self.assign_voice)

        self.log_edit = QTextEdit()
        self.log_edit.setReadOnly(True)

        self.progress_bar = QProgressBar()

        self.start_button = QPushButton("Generate Audiobook")
        self.start_button.clicked.connect(self.start_generation)
        self.stop_button = QPushButton("Abort")
        self.stop_button.clicked.connect(self.abort_generation)
        self.stop_button.setEnabled(False)

        # Layout
        form_layout = QFormLayout()
        form_layout.addRow("Input File", self._hbox(self.input_edit, self.input_browse))
        form_layout.addRow("Output Folder", self._hbox(self.output_edit, self.output_browse))
        form_layout.addRow("Model", self.model_combo)
        form_layout.addRow("Speakers", self.speaker_table)

        btn_layout = QHBoxLayout()
        btn_layout.addWidget(self.start_button)
        btn_layout.addWidget(self.stop_button)

        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.addLayout(form_layout)
        main_layout.addWidget(self.log_edit)
        main_layout.addWidget(self.progress_bar)
        main_layout.addLayout(btn_layout)
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Menu for saving/loading voices
        toolbar = QToolBar("File")
        self.addToolBar(toolbar)
        load_action = QAction("Load Voice Map", self)
        load_action.triggered.connect(self.load_voice_map)
        toolbar.addAction(load_action)
        save_action = QAction("Save Voice Map", self)
        save_action.triggered.connect(self.save_voice_map)
        toolbar.addAction(save_action)

        # Add Tools menu with diagnostics
        self._add_menu()

    # ------------------------------------------------------------------
    # Layout helper
    def _hbox(self, *widgets: QWidget) -> QWidget:
        """Return a QWidget containing the given widgets horizontally."""
        container = QWidget()
        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        for w in widgets:
            layout.addWidget(w)
        container.setLayout(layout)
        return container

    # ------------------------------------------------------------------
    # Menu helper
    def _add_menu(self) -> None:
        """Add a menu bar with a Tools menu for diagnostics."""
        if not PYSIDE_OK:
            return
        menubar = QMenuBar(self)
        tools_menu = QMenu("&Tools", self)
        diag_action = QAction("Run Diagnostics", self)
        diag_action.triggered.connect(self._on_run_diagnostics)
        tools_menu.addAction(diag_action)
        menubar.addMenu(tools_menu)
        self.setMenuBar(menubar)

    def _on_run_diagnostics(self) -> None:
        """Run diagnostics and show a short summary to the user."""
        try:
            diag = Diagnostics.run()
        except Exception as exc:
            diag = f"Diagnostics failed: {exc}"
            logging.error("Diagnostics execution failed", exc_info=True)
        summary_lines = diag.splitlines()
        display = "\n".join(summary_lines[:20])
        if len(summary_lines) > 20:
            display += "\n... (see debug.log for full report)"
        QMessageBox.information(self, "Diagnostics", display)

    # ------------------------------------------------------------------
    # File dialogs and voice assignment
    def browse_input(self) -> None:
        """Handle the input file selection."""
        filename, _ = QFileDialog.getOpenFileName(self, "Select Document", str(Path.home()), "Text/Word Files (*.txt *.docx)")
        if filename:
            self.input_edit.setText(filename)
            # Clear speakers table when a new input is selected
            self.speaker_table.setRowCount(0)

    def browse_output(self) -> None:
        """Handle the output directory selection."""
        directory = QFileDialog.getExistingDirectory(self, "Select Output Folder", str(Path.home()))
        if directory:
            self.output_edit.setText(directory)

    def assign_voice(self, item: QTableWidgetItem) -> None:
        """Open a file dialog to assign or change a reference voice for the selected speaker."""
        row = item.row()
        speaker_item = self.speaker_table.item(row, 0)
        if not speaker_item:
            return
        speaker = speaker_item.text()
        current_path_item = self.speaker_table.item(row, 1)
        start_dir = (
            str(Path(current_path_item.text()).parent)
            if current_path_item and current_path_item.text()
            else str(Path.home())
        )
        filename, _ = QFileDialog.getOpenFileName(self, f"Select reference audio for {speaker}", start_dir, "Audio Files (*.wav *.mp3)")
        if filename:
            path = Path(filename)
            self.voice_mapping[speaker] = path
            self.speaker_table.setItem(row, 1, QTableWidgetItem(str(path)))

    # ------------------------------------------------------------------
    # Generation control
    def start_generation(self) -> None:
        """Begin processing the selected document and generating audio in two phases."""
        input_path_str = self.input_edit.text().strip()
        output_dir_str = self.output_edit.text().strip()
        if not input_path_str or not output_dir_str:
            QMessageBox.warning(self, "Missing Information", "Please select both an input file and an output folder.")
            return
        input_path = Path(input_path_str)
        output_dir = Path(output_dir_str)
        if not input_path.exists():
            QMessageBox.critical(self, "Invalid Input", "The selected input file does not exist.")
            return
        if not output_dir.exists():
            QMessageBox.critical(self, "Invalid Output", "The selected output directory does not exist.")
            return
        self.output_dir = output_dir  # store for audio stage
        model_name = self.model_combo.currentData()
        # Save voice mapping before running
        self._save_voice_mapping()
        # Start the script parsing worker
        self.parse_worker = ScriptParsingWorker(input_path, model_name)
        self.current_worker = self.parse_worker
        self.parse_worker.progress.connect(self.update_progress)
        self.parse_worker.error.connect(self.worker_error)
        self.parse_worker.finished.connect(self.parse_worker_finished)
        self.parse_worker.scripts_ready.connect(self.on_scripts_ready)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.log_edit.append("Starting text processing...\n")
        self.parse_worker.start()

    def abort_generation(self) -> None:
        """Request cancellation of the current generation (either parsing or audio)."""
        if self.current_worker:
            # Signal the worker to abort
            try:
                self.current_worker.abort()  # type: ignore[attr-defined]
            except Exception:
                pass
        self.stop_button.setEnabled(False)

    def update_progress(self, value: int, message: str) -> None:
        """Update the progress bar and log with a status message."""
        self.progress_bar.setValue(value)
        self.log_edit.append(message)
        self.log_edit.verticalScrollBar().setValue(self.log_edit.verticalScrollBar().maximum())

    def worker_error(self, message: str) -> None:
        """Handle errors emitted from any worker thread."""
        QMessageBox.critical(self, "Error", message)
        # Reset UI state
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.current_worker = None

    def parse_worker_finished(self) -> None:
        """Handle completion of the script parsing worker."""
        # Parsing finished event is handled by on_scripts_ready.  Nothing else to do here.
        pass

    def audio_worker_finished(self) -> None:
        """Handle completion of the audio generation worker."""
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.current_worker = None
        self.log_edit.append("Finished.\n")
        self.progress_bar.setValue(100)

    def on_scripts_ready(self, scripts: object) -> None:
        """Received parsed scripts from the parsing worker. Prompt user to release LM Studio and continue."""
        # Cast scripts to expected type
        try:
            scripts_list: List[Tuple[str, str]] = list(scripts)  # type: ignore
        except Exception:
            self.worker_error("Invalid scripts data returned from parser")
            return
        # Store parsed scripts for later
        self.parsed_scripts = scripts_list  # type: ignore[attr-defined]
        # Prompt the user to release LM Studio before proceeding
        reply = QMessageBox.information(
            self,
            "Text Processing Complete",
            "Text processing is complete. Please close LM Studio to free GPU memory and click OK to continue with audio generation.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok,
        )
        if reply == QMessageBox.Ok:
            # Start audio generation
            self.start_audio_generation()
        else:
            # User canceled; re-enable start button
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            self.current_worker = None
            self.log_edit.append("Audio generation canceled by user.\n")

    def start_audio_generation(self) -> None:
        """Launch the audio generation worker with the parsed scripts."""
        # Ensure parsed_scripts exist
        scripts: List[Tuple[str, str]] = getattr(self, "parsed_scripts", [])  # type: ignore[attr-defined]
        if not scripts:
            QMessageBox.warning(self, "No Scripts", "There are no scripts to synthesise.")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            return
        # Launch audio worker
        self.audio_worker = AudioGenerationWorker(scripts, self.output_dir, dict(self.voice_mapping))
        self.current_worker = self.audio_worker
        self.audio_worker.progress.connect(self.update_progress)
        self.audio_worker.error.connect(self.worker_error)
        self.audio_worker.finished.connect(self.audio_worker_finished)
        # Keep start button disabled and show progress
        self.stop_button.setEnabled(True)
        self.audio_worker.start()

    # ------------------------------------------------------------------
    # Voice mapping persistence
    def load_voice_map(self) -> None:
        """Load a voice mapping from a user-selected JSON file."""
        filename, _ = QFileDialog.getOpenFileName(self, "Load Voice Map", str(Path.home()), "JSON Files (*.json)")
        if not filename:
            return
        with open(filename, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.voice_mapping = {k: Path(v) if v else None for k, v in data.items()}
        self.populate_speakers(list(self.voice_mapping.keys()))

    def save_voice_map(self) -> None:
        """Save the current voice mapping to a user-specified JSON file."""
        filename, _ = QFileDialog.getSaveFileName(self, "Save Voice Map", str(Path.home()), "JSON Files (*.json)")
        if not filename:
            return
        data = {k: str(v) if v else None for k, v in self.voice_mapping.items()}
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def populate_speakers(self, speakers: List[str]) -> None:
        """Populate the table of speakers with their reference paths."""
        self.speaker_table.setRowCount(len(speakers))
        for row, speaker in enumerate(speakers):
            speaker_item = QTableWidgetItem(speaker)
            self.speaker_table.setItem(row, 0, speaker_item)
            ref_path = self.voice_mapping.get(speaker)
            ref_item = QTableWidgetItem(str(ref_path) if ref_path else "")
            self.speaker_table.setItem(row, 1, ref_item)

    def _load_voice_mapping(self) -> Dict[str, Optional[Path]]:
        """Load voice mapping from a default JSON file if it exists."""
        mapping_path = Path(__file__).with_name("voices.json")
        if mapping_path.exists():
            with open(mapping_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {k: (Path(v) if v else None) for k, v in data.items()}
        return {}

    def _save_voice_mapping(self) -> None:
        """Persist the voice mapping to the default JSON file."""
        mapping_path = Path(__file__).with_name("voices.json")
        data = {k: str(v) if v else None for k, v in self.voice_mapping.items()}
        with open(mapping_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    # ------------------------------------------------------------------
    # Optional speaker parsing
    def parse_speakers_button(self) -> None:
        """Parse the first chapter to extract speaker names without generating audio."""
        input_path_str = self.input_edit.text().strip()
        if not input_path_str:
            QMessageBox.warning(self, "Missing Input", "Please select an input file first.")
            return
        parser = DocumentParser()
        text, chapters = parser.parse(Path(input_path_str))
        if not chapters:
            chapters = [("Untitled", slice(0, len(text)))]
        # Use first chapter for speaker extraction
        lm = LMClient(model_name=self.model_combo.currentData())
        chapter_text = "\n".join(text.splitlines()[chapters[0][1]])
        script = lm.parse_script(chapter_text)
        speakers = LMClient.extract_speakers(script)
        for s in speakers:
            if s not in self.voice_mapping:
                self.voice_mapping[s] = None
        self.populate_speakers(speakers)


def main() -> None:
    """Entry point for launching the GUI application."""
    if not PYSIDE_OK:
        raise RuntimeError(
            "PySide6 is not installed; the GUI cannot be started. "
            "Please install PySide6 or run with --diagnostics to debug your environment."
        )
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    # Support a command-line flag to run diagnostics without starting the GUI
    import argparse as _argparse

    parser = _argparse.ArgumentParser(description="Audiobook Generator")
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Run environment and dependency diagnostics, then exit",
    )
    args, unknown = parser.parse_known_args()

    if args.diagnostics:
        # Print diagnostics to stdout and exit
        print(Diagnostics.run())
        sys.exit(0)

    main()