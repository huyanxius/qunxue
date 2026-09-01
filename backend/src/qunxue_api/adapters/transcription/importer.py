"""Import existing transcript files without invoking an ASR engine."""

from __future__ import annotations

import re
from datetime import timedelta
from io import StringIO

import srt
import webvtt

from qunxue_api.adapters.research_materials import parse_material
from qunxue_api.modules.transcription import ParsedTranscript, TranscriptSegment

_SPEAKER_PREFIX = re.compile(r"^([^：:\n]{1,64})[：:]\s*(.+)$", re.DOTALL)


def parse_imported_transcript(
    *,
    filename: str,
    media_type: str | None,
    content: bytes,
) -> ParsedTranscript:
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if suffix == "srt":
        return _parse_srt(_decode(content))
    if suffix == "vtt":
        return _parse_vtt(_decode(content))
    if suffix in {"txt", "docx"}:
        return _parse_document(
            filename=filename,
            media_type=media_type,
            content=content,
        )
    raise ValueError("transcript import supports SRT, VTT, TXT, and DOCX")


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    except UnicodeDecodeError as error:
        raise ValueError("transcript text must use UTF-8") from error


def _parse_srt(text: str) -> ParsedTranscript:
    try:
        captions = tuple(srt.parse(text))
    except srt.SRTParseError as error:
        raise ValueError("invalid SRT transcript") from error
    segments = tuple(
        _segment(
            ordinal=index,
            text=caption.content,
            start_ms=_timedelta_ms(caption.start),
            end_ms=_timedelta_ms(caption.end),
        )
        for index, caption in enumerate(captions)
    )
    return ParsedTranscript(source_format="srt", segments=segments)


def _parse_vtt(text: str) -> ParsedTranscript:
    try:
        captions = tuple(webvtt.from_buffer(StringIO(text)))
    except (MalformedCaptionError, ValueError) as error:
        raise ValueError("invalid WebVTT transcript") from error
    segments = tuple(
        _segment(
            ordinal=index,
            text=caption.text,
            start_ms=round(caption.start_in_seconds * 1_000),
            end_ms=round(caption.end_in_seconds * 1_000),
            speaker=caption.voice or None,
        )
        for index, caption in enumerate(captions)
    )
    return ParsedTranscript(source_format="vtt", segments=segments)


def _parse_document(
    *,
    filename: str,
    media_type: str | None,
    content: bytes,
) -> ParsedTranscript:
    parsed = parse_material(filename=filename, media_type=media_type, content=content)
    segments = tuple(
        _segment(ordinal=index, text=block.text)
        for index, block in enumerate(parsed.blocks)
        if block.kind != "heading"
    )
    return ParsedTranscript(source_format=filename.rsplit(".", 1)[-1].lower(), segments=segments)


def _segment(
    *,
    ordinal: int,
    text: str,
    start_ms: int | None = None,
    end_ms: int | None = None,
    speaker: str | None = None,
) -> TranscriptSegment:
    normalized = text.strip()
    resolved_speaker = speaker.strip() if speaker and speaker.strip() else None
    if resolved_speaker is None:
        match = _SPEAKER_PREFIX.match(normalized)
        if match:
            resolved_speaker = match.group(1).strip()
            normalized = match.group(2).strip()
    return TranscriptSegment(
        ordinal=ordinal,
        text=normalized,
        start_ms=start_ms,
        end_ms=end_ms,
        speaker=resolved_speaker,
    )


def _timedelta_ms(value: timedelta) -> int:
    return round(value.total_seconds() * 1_000)


try:
    from webvtt.errors import MalformedCaptionError
except ImportError:  # pragma: no cover - compatibility with older webvtt-py
    MalformedCaptionError = ValueError
