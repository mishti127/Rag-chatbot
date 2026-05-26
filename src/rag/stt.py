"""Speech-to-text via Hugging Face Inference API."""

from __future__ import annotations

from rag.config import RAG_STT_MODEL, RAG_STT_PROVIDER, get_hf_token


def _map_hf_error(exc: Exception) -> str:
    if isinstance(exc, StopIteration):
        return (
            f"STT model {RAG_STT_MODEL!r} is not available on Hugging Face Inference. "
            "Set RAG_STT_MODEL and RAG_STT_PROVIDER in .env."
        )
    msg = str(exc).strip()
    lower = msg.lower()
    if "401" in lower or "unauthorized" in lower:
        return "Hugging Face token is invalid or missing. Set HF_TOKEN in your .env file."
    if "403" in lower or "forbidden" in lower:
        return (
            "Hugging Face Inference access denied for this token. "
            "Enable Inference Providers on your Hugging Face account."
        )
    if "429" in lower or "rate" in lower:
        return "Hugging Face rate limit reached. Try again in a moment."
    if "503" in lower or "unavailable" in lower or "loading" in lower:
        return "Speech model is loading or unavailable. Try again shortly."
    if msg:
        return f"Speech recognition failed: {msg}"
    return f"Speech recognition failed ({type(exc).__name__})."


def transcribe_audio(audio_bytes: bytes, *, model: str | None = None) -> str:
    """Transcribe audio bytes to text."""
    if not audio_bytes:
        raise ValueError("No audio data received.")

    token = get_hf_token()
    if not token:
        raise ValueError(
            "HF_TOKEN is not set. Add your Hugging Face token to .env (see .env.example)."
        )

    from huggingface_hub import InferenceClient

    kwargs: dict = {"token": token}
    if RAG_STT_PROVIDER:
        kwargs["provider"] = RAG_STT_PROVIDER

    client = InferenceClient(**kwargs)
    model_id = (model or RAG_STT_MODEL).strip() or RAG_STT_MODEL

    try:
        result = client.automatic_speech_recognition(audio_bytes, model=model_id)
    except Exception as exc:
        raise RuntimeError(_map_hf_error(exc)) from exc

    text = (getattr(result, "text", None) or "").strip()
    if not text and hasattr(result, "chunks") and result.chunks:
        parts = []
        for chunk in result.chunks:
            t = getattr(chunk, "text", None) or (chunk.get("text") if isinstance(chunk, dict) else "")
            if t:
                parts.append(str(t).strip())
        text = " ".join(parts).strip()

    if not text:
        raise RuntimeError("No speech detected in the recording.")
    return text
