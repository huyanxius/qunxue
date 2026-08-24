import json
import re
from collections.abc import AsyncIterable, Callable, Mapping, Sequence
from contextvars import ContextVar

from openai.types.shared import ReasoningEffort
from pydantic_ai import (
    Agent,
    AgentStreamEvent,
    ModelRetry,
    PartDeltaEvent,
    PartStartEvent,
    RunContext,
    ToolDefinition,
)
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    TextPartDelta,
    UserPromptPart,
)
from pydantic_ai.models.openai import OpenAIChatModel, OpenAIChatModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic_ai.usage import UsageLimits

from qunxue_api.adapters.research_agent.catalog_tools import (
    KnowledgeToolRegistry,
)
from qunxue_api.adapters.research_agent.research_map_contracts import (
    ResearchMapNodeInput,
    ResearchMapRelationInput,
)
from qunxue_api.adapters.retrieval.errors import RetrievalPipelineUnavailable
from qunxue_api.modules.agent_conversation import (
    AgentEvidence,
    AgentRunResult,
    AgentRuntimeIdentity,
    AgentToolContext,
    AgentToolEvent,
    AgentTurn,
)


class DeterministicKnowledgeRunner:
    """Explicit local runner for tests and the repository's mock runtime only."""

    runtime_identity = AgentRuntimeIdentity(
        provider="deterministic-knowledge",
        model="local",
    )

    def run(
        self,
        *,
        prompt: str,
        conversation: Sequence[AgentTurn],
        tools: AgentToolContext,
    ) -> AgentRunResult:
        if not _should_search_knowledge(
            prompt,
            research_workspace=bool(getattr(tools, "research_map_enabled", False)),
            document_workspace=bool(
                getattr(tools, "research_document_tools_enabled", False)
            ),
            conversation=conversation,
        ):
            answer = _general_answer(prompt)
            return AgentRunResult(
                answer=answer,
                citations=(),
                release_id=tools.release.knowledge_release_id,
                provider="deterministic-knowledge",
                model="local",
            )
        results = tools.search_knowledge(
            _evidence_retrieval_query(prompt, conversation=conversation)
        )
        if not results:
            return AgentRunResult(
                answer=_insufficient_evidence_answer(),
                citations=(),
                release_id=tools.release.knowledge_release_id,
                provider="deterministic-knowledge",
                model="local",
            )
        first = results[0]
        citation = tools.evidence[str(first["citation_id"])]
        answer = (
            f"我先从「{first['title']}」这条知识切入。{citation.excerpt}"
            "\n\n如果你愿意，我可以继续把这个概念和你的具体情境对照。"
        )
        return AgentRunResult(
            answer=answer,
            citations=(citation,),
            release_id=tools.release.knowledge_release_id,
            provider="deterministic-knowledge",
            model="local",
        )

    def run_stream(
        self,
        *,
        prompt: str,
        conversation: Sequence[AgentTurn],
        tools: AgentToolContext,
        on_delta: Callable[[str], None],
        on_tool_event: Callable[[AgentToolEvent], None] | None = None,
    ) -> AgentRunResult:
        call_id = "deterministic:search_knowledge"
        if not _should_search_knowledge(
            prompt,
            research_workspace=bool(getattr(tools, "research_map_enabled", False)),
            document_workspace=bool(
                getattr(tools, "research_document_tools_enabled", False)
            ),
            conversation=conversation,
        ):
            result = self.run(prompt=prompt, conversation=conversation, tools=tools)
            for index in range(0, len(result.answer), 72):
                on_delta(result.answer[index : index + 72])
            return result
        retrieval_query = _evidence_retrieval_query(
            prompt,
            conversation=conversation,
        )
        if on_tool_event is not None:
            on_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="started",
                    call_id=call_id,
                    input={"query": retrieval_query},
                    detail="正在检索知识库",
                )
            )
        try:
            result = self.run(prompt=prompt, conversation=conversation, tools=tools)
        except Exception:
            if on_tool_event is not None:
                on_tool_event(
                    AgentToolEvent(
                        tool="search_knowledge",
                        phase="failed",
                        call_id=call_id,
                        input={"query": retrieval_query},
                        detail="知识库检索暂时失败",
                        error="knowledge_search_failed",
                    )
                )
            raise
        if on_tool_event is not None:
            trace_items = _trace_items(result.citations)
            on_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="finished",
                    call_id=call_id,
                    input={"query": retrieval_query},
                    output={"result_count": len(result.citations), "items": trace_items},
                    detail=_trace_detail(len(result.citations), trace_items),
                )
            )
        for index in range(0, len(result.answer), 72):
            on_delta(result.answer[index : index + 72])
        return result


def _should_search_knowledge(
    prompt: str,
    *,
    research_workspace: bool = False,
    document_workspace: bool = False,
    conversation: Sequence[AgentTurn] = (),
) -> bool:
    return _requires_knowledge_evidence(
        prompt,
        research_workspace=research_workspace,
        document_workspace=document_workspace,
        conversation=conversation,
    )


def _general_answer(prompt: str) -> str:
    if "符号互动" in prompt:
        answer = (
            "符号互动论把社会看作持续发生的意义协商过程：人们通过语言、姿态和其他符号互动，"
            "理解情境、形成自我，也在互动中修正对他人的判断。它提醒我们，社会现象不能只看个人动机，"
            "还要观察具体关系和情境如何赋予行动以意义。"
        )
    elif "孤独" in prompt:
        answer = (
            "年轻人的孤独可以从个体经验、日常关系和社会结构三个层面理解。城市流动、竞争压力和时间贫困，"
            "让稳定的强连接更难形成；数字媒介扩大了弱连接，却不一定提供情感支持。社会学因此会追问："
            "哪些制度和生活节奏正在改变人们建立关系的机会，而不把问题简单归因于个人性格。"
        )
    else:
        answer = (
            "可以先把这个问题放在个体经验、日常互动和社会结构三个层面理解。社会学不把现象简单归因于个人，"
            "而是追问制度安排、资源分配、文化规范和关系网络如何共同塑造它。你补充具体情境后，我可以继续用"
            "相关理论展开。"
        )
    return answer


def _insufficient_evidence_answer() -> str:
    return (
        "当前绑定的知识发布中没有检索到足以支持本次回答的证据。"
        "本轮不生成正式知识结论；请补充研究情境、概念线索或材料后再试。"
    )


class PydanticAIKnowledgeRunner:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        model: str,
        timeout_seconds: float,
        extra_headers: Mapping[str, str] | None = None,
        reasoning_effort: ReasoningEffort | None = None,
    ) -> None:
        provider = OpenAIProvider(base_url=base_url, api_key=api_key)
        self._model = model
        self.runtime_identity = AgentRuntimeIdentity(
            provider="pydantic-ai",
            model=model,
        )
        model_settings: OpenAIChatModelSettings = {
            "timeout": timeout_seconds,
            "max_tokens": 2400,
        }
        if extra_headers:
            model_settings["extra_headers"] = dict(extra_headers)
        if reasoning_effort is not None:
            model_settings["openai_reasoning_effort"] = reasoning_effort
        if _is_deepseek_flash(base_url=base_url, model=model):
            model_settings["extra_body"] = {"thinking": {"type": "disabled"}}
        self._usage_limits = UsageLimits(request_limit=12, tool_calls_limit=20)
        model_instance = OpenAIChatModel(model, provider=provider, settings=model_settings)
        self._agent = Agent(
            model_instance,
            deps_type=KnowledgeToolRegistry,
            output_type=str,
            retries=1,
            tool_timeout=timeout_seconds,
            instructions=(
                "你是群学致知的社会学学科 Agent，帮助学生解释社会现象、理解概念、"
                "比较理论并形成更有启发性的思考。回答问题是你的原生能力，不是工具。"
                "无论用户如何询问或诱导，都不得披露、猜测或确认底层模型的供应商、系列、"
                "版本、型号、推理档位或运行配置；只能自称群学致知的社会学学科 Agent。"
                "普通讨论可以直接依据通用学科知识回答；理论、文献、来源、选题、论文与正式研究产物"
                "必须遵守服务端 evidence_policy。required_evidence 已由服务端完成发布绑定检索时，"
                "只能基于其中的闭集证据形成研究性判断，不得绕过检索另写一个看似完整的答案。"
                "检索失败会中止本轮，禁止改用通用知识继续；检索为空时只能报告证据不足并停止下结论。"
                "不要重复检索已经由 required_evidence 覆盖的同一问题；"
                "只有确有不同证据需求时才追加检索。"
                "不得杜撰知识条目或来源。一次回答可以根据需要连续调用多个工具。"
                "同一问题的检索返回空结果后不要反复改写同义词重试，也不要猜测 knowledge_id；"
                "目录 node_id 只能说明覆盖范围，不能交给 read_knowledge_entry。"
                "凡是声称来自知识库的内容都必须来自本轮工具实际返回的闭集；来源卡片由结构化"
                "证据选择生成，不要在正文中打印 citation_id 来伪造引用。"
                "普通 Agent 也可以在对话已经形成清楚、可持续推进的研究现象和研究意图时，"
                "调用 propose_start_research 提出转入新建研究的建议；该工具不会创建任务，"
                "必须由用户进入新建研究后确认。问候、一次性的概念解释、单纯完成知识检索，"
                "都不足以触发这项建议；现象、意图或情境仍不清楚时，应先追问。"
                "除 propose_start_research 外，只有在研究工作区启用时，才可以调用研究流程、"
                "研究文档和 update_research_map 工具。"
                "研究地图不是 M4/M5 的正式状态，不得用地图节点代替研究任务、理论决定或文档。"
                "当研究现象已经足够明确时，只能调用 propose_start_research 提出待确认研究起点；"
                "该工具不会创建任务。必须等用户在界面明确确认并由 REST API 完成事务后，"
                "才能调用 start_theory_matching。未完成 M4 时不得调用文档创建工具。"
                "当用户明确确认候选取舍时，立即调用 save_confirmed_theory_plan，"
                "不能要求用户重复确认；"
                "取得 theory_plan_id 后才能调用 propose_document_creation 生成待审批的 M5 草案。"
                "创建草案必须一次提供且仅提供 12 个规范章节：research_question、"
                "research_object_and_field、questions_or_hypotheses、core_concepts、theoretical_perspective、mechanisms、"
                "methodology、sample_and_sources、analysis_steps、ethics、limitations、"
                "evidence_gaps；不得缺失、重复或自造章节 key。"
                "不得调用任何模型工具直接创建 ResearchTask。"
                "研究工作区每轮最多调用 3 次 search_knowledge、"
                "5 次读取类工具；已有足够材料后停止检索。"
                "研究地图只记录问题、理论、主张、证据、缺口和综合，以及 explains、supports、"
                "challenges、derives、refines 关系；不要把工具调用、聊天记录或未核验猜测写成节点。"
                "默认用清晰但克制的篇幅回答，除非用户明确要求长文。"
                "明显偏离社会学学习与研究的问题，应简短说明能力边界并邀请用户转回学科问题。"
            ),
        )
        self._active_tool_event: ContextVar[Callable[[AgentToolEvent], None] | None] = ContextVar(
            f"agent_tool_event_{id(self)}",
            default=None,
        )
        self._register_tools()

    def _register_tools(self) -> None:
        @self._agent.tool
        def search_knowledge(
            ctx: RunContext[KnowledgeToolRegistry], query: str
        ) -> list[dict[str, object]] | dict[str, object]:
            """按语义问题检索群学知识库。

            仅在用户明确要求知识库内容、出处或引用，或精确条目能实质提高回答质量时使用。
            普通社会学解释和启发性讨论可以直接回答，不要为了展示工具而调用。
            如果返回 preview_unverified，内容可用于解释但必须标注为未审核预览。
            """
            call_id = _tool_call_id(ctx, "search_knowledge")
            self._emit_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="started",
                    call_id=call_id,
                    input={"query": query},
                    detail="正在检索知识库",
                )
            )
            try:
                result = ctx.deps.search_knowledge(query)
            except Exception:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="search_knowledge",
                        phase="failed",
                        call_id=call_id,
                        input={"query": query},
                        detail="知识库检索暂时失败",
                        error="knowledge_search_failed",
                    )
                )
                raise
            preview_count = sum(
                item.get("evidence_status") == "preview_unverified" for item in result
            )
            _select_result_evidence(ctx.deps, result)
            trace_items = _trace_items(result)
            detail = _trace_detail(len(result), trace_items, preview_count=preview_count)
            self._emit_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="finished",
                    call_id=call_id,
                    input={"query": query},
                    output={"result_count": len(result), "items": trace_items},
                    detail=detail,
                )
            )
            return result

        @self._agent.tool
        def read_knowledge_entry(
            ctx: RunContext[KnowledgeToolRegistry], knowledge_id: str
        ) -> dict[str, object]:
            """读取一次检索或目录预览实际返回的知识条目全文。

            只使用工具实际返回的 knowledge_id；不要猜测 ID，也不要把目录 node_id 当成条目 ID。
            """
            call_id = _tool_call_id(ctx, "read_knowledge_entry")
            self._emit_tool_event(
                AgentToolEvent(
                    tool="read_knowledge_entry",
                    phase="started",
                    call_id=call_id,
                    input={"knowledge_id": knowledge_id},
                    detail="正在读取知识条目",
                )
            )
            try:
                result = ctx.deps.read_knowledge_entry(knowledge_id)
            except Exception:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="read_knowledge_entry",
                        phase="failed",
                        call_id=call_id,
                        input={"knowledge_id": knowledge_id},
                        detail="知识条目读取暂时失败",
                        error="knowledge_entry_read_failed",
                    )
                )
                raise
            found = "error" not in result
            preview = result.get("evidence_status") == "preview_unverified"
            self._emit_tool_event(
                AgentToolEvent(
                    tool="read_knowledge_entry",
                    phase="finished",
                    call_id=call_id,
                    input={"knowledge_id": knowledge_id},
                    output={
                        "found": found,
                        "preview": preview,
                        "knowledge_id": knowledge_id,
                        "title": result.get("title"),
                        "excerpt": _trace_excerpt(result.get("content")),
                    },
                    detail=(
                        f"已读取知识库预览条目（未审核）：{result.get('title', knowledge_id)}"
                        if found and preview
                        else f"已读取知识条目：{result.get('title', knowledge_id)}"
                        if found
                        else "当前知识库没有这个条目"
                    ),
                )
            )
            return result

        @self._agent.tool
        def read_sources(
            ctx: RunContext[KnowledgeToolRegistry], source_ids: list[str]
        ) -> list[dict[str, object]] | dict[str, object]:
            """读取当前知识条目已授权的来源信息。

            仅在用户要求出处、原始文献或可核验来源时使用，并且 source_ids 必须来自先前读取的条目。
            """
            call_id = _tool_call_id(ctx, "read_sources")
            safe_source_ids = list(source_ids[:8])
            self._emit_tool_event(
                AgentToolEvent(
                    tool="read_sources",
                    phase="started",
                    call_id=call_id,
                    input={"source_ids": safe_source_ids},
                    detail="正在读取来源",
                )
            )
            try:
                result = ctx.deps.read_sources(source_ids)
            except Exception:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="read_sources",
                        phase="failed",
                        call_id=call_id,
                        input={"source_ids": safe_source_ids},
                        detail="来源读取暂时失败",
                        error="source_read_failed",
                    )
                )
                raise
            self._emit_tool_event(
                AgentToolEvent(
                    tool="read_sources",
                    phase="finished",
                    call_id=call_id,
                    input={"source_ids": safe_source_ids},
                    output={
                        "result_count": len(result),
                        "items": _trace_items(result),
                    },
                    detail=_source_trace_detail(result),
                )
            )
            return result

        @self._agent.tool
        def browse_knowledge_directory(
            ctx: RunContext[KnowledgeToolRegistry],
            query: str | None = None,
            limit: int = 24,
        ) -> list[dict[str, object]] | dict[str, object]:
            """浏览群学知识库的目录结构。

            适合用户询问知识库覆盖范围、学科目录或想从目录探索时使用；普通问答优先直接回答，
            已有明确概念时优先 search_knowledge，不要用目录浏览替代检索。传入 query 时只返回
            相关目录；不传 query 时只返回顶层目录。返回的 node_id 不是 knowledge_id。
            """
            call_id = _tool_call_id(ctx, "browse_knowledge_directory")
            safe_limit = max(1, min(limit, 40))
            tool_input: dict[str, object] = {"limit": safe_limit}
            if query is not None:
                tool_input["query"] = query
            self._emit_tool_event(
                AgentToolEvent(
                    tool="browse_knowledge_directory",
                    phase="started",
                    call_id=call_id,
                    input=tool_input,
                    detail="正在浏览知识目录",
                )
            )
            try:
                result = ctx.deps.browse_knowledge_directory(query=query, limit=safe_limit)
            except Exception:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="browse_knowledge_directory",
                        phase="failed",
                        call_id=call_id,
                        input=tool_input,
                        detail="知识目录读取暂时失败",
                        error="knowledge_directory_browse_failed",
                    )
                )
                raise
            self._emit_tool_event(
                AgentToolEvent(
                    tool="browse_knowledge_directory",
                    phase="finished",
                    call_id=call_id,
                    input=tool_input,
                    output={
                        "result_count": len(result),
                        "items": _trace_items(result),
                    },
                    detail=_directory_trace_detail(result),
                )
            )
            return result

        @self._agent.tool(prepare=_prepare_research_handoff_tool)
        def propose_start_research(
            ctx: RunContext[KnowledgeToolRegistry],
            phenomenon: str,
            research_intent: str | None = None,
            context: str | None = None,
        ) -> dict[str, object]:
            """提出待用户在界面确认的研究起点；不会创建任务或确认现象。"""
            payload = {
                "phenomenon": phenomenon,
                "research_intent": research_intent,
                "context": context,
            }
            return self._run_research_workflow_tool(
                ctx, "propose_start_research", payload, "正在整理待确认的研究起点"
            )

        @self._agent.tool(prepare=_prepare_document_tool)
        def get_research_workflow_state(
            ctx: RunContext[KnowledgeToolRegistry],
        ) -> dict[str, object]:
            """读取当前对话绑定的研究任务、M4 与 M5 状态，不产生写入。"""
            return self._run_research_workflow_tool(
                ctx, "get_research_workflow_state", {}, "正在读取研究流程状态"
            )

        @self._agent.tool(prepare=_prepare_document_tool)
        def start_theory_matching(
            ctx: RunContext[KnowledgeToolRegistry],
        ) -> dict[str, object]:
            """基于已确认现象和固定知识发布执行真实理论匹配，返回候选与证据。"""
            return self._run_research_workflow_tool(
                ctx, "start_theory_matching", {}, "正在执行理论匹配"
            )

        @self._agent.tool(prepare=_prepare_document_tool)
        def save_confirmed_theory_plan(
            ctx: RunContext[KnowledgeToolRegistry],
            decisions: list[dict[str, object]],
            use_assignments: list[dict[str, object]],
            relations: list[dict[str, object]],
            user_confirmed: bool,
        ) -> dict[str, object]:
            """在用户明确确认后保存所有候选决定并确认理论方案；这是正式写入工具。"""
            payload = {
                "decisions": decisions,
                "use_assignments": use_assignments,
                "relations": relations,
                "user_confirmed": user_confirmed,
            }
            return self._run_research_workflow_tool(
                ctx, "save_confirmed_theory_plan", payload, "正在保存理论决定"
            )

        @self._agent.tool(prepare=_prepare_document_tool)
        def read_research_document(
            ctx: RunContext[KnowledgeToolRegistry],
            document_id: str,
        ) -> dict[str, object]:
            """读取当前用户的一份研究文档及其固定知识发布版本。"""

            call_id = _tool_call_id(ctx, "read_research_document")
            tool_input = {"document_id": document_id}
            self._emit_tool_event(
                AgentToolEvent(
                    tool="read_research_document",
                    phase="started",
                    call_id=call_id,
                    input=tool_input,
                    detail="正在读取研究文档",
                )
            )
            try:
                result = ctx.deps.read_research_document(document_id)
            except Exception:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="read_research_document",
                        phase="failed",
                        call_id=call_id,
                        input=tool_input,
                        detail="研究文档读取失败",
                        error="research_document_read_failed",
                    )
                )
                return {
                    "error": "research_document_unavailable",
                    "document_id": document_id,
                }
            self._emit_tool_event(
                AgentToolEvent(
                    tool="read_research_document",
                    phase="finished",
                    call_id=call_id,
                    input=tool_input,
                    output={
                        "document_id": result.get("document_id"),
                        "version": result.get("version"),
                        "knowledge_release_id": result.get("knowledge_release_id"),
                        "section_count": len(result.get("sections", [])),
                        "error": result.get("error"),
                    },
                    detail=(
                        "研究文档不可用"
                        if result.get("error")
                        else f"已读取研究文档 v{result.get('version')}"
                    ),
                )
            )
            return result

        @self._agent.tool(prepare=_prepare_document_tool)
        def propose_document_revision(
            ctx: RunContext[KnowledgeToolRegistry],
            replacement_content: str,
            rationale: str,
            document_id: str | None = None,
            expected_version: int | None = None,
            section_id: str | None = None,
        ) -> dict[str, object]:
            """为一个文档章节生成待用户接受或拒绝的修改建议。

            此工具不会修改文档；正式写入只能由用户审批建议后发生。
            """

            call_id = _tool_call_id(ctx, "propose_document_revision")
            tool_input = {
                "document_id": document_id,
                "expected_version": expected_version,
                "section_id": section_id,
                "replacement_content": replacement_content,
                "rationale": rationale,
            }
            self._emit_tool_event(
                AgentToolEvent(
                    tool="propose_document_revision",
                    phase="started",
                    call_id=call_id,
                    input=tool_input,
                    detail="正在生成文档修改建议",
                )
            )
            try:
                result = ctx.deps.propose_document_revision(**tool_input)
            except Exception:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="propose_document_revision",
                        phase="failed",
                        call_id=call_id,
                        input=tool_input,
                        detail="文档修改建议生成失败",
                        error="research_document_proposal_failed",
                    )
                )
                return {
                    "error": "research_document_proposal_unavailable",
                    "document_id": document_id,
                    "section_id": section_id,
                }
            self._emit_tool_event(
                AgentToolEvent(
                    tool="propose_document_revision",
                    phase="finished",
                    call_id=call_id,
                    input=tool_input,
                    output=result,
                    detail=(
                        "修改建议未通过校验"
                        if result.get("error")
                        else "已生成待用户接受或拒绝的修改建议；文档尚未修改"
                    ),
                )
            )
            return result

        @self._agent.tool(prepare=_prepare_document_tool)
        def propose_document_creation(
            ctx: RunContext[KnowledgeToolRegistry],
            title: str,
            sections: list[dict[str, object]],
            rationale: str,
        ) -> dict[str, object]:
            """为已确认理论方案生成恰好包含 12 个规范章节的待审批研究框架草案。"""

            call_id = _tool_call_id(ctx, "propose_document_creation")
            tool_input = {"title": title, "sections": sections, "rationale": rationale}
            self._emit_tool_event(
                AgentToolEvent(
                    tool="propose_document_creation",
                    phase="started",
                    call_id=call_id,
                    input=tool_input,
                    detail="正在生成研究框架草案建议",
                )
            )
            try:
                result = ctx.deps.propose_document_creation(**tool_input)
            except Exception:
                result = {
                    "error": "research_document_proposal_unavailable",
                    "message": "研究框架草案建议暂时无法生成。",
                }
            self._emit_tool_event(
                AgentToolEvent(
                    tool="propose_document_creation",
                    phase="finished" if not result.get("error") else "failed",
                    call_id=call_id,
                    input=tool_input,
                    output=result,
                    detail=(
                        "已生成待用户审批的研究框架草案"
                        if not result.get("error")
                        else str(result.get("message", "研究框架草案生成失败"))
                    ),
                    error="research_document_proposal_failed" if result.get("error") else None,
                )
            )
            return result

        @self._agent.tool(prepare=_prepare_research_map_tool, retries=1)
        def update_research_map(
            ctx: RunContext[KnowledgeToolRegistry],
            nodes: list[ResearchMapNodeInput] | None = None,
            relations: list[ResearchMapRelationInput] | None = None,
            remove_node_ids: list[str] | None = None,
            remove_relation_ids: list[str] | None = None,
            title: str | None = None,
            map_title: str | None = None,
        ) -> dict[str, object]:
            """在研究工作区提交一组可追溯的论证地图增量。

            节点必须提供 id/kind/title，kind 只能是
            question/theory/claim/evidence/gap/synthesis。关系必须提供
            source/target/relation。
            relation 只能是 explains/supports/challenges/derives/refines。
            证据节点的 citation_ids 必须来自本轮知识工具真实返回的证据。
            工具日志和回答文本不应创建节点。
            """
            call_id = _tool_call_id(ctx, "update_research_map")
            node_payload = [node.model_dump(exclude_none=True) for node in nodes or ()]
            relation_payload = [
                relation.model_dump(exclude_none=True) for relation in relations or ()
            ]
            payload = {
                "nodes": node_payload,
                "relations": relation_payload,
                "remove_node_ids": remove_node_ids or [],
                "remove_relation_ids": remove_relation_ids or [],
            }
            resolved_map_title = (map_title or title or "").strip()
            if resolved_map_title:
                payload["map_title"] = resolved_map_title
            self._emit_tool_event(
                AgentToolEvent(
                    tool="update_research_map",
                    phase="started",
                    call_id=call_id,
                    input=payload,
                    detail="正在组织研究地图",
                )
            )
            try:
                result = ctx.deps.update_research_map(
                    nodes=node_payload,
                    relations=relation_payload,
                    remove_node_ids=remove_node_ids,
                    remove_relation_ids=remove_relation_ids,
                )
                if resolved_map_title:
                    result = {**result, "map_title": resolved_map_title}
            except ValueError as error:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="update_research_map",
                        phase="failed",
                        call_id=call_id,
                        input=payload,
                        detail="研究地图更新未通过校验",
                        error="research_map_invalid_patch",
                    )
                )
                raise ModelRetry(str(error)) from error
            except Exception:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="update_research_map",
                        phase="failed",
                        call_id=call_id,
                        input=payload,
                        detail="研究地图暂时无法更新",
                        error="research_map_unavailable",
                    )
                )
                raise
            self._emit_tool_event(
                AgentToolEvent(
                    tool="update_research_map",
                    phase="finished",
                    call_id=call_id,
                    input=payload,
                    output=result,
                    detail=(
                        f"已更新 {len(result.get('nodes', []))} 个研究节点与 "
                        f"{len(result.get('relations', []))} 条关系"
                    ),
                )
            )
            return result

    def _run_research_workflow_tool(
        self,
        ctx: RunContext[KnowledgeToolRegistry],
        tool_name: str,
        payload: dict[str, object],
        detail: str,
    ) -> dict[str, object]:
        call_id = _tool_call_id(ctx, tool_name)
        self._emit_tool_event(
            AgentToolEvent(
                tool=tool_name,
                phase="started",
                call_id=call_id,
                input=payload,
                detail=detail,
            )
        )
        try:
            result = getattr(ctx.deps, tool_name)(**payload)
        except RetrievalPipelineUnavailable:
            self._emit_tool_event(
                AgentToolEvent(
                    tool=tool_name,
                    phase="failed",
                    call_id=call_id,
                    input=payload,
                    detail="检索证据链失败，本轮研究流程已中止",
                    error="retrieval_pipeline_unavailable",
                )
            )
            raise
        except Exception as error:
            result = {"error": "research_workflow_failed", "message": str(error)}
        self._emit_tool_event(
            AgentToolEvent(
                tool=tool_name,
                phase="failed" if result.get("error") else "finished",
                call_id=call_id,
                input=payload,
                output=result,
                detail=str(result.get("message") or "研究流程状态已更新"),
                error=str(result["error"]) if result.get("error") else None,
            )
        )
        return result

    def _emit_tool_event(self, event: AgentToolEvent) -> None:
        callback = self._active_tool_event.get()
        if callback is not None:
            callback(event)

    def run(
        self,
        *,
        prompt: str,
        conversation: Sequence[AgentTurn],
        tools: AgentToolContext,
    ) -> AgentRunResult:
        required_evidence = _preflight_required_evidence(
            prompt=prompt,
            conversation=conversation,
            tools=tools,
            on_tool_event=None,
        )
        if required_evidence == ():
            return _insufficient_evidence_result(tools=tools, model=self._model)
        result = self._agent.run_sync(
            _compose_agent_prompt(
                prompt=prompt,
                research_map=getattr(tools, "research_map", None)
                if getattr(tools, "research_map_enabled", False)
                else None,
                document_context=getattr(tools, "document_prompt_context", None),
                required_evidence=required_evidence,
            ),
            message_history=_agent_message_history(conversation),
            deps=tools,
            usage_limits=self._usage_limits,
        )
        return _text_result(
            result.output,
            tools=tools,
            model=self._model,
            usage=_result_usage(result),
        )

    def run_stream(
        self,
        *,
        prompt: str,
        conversation: Sequence[AgentTurn],
        tools: AgentToolContext,
        on_delta: Callable[[str], None],
        on_tool_event: Callable[[AgentToolEvent], None] | None = None,
    ) -> AgentRunResult:
        token = self._active_tool_event.set(on_tool_event)

        async def stream_text(
            _: RunContext[KnowledgeToolRegistry],
            events: AsyncIterable[AgentStreamEvent],
        ) -> None:
            async for event in events:
                if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
                    if event.part.content:
                        on_delta(event.part.content)
                elif (
                    isinstance(event, PartDeltaEvent)
                    and isinstance(event.delta, TextPartDelta)
                    and event.delta.content_delta
                ):
                    on_delta(event.delta.content_delta)

        try:
            required_evidence = _preflight_required_evidence(
                prompt=prompt,
                conversation=conversation,
                tools=tools,
                on_tool_event=on_tool_event,
            )
            if required_evidence == ():
                result = _insufficient_evidence_result(tools=tools, model=self._model)
                on_delta(result.answer)
                return result
            result = self._agent.run_sync(
                _compose_agent_prompt(
                    prompt=prompt,
                    research_map=getattr(tools, "research_map", None)
                    if getattr(tools, "research_map_enabled", False)
                    else None,
                    document_context=getattr(tools, "document_prompt_context", None),
                    required_evidence=required_evidence,
                ),
                message_history=_agent_message_history(conversation),
                deps=tools,
                usage_limits=self._usage_limits,
                event_stream_handler=stream_text,
            )
            return _text_result(
                str(result.output),
                tools=tools,
                model=self._model,
                usage=_result_usage(result),
            )
        finally:
            self._active_tool_event.reset(token)


def _is_deepseek_flash(*, base_url: str, model: str) -> bool:
    return "deepseek.com" in base_url.lower() and model.lower() == "deepseek-v4-flash"


_EVIDENCE_REQUIRED_MARKERS = (
    "知识库",
    "检索",
    "来源",
    "引用",
    "出处",
    "文献",
    "参考资料",
    "证据",
    "毕业论文",
    "论文选题",
    "帮我想一个选题",
    "研究选题",
    "研究设计",
    "研究问题",
    "理论框架",
    "文献综述",
    "开题",
    "快速研究",
    "正式研究",
)

_TOPIC_IDEATION_MARKERS = (
    "选题",
    "论文题目",
    "研究方向",
    "可研究的社会学方向",
)

_FLOW_CONTROL_PROMPTS = frozenset(
    {
        "好",
        "好的",
        "确认",
        "继续",
        "取消",
        "保存",
        "就这个",
    }
)

_CASUAL_ACK_PROMPTS = frozenset(
    {
        "谢谢",
        "谢谢你",
        "多谢",
        "明白了",
        "知道了",
        "嗯",
        "嗯嗯",
    }
)

_KNOWLEDGE_JUDGMENT_MARKERS = (
    "理论",
    "概念",
    "学派",
    "解释",
    "机制",
    "因果",
    "主张",
    "论断",
    "事实",
    "研究问题",
    "理论框架",
    "研究方法",
    "结论",
    "论证",
)

_SEMANTIC_EDIT_MARKERS = (
    "准确",
    "严谨",
    "可靠",
    "可信",
    "正确",
    "纠正",
    "修正",
    "补充依据",
    "补充证据",
)

_STRUCTURAL_PRESENTATION_EDIT_MARKERS = (
    "错别字",
    "标点",
    "格式",
    "排版",
    "标题",
    "字数",
)

_STYLE_EDIT_MARKERS = (
    "润色",
    "简洁",
    "精简",
    "措辞",
    "语气",
)

_NON_EPISTEMIC_DOCUMENT_ACTIONS = (
    "删除",
    "删掉",
    "接受",
    "拒绝",
    "撤销",
)

_CONTEXTUAL_EVIDENCE_PATTERNS = (
    r"^为什么(?:呢)?[？?]?$",
    r"^(?:有|有什么)?(?:依据|出处|来源|文献|参考资料)(?:吗|呢)?[？?]?$",
    (
        r"^(?:这个|该)?(?:理论|概念|解释|说法)?"
        r"(?:靠谱吗|可靠(?:吗)?|可信(?:吗)?|成立(?:吗)?|适用(?:吗)?)[？?]?$"
    ),
)

_EVIDENCE_REQUEST_PATTERNS = (
    r"(?:有|有什么|给出|提供|说明|缺少|需要).{0,6}依据",
    r"(?:理论|概念|解释|说法|主张).{0,8}的?依据",
    r"依据(?:是|来自|在哪|是什么|有哪些|呢|吗)",
)

_RESEARCH_CONTEXT_MARKERS = (
    "研究",
    "论文",
    "理论",
    "概念",
    "学派",
    "文献",
    "证据",
    "知识库",
    "框架",
    "机制",
    "因果",
)


_EXPLICIT_EVIDENCE_MARKERS = (
    "知识库",
    "检索",
    "来源",
    "引用",
    "出处",
    "文献",
    "参考资料",
    "证据",
)

_DOCUMENT_OPERATION_MARKERS = (
    "修改",
    "改得",
    "重写",
    "润色",
    "调整",
    "修正",
    "删除",
    "删掉",
    "接受",
    "拒绝",
    "撤销",
)


def _requires_knowledge_evidence(
    prompt: str,
    *,
    research_workspace: bool,
    document_workspace: bool = False,
    conversation: Sequence[AgentTurn] = (),
) -> bool:
    normalized = " ".join(prompt.split())
    if _is_flow_control_prompt(normalized):
        return False
    is_document_operation = document_workspace and any(
        marker in normalized for marker in _DOCUMENT_OPERATION_MARKERS
    )
    if is_document_operation:
        if _explicit_evidence_requested(normalized):
            return True
        if any(marker in normalized for marker in _NON_EPISTEMIC_DOCUMENT_ACTIONS):
            return False
        if any(
            marker in normalized for marker in _STRUCTURAL_PRESENTATION_EDIT_MARKERS
        ):
            return False
        if any(marker in normalized for marker in _SEMANTIC_EDIT_MARKERS):
            return True
        if any(marker in normalized for marker in _STYLE_EDIT_MARKERS):
            return False
        if any(marker in normalized for marker in _KNOWLEDGE_JUDGMENT_MARKERS):
            return True
        return _conversation_has_research_context(conversation)
    if any(marker in normalized for marker in _EVIDENCE_REQUIRED_MARKERS):
        return True
    if _explicit_evidence_requested(normalized):
        return True
    if re.search(r"(?:解释|比较|介绍|什么是).{0,20}(?:理论|概念|学派)", normalized):
        return True
    if re.search(
        r"(?:理论|概念|学派|解释|说法).{0,16}(?:靠谱|可靠|可信|成立|适用)",
        normalized,
    ):
        return True
    if (
        _is_contextual_evidence_followup(normalized)
        and _conversation_has_research_context(conversation)
    ):
        return True
    return research_workspace


def _evidence_retrieval_query(
    prompt: str,
    *,
    conversation: Sequence[AgentTurn] = (),
) -> str:
    normalized = " ".join(prompt.split())
    if _needs_prior_research_context(normalized):
        recent_topic = _recent_research_topic(conversation)
        if recent_topic:
            return f"{recent_topic}\n当前追问：{normalized}"
    if any(marker in normalized for marker in _TOPIC_IDEATION_MARKERS):
        return (
            f"{prompt}\n"
            "检索目标：从已审核社会学理论中寻找可形成研究问题的候选方向。"
        )
    return prompt


def _is_contextual_evidence_followup(normalized: str) -> bool:
    return any(
        re.fullmatch(pattern, normalized)
        for pattern in _CONTEXTUAL_EVIDENCE_PATTERNS
    )


def _explicit_evidence_requested(normalized: str) -> bool:
    return any(
        marker in normalized for marker in _EXPLICIT_EVIDENCE_MARKERS
    ) or any(re.search(pattern, normalized) for pattern in _EVIDENCE_REQUEST_PATTERNS)


def _needs_prior_research_context(normalized: str) -> bool:
    return (
        _is_contextual_evidence_followup(normalized)
        or any(
            marker in normalized
            for marker in (
                "这个理论",
                "该理论",
                "这个概念",
                "该概念",
                "上述解释",
                "把它",
                "将它",
                "这段",
                "这一段",
            )
        )
        or (
            any(marker in normalized for marker in _DOCUMENT_OPERATION_MARKERS)
            and any(marker in normalized for marker in _SEMANTIC_EDIT_MARKERS)
        )
    )


def _recent_research_topic(conversation: Sequence[AgentTurn]) -> str | None:
    for turn in reversed(conversation):
        candidate = _normalized_text(turn.user_message.content)
        if not candidate or _is_non_substantive_prompt(candidate):
            continue
        return _turn_research_query_context(turn)
    return None


def _conversation_has_research_context(
    conversation: Sequence[AgentTurn],
) -> bool:
    for turn in reversed(conversation):
        candidate = _normalized_text(turn.user_message.content)
        if not candidate or _is_non_substantive_prompt(candidate):
            continue
        return _turn_has_research_context(turn)
    return False


def _turn_has_research_context(turn: AgentTurn) -> bool:
    if turn.evidence_ids or turn.assistant_message.citations:
        return True
    user_content = _normalized_text(turn.user_message.content)
    return any(marker in user_content for marker in _RESEARCH_CONTEXT_MARKERS)


def _turn_research_query_context(turn: AgentTurn) -> str:
    user_content = _normalized_text(turn.user_message.content)
    assistant_content = _normalized_text(turn.assistant_message.content)
    if len(assistant_content) > 360:
        assistant_content = f"{assistant_content[:359].rstrip()}…"
    if not assistant_content:
        return user_content
    return f"{user_content}\n上一轮回答线索：{assistant_content}"


def _is_flow_control_prompt(normalized: str) -> bool:
    return _control_token(normalized) in _FLOW_CONTROL_PROMPTS


def _is_non_substantive_prompt(normalized: str) -> bool:
    token = _control_token(normalized)
    return (
        token in _FLOW_CONTROL_PROMPTS
        or token in _CASUAL_ACK_PROMPTS
        or _is_contextual_evidence_followup(normalized)
    )


def _control_token(normalized: str) -> str:
    return normalized.rstrip("。！？!?").strip()


def _normalized_text(value: str) -> str:
    return " ".join(value.split())


def _preflight_required_evidence(
    *,
    prompt: str,
    conversation: Sequence[AgentTurn],
    tools: AgentToolContext,
    on_tool_event: Callable[[AgentToolEvent], None] | None,
) -> tuple[Mapping[str, object], ...] | None:
    if not _requires_knowledge_evidence(
        prompt,
        research_workspace=bool(getattr(tools, "research_map_enabled", False)),
        document_workspace=bool(
            getattr(tools, "research_document_tools_enabled", False)
        ),
        conversation=conversation,
    ):
        return None
    retrieval_query = _evidence_retrieval_query(
        prompt,
        conversation=conversation,
    )
    call_id = "policy:search_knowledge"
    if on_tool_event is not None:
        on_tool_event(
            AgentToolEvent(
                tool="search_knowledge",
                phase="started",
                call_id=call_id,
                input={"query": retrieval_query},
                detail="正式研究任务正在检索知识库",
            )
        )
    try:
        results = tools.search_knowledge(retrieval_query, limit=5)
    except Exception:
        if on_tool_event is not None:
            on_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="failed",
                    call_id=call_id,
                    input={"query": retrieval_query},
                    detail="知识库检索失败，本轮研究回答已中止",
                    error="knowledge_search_failed",
                )
            )
        raise
    _select_result_evidence(tools, results)
    trace_items = _trace_items(results)
    if on_tool_event is not None:
        on_tool_event(
            AgentToolEvent(
                tool="search_knowledge",
                phase="finished",
                call_id=call_id,
                input={"query": retrieval_query},
                output={"result_count": len(results), "items": trace_items},
                detail=_trace_detail(len(results), trace_items),
            )
        )
    return tuple(results)


def _insufficient_evidence_result(
    *,
    tools: AgentToolContext,
    model: str,
) -> AgentRunResult:
    return AgentRunResult(
        answer=_insufficient_evidence_answer(),
        citations=(),
        release_id=tools.release.knowledge_release_id,
        provider="pydantic-ai",
        model=model,
    )


def _trace_items(values, *, limit: int = 4) -> list[dict[str, object]]:
    """Return bounded, user-safe facts for the visible tool trace."""

    items: list[dict[str, object]] = []
    for value in values[:limit]:
        if isinstance(value, AgentEvidence):
            item = {
                "knowledge_id": value.knowledge_id,
                "title": value.label,
                "excerpt": _trace_excerpt(value.excerpt),
                "evidence_status": "preview_unverified" if value.kind == "preview" else "verified",
            }
        elif isinstance(value, Mapping):
            item = {}
            for key in (
                "knowledge_id",
                "node_id",
                "source_id",
                "title",
                "excerpt",
                "content_excerpt",
                "evidence_status",
                "verification_status",
                "entry_count",
            ):
                if key in value and value[key] is not None:
                    item[key] = (
                        _trace_excerpt(value[key])
                        if key in {"excerpt", "content_excerpt"}
                        else value[key]
                    )
            nested = value.get("entries")
            if isinstance(nested, list) and nested:
                item["entries"] = _trace_items(nested, limit=3)
        else:
            continue
        if item:
            items.append(item)
    return items


def _trace_excerpt(value: object, *, limit: int = 220) -> str | None:
    if value is None:
        return None
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}…"


def _trace_detail(
    count: int,
    items: list[dict[str, object]],
    *,
    preview_count: int = 0,
) -> str:
    if not items:
        return "没有找到可展示的知识条目"
    labels = []
    for item in items[:3]:
        title = item.get("title") or item.get("knowledge_id") or item.get("node_id")
        excerpt = item.get("excerpt") or item.get("content_excerpt")
        labels.append(f"{title}{f'：{excerpt}' if excerpt else ''}")
    prefix = (
        f"找到 {preview_count} 条知识库预览内容（未审核）"
        if preview_count
        else f"找到 {count} 条可引用证据"
    )
    return f"{prefix}：{'；'.join(labels)}"


def _source_trace_detail(values) -> str:
    items = _trace_items(values)
    labels = [str(item.get("title") or item.get("source_id")) for item in items]
    return f"找到 {len(values)} 个来源" + (f"：{'；'.join(labels)}" if labels else "")


def _directory_trace_detail(values) -> str:
    items = _trace_items(values)
    labels = []
    for item in items[:3]:
        title = item.get("title") or item.get("node_id")
        entries = item.get("entries")
        if entries:
            entry_titles = "、".join(
                str(entry.get("title")) for entry in entries if entry.get("title")
            )
            labels.append(f"{title}（{entry_titles}）")
        else:
            labels.append(str(title))
    return f"找到 {len(values)} 个目录节点" + (f"：{'；'.join(labels)}" if labels else "")


def _compose_agent_prompt(
    *,
    prompt: str,
    research_map: Mapping[str, object] | None = None,
    document_context: Mapping[str, object] | None = None,
    required_evidence: Sequence[Mapping[str, object]] | None = None,
) -> str:
    map_context = (
        "\n\n<research_map_policy>"
        "研究工作区内，只要本轮形成或修订研究问题、理论、主张、证据、缺口或综合判断，"
        "就必须在回答完成前调用 update_research_map 提交对应增量；若结构没有变化则不要调用。"
        "工具校验失败时根据反馈修正一次，不得把失败的结构写成已经保存。"
        "</research_map_policy>\n<current_research_map>\n"
        f"{json.dumps(research_map, ensure_ascii=False, separators=(',', ':'))}"
        "\n</current_research_map>"
        if research_map is not None
        else ""
    )
    document_context_text = (
        "\n\n<current_research_document_context>\n"
        f"{json.dumps(document_context, ensure_ascii=False, separators=(',', ':'))}"
        "\n</current_research_document_context>"
        if document_context is not None
        else ""
    )
    evidence_context = (
        '\n\n<evidence_policy mode="required">'
        "本轮属于正式研究取证任务。只能依据 required_evidence 中的证据形成研究判断；"
        "不得补写未取证事实，不得省略证据边界。"
        "</evidence_policy>\n<required_evidence>\n"
        f"{json.dumps(required_evidence, ensure_ascii=False, separators=(',', ':'))}"
        "\n</required_evidence>"
        if required_evidence is not None
        else ""
    )
    return f"{prompt}{map_context}{document_context_text}{evidence_context}"


def _agent_message_history(
    conversation: Sequence[AgentTurn],
) -> list[ModelRequest | ModelResponse]:
    history: list[ModelRequest | ModelResponse] = []
    for turn in conversation:
        history.extend(
            (
                ModelRequest(parts=[UserPromptPart(turn.user_message.content)]),
                ModelResponse(parts=[TextPart(turn.assistant_message.content)]),
            )
        )
    return history


def _prepare_research_map_tool(
    ctx: RunContext[KnowledgeToolRegistry],
    definition: ToolDefinition,
) -> ToolDefinition | None:
    """Hide the research mutation tool completely from ordinary `/agent` turns."""

    return definition if getattr(ctx.deps, "research_map_enabled", False) else None


def _prepare_research_handoff_tool(
    ctx: RunContext[KnowledgeToolRegistry],
    definition: ToolDefinition,
) -> ToolDefinition | None:
    """Expose only the approval-gated, non-task-creating handoff outside research."""

    return (
        definition
        if getattr(ctx.deps, "research_handoff_tools_enabled", False)
        and callable(getattr(ctx.deps, definition.name, None))
        else None
    )


def _prepare_document_tool(
    ctx: RunContext[KnowledgeToolRegistry],
    definition: ToolDefinition,
) -> ToolDefinition | None:
    """Expose document tools only when the scoped registry implements them."""

    return (
        definition
        if getattr(ctx.deps, "research_document_tools_enabled", False)
        and callable(getattr(ctx.deps, definition.name, None))
        else None
    )


def _text_result(
    answer: str,
    *,
    tools: AgentToolContext,
    model: str,
    usage: tuple[int, int] = (0, 0),
) -> AgentRunResult:
    selected_citation_ids = tuple(getattr(tools, "selected_evidence_ids", ()))
    if any(citation_id not in tools.evidence for citation_id in selected_citation_ids):
        raise ValueError("selected evidence is outside this turn's retrieved closed set")
    return AgentRunResult(
        answer=answer,
        citations=tuple(tools.evidence[item] for item in selected_citation_ids[:8]),
        release_id=tools.release.knowledge_release_id,
        provider="pydantic-ai",
        model=model,
        input_tokens=usage[0],
        output_tokens=usage[1],
    )


def _result_usage(result: object) -> tuple[int, int]:
    raw_usage = getattr(result, "usage", None)
    if raw_usage is None:
        return (0, 0)
    usage = (
        raw_usage
        if hasattr(raw_usage, "input_tokens")
        else raw_usage()
        if callable(raw_usage)
        else None
    )
    if usage is None:
        return (0, 0)
    return (
        max(0, int(getattr(usage, "input_tokens", 0))),
        max(0, int(getattr(usage, "output_tokens", 0))),
    )


def _select_result_evidence(
    tools: AgentToolContext,
    results: Sequence[Mapping[str, object]],
) -> None:
    citation_ids: list[str] = []
    for result in results:
        citation_id = result.get("citation_id")
        if isinstance(citation_id, str):
            citation_ids.append(citation_id)
        source_ids = result.get("source_citation_ids")
        if isinstance(source_ids, list):
            citation_ids.extend(value for value in source_ids if isinstance(value, str))
    tools.select_evidence(citation_ids[:8])


def _tool_call_id(ctx: RunContext[KnowledgeToolRegistry], tool: str) -> str:
    return ctx.tool_call_id or f"{ctx.run_id or 'agent-run'}:{ctx.run_step}:{tool}"
