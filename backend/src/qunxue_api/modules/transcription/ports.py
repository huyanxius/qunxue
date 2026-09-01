"""Ports implemented by existing or separately operated transcription services."""

from typing import Protocol, runtime_checkable

from qunxue_api.modules.transcription.domain import ParsedTranscript, ProcessingLocation


@runtime_checkable
class TranscriptionProvider(Protocol):
    @property
    def available(self) -> bool: ...

    @property
    def name(self) -> str | None: ...

    @property
    def processing_location(self) -> ProcessingLocation: ...

    def transcribe(
        self,
        *,
        filename: str,
        media_type: str,
        content: bytes,
    ) -> ParsedTranscript: ...


class UnavailableTranscriptionProvider:
    @property
    def available(self) -> bool:
        return False

    @property
    def name(self) -> str | None:
        return None

    @property
    def processing_location(self) -> ProcessingLocation:
        return ProcessingLocation.LOCAL

    def transcribe(self, **_kwargs: object) -> ParsedTranscript:
        from qunxue_api.modules.transcription.errors import TranscriptionUnavailable

        raise TranscriptionUnavailable("automatic transcription is not configured")
