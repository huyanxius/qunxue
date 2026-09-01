"""Regenerate the deterministic social-research QDPX interoperability fixture."""

from pathlib import Path
from uuid import UUID

from qunxue_api.modules.research_exchange import (
    QdpxCase,
    QdpxCode,
    QdpxCoding,
    QdpxMemo,
    QdpxProject,
    QdpxSelection,
    QdpxSet,
    QdpxSource,
    QdpxSourceKind,
    export_qdpx,
)

OUTPUT = (
    Path(__file__).parents[1]
    / "tests"
    / "fixtures"
    / "qdpx"
    / "community-care-interview.qdpx"
)


def build_fixture() -> bytes:
    source_id = UUID("71000000-0000-4000-8000-000000000001")
    selection_id = UUID("71000000-0000-4000-8000-000000000002")
    parent_code_id = UUID("71000000-0000-4000-8000-000000000003")
    code_id = UUID("71000000-0000-4000-8000-000000000004")
    memo_id = UUID("71000000-0000-4000-8000-000000000005")
    text = "受访者说，照护不只发生在家庭内部，邻居会轮流接送老人去社区卫生站。"
    quote = "邻居会轮流接送老人"
    start = text.index(quote)
    project = QdpxProject(
        project_id=UUID("71000000-0000-4000-8000-000000000000"),
        name="社区照护田野研究",
        origin="Qunxue interoperability fixture",
        description="用于验证社会研究项目在 REFI-QDA Project 1.0 中的标准表达。",
        codes=(
            QdpxCode(code_id=parent_code_id, name="照护网络"),
            QdpxCode(
                code_id=code_id,
                name="家庭外照护",
                description="由邻居或社区成员承担的日常照护。",
                parent_code_id=parent_code_id,
            ),
        ),
        sources=(
            QdpxSource(
                source_id=source_id,
                name="访谈01.txt",
                kind=QdpxSourceKind.TEXT,
                plain_text=text,
                selections=(
                    QdpxSelection(
                        selection_id=selection_id,
                        start_position=start,
                        end_position=start + len(quote),
                        codings=(QdpxCoding(coding_id=code_id, code_id=code_id),),
                        memo_ids=(memo_id,),
                    ),
                ),
            ),
        ),
        memos=(
            QdpxMemo(
                memo_id=memo_id,
                name="社区照护备忘",
                content="照护关系跨出家庭边界，但仍需核对互惠是否稳定。",
                target_ids=(selection_id,),
            ),
        ),
        cases=(
            QdpxCase(
                case_id=UUID("71000000-0000-4000-8000-000000000006"),
                name="受访者01",
                attributes={"社区": "青禾里", "访谈轮次": 1},
                source_ids=(source_id,),
                selection_ids=(selection_id,),
            ),
        ),
        sets=(
            QdpxSet(
                set_id=UUID("71000000-0000-4000-8000-000000000007"),
                name="第一轮访谈",
                member_source_ids=(source_id,),
                member_code_ids=(code_id,),
                member_memo_ids=(memo_id,),
            ),
        ),
    )
    return export_qdpx(project).payload


def main() -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    payload = build_fixture()
    OUTPUT.write_bytes(payload)
    print(f"{OUTPUT}: {len(payload)} bytes")


if __name__ == "__main__":
    main()
