import json
from pathlib import Path

from qunxue_api.api.routes.account_management import routers as account_routers
from qunxue_api.main import app


def export_schema() -> dict:
    # Account installation requires an administrator secret at runtime. Contract
    # generation includes its static routes without provisioning an account.
    identities = {
        (route.path, method)
        for route in app.routes
        if hasattr(route, "methods")
        for method in route.methods
    }
    for router in account_routers:
        for route in router.routes:
            if any((route.path, method) not in identities for method in route.methods):
                app.router.routes.append(route)
                identities.update((route.path, method) for method in route.methods)
    app.openapi_schema = None
    return app.openapi()


def main() -> None:
    output_path = Path(__file__).resolve().parents[1] / "openapi.json"
    content = json.dumps(
        export_schema(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    output_path.write_text(f"{content}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
