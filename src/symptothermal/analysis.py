from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from statistics import mean, pstdev
from typing import Dict, List, Optional, Tuple

from .features import feature_vector, is_disturbed
from .model import OnlineLogisticModel
from .schema import DailyObservation


@dataclass
class DailyEstimate:
    date: str
    cycle_day: int
    cycle_phase: str
    fertility_status: str
    baby_timing: str
    theoretical_estimate: bool
    initialization_source: str
    state: str
    model_probability: float
    potentially_fertile: bool
    ovulation_passed_confidence: float
    estimated_ovulation_start: str
    estimated_ovulation_end: str
    evidence: List[str]
    warnings: List[str]
    rule_version: str = "experimental-0.1"

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


def assign_cycles(observations: List[DailyObservation]) -> List[DailyObservation]:
    cycle_number = 0
    cycle_start: Optional[date] = None
    active_cycle_id = ""
    for obs in observations:
        current = date.fromisoformat(obs.date)
        if cycle_start is None or (obs.cycle_id and obs.cycle_id != active_cycle_id):
            cycle_number += 1
            cycle_start = current - timedelta(days=(obs.cycle_day or 1) - 1)
            active_cycle_id = obs.cycle_id or f"personal-{cycle_number:04d}"
        if cycle_start is None:
            cycle_number = max(1, cycle_number)
            cycle_start = current
        obs.cycle_id = obs.cycle_id or active_cycle_id
        obs.cycle_day = (current - cycle_start).days + 1
    return observations


def _historical_ovulations(observations: List[DailyObservation]) -> List[int]:
    by_cycle: Dict[str, List[DailyObservation]] = {}
    for obs in observations:
        by_cycle.setdefault(obs.cycle_id, []).append(obs)
    estimates = []
    for cycle in list(by_cycle.values())[:-1]:
        shift = detect_thermal_shift(cycle)
        if shift is not None:
            estimates.append(max(1, shift - 1))
    return estimates


def retrospective_personal_examples(
    observations: List[DailyObservation], excluded_cycle_ids: Optional[List[str]] = None
) -> Tuple[List[Tuple[Dict[str, float], int]], List[str]]:
    """Create weak labels only from completed cycles with a detected shift.

    These labels are deliberately treated as heuristic, not ground truth. The current
    cycle is excluded so future observations never leak into today's prediction.
    """
    observations = assign_cycles(observations)
    by_cycle: Dict[str, List[DailyObservation]] = {}
    for obs in observations:
        by_cycle.setdefault(obs.cycle_id, []).append(obs)
    examples: List[Tuple[Dict[str, float], int]] = []
    processed = []
    excluded = set(excluded_cycle_ids or [])
    for cycle_id, cycle in list(by_cycle.items())[:-1]:
        if not cycle_id.startswith("personal-"):
            continue
        if not cycle or cycle[0].cycle_day != 1 or not cycle[0].menstrual:
            continue
        if cycle_id in excluded:
            continue
        shift = detect_thermal_shift(cycle)
        if shift is None:
            continue
        estimated_ovulation = max(1, shift - 1)
        for index, obs in enumerate(cycle):
            day = obs.cycle_day or 1
            label = int(estimated_ovulation - 5 <= day <= estimated_ovulation + 1)
            examples.append((feature_vector(cycle, index, float(estimated_ovulation)), label))
        processed.append(cycle_id)
    return examples, processed


def detect_thermal_shift(cycle: List[DailyObservation]) -> Optional[int]:
    """Research heuristic, not a validated symptothermal-method rule."""
    clean = [(obs.cycle_day or 0, obs.temperature_c) for obs in cycle if obs.temperature_c is not None and not is_disturbed(obs)]
    for index in range(6, len(clean) - 2):
        previous = [value for _, value in clean[index - 6:index]]
        threshold = max(previous) + 0.15
        next_three = clean[index:index + 3]
        if all(value >= threshold for _, value in next_three):
            return next_three[0][0]
    return None


def estimate_today(
    observations: List[DailyObservation], model: OnlineLogisticModel,
    initial_phase: Optional[str] = None, theoretical_estimate: bool = False,
    average_cycle_length: Optional[int] = None,
) -> DailyEstimate:
    if not observations:
        raise ValueError("No observations are available.")
    observations = assign_cycles(observations)
    current_id = observations[-1].cycle_id
    current_cycle = [obs for obs in observations if obs.cycle_id == current_id]
    today = current_cycle[-1]
    history = _historical_ovulations(observations)
    expected = mean(history) if history else float(max(6, (average_cycle_length or 26) - 12))
    spread = max(2.0, pstdev(history) if len(history) >= 2 else 3.0)
    probability = model.predict_proba(feature_vector(current_cycle, len(current_cycle) - 1, expected))
    shift = detect_thermal_shift(current_cycle)
    mucus_peak_day = max(
        (obs.cycle_day or 0 for obs in current_cycle if obs.mucus_type in ("WATERY", "EGG_WHITE")),
        default=None,
    )
    day = today.cycle_day or 1
    thermal_days = day - shift + 1 if shift is not None else 0
    mucus_days = day - mucus_peak_day if mucus_peak_day is not None else 0
    post_confidence = 0.0
    evidence, warnings = [], []
    if thermal_days >= 3:
        post_confidence += 0.55
        evidence.append("A sustained thermal rise was detected across 3 valid readings.")
    if mucus_peak_day is not None and mucus_days >= 3:
        post_confidence += 0.25
        evidence.append("The last fertile-type cervical mucus sign was observed at least 3 days ago.")
    if today.mucus_type in ("WATERY", "EGG_WHITE"):
        probability = max(probability, 0.85)
        evidence.append("Fertile-type cervical mucus or sensation was observed today.")
    if is_disturbed(today):
        warnings.append("The temperature reading may be disturbed; confidence has been reduced.")
        post_confidence *= 0.65
    if len(history) < 3:
        warnings.append("Fewer than 3 interpretable cycles are available; the calendar prior is highly uncertain.")
    post_confidence = min(post_confidence, 0.95)
    potentially_fertile = probability >= model.decision_threshold or post_confidence < 0.8
    if post_confidence >= 0.8:
        state = "POST_OVULATION_SUPPORTED"
        cycle_phase = "LUTEAL_PHASE_SUPPORTED"
    elif potentially_fertile:
        state = "POTENTIALLY_FERTILE"
        cycle_phase = "OVULATORY_WINDOW_POSSIBLE" if probability >= 0.65 else "FOLLICULAR_PHASE_OR_UNCERTAIN"
    else:
        state = "UNCERTAIN"
        cycle_phase = "PHASE_UNCERTAIN"
    if today.pms is True:
        evidence.append("PMS was reported; this is compatible with a premenstrual phase but has no standalone contraceptive value.")
    if theoretical_estimate and initial_phase:
        reported_phases = {
            "MENSTRUATION": "MENSTRUATION_REPORTED",
            "FOLLICULAR": "FOLLICULAR_PHASE_REPORTED",
            "OVULATORY": "OVULATORY_WINDOW_REPORTED",
            "LUTEAL": "LUTEAL_PHASE_REPORTED_UNCONFIRMED",
            "UNKNOWN": "PHASE_UNCERTAIN",
        }
        cycle_phase = reported_phases.get(initial_phase, "PHASE_UNCERTAIN")
        state = "PHASE_REPORTED_UNCONFIRMED"
        warnings.append(
            "User-provided initialization: cycle day and phase remain theoretical until one complete personal cycle is observed."
        )
        if initial_phase == "OVULATORY":
            probability = max(probability, 0.7)
            potentially_fertile = True
    if today.menstrual:
        cycle_phase = "MENSTRUATION_OBSERVED"
        evidence.append("Menstruation was reported today; flow is stored for tracking only.")
    cycle_start = date.fromisoformat(today.date) - timedelta(days=day - 1)
    if shift is not None and thermal_days >= 3:
        # Once a sustained shift is visible, physiology overrides the calendar prior.
        # Ovulation is represented conservatively around the day before the rise.
        lower = max(1, shift - 2)
        upper = shift
    else:
        lower = max(1, round(expected - 2 * spread))
        upper = round(expected + 2 * spread)
    estimated_start = cycle_start + timedelta(days=lower - 1)
    estimated_end = cycle_start + timedelta(days=upper - 1)
    today_date = date.fromisoformat(today.date)
    possible_start = estimated_start - timedelta(days=5)
    possible_end = estimated_end + timedelta(days=1)
    favorable_start = estimated_start - timedelta(days=2)
    if favorable_start <= today_date <= possible_end and probability >= 0.65:
        baby_timing = "FAVORABLE"
    elif possible_start <= today_date <= possible_end and post_confidence < 0.8:
        baby_timing = "POSSIBLE"
    else:
        baby_timing = "OUTSIDE_ESTIMATED_WINDOW"
    fertility_status = "POTENTIALLY_FERTILE" if potentially_fertile else "FERTILITY_NOT_CURRENTLY_DETECTED"
    return DailyEstimate(
        date=today.date, cycle_day=day, cycle_phase=cycle_phase,
        fertility_status=fertility_status, baby_timing=baby_timing,
        theoretical_estimate=theoretical_estimate,
        initialization_source="USER_APPROXIMATION" if theoretical_estimate else "OBSERVED_PERSONAL_CYCLE",
        state=state, model_probability=round(probability, 4),
        potentially_fertile=potentially_fertile, ovulation_passed_confidence=round(post_confidence, 4),
        estimated_ovulation_start=estimated_start.isoformat(),
        estimated_ovulation_end=estimated_end.isoformat(),
        evidence=evidence, warnings=warnings,
    )


def forecast_calendar(estimate: DailyEstimate, days: int = 35) -> List[Dict[str, object]]:
    start = date.fromisoformat(estimate.date) - timedelta(days=estimate.cycle_day - 1)
    ovulation_start = date.fromisoformat(estimate.estimated_ovulation_start)
    ovulation_end = date.fromisoformat(estimate.estimated_ovulation_end)
    fertile_start = ovulation_start - timedelta(days=5)
    fertile_end = ovulation_end + timedelta(days=1)
    rows = []
    for offset in range(days):
        current = start + timedelta(days=offset)
        if current < date.fromisoformat(estimate.date):
            status = "OBSERVED_PAST"
        elif fertile_start <= current <= fertile_end:
            status = "POTENTIALLY_FERTILE_FORECAST"
        elif current > fertile_end:
            status = "FORECAST_UNCERTAIN_POST_WINDOW"
        else:
            status = "FORECAST_UNCERTAIN_PRE_WINDOW"
        rows.append({"date": current.isoformat(), "cycle_day": offset + 1, "forecast_state": status})
    return rows
