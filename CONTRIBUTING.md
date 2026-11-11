# 参与开发

仓库采用 `Issue → 分支 → 原子提交 → PR → 验证 → main` 的协作流程。每次只处理一个边界明确的 Issue，未写进 Issue 的改动不要顺手带入。

## 领取任务

1. 从 [GitHub Issues](https://github.com/huyanxius/qunxue/issues) 领取或确认任务。
2. 阅读 Issue 的目标、范围、不做什么和验收标准；信息不完整时先补设计，不直接写代码。
3. 从最新 `origin/main` 创建工作分支。

```bash
git fetch origin main
git switch -c <type>/<issue-number>-<short-name> origin/main
```

常用类型为 `feat`、`fix`、`refactor`、`docs`、`test`、`build` 和 `ci`。分支说明使用小写英文和连字符，例如 `docs/24-team-onboarding`。

## 开发边界

- 先读 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)，只从模块公共入口使用其他模块。
- 后端跨模块从 `modules/<name>/__init__.py` 导入；前端从 `modules/<name>/index.ts` 导入。
- `backend/openapi.json` 和 `frontend/src/api/generated/` 由契约生成，不手工修改。
- `.env`、API key、appid、数据库文件、依赖目录和构建产物不得提交。
- 旧 LiveDemo 只作历史参考，不复制其代码、资产或依赖。

## API 变更

先修改后端 Pydantic 契约或路由，再执行：

```bash
make contract
git diff -- backend/openapi.json frontend/src/api/generated
```

生成结果必须与后端变更一同提交。若只改前端，不要修改生成目录来绕过类型错误。

## 提交

提交格式为：

```text
type(scope): 中文说明
```

一个提交只承担一个逻辑单元。依赖、实现、测试、文档和纯格式化改动能独立审查时应分别提交。提交信息不加助手署名、`Co-Authored-By` 或工具名称尾注。

提交前执行与改动影响面匹配的检查，并用 `git status --short` 确认提交范围。CI 执行工作流为本次改动选中的检查。

## Pull Request

PR 必须关联对应 Issue，例如 `Closes #24`，并写清：

- 改了什么；
- 为什么这样改；
- 实际执行了哪些验证；
- 是否改变模块边界、公共契约或迁移；
- 核心模块使用编程助手时，关键指令摘要和人工检查情况。

PR 保持小而聚焦。作者需要能够解释主要改动、边界和失败后的处理方式。

## 合并规则

合并前，PR 分支必须包含最新 `main`。相关验证通过，且该版本的 CI 全部通过后，作者可以自行合并。队友 Review 为自愿。禁止直接推送 `main`，禁止 force push。

### main ruleset

`Required checks` 是 [`Qunxue delivery`](.github/workflows/delivery.yml) 的汇总作业。是否由 GitHub 强制执行，取决于对 `main` 生效的规则。仓库维护者可在 **Settings → Rules → Rulesets** 创建启用的 Branch ruleset，目标仅为 `main`，Bypass list 留空。开启 Require a pull request before merging，审批数设为 0，关闭 Code Owner 和最近一次 push 的强制审批。开启 Block force pushes，再把 GitHub Actions 的 `Required checks` 设为必需，勾选 Require branches to be up to date before merging。 [GitHub 配置说明](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/creating-rulesets-for-a-repository)

配置前后都可用以下只读命令核对。`15368` 是本仓库这项检查的 GitHub Actions `app.id`。第二条检查应在配置生效后返回 `true`。 [GitHub Rules API](https://docs.github.com/en/rest/repos/rules#get-rules-for-a-branch)

```bash
repo=huyanxius/qunxue
gh api "repos/$repo/branches/main" --jq '{protected, sha: .commit.sha}'
gh api "repos/$repo/rules/branches/main" | jq -e '
  any(.[]; .type == "pull_request")
  and all(.[] | select(.type == "pull_request");
    .parameters.required_approving_review_count == 0
    and (.parameters.require_code_owner_review != true)
    and (.parameters.require_last_push_approval != true))
  and any(.[]; .type == "non_fast_forward")
  and any(.[]; .type == "required_status_checks"
    and .parameters.strict_required_status_checks_policy == true
    and any(.parameters.required_status_checks[];
      .context == "Required checks" and .integration_id == 15368))
'
```

最后由有权读取 Bypass list 的维护者查询 `gh api "repos/$repo/rulesets/<id>"`，核对 `enforcement` 为 `active`、目标为 `refs/heads/main` 且 `bypass_actors` 为空。
