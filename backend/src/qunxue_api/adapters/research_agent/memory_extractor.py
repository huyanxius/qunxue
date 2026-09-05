import asyncio
import json
from pathlib import Path
from typing import Literal
from uuid import UUID

from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from qunxue_api.modules.agent_memory import LearningBatch, MemoryCandidate, redact_sensitive

from .pydantic_runner import _is_deepseek_flash

_INSTRUCTIONS = (Path(__file__).parent / "prompts" / "memory_extraction.md").read_text()


class ExtractedMemory(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scope: Literal["user", "project"]
    key: str = Field(max_length=64)
    content: str = Field(max_length=500)
    source_message_id: UUID
    source_quote: str = Field(min_length=1, max_length=1000)


class ExtractedMemories(BaseModel):
    memories: list[ExtractedMemory] = Field(default_factory=list, max_length=8)


class PydanticMemoryExtractor:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: float = 30,
        extra_headers: dict | None = None,
    ) -> None:
        self._base_url, self._api_key, self._model = base_url, api_key, model
        self._timeout, self._extra_headers = timeout_seconds, extra_headers

    def __call__(self, batch: LearningBatch):
        return asyncio.run(self.extract(batch))

    async def extract(self, batch: LearningBatch):
        payload = json.dumps(
            {
                "project_id": str(batch.task_id) if batch.task_id else None,
                "sources": [
                    {"message_id": str(s.message_id), "content": redact_sensitive(s.content)}
                    for s in batch.sources
                ],
                "existing_memories": [
                    {
                        "scope": "project" if m.task_id else "user",
                        "key": m.key,
                        "content": m.content,
                        "origin": m.origin,
                    }
                    for m in batch.memories
                ],
            },
            ensure_ascii=False,
        )
        if len((_INSTRUCTIONS + payload).encode("utf-8")) > 22000:
            raise ValueError("memory_extraction_input_budget_exceeded")
        async with AsyncOpenAI(
            base_url=self._base_url, api_key=self._api_key, max_retries=0, timeout=self._timeout
        ) as client:
            model = OpenAIChatModel(self._model, provider=OpenAIProvider(openai_client=client))
            settings = {"timeout": self._timeout, "max_tokens": 1500}
            if _is_deepseek_flash(base_url=self._base_url, model=self._model):
                settings["extra_body"] = {"thinking": {"type": "disabled"}}
            if self._extra_headers:
                settings["extra_headers"] = self._extra_headers
            agent = Agent(
                model,
                output_type=ExtractedMemories,
                instructions=_INSTRUCTIONS,
                retries=0,
                model_settings=settings,
            )
            result = await agent.run(
                payload, usage_limits=UsageLimits(request_limit=1, tool_calls_limit=0)
            )
            usage = result.usage
            return (
                tuple(MemoryCandidate(**m.model_dump()) for m in result.output.memories),
                usage.input_tokens,
                usage.output_tokens,
            )
