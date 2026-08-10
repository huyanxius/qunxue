from qunxue_api.adapters.model.cases import BuiltInCase, BuiltInCaseCatalog
from qunxue_api.adapters.model.types import (
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
    ResearchFrameworkDraft,
    ResearchFrameworkDraftInput,
)
from qunxue_api.modules.research_intake import PhenomenonCandidateDraft
from qunxue_api.modules.theory_matching import (
    TheoryDecisionAction,
    TheoryJudgementDraft,
    TheoryJudgementInput,
    TheoryJudgementVerdict,
)


class DeterministicMockModelProvider:
    def __init__(self, *, catalog: BuiltInCaseCatalog) -> None:
        self._catalog = catalog
        self._descriptor = ModelProviderDescriptor(
            provider="deterministic-mock",
            model_version="mock-sociology-v1",
            capability_tier="mock",
            demonstration=True,
        )

    @property
    def descriptor(self) -> ModelProviderDescriptor:
        return self._descriptor

    def extract_phenomenon(
        self,
        *,
        raw_input: str,
        research_intent: str | None,
        context: str | None,
    ) -> ModelProviderResult[PhenomenonCandidateDraft]:
        case = self._catalog.find_by_phenomenon(raw_input)
        self._raise_if_unavailable(
            case,
            capability="extract",
            knowledge_release_id=None,
        )
        source_ref_ids = (f"case:{case.case_id}",) if case else ("input:direct",)
        return ModelProviderResult(
            output=PhenomenonCandidateDraft(
                phenomenon=case.phenomenon if case else raw_input.strip(),
                research_intent=(
                    case.research_intent if case else self._clean_optional(research_intent)
                ),
                context=case.context if case else self._clean_optional(context),
                source_ref_ids=source_ref_ids,
            ),
            knowledge_release_id=None,
        )

    def judge_candidate(
        self,
        *,
        input: TheoryJudgementInput,
    ) -> ModelProviderResult[TheoryJudgementDraft]:
        case = self._catalog.find_by_phenomenon(input.phenomenon.phenomenon)
        self._raise_if_unavailable(
            case,
            capability="judge",
            knowledge_release_id=input.knowledge_release.knowledge_release_id,
        )
        evidence_ids = tuple(item.evidence_ref_id for item in input.evidence_items)
        title = input.candidate.title
        return ModelProviderResult(
            output=TheoryJudgementDraft(
                verdict=TheoryJudgementVerdict.CONDITIONAL,
                match_rationale=(
                    f"{title}能解释部分现象机制，但仍需用材料核对其适用前提。"
                ),
                applicable_conditions=("能够识别持续互动与制度环境",),
                limitations=("演示判断不能替代人工核验与正式来源审查",),
                material_requirements=("可比较的互动记录或去标识化访谈摘要",),
                evidence_gaps=("尚缺少时间顺序与竞争解释的区分材料",),
                alternative_explanations=("资源供给变化", "组织规则调整"),
                evidence_ref_ids=evidence_ids,
            ),
            knowledge_release_id=input.knowledge_release.knowledge_release_id,
            degraded=False,
        )

    def draft_framework(
        self,
        *,
        input: ResearchFrameworkDraftInput,
    ) -> ModelProviderResult[ResearchFrameworkDraft]:
        case = self._catalog.find_by_phenomenon(
            input.theory_plan.phenomenon.phenomenon
        )
        self._raise_if_unavailable(
            case,
            capability="framework",
            knowledge_release_id=(
                input.theory_plan.knowledge_release.knowledge_release_id
            ),
        )
        adopted_ids = {
            decision.candidate_id
            for decision in input.theory_plan.decisions
            if decision.action is TheoryDecisionAction.ADOPT
        }
        candidates = tuple(
            candidate
            for candidate in input.theory_plan.candidates
            if candidate.candidate_id in adopted_ids
        )
        concept_mappings = tuple(
            ConceptMappingDraft(
                candidate_id=candidate.candidate_id,
                theory_concept=candidate.content.title,
                meaning_in_study=(
                    f"用于解释“{input.confirmed_research_question}”中的关键机制"
                ),
                empirical_indicators=("互动频率", "关系持续时间"),
                unresolved_questions=("该机制与制度条件如何区分？",),
            )
            for candidate in candidates
        )
        evidence_requirements = tuple(
            FrameworkEvidenceRequirementDraft(
                requirement_id=f"requirement-{index}",
                related_candidate_ids=(candidate.candidate_id,),
                purpose="检验理论机制与现象之间的对应关系",
                required_material="去标识化互动记录或访谈摘要",
                supporting_signal="关系持续时间增加时互助更稳定",
                excluding_signal="关系变化与互助变化之间没有可观察联系",
                distinguishing_signal="控制资源供给变化后关系机制仍可观察",
                current_gap="当前案例仅包含演示性系统摘要",
            )
            for index, candidate in enumerate(candidates, start=1)
        )
        links = tuple(
            InferenceLinkDraft(
                from_ref=requirement.requirement_id,
                to_ref=str(requirement.related_candidate_ids[0]),
                relation="tests",
                rationale="材料用于检验理论机制，而不是直接证明结论",
                unresolved=True,
            )
            for requirement in evidence_requirements
        )
        return ModelProviderResult(
            output=ResearchFrameworkDraft(
                concept_mappings=concept_mappings,
                evidence_requirements=evidence_requirements,
                inference_links=links,
                alternative_explanations=("资源供给变化", "组织规则调整"),
                method_plan=None,
                scope_and_limitations=("仅解释当前已确认现象与材料边界",),
                unresolved_items=("需要用户确认取样范围与竞争解释的区分材料",),
                next_actions=("补充去标识化材料并核对适用前提",),
                ethical_boundaries=("不得上传未获授权或未去标识化的原始材料",),
            ),
            knowledge_release_id=input.theory_plan.knowledge_release.knowledge_release_id,
        )

    def audit_framework(
        self,
        *,
        framework: FrameworkVersionSnapshot,
    ) -> ModelProviderResult[FrameworkAuditDraft]:
        case = self._catalog.find_by_phenomenon(
            framework.input.theory_plan.phenomenon.phenomenon
        )
        self._raise_if_unavailable(
            case,
            capability="audit",
            knowledge_release_id=(
                framework.input.theory_plan.knowledge_release.knowledge_release_id
            ),
        )
        findings = (
            (
                AuditFindingDraft(
                    summary="框架仍有未解决项",
                    reason="草稿尚未说明如何用材料区分竞争解释",
                    impact="当前证据不足以支持正式确认",
                    recommendation="补充区分性证据计划后重新审校",
                    blocking=True,
                    finding_type=AuditFindingType.EVIDENCE,
                    severity=AuditFindingSeverity.BLOCKING,
                ),
            )
            if framework.draft.unresolved_items
            else ()
        )
        return ModelProviderResult(
            output=FrameworkAuditDraft(
                overall_status=(
                    AuditOverallStatus.REVISE if findings else AuditOverallStatus.PASS
                ),
                findings=findings,
            ),
            knowledge_release_id=(
                framework.input.theory_plan.knowledge_release.knowledge_release_id
            ),
        )

    def scenario_for_phenomenon(self, phenomenon: str) -> ModelScenario:
        case = self._catalog.find_by_phenomenon(phenomenon)
        return case.scenario if case else ModelScenario.SUCCESS

    @staticmethod
    def _clean_optional(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @staticmethod
    def _raise_if_unavailable(
        case: BuiltInCase | None,
        *,
        capability: str,
        knowledge_release_id: str | None,
    ) -> None:
        if case is None:
            return
        error = {
            ModelScenario.TIMEOUT: (
                "model_timeout",
                "The model provider timed out. The invocation can be retried.",
            ),
            ModelScenario.INSUFFICIENT_SOURCES: (
                "insufficient_sources",
                "The available sources are insufficient for this model invocation.",
            ),
            ModelScenario.NO_RELIABLE_CANDIDATE: (
                "no_reliable_candidate",
                "No reliable theory candidate is available for this evidence.",
            ),
        }.get(case.scenario)
        if error is None or (
            case.scenario is ModelScenario.NO_RELIABLE_CANDIDATE
            and capability != "judge"
        ):
            return
        code, message = error
        raise ModelProviderFailure(
            code=code,
            message=message,
            knowledge_release_id=knowledge_release_id,
            scenario=case.scenario,
        )


def create_deterministic_mock_provider(
    *,
    catalog: BuiltInCaseCatalog | None = None,
) -> DeterministicMockModelProvider:
    return DeterministicMockModelProvider(
        catalog=catalog or BuiltInCaseCatalog.default()
    )
