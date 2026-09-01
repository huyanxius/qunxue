import httpx

from qunxue_api.adapters.transcription.openai_compatible import (
    OpenAICompatibleTranscriptionProvider,
)
from qunxue_api.modules.transcription import ProcessingLocation
from qunxue_api.settings import Settings


def test_transcription_settings_require_a_complete_explicit_provider() -> None:
    absent = Settings(_env_file=None)
    partial = Settings(
        _env_file=None,
        transcription_base_url="https://transcribe.example/v1",
    )
    configured = Settings(
        _env_file=None,
        transcription_base_url="https://transcribe.example/v1",
        transcription_api_key="secret",
        transcription_model="speaker-aware-transcriber",
    )

    assert absent.has_transcription_provider is False
    assert partial.has_transcription_provider is False
    assert configured.has_transcription_provider is True


def test_openai_compatible_provider_maps_diarized_segments_and_sends_media_once() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "segments": [
                    {"start": 1.25, "end": 3.8, "speaker": "A", "text": "你好。"},
                    {"start": 4.1, "end": 6.9, "speaker": "B", "text": "你好。"},
                ]
            },
        )

    provider = OpenAICompatibleTranscriptionProvider(
        base_url="https://transcribe.example/v1",
        api_key="secret",
        model="speaker-aware-transcriber",
        processing_location=ProcessingLocation.EXTERNAL,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    parsed = provider.transcribe(
        filename="访谈.wav",
        media_type="audio/wav",
        content=b"media",
    )

    assert [(item.start_ms, item.end_ms, item.speaker, item.text) for item in parsed.segments] == [
        (1_250, 3_800, "A", "你好。"),
        (4_100, 6_900, "B", "你好。"),
    ]
    assert len(requests) == 1
    assert requests[0].url == "https://transcribe.example/v1/audio/transcriptions"
    assert requests[0].headers["authorization"] == "Bearer secret"
