import { createPortal } from "react-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useToast } from "./ui";
import { Info } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { api } from "../api/client";
import { ErrorState } from "./ui";

export type LogNewDataValues = {
  log_date: string;
  fasting_glucose: number;
  post_meal_glucose: number;
  systolic_bp: number;
  diastolic_bp: number;
  activity_minutes: number;
  notes: string;
};

export function LogNewDataForm({
  userId = 1,
  onSuccess,
}: {
  userId?: number;
  onSuccess?: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [openHelp, setOpenHelp] = useState<{ key: string; rect: DOMRect } | null>(null);

  const helpText = useMemo(
    () => ({
      log_date: "Choose the date the measurements were taken.",
      fasting_glucose: "Enter fasting glucose (mg/dL), ideally after ~8 hours without food.",
      post_meal_glucose: "Enter glucose (mg/dL) about 1–2 hours after a meal.",
      systolic_bp: "Enter the top blood pressure number (systolic, mmHg).",
      diastolic_bp: "Enter the bottom blood pressure number (diastolic, mmHg).",
      activity_minutes: "Enter minutes of activity (e.g., walking/exercise) for the day.",
      notes: "Optional: add context like meals, meds, symptoms, stress, or sleep.",
    }),
    []
  );

  const toggleHelp = useCallback((key: string, btn: HTMLButtonElement) => {
    setOpenHelp((current) =>
      current?.key === key ? null : { key, rect: btn.getBoundingClientRect() }
    );
  }, []);

  const { register, handleSubmit, reset } = useForm<LogNewDataValues>({
    defaultValues: {
      log_date: new Date().toISOString().slice(0, 10),
      fasting_glucose: 128,
      post_meal_glucose: 164,
      systolic_bp: 136,
      diastolic_bp: 86,
      activity_minutes: 25,
      notes: "",
    },
  });

  const addLog = useMutation({
    mutationFn: (values: LogNewDataValues) => api.addLog({ user_id: userId, ...values }),
    onSuccess: async () => {
      await api.assessMonitoring(userId);
      await queryClient.invalidateQueries();
      reset();
      toast({
        tone: "success",
        title: "Saved",
        body: "Your log entry was added successfully.",
      });
      onSuccess?.();
    },
  });

  function HelpPopover({ field }: { field: keyof typeof helpText }) {
    return (
      <>
        <button
          type="button"
          className="help-icon"
          onClick={(e) => toggleHelp(field, e.currentTarget)}
          aria-label={`Help: ${field}`}
          aria-expanded={openHelp?.key === field}
          aria-controls={`help-${field}`}
        >
          <Info size={14} aria-hidden="true" />
        </button>
        {openHelp?.key === field &&
          createPortal(
            <span
              id={`help-${field}`}
              className="field-help-popover"
              role="note"
              style={(() => {
                const isMobile = window.innerWidth <= 860;
                const popoverWidth = isMobile ? Math.min(320, window.innerWidth - 16) : 320;
                const fitsOnRight = openHelp.rect.right + popoverWidth <= window.innerWidth - 8;
                return {
                  position: "fixed" as const,
                  top: openHelp.rect.bottom + 8,
                  width: isMobile ? popoverWidth : undefined,
                  ...(fitsOnRight
                    ? { right: Math.max(8, window.innerWidth - openHelp.rect.right), left: "auto" }
                    : { left: Math.max(8, openHelp.rect.left - popoverWidth + openHelp.rect.width), right: "auto" }),
                };
              })()}
            >
              {helpText[field]}
            </span>,
            document.body
          )}
      </>
    );
  }

  return (
    <>
      <form
        className="log-form"
        onSubmit={handleSubmit((values) => addLog.mutate(values))}
        onMouseDownCapture={(event) => {
          if (!openHelp?.key) return;
          const target = event.target as HTMLElement;
          if (target.closest(".help-icon") || target.closest(".field-help-popover")) return;
          setOpenHelp(null);
        }}
        onTouchStartCapture={(event) => {
          if (!openHelp?.key) return;
          const target = event.target as HTMLElement;
          if (target.closest(".help-icon") || target.closest(".field-help-popover")) return;
          setOpenHelp(null);
        }}
      >
        <label className="span-all">
          <span className="label-row">
            <span>Date</span>
            <span className="help-wrap"><HelpPopover field="log_date" /></span>
          </span>
          <input type="date" {...register("log_date")} />
        </label>

        <label>
          <span className="label-row">
            <span>Fasting glucose</span>
            <span className="help-wrap"><HelpPopover field="fasting_glucose" /></span>
          </span>
          <input type="number" inputMode="numeric" {...register("fasting_glucose", { valueAsNumber: true })} />
        </label>

        <label>
          <span className="label-row">
            <span>Post-meal glucose</span>
            <span className="help-wrap"><HelpPopover field="post_meal_glucose" /></span>
          </span>
          <input type="number" inputMode="numeric" {...register("post_meal_glucose", { valueAsNumber: true })} />
        </label>

        <label>
          <span className="label-row">
            <span>Systolic BP</span>
            <span className="help-wrap"><HelpPopover field="systolic_bp" /></span>
          </span>
          <input type="number" inputMode="numeric" {...register("systolic_bp", { valueAsNumber: true })} />
        </label>

        <label>
          <span className="label-row">
            <span>Diastolic BP</span>
            <span className="help-wrap"><HelpPopover field="diastolic_bp" /></span>
          </span>
          <input type="number" inputMode="numeric" {...register("diastolic_bp", { valueAsNumber: true })} />
        </label>

        <label>
          <span className="label-row">
            <span>Activity minutes</span>
            <span className="help-wrap"><HelpPopover field="activity_minutes" /></span>
          </span>
          <input type="number" inputMode="numeric" {...register("activity_minutes", { valueAsNumber: true })} />
        </label>

        <label className="span-all">
          <span className="label-row">
            <span>Notes (optional)</span>
            <span className="help-wrap"><HelpPopover field="notes" /></span>
          </span>
          <textarea rows={3} {...register("notes")} />
        </label>

        <button className="primary" type="submit">
          {addLog.isPending ? "Saving..." : "Save Log"}
        </button>
      </form>

      {addLog.isError && (
        <ErrorState
          title="Log could not be saved"
          body={
            addLog.error instanceof Error
              ? addLog.error.message
              : "The monitoring API rejected the new entry. Please try again."
          }
        />
      )}
    </>
  );
}