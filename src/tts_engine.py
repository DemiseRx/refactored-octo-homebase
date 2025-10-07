"""Core text-to-speech pipeline powered by KaniTTS."""
from __future__ import annotations

import logging
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional, Sequence

import numpy as np

from . import config
from .chunking import ChunkingResult, chunk_text


@dataclass
class GenerationSettings:
    """Sampling parameters forwarded to the language model."""

    temperature: float = config.DEFAULT_TEMPERATURE
    top_p: float = config.DEFAULT_TOP_P
    repetition_penalty: float = config.DEFAULT_REPETITION_PENALTY
    max_new_tokens: int = config.DEFAULT_MAX_NEW_TOKENS


@dataclass
class SegmentResult:
    """A single generated audio segment."""

    text: str
    waveform: np.ndarray
    duration_seconds: float


@dataclass
class SynthesisResult:
    """Full synthesis output bundled with metadata."""

    audio_path: Path
    combined_waveform: np.ndarray
    segments: List[SegmentResult]
    chunking: ChunkingResult
    generation_settings: GenerationSettings
    speaker_id: str


class MissingDependencyError(RuntimeError):
    """Raised when optional heavy dependencies are not installed."""


class KaniTTSService:
    """High level façade around the KaniTTS + NanoCodec models."""

    sample_rate: int = 22_050

    def __init__(
        self,
        model_id: str = config.KANI_MODEL_ID,
        codec_id: str = config.KANI_CODEC_ID,
        max_input_tokens: int = config.DEFAULT_MAX_INPUT_TOKENS,
    ) -> None:
        self.model_id = model_id
        self.codec_id = codec_id
        self.max_input_tokens = max_input_tokens
        self._tokenizer = None
        self._model = None
        self._codec = None
        self._start_of_speech: Optional[int] = None
        self._end_of_speech: Optional[int] = None
        logging.debug(
            "KaniTTSService initialised (model=%s, codec=%s)", model_id, codec_id
        )

    # ------------------------------------------------------------------
    # Lazy loading helpers
    # ------------------------------------------------------------------
    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return

        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
            from nemo.collections.tts.models import AudioCodecModel
        except ImportError as exc:  # pragma: no cover - depends on optional deps
            raise MissingDependencyError(
                "KaniTTS runtime dependencies are missing. Please install torch, "
                "transformers, nemo_toolkit[tts], librosa and soundfile before "
                "running the service."
            ) from exc

        device = "cuda" if torch.cuda.is_available() else "cpu"
        dtype = torch.bfloat16 if torch.cuda.is_available() else torch.float32

        logging.info("Loading tokenizer %s", self.model_id)
        tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, trust_remote_code=True
        )
        logging.info("Loading language model %s", self.model_id)
        model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            trust_remote_code=True,
            torch_dtype=dtype,
            device_map="auto" if torch.cuda.is_available() else None,
        )
        logging.info("Loading audio codec %s", self.codec_id)
        codec = AudioCodecModel.from_pretrained(self.codec_id)
        codec = codec.to(device)
        codec.eval()

        self._tokenizer = tokenizer
        self._model = model.to(device) if not torch.cuda.is_available() else model
        self._codec = codec
        self._device = device

        self._resolve_special_tokens()

    def _resolve_special_tokens(self) -> None:
        assert self._tokenizer is not None and self._model is not None
        tokenizer = self._tokenizer
        model = self._model

        start_candidates = [
            getattr(model.config, "start_of_speech_token_id", None),
            getattr(model.generation_config, "start_of_speech_token_id", None),
        ]
        end_candidates = [
            getattr(model.config, "end_of_speech_token_id", None),
            getattr(model.generation_config, "end_of_speech_token_id", None),
        ]

        vocab = tokenizer.get_vocab()
        token_candidates = [
            "<|startofspeech|>",
            "<|start_of_speech|>",
            "<|startofaudio|>",
        ]
        for candidate in token_candidates:
            if candidate in vocab:
                start_candidates.append(tokenizer.convert_tokens_to_ids(candidate))
        token_candidates = [
            "<|endofspeech|>",
            "<|end_of_speech|>",
            "<|endofaudio|>",
        ]
        for candidate in token_candidates:
            if candidate in vocab:
                end_candidates.append(tokenizer.convert_tokens_to_ids(candidate))

        self._start_of_speech = next(
            (token for token in start_candidates if isinstance(token, int)), None
        )
        self._end_of_speech = next(
            (token for token in end_candidates if isinstance(token, int)), None
        )
        if self._end_of_speech is None:
            self._end_of_speech = tokenizer.eos_token_id
        if self._start_of_speech is None:
            logging.warning(
                "Could not determine start_of_speech token automatically; "
                "falling back to prompt boundary heuristics."
            )

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    @property
    def tokenizer(self):
        self._ensure_loaded()
        assert self._tokenizer is not None
        return self._tokenizer

    def available_voices(self) -> List[str]:
        return list(config.VOICE_MAP.keys())

    def speaker_id_for_label(self, label: str) -> str:
        return config.VOICE_MAP.get(label, config.DEFAULT_SPEAKER_ID)

    def save_waveform(self, waveform: np.ndarray) -> Path:
        """Persist a waveform to disk using the standard naming convention."""
        return self._write_waveform_to_file(waveform)

    # ------------------------------------------------------------------
    # Synthesis
    # ------------------------------------------------------------------
    def synthesise_segments(
        self,
        segments: Sequence[str],
        speaker_id: str,
        settings: GenerationSettings,
        progress_callback: Optional[Callable[[int, str, float], None]] = None,
    ) -> List[SegmentResult]:
        self._ensure_loaded()
        assert self._tokenizer is not None and self._model is not None
        tokenizer = self._tokenizer
        model = self._model

        import torch  # Imported lazily with the rest of the stack

        outputs: List[SegmentResult] = []
        for index, segment in enumerate(segments):
            prompt = f"{speaker_id}: {segment.strip()}" if speaker_id else segment.strip()
            encoded = tokenizer(
                prompt,
                return_tensors="pt",
                padding=False,
            )
            input_ids = encoded["input_ids"].to(model.device)
            attention_mask = encoded.get("attention_mask")
            if attention_mask is not None:
                attention_mask = attention_mask.to(model.device)

            logging.info("Generating audio for segment %d (tokens=%d)", index + 1, input_ids.shape[-1])
            start_time = time.perf_counter()
            with torch.inference_mode():
                generated = model.generate(
                    input_ids=input_ids,
                    attention_mask=attention_mask,
                    do_sample=True,
                    temperature=settings.temperature,
                    top_p=settings.top_p,
                    repetition_penalty=settings.repetition_penalty,
                    max_new_tokens=settings.max_new_tokens,
                    eos_token_id=self._end_of_speech,
                    pad_token_id=tokenizer.eos_token_id,
                )
            elapsed = time.perf_counter() - start_time
            logging.debug("Generation completed in %.2fs", elapsed)

            audio_tokens = self._extract_audio_tokens(
                generated[0].tolist(), input_ids[0].tolist()
            )
            waveform = self._decode_audio_tokens(audio_tokens)
            duration = float(len(waveform) / self.sample_rate)
            outputs.append(
                SegmentResult(text=segment, waveform=waveform, duration_seconds=duration)
            )
            if progress_callback:
                progress_callback(index, segment, duration)

        return outputs

    def synthesise_text(
        self,
        text: str,
        speaker_label: str,
        settings: Optional[GenerationSettings] = None,
        progress_callback: Optional[Callable[[int, str, float], None]] = None,
    ) -> SynthesisResult:
        settings = settings or GenerationSettings()
        if not text or not text.strip():
            raise ValueError("Input text must not be empty.")
        speaker_id = self.speaker_id_for_label(speaker_label)
        chunking_result = chunk_text(text, self.tokenizer, self.max_input_tokens)
        segments = chunking_result.segments or [text.strip()]
        segment_results = self.synthesise_segments(
            segments,
            speaker_id,
            settings,
            progress_callback=progress_callback,
        )

        combined_waveform = (
            np.concatenate([segment.waveform for segment in segment_results])
            if segment_results
            else np.array([], dtype=np.float32)
        )
        audio_path = self._write_waveform_to_file(combined_waveform)
        return SynthesisResult(
            audio_path=audio_path,
            combined_waveform=combined_waveform,
            segments=segment_results,
            chunking=chunking_result,
            generation_settings=settings,
            speaker_id=speaker_id,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _extract_audio_tokens(
        self, generated: Sequence[int], prompt_ids: Sequence[int]
    ) -> List[int]:
        """Extract the codec token sequence from the generated ids."""
        if self._start_of_speech is not None and self._start_of_speech in generated:
            start_index = generated.index(self._start_of_speech) + 1
        else:
            start_index = len(prompt_ids)

        if self._end_of_speech is not None and self._end_of_speech in generated:
            end_index = generated.index(self._end_of_speech, start_index)
        else:
            end_index = len(generated)

        audio_tokens = list(generated[start_index:end_index])
        if not audio_tokens:
            raise RuntimeError("No audio tokens generated by the model.")
        return audio_tokens

    def _decode_audio_tokens(self, tokens: Sequence[int]) -> np.ndarray:
        assert self._codec is not None
        import torch  # Lazy import to avoid hard dependency at module import time

        tokens_tensor = torch.tensor([tokens], dtype=torch.int32, device=self._codec.device)
        lengths = torch.tensor([tokens_tensor.shape[-1]], dtype=torch.int32, device=self._codec.device)
        with torch.inference_mode():
            waveform = self._codec.decode(tokens=tokens_tensor, tokens_len=lengths)
        return waveform.squeeze().cpu().numpy()

    def _write_waveform_to_file(self, waveform: np.ndarray) -> Path:
        from soundfile import write  # Lazy import

        output_dir = config.OUTPUT_DIR
        output_dir.mkdir(exist_ok=True)
        filename = f"kani_tts_{uuid.uuid4().hex}.wav"
        destination = output_dir / filename
        if waveform.size == 0:
            raise ValueError("Cannot write an empty waveform to disk.")
        write(destination, waveform, self.sample_rate)
        logging.info("Saved audio to %s", destination)
        return destination

