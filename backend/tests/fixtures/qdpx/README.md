# QDPX interoperability fixture

`community-care-interview.qdpx` is a deterministic, synthetic social-research
project used for schema, import and compatible-tool checks. It contains one
Chinese interview source, one quoted selection, a hierarchical code, a coding,
an analytic memo, a typed case and a set. It contains no participant data.

Regenerate it from the repository root with:

```bash
cd backend
uv run python scripts/generate_qdpx_fixture.py
```

Passing the repository's XSD and self-import tests proves only conformance to
the bundled REFI-QDA Project 1.0 schema and this implementation's round trip.
Compatible-tool evidence must be recorded separately.
