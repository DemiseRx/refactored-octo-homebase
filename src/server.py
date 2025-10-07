"""FastAPI server exposing the KaniTTS functionality and Gradio UI."""
from __future__ import annotations

import logging
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Optional

import gradio as gr
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import config
from .io_utils import load_text
from .tts_engine import GenerationSettings, KaniTTSService, MissingDependencyError
from .ui import build_interface


class SynthesisRequest(BaseModel):
    text: Optional[str] = None
    file_path: Optional[str] = None
    voice: str = config.DEFAULT_VOICE_LABEL
    temperature: float = config.DEFAULT_TEMPERATURE
    top_p: float = config.DEFAULT_TOP_P
    repetition_penalty: float = config.DEFAULT_REPETITION_PENALTY
    max_new_tokens: int = config.DEFAULT_MAX_NEW_TOKENS
    return_segments: bool = False


def get_tts_service() -> KaniTTSService:
    return KaniTTSService()


def _run_synthesis(
    tts: KaniTTSService,
    text: str,
    request: SynthesisRequest,
):
    settings = GenerationSettings(
        temperature=request.temperature,
        top_p=request.top_p,
        repetition_penalty=request.repetition_penalty,
        max_new_tokens=request.max_new_tokens,
    )
    result = tts.synthesise_text(text, request.voice, settings=settings)
    response = {
        "audio_file": str(result.audio_path),
        "voice": request.voice,
        "segment_count": len(result.segments),
        "duration_seconds": round(
            sum(segment.duration_seconds for segment in result.segments), 2
        ),
    }
    if request.return_segments:
        response["segments"] = [
            {
                "index": idx + 1,
                "text": segment.text,
                "duration_seconds": round(segment.duration_seconds, 2),
            }
            for idx, segment in enumerate(result.segments)
        ]
    return response


def create_app(tts: Optional[KaniTTSService] = None) -> FastAPI:
    tts_service = tts or KaniTTSService()
    app = FastAPI(title="KaniTTS Local Service", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    interface = build_interface(tts_service)
    gr.mount_gradio_app(app, interface, path="/ui")

    @app.post(config.SYNTHESIS_ROUTE)
    async def synthesize(payload: SynthesisRequest) -> dict:
        try:
            file_path = Path(payload.file_path) if payload.file_path else None
            text = load_text(payload.text, file_path)
            return _run_synthesis(tts_service, text, payload)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except MissingDependencyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover
            logging.exception("Unhandled synthesis error")
            raise HTTPException(status_code=500, detail=str(exc)) from exc

    @app.post(f"{config.API_PREFIX}/synthesize/file")
    async def synthesize_file(
        file: UploadFile = File(...),
        voice: str = Form(config.DEFAULT_VOICE_LABEL),
        temperature: float = Form(config.DEFAULT_TEMPERATURE),
        top_p: float = Form(config.DEFAULT_TOP_P),
        repetition_penalty: float = Form(config.DEFAULT_REPETITION_PENALTY),
        max_new_tokens: int = Form(config.DEFAULT_MAX_NEW_TOKENS),
        return_segments: bool = Form(False),
    ) -> dict:
        suffix = Path(file.filename or "text.txt").suffix
        with NamedTemporaryFile(delete=False, suffix=suffix) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(await file.read())

        try:
            payload = SynthesisRequest(
                text=None,
                file_path=str(temp_path),
                voice=voice,
                temperature=temperature,
                top_p=top_p,
                repetition_penalty=repetition_penalty,
                max_new_tokens=max_new_tokens,
                return_segments=return_segments,
            )
            text = load_text(None, temp_path)
            return _run_synthesis(tts_service, text, payload)
        except MissingDependencyError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:  # pragma: no cover
            logging.exception("File-based synthesis failed")
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            try:
                temp_path.unlink()
            except OSError:
                pass

    @app.get("/")
    async def root() -> dict:
        return {
            "message": "KaniTTS service is running.",
            "ui": "/ui",
            "synthesis_endpoint": config.SYNTHESIS_ROUTE,
        }

    return app


app = create_app()

