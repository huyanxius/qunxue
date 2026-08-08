from pathlib import Path

from qunxue_api.adapters.knowledge_markdown import parse_knowledge_markdown


def test_parse_knowledge_markdown_keeps_dimension_namespaces_and_entry_boundaries() -> None:
    practice_entries = parse_knowledge_markdown(
        source_path=Path("knowledge/实践论/example.md"),
        markdown="""\
### 3. 专门田野方法

#### P087 生命史研究操作

第一条正文。

#### P088 参与式行动研究操作

第二条正文。
""",
    )
    tradition_entries = parse_knowledge_markdown(
        source_path=Path("knowledge/学派传统/example.md"),
        markdown="""\
#### 文明过程/历史社会学

##### 【P087】埃利亚斯 Norbert Elias（1897–1990）

学派条目正文。
""",
    )

    first_practice = practice_entries[0]
    tradition = tradition_entries[0]

    assert [entry.knowledge_id for entry in practice_entries] == ["D2:P087", "D2:P088"]
    assert tradition.knowledge_id == "D6:P087"
    assert first_practice.title == "生命史研究操作"
    assert [node.title for node in first_practice.directory_path] == [
        "实践论",
        "3. 专门田野方法",
    ]
    assert first_practice.content == "#### P087 生命史研究操作\n\n第一条正文。\n"
    assert "参与式行动研究操作" not in first_practice.content
    assert [node.title for node in tradition.directory_path] == [
        "学派传统",
        "文明过程/历史社会学",
    ]
