# 新队员上手

这份说明面向第一次进入仓库的队员。完成后，你应当能启动前后端、验证当前最小链路，并知道自己的 Issue 应修改哪一层。

## 1. 准备环境

需要：

- Git；
- GNU Make；
- Python 3.12；
- [uv](https://docs.astral.sh/uv/)；
- Node.js 22.18+；
- npm；
- [GitHub CLI](https://cli.github.com/)。

先确认命令可用：

```bash
git --version
make --version
python3 --version
uv --version
node --version
npm --version
gh --version
gh auth status
```

## 2. 克隆与安装

```bash
git clone https://github.com/huyanxius/qunxue.git
cd qunxue
make bootstrap
```

如果仓库不可见，先接受 GitHub 邀请并确认当前账号有访问权限。

默认启动不需要 API key，也不需要创建 `.env`。本地数据库默认位于 `backend/var/qunxue.db`。可选环境变量为：

- `QUNXUE_DATABASE_URL`：覆盖应用与 Alembic 使用的数据库地址，通过启动命令前的 shell 环境或 `backend/.env` 提供；
- `VITE_API_BASE_URL`：覆盖浏览器请求的 API 地址，通过启动命令前的 shell 环境或 `frontend/.env.local` 提供。本地开发不要设置；跨源部署还必须由 API 明确允许前端来源，当前基线没有配置 CORS。
- `QUNXUE_RESEND_API_KEY`：启用 Resend 注册验证码邮件发送；未配置时验证码接口明确返回服务不可用，不会伪装发送成功；
- `QUNXUE_EMAIL_FROM`：已在 Resend 验证域名下的发件人，默认是 `群学致知 <noreply@qunxue.qiyuankaiwu.com>`。

模型运行默认是 `QUNXUE_RUNTIME_MODE=mock`，继续使用 deterministic Mock，不需要密钥。只要在 `backend/.env` 填入非空的 `QUNXUE_MODEL_API_KEY`，模型网关和独立知识 Agent 都会自动切换到 DeepSeek OpenAI-compatible Provider，默认使用 `https://api.deepseek.com` 与 `deepseek-v4-flash`，并关闭 thinking 以节省推理 token。使用其他兼容服务时，再额外设置 `QUNXUE_MODEL_BASE_URL`（包含服务要求的路径）和 `QUNXUE_MODEL_NAME`；`base` 与 `sft` 仍可显式选择对应运行模式。可选配置包括 `QUNXUE_MODEL_TIMEOUT_SECONDS`、JSON 对象形式的 `QUNXUE_MODEL_EXTRA_HEADERS`。`sft` 还可用 `QUNXUE_MODEL_SFT_RESOURCE_HEADER` 和 `QUNXUE_MODEL_SFT_RESOURCE_ID` 增加一个受控资源请求头。

检索模型与聊天模型独立配置：`QUNXUE_EMBEDDING_BASE_URL`、`QUNXUE_EMBEDDING_API_KEY`、`QUNXUE_EMBEDDING_MODEL` 用于 OpenAI-compatible embedding 服务，`QUNXUE_RERANKER_BASE_URL`、`QUNXUE_RERANKER_API_KEY`、`QUNXUE_RERANKER_MODEL` 用于重排服务。向量不依赖独立服务，按 `QUNXUE_RETRIEVAL_INDEX_PATH` 写入版本化本地 SQLite 索引；用 `uv run python scripts/build_retrieval_index.py <knowledge_release_id>` 为明确的 final release 建索引。只提供模型 API key 时，系统使用当前 final MATCH 发布中的 release-bound 词法目录检索，不要求额外检索密钥；配置了任一检索变量后则必须补齐整套检索配置，索引、Embedding 或 Reranker 不可用时正式研究请求失败关闭。

OpenAI-compatible provider 的 HTTP 边界有本地测试覆盖；是否调用真实供应商由环境变量决定，密钥不写入仓库。

本地 `.env` 和任何密钥都不得提交。

## 3. 启动

打开两个终端，都进入仓库根目录。

终端一：

```bash
make dev-api
```

终端二：

```bash
make dev-web
```

浏览器打开 `http://localhost:5173`。API 健康检查也可以直接访问：

```bash
curl http://127.0.0.1:8000/api/health
```

## 4. 冒烟验证

按顺序确认：

1. 首页显示接口已接通；
2. 点击“建立空白研究任务”；
3. 地址进入 `/research/<task-id>`；
4. 刷新页面后，同一任务仍能恢复；
5. 回到终端停止服务，再执行：

```bash
make check
git status --short
```

`make check` 会重新生成契约，执行后端 lint 与测试、前端模块边界检查、lint、类型检查、测试和生产构建，并检查生成文件是否漂移。

## 5. 先理解当前边界

当前真实运行的是：

```text
React → 生成 SDK → FastAPI → research_intake → SQLite
```

`knowledge_catalog`、`theory_matching`、`research_framework` 和 `application/ResearchJourney` 目前主要是公共契约与编排骨架。不要把 Protocol、静态页面、Mock 或构建通过描述成真实知识库、模型运行或完整端到端。

开始任务前按这个顺序阅读：

1. 已分配的 GitHub Issue；
2. [`../README.md`](../README.md)；
3. [`ARCHITECTURE.md`](ARCHITECTURE.md)；
4. [`../CONTRIBUTING.md`](../CONTRIBUTING.md)；
5. 与任务有关的产品文档。

不要让编程助手猜任务归属。Issue 应当写清目标、范围、不做什么和验收标准；不清楚时先补设计。

## 6. 第一次提交

从最新 `main` 创建与 Issue 对应的分支：

```bash
git switch main
git pull --ff-only
git switch -c <type>/<issue-number>-<short-name>
```

提交格式为 `type(scope): 中文说明`，一个提交只做一件事。只暂存当前 Issue 的文件：

```bash
git status --short
git add -- <path>...
git commit -m 'type(scope): 中文说明'
git push -u origin HEAD
gh pr create --base main --title 'type(scope): 中文说明'
```

`gh pr create` 会继续询问正文。正文关联 Issue，并写清改动、原因、验证结果和架构影响。合并前至少请一位队友 Review。

API 发生变化时，不要手改生成客户端：

```bash
make contract
git diff -- backend/openapi.json frontend/src/api/generated
make check
```

完整协作规则见 [`CONTRIBUTING.md`](../CONTRIBUTING.md)。
