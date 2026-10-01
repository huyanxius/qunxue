# 群学前沿：276 条研究解读的离线重建

这是截至 **2026-10-01** 的固定来源快照。仅使用 Python 3.9+ 标准库，不联网、不调用模型、不需要密钥。整个目录可移到其他机器或仓库，输入路径始终相对脚本位置。

从仓库根目录运行：

```sh
python tools/frontier-corpus-expanded/tools/assemble_expanded.py --output /tmp/qunxue-frontier-expanded
python tools/frontier-corpus-expanded/tools/validate_expanded.py --output /tmp/qunxue-frontier-expanded
python tools/frontier-corpus-expanded/tests/test_portability.py
```

省略 `--output` 时写入本目录的 `build/`，该目录已忽略 Git。输出路径相对调用者当前目录解析。输入缺失或哈希变化会立即失败，不会静默缩减语料。

## 数量与导入

- `frontier-corpus.json`：**276 条实际展示内容**，其中 273 篇研究、3 条官方实践。全部已由助手读取来源并释义，包含摘要、研究问题、发现、阅读价值和证据引用
- `research-index.json`：**517 条可读研究索引**，包括两刊 508 条和 9 条官方成果补充；其中 **244 条尚未完成释义，不应导入展示列表**
- `topic-briefs.json`：6 组跨篇研究简报；`evidence-matrix.json`：16 行方法与机制对照
- `issue-coverage.json`：67 个观察期次，15 期达到全部研究候选可读、纳入并完成释义的严格门槛
- 2 张图片仅保存已核对的原论文 URL、图注与来源归因；没有图片字节

后端展示应导入输出目录中的 `frontier-corpus.json` 和 `topic-briefs.json`。`research-index.json` 是待整理索引，不能当作 517 条完成的 AI 解读。历史工具 `../frontier-corpus/` 保留的是旧 201 条快照，不能用于重建当前数据。

## 可复现与来源

`snapshot.json` 记录原公开包的 SHA256、所有输入哈希和输出哈希。脚本保留原快照的生成时间和发表日期，因此输出文件可与已导入的冻结版本逐字节核对：

- `frontier-corpus.json`：`52d8f50ead956762ee34cf21e8942732f8cbd5818b91cd8d1ac6487d2ccf3dfb`
- `topic-briefs.json`：`033e08d8ee253e94a537a9dcebf50d53a32296387b0193d4239eb24ad586635a`

本目录只包含重建必要的安全分片、短证据、助手释义、元数据、来源 URL 和公开审核记录。没有原网页 HTML、完整摘要、论文全文、私有日志或外部工作区依赖。`SOURCE_AUDIT.md` 保留原冻结交付时的来源说明；其中历史操作状态不表示当前产品部署状态。

本次研究提炼范围是已取得的公开摘要，`analysis_scope=abstract`、`verification_status=lead_only`，不声称人工阅读全文。实践范围为 `practice_body`。未知方法与样本保留空值。4 条原站摘要错配已整组隔离，记录见 `ruc/fingerprint-audit/collision-report.json`；原图核对见 `media-checks/validation.json`。

时间比较应限定同一来源、相同完整期号的交集；136 条只有刊期的记录不能进入日历月份图。期刊样本分布不能解释为整个学科增长或社会现象发生率。本目录不提供滚动采集或可任意改变时间窗的参数；重新研究须形成新的来源快照。

## JSON 分片存储

大记录文件以 `qunxue-json-shards-v1` 清单和同目录 `.parts/` JSON 数组保存，每片不超过 250,000 UTF-8 字节。导入/回放、预览导出和离线组装命令不变；不要对清单直接使用 `json.loads` 当作业务数据。Python 消费者应使用随包提供的 `json_shards.load_json`（后端为 `qunxue_api.json_shards.load_json`）。必须连同清单复制整个 `.parts/` 目录；加载器拒绝越界路径、重复分片、缺片、SHA256 或记录数量不匹配。

这只是无损存储方式变更，记录顺序、字段和规范记录哈希不变。组装输出仍为普通 JSON，当前扩展数据的全部冻结输出 SHA256 不变。两个工具包各带相同的小型标准库加载器，以保持可单独移动、离线复现。`snapshot.json` 与 `SHA256SUMS` 记录新的清单和分片文件哈希。
