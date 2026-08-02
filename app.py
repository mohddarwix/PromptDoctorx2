"""
Streamlit frontend for PromptDoctor.

Renders the same execute-judge-revise loop as the CLI, but as a visual live-updating
web page. Sidebar shows learned lessons (memory) and session stats (from run_history).
Main column shows the input, live iteration cards, and the final improved prompt.

Run:  streamlit run app.py

The CLI (`python main.py`) still works — this is an additional frontend, not a replacement.
"""

import os

import streamlit as st

import memory
import run_history
from agent import doctor


st.set_page_config(
    page_title="PromptDoctor",
    page_icon="🩺",
    layout="wide",
)


def _render_iteration(it, is_final: bool):
    """Render one iteration as a card."""
    if it.score >= 8:
        badge_color = "green"
    elif it.score >= 5:
        badge_color = "orange"
    else:
        badge_color = "red"

    with st.container(border=True):
        cols = st.columns([3, 1])
        with cols[0]:
            label = f"**Iteration {it.number}**"
            if is_final and it.score >= 8:
                label += " — converged"
            st.markdown(label)
        with cols[1]:
            st.markdown(f":{badge_color}[**{it.score} / 10**]")

        if it.issue_types:
            issue_pills = " ".join(f"`{t}`" for t in it.issue_types)
            st.markdown(issue_pills)


def _render_completed_trajectory(traj):
    """Render a full completed trajectory (used by both plain and HITL modes)."""
    st.markdown("#### Iterations")
    for it in traj.iterations:
        _render_iteration(it, is_final=(it.number == len(traj.iterations)))

    st.markdown("#### Improved prompt")
    outcome_color = "green" if traj.converged else "orange"
    outcome_txt = "converged" if traj.converged else f"stopped: {traj.stopped_reason}"
    st.markdown(f":{outcome_color}[**{outcome_txt}**] after {len(traj.iterations)} iteration(s)")
    st.code(traj.final_prompt, language=None)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Settings")
    max_iter = st.slider("Max iterations", 1, 5, 3)
    threshold = st.slider("Score threshold", 5, 10, 8)

    st.divider()

    st.markdown("### Learned lessons")
    st.caption("Reflexion-style long-term memory. Grows over time.")
    store = memory.load()
    if not store:
        st.info("Memory is empty. Doctor some prompts to accumulate lessons.")
    else:
        ranked = sorted(store.items(), key=lambda kv: (-kv[1], kv[0]))
        for name, count in ranked[:8]:
            col1, col2 = st.columns([3, 1])
            with col1:
                st.markdown(f"`{name}`")
            with col2:
                st.markdown(f"**{count}**")

    st.divider()

    st.markdown("### Session")
    stats = run_history.stats()
    m1, m2 = st.columns(2)
    m1.metric("Total runs", stats["total_runs"])
    m2.metric("Converged", stats["converged_runs"])
    st.metric("Avg iterations", stats["avg_iterations"])


# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------

st.markdown("# 🩺 PromptDoctor")
st.caption("Iterative prompt improvement via execute → judge → revise")


# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------

tab_doctor, tab_history = st.tabs(["Doctor a prompt", "History"])


# --- Doctor tab -------------------------------------------------------------

with tab_doctor:
    rough = st.text_area(
        "Your rough prompt",
        value="write a tweet about AI safety",
        height=100,
        help="Paste the prompt you're about to send to ChatGPT, Claude, or another LLM.",
    )

    col_a, col_b = st.columns([1, 5])
    with col_a:
        run_btn = st.button("🩺 Doctor prompt", type="primary", use_container_width=True)
    with col_b:
        st.write("")

    if run_btn:
        if not rough.strip():
            st.warning("Enter a prompt first.")
            st.stop()

        os.environ["MAX_ITERATIONS"] = str(max_iter)
        os.environ["SCORE_THRESHOLD"] = str(threshold)

        with st.spinner("Running the agent loop..."):
            traj = doctor(rough, verbose=False)

        _render_completed_trajectory(traj)


# --- History tab ------------------------------------------------------------

with tab_history:
    st.markdown("#### Recent runs")
    recent = run_history.load_recent(limit=20)
    if not recent:
        st.info("No runs yet. Doctor a prompt in the other tab.")
    else:
        for rec in recent:
            with st.expander(
                f"{rec['timestamp'][:19]}  •  "
                f"{'✅' if rec.get('converged') else '❌'}  "
                f"{len(rec.get('iterations', []))} iter"
            ):
                st.markdown("**Original:**")
                st.code(rec["original_prompt"], language=None)
                st.markdown("**Final:**")
                st.code(rec["final_prompt"], language=None)
                st.markdown("**Trajectory:**")
                scores = [f"{it['score']}/10" for it in rec.get("iterations", [])]
                st.markdown(" → ".join(scores) if scores else "_(none)_")
