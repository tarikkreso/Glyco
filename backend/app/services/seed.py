import os
from datetime import datetime

from app.db.database import SessionLocal
from app.db import models
from app.rules.engine import calculate_bmi
from app.services.synthetic_seed import DemoUserSpec, SyntheticSeedConfig, seed_demo_users, seed_synthetic_dataset


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

        # Seed richer, recent time-series logs for demo accounts.
        # Guarantees multi-day history so monitoring model availability does not
        # depend on time-of-day.
        seed_demo_users(
            db,
            [
                DemoUserSpec(demo_id="demo-monitoring", full_name="Sarah Kovac", band="high", days=45, logs_per_day=4),
                DemoUserSpec(demo_id="demo-high-risk", full_name="Milan Hadzic", band="high", days=30, logs_per_day=4),
                DemoUserSpec(demo_id="demo-low-risk", full_name="Lejla Moric", band="low", days=30, logs_per_day=4),
                # Extra demo users for QA / manual testing.
                DemoUserSpec(demo_id="demo-improving", full_name="Hana Novak", fixed_id=101, band="elevated", days=60, logs_per_day=4),
                DemoUserSpec(demo_id="demo-high-variability", full_name="Marko Jukic", fixed_id=102, band="high", days=45, logs_per_day=5),
                DemoUserSpec(demo_id="demo-hypo-watch", full_name="Ema Horvat", fixed_id=103, band="low", days=45, logs_per_day=4),
                DemoUserSpec(demo_id="demo-night-shift", full_name="Ivan Knezevic", fixed_id=104, band="elevated", days=45, logs_per_day=4),
                DemoUserSpec(demo_id="demo-weekend-spikes", full_name="Petra Babic", fixed_id=105, band="elevated", days=45, logs_per_day=4),
                DemoUserSpec(demo_id="demo-stable", full_name="Luka Kralj", fixed_id=106, band="low", days=60, logs_per_day=3),
            ],
            seed=42,
        )

        sarah = users_by_demo_id["demo-monitoring"]
        share = db.query(models.FamilyShare).filter(models.FamilyShare.share_token == "demo-family-sarah").first()
        if not share:
            db.add(models.FamilyShare(user_id=sarah.id, shared_with_name="Care Circle", relationship="Family", share_token="demo-family-sarah", permissions_json={"read_only": True}))
        db.commit()
    finally:
        db.close()


def seed_synthetic_from_env() -> dict[str, int] | None:
    """Optionally seed a much larger synthetic dataset when explicitly enabled."""

    enabled = os.getenv("GLYCO_SEED_SYNTHETIC", "").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        return None

    def _int_env(name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None or not raw.strip():
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    config = SyntheticSeedConfig(
        num_users=_int_env("GLYCO_SEED_USERS", 50),
        days=_int_env("GLYCO_SEED_DAYS", 60),
        logs_per_day=_int_env("GLYCO_SEED_LOGS_PER_DAY", 4),
        seed=_int_env("GLYCO_SEED_RANDOM", 1337),
    )

    db = SessionLocal()
    try:
        return seed_synthetic_dataset(db, config)
    finally:
        db.close()
