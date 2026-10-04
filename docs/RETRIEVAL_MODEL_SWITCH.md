# 检索模型切换与回退

此变更只允许同系列的明确模型 ID：embedding 为 `Pro/BAAI/bge-m3` 或 `BAAI/bge-m3`，rerank 为 `Pro/BAAI/bge-reranker-v2-m3` 或 `BAAI/bge-reranker-v2-m3`。现有默认值不变；聊天模型配置不参与切换。

## 离线预检

在运行待发布源码或已包含此修复的 API 环境中执行：

```bash
python -m qunxue_api.retrieval_preflight --env-file /secure/qunxue.env
```

该命令在内存中预览免费模型配置，不修改文件、数据库或索引，不调用模型。它只读索引 manifest 元数据，输出目标模型下的 ready 索引数量、其他模型索引数量及记录的维度；不读取文档正文或向量值，不输出凭据或完整配置。进程环境变量按现有 Settings 规则优先于显式 env 文件；未指定文件时只读进程环境，不隐式读取默认 dotenv。

`configuration_valid` 只表示配置可被当前代码接受。`provider_verification` 和 `vector_dimension_verification` 均为 `not_performed`，不代表上游可调用或索引可用。`ready_target_indexes=0` 时，旧 Pro 索引不能满足免费模型的 release-bound 检索；数字非零也不能代替具体 release、content hash 和 schema 的匹配检查。

群学使用自身的配置和进程管理入口；该预检不接管现有部署流程。

## 切换门槛

2026-10-04 的首次诊断中，原认证调用两个免费模型均返回 HTTP 402 / 30001（余额不足）。用户充值后，同一认证的最小合成验证已成功：embedding 返回 1024 维，rerank 返回 2 条结果。后续切换仍须以运行服务的实际免费调用结果验收。

发布包含本修复的代码并完成离线预检后，才可备份私有 env 与原发布引用，修改以下两个值，并按现有进程管理方式刷新 API：

```dotenv
QUNXUE_EMBEDDING_MODEL=BAAI/bge-m3
QUNXUE_RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

备份保持原文件权限，只保存于既有私有配置目录；不得进入 Git、公开日志或补丁包。模型端点、认证、聊天模型和其他服务配置保持原值。

## 索引与单文档重试

缓存和 manifest 使用完整模型 ID。不得移除 `Pro/` 来复用缓存，不得把两个 ID 视为别名，即使维度相同。现有维度检查继续拒绝混合长度；不删除、改写或全库重建旧索引。

指定失败文档仅存在于 Everplain，本群学修复不操作该文档。模型验证成功后再按群学现有权限与入口处理需要重试的单个文档；不得在上游仍 402 时触发重试。

## 回退

恢复备份 env 中的两个原值，切回已记录的原发布引用，并按现有方式刷新 API。旧模型 ID 的缓存和索引保持原样；新模型缓存也不必删除。源码回退使用本次分支的提交逆序 revert 或移除尚未发布的候选补丁。回退过程中不覆盖生产数据库。

本 PR 保持未合并，不触发 CD 发布。用户授权的运行服务最小配置修复单独执行并保留回退备份；后续 CD 发布仍须包含本修复，以免覆盖运行时适配。
