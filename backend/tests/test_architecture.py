import ast
from pathlib import Path

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "qunxue_api"
MODULES_ROOT = PACKAGE_ROOT / "modules"
MODULE_PACKAGE = "qunxue_api.modules"
ALLOWED_MODULE_DEPENDENCIES = {
    "knowledge_catalog": set(),
    "research_intake": set(),
    "theory_matching": {"knowledge_catalog", "research_intake"},
    "research_framework": {"theory_matching"},
}
ALLOWED_CROSS_MODULE_SYMBOLS = {
    ("theory_matching", "knowledge_catalog"): {
        "KnowledgeReleaseRef",
        "SourceRecordSnapshot",
        "SourceVerificationStatus",
        "TheoryProfileSnapshot",
    },
    ("theory_matching", "research_intake"): {
        "ConfirmedPhenomenonSnapshot",
    },
    ("research_framework", "theory_matching"): {
        "ConfirmedTheoryPlanSnapshot",
    },
}
FORBIDDEN_INTERNAL_PREFIXES = (
    "qunxue_api.adapters",
    "qunxue_api.api",
    "qunxue_api.bootstrap",
    "qunxue_api.settings",
)
FORBIDDEN_FRAMEWORK_PREFIXES = (
    "fastapi",
    "pydantic",
    "pydantic_core",
    "pydantic_settings",
    "sqlalchemy",
)
CONCRETE_PROVIDER_PREFIXES = (
    "anthropic",
    "cohere",
    "dashscope",
    "google.genai",
    "google.generativeai",
    "mistralai",
    "ollama",
    "openai",
    "qianfan",
    "volcenginesdkarkruntime",
    "zhipuai",
)
FORBIDDEN_BUSINESS_PREFIXES = (
    *FORBIDDEN_INTERNAL_PREFIXES,
    *FORBIDDEN_FRAMEWORK_PREFIXES,
    *CONCRETE_PROVIDER_PREFIXES,
)


def _source_module(path: Path) -> tuple[str, bool]:
    relative = path.relative_to(PACKAGE_ROOT).with_suffix("")
    parts = ["qunxue_api", *relative.parts]
    is_package = parts[-1] == "__init__"
    if is_package:
        parts.pop()
    return ".".join(parts), is_package


def _resolve_from_import(
    *,
    source_module: str,
    source_is_package: bool,
    imported_module: str | None,
    level: int,
) -> str:
    if level == 0:
        if imported_module is None:
            raise AssertionError("absolute from-import must name a module")
        return imported_module

    package_parts = source_module.split(".")
    if not source_is_package:
        package_parts.pop()
    parent_hops = level - 1
    if parent_hops >= len(package_parts):
        raise AssertionError(f"{source_module} imports beyond the package root")
    if parent_hops:
        package_parts = package_parts[:-parent_hops]
    if imported_module:
        package_parts.extend(imported_module.split("."))
    return ".".join(package_parts)


def _is_local_module(module_name: str) -> bool:
    if module_name == "qunxue_api":
        return True
    if not module_name.startswith("qunxue_api."):
        return False
    candidate = PACKAGE_ROOT.joinpath(*module_name.split(".")[1:])
    return candidate.is_dir() or candidate.with_suffix(".py").is_file()


def _imports(path: Path) -> set[str]:
    source_module, source_is_package = _source_module(path)
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        resolved = _resolve_from_import(
            source_module=source_module,
            source_is_package=source_is_package,
            imported_module=node.module,
            level=node.level,
        )
        imports.add(resolved)
        for alias in node.names:
            possible_child = f"{resolved}.{alias.name}"
            if alias.name != "*" and (
                _is_local_module(possible_child)
                or _matches_prefix(possible_child, CONCRETE_PROVIDER_PREFIXES)
            ):
                imports.add(possible_child)
    return imports


def _from_imports(path: Path) -> list[tuple[str, set[str]]]:
    source_module, source_is_package = _source_module(path)
    tree = ast.parse(path.read_text())
    imports: list[tuple[str, set[str]]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        resolved = _resolve_from_import(
            source_module=source_module,
            source_is_package=source_is_package,
            imported_module=node.module,
            level=node.level,
        )
        imports.append((resolved, {alias.name for alias in node.names}))
    return imports


def _plain_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    return {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }


def _matches_prefix(module_name: str, prefixes: tuple[str, ...]) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in prefixes
    )


def test_relative_import_levels_are_resolved() -> None:
    source = "qunxue_api.modules.theory_matching.public"

    assert _resolve_from_import(
        source_module=source,
        source_is_package=False,
        imported_module="knowledge_catalog",
        level=2,
    ) == "qunxue_api.modules.knowledge_catalog"
    assert _resolve_from_import(
        source_module=source,
        source_is_package=False,
        imported_module="api",
        level=3,
    ) == "qunxue_api.api"
    assert _resolve_from_import(
        source_module=source,
        source_is_package=False,
        imported_module="rules",
        level=1,
    ) == "qunxue_api.modules.theory_matching.rules"


def test_business_module_dependencies_are_one_way_and_public() -> None:
    for source_path in MODULES_ROOT.rglob("*.py"):
        relative = source_path.relative_to(MODULES_ROOT)
        if len(relative.parts) < 2:
            continue
        source_module = relative.parts[0]
        for imported in _imports(source_path):
            assert not _matches_prefix(imported, FORBIDDEN_BUSINESS_PREFIXES), (
                f"{source_module} cannot import infrastructure, frameworks, "
                f"or concrete providers: {imported}"
            )
            if not imported.startswith(f"{MODULE_PACKAGE}."):
                continue
            target_module = imported.split(".")[2]
            if target_module == source_module:
                continue
            assert target_module in ALLOWED_MODULE_DEPENDENCIES[source_module], (
                f"{source_module} cannot depend on {target_module}"
            )
            assert imported == f"{MODULE_PACKAGE}.{target_module}", (
                f"{source_module} must use {target_module}'s public package root"
            )
        for imported, symbols in _from_imports(source_path):
            if not imported.startswith(f"{MODULE_PACKAGE}."):
                continue
            target_module = imported.split(".")[2]
            if target_module == source_module:
                continue
            allowed_symbols = ALLOWED_CROSS_MODULE_SYMBOLS.get(
                (source_module, target_module),
                set(),
            )
            assert symbols <= allowed_symbols, (
                f"{source_module} cannot import {sorted(symbols - allowed_symbols)} "
                f"from {target_module}"
            )
        for imported in _plain_imports(source_path):
            if not imported.startswith(f"{MODULE_PACKAGE}."):
                continue
            target_module = imported.split(".")[2]
            if target_module != source_module:
                raise AssertionError(
                    f"{source_module} must explicitly import allowed symbols "
                    f"from {target_module}'s public root"
                )


def test_external_code_cannot_import_module_internals() -> None:
    for source_path in PACKAGE_ROOT.rglob("*.py"):
        if MODULES_ROOT in source_path.parents:
            continue
        for imported in _imports(source_path):
            if not imported.startswith(f"{MODULE_PACKAGE}."):
                continue
            assert len(imported.split(".")) == 3, (
                f"{source_path.relative_to(PACKAGE_ROOT)} bypasses a module API: {imported}"
            )
