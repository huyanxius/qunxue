# Issue 183: Professional research archive boundary

## Verified baseline

- `research_materials` already owns uploads, original blobs, append-only parse versions,
  stable segment locators, retrieval citations, deletion invalidation, and tombstones. This
  work extends that identity instead of creating another material store or parser.
- A literature entry is catalog metadata, while an attachment is an existing research
  material. One entry may therefore point to several attachments without copying either.
- Collections behave like playlists: the same material or literature entry can belong to
  several collections. Tags remain portable descriptive labels rather than folders.
- Duplicate detection only produces reviewable hints. DOI equality is strong evidence and
  normalized title/year similarity is weaker evidence; neither silently merges records.
- Manual reading is independent from model processing. Only material explicitly marked
  `external_allowed` may enter an external-model Agent context; legacy material without a
  profile keeps its previous behavior until it is cataloged.

## Standards and maintained implementations checked on 2026-08-31

| Source | Current fact | Decision here |
| --- | --- | --- |
| [CSL schema](https://github.com/citation-style-language/schema) | Official CSL-JSON schema, MIT licensed | Keep CSL-compatible literature metadata and support CSL-JSON exchange directly. |
| [DataCite Metadata Schema 4.6](https://schema.datacite.org/meta/kernel-4.6/) | Released 2024-12-05; defines identifiers, creators, resource types and typed relations | Preserve identifiers, contributors, dates, types and relations as structured metadata instead of flattening them into notes. |
| [RO-Crate 1.2](https://www.researchobject.org/ro-crate/specification/1.2/) | Apache-2.0 specification using schema.org JSON-LD for research objects | Use explicit material relations and JSON-valued case attributes; do not implement a second file package in this Issue. |
| [Zotero collections and tags](https://www.zotero.org/support/collections_and_tags) | One item can be in several collections without duplication; duplicates are reviewable candidates | Model collection membership as many-to-many and keep duplicate hints separate from merge. |
| [bibtexparser 1.4.4](https://pypi.org/project/bibtexparser/) | Stable PyPI release published 2026-01-29; BSD/LGPL dual licensing; active upstream | Use the stable 1.x API for BibTeX import/export rather than writing a parser. |
| [RISpy 0.10.0](https://pypi.org/project/rispy/) | Released 2025-05-23, Python 3.9+, MIT upstream, six open issues at review time | Use for RIS import/export rather than maintaining a local tag grammar. |
| [Crossref REST API](https://github.com/CrossRef/rest-api-doc) | Public DOI metadata endpoint; network availability is not guaranteed | Put DOI lookup behind an adapter and keep supplied metadata usable when lookup is unavailable. |

## Frozen public concepts

- `MaterialArchiveProfile`: research role, specific type, stage, batch, tags and ethics/model
  policy for one existing material ID.
- `MaterialBatch` and `MaterialCollection`: task-owned organization identities.
- `LiteratureEntry`: CSL-compatible bibliographic metadata plus attachment and collection IDs.
- `ResearchCase`: task-owned case identity with researcher-defined scalar attributes and
  many-to-many material membership.
- `MaterialRelation`: typed, directed relationship between two existing materials.

Transcription, codebooks, memos, comparison matrices, theories, manuscripts, Agents,
projects, parsers and vector indexes stay outside this boundary.
