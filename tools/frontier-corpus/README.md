# 群学前沿：可移植的固定日期语料工具

## 交付边界

这是 **截至 2026-10-01 的一次性证据快照**，不是每天滚动更新的通用采集器。
优先发表窗口固定为 2025-10-01 至 2026-10-01；实践按 2025-10 至 2026-09 的完整月份各取 5 条，学术资料保留 2024–2025 历史基线。
因此脚本中的 `TODAY`、`WINDOW` 和年度目录范围是有意冻结的。没有提供表面可调却不能完整更新发现逻辑的 `--as-of` / `--since` 参数。

包内 4 份安全输入共 201 条：138 研究摘要线索、63 官方实践。12 条初始种子由助手逐条核验整理，189 条由程序采集。历史字段 `manual_curated` 表示逐条整理方式，**不表示人类审稿**；所有记录均 `human_full_text_reviewed: false`。

所有输入只含元数据、短摘录、主题提要、来源 URL 和哈希。没有 HTML、论文全文或完整摘要。`source_snapshot` 中保留的本地证据/快照引用仅描述当次采集，不代表这些文件随包提供。

## 环境

- 离线组装：Python 3.9+，仅标准库
- 联网采集：Linux/macOS，Python 3.9+，`python -m pip install -r requirements.txt`
- 进程锁使用 Unix 标准库 `fcntl`，联网脚本不支持原生 Windows；离线组装支持 Windows
- 从任意当前工作目录直接执行脚本路径，不使用 `python -m crawlers.…`
- 不需要 API key、模型服务、账号登录或 embedding

## 离线重建（推荐，无任何网络请求）

将整个 `repo-tools` 目录放到仓库任意位置，执行：

```sh
python /path/to/repo-tools/assemble_corpus.py --output /path/to/build/frontier
```

默认输入从脚本旁 `data/` 读取，和当前工作目录无关。输出目录相对路径按调用者当前目录解析。任何输入缺失立即失败，不会静默产出“不完整但已完成”的语料。

写出：
- `frontier-corpus.json`：带统计、来源清单和 `records` 的对象，适配后端导入
- `frontier-corpus-records.json`：纯数组
- `source-manifest.json`、`validation-report.json`、`deduplication-report.json`

如需组装另一个完整的同结构输入目录：

```sh
python /path/to/repo-tools/assemble_corpus.py --input-root /path/to/input-data --output /path/to/build/frontier
```

输入必须同时有 `manual-seed-records.json`、`journals/records.json`、`society/records.json`、`practice/practice-records.json`；这仍按本快照固定窗口判定，不能当通用滚动更新器使用。

## 可选联网重取（本次交付没有重新运行）

这些命令会真正访问原站，需要显式 `--allow-network` 和一个新的非空检查通过的输出目录：

```sh
python /path/to/repo-tools/crawlers/harvest_ruc_journals.py --allow-network --output ./runs/journals --target 100 --hosts shjs.ruc.edu.cn
python /path/to/repo-tools/crawlers/collect_society.py --allow-network --output ./runs/society --limit 24 --years 2026,2025
python /path/to/repo-tools/crawlers/collect_practice.py --allow-network --output ./runs/practice --per-month 5
```

实践脚本默认读取包内种子和 5 条已核排除清单；可用 `--seed`、`--exclusions` 指定其他路径，但不能缺文件。不要移走排除清单。

每域串行且同机跨输出目录加锁；常规间隔 2–5 秒，遵守更长的 robots crawl-delay。首次及每次新执行都重新核查 robots，不复用旧 robots 缓存。拒绝所有自动重定向（包括同主机，避免未经 robots 核验的目标路径）、非 HTTPS、非允许主机、URL 用户凭证及非 443 端口；401/403/429、验证码或重复失败停止。HTTP 200 中的明确验证码、人机验证或登录门槛也在内容解析前统一识别并停止整个主机，必要时宁可保守停采，不绕过限制。仅 journals 提供显式 `--resume`，其他脚本必须用新目录。

源网页可能增删或修订，robots 和可用性也会变化，所以联网重取**不保证仍然取得 201 条或字节完全相同**。可严格复现的是包内安全输入的离线组装。采集时间使用真实运行时间，和冻结的发表截止日分开。

重新采集的输出默认整目录忽略 Git；本版本只保留响应哈希/元数据和必要短摘录，不落地完整文章 HTML，即便网页允许归档。手动选择安全记录文件后才能纳入发布；不要把整个运行输出目录提交进仓库。

## 验证

```sh
python /path/to/repo-tools/tests/test_portability.py
python /path/to/repo-tools/tests/test_access_challenges.py
```

测试复制整个工具包到随机临时目录，从另一个 cwd 运行离线组装；核对 201 条、138/63 分流、16 条未知精确日期排除月统计、种子文件缺失失败、所有 CLI help 不访问网络/不产生输出、网络必须显式选择。测试本身禁止 socket 联网。另有 8 类 HTTP 200 验证码/登录挑战 × 3 个采集器的 24 项 Mock，验证解析前立即停域、无重试、后续请求为零。

`audit/portability-validation.json` 是本次实测结果，`SHA256SUMS` 可检验发布文件。离线组装只改输出时间戳，不刷新原始抓取/发表时间。

## 使用结论的限制

- `lead_only` 只表示实际取得了公开研究摘要，不能当作已阅读全文
- 批量 `summary` 是确定性主题提要，不是研究结论抽取
- `practice_signal` 是官方实践报道，不是独立效果评估
- 113 条精确日日期落在优先窗口，72 条为窗口外历史基线，16 条仅刊期不进入月度统计
- 每月实践固定配额、便利抽样和期刊可访问性都会影响分布；只能描述样本内主题与覆盖，不能据采集量计算学科增长率或现实发生率

本目录没有部署、账号上传或发布操作。

## JSON 分片存储

大记录文件以 `qunxue-json-shards-v1` 清单和同目录 `.parts/` JSON 数组保存，每片不超过 250,000 UTF-8 字节。导入/回放、预览导出和离线组装命令不变；不要对清单直接使用 `json.loads` 当作业务数据。Python 消费者应使用随包提供的 `json_shards.load_json`（后端为 `qunxue_api.json_shards.load_json`）。必须连同清单复制整个 `.parts/` 目录；加载器拒绝越界路径、重复分片、缺片、SHA256 或记录数量不匹配。

这只是无损存储方式变更，记录顺序、字段和规范记录哈希不变。组装输出仍为普通 JSON，当前扩展数据的全部冻结输出 SHA256 不变。两个工具包各带相同的小型标准库加载器，以保持可单独移动、离线复现。`snapshot.json` 与 `SHA256SUMS` 记录新的清单和分片文件哈希。
