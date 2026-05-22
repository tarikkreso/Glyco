import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { ErrorState } from "./ui";
import { useToast } from "./ui";

export type LogNewDataValues = {
  glucose_level: number;
  is_fasting: "true" | "false";
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function GlucoseWheel({
  value,
  onChange,
  min = 40,
  max = 500,
  step = 1,
}: {
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number;
}) {
  const itemHeight = 40;
  const values = useMemo(() => {
    const list: number[] = [];
    for (let v = min; v <= max; v += step) list.push(v);
    return list;
  }, [max, min, step]);

  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const lastValueRef = useRef<number>(value);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;

    const index = Math.max(0, values.indexOf(clamp(value, min, max)));
    const top = index * itemHeight;
    if (Math.abs(scroller.scrollTop - top) < 2) return;
    scroller.scrollTo({ top, behavior: "smooth" });
  }, [max, min, value, values]);

  const onScroll = useCallback(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const rawIndex = Math.round(scroller.scrollTop / itemHeight);
    const next = values[clamp(rawIndex, 0, values.length - 1)];
    if (next === undefined || next === lastValueRef.current) return;
    lastValueRef.current = next;
    onChange(next);
  }, [onChange, values]);

  return (
    <div className="wheel-picker" aria-label="Glucose wheel picker">
      <div className="wheel-window" aria-hidden="true" />
      <div className="wheel-scroller" ref={scrollerRef} onScroll={onScroll}>
        {values.map((v) => (
          <div key={v} className={v === value ? "wheel-item selected" : "wheel-item"}>
            {v}
          </div>
        ))}
      </div>
    </div>
  );
}

export function LogNewDataForm({
  userId = 1,
  onSuccess,
}: {
  userId?: number;
  onSuccess?: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();

  const GLUCOSE_MIN = 40;
  const GLUCOSE_MAX = 500;

  const [step, setStep] = useState<"type" | "value">("type");
  const [isFasting, setIsFasting] = useState(true);
  const [glucoseLevel, setGlucoseLevel] = useState(128);
  const [glucoseDraft, setGlucoseDraft] = useState("128");

  const setGlucoseCommitted = useCallback(
    (next: number) => {
      const clamped = clamp(next, GLUCOSE_MIN, GLUCOSE_MAX);
      setGlucoseLevel(clamped);
      setGlucoseDraft(String(clamped));
    },
    [GLUCOSE_MAX, GLUCOSE_MIN]
  );

  const addLog = useMutation({
    mutationFn: (values: LogNewDataValues) =>
      api.addLog({
        user_id: userId,
        glucose_level: values.glucose_level,
        is_fasting: values.is_fasting === "true",
      }),
    onSuccess: () => {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["logs"] }),
        queryClient.invalidateQueries({ queryKey: ["monitoring"] }),
        queryClient.invalidateQueries({ queryKey: ["risk"] }),
        queryClient.invalidateQueries({ queryKey: ["bayesian"] }),
        queryClient.invalidateQueries({ queryKey: ["insight"] }),
        queryClient.invalidateQueries({ queryKey: ["forecast"] }),
        queryClient.invalidateQueries({ queryKey: ["alerts"] }),
      ]);
      setStep("type");
      setGlucoseCommitted(128);
      toast({
        tone: "success",
        title: "Saved",
        body: "Your glucose reading was added successfully.",
      });
      onSuccess?.();
    },
  });

  const submit = () => {
    const parsed = Number(glucoseDraft);
    const nextValue = clamp(
      Number.isFinite(parsed) ? parsed : glucoseLevel,
      GLUCOSE_MIN,
      GLUCOSE_MAX
    );
    setGlucoseCommitted(nextValue);
    addLog.mutate({
      glucose_level: nextValue,
      is_fasting: isFasting ? "true" : "false",
    });
  };

  return (
    <>
      {step === "type" ? (
        <div className="log-step">
          <p className="log-step-title">What are you logging?</p>
          <div className="choice-row">
            <button
              type="button"
              className="secondary choice"
              onClick={() => {
                setIsFasting(true);
                setStep("value");
              }}
            >
              Fasting
            </button>
            <button
              type="button"
              className="secondary choice"
              onClick={() => {
                setIsFasting(false);
                setStep("value");
              }}
            >
              Not fasting
            </button>
          </div>
        </div>
      ) : (
        <form
          className="log-form compact-log-form"
          onSubmit={(event) => {
            event.preventDefault();
            submit();
          }}
        >
          <div className="log-type-row">
            <span>Logging</span>
            <strong>{isFasting ? "Fasting" : "Not fasting"}</strong>
            <button type="button" className="secondary" onClick={() => setStep("type")}>
              Change
            </button>
          </div>

          <label className="span-all">
            <span>Glucose level (mg/dL)</span>
            <div className="number-input-row">
              <button
                type="button"
                className="icon-button"
                aria-label="Increase glucose"
                onClick={() => setGlucoseCommitted(glucoseLevel + 1)}
              >
                <ChevronUp size={18} aria-hidden="true" />
              </button>
              <input
                type="number"
                inputMode="numeric"
                min={GLUCOSE_MIN}
                max={GLUCOSE_MAX}
                step={1}
                value={glucoseDraft}
                onChange={(event) => setGlucoseDraft(event.target.value)}
                onBlur={() => {
                  const parsed = Number(glucoseDraft);
                  if (!Number.isFinite(parsed)) {
                    setGlucoseDraft(String(glucoseLevel));
                    return;
                  }
                  setGlucoseCommitted(parsed);
                }}
              />
              <button
                type="button"
                className="icon-button"
                aria-label="Decrease glucose"
                onClick={() => setGlucoseCommitted(glucoseLevel - 1)}
              >
                <ChevronDown size={18} aria-hidden="true" />
              </button>
            </div>

            <GlucoseWheel value={glucoseLevel} onChange={setGlucoseCommitted} />
          </label>

          <button className="primary span-all" type="submit">
            {addLog.isPending ? "Saving..." : "Save Reading"}
          </button>
        </form>
      )}

      {addLog.isError && (
        <ErrorState
          title="Reading could not be saved"
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
