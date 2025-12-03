# -*- coding: utf-8 -*-
"""
game_state.py

Core data structures for the Medical Triage Decision Game.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import List, Dict, Optional

from .config import (
    DifficultyLevel,
    INITIAL_SURVIVAL_SCORE,
    INITIAL_STAFF_STRESS,
    INITIAL_REPUTATION,
    TOTAL_ROUNDS,
    MAX_BEDS,
    MAX_STAFF_CAPACITY,
)


class SeverityLevel(Enum):
    MILD = auto()
    MODERATE = auto()
    SEVERE = auto()
    CRITICAL = auto()


class TriageDecision(Enum):
    TREAT_NOW = auto()
    MONITOR = auto()
    DEFER = auto()
    TRANSFER = auto()


@dataclass
class Patient:
    id: int
    name: str
    severity_visible: SeverityLevel
    severity_hidden_true: SeverityLevel
    arrival_round: int

    is_treated: bool = False
    is_alive: bool = True
    has_left: bool = False

    def display_label(self) -> str:
        return f"{self.name} (appears {self.severity_visible.name.title()})"


@dataclass
class HospitalState:
    available_beds: int = MAX_BEDS
    staff_capacity_this_round: int = MAX_STAFF_CAPACITY

    survival_score: float = INITIAL_SURVIVAL_SCORE
    staff_stress: float = INITIAL_STAFF_STRESS
    reputation: float = INITIAL_REPUTATION


@dataclass
class RoundSummary:
    round_number: int
    decisions: Dict[int, TriageDecision] = field(default_factory=dict)
    patients_treated: List[int] = field(default_factory=list)
    patients_died: List[int] = field(default_factory=list)
    patients_deteriorated: List[int] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


@dataclass
class GameState:
    difficulty: DifficultyLevel
    current_round: int = 1
    patients: List[Patient] = field(default_factory=list)
    history: List[RoundSummary] = field(default_factory=list)
    hospital: HospitalState = field(default_factory=HospitalState)
    next_patient_id: int = 1

    def is_game_over(self) -> bool:
        if self.current_round > TOTAL_ROUNDS:
            return True

        if self.hospital.survival_score <= 0:
            return True

        if self.hospital.staff_stress >= 100:
            return True

        if self.hospital.reputation <= 0:
            return True

        return False

    def has_player_won(self) -> Optional[bool]:
        from .config import (
            MIN_SURVIVAL_TO_WIN,
            MAX_STAFF_STRESS_TO_WIN,
            MIN_REPUTATION_TO_WIN,
        )

        if not self.is_game_over():
            return None

        # Win only if we survived all rounds
        if self.current_round <= TOTAL_ROUNDS:
            return False

        if (
            self.hospital.survival_score >= MIN_SURVIVAL_TO_WIN
            and self.hospital.staff_stress <= MAX_STAFF_STRESS_TO_WIN
            and self.hospital.reputation >= MIN_REPUTATION_TO_WIN
        ):
            return True

        return False

    def add_round_summary(self, summary: RoundSummary) -> None:
        self.history.append(summary)

    def get_patient_by_id(self, pid: int) -> Optional[Patient]:
        for p in self.patients:
            if p.id == pid:
                return p
        return None

    def alive_patients(self) -> List[Patient]:
        return [
            p
            for p in self.patients
            if p.is_alive and not p.is_treated and not p.has_left
        ]

    def increment_round(self) -> None:
        self.current_round += 1
        self.hospital.staff_capacity_this_round = MAX_STAFF_CAPACITY
