# 分发与运行边界

这份文档给第一次拿到仓库的人。它能把当前版本稳定地安装、启动和检查起来，但当前交付仍是单实例本地产品包，不是已经具备公网生产保障的 SaaS。

## 运行前提

- Python 3.12；
- Node.js 22.18 或更高版本；
- `uv`、`npm` 和 GNU Make；
- 一个可写的本地目录。

复制 [`../.env.example`](../.env.example) 后，只把需要的变量放入 `backend/.env` 或 `frontend/.env.local`。API key 只放在本机环境变量或未纳入版本控制的 `.env` 文件里。

## 从零启动

```bash
git clone https://github.com/huyanxius/qunxue.git
cd qunxue
make bootstrap
```

启动 API 和 Web（各占一个终端）：

```bash
make dev-api
make dev-web
```

浏览器打开 <http://localhost:5173>。API 启动时会先执行 Alembic 迁移；手动启动 API 前也可以运行：

```bash
cd backend && uv run alembic upgrade head
```

## 先确认运行状态

```bash
curl --fail http://127.0.0.1:8000/api/health
```

健康响应中的 `runtime_mode`、`capability`、`persistence` 和 `knowledge_release_id` 是服务配置与当前知识发布的事实来源；独立 Agent 请求还要以该请求的 provider、运行记录和引用版本为准。页面上的对话、检索或知识条目不应被解读为超出这些证据的能力承诺。

| 配置 | 含义 | 可以对外怎么说 |
| --- | --- | --- |
| `QUNXUE_RUNTIME_MODE=mock` | 模型网关的确定性本地运行器（不代表独立 Agent provider） | 可演示界面和流程；模型网关不是真实模型结果 |
| `QUNXUE_RUNTIME_MODE=base` | OpenAI-compatible 模型 | 只有健康检查、真实请求和引用链都通过后，才能称为真实模型运行 |
| `QUNXUE_RUNTIME_MODE=sft` | 带受控资源标识的兼容模型 | 需额外验证资源权限、模型版本和审计记录 |

对于 `QUNXUE_RUNTIME_MODE=base` 或 `sft`，`QUNXUE_MODEL_BASE_URL` 与 `QUNXUE_MODEL_NAME` 是必填项，缺少时应用应启动失败。当前零配置路径由模型网关明确使用确定性 mock；健康接口只证明这层配置。独立 Agent 可能按自身配置选择兼容 Provider，即使健康响应仍显示 `mock`，也必须从该次运行记录中的 provider、模型名、引用链和发布版本逐项确认，不能用 API key 或健康响应推断真实模型已接通。

## 数据、备份与升级

默认数据库是 `backend/var/qunxue.db`，适用于单实例、单 worker 的本地或内网使用。当前版本没有提供多 worker 锁协调、自动备份、在线升级、回滚、对象存储或灾备能力。

发布一个内部可复现包前：

1. 停止 API 进程；
2. 复制数据库文件到受保护的备份目录，并一并保留当前代码版本和环境变量清单（不保存密钥明文）；
3. 在副本上执行 `make bootstrap` 和迁移；
4. 运行健康检查与定向浏览器冒烟；
5. 失败时恢复数据库副本和上一版本代码，不在原文件上试验性回滚。

不要把 SQLite 文件、日志、cookie、API key 或模型响应中的敏感材料提交到仓库或公共制品。

## 发布前最小验收

```bash
make check
git status --short
curl --fail http://127.0.0.1:8000/api/health
```

浏览器至少走完：注册/登录、刷新后恢复会话、创建研究输入、回到“我的研究”继续、打开知识条目并核对来源版本、断开 API 后看到可恢复的错误状态。`make check` 通过并不等于真实模型、理论匹配、研究框架或导出能力已经交付。

## 已知产品边界

当前可用的是站点壳、账号与研究恢复、研究输入/现象确认和知识浏览。`/agent` 仍是界面预览；新研究页中的 Agent 也只有在真实 provider 运行记录、引用链和发布版本同时存在时，才能按真实结果验收。M4 理论匹配与用户决定、M5 研究框架、可追溯导出和真实模型全链路仍分别由独立 Issue/PR 交付；占位路由、mock 数据和契约类型不能替代这些能力。

如果目标是公网生产服务，还需要单独完成反向代理与 TLS、进程托管、受支持的生产数据库、密钥管理、备份监控、速率限制、审计保留和灾备演练。本仓库当前没有把这些能力伪装成已完成。

## 常见故障

- **页面出现 Vite overlay 或找不到模块**：在 `frontend` 目录重新执行 `npm ci`，确认 lockfile 与代码来自同一版本；不要手删依赖来绕过错误。
- **健康检查是 `runtime_mode=mock`**：这是默认且诚实的零配置状态。需要真实模型时按上面的变量配置并重新启动 API。
- **浏览器收到 401**：先确认 API 与浏览器使用同一主机名（`localhost` 与 `127.0.0.1` 不要混用），再检查 cookie 和 CORS 配置。
- **数据库迁移失败**：停止旧进程，备份数据库后执行 `cd backend && uv run alembic upgrade head`，保留完整错误输出。
