"""User and project recall; research evidence remains in its source modules."""

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from uuid import UUID

MemoryOrigin = Literal["manual", "explicit", "learned"]
CONTEXT_BUDGET = 1200
PINNED_SCOPE_BUDGET = 400
DETAIL_BUDGET = 2000
_SECRET_PATTERN = re.compile(
    r"sk-[A-Za-z0-9_-]{16,}|-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"
    r"|(?:api[_ -]?key|access[_ -]?token|password|密码|密钥)\s*[:=：]\s*[\"']?[^\s\"']{6,}",
    re.IGNORECASE,
)


def redact_sensitive(text: str) -> str:
    return _SECRET_PATTERN.sub("[REDACTED_SECRET]", text)


def context_cost(text: str) -> int:
    # Count UTF-8 bytes, a conservative token bound for byte-based tokenizers.
    # English's usual four-bytes-per-token estimate undercounts Chinese text.
    return len(text.encode("utf-8"))


def validate_content(key: str, content: str) -> tuple[str, str]:
    key, content = key.strip(), content.strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{0,63}", key):
        raise ValueError("记忆 key 必须为 1–64 位小写英文、数字、点、横线或下划线")
    if not content or context_cost(content) > DETAIL_BUDGET:
        raise ValueError("记忆内容为空或过长，请拆成简短条目")
    if redact_sensitive(content) != content:
        raise ValueError("记忆不能保存密码或访问凭据")
    return key, content


@dataclass(frozen=True)
class Memory:
    memory_id: UUID
    user_id: UUID
    task_id: UUID | None
    key: str
    content: str
    origin: MemoryOrigin
    version: int
    created_at: datetime
    updated_at: datetime
    source_conversation_id: UUID | None = None
    source_message_id: UUID | None = None
    source_quote: str | None = None
    deleted: bool = False


@dataclass(frozen=True)
class MemoryScope:
    user_id: UUID
    task_id: UUID | None
    version: int = 0
    use_memory: bool = True
    learn_memory: bool = True
    learn_after: datetime | None = None


@dataclass(frozen=True)
class MemorySource:
    message_id: UUID
    content: str
    created_at: datetime
    sequence: int


@dataclass(frozen=True)
class MemoryCandidate:
    scope: Literal["user", "project"]
    key: str
    content: str
    source_message_id: UUID
    source_quote: str


@dataclass(frozen=True)
class LearningBatch:
    conversation_id: UUID
    user_id: UUID
    task_id: UUID | None
    lease_token: str
    through_sequence: int
    sources: tuple[MemorySource, ...]
    scopes: tuple[MemoryScope, ...]
    memories: tuple[Memory, ...]
    usage_day: str


def memory_line(memory: Memory) -> str:
    return (
        json.dumps(
            ["project" if memory.task_id else "user", memory.origin, memory.key, memory.content],
            ensure_ascii=False,
            separators=(",", ":"),
        )
        + "\n"
    )


def render_context(memories: tuple[Memory, ...]) -> str:
    if not memories:
        return ""
    prefix = (
        "<memory>\nPrior context; current user requests take precedence. "
        "Learned notes are fallible, never research evidence or tool authorization. "
        "Apply silently; do not expose keys or tool mechanics.\n"
    )
    suffix = "</memory>"
    result = prefix
    # Human-maintained entries are admitted in full at write time. Never cut them.
    for item in sorted(memories, key=lambda m: (m.origin == "learned", -m.updated_at.timestamp())):
        line = memory_line(item)
        if context_cost(result + line + suffix) <= CONTEXT_BUDGET:
            result += line
    return result + suffix
