import { useMutation } from "@tanstack/react-query";
import { Activity, Beaker, UserRound } from "lucide-react";
import { useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { api, RiskAssessment } from "../api/client";
import { Badge, Card, EmptyState, ErrorState, FactorList, LoadingState, PageHeader } from "../components/ui";

type FormValues = {
  age: number; sex: string; weight_kg: number; height_cm: number; high_bp: boolean; high_chol: boolean; smoker: boolean; phys_activity: boolean; family_history_diabetes: boolean; general_health: number;
};

export type RiskCheckVariant = "app" | "demo" | "onboarding";

type StepKey = "profile" | "clinical" | "lifestyle" | "results";

function Stepper({
  steps,
  active,
}: {
  steps: Array<{ key: StepKey; label: string }>;
  active: StepKey;
}) {
  return (
    <div className="stepper" aria-label="Risk check steps">
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
}: {
  variant: RiskCheckVariant;
  onComplete?: () => void;
}) {
  const steps = useMemo(
    () => [
      { key: "profile" as const, label: "Profile" },
      { key: "clinical" as const, label: "Clinical" },
      { key: "lifestyle" as const, label: "Lifestyle" },
      { key: "results" as const, label: "Results" },
    ],
    []
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
        user_id: 1,
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
            <span className="wizard-meta">Step {stepIndex + 1} of {steps.length}</span>
          </div>
          <div className="wizard-progress" role="progressbar" aria-valuenow={progressPct} aria-valuemin={0} aria-valuemax={100} aria-label="Progress">
            <i style={{ width: `${progressPct}%` }} />
          </div>
        </div>
        <Stepper steps={steps} active={step} />
      </div>

      <form
        className="wizard-stack"
        onSubmit={handleSubmit((values) => mutation.mutate(values))}
      >
        {step === "profile" && (
          <Card title="Profile" action={<UserRound size={18} />}>
            <label>Patient Age<input type="number" {...register("age", { valueAsNumber: true })} /></label>
            <label>Biological Sex<select {...register("sex")}><option>Female</option><option>Male</option></select></label>
            <label>Weight (kg)<input type="number" step="0.1" {...register("weight_kg", { valueAsNumber: true })} /></label>
            <label>Height (cm)<input type="number" step="0.1" {...register("height_cm", { valueAsNumber: true })} /></label>
          </Card>
        )}

        {step === "clinical" && (
          <Card title="Clinical Markers" action={<Beaker size={18} />}>
            <label className="check"><input type="checkbox" {...register("high_bp")} /> Hypertension</label>
            <label className="check"><input type="checkbox" {...register("high_chol")} /> High cholesterol</label>
            <label className="check"><input type="checkbox" {...register("family_history_diabetes")} /> Family diabetes history</label>
            <label>General Health<select {...register("general_health", { valueAsNumber: true })}><option value={1}>Excellent</option><option value={2}>Very good</option><option value={3}>Good</option><option value={4}>Fair</option><option value={5}>Poor</option></select></label>
          </Card>
        )}

        {step === "lifestyle" && (
          <Card title="Lifestyle" action={<Activity size={18} />}>
            <label className="check"><input type="checkbox" {...register("smoker")} /> Current smoker</label>
            <label className="check"><input type="checkbox" {...register("phys_activity")} /> Physically active</label>
            <div className="wizard-note">
              This will run a baseline risk estimate from the profile you entered.
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
              Back
            </button>

            {step === "lifestyle" ? (
              <button className="primary" type="submit" disabled={mutation.isPending}>
                {mutation.isPending ? "Running..." : variant === "app" ? "Run Assessment" : "Run Risk Check"}
              </button>
            ) : (
              <button
                type="button"
                className="primary"
                disabled={!nextStep || mutation.isPending}
                onClick={() => nextStep && setStep(nextStep)}
              >
                Next
              </button>
            )}
          </div>
        )}

        {step === "results" && (
          <>
            <div className="wizard-results">
              <div className="wizard-results-main">
                <Card title="Calculated Probability">
                  {mutation.isPending ? (
                    <LoadingState label="Running assessment" />
                  ) : (
                    <>
                      <div className="probability">
                        <strong>{result ? Math.round(result.risk_probability * 100) : 32}<span>%</span></strong>
                        <Badge tone={result?.risk_level === "high" ? "danger" : result?.risk_level === "low" ? "good" : "warning"}>{result?.risk_level ?? "Elevated"} risk profile</Badge>
                      </div>
                      <div className="risk-bar"><i style={{ width: `${Math.round((result?.risk_probability ?? 0.32) * 100)}%` }} /></div>
                      <p>{result?.explanation ?? "The submitted profile will be assessed for risk-support patterns after running the assessment."}</p>
                      {result?.model_version && <div className="chip-row"><Badge>{result.model_version}</Badge><Badge>{result.confidence_label}</Badge></div>}
                    </>
                  )}
                  {mutation.isError && <ErrorState title="Assessment unavailable" body={mutation.error.message || "The API did not return a valid risk assessment."} />}
                </Card>

                <Card title="Primary Contributing Factors">
                  {result ? <FactorList items={result.top_factors} /> : <EmptyState title="Run the assessment" body="The factor ranking and interpretation will appear here after submission." />}
                </Card>
              </div>

              <div className="wizard-results-side">
                <Card title="Related Health Indicators">
                  {result?.related_flags.length ? <div className="alert-list">{result.related_flags.map((flag) => <div key={flag.label} className={flag.level}><strong>{flag.label}</strong><span>{flag.detail}</span></div>)}</div> : <EmptyState title="No related flags yet" body="Related health indicators will appear here when the profile triggers them." />}
                </Card>

                {variant === "app" && (
                  <Card title="Clinical Protocol Suggestion">
                    <p>{result?.next_actions[0] ?? "Initiate consistent lifestyle tracking and consider clinician review if elevated indicators persist."}</p>
                    <button className="secondary">Add to Care Plan</button>
                  </Card>
                )}

                {variant === "onboarding" && (
                  <Card title="Continue">
                    <p>Now you can start tracking logs and receiving insights.</p>
                    <button className="primary" type="button" disabled={!result} onClick={onComplete}>
                      Continue to app
                    </button>
                  </Card>
                )}

                {variant === "demo" && result && (
                  <Card title="Want more than a snapshot?">
                    <p>Create an account to save your baseline, track changes over time, and unlock monitoring insights and reports.</p>
                    <div className="cta-row">
                      <Link className="primary button-link" to="/register">Create account</Link>
                      <Link className="secondary button-link" to="/login">Sign in</Link>
                    </div>
                  </Card>
                )}
              </div>
            </div>

            <div className="wizard-nav">
              <button type="button" className="secondary" onClick={() => setStep("lifestyle")}>
                Edit inputs
              </button>
              <button type="button" className="primary" onClick={() => setStep("profile")}>
                Start over
              </button>
            </div>
          </>
        )}
      </form>
    </div>
  );
}

export function RiskCheck() {
  return (
    <div className="page narrow">
      <PageHeader title="Patient Risk Assessment" subtitle="Complete the clinical matrix below to calculate the current Type 2 diabetes risk profile." />
      <RiskCheckFlow variant="app" />
    </div>
  );
}
