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
import { useI18n } from "../i18n";

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
  const { language, t } = useI18n();
  const bs = language === "bs";
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
        title={t("carePlan.title")}
        subtitle={t("carePlan.subtitle")}
        meta={`${t("carePlan.metaSource")}: ${source}`}
      />

      {plan.isError && <ErrorState title={t("carePlan.unavailableTitle")} body={t("carePlan.unavailableBody")} />}

      <section className="care-plan-hero">
        <div className="care-plan-hero-copy">
          <span className="generator-kicker"><ChefHat size={16} /> {t("carePlan.generatorKicker")}</span>
          <h2>{String(plan.data?.direction ?? t("carePlan.generatePrompt"))}</h2>
          <p>{t("carePlan.description")}</p>
          <div className="care-plan-action-row">
            <button type="button" className="generate-plan-button" onClick={handleGenerate} disabled={isGenerating || plan.isFetching}>
              <RefreshCw size={18} className={(isGenerating || plan.isFetching) ? "spin-icon" : undefined} />
              {(isGenerating || plan.isFetching) ? t("carePlan.generating") : t("carePlan.generateButton")}
            </button>
            <Badge tone={plan.data?.source?.endsWith("-personalized") ? "good" : "warning"}>{source}</Badge>
            <small><Clock3 size={14} /> {t("carePlan.updated")} {generatedAt}</small>
          </div>
        </div>
        <div className="care-plan-signal-board">
          <div><span>{t("carePlan.latestReading")}</span><strong>{latestReading}</strong><small>{readingKind(signals?.latest_is_fasting)}</small></div>
          <div><span>{t("carePlan.rfRisk")}</span><strong>{signals?.risk_level ?? "-"}</strong><small>{signals?.risk_model_version ?? (bs ? "učitavanje" : "loading")}</small></div>
          <div><span>{t("carePlan.trend")}</span><strong>{signals?.trend_label ?? "-"}</strong><small>{signals?.trend_model_version ?? (bs ? "učitavanje" : "loading")}</small></div>
          <div><span>{t("carePlan.bayesianRisk")}</span><strong>{percent(signals?.bayesian_posterior)}</strong><small>{t("carePlan.posteriorMean")}</small></div>
        </div>
      </section>

      {plan.isLoading ? (
        <LoadingState label={t("carePlan.updating")} />
      ) : (
        <>
          <section className="meal-plan-section">
            <div className="section-heading">
              <span><Utensils size={16} /> {t("carePlan.generatedToday")}</span>
              <h2>{t("carePlan.patientSpecificMealPlan")}</h2>
              <p>{t("carePlan.mealsFromResponse")}</p>
            </div>
            {sample.length ? (
              <div className="meal-plan-grid">
                {sample.map((item, index) => (
                  <article className="meal-plan-card" key={`${item}-${index}`}>
                    <div>
                      <span>{mealLabels[index] ?? `${bs ? "Obrok" : "Meal"} ${index + 1}`}</span>
                      <ChefHat size={20} />
                    </div>
                    {renderMealText(item)}
                  </article>
                ))}
              </div>
            ) : <EmptyState title={t("carePlan.noMealPlanTitle")} body={t("carePlan.noMealPlanBody")} />}
          </section>

          <div className="care-plan-grid">
            <section className="care-plan-panel">
              <header><Apple size={20} /><h2>{t("carePlan.prefer")}</h2></header>
              <ul className="care-plan-list positive">
                {prefer.map((item) => <li key={item}><CheckCircle2 size={17} />{item}</li>)}
              </ul>
            </section>
            <section className="care-plan-panel">
              <header><XCircle size={20} /><h2>{t("carePlan.limit")}</h2></header>
              <ul className="care-plan-list caution">
                {limit.map((item) => <li key={item}><XCircle size={17} />{item}</li>)}
              </ul>
            </section>
          </div>

          <section className="care-plan-panel weekly-panel">
            <header><CalendarDays size={20} /><h2>{t("carePlan.weeklyPlan")}</h2></header>
            <div className="weekly-action-grid">
              {weekly.map((item, index) => (
                <div key={`${item}-${index}`}><span>{String(index + 1).padStart(2, "0")}</span><p>{item}</p></div>
              ))}
            </div>
          </section>

          <section className="care-plan-evidence">
            <div className="section-heading">
              <span><Database size={16} /> {t("carePlan.whyThisChanged")}</span>
              <h2>{t("carePlan.liveSignalsUsed")}</h2>
            </div>
            <div className="model-evidence-list">
              <div><span>{t("carePlan.readingType")}</span><strong>{readingKind(signals?.latest_is_fasting)}</strong><small>{latestReading}</small></div>
              <div><span>{t("carePlan.avgFasting")}</span><strong>{signals?.avg_fasting ? `${signals.avg_fasting} mg/dL` : "-"}</strong><small>{bs ? "nedavni zapisi" : "recent logs"}</small></div>
              <div><span>{t("carePlan.avgPostMeal")}</span><strong>{signals?.avg_post_meal ? `${signals.avg_post_meal} mg/dL` : "-"}</strong><small>{bs ? "nedavni zapisi" : "recent logs"}</small></div>
              <div><span>{t("carePlan.learnedFocus")}</span><strong>{signals?.top_recommendation_type ?? "-"}</strong><small>{t("carePlan.thompsonRanker")}</small></div>
            </div>
            <p className="care-plan-safety"><ShieldCheck size={16} /> {t("carePlan.safetyNote")}</p>
          </section>

          {plan.isFetching && <div className="care-plan-refreshing"><Sparkles size={16} /> {t("carePlan.updating")}</div>}
        </>
      )}
    </div>
  );
}
