# 工程状态

本文只记录当前工程能力、边界和风险。任务状态、负责人、依赖与验收结果以 [GitHub Issues](https://github.com/huyanxius/qunxue/issues) 为唯一事实来源。

## 已完成

- 正式骨架建立在原仓库最新 `main` 上，没有复制旧 LiveDemo 代码、资产或依赖。
- 已跑通 React → 生成 SDK → FastAPI → research_intake → repository port → SQLite。
- 已实现健康检查、研究任务创建、幂等重放、稳定 ID 恢复和首条 Alembic migration。
- 后端拆为四个业务模块，前端拆为两个产品模块；自动检查限制越界依赖。
- Knowledge Explorer 已有可注入数据源的浏览组件，但尚未挂入正式路由。

## 尚未完成

- 完整领域枚举、门禁真值表、模型契约与 Run/Attempt 恢复语义仍需冻结。
- 后三个业务模块尚未接入真实持久化、知识库、模型适配器和 API。
- `idempotency_key` 暂留在 foundation 实体，后续应迁入 application 幂等记录。

## 风险

- SQLite 仅限单实例、单 worker、本地非敏感演示。
- 当前同步执行不是可靠异步队列。
- 公共类型用于验证模块接力，不等于 Proposal 全部领域契约已经冻结。

## 下一步

- 实现“输入现象 → 候选理论 → 用户决定 → 研究框架”的 Mock 纵向链。
- 冻结模型运行和恢复契约，再接入真实 provider。
