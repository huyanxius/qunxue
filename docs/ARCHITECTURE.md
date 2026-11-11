# 工程架构

本文说明正式工程的模块边界、依赖方向和常见改动入口。产品定位与竞赛事实以 [`product/README.md`](product/README.md) 为准；本文不扩展产品范围。

## 当前可运行链路

```text
React
→ 产品模块公共入口与 adapter
→ OpenAPI 生成客户端 → FastAPI
→ 应用用例与业务模块 → 仓储等端口
→ SQLite 等具体实现
```

现有链路包括健康检查、账号会话、研究任务创建与恢复、现象确认，以及知识发布、搜索、详情和来源浏览。研究工作区通过以下入口接续理论判断和文档交付。

- **M4 理论判断**从 `POST /api/research-tasks/{task_id}/match-runs` 启动匹配。`TheoryMatchingApplication` 编排用例，`TheoryMatchingService` 处理候选判断，`SqliteMatchRunRepository` 保存匹配运行和决定。用户在理论工作台选择候选，通过 `POST /api/decision-sets/{decision_set_id}/confirm` 确认正式理论方案。`POST /api/match-runs/{match_run_id}/defer` 仍返回 `501`。
- **M5 研究文档**以已确认的理论方案为输入，从任务下的 `research-documents` 入口创建或恢复文档。`ResearchDocumentApplication` 编排 `ResearchDocumentService` 和 SQLite 仓储，保存文档标识、版本和修订提案。文稿工作台提供编辑、版本查看与恢复、提案处理、完成门禁、确认及 Markdown 导出。

## 后端

后端是模块化单体。业务规则留在所属模块，技术实现放在外层，通过公共端口连接。

| 目录 | 职责 |
| --- | --- |
| `application/` | 通过模块公共入口编排跨模块用例，如理论匹配、研究文档和材料分析 |
| `api/` | HTTP DTO、路由、依赖与异常映射 |
| `adapters/` | SQLite 仓储、Markdown 知识解析、模型与检索端口的具体实现 |
| `bootstrap.py` | 创建应用并装配路由、用例和具体实现 |
| `retrieval_preflight.py` | 仅依赖 `settings`，只读检查检索模型配置与索引元数据 |

### 业务模块允许依赖

下表按发起导入的模块列出允许依赖的其他业务模块，`—` 表示该模块独立。允许导入的符号由 [`test_architecture.py`](../backend/tests/test_architecture.py) 登记。

| 模块 | 允许依赖 | 职责 |
| --- | --- | --- |
| `modules/account_management/` | `identity` | 账号设置、管理与二次使用授权 |
| `modules/agent_conversation/` | — | 对话、轮次、运行与引用 |
| `modules/agent_memory/` | — | 记忆候选、作用域与上下文预算 |
| `modules/billing/` | — | Credits 账本、兑换与模型调用计量 |
| `modules/frontier_knowledge/` | — | 前沿资料采集、核验、研读与简报 |
| `modules/identity/` | — | 账号身份、密码与会话 |
| `modules/knowledge_catalog/` | — | 版本化知识发布、来源、关系与理论身份 |
| `modules/research_analysis/` | `research_materials` | 标注、编码、比较发现与分析交接 |
| `modules/research_cycle/` | `research_analysis`, `research_materials`, `theory_matching` | 研究证据汇总、报告覆盖与缺口提示 |
| `modules/research_exchange/` | — | 研究项目归档、交换与审计 |
| `modules/research_framework/` | `theory_matching` | 版本化研究文档、修订提案与确认规则 |
| `modules/research_intake/` | — | 研究任务、入口输入、现象候选与确认 |
| `modules/research_materials/` | — | 研究材料、解析、片段定位与材料归档 |
| `modules/research_method/` | — | 研究方法方案、约束、审查与确认 |
| `modules/shared_knowledge/` | — | 课程资料集合、成员关系与共享边界 |
| `modules/teaching_assistant/` | — | 课堂活动、分组、提交与反馈 |
| `modules/theory_matching/` | `knowledge_catalog`, `research_intake` | 证据交接、候选判断与用户理论决定 |
| `modules/transcription/` | — | 音视频转录、文本导入与版本 |

- 跨模块和外层调用都从 `modules/<name>/__init__.py` 使用公共能力，传递稳定 ID、版本和不可变快照。
- 业务模块不得依赖 FastAPI、Pydantic、SQLAlchemy 或具体模型 SDK。
- 数据库、模型和检索的具体实现位于 `adapters/`，由 `bootstrap.py` 装配。

`ResearchJourney` 用于验证模块接力契约。`create_app()` 默认将它留空，只有显式传入 `journey_dependencies` 才会装配这条骨架。当前 API 通过各自的应用用例编排持久化流程，由所属模块执行确认。

### 退役的框架 API

[`frameworks.py`](../backend/src/qunxue_api/api/routes/frameworks.py) 保留旧路由的兼容响应。满足鉴权和参数校验的请求返回 `410 Gone`，并通过 `Link` 的 `successor-version` 指向 `/api/research-tasks/{task_id}/research-documents`。已知任务 ID 的调用方可从这个入口查找 `document_id`，再进入版本化文档流程。

| 退役操作（410） | 替代入口 | 迁移说明 |
| --- | --- | --- |
| `POST /api/research-tasks/{task_id}/frameworks` | `POST /api/research-tasks/{task_id}/research-documents` | 用已确认的理论方案创建研究文档 |
| `GET /api/frameworks/{framework_id}` | `GET /api/research-documents/{document_id}` | 从任务的文档列表定位 `document_id`，可按版本读取 |
| `PATCH /api/frameworks/{framework_id}` | `PATCH /api/research-documents/{document_id}` | 以当前版本为前提提交文档修改 |
| `POST /api/frameworks/{framework_id}/reviews` | `GET /api/research-documents/{document_id}/completion-gate` | 先检查文档的待完成条件，在工作台查看修订提案 |
| `GET /api/frameworks/{framework_id}/reviews/{review_run_id}` | `GET /api/research-documents/{document_id}/completion-gate`, `GET /api/research-documents/{document_id}/proposals` | 按文档查询完成状态与提案，旧审校运行 ID 只用于识别退役请求 |
| `POST /api/frameworks/{framework_id}/reviews/{review_run_id}/retry` | `GET /api/research-documents/{document_id}/completion-gate` | 修订文档后重新查询完成状态 |
| `POST /api/frameworks/{framework_id}/audit-resolutions` | `POST /api/research-document-proposals/{proposal_id}/accept`, `POST /api/research-document-proposals/{proposal_id}/reject` | 逐条接受或拒绝修订提案 |
| `POST /api/frameworks/{framework_id}/confirm` | `POST /api/research-documents/{document_id}/confirm` | 完成门禁通过后确认当前版本 |
| `GET /api/frameworks/{framework_id}/export` | `GET /api/research-documents/{document_id}/export` | 导出满足交付条件的文档及其 manifest |

确认已知调用方都已迁移后，再单独评估删除兼容路由。删除时同时更新 OpenAPI、生成客户端和退役表。新增或变更模块依赖、退役操作时，在仓库根目录运行 `python3 tools/check_architecture_docs.py`。CI 将这两张表与架构登记和 OpenAPI 对照，也会检查替代操作仍在契约中且未标为退役。

## 前端

前端按产品任务组织：

```text
app → module public API → module adapter → generated API
```

| 目录 | 职责 |
| --- | --- |
| `src/app/` | Provider、路由适配和页面组合 |
| `src/modules/account/` | 注册、登录、会话状态与“我的研究” |
| `src/modules/socio-match-workspace/` | 研究任务创建、恢复与导航 |
| `src/modules/research-document/` | 理论决定、版本化文档与提案的客户端适配 |
| `src/modules/knowledge-explorer/` | 知识发布浏览、搜索、详情和来源展示 |
| `src/api/` | 通用 HTTP 配置、系统接口和生成客户端 |
| `src/api/generated/` | 从 OpenAPI 生成的传输代码 |

- 外部调用只从 `modules/<name>/index.ts` 导入，模块内部文件默认私有。
- `app` 持有路由参数和页面导航；产品模块通过 props、callback 和稳定模型接收数据。
- 生成 DTO 在模块 adapter 中转换后再交给组件，不作为产品模块公共类型。
- 远端数据由 TanStack Query 管理；可分享、可恢复的筛选和选中状态放进 URL；临时展示状态留在组件。
- 业务代码不得裸调用 `fetch`、引入另一套 HTTP 客户端或直接调用模型 SDK。

`knowledge-explorer` 通过生成 SDK 为 `/knowledge` 与 `/knowledge/:knowledge_id` 提供当前知识发布的列表、搜索、详情与来源。`/research/:task_id/workspace/theory` 和 `/research/:task_id/workspace/writing` 由 `ResearchProjectWorkspacePage` 装载理论与文稿工作台。旧页面路径 `/research/:task_id/match` 与 `/research/:task_id/framework` 分别重定向到这两个入口。

## 契约生成

API 契约只有一个方向：

```text
Pydantic DTO / FastAPI route
→ backend/openapi.json
→ frontend/src/api/generated/
```

修改接口后执行：

```bash
make contract
git diff -- backend/openapi.json frontend/src/api/generated
```

不要手改生成文件，也不要先改前端 DTO 再要求后端迁就。生成结果发生变化时，应与触发它的后端契约改动一同提交。

## 改动放在哪里

| 需求 | 首要目录 |
| --- | --- |
| 研究任务或现象确认规则 | `backend/src/qunxue_api/modules/research_intake/` |
| 知识条目、来源或版本契约 | `backend/src/qunxue_api/modules/knowledge_catalog/` |
| 候选理论和确认门禁 | `backend/src/qunxue_api/modules/theory_matching/` |
| 研究框架规则 | `backend/src/qunxue_api/modules/research_framework/` |
| 跨模块用例 | `backend/src/qunxue_api/application/` |
| HTTP 契约和路由 | `backend/src/qunxue_api/api/` |
| 数据库或外部服务实现 | `backend/src/qunxue_api/adapters/` |
| 页面路由和组合 | `frontend/src/app/` |
| 产品交互与模块模型 | `frontend/src/modules/<name>/` |

新增业务模块时，先确定它拥有的数据和规则，再建立公共入口、允许依赖和架构测试。不要先建一个 `utils`、`common` 或共享 DTO 目录来暂存尚未归属的业务概念。
