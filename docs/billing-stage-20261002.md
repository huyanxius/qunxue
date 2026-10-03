# Billing implementation stage, 2026-10-02

This patch changes backend billing only. No production configuration, deployment,
credentials, frontend, historical balance or old ledger rows are changed.

## Reviewable sequence

1. Direct raw-usage compatibility fix and synthetic SDK stream fixtures.
2. Additive financial-evidence migration, exact price calculation and durable
   reservations; no retrospective debit or change to welcome/redemption amounts.
3. Bind real Agent/planner/tool/research requests and standalone Chat workers to
   the durable meter. Extend the account response without a new UI.
4. Cloud integration review, generated contract check and explicit activation
   decisions. Production deployment remains owned by the existing release thread.

## Implemented lifecycle

Every actual SDK HTTP attempt records route, endpoint, provider host, requested
and returned model, reasoning effort/service tier, receipt ID and numeric usage.
The fingerprint is a hash of the final serialized wire payload, including system
instructions, complete history, function schemas and tool results. No prompt,
credential or provider error body enters the financial evidence.

The compatibility mapper avoids the installed pydantic-ai/genai-prices
`output_reasoning_tokens` exception. Reasoning is already inside output. Input is
partitioned into ordinary input, cache read and cache write; final cumulative
stream usage is used once. Missing or contradictory usage remains unknown.

A short SQLite `BEGIN IMMEDIATE` transaction freezes available points before
network dispatch. No DB write transaction spans HTTP. Per-attempt, per-operation,
attempt-count and daily reference-cost budgets are finite. Final wire bytes give a
conservative input estimate; output has a provider hard cap and SDK retries are
zero. These estimates are not a mathematical input-token or supplier-cash bound.
An actual overrun is retained at full reference cost and the operation is waived.

Successful necessary attempts settle after application persistence. Failed-attempt
risk continues to consume the operator operation/day budgets, while user-fund
checks cover billable successes and in-flight attempts. A failed primary cannot
consume the funds needed for an affordable successful fallback. Failed
attempts, output-validation retries, length/refusal without delivery and cancelled
operations are operator-funded. A whole operation failure refunds its exact
original numerator, including any previously settled amount. Repeated settlement
or refund cannot double charge. A reused run ID cannot resend paid HTTP.

Price snapshots include explicit aliases, rate version, USD-to-credit coefficient,
cache omission policy and DeepSeek dispatch/calendar choice. Integer picoUSD and
per-user cumulative credit numerators preserve fractions: a synthetic 27.7-point
operation repeated ten times debits 277 points. Historical balances/ledger remain
readable. Redemption acquires the SQLite writer lock before reading holds or claiming a
code; the existing balance reset is refused while new holds are active, preserving the existing gift policy while preventing lost freezes.

Stale active operations are waived after a 30-minute inactivity cutoff on process
startup. Unknown attempts retain operator risk across days and process restarts;
late usage can reconcile evidence but cannot recharge a waived user. Cross-process
competing reservations serialize through SQLite. Receipt identity is unique per
provider host and duplicate/ambiguous receipts fail closed.

## Configuration and compatibility decisions before activation

Use the existing product environment prefix (`QUNXUE_` or `EVERPLAIN_`). No K or
money-cap production default is supplied. Required: `BILLING_CREDITS_PER_USD`,
`BILLING_PRICE_VERSION`, `BILLING_MAX_ATTEMPT_USD_MICRO`,
`BILLING_MAX_OPERATION_USD_MICRO`, `BILLING_DAILY_BUDGET_USD_MICRO`.
`BILLING_MAX_ATTEMPTS` defaults to 64. Aliases are explicit
`BILLING_MODEL_ALIASES` JSON; old model IDs have no inferred price.

`BILLING_PHASE_POLICIES` JSON explicitly chooses `user` or `operator` for
`memory_learning`, `memory_overview`, `course_knowledge`, and `model_probe`.
Probes must be operator-funded. Everplain optional `graph_topic_naming` also requires
an explicit `operator` policy. Missing configuration skips this naming phase and
keeps source-document labels and the rest of the graph; embedding/index behavior
is preserved. Omitted policies block the other Chat phases before
HTTP. The normal Agent turn is user-funded, respecting existing admin exemptions;
admin requests still record all usage/cost and obey operator risk budgets.
Everplain's explicit zero-key development fallback remains a mock.

For priced cache subtypes the production receipt needs cache-read/write counters.
An endpoint contract that omits these *only when they are zero* can be explicitly
configured with `BILLING_USAGE_POLICIES` JSON, key `provider-host:requested-model`,
value `omitted_cache_subsets_are_zero`. No universal omission-to-zero rule applies
to paid settlement. Pure legacy SDK usage extraction retains its compatibility
behavior. DeepSeek requires the hit/miss partition and agrees with nested cache
counts. Paid mismatched/missing model identity, unknown prices and nonstandard
service tiers are recorded as pending/error and never treated as free success.

DeepSeek reference billing additionally requires `BILLING_DEEPSEEK_TIME_BASIS`
`server_dispatch_at` and `BILLING_CALENDAR_VERSION`
`cn-public-holidays-2026-state-council-2025-7-v1`. This is an explicit product
reference-time policy, not a claim about the vendor's cash billing clock. Missing
2027 calendar fails closed. Reservations use peak rates. Standard OpenAI rates
and the >272000 full-request multiplier follow the supplied parent contract.

The paid health probe now requires an operator scope and known tariff/configuration;
an unconfigured probe cannot silently spend. Legacy synchronous Chat calls made
inside an Agent/tool operation are metered before raw HTTP. The mounted standalone phenomenon extraction API in both products, and theory
matching/candidate retry APIs in qunxue, now open a user-funded `user_research` operation after authentication
and ownership checks. Cached business replays return before a new hold or HTTP
attempt. These user actions cannot be made operator-funded by phase configuration;
existing administrator exemptions still retain usage and risk records. Dormant or
unowned direct adapter calls remain guarded before paid HTTP.

## Coverage and known limits

| Path | Stage behavior |
| --- | --- |
| Agent answer, planner, streaming, routed fallback, nested Chat tools/research | One operation, actual per-attempt meter |
| Memory extraction/overview | Scope covers validation and persistence; explicit phase policy |
| Course knowledge batches, parallel batches and fallback validation | Per-job scope, per-task last attempt, preserved bounded worker/checkpoints |
| Paid Chat probe | Operator scope, real receipt required |
| Everplain GraphTopicNamer | Optional operator-only scope, real route/receipt/cost; missing configuration skips naming and preserves source labels/graph |
| Vision/OCR and other multimodal paths | Outside strict text-estimate coverage; this Chat meter rejects non-text content before HTTP, existing separate bounded operator vision behavior remains outside new user charges |
| Legacy Chat inside operation | Same raw-HTTP meter |
| Existing mounted standalone phenomenon extraction (both), matching and retry (qunxue) APIs | Authenticated user scope, same finite budgets, actual legacy HTTP route/receipt, persistence before settlement |
| Dormant/unowned direct legacy Chat calls | Still blocked before HTTP; no inferred owner or operator subsidy |
| Embedding/rerank/course index, frontier encoders/models, transcription and web services | Existing bounded operator behavior preserved; outside this Chat credit patch, no new user charges or fabricated tariffs |

Official user-reference amounts and procurement cash cost are separate fields.
Cash rate/contract evidence has not been supplied: `procurement_cost_pico` remains
NULL and `procurement_status` remains `pending`, even with valid user-reference
usage. This patch provides no cash reconciliation UI or claim of supplier-cash
budget enforcement. It exposes all new Chat attempts and their outcomes through
`GET /api/account/credits`; frontend consumers must honor `pricing.mode` and must
not present obsolete token denominators as the model-rate formula. Frontend and
generated OpenAPI/types are intentionally left to the parent integration owner.

Unknown provider receipts retain risk and numeric evidence. There is no automatic
upstream receipt lookup and no safe resend after a crashed/ambiguous HTTP attempt.
An operator reconciler can use the durable attempt methods; late receipts remain
user-waived. Complete process-kill/SQL persistence fault-injection and application
schema/API integration are still cloud review requirements.

## Review corrections in v2

The independent review's four exact fixtures reproduced two P0 defects in v1.
The metered stream now implements the SDK asynchronous context manager and retains
terminal `length`/`content_filter` reasons across the final empty-choices usage
frame. Both rejected outputs retain the full operator reference cost and waive
the user. Redemption now holds the same SQLite writer lock as reservations before
checking freezes, eliminating the check-then-reset race. A real waiting writer
also progresses after redemption commits and sees the new balance.

The final memory overview snapshot check is inside the paid scope before
settlement; stale results retain the existing HTTP 409 and refund. Memory merge
reports a lost lease rather than silently succeeding; course final persistence
checks its job fencing row count. Both losing workers remain operator-funded.
An unconfigured course billing phase marks the claimed job failed and releases its
job token, rather than leaving it running until another lease timeout.

New public billing errors use the existing safe JSON/SSE envelope. Insufficient
credits are 402, frozen credits/replay are 409, budget limits are 429,
unconfigured/unknown prices are 503, and unconfirmed provider cost/output is 502.
The SSE response retains `turn_failed`, with the same safe error information;
underlying provider error strings are not sent to the user. The old account test
keeps its 100/25/grant/ledger checks and explicitly asserts the added pricing mode,
version/coefficient/currency fields.

Optional Everplain topic naming now records its real route, model, cache counters
and reference cost under an operator-only scope. Invalid naming output retains
the cost and does not debit users. Missing configuration makes no naming HTTP
request and preserves document clustering and source-title labels. Vision and
multimodal usage are not claimed to be strictly bounded by the text input estimate.

## Validation at freeze

Synthetic-only tests cover the installed SDK compatibility, stream terminal and
conflicting usage, cache partition, exact prices, long context, DeepSeek calendar,
freeze contention across SQLite connections, settlement/refund idempotency,
stale/restart unknown risk, late receipts, model/tier mismatch, overruns, admin
costs, actual fake HTTP primary/fallback, application finalization failure,
operator probes, background persistence failure and additive migration history.

The Mac test environment is a reused existing venv; no package install or paid
HTTP has been made. Sparse checkout omits knowledge catalog assets. Existing
integration tests needing those assets or binding a localhost HTTP server could
not complete under this sandbox and are delegated to cloud. No frontend/build or
production process was started. Disk reached zero briefly; the interrupted empty
migration fixture was recreated and the resulting migration test subsequently
passed.
