"""Check the structured tables in docs/ARCHITECTURE.md against their sources."""

import ast
import json
import re
from pathlib import Path

TABLE_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|([^|]*)\|")
INLINE_CODE = re.compile(r"`([^`]+)`")
MODULE_PATH = re.compile(r"modules/([a-z][a-z0-9_]*)/")
HTTP_OPERATION = re.compile(r"[A-Z]+ /api/\S+")
HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def load_module_dependencies(path: Path) -> dict[str, set[str]]:
    # Read the architecture registry without importing pytest or the application.
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "ALLOWED_MODULE_DEPENDENCIES"
            for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError(f"ALLOWED_MODULE_DEPENDENCIES is missing from {path}")


def check(root: Path) -> int:
    dependencies = load_module_dependencies(root / "backend/tests/test_architecture.py")
    openapi = json.loads((root / "backend/openapi.json").read_text(encoding="utf-8"))
    operations = {
        f"{method.upper()} {path}": operation
        for path, item in openapi["paths"].items()
        for method, operation in item.items()
        if method in HTTP_METHODS
    }
    retired = {
        name
        for name, operation in operations.items()
        if operation.get("deprecated") and "410" in operation.get("responses", {})
    }
    active = {
        name for name, operation in operations.items() if not operation.get("deprecated")
    }

    documented_modules: dict[str, set[str]] = {}
    documented_retirements: dict[str, set[str]] = {}
    errors = []
    architecture = (root / "docs/ARCHITECTURE.md").read_text(encoding="utf-8")
    for line in architecture.splitlines():
        row = TABLE_ROW.match(line)
        if row is None:
            continue
        key, values = row.groups()
        if module := MODULE_PATH.fullmatch(key):
            key = module[1]
            table = documented_modules
        elif HTTP_OPERATION.fullmatch(key):
            table = documented_retirements
        else:
            continue
        if key in table:
            errors.append(f"Duplicate architecture row: {key}")
        table[key] = set(INLINE_CODE.findall(values))
        if not table[key] and values.strip() != "—":
            errors.append(f"Missing dependency or successor values: {key}")

    covered_modules = dependencies.keys() & documented_modules.keys()
    covered_retirements = retired & documented_retirements.keys()
    print(f"Documented modules: {len(covered_modules)}/{len(dependencies)}")
    print(f"Documented retired operations: {len(covered_retirements)}/{len(retired)}")
    for label, expected, documented in (
        ("module", dependencies.keys(), documented_modules.keys()),
        ("retired operation", retired, documented_retirements.keys()),
    ):
        errors.extend(f"Missing {label}: {key}" for key in sorted(expected - documented))
        errors.extend(f"Unexpected {label}: {key}" for key in sorted(documented - expected))

    for name in sorted(covered_modules):
        actual = documented_modules[name]
        if actual != dependencies[name]:
            errors.append(
                f"{name}: expected dependencies {sorted(dependencies[name])}, found {sorted(actual)}"
            )
    for name, successors in documented_retirements.items():
        if not successors:
            errors.append(f"{name}: missing successor operation")
        if invalid := successors - active:
            errors.append(
                f"{name}: successors must be active OpenAPI operations: {sorted(invalid)}"
            )

    for error in errors:
        print(error)
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(check(Path.cwd()))
