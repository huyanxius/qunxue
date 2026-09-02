"""Transcript import and external-provider adapters."""

from qunxue_api.adapters.transcription.dashscope import DashScopeTranscriptionProvider
from qunxue_api.adapters.transcription.importer import parse_imported_transcript
from qunxue_api.adapters.transcription.openai_compatible import (
    OpenAICompatibleTranscriptionProvider,
)

__all__ = [
    "DashScopeTranscriptionProvider",
    "OpenAICompatibleTranscriptionProvider",
    "parse_imported_transcript",
]
