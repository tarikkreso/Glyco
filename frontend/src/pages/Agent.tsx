import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUp, Database, History, RotateCcw, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState, useRef, useEffect } from "react";
import { api, type AgentChatResponse } from "../api/client";
import { useAuth } from "../auth/auth";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";
import { useI18n } from "../i18n";
import { appendAgentAssistantMessage, appendAgentUserMessage, resetAgentConversation, setAgentDraft, useAgentChatSession } from "../state/agentChatSession";

function InlineFormatted({ text }: { text: string }) {
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  return (
    <>
      {parts.map((part, index) => part.startsWith("**") && part.endsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : <span key={index}>{part}</span>)}
    </>
  );
}

function FormattedResponse({ content }: { content: string }) {
  const lines = content.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const blocks: ReactNode[] = [];
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    const tableLines: string[] = [];
    while (index < lines.length && lines[index].startsWith("|") && lines[index].endsWith("|")) {
      tableLines.push(lines[index]);
      index += 1;
    }
    if (tableLines.length >= 2) {
      const rows = tableLines
        .filter((row) => !/^\|\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?$/.test(row))
        .map((row) => row.split("|").slice(1, -1).map((cell) => cell.trim()));
      blocks.push(
        <div className="response-table-wrap" key={`table-${index}`}>
          <table>
            <thead><tr>{rows[0].map((cell, cellIndex) => <th key={cellIndex}><InlineFormatted text={cell} /></th>)}</tr></thead>
            <tbody>{rows.slice(1).map((row, rowIndex) => <tr key={rowIndex}>{row.map((cell, cellIndex) => <td key={cellIndex}><InlineFormatted text={cell} /></td>)}</tr>)}</tbody>
          </table>
        </div>
      );
      continue;
    }
    if (/^#{1,4}\s+/.test(line)) {
      blocks.push(<h3 key={index}><InlineFormatted text={line.replace(/^#{1,4}\s+/, "")} /></h3>);
    } else if (/^(Bottom line|What I see|Why it matters|What to do this week|Questions for the doctor|Safety note|How family can help|Zaključak|Analiza stanja|Zašto je to važno|Šta učiniti ove sedmice|Pitanja za doktora|Sigurnosna napomena|Kako porodica može pomoći)$/i.test(line)) {
      blocks.push(<h3 key={index}><InlineFormatted text={line} /></h3>);
    } else if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^[-*]\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^[-*]\s+/, ""));
        index += 1;
      }
      blocks.push(<ul key={`ul-${index}`}>{items.map((item, itemIndex) => <li key={itemIndex}><InlineFormatted text={item} /></li>)}</ul>);
      continue;
    } else if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) {
        items.push(lines[index].replace(/^\d+\.\s+/, ""));
        index += 1;
      }
      blocks.push(<ol key={`ol-${index}`}>{items.map((item, itemIndex) => <li key={itemIndex}><InlineFormatted text={item} /></li>)}</ol>);
      continue;
    } else {
      blocks.push(<p key={index}><InlineFormatted text={line} /></p>);
    }
    index += 1;
  }
  return <div className="formatted-response">{blocks}</div>;
}

type TranslationFn = (key: string) => string;

const VALUE_KEYS: Record<string, string> = {
  balanced: "agent.value.tone.balanced",
  concise: "agent.value.tone.concise",
  detailed: "agent.value.tone.detailed",
  "family-friendly": "agent.value.tone.familyFriendly",
  nutrition: "agent.value.action.nutrition",
  activity: "agent.value.action.activity",
  monitoring: "agent.value.action.monitoring",
  medication_check: "agent.value.action.medicationCheck",
  clinician_questions: "agent.value.action.clinicianQuestions",
  fasting_routine: "agent.value.action.fastingRoutine",
  post_meal_review: "agent.value.action.postMealReview",
  sleep_stress: "agent.value.action.sleepStress",
  family_support: "agent.value.action.familySupport",
  "no-data": "agent.value.pattern.noData",
  "needs-attention": "agent.value.pattern.needsAttention",
  watch: "agent.value.trend.watch",
  steady: "agent.value.pattern.steady",
  stable: "agent.value.trend.stable",
  concerning: "agent.value.trend.concerning",
  high: "agent.value.risk.high",
  medium: "agent.value.risk.medium",
  low: "agent.value.risk.low",
  unknown: "common.unknown",
  new: "agent.value.new",
};

const RECOMMENDATION_TITLE_KEYS: Record<string, string> = {
  "Pair carbohydrates with protein or fiber": "agent.recommendation.nutrition",
  "Walk after the largest meal": "agent.recommendation.activity",
  "Keep glucose logging consistent": "agent.recommendation.monitoring",
  "Prepare medication questions": "agent.recommendation.medicationCheck",
  "Write down doctor questions": "agent.recommendation.clinicianQuestions",
  "Standardize fasting checks": "agent.recommendation.fastingRoutine",
  "Review post-meal patterns": "agent.recommendation.postMealReview",
  "Note sleep and stress context": "agent.recommendation.sleepStress",
  "Ask family for one practical support": "agent.recommendation.familySupport",
  "Keep weekly glucose logging and prepare doctor questions.": "agent.confirmedAction.weeklyLogging",
};

const FEEDBACK_TONE_OPTIONS = [
  { value: "concise", labelKey: "agent.concise" },
  { value: "detailed", labelKey: "agent.detailed" },
  { value: "family-friendly", labelKey: "agent.familyFriendly" },
];

function fallbackLabel(value: string) {
  return value
    .replace(/[_-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function translateValue(value: string | undefined | null, t: TranslationFn) {
  if (!value) return "-";
  const key = VALUE_KEYS[value];
  return key ? t(key) : fallbackLabel(value);
}

function translateRecommendationTitle(value: string | undefined | null, t: TranslationFn) {
  if (!value) return "";
  const key = RECOMMENDATION_TITLE_KEYS[value];
  return key ? t(key) : value;
}

function translateAdaptationNote(note: string | undefined, t: TranslationFn) {
  if (!note) return "";
  if (note === "No feedback yet. The agent is adapting from recent glucose patterns and general clinical guidance.") {
    return t("agent.adaptation.noFeedback");
  }

  const match = note.match(
    /^Personalized with (\d+) feedback signal\(s\): tone=([^,]+), focus=([^,]+), recent glucose pattern=([^.]+)\.$/,
  );
  if (!match) return note;

  return t("agent.adaptation.personalized")
    .replace("%d", match[1])
    .replace("%tone", translateValue(match[2], t))
    .replace("%focus", translateValue(match[3], t))
    .replace("%pattern", translateValue(match[4], t));
}

export function Agent() {
  const auth = useAuth();
  const { t } = useI18n();
  const userId = auth.session?.userId ?? 1;
  const chatSession = useAgentChatSession();
  const [feedbackTone, setFeedbackTone] = useState("concise");
  const [historyOpen, setHistoryOpen] = useState(false);
  const chatThreadRef = useRef<HTMLDivElement>(null);
  const risk = useQuery({ queryKey: ["risk", userId], queryFn: () => api.latestRisk(userId) });
  const monitoring = useQuery({ queryKey: ["monitoring", userId], queryFn: () => api.latestMonitoring(userId) });
  const logs = useQuery({ queryKey: ["logs", userId], queryFn: () => api.logs(userId) });
  const latestResponse = useMemo(() => [...chatSession.messages].reverse().find((item) => item.response)?.response, [chatSession.messages]);
  const chatHistory = useMemo(() => chatSession.messages.filter((message) => message.role === "user"), [chatSession.messages]);
  const quickPrompts = useMemo(() => [
    t("agent.promptWorried"),
    t("agent.promptChanged"),
    t("agent.promptDoctor"),
    t("agent.promptFamily"),
  ], [t]);
  const llmLabel = latestResponse ? `${latestResponse.llm_mode}: ${latestResponse.llm_model}` : t("agent.fallback");
  const learning = latestResponse?.learning_summary;
  const chat = useMutation({
    mutationFn: (message: string) => api.agentChat(message, userId),
    onSuccess: (response, message) => {
      appendAgentAssistantMessage(response.answer, response);
    },
    onError: () => {
      appendAgentAssistantMessage(t("agent.apiUnavailable"));
    },
  });
  const feedback = useMutation({
    mutationFn: (tone: string) => api.agentFeedback({
      user_id: userId,
      message: latestResponse?.answer ?? "No answer selected",
      helpful: true,
      preferred_tone: tone,
      confirmed_action: "Keep weekly glucose logging and prepare doctor questions.",
      notes: "User selected this preferred answer tone.",
    }),
    onSuccess: (_response, tone) => {
      setFeedbackTone(tone);
      appendAgentAssistantMessage(t("agent.feedbackSaved"));
    },
  });
  const resetMemory = useMutation({
    mutationFn: () => api.resetAgentMemory(),
    onSuccess: () => {
      resetAgentConversation();
    },
    onError: () => {
      resetAgentConversation();
    },
  });

  useEffect(() => {
    const timer = setTimeout(() => {
      if (chatThreadRef.current) {
        chatThreadRef.current.scrollTop = chatThreadRef.current.scrollHeight;
      }
    }, 60);
    return () => clearTimeout(timer);
  }, [chatSession.messages, chat.isPending]);

  const submit = (message = chatSession.draft) => {
    const trimmed = message.trim();
    if (!trimmed || chat.isPending) return;
    appendAgentUserMessage(trimmed);
    chat.mutate(trimmed);
  };
  return (
    <div className="page agent-page frosty-agent-page">
      <PageHeader title={t("agent.title")} subtitle={t("agent.subtitle")} meta={`${t("agent.mode")}: ${llmLabel}`} />
      <div className="agent-layout">
        <Card title={t("agent.card")} action={<div className="agent-card-actions"><button type="button" className="secondary history-toggle" onClick={() => setHistoryOpen((value) => !value)}><History size={15} /> {t("agent.history")}</button><Badge>{llmLabel}</Badge></div>}>
          <div className="agent-ambient-mark" aria-hidden="true">
            <Sparkles size={18} />
            <span>{t("agent.workspace")}</span>
          </div>
          {historyOpen && (
            <div className="chat-history-panel">
              <header>
                <strong>{t("agent.historyTitle")}</strong>
                <button type="button" className="icon-button" onClick={() => resetMemory.mutate()} disabled={resetMemory.isPending} aria-label={t("agent.aria.startNewChat")}><RotateCcw size={15} /></button>
              </header>
              {chatHistory.length ? (
                <div className="chat-history-list">
                  {chatHistory.slice().reverse().map((message) => (
                    <button type="button" key={message.created_at} onClick={() => setAgentDraft(message.content)}>
                      <span>{new Date(message.created_at).toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" })}</span>
                      <strong>{message.content}</strong>
                    </button>
                  ))}
                </div>
              ) : <EmptyState title={t("agent.noPastChats")} body={t("agent.noPastChatsBody")} />}
            </div>
          )}
          <div className="prompt-row">
            {quickPrompts.map((prompt) => <button key={prompt} className="secondary" type="button" onClick={() => submit(prompt)}>{prompt}</button>)}
          </div>
          <div ref={chatThreadRef} className="chat-thread" aria-live="polite">
            {chatSession.messages.map((message, index) => (
              <article className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
                <span>{message.role === "assistant" ? "Glyco" : t("agent.you")}</span>
                {message.role === "assistant" ? <FormattedResponse content={message.content} /> : <p>{message.content}</p>}
              </article>
            ))}
            {chat.isPending && <LoadingState label={t("agent.loading")} />}
            {chat.isError && <ErrorState title={t("agent.errorTitle")} body={t("agent.errorBody")} />}
          </div>
          <form className="chat-compose" onSubmit={(event) => { event.preventDefault(); submit(); }}>
            <input value={chatSession.draft} onChange={(event) => setAgentDraft(event.target.value)} placeholder={t("agent.placeholder")} aria-label={t("agent.aria.ask")} />
            <button className="primary" type="submit" aria-label={t("agent.aria.send")}><ArrowUp size={16} /></button>
          </form>
          {latestResponse && (
            <div className="feedback-panel">
              <div>
                <strong>{t("agent.teach")}</strong>
                <p>{t("agent.teachBody")}</p>
              </div>
              <div className="tone-choice-row" role="group" aria-label={t("agent.aria.preferredTone")}>
                {FEEDBACK_TONE_OPTIONS.map((option) => (
                  <button
                    key={option.value}
                    className={`tone-choice${feedbackTone === option.value ? " selected" : ""}`}
                    type="button"
                    disabled={feedback.isPending}
                    aria-pressed={feedbackTone === option.value}
                    onClick={() => {
                      setFeedbackTone(option.value);
                      feedback.mutate(option.value);
                    }}
                  >
                    {t(option.labelKey)}
                  </button>
                ))}
              </div>
            </div>
          )}
        </Card>
        <div className="agent-side">
          <Card title={t("agent.memory")} action={<Badge>{learning?.feedback_count ?? 0} {t("agent.signals")}</Badge>}>
            {learning ? (
              <div className="memory-stack">
                <div><span>{t("agent.preferredTone")}</span><strong>{translateValue(learning.preferred_tone, t)}</strong></div>
                <div><span>{t("agent.learnedFocus")}</span><strong>{translateValue(learning.preferred_action_type ?? "monitoring", t)}</strong></div>
                <div><span>{t("agent.glucosePattern")}</span><strong>{translateValue(learning.recent_glucose_pattern?.label ?? "new", t)}</strong></div>
                <div><span>{t("agent.helpfulness")}</span><strong>{learning.helpful_rate === null ? t("agent.value.new") : `${Math.round(learning.helpful_rate * 100)}%`}</strong></div>
                <p>{translateAdaptationNote(learning.adaptation_note, t)}</p>
                {learning.next_best_action && <small>{t("agent.next")}: {translateRecommendationTitle(learning.next_best_action.title, t)}</small>}
                {learning.confirmed_actions.length > 0 && <small>{t("agent.remembered")}: {translateRecommendationTitle(learning.confirmed_actions[0], t)}</small>}
              </div>
            ) : <EmptyState title={t("agent.noMemory")} body={t("agent.noMemoryBody")} />}
          </Card>
          <Card title={t("agent.usedData")} action={<Database size={18} />}>
            <div className="data-stack">
              <div><span>{t("agent.riskModel")}</span><strong>{translateValue(risk.data?.risk_level, t)}</strong><small>{risk.data?.model_version ?? t("common.loading")}</small></div>
              <div><span>{t("agent.trendModel")}</span><strong>{translateValue(monitoring.data?.trend_label, t)}</strong><small>{monitoring.data?.model_version ?? t("common.loading")}</small></div>
              <div><span>{t("agent.recentLogs")}</span><strong>{logs.data?.length ?? "-"}</strong><small>{t("agent.patientReadings")}</small></div>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
