"""A local cache of classifier answers, so a replay is free and identical (PRD v0.4.31; like the response cache of FR-003.5).

One file ``<key>.json`` per answer under ``.cache/jev/`` (git-ignored). The key covers what decides the answer: the
requested model name, the version of the questions, the number of lines read, the option order and the page text read.
The file holds the page text's hash, never the text, and the answer's numbers.
"""

import hashlib
import json
from pathlib import Path

DEFAULT_JEV_CACHE_DIR = Path(".cache") / "jev"


def cache_key(model: str, questions_version: str, state_lines: int, order: str, state: str) -> str:
    material = json.dumps([model, questions_version, state_lines, order, hashlib.sha256(state.encode("utf-8")).hexdigest()])
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


class JevCache:
    def __init__(self, directory: Path = DEFAULT_JEV_CACHE_DIR) -> None:
        self.directory = directory
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> dict | None:
        try:
            data = json.loads((self.directory / f"{key}.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.misses += 1
            return None
        if not isinstance(data, dict):
            self.misses += 1
            return None
        self.hits += 1
        return data

    def put(self, key: str, data: dict) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            (self.directory / f"{key}.json").write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        except OSError:
            pass  # a cache that cannot be written is only a missed saving
