# 研究材料上传与检索能力补齐记录

## 文档目的

本文先记录群学致知研究材料链路的原始差距，再记录本轮 P0/P1/P2 最小闭环的实现结果和仍需按规模触发的工程化边界。

核验基线：`fix/main-stabilization`，`ae36f4a`；实现日期：2026-09-05。

## 目录

- [结论](#结论)
- [当前完整链路](#当前完整链路)
- [已具备能力](#已具备能力)
- [当前 API 边界](#当前-api-边界)
- [主要不足](#主要不足)
- [最小补齐方案](#最小补齐方案)
- [建议的数据与状态边界](#建议的数据与状态边界)
- [验收标准](#验收标准)
- [当前源码依据](#当前源码依据)

## 结论

当前已形成可用闭环：聊天输入框可以直接上传或从任务材料库选择附件；Agent run 会固化本轮 `(material_id, parse_id)`；材料库和 Agent 共用任务级 SQLite FTS5 索引；文档上传可以进入有租约、尝试次数、退避和失败原因的持久摄取任务，并由最多两个本地 Worker 后台处理和启动恢复。每次重试使用新的 `parse_id`，完成和失败写入都以 attempt/parse 双重 fencing 防止过期 Worker 覆盖新任务。

扫描 PDF 和音视频的能力边界也已显式化：没有可提取文字的 PDF 返回 `ocr_required`；未转写媒体按 Provider 配置返回 `transcription_required` 或 `transcription_unavailable`，不会伪装成可检索。当前没有内置 OCR Provider；对象存储、断点续传和大批量配额仍按真实规模触发，不在本轮 SQLite 单实例闭环中引入。

## 当前完整链路

```text
研究任务材料面板
  -> multipart 上传
  -> 读取受限大小的完整文件
  -> SQLite 保存原始 blob
  -> 持久 ingestion job（queued / processing / ready / failed）
  -> 最多两个本地 Worker 解析并由租约支持启动恢复
  -> 音视频等待既有转写 Provider 或人工导入
  -> 保存不可变 parse version 和稳定 segment locator
  -> SQLite FTS5 持久索引 material + parse + segment + locator
  -> 材料库跨文件检索并跳转到精确原文
  -> Agent 按用户 + 任务 + 本轮固化附件范围复用同一索引
  -> 返回 material_id + parse_id + segment_id + locator 引用
```

## 已具备能力

### 上传和材料生命周期

| 能力 | 当前实现 | 状态 |
| --- | --- | --- |
| 任务级上传 | `POST /api/research-tasks/{task_id}/materials` | 已具备 |
| 格式识别 | PDF、DOCX、TXT、Markdown、MP3、M4A、WAV、MP4、WebM | 已具备 |
| 大小限制 | 文档 25 MB；音视频 100 MB | 已具备 |
| 原文件保存 | SQLite `research_material_blobs` 保存二进制和 hash | 已具备，适合当前单实例阶段 |
| 文档解析 | PDF、DOCX、TXT、Markdown 确定性解析 | 已具备 |
| 音视频处理 | 先保存原文件，之后调用既有转写 Provider、人工导入或校正 | 已具备入口；Provider 依赖配置 |
| 解析版本 | 不可变 parse version；成功后才切换 current pointer | 已具备 |
| 定位信息 | 保存页码、章节、字符范围等可证明位置 | 已具备 |
| 重解析 | 有幂等请求和版本冲突保护 | 已具备 |
| 删除 | 用户、任务归属校验后删除 | 已具备 |
| 摄取任务 | 持久 job、租约、尝试次数、退避、attempt fencing、启动恢复、2 Worker 上限 | 已具备 |
| OCR 边界 | 扫描 PDF 标记 `ocr_required` | 状态已具备；OCR Provider 尚未内置 |

### 当前“检索”能力的三个层次

| 名称 | 实际能力 | 不能代表什么 |
| --- | --- | --- |
| 阅读器“在材料中查找” | 对当前已打开材料的已加载分段做前端字符串包含匹配 | 不是跨材料检索，也没有服务端排序 |
| “检索编码片段” | 按已有 annotation/code 关系回查已经编码的原文 | 不是对全部原始材料进行全文或语义搜索 |
| 材料库跨文件检索 | 调用任务级 `/materials/search`，返回精确 parse/segment/locator 并跳转原文 | 当前为 SQLite FTS5 lexical 检索，不宣称语义召回 |
| Agent `search_research_materials` | 复用任务级持久索引；有附件时严格限定固化 parse 快照 | 当前为 lexical；后续可在同一服务之上增加 embedding/reranker |

## 当前 API 边界

研究材料路由目前提供：

- 上传材料。
- 列出当前任务材料。
- 获取材料元数据、原文件内容和指定分段。
- 重解析。
- 删除。
- `GET /materials/search` 跨文件全文检索。
- `GET /materials/{material_id}/ingestion` 摄取状态查询。
- 上传表单的 `defer_processing` 后台摄取开关；当前前端显式启用。

仍未提供的规模化能力：

- 按标题、类型、状态、日期、正文关键词组合筛选的分页契约。
- 分块/断点续传、对象存储直传和用户总配额。
- 内置 OCR Provider；当前只提供稳定的不可用原因。

## 实施前主要不足（现已按下述方案处理）

### 1. 聊天附件只有菜单文案，没有附件语义

聊天输入框中的“上传文件”“从研究材料添加”“引用文件”三个菜单项都调用 `openResearchMaterials()`。该函数只打开研究材料面板，或跳转到 `/research/materials`。

发送 Agent turn 时，请求只携带消息、工作区、任务、文档、章节和深度研究字段，没有本轮选择的材料 ID。因此系统无法表达：

- 这一轮只参考某几份材料。
- 上传完成后自动附加到尚未发送的消息。
- 在输入框中显示、移除或重试某个附件。
- 区分“任务材料库可检索”和“本轮明确引用”。

### 2. 材料库没有用户可操作的跨文件搜索

`MaterialLibraryView` 只负责上传、材料类型选择、列表展示、打开、重试和删除。当前没有搜索框、筛选状态或服务端搜索请求。

阅读器中的查找只过滤当前已加载的分段：

```ts
segments.filter((segment) =>
  `${segment.text} ${formatMaterialLocator(segment.locator)}`
    .toLocaleLowerCase()
    .includes(normalizedReaderQuery),
)
```

材料较多时，用户无法从整个任务中查找一个概念并直接跳回命中位置。

### 3. Agent 检索每次重建个人材料候选集

`search_research_materials` 每次调用都会：

1. 最多列出当前任务的 500 份材料。
2. 读取每份 ready 材料的当前 parse。
3. 把全部合法分段临时转换为 retrieval chunks。
4. 若配置了 embedding，则重新计算查询向量和全部文档向量。
5. 执行 lexical/semantic 融合和 rerank。

这一实现保留了严格授权和当前版本一致性，适合小规模任务，但材料或分段数量增长后会产生明显的重复数据库读取、网络 embedding 成本和延迟。

### 4. 上传和解析是同步、内存型流程

上传路由使用 `await file.read(limit + 1)` 将单份文件完整读入内存；文档解析在同一个请求内同步完成。初始多文件上传在前端逐份串行执行。

因此当前缺少：

- 分块或直传式上传。
- 可取消、可恢复或断点续传。
- 独立的 `uploaded -> parsing -> indexing -> ready/failed` 后台任务。
- Worker 崩溃后的任务恢复和超时处理。
- 多文件受控并发与总大小限制。

### 5. OCR 和音视频文本化不完整

当前文档解析器明确不提供 OCR。扫描 PDF 即使文件有效，也可能没有可提取文本。

音视频格式可以上传并持久保存，但上传本身不会产生可检索正文。需要转写 Provider、转写导入或研究者校正后，才会生成第一个文本 parse。

### 6. 缺少统一的检索服务和质量验收

公共知识库已有持久检索索引和评估资产，个人材料则由 Agent 工具临时检索；用户界面又使用独立的前端字符串查找。三条路径没有共享同一个任务级检索服务。

当前还需要补充：

- 任务材料搜索的排序、去重和命中高亮契约。
- lexical-only 降级时的明确状态。
- 索引身份与 `parse_id`、内容 hash 的一致性检查。
- 针对个人材料的检索评估集和回归指标。
- 删除、重解析、撤销外部模型授权后的索引清理验证。

## 最小补齐方案

### P0：完成聊天附件闭环

1. 将三个菜单动作拆开：直接上传、从任务材料选择、本地引用/附件管理。
2. 在 composer 中显示待发送附件，支持移除、失败重试和上传进度。
3. 为 Agent turn 契约增加显式附件集合 `material_ids`，并冻结其语义：
   - 未提供或提供空集合时，本轮不向 Agent 暴露任何个人材料。
   - 提供非空集合时，当前轮只能在指定材料范围检索；最多 20 份，去重后保持用户选择顺序。
   - 每份附件必须属于当前用户和任务，处于 `ready`，并在 run 创建前固化当时的 `parse_id`。
4. 后端在开始 run 前验证所有附件属于当前用户和任务，并绑定当时的 `parse_id`。
5. 引用继续返回 `material_id`、`parse_id`、`segment_id` 和 locator，保证能回到原文。

### P1：增加任务级搜索 API 和持久文本索引

建立一个由用户界面和 Agent 共同调用的 `ResearchMaterialSearchService`：

- 输入：用户、任务、查询、材料过滤条件、分页或 limit。
- 输出：标题、摘要、高亮、分数、`material_id`、`parse_id`、`segment_id`、locator。
- 授权：在进入检索候选集前完成用户和任务过滤。
- 默认索引：先用 SQLite FTS5 覆盖当前 parse blocks，不立即引入新的向量数据库。
- 索引更新：上传解析成功、重解析切换 current pointer、删除材料时事务性更新。
- Agent：复用同一搜索服务，再按配置增加 embedding 和 reranker。

持久索引必须绑定 `parse_id` 和内容 hash，不能让旧解析版本的命中伪装成当前材料。

### P2：增强摄取可靠性

本轮已增加独立 ingestion job、本地 Worker、租约、重试退避、attempt fencing、启动恢复，以及文档解析和索引的后台状态。仍按真实规模触发的后续项包括：

- 流式写入对象存储或文件存储，SQLite 只保存元数据。
- 扫描 PDF 的内置 OCR Provider；当前返回稳定的 `ocr_required`。
- 音视频转写、说话人信息和人工校正版本。
- 大批量上传的并发、总配额和生命周期清理。

当前没有为了单实例规模提前引入 Celery、对象存储或向量数据库。

## 建议的数据与状态边界

```text
ResearchMaterial
  -> 原始文件身份与任务归属

MaterialParseVersion
  -> 不可变文本、结构、parser identity、content hash

MaterialSearchDocument
  -> 只索引一个 material 的 current parse blocks
  -> parse_id + segment_id + locator

AgentTurnAttachment
  -> conversation_id + run_id/turn_id + material_id + parse_id
  -> 表达本轮明确引用，不替代任务材料库
```

轮次附件的检索语义固定如下：未提供或空集合表示本轮不使用个人材料；非空集合表示严格限制到固化的 `(material_id, parse_id)` 快照。幂等重试和深入研究续跑必须复用首次 run 保存的快照，不能因材料后来重解析而静默扩大或漂移检索范围；即使当前材料正在重解析，已固化且仍获授权的历史快照仍可读取。

“材料已上传”“材料可阅读”“材料已进入搜索索引”“材料已附加到本轮对话”是四个不同状态，不应继续由一个按钮或一个 `ready` 标签隐式表示。

## 验收标准

- [x] 用户能从聊天输入框直接上传文件，并看到等待解析、处理中、可用或不可用原因。
- [x] 用户能从任务材料库选择一份或多份材料附加到本轮消息，也能在发送前移除。
- [x] Agent 只能读取当前用户、当前任务和允许的附件/材料范围。
- [x] 用户能在整个任务材料库搜索正文，并从结果跳到准确原文位置。
- [x] 相同材料的重复查询复用 FTS5 文档，不重新计算全部文档 embedding。
- [x] 重解析后默认只检索新的 current parse；旧引用和 Agent run 快照仍能按历史 `parse_id` 审计。
- [x] 删除材料或撤销外部模型授权后，后续 Agent 检索不会返回对应内容。
- [x] 扫描 PDF 和未转写音视频显示明确的不可检索原因，不伪装为 ready。
- [x] 上传、摄取、索引、搜索和引用已有覆盖授权、失败、幂等、租约恢复和版本漂移的自动测试。

## 当前源码依据

- `frontend/src/app/agent/ResearchAgentConversationPage.tsx`：材料菜单和 Agent turn 请求。
- `frontend/src/modules/research-materials/MaterialLibraryView.tsx`：材料库上传与列表界面。
- `frontend/src/modules/research-materials/ResearchMaterialsPanel.tsx`：单份材料阅读器内查找。
- `frontend/src/modules/research-materials/CodedDocumentWorkbench.tsx`：已编码片段回查。
- `frontend/src/modules/research-materials/initialResearchMaterials.ts`：初始多文件串行上传。
- `backend/src/qunxue_api/api/routes/research_materials.py`：上传限制和材料 API。
- `backend/src/qunxue_api/application/research_materials.py`：同步解析、任务授权和版本切换。
- `backend/src/qunxue_api/modules/research_materials/domain.py`：支持格式、parse 和 locator 契约。
- `backend/src/qunxue_api/adapters/research_materials/parser.py`：PDF、DOCX、文本解析和 no-OCR 边界。
- `backend/src/qunxue_api/adapters/sqlite/research_material_model.py`：blob、parse version 和 block 持久化。
- `backend/src/qunxue_api/adapters/sqlite/research_material_search.py`：任务授权前置的 FTS5 查询与精确坐标返回。
- `backend/migrations/versions/20260904_0330_material_ingestion_jobs.py`：可恢复摄取任务、租约和失败信息。
- `backend/src/qunxue_api/adapters/research_agent/document_tools.py`：Agent 任务材料检索和引用。
- `backend/src/qunxue_api/adapters/retrieval/hybrid.py`：临时 chunks 的 lexical、embedding、RRF 和 rerank。
