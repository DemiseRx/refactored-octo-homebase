"""Entry point that launches the FastAPI server."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import uvicorn

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))
    from src.server import app  # type: ignore
else:  # pragma: no cover - normal package import path
    from .server import app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(app, host="0.0.0.0", port=8000)
