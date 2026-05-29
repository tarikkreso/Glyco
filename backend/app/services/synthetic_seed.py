from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from random import Random

from sqlalchemy.orm import Session

from app.db import models
from app.rules.engine import calculate_bmi


@dataclass(frozen=True)
class SyntheticSeedConfig:
    num_users: int = 50
    days: int = 60
    logs_per_day: int = 4
    seed: int = 1337


@dataclass(frozen=True)
class DemoUserSpec:
    demo_id: str
    full_name: str
    fixed_id: int | None = None
    band: str = "low"
    days: int = 30
    logs_per_day: int = 4


_FIRST_NAMES = [
    "Amina",
    "Noah",
    "Lea",
    "Ivan",
    "Maja",
    "Marko",
    "Ema",
    "Nina",
    "Luka",
    "Sara",
    "Filip",
    "Hana",
    "Petra",
    "David",
    "Elena",
    "Milan",
    "Lejla",
    "Sarah",
    "Amir",
    "Jasmin",
    "Tina",
    "Ana",
    "Matej",
    "Niko",
    "Iva",
    "Viktor",
]

_LAST_NAMES = [
    "Kovac",
    "Hadzic",
    "Moric",
    "Ivic",
    "Petrovic",
    "Novak",
    "Knezevic",
    "Boric",
    "Horvat",
    "Jukic",
    "Babic",
    "Kralj",
    "Vukovic",
    "Popovic",
    "Savic",
    "Jovanovic",
    "Markovic",
]


def _demo_hours(logs_per_day: int) -> list[int]:
    if logs_per_day <= 1:
        return [8]
    if logs_per_day == 2:
        return [7, 19]
    if logs_per_day == 3:
        return [7, 13, 20]
    if logs_per_day == 4:
        return [7, 12, 18, 22]
    if logs_per_day == 5:
        return [6, 10, 14, 18, 22]
    # Spread throughout the day; cap to 8 slots.
    base = [6, 9, 12, 15, 18, 21, 23, 2]
    return base[: min(8, logs_per_day)]


def _pick_name(rng: Random) -> str:
    return f"{rng.choice(_FIRST_NAMES)} {rng.choice(_LAST_NAMES)}"


def _risk_band(index: int) -> str:
    if index % 5 == 0:
        return "high"
    if index % 5 == 1:
        return "elevated"
    return "low"


def _profile_for_band(rng: Random, band: str) -> dict:
    if band == "high":
        age = rng.randint(55, 76)
        weight_kg = rng.uniform(88, 125)
        height_cm = rng.uniform(160, 178)
        high_bp = True
        high_chol = True
        smoker = rng.random() < 0.35
        phys_activity = rng.random() < 0.35
        fruits = rng.random() < 0.35
        veggies = rng.random() < 0.45
        general_health = rng.randint(3, 5)
        family_history_diabetes = True
        fasting_glucose_optional = rng.uniform(120, 170)
        hba1c_optional = rng.uniform(6.3, 9.0)
    elif band == "elevated":
        age = rng.randint(40, 64)
        weight_kg = rng.uniform(74, 110)
        height_cm = rng.uniform(158, 185)
        high_bp = rng.random() < 0.5
        high_chol = rng.random() < 0.5
        smoker = rng.random() < 0.2
        phys_activity = rng.random() < 0.6
        fruits = rng.random() < 0.6
        veggies = rng.random() < 0.7
        general_health = rng.randint(2, 4)
        family_history_diabetes = rng.random() < 0.6
        fasting_glucose_optional = rng.uniform(98, 140)
        hba1c_optional = rng.uniform(5.6, 7.4)
    else:
        age = rng.randint(22, 48)
        weight_kg = rng.uniform(54, 85)
        height_cm = rng.uniform(158, 190)
        high_bp = False
        high_chol = False
        smoker = rng.random() < 0.08
        phys_activity = rng.random() < 0.8
        fruits = rng.random() < 0.8
        veggies = rng.random() < 0.85
        general_health = rng.randint(1, 3)
        family_history_diabetes = rng.random() < 0.25
        fasting_glucose_optional = rng.uniform(78, 102)
        hba1c_optional = rng.uniform(4.9, 5.6)

    sex = "Female" if rng.random() < 0.55 else "Male"
    bmi = calculate_bmi(weight_kg, height_cm)

    return dict(
        age=age,
        sex=sex,
        height_cm=round(height_cm, 1),
        weight_kg=round(weight_kg, 1),
        bmi=bmi,
        high_bp=high_bp,
        high_chol=high_chol,
        smoker=smoker,
        phys_activity=phys_activity,
        fruits=fruits,
        veggies=veggies,
        general_health=general_health,
        stroke_history=rng.random() < (0.1 if band == "high" else 0.02),
        heart_disease_history=rng.random() < (0.12 if band == "high" else 0.03),
        difficulty_walking=rng.random() < (0.22 if band == "high" else 0.05),
        family_history_diabetes=family_history_diabetes,
        fasting_glucose_optional=round(float(fasting_glucose_optional), 1),
        hba1c_optional=round(float(hba1c_optional), 2),
        forecast_personalization_enabled=True,
    )


def _glucose_pattern_mmol(band: str) -> dict[int, float]:
    if band == "high":
        return {
            6: 8.5,
            7: 8.8,
            9: 9.2,
            12: 8.6,
            14: 10.2,
            18: 8.9,
            20: 10.6,
            22: 9.4,
        }
    if band == "elevated":
        return {
            6: 6.7,
            7: 6.9,
            9: 7.2,
            12: 6.8,
            14: 8.2,
            18: 6.9,
            20: 8.4,
            22: 7.2,
        }
    return {
        6: 5.2,
        7: 5.3,
        9: 5.6,
        12: 5.4,
        14: 6.2,
        18: 5.3,
        20: 6.4,
        22: 5.7,
    }


def _mmol_to_mgdl(value: float) -> float:
    return round(float(value) * 18.015, 1)


def seed_synthetic_dataset(db: Session, config: SyntheticSeedConfig) -> dict[str, int]:
    """Seed many realistic users plus recent logs.

    This is intentionally optional (for dev/demo) because it can create a lot
    of rows. It is idempotent for the synthetic users it manages.
    """

    rng = Random(config.seed)
    now = datetime.utcnow().replace(microsecond=0)
    start = (now - timedelta(days=int(config.days))).replace(hour=0, minute=0, second=0)

    created_users = 0
    created_profiles = 0
    created_logs = 0

    hours = _demo_hours(int(config.logs_per_day))

    for index in range(int(config.num_users)):
        band = _risk_band(index)
        demo_id = f"seed-user-{index + 1:04d}"

        user = db.query(models.User).filter(models.User.email_or_demo_id == demo_id).first()
        if not user:
            user = models.User(full_name=_pick_name(rng), email_or_demo_id=demo_id)
            db.add(user)
            db.flush()
            created_users += 1

        profile = (
            db.query(models.Profile)
            .filter(models.Profile.user_id == user.id)
            .order_by(models.Profile.created_at.desc())
            .first()
        )
        if not profile:
            db.add(models.Profile(user_id=user.id, **_profile_for_band(rng, band)))
            created_profiles += 1
        else:
            # Keep existing profiles stable; synthetic data focuses on logs.
            pass

        existing = (
            db.query(models.HealthLog.created_at)
            .filter(models.HealthLog.user_id == user.id, models.HealthLog.created_at >= start)
            .all()
        )
        existing_times = {row[0].replace(microsecond=0) for row in existing if row[0] is not None}
        pattern = _glucose_pattern_mmol(band)

        for day_offset in range(int(config.days)):
            day = (start + timedelta(days=day_offset)).date()
            for hour in hours:
                timestamp = datetime.combine(day, datetime.min.time()).replace(hour=int(hour))
                if timestamp > now:
                    continue
                if timestamp in existing_times:
                    continue

                baseline = pattern.get(int(hour), pattern[min(pattern.keys())])
                # Slight day-to-day drift and noise.
                drift = (rng.random() - 0.5) * (0.6 if band == "high" else 0.4)
                noise = rng.gauss(0.0, 0.25 if band == "high" else 0.18)
                mmol = max(3.0, baseline + drift + noise)

                is_fasting = int(hour) <= 8
                mgdl = _mmol_to_mgdl(mmol)

                db.add(
                    models.HealthLog(
                        user_id=user.id,
                        log_date=day,
                        is_fasting=is_fasting,
                        fasting_glucose=mgdl,
                        post_meal_glucose=None if is_fasting else mgdl,
                        weight_kg=profile.weight_kg if profile else None,
                        systolic_bp=120 + (5 if band == "high" else 0) + rng.randint(-4, 8),
                        diastolic_bp=78 + (4 if band == "high" else 0) + rng.randint(-3, 6),
                        activity_minutes=(10 if band == "high" else 22) + rng.randint(0, 25),
                        notes="Synthetic seed dataset v1",
                        created_at=timestamp,
                    )
                )
                created_logs += 1

    db.commit()
    return {
        "users": created_users,
        "profiles": created_profiles,
        "health_logs": created_logs,
    }


def seed_demo_users(db: Session, specs: list[DemoUserSpec], seed: int = 2026) -> dict[str, int]:
    """Seed a curated set of demo users with stable demo IDs and recent logs."""

    rng = Random(int(seed))
    now = datetime.utcnow().replace(microsecond=0)

    created_users = 0
    created_profiles = 0
    created_logs = 0

    for index, spec in enumerate(specs):
        user = db.query(models.User).filter(models.User.email_or_demo_id == spec.demo_id).first()
        if not user:
            fixed_id = int(spec.fixed_id) if spec.fixed_id is not None else None
            if fixed_id is not None and db.get(models.User, fixed_id) is None:
                user = models.User(id=fixed_id, full_name=spec.full_name, email_or_demo_id=spec.demo_id)
            else:
                user = models.User(full_name=spec.full_name, email_or_demo_id=spec.demo_id)
            db.add(user)
            db.flush()
            created_users += 1
        else:
            user.full_name = spec.full_name

        profile = (
            db.query(models.Profile)
            .filter(models.Profile.user_id == user.id)
            .order_by(models.Profile.created_at.desc())
            .first()
        )
        if not profile:
            user_rng = Random(rng.randint(1, 1_000_000) + index)
            profile_payload = _profile_for_band(user_rng, spec.band)
            db.add(models.Profile(user_id=user.id, **profile_payload))
            created_profiles += 1
        else:
            # Keep manual edits; demo seeds focus on time-series logs.
            pass

        days = max(7, int(spec.days))
        logs_per_day = max(2, int(spec.logs_per_day))
        hours = _demo_hours(logs_per_day)
        start = (now - timedelta(days=days)).replace(hour=0, minute=0, second=0)

        existing = (
            db.query(models.HealthLog.created_at)
            .filter(models.HealthLog.user_id == user.id, models.HealthLog.created_at >= start)
            .all()
        )
        existing_times = {row[0].replace(microsecond=0) for row in existing if row[0] is not None}

        user_rng = Random(int(seed) + (spec.fixed_id or 0) + index * 17)
        pattern = _glucose_pattern_mmol(spec.band)
        for day_offset in range(days):
            day = (start + timedelta(days=day_offset)).date()
            for hour in hours:
                timestamp = datetime.combine(day, datetime.min.time()).replace(hour=int(hour))
                if timestamp > now:
                    continue
                if timestamp in existing_times:
                    continue

                baseline = pattern.get(int(hour), pattern[min(pattern.keys())])
                # Mild weekly rhythm.
                weekday = timestamp.weekday()
                weekend_bump = 0.25 if weekday >= 5 else 0.0
                noise = user_rng.gauss(0.0, 0.22 if spec.band == "high" else 0.16)
                mmol = max(3.0, baseline + weekend_bump + noise)
                mgdl = _mmol_to_mgdl(mmol)
                is_fasting = int(hour) <= 8

                db.add(
                    models.HealthLog(
                        user_id=user.id,
                        log_date=day,
                        is_fasting=is_fasting,
                        fasting_glucose=mgdl,
                        post_meal_glucose=None if is_fasting else mgdl,
                        notes="Demo seed dataset v2",
                        created_at=timestamp,
                    )
                )
                created_logs += 1

    db.commit()
    return {
        "users": created_users,
        "profiles": created_profiles,
        "health_logs": created_logs,
    }
