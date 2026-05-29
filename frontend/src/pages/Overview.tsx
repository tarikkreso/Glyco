import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowUp, Maximize2, MessageSquareText, Sparkles, X } from "lucide-react";
import { useMemo, useState, useRef, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { useAuth } from "../auth/auth";
import { Badge, ErrorState, FactorList, LoadingState } from "../components/ui";
import { useI18n } from "../i18n";
import { appendAgentAssistantMessage, appendAgentUserMessage, setAgentDraft, useAgentChatSession } from "../state/agentChatSession";
import { formatGlucoseFromMgdl, useGlucoseUnit } from "../utils/glucoseUnits";

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

function localizeThompsonAction(title?: string, bs?: boolean) {
  if (!title || !bs) return title;
  const labels: Record<string, string> = {
    "Keep glucose logging consistent": "Unosite glukozu dosljedno",
    "Walk after the largest meal": "Prošetajte nakon najvećeg obroka",
    "Pair carbohydrates with protein or fiber": "Uparite ugljikohidrate s proteinima ili vlaknima",
    "Open glucose log": "Otvori unos glukoze",
    "Add current glucose reading": "Dodajte trenutno očitanje glukoze",
    "Review post-meal patterns": "Pregledajte obrasce nakon obroka",
  };
  return labels[title] ?? title;
}

function GlycoAvatar({ state }: { state: string }) {
  const clipPathVal = useMemo(() => {
    const points = [];
    for (let i = 0; i < 60; i++) {
      const angle = (i * 2 * Math.PI) / 60;
      const r = 0.445 + 0.045 * Math.cos(5 * angle);
      const x = (50 + r * 100 * Math.sin(angle)).toFixed(2);
      const y = (50 - r * 100 * Math.cos(angle)).toFixed(2);
      points.push(`${x}% ${y}%`);
    }
    return `polygon(${points.join(", ")})`;
  }, []);

  const style = { clipPath: clipPathVal };

  return (
    <div className={`glyco-avatar-large glyco-${state}`} aria-hidden="true">
      <span className="glyco-ring ring-one" style={style} />
      <span className="glyco-ring ring-two" style={style} />
      <span className="glyco-ring ring-three" style={style} />
      <span className="glyco-core" style={style} />
      <span className="glyco-nucleus" style={style} />
      <span className="glyco-glass-highlight" style={style} />
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
  bs,
  formatGlucose,
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
  bs?: boolean;
  formatGlucose: (value?: number) => string;
}) {
  const useBs = bs ?? false;
  const formatDelta = (value: number) => formatGlucose(Math.abs(value));
  const delta = current && previousAverage ? current - previousAverage : 0;
  const hasSymptoms = selectedSymptoms.length > 0 || feeling === "low" || feeling === "elevated";
  const symptomText = selectedSymptoms.length
    ? selectedSymptoms.join(", ").toLowerCase()
    : feeling === "low"
      ? (useBs ? "nisko/umorno" : "low/tired")
      : (useBs ? "izvan uobičajenog" : "off");
  const readingIsStale = daysSinceLastLog === undefined || daysSinceLastLog >= 1;
  if (hasSymptoms && readingIsStale) {
    return {
      title: useBs ? "Izmjerite glukozu sada i dodajte očitanje" : "Measure glucose now and add the reading",
      reason: daysSinceLastLog === undefined
        ? (useBs
          ? `Zabilježili ste ${symptomText}, a Glyco ne vidi skoro očitanje glukoze za poređenje.`
          : `You marked ${symptomText}, and Glyco does not see a recent glucose reading to compare against.`)
        : (useBs
          ? `Zabilježili ste ${symptomText}, a posljednji zapis glukoze je star ${daysSinceLastLog} dan(a).`
          : `You marked ${symptomText}, and the last glucose log is ${daysSinceLastLog} day(s) old.`),
      action: useBs ? "Otvori unos glukoze" : "Open glucose log",
      source: useBs ? "Promijenjeno zbog prijave simptoma i zastarjelog očitanja" : "Changed by symptom check-in + stale reading",
      adaptation: useBs ? "Sigurnost zbog simptoma ima prednost nad Thompson rangiranjem dok Glyco ne dobije svježu vrijednost glukoze." : "Symptom safety overrides Thompson ranking until Glyco has a fresh glucose value.",
    };
  }
  if (hasSymptoms && feeling === "low") {
    return {
      title: useBs ? "Provjerite glukozu prije bilo koje druge preporuke" : "Check glucose before following any other recommendation",
      reason: useBs
        ? "Označili ste nisko/umorno. Glyco treba trenutno očitanje prije nego kaže da li je obrazac nizak, normalan ili povišen."
        : `You marked low/tired. Glyco needs a current reading before it can tell whether this is a low, normal, or elevated pattern.`,
      action: useBs ? "Dodajte trenutno očitanje glukoze" : "Add current glucose reading",
      source: useBs ? "Promijenjeno zbog prijave nisko/umorno" : "Changed by low/tired check-in",
      adaptation: useBs ? "Agent daje prednost trenutnom praćenju kada su simptomi prijavljeni." : "The agent prioritizes immediate monitoring when symptoms are reported.",
    };
  }
  if (hasSymptoms && current && current >= 140) {
    return {
      title: useBs ? "Unesite još jedno očitanje i pregledajte posljednji obrok" : "Log one more reading and review the last meal",
      reason: useBs
        ? `Danas je ${formatGlucose(current)}, oko ${formatDelta(delta)} iznad vašeg nedavnog prosjeka, a označili ste ${symptomText}.`
        : `Today is ${formatGlucose(current)}, about ${formatDelta(delta)} above your recent average, and you marked ${symptomText}.`,
      action: localizeThompsonAction(thompsonTitle, useBs) ?? (useBs ? "Uparite ugljikohidrate s proteinima ili vlaknima" : "Pair carbohydrates with protein or fiber"),
      source: useBs ? "Promijenjeno zbog simptoma i trenutne glukoze" : "Changed by symptoms + current glucose",
      adaptation: thompsonTitle
        ? (useBs
          ? `Zatim Glyco pada na Thompson-rangiranu akciju ${thompsonType ?? "preporuke"}.`
          : `Then Glyco falls back to the Thompson-ranked ${thompsonType ?? "recommendation"} action.`)
        : (useBs ? "Još nema dostupne akcije rangirane na osnovu povratne informacije." : "No feedback-ranked action is available yet."),
    };
  }
  if (trend === "concerning" || riskLevel === "high") {
    return {
      title: useBs ? "Posmatrajte ovu sedmicu kao period praćenja" : "Treat this week as a watch period",
      reason: useBs
        ? "Vaši trenirani modeli pokazuju veći rizik ili zabrinjavajući trend glukoze, pa je koristan sljedeći korak dosljednost, a ne panika."
        : "Your trained models are showing higher risk or a concerning glucose trend, so the useful next step is consistency, not panic.",
      action: localizeThompsonAction(thompsonTitle, useBs) ?? (useBs ? "Unosite glukozu dosljedno" : "Keep glucose logging consistent"),
      source: thompsonTitle ? (useBs ? "Promijenjeno zbog treniranih modela i Thompson rangiranja" : "Changed by trained models + Thompson ranking") : (useBs ? "Promijenjeno zbog treniranih modela" : "Changed by trained models"),
      adaptation: thompsonTitle
        ? (useBs
          ? `Sljedeća akcija dolazi iz Thompson kruga ${thompsonType ?? "trenutnog"} i može se promijeniti nakon povratne informacije.`
          : `The next action comes from the ${thompsonType ?? "current"} Thompson arm and can change after feedback.`)
        : (useBs ? "Preporuka će se personalizovati nakon povratne informacije." : "The recommendation will personalize after feedback."),
    };
  }
  if (current && previousAverage && delta >= 15) {
    return {
      title: useBs ? "Provjerite šta se danas promijenilo" : "Check what changed today",
      reason: useBs
        ? `Ovo očitanje je ${formatDelta(delta)} iznad vašeg nedavnog prosjeka, što je dovoljno da potražite okidač u obroku, stresu, snu ili aktivnosti.`
        : `This reading is ${formatDelta(delta)} above your recent average, which is enough to look for a meal, stress, sleep, or activity trigger.`,
      action: localizeThompsonAction(thompsonTitle, useBs) ?? (useBs ? "Prošetajte nakon najvećeg obroka" : "Walk after the largest meal"),
      source: useBs ? "Promijenjeno zbog razlike glukoze" : "Changed by glucose delta",
      adaptation: thompsonTitle ? (useBs ? "Tekst akcije i dalje rangira učenje povratne informacije." : "The action text is still ranked by feedback learning.") : (useBs ? "Glyco koristi zadane smjernice dok ne stigne povratna informacija." : "Glyco is using default guidance until feedback exists."),
    };
  }
  return {
    title: useBs ? "Zadržite trenutni obrazac stabilnim" : "Keep the current pattern steady",
    reason: useBs ? "Trenutno se ne vidi hitan obrazac. Najkorisnije je da sljedeće očitanje glukoze ostane uporedivo." : "No urgent pattern is showing right now. The most useful thing is to keep the next glucose reading comparable.",
    action: localizeThompsonAction(thompsonTitle, useBs) ?? (useBs ? "Unosite glukozu dosljedno" : "Keep glucose logging consistent"),
    source: thompsonTitle ? (useBs ? "Promijenjeno zbog Thompson rangiranja" : "Changed by Thompson ranking") : (useBs ? "Zadana akcija praćenja" : "Default monitoring action"),
    adaptation: thompsonTitle
      ? (useBs
        ? `Ovo je trenutni ${thompsonType ?? "rangirani"} krug; označavanje odgovora korisnim / nekorisnim mijenja buduće rangiranje.`
        : `This is the current ${thompsonType ?? "ranked"} arm; marking answers useful/not useful changes future ranking.`)
      : (useBs ? "Sačuvajte povratnu informaciju u chatu da naučite Glyco koja vrsta akcije vam odgovara." : "Save feedback in chat to teach Glyco which action type works for you."),
  };
}

export function Overview() {
  const auth = useAuth();
  const { t, language } = useI18n();
  const { unit } = useGlucoseUnit();
  const bs = language === "bs";
  const userId = auth.session?.userId ?? 1;
  const navigate = useNavigate();
  const [feeling, setFeeling] = useState<Feeling | null>(null);
  const [selectedSymptoms, setSelectedSymptoms] = useState<string[]>([]);
  const [chatOpen, setChatOpen] = useState(false);
  const [chatExpanding, setChatExpanding] = useState(false);
  const [avatarActivated, setAvatarActivated] = useState(false);
  const [riskModalOpen, setRiskModalOpen] = useState(false);
  const chatSession = useAgentChatSession();
  const chatThreadRef = useRef<HTMLDivElement>(null);

  const risk = useQuery({ queryKey: ["risk", userId], queryFn: () => api.latestRisk(userId) });
  const monitoring = useQuery({ queryKey: ["monitoring", userId], queryFn: () => api.latestMonitoring(userId) });
  const bayesian = useQuery({ queryKey: ["bayesian", userId], queryFn: () => api.bayesianRisk(userId) });
  const logs = useQuery({ queryKey: ["logs", userId], queryFn: () => api.logs(userId) });
  const insight = useQuery({ queryKey: ["insight", userId], queryFn: () => api.insight(userId) });
  const forecast = useQuery({ queryKey: ["forecast", userId], queryFn: () => api.getForecastLatest(userId).catch(() => null), retry: false });

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
  const avatarCopy = (() => {
    const copy = glycoCopy(glycoState);
    if (!bs) return copy;
    return {
      ...copy,
      title:
        glycoState === "high"
          ? "Uočen rizik"
          : glycoState === "elevated"
            ? "Blago povišeno"
            : glycoState === "low"
              ? "Signal niske energije"
              : glycoState === "good"
                ? "Dobar dan"
                : glycoState === "no-data"
                  ? "Čekamo podatke"
                  : "Stabilna glukoza",
      subtitle:
        glycoState === "high"
          ? "Topliji spoljašnji prsten znači da Glyco prati jači signal."
          : glycoState === "elevated"
            ? "Svjetliji centar pokazuje da se glukoza kreće iznad uobičajenog raspona."
            : glycoState === "low"
              ? "Hladnija jezgra odražava simptome niže energije ili slabiji obrazac glukoze."
              : glycoState === "good"
                ? "Veći i glatkiji sjaj znači da današnji obrazac izgleda mirno."
                : glycoState === "no-data"
                  ? "Glyco će zasvijetliti čim stignu očitanja i prijave stanja."
                  : "Spora zelena animacija disanja znači da nema hitnog obrasca.",
    };
  })();
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
    bs,
    formatGlucose: (value) => formatGlucoseFromMgdl(value, unit),
  });

  const chat = useMutation({
    mutationFn: (message: string) => api.agentChat(message, userId),
    onSuccess: (response, message) => {
      appendAgentAssistantMessage(response.answer, response);
    },
    onError: () => {
      appendAgentAssistantMessage(t("agent.apiUnavailable"));
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
      <section className="glyco-hero" aria-label={bs ? "Glyco zdravstveni pregled" : "Glyco health overview"}>
        <div className="glyco-status-top">
          <div>
            <span>Glyco</span>
            <h1>{t("overview.howAreYou")}</h1>
          </div>
          <Badge tone={glycoState === "high" ? "warning" : glycoState === "stable" || glycoState === "good" ? "good" : "neutral"}>
            {avatarCopy.title}
          </Badge>
        </div>

        {(risk.isError || monitoring.isError || logs.isError) && (
          <ErrorState title={bs ? "Neki zdravstveni signali nisu dostupni" : "Some health signals are unavailable"} body={bs ? "Glyco i dalje može primiti prijavu stanja, ali živi podaci modela nisu mogli biti učitani." : "Glyco can still accept a check-in, but live model data could not be loaded."} />
        )}

        <div className="glyco-orbit">
          <button type="button" className="metric-card glucose" onClick={() => navigate("/metric/glucose")}>
            <span>{bs ? "Nivo glukoze" : "Glucose Level"}</span>
            <strong>{formatGlucoseFromMgdl(latestLog?.glucose_level, unit)}</strong>
          </button>
          <button type="button" className="metric-card nutrition" onClick={() => navigate("/care-plan")}>
            <span>{bs ? "Ishrana" : "Nutrition"}</span>
            <strong>{bs ? "Plan" : "Plan"}</strong>
          </button>
          <button type="button" className="metric-card forecast" onClick={() => navigate("/monitoring")}>
            <span>{bs ? "Prognoza" : "Forecast"}</span>
            <strong>{forecast.data?.trend_direction ?? (bs ? "Učenje" : "Learning")}</strong>
          </button>
          <button type="button" className="metric-card risk-score" onClick={() => setRiskModalOpen(true)}>
            <span>{bs ? "Rizik" : "Risk Score"}</span>
            <strong>{risk.data?.risk_level ?? (bs ? "Učitavanje" : "Loading")}</strong>
          </button>
          <button type="button" className="metric-card next-step" onClick={() => navigate("/monitoring")}>
            <span>{bs ? "Sljedeći korak" : "Next Step"}</span>
            <strong>{usefulInsight.action}</strong>
          </button>

          <div className="glyco-center">
            <button
              type="button"
              className={`glyco-avatar-button ${avatarActivated ? "is-activated" : ""}`}
              onClick={activateAvatar}
              aria-label={bs ? `Aktiviraj Glyco avatar. Trenutno stanje: ${avatarCopy.title}` : `Activate Glyco avatar. Current state: ${avatarCopy.title}`}
            >
              <GlycoAvatar state={glycoState} />
            </button>
          </div>
        </div>
        <div className="glyco-center-label">
          <strong>{avatarCopy.title}</strong>
          <span>{avatarCopy.subtitle}</span>
        </div>
        <div className="agent-learning-strip" aria-label={bs ? "Signali učenja agenta" : "Agent learning signals"}>
          <button type="button" onClick={() => navigate("/metric/bayesian")}>
            <span>{bs ? "Bajesovski rizik" : "Bayesian Risk"}</span>
            <strong>{bayesian.data ? `${Math.round(bayesian.data.posterior_mean * 100)}%` : "--"}</strong>
            <small>{bayesian.data ? `${bayesian.data.number_of_updates} ${bs ? "ažuriranja posteriora" : "posterior updates"}` : (bs ? "Čekamo posterior" : "Waiting for posterior")}</small>
          </button>
          <button type="button" onClick={() => navigate("/metric/thompson")}>
            <span>{bs ? "Thompson rangiranje" : "Thompson Ranker"}</span>
            <strong>{thompsonAction?.type ?? (bs ? "Učenje" : "Learning")}</strong>
            <small>{thompsonAction?.title ?? (bs ? "Rangira sljedeću najbolju akciju prema povratnoj informaciji" : "Ranking next best action from feedback")}</small>
          </button>
        </div>

        <div className="checkin-panel">
          <div className="checkin-question">
            <Sparkles size={18} />
            <span>{bs ? "Glyco pita" : "Glyco asks"}</span>
            <strong>{bs ? "Kako se danas osjećate?" : "How are you feeling today?"}</strong>
          </div>
          <div className="feeling-row" role="group" aria-label={bs ? "Odaberite kako se osjećate" : "Select how you feel"}>
            <button className={feeling === "good" ? "active" : ""} type="button" onClick={() => setFeeling("good")}>{bs ? "Dobro" : "Good"}</button>
            <button className={feeling === "low" ? "active" : ""} type="button" onClick={() => setFeeling("low")}>{bs ? "Nisko / umorno" : "Low / tired"}</button>
            <button className={feeling === "elevated" ? "active" : ""} type="button" onClick={() => setFeeling("elevated")}>{bs ? "Pomalo loše" : "A bit off"}</button>
          </div>
          <div className="symptom-row" role="group" aria-label={bs ? "Odaberite simptome" : "Select symptoms"}>
            {symptoms.map((symptom) => (
              <button className={selectedSymptoms.includes(symptom) ? "active" : ""} key={symptom} type="button" onClick={() => toggleSymptom(symptom)}>
                {bs ? ({ Fatigue: "Umor", Thirst: "Žeđ", Headache: "Glavobolja", Dizziness: "Vrtoglavica" } as Record<string, string>)[symptom] ?? symptom : symptom}
              </button>
            ))}
          </div>
        </div>

        <div className="today-insight">
            <span>{bs ? "Šta Glyco sada preporučuje" : "What Glyco recommends now"}</span>
          <p>{usefulInsight.title}</p>
          <small>{usefulInsight.reason}</small>
          <div className="insight-action-row">
            <strong>{t("overview.nextBestAction")}</strong>
            <button type="button" onClick={() => navigate("/monitoring")}>
              {usefulInsight.action}
            </button>
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
          placeholder={bs ? "Pitajte Glyco o ovom obrascu..." : "Ask Glyco about this pattern..."}
          aria-label={bs ? "Pitaj Glyco" : "Ask Glyco"}
        />
        <button className="primary" type="submit" aria-label={bs ? "Pošalji poruku" : "Send message"}><ArrowUp size={16} /></button>
      </form>

      {riskModalOpen && (
        <div
          className="log-panel-overlay alerts-overlay"
          role="dialog"
          aria-modal="true"
          aria-label={bs ? "Detalji rizika" : "Risk details"}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setRiskModalOpen(false);
          }}
        >
          <div className="log-panel risk-panel" onMouseDown={(event) => event.stopPropagation()}>
            <section className="card">
              <header>
                <h2>{bs ? "Šta ovaj rizik znači" : "What this risk means"}</h2>
                <button
                  type="button"
                  className="icon-button"
                  onClick={() => setRiskModalOpen(false)}
                  aria-label={bs ? "Zatvori detalje rizika" : "Close risk details"}
                >
                  <X size={18} aria-hidden="true" />
                </button>
              </header>
              <div className="card-body risk-panel-body">
                {risk.isLoading ? (
                  <LoadingState label={bs ? "Učitavanje procjene rizika" : "Loading risk assessment"} />
                ) : risk.data ? (
                  <>
                    <div className="risk-panel-summary">
                      <div>
                        <span>{bs ? "Trenutni nivo" : "Current level"}</span>
                        <strong>{risk.data.risk_level}</strong>
                      </div>
                      <div>
                        <span>{bs ? "Procijenjena vjerovatnoća" : "Estimated probability"}</span>
                        <strong>{Math.round(risk.data.risk_probability * 100)}%</strong>
                      </div>
                      <div>
                        <span>{bs ? "Model" : "Model"}</span>
                        <strong>{risk.data.model_version}</strong>
                      </div>
                    </div>
                    <p className="risk-panel-explanation">{risk.data.explanation}</p>
                    <section className="risk-panel-section">
                      <strong>{bs ? "Šta je najviše uticalo" : "What influenced it most"}</strong>
                      <FactorList items={risk.data.top_factors} />
                    </section>
                    <section className="risk-panel-section">
                      <strong>{bs ? "Šta sada ima smisla uraditi" : "What makes sense to do now"}</strong>
                      <div className="risk-panel-actions">
                        {risk.data.next_actions.map((action) => (
                          <div key={action} className="risk-panel-action-item">{action}</div>
                        ))}
                      </div>
                    </section>
                  </>
                ) : (
                  <ErrorState
                    title={bs ? "Procjena rizika nije dostupna" : "Risk assessment is unavailable"}
                    body={bs ? "Glyco trenutno nema dovoljno podataka da objasni ovaj signal." : "Glyco does not currently have enough data to explain this signal."}
                  />
                )}
              </div>
            </section>
          </div>
        </div>
      )}

      {chatOpen && (
        <aside className={`glyco-chat-window ${chatExpanding ? "route-expanding" : ""}`} aria-label={bs ? "Glyco chat prozor" : "Glyco chat window"}>
          <header>
            <div>
              <span>{bs ? "AI chat" : "AI Chat"}</span>
              <strong>Glyco</strong>
            </div>
            <div className="glyco-chat-actions">
              <button type="button" className="icon-button" onClick={expandChat} aria-label={bs ? "Otvori puni Glyco chat" : "Open full Glyco chat"}>
                <Maximize2 size={16} />
              </button>
              <button type="button" className="icon-button" onClick={() => setChatOpen(false)} aria-label={bs ? "Zatvori chat" : "Close chat"}>
                <X size={16} />
              </button>
            </div>
          </header>
          <div ref={chatThreadRef} className="glyco-chat-thread" aria-live="polite">
            {chatSession.messages.map((message, index) => (
              <article className={`glyco-chat-message ${message.role}`} key={`${message.role}-${index}`}>
                <span>{message.role === "assistant" ? "Glyco" : (bs ? "Vi" : "You")}</span>
                <p>{message.content}</p>
              </article>
            ))}
            {chat.isPending && <LoadingState label={bs ? "Glyco čita vaš trend i prijavu stanja" : "Glyco is reading your trend and check-in"} />}
          </div>
        </aside>
      )}
    </div>
  );
}
