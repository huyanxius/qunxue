from uuid import uuid4

from fastapi.testclient import TestClient


def _authenticate(client: TestClient) -> None:
    response = client.post(
        "/api/session/register",
        headers={"Idempotency-Key": str(uuid4())},
        json={
            "email": f"{uuid4()}@example.com",
            "password": "research-passphrase",
        },
    )
    assert response.status_code == 201


def test_ten_page_contract_registers_the_required_route_surface(
    client: TestClient,
) -> None:
    schema = client.app.openapi()
    operations = {
        operation["operationId"]
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if isinstance(operation, dict) and "operationId" in operation
    }

    assert {
        "register_session",
        "login_session",
        "logout_session",
        "get_current_session",
        "create_research_task",
        "get_research_task",
        "list_research_tasks",
        "delete_research_task",
        "get_research_trace",
        "export_research_trace",
        "submit_direct_input",
        "submit_material_input",
        "extract_phenomenon_candidates",
        "get_phenomenon_candidate",
        "update_phenomenon_candidate",
        "confirm_phenomenon_candidate",
        "list_phenomenon_snapshots",
        "get_current_knowledge_release",
        "list_knowledge_entries",
        "get_knowledge_entry",
        "list_builtin_cases",
        "create_match_run",
        "get_match_run",
        "list_match_candidates",
        "retry_match_candidate",
        "acknowledge_partial_match",
        "create_theory_decisions",
        "list_theory_decisions",
        "confirm_theory_plan",
        "create_framework",
        "get_framework",
        "update_framework",
        "start_framework_review",
        "get_framework_review",
        "submit_audit_resolutions",
        "confirm_framework",
        "export_confirmed_framework",
    } <= operations
    assert not any("smart-topic" in path for path in schema["paths"])


def test_every_mutating_endpoint_requires_the_idempotency_header(
    client: TestClient,
) -> None:
    schema = client.app.openapi()

    for path, path_item in schema["paths"].items():
        for method in ("post", "patch", "put", "delete"):
            operation = path_item.get(method)
            if operation is None:
                continue
            headers = {
                parameter["name"]: parameter
                for parameter in operation.get("parameters", [])
                if parameter["in"] == "header"
            }
            assert headers["Idempotency-Key"]["required"] is True, (
                f"{method.upper()} {path} has no required Idempotency-Key"
            )


def test_stub_and_validation_failures_use_the_stable_error_envelope(
    client: TestClient,
) -> None:
    stub = client.get("/api/session")
    invalid = client.post("/api/session/logout")
    missing = client.get("/api/not-a-route")
    wrong_method = client.put("/api/session")

    assert stub.status_code == 401
    assert stub.json() == {
        "error": {
            "code": "unauthenticated",
            "message": "请先登录。",
            "trace_id": stub.json()["error"]["trace_id"],
        }
    }
    assert invalid.status_code == 422
    assert invalid.json() == {
        "error": {
            "code": "validation_error",
            "message": "Request validation failed.",
            "trace_id": invalid.json()["error"]["trace_id"],
        }
    }
    assert missing.status_code == 404
    assert missing.json() == {
        "error": {
            "code": "not_found",
            "message": "Resource not found.",
            "trace_id": missing.json()["error"]["trace_id"],
        }
    }
    assert wrong_method.status_code == 405
    assert wrong_method.json() == {
        "error": {
            "code": "method_not_allowed",
            "message": "Method not allowed.",
            "trace_id": wrong_method.json()["error"]["trace_id"],
        }
    }


def test_error_and_model_metadata_enums_are_stable(client: TestClient) -> None:
    schemas = client.app.openapi()["components"]["schemas"]

    assert schemas["ErrorDetail"]["required"] == ["code", "message", "trace_id"]
    assert {
        "unauthenticated",
        "session_expired",
        "not_found",
        "validation_error",
        "phenomenon_unconfirmed",
        "no_adopted_theory",
        "candidate_ineligible",
        "external_candidate_adoption_blocked",
        "model_timeout",
        "no_reliable_candidate",
        "insufficient_sources",
        "stale_framework_revision",
        "unresolved_blocking_audit",
    } <= set(schemas["ErrorCode"]["enum"])
    assert schemas["ModelCapability"]["enum"] == ["mock", "base", "sft"]


def test_model_metadata_marks_knowledge_release_as_nullable_not_applicable(
    client: TestClient,
) -> None:
    model = client.app.openapi()["components"]["schemas"]["ModelMetadata"]

    assert "knowledge_release_id" in model["required"]
    variants = model["properties"]["knowledge_release_id"]["anyOf"]
    assert {variant.get("type") for variant in variants} == {"string", "null"}


def test_session_and_research_contracts_preserve_state_and_trace_fields(
    client: TestClient,
) -> None:
    schema = client.app.openapi()
    schemas = schema["components"]["schemas"]

    assert {"email", "password"} <= set(schemas["RegisterSessionRequest"]["required"])
    assert {"session_id", "status", "version", "allowed_actions", "user"} <= set(
        schemas["SessionResponse"]["required"]
    )
    assert "token" not in schemas["SessionResponse"]["properties"]
    assert {"entry_type", "status", "version", "allowed_actions"} <= set(
        schemas["ResearchTaskResponse"]["required"]
    )
    assert {"task_id", "version", "allowed_actions", "events", "contract_version"} <= set(
        schemas["ResearchTraceResponse"]["required"]
    )
    assert {"markdown", "contract_version", "version", "allowed_actions"} <= set(
        schemas["MarkdownExportResponse"]["required"]
    )
    assert (
        schema["paths"]["/api/research-tasks"]["get"]["responses"]["200"]["content"]
        ["application/json"]["schema"]["$ref"]
        .endswith("/ResearchTaskPageResponse")
    )


def test_research_task_navigation_restores_my_list_and_task_only_deep_links(
    client: TestClient,
) -> None:
    schema = client.app.openapi()
    schemas = schema["components"]["schemas"]
    navigation = schemas["ResearchTaskNavigationResponse"]

    assert {
        "task_id",
        "entry_type",
        "status",
        "current_stage",
        "version",
        "allowed_actions",
        "seed_theory_id",
        "phenomenon_summary",
        "adopted_theory_count",
        "current_phenomenon_candidate_id",
        "current_match_run_id",
        "current_framework_id",
        "created_at",
        "updated_at",
    } <= set(navigation["required"])
    assert {"draft", "in_progress", "completed"} <= set(
        schemas["ResearchTaskLifecycleStatus"]["enum"]
    )
    assert {
        "phenomenon_input",
        "phenomenon_confirmation",
        "theory_matching",
        "theory_decision",
        "framework_drafting",
        "framework_review",
        "completed",
    } == set(schemas["ResearchTaskStage"]["enum"])
    assert (
        schema["paths"]["/api/research-tasks/{task_id}/navigation"]["get"]
        ["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        .endswith("/ResearchTaskNavigationResponse")
    )
    page_items = schemas["ResearchTaskPageResponse"]["properties"]["items"]["items"]
    assert page_items["$ref"].endswith("/ResearchTaskNavigationResponse")


def test_phenomenon_and_knowledge_contracts_preserve_authority_and_release(
    client: TestClient,
) -> None:
    schemas = client.app.openapi()["components"]["schemas"]
    material = schemas["MaterialInputRequest"]

    assert {
        "materials",
        "deidentification_acknowledged",
        "processing_authority_acknowledged",
        "retention_policy_acknowledged",
    } <= set(material["required"])
    assert not {
        "raw_material",
        "raw_content",
        "persist_raw_material",
    } & set(material["properties"])
    assert schemas["EntryType"]["enum"] == ["direct_input"]
    assert schemas["EntryInputType"]["enum"] == ["direct_input", "material_input"]
    assert {"candidate_id", "version", "status", "allowed_actions", "model"} <= set(
        schemas["PhenomenonCandidateResponse"]["required"]
    )
    assert {
        "provider",
        "model_version",
        "capability",
        "degraded",
        "trace",
    } <= set(schemas["ModelMetadata"]["required"])
    assert {
        "knowledge_release_id",
        "entries",
        "stable_order",
        "next_cursor",
    } <= set(schemas["KnowledgeEntryPageResponse"]["required"])
    assert {
        "knowledge_release_id",
        "knowledge_id",
        "content_version",
        "sources",
        "relations",
    } <= set(schemas["KnowledgeEntryDetailResponse"]["required"])


def test_knowledge_results_keep_directory_position_and_stable_filters(
    client: TestClient,
) -> None:
    schema = client.app.openapi()
    schemas = schema["components"]["schemas"]
    directory_node = schemas["KnowledgeDirectoryNodeResponse"]
    summary = schemas["KnowledgeEntrySummaryResponse"]
    detail = schemas["KnowledgeEntryDetailResponse"]
    operation = schema["paths"]["/api/knowledge/entries"]["get"]
    parameters = {parameter["name"] for parameter in operation["parameters"]}

    assert {"node_id", "node_type", "title"} <= set(directory_node["required"])
    assert {"category_id", "dimension_id", "directory_path"} <= set(
        summary["required"]
    )
    assert {"category_id", "dimension_id", "directory_path"} <= set(
        detail["required"]
    )
    assert {"category_id", "dimension_id"} <= parameters


def test_material_input_rejects_missing_authority_acknowledgements(
    client: TestClient,
) -> None:
    _authenticate(client)
    task = client.post(
        "/api/research-tasks",
        headers={"Idempotency-Key": str(uuid4())},
        json={"entry_type": "direct_input"},
    )
    assert task.status_code == 201
    response = client.post(
        f"/api/research-tasks/{task.json()['task_id']}/inputs/material",
        headers={"Idempotency-Key": "material-contract-key"},
        json={
            "materials": [
                {
                    "material_ref_id": "interview-1",
                    "media_type": "text/plain",
                    "deidentified_text": "A de-identified excerpt.",
                }
            ],
            "deidentification_acknowledged": False,
            "processing_authority_acknowledged": False,
            "retention_policy_acknowledged": "retain_raw",
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_phenomenon_candidates_embed_displayable_evidence_references(
    client: TestClient,
) -> None:
    schemas = client.app.openapi()["components"]["schemas"]
    evidence = schemas["PhenomenonEvidenceReferenceResponse"]

    assert {
        "evidence_ref_id",
        "excerpt",
        "source_ref_id",
        "source_description",
        "locator",
        "verification_status",
        "use_boundary",
    } <= set(evidence["required"])
    assert "evidence_refs" in schemas["PhenomenonCandidateResponse"]["required"]
    assert "evidence_refs" in schemas["PhenomenonSnapshotResponse"]["required"]


def test_match_candidates_are_dynamic_ordered_and_retryable(client: TestClient) -> None:
    schema = client.app.openapi()
    operation = schema["paths"]["/api/match-runs/{match_run_id}/candidates"]["get"]
    parameters = {parameter["name"]: parameter for parameter in operation["parameters"]}
    limit_schema = parameters["limit"]["schema"]
    candidate = schema["components"]["schemas"]["TheoryCandidateResponse"]
    match_run = schema["components"]["schemas"]["MatchRunResponse"]

    assert limit_schema["default"] == 4
    assert limit_schema["minimum"] == 1
    assert limit_schema["maximum"] == 8
    assert {
        "candidate_id",
        "version",
        "allowed_actions",
        "judgement_run_status",
        "knowledge_release_id",
        "knowledge_id",
        "theory_id",
        "seed_theory_id",
        "origin",
        "content_status",
        "core_claims",
        "analysis_levels",
        "prerequisites",
        "applicability_judgement",
        "supporting_evidence",
        "conflicting_evidence",
        "missing_evidence",
        "requested_material",
        "limitations",
        "misuse_boundaries",
        "competing_theories",
        "complementary_theories",
    } <= set(candidate["required"])
    assert not any("confidence" in name for name in candidate["properties"])
    assert {
        "version",
        "allowed_actions",
        "completion_basis",
        "partial_completion_acknowledged",
        "knowledge_release_id",
        "model",
    } <= set(match_run["required"])
    assert {
        "theory_plan_id",
        "decision_set_id",
        "version",
        "allowed_actions",
        "knowledge_release_id",
        "adopted_candidate_ids",
    } <= set(
        schema["components"]["schemas"]["ConfirmedTheoryPlanResponse"]["required"]
    )

    _authenticate(client)
    invalid = client.get(
        "/api/match-runs/00000000-0000-0000-0000-000000000001/candidates",
        params={"limit": 9},
    )
    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "validation_error"


def test_match_evidence_keeps_excerpt_locator_and_source_snapshot(
    client: TestClient,
) -> None:
    schemas = client.app.openapi()["components"]["schemas"]
    evidence = schemas["EvidenceReferenceResponse"]

    assert {
        "evidence_ref_id",
        "claim",
        "excerpt",
        "locator",
        "source",
        "verification_status",
        "use_boundary",
    } <= set(evidence["required"])
    source_schema = evidence["properties"]["source"]["anyOf"][0]["$ref"]
    assert source_schema.endswith("/SourceRecordResponse")


def test_theory_decisions_support_five_core_actions_and_explicit_defer(
    client: TestClient,
) -> None:
    schema = client.app.openapi()
    schemas = schema["components"]["schemas"]

    assert {"adopt", "exclude", "retain", "combine", "defer"} <= set(
        schemas["TheoryDecisionAction"]["enum"]
    )
    assert {"reason", "related_candidate_ids"} <= set(
        schemas["TheoryDecisionInput"]["required"]
    )
    assert {"reason", "related_candidate_ids"} <= set(
        schemas["TheoryDecisionRecordResponse"]["required"]
    )
    defer_operation = schema["paths"]["/api/match-runs/{match_run_id}/defer"][
        "post"
    ]
    assert defer_operation["operationId"] == "defer_theory_plan"
    assert (
        defer_operation["responses"]["200"]["content"]["application/json"]
        ["schema"]["$ref"]
        .endswith("/DeferredTheoryPlanResponse")
    )
    assert {"task_id", "match_run_id", "version", "allowed_actions", "reason"} <= set(
        schemas["DeferredTheoryPlanResponse"]["required"]
    )


def test_framework_contract_freezes_revision_audit_and_export_gates(
    client: TestClient,
) -> None:
    schemas = client.app.openapi()["components"]["schemas"]

    assert {
        "framework_id",
        "revision_id",
        "version",
        "status",
        "allowed_actions",
        "knowledge_release_id",
        "unresolved_blocking_audit",
        "model",
    } <= set(schemas["FrameworkResponse"]["required"])
    assert {"finding_type", "severity", "blocking"} <= set(
        schemas["AuditFindingResponse"]["required"]
    )
    assert schemas["AuditResolutionAction"]["enum"] == ["handled", "overridden"]
    assert {"revision_id", "overall_status", "unresolved_blocking", "contract_version"} <= set(
        schemas["FrameworkAuditResponse"]["required"]
    )
    assert {"expected_revision_id", "audit_id", "resolutions"} <= set(
        schemas["SubmitAuditResolutionsRequest"]["required"]
    )
    assert {
        "revision_id",
        "version",
        "allowed_actions",
        "framework_status",
        "knowledge_release_id",
        "markdown",
        "contract_version",
    } <= set(schemas["FormalFrameworkExportResponse"]["required"])


def test_framework_read_restores_confirmed_phenomenon_and_theory_plan(
    client: TestClient,
) -> None:
    schemas = client.app.openapi()["components"]["schemas"]
    theory_plan = schemas["ConfirmedTheoryPlanResponse"]

    assert {
        "confirmed_phenomenon",
        "decisions",
        "use_assignments",
        "relations",
    } <= set(theory_plan["required"])
    assert "theory_plan" in schemas["FrameworkInputResponse"]["required"]
    assert {
        "relation_id",
        "candidate_ids",
        "relation_kind",
        "explanation",
        "premise_compatibility",
    } <= set(schemas["TheoryRelationResponse"]["required"])


def test_framework_review_failures_are_recoverable_and_target_retryable(
    client: TestClient,
) -> None:
    schema = client.app.openapi()
    schemas = schema["components"]["schemas"]

    assert {"timed_out", "insufficient_sources"} <= set(
        schemas["FrameworkReviewRunStatus"]["enum"]
    )
    assert "retry" in schemas["FrameworkReviewAction"]["enum"]
    assert {"code", "message", "retryable", "requested_source_ids"} <= set(
        schemas["FrameworkReviewFailureResponse"]["required"]
    )
    assert {"retry_of_review_run_id", "attempt", "failure"} <= set(
        schemas["FrameworkReviewResponse"]["required"]
    )
    retry = schema["paths"][
        "/api/frameworks/{framework_id}/reviews/{review_run_id}/retry"
    ]["post"]
    assert retry["operationId"] == "retry_framework_review"
    assert (
        retry["responses"]["200"]["content"]["application/json"]["schema"]
        ["$ref"]
        .endswith("/FrameworkReviewResponse")
    )
    assert {"expected_revision_id", "expected_review_version"} <= set(
        schemas["RetryFrameworkReviewRequest"]["required"]
    )


def test_every_documented_json_error_uses_error_response(client: TestClient) -> None:
    schema = client.app.openapi()

    for path, path_item in schema["paths"].items():
        for method, operation in path_item.items():
            if method == "parameters" or not isinstance(operation, dict):
                continue
            for status_code, response in operation["responses"].items():
                if int(status_code) < 400 or "application/json" not in response.get(
                    "content", {}
                ):
                    continue
                response_schema = response["content"]["application/json"]["schema"]
                assert response_schema["$ref"].endswith("/ErrorResponse"), (
                    f"{method.upper()} {path} documents {status_code} with "
                    f"{response_schema}"
                )
