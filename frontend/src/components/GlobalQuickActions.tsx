import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Plus, X } from "lucide-react";
import { useAuth } from "../auth/auth";
import { api } from "../api/client";
import { Card, EmptyState, LoadingState, useToast } from "./ui";
import { LogNewDataForm } from "./LogNewDataForm";
import { useI18n } from "../i18n";

type TranslationFn = (key: string) => string;

type SwipeGestureState = {
  alertId: number;
  pointerId: number;
  startX: number;
  startY: number;
  engaged: boolean;
};

const ALERT_TEXT_KEYS: Record<string, string> = {
  "Forecast glucose alert": "alerts.text.title.forecastGlucose",
  "Sustained elevated fasting glucose": "alerts.text.title.sustainedFasting",
  "Concerning trend detected": "alerts.text.title.concerningTrend",
  "Watch pattern detected": "alerts.text.title.watchPattern",
  "Review recent logs and generate a doctor summary if elevated readings continue.": "alerts.text.action.reviewLogs",
  "Review the generated doctor report and contact your clinician if this pattern persists.": "alerts.text.action.reviewDoctorReport",
  "Glucose is predicted to approach the lower boundary in the next few hours. Consider a small snack and check again soon. Contact your doctor if you feel unwell.": "alerts.text.forecast.low",
  "Glucose is trending upward and may exceed the upper boundary. Light activity (a 15-minute walk) often helps. Stay hydrated.": "alerts.text.forecast.highRising",
  "A high glucose reading is predicted. Review recent meals and activity. Consult your care plan.": "alerts.text.forecast.high",
  "Glucose is falling quickly. Keep a fast-acting carbohydrate nearby and monitor more frequently.": "alerts.text.forecast.falling",
  "Glucose looks stable. Keep up your current routine.": "alerts.text.forecast.stable",
  "Forecast generated. Continue monitoring as usual.": "alerts.text.forecast.default",
  "Repeated elevated glucose readings": "alerts.anomaly.repeatedElevated",
  "Rising glucose pattern": "alerts.anomaly.risingPattern",
  "High glucose variability": "alerts.anomaly.highVariability",
};

function translatedTrendLabel(t: TranslationFn, value: string) {
  const normalized = value.trim().toLowerCase();
  const key = `alerts.trend.${normalized}`;
  const translated = t(key);
  return translated === key ? value : translated;
}

function translateAlertText(text: string | undefined, t: TranslationFn) {
  if (!text) return "";
  const exactKey = ALERT_TEXT_KEYS[text];
  if (exactKey) return t(exactKey);

  const monitoringMatch = text.match(/^Glyco detected a (watch|concerning) glucose monitoring state\.$/i);
  if (monitoringMatch) {
    return t("alerts.text.message.monitoringState").replace("%s", translatedTrendLabel(t, monitoringMatch[1]));
  }

  const sustainedMatch = text.match(
    /^Glyco detected that the last 3 fasting glucose readings were above 7\.0 mmol\/L and generated a doctor report\. Forecast trend: ([^.]+)\.$/i,
  );
  if (sustainedMatch) {
    return t("alerts.text.message.sustainedFasting").replace("%s", translatedTrendLabel(t, sustainedMatch[1]));
  }

  return text;
}

function translateAnomalyText(text: string | undefined, t: TranslationFn) {
  if (!text) return "";
  const exactKey = ALERT_TEXT_KEYS[text];
  if (exactKey) return t(exactKey);

  const repeatedMatch = text.match(/^(\d+) recent readings were above the fasting or post-meal threshold for their log type\.$/i);
  if (repeatedMatch) return t("alerts.anomaly.detail.repeatedElevated").replace("%d", repeatedMatch[1]);

  const risingMatch = text.match(/^Recent glucose is rising about ([\d.-]+) mg\/dL per log\.$/i);
  if (risingMatch) return t("alerts.anomaly.detail.risingPattern").replace("%s", risingMatch[1]);

  const variabilityMatch = text.match(/^Recent variability is ([\d.-]+) mg\/dL\.$/i);
  if (variabilityMatch) return t("alerts.anomaly.detail.highVariability").replace("%s", variabilityMatch[1]);

  return text;
}

export function GlobalQuickActions() {
  const [logOpen, setLogOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);

  const auth = useAuth();
  const userId = auth.session?.userId ?? 1;
  const queryClient = useQueryClient();
  const toast = useToast();
  const { t } = useI18n();

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  const monitoring = useQuery({
    queryKey: ["monitoring"],
    queryFn: () => api.latestMonitoring(userId),
    enabled: alertsOpen,
  });

  const alerts = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api.alerts(userId),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const activeAlerts = useMemo(() => {
    const rows = alerts.data ?? [];
    const seen = new Set<string>();
    const unique = [] as typeof rows;
    for (const row of rows) {
      if (row.acknowledged_at) continue;
      const signature = `${row.title}||${row.severity}`;
      if (seen.has(signature)) continue;
      seen.add(signature);
      unique.push(row);
    }
    return unique;
  }, [alerts.data]);

  const swipeRef = useRef<SwipeGestureState | null>(null);
  const [draggingAlertId, setDraggingAlertId] = useState<number | null>(null);
  const [swipeOffsets, setSwipeOffsets] = useState<Record<number, number>>({});

  const acknowledgeAlert = useMutation({
    mutationFn: (alertId: number) => api.acknowledgeAlert(alertId, userId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
      toast({ tone: "success", title: t("alerts.toastDismissed") });
    },
    onError: (error) => {
      toast({
        tone: "error",
        title: t("alerts.toastDismissError"),
        body: error instanceof Error ? error.message : t("alerts.toastTryAgain"),
      });
    },
  });

  const deleteAlert = useMutation({
    mutationFn: (alertId: number) => api.deleteAlert(alertId, userId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
      toast({ tone: "success", title: t("alerts.toastDeleted") });
    },
    onError: (error) => {
      toast({
        tone: "error",
        title: t("alerts.toastDeleteError"),
        body: error instanceof Error ? error.message : t("alerts.toastTryAgain"),
      });
    },
  });

  const swipeThresholdPx = 90;
  const swipeMaxPx = 140;

  const onAlertPointerDown = (alertId: number, event: React.PointerEvent<HTMLDivElement>) => {
    if (event.pointerType !== "touch") return;
    event.currentTarget.setPointerCapture(event.pointerId);
    swipeRef.current = {
      alertId,
      pointerId: event.pointerId,
      startX: event.clientX,
      startY: event.clientY,
      engaged: false,
    };
  };

  const onAlertPointerMove = (alertId: number, event: React.PointerEvent<HTMLDivElement>) => {
    const state = swipeRef.current;
    if (!state || state.alertId !== alertId || state.pointerId !== event.pointerId) return;
    if (event.pointerType !== "touch") return;

    const dx = event.clientX - state.startX;
    const dy = event.clientY - state.startY;

    if (!state.engaged) {
      if (Math.abs(dx) < 8) return;
      if (Math.abs(dx) <= Math.abs(dy)) return;
      state.engaged = true;
      swipeRef.current = state;
      setDraggingAlertId(alertId);
    }

    if (!state.engaged) return;
    event.preventDefault();

    const clamped = Math.max(-swipeMaxPx, Math.min(0, dx));
    setSwipeOffsets((prev) => ({ ...prev, [alertId]: clamped }));
  };

  const finishSwipe = (alertId: number) => {
    setDraggingAlertId((current) => (current === alertId ? null : current));
    setSwipeOffsets((prev) => ({ ...prev, [alertId]: 0 }));
    swipeRef.current = null;
  };

  const onAlertPointerEnd = (alertId: number, event: React.PointerEvent<HTMLDivElement>) => {
    const state = swipeRef.current;
    if (!state || state.alertId !== alertId || state.pointerId !== event.pointerId) return;

    const offset = swipeOffsets[alertId] ?? 0;
    const shouldDelete = offset <= -swipeThresholdPx;
    finishSwipe(alertId);
    if (shouldDelete) deleteAlert.mutate(alertId);
  };

  const activeAlertCount = activeAlerts.length;
  const worstSeverity = activeAlerts.some((alert) => alert.severity === "danger")
    ? "danger"
    : activeAlertCount
      ? "warning"
      : "none";
  const alertsButtonTone = worstSeverity === "danger" ? "danger" : worstSeverity === "warning" ? "warning" : "none";

  useEffect(() => {
    if (!logOpen && !alertsOpen) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setLogOpen(false);
        setAlertsOpen(false);
      }
    };

    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.documentElement.style.overflow = previousOverflow;
    };
  }, [alertsOpen, logOpen]);

  return (
    <>
      <div className="fab-cluster">
        <button
          type="button"
          className={`log-fab alert secondary ${alertsButtonTone !== "none" ? `has-alerts ${alertsButtonTone}` : ""}`}
          onClick={() => {
            setLogOpen(false);
            setAlertsOpen(true);
          }}
          aria-label={activeAlertCount ? t("alerts.viewWithCount").replace("%d", String(activeAlertCount)) : t("alerts.view")}
        >
          <Bell size={18} aria-hidden="true" />
          <span className="log-fab-label">{t("log.alerts")}</span>
          {activeAlertCount ? <span className="fab-count" aria-hidden="true">{activeAlertCount}</span> : null}
        </button>

        <button
          type="button"
          className="log-fab primary"
          onClick={() => {
            setAlertsOpen(false);
            setLogOpen(true);
          }}
          aria-label={t("alerts.logNewData")}
        >
          <Plus size={18} aria-hidden="true" />
          <span className="log-fab-label">{t("log.fab")}</span>
        </button>
      </div>

      {alertsOpen && (
        <div
          className="log-panel-overlay alerts-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={t("alerts.title")}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setAlertsOpen(false);
          }}
        >
          <div className="log-panel alerts-panel" onMouseDown={(event) => event.stopPropagation()}>
            <Card
              title={t("log.alerts")}
              action={
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setAlertsOpen(false)}
                  aria-label={t("alerts.close")}
                >
                  <X size={18} aria-hidden="true" />
                </button>
              }
            >
              <p className="log-panel-meta">{t("alerts.anomalyNotice")}</p>

              <div className="alerts-panel-grid">
                <section className="alerts-panel-section">
                  <strong>{t("alerts.anomalyTitle")}</strong>
                  {monitoring.isLoading ? (
                    <LoadingState label={t("alerts.loadingAnomalies")} />
                  ) : monitoring.data?.anomaly_flags.length ? (
                    <div className="alert-list">
                      {monitoring.data.anomaly_flags.map((flag) => (
                        <div key={flag.label} className={flag.level}>
                          <strong>{translateAnomalyText(flag.label, t)}</strong>
                          <span>{translateAnomalyText(flag.detail, t)}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      title={t("alerts.noAnomalies")}
                      body={t("alerts.noAnomaliesBody")}
                    />
                  )}
                </section>

                <section className="alerts-panel-section">
                  <strong>{t("alerts.agentAlertsTitle")}</strong>
                  {alerts.isLoading ? (
                    <LoadingState label={t("alerts.loadingProactive")} />
                  ) : activeAlerts.length ? (
                    <div className="alert-list">
                      {activeAlerts.map((alert) => {
                        const title = translateAlertText(alert.title, t);
                        const message = translateAlertText(alert.message, t);
                        const recommendedAction = translateAlertText(alert.recommended_action, t);

                        return (
                          <div
                            key={alert.id}
                            className={`${alert.severity === "danger" ? "danger" : "warning"} swipeable-alert${draggingAlertId === alert.id ? " dragging" : ""}`}
                            style={
                              swipeOffsets[alert.id]
                                ? { transform: `translateX(${swipeOffsets[alert.id]}px)` }
                                : undefined
                            }
                            onPointerDown={(event) => onAlertPointerDown(alert.id, event)}
                            onPointerMove={(event) => onAlertPointerMove(alert.id, event)}
                            onPointerUp={(event) => onAlertPointerEnd(alert.id, event)}
                            onPointerCancel={(event) => onAlertPointerEnd(alert.id, event)}
                          >
                            <div className="alert-item-head">
                              <strong>{title}</strong>
                              <div className="alert-item-actions">
                                <button
                                  type="button"
                                  onClick={() => acknowledgeAlert.mutate(alert.id)}
                                  disabled={acknowledgeAlert.isPending || deleteAlert.isPending}
                                  aria-label={`${t("alerts.dismiss")}: ${title}`}
                                >
                                  {t("alerts.dismiss")}
                                </button>
                                <button
                                  type="button"
                                  onClick={() => deleteAlert.mutate(alert.id)}
                                  disabled={acknowledgeAlert.isPending || deleteAlert.isPending}
                                  aria-label={`${t("alerts.delete")}: ${title}`}
                                >
                                  {t("alerts.delete")}
                                </button>
                              </div>
                            </div>
                            <span>
                              {message}{recommendedAction ? ` ${recommendedAction}` : ""}
                            </span>
                          </div>
                        );
                      })}
                    </div>
                  ) : (
                    <EmptyState
                      title={t("alerts.noActiveTitle")}
                      body={t("alerts.noActiveBody")}
                    />
                  )}
                </section>
              </div>
            </Card>
          </div>
        </div>
      )}

      {logOpen && (
        <div
          className="log-panel-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={t("log.newDataDialog")}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setLogOpen(false);
          }}
        >
          <div className="log-panel" onMouseDown={(event) => event.stopPropagation()}>
            <Card
              title={t("log.title")}
              action={
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setLogOpen(false)}
                  aria-label={t("log.closeForm")}
                >
                  <X size={18} aria-hidden="true" />
                </button>
              }
            >
              <p className="log-panel-meta">{t("log.meta").replace("today", today)}</p>
              <LogNewDataForm userId={userId} onSuccess={() => setLogOpen(false)} />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
