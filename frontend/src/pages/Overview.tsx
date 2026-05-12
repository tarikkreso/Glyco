import { useQuery } from "@tanstack/react-query";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { GlycoInsightPanel } from "../components/GlycoInsightPanel";
import { Badge, Card, EmptyState, ErrorState, FactorList, LoadingState, PageHeader, StatCard } from "../components/ui";

export function Overview() {
  const risk = useQuery({ queryKey: ["risk"], queryFn: () => api.latestRisk() });
  const monitoring = useQuery({ queryKey: ["monitoring"], queryFn: () => api.latestMonitoring() });
  const logs = useQuery({ queryKey: ["logs"], queryFn: () => api.logs() });
  const insight = useQuery({ queryKey: ["insight"], queryFn: () => api.insight() });
  const bayesian = useQuery({ queryKey: ["bayesian-risk"], queryFn: () => api.bayesianRisk() });
  const riskTone = risk.data?.risk_level === "high" ? "danger" : risk.data?.risk_level === "medium" ? "warning" : "good";
  const hasError = risk.isError || monitoring.isError || logs.isError;
  return (
    <div className="page">
      <PageHeader title="Overview" subtitle="Clinical dashboard for diabetes risk and monitoring support." meta={risk.data?.model_version ? `Risk model: ${risk.data.model_version}` : "Last updated: Today"} />
      {hasError && <ErrorState title="Dashboard data is unavailable" body="Glyco could not load one or more overview panels. Check the API connection and try again." />}
      <div className="stats-grid">
        <StatCard label="Current Diabetes Risk" value={`${Math.round((risk.data?.risk_probability ?? 0) * 100)}%`} detail={risk.data?.risk_level ?? "Loading"} />
        <StatCard label="Monitoring Status" value={monitoring.data?.trend_label ?? "Loading"} detail={`Score ${monitoring.data?.trend_score ?? "-"}`} />
        <StatCard label="Related Risk Flags" value={`${risk.data?.related_flags.length ?? 0}`} detail="BMI, BP, cholesterol, cardio-metabolic" />
        <StatCard label="Next Recommended Action" value={risk.data?.next_actions[0] ?? "Log reading"} detail={monitoring.data?.recommended_actions[0] ?? "Review monitoring pattern this week"} />
      </div>
      <Card title="Bayesian Risk" action={<Badge tone={riskTone}>{bayesian.data?.number_of_updates ?? 0} updates</Badge>}>
        <div className="bayes-risk">
          <div className="bayes-risk-meta">
            <strong>{Math.round((bayesian.data?.posterior_mean ?? 0) * 100)}%</strong>
            <span>
              95% credible interval {Math.round((bayesian.data?.credible_interval.low ?? 0) * 100)}-
              {Math.round((bayesian.data?.credible_interval.high ?? 0) * 100)}%
            </span>
          </div>
          <div className="range-bar" aria-label="Bayesian credible interval">
            <span
              style={{
                left: `${Math.round((bayesian.data?.credible_interval.low ?? 0) * 100)}%`,
                width: `${Math.max(2, Math.round(((bayesian.data?.credible_interval.high ?? 0) - (bayesian.data?.credible_interval.low ?? 0)) * 100))}%`,
              }}
            />
            <em style={{ left: `${Math.round((bayesian.data?.posterior_mean ?? 0) * 100)}%` }} />
          </div>
        </div>
      </Card>
      <GlycoInsightPanel insight={insight.data} isLoading={insight.isLoading} />
      <div className="dashboard-grid">
        <Card title="30-Day Glucose Trend" action={<Badge tone={riskTone}>Risk {risk.data?.risk_level ?? "-"}</Badge>}>
          {logs.isLoading ? <LoadingState label="Loading glucose history" /> : logs.data?.length ? (
            <div className="chart-box">
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={logs.data}>
                  <XAxis dataKey="log_date" tick={{ fontSize: 11 }} />
                  <YAxis domain={["dataMin - 10", "dataMax + 10"]} tick={{ fontSize: 11 }} />
                  <Tooltip />
                  <Line type="monotone" dataKey="fasting_glucose" stroke="#2f5d50" strokeWidth={3} dot={{ r: 4 }} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : <EmptyState title="No glucose logs yet" body="Add a few readings in Monitoring to build a daily trend view." />}
        </Card>
        <Card title="Top Contributing Factors">
          {risk.isLoading ? <LoadingState label="Loading risk drivers" /> : risk.data?.top_factors.length ? <FactorList items={risk.data.top_factors} /> : <EmptyState title="No factor ranking yet" body="Run a risk assessment to populate the clinical driver list." />}
        </Card>
      </div>
      <div className="dashboard-grid">
        <Card title="Weekly Summary">
          {monitoring.isLoading ? <LoadingState label="Loading weekly summary" /> : <p>{String(monitoring.data?.summary.message ?? "Glyco is preparing the weekly monitoring summary.")}</p>}
          <div className="chip-row">
            <Badge tone={monitoring.data?.trend_label === "concerning" ? "danger" : monitoring.data?.trend_label === "stable" ? "good" : "warning"}>
              {monitoring.data?.trend_label ?? "watch"}
            </Badge>
            {monitoring.data?.model_version && <Badge>{monitoring.data.model_version}</Badge>}
          </div>
        </Card>
        <Card title="Recent Log Review">
          {(logs.data ?? []).length ? <div className="compact-table">
            {(logs.data ?? []).slice(-5).reverse().map((log) => <div key={log.id}><span>{log.log_date}</span><strong>{log.fasting_glucose} mg/dL</strong><span>{log.activity_minutes ?? 0} min activity</span></div>)}
          </div> : <EmptyState title="No recent logs" body="Add a new reading to start the monitoring history." />}
        </Card>
      </div>
      <Card title="Related Health Indicators">
        {risk.data?.related_flags.length ? <div className="alert-list">{risk.data.related_flags.map((flag) => <div key={flag.label} className={flag.level}><strong>{flag.label}</strong><span>{flag.detail}</span></div>)}</div> : <EmptyState title="No related flags" body="This profile does not currently trigger additional cardio-metabolic flags." />}
      </Card>
    </div>
  );
}
