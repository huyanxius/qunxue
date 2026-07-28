import json
from pathlib import Path

from qunxue_api.main import app


def main() -> None:
    output_path = Path(__file__).resolve().parents[1] / "openapi.json"
    content = json.dumps(
        app.openapi(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    output_path.write_text(f"{content}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
