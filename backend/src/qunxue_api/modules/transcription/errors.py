"""Stable transcription failure vocabulary."""


class TranscriptionError(RuntimeError):
    code = "transcription_error"


class TranscriptionUnavailable(TranscriptionError):
    code = "transcription_unavailable"


class TranscriptionPolicyDenied(TranscriptionError):
    code = "transcription_policy_denied"


class TranscriptVersionConflict(TranscriptionError):
    code = "transcript_version_conflict"


class UnsupportedTranscriptImport(TranscriptionError):
    code = "unsupported_transcript_import"
