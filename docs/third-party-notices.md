# Third-party notices

群学致知的网页搜索适配器复用了以下 MIT 许可证项目中的实现片段，记忆提取提示词复用了 Apache-2.0 片段，并保留其版权归属。项目自身其余代码继续遵守仓库根目录许可证与贡献规范。

## OpenAI Codex

- Source: <https://github.com/openai/codex/tree/2bd71f96d41809b95ea881429a1b68eb48d089b6>
- License: Apache-2.0; LICENSE and NOTICE retained in [`third_party/openai-codex`](../third_party/openai-codex/).
- Adapted area: memory extraction hygiene and minimum-signal prompt sections. Output schema and research-specific rules are adapted; [modification notice](../third_party/openai-codex/README.md).

## Stanford STORM

- Source: <https://github.com/stanford-oval/storm>
- License: <https://github.com/stanford-oval/storm/blob/main/LICENSE>
- Copyright: Copyright (c) 2024 Stanford Open Virtual Assistant Lab
- Adapted areas: Tavily provider result mapping and bounded search-box query cleaning.

## LangChain Open Deep Research

- Source: <https://github.com/langchain-ai/open_deep_research>
- License: <https://github.com/langchain-ai/open_deep_research/blob/main/LICENSE>
- Copyright: Copyright (c) 2025 LangChain
- Adapted areas: Tavily SDK request shape with raw content enabled and URL-deduplicated result handling.

## MIT license text

The adapted portions above are distributed under the MIT License:

```text
MIT License

Copyright (c) the copyright holders identified above

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
