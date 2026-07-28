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
