# Glyco Datasets

## Main Risk Dataset

Use `diabetes_binary_health_indicators_BRFSS2015.csv.zip`.

Implemented pipeline:

- Extract CSV from zip.
- Drop duplicate rows before splitting.
- Write reproducible prepared splits to `data/processed/risk_train.csv.gz` and `data/processed/risk_test.csv.gz`.
- Preserve the artifact feature order recorded in `risk_metadata.json`.
- Train logistic regression baseline and a random forest final model.
- Use threshold `0.35` for positive-class screening behavior.
- Map probability to risk level as `low < 0.30`, `medium < 0.65`, `high >= 0.65`.
- Save artifacts to `ml/artifacts`.

Current risk model metrics:

- `model_version`: `random-forest-0.1`
- `roc_auc`: `0.8104`
- Positive-class recall: `0.7934`
- Positive-class precision: `0.3081`

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
- Build rolling features: mean, std, min, max, counts, high/low counts, insulin total, meal events, exercise events, hypo events, slope, and 3-day windows.
- Derive labels from future-window rules rather than native source labels.
- Write a patient-wise split to `data/processed/trend_train.csv.gz` and `data/processed/trend_test.csv.gz`.
- Write `data/processed/trend_train_balanced.csv.gz` by oversampling minority labels inside the training split only.
- Keep the test split untouched and verify `patient_overlap=[]` in `trend_dataset_summary.json`.
- Save artifacts to `ml/artifacts`.

Current monitoring model metrics:

- `model_version`: `trend-random-forest-0.1`
- `patients`: `70`
- `rows`: `3859`
- Accuracy: `0.8148`
- Baseline accuracy: `0.6839`
- The `watch` class is weaker than `stable` and `concerning`, and this limitation is documented rather than hidden.

Processed monitoring snapshot contract:

- The stable contract is the feature order stored in `trend_preprocessor.joblib`.
- Any future processed monitoring snapshot must preserve that exact feature order.
- When user logs do not contain enough history to construct a stable feature row, the backend falls back to the deterministic monitoring engine with a "more data needed" style summary.
