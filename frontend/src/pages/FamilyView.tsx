import { useQuery } from "@tanstack/react-query";
import { Activity, AlertTriangle, CheckSquare, Clock, Droplets, Heart, ShieldAlert, TrendingUp, Users } from "lucide-react";
import { api } from "../api/client";
import { Card, LoadingState, PageHeader } from "../components/ui";

function RiskBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "var(--error)" : pct >= 40 ? "#d97706" : "var(--primary)";
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em", fontWeight: 700, color: "var(--muted)" }}>Diabetes risk score</span>
        <strong style={{ font: "700 28px/1 Manrope, Inter, sans-serif", color }}>{pct}%</strong>
      </div>
      <div style={{ height: 10, borderRadius: 999, background: "var(--surface-low)", border: "1px solid var(--outline)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 999, transition: "width .6s cubic-bezier(.2,.9,.3,1)" }} />
      </div>
      <span style={{ fontSize: 12, color: "var(--muted)" }}>High risk — based on BMI, age, blood pressure and cholesterol profile</span>
    </div>
  );
}

function AlertItem({ flag }: { flag: any }) {
  const isDanger = flag.level === "danger";
  return (
    <div style={{
      display: "grid", gap: 4, padding: "12px 14px", borderRadius: 8,
      background: isDanger ? "var(--error-bg)" : "#fff8ed",
      border: `1px solid ${isDanger ? "#f0aaa4" : "#f6c89a"}`,
    }}>
      <strong style={{ fontSize: 13, color: isDanger ? "var(--error)" : "#92400e" }}>{flag.label}</strong>
      <span style={{ fontSize: 12, color: "var(--muted)" }}>{flag.detail}</span>
    </div>
  );
}

export function FamilyView() {
  const share = useQuery({ queryKey: ["family-share"], queryFn: () => api.familyShare() });
  const data = share.data as any;

  const userName = data?.user?.full_name ?? "Sarah";
  const monitoring = data?.monitoring;
  const risk = data?.risk;
  const shareInfo = data?.share;
  const alerts: any[] = monitoring?.anomaly_flags ?? [];
  const summary = monitoring?.summary ?? {};
  const isStable = monitoring?.trend_label !== "concerning";

  return (
    <div className="page">
      <PageHeader
        title="Family Support View"
        subtitle={`Health summary shared with ${shareInfo?.shared_with_name ?? "Care Circle"} · ${shareInfo?.relationship ?? "Family"}`}
        meta="Last updated: Today, 09:42 AM"
      />

      {share.isPending && <LoadingState label="Loading family view…" />}

      {!share.isPending && (
        <div className="family-grid">
          <div className="family-main">

            {/* Status banner */}
            <div style={{
              borderRadius: 14, padding: "20px 24px",
              display: "flex", alignItems: "center", gap: 18,
              background: isStable ? "var(--primary-soft)" : "var(--error-bg)",
              border: `1px solid ${isStable ? "var(--primary)" : "#f0aaa4"}`,
            }}>
              <div style={{
                width: 52, height: 52, borderRadius: "50%", flexShrink: 0,
                background: isStable ? "var(--primary)" : "var(--error)",
                display: "grid", placeItems: "center",
              }}>
                <Heart size={24} color="#fff" />
              </div>
              <div>
                <h2 style={{ margin: 0, fontSize: 20, color: isStable ? "var(--primary)" : "var(--error)" }}>
                  {isStable ? "Stable & Trending Well" : "Attention Needed"}
                </h2>
                <p style={{ margin: "4px 0 0", color: "var(--muted)" }}>
                  {monitoring?.summary?.message ?? `${userName}'s recent readings need monitoring. See alerts below.`}
                </p>
              </div>
            </div>

            {/* Monitoring summary stats */}
            {summary && (
              <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
                {[
                  { label: "Avg fasting glucose", value: summary.avg_fasting_glucose, unit: "mg/dL", warn: Number(summary.avg_fasting_glucose) > 125 },
                  { label: "Glucose variability", value: summary.variability, unit: "mg/dL", warn: Number(summary.variability) > 20 },
                  { label: "Logs analyzed", value: summary.logs_analyzed, unit: "entries", warn: false },
                ].map(({ label, value, unit, warn }) => (
                  <div key={label} style={{
                    background: warn ? "var(--error-bg)" : "var(--surface-low)",
                    border: `1px solid ${warn ? "#f0aaa4" : "var(--outline)"}`,
                    borderRadius: 10, padding: "14px 16px", display: "grid", gap: 4,
                  }}>
                    <span style={{ color: "var(--muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em", fontWeight: 700 }}>{label}</span>
                    <div style={{ display: "flex", alignItems: "baseline", gap: 6 }}>
                      <strong style={{ font: "700 26px/1 Manrope, Inter, sans-serif", color: warn ? "var(--error)" : "var(--primary)" }}>{value}</strong>
                      <span style={{ color: "var(--muted)", fontSize: 13 }}>{unit}</span>
                      {warn && <TrendingUp size={14} color="var(--error)" />}
                    </div>
                  </div>
                ))}
              </div>
            )}

            {/* Risk score */}
            {risk && (
              <Card title="Risk Profile">
                <div style={{ display: "grid", gap: 18 }}>
                  <RiskBar value={risk.risk_probability} />
                  <div style={{ display: "grid", gap: 8 }}>
                    <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em", fontWeight: 700, color: "var(--muted)" }}>Key risk factors</span>
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                      {risk.top_factors?.map((f: any) => (
                        <span key={f.label} style={{
                          border: "1px solid var(--outline)", borderRadius: 999,
                          padding: "5px 12px", fontSize: 12, fontWeight: 700,
                          background: "var(--surface-low)", color: "var(--muted)",
                        }}>{f.label}</span>
                      ))}
                    </div>
                  </div>
                  <p style={{ margin: 0, fontSize: 13, color: "var(--muted)", borderTop: "1px solid var(--outline)", paddingTop: 12 }}>
                    {risk.explanation}
                  </p>
                </div>
              </Card>
            )}

          </div>

          <div className="family-side">

            {/* Alerts */}
            <Card
              title="Active Alerts"
              action={<AlertTriangle size={16} color={alerts.length ? "var(--error)" : "var(--muted)"} />}
            >
              {alerts.length > 0 ? (
                <div style={{ display: "grid", gap: 8 }}>
                  {alerts.map((flag: any) => <AlertItem key={flag.label} flag={flag} />)}
                </div>
              ) : (
                <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--primary)", background: "var(--primary-soft)", borderRadius: 8, padding: "12px 14px" }}>
                  <Activity size={16} />
                  <span style={{ fontSize: 13, fontWeight: 700 }}>No active alerts</span>
                </div>
              )}
            </Card>

            {/* Recommended actions from monitoring */}
            {monitoring?.recommended_actions?.length > 0 && (
              <Card title="Recommended Actions">
                <div style={{ display: "grid", gap: 10 }}>
                  {monitoring.recommended_actions.map((action: string, i: number) => (
                    <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start", paddingBottom: 10, borderBottom: i < monitoring.recommended_actions.length - 1 ? "1px solid var(--outline)" : "none" }}>
                      <ShieldAlert size={15} color="var(--primary)" style={{ marginTop: 2, flexShrink: 0 }} />
                      <span style={{ fontSize: 13, color: "var(--text)" }}>{action}</span>
                    </div>
                  ))}
                </div>
              </Card>
            )}

            {/* How to help */}
            <Card title="How You Can Help Today">
              <ul className="help-list">
                <li>
                  <CheckSquare size={16} color="var(--primary)" />
                  <div>
                    <strong style={{ fontSize: 13, color: "var(--text)" }}>Remind about post-lunch walk</strong>
                    <span>A 15-minute walk helps stabilize afternoon glucose levels.</span>
                  </div>
                </li>
                <li>
                  <Clock size={16} color="var(--primary)" />
                  <div>
                    <strong style={{ fontSize: 13, color: "var(--text)" }}>Verify evening medication</strong>
                    <span>Check pillbox around 8:00 PM.</span>
                  </div>
                </li>
                <li>
                  <Droplets size={16} color="var(--primary)" />
                  <div>
                    <strong style={{ fontSize: 13, color: "var(--text)" }}>Encourage hydration</strong>
                    <span>Aim for 8 glasses of water throughout the day.</span>
                  </div>
                </li>
                <li>
                  <Users size={16} color="var(--primary)" />
                  <div>
                    <strong style={{ fontSize: 13, color: "var(--text)" }}>Endocrinologist checkup</strong>
                    <span>Upcoming appointment — confirm date and arrange transport if needed.</span>
                  </div>
                </li>
              </ul>
            </Card>

          </div>
        </div>
      )}
    </div>
  );
}