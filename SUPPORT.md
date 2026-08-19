# 支持与排障

## 先收集这些信息

报告问题时请提供：

- 代码版本或 commit；
- `GET /api/health` 的非敏感字段（不要贴 cookie、API key 或完整模型响应）；
- 浏览器地址、操作步骤和实际看到的错误；
- 是否运行在 `mock`、`base` 或 `sft`；
- `make check` 中失败的最小命令和完整错误上下文。

## 使用边界

`/agent` 当前是界面预览，尚未连接研究模型；新研究页中的 Agent 只有在真实 provider 运行记录、引用链和发布版本同时存在时，才可按真实结果验收。来源审核状态与发布版本需要由使用者核对。当前版本没有教师端，也不会替用户作出理论选择或声称已经形成完整研究框架。理论匹配、研究框架和可追溯导出缺失时，请把页面提供的状态当作未开放，而不是故障结果。

## 入口

- 安装、环境变量、备份和发布前检查：[`docs/DISTRIBUTION.md`](docs/DISTRIBUTION.md)
- 密钥、数据和公网暴露边界：[`docs/SECURITY.md`](docs/SECURITY.md)
- 新队员开发流程：[`docs/onboarding.md`](docs/onboarding.md)
- 产品事实与交付边界：[`docs/product/README.md`](docs/product/README.md)
