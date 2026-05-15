import { useQuery } from "@tanstack/react-query";
import { Activity, Brain, ClipboardList, LineChart as LineChartIcon, Target } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
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
  const latestLog = logs.data?.length ? logs.data[logs.data.length - 1] : undefined;
  const thompsonAction = insight.data?.learning_summary?.next_best_action;
  const pattern = insight.data?.learning_summary?.recent_glucose_pattern;
  const chartData = (logs.data ?? []).slice(-14).map((log) => {
    const nonFastingValue = log.post_meal_glucose ?? log.glucose_level;
    return {
      log_date: log.log_date,
      fasting: log.is_fasting ? log.glucose_level : null,
      non_fasting: log.is_fasting ? null : nonFastingValue,
    };
  });
  const weekStatus = monitoring.data?.trend_label === "concerning" ? "Needs attention" : monitoring.data?.trend_label === "watch" ? "Watch closely" : monitoring.data?.trend_label ? "Looks steadier" : "-";

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

          <details className="bottom-line-evidence">
            <summary>Model evidence summary</summary>
            <div className="model-evidence-list">
              <div><span>RF risk model</span><strong>{risk.data?.model_version ?? "Loading"}</strong><small>{risk.data?.risk_level ?? "-"} risk</small></div>
              <div><span>Trend model</span><strong>{monitoring.data?.model_version ?? "Loading"}</strong><small>{monitoring.data?.trend_label ?? "-"} trend</small></div>
              <div><span>Bayesian posterior</span><strong>{percent(bayesian.data?.posterior_mean)}</strong><small>{bayesian.data?.number_of_updates ?? 0} updates</small></div>
              <div><span>Recommendation learning</span><strong>{thompsonAction?.type ?? "Learning"}</strong><small>{thompsonAction?.title ?? "Waiting for feedback"}</small></div>
            </div>
          </details>
        </div>
        <div className="monitoring-hero-stats">
          <div><span>Latest glucose</span><strong>{latestLog ? `${latestLog.glucose_level} mg/dL` : "-"}</strong></div>
          <div><span>This week</span><strong>{weekStatus}</strong></div>
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
            <div className="chart-legend" aria-hidden="true">
              <span className="legend-item fasting"><i />Fasting</span>
              <span className="legend-item non-fasting"><i />Not fasting</span>
            </div>
            <ResponsiveContainer width="100%" height={320}>
              <LineChart data={chartData}>
                <XAxis dataKey="log_date" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Line
                  type="monotone"
                  dataKey="fasting"
                  name="Fasting"
                  stroke="var(--primary)"
                  strokeWidth={3}
                  strokeLinecap="round"
                  connectNulls
                  isAnimationActive={false}
                  dot={{ r: 4, strokeWidth: 2, fill: "var(--surface)", stroke: "var(--primary)" }}
                  activeDot={{ r: 6 }}
                />
                <Line
                  type="monotone"
                  dataKey="non_fasting"
                  name="Not fasting"
                  stroke="var(--rust)"
                  strokeWidth={3}
                  strokeLinecap="round"
                  connectNulls
                  isAnimationActive={false}
                  dot={{ r: 4, strokeWidth: 2, fill: "var(--surface)", stroke: "var(--rust)" }}
                  activeDot={{ r: 6 }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div> : <EmptyState title="No glucose history" body="Add a few glucose logs to create a useful trend view." />}
        </Card>
        <Card title="Recent Log History" action={<Activity size={18} />}>
          {(logs.data ?? []).length ? <div className="compact-table">{(logs.data ?? []).slice(-8).reverse().map((log) => <div key={log.id}><span>{log.log_date}</span><strong>{log.glucose_level} mg/dL</strong><span>{log.is_fasting ? "Fasting" : "Not fasting"}</span></div>)}</div> : <EmptyState title="No log history" body="Use the Log data button to add the first monitoring record." />}
        </Card>
      </div>

      <Card title="What to do next" action={<ClipboardList size={18} />}>
        <div className="monitoring-next-insight">
          <div className="roadmap-panel">
            <span>Roadmap</span>
            <ol className="roadmap-list">
              <li>
                <strong>Step 1: Do the next best action</strong>
                <p>{thompsonAction ? `${thompsonAction.title} — ${thompsonAction.body}` : "Keep glucose logging consistent so Glyco can learn your trend."}</p>
              </li>
              <li>
                <strong>Step 2: Log the next reading</strong>
                <p>Use the Log data button after your next glucose check to keep the trend view accurate.</p>
              </li>
              <li>
                <strong>Step 3: Follow your weekly plan</strong>
                <p>
                  {insight.data?.what_to_do_next?.length
                    ? insight.data.what_to_do_next.slice(0, 3).join(" ")
                    : "Glyco will add a weekly plan once it has enough recent monitoring history."}
                </p>
              </li>
            </ol>
            <small>Recent pattern: {pattern?.label ?? "learning"} {pattern?.average ? `, average ${pattern.average} mg/dL` : ""}</small>
          </div>

          {insight.isLoading ? (
            <LoadingState label="Preparing Glyco insight" />
          ) : insight.data ? (
            <div className="insight-grid">
              <section className="insight-block">
                <Brain size={18} />
                <div><span>Glyco Insight</span><p>{insight.data.what_changed}</p></div>
              </section>
              <section className="insight-block">
                <Target size={18} />
                <div><span>Why it matters</span><p>{insight.data.why_it_matters}</p></div>
              </section>
              <p className="insight-note">{insight.data.confidence_note}</p>
            </div>
          ) : (
            <EmptyState title="Insight unavailable" body="Glyco needs a current risk assessment and monitoring history to prepare this panel." />
          )}
        </div>
      </Card>
    </div>
  );
}
