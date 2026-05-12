from datetime import date, datetime, timedelta
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
        for full_name, demo_id in demo_users:
            user = db.query(models.User).filter(models.User.email_or_demo_id == demo_id).first()
            if not user:
                user = models.User(full_name=full_name, email_or_demo_id=demo_id)
                db.add(user)
                db.flush()
            else:
                user.full_name = full_name
            users.append(user)

        seeded_profiles = {
            1: dict(
                age=58, sex="Female", height_cm=166, weight_kg=96, bmi=calculate_bmi(96, 166),
                high_bp=True, high_chol=True, smoker=False, phys_activity=False,
                fruits=False, veggies=True, general_health=4, stroke_history=False,
                heart_disease_history=False, difficulty_walking=True,
                family_history_diabetes=True, fasting_glucose_optional=126, hba1c_optional=6.1,
            ),
            2: dict(
                age=67, sex="Male", height_cm=170, weight_kg=108, bmi=calculate_bmi(108, 170),
                high_bp=True, high_chol=True, smoker=True, phys_activity=False,
                fruits=False, veggies=False, general_health=5, stroke_history=True,
                heart_disease_history=True, difficulty_walking=True,
                family_history_diabetes=True, fasting_glucose_optional=145, hba1c_optional=7.2,
            ),
            3: dict(
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
                profile = models.Profile(user_id=user.id, **seeded_profiles[user.id])
                db.add(profile)
            else:
                for key, value in seeded_profiles[user.id].items():
                    setattr(profile, key, value)
                profile.updated_at = datetime.utcnow()

        start = date.today() - timedelta(days=13)
        readings = [104, 108, 111, 116, 119, 121, 123, 128, 132, 130, 136, 142, 148, 154]
        db.query(models.HealthLog).filter(models.HealthLog.user_id == 1).delete()
        for idx, glucose in enumerate(readings):
            db.add(models.HealthLog(
                user_id=1, log_date=start + timedelta(days=idx), fasting_glucose=glucose,
                post_meal_glucose=glucose + 36, weight_kg=96 - idx * 0.04,
                systolic_bp=136 + (idx % 4) * 3, diastolic_bp=84 + (idx % 3) * 2,
                activity_minutes=max(8, 25 - idx), notes="Seeded Glyco demo log",
            ))
        share = db.query(models.FamilyShare).filter(models.FamilyShare.share_token == "demo-family-sarah").first()
        if not share:
            db.add(models.FamilyShare(user_id=1, shared_with_name="Care Circle", relationship="Family", share_token="demo-family-sarah", permissions_json={"read_only": True}))
        db.commit()
    finally:
        db.close()
