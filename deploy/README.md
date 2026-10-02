# 群学自动生产发布（Issue #422）

状态：源码实现和隔离安全测试；**尚未完成 GitHub → 生产主机实链路验证**。
不得将 workflow 合并、上传 artifact 或本地测试通过描述成生产部署成功。

## 正常路径

`PR 无秘密检查 → main 同 commit 检查通过 → 不可变 artifact ID/文件 SHA256 → production 环境 → 固定接收器 → 同时切换后端和前端 → 私网/公网精确版本及资源校验`。

- `.github/workflows/delivery.yml` 取代旧 `ci.yml`。旧 workflow 曾被人工停用，不能把它说成代码失败；本变更不操作 Actions 开关、账号权限或 secrets。
- PR 不引用 production、不读生产 secret。GitHub token 仅 `contents: read`，checkout 不保存凭据；第三方 actions 固定完整 commit SHA。
- main 的部署必须依赖本次 `checks` 成功，同一 job 构建已检查的前端及锁定依赖；下载指定 artifact ID，传输前及服务器再次校验 SHA256 和 commit。没有 `pull_request_target` 或手动任意 ref/命令输入。
- GitHub 和服务器分别串行化；生产任务不取消正在运行的任务。GitHub concurrency 可能合并等待中的旧提交，已运行的部署不被新提交中断。
- 不要求新增 native branch protection，也不强制每次人工批准。遵循仓库 Issue→分支→PR→验证→作者自合并流程；production 环境限制仅 main，初次接通由拥有者安全批准。更严格分支/人工审批规则是可选策略。
- 数据库、`.env`、node_modules、密钥不进入 artifact。构建下载锁文件中 hash 约束的 binary wheels，服务器仅离线安装。目标为 Linux x86_64 / CPython 3.12；主机不兼容的 wheel 或未安装 Python 会在停止服务之前失败。
- 部署会停止单实例写入者，因此有维护间隙；不是零停机或蓝绿部署。没有注册账号、收费平台、模型调用或自动知识入库步骤。

## 一次性接通：必须单独授权和核验

此目录只提供模板，不运行 bootstrap，不生成/上传 key/token，不更改生产机器、DNS、Nginx、Cloudflare、系统账号、安全设置或 GitHub 权限。普通 CD 永远不触碰 cloudflared。

生产 421 已知事实（2026-10-02 源交接，不能代替现场核验）：Tencent `43.142.87.170`，完整 revision `d27c99da860f2df0f0183ab9ea1fbd8cb68b19e5`；后端 `/root/qunxue-release421-d27c99d/backend`，前端 `/var/www/qunxue-release421-d27c99d`；root PM2 `qunxue-api` 单 fork，应用 8092、Nginx 8096；共有三个 SQLite 文件，0462 schema；已验证原有 211 张表计数保留。旧脚本的失败回滚分支未在生产演练。

接通清单：

1. 拥有者核验新的 per-app 非 root 运行账户和权限，私有 `.env` 与三个数据库的**实际完整路径**及所有写入者。模板只记录已确认的旧路径，configured=false、运行 UID/GID=0 故意阻止使用；新隔离布局仍须核验后填入，不能按名字猜用途。已确认三个文件是现役 backend/var/probe.db、qunxue.db、retrieval.db；均 root:root 0600，probe 与 qunxue 是 WAL，retrieval 非 WAL（不能推定具体 journal mode）。probe 用途尚未证实，必须原样保全；整个 var 中附件和其他文件也必须保留。主机只读核验为 x86_64、Python3.12.3、uv0.11.31、Node24.21.0、PM2 7.0.4；这些版本不证明离线 wheel 已兼容。现网 root PM2/`/root` 布局不满足此隔离边界，必须单独计划迁移/授权，不能被首次 CD 顺便改掉。迁移期间保留原数据库、原 root PM2 配置、原 release 和可读备份。将所有需要的现网 PM2 环境值在原服务器内整理为该应用的私有配置，不能跨应用继承 API key。
2. 在主机人工审计安装 root-owned、非 group/world-writable 的固定 `receiver.py` 和同目录 `payload_rules.py` 到 `/usr/local/libexec/qunxue/`，目录和两个脚本都不可被运行账户修改。强制命令使用固定 `/usr/bin/python3.12 -I /usr/local/libexec/qunxue/receiver.py`（Python 路径需现场核验），隔离 Python 环境注入；不能通过用户可写的 Python module 或 wrapper 以 root 执行。它不从 artifact 更新自己。`/etc/qunxue/deploy.json`、`/etc/qunxue/ecosystem.config.cjs` 也必须 root-owned；按核验值填写 `host-config.example.json`，最后才设置 `configured: true`。Python3.12、PM2 和兼容 glibc 必须预先具备。接收器以 root 维护 owner/mode，但所有 Python、pip、alembic、PM2 子进程降权到 qunxue 运行 UID/GID，无额外组。
3. 建立 `/srv/qunxue/{releases,backups,incoming}`（root 拥有；备份及 incoming 为 0700），`current` 是唯一发布指针。经授权把已有 421 放入/映射到 `releases/<完整SHA>/{backend,frontend,knowledge}`，生成经核验的 `release.json`，至少包含 app、revision、所有前端文件 hash，保留旧 migration 源码。这里必须是**已有运行版本的清单**，不能伪装成新部署成功。
4. 单独授权一次 Nginx web-root 适配 `/srv/qunxue/current/frontend` 和运行身份/PM2 adapter，保留现有 8096、`proxy_buffering off`、300s 超时。新 PM2 配置示例仅给出固定单进程路径，不覆盖私有参数；核验既有生产能力、持久 state 和原属主/组/权限。之后每次 CD 都不改 Nginx。无需改 Cloudflare/DNS/tunnel。之前 530 事故说明仅还原内容不够，恢复文件必须连同 uid/gid/mode 一起保留。
5. 拥有者在 GitHub 创建/核验 `production` 环境仅允许 main；不默认 required reviewers。环境变量 `PRODUCTION_CONFIGURED=true`、`DEPLOY_HOST=43.142.87.170`、`DEPLOY_USER=<专用受限登录主体>`。安全录入 `DEPLOY_SSH_KEY`、`DEPLOY_KNOWN_HOSTS`，后者必须独立核验主机指纹，不能在 CI 里临时 `ssh-keyscan` 信任网络。新持久访问需用户动作时批准，不得复用不相关 key 或直接开放通用 root SSH。
6. SSH key 必须仅允许固定强制命令接收器，并关闭 PTY、端口/agent/X11 forwarding 和 user rc；若独立 SSH 登录账户使用 sudo，sudo 仅放行固定 root-owned 接收器且只传递严格校验的协议字段，不能开放 shell、任意 env、任意脚本或通用 sudo。SSH 执行域和 key 限制由拥有者安全核验，此仓库不会替其自动安装。
7. 使用模拟库/独立测试实例验证真实 receiver/PM2/权限、失败回退、重启持久化和公网资源，再走一次真实 main 发布，核对 workflow SHA/artifact SHA256、backup inventory、health 精确 revision、公网首页 JS/CSS 的 artifact hash。完成后才能声称自动发布已接通。不要故意破坏生产来验证回滚。

模板缺值会明确失败，不会以绿色空操作冒充部署。

## 数据、迁移与回退

普通发布遵循固定序列：

1. 有界接收 tar.gz，检验 SHA256、完整 SHA、allowlist 和逐文件 hash；拒绝路径逃逸、链接、重复项、额外文件、数据库/环境配置。
2. 在新的 immutable release 目录安装 offline 依赖、核验设置中的数据库路径和生产模式；保留 shared state/env，冻结代码 owner/mode；先验证旧版本健康和资源。
3. 停止 `qunxue-api` 并确认旧写入者已退出。要求所有数据库写入者都已盘点并由此 stop 涵盖；若有 cron、外部 worker 或手工 writer，不得把模板确认项设 true，先单独设计 quiesce adapter。
4. 对显式三个 SQLite 使用 Online Backup API，包含 WAL 中已提交内容；做 integrity/FK 检查、记录每个原表计数及原文件 uid/gid/mode，backup 本身 0600，目录 0700。快照在 writer 全停下后顺序完成，三库间状态一致。
5. 先对主库最终快照的隔离副本演练升级，不启动应用/model worker。固定数据库驱动仅提供明确 SQLite URL，不加载生产 .env，audit guard 禁止 socket、子进程和生产秘密文件访问；当前 migration 环境经过隔离 schema 测试验证。检查 integrity/FK/原表计数。通过后只对原地 live DB 执行 `alembic upgrade head`，再次检查原表计数和 metadata。
6. 原子替换唯一 `current` symlink，保留其 owner/group。重启固定应用，要求本地 Nginx 和公共 HTTPS `/api/health` 的完整 revision、生产模式匹配，首页及全部构建 JS/CSS 的 SHA256 匹配；成功后 `pm2 save`。
7. 出错则切回旧代码并重启/验证原版本，数据库前向 schema 保留，绝不自动 downgrade、覆盖 live DB 或倒灌备份。新 release、最终快照、journal 保留，不自动 GC。失败回退自身失败会明确输出 operator intervention，禁止宣称健康。deploy 和人工 rollback 的 SIGTERM/HUP/INT 都进入恢复；恢复期间忽略重复信号，所有子进程和健康重试有超时边界；机器断电/SIGKILL 时 journal 阻止下一次发布，须人工诊断，不假装能捕获 SIGKILL。

`migration-policy.json` 每次必须准确列出相对当前部署的新增 migration（如 `versions/xxx.py`），无变化时为空。现有 migration 不可改/删；新迁移必须人工审计保证旧代码可在新 schema 上继续工作，并声明 `rollback_compatible: true`。控制器仅允许 literal 元数据、固定 alembic/sqlalchemy imports、create_table、非唯一 create_index、显式 nullable 且无约束的 add_column。拒绝 helpers/aliases/getattr/动态SQL/模块副作用/required列；其他形式全部要求单独维护发布。这一保守语法子集和计数检查不是任意生产语义的完整证明，review 仍须验证旧代码写入兼容性。拒绝意外原表计数变化，不自动执行破坏性收缩或数据变换。

采用 expand → 兼容代码发布 → 观察 → 后续另行批准 contract。删列/重命名/破坏性类型变更等必须走单独维护方案，不能只改布尔值硬塞到 CD。跨多个未部署提交的 migration policy 必须相对实际 active release 合并，不能只看 PR diff。

人工请求回退时固定协议为 `rollback <当前完整SHA> <上一次完整SHA>`，只允许最后一次成功发布的已验证 predecessor，校验兼容政策；仍只回退代码、保留当前数据和 schema。不提供任意 shell 输入或任意历史版本自动降库。若需恢复备份，停止所有写入者后由拥有者决定丢弃哪些发布后的写入，并按照备份记录 uid/gid/mode 单独恢复，不能当作常规自动 rollback。

## 验证与边界

本次可离线执行：

```bash
python3 -m unittest discover -s deploy/tests -v
python3 -m py_compile deploy/*.py
```

测试覆盖包校验/路径安全、SHA、owner/group/mode、三库及 WAL 快照、原表数据保留、migration 声明/破坏性操作、health/资产错配、失败自动回退、缺配置失败和无 PR secrets 的工作流门控；均为单 worker、synthetic fixture。完整 app 的 CI 检查由 workflow 在同一 commit 执行，不能把这些 deployment 测试冒充完整业务测试或真实生产演练。

官方依据：
- [GitHub deployment environments](https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments)
- [Immutable artifact uploads](https://github.com/actions/upload-artifact)
- [Python SQLite backup API](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.Connection.backup)

最近离线验证还包括现有完整 migration tree 在全新临时 SQLite 中通过固定 DB-only driver 升级至 20261002_0462（113 张表，integrity ok），没有创建 API 进程或模型调用。此数字是空库合成验证，不是三份生产库 211 张原表的重测。
