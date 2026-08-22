# 首批理论预审核发布包

`first-match-theories.pre-reviewed.json` 是可安装的 `pre-reviewed-theory-release/v1`
工件。用户已确认这三份理论档案由真实人员完成了初步审核，因此它们统一标记
`pre_review_completed`，并以 `approved_for_internal_match` 通过当前内测 MATCH
门禁。

这里的 `FINAL` 只表示发布字节不可变且可被任务固定，不代表专家终审或全面
审核。现有记录未提供初审者个人姓名、资质与实际完成时刻，所以工件中
`review_completed_at` 为 `null`，`recorded_at` 明确是用户确认该状态后进入
发布审计的时间。档案仍保留后续深度复核的边界。

每份档案都绑定了仓库知识条目版本、固定 profile 哈希、可访问的 HTTP(S)
原始文本、精确 locator、`verified` 来源状态和误用边界。数据包固定了
当前仓库内容可重现的 preview release；若知识 Markdown 发生变化，安装会拒绝
旧基线，必须重新核对内容和哈希，不会静默漂移。

## 干净数据库安装

```bash
cd backend
uv run alembic upgrade heads
uv run python scripts/install_pre_reviewed_theory_release.py \
  ../knowledge/review-packets/first-match-theories.pre-reviewed.json
```

安装器会先构建确定性 preview 基线，再验证预审核状态与准入决策、审核记录时间、
固定内容哈希、条目版本、竞争理论、来源的 HTTP(S) hostname 和 locator。相同
内容重复执行返回同一 immutable release。
