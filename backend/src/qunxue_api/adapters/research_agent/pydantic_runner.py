import asyncio
import json
import re
from asyncio import sleep as async_sleep
from collections.abc import AsyncIterable, Callable, Mapping, Sequence
from contextvars import ContextVar
from typing import Literal

from openai import AsyncOpenAI
from openai.types.shared import ReasoningEffort
from pydantic import BaseModel, Field
from pydantic_ai import (
    Agent,
    AgentStreamEvent,
    ModelRetry,
    PartDeltaEvent,
    PartStartEvent,
    RunContext,
    ToolDefinition,
)
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
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
    AgentResearchEvent,
    AgentRunResult,
    AgentRuntimeIdentity,
    AgentToolContext,
    AgentToolEvent,
    AgentTurn,
)


class DeepResearchDecision(BaseModel):
    """Structured planning output; it keeps research UX out of free-form text."""

    request_type: Literal["research", "conversation"] = "conversation"
    needs_clarification: bool = False
    question: str = ""
    options: list[str] = Field(default_factory=list)
    title: str = "深入研究"
    steps: list[str] = Field(default_factory=list)


class DeterministicKnowledgeRunner:
    """Explicit local runner for tests and the repository's mock runtime only."""

    runtime_identity = AgentRuntimeIdentity(
        provider="deterministic-knowledge",
        model="local",
    )

    def prepare_research(
        self,
        *,
        prompt: str,
        conversation: Sequence[AgentTurn],
        on_event: Callable[[AgentResearchEvent], None],
    ) -> None:
        del conversation
        if prompt.strip() in {"你好", "您好", "嗨", "hello", "hi", "谢谢", "感谢"}:
            return
        if len(prompt.strip()) < 18:
            on_event(
                AgentResearchEvent(
                    kind="ask",
                    payload={
                        "question": "你希望我重点研究哪一部分？",
                        "options": [
                            "概念与理论背景",
                            "现实案例与最新资料",
                            "不同观点之间的争议",
                            "研究方法与数据",
                            "更多自定义",
                        ],
                    },
                )
            )
            return
        on_event(
            AgentResearchEvent(
                kind="plan",
                payload={
                    "title": prompt.strip()[:80],
                    "steps": ["检索知识库", "补充网页资料", "整理证据并形成结论"],
                },
            )
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
            document_workspace=bool(getattr(tools, "research_document_tools_enabled", False)),
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
        retrieval_query = _evidence_retrieval_query(prompt, conversation=conversation)
        knowledge_results = tools.search_knowledge(retrieval_query)
        material_results = _search_material_results(tools, retrieval_query)
        results = _merge_retrieval_results(material_results, knowledge_results)
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
        source_intro = (
            f"我先从你的个人材料「{first['title']}」这段原文切入。"
            if first.get("source_kind") == "personal_material"
            else f"我先从「{first['title']}」这条知识切入。"
        )
        answer = (
            f"{source_intro}{citation.excerpt}"
            "\n\n如果你愿意，我可以继续把这个概念和你的具体情境对照。"
        )
        citation_limit = 2 if material_results else 1
        citation_results = results[:citation_limit]
        _select_result_evidence(tools, citation_results)
        citations = tuple(
            tools.evidence[str(item["citation_id"])]
            for item in citation_results
            if str(item.get("citation_id")) in tools.evidence
        )
        return AgentRunResult(
            answer=answer,
            citations=citations or (citation,),
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
        material_enabled = _material_tools_available(tools)
        if not _should_search_knowledge(
            prompt,
            research_workspace=bool(getattr(tools, "research_map_enabled", False)),
            document_workspace=bool(getattr(tools, "research_document_tools_enabled", False)),
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
            if material_enabled:
                on_tool_event(
                    AgentToolEvent(
                        tool="search_research_materials",
                        phase="started",
                        call_id="deterministic:search_research_materials",
                        input={"query": retrieval_query},
                        detail="正在检索个人研究材料",
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
                if material_enabled and on_tool_event is not None:
                    on_tool_event(
                        AgentToolEvent(
                            tool="search_research_materials",
                            phase="failed",
                            call_id="deterministic:search_research_materials",
                            input={"query": retrieval_query},
                            detail="个人材料检索暂时失败",
                            error="research_material_search_failed",
                        )
                    )
            raise
        if on_tool_event is not None:
            public_citations = tuple(
                citation
                for citation in result.citations
                if citation.source_kind != "personal_material"
            )
            trace_items = _trace_items(public_citations)
            on_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="finished",
                    call_id=call_id,
                    input={"query": retrieval_query},
                    output={"result_count": len(public_citations), "items": trace_items},
                    detail=_trace_detail(len(public_citations), trace_items),
                )
            )
            if material_enabled:
                material_citations = tuple(
                    citation
                    for citation in result.citations
                    if citation.source_kind == "personal_material"
                )
                on_tool_event(
                    AgentToolEvent(
                        tool="search_research_materials",
                        phase="finished",
                        call_id="deterministic:search_research_materials",
                        input={"query": retrieval_query},
                        output={
                            "result_count": len(material_citations),
                            "items": _trace_items(material_citations),
                        },
                        detail=_material_trace_detail(
                            [
                                {
                                    "title": item.label,
                                    "source_kind": "personal_material",
                                    "locator": item.locator,
                                }
                                for item in material_citations
                            ]
                        ),
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


def _material_tools_available(tools: AgentToolContext) -> bool:
    return bool(
        getattr(tools, "research_material_tools_enabled", False)
        and callable(getattr(tools, "search_research_materials", None))
    )


def _search_material_results(
    tools: AgentToolContext,
    query: str,
) -> list[Mapping[str, object]]:
    if not _material_tools_available(tools):
        return []
    result = tools.search_research_materials(query, limit=5)
    return (
        [item for item in result if isinstance(item, Mapping)] if isinstance(result, list) else []
    )


def _mapping_results(value: object) -> list[Mapping[str, object]]:
    return [item for item in value if isinstance(item, Mapping)] if isinstance(value, list) else []


def _merge_retrieval_results(
    material_results: Sequence[Mapping[str, object]],
    knowledge_results: Sequence[Mapping[str, object]] | Mapping[str, object],
) -> list[Mapping[str, object]]:
    public = (
        [item for item in knowledge_results if isinstance(item, Mapping)]
        if isinstance(knowledge_results, list)
        else []
    )
    # Keep one result per source segment/knowledge chunk while preserving the
    # personal-material-first ordering that makes the source distinction clear
    # in the deterministic local runtime.
    merged: list[Mapping[str, object]] = []
    seen: set[str] = set()
    for item in (*material_results, *public):
        citation_id = item.get("citation_id")
        key = str(citation_id) if citation_id is not None else repr(item)
        if key in seen:
            continue
        seen.add(key)
        merged.append(item)
    return merged


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


class _RetryingOpenAIChatModel(OpenAIChatModel):
    _PROVIDER_RETRY_DELAYS = (0.5,)

    def __init__(self, *args, fallback_models: Sequence[OpenAIChatModel] = (), **kwargs):
        super().__init__(*args, **kwargs)
        self._fallback_models = tuple(fallback_models)

    async def _request_model(self, model: OpenAIChatModel, *args, **kwargs):
        if model is self:
            return await super()._completions_create(*args, **kwargs)
        return await model._completions_create(*args, **kwargs)

    async def _race_models(self, models: Sequence[OpenAIChatModel], *args, **kwargs):
        tasks = {
            asyncio.create_task(self._request_model(model, *args, **kwargs))
            for model in models
        }
        last_error: Exception | None = None
        try:
            while tasks:
                done, tasks = await asyncio.wait(
                    tasks, return_when=asyncio.FIRST_COMPLETED
                )
                for task in done:
                    try:
                        result = task.result()
                    except (ModelHTTPError, ModelAPIError) as error:
                        last_error = error
                        continue
                    for pending in tasks:
                        pending.cancel()
                    return result
            assert last_error is not None
            raise last_error
        finally:
            for task in tasks:
                task.cancel()

    async def _completions_create(self, *args, **kwargs):
        models = (self, *self._fallback_models)
        primary_models = tuple(model for model in models if model.base_url == self.base_url)
        fallback_models = tuple(model for model in models if model.base_url != self.base_url)
        last_error: Exception | None = None

        async def request_primary():
            if len(primary_models) == 1:
                return await self._request_model(primary_models[0], *args, **kwargs)
            return await self._race_models(primary_models, *args, **kwargs)

        try:
            return await request_primary()
        except (ModelHTTPError, ModelAPIError) as error:
            last_error = error
            if not _is_retryable_model_error(error):
                raise

        if not fallback_models:
            await async_sleep(self._PROVIDER_RETRY_DELAYS[0])
            return await request_primary()

        for model_index, model in enumerate(fallback_models):
            attempts = 2 if model_index == len(fallback_models) - 1 else 1
            for attempt in range(attempts):
                try:
                    return await self._request_model(model, *args, **kwargs)
                except (ModelHTTPError, ModelAPIError) as error:
                    last_error = error
                    if not _is_retryable_model_error(error):
                        raise
                    if attempt < attempts - 1:
                        await async_sleep(self._PROVIDER_RETRY_DELAYS[0])
        assert last_error is not None
        raise last_error


class PydanticAIKnowledgeRunner:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        fallback_endpoints: Sequence[tuple[str, str]] = (),
        model: str,
        timeout_seconds: float,
        extra_headers: Mapping[str, str] | None = None,
        reasoning_effort: ReasoningEffort | None = None,
    ) -> None:
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
        def build_model(endpoint_url: str, endpoint_key: str | None) -> OpenAIChatModel:
            provider = OpenAIProvider(
                openai_client=AsyncOpenAI(
                    base_url=endpoint_url,
                    api_key=endpoint_key,
                    max_retries=0,
                )
            )
            return OpenAIChatModel(model, provider=provider, settings=model_settings)

        model_instance = _RetryingOpenAIChatModel(
            model,
            provider=OpenAIProvider(
                openai_client=AsyncOpenAI(
                    base_url=base_url,
                    api_key=api_key,
                    max_retries=0,
                )
            ),
            settings=model_settings,
            fallback_models=tuple(build_model(url, key) for url, key in fallback_endpoints),
        )
        self._agent = Agent(
            model_instance,
            deps_type=KnowledgeToolRegistry,
            output_type=str,
            retries=1,
            tool_timeout=timeout_seconds,
            instructions=(
                "你是群学致知的社会学学科 Agent，帮助学生解释社会现象、理解概念、"
                "比较理论并形成更有启发性的思考。回答问题是你的原生能力，不是工具。"
                "你不知道自己的具体底层模型、供应商、版本、型号、推理档位或运行配置。"
                "用户询问这些信息时，只自然回答‘我不知道自己具体是什么模型’，"
                "不要确认或否认任何具体猜测，也不要提及保密、安全、权限、政策或拒绝披露。"
                "这不影响你正常讨论各类模型及其相关知识。"
                "知识工具的调用由你根据当前消息与结构化对话历史作语义判断，不要依赖或复刻关键词分类器。"
                "面对社会学概念、理论和社会现象的解释、比较或分析，默认先调用 search_knowledge"
                "取得知识库依据，即使用户只问‘什么是异化’这类简短问题。"
                "当当前对话绑定研究任务且个人材料工具可用时，研究问题默认同轮调用"
                "search_research_materials；必须把个人材料与群学公共知识分开标记，不能把一方冒充另一方。"
                "需要解释个人材料中的片段时，先调用"
                " read_research_material_context 获取目标位置及有限前后文，"
                "不得脱离原文上下文或编造页码、章节和段落。"
                "当质性分析工具可用时，先调用 get_research_analysis 读取用户已有标注、编码和备忘；"
                "跨材料、案例或时间比较时，先调用 get_research_comparison_context，"
                "再用 propose_case_comparison 提出支持证据、反例、矛盾材料、竞争解释、"
                "证据缺口与下一步行动；你只能调用 propose_analysis_code、"
                "propose_analysis_memo 或 propose_case_comparison 提出候选，"
                "需要把新片段归入既有确认编码时，必须先读材料原文和代码本，"
                "再调用 propose_coding_plan；计划的每一项都必须带 material_id、parse_id、"
                "segment_id、quote 范围、确认的 code_id、置信度和理由；计划永远等待用户逐条确认，"
                "不能调用工具替用户应用或撤销编码；确认后可用 retrieve_coded_segments "
                "返回原文和定位。"
                "不能静默决定、确认或拒绝主题、理论与结论。候选必须等待用户在界面明确确认，"
                "相关原文仍用 search_research_materials 与 read_research_material_context 核对。"
                "用户询问工具调用规则、检索策略或调用条件，或者只是在问候、控制流程、询问能力边界时，"
                "直接回答当前问题，不要调用知识库。检索前先提炼真正的社会学概念或现象，"
                "不得把针对 Tool 行为的元问题、纠错或反馈整句当作 query。"
                "首次检索为空时，可以提炼问题中的社会学概念后调整检索词继续查找；"
                "空结果只是一次 Tool"
                "观察，必须回到你的判断，不得输出服务端固定失败模板。普通学习问题在合理检索仍为空时，"
                "可以明确说明知识库未命中后使用通用学科知识；正式研究、论文、引用和来源结论不得绕过证据。"
                "检索结果只限定知识库引用的依据，不限制你理解和回应用户的问题。"
                "不得杜撰知识条目或来源。一次回答可以根据需要连续调用多个工具。"
                "每轮最多调用 3 次 search_knowledge；不要重复相同检索，也不要猜测 knowledge_id；"
                "当本轮启用联网搜索时，采用知识库优先、主动联网补充的策略。"
                "按已有知识库规则取得学科依据后，结合用户意图、对话历史和检索结果，"
                "主动判断外部资料能否使回答更全面、具体或准确，不要因为知识库已有命中就直接停止。"
                "涉及现实案例、近期研究、政策变化、统计数据、争议或证据缺口时，"
                "积极调用 search_web 补充和核对，即使用户没有明确要求联网、知识库并非空结果；"
                "这些是判断补充价值的例子，不是封闭的触发清单。"
                "由你自主决定查询角度、检索轮次和阅读范围，已有充分依据时停止；"
                "稳定的概念解释在知识库已足够时无需为了调用工具而联网，问候、流程控制和工具策略元问题直接回答。"
                "知识库作为概念、理论与适用前提的优先依据，网页补充外部事实和新进展；"
                "回答中自然区分两类来源与自己的推论，遇到冲突说明来源、时间和适用范围，不静默覆盖。"
                "检索前先问自己：如果要用网页搜索引擎回答这个问题，我会在搜索框输入什么？"
                "把真正的社会学概念、现象、群体、地点、时间或制度对象写成短而独立的查询；"
                "需要不同角度时分次调用 search_web，不要把整句元问题、纠错或反馈原样当作 query；"
                "采用网页信息前必须再调用 read_web_page 阅读正文，不得只根据搜索摘要下结论。"
                "只能读取 search_web 本轮实际返回的网址，不能猜测或拼接 URL。"
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
                "研究工作区每轮最多调用 3 次 search_knowledge、3 次 search_research_materials、"
                "5 次读取类工具；已有足够材料后停止检索。"
                "研究地图只记录问题、理论、主张、证据、缺口和综合，以及 explains、supports、"
                "challenges、derives、refines 关系；不要把工具调用、聊天记录或未核验猜测写成节点。"
                "默认用清晰但克制的篇幅回答，除非用户明确要求长文。"
                "明显偏离社会学学习与研究的问题，应简短说明能力边界并邀请用户转回学科问题。"
            ),
        )
        self._planner_agent = Agent(
            model_instance,
            output_type=DeepResearchDecision,
            retries=1,
            instructions=(
                "你是深入研究模式的研究规划器。先判断当前消息是 research 还是普通 conversation。"
                "问候、致谢、闲聊、简单解释和不需要多轮证据检索的请求都标记为 conversation，"
                "直接让主 Agent 回答，不要生成 ask 或 plan。只有用户明确要求研究、比较、综述、"
                "调查，"
                "或问题确实需要多轮知识库/网页检索时才标记为 research。"
                "对 research 请求再根据用户问题和对话历史判断意图是否足够清楚。"
                "只返回结构化规划，不回答研究结论。意图不清时 needs_clarification=true，"
                "拟定一句简洁的 question，并给出 3 到 5 个互斥选项；意图清楚时给出简洁 title 和"
                "3 到 6 个研究步骤。不要把‘更多自定义’放进 options，由服务端固定追加。"
                "如果当前消息只是切换到深入研究而没有明确研究问题，请先询问用户要继续哪个研究或提供新的问题，"
                "不要把历史对话中的旧研究默认当成本轮主题。"
            ),
        )
        self._active_tool_event: ContextVar[Callable[[AgentToolEvent], None] | None] = ContextVar(
            f"agent_tool_event_{id(self)}",
            default=None,
        )
        self._register_tools()

    def prepare_research(
        self,
        *,
        prompt: str,
        conversation: Sequence[AgentTurn],
        on_event: Callable[[AgentResearchEvent], None],
    ) -> None:
        """Ask the model for the research UX envelope before retrieval starts."""

        try:
            decision = self._planner_agent.run_sync(
                _compose_agent_prompt(prompt=prompt, research_map=None, document_context=None),
                message_history=_agent_message_history(conversation),
                usage_limits=UsageLimits(request_limit=2, tool_calls_limit=0),
            ).output
        except Exception:
            # Planning must not make the regular Agent unavailable. The fallback keeps
            # the contract valid and lets the main run apply the normal evidence policy.
            decision = DeepResearchDecision(
                title="深入研究",
                steps=["检索知识库", "补充网页资料", "整理证据并形成结论"],
            )
        if decision.request_type != "research":
            return
        if decision.needs_clarification:
            options = [
                item.strip()
                for item in decision.options
                if item.strip() and item.strip() != "更多自定义"
            ][:5]
            if len(options) < 3:
                options = [
                    "概念与理论背景",
                    "现实案例与最新资料",
                    "不同观点之间的争议",
                ]
            on_event(
                AgentResearchEvent(
                    kind="ask",
                    payload={
                        "question": decision.question.strip() or "你希望我重点研究哪一部分？",
                        "options": [*options, "更多自定义"],
                    },
                )
            )
            return
        on_event(
            AgentResearchEvent(
                kind="plan",
                payload={
                    "title": decision.title.strip() or "深入研究",
                    "steps": [item.strip() for item in decision.steps if item.strip()][:6]
                    or ["检索知识库", "补充网页资料", "整理证据并形成结论"],
                },
            )
        )

    def _register_tools(self) -> None:
        @self._agent.tool
        def search_knowledge(
            ctx: RunContext[KnowledgeToolRegistry], query: str
        ) -> list[dict[str, object]] | dict[str, object]:
            """按语义问题检索群学知识库。

            社会学概念、理论和社会现象的解释、比较或分析默认先调用本工具取得依据，
            包括“什么是异化”这类简短概念问题。由模型根据语义和对话历史决定调用，
            并把问题提炼成真正的社会学概念或现象查询；不要检索工具规则、调用策略、
            能力边界、流程控制、问候或针对 Tool 行为的元反馈。空结果会返回模型，
            可在每轮最多 3 次的范围内调整概念查询后继续判断。
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
                return {
                    "error": "knowledge_search_failed",
                    "message": (
                        "知识库检索暂时失败，本次没有取得知识库证据。"
                        "请继续判断，并向用户明确说明证据边界。"
                    ),
                    "retryable": True,
                }
            _select_result_evidence(ctx.deps, result)
            trace_items = _trace_items(result)
            detail = _trace_detail(len(result), trace_items)
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

        @self._agent.tool(prepare=_prepare_web_tool)
        def search_web(
            ctx: RunContext[KnowledgeToolRegistry], query: str, limit: int = 5
        ) -> list[dict[str, object]] | dict[str, object]:
            """搜索公开网页。

            先把要回答的问题改写成你会输入网页搜索框的短查询；不要把工具反馈、
            元问题或整段聊天原样传入。需要互补角度时，分次调用本工具。
            """

            safe_limit = max(1, min(int(limit), 8))
            call_id = _tool_call_id(ctx, "search_web")
            tool_input = {"query": query, "limit": safe_limit}
            self._emit_tool_event(AgentToolEvent(
                tool="search_web",
                phase="started",
                call_id=call_id,
                input=tool_input,
                detail="正在搜索公开网页",
            ))
            try:
                result = ctx.deps.search_web(query, limit=safe_limit)
            except Exception:
                self._emit_tool_event(AgentToolEvent(
                    tool="search_web",
                    phase="failed",
                    call_id=call_id,
                    input=tool_input,
                    detail="联网搜索暂时失败",
                    error="web_search_failed",
                ))
                return {
                    "error": "web_search_failed",
                    "message": "联网搜索暂时失败，本轮没有取得网页证据。",
                    "retryable": False,
                }
            if isinstance(result, dict):
                self._emit_tool_event(AgentToolEvent(
                    tool="search_web",
                    phase="failed",
                    call_id=call_id,
                    input=tool_input,
                    detail=str(result.get("message") or "联网搜索未返回网页证据"),
                    error=str(result.get("error") or "web_search_failed"),
                ))
                return result
            _select_result_evidence(ctx.deps, result)
            self._emit_tool_event(AgentToolEvent(
                tool="search_web",
                phase="finished",
                call_id=call_id,
                input=tool_input,
                output={"result_count": len(result), "items": _trace_items(result)},
                detail=f"找到 {len(result)} 个网页结果",
            ))
            return result

        @self._agent.tool(prepare=_prepare_web_tool)
        def read_web_page(
            ctx: RunContext[KnowledgeToolRegistry], url: str
        ) -> dict[str, object]:
            """读取 search_web 本轮返回网页的正文，以便核对原始内容。"""

            call_id = _tool_call_id(ctx, "read_web_page")
            tool_input = {"url": url}
            self._emit_tool_event(AgentToolEvent(
                tool="read_web_page",
                phase="started",
                call_id=call_id,
                input=tool_input,
                detail="正在读取网页正文",
            ))
            try:
                result = ctx.deps.read_web_page(url)
            except Exception:
                self._emit_tool_event(AgentToolEvent(
                    tool="read_web_page",
                    phase="failed",
                    call_id=call_id,
                    input=tool_input,
                    detail="网页正文暂时无法读取",
                    error="web_page_read_failed",
                ))
                return {
                    "error": "web_page_read_failed",
                    "message": "网页正文暂时无法读取，不能把搜索摘要当作原文。",
                    "retryable": False,
                }
            _select_result_evidence(ctx.deps, [result])
            self._emit_tool_event(AgentToolEvent(
                tool="read_web_page",
                phase="finished",
                call_id=call_id,
                input=tool_input,
                output={"result_count": 1, "items": _trace_items([result])},
                detail=f"已读取网页：{result.get('title') or url}",
            ))
            return result

        @self._agent.tool(prepare=_prepare_material_tool)
        def search_research_materials(
            ctx: RunContext[KnowledgeToolRegistry], query: str, limit: int = 5
        ) -> list[dict[str, object]] | dict[str, object]:
            """检索当前研究任务中用户上传且仍有效的个人材料片段。

            结果总是带有 ``research_material`` 类型、稳定 segment locator 和
            ``personal_material`` 来源标记；工具不会访问其他任务或已删除正文。
            """
            safe_limit = max(1, min(int(limit), 8))
            call_id = _tool_call_id(ctx, "search_research_materials")
            tool_input = {"query": query, "limit": safe_limit}
            self._emit_tool_event(
                AgentToolEvent(
                    tool="search_research_materials",
                    phase="started",
                    call_id=call_id,
                    input=tool_input,
                    detail="正在检索个人研究材料",
                )
            )
            try:
                result = ctx.deps.search_research_materials(query, limit=safe_limit)
            except RetrievalPipelineUnavailable:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="search_research_materials",
                        phase="failed",
                        call_id=call_id,
                        input=tool_input,
                        detail="个人材料检索暂时失败",
                        error="research_material_search_failed",
                    )
                )
                raise
            except Exception:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="search_research_materials",
                        phase="failed",
                        call_id=call_id,
                        input=tool_input,
                        detail="个人材料检索暂时失败",
                        error="research_material_search_failed",
                    )
                )
                return {
                    "error": "research_material_search_failed",
                    "message": "个人研究材料检索暂时失败，请继续判断证据边界。",
                    "retryable": True,
                }
            if isinstance(result, list):
                if result:
                    _select_result_evidence(ctx.deps, result)
                count = len(result)
                output = {"result_count": count, "items": _trace_items(result)}
                detail = _material_trace_detail(result)
            else:
                output = result
                detail = str(result.get("message", "当前没有绑定个人研究材料"))
            self._emit_tool_event(
                AgentToolEvent(
                    tool="search_research_materials",
                    phase="finished" if isinstance(result, list) else "failed",
                    call_id=call_id,
                    input=tool_input,
                    output=output,
                    detail=detail,
                    error=None if isinstance(result, list) else str(result.get("error")),
                )
            )
            return result

        @self._agent.tool(prepare=_prepare_material_tool)
        def read_research_material_context(
            ctx: RunContext[KnowledgeToolRegistry],
            material_id: str,
            segment_id: str,
            parse_id: str | None = None,
            before: int = 2,
            after: int = 2,
        ) -> dict[str, object]:
            """沿稳定 locator 读取个人材料目标片段及有限前后文。

            重解析后重新打开历史引用时，必须把引用携带的 ``parse_id``
            一并传入；省略它只读取材料当前解析版本。
            """
            safe_before = max(0, min(int(before), 4))
            safe_after = max(0, min(int(after), 4))
            call_id = _tool_call_id(ctx, "read_research_material_context")
            tool_input = {
                "material_id": material_id,
                "segment_id": segment_id,
                "parse_id": parse_id,
                "before": safe_before,
                "after": safe_after,
            }
            self._emit_tool_event(
                AgentToolEvent(
                    tool="read_research_material_context",
                    phase="started",
                    call_id=call_id,
                    input=tool_input,
                    detail="正在读取个人材料原文上下文",
                )
            )
            try:
                if parse_id is None:
                    # Keep the call compatible with older test doubles and
                    # adapters while the optional argument rolls out.
                    result = ctx.deps.read_research_material_context(
                        material_id,
                        segment_id,
                        before=safe_before,
                        after=safe_after,
                    )
                else:
                    result = ctx.deps.read_research_material_context(
                        material_id,
                        segment_id,
                        parse_id=parse_id,
                        before=safe_before,
                        after=safe_after,
                    )
            except RetrievalPipelineUnavailable:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="read_research_material_context",
                        phase="failed",
                        call_id=call_id,
                        input=tool_input,
                        detail="个人材料原文读取暂时失败",
                        error="research_material_context_failed",
                    )
                )
                raise
            except Exception:
                self._emit_tool_event(
                    AgentToolEvent(
                        tool="read_research_material_context",
                        phase="failed",
                        call_id=call_id,
                        input=tool_input,
                        detail="个人材料原文读取暂时失败",
                        error="research_material_context_failed",
                    )
                )
                return {
                    "error": "research_material_context_failed",
                    "material_id": material_id,
                    "segment_id": segment_id,
                }
            found = "error" not in result
            if found:
                _select_result_evidence(ctx.deps, [result])
            self._emit_tool_event(
                AgentToolEvent(
                    tool="read_research_material_context",
                    phase="finished" if found else "failed",
                    call_id=call_id,
                    input=tool_input,
                    output={
                        "found": found,
                        "material_id": material_id,
                        "segment_id": segment_id,
                        "locator": result.get("locator"),
                        "context_count": len(result.get("context", []))
                        if isinstance(result.get("context"), list)
                        else 0,
                    },
                    detail="已读取个人材料原文上下文" if found else "没有找到当前材料片段",
                    error=None if found else str(result.get("error")),
                )
            )
            return result

        @self._agent.tool(prepare=_prepare_analysis_tool)
        def get_research_analysis(
            ctx: RunContext[KnowledgeToolRegistry],
        ) -> dict[str, object]:
            """读取当前研究任务已有的标注、编码、备忘与比较，不产生写入。"""

            return self._run_analysis_tool(
                ctx,
                "get_research_analysis",
                {},
                "正在读取质性分析",
                candidate=False,
            )

        @self._agent.tool(prepare=_prepare_analysis_tool)
        def propose_analysis_code(
            ctx: RunContext[KnowledgeToolRegistry],
            label: str,
            definition: str,
            annotation_ids: list[str],
            rationale: str,
        ) -> dict[str, object]:
            """基于用户已有标注提出待确认编码；不会确认主题、理论或结论。"""

            return self._run_analysis_tool(
                ctx,
                "propose_analysis_code",
                {
                    "label": label,
                    "definition": definition,
                    "annotation_ids": annotation_ids,
                    "rationale": rationale,
                },
                "正在生成编码候选",
                candidate=True,
            )

        @self._agent.tool(prepare=_prepare_analysis_tool)
        def propose_analysis_memo(
            ctx: RunContext[KnowledgeToolRegistry],
            title: str,
            content: str,
            memo_kind: str,
            annotation_ids: list[str],
            code_ids: list[str],
        ) -> dict[str, object]:
            """基于已有材料与分析提出待确认备忘；不会写入最终研究判断。"""

            return self._run_analysis_tool(
                ctx,
                "propose_analysis_memo",
                {
                    "title": title,
                    "content": content,
                    "memo_kind": memo_kind,
                    "annotation_ids": annotation_ids,
                    "code_ids": code_ids,
                },
                "正在生成分析备忘候选",
                candidate=True,
            )

        @self._agent.tool(prepare=_prepare_analysis_tool)
        def propose_coding_plan(
            ctx: RunContext[KnowledgeToolRegistry],
            title: str,
            rationale: str,
            items: list[dict[str, object]],
        ) -> dict[str, object]:
            """提出把新材料片段归入既有确认编码的待审计划。"""

            return self._run_analysis_tool(
                ctx,
                "propose_coding_plan",
                {"title": title, "rationale": rationale, "items": items},
                "正在生成编码计划候选",
                candidate=True,
            )

        @self._agent.tool(prepare=_prepare_analysis_tool)
        def retrieve_coded_segments(
            ctx: RunContext[KnowledgeToolRegistry],
            code_ids: list[str],
            material_id: str | None = None,
            query: str | None = None,
            limit: int = 50,
        ) -> list[dict[str, object]] | dict[str, object]:
            """读取已确认编码对应的原文片段，不产生写入。"""

            return self._run_analysis_tool(
                ctx,
                "retrieve_coded_segments",
                {"code_ids": code_ids, "material_id": material_id, "query": query, "limit": limit},
                "正在检索已确认编码片段",
                candidate=False,
            )

        @self._agent.tool(prepare=_prepare_analysis_tool)
        def get_research_comparison_context(
            ctx: RunContext[KnowledgeToolRegistry],
            case_labels: list[str],
            time_labels: list[str],
        ) -> dict[str, object]:
            """读取至少两个案例及可选时间锚点的已有分析，不产生写入。"""

            return self._run_analysis_tool(
                ctx,
                "get_research_comparison_context",
                {
                    "case_labels": case_labels,
                    "time_labels": time_labels,
                },
                "正在读取案例比较上下文",
                candidate=False,
            )

        @self._agent.tool(prepare=_prepare_analysis_tool)
        def propose_case_comparison(
            ctx: RunContext[KnowledgeToolRegistry],
            title: str,
            question: str,
            case_labels: list[str],
            time_labels: list[str],
            findings: list[dict[str, object]],
            competing_explanations: list[str],
            evidence_gaps: list[str],
            next_steps: list[dict[str, object]],
            theory_implication: str,
        ) -> dict[str, object]:
            """提出待用户确认的案例比较；不会替用户决定理论或结论。"""

            return self._run_analysis_tool(
                ctx,
                "propose_case_comparison",
                {
                    "title": title,
                    "question": question,
                    "case_labels": case_labels,
                    "time_labels": time_labels,
                    "findings": findings,
                    "competing_explanations": competing_explanations,
                    "evidence_gaps": evidence_gaps,
                    "next_steps": next_steps,
                    "theory_implication": theory_implication,
                },
                "正在生成案例比较候选",
                candidate=True,
            )

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
            self._emit_tool_event(
                AgentToolEvent(
                    tool="read_knowledge_entry",
                    phase="finished",
                    call_id=call_id,
                    input={"knowledge_id": knowledge_id},
                    output={
                        "found": found,
                        "knowledge_id": knowledge_id,
                        "title": result.get("title"),
                        "excerpt": _trace_excerpt(result.get("content")),
                    },
                    detail=(
                        f"已读取知识条目：{result.get('title', knowledge_id)}"
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

    def _run_analysis_tool(
        self,
        ctx: RunContext[KnowledgeToolRegistry],
        tool_name: str,
        payload: dict[str, object],
        detail: str,
        *,
        candidate: bool,
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
            invocation = dict(payload)
            if candidate:
                # The model never supplies provenance. The runner binds each
                # candidate to Pydantic AI's stable call identity.
                invocation["tool_call_id"] = call_id
            result = getattr(ctx.deps, tool_name)(**invocation)
        except Exception as error:
            failure = {
                "error": "research_analysis_tool_failed",
                "message": str(error),
            }
            self._emit_tool_event(
                AgentToolEvent(
                    tool=tool_name,
                    phase="failed",
                    call_id=call_id,
                    input=payload,
                    output=failure,
                    detail="质性分析操作未完成",
                    error="research_analysis_tool_failed",
                )
            )
            return failure
        failed = bool(result.get("error"))
        self._emit_tool_event(
            AgentToolEvent(
                tool=tool_name,
                phase="failed" if failed else "finished",
                call_id=call_id,
                input=payload,
                output=result,
                detail=(
                    str(result.get("message", "质性分析操作未完成"))
                    if failed
                    else "已生成待用户确认的分析候选"
                    if candidate
                    else "已读取质性分析"
                ),
                error=str(result["error"]) if failed else None,
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
        retrieved_evidence = self._preload_bound_research_evidence(
            prompt=prompt,
            conversation=conversation,
            tools=tools,
        )
        result = self._agent.run_sync(
            _compose_agent_prompt(
                prompt=prompt,
                research_map=getattr(tools, "research_map", None)
                if getattr(tools, "research_map_enabled", False)
                else None,
                document_context=getattr(tools, "document_prompt_context", None),
                retrieved_evidence=retrieved_evidence,
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
            retrieved_evidence = self._preload_bound_research_evidence(
                prompt=prompt,
                conversation=conversation,
                tools=tools,
            )
            result = self._agent.run_sync(
                _compose_agent_prompt(
                    prompt=prompt,
                    research_map=getattr(tools, "research_map", None)
                    if getattr(tools, "research_map_enabled", False)
                    else None,
                    document_context=getattr(tools, "document_prompt_context", None),
                    retrieved_evidence=retrieved_evidence,
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

    def _preload_bound_research_evidence(
        self,
        *,
        prompt: str,
        conversation: Sequence[AgentTurn],
        tools: AgentToolContext,
    ) -> dict[str, object] | None:
        """Load both evidence pools before a bound research turn reaches the model."""

        if not _material_tools_available(tools) or not _should_search_knowledge(
            prompt,
            research_workspace=bool(getattr(tools, "research_map_enabled", False)),
            document_workspace=bool(
                getattr(tools, "research_document_tools_enabled", False)
            ),
            conversation=conversation,
        ):
            return None
        query = _evidence_retrieval_query(prompt, conversation=conversation)
        public = self._preload_public_evidence(tools=tools, query=query)
        personal = self._preload_personal_evidence(tools=tools, query=query)
        return {
            "query": query,
            "public_knowledge": public,
            "personal_materials": personal,
        }

    def _preload_public_evidence(
        self,
        *,
        tools: AgentToolContext,
        query: str,
    ) -> list[Mapping[str, object]] | dict[str, object]:
        call_id = "runner:search_knowledge"
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
            raw_result = tools.search_knowledge(query)
        except Exception:
            failure = {
                "error": "knowledge_search_failed",
                "message": "知识库检索暂时失败，本次没有取得公共知识证据。",
                "retryable": True,
            }
            self._emit_tool_event(
                AgentToolEvent(
                    tool="search_knowledge",
                    phase="failed",
                    call_id=call_id,
                    input={"query": query},
                    output=failure,
                    detail="知识库检索暂时失败",
                    error="knowledge_search_failed",
                )
            )
            return failure
        result = _mapping_results(raw_result)
        if result:
            _select_result_evidence(tools, result)
        trace_items = _trace_items(result)
        self._emit_tool_event(
            AgentToolEvent(
                tool="search_knowledge",
                phase="finished",
                call_id=call_id,
                input={"query": query},
                output={"result_count": len(result), "items": trace_items},
                detail=_trace_detail(len(result), trace_items),
            )
        )
        return result

    def _preload_personal_evidence(
        self,
        *,
        tools: AgentToolContext,
        query: str,
    ) -> list[Mapping[str, object]] | dict[str, object]:
        call_id = "runner:search_research_materials"
        tool_input = {"query": query, "limit": 5}
        self._emit_tool_event(
            AgentToolEvent(
                tool="search_research_materials",
                phase="started",
                call_id=call_id,
                input=tool_input,
                detail="正在检索个人研究材料",
            )
        )
        try:
            raw_result = tools.search_research_materials(query, limit=5)
        except RetrievalPipelineUnavailable:
            self._emit_tool_event(
                AgentToolEvent(
                    tool="search_research_materials",
                    phase="failed",
                    call_id=call_id,
                    input=tool_input,
                    detail="个人材料检索暂时失败",
                    error="research_material_search_failed",
                )
            )
            raise
        except Exception:
            failure = {
                "error": "research_material_search_failed",
                "message": "个人研究材料检索暂时失败，请继续判断证据边界。",
                "retryable": True,
            }
            self._emit_tool_event(
                AgentToolEvent(
                    tool="search_research_materials",
                    phase="failed",
                    call_id=call_id,
                    input=tool_input,
                    output=failure,
                    detail="个人材料检索暂时失败",
                    error="research_material_search_failed",
                )
            )
            return failure
        result = _mapping_results(raw_result)
        if result:
            _select_result_evidence(tools, result)
        self._emit_tool_event(
            AgentToolEvent(
                tool="search_research_materials",
                phase="finished",
                call_id=call_id,
                input=tool_input,
                output={"result_count": len(result), "items": _trace_items(result)},
                detail=_material_trace_detail(result),
            )
        )
        return result


def _is_deepseek_flash(*, base_url: str, model: str) -> bool:
    return "deepseek.com" in base_url.lower() and model.lower() == "deepseek-v4-flash"


def _is_transient_unknown_provider(error: ModelHTTPError) -> bool:
    if error.status_code != 400:
        return False
    body = error.body
    message: object | None = None
    if isinstance(body, Mapping):
        message = body.get("message")
        nested_error = body.get("error")
        if message is None and isinstance(nested_error, Mapping):
            message = nested_error.get("message")
    return isinstance(message, str) and "unknown provider for model" in message.lower()


def _is_retryable_model_error(error: ModelHTTPError | ModelAPIError) -> bool:
    if isinstance(error, ModelHTTPError):
        return (
            _is_transient_unknown_provider(error)
            or error.status_code in {408, 409, 429}
            or error.status_code >= 500
        )
    return True


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
        "好的，谢谢",
        "你好",
        "您好",
        "辛苦了",
        "再见",
        "晚安",
        "早上好",
        "下午好",
        "晚上好",
        "嗯",
        "嗯嗯",
    }
)

_CASUAL_ACK_PATTERNS = (
    r"(?:你|您)好(?:呀|啊|啦)?",
    r"辛苦(?:了|啦)",
    r"收到(?:了)?",
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

_GENERATIVE_KNOWLEDGE_DOCUMENT_ACTIONS = (
    "重写",
    "改写",
    "补充",
    "新增",
    "增加",
    "扩写",
    "生成",
)

_CONTEXTUAL_EVIDENCE_PATTERNS = (
    r"^为什么(?:呢)?[？?]?$",
    r"^(?:有|有什么)?(?:依据|出处|来源|文献|参考资料)(?:吗|呢)?[？?]?$",
    r"^(?:还)?需要(?:什么|哪些|怎样的?)依据[？?]?$",
    (
        r"^(?:这个|该|这一)(?:理论|概念|解释|说法|主张|结论)的?"
        r"依据(?:是什么|有哪些|在哪|呢|吗)?[？?]?$"
    ),
    (
        r"^(?:这个|该|这一)?(?:理论|概念|解释|说法)?"
        r"(?:靠谱吗|可靠(?:吗)?|可信(?:吗)?|成立(?:吗)?|适用(?:吗)?)[？?]?$"
    ),
)

_EVIDENCE_REQUEST_PATTERNS = (
    (
        r"(?:有|有什么|给出|提供|说明|缺少).{0,6}"
        r"依据(?!现有|当前|给定|上述|以下|这个|该|模板|格式|要求|规则|材料)"
    ),
    r"需要(?:什么|哪些|怎样的?)依据",
    r"(?:理论|概念|解释|说法|主张).{0,8}的?依据",
    r"依据(?:是|来自|在哪|是什么|有哪些|呢|吗)",
)

_IDENTITY_CONTEXT_PATTERNS = (
    r"^(?:你是谁|你叫什么(?:名字)?|你能做什么|你可以做什么)[？?]?$",
    r"^你的(?:身份|模型|名字|能力)(?:是|是什么|呢|吗)?[？?]?$",
    (
        r"^(?:请问\s*)?你是\s*(?:一名|一个)?\s*(?:什么|哪个)?\s*"
        r"(?:社会学|研究|ai|人工智能)?\s*"
        r"(?:agent|助手|模型|智能体|机器人)\s*(?:吗|呢)?[？?]?$"
    ),
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
    "纠正",
    "删除",
    "删掉",
    "接受",
    "拒绝",
    "撤销",
    "改写",
    "补充",
    "新增",
    "增加",
    "扩写",
    "生成",
    "写成",
)


def _requires_knowledge_evidence(
    prompt: str,
    *,
    research_workspace: bool,
    document_workspace: bool = False,
    conversation: Sequence[AgentTurn] = (),
) -> bool:
    normalized = " ".join(prompt.split())
    if _is_flow_control_prompt(normalized) or _is_casual_ack_prompt(normalized):
        return False
    is_document_operation = document_workspace and any(
        marker in normalized for marker in _DOCUMENT_OPERATION_MARKERS
    )
    if is_document_operation:
        if _explicit_evidence_requested(normalized):
            return True
        if any(marker in normalized for marker in _SEMANTIC_EDIT_MARKERS):
            return True
        if any(marker in normalized for marker in _KNOWLEDGE_JUDGMENT_MARKERS) and any(
            marker in normalized for marker in _GENERATIVE_KNOWLEDGE_DOCUMENT_ACTIONS
        ):
            return True
        if any(marker in normalized for marker in _NON_EPISTEMIC_DOCUMENT_ACTIONS):
            return False
        if any(marker in normalized for marker in _STRUCTURAL_PRESENTATION_EDIT_MARKERS):
            return False
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
    if _is_contextual_evidence_followup(normalized) and _conversation_has_research_context(
        conversation
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
        return f"{prompt}\n检索目标：从知识库中寻找可形成研究问题的候选方向。"
    return prompt


def _is_contextual_evidence_followup(normalized: str) -> bool:
    return any(re.fullmatch(pattern, normalized) for pattern in _CONTEXTUAL_EVIDENCE_PATTERNS)


def _explicit_evidence_requested(normalized: str) -> bool:
    return any(marker in normalized for marker in _EXPLICIT_EVIDENCE_MARKERS) or any(
        re.search(pattern, normalized) for pattern in _EVIDENCE_REQUEST_PATTERNS
    )


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
                "这个说法",
                "该说法",
                "这一说法",
                "这个主张",
                "该主张",
                "这一主张",
                "这个结论",
                "该结论",
                "这一结论",
                "这个解释",
                "该解释",
                "这一解释",
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
        or (
            any(marker in normalized for marker in _GENERATIVE_KNOWLEDGE_DOCUMENT_ACTIONS)
            and any(marker in normalized for marker in _KNOWLEDGE_JUDGMENT_MARKERS)
        )
    )


def _recent_research_topic(conversation: Sequence[AgentTurn]) -> str | None:
    for turn in reversed(conversation):
        if _turn_has_structured_evidence(turn):
            return _turn_research_query_context(turn)
        candidate = _normalized_text(turn.user_message.content)
        if not candidate or _is_non_substantive_prompt(candidate):
            continue
        return _turn_research_query_context(turn)
    return None


def _conversation_has_research_context(
    conversation: Sequence[AgentTurn],
) -> bool:
    for turn in reversed(conversation):
        if _turn_has_structured_evidence(turn):
            return True
        candidate = _normalized_text(turn.user_message.content)
        if not candidate or _is_non_substantive_prompt(candidate):
            continue
        return _turn_has_research_context(turn)
    return False


def _turn_has_research_context(turn: AgentTurn) -> bool:
    if _turn_has_structured_evidence(turn):
        return True
    user_content = _normalized_text(turn.user_message.content)
    if _is_identity_context_prompt(user_content):
        return False
    assistant_content = _normalized_text(turn.assistant_message.content)
    return any(
        marker in content
        for content in (user_content, assistant_content)
        for marker in _RESEARCH_CONTEXT_MARKERS
    )


def _turn_has_structured_evidence(turn: AgentTurn) -> bool:
    return bool(turn.evidence_ids or turn.assistant_message.citations)


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


def _is_casual_ack_prompt(normalized: str) -> bool:
    token = _control_token(normalized)
    return token in _CASUAL_ACK_PROMPTS or any(
        re.fullmatch(pattern, token) for pattern in _CASUAL_ACK_PATTERNS
    )


def _is_identity_context_prompt(normalized: str) -> bool:
    return any(
        re.search(pattern, normalized, flags=re.IGNORECASE)
        for pattern in _IDENTITY_CONTEXT_PATTERNS
    )


def _is_non_substantive_prompt(normalized: str) -> bool:
    return (
        _is_flow_control_prompt(normalized)
        or _is_casual_ack_prompt(normalized)
        or _is_contextual_evidence_followup(normalized)
    )


def _control_token(normalized: str) -> str:
    return normalized.rstrip("。！？!?….").strip()


def _normalized_text(value: str) -> str:
    return " ".join(value.split())


def _trace_items(values, *, limit: int = 4) -> list[dict[str, object]]:
    """Return bounded, user-safe facts for the visible tool trace."""

    items: list[dict[str, object]] = []
    for value in values[:limit]:
        if isinstance(value, AgentEvidence):
            item = {
                "title": value.label,
                "excerpt": _trace_excerpt(value.excerpt),
                "evidence_status": "verified",
            }
            for key, field_value in (
                ("knowledge_id", value.knowledge_id),
                ("material_id", value.material_id),
                ("parse_id", value.parse_id),
                ("segment_id", value.segment_id),
                ("source_id", value.source_id),
                ("source_kind", value.source_kind),
            ):
                if field_value is not None:
                    item[key] = field_value
            if value.locator is not None:
                item["locator"] = dict(value.locator)
        elif isinstance(value, Mapping):
            item = {}
            for key in (
                "knowledge_id",
                "material_id",
                "segment_id",
                "source_kind",
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
                        "verified"
                        if key == "evidence_status"
                        else _trace_excerpt(value[key])
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
) -> str:
    if not items:
        return "没有找到可展示的知识条目"
    labels = []
    for item in items[:3]:
        title = item.get("title") or item.get("knowledge_id") or item.get("node_id")
        excerpt = item.get("excerpt") or item.get("content_excerpt")
        labels.append(f"{title}{f'：{excerpt}' if excerpt else ''}")
    return f"找到 {count} 条可引用证据：{'；'.join(labels)}"


def _material_trace_detail(values: Sequence[Mapping[str, object]]) -> str:
    if not values:
        return "没有找到可展示的个人材料片段"
    labels = []
    for item in values[:3]:
        title = item.get("title") or item.get("material_id") or "个人材料"
        locator = item.get("locator")
        labels.append(f"{title}{f'（{_locator_trace(locator)}）' if locator else ''}")
    return f"找到 {len(values)} 条个人材料证据：{'；'.join(labels)}"


def _locator_trace(value: object) -> str:
    if not isinstance(value, Mapping):
        return "原文位置"
    pieces: list[str] = []
    if value.get("page") is not None:
        pieces.append(f"第{value['page']}页")
    if value.get("paragraph") is not None:
        pieces.append(f"第{value['paragraph']}段")
    if value.get("line_start") is not None:
        end = value.get("line_end") or value["line_start"]
        pieces.append(f"第{value['line_start']}-{end}行")
    return "，".join(pieces) or "原文位置"


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
    retrieved_evidence: Mapping[str, object] | None = None,
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
    retrieved_evidence_text = (
        "\n\n<retrieved_research_evidence_policy>"
        "服务端已为本轮同时检索群学公共知识与当前任务的个人材料。"
        "下面两组结果均为空时才表示没有候选证据；同一 query 不要重复调用检索工具，"
        "只有需要改写查询或补充证据时才再次检索。回答必须明确区分两类来源。"
        "</retrieved_research_evidence_policy>\n<retrieved_research_evidence>\n"
        f"{json.dumps(retrieved_evidence, ensure_ascii=False, separators=(',', ':'), default=str)}"
        "\n</retrieved_research_evidence>"
        if retrieved_evidence is not None
        else ""
    )
    return f"{prompt}{map_context}{document_context_text}{retrieved_evidence_text}"


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


def _prepare_web_tool(
    ctx: RunContext[KnowledgeToolRegistry],
    definition: ToolDefinition,
) -> ToolDefinition | None:
    """Expose open-web tools only when the user enables them for this turn."""

    return (
        definition
        if getattr(ctx.deps, "web_search_enabled", False)
        and callable(getattr(ctx.deps, definition.name, None))
        else None
    )


def _prepare_material_tool(
    ctx: RunContext[KnowledgeToolRegistry],
    definition: ToolDefinition,
) -> ToolDefinition | None:
    """Expose personal-material tools only for an authorized bound task."""

    return (
        definition
        if getattr(ctx.deps, "research_material_tools_enabled", False)
        and callable(getattr(ctx.deps, definition.name, None))
        else None
    )


def _prepare_analysis_tool(
    ctx: RunContext[KnowledgeToolRegistry],
    definition: ToolDefinition,
) -> ToolDefinition | None:
    """Expose only approval-gated analysis tools with complete run provenance."""

    return (
        definition
        if getattr(ctx.deps, "research_analysis_tools_enabled", False)
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
    incoming = tuple(dict.fromkeys(citation_ids))
    if not incoming:
        _set_selected_evidence(tools, ())
        return

    # A research turn may deliberately combine a public concept with a
    # task-scoped personal excerpt.  Keep both source kinds in that case;
    # repeated searches within one source still replace the previous closed
    # set, preserving the existing reformulation behavior.
    existing = tuple(getattr(tools, "selected_evidence_ids", ()))
    incoming_kinds = {_evidence_source_bucket(tools, citation_id) for citation_id in incoming}
    if existing and len(incoming_kinds) == 1:
        # A reformulation replaces candidates from its own evidence pool while
        # retaining knowledge, personal material, and web evidence from the
        # other pools used in the same answer.
        incoming_bucket = next(iter(incoming_kinds))
        preserved = tuple(
            citation_id
            for citation_id in existing
            if _evidence_source_bucket(tools, citation_id) != incoming_bucket
        )
        selected = tuple(dict.fromkeys((*preserved[:7], *incoming)))
    else:
        selected = incoming
    _set_selected_evidence(tools, selected[:8])


def _set_selected_evidence(tools: AgentToolContext, citation_ids: Sequence[str]) -> None:
    """Keep partial test/tool contexts compatible with the evidence protocol.

    Production registries expose ``select_evidence`` so the closed citation set
    is persisted in the run context.  A few lightweight deterministic runner
    fixtures intentionally provide only search and evidence maps; preserving
    their selected ids locally keeps those fixtures useful without weakening
    the production protocol.
    """

    selector = getattr(tools, "select_evidence", None)
    if callable(selector):
        selector(citation_ids)
        return
    try:
        tools.selected_evidence_ids = tuple(citation_ids)  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        # Immutable partial contexts cannot retain selection, but they can
        # still produce the deterministic answer and trace.
        return


def _evidence_source_bucket(tools: AgentToolContext, citation_id: str) -> str:
    evidence = tools.evidence.get(citation_id)
    source_kind = getattr(evidence, "source_kind", None)
    if source_kind == "personal_material":
        return "personal"
    if source_kind == "web":
        return "web"
    return "public"


def _tool_call_id(ctx: RunContext[KnowledgeToolRegistry], tool: str) -> str:
    return ctx.tool_call_id or f"{ctx.run_id or 'agent-run'}:{ctx.run_step}:{tool}"
