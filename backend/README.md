# 群学致知 API

当前真实端点：

- `GET /api/health`
- `POST /api/research-tasks`
- `GET /api/research-tasks/{task_id}`

后端采用模块化单体。API 与 SQLite adapter 只从业务模块公共入口导入；`application/ResearchJourney` 只负责跨模块编排。架构测试会阻止深层导入、反向依赖以及业务模块直引 Web、ORM 或具体模型 SDK。

```bash
uv sync
uv run alembic upgrade head
uv run uvicorn qunxue_api.main:app --reload
```

SQLite 仅用于单实例、单 worker、本地非敏感演示。

## 群学前沿（本地验收，默认不采集、不调用模型）

详见 [`docs/frontier.md`](docs/frontier.md)。读 API 真实读取 SQLite；不会自动退回静态种子。
默认 `make dev-api` 只迁移数据库，不自动导入资料。请使用单独的本地数据库导入验收语料，
不要把示例命令指向生产数据库。前沿模型与既有研究 Agent 的 API key 完全分离。
