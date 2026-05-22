import sys
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.database import SessionLocal
from app.db import models
from app.main import app
from app.ml.inference import ARTIFACTS, _is_lfs_pointer, _load_risk_bundle, _load_trend_bundle, predict_monitoring
from app.rules.engine import calculate_bmi


class GlycoApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(app)

    def test_model_artifacts_load(self) -> None:
        for filename in ("risk_model.joblib", "risk_preprocessor.joblib", "trend_model.joblib", "trend_preprocessor.joblib"):
            self.assertFalse(_is_lfs_pointer(ARTIFACTS / filename), filename)
        risk = _load_risk_bundle()
        trend = _load_trend_bundle()
        self.assertIn("features", risk["preprocessor"])
        self.assertIn("features", trend["preprocessor"])
        self.assertEqual(risk["metadata"]["model_version"], "random-forest-0.2")
        self.assertEqual(trend["metadata"]["model_version"], "glucose-trend-random-forest-0.2")

    def test_seeded_demo_users_cover_high_and_low_risk(self) -> None:
        monitoring_user = self.client.get("/api/risk-assessment/1/latest").json()
        high_user = self.client.get("/api/risk-assessment/2/latest").json()
        low_user = self.client.get("/api/risk-assessment/3/latest").json()
        self.assertEqual(monitoring_user["model_version"], "random-forest-0.2")
        self.assertEqual(monitoring_user["risk_level"], "high")
        self.assertEqual(high_user["risk_level"], "high")
        self.assertEqual(low_user["risk_level"], "low")

    def test_seeded_monitoring_user_is_model_backed(self) -> None:
        monitoring = self.client.get("/api/monitoring-assessment/1/latest").json()
        self.assertEqual(monitoring["model_version"], "glucose-trend-random-forest-0.2")
        self.assertIn(monitoring["trend_label"], {"watch", "concerning"})

    def test_insufficient_history_falls_back_cleanly(self) -> None:
        db = SessionLocal()
        user = None
        try:
            user = models.User(full_name="Fallback Check", email_or_demo_id="demo-fallback-check")
            db.add(user)
            db.commit()
            db.refresh(user)
            profile = models.Profile(
                user_id=user.id,
                age=44,
                sex="Female",
                height_cm=165,
                weight_kg=71,
                bmi=calculate_bmi(71, 165),
                high_bp=False,
                high_chol=False,
                smoker=False,
                phys_activity=True,
                fruits=True,
                veggies=True,
                general_health=2,
                stroke_history=False,
                heart_disease_history=False,
                difficulty_walking=False,
                family_history_diabetes=False,
                fasting_glucose_optional=96,
                hba1c_optional=5.4,
            )
            db.add(profile)
            db.add(
                models.HealthLog(
                    user_id=user.id,
                    log_date=date.today(),
                    fasting_glucose=102,
                    post_meal_glucose=138,
                    systolic_bp=122,
                    diastolic_bp=78,
                    activity_minutes=22,
                )
            )
            db.commit()
            direct = predict_monitoring(
                db.query(models.HealthLog)
                .filter(models.HealthLog.user_id == user.id)
                .order_by(models.HealthLog.log_date.asc())
                .all()
            )
            self.assertFalse(direct["ok"])
            payload = self.client.get(f"/api/monitoring-assessment/{user.id}/latest").json()
            self.assertEqual(payload["model_version"], "engineered-rules-0.1")
            self.assertIn("message", payload["summary"])
        finally:
            if user is not None:
                db.query(models.HealthLog).filter(models.HealthLog.user_id == user.id).delete()
                db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
                db.query(models.User).filter(models.User.id == user.id).delete()
                db.commit()
            db.close()

    def test_log_creation_uses_simple_payload_without_risk_assessment(self) -> None:
        db = SessionLocal()
        user = None
        try:
            user = models.User(full_name="Simple Log Check", email_or_demo_id="demo-simple-log-check")
            db.add(user)
            db.commit()
            db.refresh(user)
            db.add(
                models.Profile(
                    user_id=user.id,
                    age=55,
                    sex="Female",
                    height_cm=168,
                    weight_kg=86,
                    bmi=calculate_bmi(86, 168),
                    high_bp=True,
                    high_chol=True,
                    smoker=False,
                    phys_activity=True,
                    fruits=True,
                    veggies=True,
                    general_health=3,
                    stroke_history=False,
                    heart_disease_history=False,
                    difficulty_walking=False,
                    family_history_diabetes=True,
                )
            )
            db.commit()

            payload = self.client.post(
                "/api/logs",
                json={"user_id": user.id, "glucose_level": 177, "is_fasting": False},
            ).json()

            self.assertEqual(payload["glucose_level"], 177)
            self.assertFalse(payload["is_fasting"])
            self.assertEqual(payload["log_date"], date.today().isoformat())
            self.assertEqual(payload["post_meal_glucose"], 177)
            risk_count = db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user.id).count()
            self.assertEqual(risk_count, 0)
            monitoring_count = db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).count()
            self.assertGreaterEqual(monitoring_count, 1)
            monitoring = db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).order_by(models.MonitoringAssessment.created_at.desc()).first()
            self.assertEqual(monitoring.summary_json["avg_fasting_glucose"], None)
            self.assertEqual(monitoring.summary_json["avg_post_meal_glucose"], 177)
        finally:
            if user is not None:
                db.query(models.AgentAlert).filter(models.AgentAlert.user_id == user.id).delete()
                db.query(models.Report).filter(models.Report.user_id == user.id).delete()
                db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).delete()
                db.query(models.HealthLog).filter(models.HealthLog.user_id == user.id).delete()
                db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user.id).delete()
                db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
                db.query(models.User).filter(models.User.id == user.id).delete()
                db.commit()
            db.close()

    def test_monitoring_ignores_blood_pressure_values(self) -> None:
        from app.rules.engine import monitoring_state

        logs = [
            SimpleNamespace(log_date=date(2026, 5, index + 1), glucose_level=105, systolic_bp=180, diastolic_bp=110)
            for index in range(4)
        ]
        state = monitoring_state(logs)
        labels = {flag["label"] for flag in state["anomaly_flags"]}
        self.assertNotIn("Blood pressure pattern", labels)

    def test_report_generation_uses_model_backed_language(self) -> None:
        report = self.client.post("/api/reports/doctor?user_id=1").json()
        bodies = [section["body"] for section in report["content"]["sections"]]
        self.assertTrue(any("random-forest-0.2" in body for body in bodies))
        self.assertTrue(any("glucose-trend-random-forest-0.2" in body or "concerning" in body for body in bodies))

    def test_glyco_insight_contains_agent_sections(self) -> None:
        insight = self.client.get("/api/insights/1").json()
        self.assertIn("what_changed", insight)
        self.assertIn("why_it_matters", insight)
        self.assertIn("what_to_do_next", insight)
        self.assertIn("what_to_ask_your_doctor", insight)
        self.assertIn("tool_calls", insight)
        self.assertGreaterEqual(len(insight["what_to_do_next"]), 1)
        self.assertGreaterEqual(len(insight["what_to_ask_your_doctor"]), 1)

    def test_agent_chat_uses_patient_tools_without_llm(self) -> None:
        response = self.client.post("/api/agent/chat", json={"user_id": 1, "message": "Trebam li se brinuti ovaj tjedan?"}).json()
        self.assertIn("answer", response)
        self.assertEqual(response["llm_mode"], "fallback")
        tool_names = {tool["name"] for tool in response["tool_calls"]}
        self.assertTrue({
            "get_glucose_logs",
            "run_trained_risk_model",
            "get_bayesian_risk_state",
            "run_trained_glucose_trend_model",
            "retrieve_guidelines",
            "read_agent_learning_memory",
            "rank_recommendations_with_thompson_sampling",
        }.issubset(tool_names))
        risk_tool = next(tool for tool in response["tool_calls"] if tool["name"] == "run_trained_risk_model")
        trend_tool = next(tool for tool in response["tool_calls"] if tool["name"] == "run_trained_glucose_trend_model")
        bayesian_tool = next(tool for tool in response["tool_calls"] if tool["name"] == "get_bayesian_risk_state")
        self.assertEqual(risk_tool["model_version"], "random-forest-0.2")
        self.assertEqual(trend_tool["model_version"], "glucose-trend-random-forest-0.2")
        self.assertIn("posterior", bayesian_tool["result_summary"])
        self.assertIn("glucose trend model", response["answer"])
        self.assertIn("RF risk model", response["answer"])
        self.assertIn("Bayesian layer", response["answer"])
        self.assertGreaterEqual(len(response["guideline_snippets"]), 1)
        self.assertIn("learning_summary", response)
        self.assertIn("does not diagnose", response["safety_note"])

    def test_agent_feedback_personalizes_next_answer(self) -> None:
        db = SessionLocal()
        user = None
        try:
            user = models.User(full_name="Memory Check", email_or_demo_id="demo-memory-check")
            db.add(user)
            db.commit()
            db.refresh(user)
            profile = models.Profile(
                user_id=user.id,
                age=58,
                sex="Female",
                height_cm=166,
                weight_kg=88,
                bmi=calculate_bmi(88, 166),
                high_bp=True,
                high_chol=True,
                smoker=False,
                phys_activity=True,
                fruits=True,
                veggies=True,
                general_health=3,
                stroke_history=False,
                heart_disease_history=False,
                difficulty_walking=False,
                family_history_diabetes=True,
                fasting_glucose_optional=122,
                hba1c_optional=6.1,
            )
            db.add(profile)
            db.commit()
            self.client.post(
                "/api/agent/feedback",
                json={
                    "user_id": user.id,
                    "message": "This was useful",
                    "helpful": True,
                    "preferred_tone": "concise",
                    "confirmed_action": "Walk after the largest meal.",
                },
            )
            response = self.client.post("/api/agent/chat", json={"user_id": user.id, "message": "Should I be worried this week?"}).json()
            self.assertEqual(response["learning_summary"]["feedback_count"], 1)
            self.assertEqual(response["learning_summary"]["preferred_tone"], "concise")
            self.assertEqual(response["learning_summary"]["preferred_action_type"], "activity")
            self.assertIn("next_best_action", response["learning_summary"])
            self.assertIn("Walk after the largest meal.", response["answer"])
            ranker = next(tool for tool in response["tool_calls"] if tool["name"] == "rank_recommendations_with_thompson_sampling")
            self.assertIn("ranked_recommendations", ranker["details"])
        finally:
            if user is not None:
                db.query(models.AgentFeedback).filter(models.AgentFeedback.user_id == user.id).delete()
                db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
                db.query(models.BayesianRiskState).filter(models.BayesianRiskState.user_id == user.id).delete()
                db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user.id).delete()
                db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).delete()
                db.query(models.HealthLog).filter(models.HealthLog.user_id == user.id).delete()
                db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
                db.query(models.User).filter(models.User.id == user.id).delete()
                db.commit()
            db.close()

    def test_agent_chat_urgent_symptom_safety(self) -> None:
        response = self.client.post("/api/agent/chat", json={"user_id": 1, "message": "I have chest pain and shortness of breath"}).json()
        self.assertIn("urgent medical attention", response["answer"])
        self.assertGreaterEqual(len(response["tool_calls"]), 1)

    def test_proactive_alert_endpoint_returns_alert_for_seeded_user(self) -> None:
        result = self.client.post("/api/agent/proactive-check/1").json()
        self.assertIn(result["reason"] if not result["created"] else result["title"], {"existing", "Concerning trend detected", "Watch pattern detected"})
        alerts = self.client.get("/api/alerts/1").json()
        self.assertGreaterEqual(len(alerts), 1)

    def test_care_plan_uses_current_patient_data(self) -> None:
        plan = self.client.post("/api/care-plan/diet?user_id=1").json()
        self.assertIn(plan["source"], {"data-fallback", "gemini-personalized"})
        self.assertIn("signals", plan)
        self.assertEqual(plan["signals"]["risk_model_version"], "random-forest-0.2")
        self.assertEqual(plan["signals"]["trend_model_version"], "glucose-trend-random-forest-0.2")
        self.assertIsNotNone(plan["signals"]["latest_glucose"])
        combined = " ".join(plan["weekly_recommendations"] + [plan["direction"]])
        self.assertTrue(str(int(plan["signals"]["latest_glucose"])) in combined or plan["signals"]["trend_label"] in combined)

    def test_care_plan_reflects_not_fasting_latest_reading(self) -> None:
        db = SessionLocal()
        user = None
        try:
            user = models.User(full_name="Care Plan Meal", email_or_demo_id="care-plan-meal")
            db.add(user)
            db.commit()
            db.refresh(user)
            db.add(models.Profile(
                user_id=user.id,
                age=52,
                sex="Female",
                height_cm=166,
                weight_kg=82,
                bmi=calculate_bmi(82, 166),
                high_bp=True,
                high_chol=False,
                smoker=False,
                phys_activity=True,
                fruits=True,
                veggies=True,
                general_health=3,
                stroke_history=False,
                heart_disease_history=False,
                difficulty_walking=False,
                family_history_diabetes=True,
            ))
            db.add(models.HealthLog(user_id=user.id, log_date=date.today(), is_fasting=False, fasting_glucose=190, post_meal_glucose=190))
            db.commit()
            plan = self.client.post(f"/api/care-plan/diet?user_id={user.id}").json()
            self.assertFalse(plan["signals"]["latest_is_fasting"])
            self.assertEqual(plan["signals"]["avg_post_meal"], 190)
            self.assertIn("not-fasting", plan["direction"])
        finally:
            if user is not None:
                db.query(models.AgentAlert).filter(models.AgentAlert.user_id == user.id).delete()
                db.query(models.Report).filter(models.Report.user_id == user.id).delete()
                db.query(models.MonitoringAssessment).filter(models.MonitoringAssessment.user_id == user.id).delete()
                db.query(models.RiskAssessment).filter(models.RiskAssessment.user_id == user.id).delete()
                db.query(models.BayesianRiskState).filter(models.BayesianRiskState.user_id == user.id).delete()
                db.query(models.BanditArmState).filter(models.BanditArmState.user_id == user.id).delete()
                db.query(models.HealthLog).filter(models.HealthLog.user_id == user.id).delete()
                db.query(models.Profile).filter(models.Profile.user_id == user.id).delete()
                db.query(models.User).filter(models.User.id == user.id).delete()
                db.commit()
            db.close()


if __name__ == "__main__":
    unittest.main()
