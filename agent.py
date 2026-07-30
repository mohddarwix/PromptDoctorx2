"""
The agent loop: run → judge → converged? → revise → repeat.

This is the core of PromptDoctor. Everything else (LLM client, memory, clipboard,
hotkey listener) is plumbing around this loop.

Loop shape:
    for iteration in 1..MAX_ITERATIONS:
        output   = run_prompt(current)                       # tool 1: evidence
        verdict  = judge_prompt(current, output, lessons)    # tool 2: critique
        memorize the issue types
        if verdict.score >= SCORE_THRESHOLD: converged, stop
        if this is the last iteration: stop (no point revising further)
        current = revise_prompt(current, verdict.issues, lessons)  # tool 3: fix
"""

import os
from dataclasses import dataclass, field
from typing import List

import memory
from tools import run_prompt, judge_prompt, revise_prompt


def _max_iterations() -> int:
    try:
        return max(1, int(os.getenv("MAX_ITERATIONS", "3")))
    except ValueError:
        return 3


def _score_threshold() -> int:
    try:
        return int(os.getenv("SCORE_THRESHOLD", "8"))
    except ValueError:
        return 8


@dataclass
class Iteration:
    number: int
    prompt: str
    output_length: int
    score: int
    issue_types: List[str] = field(default_factory=list)


@dataclass
class Trajectory:
    """Record of one complete doctoring session."""
    original_prompt: str = ""
    final_prompt: str = ""
    iterations: List[Iteration] = field(default_factory=list)
    converged: bool = False
    stopped_reason: str = ""


def doctor(rough_prompt: str, verbose: bool = True) -> Trajectory:
    """
    Run the full agent loop on a rough prompt.

    Returns a Trajectory with the final improved prompt and per-iteration records.
    """
    max_iter = _max_iterations()
    threshold = _score_threshold()

    store = memory.load()
    lessons = memory.top_lessons(store, k=5)

    if verbose:
        if lessons:
            print(f"[memory] Loaded {len(store)} known issue types; injecting top 5.")
        else:
            print(f"[memory] Empty. Will start accumulating lessons from this run.")

    current = (rough_prompt or "").strip()
    traj = Trajectory(original_prompt=current, final_prompt=current)

    if not current:
        traj.stopped_reason = "empty_input"
        return traj

    for i in range(1, max_iter + 1):
        if verbose:
            print(f"\n--- Iteration {i} of {max_iter} ---")

        # Tool 1 — Executor
        try:
            output = run_prompt(current)
        except Exception as e:
            if verbose:
                print(f"[executor error] {e}")
            traj.stopped_reason = f"executor_error: {e}"
            break

        if verbose:
            preview = output.replace("\n", " ")[:120]
            print(f"[run]   output {len(output)} chars: {preview}{'...' if len(output) > 120 else ''}")

        # Tool 2 — Judge
        try:
            verdict = judge_prompt(current, output, lessons)
        except Exception as e:
            if verbose:
                print(f"[judge error] {e}")
            traj.stopped_reason = f"judge_error: {e}"
            break

        score = int(verdict.get("score", 0))
        issues = verdict.get("issues", []) or []
        issue_types = [str(it.get("type", "unknown")) for it in issues]

        if verbose:
            print(f"[judge] score {score}/10")
            for it in issues[:5]:
                t = it.get("type", "?")
                d = it.get("description", "")
                print(f"        - {t}: {d}")

        traj.iterations.append(Iteration(
            number=i,
            prompt=current,
            output_length=len(output),
            score=score,
            issue_types=issue_types,
        ))

        memory.learn(store, issue_types)

        if score >= threshold:
            traj.converged = True
            traj.stopped_reason = "converged"
            if verbose:
                print(f"[✓] Converged (score {score} >= threshold {threshold}).")
            break

        if i == max_iter:
            traj.stopped_reason = "iteration_cap"
            if verbose:
                print(f"[!] Iteration cap reached without convergence.")
            break

        # Tool 3 — Reviser
        try:
            current = revise_prompt(current, issues, lessons)
        except Exception as e:
            if verbose:
                print(f"[reviser error] {e}")
            traj.stopped_reason = f"reviser_error: {e}"
            break

        if verbose:
            preview = current.replace("\n", " ")[:120]
            print(f"[revise] {preview}{'...' if len(current) > 120 else ''}")

    memory.save(store)
    traj.final_prompt = current
    return traj
