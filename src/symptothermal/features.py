from __future__ import annotations

from statistics import mean
from typing import Dict, List

from .schema import DailyObservation


FEATURE_NAMES = [
    "bias", "cycle_day_scaled", "temperature_delta", "fertile_mucus",
    "disturbed", "menstrual", "history_prior",
]


def is_disturbed(obs: DailyObservation) -> bool:
    return obs.disturbed


def feature_vector(observations: List[DailyObservation], index: int, expected_ovulation: float = 14.0) -> Dict[str, float]:
    obs = observations[index]
    previous = [
        item.temperature_c for item in observations[max(0, index - 6):index]
        if item.temperature_c is not None and not is_disturbed(item)
    ]
    baseline = mean(previous) if len(previous) >= 3 else obs.temperature_c
    delta = 0.0
    if obs.temperature_c is not None and baseline is not None and not is_disturbed(obs):
        delta = max(-1.0, min(1.0, (obs.temperature_c - baseline) / 0.4))
    cycle_day = obs.cycle_day or 1
    distance = abs(cycle_day - expected_ovulation)
    return {
        "bias": 1.0,
        "cycle_day_scaled": min(cycle_day, 45) / 45.0,
        "temperature_delta": delta,
        "fertile_mucus": 1.0 if obs.mucus_type in ("WATERY", "EGG_WHITE") else (0.5 if obs.mucus_type == "CREAMY" else 0.0),
        "disturbed": 1.0 if is_disturbed(obs) else 0.0,
        "menstrual": 1.0 if obs.menstrual else 0.0,
        "history_prior": max(0.0, 1.0 - distance / 8.0),
    }
