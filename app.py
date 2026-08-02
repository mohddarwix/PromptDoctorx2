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

    # HITL state
    if "hitl_state" not in st.session_state:
        st.session_state.hitl_state = None
    if "hitl_prompt" not in st.session_state:
        st.session_state.hitl_prompt = ""

    hitl_mode = st.toggle(
        "Human in the loop",
        value=False,
        help="Review each iteration's issues before the reviser rewrites the prompt.",
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

        if hitl_mode:
            st.session_state.hitl_state = {"current_prompt": rough, "phase": "start"}
            st.session_state.hitl_prompt = rough
            st.rerun()
        else:
            with st.spinner("Running the agent loop..."):
                traj = doctor(rough, verbose=False)
            _render_completed_trajectory(traj)

    # HITL: continue an in-progress session
    if hitl_mode and st.session_state.hitl_state is not None:
        from agent import doctor_step, Trajectory

        state = st.session_state.hitl_state

        # If a button (Accept/Skip/Stop) just set a pending decision while we
        # were parked at "await_user", consume it first. Otherwise the loop
        # below would see phase == "await_user" and never call doctor_step
        # again, silently re-rendering the same stale pause screen forever.
        if state.get("phase") == "await_user" and "user_decision" in state:
            state = doctor_step(state)

        while state.get("phase") not in ("await_user", "done"):
            state = doctor_step(state)

        if state.get("iterations"):
            st.markdown("#### Iterations so far")
            for it in state["iterations"]:
                _render_iteration(it, is_final=False)

        if state.get("phase") == "await_user":
            verdict = state["pending_verdict"]
            score = int(verdict.get("score", 0))
            issues = verdict.get("issues", []) or []

            st.markdown("---")
            st.markdown(f"#### Iteration {len(state['iterations']) + 1} — judge's verdict")
            badge_color = "green" if score >= 8 else "orange" if score >= 5 else "red"
            st.markdown(f":{badge_color}[**Score: {score} / 10**]")

            if issues:
                st.markdown("**Issues found:**")
                for issue in issues:
                    st.markdown(f"- `{issue.get('type', '?')}` — {issue.get('description', '')}")

            st.markdown("**What do you want to do?**")
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("✅ Accept revision", use_container_width=True, key="hitl_accept"):
                    state["user_decision"] = "accept"
                    st.rerun()
            with c2:
                if st.button("⏭️ Skip (retry same)", use_container_width=True, key="hitl_skip"):
                    state["user_decision"] = "skip"
                    st.rerun()
            with c3:
                if st.button("🛑 Stop here", use_container_width=True, key="hitl_stop"):
                    state["user_decision"] = "stop"
                    st.rerun()

        elif state.get("phase") == "done":
            traj = Trajectory(
                original_prompt=st.session_state.hitl_prompt,
                final_prompt=state["current_prompt"],
                iterations=state["iterations"],
                converged=state.get("converged", False),
                stopped_reason=state.get("stopped_reason", ""),
            )
            run_history.append_run(traj)
            st.markdown("---")
            _render_completed_trajectory(traj)

            if st.button("Start a new run", key="hitl_reset"):
                st.session_state.hitl_state = None
                st.rerun()


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
