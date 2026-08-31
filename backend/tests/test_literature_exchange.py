from datetime import UTC, datetime
from uuid import UUID

from qunxue_api.modules.research_materials import (
    LiteratureEntry,
    LiteratureExchangeFormat,
    export_literature_entries,
    import_literature_entries,
)

NOW = datetime(2026, 8, 31, 12, tzinfo=UTC)


def test_imports_realistic_bibtex_and_ris_into_one_csl_shaped_boundary() -> None:
    bibtex = b"""@article{li2025care,
      title={Care after Migration},
      author={Li, Ming and Wang, Yan},
      year={2025},
      journal={Journal of Migration},
      doi={10.1234/ABC.1}
    }"""
    ris = b"""TY  - JOUR
TI  - Care after Migration
AU  - Li, Ming
PY  - 2025
DO  - 10.1234/ABC.1
ER  -
"""

    bib_records = import_literature_entries(LiteratureExchangeFormat.BIBTEX, bibtex)
    ris_records = import_literature_entries(LiteratureExchangeFormat.RIS, ris)

    assert bib_records[0].title == ris_records[0].title == "Care after Migration"
    assert bib_records[0].doi == ris_records[0].doi == "10.1234/abc.1"
    assert bib_records[0].csl_data["author"][0] == {"family": "Li", "given": "Ming"}


def test_csl_json_round_trip_preserves_identifiers_contributors_and_dates() -> None:
    entry = LiteratureEntry.create(
        literature_id=UUID(int=10),
        user_id=UUID(int=2),
        task_id=UUID(int=3),
        item_type="article-journal",
        title="Care after Migration",
        doi="10.1234/abc.1",
        csl_data={
            "id": "li2025care",
            "type": "article-journal",
            "title": "Care after Migration",
            "DOI": "10.1234/abc.1",
            "author": [{"family": "Li", "given": "Ming"}],
            "issued": {"date-parts": [[2025, 4]]},
        },
        now=NOW,
    )

    payload = export_literature_entries(LiteratureExchangeFormat.CSL_JSON, (entry,))
    imported = import_literature_entries(LiteratureExchangeFormat.CSL_JSON, payload)

    assert imported[0].csl_data["issued"] == {"date-parts": [[2025, 4]]}
    assert imported[0].csl_data["author"] == [{"family": "Li", "given": "Ming"}]
