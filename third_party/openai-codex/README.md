# OpenAI Codex memory prompt reuse

Upstream: https://github.com/openai/codex/tree/2bd71f96d41809b95ea881429a1b68eb48d089b6

The hygiene and minimum-signal sections in `backend/src/qunxue_api/adapters/research_agent/prompts/memory_extraction.md` are copied from `codex-rs/memories/write/templates/memories/stage_one_system.md`. The empty-output schema is adapted, and Qunxue-specific scope/source rules are appended. Copyright and Apache-2.0 license are retained here.

The Python implementation follows the upstream incremental cursor, lease, no-output and authoritative-correction design. It does not embed or depend on the Codex runtime. SQL transactions replace its local file/Git consolidation workflow.
