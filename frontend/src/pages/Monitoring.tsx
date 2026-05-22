import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Brain, ClipboardList, LineChart as LineChartIcon, Target } from "lucide-react";
import { Area, ComposedChart, Legend, Line, LineChart, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type GlucoseForecast } from "../api/client";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";

function percent(value?: number) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "-";
}

function trendTone(label?: string) {
  if (label === "concerning") return "danger";
  if (label === "watch") return "warning";
  return "good";
}

function toMmol(value: number) {
  return value > 40 ? value / 18.015 : value;
}

function trendBadgeTone(label?: string) {
  if (label === "rising") return "warning";
  if (label === "falling") return "danger";
  if (label === "stable") return "good";
  return "neutral";
}

function ForecastChart({ actualLogs, forecast }: { actualLogs: Array<{ timestamp: string; glucose_mmol: number }>; forecast: GlucoseForecast | null }) {
  const queryClient = useQueryClient();
  const refreshForecast = useMutation({
    mutationFn: () => api.triggerForecast(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["forecast"] });
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["insight"] });
    },
  });
  const sortedLogs = [...actualLogs].sort((left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime());
  const lastActualTime = sortedLogs.length ? new Date(sortedLogs[sortedLogs.length - 1].timestamp).getTime() : Date.now();
  const eightHoursAgo = lastActualTime - 8 * 60 * 60 * 1000;
  const actualPoints = sortedLogs
    .filter((log) => new Date(log.timestamp).getTime() >= eightHoursAgo)
    .map((log) => ({
      time: new Date(log.timestamp).getTime(),
      actual: Number(log.glucose_mmol.toFixed(2)),
      forecast: null,
      forecastBand: null,
    }));
  const forecastPoints = forecast
    ? ([60, 120, 180, 240] as const).map((minutes) => {
        const key = String(minutes) as "60" | "120" | "180" | "240";
        return {
          time: lastActualTime + minutes * 60 * 1000,
          actual: null,
          forecast: forecast.predictions[key],
          forecastBand: [forecast.confidence_intervals[key].low, forecast.confidence_intervals[key].high],
        };
      })
    : [];
  const chartData = [...actualPoints, ...forecastPoints].sort((left, right) => left.time - right.time);
  const trendLabel = forecast?.trend_direction ? forecast.trend_direction[0].toUpperCase() + forecast.trend_direction.slice(1) : "";

  return (
    <Card title="Glucose Forecast" action={forecast ? <Badge tone={trendBadgeTone(forecast.trend_direction)}>{trendLabel}</Badge> : <Badge>Forecast</Badge>}>
      <div className="forecast-status">
        {!forecast && <p>Add more readings to enable glucose forecasting</p>}
        {forecast?.predicted_low_alert && <div className="forecast-warning danger">{forecast.recommendation}</div>}
        {forecast?.predicted_high_alert && <div className="forecast-warning warning">{forecast.recommendation}</div>}
      </div>
      <div className="chart-box monitoring-chart forecast-chart">
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart data={chartData}>
            <XAxis
              dataKey="time"
              domain={[eightHoursAgo, lastActualTime + 4 * 60 * 60 * 1000]}
              tick={{ fontSize: 11 }}
              tickFormatter={(value) => new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              type="number"
            />
            <YAxis domain={[2, 16]} tick={{ fontSize: 11 }} />
            <Tooltip labelFormatter={(value) => new Date(Number(value)).toLocaleString()} />
            <Legend payload={[
              { value: "Actual", type: "line", color: "#154539" },
              { value: "Forecast", type: "line", color: "#4f46e5" },
              { value: "Target Range", type: "rect", color: "#d9f4df" },
            ]} />
            <ReferenceArea y1={2} y2={3.9} fill="#dc2626" fillOpacity={0.08} />
            <ReferenceArea y1={10} y2={16} fill="#f97316" fillOpacity={0.08} />
            <ReferenceLine x={Date.now()} stroke="#6b7280" strokeDasharray="4 4" />
            <Area dataKey="forecastBand" stroke="none" fill="#4f46e5" fillOpacity={0.15} connectNulls />
            <Line name="Actual" dataKey="actual" stroke="#154539" strokeWidth={3} dot={{ r: 3 }} connectNulls={false} />
            <Line name="Forecast" dataKey="forecast" stroke="#4f46e5" strokeWidth={3} strokeDasharray="7 5" dot={{ r: 4 }} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="forecast-actions">
        <button type="button" className="secondary" disabled={refreshForecast.isPending} onClick={() => refreshForecast.mutate()}>
          Refresh Forecast
        </button>
      </div>
    </Card>
  );
}

export function Monitoring() {
  const logs = useQuery({ queryKey: ["logs"], queryFn: () => api.logs() });
  const monitoring = useQuery({ queryKey: ["monitoring"], queryFn: () => api.latestMonitoring() });
  const risk = useQuery({ queryKey: ["risk"], queryFn: () => api.latestRisk() });
  const bayesian = useQuery({ queryKey: ["bayesian"], queryFn: () => api.bayesianRisk() });
  const insight = useQuery({ queryKey: ["insight"], queryFn: () => api.insight() });
  const forecast = useQuery({ queryKey: ["forecast"], queryFn: () => api.getForecastLatest().catch(() => null), retry: false });
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
  const actualLogs = (logs.data ?? []).map((log) => ({
    timestamp: log.created_at ?? log.log_date,
    glucose_mmol: toMmol(log.glucose_level),
  }));
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
                <Line type="monotone" dataKey="fasting" name="Fasting" stroke="var(--primary)" strokeWidth={3} strokeLinecap="round" connectNulls isAnimationActive={false} dot={{ r: 4, strokeWidth: 2, fill: "var(--surface)", stroke: "var(--primary)" }} activeDot={{ r: 6 }} />
                <Line type="monotone" dataKey="non_fasting" name="Not fasting" stroke="var(--rust)" strokeWidth={3} strokeLinecap="round" connectNulls isAnimationActive={false} dot={{ r: 4, strokeWidth: 2, fill: "var(--surface)", stroke: "var(--rust)" }} activeDot={{ r: 6 }} />
              </LineChart>
            </ResponsiveContainer>
          </div> : <EmptyState title="No glucose history" body="Add a few glucose logs to create a useful trend view." />}
        </Card>
        <ForecastChart actualLogs={actualLogs} forecast={forecast.data ?? null} />
      </div>

      <div className="monitoring-main-grid">
        <Card title="Recent Log History" action={<Activity size={18} />}>
          {(logs.data ?? []).length ? <div className="compact-table">{(logs.data ?? []).slice(-8).reverse().map((log) => <div key={log.id}><span>{log.log_date}</span><strong>{log.glucose_level} mg/dL</strong><span>{log.is_fasting ? "Fasting" : "Not fasting"}</span></div>)}</div> : <EmptyState title="No log history" body="Use the Log data button to add the first monitoring record." />}
        </Card>

        <Card title="What to do next" action={<ClipboardList size={18} />}>
          <div className="monitoring-next-insight">
            <div className="roadmap-panel">
              <span>Roadmap</span>
              <ol className="roadmap-list">
                <li>
                  <strong>Step 1: Do the next best action</strong>
                  <p>{thompsonAction ? `${thompsonAction.title} - ${thompsonAction.body}` : "Keep glucose logging consistent so Glyco can learn your trend."}</p>
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
    </div>
  );
}
