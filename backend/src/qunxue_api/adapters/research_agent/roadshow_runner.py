"""Account-scoped rehearsal reports with observable, real retrieval calls."""

import json
import time
from pathlib import Path
from uuid import uuid4

from qunxue_api.modules.agent_conversation import (
    AgentInterrupted,
    AgentResearchEvent,
    AgentRunResult,
    AgentToolEvent,
)


class RoadshowRunner:
    def __init__(self, fallback, config):
        self.fallback = fallback
        self.config = config
        self.runtime_identity = fallback.runtime_identity

    @classmethod
    def wrap(cls, fallback):
        # This private deployment file holds the account ID and authored reports.
        # Absence leaves the normal runner intact, including its optional callbacks.
        path = Path(__file__).resolve().parents[4] / "var" / "roadshow.json"
        return cls(fallback, json.loads(path.read_text())) if path.is_file() else fallback

    def _case(self, prompt, tools):
        context = tools.agent_route_context() if tools is not None else {}
        if str(context.get("user_id")) != self.config["user_id"]:
            return None
        return next(
            (
                case
                for case in self.config["cases"]
                if any(word in prompt for word in case["keywords"])
            ),
            None,
        )

    def handles(self, *, prompt, tools):
        return self._case(prompt, tools) is not None

    def prepare_research(
        self, *, prompt, conversation, tools=None, on_event, is_cancelled=None, on_title=None
    ):
        case = self._case(prompt, tools)
        if case is None:
            from inspect import signature

            kwargs = dict(
                prompt=prompt,
                conversation=conversation,
                tools=tools,
                on_event=on_event,
                is_cancelled=is_cancelled,
                on_title=on_title,
            )
            parameters = signature(self.fallback.prepare_research).parameters
            self.fallback.prepare_research(**{k: v for k, v in kwargs.items() if k in parameters})
            return
        if on_title:
            on_title(case["title"])
        selected = prompt.rsplit("用户选择的研究重点：", 1)[-1].strip()
        if "用户选择的研究重点：" in prompt or "用户跳过了本次澄清" in prompt:
            title = case["title"]
            if "用户选择的研究重点：" in prompt:
                title += f" · {selected}"
            on_event(AgentResearchEvent("plan", {"title": title, "steps": case["steps"]}))
        else:
            on_event(
                AgentResearchEvent(
                    "ask",
                    {
                        "question": case["question"],
                        "options": [*case["options"], "更多自定义"],
                    },
                )
            )

    def run(self, *, prompt, conversation, tools):
        return self.run_stream(
            prompt=prompt, conversation=conversation, tools=tools, on_delta=lambda _: None
        )

    def run_stream(
        self,
        *,
        prompt,
        conversation,
        tools,
        on_delta,
        on_tool_event=None,
        is_cancelled=None,
        on_checkpoint=None,
        can_cancel=None,
    ):
        case = self._case(prompt, tools)
        if case is None:
            from inspect import signature

            kwargs = dict(
                prompt=prompt,
                conversation=conversation,
                tools=tools,
                on_delta=on_delta,
                on_tool_event=on_tool_event,
                is_cancelled=is_cancelled,
                on_checkpoint=on_checkpoint,
                can_cancel=can_cancel,
            )
            parameters = signature(self.fallback.run_stream).parameters
            if any(p.kind == p.VAR_KEYWORD for p in parameters.values()):
                return self.fallback.run_stream(**kwargs)
            return self.fallback.run_stream(**{k: v for k, v in kwargs.items() if k in parameters})

        def check_cancelled():
            if is_cancelled and is_cancelled():
                raise AgentInterrupted("Agent run was interrupted")

        def invoke(name, payload):
            check_cancelled()
            call_id = str(uuid4())
            if on_tool_event:
                on_tool_event(AgentToolEvent(name, "started", call_id, input=payload))
            try:
                result = getattr(tools, name)(**payload)
                if isinstance(result, dict) and result.get("error"):
                    raise ValueError(str(result["error"]))
            except AgentInterrupted:
                raise
            except Exception as error:
                if on_tool_event:
                    on_tool_event(
                        AgentToolEvent(
                            name,
                            "failed",
                            call_id,
                            input=payload,
                            error=type(error).__name__,
                            detail="本次资料获取未完成，继续整理已有材料",
                        )
                    )
                return []
            check_cancelled()
            if on_tool_event:
                items = result if isinstance(result, list) else [result]
                on_tool_event(
                    AgentToolEvent(
                        name,
                        "finished",
                        call_id,
                        input=payload,
                        output={"result_count": len(items), "items": items},
                        detail=f"已获取 {len(items)} 条资料",
                    )
                )
            return result

        check_cancelled()
        tools.enable_web_search()
        for query in case.get("knowledge_queries", []):
            invoke("search_knowledge", {"query": query, "limit": 3})
        read_urls = set()
        for query in case.get("web_queries", []):
            results = invoke("search_web", {"query": query, "limit": 3})
            if isinstance(results, list):
                for item in results[:1]:
                    url = item.get("url")
                    if url and url not in read_urls:
                        read_urls.add(url)
                        invoke("read_web_page", {"url": url})
        answer = case["answer"]
        for index in range(0, len(answer), 64):
            check_cancelled()
            on_delta(answer[index : index + 64])
            time.sleep(self.config.get("chunk_delay", 0.025))
        # Retrieved sources are exploration records, not automatic support for an
        # authored report; do not manufacture inline citations from nearby results.
        return AgentRunResult(
            answer=answer,
            citations=(),
            release_id=tools.release.knowledge_release_id,
            provider="authored-case",
            model="report-v1",
        )
