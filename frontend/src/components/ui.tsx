import type { ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useI18n } from "../i18n";

type ToastTone = "success" | "error";

type ToastInput = {
  tone: ToastTone;
  title: string;
  body?: string;
  timeoutMs?: number;
};

type ToastState = {
  tone: ToastTone;
  title: string;
  body?: string;
  timeoutMs: number;
};

const ToastContext = createContext<((toast: ToastInput) => void) | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toast, setToast] = useState<ToastState | null>(null);
  const timeoutHandle = useRef<number | null>(null);
  const { t } = useI18n();

  const dismiss = useCallback(() => {
    setToast(null);
    if (timeoutHandle.current !== null) {
      window.clearTimeout(timeoutHandle.current);
      timeoutHandle.current = null;
    }
  }, []);

  const showToast = useCallback(
    (input: ToastInput) => {
      const timeoutMs = input.timeoutMs ?? (input.tone === "error" ? 5000 : 3500);
      setToast({ tone: input.tone, title: input.title, body: input.body, timeoutMs });

      if (timeoutHandle.current !== null) window.clearTimeout(timeoutHandle.current);
      timeoutHandle.current = window.setTimeout(() => {
        setToast(null);
        timeoutHandle.current = null;
      }, timeoutMs);
    },
    []
  );

  useEffect(() => {
    return () => {
      if (timeoutHandle.current !== null) window.clearTimeout(timeoutHandle.current);
    };
  }, []);

  return (
    <ToastContext.Provider value={showToast}>
      {children}
      {toast && (
        <div className="toast-host" aria-live="polite" aria-atomic="true">
          <button
            type="button"
            className={`toast toast-${toast.tone}`}
            onClick={dismiss}
            aria-label={t("common.dismiss")}
          >
            <strong>{toast.title}</strong>
            {toast.body && <p>{toast.body}</p>}
          </button>
        </div>
      )}
    </ToastContext.Provider>
  );
}

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within a ToastProvider");
  return ctx;
}

export function PageHeader({ title, subtitle, meta, action }: { title: string; subtitle: string; meta?: string; action?: ReactNode }) {
  return (
    <div className="page-header">
      <div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      {(meta || action) && (
        <div className="page-header-actions">
          {meta && <span className="meta">{meta}</span>}
          {action}
        </div>
      )}
    </div>
  );
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

export function SuccessState({ title, body }: { title: string; body: string }) {
  return <div className="success-state"><strong>{title}</strong><p>{body}</p></div>;
}

export function LoadingState({ label = "Loading" }: { label?: string }) {
  const { t } = useI18n();
  return <div className="loading-state" aria-live="polite"><span className="loading-dot" />{label === "Loading" ? t("common.loading") : label}</div>;
}
