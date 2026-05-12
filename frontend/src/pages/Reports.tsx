import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";

const reportTypes = ["doctor", "family", "weekly"];

export function Reports() {
  const queryClient = useQueryClient();
  const reports = useQuery({ queryKey: ["reports"], queryFn: () => api.reports() });
  const create = useMutation({ mutationFn: (type: string) => api.report(type), onSuccess: () => queryClient.invalidateQueries({ queryKey: ["reports"] }) });
  return (
    <div className="page">
      <PageHeader title="Reports" subtitle="Template-based summaries for clinical review, weekly reflection, and family support." />
      {reports.isError && <ErrorState title="Reports are unavailable" body="Glyco could not load the stored report list." />}
      <div className="report-grid">
        {reportTypes.map((type) => (
          <Card key={type} title={`${type[0].toUpperCase()}${type.slice(1)} Summary`}>
            <p>Generate a concise Glyco report using the latest risk assessment, monitoring state, and health logs.</p>
            <button className="primary" onClick={() => create.mutate(type)}>{create.isPending ? "Generating..." : "Generate Report"}</button>
          </Card>
        ))}
      </div>
      {create.isError && <ErrorState title="Report generation failed" body="The backend did not return a report document." />}
      <div className="report-grid">
        {reports.isLoading ? (
          <Card title="Report Preview"><LoadingState label="Loading saved reports" /></Card>
        ) : !(reports.data ?? []).length ? (
          <Card title="Report Preview"><EmptyState title="No saved reports yet" body="Generate a doctor, family, or weekly summary to populate the document shelf." /></Card>
        ) : (
          (reports.data ?? []).map((report, index) => (
            <Card key={`${report.report_type}-${index}`} title={report.content.title}>
              <div className="document-preview">
                {report.created_at && <div className="report-meta">Created {new Date(report.created_at).toLocaleString()}</div>}
                {report.content.sections.map((section) => <section key={section.title}><h3>{section.title}</h3><p>{section.body}</p></section>)}
                {report.content.disclaimer && <p className="disclaimer">{report.content.disclaimer}</p>}
                {report.id && <a className="secondary download-link" href={api.reportPdfUrl(report.id)}>Download PDF</a>}
              </div>
            </Card>
          ))
        )}
      </div>
    </div>
  );
}
