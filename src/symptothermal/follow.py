from __future__ import annotations

import argparse
import csv
import json
from datetime import date
from pathlib import Path

from .analysis import estimate_today, forecast_calendar, retrospective_personal_examples
from .model import OnlineLogisticModel
from .schema import read_observations


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Analyze personal observations and create an experimental CycleSeed forecast.")
    parser.add_argument("--data", type=Path, default=Path("data/personal.csv"))
    parser.add_argument("--history-data", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--model", type=Path, default=Path("models/base_model.json"))
    parser.add_argument("--personal-model", type=Path, default=Path("models/personal_model.json"))
    parser.add_argument("--profile", type=Path, default=Path("data/profile.json"))
    parser.add_argument("--initial-cycle-day", type=int, help="Approximate cycle day at first launch.")
    parser.add_argument("--average-cycle-length", type=int, help="Usual average cycle length.")
    parser.add_argument(
        "--initial-phase", choices=("MENSTRUATION", "FOLLICULAR", "OVULATORY", "LUTEAL", "UNKNOWN"),
        help="Approximate phase at first launch.",
    )
    parser.add_argument("--output", type=Path, default=Path("output"))
    args = parser.parse_args(argv)
    personal_observations = read_observations(args.data)
    if not personal_observations:
        raise ValueError("No personal data found. Run collect.py before daily_followup.py.")
    if args.history_data:
        raise ValueError("Synthetic data must not be used for personal follow-up.")

    if args.profile.exists():
        profile = json.loads(args.profile.read_text(encoding="utf-8"))
    else:
        cycle_day = args.initial_cycle_day
        if cycle_day is None:
            cycle_day = int(input("Approximate cycle day today: ").strip())
        if cycle_day < 1 or cycle_day > 90:
            raise ValueError("The approximate cycle day must be between 1 and 90.")
        phase = args.initial_phase
        if phase is None:
            print("Phases: MENSTRUATION, FOLLICULAR, OVULATORY, LUTEAL, UNKNOWN")
            phase = input("Approximate current phase: ").strip().upper()
        if phase not in ("MENSTRUATION", "FOLLICULAR", "OVULATORY", "LUTEAL", "UNKNOWN"):
            raise ValueError("Invalid initial phase.")
        average_cycle_length = args.average_cycle_length
        if average_cycle_length is None:
            average_cycle_length = int(input("Average number of days in your cycle: ").strip())
        if average_cycle_length < 15 or average_cycle_length > 90:
            raise ValueError("Average cycle length must be between 15 and 90 days.")
        profile = {
            "anchor_date": personal_observations[-1].date,
            "anchor_cycle_day": cycle_day,
            "initial_phase": phase,
            "average_cycle_length": average_cycle_length,
            "theoretical_until_complete_cycle": True,
        }
        args.profile.parent.mkdir(parents=True, exist_ok=True)
        args.profile.write_text(json.dumps(profile, indent=2), encoding="utf-8")

    anchor = date.fromisoformat(profile["anchor_date"])
    anchor_day = int(profile["anchor_cycle_day"])
    first_cycle_id = personal_observations[0].cycle_id
    for observation in personal_observations:
        if observation.cycle_id == first_cycle_id:
            observation.cycle_day = anchor_day + (date.fromisoformat(observation.date) - anchor).days
    observations = personal_observations
    model = OnlineLogisticModel.load(args.personal_model if args.personal_model.exists() else args.model)
    personal_examples, processed_cycles = retrospective_personal_examples(
        observations, model.processed_personal_cycles
    )
    if personal_examples:
        model.partial_fit(personal_examples, learning_rate=0.002)
        model.processed_personal_cycles.extend(processed_cycles)
        model.save(args.personal_model)
    cycles = {}
    for observation in personal_observations:
        cycles.setdefault(observation.cycle_id, []).append(observation)
    completed_cycles = list(cycles.values())[:-1]
    has_complete_personal_cycle = any(
        cycle and cycle[0].cycle_day == 1 and cycle[0].menstrual
        for cycle in completed_cycles
    )
    if has_complete_personal_cycle:
        profile["theoretical_until_complete_cycle"] = False
        args.profile.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    theoretical = bool(profile.get("theoretical_until_complete_cycle", True))
    estimate = estimate_today(
        observations, model, initial_phase=profile.get("initial_phase"),
        theoretical_estimate=theoretical,
        average_cycle_length=int(profile.get("average_cycle_length", 26)),
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "today.json").write_text(json.dumps(estimate.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
    calendar = forecast_calendar(estimate)
    with (args.output / "forecast.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["date", "cycle_day", "forecast_state"])
        writer.writeheader()
        writer.writerows(calendar)
    print(json.dumps(estimate.to_dict(), indent=2, ensure_ascii=False))
    print("\nSUMMARY")
    print(f"Cycle day: {estimate.cycle_day}")
    print(f"Estimated phase: {estimate.cycle_phase}")
    print(f"Fertility: {estimate.fertility_status}")
    print(f"Pregnancy timing: {estimate.baby_timing}")
    print(f"Theoretical estimate: {'YES' if estimate.theoretical_estimate else 'NO'}")
    print(f"\nRetrospective personal examples used: {len(personal_examples)}")
    print("\nWARNING: experimental tool; not validated for decisions about unprotected intercourse.")
