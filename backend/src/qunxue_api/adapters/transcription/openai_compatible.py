"""Adapter for an existing OpenAI-compatible transcription endpoint."""

from __future__ import annotations

from typing import Any

import httpx

from qunxue_api.modules.transcription import (
    ParsedTranscript,
    ProcessingLocation,
    TranscriptionError,
    TranscriptSegment,
)


class OpenAICompatibleTranscriptionProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        processing_location: ProcessingLocation,
        timeout_seconds: float = 180,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._processing_location = processing_location
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def available(self) -> bool:
        return bool(self._base_url and self._api_key and self._model)

    @property
    def name(self) -> str:
        return f"openai-compatible:{self._model}"

    @property
    def processing_location(self) -> ProcessingLocation:
        return self._processing_location

    def transcribe(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
    ) -> ParsedTranscript:
        try:
            response = self._client.post(
                f"{self._base_url}/audio/transcriptions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                data={"model": self._model, "response_format": "diarized_json"},
                files={"file": (filename, content, media_type)},
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise TranscriptionError("transcription provider request failed") from error
        raw_segments = payload.get("segments") if isinstance(payload, dict) else None
        if not isinstance(raw_segments, list) or not raw_segments:
            raise TranscriptionError("transcription provider returned no timed segments")
        segments = tuple(
            self._segment(index=index, value=value)
            for index, value in enumerate(raw_segments)
        )
        return ParsedTranscript(source_format="diarized_json", segments=segments)

    @staticmethod
    def _segment(*, index: int, value: Any) -> TranscriptSegment:
        if not isinstance(value, dict):
            raise TranscriptionError("transcription provider returned an invalid segment")
        try:
            start_ms = round(float(value["start"]) * 1_000)
            end_ms = round(float(value["end"]) * 1_000)
            text = str(value["text"]).strip()
        except (KeyError, TypeError, ValueError) as error:
            message = "transcription provider returned an invalid segment"
            raise TranscriptionError(message) from error
        speaker = str(value["speaker"]).strip() if value.get("speaker") else None
        return TranscriptSegment(
            ordinal=index,
            start_ms=start_ms,
            end_ms=end_ms,
            speaker=speaker,
            text=text,
        )
