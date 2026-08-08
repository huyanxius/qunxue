"""Parse repository Markdown into the logical entries used by the catalog."""

import re
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt

from qunxue_api.modules.knowledge_catalog import (
    KnowledgeDirectoryNodeSnapshot,
    KnowledgeDirectoryNodeType,
)

_DIMENSIONS = {
    "本体论": "D1",
    "实践论": "D2",
    "方法论": "D3",
    "价值论": "D4",
    "认识论": "D5",
    "学派传统": "D6",
    "学科史": "D7",
}
_ENTRY_HEADING = re.compile(r"^(?:【)?(?P<entry_id>P\d{3})(?:】)?\s*(?P<title>.+?)\s*$")


@dataclass(frozen=True, slots=True)
class ParsedKnowledgeEntry:
    knowledge_id: str
    title: str
    directory_path: tuple[KnowledgeDirectoryNodeSnapshot, ...]
    content: str


@dataclass(frozen=True, slots=True)
class _Heading:
    level: int
    title: str
    start_line: int


def parse_knowledge_markdown(
    source_path: Path,
    markdown: str,
) -> tuple[ParsedKnowledgeEntry, ...]:
    """Split one source file at P-numbered Markdown headings.

    Existing source dimensions reuse P numbers, so the dimension is part of
    the stable public ID. Content is sliced from source lines rather than
    rendered HTML so later release records can retain the original Markdown.
    """

    dimension_title, dimension_id = _dimension_from(source_path)
    headings = _headings(markdown)
    entries = [heading for heading in headings if _ENTRY_HEADING.match(heading.title)]
    lines = markdown.splitlines(keepends=True)

    parsed_entries = []
    for index, entry_heading in enumerate(entries):
        match = _ENTRY_HEADING.match(entry_heading.title)
        if match is None:
            continue

        category_heading = next(
            (
                heading
                for heading in reversed(headings[: headings.index(entry_heading)])
                if heading.level < entry_heading.level
            ),
            None,
        )
        if category_heading is None:
            raise ValueError(f"Missing catalog category before {entry_heading.title!r}")

        next_entry_line = (
            entries[index + 1].start_line if index + 1 < len(entries) else len(lines)
        )
        content_end_line = next_entry_line
        while content_end_line > entry_heading.start_line and not lines[
            content_end_line - 1
        ].strip():
            content_end_line -= 1
        category_title = category_heading.title
        parsed_entries.append(
            ParsedKnowledgeEntry(
                knowledge_id=f"{dimension_id}:{match.group('entry_id')}",
                title=match.group("title"),
                directory_path=(
                    KnowledgeDirectoryNodeSnapshot(
                        node_id=dimension_id,
                        node_type=KnowledgeDirectoryNodeType.DIMENSION,
                        title=dimension_title,
                    ),
                    KnowledgeDirectoryNodeSnapshot(
                        node_id=f"{dimension_id}:{category_title}",
                        node_type=KnowledgeDirectoryNodeType.CATEGORY,
                        title=category_title,
                    ),
                ),
                content="".join(lines[entry_heading.start_line:content_end_line]),
            )
        )

    return tuple(parsed_entries)


def _dimension_from(source_path: Path) -> tuple[str, str]:
    for part in source_path.parts:
        if part in _DIMENSIONS:
            return part, _DIMENSIONS[part]
    raise ValueError(f"Unsupported knowledge source path: {source_path}")


def _headings(markdown: str) -> tuple[_Heading, ...]:
    tokens = MarkdownIt("commonmark").parse(markdown)
    headings = []
    for index, token in enumerate(tokens):
        if token.type != "heading_open" or token.map is None:
            continue
        inline = tokens[index + 1]
        headings.append(
            _Heading(
                level=int(token.tag.removeprefix("h")),
                title=inline.content.strip(),
                start_line=token.map[0],
            )
        )
    return tuple(headings)
