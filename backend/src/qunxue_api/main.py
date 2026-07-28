import uvicorn

from qunxue_api.bootstrap import create_app

app = create_app()


def main() -> None:
    uvicorn.run(
        "qunxue_api.main:app",
        host="127.0.0.1",
        port=8000,
        reload=True,
    )
