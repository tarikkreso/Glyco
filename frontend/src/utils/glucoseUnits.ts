import { useEffect, useState } from "react";

export type GlucoseUnit = "mmol" | "mgdl";

const GLUCOSE_UNIT_KEY = "glyco_glucose_unit_v1";
const MGDL_PER_MMOL = 18.01559;

export function mgdlToMmol(value: number) {
  return value / MGDL_PER_MMOL;
}

export function mmolToMgdl(value: number) {
  return value * MGDL_PER_MMOL;
}

export function normalizeGlucoseUnit(value: string | null): GlucoseUnit {
  return value === "mgdl" ? "mgdl" : "mmol";
}

export function getStoredGlucoseUnit(): GlucoseUnit {
  if (typeof window === "undefined") return "mmol";
  return normalizeGlucoseUnit(window.localStorage.getItem(GLUCOSE_UNIT_KEY));
}

export function setStoredGlucoseUnit(unit: GlucoseUnit) {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(GLUCOSE_UNIT_KEY, unit);
  window.dispatchEvent(new CustomEvent("glyco-glucose-unit-change", { detail: unit }));
}

export function useGlucoseUnit() {
  const [unit, setUnitState] = useState<GlucoseUnit>(getStoredGlucoseUnit);

  useEffect(() => {
    const sync = () => setUnitState(getStoredGlucoseUnit());
    window.addEventListener("storage", sync);
    window.addEventListener("glyco-glucose-unit-change", sync);
    return () => {
      window.removeEventListener("storage", sync);
      window.removeEventListener("glyco-glucose-unit-change", sync);
    };
  }, []);

  const setUnit = (next: GlucoseUnit) => {
    setStoredGlucoseUnit(next);
    setUnitState(next);
  };

  return { unit, setUnit };
}

export function formatGlucoseFromMgdl(value?: number | null, unit: GlucoseUnit = "mmol") {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  if (unit === "mgdl") return `${Math.round(value)} mg/dL`;
  return `${mgdlToMmol(value).toFixed(1)} mmol/L`;
}

export function formatGlucoseFromMmol(value?: number | null, unit: GlucoseUnit = "mmol") {
  if (typeof value !== "number" || Number.isNaN(value)) return "-";
  if (unit === "mgdl") return `${Math.round(mmolToMgdl(value))} mg/dL`;
  return `${value.toFixed(1)} mmol/L`;
}

export function glucoseInputConfig(unit: GlucoseUnit) {
  return unit === "mgdl"
    ? { min: 40, max: 500, step: 1, defaultValue: 128 }
    : { min: 2.2, max: 27.8, step: 0.1, defaultValue: 7.1 };
}

export function displayInputFromMgdl(value: number, unit: GlucoseUnit) {
  return unit === "mgdl" ? Math.round(value) : Number(mgdlToMmol(value).toFixed(1));
}

export function mgdlFromDisplayInput(value: number, unit: GlucoseUnit) {
  return unit === "mgdl" ? value : mmolToMgdl(value);
}
