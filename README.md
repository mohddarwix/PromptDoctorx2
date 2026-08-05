# PromptDoctor

An AI agent that improves the prompts you write, iteratively.

You copy a rough prompt to your clipboard, press Ctrl+Shift+D, and PromptDoctor:
1. runs your prompt through Claude to see what it produces (executor),
2. critiques the prompt using the output as evidence (judge),
3. rewrites the prompt to fix specific issues (reviser),
4. repeats until the judge is satisfied or an iteration cap is hit,
5. drops the improved prompt back on your clipboard.

Because it works at the clipboard layer, PromptDoctor is model-agnostic and
app-agnostic: the same tool improves prompts you're about to paste into ChatGPT,
Claude, Gemini, or any other chat interface.

## The design in one paragraph

A ReAct-style loop with three tools and Reflexion-style long-term memory:

- Tool 1 — Executor (`run_prompt`): runs the prompt through Claude via the CLI.
- Tool 2 — Judge (`judge_prompt`): evaluates the prompt (not the output) using
  the output as diagnostic evidence; returns a structured score and issues list.
- Tool 3 — Reviser (`revise_prompt`): rewrites the prompt to fix the specific
  issues raised by the judge.
- Memory: after every run, the types of issues found are added to a running
  counter on disk. On subsequent runs, the top-K most-common issue types are
  injected into judge and reviser as hints — the agent gets progressively wiser
  without any model retraining.

## Setup

Requires Python 3.9+ and the Claude CLI (`claude --version` must work).

    git clone <this-repo>
    cd promptdoctor
    python -m venv .venv
    source .venv/bin/activate    # Windows: .venv\Scripts\activate
    pip install -r requirements.txt

No API keys required. PromptDoctor uses your existing Claude subscription via
the CLI.

## Run

    python main.py

Then copy a prompt from any app, press Ctrl + Shift + D, and paste the
improved prompt anywhere.

## Modes without hotkey

    python main.py --once                       # doctor the clipboard once, exit
    python main.py --prompt "summarize X"       # doctor a specific string

### Streamlit frontend

    streamlit run app.py

Opens in your browser. Sidebar shows learned lessons and session stats.
The CLI hotkey mode (`python main.py`) still works — Streamlit is an
additional frontend, not a replacement.

Toggle **Human in the loop** in the Doctor tab to review each iteration's
judge verdict before the reviser rewrites the prompt. You can Accept the
revision, Skip and retry the same prompt, or Stop early with what you have.

Use --prompt mode on WSL, SSH, or Wayland — anywhere global hotkeys don't work.

## Configuration

Environment variables (all optional):

| Variable | Default | Meaning |
| --- | --- | --- |
| MAX_ITERATIONS | 3 | Hard cap on the loop. |
| SCORE_THRESHOLD | 8 | Judge score at which the loop declares success. |
| MEMORY_PATH | memory_store.json | Where the aggregate-lesson counter lives. |
| HISTORY_PATH | runs.jsonl | Where the per-session run log lives. |

## Evaluation

A small automated eval suite lives in `eval/`. It runs PromptDoctor against
5 known-bad prompts and scores it on:
- **Issue recall** — did the judge catch the expected weaknesses?
- **Final-fix rate** — did the final prompt contain the expected fix?
- **Convergence rate** — how often did the loop reach the threshold?

Run with:

    python eval/run_eval.py

Results are written to `eval/eval_results.jsonl`. Add new test prompts by
editing `eval/test_prompts.json`.

## n8n integration

The [`n8n/`](n8n/) folder packages this agent as a custom n8n node (Gemini-powered,
since it needs to run headless) and a self-hosted workflow that puts it behind a
webhook alongside branching, looping, filtering, and error handling. See
[n8n/README.md](n8n/README.md) for setup and usage.

## Platform notes

- macOS: first run will prompt for Accessibility permission (System Settings
  → Privacy & Security → Input Monitoring). Enable it and restart the terminal.
- Linux (Wayland) or WSL: global hotkeys don't work reliably — use
  --once or --prompt mode.
- Windows: no special setup.
