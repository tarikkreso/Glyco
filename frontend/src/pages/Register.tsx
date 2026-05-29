import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { api } from "../api/client";
import { Card, ErrorState } from "../components/ui";
import { useAuth } from "../auth/auth";
import { useI18n } from "../i18n";

type FormValues = {
  fullName: string;
  email: string;
  password: string;
  age: number;
  sex: string;
  weight_kg: number;
  height_cm: number;
  high_bp: boolean;
  high_chol: boolean;
  smoker: boolean;
  phys_activity: boolean;
  family_history_diabetes: boolean;
  general_health: number;
};

export function Register() {
  const auth = useAuth();
  const { language, setLanguage } = useI18n();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);
  const bs = language === "bs";

  const { register, handleSubmit } = useForm<FormValues>({
    defaultValues: {
      fullName: "",
      email: "",
      password: "",
      age: 55,
      sex: "Female",
      weight_kg: 86,
      height_cm: 168,
      high_bp: false,
      high_chol: false,
      smoker: false,
      phys_activity: true,
      family_history_diabetes: false,
      general_health: 3,
    },
  });

  if (auth.isAuthenticated) return <Navigate to="/overview" replace />;

  return (
    <div className="auth-shell">
      <div className="public-nav">
        <Link to="/risk-check-demo" className="public-brand">
          <span className="seal">G</span>
          <strong>Glyco</strong>
        </Link>
        <div>
          <select className="language-switch" value={language} onChange={(event) => setLanguage(event.target.value as "en" | "bs") }>
            <option value="en">EN</option>
            <option value="bs">BS</option>
          </select>
          <Link className="secondary button-link" to="/risk-check-demo">{bs ? "Provjera rizika" : "Risk check"}</Link>
          <Link className="secondary button-link" to="/login">{bs ? "Prijava" : "Sign in"}</Link>
        </div>
      </div>
      <div className="auth-page">
        <section className="auth-copy">
          <span className="auth-eyebrow">{bs ? "Krenite od početne slike" : "Start with a baseline"}</span>
          <h1>{bs ? "Kreirajte svoj Glyco prostor." : "Create your Glyco workspace."}</h1>
          <p>{bs ? "Registracija odmah čuva vaš početni zdravstveni profil, tako da aplikacija može izračunati rizik prije prvog unosa glukoze." : "Registration now saves your baseline health profile right away, so the app can calculate risk before you start logging glucose."}</p>
        </section>

        <Card title={bs ? "Račun i zdravstveni profil" : "Account and Health Profile"}>
          <form
            className="form-stack profile-form-grid"
            onSubmit={handleSubmit(async (values) => {
              setError(null);
              let user;
              try {
                user = await api.registerUser({ full_name: values.fullName || "Glyco User", email: values.email });
                await api.assessRisk({
                  user_id: user.id,
                  fruits: true,
                  veggies: true,
                  stroke_history: false,
                  heart_disease_history: false,
                  difficulty_walking: false,
                  age: values.age,
                  sex: values.sex,
                  weight_kg: values.weight_kg,
                  height_cm: values.height_cm,
                  high_bp: values.high_bp,
                  high_chol: values.high_chol,
                  smoker: values.smoker,
                  phys_activity: values.phys_activity,
                  family_history_diabetes: values.family_history_diabetes,
                  general_health: values.general_health,
                });
              } catch (error) {
                setError(error instanceof Error ? error.message : "Could not create your account and baseline profile.");
                return;
              }
              const result = auth.register({ ...values, userId: user.id });
              if (!result.ok) {
                setError(result.error);
                return;
              }
              navigate("/overview", { replace: true });
            })}
          >
            <label className="span-2">
              {bs ? "Puno ime" : "Full name"}
              <input type="text" autoComplete="name" {...register("fullName")} />
            </label>
            <label>
              {bs ? "Email" : "Email"}
              <input type="email" autoComplete="email" {...register("email")} />
            </label>
            <label>
              {bs ? "Lozinka" : "Password"}
              <input type="password" autoComplete="new-password" {...register("password")} />
            </label>
            <label>
              {bs ? "Godine" : "Age"}
              <input type="number" {...register("age", { valueAsNumber: true })} />
            </label>
            <label>
              {bs ? "Biološki spol" : "Biological sex"}
              <select {...register("sex")}><option>{bs ? "Ženski" : "Female"}</option><option>{bs ? "Muški" : "Male"}</option></select>
            </label>
            <label>
              {bs ? "Težina (kg)" : "Weight (kg)"}
              <input type="number" step="0.1" {...register("weight_kg", { valueAsNumber: true })} />
            </label>
            <label>
              {bs ? "Visina (cm)" : "Height (cm)"}
              <input type="number" step="0.1" {...register("height_cm", { valueAsNumber: true })} />
            </label>
            <label>
              {bs ? "Opšte zdravlje" : "General health"}
              <select {...register("general_health", { valueAsNumber: true })}>
                <option value={1}>{bs ? "Odlično" : "Excellent"}</option>
                <option value={2}>{bs ? "Vrlo dobro" : "Very good"}</option>
                <option value={3}>{bs ? "Dobro" : "Good"}</option>
                <option value={4}>{bs ? "Zadovoljavajuće" : "Fair"}</option>
                <option value={5}>{bs ? "Loše" : "Poor"}</option>
              </select>
            </label>
            <div className="span-2 check-grid">
              <label className="check"><input type="checkbox" {...register("high_bp")} /> {bs ? "Visok krvni pritisak" : "High blood pressure"}</label>
              <label className="check"><input type="checkbox" {...register("high_chol")} /> {bs ? "Visok holesterol" : "High cholesterol"}</label>
              <label className="check"><input type="checkbox" {...register("family_history_diabetes")} /> {bs ? "Porodična historija dijabetesa" : "Family history of diabetes"}</label>
              <label className="check"><input type="checkbox" {...register("smoker")} /> {bs ? "Trenutni pušač" : "Current smoker"}</label>
              <label className="check"><input type="checkbox" {...register("phys_activity")} /> {bs ? "Fizički aktivan" : "Physically active"}</label>
            </div>
            <button className="primary" type="submit">{bs ? "Registruj se" : "Register"}</button>
            <Link className="secondary button-link" to="/login">{bs ? "Već imate račun" : "Already have an account"}</Link>
          </form>

          {error && <ErrorState title={bs ? "Registracija nije uspjela" : "Could not register"} body={error} />}
        </Card>

        <div className="auth-bottom">
          <Link className="secondary button-link" to="/risk-check-demo">
            {bs ? "Isprobaj provjeru rizika (bez računa)" : "Try Risk Check (no account)"}
          </Link>
        </div>
      </div>
    </div>
  );
}
