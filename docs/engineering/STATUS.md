# 工程状态

本文只记录当前工程能力、边界和风险。任务状态、负责人、依赖与验收结果以 [GitHub Issues](https://github.com/huyanxius/qunxue/issues) 为唯一事实来源。

## 已完成

- 正式骨架建立在原仓库最新 `main` 上，没有复制旧 LiveDemo 代码、资产或依赖。
- M1 / PR #66、M2 / PR #58、M3 / PR #68、M6 / PR #73 已合入 `main`。
- 已跑通 React → 生成 SDK → FastAPI → 业务模块 → repository port → SQLite。
- 已实现健康检查、账号与会话、研究任务创建和恢复、现象候选确认，以及知识发布、搜索、详情和来源浏览。
- 后端拆为五个业务模块，前端拆为三个产品模块；自动检查限制越界依赖。
- Knowledge Explorer 已接入 `/knowledge` 与 `/knowledge/:knowledge_id` 正式路由和真实知识 API。

## 尚未完成

- M4 理论匹配与用户决定尚未交付：前端 match 路由仍为占位，后端 matching 接口仍为 501。
- M5 研究框架尚未交付：前端 framework 路由仍为占位，后端 frameworks 接口仍为 501。
- 模型运行与 Run/Attempt 恢复语义尚未形成已交付的主链。

## 风险

- SQLite 仅限单实例、单 worker、本地非敏感演示。
- 当前同步执行不是可靠异步队列。
- 公共类型用于验证模块接力，不等于 Proposal 全部领域契约已经冻结。
- 知识源转换清单为 2,864 条，当前发布解析为 2,860 条；D7 H088-H091 缺少正文且未伪造。
- `main` 当前没有 GitHub 原生分支保护；PR-only 是团队规则，不是平台强制。

## 下一步

- M4、M5 仍需独立 Issue 与评审；本次状态收口不排期、不推进，也不得把占位路由或 501 契约描述为已实现。
- 冻结模型运行和恢复契约后，再决定真实 provider 接入。
