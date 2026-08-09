"""Deterministic high-precision relation candidates from repository Markdown."""

import json
import re
from dataclasses import dataclass
from hashlib import sha256

PRODUCER = "explicit-title-trigger"
PRODUCER_CONFIG_VERSION = "explicit-title-trigger-v1"

_TRIGGERS = (
    ("broader_than", ("上位概念", "包含了", "包括了")),
    ("narrower_than", ("下位概念", "属于")),
    ("extends", ("扩展了", "拓展了", "发展了", "继承并发展")),
    ("critiques", ("批判了", "批评了", "反驳了", "质疑了")),
    ("contrasts_with", ("形成鲜明对比", "相互对立", "不同于", "区别于")),
    ("complements", ("相互补充", "形成互补", "补充了")),
    ("operationalizes", ("操作化为", "转化为可测量")),
    ("applies_to", ("应用于", "适用于", "用于分析")),
    ("historically_precedes", ("早于", "先于")),
)
_SENTENCE = re.compile(r"[^。！？!?\n]+[。！？!?]?")


@dataclass(frozen=True, slots=True)
class RelationCandidateInput:
    knowledge_id: str
    title: str
    content: str
    source_path: str
    content_version: int


@dataclass(frozen=True, slots=True)
class StructuralNodeInput:
    node_id: str
    node_type: str
    title: str


@dataclass(frozen=True, slots=True)
class StructuralConnectionInput:
    knowledge_id: str
    title: str
    directory_path: tuple[StructuralNodeInput, ...]


@dataclass(frozen=True, slots=True)
class StructuralConnection:
    connection_id: str
    source_node_id: str
    source_node_type: str
    source_title: str
    target_node_id: str
    target_node_type: str
    target_title: str
    connection_type: str
    direction: str


@dataclass(frozen=True, slots=True)
class ExtractedRelationCandidate:
    candidate_id: str
    source_knowledge_id: str
    target_knowledge_id: str
    suggested_relation_type: str
    direction: str
    evidence_excerpt: str
    evidence_locator: str
    evidence_source_id: str
    source_content_version: int
    target_content_version: int
    producer: str
    producer_config_version: str
    score: float
    trigger_reason: str
    review_status: str


def build_structural_connections(
    entries: tuple[StructuralConnectionInput, ...],
) -> tuple[StructuralConnection, ...]:
    """Project directory paths into stable contains edges without copying facts."""

    edges: dict[tuple[str, str], StructuralConnection] = {}
    for entry in sorted(entries, key=lambda item: item.knowledge_id):
        entry_node = StructuralNodeInput(entry.knowledge_id, "entry", entry.title)
        path = (*entry.directory_path, entry_node)
        for source, target in zip(path, path[1:], strict=False):
            identity = f"{source.node_type}:{source.node_id}->{target.node_type}:{target.node_id}"
            connection = StructuralConnection(
                connection_id=f"structure:{sha256(identity.encode()).hexdigest()[:32]}",
                source_node_id=source.node_id,
                source_node_type=source.node_type,
                source_title=source.title,
                target_node_id=target.node_id,
                target_node_type=target.node_type,
                target_title=target.title,
                connection_type="contains",
                direction="outbound",
            )
            edges[(source.node_id, target.node_id)] = connection
    return tuple(
        sorted(edges.values(), key=lambda item: (item.source_node_id, item.target_node_id))
    )


def extract_relation_candidates(
    entries: tuple[RelationCandidateInput, ...],
) -> tuple[ExtractedRelationCandidate, ...]:
    """Extract candidates only when a unique catalog title and trigger co-occur."""

    title_entries: dict[str, list[RelationCandidateInput]] = {}
    id_entries = {entry.knowledge_id: entry for entry in entries}
    for entry in entries:
        title_entries.setdefault(entry.title, []).append(entry)
    unique_titles = {
        title: matches[0]
        for title, matches in title_entries.items()
        if len(matches) == 1 and title.strip()
    }
    mention_pattern = _mention_pattern(unique_titles, id_entries)

    found: dict[tuple[str, str, str], ExtractedRelationCandidate] = {}
    pair_types: dict[tuple[str, str], set[str]] = {}
    for source in sorted(entries, key=lambda item: item.knowledge_id):
        for line_number, sentence in _evidence_sentences(source.content):
            triggers = [
                (relation_type, trigger)
                for relation_type, values in _TRIGGERS
                for trigger in values
                if trigger in sentence
            ]
            if not triggers:
                continue
            targets = _mentioned_entries(sentence, mention_pattern, unique_titles, id_entries)
            for target in targets:
                if target.knowledge_id == source.knowledge_id:
                    continue
                for relation_type, trigger in triggers:
                    pair = (source.knowledge_id, target.knowledge_id)
                    pair_types.setdefault(pair, set()).add(relation_type)
                    key = (*pair, relation_type)
                    if key not in found:
                        found[key] = _candidate(
                            source=source,
                            target=target,
                            relation_type=relation_type,
                            trigger=trigger,
                            excerpt=sentence,
                            line_number=line_number,
                        )

    candidates = [
        candidate
        for key, candidate in found.items()
        if len(pair_types[key[:2]]) == 1
    ]
    return tuple(sorted(candidates, key=lambda item: item.candidate_id))


def _mention_pattern(
    unique_titles: dict[str, RelationCandidateInput],
    id_entries: dict[str, RelationCandidateInput],
) -> re.Pattern[str]:
    mentions = sorted((*unique_titles, *id_entries), key=lambda value: (-len(value), value))
    if not mentions:
        return re.compile(r"(?!x)x")
    return re.compile("|".join(re.escape(value) for value in mentions))


def _evidence_sentences(content: str) -> tuple[tuple[int, str], ...]:
    evidence = []
    for line_number, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith((">", "#"))
            or stripped.startswith(("参考文献", "审核补充文献", "**文献"))
        ):
            continue
        for match in _SENTENCE.finditer(stripped):
            sentence = match.group().strip()
            if sentence:
                evidence.append((line_number, sentence))
    return tuple(evidence)


def _mentioned_entries(
    sentence: str,
    pattern: re.Pattern[str],
    unique_titles: dict[str, RelationCandidateInput],
    id_entries: dict[str, RelationCandidateInput],
) -> tuple[RelationCandidateInput, ...]:
    matches = {
        entry.knowledge_id: entry
        for match in pattern.finditer(sentence)
        if (entry := id_entries.get(match.group()) or unique_titles.get(match.group())) is not None
    }
    return tuple(matches[key] for key in sorted(matches))


def _candidate(
    *,
    source: RelationCandidateInput,
    target: RelationCandidateInput,
    relation_type: str,
    trigger: str,
    excerpt: str,
    line_number: int,
) -> ExtractedRelationCandidate:
    locator = f"{source.source_path}#{source.knowledge_id}:content-line-{line_number}"
    reason = f"trigger={trigger}; unique-title={target.title}"
    identity = json.dumps(
        {
            "source": source.knowledge_id,
            "target": target.knowledge_id,
            "type": relation_type,
            "direction": "outbound",
            "excerpt": excerpt,
            "locator": locator,
            "producer_config_version": PRODUCER_CONFIG_VERSION,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    candidate_id = f"candidate:{sha256(identity.encode()).hexdigest()[:32]}"
    return ExtractedRelationCandidate(
        candidate_id=candidate_id,
        source_knowledge_id=source.knowledge_id,
        target_knowledge_id=target.knowledge_id,
        suggested_relation_type=relation_type,
        direction="outbound",
        evidence_excerpt=excerpt,
        evidence_locator=locator,
        evidence_source_id=f"source:{source.knowledge_id}",
        source_content_version=source.content_version,
        target_content_version=target.content_version,
        producer=PRODUCER,
        producer_config_version=PRODUCER_CONFIG_VERSION,
        score=1.0,
        trigger_reason=reason,
        review_status="pending",
    )
