import type { ReactNode } from "react";

export function PageHeader({ title, subtitle, meta }: { title: string; subtitle: string; meta?: string }) {
  return <div className="page-header"><div><h1>{title}</h1><p>{subtitle}</p></div>{meta && <span className="meta">{meta}</span>}</div>;
}

export function Card({ title, children, action }: { title?: string; children: ReactNode; action?: ReactNode }) {
  return <section className="card">{title && <header><h2>{title}</h2>{action}</header>}<div className="card-body">{children}</div></section>;
}

export function StatCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  return <div className="stat-card"><span>{label}</span><strong>{value}</strong><small>{detail}</small></div>;
}

export function Badge({ tone = "neutral", children }: { tone?: "neutral" | "good" | "warning" | "danger"; children: ReactNode }) {
  return <span className={`badge ${tone}`}>{children}</span>;
}

export function FactorList({ items }: { items: Array<{ label: string; detail: string; impact?: number }> }) {
  return <div className="factor-list">{items.map((item) => <div key={item.label}><strong>{item.label}</strong><span>{item.detail}</span>{item.impact !== undefined && <em>{item.impact}</em>}</div>)}</div>;
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return <div className="empty-state"><strong>{title}</strong><p>{body}</p></div>;
}

export function ErrorState({ title, body }: { title: string; body: string }) {
  return <div className="error-state"><strong>{title}</strong><p>{body}</p></div>;
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return <div className="loading-state" aria-live="polite"><span className="loading-dot" />{label}</div>;
}
