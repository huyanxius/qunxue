# 群学自动生产发布（Issue #422）

## 增量路径（Issue #437）

现网兼容接收器保留现有运维身份和生产布局。GitHub production 缺少可用部署私钥时，门控保持关闭，不能报告自动上线成功。

检查按前后端变更分别运行并允许并行，只有生产发布保留串行锁。生产构建前通过固定 SSH `status` 协议读取真实 active manifest，累积比较实际已部署 commit 与目标 commit。文档或 CI 脚本变化不构建业务；前端变化不安装后端依赖。锁文件相同则沿用已验证 wheelhouse 与虚拟环境；锁文件变化时复用按锁摘要缓存的离线 wheelhouse。

version 2 差异包保留完整最终文件清单、每个 SHA256、实际基线与独立前后端 revision，tar 内只有变化字节。接收器逐一核验省略文件在基线中的摘要，独立复制已验证源文件，不允许路径逃逸或让新 release 的权限操作改变前一版本。前端只切 current，API PID 保留；后端才停止/重启 `qunxue-api`。现网 adapter 遇到新增迁移在停机前拒绝，交由单独审计维护；普通业务代码与前端更新不做三库备份。

`status` 只输出发布文件指纹，不返回配置或 secrets；接收器本身仍必须是预安装的固定可信文件，不能由应用差异包更新。旧 version 1 完整包保持兼容。完成真实生产三类改动及记录耗时、上传字节、PID 前后对照之前，不宣称满足十分钟目标。

公网请求明确标识为 `qunxue-deploy/1`。本地 HTML 及两端所有 JS/CSS 均要求精确摘要；公网首页仅允许一个空内容、官方固定来源及受限属性的 Cloudflare 分析脚本，移除这个已核验插入项后全部业务 HTML 字节仍须精确匹配。其他脚本、重复插入、inline 内容或业务差异均拒绝，不修改 CDN 设置。

状态：源码实现和隔离安全测试；**尚未完成 GitHub → 生产主机实链路验证**。
不得将 workflow 合并、上传 artifact 或本地测试通过描述成生产部署成功。

## 正常路径

`PR 无秘密检查 → main 同 commit 检查通过 → 不可变 artifact ID/文件 SHA256 → production 环境 → 固定接收器 → 按实际载荷切换受影响服务 → 私网/公网精确版本及资源校验`。

- `.github/workflows/delivery.yml` 取代旧 `ci.yml`。旧 workflow 曾被人工停用，不能把它说成代码失败；本变更不操作 Actions 开关、账号权限或 secrets。
- PR 不引用 production、不读生产 secret。GitHub token 仅 `contents: read`，checkout 不保存凭据；第三方 actions 固定完整 commit SHA。
- main 的部署依赖本次 `checks` 成功；生产 job 读取实际基线，只构建受影响前端或已变化的离线依赖。差异包直接从同一 job 的已检查提交生成，并保存不可变 artifact；发送前及服务器再次校验 SHA256 和 commit。没有 `pull_request_target` 或手动任意 ref/命令输入。
- GitHub 和服务器分别串行化；生产任务不取消正在运行的任务。GitHub concurrency 可能合并等待中的旧提交，已运行的部署不被新提交中断。
- 不要求新增 native branch protection，也不强制每次人工批准。遵循仓库 Issue→分支→PR→验证→作者自合并流程；production 环境限制仅 main，初次接通由拥有者安全批准。更严格分支/人工审批规则是可选策略。
- 数据库、`.env`、node_modules、密钥不进入 artifact。构建下载锁文件中 hash 约束的 binary wheels，服务器仅离线安装。目标为 Linux x86_64 / CPython 3.12；主机不兼容的 wheel 或未安装 Python 会在停止服务之前失败。
- 前端和元数据更新保留 API PID；只有实际后端文件或依赖锁指纹变化才停止单实例写入者，因此后端更新有维护间隙，不是零停机或蓝绿部署。没有注册账号、收费平台、模型调用或自动知识入库步骤。

## 现网接通（Issue #444）

现网使用 `legacy-root-pm2` 配置，通过同一个固定 `receiver.py` 入口调用 `legacy_receiver.py`。保留 `/root/qunxue-src`、`/var/www/qunxue` 两个发布指针、root PM2 `qunxue-api` 和现有 `backend/var`、私有 `.env`。无需新增账号、迁移数据目录或改 Nginx、DNS、Cloudflare。`/root/.qunxue-deploy` 仅保存私有发布元数据、锁和临时校验文件；应用代码仍在已有两处发布目录。

1. 从经过检查的 main 安装 root-owned 的 `receiver.py`、`legacy_receiver.py`、`payload_rules.py` 到 `/usr/local/libexec/qunxue/`，目录 0755、文件 0644，不能由 artifact 更新。固定入口为 `/usr/bin/python3.12 -I /usr/local/libexec/qunxue/receiver.py`。按主机已核验的 Python、PM2、现有 `.env` 和三个数据库真实路径填写 `/etc/qunxue/deploy.json`（root-owned 0600）；模板默认 `configured: false`。adapter 明确保留已有 root 应用身份，不把新增账户或隔离目录当作接通前提。
2. 固定协议 `status` 从实际两个指针及健康接口生成文件指纹，核验本地/公网 backend revision、运行模式和首页、JS/CSS 摘要后才保存基线。后续指针与元数据不一致会失败，不能把目标 commit 冒充已经部署的版本。状态不会输出私有配置、PM2 环境或数据库内容。
3. GitHub `production` 保持仅 main。普通变量 `DEPLOY_HOST`、`DEPLOY_USER` 对应已授权连接；独立核验的公开主机记录存入 `DEPLOY_KNOWN_HOSTS`。拥有者安全录入缺少的 `DEPLOY_SSH_KEY`，不在聊天中发送，不由助手读取或上传现有通用私钥。只有接收器、可用 CI 连接和实际验证就绪后才设 `PRODUCTION_CONFIGURED=true`；此前部署明确失败。

SSH 凭据应限制到固定接收器协议并关闭 PTY、端口/agent/X11 forwarding 和 user rc。发送端使用既有 ubuntu 身份和固定 sudo 接收器路径，不新装 wrapper 或扩大该身份权限；接收器仅接受严格验证的 `status` 或 `deploy <完整SHA> <SHA256>` 到固定 root-owned 接收器，不能让 payload 更新控制器或注入任意命令。凭据限制由拥有者核验，不自动创建或扩大权限。

安全录入后可以重跑最新 main 的失败 job，沿用同一 workflow 的检查、实际生产基线和不可变 artifact；无需第二条发版入口。

## 数据、迁移与回退

构建器与接收器共用完整文件清单和依赖锁指纹判断后端变化。项目说明元信息变化不推进后端 revision；锁指纹变化仍是依赖发布。

1. 有界接收差异 tar，核验完整 SHA、SHA256、allowlist、实际基线及每个复用文件摘要；拒绝路径逃逸、链接、数据库和私有配置。提前检查重建磁盘空间，失败不停止进程。
2. 前端变化只创建 `/var/www/qunxue-release-<完整SHA>` 并原子切换静态指针。API PID、源码指针和数据库均保留。无业务变化只更新已核验发布元数据，不切指针、不重启服务。
3. 后端变化才创建 `/root/qunxue-release-<完整SHA>`。依赖锁相同复用旧虚拟环境；锁变化才离线安装已锁定 wheelhouse。上线前核验既有主库路径和运行模式，链接原有 `.env`、整个 `var`；随后只停止/重启 `qunxue-api`，保留原 PM2 参数和服务器内私有环境。
4. 现网 adapter 拒绝修改/删除既有 migration，也拒绝新增 migration，在切换或停止前失败。新增 schema 需另行审计维护发布；普通代码更新不备份数据库、不停其他服务。保留的隔离布局接收器兼容测试不能被描述成现网 migration 已执行。
5. 切换后核验本地/公网 backend 精确 revision、生产模式和首页全部 JS/CSS 摘要。成功才保存 active 元数据，后端变化才 `pm2 save`。失败只尝试一次切回本次受影响指针和旧 PM2 定义，再核验旧版本；不覆盖 live DB、不 downgrade、不倒灌备份。回退失败或断电/SIGKILL 的未完成 journal 要求人工诊断，下一次发布禁止越过它。

之前的 `/srv/qunxue` 隔离布局实现只保留兼容代码和合成测试，不是当前主机的接通要求；不得据此创建新身份或迁移现网。

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

## 锁定 sdist 的离线 wheel 构建修复

PyPI 的 bibtexparser 1.4.4 与 srt 3.5.3 只有 source distribution，`pip download --only-binary=:all:` 会阻止 main artifact 生成。CI现在先安装单独 SHA256 锁定的构建工具，再用 `pip wheel --require-hashes --no-deps --no-build-isolation` 从原始导出锁构建，不升级应用版本或重新解析依赖。

`build_wheelhouse.py` 验证当前平台所需包名/版本、wheel metadata和标签，基于实际wheel bytes生成部署requirements.lock及来源证明。不能把sdist hash误当作新wheel hash。服务器仍只有wheel、`--no-index --require-hashes`，不联网编译。原始backend/uv.lock的SHA256记入release manifest，来源导出锁hash与每个wheel hash记入随artifact保存的wheel-build-provenance.json。构建工具是CI工具，不进入应用锁版本。

PR/main 的发布安全测试使用合成离线包；生产 wheelhouse 按锁文件、构建工具锁与构建脚本摘要缓存，只有实际依赖锁变化且缓存未命中才重新构建。发布 artifact 和生产部署仅允许 main push。每次新 wheel 构建禁用 pip wheel 缓存，保证从 hash 核验后的源输入构建。可在临时虚拟环境用 `pip install --no-index --only-binary=:all: --require-hashes --find-links release/wheelhouse -r release/requirements.lock` 验证离线闭包。
