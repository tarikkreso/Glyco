import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Bell, Plus, X } from "lucide-react";
import { api } from "../api/client";
import { Card, EmptyState, LoadingState } from "./ui";
import { LogNewDataForm } from "./LogNewDataForm";

export function GlobalQuickActions() {
  const [logOpen, setLogOpen] = useState(false);
  const [alertsOpen, setAlertsOpen] = useState(false);

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  const monitoring = useQuery({
    queryKey: ["monitoring"],
    queryFn: () => api.latestMonitoring(),
    enabled: alertsOpen,
  });

  const alerts = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api.alerts(),
    staleTime: 30_000,
    refetchInterval: 60_000,
  });

  const activeAlertCount = (alerts.data ?? []).length;
  const worstSeverity = (alerts.data ?? []).some((alert) => alert.severity === "danger")
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
          className="log-panel-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Alerts"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setAlertsOpen(false);
          }}
        >
          <div className="log-panel" onMouseDown={(event) => event.stopPropagation()}>
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
                  ) : (alerts.data ?? []).length ? (
                    <div className="alert-list">
                      {alerts.data?.slice(0, 6).map((alert) => (
                        <div
                          key={alert.id}
                          className={alert.severity === "danger" ? "danger" : "warning"}
                        >
                          <strong>{alert.title}</strong>
                          <span>
                            {alert.message} {alert.recommended_action}
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
              <LogNewDataForm onSuccess={() => setLogOpen(false)} />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
