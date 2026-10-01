# Offline corpus import

The committed `backend/data/frontier-closeout.json` is public metadata for 861 canonical research studies and 2738 practice records. It omits original source abstracts, raw responses and evidence snippets. It is not the deployment evidence package.

Use the separately delivered private `qunxue-private-runtime-import.tar.gz` for runtime imports. Package SHA256: `aedf443ba7fbe06af6ca3ed32501b16bc94c4b88f23b2f6c21576d49753b3255`. Its corpus canonical SHA256 is `40900786b0b32fc2704b20f439f5b95920fec5b8f795e1c3ea45399dd03ae43a`. Public metadata and private corpus have the same record identity manifest SHA256 `21ef769e344c42c433f17a50bdd6a8f9ad4b82c47c21b82ee3bb8d3c875b3694`.

Extract that package into a private directory outside Git. Migrate an explicitly designated SQLite database first, then use the importer with a fresh backup path:

```sh
python backend/scripts/import_frontier_closeout.py \
  "$QUNXUE_RUNTIME_DIR/frontier-closeout.json" \
  --audit "$QUNXUE_RUNTIME_DIR/frontier-closeout-audit.json" \
  --database "$QUNXUE_IMPORT_DATABASE" \
  --backup "$QUNXUE_IMPORT_BACKUP"
```

The importer never chooses a production database from Settings. It takes a consistent SQLite backup before import. First import created 3607 records and reconciled 8 duplicate identities; replay created 0 records and 0 versions, leaving all 3607 unchanged. Eight incomplete source entries remain blocked manual-review jobs and cannot be resumed into the automated worker queue. They are not published records.

Only the three hash-checked, self-written reading notes are abstract-supported reading summaries. Public metadata alone cannot establish abstract support. Publication issue precision stays issue-only; annual fixed issue coverage never supplies a fabricated month or day. The repository's existing pre-reviewed theory bundle provides the test knowledge release and does not represent expert final review.

See `verification-closeout.json` for full checks and exact baseline failure comparisons. The full backend suite is not green: its 54 failures were all reproduced on clean main with the same locked dependencies and test fixtures. Do not describe isolated tests or builds as browser acceptance or model execution.
