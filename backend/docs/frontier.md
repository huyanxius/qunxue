# 群学前沿后端与本地验收

## 已实现

- 独立 `frontier_knowledge` 领域、SQLite/Alembic 表，不修改稳定知识 release
- 来源、材料、快照、记录版本、主张、词法索引、持久任务、审核结果、主题运行与编辑提炼持久化
- 原来源 ID → DOI → 规范化标题+作者 → 可用全文哈希的四级去重；保留转载关系及变更版本
- 仅元数据/摘录的输入明确标为该范围，不伪造正文哈希或全文核验
- 真正分页检索/详情/主题/趋势/来源状态 API，默认本地词法检索
- 独立可注入embedding提供者、持久chunk向量与缓存（model+schema+contenthash）；配置后鉴权研究Agent可词法+向量RRF，公开HTTP检索始终词法零模型成本
- 未变化内容零新增embedding；新版本不变块可复用；撤回即时过滤并删除对应索引
- 显式主题词典归一、研究/实践分流、去重、证据 ID、日精度30/90/180天统计
- 增长基线为最近30天之前90天；持续比较前后90天。至少4条、2来源，缺完整覆盖不会成立
- 固定业务时区 `Asia/Shanghai`；HTTP 可传 `as_of=YYYY-MM-DD` 回放
- 首批人工12条是测试资料；大量算法采集资料可从相同离线导入入口增量入库
- 独立 extractor/verifier 严格 JSON Schema，块引用、数字和正文有效性门禁；缺配置显式 blocked
- 持久租约、token fencing、崩溃恢复、幂等任务、30/120/600秒退避、最多4次尝试
- 研究 Agent 的 `search_frontier` 工具返回分开的 evidence 与 leads；摘要只作发现线索
- 可追溯编辑提炼覆盖；引用缺失、撤回或版本变化后旧提炼自动失效

## 明确边界

采集脚本按授权公开站点运行，独立于服务内周期采集。当前服务内6个原计划来源加2个扩展
来源的自动适配器是安全关闭状态，WeRSS未部署、账号身份和授权待核实。不能把离线抓取
成功说成持续监控已上线，也没有7天连续运行验收。

当前随仓库交付276条已读释义（273研究、3实践）、6条跨篇简报、2张带出处的论文图链接。
另有517条可读研究索引，其中244条待释义，未混入展示数据。来源级持续覆盖仍为
`coverage_complete=false`，不会把最早收录日期当覆盖起点。15个《社会建设》完整期次可在
同刊、同一期号的跨年队列比较主题份额；数量不代表全学科发文增长。未匹配标签仍可检索，
并显示在“待归类”集合；待归类集合不提出趋势。

全文模型输出未经过冻结30篇人工对照集验证。embedding端口、增量缓存与向量检索已经离线
fakeprovider验收，但未接真实提供者验证，reranker与BERTopic未实现。默认配置仍是词法检索，
不能说当前语料已生成向量。旧embedding key完全隔离，独立key之外还须显式允许模型网络。
独立worker需要明确运行，没有Web匿名写接口。模型审核结果留在审核存储；发布完整模型
记录和教师审核UI仍需后续完整验收，不影响当前公开文献线索检索。

## 全新隔离数据库运行

在仓库 backend 目录，先确认虚拟环境和依赖已安装：

```bash
export QUNXUE_DATABASE_URL="sqlite:////tmp/qunxue-frontier-demo.db"
.venv/bin/alembic upgrade head
.venv/bin/python scripts/frontier.py import data/frontier-corpus.json
.venv/bin/python scripts/frontier.py briefs data/frontier-editorial-briefs.json
# 重复执行上条：相同内容应全部 unchanged，无重复 item/record
.venv/bin/python scripts/frontier.py status
.venv/bin/uvicorn qunxue_api.main:app --host 127.0.0.1 --port 8000
```

不要覆写用户原数据库。本模块不自动导入或自动爬取资料。只启动 `make dev-api` 而没有明确
导入时，前沿 API 返回空列表。初始12条可替换路径为 `data/frontier-seed.json`，只能用于
初始规则验收，不能代替扩展语料。

如本机已有主系统模型配置，启动其他模块原有任务行为由主系统配置管理；前沿不会复用它。
验收时建议 `QUNXUE_MEMORY_LEARNING_ENABLED=false` 并使用无模型配置的环境。

## 读取接口

- `GET /api/frontier/search?q=&stream=research|practice&source_id=&topic_id=&since_days=&limit=200&offset=0`
- `GET /api/frontier/records/{record_id}`，不存在真实404
- `GET /api/frontier/topics?as_of=2026-10-01`
- `GET /api/frontier/trends?window=30|90|180&as_of=2026-10-01`
- `GET /api/frontier/sources`
- `GET /api/frontier/status`

返回 `next_offset` 为 null 时结束分页；固定语料内按来源网页日期+ID稳定排序。网页日期只用于
“来源更新”排序；任何研究时间窗口只使用明确的论文日精度发布日期。`window` 选择展示窗口，
同一趋势卡仍返回所有固定窗口及门槛，不对任意时间范围外推。

## 编辑提炼

```json
{"briefs":[{"topic_key":"care-family","stream":"research","title":"...",
"summary":"...","why_it_matters":"...","evidence_record_ids":["真实ID"],
"generated_by":"offline_editorial"}]}
```

```bash
.venv/bin/python scripts/frontier.py briefs /absolute/path/editorial-briefs.json
```

引用须存在且属于同一主题和材料流。系统计算 `basis_content_hash`、`updated_at`，不接受
用不存在文献凑数。摘要与why_it_matters必须由实际证据支持，导入成功不等于系统替代语义审读。

## Source生命周期与任务投递

真实爬虫从授权公开站点采集后生成统一JSON。显式回放会走
DISCOVER → FETCH → PARSE → EXTRACT，并将各阶段写入可恢复队列：

```bash
.venv/bin/python scripts/frontier.py replay data/frontier-corpus.json
```

本地source adapter按内容指纹推进cursor，变化后的老ID也会重新处理；相同内容幂等。
没有模型配置时EXTRACT为blocked/NotConfigured（没有实际正文摘录则AwaitingSourceText）。
`frontier.py schedule` 根据已启用source与时间桶幂等投递，默认全部禁用，不会触发网站请求。
未来服务定时器可只调用schedule，再由独立worker消费；本交付没有部署定时器。

`frontier.py withdraw <record_id>` 是本地管理入口，撤回后检索、主题、编辑提炼和向量结果
均不再发布该记录，原始快照仍保留。没有匿名HTTP写入口。

## 独立 worker / 未来模型配置

```bash
.venv/bin/python scripts/frontier.py enqueue EXTRACT <snapshot_id> --key extract:<snapshot_hash>:v1
.venv/bin/python scripts/frontier.py worker --max-jobs 100
.venv/bin/python scripts/frontier.py status
# 解决配置阻塞后，必须明确恢复，服务不会自动反复调用
.venv/bin/python scripts/frontier.py resume-blocked
```

仅读取独立 `QUNXUE_FRONTIER_EXTRACTOR_BASE_URL/API_KEY/MODEL` 与
`QUNXUE_FRONTIER_VERIFIER_BASE_URL/API_KEY/MODEL`。还需显式
`QUNXUE_FRONTIER_ALLOW_MODEL_NETWORK=true`。这里的斜杠是字段缩写，应分别设置完整变量名。
embedding另用 `QUNXUE_FRONTIER_EMBEDDING_BASE_URL`、`QUNXUE_FRONTIER_EMBEDDING_API_KEY`、
`QUNXUE_FRONTIER_EMBEDDING_MODEL`。全部默认未配置且网络关闭。
抽取、核验角色可以配置不同模型/端点。绝不从 `QUNXUE_MODEL_API_KEY` 或 embedding字段回退。
不应将任何 key 写入仓库、命令历史、日志或验收快照。

## 从真实 HTTP 合同导出显式预览

```bash
.venv/bin/python scripts/export_frontier_preview.py \
  /absolute/path/frontier-corpus.json /tmp/frontier-preview-snapshot.json \
  --briefs /absolute/path/editorial-briefs.json
```

该脚本创建临时隔离SQLite、跑Alembic、导入并经TestClient读取全部分页，再导出JSON。
它不连接模型/采集网站，不污染已有数据库。输出 `preview_only=true`；生产API失败不能把它
当自动兜底。预览仅服务审核，不是线上运行或真实连续采集完成的证据。

## 验证

```bash
.venv/bin/pytest tests/test_frontier_store.py tests/test_frontier_analysis.py \
  tests/test_frontier_models.py tests/test_frontier_pipeline.py tests/test_frontier_embedding.py \
  tests/test_frontier_research_briefs.py tests/test_migrations.py::test_alembic_head_matches_orm_metadata
.venv/bin/python scripts/export_openapi.py
cd ../frontend && npm run generate:api
```

上述是聚焦回归。仓库完整测试已知有既有失败，不能把聚焦通过说成全仓绿灯；最终以完整
测试日志逐项比对为准。无推送、PR、部署动作。

## 可移植采集工具

联网采集算法、固定快照分片、robots/重定向边界和离线可移植性测试保存在仓库
[`tools/frontier-corpus`](../../tools/frontier-corpus/README.md)，不要复制本次审计HTML归档到产品中。
从 backend 目录可先完全离线重建，再显式导入：

```bash
.venv/bin/python ../tools/frontier-corpus/assemble_corpus.py --output /tmp/frontier-rebuilt
.venv/bin/python scripts/frontier.py import /tmp/frontier-rebuilt/frontier-corpus.json
```

上述工具保留早期201条的可复跑基线，不会重建当前276条研究释义。当前扩展交付的安全
分片与离线重建入口位于 `tools/frontier-corpus-expanded`，请按其README使用。
这些工具固定截至2026-10-01，是可复现的一次性语料构建，不是已经部署的每天滚动监测。
联网重抓需要它自己的 `--allow-network` 开关，且可能因网站更新/授权条件变化得到不同数量。

## 研究者提炼与可比图形（新增）

逐篇内容可以显式导入 `extraction_method` / `summary_method` 为
`assistant_evidence_synthesis` 的真实摘要释义，另有 `why_read`、`analysis_scope` 和
`analysis_evidence:[{field, statement, evidence_indexes}]`。索引必须指向该条已有来源证据。
摘要释义仍是 `lead_only`，不会因此升级为全文验证或结论RAG证据。

原 `briefs` 输入向后兼容。可附 `research_brief`：headline、development、consensus、
differences、methods、research_implication、priority_reads、evidence_record_ids。
各分析段为 `{text, evidence_record_ids}`；共识/差异至少引用两项独立研究。优先阅读项为
`{record_id, reason}`。持久化沿用现有JSON列，没有重写已建立的迁移。
每次新brief导入会解析当前item版本、校验同主题/同流引用并计算内容hash；撤回或版本变化
使旧提炼失效。旧title/summary/why_it_matters依然可用。

主题API额外返回：

- `monthly_series`：12个自然月的去重数量、同流分母、样本内占比与可追溯记录ID。
  未验证全量覆盖时 `normalized_share=null`，不能将采样曲线称为整个领域发文增长
- `issue_series`：按来源的真实candidate/readable/included计数和当前释义记录对照。
  只有整期候选、可读、纳入和已完成摘要释义数一致才计算share；比较组进一步固定
  同一期刊、同一期号，避免某年2期与某年3期直接混成年度增长
- `series_metadata`：说明是否存在可比期次，以及日期、单位、覆盖范围。主题可多归属，
  各主题份额不要求加总为100%

可在语料顶层提供 `issue_coverage`，每项含source_name、issue_id、publication_year、
publication_issue、publication_month、candidate_count、readable_count、included_count、
coverage_complete、issue_url。未知月可以保存（coverage_complete=false），但不会猜测时间
坐标；当前月尚未完整时月度点也明确标记。

## 正文图片引用

`record.media` 默认空数组；每项为url、caption、source_url、kind与可选alt。
kind仅支持figure/chart/article_photo/illustration，排除logo、banner和默认封面。
原网页与图URL必须为精确允许的出版社/机构HTTPS主机，禁止凭证和任意外站。
仅存链接和归因，不在产品语料中存图片字节或完整文章；无图不生成替代占位。

## 全语料研究综述

`GET /api/frontier/overview` 返回持久化 `overview`、当前实际 `statistics` 与
`ready/not_configured/stale` 状态。综述包含共同关注、可比变化、方法特点、关键差异、
研究机会五组证据陈述。研究与实践分开；来源/年份/主题/方法/数据分布只统计研究。
方法与数据类别采用明确字段词典，未知和未分类单列，重叠类别不能加总为100%。

```bash
.venv/bin/python scripts/frontier.py overview data/frontier-corpus-overview.json
.venv/bin/python scripts/export_frontier_preview.py data/frontier-corpus.json \
  /tmp/frontier-preview-snapshot.json --briefs data/frontier-editorial-briefs.json \
  --overview data/frontier-corpus-overview.json
```

导入要求 `scope.coverage_record_ids`、`reviewed_record_ids` 和 `review_index` 完整对应
当前可浏览、去重后的全部研究。`review_index` 每项含 record_id 和 summary_sha256，后者
是原摘要释义字符串UTF-8字节的SHA256；不是模型声称的阅读数量。各陈述必须引用存在的
研究ID，共同关注、变化和差异至少引用两项研究。系统校验覆盖和版本，不能代替内容审读。

系统计算全范围 `source_hashes`、`basis_content_hash` 与更新时间，存入已有编辑JSON专用键。
新增、撤回或更新任何纳入研究后，旧综述不再公开，状态转 stale；统计仍按当前可见材料
重算。实践更新不会错误地使研究总述失效。没有匿名写入端点；导入和统计均不调用模型。

## JSON 分片存储

大记录文件以 `qunxue-json-shards-v1` 清单和同目录 `.parts/` JSON 数组保存，每片不超过 250,000 UTF-8 字节。导入/回放、预览导出和离线组装命令不变；不要对清单直接使用 `json.loads` 当作业务数据。Python 消费者应使用随包提供的 `json_shards.load_json`（后端为 `qunxue_api.json_shards.load_json`）。必须连同清单复制整个 `.parts/` 目录；加载器拒绝越界路径、重复分片、缺片、SHA256 或记录数量不匹配。

这只是无损存储方式变更，记录顺序、字段和规范记录哈希不变。组装输出仍为普通 JSON，当前扩展数据的全部冻结输出 SHA256 不变。两个工具包各带相同的小型标准库加载器，以保持可单独移动、离线复现。`snapshot.json` 与 `SHA256SUMS` 记录新的清单和分片文件哈希。
