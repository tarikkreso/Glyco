import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Brain, ClipboardList, LineChart, ShieldCheck, Target, TrendingUp } from "lucide-react";
import { useMemo } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/auth";
import { Badge, Card, EmptyState, LoadingState, PageHeader } from "../components/ui";

const metricCopy: Record<string, { title: string; plain: string; icon: typeof TrendingUp }> = {
  glucose: {
    title: "Glucose level",
    plain: "This is the latest glucose reading you logged. Glyco compares it with your recent pattern instead of treating one number as the whole story.",
    icon: TrendingUp,
  },
  nutrition: {
    title: "Nutrition focus",
    plain: "This is a practical food-related focus chosen from your risk/trend pattern and recommendation learning. It is not a diet diagnosis.",
    icon: ClipboardList,
  },
  hba1c: {
    title: "HbA1c context",
    plain: "HbA1c is a longer-term glucose marker. In this MVP it is shown as context unless you enter a lab value in the profile.",
    icon: ShieldCheck,
  },
  risk: {
    title: "Risk score",
    plain: "This comes from the active risk scorer. When RF artifacts are available, Glyco uses the trained Random Forest model; otherwise it falls back to transparent rules.",
    icon: Brain,
  },
  activity: {
    title: "Daily activity",
    plain: "Activity is used as a low-risk lever because light movement after meals can help many people smooth glucose spikes.",
    icon: LineChart,
  },
  bayesian: {
    title: "Bayesian risk layer",
    plain: "The Bayesian layer smooths the Random Forest risk probability over time, so one assessment does not swing the story too hard.",
    icon: Brain,
  },
  thompson: {
    title: "Thompson recommendation ranker",
    plain: "This is the online learning layer. When you mark recommendations useful or not useful, it changes which action Glyco ranks first.",
    icon: Target,
  },
};

function formatPercent(value?: number) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "-";
}

export function MetricDetail() {
  const auth = useAuth();
  const userId = auth.session?.userId ?? 1;
  const navigate = useNavigate();
  const { metricId = "glucose" } = useParams();
  const copy = metricCopy[metricId] ?? metricCopy.glucose;
  const Icon = copy.icon;
  const logs = useQuery({ queryKey: ["logs", userId], queryFn: () => api.logs(userId) });
  const risk = useQuery({ queryKey: ["risk", userId], queryFn: () => api.latestRisk(userId) });
  const monitoring = useQuery({ queryKey: ["monitoring", userId], queryFn: () => api.latestMonitoring(userId) });
  const bayesian = useQuery({ queryKey: ["bayesian", userId], queryFn: () => api.bayesianRisk(userId) });
  const insight = useQuery({ queryKey: ["insight", userId], queryFn: () => api.insight(userId) });
  const latestLog = logs.data?.length ? logs.data[logs.data.length - 1] : undefined;
  const values = useMemo(() => (logs.data ?? []).slice(-8).map((log) => log.glucose_level), [logs.data]);
  const average = values.length ? Math.round(values.reduce((sum, value) => sum + value, 0) / values.length) : undefined;
  const thompsonAction = insight.data?.learning_summary?.next_best_action;
  const riskSource = risk.data?.model_version === "random-forest-0.2" ? "trained RF risk model" : "risk fallback scorer";
  const trendSource = monitoring.data?.model_version === "glucose-trend-random-forest-0.2" ? "trained glucose trend model" : "monitoring fallback scorer";
  const primaryValue = {
    glucose: latestLog ? `${latestLog.glucose_level} mg/dL` : "-",
    nutrition: thompsonAction?.type ?? (risk.data?.risk_level === "high" ? "watch" : "steady"),
    hba1c: "6.5%",
    risk: risk.data?.risk_level ?? "-",
    activity: (latestLog?.activity_minutes ?? 0) >= 30 ? "Good" : "Low",
    bayesian: formatPercent(bayesian.data?.posterior_mean),
    thompson: thompsonAction?.title ?? "Learning from feedback",
  }[metricId] ?? "-";

  return (
    <div className="page metric-detail-page">
      <button className="secondary back-button" type="button" onClick={() => navigate("/overview")}><ArrowLeft size={16} /> Back to overview</button>
      <PageHeader title={copy.title} subtitle={copy.plain} meta="Patient-friendly explanation" />
      <section className="metric-detail-hero">
        <div className="metric-detail-icon"><Icon size={28} /></div>
        <div>
          <span>Current signal</span>
          <strong>{primaryValue}</strong>
          <p>{metricId === "thompson" ? thompsonAction?.body : monitoring.data?.summary.message ?? "Glyco will explain this as more readings arrive."}</p>
        </div>
      </section>
      <div className="metric-detail-grid">
        <Card title="Why this matters">
          <ul className="explain-list">
            <li>Glyco looks for patterns across logs, model output, and feedback, not just one isolated value.</li>
            <li>The {trendSource} describes the recent reading pattern as <strong>{monitoring.data?.trend_label ?? "unknown"}</strong>.</li>
            <li>The {riskSource} currently estimates <strong>{risk.data?.risk_level ?? "unknown"}</strong> risk.</li>
          </ul>
        </Card>
        <Card title="What Glyco uses">
          <div className="model-evidence-list">
            <div><span>Recent average</span><strong>{average ? `${average} mg/dL` : "-"}</strong></div>
            <div><span>RF risk model</span><strong>{risk.data?.model_version ?? "Loading"}</strong></div>
            <div><span>Trend model</span><strong>{monitoring.data?.model_version ?? "Loading"}</strong></div>
            <div><span>Bayesian posterior</span><strong>{formatPercent(bayesian.data?.posterior_mean)}</strong></div>
          </div>
        </Card>
        <Card title="Next useful action" action={<Badge>{thompsonAction?.type ?? "monitoring"}</Badge>}>
          {insight.isLoading ? <LoadingState label="Loading action" /> : thompsonAction ? (
            <p><strong>{thompsonAction.title}.</strong> {thompsonAction.body}</p>
          ) : <EmptyState title="No learned action yet" body="Ask Glyco a question and save feedback to personalize future actions." />}
        </Card>
      </div>
    </div>
  );
}
