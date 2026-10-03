# 独立研究入口计费兼容补丁

本补丁在已通过独立复验的 v2 基础上恢复群学三个现有研究入口、Everplain
现象提取入口的付费模型调用。Everplain 原本未挂载匹配/重试 API，本次保持 404；
共享匹配 application 的合成回归不代表该产品存在公开匹配接口。
沿用现有鉴权、任务归属、业务幂等、积分冻结、模型费率、运营风险预算和错误退款，
不新增架构、前端或生产配置，也不推定采购现金报价。

| 现有调用点 | 费用归属与计费边界 |
| --- | --- |
| `api/routes/phenomena.py::extract_phenomenon_candidates` → `ModelGateway.build` | 通过已有任务归属鉴权后，以任务用户开启 `user_research`；独立业务 session 最终提交成功后结算；保存失败退款 |
| 群学 `application/theory_matching.py::_start_impl` → `TheoryMatchingService.start` → `ModelGateway.judge_and_rerank` | 独立 API 的已鉴权用户付费；已有幂等结果、已固定匹配结果在新冻结和 HTTP 前返回；任务 CAS、结果保存及提交失败均退款 |
| 群学 `application/theory_matching.py::retry_candidate` → `TheoryMatchingService.retry_candidate` | 先检查匹配结果归属，按匹配结果和幂等键建立操作；原业务重试记录回放交原模块校验，不重复付费调用 |
| Everplain `api/routes/matching.py` 未挂载接口 | 明确测试 OpenAPI 中不存在、原请求返回 404，零 HTTP/零冻结；不新增产品入口 |
| `bootstrap.py::disciplinary_agent_scope` 内的匹配 application | 复用 Agent turn 已有操作，避免为嵌套工具建立第二笔冻结或重复结算 |
| `bootstrap.py` 模型探测、记忆学习/概览、课程知识 worker | 保持 v2 的独立 phase 和有限预算；探测必须运营承担，其他后台 phase 继续要求明确配置 |
| Everplain `GraphTopicNamer` | 保持 v2 可选运营 phase；缺配置跳过命名并保留原文档标签及图谱 |
| `api/routes/frameworks.py` 旧草拟/审校入口 | 群学原来即返回 410，Everplain 未挂载保持 404；未恢复或新增模型调用；`ModelGateway.draft/audit` 未发现当前有效业务调用者 |
| `adapters/model/openai_compatible_provider.py::_send` 的其他无操作调用 | 仍在 HTTP 前明确失败；没有可推定的鉴权用户或后台归属，不默认免费或运营承担 |

`user_research` 固定为用户费用，不能用 phase 配置改为运营承担；已有管理员豁免
仍然记录成本并受运营预算约束。未配置 K、价格版本或风险金额时继续显式失败，
本补丁不提供生产值。

每次旧同步 HTTP 调用记录实际 endpoint、route、provider host、请求/返回模型、
输入/缓存/输出和 receipt。失败 HTTP 的未知用量留在运营风险账；已知用量但
业务结果无效的候选标为不可向用户收费。有效 fallback 只结算必要的成功步骤。
未知或不合法 usage 保留安全 502 计费错误，不被旧 `ValueError` 分支降为 409。
Everplain 未配置独立输出上限时采用与群学相同的 5000 上限，已配置的有限上限继续优先。

新增合成回归覆盖真实旧模型适配器、主路由失败/fallback、缓存计价、有效/无效候选、
理论匹配与重试、幂等回放、越权用户、提交/保存故障、缺配置和未知 usage 的 JSON 错误。
API 回归使用真实鉴权和 SQLite 业务表；目录证据和模型 HTTP 均为合成输入，未发付费请求。
另外保留并重跑 v2 原始独立复验用例，消费端证据包 SHA256：
`8cb7cebc239b7e9f42d2a329b8be1068ced90900b864fa57d8626a48a0334918`。

未发现其余有效独立研究 Chat 调用点有费用归属待定。Embedding、rerank、索引、
单独 vision/OCR、转录及网页服务的既有有界运营行为保持不变，仍在本轮 Chat 积分补丁外。
