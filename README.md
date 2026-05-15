# Glyco

Glyco is a clinical editorial MVP for Type 2 diabetes risk and monitoring support. It combines:

- a FastAPI backend
- a React + Vite frontend
- SQLite persistence
- deterministic clinical rules
- machine-learning artifacts trained from diabetes datasets
- agent memory from user feedback
- report generation and family-sharing views

The product is meant to help users track health data, review risk signals, and generate clinician-friendly summaries. It is not a diagnosis tool.

## What The App Does

### Overview Dashboard

- Shows the latest diabetes risk estimate
- Shows the latest monitoring trend
- Plots glucose history
- Lists the strongest contributing risk factors
- Displays a generated Glyco insight summary

### Risk Check

- Collects a patient profile
- Calculates BMI
- Runs a diabetes risk assessment
- Returns:
  - risk probability
  - risk level
  - ranked contributing factors
  - related health flags
  - suggested next actions

### Monitoring

- Stores simple glucose readings with fasting / not-fasting status
- Rebuilds the monitoring trend after each log entry
- Shows:
  - current monitoring state
  - average glucose
  - variability
  - anomaly notices
  - log history and trend chart

### Agent Memory

- Lets the user ask natural-language questions about risk, trend changes, doctor questions, and family support
- Shows which tools were used: profile, logs, risk model, trend model, guidelines, and memory
- Stores feedback about whether an answer was useful
- Learns a preferred response tone and remembers confirmed actions for future answers

### Reports

- Generates stored report documents for:
  - doctor
  - family
  - weekly review
- Combines the latest risk assessment, monitoring state, and log history

### Care Plan

- Presents simple nutrition and lifestyle guidance
- Gives foods to prefer and limit
- Provides a sample day and weekly recommendations

### Family View

- Shows a simplified shared-care view
- Highlights current status and trend
- Displays a family-friendly glucose chart
- Shows reminders and support suggestions

## Architecture

### Frontend

- React 19
- Vite
- React Router
- TanStack Query
- Recharts
- React Hook Form

### Backend

- FastAPI
- SQLAlchemy
- SQLite
- Pydantic schemas
- Report and insight generation services

### Machine Learning

- Risk model artifacts live in `ml/artifacts`
- Glucose trend model artifacts live in `ml/artifacts`
- Training and dataset-preparation scripts live in `ml/scripts`
- The backend loads the trained artifacts when available
- If artifacts cannot be loaded, the backend falls back to deterministic rules so the app still works

### Agent Learning

Glyco now learns on two levels:

- Offline model learning from diabetes datasets, saved as versioned ML artifacts.
- Online personalization from `agent_feedback`, where user feedback teaches the agent preferred tone and confirmed actions.

## How Data Flows Through The System

1. The frontend collects user profile data or health logs.
2. The backend saves that data into SQLite.
3. The backend converts the saved data into model features.
4. The trained model or rule fallback generates a score, label, and explanation.
5. The result is stored as an assessment or report row in SQLite.
6. The frontend reads the saved rows back and renders the dashboard.

## How Training Data Influences The App

This is the important part: the training datasets do not directly overwrite user-entered data. They influence the predictions and summaries that Glyco generates from user data.

### Risk Model Training Data

The risk model is trained from the CDC BRFSS diabetes dataset:

- source: `diabetes_binary_health_indicators_BRFSS2015.csv.zip`
- preparation script: `ml/scripts/prepare_datasets.py`
- training script: `ml/scripts/train_risk_model.py`

That pipeline:

- removes duplicate rows
- creates a stratified train/test split
- trains a random forest classifier
- saves metadata such as feature names, threshold, and evaluation metrics

When a user submits a profile in the app:

- the backend maps the profile into the same feature shape the model expects
- the model predicts a diabetes risk probability
- the probability is turned into a risk level such as low, medium, or high
- the backend stores the result in the `risk_assessments` table

So the training data influences:

- the risk probability
- the risk label
- the ranked factors shown in the UI
- the stored assessment version and metadata

It does not change the original user profile row.

### Glucose Trend Model Training Data

The monitoring trend model is built from the UCI diabetes time-series archive, but its production feature contract now uses only glucose-derived features that match the simplified patient flow:

- source: `diabetes.zip`
- preparation script: `ml/scripts/prepare_datasets.py`
- monitoring data summary script: `ml/scripts/prepare_monitoring_data.py`
- training script: `ml/scripts/train_monitoring_model.py`

That pipeline:

- parses raw patient event files
- builds daily glucose features
- labels days as `stable`, `watch`, or `concerning`
- splits data by patient so the same patient does not appear in both train and test sets
- oversamples minority labels only in the training split
- trains a class-weighted random forest classifier with extra weight on the difficult `watch` class
- saves model metadata and feature definitions

When a user adds glucose readings:

- the backend rebuilds the recent glucose feature window
- the model predicts the current monitoring state
- the backend stores the outcome in the `monitoring_assessments` table

So the training data influences:

- the monitoring trend label
- the monitoring score
- the anomaly and summary interpretation
- the stored monitoring assessment version

Again, it does not rewrite the user’s logs. It only shapes how those logs are interpreted.

### Fallback Behavior

If the trained artifacts are missing or cannot be loaded:

- the risk flow falls back to deterministic rule-based logic
- the monitoring flow falls back to engineered rules over the saved health logs

That means the app still runs even before training, but the outputs will come from the rules engine instead of the ML model.

## Persistence

The backend stores data in SQLite.

Main tables include:

- users
- profiles
- health_logs
- risk_assessments
- monitoring_assessments
- reports
- family_shares
- agent_feedback

Note: the current SQLite path is relative, so the file location depends on where you start the backend from. If you run it from different folders, you can accidentally create multiple `glyco.db` files.

## Running The App

### Backend

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python -m uvicorn app.main:app --reload
```

Backend URL:

- `http://127.0.0.1:8000`
- API docs: `http://127.0.0.1:8000/docs`

### Frontend

```powershell
cd frontend
npm install
npm run dev
```

Frontend URL:

- `http://127.0.0.1:5173`

If port `5173` is already taken, Vite may choose another nearby port like `5174`.

## Training The Models

The backend works without retraining, but you can regenerate artifacts with the ML scripts:

```powershell
python ml\scripts\prepare_datasets.py
python ml\scripts\train_risk_model.py
python ml\scripts\prepare_monitoring_data.py
python ml\scripts\train_monitoring_model.py
```

Generated outputs are written to:

- `data/processed`
- `ml/artifacts`

## Datasets

- `diabetes_binary_health_indicators_BRFSS2015.csv.zip` is used for the risk model
- `diabetes.zip` is used for the monitoring trend model

## Project Structure

- `backend/` FastAPI app, database models, business logic, reports, ML inference
- `frontend/` React user interface
- `ml/` dataset preparation, training scripts, and saved model artifacts
- `data/` intermediate processed datasets and summaries

## Short Version

Glyco is a diabetes support dashboard that:

- stores patient profile and monitoring data
- scores risk with an ML model trained on CDC data
- scores monitoring trends with an ML model trained on UCI time-series data
- saves assessments and reports in SQLite
- falls back to rules when trained models are unavailable
