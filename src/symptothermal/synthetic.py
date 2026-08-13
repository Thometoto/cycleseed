from __future__ import annotations

import random
from datetime import date, timedelta
from pathlib import Path
from typing import List

from .schema import DailyObservation, write_observations


def generate_cycles(count: int, seed: int = 42, start_date: date = date(2020, 1, 1)) -> List[DailyObservation]:
    rng = random.Random(seed)
    observations = []
    current = start_date
    for cycle_number in range(1, count + 1):
        # Personalized scenario requested for this test set: mean near 30 days.
        # The 3.4-day variability is informed by Fehring et al.; a small tail is
        # retained to exercise short/long-cycle code paths.
        if rng.random() < 0.95:
            length = max(22, min(38, round(rng.gauss(30.0, 3.4))))
        else:
            length = rng.choice((20, 21, 39, 40, 41, 42))
        # Large BBT cohort: mean high-temperature phase about 11.8 days.
        luteal = max(9, min(16, round(rng.gauss(11.8, 1.4))))
        ovulation = length - luteal
        anovulatory = rng.random() < 0.06
        # Population-level means are near 36.4 C follicular / 36.7 C luteal.
        follicular_temp = rng.gauss(36.4, 0.10)
        shift = max(0.25, min(0.50, rng.gauss(0.34, 0.07)))
        if rng.random() < 0.10:
            shift = rng.uniform(0.15, 0.24)
        gradual_shift = rng.random() < 0.20
        menstruation_days = rng.choice((3, 4, 5, 5, 6))
        disturbance_start = rng.randint(1, length) if rng.random() < 0.18 else -10
        disturbance_length = rng.randint(2, 4)
        luteal_dip_day = ovulation + rng.randint(3, max(3, luteal - 2)) if rng.random() < 0.15 else -10
        for day in range(1, length + 1):
            distance = day - ovulation
            fertile = 0 if anovulatory else int(-5 <= distance <= 1)
            if distance <= -4:
                mucus = "DRY" if rng.random() < 0.7 else "STICKY"
            elif distance <= -2:
                mucus = "CREAMY" if rng.random() < 0.55 else "WATERY"
            elif distance <= 0:
                mucus = "EGG_WHITE" if rng.random() < 0.7 else "WATERY"
            else:
                mucus = "DRY" if rng.random() < 0.75 else "STICKY"
            if anovulatory and mucus in ("WATERY", "EGG_WHITE") and rng.random() < 0.75:
                mucus = rng.choice(("DRY", "STICKY", "CREAMY"))
            if rng.random() < 0.12:
                mucus = rng.choice(("DRY", "STICKY", "CREAMY", "WATERY", "EGG_WHITE"))
            disturbed = rng.random() < 0.05 or disturbance_start <= day < disturbance_start + disturbance_length
            pms = day >= length - 6 and rng.random() < 0.65
            menstruation = day <= menstruation_days
            if not menstruation:
                menstrual_flow = "NONE"
            elif day == 1 or day == menstruation_days:
                menstrual_flow = "LIGHT"
            elif day in (2, 3) and rng.random() < 0.7:
                menstrual_flow = "HEAVY"
            else:
                menstrual_flow = "MEDIUM"
            if menstruation:
                phase_label = "MENSTRUATION"
            elif anovulatory:
                phase_label = "ANOVULATORY_UNCERTAIN"
            elif distance < -5:
                phase_label = "FOLLICULAR"
            elif distance < 0:
                phase_label = "FERTILE_PREOVULATORY"
            elif distance <= 1:
                phase_label = "OVULATION"
            else:
                phase_label = "LUTEAL"
            # A short periovulatory dip is possible but not mandatory.
            periovulatory_dip = rng.uniform(0.05, 0.18) if day == ovulation and rng.random() < 0.45 else 0.0
            if anovulatory or day <= ovulation:
                thermal_increase = 0.0
            elif gradual_shift:
                thermal_increase = shift * min(1.0, (day - ovulation) / 3.0)
            else:
                thermal_increase = shift
            temperature = follicular_temp + thermal_increase - periovulatory_dip + rng.gauss(0, 0.09)
            if day == luteal_dip_day and not anovulatory:
                temperature -= rng.uniform(0.15, 0.30)
            if disturbed:
                temperature += rng.uniform(0.2, 0.7)
            if rng.random() < 0.03:
                temperature = None
            observations.append(DailyObservation(
                date=(current + timedelta(days=day - 1)).isoformat(),
                temperature_c=round(temperature, 2) if temperature is not None else None,
                mucus_type=mucus, disturbed=disturbed, pms=pms,
                menstrual=menstruation, menstrual_flow=menstrual_flow,
                cycle_id=f"synthetic-{cycle_number:04d}", cycle_day=day,
                synthetic_label_fertile=fertile,
                synthetic_ovulation_day=None if anovulatory else ovulation,
                synthetic_phase_label=phase_label,
            ))
        current += timedelta(days=length)
    return observations


def generate_file(path: Path, count: int, seed: int) -> None:
    write_observations(path, generate_cycles(count=count, seed=seed))


def generate_days(count: int, end_date: date, seed: int = 42) -> List[DailyObservation]:
    """Generate exactly ``count`` consecutive synthetic days ending on ``end_date``."""
    if count < 1:
        raise ValueError("The number of days must be positive.")
    first_date = end_date - timedelta(days=count - 1)
    cycles = generate_cycles(
        count=(count // 20) + 20,
        seed=seed,
        start_date=first_date,
    )
    return cycles[:count]


def generate_days_file(path: Path, count: int, end_date: date, seed: int) -> None:
    write_observations(path, generate_days(count=count, end_date=end_date, seed=seed))
