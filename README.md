# CycleSeed

CycleSeed is an experimental, privacy-first symptothermal cycle tracker. It records daily observations, trains a lightweight fertility-window classifier, adapts cautiously to completed personal cycles, and displays cycle phases in a chart and calendar.

> [!WARNING]
> CycleSeed is not a medical device or a validated contraceptive method. Its scores are not pregnancy probabilities and must not be used to decide that unprotected intercourse is safe. Synthetic data tests software behavior; it does not establish clinical effectiveness.

## Features

- Records the date, basal temperature, cervical mucus, disturbed readings, PMS, menstruation, and menstrual flow.
- Stores health data locally in CSV and JSON files.
- Trains an interpretable online logistic-regression classifier without third-party dependencies.
- Combines model predictions with explicit thermal-shift and cervical-mucus heuristics.
- Distinguishes theoretical, reported, and observation-supported phases.
- Shows cycle progress, temperature history, and a three-month phase calendar.
- Updates a personal model only from completed, retrospectively interpretable cycles.

## Requirements

Python 3.9 or newer. The core application has no third-party dependencies.

## Quick start

Train the initial model from the supplied synthetic dataset:

```bash
/usr/bin/python3 train_model.py
```

Launch the local graphical interface:

```bash
/usr/bin/python3 gui.py
```

CycleSeed opens in the default browser. Nothing is published or sent over the internet. Press `Ctrl+C` in the terminal to stop the local server.

The command-line workflow remains available:

```bash
/usr/bin/python3 collect.py
/usr/bin/python3 daily_followup.py
```

On the first follow-up, CycleSeed asks for the approximate current cycle day, approximate phase, and average cycle length. Results remain marked as theoretical until one complete personal cycle has been observed.

## iPad progressive web app

The `pwa/` directory contains a separate browser-only edition designed for private testing on iPad. It can be hosted free of charge with GitHub Pages and added to the iPad Home Screen from Safari.

- Observations and profile data stay in the browser storage of that iPad.
- The app works offline after its first successful visit.
- JSON backup and CSV export make it possible to transfer observations for later research.
- Removing the app, clearing Safari website data, or losing the iPad can erase local observations, so regular exports are essential.
- The embedded model is a browser-compatible copy of the experimental logistic-regression model; no Python server is involved.

The included GitHub Pages workflow deploys `pwa/` after it is merged into `main` and Pages is configured to use **GitHub Actions** in the repository settings.

## Optional installation

```bash
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/cycleseed
```

## Data files

- `data/synthetic_5000_days.csv`: artificial training and software-test data only.
- `data/personal.csv`: personal daily observations.
- `data/profile.json`: first-use cycle anchor and average cycle length.
- `models/base_model.json`: model trained from synthetic data.
- `models/personal_model.json`: optional adaptation from completed personal cycles.
- `output/today.json`: latest analysis.
- `output/forecast.csv`: experimental calendar forecast.

Personal and synthetic observations remain separate. Personal observations are never treated as ground truth unless a completed cycle can be labeled retrospectively by the current research heuristic.

## Model

The current classifier is an online logistic regression implemented in pure Python. Training uses cycle-level train, validation, and holdout splits, gives additional weight to fertile examples, and runs a second independent synthetic test.

`model_probability` is the classifier score for membership in a **simulated** fertile interval. It is not a probability of pregnancy. `ovulation_passed_confidence` is an explainable heuristic score, not medically calibrated confidence.

## Tests

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## Important limitations

Before real-world or contraceptive use, this project would need to:

- implement a published symptothermal method faithfully;
- have its rules and terminology reviewed by qualified professionals;
- train and validate on real data with independently established ovulation labels;
- calibrate uncertainty and evaluate false negatives prospectively;
- define situations in which the software must refuse to conclude;
- complete the applicable medical-device, privacy, security, and clinical-validation work.

See [Synthetic data assumptions](docs/synthetic-data.md) for details about the generated dataset.
