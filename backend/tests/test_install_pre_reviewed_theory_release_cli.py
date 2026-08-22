import json
import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from test_pre_reviewed_theory_release import _write_bundle

from qunxue_api.modules.knowledge_catalog import KnowledgeUsePurpose


def test_cli_installs_and_replays_a_pre_reviewed_release(
    client: TestClient,
    tmp_path: Path,
) -> None:
    preview = client.app.state.knowledge_catalog.current_release(
        purpose=KnowledgeUsePurpose.BROWSE
    )
    bundle = _write_bundle(
        tmp_path / "pre-reviewed-theories.json",
        base_release_id=preview.knowledge_release_id,
    )
    command = [
        sys.executable,
        str(Path(__file__).parents[1] / "scripts/install_pre_reviewed_theory_release.py"),
        str(bundle),
    ]
    environment = {
        **os.environ,
        "QUNXUE_DATABASE_URL": client.app.state.settings.database_url,
    }

    first = subprocess.run(
        command,
        cwd=Path(__file__).parents[1],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    replayed = subprocess.run(
        command,
        cwd=Path(__file__).parents[1],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert first.returncode == 0, first.stderr
    assert replayed.returncode == 0, replayed.stderr
    assert json.loads(replayed.stdout) == json.loads(first.stdout)
    payload = json.loads(first.stdout)
    assert payload["level"] == "final"
    assert payload["theory_ids"] == [
        "theory-pre-reviewed-1",
        "theory-pre-reviewed-2",
        "theory-pre-reviewed-3",
    ]
    assert payload["review_record_ids"] == [
        "review:theory-1:v1",
        "review:theory-2:v1",
        "review:theory-3:v1",
    ]
