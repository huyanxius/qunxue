from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from uuid import UUID
from zipfile import ZipFile

import pytest

from qunxue_api.modules.research_exchange import (
    QdpxCase,
    QdpxCode,
    QdpxCoding,
    QdpxLink,
    QdpxMemo,
    QdpxProject,
    QdpxSelection,
    QdpxSet,
    QdpxSource,
    QdpxSourceKind,
    QdpxUser,
    export_qdpx,
    import_qdpx,
    validate_qdpx,
)

PROJECT_ID = UUID("10000000-0000-4000-8000-000000000001")
USER_ID = UUID("10000000-0000-4000-8000-000000000002")
SOURCE_ID = UUID("10000000-0000-4000-8000-000000000003")
SELECTION_ID = UUID("10000000-0000-4000-8000-000000000004")
PARENT_CODE_ID = UUID("10000000-0000-4000-8000-000000000005")
CODE_ID = UUID("10000000-0000-4000-8000-000000000006")
CODING_ID = UUID("10000000-0000-4000-8000-000000000007")
MEMO_ID = UUID("10000000-0000-4000-8000-000000000008")
CASE_ID = UUID("10000000-0000-4000-8000-000000000009")
SET_ID = UUID("10000000-0000-4000-8000-00000000000a")
LINK_ID = UUID("10000000-0000-4000-8000-00000000000b")
FIXTURE = Path(__file__).parent / "fixtures" / "qdpx" / "community-care-interview.qdpx"


def _social_research_project() -> QdpxProject:
    text = "受访者说，搬到城中村后通勤时间缩短了，但邻里互助也变少了。"
    quote = "通勤时间缩短了"
    start = text.index(quote)
    return QdpxProject(
        project_id=PROJECT_ID,
        name="城中村流动与邻里关系",
        origin="群学致知",
        description="一项围绕居住流动、通勤与邻里互助的访谈研究。",
        users=(QdpxUser(user_id=USER_ID, name="研究者"),),
        codes=(
            QdpxCode(code_id=PARENT_CODE_ID, name="城市流动"),
            QdpxCode(
                code_id=CODE_ID,
                name="通勤改善",
                description="搬迁后通勤耗时下降。",
                parent_code_id=PARENT_CODE_ID,
            ),
        ),
        sources=(
            QdpxSource(
                source_id=SOURCE_ID,
                name="访谈01.txt",
                kind=QdpxSourceKind.TEXT,
                plain_text=text,
                selections=(
                    QdpxSelection(
                        selection_id=SELECTION_ID,
                        start_position=start,
                        end_position=start + len(quote),
                        codings=(QdpxCoding(coding_id=CODING_ID, code_id=CODE_ID),),
                        memo_ids=(MEMO_ID,),
                    ),
                ),
            ),
        ),
        memos=(
            QdpxMemo(
                memo_id=MEMO_ID,
                name="初步分析备忘",
                content="通勤改善与邻里关系减弱同时出现，不能只解释为单向收益。",
                target_ids=(SELECTION_ID,),
            ),
        ),
        cases=(
            QdpxCase(
                case_id=CASE_ID,
                name="受访者01",
                description="近一年搬入城中村的服务业劳动者。",
                attributes={"职业": "服务业", "迁入年数": 1, "本地户籍": False},
                source_ids=(SOURCE_ID,),
                selection_ids=(SELECTION_ID,),
            ),
        ),
        sets=(
            QdpxSet(
                set_id=SET_ID,
                name="第一轮访谈",
                member_source_ids=(SOURCE_ID,),
                member_code_ids=(CODE_ID,),
                member_memo_ids=(MEMO_ID,),
            ),
        ),
        links=(
            QdpxLink(
                link_id=LINK_ID,
                name="通勤改善关联邻里互助",
                origin_id=CODE_ID,
                target_id=MEMO_ID,
            ),
        ),
    )


def test_qdpx_export_is_schema_valid_deterministic_and_contains_no_private_xml() -> None:
    project = _social_research_project()

    first = export_qdpx(project)
    second = export_qdpx(project)

    assert first.payload == second.payload
    assert first.sha256 == second.sha256
    assert [loss.field for loss in first.report.losses] == ["project_id"]
    assert first.report.losses[0].disposition == "recovery_manifest"
    assert validate_qdpx(first.payload).valid is True
    with ZipFile(BytesIO(first.payload)) as archive:
        assert archive.namelist() == [
            "project.qde",
            f"Sources/{SOURCE_ID}.txt",
            f"Sources/{MEMO_ID}.txt",
        ]
        project_xml = archive.read("project.qde").decode("utf-8")
        assert archive.read(f"Sources/{SOURCE_ID}.txt").decode("utf-8") == project.sources[
            0
        ].plain_text
        assert archive.read(f"Sources/{MEMO_ID}.txt").decode("utf-8") == project.memos[
            0
        ].content
    assert 'xmlns="urn:QDA-XML:project:1.0"' in project_xml
    assert "qunxue" not in project_xml.lower()
    assert f'plainTextPath="internal://{SOURCE_ID}.txt"' in project_xml
    assert "PlainTextSelection" in project_xml


def test_qdpx_round_trip_preserves_standard_ids_coding_cases_sets_and_links() -> None:
    project = _social_research_project()

    imported = import_qdpx(export_qdpx(project).payload)

    assert imported.report.losses == ()
    assert imported.project == replace(project, project_id=None)


def test_qdpx_import_rejects_archives_with_path_traversal_or_invalid_schema() -> None:
    invalid = BytesIO()
    with ZipFile(invalid, "w") as archive:
        archive.writestr("../project.qde", b"<Project />")

    with pytest.raises(ValueError, match="unsafe archive member"):
        import_qdpx(invalid.getvalue())

    invalid = BytesIO()
    with ZipFile(invalid, "w") as archive:
        archive.writestr(
            "project.qde",
            b'<Project xmlns="urn:QDA-XML:project:1.0" />',
        )

    with pytest.raises(ValueError, match="schema"):
        import_qdpx(invalid.getvalue())


def test_committed_social_research_fixture_validates_and_imports() -> None:
    payload = FIXTURE.read_bytes()

    assert validate_qdpx(payload).valid is True
    project = import_qdpx(payload).project
    assert project.name == "社区照护田野研究"
    assert project.origin == "Qunxue interoperability fixture"
    assert [source.name for source in project.sources] == ["访谈01.txt"]
    assert {code.name for code in project.codes} == {"照护网络", "家庭外照护"}
    assert project.cases[0].attributes == {"社区": "青禾里", "访谈轮次": 1}
