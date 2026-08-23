# Agent 工作规范 / Agent Working Rules

> 本文件供编程助手自动读取。人类协作规范见 CONTRIBUTING.md。
> This file is auto-read by coding agents. Human collaboration rules: see CONTRIBUTING.md.

## 中文

每次提交代码必须走以下流程，禁止跳步：

1. 从最新 main 切新分支：`git switch main && git pull --ff-only && git switch -c <type>/<issue-number>-<short-name>`
2. 完成改动后自查：确认没有 `.env`、密钥、`node_modules`、大体积产物混入
3. 提交并推送**分支**。团队规则禁止推 main；当前仓库没有 GitHub 原生分支保护，不能把平台拦截当作保障
4. 用 `gh pr create` 发 PR：标题一句话说清改动；正文写清改动、原因、验证结果和架构影响，关联对应 Issue（如 `Closes #12`）
5. 完成与改动影响面匹配的验证后，编程助手必须自行合并自己提交的 PR；不等待、不要求也不提醒队友 Review。合并后把 PR 链接和结果交给用户，作者本人仍须能讲清这次改动

红线：永不 `git push --force`；永不提交任何密钥（API key、appid）；PR 小而聚焦，不夹带无关改动。

提交格式：`type(scope): 中文说明`。一个提交只承担一个逻辑单元；禁止助手署名、`Co-Authored-By` 或工具名称尾注。完整流程见 [`CONTRIBUTING.md`](CONTRIBUTING.md)。

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

业务模块不得依赖 FastAPI、Pydantic、SQLAlchemy 或具体模型 SDK。模块间只从包根导入，并传递稳定 ID、版本和不可变快照。完整依赖方向见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

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

1. Branch off the latest main: `git switch main && git pull --ff-only && git switch -c <type>/<issue-number>-<short-name>`
2. Before committing, self-check: no `.env`, secrets, `node_modules`, or large artifacts included
3. Commit and push the **branch**. Team rules prohibit pushes to main; the repository currently has no native GitHub branch protection, so do not rely on platform enforcement
4. Open a PR via `gh pr create`: one-line title; body states the change, reason, verification, and architecture impact; link the Issue (e.g. `Closes #12`)
5. After verification matched to the change impact, the coding agent MUST merge every PR it submits by itself. Do not wait for, require, or remind the user about teammate review. After merging, hand the PR link and result back to the user; the author must still be able to explain the change

Hard rules: never `git push --force`; never commit any secret (API key, appid); keep PRs small and focused.
