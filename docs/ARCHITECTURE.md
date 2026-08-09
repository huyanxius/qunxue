# 工程架构

本文说明正式工程的模块边界、依赖方向和常见改动入口。产品定位与竞赛事实以 [`product/README.md`](product/README.md) 为准；本文不扩展产品范围。

## 当前可运行链路

```text
React
→ 产品模块公共入口
→ OpenAPI 生成客户端
→ FastAPI
→ research_intake / knowledge_catalog
→ repository port
→ SQLite
```

真实完成的是健康检查、账号会话、研究任务与现象确认，以及知识发布、搜索、详情和来源浏览。`theory_matching`、`research_framework` 目前主要提供公共类型、冻结路由契约和人工门禁规则；前端对应页面仍为占位，后端对应接口仍返回 501，不代表 M4/M5 已经实现。

## 后端

后端是模块化单体。业务规则留在所属模块，技术实现放在外层，通过公共端口连接。

| 目录 | 职责 | 当前状态 |
| --- | --- | --- |
| `modules/identity/` | 账号身份、密码与会话边界 | 注册、登录、会话恢复已实现 |
| `modules/research_intake/` | 研究任务、入口输入、现象候选与确认边界 | 创建、恢复、材料输入与现象确认已实现 |
| `modules/knowledge_catalog/` | 版本化知识发布、来源、关系与理论身份 | 发布、列表、搜索、详情与来源浏览已实现 |
| `modules/theory_matching/` | 候选理论判断、证据交接与用户决定 | 公共契约和门禁规则 |
| `modules/research_framework/` | 研究框架草拟、审校、修订与确认 | 公共契约 |
| `application/` | 通过模块公共入口编排跨模块流程 | 契约编排骨架 |
| `api/` | HTTP DTO、路由、依赖与异常映射 | 健康、账号、研究任务、现象与知识接口；M4/M5 为 501 契约 |
| `adapters/` | 数据库、模型、检索等端口实现 | SQLite 仓储、Markdown 知识解析、deterministic Mock 与 OpenAI-compatible 模型 Provider |
| `bootstrap.py` | 创建应用并装配具体实现 | 唯一装配入口 |

业务模块之间的依赖是单向的：

```text
knowledge_catalog       research_intake
          ↘              ↙
           theory_matching
                  ↓
          research_framework
```

- `knowledge_catalog` 和 `research_intake` 不依赖其他业务模块。
- `identity` 独立管理账号与会话，不承载研究或知识规则。
- `theory_matching` 只依赖前两者公开的不可变快照。
- `research_framework` 只依赖 `theory_matching` 的已确认结果。
- `application`、`api` 和 `adapters` 只能从 `modules/<name>/__init__.py` 使用业务能力。
- 业务模块不得依赖 FastAPI、Pydantic、SQLAlchemy 或具体模型 SDK。
- 具体数据库、模型和检索实现只能在 adapter 中创建，并由 `bootstrap.py` 装配。

`application/ResearchJourney` 目前用于验证模块接力契约，不是已经接通 API 和持久化的完整主链。路由不得手工构造“已确认”快照来跳过所属模块的确认流程。

## 前端

前端按产品任务组织：

```text
app → module public API → module adapter → generated API
```

| 目录 | 职责 |
| --- | --- |
| `src/app/` | Provider、路由适配和页面组合 |
| `src/modules/account/` | 注册、登录、会话状态与“我的研究” |
| `src/modules/socio-match-workspace/` | 研究任务创建、恢复和工作区 |
| `src/modules/knowledge-explorer/` | 知识发布浏览、搜索、详情和来源展示 |
| `src/api/` | 通用 HTTP 配置、系统接口和生成客户端 |
| `src/api/generated/` | 从 OpenAPI 生成的传输代码 |

- 外部调用只从 `modules/<name>/index.ts` 导入，模块内部文件默认私有。
- `app` 持有路由参数和页面导航；产品模块通过 props、callback 和稳定模型接收数据。
- 生成 DTO 在模块 adapter 中转换后再交给组件，不作为产品模块公共类型。
- 远端数据由 TanStack Query 管理；可分享、可恢复的筛选和选中状态放进 URL；临时展示状态留在组件。
- 业务代码不得裸调用 `fetch`、引入另一套 HTTP 客户端或直接调用模型 SDK。

`knowledge-explorer` 已通过生成 SDK 接入 `/knowledge` 与 `/knowledge/:knowledge_id`，使用当前知识发布提供列表、搜索、详情与来源。`/research/:task_id/match` 与 `/research/:task_id/framework` 仍由 `app` 提供占位页。

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
make check
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
