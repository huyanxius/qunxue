# RUN_STATE

> 2026-08-09 按最新 `origin/main` 与 GitHub 当前状态核对。本文记录已合并能力和仍未交付的边界，不把冻结契约、占位页面或历史验证记录算作交付。

## 已合并交付

- M1 / [PR #66](https://github.com/huyanxius/qunxue/pull/66)：站点壳、首页与研究/知识双入口。
- M2 / [PR #58](https://github.com/huyanxius/qunxue/pull/58)：账号注册登录、会话恢复与“我的研究”。
- M3 / [PR #68](https://github.com/huyanxius/qunxue/pull/68)：直接输入或单份材料、现象候选编辑与确认、进度恢复。
- M6 / [PR #73](https://github.com/huyanxius/qunxue/pull/73)：真实 Markdown 知识发布、SQLite 持久化，以及列表、搜索、详情与来源浏览；正式路由为 `/knowledge` 和 `/knowledge/:knowledge_id`。

## 尚未交付

- M4 理论匹配与用户决定尚未实现。前端 `/research/:task_id/match` 是占位页；后端 matching 路由只保留冻结契约，确认现象后的业务请求仍返回 501。
- M5 研究框架尚未实现。前端 `/research/:task_id/framework` 是占位页；后端 frameworks 路由只保留冻结契约并返回 501。
- 公共类型、OpenAPI 契约、门禁规则或占位路由不构成 M4/M5 交付；本状态也不推进知识关系或图谱能力。

## 知识条目口径

- 源文档转换清单：2,864 条，其中 D7 按 `H001`–`H091` 计 91 条。
- 当前发布与浏览解析：2,860 条；仓库实际具备正文的是 `H001`–`H087`。
- D7 `H088`–`H091` 缺少正文，发布过程没有补写或伪造这四条内容。

## 仓库治理

- 所有改动走 Issue → 分支 → PR → Review → `main`，这是团队规则。
- 当前 private 仓库的 `main` 没有 GitHub 原生分支保护；PR-only 不是平台强制。不得把升级套餐、公开仓库或改变可见性当作默认修复。
