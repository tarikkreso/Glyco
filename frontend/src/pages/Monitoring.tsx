import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, ClipboardList } from "lucide-react";
import { Area, ComposedChart, Legend, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api, type ForecastAccuracy, type GlucoseForecast, type MonitoringAssessment } from "../api/client";
import { useAuth } from "../auth/auth";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";
import { useI18n } from "../i18n";
import { formatGlucoseFromMgdl, formatGlucoseFromMmol, useGlucoseUnit } from "../utils/glucoseUnits";

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

function trendLabel(value: string | undefined, t: (key: string) => string) {
  if (value === "rising") return t("monitoring.trend.rising");
  if (value === "falling") return t("monitoring.trend.falling");
  if (value === "stable") return t("monitoring.trend.stable");
  if (value === "watch") return t("monitoring.trend.watch");
  if (value === "concerning") return t("monitoring.trend.concerning");
  return value ? titleCase(value) : "-";
}

function forecastQualityValue(value: string | null | undefined, t: (key: string) => string) {
  if (value === "learning") return t("monitoring.learning");
  if (value === "calibrated") return t("monitoring.personalized");
  if (value === "personalization_off") return t("monitoring.personalizationOff");
  if (value === "needs_more_data" || !value) return t("monitoring.needsMoreData");
  return value.replace(/_/g, " ");
}

function translateForecastRecommendation(text: string | undefined, t: (key: string) => string) {
  if (!text) return t("monitoring.defaultAction");
  const keyByText: Record<string, string> = {
    "Glucose is predicted to approach the lower boundary in the next few hours. Consider a small snack and check again soon. Contact your doctor if you feel unwell.": "monitoring.recommendation.low",
    "Glucose is trending upward and may exceed the upper boundary. Light activity (a 15-minute walk) often helps. Stay hydrated.": "monitoring.recommendation.highRising",
    "A high glucose reading is predicted. Review recent meals and activity. Consult your care plan.": "monitoring.recommendation.high",
    "Glucose is falling quickly. Keep a fast-acting carbohydrate nearby and monitor more frequently.": "monitoring.recommendation.falling",
    "Glucose looks stable. Keep up your current routine.": "monitoring.recommendation.stable",
    "Forecast generated. Continue monitoring as usual.": "monitoring.recommendation.default",
  };
  return keyByText[text] ? t(keyByText[text]) : text;
}

function translateMonitoringSummary(text: unknown, t: (key: string) => string) {
  if (typeof text !== "string") return t("monitoring.noForecastPrompt");
  if (text === "More readings are needed.") return t("monitoring.moreReadingsNeeded");
  const match = text.match(/^Recent monitoring state is ([^.]+)\./);
  if (match) return t("monitoring.stateSummary").replace("%s", trendLabel(match[1], t));
  return text;
}

function formatForecastTick(value: number, range: 8 | 24 | 48 | "all") {
  const date = new Date(value);
  if (range === 8 || range === 24) {
    return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }
  if (range === 48) {
    return date.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit" });
  }
  return date.toLocaleDateString([], { month: "short", day: "numeric" });
}

function forecastHeadline(forecast: GlucoseForecast | null, monitoring: MonitoringAssessment | undefined, t: (key: string) => string) {
  if (forecast?.predicted_low_alert) return t("monitoring.forecastLow");
  if (forecast?.predicted_high_alert) return t("monitoring.forecastHigh");
  if (forecast?.trend_direction === "rising") return t("monitoring.riseSoon");
  if (forecast?.trend_direction === "falling") return t("monitoring.fallSoon");
  if (forecast?.trend_direction === "stable") return t("monitoring.stableForecast");
  if (monitoring?.trend_label === "concerning") return t("monitoring.weekAttention");
  if (monitoring?.trend_label === "watch") return t("monitoring.watchReadings");
  return t("monitoring.patternSteady");
}

function forecastSummary(forecast: GlucoseForecast | null, monitoring: MonitoringAssessment | undefined, t: (key: string) => string, unit: "mmol" | "mgdl") {
  if (forecast) {
    if (forecast.predicted_low_alert || forecast.predicted_high_alert) return translateForecastRecommendation(forecast.recommendation, t);
    return `${t("monitoring.forecast")} ${trendLabel(forecast.trend_direction, t)}: +60 min ${formatGlucoseFromMmol(forecast.predictions["60"], unit)}. ${t("monitoring.forecastsEstimate")}`;
  }
  return translateMonitoringSummary(monitoring?.summary.message, t);
}

function nextCheckText(forecast: GlucoseForecast | null, t: (key: string) => string) {
  if (!forecast) return t("monitoring.defaultAction");
  if (forecast.predicted_low_alert || forecast.predicted_high_alert) return t("monitoring.checkSoon");
  if (forecast.trend_direction === "rising" || forecast.trend_direction === "falling") return t("monitoring.checkWithinHour");
  return t("monitoring.usualMonitoring");
}

function qualityLabel(forecast: GlucoseForecast | null, accuracy: ForecastAccuracy | undefined, t: (key: string) => string) {
  if (!forecast) return t("monitoring.needsMoreData");
  if (forecast.personalization_enabled === false || accuracy?.personalization_enabled === false) return t("monitoring.personalizationOff");
  if (forecast.calibration_applied) return t("monitoring.personalized");
  if ((accuracy?.total_evaluations ?? 0) > 0) return t("monitoring.learning");
  return t("monitoring.needsMoreData");
}

function ForecastActualDot(props: { cx?: number; cy?: number; payload?: { is_fasting?: boolean } }) {
  const { cx, cy, payload } = props;
  if (typeof cx !== "number" || typeof cy !== "number") return null;
  return <circle cx={cx} cy={cy} r={4} fill={payload?.is_fasting ? "#154539" : "#c2572b"} stroke="#fff" strokeWidth={2} />;
}

function ForecastTooltip({ active, label, payload }: { active?: boolean; label?: number; payload?: Array<{ dataKey?: string; value?: number; payload?: { is_fasting?: boolean; actual?: number; forecast?: number; forecastBand?: [number, number] } }> }) {
  const { t } = useI18n();
  const { unit } = useGlucoseUnit();
  if (!active || !payload?.length) return null;
  const point = payload.find((item) => item.payload?.actual != null || item.payload?.forecast != null)?.payload;
  if (!point) return null;
  return (
    <div className="forecast-tooltip">
      <strong>{label ? new Date(Number(label)).toLocaleString() : t("monitoring.recent")}</strong>
      {point.actual != null && <span>{t("monitoring.actual")}: {formatGlucoseFromMmol(point.actual, unit)} ({point.is_fasting ? t("log.fasting") : t("log.notFasting")})</span>}
      {point.forecast != null && <span>{t("monitoring.forecast")}: {formatGlucoseFromMmol(point.forecast, unit)}</span>}
      {point.forecastBand && <span>{t("monitoring.confidence")}: {formatGlucoseFromMmol(point.forecastBand[0], unit)}-{formatGlucoseFromMmol(point.forecastBand[1], unit)}</span>}
    </div>
  );
}

function ForecastChart({ actualLogs, forecast, monitoring, accuracy, userId }: { actualLogs: Array<{ timestamp: string; glucose_mmol: number; is_fasting: boolean }>; forecast: GlucoseForecast | null; monitoring?: MonitoringAssessment; accuracy?: ForecastAccuracy; userId: number }) {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const { unit } = useGlucoseUnit();
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
  const badgeTrendLabel = trendLabel(forecast?.trend_direction, t);

  return (
    <Card title={t("monitoring.forecastCard")} action={forecast ? <Badge tone={trendBadgeTone(forecast.trend_direction)}>{badgeTrendLabel}</Badge> : <Badge>{t("monitoring.forecast")}</Badge>}>
      <div className="forecast-status">
        {!forecast && <p>{t("monitoring.noForecastPrompt")}</p>}
        {forecast && <p>{forecast.used_fallback ? t("monitoring.fallbackForecast") : t("monitoring.modelForecast")} - {forecast.model_version}</p>}

        <div className="forecast-range-controls" role="group" aria-label={t("monitoring.historyRangeAria")}>
          {([8, 24, 48, "all"] as const).map((range) => (
            <button key={range} type="button" className={historyHours === range ? "active" : ""} onClick={() => setHistoryHours(range)}>
              {range === "all" ? t("monitoring.all") : `${range}h`}
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
              tickFormatter={(value) => formatForecastTick(Number(value), historyHours)}
              type="number"
            />
            <YAxis domain={[2, 16]} tick={{ fontSize: 11 }} />
            <Tooltip content={<ForecastTooltip />} />
            <Legend payload={[
              { value: t("monitoring.actual"), type: "line", color: "#154539" },
              { value: t("monitoring.forecast"), type: "line", color: "#4f46e5" },
              { value: t("monitoring.targetRange"), type: "rect", color: "#d9f4df" },
            ]} />
            <ReferenceArea y1={2} y2={3.9} fill="#dc2626" fillOpacity={0.08} />
            <ReferenceArea y1={10} y2={16} fill="#f97316" fillOpacity={0.08} />
            <ReferenceLine x={Date.now()} stroke="#6b7280" strokeDasharray="4 4" />
            <Area dataKey="forecastBand" stroke="none" fill="#4f46e5" fillOpacity={0.15} connectNulls />
            <Line name={t("monitoring.actual")} dataKey="actual" stroke="#154539" strokeWidth={3} dot={<ForecastActualDot />} connectNulls={false} />
            <Line name={t("monitoring.forecast")} dataKey="forecast" stroke="#4f46e5" strokeWidth={3} strokeDasharray="7 5" dot={{ r: 4 }} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
      <div className="forecast-actions">
        <div className="forecast-model-evidence">
          <span>{t("monitoring.forecastModel")}: {forecast?.model_version ?? t("monitoring.waitingForForecast")}</span>
          <span>{t("monitoring.trendSupport")}: {monitoring?.model_version ?? t("monitoring.loadingTrendModel")}</span>
        </div>
        <button type="button" className="secondary" disabled={refreshForecast.isPending} onClick={() => refreshForecast.mutate()}>
          {t("monitoring.refresh")}
        </button>
      </div>
      <div className="forecast-quality-panel">
        <div>
          <span>{t("monitoring.forecastQuality")}</span>
          <strong>{qualityLabel(forecast, accuracy, t)}</strong>
          <small>{accuracy?.total_evaluations ?? 0} {t("monitoring.evaluated")}</small>
        </div>
        {(["60", "120", "180", "240"] as const).map((horizon) => {
          const row = accuracy?.per_horizon?.[horizon];
          const personalMae = forecast?.personal_mae_per_horizon?.[horizon];
          return (
            <div key={horizon}>
              <span>{horizon} min MAE</span>
              <strong>{row?.count ? formatGlucoseFromMmol(row.mae, unit) : personalMae ? formatGlucoseFromMmol(personalMae, unit) : "-"}</strong>
              <small>{row?.count ?? 0} {t("monitoring.checked")}</small>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

export function Monitoring() {
  const auth = useAuth();
  const { t } = useI18n();
  const { unit } = useGlucoseUnit();
  const userId = auth.session?.userId ?? 1;
  const [readingsPage, setReadingsPage] = useState(0);
  const logs = useQuery({ queryKey: ["logs", userId], queryFn: () => api.logs(userId) });
  const monitoring = useQuery({ queryKey: ["monitoring", userId], queryFn: () => api.latestMonitoring(userId) });
  const accuracy = useQuery({ queryKey: ["forecast-accuracy", userId], queryFn: () => api.getForecastAccuracy(userId) });
  const forecast = useQuery({ queryKey: ["forecast", userId], queryFn: () => api.getForecastLatest(userId).catch(() => null), retry: false });
  const latestLog = logs.data?.length ? logs.data[logs.data.length - 1] : undefined;
  const actualLogs = (logs.data ?? []).map((log) => ({
    timestamp: log.reading_time ?? log.created_at ?? log.log_date,
    glucose_mmol: toMmol(log.glucose_level),
    is_fasting: log.is_fasting,
  }));
  const orderedReadings = [...(logs.data ?? [])].reverse();
  const readingsPerPage = 8;
  const readingsPageCount = Math.max(1, Math.ceil(orderedReadings.length / readingsPerPage));
  const safeReadingsPage = Math.min(readingsPage, readingsPageCount - 1);
  const visibleReadings = orderedReadings.slice(safeReadingsPage * readingsPerPage, safeReadingsPage * readingsPerPage + readingsPerPage);

  useEffect(() => {
    if (readingsPage > readingsPageCount - 1) setReadingsPage(Math.max(0, readingsPageCount - 1));
  }, [readingsPage, readingsPageCount]);

  return (
    <div className="page monitoring-page">
      <PageHeader
        title={t("monitoring.title")}
        subtitle={t("monitoring.subtitle")}
        meta={forecast.data?.model_version ? `${t("monitoring.forecastModel")}: ${forecast.data.model_version}` : undefined}
      />
      {(logs.isError || monitoring.isError) && <ErrorState title={t("monitoring.errorTitle")} body={t("monitoring.errorBody")} />}

      <section className="monitoring-hero-panel">
        <div>
          <span>{t("monitoring.bottomLine")}</span>
          <h2>{forecastHeadline(forecast.data ?? null, monitoring.data, t)}</h2>
          <p>{forecastSummary(forecast.data ?? null, monitoring.data, t, unit)}</p>
        </div>
      </section>

      <div className="monitoring-main-grid forecast-primary-grid">
        {logs.isLoading ? <Card title={t("monitoring.forecastCard")}><LoadingState label={t("monitoring.loadingHistory")} /></Card> : <ForecastChart actualLogs={actualLogs} forecast={forecast.data ?? null} monitoring={monitoring.data} accuracy={accuracy.data} userId={userId} />}
      </div>

      <div className="monitoring-main-grid">
        <Card title={t("monitoring.recentHistory")} action={<Activity size={18} />}>
          {(logs.data ?? []).length ? (
            <div className="reading-history">
              <div className="reading-history-pager">
                <span>{t("monitoring.page")} {safeReadingsPage + 1} / {readingsPageCount}</span>
                <div className="reading-history-controls" role="group" aria-label={t("monitoring.readingPaginationAria")}>
                  <button type="button" disabled={safeReadingsPage === 0} onClick={() => setReadingsPage((page) => Math.max(0, page - 1))}>{t("common.previous")}</button>
                  <button type="button" disabled={safeReadingsPage >= readingsPageCount - 1} onClick={() => setReadingsPage((page) => Math.min(readingsPageCount - 1, page + 1))}>{t("common.next")}</button>
                </div>
              </div>
              <div className="compact-table reading-history-table">
                {visibleReadings.map((log) => (
                  <div key={log.id}>
                    <span>{log.reading_time || log.created_at ? new Date(log.reading_time ?? log.created_at ?? "").toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }) : log.log_date}</span>
                    <strong>{formatGlucoseFromMgdl(log.glucose_level, unit)}</strong>
                    <span>{log.is_fasting ? t("log.fasting") : t("log.notFasting")}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : <EmptyState title={t("monitoring.noLogHistory")} body={t("monitoring.noLogBody")} />}
        </Card>

        <Card title={t("monitoring.whatNext")} action={<ClipboardList size={18} />}>
          <div className="forecast-action-panel">
            <section>
              <span>{t("monitoring.mainAction")}</span>
              <strong>{translateForecastRecommendation(forecast.data?.recommendation, t)}</strong>
            </section>
            <section>
              <span>{t("monitoring.nextCheck")}</span>
              <p>{nextCheckText(forecast.data ?? null, t)}</p>
            </section>
            <div className="forecast-context-chips">
              <Badge>{latestLog ? formatGlucoseFromMgdl(latestLog.glucose_level, unit) : t("monitoring.noReading")}</Badge>
              <Badge tone={trendBadgeTone(forecast.data?.trend_direction)}>{forecast.data?.trend_direction ? trendLabel(forecast.data.trend_direction, t) : t("monitoring.forecastPending")}</Badge>
              <Badge tone={forecast.data?.predicted_low_alert ? "danger" : forecast.data?.predicted_high_alert ? "warning" : "good"}>{forecast.data?.predicted_low_alert ? t("monitoring.lowAlert") : forecast.data?.predicted_high_alert ? t("monitoring.highAlert") : t("monitoring.noAlert")}</Badge>
              <Badge>{forecastQualityValue(forecast.data?.forecast_quality, t)}</Badge>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
