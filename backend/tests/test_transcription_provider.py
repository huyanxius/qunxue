import json

import httpx

from qunxue_api import bootstrap
from qunxue_api.adapters import transcription as transcription_adapters
from qunxue_api.adapters.transcription.openai_compatible import (
    OpenAICompatibleTranscriptionProvider,
)
from qunxue_api.modules.transcription import ProcessingLocation
from qunxue_api.settings import Settings


def test_dashscope_provider_uploads_polls_and_maps_diarized_sentences() -> None:
    provider_type = getattr(transcription_adapters, "DashScopeTranscriptionProvider", None)
    assert provider_type is not None
    requests: list[httpx.Request] = []
    task_polls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal task_polls
        requests.append(request)
        if request.url.path == "/api/v1/uploads":
            return httpx.Response(
                200,
                json={
                    "data": {
                        "policy": "policy",
                        "signature": "signature",
                        "upload_dir": "dashscope-instant/dir",
                        "upload_host": "https://upload.example",
                        "oss_access_key_id": "access-key",
                        "x_oss_object_acl": "private",
                        "x_oss_forbid_overwrite": "true",
                    }
                },
            )
        if request.url.host == "upload.example":
            return httpx.Response(200)
        if request.url.path == "/api/v1/services/audio/asr/transcription":
            return httpx.Response(200, json={"output": {"task_id": "task-1"}})
        if request.url.path == "/api/v1/tasks/task-1":
            task_polls += 1
            if task_polls == 1:
                return httpx.Response(200, json={"output": {"task_status": "RUNNING"}})
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_status": "SUCCEEDED",
                        "results": [
                            {
                                "subtask_status": "SUCCEEDED",
                                "transcription_url": "https://result.example/transcript.json",
                            }
                        ],
                    }
                },
            )
        if request.url.host == "result.example":
            return httpx.Response(
                200,
                json={
                    "transcripts": [
                        {
                            "sentences": [
                                {
                                    "begin_time": 120,
                                    "end_time": 2_340,
                                    "speaker_id": 0,
                                    "text": "我们今天谈谈田野调查。",
                                },
                                {
                                    "begin_time": 2_500,
                                    "end_time": 4_100,
                                    "speaker_id": 1,
                                    "text": "好的。",
                                },
                            ]
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    provider = provider_type(
        base_url="https://dashscope.aliyuncs.com/api/v1",
        api_key="secret",
        model="qwen-audio-3.0-asr-flash-filetrans",
        processing_location=ProcessingLocation.EXTERNAL,
        client=httpx.Client(transport=httpx.MockTransport(handler)),
        poll_interval_seconds=0,
    )

    parsed = provider.transcribe(
        filename="访谈.wav",
        media_type="audio/wav",
        content=b"media",
    )

    assert [(item.start_ms, item.end_ms, item.speaker, item.text) for item in parsed.segments] == [
        (120, 2_340, "SPEAKER_00", "我们今天谈谈田野调查。"),
        (2_500, 4_100, "SPEAKER_01", "好的。"),
    ]
    submission = next(
        request
        for request in requests
        if request.url.path == "/api/v1/services/audio/asr/transcription"
    )
    assert submission.headers["x-dashscope-async"] == "enable"
    assert submission.headers["x-dashscope-ossresourceresolve"] == "enable"
    assert json.loads(submission.content) == {
        "model": "qwen-audio-3.0-asr-flash-filetrans",
        "input": {"file_urls": ["oss://dashscope-instant/dir/访谈.wav"]},
        "parameters": {
            "channel_id": [0],
            "language_hints": ["zh"],
            "diarization_enabled": True,
        },
    }


def test_transcription_settings_select_dashscope_filetrans_provider() -> None:
    build_provider = getattr(bootstrap, "_build_transcription_provider", None)
    assert build_provider is not None
    provider = build_provider(
        Settings(
            _env_file=None,
            transcription_base_url="https://dashscope.aliyuncs.com/api/v1",
            transcription_api_key="secret",
            transcription_model="qwen-audio-3.0-asr-flash-filetrans",
        )
    )

    assert provider.name == "dashscope:qwen-audio-3.0-asr-flash-filetrans"


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
