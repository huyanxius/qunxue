# Agent 工作规范 / Agent Working Rules

> 本文件供 AI 编程助手自动读取。人类协作规范见 README.md。
> This file is auto-read by AI coding agents. Human collaboration rules: see README.md.

## 中文

每次提交代码必须走以下流程，禁止跳步：

1. 从最新 main 切新分支：`git checkout main && git pull && git checkout -b feat/<简短英文名>`
2. 完成改动后自查：确认没有 `.env`、密钥、`node_modules`、大体积产物混入
3. 提交并推送**分支**。禁止推 main（有分支保护，推不上去）
4. 用 `gh pr create` 发 PR：标题一句话说清改动；正文写清"改了什么、为什么这么改"，关联对应 Issue（如 `Closes #12`）
5. 把 PR 链接交给用户，并提醒：合并前需至少一位队友 Review，作者本人要能讲清这次改动

红线：永不 `git push --force`；永不提交任何密钥（API key、appid）；PR 小而聚焦，不夹带无关改动。

提交格式：`type(scope): 中文说明`。一个提交只承担一个逻辑单元；禁止助手署名、`Co-Authored-By` 或工具名称尾注。

## 工程架构

### 后端

- `modules/research_intake/`：研究任务、入口输入与已确认现象。
- `modules/knowledge_catalog/`：版本化知识发布、条目、关系与理论身份。
- `modules/theory_matching/`：证据交接、候选判断与用户理论决定。
- `modules/research_framework/`：框架草拟、审校、修订与确认。
- `application/`：只通过模块公共入口编排主链，不承载模块内部规则。
- `api/`：FastAPI DTO、路由和异常映射。
- `adapters/`：SQLite 及后续外部服务实现。
- `bootstrap.py`：唯一依赖装配点。

业务模块不得依赖 FastAPI、Pydantic、SQLAlchemy 或具体模型 SDK。模块间只从包根导入，并传递稳定 ID、版本和不可变快照。

### 前端

- `src/app/`：应用壳与路由。
- `src/api/generated/`：由 OpenAPI 生成，只生成不手改。
- `src/modules/socio-match-workspace/`：研究任务创建、恢复与工作区。
- `src/modules/knowledge-explorer/`：知识浏览、搜索、详情与来源。

产品模块只通过 `index.ts` 暴露能力；业务组件不得裸调用 `fetch`、手写重复 DTO 或直连模型服务。

### 运行与检查

```bash
make dev-api
make dev-web
make check
```

禁止复制旧 LiveDemo 的代码、资产和依赖。Mock、静态页面、类型契约或构建通过不得描述为真实模型或完整端到端交付。

## English

Every code submission MUST follow this flow, no skipping:

1. Branch off the latest main: `git checkout main && git pull && git checkout -b feat/<short-name>`
2. Before committing, self-check: no `.env`, secrets, `node_modules`, or large artifacts included
3. Commit and push the **branch**. Never push to main (branch protection will reject it anyway)
4. Open a PR via `gh pr create`: one-line title; body states *what changed and why*; link the Issue (e.g. `Closes #12`)
5. Hand the PR link back to the user, reminding them: at least one teammate must review before merge, and the author must be able to explain the change

Hard rules: never `git push --force`; never commit any secret (API key, appid); keep PRs small and focused.
