from __future__ import annotations

import json
import subprocess
import sys
import tkinter as tk
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Optional

from .schema import DailyObservation, MENSTRUAL_FLOWS, MUCOUS_TYPES, read_observations, upsert_observation


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_FILE = PROJECT_ROOT / "data" / "personal.csv"
PROFILE_FILE = PROJECT_ROOT / "data" / "profile.json"
MODEL_FILE = PROJECT_ROOT / "models" / "base_model.json"
OUTPUT_FILE = PROJECT_ROOT / "output" / "today.json"

PHASES = ("MENSTRUATION", "FOLLICULAR", "OVULATORY", "LUTEAL", "UNKNOWN")
PMS_VALUES = ("Unknown", "No", "Yes")


@dataclass
class EntryValues:
    observation_date: str
    temperature: Optional[float]
    mucus_type: str
    disturbed: bool
    pms: Optional[bool]
    menstrual: bool
    menstrual_flow: str


def save_daily_observation(values: EntryValues, path: Path = DATA_FILE) -> DailyObservation:
    existing = read_observations(path)
    menstruation_started = values.menstrual and (not existing or not existing[-1].menstrual)
    if not existing or menstruation_started:
        previous_number = max(
            [int(item.cycle_id.rsplit("-", 1)[-1]) for item in existing if item.cycle_id.startswith("personal-")],
            default=0,
        )
        cycle_id = f"personal-{previous_number + 1:04d}"
    else:
        cycle_id = existing[-1].cycle_id
    observation = DailyObservation(
        date=values.observation_date,
        temperature_c=values.temperature,
        mucus_type=values.mucus_type,
        disturbed=values.disturbed,
        pms=values.pms,
        menstrual=values.menstrual,
        menstrual_flow=values.menstrual_flow if values.menstrual else "NONE",
        cycle_id=cycle_id,
    )
    observation.validate()
    upsert_observation(path, observation)
    return observation


class BootstrapDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, anchor_date: str):
        super().__init__(parent)
        self.title("CycleSeed setup")
        self.resizable(False, False)
        self.result = None
        self.transient(parent)
        self.grab_set()

        body = ttk.Frame(self, padding=18)
        body.grid(sticky="nsew")
        ttk.Label(body, text="First use", font=("TkDefaultFont", 14, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 12)
        )
        ttk.Label(body, text="Approximate cycle day").grid(row=1, column=0, sticky="w", pady=5)
        self.day = tk.StringVar(value="1")
        ttk.Entry(body, textvariable=self.day, width=12).grid(row=1, column=1, sticky="ew", pady=5)
        ttk.Label(body, text="Approximate phase").grid(row=2, column=0, sticky="w", pady=5)
        self.phase = tk.StringVar(value="UNKNOWN")
        ttk.Combobox(body, textvariable=self.phase, values=PHASES, state="readonly", width=20).grid(
            row=2, column=1, sticky="ew", pady=5
        )
        ttk.Label(body, text="Average cycle length").grid(row=3, column=0, sticky="w", pady=5)
        self.average = tk.StringVar(value="30")
        ttk.Entry(body, textvariable=self.average, width=12).grid(row=3, column=1, sticky="ew", pady=5)
        ttk.Label(
            body,
            text="These details remain theoretical until one complete cycle has been observed.",
            wraplength=360,
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 14))
        ttk.Button(body, text="Confirm", command=lambda: self._save(anchor_date)).grid(
            row=5, column=0, columnspan=2, sticky="e"
        )
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def _save(self, anchor_date: str) -> None:
        try:
            day = int(self.day.get())
            average = int(self.average.get())
            if not 1 <= day <= 90 or not 15 <= average <= 90:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid value", "Cycle day: 1–90. Average length: 15–90.", parent=self)
            return
        self.result = {
            "anchor_date": anchor_date,
            "anchor_cycle_day": day,
            "initial_phase": self.phase.get(),
            "average_cycle_length": average,
            "theoretical_until_complete_cycle": True,
        }
        self.destroy()


class SymptothermalApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CycleSeed")
        self.geometry("680x720")
        self.minsize(620, 650)
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        self._build()
        self._toggle_flow()
        if OUTPUT_FILE.exists():
            self._show_result(json.loads(OUTPUT_FILE.read_text(encoding="utf-8")))

    def _build(self) -> None:
        root = ttk.Frame(self, padding=22)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="CycleSeed", font=("TkDefaultFont", 18, "bold")).pack(anchor="w")
        ttk.Label(root, text="Daily tracking. Your data stays on this computer.").pack(anchor="w", pady=(2, 16))

        form = ttk.Frame(root)
        form.pack(fill="x")
        form.columnconfigure(1, weight=1)
        self.date_value = tk.StringVar(value=date.today().isoformat())
        self.temperature = tk.StringVar()
        self.mucus = tk.StringVar(value="DRY")
        self.disturbed = tk.BooleanVar(value=False)
        self.pms = tk.StringVar(value="Unknown")
        self.menstrual = tk.BooleanVar(value=False)
        self.flow = tk.StringVar(value="MEDIUM")

        fields = (
            ("Date", ttk.Entry(form, textvariable=self.date_value)),
            ("Basal temperature (°C)", ttk.Entry(form, textvariable=self.temperature)),
            ("Cervical mucus", ttk.Combobox(form, textvariable=self.mucus, values=MUCOUS_TYPES, state="readonly")),
            ("PMS", ttk.Combobox(form, textvariable=self.pms, values=PMS_VALUES, state="readonly")),
        )
        for row, (label, widget) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 16), pady=6)
            widget.grid(row=row, column=1, sticky="ew", pady=6)

        ttk.Checkbutton(form, text="Disturbed reading", variable=self.disturbed).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=6
        )
        ttk.Checkbutton(
            form, text="Menstruation today", variable=self.menstrual, command=self._toggle_flow
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(form, text="Flow").grid(row=6, column=0, sticky="w", padx=(0, 16), pady=6)
        self.flow_widget = ttk.Combobox(
            form, textvariable=self.flow, values=MENSTRUAL_FLOWS[1:], state="readonly"
        )
        self.flow_widget.grid(row=6, column=1, sticky="ew", pady=6)

        actions = ttk.Frame(root)
        actions.pack(fill="x", pady=18)
        ttk.Button(actions, text="Save and analyze", command=self._save_and_analyze).pack(side="left")

        ttk.Separator(root).pack(fill="x", pady=(2, 16))
        ttk.Label(root, text="Result", font=("TkDefaultFont", 16, "bold")).pack(anchor="w")
        self.result = tk.Text(root, height=18, wrap="word", state="disabled", relief="flat", padx=8, pady=8)
        self.result.pack(fill="both", expand=True, pady=(8, 10))
        ttk.Label(
            root,
            text="Experimental prototype. Not validated for decisions about unprotected intercourse.",
            foreground="#8b1a1a",
        ).pack(anchor="w")
        self.status = tk.StringVar(value="Ready")
        ttk.Label(root, textvariable=self.status).pack(anchor="w", pady=(8, 0))

    def _toggle_flow(self) -> None:
        self.flow_widget.configure(state="readonly" if self.menstrual.get() else "disabled")

    def _entry_values(self) -> EntryValues:
        raw_temperature = self.temperature.get().strip().replace(",", ".")
        pms = {"Yes": True, "No": False, "Unknown": None}[self.pms.get()]
        return EntryValues(
            observation_date=self.date_value.get().strip(),
            temperature=float(raw_temperature) if raw_temperature else None,
            mucus_type=self.mucus.get(), disturbed=self.disturbed.get(), pms=pms,
            menstrual=self.menstrual.get(), menstrual_flow=self.flow.get(),
        )

    def _save(self) -> bool:
        try:
            observation = save_daily_observation(self._entry_values())
        except (ValueError, OSError) as error:
            messagebox.showerror("Invalid input", str(error), parent=self)
            return False
        self.status.set(f"Observation for {observation.date} saved")
        return True

    def _save_and_analyze(self) -> None:
        if not self._save():
            return
        if not MODEL_FILE.exists():
            messagebox.showerror("Model not found", "Run train_model.py first.", parent=self)
            return
        observations = read_observations(DATA_FILE)
        if not PROFILE_FILE.exists():
            dialog = BootstrapDialog(self, observations[-1].date)
            if dialog.result is None:
                self.status.set("Initialization cancelled")
                return
            PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
            PROFILE_FILE.write_text(json.dumps(dialog.result, indent=2), encoding="utf-8")
        self.status.set("Analyzing…")
        self.update_idletasks()
        command = [
            sys.executable, str(PROJECT_ROOT / "daily_followup.py"),
            "--data", str(DATA_FILE), "--model", str(MODEL_FILE), "--profile", str(PROFILE_FILE),
            "--output", str(PROJECT_ROOT / "output"),
        ]
        completed = subprocess.run(command, cwd=str(PROJECT_ROOT), capture_output=True, text=True)
        if completed.returncode != 0:
            messagebox.showerror("Analysis failed", completed.stderr or completed.stdout, parent=self)
            self.status.set("Analysis error")
            return
        self._show_result(json.loads(OUTPUT_FILE.read_text(encoding="utf-8")))
        self.status.set("Analysis complete")

    def _show_result(self, result: dict) -> None:
        warnings = "\n".join(f"• {item}" for item in result.get("warnings", [])) or "None"
        evidence = "\n".join(f"• {item}" for item in result.get("evidence", [])) or "None"
        content = (
            f"Cycle day: {result.get('cycle_day', '—')}\n"
            f"Estimated phase: {result.get('cycle_phase', '—')}\n"
            f"Fertility: {result.get('fertility_status', '—')}\n"
            f"Pregnancy timing: {result.get('baby_timing', '—')}\n"
            f"Theoretical estimate: {'YES' if result.get('theoretical_estimate') else 'NO'}\n"
            f"Estimated ovulation: {result.get('estimated_ovulation_start', '—')} → "
            f"{result.get('estimated_ovulation_end', '—')}\n\n"
            f"Evidence\n{evidence}\n\nWarnings\n{warnings}"
        )
        self.result.configure(state="normal")
        self.result.delete("1.0", "end")
        self.result.insert("1.0", content)
        self.result.configure(state="disabled")


def main() -> None:
    SymptothermalApp().mainloop()


def diagnose() -> None:
    app = SymptothermalApp()
    app.update_idletasks()

    def count_widgets(widget: tk.Misc) -> int:
        return 1 + sum(count_widgets(child) for child in widget.winfo_children())

    print(f"Tk {app.tk.call('info', 'patchlevel')} — {count_widgets(app)} widgets built")
    app.destroy()
