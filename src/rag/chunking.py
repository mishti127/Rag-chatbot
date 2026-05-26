from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    text: str
    source: str
    chunk_index: int


def chunk_text(
    text: str,
    source: str,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> list[TextChunk]:
    text = text.strip()
    if not text:
        return []
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")
    chunks: list[TextChunk] = []
    start = 0
    idx = 0
    n = len(text)
    while start < n:
        end = min(start + chunk_size, n)
        piece = text[start:end].strip()
        if piece:
            chunks.append(TextChunk(text=piece, source=source, chunk_index=idx))
            idx += 1
        if end >= n:
            break
        start = end - chunk_overlap
    return chunks
