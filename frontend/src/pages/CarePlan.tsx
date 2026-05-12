import { useQuery } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { api } from "../api/client";
import { Card, PageHeader } from "../components/ui";

export function CarePlan() {
  const plan = useQuery({ queryKey: ["diet"], queryFn: () => api.diet() });
  const prefer = (plan.data?.prefer as string[]) ?? [];
  const limit = (plan.data?.limit as string[]) ?? [];
  const sample = (plan.data?.sample_day as string[]) ?? [];
  const weekly = (plan.data?.weekly_recommendations as string[]) ?? [];
  return (
    <div className="page">
      <PageHeader title="Care Plan" subtitle="Supportive meal and lifestyle direction based on current Glyco risk patterns." />
      <Card title="Suggested Nutrition Direction">
        <p>{String(plan.data?.direction ?? "Steady glucose support")}</p>
      </Card>
      <div className="dashboard-grid">
        <Card title="Foods To Prefer"><ul className="clinical-list">{prefer.map((item) => <li key={item}><CheckCircle2 size={16} />{item}</li>)}</ul></Card>
        <Card title="Foods To Limit"><ul className="clinical-list">{limit.map((item) => <li key={item}><CheckCircle2 size={16} />{item}</li>)}</ul></Card>
      </div>
      <div className="dashboard-grid">
        <Card title="Sample Day">{sample.map((item) => <div className="meal-card" key={item}>{item}</div>)}</Card>
        <Card title="Weekly Recommendations"><ul className="clinical-list">{weekly.map((item) => <li key={item}><CheckCircle2 size={16} />{item}</li>)}</ul></Card>
      </div>
    </div>
  );
}
