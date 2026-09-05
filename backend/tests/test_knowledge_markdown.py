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


def test_parse_knowledge_markdown_preserves_source_metadata() -> None:
    value_entries = parse_knowledge_markdown(
        source_path=Path("knowledge/价值论/example.md"),
        markdown="""\
<!-- 大类：I. 社会学的学科目的 -->

## I. 社会学的学科目的

#### **V230 差序格局与关系伦理**

价值条目正文。
""",
    )
    school_entries = parse_knowledge_markdown(
        source_path=Path("knowledge/学派传统/example.md"),
        markdown="""\
<!-- 学统：中国学统 -->
<!-- 地区传统：当代重建 -->

##### 【P158】郑杭生

人物条目正文。
""",
    )
    history_entries = parse_knowledge_markdown(
        source_path=Path("knowledge/学科史/example.md"),
        markdown="""\
<!-- 学科史分组：统一前史 -->

# **H001 从伊本·赫勒敦到孔德之前**

编年条目正文。
""",
    )
    school_headings = parse_knowledge_markdown(
        source_path=Path("knowledge/学派传统/example.md"),
        markdown="""\
#### S043 土耳其民族主义
""",
    )

    assert value_entries[0].knowledge_id == "D4:V230"
    assert value_entries[0].title == "差序格局与关系伦理"
    assert [node.title for node in value_entries[0].directory_path] == [
        "价值论",
        "I. 社会学的学科目的",
    ]
    assert school_entries[0].knowledge_id == "D6:P158"
    assert [node.title for node in school_entries[0].directory_path] == [
        "学派传统",
        "中国学统",
        "当代重建",
    ]
    assert history_entries[0].knowledge_id == "D7:H001"
    assert [node.title for node in history_entries[0].directory_path] == [
        "学科史",
        "统一前史",
    ]
    assert school_headings == ()


def test_sibling_entries_do_not_inherit_previous_entry_or_its_sections() -> None:
    entries = parse_knowledge_markdown(
        Path("knowledge/本体论/example.md"),
        "### 社会资本理论\n\n#### C268 结合型社会资本\n\n"
        "##### T4 当代发展\n\n原文。\n\n#### C269 桥接型社会资本\n\n正文。\n",
    )
    assert [node.title for node in entries[1].directory_path] == ["本体论", "社会资本理论"]
    assert "原文。" in entries[0].content
    assert "桥接型" not in entries[0].content
