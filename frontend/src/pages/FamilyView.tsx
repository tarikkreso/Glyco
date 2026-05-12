import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckSquare, Heart } from "lucide-react";
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api/client";
import { Card, PageHeader } from "../components/ui";

export function FamilyView() {
  const share = useQuery({ queryKey: ["family-share"], queryFn: () => api.familyShare() });
  const data = share.data as any;
  const logs = data?.logs ?? [];
  const monitoring = data?.monitoring;
  return (
    <div className="page">
      <PageHeader title="Family Support View" subtitle={`Simplified health summary for ${data?.user?.full_name ?? "Sarah"}'s care circle.`} meta="Last updated: Today, 09:42 AM" />
      <div className="family-grid">
        <div className="family-main">
          <Card title="Current Status">
            <div className="status-callout"><div><Heart size={38} /></div><section><h2>{monitoring?.trend_label === "concerning" ? "Attention Needed" : "Stable & Trending Well"}</h2><p>Recent readings are summarized for family support. Use this view to help with reminders and care routines.</p></section></div>
          </Card>
          <Card title="Weekly Glucose Trend">
            <div className="chart-box family-chart">
              <ResponsiveContainer width="100%" height={260}>
                <LineChart data={logs}><XAxis dataKey="log_date" hide /><YAxis hide /><Tooltip /><Line dataKey="fasting_glucose" stroke="#3ba4aa" strokeWidth={4} dot={{ r: 4 }} /></LineChart>
              </ResponsiveContainer>
            </div>
          </Card>
        </div>
        <div className="family-side">
          <Card title="Attention Needed" action={<AlertTriangle size={18} />}>
            <div className="alert-list">{(monitoring?.anomaly_flags ?? [{ label: "Upcoming Appointment", detail: "Endocrinologist checkup next Tuesday at 10:00 AM.", level: "neutral" }]).map((flag: any) => <div key={flag.label} className={flag.level}><strong>{flag.label}</strong><span>{flag.detail}</span></div>)}</div>
          </Card>
          <Card title="How You Can Help Today">
            <ul className="help-list">
              <li><CheckSquare size={16} /> Remind about post-lunch walk<span>A 15-minute walk helps stabilize afternoon levels.</span></li>
              <li><CheckSquare size={16} /> Verify evening medication<span>Check pillbox around 8:00 PM.</span></li>
              <li><CheckSquare size={16} /> Prepare low-carb snack<span>For the afternoon slump.</span></li>
            </ul>
          </Card>
        </div>
      </div>
    </div>
  );
}
