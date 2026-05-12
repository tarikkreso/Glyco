import { useMutation } from "@tanstack/react-query";
import { Activity, Beaker, UserRound } from "lucide-react";
import { useForm } from "react-hook-form";
import { api, RiskAssessment } from "../api/client";
import { Badge, Card, EmptyState, ErrorState, FactorList, LoadingState, PageHeader } from "../components/ui";

type FormValues = {
  age: number; sex: string; weight_kg: number; height_cm: number; high_bp: boolean; high_chol: boolean; smoker: boolean; phys_activity: boolean; family_history_diabetes: boolean; general_health: number;
};

export function RiskCheck() {
  const { register, handleSubmit } = useForm<FormValues>({ defaultValues: { age: 58, sex: "Female", weight_kg: 88, height_cm: 166, high_bp: true, high_chol: true, smoker: false, phys_activity: true, family_history_diabetes: true, general_health: 3 } });
  const mutation = useMutation<RiskAssessment, Error, FormValues>({ mutationFn: (values) => api.assessRisk({ user_id: 1, fruits: true, veggies: true, stroke_history: false, heart_disease_history: false, difficulty_walking: false, ...values }) });
  const result = mutation.data;
  return (
    <div className="page narrow">
      <PageHeader title="Patient Risk Assessment" subtitle="Complete the clinical matrix below to calculate the current Type 2 diabetes risk profile." />
      <div className="risk-layout">
        <form onSubmit={handleSubmit((values) => mutation.mutate(values))} className="form-stack">
          <Card title="Demographics & Anthropometrics" action={<UserRound size={18} />}>
            <label>Patient Age<input type="number" {...register("age", { valueAsNumber: true })} /></label>
            <label>Biological Sex<select {...register("sex")}><option>Female</option><option>Male</option></select></label>
            <label>Weight (kg)<input type="number" step="0.1" {...register("weight_kg", { valueAsNumber: true })} /></label>
            <label>Height (cm)<input type="number" step="0.1" {...register("height_cm", { valueAsNumber: true })} /></label>
          </Card>
          <Card title="Clinical Markers" action={<Beaker size={18} />}>
            <label className="check"><input type="checkbox" {...register("high_bp")} /> Hypertension</label>
            <label className="check"><input type="checkbox" {...register("high_chol")} /> High cholesterol</label>
            <label className="check"><input type="checkbox" {...register("family_history_diabetes")} /> Family diabetes history</label>
            <label>General Health<select {...register("general_health", { valueAsNumber: true })}><option value={1}>Excellent</option><option value={2}>Very good</option><option value={3}>Good</option><option value={4}>Fair</option><option value={5}>Poor</option></select></label>
          </Card>
          <Card title="Behavioral & Lifestyle" action={<Activity size={18} />}>
            <label className="check"><input type="checkbox" {...register("smoker")} /> Current smoker</label>
            <label className="check"><input type="checkbox" {...register("phys_activity")} /> Physically active</label>
          </Card>
          <button className="primary" type="submit">Run Assessment</button>
        </form>
        <div className="result-column">
          <Card title="Calculated Probability">
            {mutation.isPending ? <LoadingState label="Running assessment" /> : <>
              <div className="probability">
                <strong>{result ? Math.round(result.risk_probability * 100) : 32}<span>%</span></strong>
                <Badge tone={result?.risk_level === "high" ? "danger" : result?.risk_level === "low" ? "good" : "warning"}>{result?.risk_level ?? "Elevated"} risk profile</Badge>
              </div>
              <div className="risk-bar"><i style={{ width: `${Math.round((result?.risk_probability ?? 0.32) * 100)}%` }} /></div>
              <p>{result?.explanation ?? "The submitted profile will be assessed for risk-support patterns after running the assessment."}</p>
              {result?.model_version && <div className="chip-row"><Badge>{result.model_version}</Badge><Badge>{result.confidence_label}</Badge></div>}
            </>}
            {mutation.isError && <ErrorState title="Assessment unavailable" body={mutation.error.message || "The API did not return a valid risk assessment."} />}
          </Card>
          <Card title="Primary Contributing Factors">
            {result ? <FactorList items={result.top_factors} /> : <EmptyState title="Run the assessment" body="The factor ranking and interpretation will appear here after submission." />}
          </Card>
          <Card title="Related Health Indicators">
            {result?.related_flags.length ? <div className="alert-list">{result.related_flags.map((flag) => <div key={flag.label} className={flag.level}><strong>{flag.label}</strong><span>{flag.detail}</span></div>)}</div> : <EmptyState title="No related flags yet" body="Related health indicators will appear here when the profile triggers them." />}
          </Card>
          <Card title="Clinical Protocol Suggestion">
            <p>{result?.next_actions[0] ?? "Initiate consistent lifestyle tracking and consider clinician review if elevated indicators persist."}</p>
            <button className="secondary">Add to Care Plan</button>
          </Card>
        </div>
      </div>
    </div>
  );
}
