"""Text-to-speech module tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from rag.tts import prepare_speech_text, synthesize_speech


def test_prepare_speech_text_strips_markdown() -> None:
    raw = "# Title\n\n**Bold** text with `code` and [link](http://x.com)."
    out = prepare_speech_text(raw)
    assert "Title" in out
    assert "**" not in out
    assert "`" not in out
    assert "link" in out


def test_prepare_speech_text_truncates() -> None:
    with patch("rag.tts.RAG_TTS_MAX_CHARS", 50):
        out = prepare_speech_text("word " * 30)
        assert len(out) <= 50
        assert "truncated" in out


def test_synthesize_speech_requires_token() -> None:
    with patch("rag.tts.get_hf_token", return_value=""):
        with pytest.raises(ValueError, match="HF_TOKEN"):
            synthesize_speech("Hello")


def test_synthesize_speech_calls_hf_client() -> None:
    fake_audio = b"RIFF" + b"\x00" * 100
    mock_client = MagicMock()
    mock_client.text_to_speech.return_value = fake_audio

    with (
        patch("rag.tts.get_hf_token", return_value="hf_test"),
        patch("huggingface_hub.InferenceClient", return_value=mock_client),
    ):
        data, media_type = synthesize_speech("Hello world", model="facebook/mms-tts-eng")

    assert data == fake_audio
    assert media_type.startswith("audio/")
    mock_client.text_to_speech.assert_called_once()
