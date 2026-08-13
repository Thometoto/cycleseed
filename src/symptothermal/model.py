from __future__ import annotations

import json
import math
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

from .features import FEATURE_NAMES


def _sigmoid(value: float) -> float:
    value = max(-30.0, min(30.0, value))
    return 1.0 / (1.0 + math.exp(-value))


@dataclass
class OnlineLogisticModel:
    feature_names: List[str] = field(default_factory=lambda: list(FEATURE_NAMES))
    weights: Dict[str, float] = field(default_factory=lambda: {name: 0.0 for name in FEATURE_NAMES})
    mean: Dict[str, float] = field(default_factory=dict)
    scale: Dict[str, float] = field(default_factory=dict)
    training_examples: int = 0
    validation_metrics: Dict[str, float] = field(default_factory=dict)
    test_metrics: Dict[str, float] = field(default_factory=dict)
    decision_threshold: float = 0.15
    positive_class_weight: float = 5.0
    processed_personal_cycles: List[str] = field(default_factory=list)
    model_purpose: str = "experimental_fertile_interval_classifier"

    def _normalized(self, features: Dict[str, float]) -> Dict[str, float]:
        return {
            name: (features.get(name, 0.0) - self.mean.get(name, 0.0)) / self.scale.get(name, 1.0)
            if name != "bias" else 1.0
            for name in self.feature_names
        }

    def predict_proba(self, features: Dict[str, float]) -> float:
        values = self._normalized(features)
        return _sigmoid(sum(self.weights.get(name, 0.0) * values[name] for name in self.feature_names))

    def fit(self, examples: Sequence[Tuple[Dict[str, float], int]], epochs: int = 30, learning_rate: float = 0.08, seed: int = 7) -> None:
        if not examples:
            raise ValueError("No training examples were provided.")
        for name in self.feature_names:
            if name == "bias":
                self.mean[name], self.scale[name] = 0.0, 1.0
                continue
            values = [features.get(name, 0.0) for features, _ in examples]
            average = sum(values) / len(values)
            variance = sum((value - average) ** 2 for value in values) / max(1, len(values) - 1)
            self.mean[name] = average
            self.scale[name] = max(math.sqrt(variance), 1e-6)
        rng = random.Random(seed)
        shuffled = list(examples)
        for _ in range(epochs):
            rng.shuffle(shuffled)
            for features, label in shuffled:
                normalized = self._normalized(features)
                error = self.predict_proba(features) - label
                example_weight = self.positive_class_weight if label == 1 else 1.0
                for name in self.feature_names:
                    penalty = 0.0005 * self.weights[name] if name != "bias" else 0.0
                    self.weights[name] -= learning_rate * (example_weight * error * normalized[name] + penalty)
        self.training_examples += len(examples)

    def partial_fit(self, examples: Iterable[Tuple[Dict[str, float], int]], learning_rate: float = 0.01) -> None:
        for features, label in examples:
            normalized = self._normalized(features)
            error = self.predict_proba(features) - label
            for name in self.feature_names:
                self.weights[name] -= learning_rate * error * normalized[name]
            self.training_examples += 1

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, sort_keys=True), encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "OnlineLogisticModel":
        return cls(**json.loads(path.read_text(encoding="utf-8")))


def classification_metrics(labels: Sequence[int], probabilities: Sequence[float], threshold: float = 0.15) -> Dict[str, float]:
    predicted = [1 if value >= threshold else 0 for value in probabilities]
    tp = sum(a == b == 1 for a, b in zip(labels, predicted))
    tn = sum(a == b == 0 for a, b in zip(labels, predicted))
    fp = sum(a == 0 and b == 1 for a, b in zip(labels, predicted))
    fn = sum(a == 1 and b == 0 for a, b in zip(labels, predicted))
    return {
        "sensitivity": tp / max(1, tp + fn),
        "specificity": tn / max(1, tn + fp),
        "false_negative_rate": fn / max(1, tp + fn),
        "brier_score": sum((prob - label) ** 2 for label, prob in zip(labels, probabilities)) / max(1, len(labels)),
        "threshold": threshold,
        "examples": float(len(labels)),
        "true_positives": float(tp),
        "true_negatives": float(tn),
        "false_positives": float(fp),
        "false_negatives": float(fn),
    }
