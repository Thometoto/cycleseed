from __future__ import annotations

import csv
from dataclasses import asdict, dataclass, fields
from datetime import date
from pathlib import Path
from typing import List, Optional


MUCOUS_TYPES = ("DRY", "STICKY", "CREAMY", "WATERY", "EGG_WHITE")
MENSTRUAL_FLOWS = ("NONE", "LIGHT", "MEDIUM", "HEAVY")


@dataclass
class DailyObservation:
    date: str
    temperature_c: Optional[float] = None
    mucus_type: str = "DRY"
    disturbed: bool = False
    pms: Optional[bool] = None
    menstrual: bool = False
    menstrual_flow: str = "NONE"
    cycle_id: str = ""
    cycle_day: Optional[int] = None
    synthetic_label_fertile: Optional[int] = None
    synthetic_ovulation_day: Optional[int] = None
    synthetic_phase_label: str = ""

    def validate(self) -> None:
        date.fromisoformat(self.date)
        if self.temperature_c is not None and not 34.0 <= self.temperature_c <= 42.0:
            raise ValueError("Temperature must be between 34 and 42 °C.")
        if self.mucus_type not in MUCOUS_TYPES:
            raise ValueError("Invalid cervical mucus type.")
        if self.menstrual_flow not in MENSTRUAL_FLOWS:
            raise ValueError("Invalid menstrual flow.")
        if not self.menstrual and self.menstrual_flow != "NONE":
            raise ValueError("Menstrual flow cannot be recorded when menstruation is absent.")


def _parse_optional_float(value: str) -> Optional[float]:
    return None if value in ("", None) else float(value)


def _parse_optional_int(value: str) -> Optional[int]:
    return None if value in ("", None) else int(value)


def _parse_bool(value: str) -> bool:
    return str(value).lower() in ("1", "true", "yes", "oui")


def _parse_optional_bool(value: str) -> Optional[bool]:
    if value in ("", None, "None", "null", "unknown"):
        return None
    return _parse_bool(value)


def read_observations(path: Path) -> List[DailyObservation]:
    if not path.exists():
        return []
    result = []
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            obs = DailyObservation(
                date=row["date"],
                temperature_c=_parse_optional_float(row.get("temperature_c", "")),
                mucus_type=row.get("mucus_type", "DRY"),
                disturbed=_parse_bool(row.get("disturbed", "")),
                pms=_parse_optional_bool(row.get("pms", "")),
                menstrual=_parse_bool(row.get("menstrual", row.get("menstruation", ""))),
                menstrual_flow=row.get("menstrual_flow", "NONE") or "NONE",
                cycle_id=row.get("cycle_id", ""),
                cycle_day=_parse_optional_int(row.get("cycle_day", "")),
                synthetic_label_fertile=_parse_optional_int(row.get("synthetic_label_fertile", "")),
                synthetic_ovulation_day=_parse_optional_int(row.get("synthetic_ovulation_day", "")),
                synthetic_phase_label=row.get("synthetic_phase_label", ""),
            )
            obs.validate()
            result.append(obs)
    return sorted(result, key=lambda item: item.date)


def write_observations(path: Path, observations: List[DailyObservation]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    names = [field.name for field in fields(DailyObservation)]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=names)
        writer.writeheader()
        for observation in sorted(observations, key=lambda item: item.date):
            observation.validate()
            writer.writerow(asdict(observation))


def upsert_observation(path: Path, observation: DailyObservation) -> None:
    observations = read_observations(path)
    observations = [item for item in observations if item.date != observation.date]
    observations.append(observation)
    write_observations(path, observations)
