import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Brain, ClipboardList, LineChart, ShieldCheck, Target, TrendingUp } from "lucide-react";
import { useMemo } from "react";
import { useI18n } from "../i18n";
import { useNavigate, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/auth";
import { Badge, Card, EmptyState, LoadingState, PageHeader } from "../components/ui";
import { formatGlucoseFromMgdl, useGlucoseUnit } from "../utils/glucoseUnits";

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
  const { t } = useI18n();
  const { unit } = useGlucoseUnit();
  const auth = useAuth();
  const userId = auth.session?.userId ?? 1;
  const navigate = useNavigate();
  const { metricId = "glucose" } = useParams();
  const copy = metricCopy[metricId] ?? metricCopy.glucose;
  const Icon = copy.icon;
  const title = t(`metric.${metricId}.title`);
  const plain = t(`metric.${metricId}.plain`);
  const logs = useQuery({ queryKey: ["logs", userId], queryFn: () => api.logs(userId) });
  const risk = useQuery({ queryKey: ["risk", userId], queryFn: () => api.latestRisk(userId) });
  const monitoring = useQuery({ queryKey: ["monitoring", userId], queryFn: () => api.latestMonitoring(userId) });
  const bayesian = useQuery({ queryKey: ["bayesian", userId], queryFn: () => api.bayesianRisk(userId) });
  const insight = useQuery({ queryKey: ["insight", userId], queryFn: () => api.insight(userId) });
  const latestLog = logs.data?.length ? logs.data[logs.data.length - 1] : undefined;
  const values = useMemo(() => (logs.data ?? []).slice(-8).map((log) => log.glucose_level), [logs.data]);
  const average = values.length ? Math.round(values.reduce((sum, value) => sum + value, 0) / values.length) : undefined;
  const thompsonAction = insight.data?.learning_summary?.next_best_action;
  const trendSource = monitoring.data?.model_version === "glucose-trend-random-forest-0.3" ? "trained glucose trend model" : "monitoring fallback scorer";
  const primaryValue = {
    glucose: formatGlucoseFromMgdl(latestLog?.glucose_level, unit),
    nutrition: thompsonAction?.type ?? (risk.data?.risk_level === "high" ? "watch" : "steady"),
    hba1c: "6.5%",
    risk: risk.data?.risk_level ?? "-",
    activity: (latestLog?.activity_minutes ?? 0) >= 30 ? "Good" : "Low",
    bayesian: formatPercent(bayesian.data?.posterior_mean),
    thompson: thompsonAction?.title ?? "Learning from feedback",
  }[metricId] ?? "-";

  return (
    <div className="page metric-detail-page">
      <button className="secondary back-button" type="button" onClick={() => navigate("/overview")}><ArrowLeft size={16} /> {t("common.backToOverview")}</button>
      <PageHeader title={title} subtitle={plain} meta={t("metric.meta")} />
      <section className="metric-detail-hero">
        <div className="metric-detail-icon"><Icon size={28} /></div>
        <div>
          <span>{t("metric.currentSignal")}</span>
          <strong>{primaryValue}</strong>
          <p>{metricId === "thompson" ? thompsonAction?.body : monitoring.data?.summary.message ?? t("metric.noExplanation")}</p>
        </div>
      </section>
      <div className="metric-detail-grid">
        <Card title={t("metric.whyTitle")}>
          <ul className="explain-list">
            <li>{t("metric.whyA")}</li>
            <li>{t("metric.whyB")} {t(trendSource === "trained glucose trend model" ? "metric.trendModel" : "metric.trendModel")} {t("metric.whyPattern")} <strong>{monitoring.data?.trend_label ?? t("common.unknown")}</strong>.</li>
            <li>{t("metric.whyC")} {t("metric.riskModel")} {t("metric.whyRisk")} <strong>{risk.data?.risk_level ?? t("common.unknown")}</strong>.</li>
          </ul>
        </Card>
        <Card title={t("metric.whatUses")}>
          <div className="model-evidence-list">
            <div><span>{t("metric.recentAverage")}</span><strong>{formatGlucoseFromMgdl(average, unit)}</strong></div>
            <div><span>{t("metric.riskModel")}</span><strong>{risk.data?.model_version ?? t("common.loading")}</strong></div>
            <div><span>{t("metric.trendModel")}</span><strong>{monitoring.data?.model_version ?? t("common.loading")}</strong></div>
            <div><span>{t("metric.bayesianPosterior")}</span><strong>{formatPercent(bayesian.data?.posterior_mean)}</strong></div>
          </div>
        </Card>
        <Card title={t("metric.nextActionTitle")} action={<Badge>{thompsonAction?.type ?? t("metric.monitoring")}</Badge>}>
          {insight.isLoading ? <LoadingState label={t("metric.loadingAction")} /> : thompsonAction ? (
            <p><strong>{thompsonAction.title}.</strong> {thompsonAction.body}</p>
          ) : <EmptyState title={t("metric.noLearnedActionTitle")} body={t("metric.noLearnedActionBody")} />}
        </Card>
      </div>
    </div>
  );
}
