import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, ClipboardList } from "lucide-react";
import { Area, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type GlucoseForecast, type MonitoringAssessment } from "../api/client";
import { useAuth } from "../auth/auth";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";

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

function titleCase(value?: string) {
  return value ? value[0].toUpperCase() + value.slice(1) : "";
}

function forecastHeadline(forecast: GlucoseForecast | null, monitoring?: MonitoringAssessment) {
  if (forecast?.predicted_low_alert) return "Forecast shows possible low glucose";
  if (forecast?.predicted_high_alert) return "Forecast shows possible high glucose";
  if (forecast?.trend_direction === "rising") return "Glucose may rise soon";
  if (forecast?.trend_direction === "falling") return "Glucose may fall soon";
  if (forecast?.trend_direction === "stable") return "Glucose forecast looks stable";
  if (monitoring?.trend_label === "concerning") return "This week needs attention";
  if (monitoring?.trend_label === "watch") return "Watch the next few readings";
  return "Pattern looks steadier";
}

function forecastSummary(forecast: GlucoseForecast | null, monitoring?: MonitoringAssessment) {
  if (forecast) {
    if (forecast.predicted_low_alert || forecast.predicted_high_alert) return forecast.recommendation;
    return `Forecast estimates ${forecast.trend_direction} glucose over the next 4 hours, with +60 min around ${forecast.predictions["60"]} mmol/L. Forecasts are estimates.`;
  }
  return String(monitoring?.summary.message ?? "Glyco is waiting for enough glucose logs to describe the trend.");
}

function nextCheckText(forecast: GlucoseForecast | null) {
  if (!forecast) return "Add a few readings, then refresh the forecast.";
  if (forecast.predicted_low_alert || forecast.predicted_high_alert) return "Check again soon and follow your care plan if symptoms or repeated out-of-range readings appear.";
  if (forecast.trend_direction === "rising" || forecast.trend_direction === "falling") return "Check again within the next 60 to 120 minutes to confirm the forecast direction.";
  return "Continue usual monitoring and refresh after your next reading.";
}

function ForecastActualDot(props: { cx?: number; cy?: number; payload?: { is_fasting?: boolean } }) {
  const { cx, cy, payload } = props;
  if (typeof cx !== "number" || typeof cy !== "number") return null;
  return <circle cx={cx} cy={cy} r={4} fill={payload?.is_fasting ? "#154539" : "#c2572b"} stroke="#fff" strokeWidth={2} />;
}

function ForecastTooltip({ active, label, payload }: { active?: boolean; label?: number; payload?: Array<{ dataKey?: string; value?: number; payload?: { is_fasting?: boolean; actual?: number; forecast?: number; forecastBand?: [number, number] } }> }) {
  if (!active || !payload?.length) return null;
  const point = payload.find((item) => item.payload?.actual != null || item.payload?.forecast != null)?.payload;
  if (!point) return null;
  return (
    <div className="forecast-tooltip">
      <strong>{label ? new Date(Number(label)).toLocaleString() : "Reading"}</strong>
      {point.actual != null && <span>Actual: {point.actual} mmol/L ({point.is_fasting ? "fasting" : "not fasting"})</span>}
      {point.forecast != null && <span>Forecast: {point.forecast} mmol/L</span>}
      {point.forecastBand && <span>Confidence: {point.forecastBand[0]}-{point.forecastBand[1]} mmol/L</span>}
    </div>
  );
}

function ForecastChart({ actualLogs, forecast, monitoring, userId }: { actualLogs: Array<{ timestamp: string; glucose_mmol: number; is_fasting: boolean }>; forecast: GlucoseForecast | null; monitoring?: MonitoringAssessment; userId: number }) {
  const queryClient = useQueryClient();
  const [historyHours, setHistoryHours] = useState<8 | 24 | 48 | "all">(24);
  const refreshForecast = useMutation({
    mutationFn: () => api.triggerForecast(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["forecast"] });
      queryClient.invalidateQueries({ queryKey: ["alerts"] });
      queryClient.invalidateQueries({ queryKey: ["insight"] });
    },
  });
  const sortedLogs = [...actualLogs].sort((left, right) => new Date(left.timestamp).getTime() - new Date(right.timestamp).getTime());
  const lastActualTime = sortedLogs.length ? new Date(sortedLogs[sortedLogs.length - 1].timestamp).getTime() : Date.now();
  const firstActualTime = sortedLogs.length ? new Date(sortedLogs[0].timestamp).getTime() : lastActualTime - 24 * 60 * 60 * 1000;
  const historyStartTime = historyHours === "all" ? firstActualTime : lastActualTime - historyHours * 60 * 60 * 1000;
  const actualPoints = sortedLogs
    .filter((log) => new Date(log.timestamp).getTime() >= historyStartTime)
    .map((log) => ({
      time: new Date(log.timestamp).getTime(),
      actual: Number(log.glucose_mmol.toFixed(2)),
      is_fasting: log.is_fasting,
      forecast: null,
      forecastBand: null,
    }));
  const forecastPoints = forecast
    ? ([60, 120, 180, 240] as const).map((minutes) => {
        const key = String(minutes) as "60" | "120" | "180" | "240";
        return {
          time: lastActualTime + minutes * 60 * 1000,
          actual: null,
          is_fasting: null,
          forecast: forecast.predictions[key],
          forecastBand: [forecast.confidence_intervals[key].low, forecast.confidence_intervals[key].high],
        };
      })
    : [];
  const chartData = [...actualPoints, ...forecastPoints].sort((left, right) => left.time - right.time);
  const trendLabel = titleCase(forecast?.trend_direction);
  const historicalTrend = titleCase(monitoring?.trend_label);

  return (
    <Card title="Glucose Forecast" action={forecast ? <Badge tone={trendBadgeTone(forecast.trend_direction)}>{trendLabel}</Badge> : <Badge>Forecast</Badge>}>
      <div className="forecast-status">
        {!forecast && <p>Add more readings to enable glucose forecasting</p>}
        {forecast && <p>{forecast.used_fallback ? "Fallback forecast" : "Model forecast"} - {forecast.model_version}</p>}

        <div className="forecast-range-controls" role="group" aria-label="Actual glucose history shown in forecast chart">
          {([8, 24, 48, "all"] as const).map((range) => (
            <button key={range} type="button" className={historyHours === range ? "active" : ""} onClick={() => setHistoryHours(range)}>
              {range === "all" ? "All" : `${range}h`}
            </button>
          ))}
        </div>
      </div>
      <div className="chart-box monitoring-chart forecast-chart">
        <ResponsiveContainer width="100%" height={340}>
          <ComposedChart data={chartData}>
            <XAxis
              dataKey="time"
              domain={[historyStartTime, lastActualTime + 4 * 60 * 60 * 1000]}
              tick={{ fontSize: 11 }}
              tickFormatter={(value) => new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
              type="number"
            />
            <YAxis domain={[2, 16]} tick={{ fontSize: 11 }} />
            <Tooltip content={<ForecastTooltip />} />
            <Legend payload={[
              { value: "Actual", type: "line", color: "#154539" },
              { value: "Forecast", type: "line", color: "#4f46e5" },
              { value: "Target Range", type: "rect", color: "#d9f4df" },
            ]} />
            <ReferenceArea y1={2} y2={3.9} fill="#dc2626" fillOpacity={0.08} />
            <ReferenceArea y1={10} y2={16} fill="#f97316" fillOpacity={0.08} />
            <ReferenceLine x={Date.now()} stroke="#6b7280" strokeDasharray="4 4" />
            <Area dataKey="forecastBand" stroke="none" fill="#4f46e5" fillOpacity={0.15} connectNulls />
            <Line name="Actual" dataKey="actual" stroke="#154539" strokeWidth={3} dot={<ForecastActualDot />} connectNulls={false} />
            <Line name="Forecast" dataKey="forecast" stroke="#4f46e5" strokeWidth={3} strokeDasharray="7 5" dot={{ r: 4 }} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="forecast-actions">
        <div className="forecast-model-evidence">
          <span>Forecast model: {forecast?.model_version ?? "Waiting for forecast"}</span>
          <span>Trend support: {monitoring?.model_version ?? "Loading trend model"}</span>
        </div>
        <button type="button" className="secondary" disabled={refreshForecast.isPending} onClick={() => refreshForecast.mutate()}>
          Refresh Forecast
        </button>
      </div>
    </Card>
  );
}

export function Monitoring() {
  const auth = useAuth();
  const userId = auth.session?.userId ?? 1;
  const [showAllReadings, setShowAllReadings] = useState(false);
  const logs = useQuery({ queryKey: ["logs", userId], queryFn: () => api.logs(userId) });
  const monitoring = useQuery({ queryKey: ["monitoring", userId], queryFn: () => api.latestMonitoring(userId) });
  const accuracy = useQuery({ queryKey: ["forecast-accuracy", userId], queryFn: () => api.getForecastAccuracy(userId) });
  const forecast = useQuery({ queryKey: ["forecast", userId], queryFn: () => api.getForecastLatest(userId).catch(() => null), retry: false });
  const latestLog = logs.data?.length ? logs.data[logs.data.length - 1] : undefined;
  const actualLogs = (logs.data ?? []).map((log) => ({
    timestamp: log.created_at ?? log.log_date,
    glucose_mmol: toMmol(log.glucose_level),
    is_fasting: log.is_fasting,
  }));
  const forecastStatus = forecast.data?.predicted_low_alert ? "Low forecast" : forecast.data?.predicted_high_alert ? "High forecast" : forecast.data?.trend_direction ? titleCase(forecast.data.trend_direction) : "-";
  const weekStatus = monitoring.data?.trend_label === "concerning" ? "Needs attention" : monitoring.data?.trend_label === "watch" ? "Watch closely" : monitoring.data?.trend_label ? "Looks steadier" : "-";
  const orderedReadings = [...(logs.data ?? [])].reverse();
  const visibleReadings = showAllReadings ? orderedReadings : orderedReadings.slice(0, 8);

  return (
    <div className="page monitoring-page">
      <PageHeader
        title="Monitoring"
        subtitle="Recent glucose readings, fasting context, and a next 4-hour forecast in one place."
        meta={forecast.data?.model_version ? `Forecast model: ${forecast.data.model_version}` : undefined}
      />
      {(logs.isError || monitoring.isError) && <ErrorState title="Monitoring data is unavailable" body="Glyco could not load one or more monitoring signals." />}

      <section className="monitoring-hero-panel">
        <div>
          <span>Bottom line</span>
          <h2>{forecastHeadline(forecast.data ?? null, monitoring.data)}</h2>
          <p>{forecastSummary(forecast.data ?? null, monitoring.data)}</p>
        </div>
        <div className="monitoring-hero-stats">
          <div><span>Latest glucose</span><strong>{latestLog ? `${latestLog.glucose_level} mg/dL` : "-"}</strong></div>
          <div><span>Forecast</span><strong>{forecastStatus}</strong></div>
          <div><span>Historical trend</span><strong>{weekStatus}</strong></div>
          <div><span>Evaluated forecasts</span><strong>{accuracy.data?.total_evaluations ?? 0}</strong></div>
          <div><span>Learning</span><strong>{forecast.data?.calibration_applied ? "Calibrated" : "Learning"}</strong></div>
        </div>
      </section>

      <div className="monitoring-main-grid forecast-primary-grid">
        {logs.isLoading ? <Card title="Glucose Forecast"><LoadingState label="Loading glucose history" /></Card> : <ForecastChart actualLogs={actualLogs} forecast={forecast.data ?? null} monitoring={monitoring.data} userId={userId} />}
      </div>

      <div className="monitoring-main-grid">
        <Card title={showAllReadings ? "All Glucose Readings" : "Recent Log History"} action={<Activity size={18} />}>
          {(logs.data ?? []).length ? (
            <div className="reading-history">
              <div className="reading-history-controls" role="group" aria-label="Reading history range">
                <button type="button" className={!showAllReadings ? "active" : ""} onClick={() => setShowAllReadings(false)}>Recent</button>
                <button type="button" className={showAllReadings ? "active" : ""} onClick={() => setShowAllReadings(true)}>All {orderedReadings.length}</button>
              </div>
              <div className={showAllReadings ? "compact-table reading-history-table all-readings" : "compact-table reading-history-table"}>
                {visibleReadings.map((log) => (
                  <div key={log.id}>
                    <span>{log.created_at ? new Date(log.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : log.log_date}</span>
                    <strong>{log.glucose_level} mg/dL</strong>
                    <span>{log.is_fasting ? "Fasting" : "Not fasting"}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : <EmptyState title="No log history" body="Use the Log data button to add the first monitoring record." />}
        </Card>

        <Card title="What to do next" action={<ClipboardList size={18} />}>
          <div className="forecast-action-panel">
            <section>
              <span>Main action</span>
              <strong>{forecast.data?.recommendation ?? "Add more readings to enable a forecast-based action."}</strong>
            </section>
            <section>
              <span>Next check</span>
              <p>{nextCheckText(forecast.data ?? null)}</p>
            </section>
            <div className="forecast-context-chips">
              <Badge>{latestLog ? `${latestLog.glucose_level} mg/dL` : "No reading"}</Badge>
              <Badge tone={trendBadgeTone(forecast.data?.trend_direction)}>{forecast.data?.trend_direction ?? "forecast pending"}</Badge>
              <Badge tone={forecast.data?.predicted_low_alert ? "danger" : forecast.data?.predicted_high_alert ? "warning" : "good"}>{forecast.data?.predicted_low_alert ? "Low alert" : forecast.data?.predicted_high_alert ? "High alert" : "No forecast alert"}</Badge>
              <Badge>{forecast.data?.forecast_quality ?? "needs_more_data"}</Badge>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
