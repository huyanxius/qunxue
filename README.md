# 群学致知

面向一流学科建设的社会学垂类大模型与智能体平台（挑战杯"揭榜挂帅"擂台赛，榜题 XH-202620，科大讯飞发榜）。

当前产品帮助社会学入门者和初级研究者从研究现象出发，理解候选理论的适用条件、差异和证据线索，最终由用户决定采用什么理论。产品事实以 [`docs/product/README.md`](docs/product/README.md) 为入口。

## 当前工程基线

正式工程不继承旧 LiveDemo 的代码、资产或依赖。当前可运行的最小链路是：

```text
React 页面
→ 产品模块公共入口
→ OpenAPI 生成客户端
→ FastAPI
→ research_intake
→ repository port
→ SQLite
```

已经真实实现：

- 后端健康检查；
- 创建 `direct_input` 研究任务；
- 使用稳定 ID 恢复任务；
- 使用 `Idempotency-Key` 避免重复创建；
- Pydantic → OpenAPI → TypeScript SDK 单向生成；
- 本地检查与 GitHub CI。

`knowledge_catalog`、`theory_matching`、`research_framework` 已定义模块公共契约和人工门禁规则，但尚未接入真实知识库、模型与持久化，不视为完整业务交付。

## 技术栈

- Web：React、TypeScript、Vite、TanStack Query
- API：FastAPI、Pydantic
- 数据：SQLAlchemy、Alembic、SQLite
- 契约：OpenAPI、Hey API
- 工具：uv、npm、Ruff、Vitest、Oxlint

## 安装与启动

需要 Python 3.12、Node.js 20.19+/22.12+、`uv` 和 `npm`。

```bash
make bootstrap
```

分别启动 API 和 Web：

```bash
make dev-api
make dev-web
```

打开 `http://127.0.0.1:5173`。

## 检查

```bash
make check
```

该命令执行契约生成与漂移检查、后端 lint/测试、前端模块边界检查、lint、类型检查、测试和生产构建。

SQLite 仅用于单实例、单 worker、本地非敏感演示。当前同步执行不是可靠异步队列；认证、多用户、生产数据库、真实知识库和模型接入均不在本次基线范围。

## 协作规范

1. main 已开分支保护：所有改动走分支 + PR 合入，不直接推 main。
2. 每个 PR 对应一个 Issue，改动范围与 Issue 一致，不夹带无关改动；PR 小而频繁，不攒大包。
3. PR 描述写清两件事：改了什么、为什么这么改。可以让 AI 写代码和提交，但作者本人要能讲清改动——责任在人，不在 AI。合并前至少一位同学 Review。
4. 密钥红线：API key、appid 只放本地 `.env` 文件，任何时候不进仓库。

详细流程见 [`CONTRIBUTING.md`](CONTRIBUTING.md)，首次配置见 [`docs/onboarding.md`](docs/onboarding.md)。
