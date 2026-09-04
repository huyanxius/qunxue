# AI 网关能力差距分析

## 当前结论（2026-09-05）

本分支已完成进程内 AI Gateway 稳定化实现：业务模型与 Agent 模型共用有序路由、重试、熔断、健康聚合和逐次尝试审计；`/api/health` 增加模型状态、最近检查时间和发布版本字段。

这仅是本地分支状态。当前改动**尚未部署、尚未推送、尚未创建 PR**；因此不能把它表述为生产环境已修复。此前对生产 SSH、PM2、Nginx 和旧健康响应的观察只说明当时部署的行为，不是本分支的部署验收。

本轮仍不把项目扩展为通用模型转售平台：不新增公开 OpenAI 兼容接口、开发者 Key、BYOK、支付或 Provider 管理后台。

## 已完成的能力

| 能力 | 本分支状态 | 行为边界 |
| --- | --- | --- |
| 统一路由 | 已完成 | 业务 `ModelGateway` 与 Agent 调用按 primary、fallback-1… 顺序复用同一执行器；不并发竞速或 hedge 已计费请求。 |
| 失败与熔断 | 已完成 | 仅连接/传输、超时、408/409/429/5xx 及既有的 transient `unknown provider for model` 进入 fallback；连续 3 次可重试失败开路，30 秒后只放行一个恢复请求。 |
| 尝试审计 | 已完成 | 每次真实上游请求写入 `model_route_attempts`；保留现有业务级 `model_invocations`。 |
| 配置 | 已完成 | `QUNXUE_MODEL_FALLBACKS` 为有序 JSON；每项要求 `base_url`、`api_key`，可选 `model`，未指定时继承主模型。URL 不得带凭证。 |
| 主动探活 | 已完成 | 真实运行时启动后异步探活一次，之后按 `QUNXUE_MODEL_PROBE_INTERVAL_SECONDS`（默认 300）循环；关停时取消并等待任务。mock 模式不发外网探活。 |
| 健康与版本 | 已完成 | 健康响应保留旧字段，并增加 `model_status`、`model_checked_at`、`release_revision`。部署时由 `QUNXUE_RELEASE_REVISION` 写入精确提交；本地占位值 `unreleased` 不是部署证明。 |

## 配置、迁移和健康语义

将 `.env.example` 的占位符复制到受保护的 `backend/.env` 或部署环境。真实模型至少需要主模型的 key/endpoint/model；备用端点可覆盖模型名。不要把任何真实密钥、带用户名或密码的 URL 放入仓库、日志、健康响应或审计表。

部署数据库必须在目标发布数据库上执行 `cd backend && uv run alembic upgrade head`。本轮迁移新增 `model_route_attempts`，其 revision 为 `20260905_0340`；升级前应先完成可恢复的数据库备份和现有迁移链检查。

公共 `model_status` 为 `unknown`、`healthy`、`degraded` 或 `unavailable`：mock 始终为 `healthy`；没有可用路由器的真实配置为 `unknown`；部分失败或内部恢复期对外为 `degraded`；所有真实端点都被熔断时为 `unavailable` 并返回 HTTP 503 的 `HealthResponse`。检索就绪失败仍沿用既有的 503 错误响应。`model_checked_at` 是最近一次探活或路由器报告的检查时间，不是对任意业务请求成功的承诺。

## 审计和敏感信息边界

`model_route_attempts` 仅保存关联标识（attempt/route/trace/request/task/agent run）、能力、端点 ID、provider、模型、次数、fallback/成功/选中标志、起止时间、时延、失败分类和可得的 token 计数。它不得保存提示词、私密材料正文、请求/响应 body、endpoint URL、header、cookie、API key 或其他凭证。排障应使用 `trace_id`、`route_id` 或 `agent_run_id` 关联，而不是扩大持久化内容。

## 仍缺与部署后验证

代码分支之外仍需要发布者完成以下操作：

1. 审核并推送本分支，创建 PR，等待 CI、代码审查和合并；本任务不执行这些外部动作。
2. 在变更窗口备份生产数据库，发布构建，并在真实运行环境设置准确的 `QUNXUE_RELEASE_REVISION`、模型配置和密钥。
3. 执行 Alembic 升级；如升级或应用启动失败，停止切流，回滚到已知可用版本，并依照本次迁移的 downgrade 策略恢复。不要通过删除审计表来掩盖失败。
4. 通过实际发布入口检查 `/api/health`：确认 `release_revision` 等于发布提交，验证正常、降级和全端点不可用时的状态/503 语义，并确认响应不含 URL 或凭证。
5. 在受控的非生产或低风险请求中验证一次主端点和一次允许的 fallback；核对每个真实上游调用恰有一条无敏感内容的 attempt 记录，并检查 SSE 事件和既有 `model_invocations` 行为未变。
6. 观察至少一个 probe 周期和一次应用关停/重启，确认无 mock 外网调用、无悬挂 probe 任务及无重复探活。

## 回滚

应用异常时先停止流量并回退应用到上一个已验证发布版本；保留数据库备份和审计证据。若必须回退迁移，使用受控的 Alembic downgrade，并先确认没有下游版本依赖新表。回滚后重新检查健康响应中的版本与模型状态，不能仅以 PM2 在线或 HTTP 200 作为模型可用的结论。
