# 新成员 / AI 助手一键上手

把下面对应语言的整段话原样粘贴给你的 AI 编程助手（Cursor / Claude Code / Codex / WorkBuddy / TraeWorkCN）。

## 中文版

请帮我配置"群学致知"项目：克隆 https://github.com/huyan1349/qunxue.git 并进入目录（如果没有权限，提醒我先接受仓库邀请、完成 GitHub 登录）。根据仓库里实际有什么来安装环境：前端装依赖，后端建虚拟环境；有 .env.example 就复制为 .env 并告诉我要填哪些密钥，任何时候不许提交 .env。然后通读 README.md、CONTRIBUTING.md、AGENTS.md 和 docs/ 全部文档，用十行以内向我总结项目现状和我的任务大概落在哪。此后我让你做的一切改动：从最新 main 切分支，提交前自查无密钥无大文件，推分支后用 gh pr create 发 PR（写清改了什么、为什么改，关联 Issue），把 PR 链接给我并提醒我合并前需队友审查、我本人要能讲清改动。永远不碰 main，永远不 force push。

## English

Set up the "Qunxue" project for me: clone https://github.com/huyan1349/qunxue.git and cd in (if access fails, remind me to accept the repo invitation and log in via gh auth login). Install per what the repo actually contains: package install for the frontend, a virtualenv for the backend; if .env.example exists, copy it to .env and tell me which keys to fill — never commit .env. Then read README.md, CONTRIBUTING.md, AGENTS.md and everything in docs/, and summarize in ten lines what exists and where my task likely lives. For all future changes: branch off the latest main, self-check for secrets and large files before committing, push the branch and open a PR via gh pr create (state what changed and why, link the Issue), then hand me the PR link and remind me a teammate must review and I must be able to explain the change. Never touch main. Never force push.
