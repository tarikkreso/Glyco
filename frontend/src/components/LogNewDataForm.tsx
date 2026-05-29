import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import { useI18n } from "../i18n";
import { ErrorState } from "./ui";
import { useToast } from "./ui";
import { displayInputFromMgdl, glucoseInputConfig, mgdlFromDisplayInput, useGlucoseUnit } from "../utils/glucoseUnits";

export type LogNewDataValues = {
  glucose_level: number;
  is_fasting: "true" | "false";
  reading_time: string;
};

function clamp(value: number, min: number, max: number) {
  return Math.max(min, Math.min(max, value));
}

function datetimeLocalValue(date: Date) {
  const pad = (value: number) => String(value).padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
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
  const { t } = useI18n();
  const itemHeight = 40;
  const values = useMemo(() => {
    const list: number[] = [];
    for (let v = min; v <= max + step / 2; v += step) list.push(Number(v.toFixed(1)));
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
    <div className="wheel-picker" aria-label={t("log.glucoseWheel")}>
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
  const { t } = useI18n();
  const { unit } = useGlucoseUnit();
  const inputConfig = glucoseInputConfig(unit);

  const [step, setStep] = useState<"type" | "value">("type");
  const [isFasting, setIsFasting] = useState(true);
  const [glucoseLevel, setGlucoseLevel] = useState(inputConfig.defaultValue);
  const [glucoseDraft, setGlucoseDraft] = useState(String(inputConfig.defaultValue));
  const [readingTime, setReadingTime] = useState(() => datetimeLocalValue(new Date()));
  const previousUnitRef = useRef(unit);

  useEffect(() => {
    const previousUnit = previousUnitRef.current;
    if (previousUnit === unit) return;
    const currentMgdl = mgdlFromDisplayInput(glucoseLevel, previousUnit);
    const next = displayInputFromMgdl(currentMgdl, unit);
    setGlucoseLevel(next);
    setGlucoseDraft(String(next));
    previousUnitRef.current = unit;
  }, [glucoseLevel, unit]);

  const setGlucoseCommitted = useCallback(
    (next: number) => {
      const clamped = clamp(next, inputConfig.min, inputConfig.max);
      setGlucoseLevel(clamped);
      setGlucoseDraft(String(clamped));
    },
    [inputConfig.max, inputConfig.min]
  );

  const addLog = useMutation({
    mutationFn: (values: LogNewDataValues) =>
      api.addLog({
        user_id: userId,
        glucose_level: values.glucose_level,
        is_fasting: values.is_fasting === "true",
        reading_time: values.reading_time,
      }),
    onSuccess: () => {
      void Promise.all([
        queryClient.invalidateQueries({ queryKey: ["logs"] }),
        queryClient.invalidateQueries({ queryKey: ["monitoring"] }),
        queryClient.invalidateQueries({ queryKey: ["risk"] }),
        queryClient.invalidateQueries({ queryKey: ["bayesian"] }),
        queryClient.invalidateQueries({ queryKey: ["insight"] }),
        queryClient.invalidateQueries({ queryKey: ["forecast"] }),
        queryClient.invalidateQueries({ queryKey: ["forecast-accuracy"] }),
        queryClient.invalidateQueries({ queryKey: ["alerts"] }),
      ]);
      setStep("type");
      setGlucoseCommitted(inputConfig.defaultValue);
      setReadingTime(datetimeLocalValue(new Date()));
      toast({
        tone: "success",
        title: t("log.savedTitle"),
        body: t("log.savedBody"),
      });
      onSuccess?.();
    },
  });

  const submit = () => {
    const parsed = Number(glucoseDraft);
    const nextValue = clamp(
      Number.isFinite(parsed) ? parsed : glucoseLevel,
      inputConfig.min,
      inputConfig.max
    );
    setGlucoseCommitted(nextValue);
    addLog.mutate({
      glucose_level: Math.round(mgdlFromDisplayInput(nextValue, unit)),
      is_fasting: isFasting ? "true" : "false",
      reading_time: readingTime,
    });
  };

  return (
    <>
      {step === "type" ? (
        <div className="log-step">
          <p className="log-step-title">{t("log.typeQuestion")}</p>
          <div className="choice-row">
            <button
              type="button"
              className="secondary choice"
              onClick={() => {
                setIsFasting(true);
                setStep("value");
              }}
            >
              {t("log.fasting")}
            </button>
            <button
              type="button"
              className="secondary choice"
              onClick={() => {
                setIsFasting(false);
                setStep("value");
              }}
            >
              {t("log.notFasting")}
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
            <span>{t("log.logging")}</span>
            <strong>{isFasting ? t("log.fasting") : t("log.notFasting")}</strong>
            <button type="button" className="secondary" onClick={() => setStep("type")}>
              {t("log.change")}
            </button>
          </div>

          <label className="span-all">
            <span>{t("log.glucoseLevel")} ({unit === "mgdl" ? "mg/dL" : "mmol/L"})</span>
            <div className="number-input-row">
              <button
                type="button"
                className="icon-button"
                aria-label={t("log.increaseGlucose")}
                onClick={() => setGlucoseCommitted(glucoseLevel + inputConfig.step)}
              >
                <ChevronUp size={18} aria-hidden="true" />
              </button>
              <input
                type="number"
                inputMode="numeric"
                min={inputConfig.min}
                max={inputConfig.max}
                step={inputConfig.step}
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
                aria-label={t("log.decreaseGlucose")}
                onClick={() => setGlucoseCommitted(glucoseLevel - inputConfig.step)}
              >
                <ChevronDown size={18} aria-hidden="true" />
              </button>
            </div>

            <GlucoseWheel value={glucoseLevel} onChange={setGlucoseCommitted} min={inputConfig.min} max={inputConfig.max} step={inputConfig.step} />
          </label>

          <label className="span-all">
            <span>{t("log.readingTime")}</span>
            <input
              type="datetime-local"
              value={readingTime}
              max={datetimeLocalValue(new Date())}
              onChange={(event) => setReadingTime(event.target.value)}
            />
          </label>

          <button className="primary span-all" type="submit">
            {addLog.isPending ? t("log.saving") : t("log.save")}
          </button>
        </form>
      )}

      {addLog.isError && (
        <ErrorState
          title={t("log.errorTitle")}
          body={
            addLog.error instanceof Error
              ? addLog.error.message
              : t("log.errorBody")
          }
        />
      )}
    </>
  );
}
