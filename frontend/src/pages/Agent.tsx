import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUp, ClipboardList, Database, History, RotateCcw, ShieldCheck, Sparkles } from "lucide-react";
import type { ReactNode } from "react";
import { useMemo, useState, useRef, useEffect } from "react";
import { api, type AgentChatResponse } from "../api/client";
import { useAuth } from "../auth/auth";
import { Badge, Card, EmptyState, ErrorState, LoadingState, PageHeader } from "../components/ui";
import { appendAgentAssistantMessage, appendAgentUserMessage, resetAgentConversation, setAgentDraft, useAgentChatSession } from "../state/agentChatSession";

const quickPrompts = [
  "Should I be worried this week?",
  "What changed in my recent readings?",
  "What should I ask my doctor?",
  "How can my family help this week?",
];

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
    } else if (/^(Bottom line|What I see|Why it matters|What to do this week|Questions for the doctor|Safety note|How family can help)$/i.test(line)) {
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

export function Agent() {
  const auth = useAuth();
  const userId = auth.session?.userId ?? 1;
  const chatSession = useAgentChatSession();
  const [feedbackTone, setFeedbackTone] = useState("concise");
  const [historyOpen, setHistoryOpen] = useState(false);
  const chatThreadRef = useRef<HTMLDivElement>(null);
  const risk = useQuery({ queryKey: ["risk", userId], queryFn: () => api.latestRisk(userId) });
  const monitoring = useQuery({ queryKey: ["monitoring", userId], queryFn: () => api.latestMonitoring(userId) });
  const logs = useQuery({ queryKey: ["logs", userId], queryFn: () => api.logs(userId) });
  const alerts = useQuery({ queryKey: ["alerts", userId], queryFn: () => api.alerts(userId) });
  const latestResponse = useMemo(() => [...chatSession.messages].reverse().find((item) => item.response)?.response, [chatSession.messages]);
  const chatHistory = useMemo(() => chatSession.messages.filter((message) => message.role === "user"), [chatSession.messages]);
  const llmLabel = latestResponse ? `${latestResponse.llm_mode}: ${latestResponse.llm_model}` : "fallback";
  const learning = latestResponse?.learning_summary;
  const chat = useMutation({
    mutationFn: (message: string) => api.agentChat(message, userId),
    onSuccess: (response, message) => {
      appendAgentAssistantMessage(response.answer, response);
    },
    onError: () => {
      appendAgentAssistantMessage("I could not reach the agent service. Try again after the API is available.");
    },
  });
  const feedback = useMutation({
    mutationFn: (helpful: boolean) => api.agentFeedback({
      user_id: userId,
      message: latestResponse?.answer ?? "No answer selected",
      helpful,
      preferred_tone: feedbackTone,
      confirmed_action: helpful ? "Keep weekly glucose logging and prepare doctor questions." : undefined,
      notes: helpful ? "User confirmed this answer style was useful." : "User wants a different style next time.",
    }),
    onSuccess: () => {
      appendAgentAssistantMessage("Feedback saved. Glyco will use it to personalize the next answer.");
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
      <PageHeader title="Glyco Chat" subtitle="Ask natural-language questions while Glyco runs the active risk scorer, monitoring scorer, Bayesian layer, and adaptive recommendation ranker." meta={`Mode: ${llmLabel}`} />
      <div className="agent-layout">
        <Card title="Glyco Agent" action={<div className="agent-card-actions"><button type="button" className="secondary history-toggle" onClick={() => setHistoryOpen((value) => !value)}><History size={15} /> History</button><Badge>{llmLabel}</Badge></div>}>
          <div className="agent-ambient-mark" aria-hidden="true">
            <Sparkles size={18} />
            <span>Frosted AI workspace</span>
          </div>
          {historyOpen && (
            <div className="chat-history-panel">
              <header>
                <strong>Chat history</strong>
                <button type="button" className="icon-button" onClick={() => resetMemory.mutate()} disabled={resetMemory.isPending} aria-label="Start a new chat"><RotateCcw size={15} /></button>
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
              ) : <EmptyState title="No past chats yet" body="Ask Glyco a question and it will appear here." />}
            </div>
          )}
          <div className="prompt-row">
            {quickPrompts.map((prompt) => <button key={prompt} className="secondary" type="button" onClick={() => submit(prompt)}>{prompt}</button>)}
          </div>
          <div ref={chatThreadRef} className="chat-thread" aria-live="polite">
            {chatSession.messages.map((message, index) => (
              <article className={`chat-message ${message.role}`} key={`${message.role}-${index}`}>
                <span>{message.role === "assistant" ? "Glyco" : "You"}</span>
                {message.role === "assistant" ? <FormattedResponse content={message.content} /> : <p>{message.content}</p>}
              </article>
            ))}
            {chat.isPending && <LoadingState label="Glyco is checking profile, logs, models, and guidance" />}
            {chat.isError && <ErrorState title="Agent could not answer" body="The chat request failed. Check the API connection and try again." />}
          </div>
          <form className="chat-compose" onSubmit={(event) => { event.preventDefault(); submit(); }}>
            <input value={chatSession.draft} onChange={(event) => setAgentDraft(event.target.value)} placeholder="Ask Glyco about this week..." aria-label="Ask Glyco" />
            <button className="primary" type="submit" aria-label="Send message"><ArrowUp size={16} /></button>
          </form>
          {latestResponse && (
            <div className="feedback-panel">
              <div>
                <strong>Teach Glyco</strong>
                <p>Save feedback so the next answer adapts its tone and remembers confirmed actions.</p>
              </div>
              <select value={feedbackTone} onChange={(event) => setFeedbackTone(event.target.value)} aria-label="Preferred answer tone">
                <option value="concise">Concise</option>
                <option value="detailed">Detailed</option>
                <option value="family-friendly">Family friendly</option>
              </select>
              <button className="secondary" type="button" disabled={feedback.isPending} onClick={() => feedback.mutate(true)}>Useful</button>
              <button className="secondary" type="button" disabled={feedback.isPending} onClick={() => feedback.mutate(false)}>Needs work</button>
            </div>
          )}
        </Card>
        <div className="agent-side">
          <Card title="Agent Memory" action={<Badge>{learning?.feedback_count ?? 0} signals</Badge>}>
            {learning ? (
              <div className="memory-stack">
                <div><span>Preferred tone</span><strong>{learning.preferred_tone}</strong></div>
                <div><span>Learned focus</span><strong>{learning.preferred_action_type ?? "monitoring"}</strong></div>
                <div><span>Glucose pattern</span><strong>{learning.recent_glucose_pattern?.label ?? "new"}</strong></div>
                <div><span>Helpfulness</span><strong>{learning.helpful_rate === null ? "new" : `${Math.round(learning.helpful_rate * 100)}%`}</strong></div>
                <p>{learning.adaptation_note}</p>
                {learning.next_best_action && <small>Next: {learning.next_best_action.title}</small>}
                {learning.confirmed_actions.length > 0 && <small>Remembered: {learning.confirmed_actions[0]}</small>}
              </div>
            ) : <EmptyState title="No memory yet" body="Ask a question and save feedback to activate personalization." />}
          </Card>
          <Card title="Used Data" action={<Database size={18} />}>
            <div className="data-stack">
              <div><span>Risk model</span><strong>{risk.data?.risk_level ?? "-"}</strong><small>{risk.data?.model_version ?? "Loading"}</small></div>
              <div><span>Trend model</span><strong>{monitoring.data?.trend_label ?? "-"}</strong><small>{monitoring.data?.model_version ?? "Loading"}</small></div>
              <div><span>Recent logs</span><strong>{logs.data?.length ?? "-"}</strong><small>patient-entered readings</small></div>
            </div>
          </Card>
          <Card title="Guidance Grounding" action={<ClipboardList size={18} />}>
            {latestResponse?.guideline_snippets.length ? (
              <div className="guideline-list">
                {latestResponse.guideline_snippets.map((snippet) => <div key={snippet.id}><strong>{snippet.category}</strong><p>{snippet.text}</p></div>)}
              </div>
            ) : <EmptyState title="No snippets used yet" body="Ask a question to see the curated guidance notes the agent used." />}
          </Card>
          <Card title="Safety Boundary" action={<ShieldCheck size={18} />}>
            <p>{latestResponse?.safety_note ?? "Glyco can support interpretation and preparation, but it does not diagnose or replace a clinician."}</p>
          </Card>
          <Card title="Proactive Alerts">
            {(alerts.data ?? []).length ? <div className="alert-list">{alerts.data?.slice(0, 3).map((alert) => <div key={alert.id} className={alert.severity === "danger" ? "danger" : "warning"}><strong>{alert.title}</strong><span>{alert.message}</span></div>)}</div> : <EmptyState title="No active alerts" body="Glyco creates alerts after new logs when a watch or concerning pattern is detected." />}
          </Card>
        </div>
      </div>
    </div>
  );
}
