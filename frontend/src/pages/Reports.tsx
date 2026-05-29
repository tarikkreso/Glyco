import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import type { ReportDocument } from "../api/client";
import { useAuth } from "../auth/auth";
import { ErrorState, LoadingState, PageHeader } from "../components/ui";
import { useI18n } from "../i18n";

const reportTypes = [
  {
    id: "doctor",
    labelKey: "reports.type.doctor",
    descriptionKey: "reports.type.doctorDescription",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
      </svg>
    ),
  },
  {
    id: "family",
    labelKey: "reports.type.family",
    descriptionKey: "reports.type.familyDescription",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
        <path d="M16 3.13a4 4 0 0 1 0 7.75" />
      </svg>
    ),
  },
  {
    id: "weekly",
    labelKey: "reports.type.weekly",
    descriptionKey: "reports.type.weeklyDescription",
    icon: (
      <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
        <line x1="16" y1="2" x2="16" y2="6" />
        <line x1="8" y1="2" x2="8" y2="6" />
        <line x1="3" y1="10" x2="21" y2="10" />
      </svg>
    ),
  },
];

function reportTypeLabel(type: string, t: (key: string) => string) {
  if (type === "doctor") return t("reports.type.doctor");
  if (type === "family") return t("reports.type.family");
  if (type === "weekly") return t("reports.type.weekly");
  return type;
}

function reportTitle(report: ReportDocument, t: (key: string) => string) {
  return reportTypeLabel(report.report_type, t) || report.content.title;
}

function archiveEmptyText(type: string, t: (key: string) => string) {
  if (type === "all") return t("reports.archive.emptyAll");
  return t("reports.archive.emptyType").replace("%s", reportTypeLabel(type, t).toLowerCase());
}

/* ─── Doctor PDF — crisp clinical blue ───────────────────────────── */
function DoctorPdf({ report }: { report: ReportDocument }) {
  return (
    <div className="pdf-page" style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}>
      {/* Header bar */}
      <div style={{ background: "#1d4ed8", borderRadius: "6px 6px 0 0", padding: "16px 28px", display: "flex", justifyContent: "space-between", alignItems: "center", margin: "-40px -48px 28px" }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 32, height: 32, borderRadius: 6, background: "rgba(255,255,255,0.2)", display: "grid", placeItems: "center", color: "#fff" }}>
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></svg>
          </div>
          <div>
            <div style={{ color: "#fff", fontFamily: "Inter, sans-serif", fontWeight: 800, fontSize: 13, letterSpacing: ".08em", textTransform: "uppercase" }}>Glyco Health</div>
            <div style={{ color: "rgba(255,255,255,.7)", fontFamily: "Inter, sans-serif", fontSize: 11, marginTop: 2 }}>Clinical Summary Report</div>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          {report.created_at && <div style={{ color: "rgba(255,255,255,.8)", fontFamily: "Inter, sans-serif", fontSize: 11, marginBottom: 4 }}>{new Date(report.created_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}</div>}
          <span style={{ background: "rgba(255,255,255,.15)", color: "#fff", fontFamily: "Inter, sans-serif", fontSize: 10, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", padding: "3px 8px", borderRadius: 999 }}>CLINICAL</span>
        </div>
      </div>

      <h1 style={{ fontFamily: "Georgia, serif", fontSize: 20, color: "#1e3a5f", margin: "0 0 20px", lineHeight: 1.3 }}>{report.content.title}</h1>

      <div style={{ display: "grid", gap: 18 }}>
        {report.content.sections.map((section) => (
          <div key={section.title} style={{ borderLeft: "3px solid #1d4ed8", paddingLeft: 14 }}>
            <h2 style={{ fontFamily: "Inter, sans-serif", fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em", color: "#1d4ed8", fontWeight: 800, margin: "0 0 6px" }}>{section.title}</h2>
            <p style={{ fontFamily: "Georgia, serif", fontSize: 13, lineHeight: 1.65, color: "#222", margin: 0 }}>{section.body}</p>
          </div>
        ))}
      </div>

      {report.content.disclaimer && (
        <div style={{ marginTop: 28, paddingTop: 14, borderTop: "1px solid #e2e8f0", fontSize: 11, color: "#64748b", fontFamily: "Inter, sans-serif", lineHeight: 1.5 }}>{report.content.disclaimer}</div>
      )}
    </div>
  );
}

/* ─── Family PDF — warm pink/rose ────────────────────────────────── */
function FamilyPdf({ report }: { report: ReportDocument }) {
  return (
    <div className="pdf-page" style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}>
      {/* Warm header */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 20 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 40, height: 40, borderRadius: "50%", background: "#fce7f3", display: "grid", placeItems: "center", color: "#9d174d", border: "1px solid #fbcfe8" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" />
              <circle cx="9" cy="7" r="4" />
              <path d="M23 21v-2a4 4 0 0 0-3-3.87" />
              <path d="M16 3.13a4 4 0 0 1 0 7.75" />
            </svg>
          </div>
          <div>
            <div style={{ fontFamily: "Inter, sans-serif", fontWeight: 800, fontSize: 13, letterSpacing: ".08em", textTransform: "uppercase", color: "#9d174d" }}>Glyco Health</div>
            <div style={{ fontFamily: "Inter, sans-serif", fontSize: 11, color: "#be185d", marginTop: 2 }}>Family Update</div>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          {report.created_at && <div style={{ fontFamily: "Inter, sans-serif", fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>{new Date(report.created_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}</div>}
          <span style={{ background: "#fce7f3", color: "#9d174d", fontFamily: "Inter, sans-serif", fontSize: 10, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", padding: "3px 8px", borderRadius: 999 }}>FAMILY</span>
        </div>
      </div>

      {/* Gradient rule */}
      <div style={{ height: 3, background: "linear-gradient(90deg, #ec4899 0%, #fce7f3 100%)", borderRadius: 999, marginBottom: 22, border: "none" }} />

      <h1 style={{ fontFamily: "Georgia, serif", fontSize: 20, color: "#831843", margin: "0 0 20px", lineHeight: 1.3 }}>{report.content.title}</h1>

      <div style={{ display: "grid", gap: 16 }}>
        {report.content.sections.map((section, i) => (
          <div key={section.title} style={{ background: i % 2 === 0 ? "#fff9fb" : "#fff", border: "1px solid #fbcfe8", borderRadius: 8, padding: "14px 16px" }}>
            <h2 style={{ fontFamily: "Inter, sans-serif", fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em", color: "#be185d", fontWeight: 800, margin: "0 0 6px" }}>{section.title}</h2>
            <p style={{ fontFamily: "Georgia, serif", fontSize: 13, lineHeight: 1.65, color: "#333", margin: 0 }}>{section.body}</p>
          </div>
        ))}
      </div>

      {report.content.disclaimer && (
        <div style={{ marginTop: 28, paddingTop: 14, borderTop: "1px solid #fbcfe8", fontSize: 11, color: "#9ca3af", fontFamily: "Inter, sans-serif", lineHeight: 1.5 }}>{report.content.disclaimer}</div>
      )}
    </div>
  );
}

/* ─── Weekly PDF — fresh green ───────────────────────────────────── */
function WeeklyPdf({ report }: { report: ReportDocument }) {
  return (
    <div className="pdf-page" style={{ fontFamily: "Georgia, 'Times New Roman', serif" }}>
      {/* Header with day-grid accent */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 10 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <div style={{ width: 36, height: 36, borderRadius: 8, background: "#d1e8da", display: "grid", placeItems: "center", color: "#154539" }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
          </div>
          <div>
            <div style={{ fontFamily: "Inter, sans-serif", fontWeight: 800, fontSize: 13, letterSpacing: ".08em", textTransform: "uppercase", color: "#154539" }}>Glyco Health</div>
            <div style={{ fontFamily: "Inter, sans-serif", fontSize: 11, color: "#2f5d50", marginTop: 2 }}>Weekly Reflection</div>
          </div>
        </div>
        <div style={{ textAlign: "right" }}>
          {report.created_at && <div style={{ fontFamily: "Inter, sans-serif", fontSize: 11, color: "#9ca3af", marginBottom: 4 }}>{new Date(report.created_at).toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}</div>}
          <span style={{ background: "#d1e8da", color: "#154539", fontFamily: "Inter, sans-serif", fontSize: 10, fontWeight: 800, letterSpacing: ".08em", textTransform: "uppercase", padding: "3px 8px", borderRadius: 999 }}>WEEKLY</span>
        </div>
      </div>

      {/* Day strip */}
      <div style={{ display: "flex", gap: 4, marginBottom: 20 }}>
        {["M","T","W","T","F","S","S"].map((d, i) => (
          <div key={i} style={{ flex: 1, textAlign: "center", padding: "5px 0", background: i < 5 ? "#d1e8da" : "#f3f4f1", borderRadius: 4, fontFamily: "Inter, sans-serif", fontSize: 10, fontWeight: 800, color: i < 5 ? "#154539" : "#9ca3af" }}>{d}</div>
        ))}
      </div>

      <h1 style={{ fontFamily: "Georgia, serif", fontSize: 20, color: "#154539", margin: "0 0 20px", lineHeight: 1.3 }}>{report.content.title}</h1>

      <div style={{ display: "grid", gap: 16 }}>
        {report.content.sections.map((section) => (
          <div key={section.title}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
              <div style={{ width: 6, height: 6, borderRadius: "50%", background: "#154539", flexShrink: 0 }} />
              <h2 style={{ fontFamily: "Inter, sans-serif", fontSize: 10, textTransform: "uppercase", letterSpacing: ".08em", color: "#154539", fontWeight: 800, margin: 0 }}>{section.title}</h2>
            </div>
            <p style={{ fontFamily: "Georgia, serif", fontSize: 13, lineHeight: 1.65, color: "#333", margin: "0 0 0 14px" }}>{section.body}</p>
          </div>
        ))}
      </div>

      {report.content.disclaimer && (
        <div style={{ marginTop: 28, paddingTop: 14, borderTop: "1px solid #c0c8c4", fontSize: 11, color: "#9ca3af", fontFamily: "Inter, sans-serif", lineHeight: 1.5 }}>{report.content.disclaimer}</div>
      )}
    </div>
  );
}

function ReportPdfPreview({ report }: { report: ReportDocument }) {
  if (report.report_type === "doctor") return <DoctorPdf report={report} />;
  if (report.report_type === "family") return <FamilyPdf report={report} />;
  return <WeeklyPdf report={report} />;
}

/* ─── Main page ───────────────────────────────────────────────────── */
export function Reports() {
  const auth = useAuth();
  const { language, t } = useI18n();
  const bs = language === "bs";
  const userId = auth.session?.userId ?? 1;
  const queryClient = useQueryClient();
  const [previewReport, setPreviewReport] = useState<ReportDocument | null>(null);
  const [activeArchiveType, setActiveArchiveType] = useState<string>("all");

  const reports = useQuery<ReportDocument[]>({
    queryKey: ["reports", userId],
    queryFn: () => api.reports(userId),
  });

  const create = useMutation({
    mutationFn: (type: string) => api.report(type, userId, language),
    onSuccess: (newReport: ReportDocument) => {
      queryClient.invalidateQueries({ queryKey: ["reports", userId] });
      setPreviewReport(newReport);
    },
  });

  const allReports: ReportDocument[] = reports.data ?? [];
  const latestReport = previewReport ?? (allReports.length ? allReports[0] : null);
  const latestPdfUrl = latestReport?.id ? api.reportPdfUrl(latestReport.id, true) : null;

  const filteredArchive =
    activeArchiveType === "all"
      ? allReports
      : allReports.filter((r) => r.report_type === activeArchiveType);

  return (
    <div className="page reports-page">
      <PageHeader
        title={bs ? "Izvještaji" : "Reports"}
        subtitle={bs ? "Generišite i upravljajte kliničkim, porodičnim i sedmičnim zdravstvenim sažecima." : "Generate and manage clinical, family, and weekly health summaries."}
      />

      {create.isError && (
        <ErrorState
          title={bs ? "Generisanje izvještaja nije uspjelo" : "Report generation failed"}
          body={bs ? "Backend nije vratio dokument izvještaja." : "The backend did not return a report document."}
        />
      )}

      <div className="reports-layout">
        {/* LEFT — Generator Panel */}
        <aside className="reports-generator">
          <div className="generator-header">
            <span className="generator-label">{bs ? "Generiši" : "Generate"}</span>
          </div>
          <div className="generator-cards">
            {reportTypes.map((rt) => {
              const isPending = create.isPending && create.variables === rt.id;
              return (
                <button
                  key={rt.id}
                  className={`gen-card${isPending ? " gen-card--pending" : ""}`}
                  onClick={() => create.mutate(rt.id)}
                  disabled={create.isPending}
                >
                  <div className="gen-card-icon">{rt.icon}</div>
                  <div className="gen-card-body">
                    <strong>{t(rt.labelKey)}</strong>
                    <p>{t(rt.descriptionKey)}</p>
                  </div>
                  <div className="gen-card-action">
                    {isPending ? (
                      <span className="gen-spinner" />
                    ) : (
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <line x1="12" y1="5" x2="12" y2="19" />
                        <line x1="5" y1="12" x2="19" y2="12" />
                      </svg>
                    )}
                  </div>
                </button>
              );
            })}
          </div>

          {reports.isError && (
            <div className="gen-error">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="12" cy="12" r="10" /><line x1="12" y1="8" x2="12" y2="12" /><line x1="12" y1="16" x2="12.01" y2="16" />
              </svg>
              {bs ? "Nije moguće učitati sačuvane izvještaje." : "Could not load saved reports."}
            </div>
          )}
        </aside>

        {/* CENTER — PDF Preview */}
        <main className="reports-preview">
          <div className="preview-header">
            <span className="generator-label">{bs ? "Najnoviji izvještaj" : "Latest Report"}</span>
            {latestReport?.id && (
              <a
                className="preview-download"
                href={api.reportPdfUrl(latestReport.id!, false, language)}
                download
              >
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="7 10 12 15 17 10" />
                  <line x1="12" y1="15" x2="12" y2="3" />
                </svg>
                {bs ? "Preuzmi PDF" : "Download PDF"}
              </a>
            )}
          </div>

          {create.isPending ? (
            <div className="preview-empty">
              <LoadingState label={bs ? "Generisanje izvještaja…" : "Generating report…"} />
            </div>
          ) : !latestReport ? (
            <div className="preview-empty">
              <div className="preview-empty-icon">
                <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <polyline points="10 9 9 9 8 9" />
                </svg>
              </div>
              <strong>{bs ? "Još nema izvještaja" : "No report yet"}</strong>
              <p>{bs ? "Generišite ljekarski, porodični ili sedmični sažetak da biste ga pregledali ovdje." : "Generate a doctor, family, or weekly summary to preview it here."}</p>
            </div>
          ) : latestPdfUrl ? (
            <div className="pdf-viewer">
              <iframe
                key={latestReport?.id}
                className="pdf-frame"
                src={latestPdfUrl}
                title={`${latestReport.report_type} report preview`}
              />
            </div>
          ) : null}
        </main>

        {/* RIGHT — Archive */}
        <aside className="reports-archive">
          <div className="archive-header">
            <span className="generator-label">{bs ? "Arhiva" : "Archive"}</span>
            <span className="archive-count">{allReports.length}</span>
          </div>

          <div className="archive-filters">
            {["all", "doctor", "family", "weekly"].map((f) => (
              <button
                key={f}
                className={`archive-filter${activeArchiveType === f ? " active" : ""}`}
                onClick={() => setActiveArchiveType(f)}
              >
                {t(`reports.archive.filter${f[0].toUpperCase() + f.slice(1)}`)}
              </button>
            ))}
          </div>

          <div className="archive-list">
            {reports.isLoading ? (
              <LoadingState label="Loading archive…" />
            ) : filteredArchive.length === 0 ? (
              <div className="archive-empty">{activeArchiveType === "all" ? t("reports.archive.emptyAll") : archiveEmptyText(activeArchiveType, t)}</div>
            ) : (
              filteredArchive.map((report, index) => (
                <button
                  key={`${report.report_type}-${index}`}
                  className={`archive-item${latestReport === report || (previewReport === null && index === 0) ? " archive-item--active" : ""}`}
                  onClick={() => setPreviewReport(report)}
                >
                  <div className="archive-item-top">
                    <span className={`archive-type-dot dot-${report.report_type}`} />
                    <span className="archive-item-type">{reportTypeLabel(report.report_type, t)}</span>
                    {report.created_at && (
                      <span className="archive-item-date">
                        {new Date(report.created_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                      </span>
                    )}
                  </div>
                  <div className="archive-item-title">{report.content.title}</div>
                  {report.id && (
                    <a
                      className="archive-dl"
                      href={api.reportPdfUrl(report.id!, false, language)}
                      download
                      onClick={(e) => e.stopPropagation()}
                    >
                      <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                        <polyline points="7 10 12 15 17 10" />
                        <line x1="12" y1="15" x2="12" y2="3" />
                      </svg>
                      PDF
                    </a>
                  )}
                </button>
              ))
            )}
          </div>
        </aside>
      </div>
    </div>
  );
}
