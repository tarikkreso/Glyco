import { useQuery } from "@tanstack/react-query";
import { Activity, Brain, ClipboardList, LineChart as LineChartIcon, Plus, Target, TrendingUp } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { GlycoInsightPanel } from "../components/GlycoInsightPanel";
import { LogNewDataForm } from "../components/LogNewDataForm";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";

function percent(value?: number) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "-";
}

function trendTone(label?: string) {
  if (label === "concerning") return "danger";
  if (label === "watch") return "warning";
  return "good";
}

export function Monitoring() {
  const logs = useQuery({ queryKey: ["logs"], queryFn: () => api.logs() });
  const monitoring = useQuery({ queryKey: ["monitoring"], queryFn: () => api.latestMonitoring() });
  const risk = useQuery({ queryKey: ["risk"], queryFn: () => api.latestRisk() });
  const bayesian = useQuery({ queryKey: ["bayesian"], queryFn: () => api.bayesianRisk() });
  const insight = useQuery({ queryKey: ["insight"], queryFn: () => api.insight() });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api.alerts() });
  const latestLog = logs.data?.length ? logs.data[logs.data.length - 1] : undefined;
  const thompsonAction = insight.data?.learning_summary?.next_best_action;
  const pattern = insight.data?.learning_summary?.recent_glucose_pattern;
  const chartData = (logs.data ?? []).slice(-14);

  return (
    <div className="page monitoring-page">
      <PageHeader
        title="Monitoring"
        subtitle="A patient-friendly view of glucose trend support, model evidence, Bayesian smoothing, and adaptive recommendations."
        meta={monitoring.data?.model_version ? `Trend model: ${monitoring.data.model_version}` : undefined}
      />
      {(logs.isError || monitoring.isError || bayesian.isError) && <ErrorState title="Monitoring data is unavailable" body="Glyco could not load one or more monitoring signals." />}

      <section className="monitoring-hero-panel">
        <div>
          <span>Bottom line</span>
          <h2>{monitoring.data?.trend_label === "concerning" ? "This week needs attention" : monitoring.data?.trend_label === "watch" ? "Watch the next few readings" : "Pattern looks steadier"}</h2>
          <p>{String(monitoring.data?.summary.message ?? "Glyco is waiting for enough glucose logs to describe the trend.")}</p>
        </div>
        <div className="monitoring-hero-stats">
          <div><span>Latest glucose</span><strong>{latestLog ? `${latestLog.glucose_level} mg/dL` : "-"}</strong></div>
          <div><span>Trend state</span><strong>{monitoring.data?.trend_label ?? "-"}</strong></div>
          <div><span>Bayesian risk</span><strong>{percent(bayesian.data?.posterior_mean)}</strong></div>
          <div><span>Next action</span><strong>{thompsonAction?.type ?? "Learning"}</strong></div>
        </div>
      </section>

      <div className="model-flow-grid">
        <Card title="Trained Glucose Trend Model" action={<Badge tone={trendTone(monitoring.data?.trend_label)}>{monitoring.data?.trend_label ?? "loading"}</Badge>}>
          <div className="explain-card-body">
            <LineChartIcon size={22} />
            <p>The trend model reads recent glucose logs only. It classifies the pattern as stable, watch, or concerning, so this is glucose trend support, not full vitals monitoring.</p>
            <small>{monitoring.data?.model_version ?? "Loading model version"}</small>
          </div>
        </Card>
        <Card title="Bayesian Risk Layer" action={<Badge>{bayesian.data ? `${bayesian.data.number_of_updates} updates` : "posterior"}</Badge>}>
          <div className="explain-card-body">
            <Brain size={22} />
            <p>Bayesian smoothing keeps the risk signal from jumping too much after a single RF model result. It shows the current risk belief over time.</p>
            <small>Posterior {percent(bayesian.data?.posterior_mean)} with interval {bayesian.data ? `${percent(bayesian.data.credible_interval.low)}-${percent(bayesian.data.credible_interval.high)}` : "-"}</small>
          </div>
        </Card>
        <Card title="Thompson Recommendation Ranker" action={<Badge>{thompsonAction?.type ?? "learning"}</Badge>}>
          <div className="explain-card-body">
            <Target size={22} />
            <p>This is the agent learning layer. Feedback changes which recommendation type Glyco puts first next time.</p>
            <small>{thompsonAction ? `${thompsonAction.title}: ${thompsonAction.body}` : "No personalized action yet"}</small>
          </div>
        </Card>
      </div>

      <div className="monitoring-main-grid">
        <Card title="Glucose Trend" action={<Badge tone={trendTone(monitoring.data?.trend_label)}>{monitoring.data?.trend_label ?? "watch"}</Badge>}>
          {logs.isLoading ? <LoadingState label="Loading glucose history" /> : chartData.length ? <div className="chart-box monitoring-chart">
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData}><XAxis dataKey="log_date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Line dataKey="glucose_level" stroke="#154539" strokeWidth={3} dot={{ r: 3 }} /></LineChart>
            </ResponsiveContainer>
          </div> : <EmptyState title="No glucose history" body="Add a few glucose logs to create a useful trend view." />}
        </Card>
        <Card title="What to do next" action={<ClipboardList size={18} />}>
          <div className="next-action-panel">
            <span>Adaptive next-best action</span>
            <strong>{thompsonAction?.title ?? "Keep glucose logging consistent"}</strong>
            <p>{thompsonAction?.body ?? "Add the next glucose reading so Glyco can detect whether the pattern is improving."}</p>
            <small>Recent pattern: {pattern?.label ?? "learning"} {pattern?.average ? `, average ${pattern.average} mg/dL` : ""}</small>
          </div>
        </Card>
      </div>

      <div className="monitoring-main-grid">
        <Card title="Anomaly Notices">
          {monitoring.isLoading ? <LoadingState label="Loading anomaly flags" /> : monitoring.data?.anomaly_flags.length ? (
            <div className="alert-list">{monitoring.data.anomaly_flags.map((flag) => <div key={flag.label} className={flag.level}><strong>{flag.label}</strong><span>{flag.detail}</span></div>)}</div>
          ) : <EmptyState title="No anomaly notices" body="Recent glucose logs do not currently show a flagged anomaly pattern." />}
        </Card>
        <Card title="Agent Alerts">
          {alerts.isLoading ? <LoadingState label="Loading proactive alerts" /> : (alerts.data ?? []).length ? (
            <div className="alert-list">{alerts.data?.slice(0, 4).map((alert) => <div key={alert.id} className={alert.severity === "danger" ? "danger" : "warning"}><strong>{alert.title}</strong><span>{alert.message} {alert.recommended_action}</span></div>)}</div>
          ) : <EmptyState title="No active alerts" body="After a new log, the agent creates an alert when the trend shifts into watch or concerning." />}
        </Card>
      </div>

      <GlycoInsightPanel insight={insight.data} isLoading={insight.isLoading} />

      <div className="monitoring-main-grid">
        <Card title="Add New Glucose Log" action={<Plus size={18} />}>
          <LogNewDataForm />
        </Card>
        <Card title="Recent Log History" action={<Activity size={18} />}>
          {(logs.data ?? []).length ? <div className="compact-table">{(logs.data ?? []).slice(-8).reverse().map((log) => <div key={log.id}><span>{log.log_date}</span><strong>{log.glucose_level} mg/dL</strong><span>{log.is_fasting ? "Fasting" : "Not fasting"}</span></div>)}</div> : <EmptyState title="No log history" body="Use the form to add the first monitoring record." />}
        </Card>
      </div>

      <Card title="Model Evidence Summary" action={<TrendingUp size={18} />}>
        <div className="model-evidence-list">
          <div><span>RF risk model</span><strong>{risk.data?.model_version ?? "Loading"}</strong><small>{risk.data?.risk_level ?? "-"} risk</small></div>
          <div><span>Trend model</span><strong>{monitoring.data?.model_version ?? "Loading"}</strong><small>{monitoring.data?.trend_label ?? "-"} trend</small></div>
          <div><span>Bayesian posterior</span><strong>{percent(bayesian.data?.posterior_mean)}</strong><small>{bayesian.data?.number_of_updates ?? 0} updates</small></div>
          <div><span>Recommendation learning</span><strong>{thompsonAction?.type ?? "Learning"}</strong><small>{thompsonAction?.title ?? "Waiting for feedback"}</small></div>
        </div>
      </Card>
    </div>
  );
}
