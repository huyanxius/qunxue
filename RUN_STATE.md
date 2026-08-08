# RUN_STATE

- M6 stage A: Markdown 解析器已覆盖 C/E/V/M/P/H 与源目录元数据；当前文本解析出 2,860 条且无重复。D7 的 H088-H091 正文不在当前目录，未伪造。
- M6 stage B: SQLite preview 发布会持久化真实 Markdown、目录与导入溯源；相同内容复用 release，健康检查与当前发布接口返回同一真实 release。下一步：列表、搜索与详情。
- M6 stage C: 列表、搜索与详情已固定在 release 内；`browse_eligible=false` 不会泄漏。下一步：生成契约并接真实知识浏览前端。
- M6 stage D: OpenAPI 与生成 SDK 已随真实知识浏览接口同步（`7f8cb68`）；下一步：接入独立知识浏览前端。
- M1: PR #66 open, CI passed, independent review passed; awaiting user merge.
- M2: PR #58 open, CI passed, independent review passed; awaiting user merge.
- M3 stage A: direct input -> editable candidate -> confirmation -> refresh recovery is green on the stacked M2 baseline; confirmation updates the M2 progress projection and unconfirmed matching returns `phenomenon_unconfirmed`.
- M3 stage B: candidate edits append retrievable versions; confirmation freezes a SHA-256-addressed snapshot while updating M2 progress.
- M3 stage C: three built-in examples are migration-seeded and API-served; task creation and recovery retain the narrow seed theory id/name clue.
- M3 stage D: single pasted/TXT/DOCX material requires all four processing confirmations, runs synchronously, persists no complete source document, and restores 3-5 traceable candidates.
- M3 stage E: `/research/new` exposes direct input, one material, and the smart-topic placeholder; generated adapters restore candidate provenance, seed clues, evidence, and confirmation snapshots without opening the M4 boundary.
- M3 review repairs: candidate generation and edits advance the M2 task projection; only the first candidate may freeze the snapshot; DOCX XML expansion is bounded; the workspace no longer imports app UI; unchanged system candidates retain their source label.
- M3 focused verification: 12 backend intake/task tests, 9 frontend workspace/adapter tests, and the module-boundary check passed on the current review-fix head.
- M3 full verification: `make check` passed (89 backend tests, 58 frontend tests, boundary, lint, typecheck, build, and generated-drift checks); lint retains two pre-existing account warnings.
- M3 landscape runtime: direct example -> untouched confirmation -> refresh recovery -> M2 "我的研究" projection, plus pasted material -> three traceable candidates, passed at 1440x900 without horizontal overflow or browser console errors. Evidence: `docs/screenshots/m3-research-entry-landscape.jpg`, `docs/screenshots/m3-material-candidates-landscape.jpg`, and `docs/screenshots/m3-phenomenon-confirmation-landscape.jpg`.
- M3 independent acceptance: fresh Terra Max reviewer returned PASS after independently reviewing the full diff and rerunning `make check`; only the two pre-existing AccountProvider lint warnings remain.
- Next breakpoint: submit the stacked PR without merging it; it depends on the still-open M2 PR #58.
