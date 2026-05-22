import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Apple,
  CalendarDays,
  CheckCircle2,
  ChefHat,
  Clock3,
  Database,
  RefreshCw,
  ShieldCheck,
  Sparkles,
  Utensils,
  XCircle,
} from "lucide-react";
import { api } from "../api/client";
import { useAuth } from "../auth/auth";
import { Badge, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";

function percent(value?: number) {
  return typeof value === "number" ? `${Math.round(value * 100)}%` : "-";
}

function readingKind(value?: boolean) {
  if (value === true) return "fasting";
  if (value === false) return "not fasting";
  return "not labeled";
}

function sourceLabel(source?: string) {
  if (source === "gemini-personalized") return "Gemini Personalized";
  if (source === "deepseek-personalized") return "DeepSeek Personalized";
  if (source === "liquid-personalized") return "Liquid Personalized";
  if (source === "data-fallback" || source === "data-personalized-fallback") return "Data Personalized (Fallback)";
  return source ?? "Data generated";
}

const mealLabels = ["Breakfast", "Lunch", "Dinner", "Snack"];

function renderMealText(item: string) {
  const lines = item.split("\n");
  const parsedElements: React.ReactNode[] = [];
  let inList = false;
  let listItems: string[] = [];

  lines.forEach((line, index) => {
    const trimmed = line.trim();
    if (trimmed.startsWith("-") || trimmed.startsWith("*")) {
      if (!inList) {
        inList = true;
        listItems = [];
      }
      listItems.push(trimmed.substring(1).trim());
    } else {
      if (inList) {
        parsedElements.push(
          <ul key={`list-${index}`} style={{ margin: "8px 0", paddingLeft: "16px", listStyleType: "disc" }}>
            {listItems.map((li, liIdx) => (
              <li key={liIdx} style={{ marginBottom: "2px", fontWeight: "normal", color: "var(--text)" }}>{li}</li>
            ))}
          </ul>
        );
        inList = false;
      }
      
      if (trimmed) {
        if (index === 0 && (trimmed.endsWith(":") || trimmed.length < 50)) {
          parsedElements.push(
            <h4 key={`header-${index}`} style={{ fontWeight: 800, fontSize: "14px", margin: "0 0 6px 0", color: "var(--primary)" }}>
              {trimmed.endsWith(":") ? trimmed.slice(0, -1) : trimmed}
            </h4>
          );
        } else {
          parsedElements.push(
            <p key={`p-${index}`} style={{ margin: "6px 0", fontSize: "13px", fontWeight: "normal", color: "var(--muted)", lineHeight: "1.4" }}>
              {trimmed}
            </p>
          );
        }
      }
    }
  });

  if (inList) {
    parsedElements.push(
      <ul key="list-end" style={{ margin: "8px 0", paddingLeft: "16px", listStyleType: "disc" }}>
        {listItems.map((li, liIdx) => (
          <li key={liIdx} style={{ marginBottom: "2px", fontWeight: "normal", color: "var(--text)" }}>{li}</li>
        ))}
      </ul>
    );
  }

  return <div style={{ display: "flex", flexDirection: "column", gap: "2px" }}>{parsedElements}</div>;
}

export function CarePlan() {
  const auth = useAuth();
  const userId = auth.session?.userId ?? 1;
  const queryClient = useQueryClient();
  const [isGenerating, setIsGenerating] = useState(false);

  const plan = useQuery({
    queryKey: ["diet", userId],
    queryFn: () => api.diet(userId, false),
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });

  const handleGenerate = async () => {
    setIsGenerating(true);
    try {
      const freshData = await api.diet(userId, true);
      queryClient.setQueryData(["diet", userId], freshData);
    } catch (e) {
      console.error("Failed to generate meal plan", e);
    } finally {
      setIsGenerating(false);
    }
  };
  const prefer = (plan.data?.prefer as string[]) ?? [];
  const limit = (plan.data?.limit as string[]) ?? [];
  const sample = (plan.data?.sample_day as string[]) ?? [];
  const weekly = (plan.data?.weekly_recommendations as string[]) ?? [];
  const signals = plan.data?.signals;
  const generatedAt = plan.dataUpdatedAt
    ? new Date(plan.dataUpdatedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
    : "not generated";
  const latestReading = signals?.latest_glucose ? `${signals.latest_glucose} mg/dL` : "-";
  const source = sourceLabel(plan.data?.source);

  return (
    <div className="page care-plan-page">
      <PageHeader
        title="Care Plan"
        subtitle="Generate a patient-specific meal plan from the latest glucose reading, RF model signals, Bayesian risk, and learned feedback."
        meta={`Meal plan source: ${source}`}
      />

      {plan.isError && <ErrorState title="Care plan is unavailable" body="Glyco could not generate the meal plan from the current patient data." />}

      <section className="care-plan-hero">
        <div className="care-plan-hero-copy">
          <span className="generator-kicker"><ChefHat size={16} /> Real meal plan generator</span>
          <h2>{String(plan.data?.direction ?? "Generate a plan from the newest patient data")}</h2>
          <p>
            This screen calls the care-plan API and rebuilds the meal plan from current readings, risk assessment,
            glucose trend, Bayesian posterior, and Thompson recommendation learning.
          </p>
          <div className="care-plan-action-row">
            <button type="button" className="generate-plan-button" onClick={handleGenerate} disabled={isGenerating || plan.isFetching}>
              <RefreshCw size={18} className={(isGenerating || plan.isFetching) ? "spin-icon" : undefined} />
              {(isGenerating || plan.isFetching) ? "Generating" : "Generate meal plan"}
            </button>
            <Badge tone={plan.data?.source?.endsWith("-personalized") ? "good" : "warning"}>{source}</Badge>
            <small><Clock3 size={14} /> Updated {generatedAt}</small>
          </div>
        </div>
        <div className="care-plan-signal-board">
          <div><span>Latest reading</span><strong>{latestReading}</strong><small>{readingKind(signals?.latest_is_fasting)}</small></div>
          <div><span>RF risk</span><strong>{signals?.risk_level ?? "-"}</strong><small>{signals?.risk_model_version ?? "loading"}</small></div>
          <div><span>Trend</span><strong>{signals?.trend_label ?? "-"}</strong><small>{signals?.trend_model_version ?? "loading"}</small></div>
          <div><span>Bayesian risk</span><strong>{percent(signals?.bayesian_posterior)}</strong><small>posterior mean</small></div>
        </div>
      </section>

      {plan.isLoading ? (
        <LoadingState label="Generating care plan from profile, logs, models, and learning memory" />
      ) : (
        <>
          <section className="meal-plan-section">
            <div className="section-heading">
              <span><Utensils size={16} /> Generated today</span>
              <h2>Patient-specific meal plan</h2>
              <p>These meals come from the current care-plan response, not a static frontend template.</p>
            </div>
            {sample.length ? (
              <div className="meal-plan-grid">
                {sample.map((item, index) => (
                  <article className="meal-plan-card" key={`${item}-${index}`}>
                    <div>
                      <span>{mealLabels[index] ?? `Meal ${index + 1}`}</span>
                      <ChefHat size={20} />
                    </div>
                    {renderMealText(item)}
                  </article>
                ))}
              </div>
            ) : <EmptyState title="No meal plan yet" body="Generate a plan after the patient has at least one glucose reading." />}
          </section>

          <div className="care-plan-grid">
            <section className="care-plan-panel">
              <header><Apple size={20} /><h2>Prefer</h2></header>
              <ul className="care-plan-list positive">
                {prefer.map((item) => <li key={item}><CheckCircle2 size={17} />{item}</li>)}
              </ul>
            </section>
            <section className="care-plan-panel">
              <header><XCircle size={20} /><h2>Limit</h2></header>
              <ul className="care-plan-list caution">
                {limit.map((item) => <li key={item}><XCircle size={17} />{item}</li>)}
              </ul>
            </section>
          </div>

          <section className="care-plan-panel weekly-panel">
            <header><CalendarDays size={20} /><h2>Weekly plan</h2></header>
            <div className="weekly-action-grid">
              {weekly.map((item, index) => (
                <div key={`${item}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><p>{item}</p></div>
              ))}
            </div>
          </section>

          <section className="care-plan-evidence">
            <div className="section-heading">
              <span><Database size={16} /> Why this changed</span>
              <h2>Live patient signals used</h2>
            </div>
            <div className="model-evidence-list">
              <div><span>Reading type</span><strong>{readingKind(signals?.latest_is_fasting)}</strong><small>{latestReading}</small></div>
              <div><span>Average fasting</span><strong>{signals?.avg_fasting ? `${signals.avg_fasting} mg/dL` : "-"}</strong><small>recent logs</small></div>
              <div><span>Average post-meal</span><strong>{signals?.avg_post_meal ? `${signals.avg_post_meal} mg/dL` : "-"}</strong><small>recent logs</small></div>
              <div><span>Learned focus</span><strong>{signals?.top_recommendation_type ?? "-"}</strong><small>Thompson ranker</small></div>
            </div>
            <p className="care-plan-safety"><ShieldCheck size={16} /> This is supportive diabetes tracking guidance. It does not replace clinician nutrition advice or medication changes.</p>
          </section>

          {plan.isFetching && <div className="care-plan-refreshing"><Sparkles size={16} /> Updating meal plan from latest backend data...</div>}
        </>
      )}
    </div>
  );
}
