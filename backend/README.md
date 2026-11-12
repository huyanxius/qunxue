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

## 管理员引导与账户运行

首次引导使用 `QUNXUE_ACCOUNT_INITIAL_ADMIN_EMAIL` 和
`QUNXUE_ACCOUNT_INITIAL_ADMIN_PASSWORD`；日常账户路由使用
`QUNXUE_ACCOUNT_SIGNING_KEY`，优先于初始密码。引导完成后可删除两项引导配置，
保留签名 key，重启仍从数据库读取原管理员及其积分豁免，不重置密码或重复引导。

旧配置未指定签名 key 时继续使用初始密码签名。迁移时将原签名值不变地移到
`QUNXUE_ACCOUNT_SIGNING_KEY`，保持密码重置链接和兑换码的幂等重放。
存量链接和兑换码仍按数据库摘要验证，不因配置分离失效；本次不提供 key 轮换机制。
回滚旧版代码时需恢复原引导配置及原签名值，不改数据库。实际生产配置由 Finn 处理。

## 群学前沿（本地验收，默认不采集、不调用模型）

详见 [`docs/frontier.md`](docs/frontier.md)。读 API 真实读取 SQLite；不会自动退回静态种子。
默认 `make dev-api` 只迁移数据库，不自动导入资料。请使用单独的本地数据库导入验收语料，
不要把示例命令指向生产数据库。前沿模型与既有研究 Agent 的 API key 完全分离。
