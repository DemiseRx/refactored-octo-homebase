"""Text chunking utilities used by the TTS pipeline."""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Iterable, List, Protocol, Sequence

try:  # pragma: no cover - optional dependency for runtime usage
    from transformers import PreTrainedTokenizerBase
except ImportError:  # pragma: no cover - used in lightweight test environments
    class PreTrainedTokenizerBase(Protocol):
        def __call__(
            self,
            text: str,
            add_special_tokens: bool = ...,  # noqa: D401
            return_attention_mask: bool = ...,
            return_tensors: str | None = ...,
        ) -> dict:
            ...


@dataclass
class ChunkingResult:
    """Container with the prepared segments and statistics."""

    segments: List[str]
    total_tokens: int
    average_tokens: float


def split_into_sentences(text: str) -> List[str]:
    """Split a paragraph into sentences using a light-weight heuristic."""
    if not text.strip():
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    cleaned = [sentence.strip() for sentence in sentences if sentence.strip()]
    return cleaned or [text.strip()]


def _split_overlong_sentence(
    sentence: str,
    tokenizer: PreTrainedTokenizerBase,
    max_tokens: int,
) -> Iterable[str]:
    words = sentence.split()
    if not words:
        return []
    fragment: List[str] = []
    for word in words:
        fragment.append(word)
        token_count = len(
            tokenizer(
                " ".join(fragment),
                add_special_tokens=False,
                return_attention_mask=False,
            )["input_ids"]
        )
        if token_count >= max_tokens:
            yield " ".join(fragment)
            fragment = []
    if fragment:
        yield " ".join(fragment)


def merge_until_token_limit(
    sentences: Sequence[str],
    tokenizer: PreTrainedTokenizerBase,
    max_tokens: int,
) -> Iterable[List[str]]:
    """Yield groups of sentences whose combined token length is below *max_tokens*."""
    current: List[str] = []
    current_token_count = 0
    for sentence in sentences:
        sentence_tokens = len(
            tokenizer(
                sentence,
                add_special_tokens=False,
                return_attention_mask=False,
                return_tensors=None,
            )["input_ids"]
        )
        if sentence_tokens > max_tokens and sentence:
            logging.debug("Sentence exceeds limit; splitting into sub-fragments")
            if current:
                yield current
                current = []
                current_token_count = 0
            for fragment in _split_overlong_sentence(
                sentence, tokenizer, max_tokens
            ):
                yield [fragment]
            continue

        if current and current_token_count + sentence_tokens > max_tokens:
            yield current
            current = [sentence]
            current_token_count = sentence_tokens
        else:
            current.append(sentence)
            current_token_count += sentence_tokens

    if current:
        yield current


def chunk_text(
    text: str,
    tokenizer: PreTrainedTokenizerBase,
    max_tokens: int,
) -> ChunkingResult:
    """Split *text* into manageable chunks for the TTS model."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs:
        return ChunkingResult([], 0, 0.0)

    segments: List[str] = []
    token_counts: List[int] = []

    for paragraph in paragraphs:
        sentences = split_into_sentences(paragraph)
        for group in merge_until_token_limit(sentences, tokenizer, max_tokens):
            chunk = " ".join(group).strip()
            if not chunk:
                continue
            chunk_token_count = len(
                tokenizer(
                    chunk,
                    add_special_tokens=False,
                    return_attention_mask=False,
                    return_tensors=None,
                )["input_ids"]
            )
            segments.append(chunk)
            token_counts.append(chunk_token_count)

    total_tokens = int(sum(token_counts))
    average_tokens = float(total_tokens) / len(token_counts) if token_counts else 0.0
    logging.debug(
        "Prepared %d segments (avg tokens %.1f).", len(segments), average_tokens
    )
    return ChunkingResult(segments=segments, total_tokens=total_tokens, average_tokens=average_tokens)

