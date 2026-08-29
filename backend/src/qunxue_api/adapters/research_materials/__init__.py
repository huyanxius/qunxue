"""Parsing adapters for user-owned research materials.

The parser boundary is deliberately separate from the research-material domain:
parsers may be replaced after measured fixture evaluation without changing the
task ownership, versioning, or citation contracts.
"""

from qunxue_api.adapters.research_materials.parser import parse_material
from qunxue_api.modules.research_materials import MaterialParseError, ParsedMaterial

__all__ = ["MaterialParseError", "ParsedMaterial", "parse_material"]
