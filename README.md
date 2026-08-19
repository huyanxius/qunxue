# 群学致知

面向一流学科建设的社会学垂类大模型与智能体平台（挑战杯"揭榜挂帅"擂台赛，榜题 XH-202620，科大讯飞发榜）。

当前产品帮助社会学入门者和初级研究者从研究现象出发，理解候选理论的适用条件、差异和证据线索，最终由用户决定采用什么理论。产品事实以 [`docs/product/README.md`](docs/product/README.md) 为入口，交付状态以已合入 `main` 的代码和 PR 为准。

## 当前工程基线

正式工程不继承旧 LiveDemo 的代码、资产或依赖。当前已合入 `main` 的能力包括：

```text
M1 / PR #66 站点壳与首页双入口
M2 / PR #58 账号会话与“我的研究”
M3 / PR #68 研究输入、现象候选与用户确认
M6 / PR #73 知识发布、浏览、搜索、详情与来源
```

其中真实运行链路仍遵循 React 页面 → 产品模块公共入口 → OpenAPI 生成客户端 → FastAPI → 业务模块 → repository port → SQLite。已经真实实现：

- 后端健康检查；
- 账号注册、登录、会话恢复与“我的研究”；
- 创建 `direct_input` 或单份材料研究任务，编辑并确认现象候选，使用稳定 ID 恢复进度；
- 使用 `Idempotency-Key` 避免重复写入；
- 从仓库 Markdown 生成并持久化知识发布，通过 `/knowledge` 和 `/knowledge/:knowledge_id` 浏览、搜索、查看详情与来源；
- Pydantic → OpenAPI → TypeScript SDK 单向生成；
- 本地检查与 GitHub CI。

M4（理论匹配与用户决定）和 M5（研究框架）尚未交付：前端 `/research/:task_id/match`、`/research/:task_id/framework` 仍是占位页，后端对应路由保留冻结契约并返回 501。公共类型、路由和门禁规则不等于业务能力已经实现。

知识源转换清单为 2,864 条；当前可发布、可浏览的 Markdown 正文解析为 2,860 条。差额来自 D7 的 H088–H091：源清单保留编号，但仓库中没有这四条正文，发布过程没有伪造内容。

## 技术栈

- Web：React、TypeScript、Vite、TanStack Query
- API：FastAPI、Pydantic
- 数据：SQLAlchemy、Alembic、SQLite
- 契约：OpenAPI、Hey API
- 工具：uv、npm、Ruff、Vitest、Oxlint

## 文档入口

- 第一次参与开发：[`docs/onboarding.md`](docs/onboarding.md)
- 分发、运行、备份与发布前检查：[`docs/DISTRIBUTION.md`](docs/DISTRIBUTION.md)
- 安全与隐私边界：[`docs/SECURITY.md`](docs/SECURITY.md)
- 使用支持与排障：[`SUPPORT.md`](SUPPORT.md)
- 变更记录：[`CHANGELOG.md`](CHANGELOG.md)
- 模块职责与依赖方向：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- 分支、提交与 PR：[`CONTRIBUTING.md`](CONTRIBUTING.md)
- 产品事实与竞赛边界：[`docs/product/README.md`](docs/product/README.md)

## 五分钟启动

需要 Python 3.12、Node.js 22.18+、`uv` 和 `npm`。

```bash
git clone https://github.com/huyanxius/qunxue.git
cd qunxue
make bootstrap
```

分别启动 API 和 Web：

```bash
make dev-api
make dev-web
```

打开 `http://localhost:5173`。

默认启动不需要密钥。完整冒烟步骤和环境变量见 [`docs/onboarding.md`](docs/onboarding.md)。

## 检查

```bash
make check
```

该命令执行契约生成与漂移检查、后端 lint/测试、前端模块边界检查、lint、类型检查、测试和生产构建。

SQLite 仅用于单实例、单 worker、本地非敏感演示。当前同步执行不是可靠异步队列；账号会话与知识发布已经合并，但生产级认证加固、生产数据库、真实模型 provider 和正式部署仍不在当前交付范围。

## 协作规范

1. 所有改动按团队规则走分支 + PR 合入，不直接推 `main`。当前 `main` 没有 GitHub 原生分支保护，PR-only 是协作规则，不是平台强制。
2. 每个 PR 对应一个 Issue，改动范围与 Issue 一致，不夹带无关改动；PR 小而频繁，不攒大包。
3. PR 描述写清改动、原因、验证结果和架构影响。作者本人要能讲清改动，合并前至少一位同学 Review。
4. 密钥红线：API key、appid 只放本地 `.env` 文件，任何时候不进仓库。

详细流程见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，首次配置见 [`docs/onboarding.md`](docs/onboarding.md)。
