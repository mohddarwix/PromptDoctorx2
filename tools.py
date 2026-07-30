"""
The three tools PromptDoctor uses.

Tool 1  run_prompt      Executes the prompt to gather EVIDENCE of what it produces.
Tool 2  judge_prompt    Evaluates the PROMPT (using output as evidence). Structured critique.
Tool 3  revise_prompt   Rewrites the prompt to fix the specific issues raised.

Why three separate CLI calls and not one mega-call: collapsing execute/judge/revise
into one pass makes the model self-grade its own rewrite. Separating the roles
forces the model to show its work at each step and makes the loop's convergence
signal meaningful.

Since all three tools call the same CLI (same model under the hood), role separation
is enforced at the PROMPT level — each tool's instructions narrow its cognitive
role. The judge is forbidden from proposing fixes; the reviser is forbidden from
re-evaluating quality.
"""

from llm_client import call_text, call_json


# Models are ignored by the CLI wrapper, but we keep the interface for clarity
# and to make future swap-back to an API trivial.
_EXECUTOR_MODEL = "claude-cli-default"
_JUDGE_MODEL = "claude-cli-default"
_REVISER_MODEL = "claude-cli-default"


# ---------------------------------------------------------------------------
# Tool 1 — Executor
# ---------------------------------------------------------------------------

def run_prompt(prompt: str) -> str:
    """
    Run the prompt through the LLM and return raw output.

    This is PromptDoctor's grounding step: the other two tools reason ABOUT the
    prompt, this one produces empirical evidence of what it does.
    """
    return call_text(_EXECUTOR_MODEL, prompt)


# ---------------------------------------------------------------------------
# Tool 2 — Judge
# ---------------------------------------------------------------------------

_JUDGE_INSTRUCTIONS = """You are evaluating the QUALITY OF A PROMPT, not the correctness of its output.

You will be given:
1. A prompt (the artifact being evaluated).
2. The output that prompt produced when run through an LLM (diagnostic evidence).
3. Optionally, a list of common weaknesses this agent has learned to look for from past runs.

Score the PROMPT on a scale from 0 to 10, and list specific ISSUES.

A high-quality prompt:
- Clearly states the task (verb + object).
- Constrains the output format when relevant (length, structure, tone, language).
- Provides sufficient context for the task.
- Is unambiguous — a reader would not need to ask for clarification.
- Does not contradict itself.

Use the OUTPUT as diagnostic evidence:
- If the output is bloated or off-topic, the prompt likely lacks constraints.
- If the output asks a clarifying question, the prompt was ambiguous.
- If the output format is not what a reasonable user would want, the prompt did not specify it.
- If the output is clean and on-target, the prompt is probably good.

Issue "type" fields must be short snake_case identifiers such as:
    no_length_constraint, missing_output_format, vague_task, ambiguous_subject,
    no_tone_specified, missing_context, contradictory_instructions

DO NOT propose fixes or rewrites. Your only job is to critique.
If the prompt is already high-quality (score >= 8), return an empty issues list.
"""


_JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "score": {"type": "integer"},
        "issues": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {"type": "string"},
                    "description": {"type": "string"},
                },
                "required": ["type", "description"],
            },
        },
        "reasoning": {"type": "string"},
    },
    "required": ["score", "issues", "reasoning"],
}


def judge_prompt(prompt: str, output: str, lessons: list = None) -> dict:
    """
    Evaluate prompt quality, using the output as diagnostic evidence.

    Returns:
        {"score": int 0-10,
         "issues": [{"type": str, "description": str}, ...],
         "reasoning": str}
    """
    lessons_hint = ""
    if lessons:
        lessons_hint = (
            "\n\nCommon weaknesses this agent has learned to look for from past runs "
            "(HINTS, not verdicts — evaluate the current prompt on its own merits):\n"
            + "\n".join(f"- {l}" for l in lessons)
        )

    user_msg = f"""{_JUDGE_INSTRUCTIONS}{lessons_hint}

PROMPT UNDER EVALUATION:
\"\"\"
{prompt}
\"\"\"

OUTPUT PRODUCED BY THE PROMPT (evidence):
\"\"\"
{output}
\"\"\"

Return the JSON now."""

    return call_json(_JUDGE_MODEL, user_msg, _JUDGE_SCHEMA)


# ---------------------------------------------------------------------------
# Tool 3 — Reviser
# ---------------------------------------------------------------------------

_REVISER_INSTRUCTIONS = """You are a prompt engineer. You will be given:
1. A prompt that needs improvement.
2. A list of specific issues with it (from a separate judge).
3. Optionally, a list of common weaknesses to be aware of.

Rewrite the prompt so those specific issues are fixed.

Hard rules:
- Preserve the intended task. Do NOT change what the prompt is asking for, only how.
- Fix ONLY the listed issues. Do not introduce unrelated "improvements".
- Do not add examples unless the issues specifically call for them.
- Keep the same language as the original prompt.
- Return ONLY the revised prompt text. No preamble, no explanation, no surrounding quotes.
"""


def revise_prompt(prompt: str, issues: list, lessons: list = None) -> str:
    """
    Rewrite the prompt to fix the specific issues the judge raised.

    `issues` is the list from judge_prompt()'s output; each item is a dict with
    keys "type" and "description".
    """
    lessons_hint = ""
    if lessons:
        lessons_hint = (
            "\n\nCommon weaknesses to be aware of (hints only, not required fixes):\n"
            + "\n".join(f"- {l}" for l in lessons)
        )

    issues_text = "\n".join(
        f"- [{i.get('type', '?')}] {i.get('description', '')}" for i in issues
    ) or "- (no specific issues supplied; polish for clarity and specificity)"

    user_msg = f"""{_REVISER_INSTRUCTIONS}{lessons_hint}

ORIGINAL PROMPT:
\"\"\"
{prompt}
\"\"\"

ISSUES TO FIX:
{issues_text}

Now return the revised prompt (text only, no preamble)."""

    revised = call_text(_REVISER_MODEL, user_msg).strip()

    # Some models add surrounding quotes despite instructions; strip once.
    if len(revised) >= 2 and revised[0] == revised[-1] and revised[0] in ('"', "'"):
        revised = revised[1:-1].strip()

    return revised
