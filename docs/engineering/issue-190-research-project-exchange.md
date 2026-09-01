# Issue 190 research-project exchange and archive decisions

This note records the bounded standards and interoperability decisions for the
project exchange boundary. It does not redefine facts owned by materials,
analysis, research-cycle, theory, method, or document modules.

## Standard, version, and license

- The exchange format is **REFI-QDA Project 1.0**, released on 2019-03-18. A
  `.qdpx` file is a ZIP package containing `project.qde` and any internal source
  payloads. The XML namespace is `urn:QDA-XML:project:1.0`. The exact XSD is
  bundled at `backend/src/qunxue_api/modules/research_exchange/resources/Project.xsd`
  and mirrored from
  [openqda/refi-tools](https://github.com/openqda/refi-tools/blob/main/docs/schemas/project/v1.0/Project.xsd).
- REFI specification documents are copyright QDAsoftware.org and distributed
  under the MIT license according to the
  [REFI tools license notice](https://github.com/openqda/refi-tools/blob/main/docs/index.md).
  The implementation does not add private XML elements or claim a new QDA
  standard.
- The official [REFI-QDA project page](https://www.qdasoftware.org/project)
  explicitly says the current version does not enable cross-tool round trips.
  A valid XSD document therefore proves schema conformance, not semantic
  preservation by every QDA product.
- The native preservation wrapper follows
  [BagIt 1.0 / RFC 8493](https://datatracker.ietf.org/doc/html/rfc8493): SHA-256
  payload and tag manifests make corruption detectable without changing QDPX.

## Mapping and loss policy

| Qunxue public fact | REFI-QDA Project 1.0 mapping | Native preservation and declared loss |
| --- | --- | --- |
| Project title and description | `Project@name`, `Project@origin`, `Description` | Stable task UUID and task version stay in `data/project.json`; REFI Project has no project GUID. |
| Researcher UUID | `User@guid` | Account and authorization facts are not exported. |
| Material UUID and current proven text | `TextSource@guid`, internal plain-text payload | Original blob is also stored under `data/materials/<material-id>/original`; filename, MIME type, checksum, parse history, deletion state and permissions remain in native JSON. |
| Published audio/video transcript | Current transcript blocks become a `TextSource` with stable material GUID | Original media remains in the native archive; timecodes, speakers, transcript-version source/provider and processing policy are named losses. The adapter does not invent an audio/video transcript binding. |
| Current source-pinned annotation | `PlainTextSelection@guid` with absolute half-open offsets | Segment ID, locator, parse UUID/version, quote hash and analysis status remain in native JSON. Tombstoned, stale or mismatched selections are omitted with a blocking loss item. |
| Confirmed analysis code | Hierarchical `Code` and `Coding` | Candidate/rejected state, native version, rationale and structured codebook rules remain in native JSON. Unconfirmed codes are not promoted into formal QDPX codes. |
| Analysis memo | `Note` plus standard references | Candidate/confirmed state and version history remain in native JSON. |
| Research case and scalar attributes | `Case`, typed `Variable`, `VariableValue`, source/selection references | Unsupported or lossy scalar typing is reported by the QDPX writer. |
| Material collection and relation | `Set` and `Link` | Relation notes and native organization metadata remain in native JSON. |
| Research-cycle snapshots | No equivalent | All published `research-cycle-v1` versions stay under `extensions.research_cycle_versions` and generate a loss item when present. |
| Formal research documents | No equivalent | Latest public document snapshots are retained as JSON; confirmed versions also receive Markdown artifacts. Formatting and citation audit remain native. |
| Future module snapshots | No guessed mapping | Only a named, published adapter may add an extension snapshot. Unknown or unpublished objects are never introspected, merged, or rebound. |

Every recoverable non-QDPX field is named in `data/reports/exchange-loss.json`
and its Markdown rendering. A field that cannot be safely represented or
recovered is marked `blocking`; recoverable semantic narrowing is marked
`warning`. The archive retains stable native IDs exactly and records the REFI
GUID used for each exported object.

## Import and migration boundaries

- QDPX import currently performs safe ZIP inspection, official-XSD validation,
  parsing and a content-count preview. It writes an exchange run and append-only
  `project.import_previewed` audit event, but it does **not** restore, merge,
  reparse, deduplicate, or guess bindings in an existing project.
- Archive export writes a completed exchange run plus a `project.exported`
  event containing the exact task version and loss counts. The event is also
  included in the exported audit NDJSON.
- Migration `20260901_0190` extends the then-current single Alembic head
  `20260901_0188`. It only adds exchange-run and append-only audit storage; it
  does not rewrite existing research rows. Existing projects therefore open
  unchanged after upgrade.

## Evidence levels

1. **Official-XSD validation**: `xmlschema` validates `project.qde` against the
   bundled Project 1.0 XSD.
2. **Implementation round trip**: export then import preserves the supported
   REFI objects and stable GUIDs inside this implementation.
3. **Committed social-research fixture**:
   `backend/tests/fixtures/qdpx/community-care-interview.qdpx` contains a
   Chinese interview, selection, hierarchical codes, coding, memo, typed case
   and set. It is synthetic and contains no participant data.
4. **Compatible-tool evidence**: QualCoder documents project import/export as
   functional but experimental and lists known losses for sets, graphs, data
   types, relative files and some cross-tool offsets. See its
   [import/export documentation](https://github.com/ccbogel/QualCoder/wiki/6.1.-Imports-and-Exports)
   and [REFI implementation](https://github.com/ccbogel/QualCoder/blob/master/src/qualcoder/refi.py).
   The committed fixture was imported through that implementation at commit
   `4c1d9e20adb118db197acb7873ff17c8ab86e4a4` in an isolated, headless
   QualCoder project. Queries against QualCoder's resulting SQLite database
   confirmed the source text, two-level code hierarchy, coded span and offsets,
   case, two typed values, memo, and source-set attribute. This is genuine
   compatible-tool import evidence for that fixture and commit; it does not
   prove export back from QualCoder, round-trip identity, GUI behavior, or any
   other QDA product. The exercise also established why Qunxue writes standard
   `internal://` source members instead of relying on the XSD-valid inline text
   representation that this QualCoder importer does not consume.

The archive and UI use these evidence levels verbatim. They must not describe
schema validation or self-round-trip as verified cross-tool interoperability.
