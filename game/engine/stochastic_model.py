# -*- coding: utf-8 -*-
"""
stochastic_model.py

Probabilistic behavior for the game:
- Patient arrival generation
- Hidden vs visible severity
- Deterioration and outcomes
- AI-style explanations of decisions and outcomes
- Random environment shocks in STOCHASTIC difficulty
- Narrative layer describing realistic hospital scenarios
"""

from __future__ import annotations

from typing import List, Tuple, Dict
import random

from .config import (
    DifficultyLevel,
    BASIC_PATIENTS_PER_ROUND,
    STOCH_PATIENTS_PER_ROUND,
    BASIC_SEVERE_PROB,
    STOCH_SEVERE_PROB,
    BASIC_DETERIORATE_PROB,
    STOCH_DETERIORATE_PROB,
    RNG_SEED,
    MAX_BEDS,
)
from .game_state import (
    GameState,
    Patient,
    SeverityLevel,
    TriageDecision,
    RoundSummary,
)

# Single RNG instance so we can control seeding centrally
_rng = random.Random(RNG_SEED)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _patients_per_round(difficulty: DifficultyLevel) -> Tuple[int, int]:
    if difficulty == DifficultyLevel.BASIC:
        return BASIC_PATIENTS_PER_ROUND
    return STOCH_PATIENTS_PER_ROUND


def _severe_probability(difficulty: DifficultyLevel) -> float:
    if difficulty == DifficultyLevel.BASIC:
        return BASIC_SEVERE_PROB
    return STOCH_SEVERE_PROB


def _deterioration_probability(difficulty: DifficultyLevel) -> float:
    if difficulty == DifficultyLevel.BASIC:
        return BASIC_DETERIORATE_PROB
    return STOCH_DETERIORATE_PROB


def _sample_true_severity(severe_prob: float) -> SeverityLevel:
    """
    Simple two-bucket model:
    - with probability severe_prob -> SEVERE or CRITICAL
    - otherwise -> MILD or MODERATE
    """
    x = _rng.random()
    if x < severe_prob:
        return SeverityLevel.SEVERE if _rng.random() < 0.6 else SeverityLevel.CRITICAL
    else:
        return SeverityLevel.MILD if _rng.random() < 0.5 else SeverityLevel.MODERATE


def _severity_to_int(sev: SeverityLevel) -> int:
    mapping = {
        SeverityLevel.MILD: 0,
        SeverityLevel.MODERATE: 1,
        SeverityLevel.SEVERE: 2,
        SeverityLevel.CRITICAL: 3,
    }
    return mapping[sev]


def _int_to_severity(idx: int) -> SeverityLevel:
    idx = max(0, min(3, idx))
    if idx == 0:
        return SeverityLevel.MILD
    if idx == 1:
        return SeverityLevel.MODERATE
    if idx == 2:
        return SeverityLevel.SEVERE
    return SeverityLevel.CRITICAL


def _noisy_visible_severity(
    true_severity: SeverityLevel,
    difficulty: DifficultyLevel,
) -> SeverityLevel:
    """
    Visible severity is a noisy observation of true severity.

    BASIC:
        ~80% correct, else off by +/-1

    STOCHASTIC:
        ~60% correct, 30% off by +/-1, 10% off by +/-2
    """
    true_idx = _severity_to_int(true_severity)
    r = _rng.random()

    if difficulty == DifficultyLevel.BASIC:
        if r < 0.8:
            delta = 0
        else:
            delta = _rng.choice([-1, 1])
    else:
        if r < 0.6:
            delta = 0
        elif r < 0.9:
            delta = _rng.choice([-1, 1])
        else:
            delta = _rng.choice([-2, 2])

    visible_idx = true_idx + delta
    return _int_to_severity(visible_idx)


def _death_probability(
    true_severity: SeverityLevel,
    treated: bool,
    decision: TriageDecision,
) -> float:
    """
    Per-round death probability based on severity and decision.
    """
    base = {
        SeverityLevel.MILD: 0.01,
        SeverityLevel.MODERATE: 0.05,
        SeverityLevel.SEVERE: 0.15,
        SeverityLevel.CRITICAL: 0.30,
    }[true_severity]

    if treated:
        # Treatment reduces risk but does not remove it
        if true_severity in (SeverityLevel.SEVERE, SeverityLevel.CRITICAL):
            return base * 0.25
        return base * 0.10

    # Not treated this round; adjust by decision type
    if decision == TriageDecision.MONITOR:
        return base * 1.2
    if decision == TriageDecision.DEFER:
        return base * 2.0
    if decision == TriageDecision.TRANSFER:
        # Off-site; some extra risk due to transport
        return base * 1.5

    return base


def _update_metrics_for_patient_outcome(
    game_state: GameState,
    patient: Patient,
    died: bool,
    decision: TriageDecision,
) -> None:
    """
    Adjust survival_score, staff_stress, and reputation for this patient's outcome.
    """
    hospital = game_state.hospital

    if died:
        hospital.survival_score -= 4.0
        hospital.reputation -= 2.0
        hospital.staff_stress += 3.0
    else:
        hospital.survival_score += 0.5
        hospital.reputation += 0.5

    # Decision load and optics
    if decision == TriageDecision.TREAT_NOW:
        hospital.staff_stress += 1.0
        hospital.reputation += 0.5
    elif decision == TriageDecision.MONITOR:
        hospital.staff_stress += 0.5
    elif decision == TriageDecision.DEFER:
        hospital.reputation -= 1.0
    elif decision == TriageDecision.TRANSFER:
        if hospital.available_beds <= 0 or hospital.staff_capacity_this_round <= 0:
            hospital.reputation += 0.5
        else:
            hospital.reputation -= 1.0

    # Clamp metrics
    hospital.survival_score = max(0.0, min(100.0, hospital.survival_score))
    hospital.staff_stress = max(0.0, min(100.0, hospital.staff_stress))
    hospital.reputation = max(0.0, min(100.0, hospital.reputation))


def _deteriorate_severity_if_needed(
    game_state: GameState,
    patient: Patient,
    deterioration_prob: float,
) -> bool:
    """
    Possibly worsen a patient's true severity by one level.
    Returns True if severity worsened.
    """
    if not patient.is_alive or patient.is_treated or patient.has_left:
        return False

    if _rng.random() < deterioration_prob:
        current_idx = _severity_to_int(patient.severity_hidden_true)
        if current_idx < _severity_to_int(SeverityLevel.CRITICAL):
            new_idx = current_idx + 1
            patient.severity_hidden_true = _int_to_severity(new_idx)
            return True
    return False


def _describe_severity(sev: SeverityLevel) -> str:
    """Human-friendly severity description for explanations."""
    mapping = {
        SeverityLevel.MILD: "mild",
        SeverityLevel.MODERATE: "moderate",
        SeverityLevel.SEVERE: "severe",
        SeverityLevel.CRITICAL: "critical",
    }
    return mapping[sev]


def _explain_decision_and_outcome(
    summary: RoundSummary,
    patient: Patient,
    visible_severity: SeverityLevel,
    true_severity_at_decision: SeverityLevel,
    decision: TriageDecision,
    treated_this_round: bool,
    died: bool,
) -> None:
    """
    Generate an AI-style explanation string for this patient's outcome
    and append it to summary.notes.
    """
    visible_text = _describe_severity(visible_severity)
    true_text = _describe_severity(true_severity_at_decision)
    decision_label = {
        TriageDecision.TREAT_NOW: "treat now",
        TriageDecision.MONITOR: "monitor",
        TriageDecision.DEFER: "defer",
        TriageDecision.TRANSFER: "transfer",
    }[decision]

    outcome_text = "survived this round"
    if died:
        outcome_text = "died this round"

    # Basic assessment of decision vs true severity
    if decision == TriageDecision.TREAT_NOW and true_severity_at_decision in (
        SeverityLevel.SEVERE,
        SeverityLevel.CRITICAL,
    ):
        quality = "aligned with the high true risk"
    elif decision == TriageDecision.TREAT_NOW and true_severity_at_decision in (
        SeverityLevel.MILD,
        SeverityLevel.MODERATE,
    ):
        quality = "conservative, using resources on a lower-risk patient"
    elif decision in (TriageDecision.MONITOR, TriageDecision.DEFER) and true_severity_at_decision in (
        SeverityLevel.SEVERE,
        SeverityLevel.CRITICAL,
    ):
        quality = "risky given the underlying severity"
    elif decision == TriageDecision.TRANSFER and true_severity_at_decision in (
        SeverityLevel.SEVERE,
        SeverityLevel.CRITICAL,
    ):
        quality = "high-risk, depending on external capacity"
    else:
        quality = "reasonable for the estimated risk"

    # Uncertainty commentary
    if visible_severity != true_severity_at_decision:
        uncertainty_part = (
            f"Note: the patient appeared {visible_text}, "
            f"but was actually {true_text}, illustrating diagnostic uncertainty."
        )
    else:
        uncertainty_part = (
            f"In this case, the visible severity ({visible_text}) matched "
            f"the true severity, so uncertainty played a smaller role."
        )

    treatment_part = (
        "You allocated scarce beds/staff to this patient."
        if treated_this_round
        else "You did not allocate full treatment capacity this round."
    )

    explanation = (
        f"Patient {patient.id}: appeared {visible_text}, true severity {true_text}. "
        f"You chose to {decision_label}, which was {quality}. "
        f"As a result, the patient {outcome_text}. "
        f"{treatment_part} {uncertainty_part}"
    )

    summary.notes.append(explanation)


def _apply_environment_shocks(
    game_state: GameState,
    summary: RoundSummary,
    base_deterioration_prob: float,
) -> float:
    """
    In STOCHASTIC mode, introduce random environment events that
    affect resources and risk for this round AND describe them narratively.

    Returns the (possibly updated) deterioration probability.
    """
    if game_state.difficulty != DifficultyLevel.STOCHASTIC:
        return base_deterioration_prob

    hospital = game_state.hospital
    roll = _rng.random()

    # ~20% chance each for three main shock types; otherwise no major shock.
    if roll < 0.20:
        # Staff shortage: thematic narrative + mechanical impact
        original = hospital.staff_capacity_this_round
        new_capacity = max(1, int(round(original * 0.6)))
        hospital.staff_capacity_this_round = new_capacity

        summary.notes.append(
            "Scenario: A respiratory virus has spread among hospital staff. "
            "Several nurses and residents call in sick just before the shift, "
            "forcing you to manage with fewer people on the floor."
        )
        summary.notes.append(
            f"Environment event: unexpected staff shortage reduced staff capacity "
            f"from {original} to {new_capacity} this round, making 'Treat now' "
            f"decisions more expensive."
        )

    elif roll < 0.40:
        # Bed outage: ward or equipment offline
        original = hospital.available_beds
        if original > 0:
            reduction = max(1, original // 2)
            new_beds = max(0, original - reduction)
            hospital.available_beds = new_beds

            summary.notes.append(
                "Scenario: A burst pipe floods one of the surgical wards. "
                "Facilities management has to close several rooms for emergency repairs, "
                "leaving you with fewer usable beds."
            )
            summary.notes.append(
                f"Environment event: a ward outage made some beds unavailable "
                f"({original} → {new_beds} beds) this round, tightening your "
                f"capacity for new admissions."
            )

    elif roll < 0.60:
        # Epidemic / mass-casualty spike: higher deterioration risk
        new_prob = min(0.9, base_deterioration_prob * 1.7)
        summary.notes.append(
            "Scenario: A multi-vehicle highway collision and a local festival outbreak "
            "hit the region at the same time. Incoming patients are more unstable, "
            "and those waiting in the hospital are at higher risk of sudden decline."
        )
        summary.notes.append(
            "Environment event: deterioration risk for untreated patients increased "
            "this round due to the external surge in severe cases."
        )
        base_deterioration_prob = new_prob

    else:
        # No major shock, but still contextual narrative for immersion
        quiet_roll = _rng.random()
        if quiet_roll < 0.5:
            summary.notes.append(
                "Scenario: This round represents a relatively routine shift. "
                "Uncertainty still exists at the patient level, but there are no "
                "major external disruptions to hospital operations."
            )
        else:
            summary.notes.append(
                "Scenario: Community conditions are stable this round. "
                "Your main challenge is triaging with incomplete information "
                "rather than reacting to large external crises."
            )

    return base_deterioration_prob


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_new_patients_for_round(game_state: GameState) -> List[Patient]:
    """
    Create a new batch of patients for the current round, based on difficulty.
    """
    difficulty = game_state.difficulty
    min_p, max_p = _patients_per_round(difficulty)
    severe_prob = _severe_probability(difficulty)

    num_new = _rng.randint(min_p, max_p)
    new_patients: List[Patient] = []

    for _ in range(num_new):
        true_severity = _sample_true_severity(severe_prob)
        visible_severity = _noisy_visible_severity(true_severity, difficulty)

        pid = game_state.next_patient_id
        game_state.next_patient_id += 1

        name = f"Patient {pid}"

        p = Patient(
            id=pid,
            name=name,
            severity_visible=visible_severity,
            severity_hidden_true=true_severity,
            arrival_round=game_state.current_round,
        )

        game_state.patients.append(p)
        new_patients.append(p)

    return new_patients


def apply_player_decisions(
    game_state: GameState,
    decisions: Dict[int, TriageDecision],
) -> RoundSummary:
    """
    Apply player decisions, update patient outcomes and hospital metrics,
    and return a RoundSummary for the current round, including explanations
    and any stochastic environment events with narrative context.
    """
    summary = RoundSummary(round_number=game_state.current_round)
    summary.decisions = dict(decisions)

    hospital = game_state.hospital
    deterioration_prob = _deterioration_probability(game_state.difficulty)

    # Apply environmental randomness for this round (STOCHASTIC only)
    deterioration_prob = _apply_environment_shocks(
        game_state, summary, deterioration_prob
    )

    # 1) Apply explicit decisions
    for pid, decision in decisions.items():
        patient = game_state.get_patient_by_id(pid)
        if patient is None or not patient.is_alive or patient.has_left:
            continue

        treated_this_round = False

        # Capture severities at the decision time for explanation
        true_severity_at_decision = patient.severity_hidden_true
        visible_at_decision = patient.severity_visible

        if decision == TriageDecision.TREAT_NOW:
            if hospital.staff_capacity_this_round > 0 and hospital.available_beds > 0:
                treated_this_round = True
                patient.is_treated = True
                hospital.staff_capacity_this_round -= 1
                hospital.available_beds -= 1
                summary.patients_treated.append(pid)
            else:
                summary.notes.append(
                    f"Patient {patient.id}: you attempted to treat, "
                    f"but there were no beds or staff left, so the decision "
                    f"effectively became 'defer'."
                )
                decision = TriageDecision.DEFER

        elif decision == TriageDecision.TRANSFER:
            patient.has_left = True
            death_prob = _death_probability(
                patient.severity_hidden_true, False, decision
            )
            died = _rng.random() < death_prob
            patient.is_alive = not died
            if died:
                summary.patients_died.append(pid)
            _update_metrics_for_patient_outcome(
                game_state, patient, died=died, decision=decision
            )

            _explain_decision_and_outcome(
                summary=summary,
                patient=patient,
                visible_severity=visible_at_decision,
                true_severity_at_decision=true_severity_at_decision,
                decision=decision,
                treated_this_round=False,
                died=died,
            )
            continue

        # For treat / monitor / defer, compute outcome
        death_prob = _death_probability(
            patient.severity_hidden_true, treated_this_round, decision
        )
        died = _rng.random() < death_prob

        if died:
            patient.is_alive = False
            summary.patients_died.append(pid)

        _update_metrics_for_patient_outcome(
            game_state, patient, died=died, decision=decision
        )

        _explain_decision_and_outcome(
            summary=summary,
            patient=patient,
            visible_severity=visible_at_decision,
            true_severity_at_decision=true_severity_at_decision,
            decision=decision,
            treated_this_round=treated_this_round,
            died=died,
        )

    # 2) Deterioration for in-hospital, untreated patients
    for patient in game_state.patients:
        if not patient.is_alive or patient.has_left:
            continue
        if patient.is_treated:
            continue

        worsened = _deteriorate_severity_if_needed(
            game_state, patient, deterioration_prob
        )
        if worsened:
            summary.patients_deteriorated.append(patient.id)
            summary.notes.append(
                f"Patient {patient.id}: condition deteriorated due to the "
                f"stochastic environment (random health changes over time). "
                f"This models how patients can worsen even without a new decision."
            )

    # 3) Recompute available beds
    occupied_beds = 0
    for p in game_state.patients:
        if p.is_alive and p.is_treated and not p.has_left:
            occupied_beds += 1
    hospital.available_beds = max(0, MAX_BEDS - occupied_beds)

    # Final clamp
    hospital.survival_score = max(0.0, min(100.0, hospital.survival_score))
    hospital.staff_stress = max(0.0, min(100.0, hospital.staff_stress))
    hospital.reputation = max(0.0, min(100.0, hospital.reputation))

    return summary
