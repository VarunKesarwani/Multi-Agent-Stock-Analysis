"""Bounded text chunks with stable document identities."""

import hashlib
from typing import Any, Sequence
from uuid import NAMESPACE_URL, uuid5

from src.chunking.markdown_structure import parse_markdown_structure
from src.utils.config import PipelineConfig


def split_bounded_text(text: str, max_chars: int, overlap_chars: int) -> list[str]:
    """Split text with guaranteed forward progress and a hard size ceiling."""
    if max_chars < 1 or not 0 <= overlap_chars < max_chars:
        raise ValueError("Chunk size must be positive and overlap smaller than size")
    text = str(text or "").strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    parts: list[str] = []
    start = 0
    text_length = len(text)
    minimum_break = max(1, max_chars // 2)

    while start < text_length:
        hard_end = min(start + max_chars, text_length)
        end = hard_end

        if hard_end < text_length:
            search_start = min(start + minimum_break, hard_end)
            candidates = (
                text.rfind("\n\n", search_start, hard_end),
                text.rfind("\n", search_start, hard_end),
                text.rfind(" ", search_start, hard_end),
            )
            valid_breaks = [position for position in candidates if position > start]
            if valid_breaks:
                end = max(valid_breaks)

        part = text[start:end].strip()
        if part:
            parts.append(part)
        if end >= text_length:
            break

        next_start = max(end - overlap_chars, start + 1)
        if next_start <= start:  # Defensive guard against future changes.
            next_start = end
        start = next_start

    return parts


def _stable_point_id(chunk: dict[str, Any], part_number: int, text: str) -> str:
    source = str(
        chunk.get("document_id")
        or chunk.get("source_file")
        or chunk.get("source_pdf")
        or "unknown"
    )
    identity = "|".join(
        (
            source,
            str(chunk.get("symbol") or ""),
            str(chunk.get("year") or ""),
            str(chunk.get("chunk_id") or ""),
            str(part_number),
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        )
    )
    return str(uuid5(NAMESPACE_URL, identity))


def prepare_chunks(
    chunks: Sequence[dict[str, Any]], max_chars: int, overlap_chars: int
) -> list[dict[str, Any]]:
    """Remove empty inputs, bound oversized chunks, and assign repeatable IDs."""
    prepared: list[dict[str, Any]] = []
    for chunk in chunks:
        parts = split_bounded_text(chunk.get("text", ""), max_chars, overlap_chars)
        for part_index, part in enumerate(parts):
            item = dict(chunk)
            item["text"] = part
            item["original_chunk_id"] = chunk.get("chunk_id")
            item["chunk_part"] = part_index + 1
            item["chunk_part_count"] = len(parts)
            item["point_id"] = _stable_point_id(chunk, part_index, part)
            prepared.append(item)
    return prepared


def chunk_markdown(markdown: str, metadata: dict, config: PipelineConfig) -> list[dict]:
    """Preserve heading/table boundaries and bound text with configured overlap."""
    result = []
    for index, block in enumerate(parse_markdown_structure(markdown)):
        block_text = block["text"].strip()
        # Do not apply company-specific navigation filters to educational text.
        for part, text in enumerate(
            split_bounded_text(
                block_text, config.max_chunk_chars, config.chunk_overlap_chars
            )
        ):
            result.append(
                {
                    **block,
                    **metadata,
                    "text": text,
                    "chunk_id": f"{metadata.get('page_number', 0)}:{index}:{part}",
                    "char_count": len(text),
                }
            )
    return result
