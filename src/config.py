"""Configuration constants for the KaniTTS service."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

# Base directories -----------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# Model configuration --------------------------------------------------------

# Hugging Face identifiers for the language model and codec used by KaniTTS.
KANI_MODEL_ID = "nineninesix/kani-tts-370m"
KANI_CODEC_ID = "nvidia/nemo-nano-codec-22khz-0.6kbps-12.5fps"

# Default sampling parameters recommended by the model authors.
DEFAULT_TEMPERATURE = 1.4
DEFAULT_TOP_P = 0.95
DEFAULT_REPETITION_PENALTY = 1.1
DEFAULT_MAX_NEW_TOKENS = 1536

# Chunking -------------------------------------------------------------------

# Soft token limit used when chunking long passages. The value is lower than
# the model's upper bound to preserve quality and avoid overlong generations.
DEFAULT_MAX_INPUT_TOKENS = 1024

# Voices ---------------------------------------------------------------------

# Mapping of user friendly labels to the internal speaker identifiers expected
# by the model. The list mirrors the official Hugging Face space for KaniTTS
# and can be extended easily.
VOICE_MAP: Dict[str, str] = {
    "Andrew (English)": "andrew",
    "Angus (English, Scottish)": "angus",
    "Aria (English, American)": "aria",
    "David (English, British)": "david",
    "Emma (English, American)": "emma",
    "Freya (English, Australian)": "freya",
    "Jenny (English, Irish)": "jenny",
    "Lisa (English, General American)": "lisa",
    "Maria (Spanish)": "maria",
    "Martina (German)": "martina",
    "Seulgi (Korean)": "seulgi",
    "Thorsten (German)": "thorsten",
    "Xavier (French)": "xavier",
    "Yousef (Arabic)": "yousef",
}

DEFAULT_VOICE_LABEL = "Andrew (English)"
DEFAULT_SPEAKER_ID = VOICE_MAP[DEFAULT_VOICE_LABEL]

# API ------------------------------------------------------------------------

API_PREFIX = "/api"
SYNTHESIS_ROUTE = f"{API_PREFIX}/synthesize"

