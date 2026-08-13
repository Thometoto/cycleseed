from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path

from .analysis import assign_cycles
from .features import feature_vector
from .model import OnlineLogisticModel, classification_metrics
from .schema import read_observations
from .synthetic import generate_cycles, generate_days_file, generate_file


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic data and pre-train the experimental CycleSeed classifier.")
    parser.add_argument("--data", type=Path, default=Path("data/synthetic_5000_days.csv"))
    parser.add_argument("--personal-data", type=Path, help="Optional personal CSV to read chronologically.")
    parser.add_argument("--model", type=Path, default=Path("models/base_model.json"))
    parser.add_argument("--cycles", type=int, default=500)
    parser.add_argument("--days", type=int, help="Generate exactly this many consecutive days.")
    parser.add_argument("--end-date", type=date.fromisoformat, help="Last synthetic date in YYYY-MM-DD format.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--generate", action="store_true")
    args = parser.parse_args(argv)
    if args.generate or not args.data.exists():
        if args.days:
            end_date = args.end_date or (date.today() - timedelta(days=1))
            generate_days_file(args.data, args.days, end_date, args.seed)
        else:
            generate_file(args.data, args.cycles, args.seed)
    synthetic_observations = read_observations(args.data)
    personal_observations = read_observations(args.personal_data) if args.personal_data else []
    dates = [obs.date for obs in synthetic_observations + personal_observations]
    if len(dates) != len(set(dates)):
        raise ValueError("The two datasets contain at least one duplicate date.")
    observations = assign_cycles(synthetic_observations + personal_observations)
    cycle_ids = sorted(set(obs.cycle_id for obs in observations))
    training_end = max(1, round(len(cycle_ids) * 0.70))
    validation_end = max(training_end + 1, round(len(cycle_ids) * 0.85))
    training_ids = set(cycle_ids[:training_end])
    validation_ids = set(cycle_ids[training_end:validation_end])
    train_examples, validation_examples, holdout_examples = [], [], []
    by_cycle = {}
    for obs in observations:
        by_cycle.setdefault(obs.cycle_id, []).append(obs)
    for cycle_id, cycle in by_cycle.items():
        expected = float(cycle[0].synthetic_ovulation_day or 14)
        target = train_examples if cycle_id in training_ids else (
            validation_examples if cycle_id in validation_ids else holdout_examples
        )
        for index, obs in enumerate(cycle):
            if obs.synthetic_label_fertile is not None:
                target.append((feature_vector(cycle, index, expected), obs.synthetic_label_fertile))
    model = OnlineLogisticModel()
    model.fit(train_examples)
    labels = [label for _, label in validation_examples]
    probabilities = [model.predict_proba(features) for features, _ in validation_examples]
    model.validation_metrics = classification_metrics(labels, probabilities, model.decision_threshold)
    holdout_labels = [label for _, label in holdout_examples]
    holdout_probabilities = [model.predict_proba(features) for features, _ in holdout_examples]
    model.test_metrics = classification_metrics(
        holdout_labels, holdout_probabilities, model.decision_threshold
    )

    independent = assign_cycles(
        generate_cycles(50, seed=args.seed + 10_000, start_date=date(1990, 1, 1))
    )
    independent_by_cycle = {}
    for obs in independent:
        independent_by_cycle.setdefault(obs.cycle_id, []).append(obs)
    independent_examples = []
    for cycle in independent_by_cycle.values():
        expected = float(cycle[0].synthetic_ovulation_day or 14)
        independent_examples.extend(
            (feature_vector(cycle, index, expected), obs.synthetic_label_fertile)
            for index, obs in enumerate(cycle)
            if obs.synthetic_label_fertile is not None
        )
    independent_labels = [label for _, label in independent_examples]
    independent_probabilities = [model.predict_proba(features) for features, _ in independent_examples]
    independent_metrics = classification_metrics(
        independent_labels, independent_probabilities, model.decision_threshold
    )
    model.test_metrics.update({f"independent_{name}": value for name, value in independent_metrics.items()})
    model.validation_metrics["synthetic_labeled_rows"] = float(
        len(train_examples) + len(validation_examples) + len(holdout_examples)
    )
    model.validation_metrics["personal_unlabeled_rows"] = float(len(personal_observations))
    model.save(args.model)
    print(f"Model written to {args.model}")
    print("Metrics on synthetic data only:", model.validation_metrics)
    print("Holdout metrics not used for tuning:", model.test_metrics)
    if personal_observations:
        print(
            f"Personal dataset read: {len(personal_observations)} row(s); "
            "kept for follow-up but not used as false ground truth."
        )
