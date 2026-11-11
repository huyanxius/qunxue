# 生产依赖公告检查

`Qunxue delivery` 在 PR 和 main push 选中后端或前端检查时，运行 `dependency_audit` 并把结果纳入 `Required checks`。发布事件沿用原有发布验证。Dependabot 继续每周检查 npm、uv 和 GitHub Actions。

扫描器读取 `frontend/package-lock.json` 和 `backend/uv.lock`，记录 SHA-256 并在退出前复核。前端使用 npm 公共 registry 的生产锁审计。后端用 uv 导出带哈希的生产闭包，由 pip-audit 在当前 Python 平台上查询 OSV。npm 日志列出锁中的安装路径，包含 npm 报告的间接影响关系。Python 日志列出 uv 导出中的直接上游包、公告 ID 和别名。

在 [例外清单](../.github/dependency-audit-exceptions.json) 中按生态、包、精确版本和单条公告 ID 登记。`advisories` 可列同范围、同理由和同截止日的多个 ID。OSV 报告的 ID 或别名均可匹配该包和版本的例外。每项附兼容验证理由及 `expires`。从截止日 `00:00 UTC` 起，仍命中的例外会阻断检查。新增或升级依赖时，复核相关例外并清理已修复条目。

在仓库根目录使用 Node 22、Python 3.12 和项目 CI 的 uv 版本复跑。

```sh
node --test tools/dependency-audit/check.test.mjs
audit_env=$(mktemp -d)
uv venv --python 3.12 "$audit_env"
uv pip sync --python "$audit_env/bin/python" --require-hashes --only-binary :all: tools/dependency-audit/pip-audit.lock
PATH="$audit_env/bin:$PATH" node tools/dependency-audit/check.mjs
```

退出码 `0` 表示通过，`1` 表示存在未登记或已过期的命中，`2` 表示扫描或配置失败。实时结果随公告源更新，固定样例用于复跑门禁规则。
