# Glyco Datasets

## Main Risk Dataset

Use `diabetes_binary_health_indicators_BRFSS2015.csv.zip`.

Implemented pipeline:

- Extract CSV from zip.
- Drop duplicate rows before splitting.
- Write reproducible prepared splits to `data/processed/risk_train.csv.gz` and `data/processed/risk_test.csv.gz`.
- Preserve the artifact feature order recorded in `risk_metadata.json`.
- Train logistic regression baseline and a histogram gradient boosting final model.
- Choose the operating threshold on the held-out split by maximizing positive-class F1.
- Map probability to risk level as `low < 0.30`, `medium < 0.65`, `high >= 0.65`.
- Save artifacts to `ml/artifacts`.

Current risk model metrics:

- `model_version`: `hist-gradient-boosting-risk-0.3`
- `roc_auc`: `0.8189`
- `average_precision`: `0.4448`
- `brier_score`: `0.1812`
- `threshold`: `0.6422`
- Positive-class recall: `0.6122`
- Positive-class precision: `0.3915`
- Positive-class F1: `0.4776`

Backend inference defaults for missing BRFSS inputs not collected in the UI:

- `CholCheck=1`
- `HvyAlcoholConsump=0`
- `AnyHealthcare=1`
- `NoDocbcCost=0`
- `MentHlth=3`
- `PhysHlth=2` unless `difficulty_walking=True`, then `5`
- `Education=4`
- `Income=5`
- `Age` is converted from the real age to the BRFSS age bucket used by the trained dataset

## Monitoring Dataset

Use `diabetes.zip`, which contains the UCI diabetes time-series archive.

Implemented processing:

- Extract compressed archive.
- Parse patient/time/event records.
- Clean malformed numeric tokens such as `0Hi` by keeping the numeric portion.
- Coerce malformed event codes to null and drop invalid rows.
- Skip malformed lines during parsing.
- Aggregate patient events into daily glucose summaries.
- Build rolling features: mean, std, min, max, counts, high/low counts, slope, and 3-day windows.
- Derive labels from future-window rules rather than native source labels.
- Write a patient-wise split to `data/processed/trend_train.csv.gz` and `data/processed/trend_test.csv.gz`.
- Write `data/processed/trend_train_balanced.csv.gz` by oversampling minority labels inside the training split only.
- Keep the test split untouched and verify `patient_overlap=[]` in `trend_dataset_summary.json`.
- Save artifacts to `ml/artifacts`.

Current monitoring model metrics:

- `model_version`: `glucose-trend-random-forest-0.3`
- `patients`: `70`
- `rows`: `3859`
- Accuracy: `0.8126`
- Baseline accuracy: `0.7091`
- Watch-class recall: `0.5161`
- Watch-class F1: `0.4706`
- The `watch` class is still weaker than `stable` and `concerning`, but the v0.3 model now uses a glucose-only feature contract and stronger class weight for `watch`.

Processed monitoring snapshot contract:

- The stable contract is the glucose-only feature order stored in `trend_preprocessor.joblib`.
- Any future processed monitoring snapshot must preserve that exact feature order.
- When user logs do not contain enough history to construct a stable feature row, the backend falls back to the deterministic monitoring engine with a "more data needed" style summary.

## CGM Forecast Dataset

Use the processed CGM features in `data/processed/cgm_features.csv`.

Current dense-CGM forecast metrics:

- `model_version`: `hybrid-lgbm-baseline-forecast-0.3`
- Held-out patient: `Subject 5`
- 60 min: `MAE=1.9564 mmol/L`, deployment strategy `last_delta`
- 120 min: `MAE=3.1334 mmol/L`, deployment strategy `last_delta`
- 180 min: `MAE=3.5177 mmol/L`, deployment strategy `persistence`
- 240 min: `MAE=3.5853 mmol/L`, deployment strategy `rolling_mean_6`

The deployed forecast is intentionally hybrid: it trains LightGBM for every horizon, records those metrics, and only uses LightGBM when it beats simple glucose baselines on the held-out patient split. This avoids deploying a model prediction that is less useful than a transparent baseline.

## Postprandial Forecast Dataset

Use the recovered CGMacros participant CSVs.

Current post-meal forecast metrics:

- `model_version`: `cgmacros-postprandial-lgbm-0.2`
- `training_rows`: `609`
- Held-out patients: `CGMacros-030`, `CGMacros-033`, `CGMacros-048`
- 30 min: `MAE=1.5524 mmol/L`, `R2=0.4969`
- 60 min: `MAE=2.1891 mmol/L`, `R2=0.3680`
- 120 min: `MAE=2.4096 mmol/L`, `R2=0.2749`
