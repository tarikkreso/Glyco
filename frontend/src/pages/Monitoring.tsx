import { useQuery } from "@tanstack/react-query";
import { Plus } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { GlycoInsightPanel } from "../components/GlycoInsightPanel";
import { LogNewDataForm } from "../components/LogNewDataForm";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageHeader, StatCard } from "../components/ui";

export function Monitoring() {
  const logs = useQuery({ queryKey: ["logs"], queryFn: () => api.logs() });
  const monitoring = useQuery({ queryKey: ["monitoring"], queryFn: () => api.latestMonitoring() });
  const insight = useQuery({ queryKey: ["insight"], queryFn: () => api.insight() });
  const alerts = useQuery({ queryKey: ["alerts"], queryFn: () => api.alerts() });
  return (
    <div className="page">
      <PageHeader title="Monitoring" subtitle="Time-based glucose, blood pressure, weight, and activity patterns." meta={monitoring.data?.model_version ? `Trend model: ${monitoring.data.model_version}` : undefined} />
      {(logs.isError || monitoring.isError) && <ErrorState title="Monitoring data is unavailable" body="Glyco could not load the trend history or monitoring summary." />}
      <div className="stats-grid">
        <StatCard label="Current State" value={monitoring.data?.trend_label ?? "-"} detail="Monitoring classifier" />
        <StatCard label="Avg Fasting Glucose" value={`${monitoring.data?.summary.avg_fasting_glucose ?? "-"} mg/dL`} detail="Recent window" />
        <StatCard label="Variability" value={`${monitoring.data?.summary.variability ?? "-"} mg/dL`} detail="Recent readings" />
        <StatCard label="Last Log" value={logs.data?.[logs.data.length - 1]?.log_date ?? "-"} detail="Patient-entered" />
      </div>
      <GlycoInsightPanel insight={insight.data} isLoading={insight.isLoading} />
      <div className="dashboard-grid">
        <Card title="Glucose Trend" action={<Badge tone={monitoring.data?.trend_label === "concerning" ? "danger" : "warning"}>{monitoring.data?.trend_label ?? "watch"}</Badge>}>
          {logs.isLoading ? <LoadingState label="Loading monitoring history" /> : logs.data?.length ? <div className="chart-box">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={logs.data}><XAxis dataKey="log_date" tick={{ fontSize: 11 }} /><YAxis tick={{ fontSize: 11 }} /><Tooltip /><Line dataKey="fasting_glucose" stroke="#2f5d50" strokeWidth={3} /></LineChart>
            </ResponsiveContainer>
          </div> : <EmptyState title="No monitoring history" body="Add at least a few glucose logs to create a trend panel." />}
        </Card>
        <Card title="Anomaly Notices">
          {monitoring.isLoading ? <LoadingState label="Loading anomaly flags" /> : monitoring.data?.anomaly_flags.length ? <div className="alert-list">{monitoring.data.anomaly_flags.map((flag) => <div key={flag.label} className={flag.level}><strong>{flag.label}</strong><span>{flag.detail}</span></div>)}</div> : <EmptyState title="No anomaly notices" body="Recent logs do not currently show a flagged anomaly pattern." />}
        </Card>
      </div>
      <Card title="Agent Alerts">
        {alerts.isLoading ? <LoadingState label="Loading proactive alerts" /> : (alerts.data ?? []).length ? <div className="alert-list">{alerts.data?.slice(0, 4).map((alert) => <div key={alert.id} className={alert.severity === "danger" ? "danger" : "warning"}><strong>{alert.title}</strong><span>{alert.message} {alert.recommended_action}</span></div>)}</div> : <EmptyState title="No active alerts" body="After a new log, the agent creates an alert when the trend shifts into watch or concerning." />}
      </Card>
      <div className="dashboard-grid">
        <Card title="Add New Log" action={<Plus size={18} />}>
          <LogNewDataForm />
        </Card>
        <Card title="Log History">
          {(logs.data ?? []).length ? <div className="compact-table">{(logs.data ?? []).slice(-8).reverse().map((log) => <div key={log.id}><span>{log.log_date}</span><strong>{log.fasting_glucose} mg/dL</strong><span>{log.systolic_bp}/{log.diastolic_bp}</span></div>)}</div> : <EmptyState title="No log history" body="Use the form to add the first monitoring record." />}
        </Card>
      </div>
      <Card title="Monitoring Interpretation">
        {monitoring.isLoading ? <LoadingState label="Loading interpretation" /> : <p>{String(monitoring.data?.summary.message ?? "Glyco will explain the recent monitoring trend here.")}</p>}
      </Card>
    </div>
  );
}
