# -*- coding: utf-8 -*-
"""
config.py

Global configuration values for the Medical Triage Decision Game.
"""

from enum import Enum, auto


class DifficultyLevel(Enum):
    BASIC = auto()
    STOCHASTIC = auto()


# Game structure
TOTAL_ROUNDS = 5

# Score / meters
INITIAL_SURVIVAL_SCORE = 100.0
INITIAL_STAFF_STRESS = 10.0
INITIAL_REPUTATION = 60.0

# Win conditions
MIN_SURVIVAL_TO_WIN = 70.0
MAX_STAFF_STRESS_TO_WIN = 40.0
MIN_REPUTATION_TO_WIN = 50.0

# Patients per round
BASIC_PATIENTS_PER_ROUND = (3, 4)
STOCH_PATIENTS_PER_ROUND = (4, 7)

# Severity probabilities
BASIC_SEVERE_PROB = 0.25
STOCH_SEVERE_PROB = 0.45

# Deterioration probabilities
BASIC_DETERIORATE_PROB = 0.15
STOCH_DETERIORATE_PROB = 0.35

# Resources
MAX_BEDS = 5
MAX_STAFF_CAPACITY = 4

# Random seed (None = fresh randomness each run)
RNG_SEED = None
