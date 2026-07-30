"""
Long-term aggregate-lesson memory (Reflexion-style).

We store a counter of the TYPES of issues the judge has flagged across all past
runs. The top-K most-common issue types are injected into judge and reviser
prompts as hints on subsequent runs.

Design choice: aggregate lessons over verbatim past examples. Full-example
memory would require an embedding index (extra dependency) and a semantic
similarity search, and generalizes worse than "the judge has flagged missing
length constraints 47 times, watch for it."
"""

import json
import os
from pathlib import Path


def _path() -> Path:
    return Path(os.getenv("MEMORY_PATH", "memory_store.json"))


def load() -> dict:
    p = _path()
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return {str(k): int(v) for k, v in data.items() if isinstance(v, (int, float))}
            return {}
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return {}


def save(store: dict) -> None:
    p = _path()
    try:
        tmp = p.with_suffix(p.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(store, f, indent=2, sort_keys=True)
        tmp.replace(p)
    except OSError:
        pass  # memory is best-effort; never crash the agent over a disk error


def learn(store: dict, issue_types: list) -> None:
    for t in issue_types:
        if not t:
            continue
        key = str(t).strip()
        if key:
            store[key] = store.get(key, 0) + 1


def top_lessons(store: dict, k: int = 5) -> list:
    if not store:
        return []
    ranked = sorted(store.items(), key=lambda kv: (-kv[1], kv[0]))
    return [f"{t} (seen {n} time{'s' if n != 1 else ''})" for t, n in ranked[:k]]
