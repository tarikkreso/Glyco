import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUp, Maximize2, MessageSquareText, Sparkles, X } from "lucide-react";
import { useMemo, useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/auth";
import { Badge, ErrorState, LoadingState } from "../components/ui";
import { appendAgentAssistantMessage, appendAgentUserMessage, setAgentDraft, useAgentChatSession } from "../state/agentChatSession";

type Feeling = "good" | "low" | "elevated" | "no-data";

const symptoms = ["Fatigue", "Thirst", "Headache", "Dizziness"];

function classifyWeeklyGlycoState({
  current,
  recentAverage,
  trend,
  riskLevel,
  feeling,
}: {
  current?: number;
  recentAverage?: number;
  trend?: string;
  riskLevel?: string;
  feeling?: Feeling;
}) {
  if (!current) return "no-data";
  if (feeling === "low") return "low";

  const aboveWeek = recentAverage ? current - recentAverage : 0;
  if (riskLevel === "high" || trend === "concerning" || current >= 180 || aboveWeek >= 35) return "high";
  if (riskLevel === "medium" || trend === "watch" || current >= 140 || aboveWeek >= 15) return "elevated";
  if (feeling === "good" && trend === "stable" && riskLevel === "low") return "good";
  return "stable";
}

function glycoCopy(state: string) {
  switch (state) {
    case "high":
      return { title: "Risk detected", subtitle: "A warmer outer ring means Glyco is watching a stronger signal." };
    case "elevated":
      return { title: "Slightly elevated", subtitle: "The brighter center reflects glucose trending above the usual range." };
    case "low":
      return { title: "Low energy signal", subtitle: "The cooler core reflects lower energy symptoms or a dimmer glucose pattern." };
    case "good":
      return { title: "Good day", subtitle: "The larger smooth glow means today's pattern looks calm." };
    case "no-data":
      return { title: "Waiting for data", subtitle: "Glyco will brighten as readings and check-ins arrive." };
    default:
      return { title: "Stable glucose", subtitle: "The slow green breathing animation means no urgent pattern is showing." };
  }
}

function GlycoAvatar({ state }: { state: string }) {
  return (
    <div className={`glyco-avatar-large glyco-${state}`} aria-hidden="true">
      <span className="glyco-ring ring-one" />
      <span className="glyco-ring ring-two" />
      <span className="glyco-ring ring-three" />
      <span className="glyco-core" />
      <span className="glyco-nucleus" />
    </div>
  );
}

function buildUsefulInsight({
  current,
  previousAverage,
  trend,
  riskLevel,
  selectedSymptoms,
  feeling,
  daysSinceLastLog,
  thompsonTitle,
  thompsonType,
}: {
  current?: number;
  previousAverage?: number;
  trend?: string;
  riskLevel?: string;
  selectedSymptoms: string[];
  feeling?: Feeling | null;
  daysSinceLastLog?: number;
  thompsonTitle?: string;
  thompsonType?: string;
}) {
  const delta = current && previousAverage ? current - previousAverage : 0;
  const hasSymptoms = selectedSymptoms.length > 0 || feeling === "low" || feeling === "elevated";
  const symptomText = selectedSymptoms.length ? selectedSymptoms.join(", ").toLowerCase() : feeling === "low" ? "low/tired" : "off";
  const readingIsStale = daysSinceLastLog === undefined || daysSinceLastLog >= 1;
  if (hasSymptoms && readingIsStale) {
    return {
      title: "Measure glucose now and add the reading",
      reason: daysSinceLastLog === undefined
        ? `You marked ${symptomText}, and Glyco does not see a recent glucose reading to compare against.`
        : `You marked ${symptomText}, and the last glucose log is ${daysSinceLastLog} day(s) old.`,
      action: "Open glucose log",
      source: "Changed by symptom check-in + stale reading",
      adaptation: "Symptom safety overrides Thompson ranking until Glyco has a fresh glucose value.",
    };
  }
  if (hasSymptoms && feeling === "low") {
    return {
      title: "Check glucose before following any other recommendation",
      reason: `You marked low/tired. Glyco needs a current reading before it can tell whether this is a low, normal, or elevated pattern.`,
      action: "Add current glucose reading",
      source: "Changed by low/tired check-in",
      adaptation: "The agent prioritizes immediate monitoring when symptoms are reported.",
    };
  }
  if (hasSymptoms && current && current >= 140) {
    return {
      title: "Log one more reading and review the last meal",
      reason: `Today is ${current} mg/dL, about ${Math.round(delta)} mg/dL above your recent average, and you marked ${symptomText}.`,
      action: thompsonTitle ?? "Pair carbohydrates with protein or fiber",
      source: "Changed by symptoms + current glucose",
      adaptation: thompsonTitle ? `Then Glyco falls back to the Thompson-ranked ${thompsonType ?? "recommendation"} action.` : "No feedback-ranked action is available yet.",
    };
  }
  if (trend === "concerning" || riskLevel === "high") {
    return {
      title: "Treat this week as a watch period",
      reason: "Your trained models are showing higher risk or a concerning glucose trend, so the useful next step is consistency, not panic.",
      action: thompsonTitle ?? "Keep glucose logging consistent",
      source: thompsonTitle ? "Changed by trained models + Thompson ranking" : "Changed by trained models",
      adaptation: thompsonTitle ? `The next action comes from the ${thompsonType ?? "current"} Thompson arm and can change after feedback.` : "The recommendation will personalize after feedback.",
    };
  }
  if (current && previousAverage && delta >= 15) {
    return {
      title: "Check what changed today",
      reason: `This reading is ${Math.round(delta)} mg/dL above your recent average, which is enough to look for a meal, stress, sleep, or activity trigger.`,
      action: thompsonTitle ?? "Walk after the largest meal",
      source: "Changed by glucose delta",
      adaptation: thompsonTitle ? "The action text is still ranked by feedback learning." : "Glyco is using default guidance until feedback exists.",
    };
  }
  return {
    title: "Keep the current pattern steady",
    reason: "No urgent pattern is showing right now. The most useful thing is to keep the next glucose reading comparable.",
    action: thompsonTitle ?? "Keep glucose logging consistent",
    source: thompsonTitle ? "Changed by Thompson ranking" : "Default monitoring action",
    adaptation: thompsonTitle ? `This is the current ${thompsonType ?? "ranked"} arm; marking answers useful/not useful changes future ranking.` : "Save feedback in chat to teach Glyco which action type works for you.",
  };
}

export function Overview() {
  const auth = useAuth();
  const userId = auth.session?.userId ?? 1;
  const navigate = useNavigate();
  const [feeling, setFeeling] = useState<Feeling | null>(null);
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>([]);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatExpanding, setChatExpanding] = useState(false);
  const [avatarActivated, setAvatarActivated] = useState(false);
  const chatSession = useAgentChatSession();
  const chatThreadRef = useRef<HTMLDivElement>(null);

  const risk = useQuery({ queryKey: ["risk", userId], queryFn: () => api.latestRisk(userId) });
  const monitoring = useQuery({ queryKey: ["monitoring", userId], queryFn: () => api.latestMonitoring(userId) });
  const bayesian = useQuery({ queryKey: ["bayesian", userId], queryFn: () => api.bayesianRisk(userId) });
  const logs = useQuery({ queryKey: ["logs", userId], queryFn: () => api.logs(userId) });
  const insight = useQuery({ queryKey: ["insight", userId], queryFn: () => api.insight(userId) });

  const latestLog = logs.data?.length ? logs.data[logs.data.length - 1] : undefined;
  const daysSinceLastLog = useMemo(() => {
    if (!latestLog?.log_date) return undefined;
    const today = new Date();
    const logged = new Date(`${latestLog.log_date}T00:00:00`);
    const todayMidnight = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    return Math.max(0, Math.floor((todayMidnight.getTime() - logged.getTime()) / 86400000));
  }, [latestLog?.log_date]);
  const previousAverage = useMemo(() => {
    const values = (logs.data ?? []).slice(-8, -1).map((log) => log.glucose_level);
    if (!values.length) return undefined;
    return Math.round(values.reduce((sum, value) => sum + value, 0) / values.length);
  }, [logs.data]);

  const glycoState = classifyWeeklyGlycoState({
    current: latestLog?.glucose_level,
    recentAverage: previousAverage,
    trend: monitoring.data?.trend_label,
    riskLevel: risk.data?.risk_level,
    feeling: feeling ?? undefined,
  });
  const avatarCopy = glycoCopy(glycoState);
  const thompsonAction = insight.data?.learning_summary?.next_best_action;
  const usefulInsight = buildUsefulInsight({
    current: latestLog?.glucose_level,
    previousAverage,
    trend: monitoring.data?.trend_label,
    riskLevel: risk.data?.risk_level,
    selectedSymptoms,
    feeling,
    daysSinceLastLog,
    thompsonTitle: thompsonAction?.title,
    thompsonType: thompsonAction?.type,
  });

  const chat = useMutation({
    mutationFn: (message: string) => api.agentChat(message, userId),
    onSuccess: (response, message) => {
      appendAgentAssistantMessage(response.answer, response);
    },
    onError: () => {
      appendAgentAssistantMessage("I could not reach the agent service. Try again after the API is available.");
    },
  });

  useEffect(() => {
    const timer = setTimeout(() => {
      if (chatOpen && chatThreadRef.current) {
        chatThreadRef.current.scrollTop = chatThreadRef.current.scrollHeight;
      }
    }, 80);
    return () => clearTimeout(timer);
  }, [chatSession.messages, chat.isPending, chatOpen]);

  const submit = (message = chatSession.draft) => {
    const trimmed = message.trim();
    if (!trimmed || chat.isPending) return;
    setChatOpen(true);
    appendAgentUserMessage(trimmed);
    chat.mutate(trimmed);
  };

  const toggleSymptom = (symptom: string) => {
    setSelectedSymptoms((items) => items.includes(symptom) ? items.filter((item) => item !== symptom) : [...items, symptom]);
  };

  const activateAvatar = () => {
    setAvatarActivated(true);
    window.setTimeout(() => setAvatarActivated(false), 760);
  };

  const expandChat = () => {
    setChatOpen(true);
    setChatExpanding(true);
    window.setTimeout(() => navigate("/agent", { state: { fromDock: true } }), 420);
  };

  return (
    <div className={`page glyco-home glyco-home-${glycoState} ${chatExpanding ? "chat-route-expanding" : ""}`}>
      <section className="glyco-hero" aria-label="Glyco health overview">
        <div className="glyco-status-top">
          <div>
            <span>Glyco</span>
            <h1>How are you feeling today?</h1>
          </div>
          <Badge tone={glycoState === "high" ? "warning" : glycoState === "stable" || glycoState === "good" ? "good" : "neutral"}>
            {avatarCopy.title}
          </Badge>
        </div>

        {(risk.isError || monitoring.isError || logs.isError) && (
          <ErrorState title="Some health signals are unavailable" body="Glyco can still accept a check-in, but live model data could not be loaded." />
        )}

        <div className="glyco-orbit">
          <button type="button" className="metric-card glucose" onClick={() => navigate("/metric/glucose")}>
            <span>Glucose Level</span>
            <strong>{latestLog?.glucose_level ?? "--"} <small>mg/dL</small></strong>
          </button>
          <button type="button" className="metric-card nutrition" onClick={() => navigate("/metric/nutrition")}>
            <span>Nutrition</span>
            <strong>{risk.data?.risk_level === "high" ? "Watch" : "Optimal"}</strong>
          </button>
          <button type="button" className="metric-card hba1c" onClick={() => navigate("/metric/hba1c")}>
            <span>HbA1c</span>
            <strong>6.5 <small>%</small></strong>
          </button>
          <button type="button" className="metric-card risk-score" onClick={() => navigate("/metric/risk")}>
            <span>Risk Score</span>
            <strong>{risk.data?.risk_level ?? "Loading"}</strong>
          </button>
          <button type="button" className="metric-card activity" onClick={() => navigate("/metric/activity")}>
            <span>Daily Activity</span>
            <strong>{(latestLog?.activity_minutes ?? 0) >= 30 ? "Good" : "Low"}</strong>
          </button>

          <div className="glyco-center">
            <button
              type="button"
              className={`glyco-avatar-button ${avatarActivated ? "is-activated" : ""}`}
              onClick={activateAvatar}
              aria-label={`Activate Glyco avatar. Current state: ${avatarCopy.title}`}
            >
              <GlycoAvatar state={glycoState} />
            </button>
            <div className="glyco-center-label">
              <strong>{avatarCopy.title}</strong>
              <span>{avatarCopy.subtitle}</span>
            </div>
          </div>
        </div>
        <div className="agent-learning-strip" aria-label="Agent learning signals">
          <button type="button" onClick={() => navigate("/metric/bayesian")}>
            <span>Bayesian Risk</span>
            <strong>{bayesian.data ? `${Math.round(bayesian.data.posterior_mean * 100)}%` : "--"}</strong>
            <small>{bayesian.data ? `${bayesian.data.number_of_updates} posterior updates` : "Waiting for posterior"}</small>
          </button>
          <button type="button" onClick={() => navigate("/metric/thompson")}>
            <span>Thompson Ranker</span>
            <strong>{thompsonAction?.type ?? "Learning"}</strong>
            <small>{thompsonAction?.title ?? "Ranking next best action from feedback"}</small>
          </button>
        </div>

        <div className="checkin-panel">
          <div className="checkin-question">
            <Sparkles size={18} />
            <span>Glyco asks</span>
            <strong>How are you feeling today?</strong>
          </div>
          <div className="feeling-row" role="group" aria-label="Select how you feel">
            <button className={feeling === "good" ? "active" : ""} type="button" onClick={() => setFeeling("good")}>Good</button>
            <button className={feeling === "low" ? "active" : ""} type="button" onClick={() => setFeeling("low")}>Low / tired</button>
            <button className={feeling === "elevated" ? "active" : ""} type="button" onClick={() => setFeeling("elevated")}>A bit off</button>
          </div>
          <div className="symptom-row" role="group" aria-label="Select symptoms">
            {symptoms.map((symptom) => (
              <button className={selectedSymptoms.includes(symptom) ? "active" : ""} key={symptom} type="button" onClick={() => toggleSymptom(symptom)}>
                {symptom}
              </button>
            ))}
          </div>
        </div>

        <div className="today-insight">
          <span>What Glyco recommends now</span>
          <p>{usefulInsight.title}</p>
          <small>{usefulInsight.reason}</small>
          <div className="insight-action-row">
            <strong>Next best action</strong>
            <button type="button" onClick={() => navigate("/monitoring")}>{usefulInsight.action}</button>
          </div>
          <div className="insight-adaptation-note">
            <span>{usefulInsight.source}</span>
            <small>{usefulInsight.adaptation}</small>
          </div>
        </div>
      </section>

      <form className={`glyco-chat-dock ${chatOpen ? "is-open" : ""}`} onSubmit={(event) => { event.preventDefault(); submit(); }}>
        <MessageSquareText size={20} />
          <input
          value={chatSession.draft}
          onChange={(event) => {
            setAgentDraft(event.target.value);
            if (event.target.value.length > 0) setChatOpen(true);
          }}
          onFocus={() => setChatOpen(true)}
          placeholder="Ask Glyco about this pattern..."
          aria-label="Ask Glyco"
        />
        <button className="primary" type="submit" aria-label="Send message"><ArrowUp size={16} /></button>
      </form>

      {chatOpen && (
        <aside className={`glyco-chat-window ${chatExpanding ? "route-expanding" : ""}`} aria-label="Glyco chat window">
          <header>
            <div>
              <span>AI Chat</span>
              <strong>Glyco</strong>
            </div>
            <div className="glyco-chat-actions">
              <button type="button" className="icon-button" onClick={expandChat} aria-label="Open full Glyco chat">
                <Maximize2 size={16} />
              </button>
              <button type="button" className="icon-button" onClick={() => setChatOpen(false)} aria-label="Close chat">
                <X size={16} />
              </button>
            </div>
          </header>
          <div ref={chatThreadRef} className="glyco-chat-thread" aria-live="polite">
            {chatSession.messages.map((message, index) => (
              <article className={`glyco-chat-message ${message.role}`} key={`${message.role}-${index}`}>
                <span>{message.role === "assistant" ? "Glyco" : "You"}</span>
                <p>{message.content}</p>
              </article>
            ))}
            {chat.isPending && <LoadingState label="Glyco is reading your trend and check-in" />}
          </div>
        </aside>
      )}
    </div>
  );
}
