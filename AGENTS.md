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

## English

Every code submission MUST follow this flow, no skipping:

1. Branch off the latest main: `git checkout main && git pull && git checkout -b feat/<short-name>`
2. Before committing, self-check: no `.env`, secrets, `node_modules`, or large artifacts included
3. Commit and push the **branch**. Never push to main (branch protection will reject it anyway)
4. Open a PR via `gh pr create`: one-line title; body states *what changed and why*; link the Issue (e.g. `Closes #12`)
5. Hand the PR link back to the user, reminding them: at least one teammate must review before merge, and the author must be able to explain the change

Hard rules: never `git push --force`; never commit any secret (API key, appid); keep PRs small and focused.
