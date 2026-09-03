# Issue #246：Agent coding tools 接入质性编码闭环

## 状态与范围

本增量把 Agent 从“提出候选编码”推进到“提出可审阅的既有代码归类计划”。它复用现有 `CodedDocumentWorkbench` 的三栏阅读、代码树、片段标记、检查器、备忘和检索入口，不新增第二个工作台，也不让 Agent 直接写入确认结果。

闭环固定为：读取材料与邻近片段 → 读取确认代码及代码本 → 生成带来源锚点的 coding plan → 用户逐项确认或拒绝 → 确认项通过现有 annotation 写入并挂到既有 confirmed code → 从原始 quote 与 locator 检索 → 审计、重放和失败恢复。

不在本 Issue 内：自动确认、自动撤销已确认编码、新模型供应商、新检索索引、批量全材料自动编码、替换现有人工工作台、生产部署策略。

## 依据与产品判断

- MAXQDA 的 AI coding suggestions 需要研究者评价后选择，代码 memo 会作为规则依据，结果仍要检查：[AI Coding: New Code Suggestions](https://www.maxqda.com/help/ai-assist/ai-coding/ai-new-codes-suggestions)。
- MAXQDA 对片段建议提供逐条或批量 approve/discard、apply changes 和 revert，解释保留在项目记录中：[AI Coding Segments](https://www.maxqda.com/help/ai-assist/ai-coding/ai-coding-segments)。
- MAXQDA 的代码系统支持层级、代码 memo 和合并历史；同名代码不重复创建：[The Code System](https://www.maxqda.com/help/the-workspace/the-main-menu-and-the-four-main-windows/the-code-system)。
- MAXQDA 的 memo 可以链接到文档、片段和代码，并记录作者与日期：[About Memos](https://www.maxqda.com/help/memos/about-memos)。
- ATLAS.ti 把代码组和 memo 作为可过滤、可回到证据的组织层；memo 可以链接 quotation、code 和 memo：[Code Groups](https://manuals.atlasti.com/Win/en/manual/Codes/CodeGroupsWorkingWith.html)、[Memos and Comments](https://doc.atlasti.com/ManualWin/Memos/MemosAndComments.html)。
- NVivo 查询配置可保存，但结果只有显式保存才成为研究记录：[Queries](https://help-nv.qsrinternational.com/12/win/v12.1.115-d3ea61/Content/queries/queries.htm)。因此本实现保存的是可重放的 plan、决定和原文锚点，不保存不可复核的模型瞬时结果。
- Agent 运行采用 plan/act/observe/adjust 循环，并保留 human control、transparency 和 privacy：[Anthropic, Trustworthy Agents](https://www.anthropic.com/research/trustworthy-agents)。OpenAI 的工具调用也把 approval 作为显式边界：[Responses API tools and approvals](https://platform.openai.com/docs/api-reference/responses-streaming/response/refusal?lang=python)。

## 现有接入点

| 层 | 复用对象 | 本 Issue 的变化 |
| --- | --- | --- |
| 材料 | `ResearchMaterialReader`、`search_research_materials`、`read_research_material_context` | 不改变检索授权；plan 保存 material/parse/segment/hash/range/locator |
| 分析 | `ResearchAnalysisApplication`、`AnalysisAnnotation`、`AnalysisCode`、`CodebookEntry` | 增加 `AnalysisCodingPlan`；确认时调用已有 annotation 创建和 confirmed code 挂接 |
| Agent | `ResearchDocumentToolRegistry`、`pydantic_runner` | 增加 `propose_coding_plan`（候选）和 `retrieve_coded_segments`（只读） |
| API | `/api/research-tasks/{task_id}/analysis` | snapshot 返回 plans；新增 plan decision、retrieved-segments、audit 端点 |
| 前端 | `ResearchAnalysisPanel` → `ResearchAnalysisWorkspace` | 在已有“待你判断”区域显示片段、目标代码、置信度、定位和逐项按钮 |

## 数据契约

### Coding plan

`AnalysisCodingPlan` 是任务所有、不可跨任务读取的版本化记录。它包含 `plan_id/title/rationale/source/status/version/created_at`、Agent conversation/run/turn/tool provenance，以及 `items[]`。

每个 item 必须包含：

- `material_id`, `parse_id`, `segment_id`, `segment_content_hash`
- `quote`, `quote_hash`, `quote_start`, `quote_end`, `locator`
- 已确认的 `code_id`，以及生成时的 `code_label/code_definition/codebook_version`
- `confidence`（0–1）、`rationale`
- `status`（`candidate` → `applied` 或 `rejected`）、`annotation_id`、`decision_reason`

计划状态为 `candidate`、`applied`、`partially_applied`、`rejected`、`revoked`。一旦用户决定，plan version +1；每个 item 只允许一次决定，已应用批次可显式撤销。

### API

```text
GET  /api/research-tasks/{task_id}/analysis
     -> ... coding_plans[]

POST /api/research-tasks/{task_id}/analysis/coding-plans/{plan_id}/decision
     Idempotency-Key: <key>
     { expected_version, decisions: [{ item_id, decision: confirmed|rejected, reason }] }

GET  /api/research-tasks/{task_id}/analysis/retrieved-segments
     ?code_id=<uuid>&material_id=<uuid>&query=<text>&limit=<n>

GET  /api/research-tasks/{task_id}/analysis/audit

POST /api/research-tasks/{task_id}/analysis/coding-plans/{plan_id}/revoke
     Idempotency-Key: <key>
     { expected_version, reason }
```

决策端点要求任务归属、完整 item 集合、CAS version、非空 reason 和当前 source hash/quote 匹配。确认项会以 `coding-plan:{plan_id}:item:{item_id}` 作为 annotation 幂等键。

### Agent tools

- `propose_coding_plan(title, rationale, items)`：只产生 `candidate`，工具 trace 绑定稳定 `tool_call_id`，返回 `requires_user_confirmation=true`。
- `retrieve_coded_segments(code_ids, material_id?, query?, limit?)`：只读，返回 confirmed code、原始 quote、material/parse/segment/locator、plan_id 和 confidence。

Agent 指令明确：先读材料和代码本；不得把候选写成 confirmed；不得调用内部 API 代替用户决定。

## 状态、幂等与恢复

```text
candidate --用户逐项确认--> applied
candidate --部分确认--> partially_applied
candidate --全部拒绝--> rejected
applied/partially_applied --用户撤回--> revoked
```

- plan proposal 以 Agent provenance 派生的写入身份幂等；重复 tool call 返回相同 plan。
- decision 以 `Idempotency-Key + request hash` 幂等；同 key 不同 payload 返回 409。
- plan version 使用 CAS；旧界面提交返回 stale version，不覆盖新决定。
- 应用前重新读取 source segment；parse、hash 或 quote 任何一项漂移都拒绝整次确认，保留 candidate 供用户回到原文重提。
- 确认过程先完成全部输入校验，再逐项写 annotation/code/audit；中途进程中断后，annotation 幂等键和 plan 状态允许安全重试。
- 已确认代码只追加 annotation，不删除或改写既有片段；撤销只释放本计划新增的 code→annotation 关系，保留原代码、原文标记和审计记录。

## 审计与重放

`research_analysis_audit_events` 为 append-only 任务事件表，记录 `actor/action/entity refs/idempotency_key/provenance/payload/created_at`。当前动作包括 `coding_plan.proposed`、`coding_plan.decided`、`coding_item.applied`、`coding_item.rejected`。审计只暴露当前用户任务范围；原文仍从 immutable parse 重新读取。

## 数据库迁移

迁移 `20260904_0246_agent_coding_tools` 新增：

- `research_analysis_coding_plans`：plan 元数据和 item JSON、CAS version、决定时间与 Agent provenance。
- `research_analysis_audit_events`：任务隔离的 append-only 事件及 JSON provenance/payload。

现有 `research_analysis_annotations`、`research_analysis_codes`、代码本表不改结构，避免与人工工作台建立第二套事实来源。

## 前端反馈

在 `ResearchAnalysisWorkspace` 的候选区，plan 卡片显示原文 quote、页码/章节/字符范围、目标代码、置信度和理由。用户必须先填“判断依据”，再对每项点击“确认此项”或“拒绝此项”；最后一项决定后调用现有分析 API，成功通知“原文标记已回写”，刷新后由原有三栏检查器显示 confirmed code 与片段。失败会保留卡片、清除提交状态并展示错误，可重新核对后重试。

## 验证策略

- 后端：plan source/codebook snapshot、confirmed/rejected item、CAS stale、幂等重放、source hash drift、检索原文与审计事件。
- SQLite：迁移 head、plan/audit JSON round-trip、confirmed code annotation append。
- Agent：工具注册、candidate 与 read-only 分界、provenance 绑定、禁止 decision 工具。
- 前端：候选卡片的 reason gate、逐项按钮和完整 decision payload；TypeScript build。

不运行与本次边界无关的全量门禁；部署后的真实浏览器验收另按 Issue #246 交付流程执行。
