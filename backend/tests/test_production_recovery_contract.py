import importlib.util
from pathlib import Path


def test_account_contract_exports_recovery_without_admin_provisioning():
    path = Path(__file__).resolve().parents[1] / "scripts/export_openapi.py"
    spec = importlib.util.spec_from_file_location("recovery_contract", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    schema = module.export_schema()
    route = schema["paths"]["/api/account/password-resets/request"]["post"]
    assert route["operationId"] == "request_account_password_reset"
    assert "202" in route["responses"]
    assert "/api/admin/users" in schema["paths"]
    before = len(module.app.routes)
    assert module.export_schema() == schema
    assert len(module.app.routes) == before
