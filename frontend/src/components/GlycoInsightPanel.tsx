import { Brain, ClipboardList, HelpCircle, TrendingUp } from "lucide-react";
import type { GlycoInsight } from "../api/client";
import { Card, EmptyState, LoadingState } from "./ui";

export function GlycoInsightPanel({ insight, isLoading }: { insight?: GlycoInsight; isLoading?: boolean }) {
  return (
    <Card title="Glyco Insight" action={<Brain size={18} />}>
      {isLoading ? <LoadingState label="Preparing insight" /> : insight ? (
        <div className="insight-grid">
          <section className="insight-block">
            <TrendingUp size={18} />
            <div><span>What changed?</span><p>{insight.what_changed}</p></div>
          </section>
          <section className="insight-block">
            <Brain size={18} />
            <div><span>Why it matters</span><p>{insight.why_it_matters}</p></div>
          </section>
          <section className="insight-block">
            <ClipboardList size={18} />
            <div>
              <span>What to do next</span>
              <ul>{insight.what_to_do_next.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </section>
          <section className="insight-block">
            <HelpCircle size={18} />
            <div>
              <span>What to ask your doctor</span>
              <ul>{insight.what_to_ask_your_doctor.map((item) => <li key={item}>{item}</li>)}</ul>
            </div>
          </section>
          <p className="insight-note">{insight.confidence_note}</p>
        </div>
      ) : <EmptyState title="Insight unavailable" body="Glyco needs a current risk assessment and monitoring history to prepare this panel." />}
    </Card>
  );
}
