# Issue 189 document difference and export research

This note records the bounded implementation research for the existing research-document workbench. It is a decision record, not a new editor design.

## Facts and decisions

- Rich-text difference uses `prosemirror-changeset` against Tiptap/ProseMirror documents. The library represents insertions and deletions as document ranges, so heading, list, and mark boundaries remain available instead of flattening the document into one plain-text diff. The installed package is MIT-licensed. The former GitHub mirror is archived and points to the maintained upstream; its public API and changelog remain current for the installed 2.4 line. Source: [prosemirror-changeset](https://github.com/ProseMirror/prosemirror-changeset).
- Citation formatting uses `citeproc` directly. Citation.js was evaluated first, but its browser bundle imports `node-fetch` and failed in the real Vite workbench with a `node:util.promisify` browser-external runtime error. Direct `citeproc` keeps the same CSL processor without that Node-only path. The workbench supplies CSL-JSON only through a metadata resolver port; missing metadata stays `needs_verification` and is never synthesized from a source ID. The pinned package declares `CPAL-1.0 OR AGPL-1.0`, which must remain visible in distribution compliance work. Sources: [Citation.js](https://github.com/citation-js/citation-js), [citeproc package metadata](https://github.com/Juris-M/citeproc-js/blob/master/package.json).
- ASA, GB/T 7714 author-date, Chicago author-date, and `zh-CN` locale data come from the official CSL repositories. Formatting punctuation is therefore produced by CSL rather than handwritten application rules. Official styles and locales are CC BY-SA 3.0; their embedded author, contributor, rights, and license metadata is retained. Source: [official CSL styles](https://github.com/citation-style-language/styles).
- DOCX output uses the browser-capable `docx` package and produces an OOXML ZIP package, not HTML renamed to `.docx`. The package is MIT-licensed. Source: [docx repository](https://github.com/dolanmiu/docx).
- PDF output deliberately reuses the same HTML print preview as the formal document and delegates PDF creation to the browser print dialog. This avoids a second layout engine and server-side font/runtime deployment. The audit export remains a separate JSON file from the exact version manifest.
- Chinese print defaults follow W3C CLREQ constraints relevant to this surface: CJK-capable font fallbacks, solid Han composition, two-character paragraph indentation, justified text, and widow/orphan protection. Source: [W3C Requirements for Chinese Text Layout](https://www.w3.org/TR/clreq/).
- ASA uses US Letter and one-inch margins; the Chinese social-science template uses A4 and CJK font fallbacks. Custom CSL XML and print CSS are stored with the immutable document version so old exports are reproducible after reload.

## Deployment and validation boundary

All selected capabilities run in the existing frontend build and require no office suite, Pandoc, LaTeX, or server-side browser. The mixed-language fixtures in `frontend/src/modules/research-document/model/documentExport.test.ts` validate Chinese and English bibliography data, printable HTML, unresolved citations, and a real DOCX package signature. `documentDiff.test.ts` validates local replacements without collapsing headings or list structure.

The document model stores stable citation source IDs, source versions, locators, and verification states only. Literature metadata remains owned by Issue 183 and confirmed analysis remains owned by Issue 186; this module consumes both through adapter-shaped inputs rather than copying either domain model.
