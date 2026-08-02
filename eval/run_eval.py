"""
Automated evaluation of PromptDoctor.

For each test prompt:
  1. Run the agent.
  2. Check whether the judge found any of the expected issue types (recall).
  3. Check whether the final prompt contains any of the expected fix keywords (fix rate).
  4. Record convergence.

Prints a summary and writes eval_results.jsonl. Runs are also logged to runs.jsonl
via the standard agent path.

Run:  python eval/run_eval.py
"""

import json
import sys
from pathlib import Path

# Windows consoles default to the cp1252 codepage, which can't encode some
# characters that show up in exception messages or model output. Force UTF-8
# on stdout so this doesn't crash mid-run (same fix as main.py).
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent import doctor


def load_tests(path: Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def check_expected_issues(traj, expected_issues: list) -> tuple:
    """Return (recall, matched), how many expected issues the judge actually found."""
    seen = set()
    for it in traj.iterations:
        seen.update(it.issue_types)
    matched = [e for e in expected_issues if e in seen]
    recall = len(matched) / len(expected_issues) if expected_issues else 1.0
    return recall, matched


def check_final_fix(traj, final_check: dict) -> bool:
    """Check whether the final prompt contains any of the required fix keywords."""
    keywords = final_check.get("must_contain_any_of", [])
    final = (traj.final_prompt or "").lower()
    return any(k.lower() in final for k in keywords)


def run_one(test: dict) -> dict:
    print(f"\n--- {test['id']} ---")
    print(f"    rough: {test['rough_prompt']}")

    traj = doctor(test["rough_prompt"], verbose=False)

    recall, matched = check_expected_issues(traj, test["expected_issues"])
    fixed = check_final_fix(traj, test["final_check"])

    result = {
        "id": test["id"],
        "converged": traj.converged,
        "iterations_used": len(traj.iterations),
        "expected_issues": test["expected_issues"],
        "matched_issues": matched,
        "issue_recall": round(recall, 2),
        "final_fixed_check": fixed,
        "final_prompt": traj.final_prompt,
    }

    print(f"    converged: {traj.converged}   iters: {len(traj.iterations)}")
    print(f"    issue recall: {recall:.0%}   ({len(matched)}/{len(test['expected_issues'])} expected issues found)")
    print(f"    final-fix check: {'PASS' if fixed else 'FAIL'}")
    return result


def main():
    tests_path = Path(__file__).parent / "test_prompts.json"
    tests = load_tests(tests_path)

    print(f"Running {len(tests)} eval prompts...")
    print("=" * 60)

    results = []
    for test in tests:
        try:
            result = run_one(test)
        except Exception as e:
            print(f"    ERROR: {e}")
            result = {"id": test["id"], "error": str(e)}
        results.append(result)

    ok = [r for r in results if "error" not in r]
    converged = sum(1 for r in ok if r["converged"])
    avg_recall = sum(r["issue_recall"] for r in ok) / len(ok) if ok else 0
    fixed_ct = sum(1 for r in ok if r["final_fixed_check"])

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total tests:        {len(tests)}")
    print(f"Errored:            {len(results) - len(ok)}")
    print(f"Converged:          {converged} / {len(ok)}")
    print(f"Avg issue recall:   {avg_recall:.0%}")
    print(f"Final-fix pass:     {fixed_ct} / {len(ok)}")

    out_path = Path(__file__).parent / "eval_results.jsonl"
    with open(out_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"\nResults written to {out_path}")


if __name__ == "__main__":
    main()
