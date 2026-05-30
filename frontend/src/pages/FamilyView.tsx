import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useMemo, useRef } from "react";
import { useParams } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  CheckSquare,
  Clock,
  Droplets,
  Heart,
  ShieldAlert,
  TrendingUp,
  Users,
  Copy,
  Mail,
  Check,
  ExternalLink,
  Lock,
  Calendar,
  Sparkles,
  Layers,
  Sparkle,
  PlusCircle,
  HelpCircle,
  Eye,
  Link2,
  X
} from "lucide-react";
import { api } from "../api/client";
import { Card, LoadingState, PageHeader, Badge } from "../components/ui";
import { useI18n } from "../i18n";
import { formatGlucoseFromMgdl, mgdlToMmol, useGlucoseUnit } from "../utils/glucoseUnits";

function RiskBar({ value, t }: { value: number; t: (k: string) => string }) {
  const pct = Math.round(value * 100);
  const color = pct >= 70 ? "var(--error)" : pct >= 40 ? "#d97706" : "var(--primary)";
  return (
    <div style={{ display: "grid", gap: 6 }}>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline" }}>
        <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em", fontWeight: 700, color: "var(--muted)" }}>{t("family.risk.score")}</span>
        <strong style={{ font: "700 28px/1 Manrope, Inter, sans-serif", color }}>{pct}%</strong>
      </div>
      <div style={{ height: 10, borderRadius: 999, background: "var(--surface-low)", border: "1px solid var(--outline)", overflow: "hidden" }}>
        <div style={{ height: "100%", width: `${pct}%`, background: color, borderRadius: 999, transition: "width .6s cubic-bezier(.2,.9,.3,1)" }} />
      </div>
      <span style={{ fontSize: 12, color: "var(--muted)" }}>{t("family.risk.modelDesc")}</span>
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

export function FamilyView({ isPublic = false }: { isPublic?: boolean }) {
  const { token } = useParams<{ token?: string }>();
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const { unit } = useGlucoseUnit();

  const [activeToken, setActiveToken] = useState<string>(token || "demo-family-sarah");
  const [showShareDialog, setShowShareDialog] = useState(false);
  const shareSectionRef = useRef<HTMLDivElement | null>(null);

  // UI states for share panel
  const [copied, setCopied] = useState(false);
  const [emailInput, setEmailInput] = useState("");
  const [emailSending, setEmailSending] = useState(false);
  const [emailSentTo, setEmailSentTo] = useState<string | null>(null);

  // Custom link generation states
  const [newCaregiverName, setNewCaregiverName] = useState("");
  const [newRelationship, setNewRelationship] = useState("Family");

  // Caregiver Interactive Checklist
  const [checkedHelpItems, setCheckedHelpItems] = useState<string[]>(["water"]);

  const share = useQuery({
    queryKey: ["family-share", activeToken],
    queryFn: () => api.familyShare(activeToken),
    retry: false
  });

  const createShareMutation = useMutation({
    mutationFn: (payload: { user_id: number; shared_with_name: string; relationship: string }) =>
      api.createFamilyShare(payload),
    onSuccess: (response) => {
      setActiveToken(response.share_token);
      setNewCaregiverName("");
      setNewRelationship("Family");
      queryClient.invalidateQueries({ queryKey: ["family-share", response.share_token] });
    }
  });

  const data = share.data as any;
  const userName = data?.user?.full_name ?? "Sarah";
  const monitoring = data?.monitoring;
  const risk = data?.risk;
  const shareInfo = data?.share;
  const alerts: any[] = monitoring?.anomaly_flags ?? [];
  const isStable = monitoring?.trend_label !== "concerning";

  const computedStats = useMemo(() => {
    const allLogs = data?.logs ?? [];
    if (!allLogs.length) return null;
    const resolvedLogs = allLogs.map((l: any) => {
      const glucose = l.glucose_level ?? (l.is_fasting ? (l.fasting_glucose ?? l.post_meal_glucose) : (l.post_meal_glucose ?? l.fasting_glucose)) ?? 0;
      return { ...l, resolvedGlucose: glucose };
    });
    const fastingLogs = resolvedLogs.filter((l: any) => l.is_fasting && l.resolvedGlucose);
    const postMealLogs = resolvedLogs.filter((l: any) => !l.is_fasting && l.resolvedGlucose);
    const avgFasting = fastingLogs.length ? Math.round(fastingLogs.reduce((sum: number, l: any) => sum + l.resolvedGlucose, 0) / fastingLogs.length) : null;
    const avgPostMeal = postMealLogs.length ? Math.round(postMealLogs.reduce((sum: number, l: any) => sum + l.resolvedGlucose, 0) / postMealLogs.length) : null;
    const hypoEpisodes = resolvedLogs.filter((l: any) => l.resolvedGlucose < 70).length;
    const hyperEpisodes = resolvedLogs.filter((l: any) => l.resolvedGlucose > 180).length;
    const recentLogs = resolvedLogs.slice(-10).reverse();
    return { avgFasting, avgPostMeal, hypoEpisodes, hyperEpisodes, totalLogs: resolvedLogs.length, recentLogs };
  }, [data?.logs]);

  const shareUrl = `${window.location.origin}/share/${activeToken}`;

  const handleCopy = () => {
    navigator.clipboard.writeText(shareUrl);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleEmailSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!emailInput.trim()) return;
    setEmailSending(true);
    setTimeout(() => {
      setEmailSending(false);
      setEmailSentTo(emailInput.trim());
      setEmailInput("");
      setTimeout(() => setEmailSentTo(null), 5000);
    }, 1200);
  };

  const handleCreateShare = (e: React.FormEvent) => {
    e.preventDefault();
    if (!newCaregiverName.trim()) return;
    createShareMutation.mutate({ user_id: 1, shared_with_name: newCaregiverName.trim(), relationship: newRelationship });
  };

  const toggleHelpItem = (itemId: string) => {
    setCheckedHelpItems((prev) => prev.includes(itemId) ? prev.filter((id) => id !== itemId) : [...prev, itemId]);
  };

  const getGlucoseStatus = (level: number, isFasting: boolean) => {
    if (level < 70) return { label: t("family.glucose.hypo"), color: "var(--error)", bg: "var(--error-bg)", text: "var(--error)" };
    if (isFasting) {
      if (level <= 130) return { label: t("family.glucose.optimalFasting"), color: "var(--primary)", bg: "var(--primary-soft)", text: "var(--primary)" };
      if (level <= 180) return { label: t("family.glucose.elevatedFasting"), color: "#d97706", bg: "#fff8ed", text: "#b45309" };
      return { label: t("family.glucose.high"), color: "var(--error)", bg: "var(--error-bg)", text: "var(--error)" };
    } else {
      if (level <= 140) return { label: t("family.glucose.optimalPostMeal"), color: "var(--primary)", bg: "var(--primary-soft)", text: "var(--primary)" };
      if (level <= 180) return { label: t("family.glucose.elevatedPostMeal"), color: "#d97706", bg: "#fff8ed", text: "#b45309" };
      return { label: t("family.glucose.high"), color: "var(--error)", bg: "var(--error-bg)", text: "var(--error)" };
    }
  };

  if (share.isError) {
    return (
      <div style={{ display: "grid", placeItems: "center", minHeight: "60vh", textAlign: "center", padding: 24, gap: 16 }}>
        <div style={{ width: 64, height: 64, borderRadius: "50%", background: "var(--error-bg)", display: "grid", placeItems: "center", color: "var(--error)" }}>
          <Lock size={32} />
        </div>
        <h2 style={{ fontSize: 22, color: "var(--text)" }}>{t("family.errorTitle")}</h2>
        <p style={{ maxWidth: 450, color: "var(--muted)", margin: "0 auto", fontSize: 14 }}>
          {t("family.errorBody")}
        </p>
      </div>
    );
  }

  const dashboardContent = (
    <div className="family-grid" style={{ marginTop: isPublic ? 0 : 16 }}>
      <div className="family-main" style={{ display: "grid", gap: 20 }}>
        {/* Status banner */}
        <div style={{
          borderRadius: 16, padding: "20px 24px",
          display: "flex", alignItems: "center", gap: 20,
          background: isStable
            ? "linear-gradient(135deg, rgba(16, 185, 129, 0.08) 0%, rgba(16, 185, 129, 0.03) 100%)"
            : "linear-gradient(135deg, rgba(239, 68, 68, 0.08) 0%, rgba(239, 68, 68, 0.03) 100%)",
          border: `1px solid ${isStable ? "rgba(16, 185, 129, 0.25)" : "rgba(239, 68, 68, 0.25)"}`,
          boxShadow: "0 4px 20px -2px rgba(0, 0, 0, 0.02)",
          backdropFilter: "blur(8px)",
          position: "relative", overflow: "hidden"
        }}>
          <div style={{ position: "absolute", top: -50, right: -50, width: 120, height: 120, borderRadius: "50%", background: isStable ? "rgba(16, 185, 129, 0.08)" : "rgba(239, 68, 68, 0.08)", filter: "blur(30px)", pointerEvents: "none" }} />
          <div style={{
            width: 48, height: 48, borderRadius: "50%", flexShrink: 0,
            background: isStable ? "linear-gradient(135deg, var(--primary), #10b981)" : "linear-gradient(135deg, var(--error), #ef4444)",
            display: "grid", placeItems: "center",
            boxShadow: `0 4px 14px ${isStable ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)"}`
          }}>
            <Heart size={20} color="#fff" />
          </div>
          <div>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <h2 style={{ margin: 0, fontSize: 18, color: isStable ? "var(--primary)" : "var(--error)", fontWeight: 800, letterSpacing: "-0.01em" }}>
                {isStable ? t("family.status.stable") : t("family.status.attention")}
              </h2>
              <span style={{
                fontSize: 9, fontWeight: 700, padding: "2px 6px", borderRadius: 4,
                background: isStable ? "rgba(16, 185, 129, 0.15)" : "rgba(239, 68, 68, 0.15)",
                color: isStable ? "var(--primary)" : "var(--error)",
                textTransform: "uppercase", letterSpacing: "0.05em"
              }}>
                {isStable ? t("family.status.stableBadge") : t("family.status.warningBadge")}
              </span>
            </div>
            <p style={{ margin: "4px 0 0", color: "var(--muted)", fontSize: 13, lineHeight: 1.5, fontWeight: 500 }}>
              {monitoring?.summary?.message ?? t("family.status.defaultMessage").replace("%s", userName)}
            </p>
          </div>
        </div>

        {/* Dynamic metrics */}
        {computedStats && (
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 14 }}>
            {[
              {
                title: t("family.metric.avgFasting"),
                value: computedStats.avgFasting ? (unit === "mgdl" ? computedStats.avgFasting : Number(mgdlToMmol(computedStats.avgFasting).toFixed(1))) : null,
                color: computedStats.avgFasting && computedStats.avgFasting > 125 ? "var(--error)" : "var(--primary)",
                isError: computedStats.avgFasting && computedStats.avgFasting > 125,
                sub: computedStats.avgFasting ? formatGlucoseFromMgdl(computedStats.avgFasting, unit) : null,
                footer: t("family.metric.optimalFasting")
              },
              {
                title: t("family.metric.avgPostMeal"),
                value: computedStats.avgPostMeal ? (unit === "mgdl" ? computedStats.avgPostMeal : Number(mgdlToMmol(computedStats.avgPostMeal).toFixed(1))) : null,
                color: computedStats.avgPostMeal && computedStats.avgPostMeal > 140 ? "#d97706" : "var(--primary)",
                isError: computedStats.avgPostMeal && computedStats.avgPostMeal > 140,
                sub: computedStats.avgPostMeal ? formatGlucoseFromMgdl(computedStats.avgPostMeal, unit) : null,
                footer: t("family.metric.optimalPostMeal")
              },
              {
                title: t("family.metric.alertEpisodes"),
                value: computedStats.hyperEpisodes + computedStats.hypoEpisodes,
                color: computedStats.hyperEpisodes > 0 || computedStats.hypoEpisodes > 0 ? "var(--error)" : "var(--primary)",
                isError: computedStats.hyperEpisodes > 0 || computedStats.hypoEpisodes > 0,
                sub: t("family.metric.hypoHyper").replace("%d", String(computedStats.hypoEpisodes)).replace("%d", String(computedStats.hyperEpisodes)),
                footer: t("family.metric.outOfRange")
              },
              {
                title: t("family.metric.glucoseLogs"),
                value: computedStats.totalLogs,
                color: "var(--primary)",
                isError: false,
                sub: t("family.metric.activeMonitoring"),
                footer: t("family.metric.shownBelow").replace("%d", String(computedStats.recentLogs.length))
              }
            ].map((stat, i) => (
              <div
                key={i}
                onMouseEnter={(e) => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "0 8px 24px rgba(0, 0, 0, 0.05)"; e.currentTarget.style.borderColor = stat.isError ? "var(--error)" : "var(--primary)"; }}
                onMouseLeave={(e) => { e.currentTarget.style.transform = "none"; e.currentTarget.style.boxShadow = "none"; e.currentTarget.style.borderColor = "var(--outline)"; }}
                style={{ background: "var(--surface-low)", border: "1px solid var(--outline)", borderRadius: 12, padding: "16px 18px", display: "grid", gap: 6, transition: "all 0.2s ease-in-out", cursor: "default" }}
              >
                <span style={{ color: "var(--muted)", fontSize: 10, textTransform: "uppercase", letterSpacing: ".06em", fontWeight: 700 }}>{stat.title}</span>
                <div style={{ display: "flex", alignItems: "baseline", gap: 4 }}>
                  <strong style={{ font: "800 26px/1 Manrope, Inter, sans-serif", color: stat.color }}>
                    {stat.value ?? "--"}
                  </strong>
                  {stat.value && i < 2 && <span style={{ color: "var(--muted)", fontSize: 11, fontWeight: 600 }}>{unit === "mgdl" ? "mg/dL" : "mmol/L"}</span>}
                </div>
                {stat.sub && <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 600 }}>{stat.sub}</span>}
                <span style={{ fontSize: 10, color: "var(--muted)", borderTop: "1px solid var(--outline)", paddingTop: 4, marginTop: 4 }}>{stat.footer}</span>
              </div>
            ))}
          </div>
        )}

        {/* Glucose Timeline */}
        {computedStats && (
          <Card title={t("family.timeline.title")}>
            <p style={{ fontSize: 12, color: "var(--muted)", margin: "-10px 0 16px 0", lineHeight: 1.4 }}>
              {t("family.timeline.desc")}
            </p>
            <div style={{ overflowX: "auto", border: "1px solid var(--outline)", borderRadius: 10, background: "var(--surface)" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13, textAlign: "left" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--outline)", background: "var(--surface-low)" }}>
                    <th style={{ padding: "10px 14px", fontWeight: 700, color: "var(--muted)", fontSize: 11, textTransform: "uppercase", width: 40, textAlign: "center" }}>{t("family.timeline.status")}</th>
                    <th style={{ padding: "10px 14px", fontWeight: 700, color: "var(--muted)", fontSize: 11, textTransform: "uppercase" }}>{t("family.timeline.glucoseLevel")}</th>
                    <th style={{ padding: "10px 14px", fontWeight: 700, color: "var(--muted)", fontSize: 11, textTransform: "uppercase", width: 100 }}>{t("family.timeline.mealContext")}</th>
                    <th style={{ padding: "10px 14px", fontWeight: 700, color: "var(--muted)", fontSize: 11, textTransform: "uppercase" }}>{t("family.timeline.date")}</th>
                    <th style={{ padding: "10px 14px", fontWeight: 700, color: "var(--muted)", fontSize: 11, textTransform: "uppercase" }}>{t("family.timeline.notes")}</th>
                    <th style={{ padding: "10px 14px", fontWeight: 700, color: "var(--muted)", fontSize: 11, textTransform: "uppercase", textAlign: "right" }}>{t("family.timeline.classification")}</th>
                  </tr>
                </thead>
                <tbody>
                  {computedStats.recentLogs.map((log: any, idx: number) => {
                    const glucose = log.resolvedGlucose;
                    const classification = getGlucoseStatus(glucose, log.is_fasting);
                    return (
                      <tr key={log.id || idx} style={{ borderBottom: idx < computedStats.recentLogs.length - 1 ? "1px solid var(--outline)" : "none", transition: "background 0.2s ease" }}
                        onMouseEnter={(e) => (e.currentTarget.style.background = "var(--surface-low)")}
                        onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                      >
                        <td style={{ padding: "10px 14px", verticalAlign: "middle", textAlign: "center" }}>
                          <div style={{ width: 8, height: 8, borderRadius: "50%", background: classification.color, boxShadow: `0 0 8px ${classification.color}`, margin: "0 auto" }} />
                        </td>
                        <td style={{ padding: "10px 14px", fontWeight: 700, color: "var(--text)", whiteSpace: "nowrap" }}>
                          <span style={{ fontSize: 14 }}>{unit === "mgdl" ? Math.round(glucose) : mgdlToMmol(glucose).toFixed(1)}</span>
                          <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 500, marginLeft: 4 }}>{unit === "mgdl" ? "mg/dL" : "mmol/L"}</span>
                          <span style={{ margin: "0 6px", color: "var(--outline)", fontSize: 11 }}>|</span>
                          <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 500 }}>
                            {unit === "mgdl" ? mgdlToMmol(glucose).toFixed(1) : Math.round(glucose)} <span style={{ fontSize: 10 }}>{unit === "mgdl" ? "mmol/L" : "mg/dL"}</span>
                          </span>
                        </td>
                        <td style={{ padding: "10px 14px", verticalAlign: "middle" }}>
                          <span style={{ fontSize: 10, padding: "2px 8px", borderRadius: 4, fontWeight: 700, background: log.is_fasting ? "rgba(16, 185, 129, 0.12)" : "var(--outline)", color: log.is_fasting ? "var(--primary)" : "var(--text)", display: "inline-block" }}>
                            {log.is_fasting ? t("family.timeline.fasting") : t("family.timeline.postMeal")}
                          </span>
                        </td>
                        <td style={{ padding: "10px 14px", color: "var(--muted)", fontSize: 12, whiteSpace: "nowrap" }}>{log.log_date}</td>
                        <td style={{ padding: "10px 14px", fontSize: 12 }}>
                          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                            {log.activity_minutes > 0 && (
                              <span style={{ fontSize: 10, padding: "2px 6px", borderRadius: 4, fontWeight: 700, background: "rgba(16, 185, 129, 0.08)", color: "var(--primary)", display: "inline-flex", alignItems: "center", gap: 3 }}>
                                <Clock size={10} /> {t("family.timeline.walk").replace("%d", String(log.activity_minutes))}
                              </span>
                            )}
                            {log.notes ? (
                              <span style={{ color: "var(--text)", fontStyle: "italic", maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={log.notes}>
                                "{log.notes}"
                              </span>
                            ) : (
                              <span style={{ color: "var(--outline)", fontSize: 11 }}>—</span>
                            )}
                          </div>
                        </td>
                        <td style={{ padding: "10px 14px", textAlign: "right", verticalAlign: "middle" }}>
                          <span style={{ fontSize: 10, fontWeight: 700, padding: "3px 8px", borderRadius: 999, background: classification.bg, color: classification.text, letterSpacing: ".02em", textTransform: "uppercase", display: "inline-block" }}>
                            {classification.label}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </Card>
        )}

        {/* Risk profile */}
        {risk && (
          <Card title={t("family.risk.title")}>
            <div style={{ display: "grid", gap: 18 }}>
              <RiskBar value={risk.risk_probability} t={t} />
              <div style={{ display: "grid", gap: 8 }}>
                <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".05em", fontWeight: 700, color: "var(--muted)" }}>{t("family.risk.factors")}</span>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
                  {risk.top_factors?.map((f: any) => (
                    <span key={f.label} style={{ border: "1px solid var(--outline)", borderRadius: 999, padding: "5px 12px", fontSize: 12, fontWeight: 700, background: "var(--surface-low)", color: "var(--muted)" }}>{f.label}</span>
                  ))}
                </div>
              </div>
              <p style={{ margin: 0, fontSize: 13, color: "var(--muted)", borderTop: "1px solid var(--outline)", paddingTop: 12, lineHeight: 1.5 }}>
                {risk.explanation}
              </p>
            </div>
          </Card>
        )}
      </div>

      <div className="family-side" style={{ display: "grid", gap: 20 }}>
        {/* Active Alerts */}
        <Card
          title={t("family.alerts.title")}
          action={<AlertTriangle size={16} color={alerts.length ? "var(--error)" : "var(--muted)"} />}
        >
          {alerts.length > 0 ? (
            <div style={{ display: "grid", gap: 8 }}>
              {alerts.map((flag: any) => <AlertItem key={flag.label} flag={flag} />)}
            </div>
          ) : (
            <div style={{ display: "flex", alignItems: "center", gap: 10, color: "var(--primary)", background: "var(--primary-soft)", borderRadius: 8, padding: "12px 14px" }}>
              <Activity size={16} />
              <span style={{ fontSize: 13, fontWeight: 700 }}>{t("family.alerts.none")}</span>
            </div>
          )}
        </Card>

        {/* Recommended actions */}
        {monitoring?.recommended_actions?.length > 0 && (
          <Card title={t("family.actions.title")}>
            <div style={{ display: "grid", gap: 10 }}>
              {monitoring.recommended_actions.map((action: string, i: number) => (
                <div key={i} style={{ display: "flex", gap: 10, alignItems: "flex-start", paddingBottom: 10, borderBottom: i < monitoring.recommended_actions.length - 1 ? "1px solid var(--outline)" : "none" }}>
                  <ShieldAlert size={15} color="var(--primary)" style={{ marginTop: 2, flexShrink: 0 }} />
                  <span style={{ fontSize: 13, color: "var(--text)", lineHeight: 1.4 }}>{action}</span>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* Checklist */}
        <Card title={t("family.checklist.title")}>
          <p style={{ fontSize: 12, color: "var(--muted)", margin: "-10px 0 16px 0", lineHeight: 1.4 }}>
            {t("family.checklist.desc")}
          </p>
          <ul className="help-list" style={{ display: "grid", gap: 12, listStyle: "none", padding: 0, margin: 0 }}>
            {[
              { id: "walk", title: t("family.checklist.walk"), desc: t("family.checklist.walkDesc"), icon: Clock },
              { id: "water", title: t("family.checklist.water"), desc: t("family.checklist.waterDesc"), icon: Droplets },
              { id: "log", title: t("family.checklist.log"), desc: t("family.checklist.logDesc"), icon: CheckSquare },
              { id: "med", title: t("family.checklist.med"), desc: t("family.checklist.medDesc"), icon: Users }
            ].map((item) => {
              const isChecked = checkedHelpItems.includes(item.id);
              const ItemIcon = item.icon;
              return (
                <li key={item.id}
                  onClick={() => toggleHelpItem(item.id)}
                  style={{
                    display: "flex", gap: 12, alignItems: "flex-start", cursor: "pointer",
                    padding: "12px 14px", borderRadius: 10, background: isChecked ? "var(--primary-soft)" : "var(--surface-low)",
                    transition: "all 0.2s ease-in-out", border: `1px solid ${isChecked ? "var(--primary)" : "var(--outline)"}`
                  }}
                  onMouseEnter={(e) => { if (!isChecked) { e.currentTarget.style.borderColor = "var(--primary)"; e.currentTarget.style.background = "var(--surface)"; } }}
                  onMouseLeave={(e) => { if (!isChecked) { e.currentTarget.style.borderColor = "var(--outline)"; e.currentTarget.style.background = "var(--surface-low)"; } }}
                >
                  <div style={{
                    width: 20, height: 20, borderRadius: 6, border: "2px solid var(--outline)",
                    display: "grid", placeItems: "center", background: isChecked ? "var(--primary)" : "var(--surface)",
                    borderColor: isChecked ? "var(--primary)" : "var(--outline)", flexShrink: 0, marginTop: 2, transition: "all 0.2s"
                  }}>
                    {isChecked && <Check size={12} color="#fff" strokeWidth={3} />}
                  </div>
                  <div style={{ display: "grid", gap: 2 }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <ItemIcon size={14} color={isChecked ? "var(--primary)" : "var(--muted)"} />
                      <strong style={{ fontSize: 13, color: isChecked ? "var(--primary)" : "var(--text)", textDecoration: isChecked ? "line-through" : "none" }}>
                        {item.title}
                      </strong>
                    </div>
                    <span style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.4 }}>{item.desc}</span>
                  </div>
                </li>
              );
            })}
          </ul>
        </Card>
      </div>
    </div>
  );

  // Public caregiver view
  if (isPublic) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--background)", padding: "40px 16px", fontFamily: "Inter, sans-serif" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto", display: "grid", gap: 24 }}>
          <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid var(--outline)", paddingBottom: 16, flexWrap: "wrap", gap: 12 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <div style={{ width: 38, height: 38, borderRadius: "50%", background: "linear-gradient(135deg, var(--primary), #0284c7)", display: "grid", placeItems: "center", color: "#fff", fontWeight: 800 }}>G</div>
              <div style={{ display: "grid", gap: 1 }}>
                <strong style={{ fontSize: 16, color: "var(--text)" }}>{t("family.public.brand")}</strong>
                <span style={{ fontSize: 11, color: "var(--muted)" }}>{t("family.public.security")}</span>
              </div>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <Lock size={12} color="var(--primary)" />
              <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 700 }}>{t("family.public.secureShare")}</span>
            </div>
          </header>

          <div style={{ background: "var(--primary-soft)", border: "1px solid var(--primary)", borderRadius: 10, padding: "12px 18px", display: "flex", gap: 10, alignItems: "center" }}>
            <Eye size={16} color="var(--primary)" />
            <span style={{ fontSize: 13, color: "var(--text)" }}>
              {t("family.public.caregiverMode")} <strong>{userName}</strong>.
            </span>
          </div>

          {share.isPending ? <LoadingState label={t("family.public.loading")} /> : dashboardContent}

          <footer style={{ textAlign: "center", color: "var(--muted)", fontSize: 11, marginTop: 40, borderTop: "1px solid var(--outline)", paddingTop: 20 }}>
            {t("family.public.footer")}
          </footer>
        </div>
      </div>
    );
  }

  // Patient dashboard view
  return (
    <div className="page">
      <PageHeader
        title={t("family.title")}
        subtitle={t("family.subtitle")}
        meta={t("family.meta")}
        action={
          <button
            type="button"
            className="secondary"
            onClick={() => {
              setShowShareDialog((prev) => !prev);
              if (!showShareDialog) {
                setTimeout(() => {
                  shareSectionRef.current?.scrollIntoView({ behavior: "smooth" });
                }, 100);
              }
            }}
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              padding: "8px 14px",
              fontSize: "12px",
              height: "38px",
              whiteSpace: "nowrap",
            }}
          >
            <Link2 size={16} />
            <span>{t("family.shareSettings")}</span>
          </button>
        }
      />

      {share.isPending && <LoadingState label={t("family.loading")} />}

      {!share.isPending && (
        <div style={{ display: "grid", gap: 24 }}>
          {/* Compact share status bar */}
          <div style={{
            background: "var(--surface-low)", border: "1px solid var(--outline)",
            borderRadius: 12, padding: "14px 20px", display: "flex", justifyContent: "space-between",
            alignItems: "center", flexWrap: "wrap", gap: 12
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <Users size={20} color="var(--primary)" />
              <div>
                <strong style={{ fontSize: 15, color: "var(--text)" }}>
                  {t("family.circle.current")}: {shareInfo?.shared_with_name ?? t("family.circle.defaultName")}
                </strong>
                <span style={{ display: "block", fontSize: 12, color: "var(--muted)" }}>
                  {t("family.circle.relationship")}: {shareInfo?.relationship ?? "Family"}
                </span>
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <a href={shareUrl} target="_blank" rel="noreferrer" style={{ display: "inline-flex", alignItems: "center", gap: 6, fontSize: 13, fontWeight: 700, color: "var(--primary)", textDecoration: "none" }}>
                {t("family.circle.preview")} <ExternalLink size={14} />
              </a>
            </div>
          </div>

          <div style={{ borderTop: "1px solid var(--outline)", paddingTop: 20 }}>
            <h3 style={{ fontSize: 16, fontWeight: 700, color: "var(--text)", margin: "0 0 10px 0" }}>
              {t("family.dashboardPreview")}
            </h3>
            {dashboardContent}
          </div>
          {/* Inline Share Settings Card instead of Modal */}
          {showShareDialog && (
            <div
              ref={shareSectionRef}
              style={{
                borderTop: "1px solid var(--outline)",
                paddingTop: 24,
                animation: "panelIn 280ms cubic-bezier(.2,.9,.3,1)"
              }}
            >
              <Card
                title={t("family.shareSettings")}
                action={
                  <button
                    type="button"
                    className="icon-button"
                    onClick={() => setShowShareDialog(false)}
                    aria-label="Close"
                    style={{
                      width: 32,
                      height: 32,
                      borderRadius: "10px",
                      border: "1px solid var(--outline)",
                      background: "var(--surface-low)",
                      color: "var(--muted)",
                      cursor: "pointer",
                      display: "grid",
                      placeItems: "center",
                      transition: "all 150ms"
                    }}
                  >
                    <X size={16} />
                  </button>
                }
              >
                <div style={{ display: "grid", gap: 24 }}>
                  {/* Active Access Link Section */}
                  <div className="family-share-section">
                    <h3 className="family-share-section-title">{t("family.accessLink.title")}</h3>
                    <p style={{ fontSize: 12, color: "var(--muted)", margin: "0 0 14px", lineHeight: 1.4 }}>
                      {t("family.accessLink.desc")}
                    </p>
                    <div style={{ display: "grid", gap: 12 }}>
                      <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                        <input
                          type="text" readOnly value={shareUrl}
                          style={{ flex: 1, minWidth: 200, padding: "10px 12px", borderRadius: 8, border: "1px solid var(--outline)", background: "var(--surface-low)", fontSize: 13, fontFamily: "monospace", color: "var(--text)" }}
                        />
                        <button type="button" onClick={handleCopy} className="primary" style={{ display: "flex", alignItems: "center", gap: 6, whiteSpace: "nowrap" }}>
                          {copied ? <Check size={16} /> : <Copy size={16} />}
                          {copied ? t("family.accessLink.copied") : t("family.accessLink.copy")}
                        </button>
                      </div>
                      <form onSubmit={handleEmailSend} style={{ borderTop: "1px solid var(--outline)", paddingTop: 12, display: "grid", gap: 10 }}>
                        <label style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)" }}>{t("family.accessLink.emailLabel")}</label>
                        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
                          <input
                            type="email" required placeholder={t("family.accessLink.emailPlaceholder")} value={emailInput}
                            onChange={(e) => setEmailInput(e.target.value)}
                            style={{ flex: 1, minWidth: 200, padding: "8px 12px", borderRadius: 8, border: "1px solid var(--outline)", background: "var(--surface)", fontSize: 13 }}
                          />
                          <button type="submit" disabled={emailSending} className="secondary" style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 120, justifyContent: "center" }}>
                            {emailSending ? t("family.accessLink.sending") : <><Mail size={15} /> {t("family.accessLink.sendEmail")}</>}
                          </button>
                        </div>
                        {emailSentTo && (
                          <div style={{ fontSize: 12, color: "var(--primary)", background: "var(--primary-soft)", padding: "6px 12px", borderRadius: 6, display: "flex", gap: 6, alignItems: "center" }}>
                            <Check size={14} />
                            {t("family.accessLink.sentTo").replace("%s", emailSentTo)}
                          </div>
                        )}
                      </form>
                    </div>
                  </div>

                  {/* Generate New Share Key Section */}
                  <div className="family-share-section">
                    <h3 className="family-share-section-title">{t("family.newKey.title")}</h3>
                    <p style={{ fontSize: 12, color: "var(--muted)", margin: "0 0 14px", lineHeight: 1.4 }}>
                      {t("family.newKey.desc")}
                    </p>
                    <form onSubmit={handleCreateShare} style={{ display: "grid", gap: 12 }}>
                      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, flexWrap: "wrap" }}>
                        <div style={{ display: "grid", gap: 6 }}>
                          <label style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase" }}>{t("family.newKey.nameLabel")}</label>
                          <input
                            type="text" required placeholder={t("family.newKey.namePlaceholder")} value={newCaregiverName}
                            onChange={(e) => setNewCaregiverName(e.target.value)}
                            style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid var(--outline)", background: "var(--surface)", fontSize: 13 }}
                          />
                        </div>
                        <div style={{ display: "grid", gap: 6 }}>
                          <label style={{ fontSize: 11, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase" }}>{t("family.newKey.relationship")}</label>
                          <select
                            value={newRelationship} onChange={(e) => setNewRelationship(e.target.value)}
                            style={{ padding: "8px 12px", borderRadius: 8, border: "1px solid var(--outline)", background: "var(--surface)", fontSize: 13, height: "100%", color: "var(--text)" }}
                          >
                            <option value="Family">{t("family.newKey.relFamily")}</option>
                            <option value="Spouse">{t("family.newKey.relSpouse")}</option>
                            <option value="Caregiver">{t("family.newKey.relCaregiver")}</option>
                            <option value="Doctor">{t("family.newKey.relDoctor")}</option>
                          </select>
                        </div>
                      </div>
                      <button type="submit" disabled={createShareMutation.isPending} className="primary" style={{ display: "flex", alignItems: "center", gap: 8, justifyContent: "center", padding: "10px 14px" }}>
                        <PlusCircle size={16} />
                        {createShareMutation.isPending ? t("family.newKey.generating") : t("family.newKey.generate")}
                      </button>
                    </form>
                  </div>
                </div>
              </Card>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
