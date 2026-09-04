import ast
from inspect import signature
from pathlib import Path

from qunxue_api.adapters.sqlite.research_task_repository import (
    SqliteResearchTaskRepository,
)
from qunxue_api.modules import research_intake
from qunxue_api.modules.research_intake import ResearchTaskRepository

PACKAGE_ROOT = Path(__file__).parents[1] / "src" / "qunxue_api"
MODULES_ROOT = PACKAGE_ROOT / "modules"
MODULE_PACKAGE = "qunxue_api.modules"
ALLOWED_MODULE_DEPENDENCIES = {
    "account_management": {"identity"},
    "agent_conversation": set(),
    "billing": set(),
    "identity": set(),
    "knowledge_catalog": set(),
    "research_intake": set(),
    "research_analysis": {"research_materials"},
    "research_cycle": {
        "research_analysis",
        "research_materials",
        "theory_matching",
    },
    "research_exchange": set(),
    "research_materials": set(),
    "research_method": set(),
    "transcription": set(),
    "theory_matching": {"knowledge_catalog", "research_intake"},
    "research_framework": {"theory_matching"},
}
ALLOWED_CROSS_MODULE_SYMBOLS = {
    ("research_analysis", "research_materials"): {"MaterialLocator"},
    ("research_cycle", "research_analysis"): {
        "AnalysisCodeStatus",
        "AnalysisRecordStatus",
        "ComparisonFindingKind",
        "ResearchAnalysisHandoff",
    },
    ("research_cycle", "research_materials"): {
        "MaterialKind",
        "ProfessionalMaterialArchiveView",
        "ResearchMaterial",
    },
    ("research_cycle", "theory_matching"): {"ConfirmedTheoryPlanSnapshot"},
    ("account_management", "identity"): {
        "AccountRole",
        "AccountStatus",
    },
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
ALLOWED_TOP_LEVEL_DEPENDENCIES = {
    "account_extension": {"adapters", "api", "modules"},
    "modules": {"modules"},
    "application": {"application", "modules"},
    "api": {"api", "application", "modules", "settings"},
    "adapters": {"adapters", "modules"},
    "bootstrap": {
        "account_extension",
        "adapters",
        "api",
        "application",
        "modules",
        "settings",
    },
    "settings": set(),
    "main": {"bootstrap"},
}
ALLOWED_MODULE_INTERNAL_DEPENDENCIES = {
    "domain": {"domain", "errors"},
    "errors": {"errors"},
    "ports": {"domain", "errors", "ports"},
    "service": {"domain", "errors", "ports", "service"},
}
MODULE_INTERNAL_ROLE_ALIASES = {
    "qualitative_workspace": "domain",
    "research_map": "domain",
}
FORBIDDEN_INTERNAL_PREFIXES = (
    "qunxue_api.adapters",
    "qunxue_api.api",
    "qunxue_api.application",
    "qunxue_api.bootstrap",
    "qunxue_api.main",
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


def _source_module(
    path: Path,
    package_root: Path = PACKAGE_ROOT,
) -> tuple[str, bool]:
    relative = path.relative_to(package_root).with_suffix("")
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


def _is_local_module(
    module_name: str,
    package_root: Path = PACKAGE_ROOT,
) -> bool:
    if module_name == "qunxue_api":
        return True
    if not module_name.startswith("qunxue_api."):
        return False
    candidate = package_root.joinpath(*module_name.split(".")[1:])
    return candidate.is_dir() or candidate.with_suffix(".py").is_file()


def _import_details(
    path: Path,
    package_root: Path = PACKAGE_ROOT,
) -> tuple[set[str], list[tuple[str, set[str]]], set[str]]:
    source_module, source_is_package = _source_module(path, package_root)
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    from_imports: list[tuple[str, set[str]]] = []
    plain_imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported = {alias.name for alias in node.names}
            imports.update(imported)
            plain_imports.update(imported)
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
        symbols = {alias.name for alias in node.names}
        from_imports.append((resolved, symbols))
        for symbol in symbols:
            possible_child = f"{resolved}.{symbol}"
            if symbol != "*" and (
                _is_local_module(possible_child, package_root)
                or _matches_prefix(possible_child, CONCRETE_PROVIDER_PREFIXES)
            ):
                imports.add(possible_child)
    return imports, from_imports, plain_imports


def _matches_prefix(module_name: str, prefixes: tuple[str, ...]) -> bool:
    return any(
        module_name == prefix or module_name.startswith(f"{prefix}.")
        for prefix in prefixes
    )


def _module_layout_violations(
    modules_root: Path,
    dependency_graph: dict[str, set[str]] = ALLOWED_MODULE_DEPENDENCIES,
) -> list[str]:
    discovered = {
        path.name
        for path in modules_root.iterdir()
        if path.is_dir() and path.name != "__pycache__"
    }
    registered = set(dependency_graph)
    violations = [
        f"{name} is not registered" for name in sorted(discovered - registered)
    ]
    violations.extend(
        f"{name} is registered without a directory"
        for name in sorted(registered - discovered)
    )
    violations.extend(
        f"{name} has no public __init__.py"
        for name in sorted(discovered)
        if not (modules_root / name / "__init__.py").is_file()
    )
    violations.extend(
        f"{source} names unregistered dependency {target}"
        for source, targets in dependency_graph.items()
        for target in sorted(targets - registered)
    )
    violations.extend(
        f"{path.name} is a single-file business module"
        for path in modules_root.glob("*.py")
        if path.name != "__init__.py"
    )
    return violations


def _architecture_violations(
    package_root: Path = PACKAGE_ROOT,
) -> list[str]:
    modules_root = package_root / "modules"
    root_entry = package_root / "__init__.py"
    violations: set[str] = set()

    for source_path in package_root.rglob("*.py"):
        imports, from_imports, plain_imports = _import_details(
            source_path, package_root
        )
        relative = source_path.relative_to(package_root)
        relative_label = relative.as_posix()

        if source_path == root_entry:
            for imported in imports:
                if imported.startswith("qunxue_api."):
                    violations.add(
                        f"{relative_label} cannot import internal layer {imported}"
                    )
            continue

        source_component = (
            relative.parts[0] if len(relative.parts) > 1 else relative.stem
        )
        if source_component not in ALLOWED_TOP_LEVEL_DEPENDENCIES:
            violations.add(f"{relative_label} is not a registered top-level component")
            continue
        for imported in imports:
            if not imported.startswith("qunxue_api."):
                continue
            target_component = imported.split(".")[1]
            if target_component not in ALLOWED_TOP_LEVEL_DEPENDENCIES[source_component]:
                violations.add(
                    f"{relative_label}: {source_component} cannot depend on "
                    f"{target_component}"
                )

        if modules_root not in source_path.parents:
            for imported in imports:
                if (
                    imported.startswith(f"{MODULE_PACKAGE}.")
                    and len(imported.split(".")) != 3
                ):
                    violations.add(
                        f"{relative_label} bypasses a module public package root: {imported}"
                    )
            continue

        module_relative = source_path.relative_to(modules_root)
        module_relative_label = module_relative.as_posix()
        if len(module_relative.parts) < 2:
            continue
        source_module = module_relative.parts[0]
        for imported in imports:
            if _matches_prefix(imported, FORBIDDEN_BUSINESS_PREFIXES):
                violations.add(
                    f"{module_relative_label}: business module cannot import {imported}"
                )
            if not imported.startswith(f"{MODULE_PACKAGE}."):
                continue
            target_module = imported.split(".")[2]
            if target_module == source_module:
                continue
            if target_module not in ALLOWED_MODULE_DEPENDENCIES.get(
                source_module, set()
            ):
                violations.add(
                    f"{module_relative_label}: {source_module} cannot depend on "
                    f"{target_module}"
                )
            if imported != f"{MODULE_PACKAGE}.{target_module}":
                violations.add(
                    f"{module_relative_label} bypasses {target_module}'s public package root"
                )

        for imported, symbols in from_imports:
            if imported == MODULE_PACKAGE:
                violations.add(
                    f"{module_relative_label} must import from a module public package root"
                )
                continue
            if not imported.startswith(f"{MODULE_PACKAGE}."):
                continue
            target_module = imported.split(".")[2]
            if target_module == source_module:
                continue
            allowed_symbols = ALLOWED_CROSS_MODULE_SYMBOLS.get(
                (source_module, target_module),
                set(),
            )
            unexpected = symbols - allowed_symbols
            if unexpected:
                violations.add(
                    f"{module_relative_label} cannot import {sorted(unexpected)} "
                    f"from {target_module}"
                )

        for imported in plain_imports:
            if not imported.startswith(f"{MODULE_PACKAGE}."):
                continue
            target_module = imported.split(".")[2]
            if target_module != source_module:
                violations.add(
                    f"{module_relative_label} must explicitly import symbols "
                    f"from {target_module}"
                )

        source_role = MODULE_INTERNAL_ROLE_ALIASES.get(
            Path(module_relative.parts[1]).stem,
            Path(module_relative.parts[1]).stem,
        )
        if source_role not in ALLOWED_MODULE_INTERNAL_DEPENDENCIES:
            continue
        module_root = f"{MODULE_PACKAGE}.{source_module}"
        for imported in imports:
            if imported == module_root:
                violations.add(
                    f"{module_relative_label}: {source_role} cannot import "
                    "its module package root"
                )
                continue
            if not imported.startswith(f"{module_root}."):
                continue
            target_role = MODULE_INTERNAL_ROLE_ALIASES.get(
                imported.split(".")[3],
                imported.split(".")[3],
            )
            if (
                target_role
                not in ALLOWED_MODULE_INTERNAL_DEPENDENCIES[source_role]
            ):
                violations.add(
                    f"{module_relative_label}: {source_role} cannot depend on {target_role}"
                )

    return sorted(violations)


def test_backend_obeys_registered_architecture() -> None:
    assert not _module_layout_violations(MODULES_ROOT)
    assert not _architecture_violations(PACKAGE_ROOT)


def test_research_method_is_registered_as_a_dependency_free_module() -> None:
    assert ALLOWED_MODULE_DEPENDENCIES["research_method"] == set()


def test_sqlite_repository_implements_the_public_research_intake_port() -> None:
    assert research_intake.ResearchTaskRepository is ResearchTaskRepository
    assert issubclass(SqliteResearchTaskRepository, ResearchTaskRepository)
    for method_name in ("get", "add_or_get_by_idempotency_key"):
        assert method_name in SqliteResearchTaskRepository.__dict__
        assert signature(
            SqliteResearchTaskRepository.__dict__[method_name]
        ) == signature(ResearchTaskRepository.__dict__[method_name])


def test_real_source_tree_exercises_negative_guards(tmp_path: Path) -> None:
    package_root = tmp_path / "qunxue_api"
    sources = {
        "__init__.py": "from .application import ResearchJourney\n",
        "application/__init__.py": "",
        "application/use_case.py": (
            "from qunxue_api.modules.research_intake.domain import ResearchTask\n"
        ),
        "bootstrap.py": "",
        "settings.py": "from .bootstrap import create_app\n",
        "modules/__init__.py": "",
        "modules/rogue.py": "",
        "modules/knowledge_catalog/domain.py": "",
        "modules/unregistered/__init__.py": "",
        "modules/research_intake/__init__.py": "",
        "modules/research_intake/domain.py": (
            "from ...application import ResearchJourney\n"
            "from .ports import ResearchTaskRepository\n"
            "from qunxue_api.modules.research_intake import ResearchTask\n"
        ),
        "modules/research_intake/ports.py": (
            "from .service import ResearchTaskService\n"
        ),
        "modules/research_intake/service.py": "",
    }
    for relative, source in sources.items():
        target = package_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(source)

    layout_violations = _module_layout_violations(package_root / "modules")
    architecture_violations = _architecture_violations(package_root)

    for expected in (
        "unregistered is not registered",
        "knowledge_catalog has no public __init__.py",
        "rogue.py is a single-file business module",
    ):
        assert expected in layout_violations
    for expected in (
        "__init__.py cannot import internal layer qunxue_api.application",
        "modules/research_intake/domain.py: modules cannot depend on application",
        "domain cannot depend on ports",
        "domain cannot import its module package root",
        "ports cannot depend on service",
        "application/use_case.py bypasses a module public package root",
        "settings.py: settings cannot depend on bootstrap",
    ):
        assert any(
            expected in violation for violation in architecture_violations
        ), expected
