from datetime import date, datetime, timedelta
from random import Random
from app.db.database import SessionLocal
from app.db import models
from app.rules.engine import calculate_bmi


def seed_demo_data() -> None:
    db = SessionLocal()
    try:
        demo_users = [
            ("Sarah Kovac", "demo-monitoring"),
            ("Milan Hadzic", "demo-high-risk"),
            ("Lejla Moric", "demo-low-risk"),
        ]
        users = []
        users_by_demo_id = {}
        for full_name, demo_id in demo_users:
            user = db.query(models.User).filter(models.User.email_or_demo_id == demo_id).first()
            if not user:
                user = models.User(full_name=full_name, email_or_demo_id=demo_id)
                db.add(user)
                db.flush()
            else:
                user.full_name = full_name
            users.append(user)
            users_by_demo_id[demo_id] = user

        seeded_profiles = {
            "demo-monitoring": dict(
                age=58, sex="Female", height_cm=166, weight_kg=96, bmi=calculate_bmi(96, 166),
                high_bp=True, high_chol=True, smoker=False, phys_activity=False,
                fruits=False, veggies=True, general_health=4, stroke_history=False,
                heart_disease_history=False, difficulty_walking=True,
                family_history_diabetes=True, fasting_glucose_optional=126, hba1c_optional=6.1,
            ),
            "demo-high-risk": dict(
                age=67, sex="Male", height_cm=170, weight_kg=108, bmi=calculate_bmi(108, 170),
                high_bp=True, high_chol=True, smoker=True, phys_activity=False,
                fruits=False, veggies=False, general_health=5, stroke_history=True,
                heart_disease_history=True, difficulty_walking=True,
                family_history_diabetes=True, fasting_glucose_optional=145, hba1c_optional=7.2,
            ),
            "demo-low-risk": dict(
                age=29, sex="Female", height_cm=168, weight_kg=60, bmi=calculate_bmi(60, 168),
                high_bp=False, high_chol=False, smoker=False, phys_activity=True,
                fruits=True, veggies=True, general_health=1, stroke_history=False,
                heart_disease_history=False, difficulty_walking=False,
                family_history_diabetes=False, fasting_glucose_optional=88, hba1c_optional=5.1,
            ),
        }
        for user in users:
            profile = db.query(models.Profile).filter(models.Profile.user_id == user.id).order_by(models.Profile.created_at.desc()).first()
            if not profile:
                profile = models.Profile(user_id=user.id, **seeded_profiles[user.email_or_demo_id])
                db.add(profile)
            else:
                for key, value in seeded_profiles[user.email_or_demo_id].items():
                    setattr(profile, key, value)
                profile.updated_at = datetime.utcnow()

        sarah = users_by_demo_id["demo-monitoring"]
        sarah_log_count = db.query(models.HealthLog).filter(models.HealthLog.user_id == sarah.id).count()
        if sarah_log_count < 20:
            rng = Random(42)
            pattern_mmol = {
                6: 7.8,
                8: 8.4,
                10: 7.2,
                12: 7.0,
                14: 9.1,
                16: 7.8,
                18: 7.2,
                20: 9.8,
                22: 8.1,
                0: 7.3,
                2: 6.9,
                4: 7.1,
            }
            raw_start = datetime.utcnow() - timedelta(hours=48)
            start_time = raw_start.replace(hour=(raw_start.hour // 2) * 2, minute=0, second=0, microsecond=0)
            for idx in range(24):
                timestamp = start_time + timedelta(hours=idx * 2)
                baseline = pattern_mmol[timestamp.hour]
                glucose_mmol = max(3.5, baseline + rng.gauss(0.0, 0.3))
                glucose_mgdl = round(glucose_mmol * 18.015, 1)
                is_fasting = timestamp.hour not in {6, 12, 18}
                db.add(models.HealthLog(
                    user_id=sarah.id,
                    log_date=timestamp.date(),
                    is_fasting=is_fasting,
                    fasting_glucose=glucose_mgdl,
                    post_meal_glucose=None if is_fasting else glucose_mgdl,
                    weight_kg=96,
                    systolic_bp=136 + (idx % 4) * 2,
                    diastolic_bp=84 + (idx % 3),
                    activity_minutes=18 + (idx % 5),
                    notes="Seeded 48-hour Type 2 glucose pattern",
                    created_at=timestamp,
                ))
        share = db.query(models.FamilyShare).filter(models.FamilyShare.share_token == "demo-family-sarah").first()
        if not share:
            db.add(models.FamilyShare(user_id=sarah.id, shared_with_name="Care Circle", relationship="Family", share_token="demo-family-sarah", permissions_json={"read_only": True}))
        db.commit()
    finally:
        db.close()
