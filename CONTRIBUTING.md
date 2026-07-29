# 参与开发

仓库采用 `Issue → 分支 → 原子提交 → PR → Review → main` 的协作流程。每次只处理一个边界明确的 Issue，未写进 Issue 的改动不要顺手带入。

## 领取任务

1. 从 [GitHub Issues](https://github.com/huyanxius/qunxue/issues) 领取或确认任务。
2. 阅读 Issue 的目标、范围、不做什么和验收标准；信息不完整时先补设计，不直接写代码。
3. 更新本地 `main`，再按任务类型创建分支：

```bash
git switch main
git pull --ff-only
git switch -c <type>/<issue-number>-<short-name>
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
make check
```

生成结果必须与后端变更一同提交。若只改前端，不要修改生成目录来绕过类型错误。

## 提交

提交格式为：

```text
type(scope): 中文说明
```

一个提交只承担一个逻辑单元。依赖、实现、测试、文档和纯格式化改动能独立审查时应分别提交。提交信息不加助手署名、`Co-Authored-By` 或工具名称尾注。

提交前至少执行与改动相关的检查；准备 PR 前执行完整检查：

```bash
make check
git status --short
```

## Pull Request

PR 必须关联对应 Issue，例如 `Closes #24`，并写清：

- 改了什么；
- 为什么这样改；
- 实际执行了哪些验证；
- 是否改变模块边界、公共契约或迁移；
- 核心模块使用编程助手时，关键指令摘要和人工检查情况。

PR 保持小而聚焦，合并前至少由一位队友 Review。作者需要能够解释主要改动、边界和失败后的处理方式。禁止直接推送 `main`，禁止 force push。
