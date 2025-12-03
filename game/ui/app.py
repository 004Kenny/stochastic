# -*- coding: utf-8 -*-
"""
Streamlit UI for the Medical Triage Decision Game.
"""

import os
import sys

# Ensure project root (/Users/kenny/LukeTheDoctor) is on sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))          # .../game/ui
PROJECT_ROOT = os.path.dirname(os.path.dirname(CURRENT_DIR))      # .../LukeTheDoctor
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import streamlit as st

from game.engine.config import DifficultyLevel, TOTAL_ROUNDS
from game.engine.game_state import GameState, TriageDecision, RoundSummary
from game.engine.stochastic_model import (
    generate_new_patients_for_round,
    apply_player_decisions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _init_game_if_needed(selected_difficulty: DifficultyLevel) -> None:
    """
    Initialize or reset the GameState in Streamlit's session_state.
    """
    if "game_state" not in st.session_state:
        st.session_state.game_state = GameState(difficulty=selected_difficulty)
        st.session_state.current_round_patient_ids = []
        st.session_state.patients_generated_for_round = False
        st.session_state.last_round_summary = None
        st.session_state.difficulty = selected_difficulty
        return

    # If difficulty changed, start a new game
    if st.session_state.get("difficulty") != selected_difficulty:
        st.session_state.game_state = GameState(difficulty=selected_difficulty)
        st.session_state.current_round_patient_ids = []
        st.session_state.patients_generated_for_round = False
        st.session_state.last_round_summary = None
        st.session_state.difficulty = selected_difficulty


def _difficulty_label(level: DifficultyLevel) -> str:
    if level == DifficultyLevel.BASIC:
        return "Basic (more predictable)"
    if level == DifficultyLevel.STOCHASTIC:
        return "Stochastic (higher uncertainty)"
    return level.name


def _render_metrics(game_state: GameState) -> None:
    """
    Show current hospital metrics in a compact layout.
    """
    h = game_state.hospital
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Round", f"{game_state.current_round} / {TOTAL_ROUNDS}")
    col2.metric("Survival Score", f"{h.survival_score:.1f}")
    col3.metric("Staff Stress", f"{h.staff_stress:.1f}")
    col4.metric("Reputation", f"{h.reputation:.1f}")


def _render_last_round_summary() -> None:
    """
    Show what happened in the previous round, including AI feedback.
    """
    summary: RoundSummary | None = st.session_state.get("last_round_summary")
    if summary is None:
        return

    with st.expander(
        f"Last Round Summary (Round {summary.round_number})",
        expanded=False,
    ):
        if summary.patients_treated:
            st.write(
                "Treated patient IDs:",
                ", ".join(map(str, summary.patients_treated)),
            )
        if summary.patients_died:
            st.write(
                "Patients who died:",
                ", ".join(map(str, summary.patients_died)),
            )
        if summary.patients_deteriorated:
            st.write(
                "Patients who deteriorated:",
                ", ".join(map(str, summary.patients_deteriorated)),
            )

        if summary.notes:
            st.markdown("**AI feedback on your decisions this round:**")
            for note in summary.notes:
                st.markdown(f"- {note}")
        elif not (
            summary.patients_treated
            or summary.patients_died
            or summary.patients_deteriorated
        ):
            st.write("No significant events last round.")


def _render_game_over(game_state: GameState) -> None:
    """
    Show game-over message and a restart button.
    """
    result = game_state.has_player_won()

    if result is True:
        st.success(
            f"You completed all {TOTAL_ROUNDS} rounds and met the win conditions."
        )
    elif result is False:
        st.error(
            f"Game over. After {TOTAL_ROUNDS} rounds, you did not meet the win conditions."
        )
    else:
        st.warning(
            f"Game over. After {TOTAL_ROUNDS} rounds, the final outcome is ambiguous."
        )

    _render_metrics(game_state)

    if st.button("Restart Game"):
        current_diff = st.session_state.get("difficulty", DifficultyLevel.BASIC)
        st.session_state.game_state = GameState(difficulty=current_diff)
        st.session_state.current_round_patient_ids = []
        st.session_state.patients_generated_for_round = False
        st.session_state.last_round_summary = None
        st.rerun()


# ---------------------------------------------------------------------------
# Main app
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(page_title="Medical Triage Decision Game", layout="wide")
    st.title("Medical Triage Decision Game")
    st.write(
        "Make triage decisions under uncertainty. "
        "Your choices affect patient survival, staff stress, and hospital reputation."
    )

    # Sidebar: difficulty selection
    st.sidebar.header("Game Settings")
    difficulty_choice = st.sidebar.radio(
        "Select Difficulty",
        options=[DifficultyLevel.BASIC, DifficultyLevel.STOCHASTIC],
        format_func=_difficulty_label,
    )

    _init_game_if_needed(difficulty_choice)
    game_state: GameState = st.session_state.game_state

    st.sidebar.write(f"Current mode: {_difficulty_label(game_state.difficulty)}")

    # 🔹 Explanatory text for stochastic mode
    if game_state.difficulty == DifficultyLevel.STOCHASTIC:
        st.info(
            "Stochastic mode: each round may include random environment shocks that "
            "change staff capacity, available beds, or deterioration risk."
        )

    # Check for terminal state
    if game_state.is_game_over():
        _render_game_over(game_state)
        return

    # Dashboard
    _render_metrics(game_state)
    _render_last_round_summary()

    st.markdown("---")
    st.subheader(f"Round {game_state.current_round}: Incoming Patients")

    # Step 1: generate patients for this round
    if not st.session_state.get("patients_generated_for_round", False):
        if st.button("Generate Patients For This Round"):
            new_patients = generate_new_patients_for_round(game_state)
            st.session_state.current_round_patient_ids = [p.id for p in new_patients]
            st.session_state.patients_generated_for_round = True
            st.rerun()
        else:
            st.info("Click 'Generate Patients For This Round' to see new arrivals.")
            return

    # If we are here, patients for this round exist
    current_ids = st.session_state.get("current_round_patient_ids", [])

    if not current_ids:
        st.warning(
            "No new patients arrived this round. "
            "You can proceed to the next round without decisions."
        )
    else:
        st.write(
            "These patients have just arrived. Based on their visible "
            "severity (which may be noisy), choose a triage decision for each."
        )

    # Step 2: collect decisions in a form
    decisions: dict[int, TriageDecision] = {}

    with st.form(f"triage_form_round_{game_state.current_round}"):
        for pid in current_ids:
            patient = game_state.get_patient_by_id(pid)
            if patient is None or not patient.is_alive or patient.has_left:
                continue

            st.markdown(f"**{patient.display_label()}**")
            choice = st.radio(
                f"Decision for patient {pid}",
                key=f"decision_for_{pid}",
                options=list(TriageDecision),
                format_func=lambda d: {
                    TriageDecision.TREAT_NOW: "Treat now (use beds and staff)",
                    TriageDecision.MONITOR: "Monitor this round",
                    TriageDecision.DEFER: "Defer (delay treatment)",
                    TriageDecision.TRANSFER: "Transfer to another facility",
                }[d],
            )
            decisions[pid] = choice
            st.markdown("---")

        submitted = st.form_submit_button("Apply Decisions And Resolve Round")

    # Step 3: apply decisions and advance round
    if submitted:
        if decisions:
            summary = apply_player_decisions(game_state, decisions)
        else:
            summary = RoundSummary(round_number=game_state.current_round)

        game_state.add_round_summary(summary)
        st.session_state.last_round_summary = summary

        game_state.increment_round()
        st.session_state.current_round_patient_ids = []
        st.session_state.patients_generated_for_round = False

        st.rerun()
    else:
        if current_ids:
            st.info(
                "Set your decisions above and click "
                "'Apply Decisions And Resolve Round'."
            )


if __name__ == "__main__":
    main()
