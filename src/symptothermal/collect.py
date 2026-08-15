from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path

from .schema import MENSTRUAL_FLOWS, MUCOUS_TYPES, DailyObservation, read_observations, upsert_observation


def _choice(prompt: str, choices, default: str) -> str:
    value = input(f"{prompt} {choices} [{default}] : ").strip().upper() or default
    if value not in choices:
        raise ValueError(f"Invalid value: {value}")
    return value


def _yes_no(prompt: str) -> bool:
    return input(f"{prompt} [y/N]: ").strip().lower() in ("y", "yes")


def _optional_yes_no(prompt: str):
    value = input(f"{prompt} [y/n/?]: ").strip().lower()
    if value in ("y", "yes"):
        return True
    if value in ("n", "no"):
        return False
    return None


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Record a daily symptothermal observation in CycleSeed.")
    parser.add_argument("--file", type=Path, default=Path("data/personal.csv"))
    parser.add_argument("--date", dest="observation_date", help="Observation date in YYYY-MM-DD format.")
    parser.add_argument("--new-cycle", action="store_true", help="Use on the first day of a new cycle.")
    args = parser.parse_args(argv)
    existing = read_observations(args.file)
    menstruation = _yes_no("Menstruation today?")
    spotting = _yes_no("Spotting today?") if not menstruation else False
    menstrual_flow = _choice("Menstrual flow", MENSTRUAL_FLOWS[1:], "MEDIUM") if menstruation else "NONE"
    menstruation_started = menstruation and (not existing or not existing[-1].menstrual)
    if not existing or args.new_cycle or menstruation_started:
        previous_number = max(
            [int(item.cycle_id.rsplit("-", 1)[-1]) for item in existing if item.cycle_id.startswith("personal-")],
            default=0,
        )
        cycle_id = f"personal-{previous_number + 1:04d}"
    else:
        cycle_id = existing[-1].cycle_id
    observation_date = args.observation_date or input(
        f"Date in YYYY-MM-DD format [{date.today().isoformat()}]: "
    ).strip() or date.today().isoformat()
    raw_temperature = input("Basal temperature in °C (leave blank if unavailable): ").strip().replace(",", ".")
    observation = DailyObservation(
        date=observation_date,
        temperature_c=float(raw_temperature) if raw_temperature else None,
        mucus_type=_choice("Cervical mucus", MUCOUS_TYPES, "DRY"),
        disturbed=_yes_no("Disturbed reading (alcohol, illness, poor sleep, travel, etc.)?"),
        pms=_optional_yes_no("Premenstrual symptoms (PMS) today?"),
        menstrual=menstruation,
        menstrual_flow=menstrual_flow,
        spotting=spotting,
        cycle_id=cycle_id,
    )
    observation.validate()
    upsert_observation(args.file, observation)
    print(f"Observation saved to {args.file}")
