import { Brain, ClipboardList, HelpCircle, TrendingUp } from "lucide-react";
import type { GlycoInsight } from "../api/client";
import { Card, EmptyState, LoadingState } from "./ui";
import { useI18n } from "../i18n";

export function GlycoInsightPanel({ insight, isLoading }: { insight?: GlycoInsight; isLoading?: boolean }) {
  const { t, language } = useI18n();
  return (
    <Card title={t("glycoInsight.title")} action={<Brain size={18} />}>
      {isLoading ? <LoadingState label={t("glycoInsight.preparing")} /> : insight ? (
        <div className="insight-grid">
          <section className="insight-block">
            <TrendingUp size={18} />
            <div><span>{t("glycoInsight.whatChanged")}</span><p>{insight.what_changed}</p></div>
          </section>
          <section className="insight-block">
            <Brain size={18} />
            <div><span>{t("glycoInsight.whyItMatters")}</span><p>{insight.why_it_matters}</p></div>
          </section>
          <section className="insight-block">
            <ClipboardList size={18} />
            <div>
              <span>{t("glycoInsight.whatToDoNext")}</span>
              <ul>{insight.what_to_do_next.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </section>
          <section className="insight-block">
            <HelpCircle size={18} />
            <div>
              <span>{t("glycoInsight.whatToAskDoctor")}</span>
              <ul>{insight.what_to_ask_your_doctor.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </section>
          <p className="insight-note">{insight.confidence_note}</p>
        </div>
      ) : <EmptyState title={t("glycoInsight.unavailableTitle")} body={t("glycoInsight.unavailableBody")} />}
    </Card>
  );
}
