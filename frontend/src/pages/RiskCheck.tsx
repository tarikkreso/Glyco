import { useMutation } from "@tanstack/react-query";
import { Activity, Beaker, UserRound } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { api, RiskAssessment } from "../api/client";
import { useAuth } from "../auth/auth";
import { Badge, Card, EmptyState, ErrorState, FactorList, LoadingState, PageHeader } from "../components/ui";
import { useI18n } from "../i18n";

type FormValues = {
  age: number; sex: string; weight_kg: number; height_cm: number; high_bp: boolean; high_chol: boolean; smoker: boolean; phys_activity: boolean; family_history_diabetes: boolean; general_health: number;
};

export type RiskCheckVariant = "app" | "demo" | "onboarding";

type StepKey = "profile" | "clinical" | "lifestyle" | "results";

function Stepper({
  steps,
  active,
  bs,
}: {
  steps: Array<{ key: StepKey; label: string }>;
  active: StepKey;
  bs: boolean;
}) {
  return (
    <div className="stepper" aria-label={bs ? "Koraci procjene rizika" : "Risk check steps"}>
      {steps.map((s, idx) => {
        const isActive = s.key === active;
        const isDone = steps.findIndex((x) => x.key === active) > idx;
        return (
          <div
            key={s.key}
            className={`stepper-step${isActive ? " active" : ""}${isDone ? " done" : ""}`}
            aria-current={isActive ? "step" : undefined}
          >
            <span className="stepper-index">{idx + 1}</span>
            <span className="stepper-label">{s.label}</span>
          </div>
        );
      })}
    </div>
  );
}

export function RiskCheckFlow({
  variant,
  onComplete,
  userId = 1,
}: {
  variant: RiskCheckVariant;
  onComplete?: () => void;
  userId?: number;
}) {
  const { language } = useI18n();
  const bs = language === "bs";
  const steps = useMemo(
    () => [
      { key: "profile" as const, label: bs ? "Profil" : "Profile" },
      { key: "clinical" as const, label: bs ? "Klinički" : "Clinical" },
      { key: "lifestyle" as const, label: bs ? "Životne navike" : "Lifestyle" },
      { key: "results" as const, label: bs ? "Rezultati" : "Results" },
    ],
    [bs]
  );

  const [step, setStep] = useState<StepKey>("profile");

  const { register, handleSubmit } = useForm<FormValues>({
    defaultValues: {
      age: 58,
      sex: "Female",
      weight_kg: 88,
      height_cm: 166,
      high_bp: true,
      high_chol: true,
      smoker: false,
      phys_activity: true,
      family_history_diabetes: true,
      general_health: 3,
    },
    shouldUnregister: false,
  });

  const mutation = useMutation<RiskAssessment, Error, FormValues>({
    mutationFn: (values) =>
      api.assessRisk({
        user_id: userId,
        fruits: true,
        veggies: true,
        stroke_history: false,
        heart_disease_history: false,
        difficulty_walking: false,
        ...values,
      }),
    onSuccess: () => setStep("results"),
  });
  const result = mutation.data;

  const stepIndex = steps.findIndex((s) => s.key === step);
  const canGoBack = stepIndex > 0;
  const canGoNext = stepIndex < steps.length - 2; // before Lifestyle
  const nextStep = canGoNext ? steps[stepIndex + 1].key : null;
  const prevStep = canGoBack ? steps[stepIndex - 1].key : null;
  const progressPct = Math.round(((stepIndex + 1) / steps.length) * 100);

  return (
    <div className="wizard">
      <div className="wizard-header">
        <div className="wizard-header-row">
          <div>
            <strong className="wizard-heading">{steps[stepIndex]?.label}</strong>
            <span className="wizard-meta">{bs ? `Korak ${stepIndex + 1} od ${steps.length}` : `Step ${stepIndex + 1} of ${steps.length}`}</span>
          </div>
          <div className="wizard-progress" role="progressbar" aria-valuenow={progressPct} aria-valuemin={0} aria-valuemax={100} aria-label={bs ? "Napredak" : "Progress"}>
            <i style={{ width: `${progressPct}%` }} />
          </div>
        </div>
        <Stepper steps={steps} active={step} bs={bs} />
      </div>

      <form
        className="wizard-stack"
        onSubmit={handleSubmit((values) => mutation.mutate(values))}
      >
        {step === "profile" && (
          <Card title={bs ? "Profil" : "Profile"} action={<UserRound size={18} />}>
            <label>{bs ? "Godine pacijenta" : "Patient Age"}<input type="number" {...register("age", { valueAsNumber: true })} /></label>
            <label>{bs ? "Biološki spol" : "Biological Sex"}<select {...register("sex")}><option>{bs ? "Ženski" : "Female"}</option><option>{bs ? "Muški" : "Male"}</option></select></label>
            <label>{bs ? "Težina (kg)" : "Weight (kg)"}<input type="number" step="0.1" {...register("weight_kg", { valueAsNumber: true })} /></label>
            <label>{bs ? "Visina (cm)" : "Height (cm)"}<input type="number" step="0.1" {...register("height_cm", { valueAsNumber: true })} /></label>
          </Card>
        )}

        {step === "clinical" && (
          <Card title={bs ? "Klinički markeri" : "Clinical Markers"} action={<Beaker size={18} />}>
            <label className="check"><input type="checkbox" {...register("high_bp")} /> {bs ? "Hipertenzija" : "Hypertension"}</label>
            <label className="check"><input type="checkbox" {...register("high_chol")} /> {bs ? "Visok holesterol" : "High cholesterol"}</label>
            <label className="check"><input type="checkbox" {...register("family_history_diabetes")} /> {bs ? "Porodična historija dijabetesa" : "Family diabetes history"}</label>
            <label>{bs ? "Opšte zdravlje" : "General Health"}<select {...register("general_health", { valueAsNumber: true })}><option value={1}>{bs ? "Odlično" : "Excellent"}</option><option value={2}>{bs ? "Vrlo dobro" : "Very good"}</option><option value={3}>{bs ? "Dobro" : "Good"}</option><option value={4}>{bs ? "Zadovoljavajuće" : "Fair"}</option><option value={5}>{bs ? "Loše" : "Poor"}</option></select></label>
          </Card>
        )}

        {step === "lifestyle" && (
          <Card title={bs ? "Životne navike" : "Lifestyle"} action={<Activity size={18} />}>
            <label className="check"><input type="checkbox" {...register("smoker")} /> {bs ? "Trenutni pušač" : "Current smoker"}</label>
            <label className="check"><input type="checkbox" {...register("phys_activity")} /> {bs ? "Fizički aktivan" : "Physically active"}</label>
            <div className="wizard-note">
              {bs ? "Ovo će pokrenuti početnu procjenu rizika na osnovu profila koji ste unijeli." : "This will run a baseline risk estimate from the profile you entered."}
            </div>
          </Card>
        )}

        {step !== "results" && (
          <div className="wizard-nav">
            <button
              type="button"
              className="secondary"
              disabled={!canGoBack || mutation.isPending}
              onClick={() => prevStep && setStep(prevStep)}
            >
              {bs ? "Nazad" : "Back"}
            </button>

            {step === "lifestyle" ? (
              <button className="primary" type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? (bs ? "Pokretanje..." : "Running...") : variant === "app" ? (bs ? "Pokreni procjenu" : "Run Assessment") : (bs ? "Pokreni provjeru rizika" : "Run Risk Check")}
              </button>
            ) : (
              <button
                type="button"
                className="primary"
                disabled={!nextStep || mutation.isPending}
                onClick={() => nextStep && setStep(nextStep)}
              >
                {bs ? "Dalje" : "Next"}
              </button>
            )}
          </div>
        )}

        {step === "results" && (
          <>
            <div className="wizard-results">
              <div className="wizard-results-main">
                <Card title={bs ? "Izračunata vjerovatnoća" : "Calculated Probability"}>
                  {mutation.isPending ? (
                    <LoadingState label={bs ? "Procjena se pokreće" : "Running assessment"} />
                  ) : (
                    <>
                      <div className="probability">
                        <strong>{result ? Math.round(result.risk_probability * 100) : 32}<span>%</span></strong>
                        <Badge tone={result?.risk_level === "high" ? "danger" : result?.risk_level === "low" ? "good" : "warning"}>{result?.risk_level ?? (bs ? "Povišen" : "Elevated")} {bs ? "profil rizika" : "risk profile"}</Badge>
                      </div>
                      <div className="risk-bar"><i style={{ width: `${Math.round((result?.risk_probability ?? 0.32) * 100)}%` }} /></div>
                      <p>{result?.explanation ?? (bs ? "Poslani profil će biti procijenjen na obrasce koji podržavaju procjenu rizika nakon pokretanja analize." : "The submitted profile will be assessed for risk-support patterns after running the assessment.")}</p>
                      {result?.model_version && <div className="chip-row"><Badge>{result.model_version}</Badge><Badge>{result.confidence_label}</Badge></div>}
                    </>
                  )}
                  {mutation.isError && <ErrorState title={bs ? "Procjena nije dostupna" : "Assessment unavailable"} body={mutation.error.message || (bs ? "API nije vratio ispravnu procjenu rizika." : "The API did not return a valid risk assessment.")} />}
                </Card>

                <Card title={bs ? "Glavni faktori" : "Primary Contributing Factors"}>
                  {result ? <FactorList items={result.top_factors} /> : <EmptyState title={bs ? "Pokrenite procjenu" : "Run the assessment"} body={bs ? "Rangiranje faktora i interpretacija pojavit će se ovdje nakon slanja." : "The factor ranking and interpretation will appear here after submission."} />}
                </Card>
              </div>

              <div className="wizard-results-side">
                <Card title={bs ? "Povezani zdravstveni indikatori" : "Related Health Indicators"}>
                  {result?.related_flags.length ? <div className="alert-list">{result.related_flags.map((flag) => <div key={flag.label} className={flag.level}><strong>{flag.label}</strong><span>{flag.detail}</span></div>)}</div> : <EmptyState title={bs ? "Još nema povezanih oznaka" : "No related flags yet"} body={bs ? "Povezani zdravstveni indikatori će se pojaviti ovdje kada ih profil pokrene." : "Related health indicators will appear here when the profile triggers them."} />}
                </Card>

                {variant === "app" && (
                  <Card title={bs ? "Prijedlog kliničkog protokola" : "Clinical Protocol Suggestion"}>
                    <p>{result?.next_actions[0] ?? (bs ? "Uspostavite dosljedno praćenje životnih navika i razmotrite pregled kliničara ako povišeni indikatori potraju." : "Initiate consistent lifestyle tracking and consider clinician review if elevated indicators persist.")}</p>
                    <button className="secondary">{bs ? "Dodaj u ishranu" : "Add to Nutrition"}</button>
                  </Card>
                )}

                {variant === "onboarding" && (
                  <Card title={bs ? "Nastavi" : "Continue"}>
                    <p>{bs ? "Sada možete početi s unosom zapisa i dobijati uvide." : "Now you can start tracking logs and receiving insights."}</p>
                    <button className="primary" type="button" disabled={!result} onClick={onComplete}>
                      {bs ? "Nastavi u aplikaciju" : "Continue to app"}
                    </button>
                  </Card>
                )}

                {variant === "demo" && result && (
                  <Card title={bs ? "Želite više od snimka stanja?" : "Want more than a snapshot?"}>
                    <p>{bs ? "Kreirajte račun da sačuvate početno stanje, pratite promjene kroz vrijeme i otključate uvide o praćenju i izvještaje." : "Create an account to save your baseline, track changes over time, and unlock monitoring insights and reports."}</p>
                    <div className="cta-row">
                      <Link className="primary button-link" to="/register">{bs ? "Kreiraj račun" : "Create account"}</Link>
                      <Link className="secondary button-link" to="/login">{bs ? "Prijava" : "Sign in"}</Link>
                    </div>
                  </Card>
                )}
              </div>
            </div>

            <div className="wizard-nav">
              <button type="button" className="secondary" onClick={() => setStep("lifestyle")}>
                {bs ? "Uredi unos" : "Edit inputs"}
              </button>
              <button type="button" className="primary" onClick={() => setStep("profile")}>
                {bs ? "Kreni ispočetka" : "Start over"}
              </button>
            </div>
          </>
        )}
      </form>
    </div>
  );
}

export function RiskCheck() {
  const auth = useAuth();
  const { language } = useI18n();
  const bs = language === "bs";

  return (
    <div className="page narrow">
      <PageHeader title={bs ? "Procjena rizika pacijenta" : "Patient Risk Assessment"} subtitle={bs ? "Popunite kliničku matricu ispod da izračunate trenutni profil rizika za dijabetes tipa 2." : "Complete the clinical matrix below to calculate the current Type 2 diabetes risk profile."} />
      <RiskCheckFlow variant="app" userId={auth.session?.userId ?? 1} />
    </div>
  );
}
