import json
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from qunxue_api.adapters.sqlite.database import Database
from qunxue_api.adapters.sqlite.knowledge_catalog import SqliteKnowledgeCatalog
from qunxue_api.adapters.sqlite.knowledge_catalog_model import KnowledgeEntryReviewRow
from qunxue_api.modules.knowledge_catalog import (
    KnowledgeReleaseLevel,
    KnowledgeReviewStatus,
    KnowledgeUsePurpose,
)


def _hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{sha256(encoded.encode()).hexdigest()}"


def _profile(index: int) -> dict[str, object]:
    knowledge_id = f"D1:C00{index}"
    source_id = f"source:pre-reviewed:theory-{index}"
    profile = {
        "theory_id": f"theory-pre-reviewed-{index}",
        "related_knowledge_ids": [knowledge_id],
        "title": f"已审校理论 {index}",
        "core_propositions": [f"理论 {index} 的核心命题"],
        "applicable_phenomena": ["社区互动与成员流动"],
        "analysis_levels": ["关系", "组织"],
        "prerequisites": ["存在可观察的持续互动"],
        "exclusion_signals": ["不存在成员之间的互动记录"],
        "observable_evidence": ["互动频率与互助记录"],
        "competing_or_complementary_theory_ids": [
            f"theory-pre-reviewed-{value}" for value in range(1, 4) if value != index
        ],
        "source_ids": [source_id],
        "content_version": 1,
    }
    return {
        **profile,
        "sources": [
            {
                "source_id": source_id,
                "source_type": "book",
                "title": f"Theory source {index}",
                "authors_or_institution": ["Test Sociology Press"],
                "year": 2024,
            "publication": "Test-only pre-reviewed source fixture",
                "locator": f"chapter {index}, pp. {index * 10}-{index * 10 + 9}",
                "url": f"https://example.test/theory-{index}",
                "verification_status": "verified",
                "use_boundary": "仅用于验证正式发布流程的测试来源。",
            }
        ],
        "review": {
            "review_record_id": f"review:theory-{index}:v1",
            "review_status": "pre_review_completed",
            "reviewer_id": "human-pre-review:test-team",
            "reviewer_display_name": "测试真实人员初审组",
            "reviewer_credentials": "未声明专家终审资质；仅验证预审核状态",
            "review_completed_at": None,
            "recorded_at": datetime(2026, 8, 22, index, tzinfo=UTC).isoformat(),
            "subject_hash": _hash(profile),
            "decision": "approved_for_internal_match",
            "notes": "实际初审完成时间未单独登记；recorded_at 是状态确认时间。",
            "attestation": (
                "真实人员已完成初步审核，仅供内测匹配；不代表专家终审或全面审核，"
                "后续仍可深度复核。"
            ),
        },
    }


def _write_bundle(
    path: Path,
    *,
    base_release_id: str,
    profiles: list[dict[str, object]] | None = None,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "pre-reviewed-theory-release/v1",
                "release_key": "pre-reviewed-theories-test-v1",
                "base_release_id": base_release_id,
                "profiles": profiles or [_profile(1), _profile(2), _profile(3)],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def test_match_release_never_falls_back_to_a_preview_without_pre_review(
    client: TestClient,
) -> None:
    preview = client.app.state.knowledge_catalog.current_release(
        purpose=KnowledgeUsePurpose.BROWSE
    )

    with pytest.raises(LookupError, match="final MATCH knowledge release"):
        client.app.state.knowledge_catalog.current_release(
            purpose=KnowledgeUsePurpose.MATCH
        )

    assert preview.level is KnowledgeReleaseLevel.PREVIEW


def test_pre_reviewed_bundle_installs_one_reproducible_final_release(
    client: TestClient,
    tmp_path: Path,
) -> None:
    catalog = client.app.state.knowledge_catalog
    preview = catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
    bundle_path = _write_bundle(
        tmp_path / "pre-reviewed-theories.json",
        base_release_id=preview.knowledge_release_id,
    )

    first = catalog.install_pre_reviewed_bundle(bundle_path)
    replayed = catalog.install_pre_reviewed_bundle(bundle_path)
    match_release = catalog.current_release(purpose=KnowledgeUsePurpose.MATCH)

    assert first == replayed
    assert first.release == match_release
    assert first.release.level is KnowledgeReleaseLevel.FINAL
    assert first.theory_ids == (
        "theory-pre-reviewed-1",
        "theory-pre-reviewed-2",
        "theory-pre-reviewed-3",
    )
    assert first.review_record_ids == (
        "review:theory-1:v1",
        "review:theory-2:v1",
        "review:theory-3:v1",
    )
    assert catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE) == preview

    page = catalog.browse(
        release_id=first.release.knowledge_release_id,
        query=None,
        category=None,
        category_id=None,
        dimension_id=None,
        cursor=None,
        limit=10,
    )
    eligible = [item for item in page.entries if item.eligibility.match_eligible]
    assert [item.knowledge_id for item in eligible] == ["D1:C001", "D1:C002", "D1:C003"]
    detail = catalog.get_entry(
        knowledge_id="D1:C001",
        release_id=first.release.knowledge_release_id,
    )
    assert detail.theory_profile is not None
    assert detail.theory_profile.review_status is KnowledgeReviewStatus.PRE_REVIEW_COMPLETED
    assert detail.theory_profile.match_eligible is True
    assert detail.sources[0].locator == "chapter 1, pp. 10-19"

    with client.app.state.database.session() as session:
        review = session.scalar(
            select(KnowledgeEntryReviewRow).where(
                KnowledgeEntryReviewRow.knowledge_release_id
                == first.release.knowledge_release_id,
                KnowledgeEntryReviewRow.review_record_id == "review:theory-1:v1",
            )
        )
        assert review is not None
        assert review.theory_id == "theory-pre-reviewed-1"
        assert review.review_status == "pre_review_completed"
        assert review.reviewer_id == "human-pre-review:test-team"
        assert review.reviewer_display_name == "测试真实人员初审组"
        assert review.reviewer_credentials == "未声明专家终审资质；仅验证预审核状态"
        assert review.reviewed_subject_hash == _profile(1)["review"]["subject_hash"]
        assert review.decision == "approved_for_internal_match"
        assert "recorded_at 是状态确认时间" in review.review_notes
        assert review.attestation

    restarted_database = Database(client.app.state.settings.database_url)
    try:
        restarted_catalog = SqliteKnowledgeCatalog(
            restarted_database,
            knowledge_root=Path(__file__).parents[2] / "knowledge",
        )
        assert (
            restarted_catalog.current_release(purpose=KnowledgeUsePurpose.MATCH)
            == match_release
        )
        assert restarted_catalog.get_manifest(match_release.knowledge_release_id) == first
    finally:
        restarted_database.engine.dispose()


def test_concurrent_pre_reviewed_bundle_install_converges_on_one_release(
    client: TestClient,
    tmp_path: Path,
) -> None:
    catalog = client.app.state.knowledge_catalog
    preview = catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
    bundle_path = _write_bundle(
        tmp_path / "pre-reviewed-theories.json",
        base_release_id=preview.knowledge_release_id,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        manifests = list(
            executor.map(lambda _: catalog.install_pre_reviewed_bundle(bundle_path), range(2))
        )

    assert manifests[0] == manifests[1]
    assert catalog.current_release(purpose=KnowledgeUsePurpose.MATCH) == manifests[0].release


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (
            lambda profile: profile["review"].update({"attestation": ""}),
            "human review attestation",
        ),
        (
            lambda profile: profile["review"].update({"subject_hash": "sha256:stale"}),
            "pre-review subject hash",
        ),
        (
            lambda profile: profile["review"].update({"review_status": "reviewed"}),
            "review status",
        ),
        (
            lambda profile: profile["review"].update({"decision": "approved"}),
            "decision",
        ),
        (
            lambda profile: profile["sources"][0].update({"locator": None}),
            "source locator",
        ),
        (
            lambda profile: profile["sources"][0].update({"url": "file:///tmp/source"}),
            "source URL",
        ),
    ],
)
def test_invalid_pre_review_bundle_cannot_promote_a_profile(
    client: TestClient,
    tmp_path: Path,
    mutate,
    message: str,
) -> None:
    catalog = client.app.state.knowledge_catalog
    preview = catalog.current_release(purpose=KnowledgeUsePurpose.BROWSE)
    profiles = [_profile(1), _profile(2), _profile(3)]
    mutate(profiles[0])
    bundle_path = _write_bundle(
        tmp_path / "invalid-pre-reviewed-theories.json",
        base_release_id=preview.knowledge_release_id,
        profiles=profiles,
    )

    with pytest.raises(ValueError, match=message):
        catalog.install_pre_reviewed_bundle(bundle_path)

    with pytest.raises(LookupError):
        catalog.current_release(purpose=KnowledgeUsePurpose.MATCH)
