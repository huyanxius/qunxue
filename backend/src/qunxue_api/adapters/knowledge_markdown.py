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
_ENTRY_PREFIXES = {
    "D1": "C",
    "D2": "P",
    "D3": "M",
    "D4": "V",
    "D5": "E",
    "D6": "P",
    "D7": "H",
}
_ENTRY_HEADING = re.compile(r"^(?:【)?(?P<entry_id>[A-Z]\d{3,})(?:】)?\s*(?P<title>.+?)\s*$")
_DIRECTORY_METADATA = frozenset({"大类", "学统", "地区传统", "学科史分组"})
_METADATA_COMMENT = re.compile(
    r"^\s*<!--\s*(?P<label>[^：:]+)\s*[：:]\s*(?P<value>.*?)\s*-->\s*$"
)


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
    """Split one source file at the numbered headings used by the source.

    Existing source dimensions reuse identifiers, so the dimension is part of
    the stable public ID. Content is sliced from source lines rather than
    rendered HTML so later release records can retain the original Markdown.
    """

    dimension_title, dimension_id = _dimension_from(source_path)
    headings = _headings(markdown)
    entries = [
        (heading_index, heading, match)
        for heading_index, heading in enumerate(headings)
        if (match := _ENTRY_HEADING.match(heading.title)) is not None
        and match.group("entry_id")[0] == _ENTRY_PREFIXES[dimension_id]
    ]
    metadata_titles = _directory_metadata(markdown)
    lines = markdown.splitlines(keepends=True)

    parsed_entries = []
    for index, (heading_index, entry_heading, match) in enumerate(entries):
        ancestor_titles = [
            heading.title for heading in _ancestor_headings(headings, heading_index)
        ]
        directory_titles = _distinct_titles(metadata_titles + ancestor_titles)

        next_entry_line = (
            entries[index + 1][1].start_line if index + 1 < len(entries) else len(lines)
        )
        content_end_line = next_entry_line
        while content_end_line > entry_heading.start_line and not lines[
            content_end_line - 1
        ].strip():
            content_end_line -= 1
        parsed_entries.append(
            ParsedKnowledgeEntry(
                knowledge_id=f"{dimension_id}:{match.group('entry_id')}",
                title=match.group("title"),
                directory_path=_directory_path(
                    dimension_id,
                    dimension_title,
                    directory_titles,
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
                title=inline.content.strip().strip("* "),
                start_line=token.map[0],
            )
        )
    return tuple(headings)


def _directory_metadata(markdown: str) -> list[str]:
    metadata = []
    for line in markdown.splitlines():
        if not line.strip():
            continue
        match = _METADATA_COMMENT.match(line)
        if match is None:
            break
        if match.group("label") in _DIRECTORY_METADATA:
            metadata.append(match.group("value"))
    return metadata


def _ancestor_headings(
    headings: tuple[_Heading, ...],
    entry_index: int,
) -> tuple[_Heading, ...]:
    stack: list[_Heading] = []
    for heading in headings[:entry_index]:
        while stack and stack[-1].level >= heading.level:
            stack.pop()
        stack.append(heading)
    # Siblings and their sections belong to the previous entry, not this path.
    while stack and stack[-1].level >= headings[entry_index].level:
        stack.pop()
    return tuple(heading for heading in stack if heading.level > 1)


def _distinct_titles(titles: list[str]) -> list[str]:
    distinct = []
    for title in titles:
        if title not in distinct:
            distinct.append(title)
    return distinct


def _directory_path(
    dimension_id: str,
    dimension_title: str,
    category_titles: list[str],
) -> tuple[KnowledgeDirectoryNodeSnapshot, ...]:
    nodes = [
        KnowledgeDirectoryNodeSnapshot(
            node_id=dimension_id,
            node_type=KnowledgeDirectoryNodeType.DIMENSION,
            title=dimension_title,
        )
    ]
    for index, title in enumerate(category_titles, start=1):
        nodes.append(
            KnowledgeDirectoryNodeSnapshot(
                node_id=f"{dimension_id}:{'/'.join(category_titles[:index])}",
                node_type=KnowledgeDirectoryNodeType.CATEGORY,
                title=title,
            )
        )
    return tuple(nodes)
