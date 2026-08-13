# Synthetic data assumptions

The generator creates artificial observations exclusively for software development and testing. It does not reproduce a clinical cohort and cannot validate the model.

## Simulated parameters

- Target mean cycle length of approximately 30 days, with realistic short- and long-cycle variability.
- High-temperature phase centered around 11.8 days.
- Individual follicular temperature centered around 36.4 °C.
- Typical post-ovulatory rise between 0.25 and 0.50 °C.
- Daily noise, occasional peri-ovulatory dips, and disturbed readings.
- Synthetic menstruation lasting 3 to 6 days. `menstrual` is available to the model, while `menstrual_flow` is stored for tracking only.
- Anovulatory cycles, missing temperatures, gradual or weak rises, clustered disturbances, luteal dips, and atypical mucus patterns.
- A synthetic multiclass phase label: `MENSTRUATION`, `FOLLICULAR`, `FERTILE_WINDOW`, `LUTEAL`, or `ANOVULATORY_UNCERTAIN`. This label is never requested from a user.
- Cervical mucus usually progresses from `DRY/STICKY` through `CREAMY`, `WATERY`, and `EGG_WHITE` near ovulation, then returns to `STICKY/DRY`.
- The binary fertile label covers five days before through one day after simulated ovulation.

The user-provided reference chart was used only as a visual check for a plausible biphasic pattern. It was not digitized as clinical training data.

## Interpretation

Strong performance on this dataset means that the model recovered the generator's structure. It does not demonstrate performance on real cycles, generalization across users, contraceptive effectiveness, or clinical safety.
