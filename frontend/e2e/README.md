# 端到端测试（Playwright）

覆盖研究任务的关键链路：**创建 → 进入 `/research/:id` → 客户端跳转到阶段路由 → 刷新后恢复同一任务与输入**。

## 运行

一条命令（在仓库根目录）：

```bash
make e2e
```

`make e2e` 会通过 Playwright 自动启动：

- 后端：`backend/scripts/serve_e2e.py`，确定性 Mock 运行时，关闭邮箱验证码，使用每次启动都重建的一次性 SQLite（`backend/var/e2e.db`）；
- 前端：Vite dev server，`/api` 反代到上面的后端，浏览器只与一个源通信。

首次运行前需要安装一次浏览器：

```bash
cd frontend && npx playwright install chromium
```

## 结构

- `global-setup.ts`：只通过真实 HTTP API 造数——注册用户、创建研究任务、提交直接输入并抽取现象候选，然后把会话 `storage-state.json` 和 `seed.json` 写入 `.artifacts/`。浏览器用例只验证用户可见的路由与刷新恢复。
- `research-flow.spec.ts`：加载会话状态，打开裸任务地址，断言跳转到 `/research/:id/phenomenon`、任务标识与现象输入可见，刷新后仍一致。

## 约束

- 仅 Chromium，单 worker；`trace` 只在失败重试时保留（`test-results/`、`playwright-report/`）。
- 不依赖固定 ID、执行顺序或开发者本地数据；每次运行都是全新用户、全新任务、全新数据库。
- 不覆盖知识库、理论候选与模型流程。
