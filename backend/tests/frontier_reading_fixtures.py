import os
from pathlib import Path

from qunxue_api.json_shards import load_json


def import_real_corpus(client):
    corpus = load_json(
        os.environ.get("QUNXUE_READING_CORPUS")
        or Path(__file__).parents[1] / "data/frontier-corpus.json"
    )
    return client.app.state.frontier_store.import_seed(corpus)
