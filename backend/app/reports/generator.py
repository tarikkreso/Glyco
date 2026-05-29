from statistics import mean


def _fmt(value, unit: str = "", language: str = "en") -> str:
    if value is None:
        return "n/a" if language != "bs" else "n/d"
    if isinstance(value, float):
        value = round(value, 1)
    return f"{value}{unit}"


def _risk_label(value: str | None, language: str) -> str:
    if language != "bs":
        return value or "unknown"
    return {"high": "visok", "medium": "srednji", "low": "nizak", "unknown": "nepoznat"}.get(value or "unknown", value or "nepoznat")


def _trend_label(value: str | None, language: str) -> str:
    if language != "bs":
        return value or "unknown"
    return {
        "stable": "stabilan",
        "watch": "za pracenje",
        "concerning": "zabrinjavajuci",
        "unknown": "nepoznat",
    }.get(value or "unknown", value or "nepoznat")


def _risk_text(risk, language: str) -> str:
    if not risk:
        return "No recent risk assessment" if language != "bs" else "Nema nedavne procjene rizika"
    if language == "bs":
        return f"{_risk_label(risk.risk_level, language)} rizik na {int(risk.risk_probability * 100)}% koristeci {risk.model_version}"
    return f"{risk.risk_level} risk at {int(risk.risk_probability * 100)}% using {risk.model_version}"


def _monitor_text(monitoring, language: str) -> str:
    if not monitoring:
        return "No monitoring assessment" if language != "bs" else "Nema procjene pracenja"
    if language == "bs":
        return f"{_trend_label(monitoring.trend_label, language)} koristeci {monitoring.model_version}"
    return f"{monitoring.trend_label} using {monitoring.model_version}"


def build_report(report_type: str, user, risk, monitoring, logs, language: str = "en") -> dict:
    language = "bs" if language == "bs" else "en"
    latest_log = logs[-1] if logs else None
    name = user.full_name if user else ("Demo patient" if language != "bs" else "Demo pacijent")
    fasting_values = [log.glucose_level for log in logs if log.glucose_level is not None and getattr(log, "is_fasting", True)]
    post_meal_values = [log.glucose_level for log in logs if log.glucose_level is not None and not getattr(log, "is_fasting", True)]
    activity_values = [log.activity_minutes for log in logs if log.activity_minutes is not None]
    avg_fasting = round(mean(fasting_values), 1) if fasting_values else None
    avg_post_meal = round(mean(post_meal_values), 1) if post_meal_values else None
    avg_activity = round(mean(activity_values), 1) if activity_values else None
    fasting_min = min(fasting_values) if fasting_values else None
    fasting_max = max(fasting_values) if fasting_values else None
    delta = None
    if len(fasting_values) >= 2:
        delta = round(fasting_values[-1] - fasting_values[-2], 1)

    risk_text = _risk_text(risk, language)
    monitor_text = _monitor_text(monitoring, language)

    if report_type == "doctor":
        if language == "bs":
            sections = [
                {"title": "Pregled pacijenta", "body": f"{name} koristi Glyco za podrsku u procjeni rizika od dijabetesa i pracenju glukoze."},
                {"title": "Profil rizika", "body": risk_text},
                {"title": "Trend pracenja", "body": f"Nedavni status trenda: {monitor_text}."},
                {"title": "Sazetak glukoze", "body": f"Prosjecna glukoza nataste: {_fmt(avg_fasting, ' mg/dL', language)}. Prosjecna glukoza nakon obroka: {_fmt(avg_post_meal, ' mg/dL', language)}. Raspon nataste: {_fmt(fasting_min, ' mg/dL', language)} do {_fmt(fasting_max, ' mg/dL', language)}."},
                {"title": "Nedavni vitalni podaci", "body": f"Zadnji pritisak: {_fmt(getattr(latest_log, 'systolic_bp', None), ' /', language)} {_fmt(getattr(latest_log, 'diastolic_bp', None), ' mmHg', language)}. Prosjecna aktivnost: {_fmt(avg_activity, ' min/dan', language)}."},
            ]
        else:
            sections = [
                {"title": "Patient Overview", "body": f"{name} is using Glyco for diabetes risk screening and monitoring support."},
                {"title": "Risk Profile", "body": risk_text},
                {"title": "Monitoring Trend", "body": f"Recent trend status: {monitor_text}."},
                {"title": "Glucose Summary", "body": f"Average fasting glucose: {_fmt(avg_fasting, ' mg/dL')}. Average not-fasting glucose: {_fmt(avg_post_meal, ' mg/dL')}. Fasting range: {_fmt(fasting_min, ' mg/dL')} to {_fmt(fasting_max, ' mg/dL')}."},
                {"title": "Recent Vitals", "body": f"Latest BP: {_fmt(getattr(latest_log, 'systolic_bp', None), ' /')} {_fmt(getattr(latest_log, 'diastolic_bp', None), ' mmHg')}. Avg activity: {_fmt(avg_activity, ' min/day')}."},
            ]
        if risk:
            sections.append({"title": "Tumacenje rizika" if language == "bs" else "Risk Interpretation", "body": risk.explanation if language != "bs" else risk_text})
        if monitoring and monitoring.summary_json.get("message"):
            sections.append({"title": "Tumacenje pracenja" if language == "bs" else "Monitoring Interpretation", "body": monitoring.summary_json["message"] if language != "bs" else f"Nedavni status trenda: {monitor_text}."})
        sections.append({
            "title": "Tacke za razgovor s doktorom" if language == "bs" else "Clinical Discussion Points",
            "body": "Pregledati faktore rizika, pridrzavanje terapije, kontrolu pritiska i ciljeve za varijabilnost glukoze." if language == "bs" else "Review risk drivers, medication adherence, BP control, and targets for glucose variability.",
        })
        title = "Sažetak za doktora" if language == "bs" else "Doctor Summary"
        disclaimer = "Samo podrska klinickoj odluci. Nije dijagnoza." if language == "bs" else "Clinical decision support only. Not a diagnosis."
    elif report_type == "family":
        if language == "bs":
            sections = [
                {"title": "Pregled", "body": f"{name} prati zdravstvene obrasce kako bi smanjio/la rizik od dijabetesa."},
                {"title": "Kako stvari izgledaju", "body": f"Rizik je trenutno {_risk_label(risk.risk_level if risk else None, language)}, a trend pracenja je {_trend_label(monitoring.trend_label if monitoring else None, language)}."},
                {"title": "Nedavna ocitanja", "body": f"Prosjecna glukoza nataste: {_fmt(avg_fasting, ' mg/dL', language)}. Prosjecna glukoza nakon obroka: {_fmt(avg_post_meal, ' mg/dL', language)}. Zadnje ocitanje: {_fmt(getattr(latest_log, 'glucose_level', None), ' mg/dL', language)}."},
                {"title": "Kako porodica moze pomoci", "body": "Ponudite podsjetnike za unos ocitanja, planiranje uravnotezenih obroka i kratke setnje nakon obroka."},
                {"title": "Sljedeca provjera", "body": "Ako ocitanja ostanu povisena nekoliko dana, razmislite o kontaktiranju klinicara."},
            ]
        else:
            sections = [
                {"title": "Overview", "body": f"{name} is tracking health patterns to reduce diabetes risk."},
                {"title": "How Things Look", "body": f"Risk is currently {risk.risk_level if risk else 'unknown'} and the monitoring trend is {monitoring.trend_label if monitoring else 'unknown'}."},
                {"title": "Recent Readings", "body": f"Average fasting glucose: {_fmt(avg_fasting, ' mg/dL')}. Average not-fasting glucose: {_fmt(avg_post_meal, ' mg/dL')}. Latest reading: {_fmt(getattr(latest_log, 'glucose_level', None), ' mg/dL')}."},
                {"title": "How Family Can Help", "body": "Offer reminders to log readings, plan balanced meals, and take short walks after meals."},
                {"title": "Next Check-In", "body": "If readings stay elevated for several days, consider contacting a clinician."},
            ]
        title = "Porodicni sazetak" if language == "bs" else "Family Update"
        disclaimer = "Podijeljeno radi informisanja porodice. Nije dijagnoza." if language == "bs" else "Shared to keep family informed. Not a diagnosis."
    else:
        change_text = ("Jos nema promjene." if language == "bs" else "No change yet.") if delta is None else f"Fasting glucose changed by {abs(delta)} mg/dL since the last log."
        if delta is not None:
            if language == "bs":
                direction = "porasla" if delta > 0 else "pala" if delta < 0 else "ostala ista"
                change_text = f"Glukoza nataste je {direction} za {abs(delta)} mg/dL od zadnjeg zapisa."
            else:
                change_text = f"Fasting glucose {'increased' if delta > 0 else 'decreased' if delta < 0 else 'stayed level'} by {abs(delta)} mg/dL since the last log."
        if language == "bs":
            sections = [
                {"title": "Sedmica ukratko", "body": f"Prosjecna glukoza nataste: {_fmt(avg_fasting, ' mg/dL', language)}. {change_text}"},
                {"title": "Aktivnost", "body": f"Prosjecna aktivnost: {_fmt(avg_activity, ' min/dan', language)}."},
                {"title": "Fokus za narednu sedmicu", "body": "Zadrzite dosljedan raspored unosa i povežite obroke s vise ugljikohidrata s laganom aktivnoscu."},
            ]
        else:
            sections = [
                {"title": "Week At A Glance", "body": f"Average fasting glucose: {_fmt(avg_fasting, ' mg/dL')}. {change_text}"},
                {"title": "Activity", "body": f"Average activity: {_fmt(avg_activity, ' min/day')}."},
                {"title": "Focus For Next Week", "body": "Keep a consistent logging schedule and match higher-carb meals with light activity."},
            ]
        title = "Sedmicni pregled" if language == "bs" else "Weekly Reflection"
        disclaimer = "Licni sedmicni sazetak. Nije dijagnoza." if language == "bs" else "Personal reflection summary. Not a diagnosis."

    return {"title": title, "sections": sections, "disclaimer": disclaimer, "language": language}
