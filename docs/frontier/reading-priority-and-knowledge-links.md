# Reading evidence and knowledge release links

This module is read-only. It does not collect sources, run a model, write reviews,
create a knowledge release, or authorize publication.

## Public API and UI wiring

- `GET /api/frontier/records/{record_id}/reading-priority?as_of=YYYY-MM-DD`
- `GET /api/frontier/reading-priorities?q=...&as_of=...&readiness=abstract_supported&assessment_status=unassessed&min_academic_value=50&offset=0&limit=24`
- `GET /api/frontier/records/{record_id}/knowledge-links?as_of=YYYY-MM-DD`
- Existing record detail also accepts `as_of`.

All record-specific reads use `FrontierService.record(record_id, as_of=...)`.
Missing, withdrawn, obsolete, hidden and unavailable future records return 404.
Public record responses preserve the data integration worker's `public_record`
projection. Internal abstracts are never returned by the reading endpoints.

Import `FrontierRecordInsights` from the frontier module's public index:

```tsx
<FrontierRecordInsights recordId={record.id} asOf={asOf} />
```

Props are `{recordId: string; asOf?: string}`. A QueryClientProvider is required,
as in the existing application. The container loads both endpoints through the
SDK, rejects mismatched record IDs/version/hashes, and offers manual retry.
It does not enable interval or focus refresh. The UI worker owns layout wiring.
Independent presentational components accept the product projections produced by
`readingInsightsApi.ts`; their props do not expose raw generated DTOs.
`readReadingPriorities` is available through the public facade
`readingPriorityAccess.ts` and returns product projections with pagination.

## What reading priority means

`passage_supported`, `abstract_supported`, and `metadata_only` describe located
source evidence readiness, in that order. Ties use supported-field count, then
record ID. Field count is a reading preparation aid, never an academic quality
score. The API exposes the sort basis, supporting fields, source URL/locator,
record version/hash, and missing field reasons.

Located excerpts must match the source snapshot ID/hash, block ID, locator, URL
and retained text. Approved `assistant_abstract_reading` notes take a separate
path: their raw source abstract must match the UTF-8 SHA256 recorded for the note
and the original bound snapshot. Each displayed statement must match a public
field and cite a valid abstract evidence index. Only the self-written statement
is returned, labeled as an abstract reading note; the internal abstract remains
private. These notes are not peer review and never make a scholarly score.

## Academic rubric

The existing draft weights remain: question significance 15, contribution
increment 30, warrantedness 25, scope/limits 15, scholarly dialogue 15. They are
project policy, not scholarly consensus or model understanding.

Optional trusted stored `value_assessment` facts contain `track`,
`evidence_readiness`, and `ratings` by criterion. Scores range from 0 through 4;
each needs a rationale and evidence `{record_id, version, snapshot_hash,
locator, reviewed_by}`. The evaluator checks the current version/hash and
retained passage. Full-text passage readiness is required. No write endpoint,
review workflow or synthetic ratings are added.

Without all supported ratings the total stays null. Unknown is not zero and
partial weights are not renormalized. Responses include `unassessed`, `partial`
or `assessed`, criterion weights, rationale/evidence, and missing reasons.
Any numeric threshold filter excludes unassessed/partial totals. Current real
abstract reading notes remain academically unassessed. Score arithmetic is
verified only with clearly identified test review fixtures.

## Knowledge release contract

`KnowledgeCatalog.existing_release(purpose=BROWSE)` returns an existing browse
release or None, without lazy preview publishing. Existing `current_release`
behavior is retained for compatibility with the knowledge module's other users.
Alternative catalog implementations must implement the new read-only method.

The link response adds record version/hash, nullable release ID/hash/level,
`status`, and limitations. States are `ready`, `no_release`, `no_topics`,
`no_matches`, and `low_evidence`. A low-evidence item may provide topic metadata
reading leads, never a claimed theoretical relationship. Queries and all entry
versions are pinned to the same release; the application verifies every page's
release identity. It checks browse eligibility and returns at most ten entries
from up to six topic queries, each retrieving its first twenty matches.

Navigation includes the exact `knowledge_release_id`. `as_of` gates the frontier
record's availability; the knowledge release is the currently existing browse
release, not a reconstructed historical release. Relationships remain
`reading_lead` / `topic_lexical_retrieval`, not evidence of theory applicability,
quality, causal effects or a need to update stable knowledge.

## Merge dependencies

This patch excludes the trend worker's `service.py`/`periods.py` and the data
worker's presenter, source-host additions and repository fixes. Integrate those
first. The required service method is `record(record_id, *, as_of=None) -> dict`,
raising LookupError for unavailable records. Preserve the public presenter when
merging the routes. No database migration is required.

The frontier route/DTO/SDK increment also includes the trend worker's agreed
period coverage and measurement v2 fields. The trend worker supplies their
computation; this patch provides transport and generated types only.

## v1.1 review fix

Every mount of `FrontierRecordInsights` now re-reads both endpoints, including
reopening the same record and cutoff. Cached reading support is hidden until
the requests finish. Normal and error states offer manual refresh; no polling,
focus refresh or reconnect refresh is enabled. Props are unchanged.

Public reading results now return citation-only basis items: `snippet` remains
present for DTO compatibility but is always empty. Source locator, URL, hash,
fields and evidence readiness remain available. Internal source evidence is
unchanged and still used for binding and assessment. This independent output
projection prevents even a valid full-abstract snippet from escaping through
the reading endpoint. The component skips empty snippet paragraphs.
