"""
Thin wrapper around the Claude CLI.

Exposes two functions the rest of the agent uses:
  - call_text(model, prompt)  → returns the CLI's stdout as a string
  - call_json(model, prompt, response_schema) → returns parsed JSON as a dict

The `model` parameter is accepted for API compatibility with the previous
Gemini-based version but ignored — the CLI uses whatever model your
subscription defaults to.
"""

import json
import re
import shutil
import subprocess


CLAUDE_TIMEOUT_SECONDS = 180  # generous; CLI can be slow on first invocation


def _run_claude(prompt: str) -> str:
    """Invoke `claude -p` with the prompt piped over stdin, return stdout, stripped."""
    # On Windows, `claude` is often an npm-installed `.cmd` shim. subprocess
    # with shell=False uses CreateProcess directly, which — unlike cmd.exe —
    # does not search PATHEXT, so a bare "claude" silently fails to resolve
    # even though it works fine when typed in a shell. shutil.which() does
    # honor PATHEXT on Windows, so resolve the full path through it first.
    claude_path = shutil.which("claude") or "claude"

    # The prompt is piped via stdin rather than passed as a CLI argument.
    # Windows launches .cmd shims through an implicit cmd.exe wrapper, whose
    # command-line parsing mangles multi-line arguments (embedded newlines
    # break token/quote handling), silently truncating or corrupting long
    # prompts. Piping sidesteps that entirely and also avoids OS argv-length
    # limits on any platform.
    try:
        result = subprocess.run(
            [claude_path, "-p"],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CLAUDE_TIMEOUT_SECONDS,
            check=False,
        )
    except FileNotFoundError:
        raise RuntimeError(
            "`claude` command not found. Install the Claude CLI and verify with "
            "`claude --version` before running PromptDoctor."
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError(
            f"Claude CLI timed out after {CLAUDE_TIMEOUT_SECONDS}s. "
            "This can happen on very long prompts or slow network — try again."
        )

    if result.returncode != 0:
        raise RuntimeError(
            f"Claude CLI exited with code {result.returncode}.\n"
            f"stderr: {(result.stderr or '')[:500]}"
        )

    return (result.stdout or "").strip()


def call_text(model: str, prompt: str) -> str:
    """Send a prompt, return the raw response text."""
    return _run_claude(prompt)


def call_json(model: str, prompt: str, response_schema: dict) -> dict:
    """
    Send a prompt with an appended JSON-format instruction, parse the reply.

    Unlike the Gemini API's response_schema mode which guarantees valid JSON,
    the CLI just returns text. We ask the model to emit a JSON object matching
    the schema and then defensively strip common wrappers (markdown fences,
    prose preambles) before parsing.
    """
    schema_hint = json.dumps(response_schema, indent=2)
    wrapped = (
        f"{prompt}\n\n"
        f"---\n"
        f"Respond with ONLY a single JSON object matching this schema. "
        f"No markdown code fences. No prose before or after. Just the JSON.\n\n"
        f"Schema:\n{schema_hint}"
    )

    raw = _run_claude(wrapped)
    cleaned = raw.strip()

    # Strip ```json ... ``` fences if the model added them despite instructions.
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```\s*$", "", cleaned)

    # If there's leading prose, extract the first {...} block.
    if not cleaned.startswith("{"):
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            cleaned = match.group(0)

    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Claude CLI returned non-JSON despite the format instruction.\n"
            f"Error: {e}\n"
            f"Raw output (first 500 chars):\n{raw[:500]}"
        )
