"""Gradio interface for the KaniTTS service."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import gradio as gr

from . import config
from .chunking import chunk_text
from .io_utils import load_text
from .tts_engine import GenerationSettings, KaniTTSService, MissingDependencyError


def _resolve_file_path(upload: Optional[gr.files.TempFile]) -> Optional[Path]:
    if upload is None:
        return None
    return Path(upload.name)


def _build_settings(
    temperature: float,
    top_p: float,
    repetition_penalty: float,
    max_new_tokens: int,
) -> GenerationSettings:
    return GenerationSettings(
        temperature=temperature,
        top_p=top_p,
        repetition_penalty=repetition_penalty,
        max_new_tokens=max_new_tokens,
    )


def _summarise_segments(segments) -> List[Dict[str, Any]]:
    summary = []
    for idx, segment in enumerate(segments, start=1):
        summary.append(
            {
                "segment": idx,
                "characters": len(segment.text),
                "duration_seconds": round(segment.duration_seconds, 2),
            }
        )
    return summary


def automatic_synthesis(
    text: str,
    file: Optional[gr.files.TempFile],
    voice: str,
    temperature: float,
    top_p: float,
    repetition_penalty: float,
    max_new_tokens: int,
    tts: KaniTTSService,
) -> tuple[str | None, str, List[Dict[str, Any]]]:
    try:
        file_path = _resolve_file_path(file)
        resolved_text = load_text(text, file_path)
        settings = _build_settings(
            temperature=temperature,
            top_p=top_p,
            repetition_penalty=repetition_penalty,
            max_new_tokens=max_new_tokens,
        )
        result = tts.synthesise_text(resolved_text, voice, settings=settings)
        message = (
            f"Generated {len(result.segments)} segments with voice '{voice}'. "
            f"Audio saved to {result.audio_path}."
        )
        return (
            str(result.audio_path),
            message,
            _summarise_segments(result.segments),
        )
    except MissingDependencyError as exc:
        logging.exception("Missing runtime dependency for synthesis")
        return None, str(exc), []
    except Exception as exc:  # pragma: no cover - relies on runtime environment
        logging.exception("Automatic synthesis failed")
        return None, f"Error: {exc}", []


def prepare_manual_session(
    text: str,
    file: Optional[gr.files.TempFile],
    voice: str,
    temperature: float,
    top_p: float,
    repetition_penalty: float,
    max_new_tokens: int,
    tts: KaniTTSService,
) -> tuple[List[str], Dict[str, Any], int, str, str, List[Dict[str, Any]]]:
    settings = _build_settings(
        temperature=temperature,
        top_p=top_p,
        repetition_penalty=repetition_penalty,
        max_new_tokens=max_new_tokens,
    )
    try:
        file_path = _resolve_file_path(file)
        resolved_text = load_text(text, file_path)
        chunking_result = chunk_text(
            resolved_text,
            tts.tokenizer,
            tts.max_input_tokens,
        )
        segments_text = chunking_result.segments
        if not segments_text:
            raise ValueError("No segments were generated from the input text.")

        summary = []
        for idx, segment in enumerate(segments_text, start=1):
            token_count = len(
                tts.tokenizer(
                    segment,
                    add_special_tokens=False,
                    return_attention_mask=False,
                )["input_ids"]
            )
            summary.append(
                {
                    "segment": idx,
                    "characters": len(segment),
                    "estimated_tokens": token_count,
                }
            )
        first_preview = segments_text[0]
        message = (
            f"Prepared {len(segments_text)} segments. Use 'Generate next segment' "
            "to render them individually."
        )
        return (
            segments_text,
            settings.__dict__,
            0,
            first_preview,
            message,
            summary,
        )
    except MissingDependencyError as exc:
        logging.exception("Missing runtime dependency for manual preparation")
        return [], settings.__dict__, 0, "", str(exc), []
    except Exception as exc:  # pragma: no cover
        logging.exception("Failed to prepare manual session")
        return [], settings.__dict__, 0, "", f"Error: {exc}", []


def manual_generate_next(
    segments: List[str],
    settings_dict: Dict[str, Any],
    index: int,
    voice: str,
    tts: KaniTTSService,
) -> tuple[str | None, int, str, str]:
    if not segments:
        return None, 0, "", "No segments available."
    if index >= len(segments):
        return None, index, "", "All segments have already been generated."

    settings = GenerationSettings(**settings_dict)
    try:
        segment_result = tts.synthesise_segments(
            [segments[index]],
            tts.speaker_id_for_label(voice),
            settings,
        )[0]
        audio_path = tts.save_waveform(segment_result.waveform)
        next_index = index + 1
        next_preview = segments[next_index] if next_index < len(segments) else ""
        message = (
            f"Segment {index + 1}/{len(segments)} saved to {audio_path}."
            + (" Manual session complete." if next_index >= len(segments) else "")
        )
        return str(audio_path), next_index, next_preview, message
    except MissingDependencyError as exc:
        logging.exception("Missing runtime dependency for manual synthesis")
        return None, index, "", str(exc)
    except Exception as exc:  # pragma: no cover
        logging.exception("Manual synthesis failed")
        return None, index, "", f"Error: {exc}"


def build_interface(tts: KaniTTSService) -> gr.Blocks:
    voices = tts.available_voices()

    with gr.Blocks(title="KaniTTS Local Service") as demo:
        gr.Markdown(
            """# KaniTTS Local Service

Generate natural, multi-speaker audio using the open KaniTTS model.\
Select **Automatic mode** for one-click synthesis or switch to **Manual mode**
when you want full control over each segment.
"""
        )

        with gr.Tab("Automatic mode"):
            auto_text = gr.Textbox(
                label="Text input",
                placeholder="Paste the text you want to narrate...",
                lines=10,
            )
            auto_file = gr.File(label="Or upload a text document", file_types=[".txt", ".docx", ".epub"])
            auto_voice = gr.Dropdown(
                label="Voice",
                choices=voices,
                value=config.DEFAULT_VOICE_LABEL,
            )
            with gr.Accordion("Advanced settings", open=False):
                auto_temperature = gr.Slider(
                    label="Temperature",
                    minimum=0.1,
                    maximum=2.0,
                    step=0.05,
                    value=config.DEFAULT_TEMPERATURE,
                )
                auto_top_p = gr.Slider(
                    label="Top-p",
                    minimum=0.1,
                    maximum=1.0,
                    step=0.05,
                    value=config.DEFAULT_TOP_P,
                )
                auto_rep_penalty = gr.Slider(
                    label="Repetition penalty",
                    minimum=0.5,
                    maximum=2.0,
                    step=0.05,
                    value=config.DEFAULT_REPETITION_PENALTY,
                )
                auto_max_tokens = gr.Slider(
                    label="Max new tokens",
                    minimum=256,
                    maximum=2048,
                    step=64,
                    value=config.DEFAULT_MAX_NEW_TOKENS,
                )
            auto_button = gr.Button("Synthesize")
            auto_audio = gr.Audio(label="Preview", type="filepath")
            auto_status = gr.Textbox(label="Status", interactive=False)
            auto_summary = gr.Dataframe(
                headers=["segment", "characters", "duration_seconds"],
                label="Segment summary",
            )

            auto_button.click(
                fn=lambda *args: automatic_synthesis(*args, tts=tts),
                inputs=[
                    auto_text,
                    auto_file,
                    auto_voice,
                    auto_temperature,
                    auto_top_p,
                    auto_rep_penalty,
                    auto_max_tokens,
                ],
                outputs=[auto_audio, auto_status, auto_summary],
            )

        with gr.Tab("Manual mode"):
            manual_text = gr.Textbox(
                label="Text input",
                placeholder="Paste the text to narrate...",
                lines=10,
            )
            manual_file = gr.File(label="Or upload a document", file_types=[".txt", ".docx", ".epub"])
            manual_voice = gr.Dropdown(
                label="Voice",
                choices=voices,
                value=config.DEFAULT_VOICE_LABEL,
            )
            with gr.Accordion("Advanced settings", open=False):
                manual_temperature = gr.Slider(
                    label="Temperature",
                    minimum=0.1,
                    maximum=2.0,
                    step=0.05,
                    value=config.DEFAULT_TEMPERATURE,
                )
                manual_top_p = gr.Slider(
                    label="Top-p",
                    minimum=0.1,
                    maximum=1.0,
                    step=0.05,
                    value=config.DEFAULT_TOP_P,
                )
                manual_rep_penalty = gr.Slider(
                    label="Repetition penalty",
                    minimum=0.5,
                    maximum=2.0,
                    step=0.05,
                    value=config.DEFAULT_REPETITION_PENALTY,
                )
                manual_max_tokens = gr.Slider(
                    label="Max new tokens",
                    minimum=256,
                    maximum=2048,
                    step=64,
                    value=config.DEFAULT_MAX_NEW_TOKENS,
                )

            prepare_button = gr.Button("Prepare manual session")
            manual_segments_state = gr.State([])
            manual_settings_state = gr.State({})
            manual_index_state = gr.State(0)

            manual_preview = gr.Textbox(
                label="Current segment preview",
                lines=6,
                interactive=False,
            )
            manual_log = gr.Textbox(label="Manual status", interactive=False)
            manual_notes = gr.Dataframe(
                headers=["segment", "characters", "estimated_tokens"],
                label="Segment overview",
            )

            next_button = gr.Button("Generate next segment")
            manual_audio = gr.Audio(label="Segment audio", type="filepath")

            prepare_button.click(
                fn=lambda *args: prepare_manual_session(*args, tts=tts),
                inputs=[
                    manual_text,
                    manual_file,
                    manual_voice,
                    manual_temperature,
                    manual_top_p,
                    manual_rep_penalty,
                    manual_max_tokens,
                ],
                outputs=[
                    manual_segments_state,
                    manual_settings_state,
                    manual_index_state,
                    manual_preview,
                    manual_log,
                    manual_notes,
                ],
            )

            next_button.click(
                fn=lambda segments, settings, index, voice: manual_generate_next(
                    segments, settings, index, voice, tts
                ),
                inputs=[manual_segments_state, manual_settings_state, manual_index_state, manual_voice],
                outputs=[manual_audio, manual_index_state, manual_preview, manual_log],
            )

    return demo

