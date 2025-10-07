from dataclasses import dataclass

from src.chunking import _split_overlong_sentence, chunk_text, split_into_sentences


@dataclass
class DummyTokenizer:
    max_tokens_per_word: int = 1

    def __call__(
        self,
        text,
        add_special_tokens=False,
        return_attention_mask=False,
        return_tensors=None,
    ):
        tokens = []
        for word in text.split():
            tokens.extend([0] * max(len(word) // self.max_tokens_per_word, 1))
        return {"input_ids": tokens}


@dataclass
class WordTokenizer:
    def __call__(
        self,
        text,
        add_special_tokens=False,
        return_attention_mask=False,
        return_tensors=None,
    ):
        return {"input_ids": [0] * len(text.split())}


def test_split_into_sentences_handles_basic_punctuation():
    sentences = split_into_sentences("Hello world. This is great! Right?")
    assert sentences == ["Hello world.", "This is great!", "Right?"]


def test_chunk_text_respects_token_limit():
    tokenizer = DummyTokenizer(max_tokens_per_word=2)
    text = "Paragraph one. " + "word " * 50 + "\n\nParagraph two is here."
    result = chunk_text(text, tokenizer, max_tokens=20)
    assert result.segments  # at least one segment
    assert all(len(tokenizer(segment)["input_ids"]) <= 20 for segment in result.segments)


def test_split_overlong_sentence_drops_overflow_word_from_fragment():
    tokenizer = WordTokenizer()
    sentence = "one two three four"
    fragments = list(_split_overlong_sentence(sentence, tokenizer, max_tokens=2))
    assert fragments == ["one two", "three four"]
