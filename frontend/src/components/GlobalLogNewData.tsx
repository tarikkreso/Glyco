import { useEffect, useMemo, useState } from "react";
import { Plus, X } from "lucide-react";
import { Card } from "./ui";
import { LogNewDataForm } from "./LogNewDataForm";

export function GlobalLogNewData() {
  const [open, setOpen] = useState(false);

  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);

  useEffect(() => {
    if (!open) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };

    document.addEventListener("keydown", onKeyDown);
    const previousOverflow = document.documentElement.style.overflow;
    document.documentElement.style.overflow = "hidden";

    return () => {
      document.removeEventListener("keydown", onKeyDown);
      document.documentElement.style.overflow = previousOverflow;
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        className="log-fab primary"
        onClick={() => setOpen(true)}
        aria-label="Log new health data"
      >
        <Plus size={18} aria-hidden="true" />
        <span className="log-fab-label">Log data</span>
      </button>

      {open && (
        <div
          className="log-panel-overlay"
          role="dialog"
          aria-modal="true"
          aria-label="Log new data"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setOpen(false);
          }}
        >
          <div className="log-panel" onMouseDown={(event) => event.stopPropagation()}>
            <Card
              title="Log New Data"
              action={
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setOpen(false)}
                  aria-label="Close log form"
                >
                  <X size={18} aria-hidden="true" />
                </button>
              }
            >
              <p className="log-panel-meta">Quick entry for {today}. You can change the date.</p>
              <LogNewDataForm onSuccess={() => setOpen(false)} />
            </Card>
          </div>
        </div>
      )}
    </>
  );
}
