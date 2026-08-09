from qunxue_api.adapters.knowledge_relations import (
    RelationCandidateInput,
    StructuralConnectionInput,
    StructuralNodeInput,
    build_structural_connections,
    extract_relation_candidates,
)


def test_explicit_unique_title_and_trigger_produce_one_traceable_candidate() -> None:
    entries = (
        RelationCandidateInput(
            knowledge_id="D3:M001",
            title="结构化访谈",
            content=(
                "结构化访谈扩展了深度访谈的标准化记录方式。\n\n"
                "> 结构化访谈扩展了深度访谈的标准化记录方式。"
            ),
            source_path="方法论/访谈.md",
            content_version=2,
        ),
        RelationCandidateInput(
            knowledge_id="D3:M002",
            title="深度访谈",
            content="深度访谈强调开放追问。",
            source_path="方法论/访谈.md",
            content_version=3,
        ),
    )

    candidates = extract_relation_candidates(entries)

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.source_knowledge_id == "D3:M001"
    assert candidate.target_knowledge_id == "D3:M002"
    assert candidate.suggested_relation_type == "extends"
    assert candidate.direction == "outbound"
    assert candidate.evidence_excerpt == "结构化访谈扩展了深度访谈的标准化记录方式。"
    assert candidate.evidence_locator == "方法论/访谈.md#D3:M001:content-line-1"
    assert candidate.evidence_source_id == "source:D3:M001"
    assert candidate.source_content_version == 2
    assert candidate.target_content_version == 3
    assert candidate.producer == "explicit-title-trigger"
    assert candidate.producer_config_version == "explicit-title-trigger-v1"
    assert candidate.score == 1.0
    assert candidate.trigger_reason == "trigger=扩展了; unique-title=深度访谈"
    assert candidate.review_status == "pending"
    assert candidate.candidate_id.startswith("candidate:")


def test_ambiguous_titles_self_loops_and_conflicting_types_are_not_candidates() -> None:
    entries = (
        RelationCandidateInput(
            knowledge_id="D1:C001",
            title="行动",
            content="行动扩展了行动。共同体补充了制度，同时共同体批判了制度。",
            source_path="本体论/行动.md",
            content_version=1,
        ),
        RelationCandidateInput(
            knowledge_id="D1:C002",
            title="制度",
            content="制度用于约束行动。",
            source_path="本体论/制度.md",
            content_version=1,
        ),
        RelationCandidateInput(
            knowledge_id="D2:P001",
            title="共同体",
            content="共同体形成共享规范。",
            source_path="实践论/共同体.md",
            content_version=1,
        ),
        RelationCandidateInput(
            knowledge_id="D2:P002",
            title="共同体",
            content="同名条目使标题指向不唯一。",
            source_path="实践论/共同体二.md",
            content_version=1,
        ),
    )

    assert extract_relation_candidates(entries) == ()


def test_directory_paths_produce_stable_deduplicated_entry_connections() -> None:
    dimension = StructuralNodeInput("D3", "dimension", "方法论")
    category = StructuralNodeInput("D3:质性研究", "category", "质性研究")
    entries = (
        StructuralConnectionInput(
            knowledge_id="D3:M001",
            title="结构化访谈",
            directory_path=(dimension, category),
        ),
        StructuralConnectionInput(
            knowledge_id="D3:M002",
            title="深度访谈",
            directory_path=(dimension, category),
        ),
    )

    connections = build_structural_connections(entries)

    assert [
        (
            item.source_node_id,
            item.source_node_type,
            item.target_node_id,
            item.target_node_type,
        )
        for item in connections
    ] == [
        ("D3", "dimension", "D3:质性研究", "category"),
        ("D3:质性研究", "category", "D3:M001", "entry"),
        ("D3:质性研究", "category", "D3:M002", "entry"),
    ]
    assert all(item.connection_type == "contains" for item in connections)
    assert all(item.direction == "outbound" for item in connections)
    assert len({item.connection_id for item in connections}) == 3
