# Open-web research source ledger

## Selected implementation

群学的研究链路直接复用了两个 MIT 项目中可独立移植的网页检索实现：Tavily SDK 调用、`include_raw_content` 原文返回与结果 URL 去重来自 [LangChain Open Deep Research](https://github.com/langchain-ai/open_deep_research)；查询框清理和“由 Agent 先写搜索框查询”的边界来自 [STORM](https://github.com/stanford-oval/storm)。具体版权和许可证记录见 [third-party-notices.md](third-party-notices.md)。

参考文件：

- [deep_researcher.py](https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/deep_researcher.py)：研究简报、监督循环和有限迭代。
- [utils.py](https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/utils.py)：多查询检索、去重和网页摘要的边界。
- [prompts.py](https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/prompts.py)：澄清问题、研究简报和查询改写提示。
- [state.py](https://github.com/langchain-ai/open_deep_research/blob/main/src/open_deep_research/state.py)：研究状态和结构化输出边界。

## 群学适配部分

- 现有 pydantic-ai Agent 工具边界、自定义 JSON provider、官方域名和来源等级排序。
- 中文网页结果的证据闭集、URL 公开地址校验、网页正文读取和 Trafilatura 正文抽取。
- Tavily 原始结果到群学 `title/url/snippet` 结构的最小映射。
- 网页证据闭集、同轮重复查询阻断和终止性失败返回。
- 现有知识库调用策略、Agent 对话状态和 citation 选择边界保持不变。

## 未复制的项目

- [STORM](https://github.com/stanford-oval/storm) 使用 MIT 许可证；本次直接适配其查询清理和查询预算边界，没有复制 dspy、Bing 或报告生成代码。
- [Vane](https://github.com/ItzCrazyKns/Vane) 使用 MIT 许可证，但其公开 README 以 SearXNG 为主要搜索后端；当前任务明确禁止继续以 SearXNG 为核心，因此没有复用。
- [GPT Researcher](https://github.com/assafelovic/gpt-researcher) 使用 Apache-2.0；未复制其代码，避免在没有逐项兼容审查时引入 Apache 代码。

## 产品边界

OpenAI 的 [Responses API web search](https://developers.openai.com/api/reference/cli/resources/responses/methods/create) 和 Anthropic 的 [Claude web search tool](https://platform.claude.com/docs/zh-CN/agents-and-tools/tool-use/web-search-tool) 只公开工具协议和返回结构，不公开各自的内部搜索实现。DeepSeek 的 [Harness](https://github.com/deepseek-ai/deepseek-harness) 是 MIT 的开源 Agent Harness；它的 web-search provider 是外部 API 适配器，不应被描述为 DeepSeek、ChatGPT、Codex 或 Claude 的内部联网逻辑。
