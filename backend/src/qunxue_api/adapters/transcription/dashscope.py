"""DashScope asynchronous file transcription adapter."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import httpx

from qunxue_api.modules.transcription import (
    ParsedTranscript,
    ProcessingLocation,
    TranscriptionError,
    TranscriptSegment,
)


class DashScopeTranscriptionProvider:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        processing_location: ProcessingLocation,
        timeout_seconds: float = 180,
        poll_interval_seconds: float = 2,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model = model
        self._processing_location = processing_location
        self._timeout_seconds = timeout_seconds
        self._poll_interval_seconds = poll_interval_seconds
        self._client = client or httpx.Client(timeout=timeout_seconds)

    @property
    def available(self) -> bool:
        return bool(self._base_url and self._api_key and self._model)

    @property
    def name(self) -> str:
        return f"dashscope:{self._model}"

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
            audio_url = self._upload(filename=filename, media_type=media_type, content=content)
            task_id = self._submit(audio_url)
            result_url = self._wait_for_result(task_id)
            response = self._client.get(result_url)
            response.raise_for_status()
            segments = self._segments(response.json())
        except TranscriptionError:
            raise
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
            raise TranscriptionError("DashScope transcription request failed") from error
        return ParsedTranscript(source_format="dashscope_filetrans", segments=segments)

    def _upload(self, *, filename: str, media_type: str, content: bytes) -> str:
        response = self._client.get(
            f"{self._base_url}/uploads",
            headers=self._headers(),
            params={"action": "getPolicy", "model": self._model},
        )
        response.raise_for_status()
        policy = response.json()["data"]
        safe_filename = Path(filename).name
        object_key = f"{policy['upload_dir'].rstrip('/')}/{safe_filename}"
        upload = self._client.post(
            policy["upload_host"],
            data={
                "OSSAccessKeyId": policy["oss_access_key_id"],
                "policy": policy["policy"],
                "Signature": policy["signature"],
                "key": object_key,
                "x-oss-object-acl": policy["x_oss_object_acl"],
                "x-oss-forbid-overwrite": policy["x_oss_forbid_overwrite"],
                "success_action_status": "200",
            },
            files={"file": (safe_filename, content, media_type)},
        )
        upload.raise_for_status()
        return f"oss://{object_key}"

    def _submit(self, audio_url: str) -> str:
        response = self._client.post(
            f"{self._base_url}/services/audio/asr/transcription",
            headers={
                **self._headers(),
                "X-DashScope-Async": "enable",
                "X-DashScope-OssResourceResolve": "enable",
            },
            json={
                "model": self._model,
                "input": {"file_urls": [audio_url]},
                "parameters": {
                    "channel_id": [0],
                    "language_hints": ["zh"],
                    "diarization_enabled": True,
                },
            },
        )
        response.raise_for_status()
        return str(response.json()["output"]["task_id"])

    def _wait_for_result(self, task_id: str) -> str:
        deadline = time.monotonic() + self._timeout_seconds
        while time.monotonic() < deadline:
            response = self._client.get(
                f"{self._base_url}/tasks/{task_id}",
                headers=self._headers(),
            )
            response.raise_for_status()
            output = response.json()["output"]
            status = output.get("task_status")
            if status == "SUCCEEDED":
                results = output.get("results")
                if isinstance(results, list) and results:
                    result = results[0]
                    if result.get("subtask_status") == "SUCCEEDED":
                        return str(result["transcription_url"])
                break
            if status == "FAILED":
                break
            if self._poll_interval_seconds:
                time.sleep(self._poll_interval_seconds)
        raise TranscriptionError("DashScope transcription task failed or timed out")

    @staticmethod
    def _segments(payload: Any) -> tuple[TranscriptSegment, ...]:
        transcripts = payload.get("transcripts") if isinstance(payload, dict) else None
        if not isinstance(transcripts, list):
            raise TranscriptionError("DashScope transcription returned no timed segments")
        sentences = [
            sentence
            for transcript in transcripts
            if isinstance(transcript, dict)
            for sentence in transcript.get("sentences", [])
            if isinstance(sentence, dict)
        ]
        if not sentences:
            raise TranscriptionError("DashScope transcription returned no timed segments")
        try:
            return tuple(
                TranscriptSegment(
                    ordinal=index,
                    start_ms=int(sentence["begin_time"]),
                    end_ms=int(sentence["end_time"]),
                    speaker=DashScopeTranscriptionProvider._speaker(sentence.get("speaker_id")),
                    text=str(sentence["text"]).strip(),
                )
                for index, sentence in enumerate(sentences)
            )
        except (KeyError, TypeError, ValueError) as error:
            message = "DashScope transcription returned an invalid segment"
            raise TranscriptionError(message) from error

    @staticmethod
    def _speaker(value: Any) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        text = str(value).strip()
        return f"SPEAKER_{int(text):02d}" if text.isdigit() else f"SPEAKER_{text}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
