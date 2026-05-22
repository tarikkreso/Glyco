import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, Plus, X } from "lucide-react";
import { useAuth } from "../auth/auth";
import { api } from "../api/client";
import { Card, EmptyState, LoadingState, useToast } from "./ui";
import { LogNewDataForm } from "./LogNewDataForm";

type SwipeGestureState = {
  alertId: number;
  pointerId: number;
  startX: number;
  startY: number;
  engaged: boolean;
};

export function GlobalQuickActions() {
  const [logOpen, setLogOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);

  const auth = useAuth();
  const userId = auth.session?.userId ?? 1;
  const queryClient = useQueryClient();
  const toast = useToast();

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
      toast({ tone: "success", title: "Alert dismissed" });
    },
    onError: (error) => {
      toast({
        tone: "error",
        title: "Could not dismiss alert",
        body: error instanceof Error ? error.message : "Please try again.",
      });
    },
  });

  const deleteAlert = useMutation({
    mutationFn: (alertId: number) => api.deleteAlert(alertId, userId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] });
      toast({ tone: "success", title: "Alert deleted" });
    },
    onError: (error) => {
      toast({
        tone: "error",
        title: "Could not delete alert",
        body: error instanceof Error ? error.message : "Please try again.",
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
          aria-label={activeAlertCount ? `View alerts (${activeAlertCount} active)` : "View alerts"}
        >
          <Bell size={18} aria-hidden="true" />
          <span className="log-fab-label">Alerts</span>
          {activeAlertCount ? <span className="fab-count" aria-hidden="true">{activeAlertCount}</span> : null}
        </button>

        <button
          type="button"
          className="log-fab primary"
          onClick={() => {
            setAlertsOpen(false);
            setLogOpen(true);
          }}
          aria-label="Log new health data"
        >
          <Plus size={18} aria-hidden="true" />
          <span className="log-fab-label">Log data</span>
        </button>
      </div>

      {alertsOpen && (
        <div
          className="log-panel-overlay alerts-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Alerts"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setAlertsOpen(false);
          }}
        >
          <div className="log-panel alerts-panel" onMouseDown={(event) => event.stopPropagation()}>
            <Card
              title="Alerts"
              action={
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setAlertsOpen(false)}
                  aria-label="Close alerts"
                >
                  <X size={18} aria-hidden="true" />
                </button>
              }
            >
              <p className="log-panel-meta">Anomaly notices and agent alerts based on your recent glucose logs.</p>

              <div className="alerts-panel-grid">
                <section className="alerts-panel-section">
                  <strong>Anomaly Notices</strong>
                  {monitoring.isLoading ? (
                    <LoadingState label="Loading anomaly flags" />
                  ) : monitoring.data?.anomaly_flags.length ? (
                    <div className="alert-list">
                      {monitoring.data.anomaly_flags.map((flag) => (
                        <div key={flag.label} className={flag.level}>
                          <strong>{flag.label}</strong>
                          <span>{flag.detail}</span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      title="No anomaly notices"
                      body="Recent glucose logs do not currently show a flagged anomaly pattern."
                    />
                  )}
                </section>

                <section className="alerts-panel-section">
                  <strong>Agent Alerts</strong>
                  {alerts.isLoading ? (
                    <LoadingState label="Loading proactive alerts" />
                  ) : activeAlerts.length ? (
                    <div className="alert-list">
                      {activeAlerts.map((alert) => (
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
                            <strong>{alert.title}</strong>
                            <div className="alert-item-actions">
                              <button
                                type="button"
                                onClick={() => acknowledgeAlert.mutate(alert.id)}
                                disabled={acknowledgeAlert.isPending || deleteAlert.isPending}
                                aria-label={`Dismiss alert: ${alert.title}`}
                              >
                                Dismiss
                              </button>
                              <button
                                type="button"
                                onClick={() => deleteAlert.mutate(alert.id)}
                                disabled={acknowledgeAlert.isPending || deleteAlert.isPending}
                                aria-label={`Delete alert: ${alert.title}`}
                              >
                                Delete
                              </button>
                            </div>
                          </div>
                          <span>
                            {alert.message}{alert.recommended_action ? ` ${alert.recommended_action}` : ""}
                          </span>
                        </div>
                      ))}
                    </div>
                  ) : (
                    <EmptyState
                      title="No active alerts"
                      body="After a new log, the agent creates an alert when the trend shifts into watch or concerning."
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
          aria-label="Log new data"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setLogOpen(false);
          }}
        >
          <div className="log-panel" onMouseDown={(event) => event.stopPropagation()}>
            <Card
              title="Log New Data"
              action={
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setLogOpen(false)}
                  aria-label="Close log form"
                >
                  <X size={18} aria-hidden="true" />
                </button>
              }
            >
              <p className="log-panel-meta">Quick glucose entry for {today}. Date and time are recorded automatically.</p>
              <LogNewDataForm userId={userId} onSuccess={() => setLogOpen(false)} />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
