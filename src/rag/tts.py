"""Text-to-speech via Hugging Face Inference API."""

from __future__ import annotations

import re

from rag.config import RAG_TTS_MAX_CHARS, RAG_TTS_MODEL, RAG_TTS_PROVIDER, get_hf_token

_TRUNC_SUFFIX = " … [truncated for speech]"


def prepare_speech_text(text: str) -> str:
    """Strip markup and cap length for TTS."""
    t = (text or "").strip()
    if not t:
        return ""
    t = re.sub(r"```[\s\S]*?```", " ", t)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"^#{1,6}\s+", "", t, flags=re.MULTILINE)
    t = re.sub(r"[*_~]+", "", t)
    t = re.sub(r"<[^>]+>", " ", t)
    t = " ".join(t.split())
    if len(t) > RAG_TTS_MAX_CHARS:
        keep = RAG_TTS_MAX_CHARS - len(_TRUNC_SUFFIX)
        t = t[:keep].rstrip() + _TRUNC_SUFFIX
    return t


def _map_hf_error(exc: Exception) -> str:
    if isinstance(exc, StopIteration):
        return (
            f"TTS model {RAG_TTS_MODEL!r} is not available on Hugging Face Inference. "
            "Set RAG_TTS_MODEL and RAG_TTS_PROVIDER in .env, or use browser speech (Listen falls back automatically)."
        )
    msg = str(exc).strip()
    lower = msg.lower()
    if "401" in lower or "unauthorized" in lower:
        return "Hugging Face token is invalid or missing. Set HF_TOKEN in your .env file."
    if "403" in lower or "forbidden" in lower:
        return (
            "Hugging Face Inference access denied for this token. "
            "Enable Inference Providers on your HF account, or rely on browser speech (Listen falls back automatically)."
        )
    if "429" in lower or "rate" in lower:
        return "Hugging Face rate limit reached. Try again in a moment."
    if "503" in lower or "unavailable" in lower or "loading" in lower:
        return "TTS model is loading or unavailable. Try again shortly."
    if msg:
        return f"Speech synthesis failed: {msg}"
    return f"Speech synthesis failed ({type(exc).__name__})."


def synthesize_speech(text: str, *, model: str | None = None) -> tuple[bytes, str]:
    """Return (audio_bytes, media_type)."""
    prepared = prepare_speech_text(text)
    if not prepared:
        raise ValueError("No text to speak after cleaning.")

    token = get_hf_token()
    if not token:
        raise ValueError(
            "HF_TOKEN is not set. Add your Hugging Face token to .env (see .env.example)."
        )

    from huggingface_hub import InferenceClient

    kwargs: dict = {"token": token}
    if RAG_TTS_PROVIDER:
        kwargs["provider"] = RAG_TTS_PROVIDER

    client = InferenceClient(**kwargs)
    model_id = (model or RAG_TTS_MODEL).strip() or RAG_TTS_MODEL

    try:
        audio_bytes = client.text_to_speech(prepared, model=model_id)
    except Exception as exc:
        raise RuntimeError(_map_hf_error(exc)) from exc

    if not isinstance(audio_bytes, bytes):
        raise RuntimeError("Unexpected response from Hugging Face TTS (expected audio bytes).")

    media_type = "audio/wav"
    if audio_bytes[:4] == b"ID3 " or audio_bytes[:2] in (b"\xff\xfb", b"\xff\xf3"):
        media_type = "audio/mpeg"
    elif audio_bytes[:4] == b"OggS":
        media_type = "audio/ogg"

    return audio_bytes, media_type
