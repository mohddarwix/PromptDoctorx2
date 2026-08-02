"""
Append-only session log.

Every completed doctoring run gets one line in runs.jsonl (JSON Lines format).
Each line is a self-contained record, no cross-line references, so the file
can be truncated, grepped, or streamed without state.

Design choices:
- JSON Lines (not JSON array) so appends are O(1) and the file is streamable.
- Timestamps in ISO-8601 UTC so sorting is lexicographic.
- Prompts stored verbatim so the file is also a corpus for future analysis.
- All errors swallowed silently, history is best-effort, must never crash the agent.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _path() -> Path:
    return Path(os.getenv("HISTORY_PATH", "runs.jsonl"))


def append_run(traj) -> None:
    """
    Append one Trajectory to the history file.

    `traj` is the Trajectory dataclass from agent.py. We convert it to a dict
    inline rather than importing the class, to keep this module import-safe
    from any context.
    """
    try:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "original_prompt": traj.original_prompt,
            "final_prompt": traj.final_prompt,
            "converged": traj.converged,
            "stopped_reason": traj.stopped_reason,
            "iterations": [
                {
                    "number": it.number,
                    "score": it.score,
                    "issue_types": it.issue_types,
                    "output_length": it.output_length,
                }
                for it in traj.iterations
            ],
        }
        with open(_path(), "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except (OSError, TypeError, AttributeError):
        pass  # history is best-effort


def load_recent(limit: int = 20) -> list:
    """Return the most recent N runs, newest first. Returns [] on any error."""
    p = _path()
    if not p.exists():
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            lines = f.readlines()
        records = []
        for line in reversed(lines[-limit * 2:]):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
                if len(records) >= limit:
                    break
            except json.JSONDecodeError:
                continue
        return records
    except OSError:
        return []


def stats() -> dict:
    """Aggregate stats across all runs. Useful for the sidebar."""
    p = _path()
    if not p.exists():
        return {"total_runs": 0, "converged_runs": 0, "avg_iterations": 0.0}

    total = 0
    converged = 0
    iters_sum = 0

    try:
        with open(p, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                total += 1
                if rec.get("converged"):
                    converged += 1
                iters_sum += len(rec.get("iterations", []))
    except OSError:
        return {"total_runs": 0, "converged_runs": 0, "avg_iterations": 0.0}

    return {
        "total_runs": total,
        "converged_runs": converged,
        "avg_iterations": round(iters_sum / total, 2) if total else 0.0,
    }
