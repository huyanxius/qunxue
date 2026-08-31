"""BibTeX, RIS and CSL-JSON exchange through maintained format libraries."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

import bibtexparser
import rispy
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bwriter import BibTexWriter

from qunxue_api.modules.research_materials.professional import (
    ImportedLiteratureRecord,
    LiteratureEntry,
    LiteratureExchangeFormat,
    normalize_doi,
)


def import_literature_entries(
    exchange_format: LiteratureExchangeFormat,
    payload: bytes,
) -> tuple[ImportedLiteratureRecord, ...]:
    exchange_format = LiteratureExchangeFormat(exchange_format)
    text = payload.decode("utf-8-sig")
    if exchange_format is LiteratureExchangeFormat.CSL_JSON:
        raw = json.loads(text)
        values = raw if isinstance(raw, list) else [raw]
        return tuple(_from_csl(value) for value in values)
    if exchange_format is LiteratureExchangeFormat.BIBTEX:
        return tuple(_from_bibtex(value) for value in bibtexparser.loads(text).entries)
    return tuple(_from_ris(value) for value in rispy.loads(text))


def export_literature_entries(
    exchange_format: LiteratureExchangeFormat,
    entries: Sequence[LiteratureEntry],
) -> bytes:
    exchange_format = LiteratureExchangeFormat(exchange_format)
    if exchange_format is LiteratureExchangeFormat.CSL_JSON:
        return json.dumps(
            [entry.csl_data for entry in entries],
            ensure_ascii=False,
            indent=2,
        ).encode()
    if exchange_format is LiteratureExchangeFormat.BIBTEX:
        database = BibDatabase()
        database.entries = [_to_bibtex(entry, index=index) for index, entry in enumerate(entries)]
        return BibTexWriter().write(database).encode()
    return rispy.dumps([_to_ris(entry) for entry in entries]).encode()


def _from_csl(value: object) -> ImportedLiteratureRecord:
    if not isinstance(value, dict):
        raise ValueError("CSL-JSON entries must be objects")
    title = _required_text(value.get("title"), "title")
    item_type = _required_text(value.get("type"), "type")
    metadata = dict(value)
    doi = normalize_doi(_text(value.get("DOI")))
    if doi is not None:
        metadata["DOI"] = doi
    return ImportedLiteratureRecord(item_type, title, doi, metadata)


def _from_bibtex(value: Mapping[str, str]) -> ImportedLiteratureRecord:
    title = _required_text(value.get("title"), "title")
    item_type = _bibtex_to_csl_type(value.get("ENTRYTYPE", "misc"))
    metadata: dict[str, object] = {
        "id": value.get("ID", ""),
        "type": item_type,
        "title": title,
    }
    authors = _bibtex_names(value.get("author"))
    if authors:
        metadata["author"] = authors
    year = value.get("year")
    if year and year.isdigit():
        metadata["issued"] = {"date-parts": [[int(year)]]}
    fields = (("journal", "container-title"), ("publisher", "publisher"), ("url", "URL"))
    for source, target in fields:
        if value.get(source):
            metadata[target] = value[source]
    doi = normalize_doi(value.get("doi"))
    if doi is not None:
        metadata["DOI"] = doi
    return ImportedLiteratureRecord(item_type, title, doi, metadata)


def _from_ris(value: Mapping[str, object]) -> ImportedLiteratureRecord:
    title = _required_text(value.get("title") or value.get("primary_title"), "title")
    item_type = _ris_to_csl_type(_text(value.get("type_of_reference")) or "GEN")
    metadata: dict[str, object] = {"type": item_type, "title": title}
    authors = value.get("authors") or value.get("first_authors")
    if isinstance(authors, list):
        metadata["author"] = [_split_name(str(name)) for name in authors]
    year = _text(value.get("year") or value.get("publication_year"))
    if year and year[:4].isdigit():
        metadata["issued"] = {"date-parts": [[int(year[:4])]]}
    doi = normalize_doi(_text(value.get("doi")))
    if doi is not None:
        metadata["DOI"] = doi
    return ImportedLiteratureRecord(item_type, title, doi, metadata)


def _to_bibtex(entry: LiteratureEntry, *, index: int) -> dict[str, str]:
    metadata = entry.csl_data
    value = {
        "ENTRYTYPE": _csl_to_bibtex_type(entry.item_type),
        "ID": str(metadata.get("id") or f"qunxue-{index + 1}"),
        "title": entry.title,
    }
    authors = metadata.get("author")
    if isinstance(authors, list):
        value["author"] = " and ".join(_format_bibtex_name(author) for author in authors)
    year = _year(metadata)
    if year is not None:
        value["year"] = str(year)
    fields = (("journal", "container-title"), ("publisher", "publisher"), ("url", "URL"))
    for target, source in fields:
        text = _text(metadata.get(source))
        if text:
            value[target] = text
    if entry.doi:
        value["doi"] = entry.doi
    return value


def _to_ris(entry: LiteratureEntry) -> dict[str, object]:
    metadata = entry.csl_data
    value: dict[str, object] = {
        "type_of_reference": _csl_to_ris_type(entry.item_type),
        "title": entry.title,
    }
    authors = metadata.get("author")
    if isinstance(authors, list):
        value["authors"] = [_format_ris_name(author) for author in authors]
    year = _year(metadata)
    if year is not None:
        value["year"] = str(year)
    if entry.doi:
        value["doi"] = entry.doi
    return value


def _bibtex_names(value: str | None) -> list[dict[str, str]]:
    return [_split_name(item.strip()) for item in (value or "").split(" and ") if item.strip()]


def _split_name(value: str) -> dict[str, str]:
    if "," in value:
        family, given = (part.strip() for part in value.split(",", 1))
        return {"family": family, "given": given}
    parts = value.split()
    return {"family": parts[-1], "given": " ".join(parts[:-1])} if parts else {"literal": value}


def _format_bibtex_name(value: object) -> str:
    if not isinstance(value, dict):
        return str(value)
    if literal := _text(value.get("literal")):
        return literal
    family = _text(value.get("family")) or ""
    given = _text(value.get("given")) or ""
    return f"{family}, {given}".strip(" ,")


def _format_ris_name(value: object) -> str:
    return _format_bibtex_name(value)


def _year(metadata: Mapping[str, object]) -> int | None:
    issued = metadata.get("issued")
    if not isinstance(issued, dict):
        return None
    parts = issued.get("date-parts")
    if not isinstance(parts, list) or not parts or not isinstance(parts[0], list) or not parts[0]:
        return None
    year = parts[0][0]
    return int(year) if isinstance(year, (int, str)) and str(year).isdigit() else None


def _required_text(value: object, field: str) -> str:
    text = _text(value)
    if not text:
        raise ValueError(f"literature {field} is required")
    return text


def _text(value: object) -> str | None:
    return value.strip() if isinstance(value, str) and value.strip() else None


def _bibtex_to_csl_type(value: str) -> str:
    return {
        "article": "article-journal",
        "book": "book",
        "inbook": "chapter",
        "incollection": "chapter",
        "inproceedings": "paper-conference",
        "phdthesis": "thesis",
        "mastersthesis": "thesis",
        "techreport": "report",
    }.get(value.lower(), "document")


def _csl_to_bibtex_type(value: str) -> str:
    return {
        "article-journal": "article",
        "book": "book",
        "chapter": "incollection",
        "paper-conference": "inproceedings",
        "thesis": "phdthesis",
        "report": "techreport",
    }.get(value, "misc")


def _ris_to_csl_type(value: str) -> str:
    mapping = {
        "JOUR": "article-journal",
        "BOOK": "book",
        "CHAP": "chapter",
        "THES": "thesis",
        "RPRT": "report",
    }
    return mapping.get(value.upper(), "document")


def _csl_to_ris_type(value: str) -> str:
    mapping = {
        "article-journal": "JOUR",
        "book": "BOOK",
        "chapter": "CHAP",
        "thesis": "THES",
        "report": "RPRT",
    }
    return mapping.get(value, "GEN")
