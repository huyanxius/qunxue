import json
import re
from dataclasses import asdict, is_dataclass
from datetime import datetime
from enum import Enum
from http.client import HTTPException
from typing import Literal, TypeVar
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from qunxue_api.adapters.model.types import (
    ModelCapabilityName,
    ModelProviderDescriptor,
    ModelProviderFailure,
    ModelProviderResult,
    ModelScenario,
)
from qunxue_api.modules.research_framework import (
    AuditFindingDraft,
    AuditFindingSeverity,
    AuditFindingType,
    AuditOverallStatus,
    ConceptMappingDraft,
    FrameworkAuditDraft,
    FrameworkEvidenceRequirementDraft,
    FrameworkVersionSnapshot,
    InferenceLinkDraft,
    MethodPlanDraft,
    ResearchFrameworkDraft,
    ResearchFrameworkDraftInput,
)
from qunxue_api.modules.research_intake import PhenomenonCandidateDraft
from qunxue_api.modules.theory_matching import (
    TheoryJudgementDraft,
    TheoryJudgementInput,
    TheoryJudgementVerdict,
)

_MAX_RESPONSE_BYTES = 1_000_000
_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_RESERVED_HEADERS = {"authorization", "content-length", "content-type", "host"}
ResponseT = TypeVar("ResponseT", bound=BaseModel)


class _StrictResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")


class _PhenomenonOutput(_StrictResponse):
    phenomenon: str = Field(min_length=1)
    research_intent: str | None
    context: str | None
    source_ref_ids: list[str]


class _PhenomenonResponse(_StrictResponse):
    status: Literal["ok"]
    knowledge_release_id: None
    theory_ids: list[str]
    output: _PhenomenonOutput


class _JudgementOutput(_StrictResponse):
    verdict: TheoryJudgementVerdict
    match_rationale: str = Field(min_length=1)
    applicable_conditions: list[str]
    limitations: list[str]
    material_requirements: list[str]
    evidence_gaps: list[str]
    alternative_explanations: list[str]
    evidence_ref_ids: list[str]
    supporting_evidence_ref_ids: list[str] = Field(default_factory=list)
    conflicting_evidence_ref_ids: list[str] = Field(default_factory=list)


class _JudgementResponse(_StrictResponse):
    status: Literal["ok"]
    knowledge_release_id: str
    theory_ids: list[str]
    output: _JudgementOutput


class _ConceptMappingOutput(_StrictResponse):
    candidate_id: UUID
    theory_concept: str
    meaning_in_study: str
    empirical_indicators: list[str]
    unresolved_questions: list[str]


class _EvidenceRequirementOutput(_StrictResponse):
    requirement_id: str
    related_candidate_ids: list[UUID]
    purpose: str
    required_material: str
    supporting_signal: str
    excluding_signal: str
    distinguishing_signal: str | None
    current_gap: str | None


class _InferenceLinkOutput(_StrictResponse):
    from_ref: str
    to_ref: str
    relation: str
    rationale: str
    unresolved: bool


class _MethodPlanOutput(_StrictResponse):
    method_kind: str
    rationale: str
    material_plan: list[str]
    analysis_plan: list[str]
    integration_points: list[str]


class _FrameworkOutput(_StrictResponse):
    concept_mappings: list[_ConceptMappingOutput]
    evidence_requirements: list[_EvidenceRequirementOutput]
    inference_links: list[_InferenceLinkOutput]
    alternative_explanations: list[str]
    method_plan: _MethodPlanOutput | None
    scope_and_limitations: list[str]
    unresolved_items: list[str]
    next_actions: list[str]
    ethical_boundaries: list[str]


class _FrameworkResponse(_StrictResponse):
    status: Literal["ok"]
    knowledge_release_id: str
    theory_ids: list[str]
    output: _FrameworkOutput


class _AuditFindingOutput(_StrictResponse):
    summary: str
    reason: str
    impact: str
    recommendation: str
    blocking: bool
    finding_type: AuditFindingType
    severity: AuditFindingSeverity


class _AuditOutput(_StrictResponse):
    overall_status: AuditOverallStatus
    findings: list[_AuditFindingOutput]


class _AuditResponse(_StrictResponse):
    status: Literal["ok"]
    knowledge_release_id: str
    theory_ids: list[str]
    output: _AuditOutput


class _InsufficientSourcesResponse(_StrictResponse):
    status: Literal["insufficient_sources"]
    knowledge_release_id: str | None
    theory_ids: list[str]


class OpenAICompatibleModelProvider:
    """OpenAI Chat Completions transport mapped onto the shared model port."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
        capability_tier: str,
        extra_headers: dict[str, str] | None = None,
    ) -> None:
        parsed_url = urlsplit(base_url)
        if (
            parsed_url.scheme not in {"http", "https"}
            or not parsed_url.netloc
            or parsed_url.username is not None
            or parsed_url.password is not None
            or parsed_url.query
            or parsed_url.fragment
        ):
            raise ValueError("model base URL must be an HTTP(S) URL without credentials")
        if not model.strip():
            raise ValueError("model name must not be empty")
        if timeout_seconds <= 0:
            raise ValueError("model timeout must be greater than zero")
        if capability_tier not in {"base", "sft"}:
            raise ValueError("model capability tier must be base or sft")

        self._extra_headers = _validated_headers(extra_headers or {})
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._api_key = _validated_api_key(api_key)
        self._model = model.strip()
        self._timeout_seconds = timeout_seconds
        self._descriptor = ModelProviderDescriptor(
            provider="openai-compatible",
            model_version=self._model,
            capability_tier=capability_tier,
            demonstration=False,
        )

    @property
    def descriptor(self) -> ModelProviderDescriptor:
        return self._descriptor

    def probe(self) -> None:
        """Send the smallest useful completion request to verify reachability."""

        request_body = json.dumps(
            {
                "model": self._model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "max_tokens": 1,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        self._send(request_body=request_body, knowledge_release_id=None)

    def extract_phenomenon(
        self,
        *,
        raw_input: str,
        research_intent: str | None,
        context: str | None,
    ) -> ModelProviderResult[PhenomenonCandidateDraft]:
        allowed = _allowed_references()
        content = self._complete(
            capability=ModelCapabilityName.PHENOMENON_EXTRACTION,
            response_type=_PhenomenonResponse,
            input_payload={
                "raw_input": raw_input,
                "research_intent": research_intent,
                "context": context,
            },
            allowed_references=allowed,
            knowledge_release_id=None,
        )
        response = self._validated_response(
            content,
            response_type=_PhenomenonResponse,
            allowed_references=allowed,
            knowledge_release_id=None,
        )
        assert isinstance(response, _PhenomenonResponse)
        if not set(response.output.source_ref_ids) <= {"input:direct"}:
            self._raise_invalid_output(knowledge_release_id=None)
        return ModelProviderResult(
            output=PhenomenonCandidateDraft(
                phenomenon=response.output.phenomenon,
                research_intent=response.output.research_intent,
                context=response.output.context,
                source_ref_ids=tuple(response.output.source_ref_ids),
            ),
            knowledge_release_id=None,
        )

    def judge_candidate(
        self,
        *,
        input: TheoryJudgementInput,
    ) -> ModelProviderResult[TheoryJudgementDraft]:
        knowledge_release_id = input.knowledge_release.knowledge_release_id
        allowed = _allowed_references(
            knowledge_release_ids=(knowledge_release_id,),
            theory_ids=_theory_ids(
                input.candidate,
                *input.comparison_candidates,
            ),
            evidence_ref_ids=tuple(
                item.evidence_ref_id for item in input.evidence_items
            ),
        )
        content = self._complete(
            capability=ModelCapabilityName.CANDIDATE_JUDGEMENT_AND_RERANK,
            response_type=_JudgementResponse,
            input_payload=input,
            allowed_references=allowed,
            knowledge_release_id=knowledge_release_id,
        )
        response = self._validated_response(
            content,
            response_type=_JudgementResponse,
            allowed_references=allowed,
            knowledge_release_id=knowledge_release_id,
        )
        assert isinstance(response, _JudgementResponse)
        output = response.output
        referenced_evidence_ids = {
            *output.evidence_ref_ids,
            *output.supporting_evidence_ref_ids,
            *output.conflicting_evidence_ref_ids,
        }
        if not referenced_evidence_ids <= set(allowed["evidence_ref_ids"]):
            self._raise_invalid_output(knowledge_release_id=knowledge_release_id)
        supporting_evidence_ref_ids = tuple(
            output.supporting_evidence_ref_ids or output.evidence_ref_ids
        )
        conflicting_evidence_ref_ids = tuple(output.conflicting_evidence_ref_ids)
        evidence_ref_ids = tuple(
            dict.fromkeys(
                (
                    *output.evidence_ref_ids,
                    *supporting_evidence_ref_ids,
                    *conflicting_evidence_ref_ids,
                )
            )
        )
        return ModelProviderResult(
            output=TheoryJudgementDraft(
                verdict=output.verdict,
                match_rationale=output.match_rationale,
                applicable_conditions=tuple(output.applicable_conditions),
                limitations=tuple(output.limitations),
                material_requirements=tuple(output.material_requirements),
                evidence_gaps=tuple(output.evidence_gaps),
                alternative_explanations=tuple(output.alternative_explanations),
                evidence_ref_ids=evidence_ref_ids,
                supporting_evidence_ref_ids=supporting_evidence_ref_ids,
                conflicting_evidence_ref_ids=conflicting_evidence_ref_ids,
            ),
            knowledge_release_id=knowledge_release_id,
        )

    def draft_framework(
        self,
        *,
        input: ResearchFrameworkDraftInput,
    ) -> ModelProviderResult[ResearchFrameworkDraft]:
        theory_plan = input.theory_plan
        knowledge_release_id = theory_plan.knowledge_release.knowledge_release_id
        allowed = _allowed_references(
            knowledge_release_ids=(knowledge_release_id,),
            theory_ids=_theory_ids(
                *(candidate.content for candidate in theory_plan.candidates)
            ),
            evidence_ref_ids=tuple(
                item.evidence_ref_id
                for item in theory_plan.evidence_bundle.evidence_items
            ),
            candidate_ids=tuple(
                str(candidate.candidate_id) for candidate in theory_plan.candidates
            ),
        )
        content = self._complete(
            capability=ModelCapabilityName.FRAMEWORK_DRAFT,
            response_type=_FrameworkResponse,
            input_payload=input,
            allowed_references=allowed,
            knowledge_release_id=knowledge_release_id,
        )
        response = self._validated_response(
            content,
            response_type=_FrameworkResponse,
            allowed_references=allowed,
            knowledge_release_id=knowledge_release_id,
        )
        assert isinstance(response, _FrameworkResponse)
        self._validate_framework_references(
            response.output,
            allowed_candidate_ids=set(allowed["candidate_ids"]),
            knowledge_release_id=knowledge_release_id,
        )
        output = response.output
        method_plan = (
            MethodPlanDraft(
                method_kind=output.method_plan.method_kind,
                rationale=output.method_plan.rationale,
                material_plan=tuple(output.method_plan.material_plan),
                analysis_plan=tuple(output.method_plan.analysis_plan),
                integration_points=tuple(output.method_plan.integration_points),
            )
            if output.method_plan is not None
            else None
        )
        return ModelProviderResult(
            output=ResearchFrameworkDraft(
                concept_mappings=tuple(
                    ConceptMappingDraft(
                        candidate_id=item.candidate_id,
                        theory_concept=item.theory_concept,
                        meaning_in_study=item.meaning_in_study,
                        empirical_indicators=tuple(item.empirical_indicators),
                        unresolved_questions=tuple(item.unresolved_questions),
                    )
                    for item in output.concept_mappings
                ),
                evidence_requirements=tuple(
                    FrameworkEvidenceRequirementDraft(
                        requirement_id=item.requirement_id,
                        related_candidate_ids=tuple(item.related_candidate_ids),
                        purpose=item.purpose,
                        required_material=item.required_material,
                        supporting_signal=item.supporting_signal,
                        excluding_signal=item.excluding_signal,
                        distinguishing_signal=item.distinguishing_signal,
                        current_gap=item.current_gap,
                    )
                    for item in output.evidence_requirements
                ),
                inference_links=tuple(
                    InferenceLinkDraft(
                        from_ref=item.from_ref,
                        to_ref=item.to_ref,
                        relation=item.relation,
                        rationale=item.rationale,
                        unresolved=item.unresolved,
                    )
                    for item in output.inference_links
                ),
                alternative_explanations=tuple(output.alternative_explanations),
                method_plan=method_plan,
                scope_and_limitations=tuple(output.scope_and_limitations),
                unresolved_items=tuple(output.unresolved_items),
                next_actions=tuple(output.next_actions),
                ethical_boundaries=tuple(output.ethical_boundaries),
            ),
            knowledge_release_id=knowledge_release_id,
        )

    def audit_framework(
        self,
        *,
        framework: FrameworkVersionSnapshot,
    ) -> ModelProviderResult[FrameworkAuditDraft]:
        theory_plan = framework.input.theory_plan
        knowledge_release_id = theory_plan.knowledge_release.knowledge_release_id
        allowed = _allowed_references(
            knowledge_release_ids=(knowledge_release_id,),
            theory_ids=_theory_ids(
                *(candidate.content for candidate in theory_plan.candidates)
            ),
            evidence_ref_ids=tuple(
                item.evidence_ref_id
                for item in theory_plan.evidence_bundle.evidence_items
            ),
            candidate_ids=tuple(
                str(candidate.candidate_id) for candidate in theory_plan.candidates
            ),
        )
        content = self._complete(
            capability=ModelCapabilityName.FRAMEWORK_AUDIT,
            response_type=_AuditResponse,
            input_payload=framework,
            allowed_references=allowed,
            knowledge_release_id=knowledge_release_id,
        )
        response = self._validated_response(
            content,
            response_type=_AuditResponse,
            allowed_references=allowed,
            knowledge_release_id=knowledge_release_id,
        )
        assert isinstance(response, _AuditResponse)
        return ModelProviderResult(
            output=FrameworkAuditDraft(
                overall_status=response.output.overall_status,
                findings=tuple(
                    AuditFindingDraft(
                        summary=item.summary,
                        reason=item.reason,
                        impact=item.impact,
                        recommendation=item.recommendation,
                        blocking=item.blocking,
                        finding_type=item.finding_type,
                        severity=item.severity,
                    )
                    for item in response.output.findings
                ),
            ),
            knowledge_release_id=knowledge_release_id,
        )

    def _complete(
        self,
        *,
        capability: ModelCapabilityName,
        response_type: type[BaseModel],
        input_payload: object,
        allowed_references: dict[str, list[str]],
        knowledge_release_id: str | None,
    ) -> dict[str, object]:
        user_payload = {
            "contract_version": "openai-compatible-model-provider.v1",
            "capability": capability.value,
            "allowed_references": allowed_references,
            "response_contract": {
                "success": response_type.model_json_schema(),
                "insufficient_sources": (
                    _InsufficientSourcesResponse.model_json_schema()
                ),
            },
            "input": _to_jsonable(input_payload),
        }
        judgement_instruction = (
            " For candidate judgement, classify allowed evidence references into "
            "supporting_evidence_ref_ids and conflicting_evidence_ref_ids. Theory-source "
            "claims establish the theory; confirmed phenomenon evidence tests its fit. "
            "Leave a list empty when the input has no evidence for that direction."
            if capability is ModelCapabilityName.CANDIDATE_JUDGEMENT_AND_RERANK
            else ""
        )
        request_body = json.dumps(
            {
                "model": self._model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Return one JSON object matching response_contract. "
                            "Use only IDs in allowed_references and never make "
                            f"a user decision.{judgement_instruction}"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            user_payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
        raw_response = self._send(
            request_body=request_body,
            knowledge_release_id=knowledge_release_id,
        )

        if len(raw_response) > _MAX_RESPONSE_BYTES:
            self._raise_invalid_output(knowledge_release_id=knowledge_release_id)
        try:
            completion = json.loads(raw_response)
            if not isinstance(completion, dict):
                self._raise_invalid_output(knowledge_release_id=knowledge_release_id)
            choices = completion.get("choices")
            if not isinstance(choices, list) or not choices:
                self._raise_invalid_output(knowledge_release_id=knowledge_release_id)
            choice = choices[0]
            if not isinstance(choice, dict):
                self._raise_invalid_output(knowledge_release_id=knowledge_release_id)
            if choice.get("finish_reason") not in {None, "stop"}:
                self._raise_invalid_output(knowledge_release_id=knowledge_release_id)
            message = choice.get("message")
            if not isinstance(message, dict):
                self._raise_invalid_output(knowledge_release_id=knowledge_release_id)
            content = message.get("content")
            if not isinstance(content, str):
                self._raise_invalid_output(knowledge_release_id=knowledge_release_id)
            decoded = json.loads(content)
            if not isinstance(decoded, dict):
                self._raise_invalid_output(knowledge_release_id=knowledge_release_id)
            return decoded
        except ModelProviderFailure:
            raise
        except (KeyError, IndexError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
            self._raise_invalid_output(knowledge_release_id=knowledge_release_id)

    def _send(
        self,
        *,
        request_body: bytes,
        knowledge_release_id: str | None,
    ) -> bytes:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            **self._extra_headers,
        }
        if self._api_key is not None:
            headers["Authorization"] = f"Bearer {self._api_key}"
        request = Request(
            self._endpoint,
            data=request_body,
            headers=headers,
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                raw_response = response.read(_MAX_RESPONSE_BYTES + 1)
                declared_length = response.headers.get("Content-Length")
                if (
                    declared_length is not None
                    and int(declared_length) > len(raw_response)
                ):
                    raise ModelProviderFailure(
                        code="model_unavailable",
                        message=(
                            "The model provider closed the response before it completed."
                        ),
                        knowledge_release_id=knowledge_release_id,
                        scenario=ModelScenario.PROVIDER_UNAVAILABLE,
                    )
        except HTTPError as error:
            if error.code == 429:
                raise ModelProviderFailure(
                    code="model_rate_limited",
                    message="The model provider rate limit was reached. Retry later.",
                    knowledge_release_id=knowledge_release_id,
                    scenario=ModelScenario.RATE_LIMITED,
                ) from error
            if error.code in {408, 409} or 500 <= error.code < 600:
                raise ModelProviderFailure(
                    code="model_unavailable",
                    message="The model provider could not complete the request.",
                    knowledge_release_id=knowledge_release_id,
                    scenario=ModelScenario.PROVIDER_UNAVAILABLE,
                ) from error
            raise ModelProviderFailure(
                code="model_request_rejected",
                message="The model provider rejected the request.",
                knowledge_release_id=knowledge_release_id,
                scenario=ModelScenario.REQUEST_REJECTED,
            ) from error
        except TimeoutError as error:
            raise ModelProviderFailure(
                code="model_timeout",
                message="The model provider timed out. The invocation can be retried.",
                knowledge_release_id=knowledge_release_id,
                scenario=ModelScenario.TIMEOUT,
            ) from error
        except URLError as error:
            raise ModelProviderFailure(
                code="model_unavailable",
                message="The model provider is unavailable. The invocation can be retried.",
                knowledge_release_id=knowledge_release_id,
                scenario=ModelScenario.PROVIDER_UNAVAILABLE,
            ) from error
        except ModelProviderFailure:
            raise
        except (HTTPException, ConnectionError, OSError, ValueError) as error:
            raise ModelProviderFailure(
                code="model_unavailable",
                message="The model provider connection ended unexpectedly.",
                knowledge_release_id=knowledge_release_id,
                scenario=ModelScenario.PROVIDER_UNAVAILABLE,
            ) from error

        return raw_response

    def _validated_response(
        self,
        content: dict[str, object],
        *,
        response_type: type[ResponseT],
        allowed_references: dict[str, list[str]],
        knowledge_release_id: str | None,
    ) -> ResponseT:
        try:
            if content.get("status") == "insufficient_sources":
                response = _InsufficientSourcesResponse.model_validate(content)
                self._validate_common_references(
                    response.knowledge_release_id,
                    response.theory_ids,
                    allowed_references=allowed_references,
                    knowledge_release_id=knowledge_release_id,
                )
                raise ModelProviderFailure(
                    code="insufficient_sources",
                    message="The available sources are insufficient for this model invocation.",
                    knowledge_release_id=knowledge_release_id,
                    scenario=ModelScenario.INSUFFICIENT_SOURCES,
                )
            response = response_type.model_validate(content)
            self._validate_common_references(
                response.knowledge_release_id,  # type: ignore[attr-defined]
                response.theory_ids,  # type: ignore[attr-defined]
                allowed_references=allowed_references,
                knowledge_release_id=knowledge_release_id,
            )
            return response
        except ModelProviderFailure:
            raise
        except (ValidationError, TypeError, ValueError):
            self._raise_invalid_output(knowledge_release_id=knowledge_release_id)

    def _validate_common_references(
        self,
        response_release_id: str | None,
        response_theory_ids: list[str],
        *,
        allowed_references: dict[str, list[str]],
        knowledge_release_id: str | None,
    ) -> None:
        if response_release_id != knowledge_release_id or not set(
            response_theory_ids
        ) <= set(allowed_references["theory_ids"]):
            self._raise_invalid_output(knowledge_release_id=knowledge_release_id)

    def _validate_framework_references(
        self,
        output: _FrameworkOutput,
        *,
        allowed_candidate_ids: set[str],
        knowledge_release_id: str,
    ) -> None:
        referenced_candidate_ids = {
            str(item.candidate_id) for item in output.concept_mappings
        } | {
            str(candidate_id)
            for item in output.evidence_requirements
            for candidate_id in item.related_candidate_ids
        }
        requirement_ids = {
            item.requirement_id for item in output.evidence_requirements
        }
        link_refs = {
            value
            for item in output.inference_links
            for value in (item.from_ref, item.to_ref)
        }
        if (
            not referenced_candidate_ids <= allowed_candidate_ids
            or not link_refs <= (allowed_candidate_ids | requirement_ids)
        ):
            self._raise_invalid_output(knowledge_release_id=knowledge_release_id)

    @staticmethod
    def _raise_invalid_output(*, knowledge_release_id: str | None) -> None:
        raise ModelProviderFailure(
            code="model_invalid_output",
            message="The model provider returned output outside the accepted contract.",
            knowledge_release_id=knowledge_release_id,
            scenario=ModelScenario.INVALID_OUTPUT,
        )


def _validated_headers(headers: dict[str, str]) -> dict[str, str]:
    validated: dict[str, str] = {}
    for name, value in headers.items():
        if (
            not _HEADER_NAME.fullmatch(name)
            or name.lower() in _RESERVED_HEADERS
            or "\r" in value
            or "\n" in value
        ):
            raise ValueError("invalid or reserved model extension header")
        validated[name] = value
    return validated


def _validated_api_key(api_key: str | None) -> str | None:
    if api_key is None or api_key == "":
        return None
    if any(ord(character) < 0x21 or ord(character) > 0x7E for character in api_key):
        raise ValueError("invalid model API key header value")
    return api_key


def _allowed_references(
    *,
    knowledge_release_ids: tuple[str, ...] = (),
    theory_ids: tuple[str, ...] = (),
    evidence_ref_ids: tuple[str, ...] = (),
    candidate_ids: tuple[str, ...] = (),
) -> dict[str, list[str]]:
    return {
        "knowledge_release_ids": list(dict.fromkeys(knowledge_release_ids)),
        "theory_ids": list(dict.fromkeys(theory_ids)),
        "evidence_ref_ids": list(dict.fromkeys(evidence_ref_ids)),
        "candidate_ids": list(dict.fromkeys(candidate_ids)),
    }


def _theory_ids(*candidates: object) -> tuple[str, ...]:
    return tuple(
        theory_id
        for candidate in candidates
        if (theory_id := getattr(candidate, "theory_id", None)) is not None
    )


def _to_jsonable(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_jsonable(asdict(value))
    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"unsupported model request value: {type(value).__name__}")
