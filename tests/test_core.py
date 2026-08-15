import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from symptothermal.analysis import assign_cycles, detect_thermal_shift, estimate_today, forecast_calendar, retrospective_personal_examples
from symptothermal.features import feature_vector
from symptothermal.web_gui import EntryValues, save_daily_observation
from symptothermal.model import OnlineLogisticModel, classification_metrics
from symptothermal.schema import DailyObservation, read_observations, write_observations
from symptothermal.synthetic import generate_cycles, generate_days


class CoreTests(unittest.TestCase):
    def test_csv_round_trip(self):
        observations = [DailyObservation(
            date="2026-08-11", temperature_c=36.45, mucus_type="CREAMY",
            disturbed=True, menstrual=True, menstrual_flow="MEDIUM", spotting=False,
        )]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "observations.csv"
            write_observations(path, observations)
            loaded = read_observations(path)
        self.assertEqual(loaded[0].mucus_type, "CREAMY")
        self.assertEqual(loaded[0].temperature_c, 36.45)
        self.assertTrue(loaded[0].disturbed)
        self.assertTrue(loaded[0].menstrual)
        self.assertEqual(loaded[0].menstrual_flow, "MEDIUM")
        self.assertFalse(loaded[0].spotting)

    def test_gui_layer_saves_with_core_schema(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "personal.csv"
            saved = save_daily_observation(EntryValues(
                observation_date="2026-08-11", temperature=36.7, mucus_type="STICKY",
                disturbed=False, pms=None, menstrual=False, menstrual_flow="NONE", spotting=True,
            ), path)
            loaded = read_observations(path)
        self.assertEqual(saved.cycle_id, "personal-0001")
        self.assertTrue(saved.spotting)
        self.assertEqual(loaded[0].temperature_c, 36.7)

    def test_synthetic_data_is_reproducible_and_coherent(self):
        first = generate_cycles(3, seed=12)
        second = generate_cycles(3, seed=12)
        self.assertEqual(first, second)
        self.assertTrue(all(20 <= max(x.cycle_day for x in first if x.cycle_id == cycle) <= 42 for cycle in {x.cycle_id for x in first}))
        self.assertTrue(any(x.synthetic_label_fertile == 1 for x in first))
        self.assertTrue(any(x.menstrual for x in first))
        self.assertTrue(all(x.menstrual_flow != "NONE" for x in first if x.menstrual))
        self.assertTrue(all(x.synthetic_phase_label for x in first))
        self.assertIn("LUTEAL", {x.synthetic_phase_label for x in first})

    def test_exact_day_generation(self):
        observations = generate_days(5000, end_date=date(2026, 8, 10), seed=20260811)
        self.assertEqual(len(observations), 5000)
        self.assertEqual(observations[0].date, "2012-12-02")
        self.assertEqual(observations[-1].date, "2026-08-10")
        self.assertEqual(len({item.date for item in observations}), 5000)

    def test_thermal_shift(self):
        temperatures = [36.2, 36.3, 36.25, 36.3, 36.2, 36.25, 36.55, 36.58, 36.6]
        cycle = [DailyObservation(date=f"2026-08-{day:02d}", temperature_c=value, cycle_day=day) for day, value in enumerate(temperatures, 1)]
        self.assertEqual(detect_thermal_shift(cycle), 7)

    def test_training_and_forecast(self):
        observations = assign_cycles(generate_cycles(16, seed=4))
        by_cycle = {}
        for obs in observations:
            by_cycle.setdefault(obs.cycle_id, []).append(obs)
        examples = []
        for cycle in by_cycle.values():
            expected = float(cycle[0].synthetic_ovulation_day or 14)
            examples.extend((feature_vector(cycle, i, expected), obs.synthetic_label_fertile) for i, obs in enumerate(cycle))
        model = OnlineLogisticModel()
        model.fit(examples, epochs=8)
        probabilities = [model.predict_proba(features) for features, _ in examples]
        metrics = classification_metrics(
            [label for _, label in examples], probabilities, model.decision_threshold
        )
        self.assertGreater(metrics["sensitivity"], 0.9)
        estimate = estimate_today(observations, model)
        self.assertEqual(len(forecast_calendar(estimate)), 35)
        self.assertIn(estimate.state, {"POTENTIALLY_FERTILE", "OVULATION_POSSIBLE", "POST_OVULATION_SUPPORTED", "UNCERTAIN"})
        self.assertIn(estimate.baby_timing, {"FAVORABLE", "POSSIBLE", "OUTSIDE_ESTIMATED_WINDOW"})
        first_examples, cycle_ids = retrospective_personal_examples(observations)
        self.assertFalse(first_examples)
        self.assertFalse(cycle_ids)


if __name__ == "__main__":
    unittest.main()
