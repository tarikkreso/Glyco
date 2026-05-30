import { Activity, ArrowRight, Bot, FileText, Home, ShieldCheck, Siren, Utensils } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useAuth, type DemoAccount } from "../auth/auth";
import { Badge, PageHeader } from "../components/ui";

const scenarioTone: Record<DemoAccount["scenario"], "good" | "warning" | "danger"> = {
  stable: "good",
  watch: "warning",
  concerning: "danger",
};

const scenarioCopy: Record<DemoAccount["scenario"], { title: string; steps: string[] }> = {
  stable: {
    title: "Stable contrast",
    steps: ["Open Overview", "Show that Glyco stays calm", "Generate a low-noise report"],
  },
  watch: {
    title: "Watch pattern",
    steps: ["Open Monitoring", "Show trend and forecast context", "Move into Nutrition"],
  },
  concerning: {
    title: "Competition storyline",
    steps: ["Open Overview", "Ask the Agent why it changed", "Export doctor-ready report"],
  },
};

function groupedDemos(demos: DemoAccount[]) {
  return demos.reduce<Record<DemoAccount["scenario"], DemoAccount[]>>(
    (groups, demo) => {
      groups[demo.scenario].push(demo);
      return groups;
    },
    { stable: [], watch: [], concerning: [] }
  );
}

export function CompetitionDemo() {
  const auth = useAuth();
  const navigate = useNavigate();
  const groups = groupedDemos(auth.demoAccounts);

  const activate = (demo: DemoAccount, path = "/overview") => {
    auth.switchDemoAccount(demo.email);
    navigate(path);
  };

  return (
    <div className="page competition-demo-page">
      <PageHeader
        title="Competition demo"
        subtitle="Switch between prepared patient stories so judges can see risk, trend, forecast, nutrition, agent reasoning, and reports in under a minute."
        meta="Demo mode"
      />

      <section className="competition-demo-hero">
        <div>
          <Badge tone="good">Recommended path</Badge>
          <h2>Start with Sarah Kovac, then compare stable and watch cases.</h2>
          <p>
            The strongest story is a concerning trend where Glyco explains the signal, recommends the next step, and prepares a doctor handoff.
          </p>
        </div>
        <div className="demo-path-actions">
          <button type="button" className="primary" onClick={() => activate(auth.demoAccounts[0], "/overview")}>
            <Home size={16} /> Start Overview
          </button>
          <button type="button" className="secondary" onClick={() => activate(auth.demoAccounts[0], "/agent")}>
            <Bot size={16} /> Open Agent
          </button>
          <button type="button" className="secondary" onClick={() => activate(auth.demoAccounts[0], "/reports")}>
            <FileText size={16} /> Doctor Report
          </button>
        </div>
      </section>

      <section className="competition-demo-grid">
        {(["concerning", "watch", "stable"] as const).map((scenario) => {
          const copy = scenarioCopy[scenario];
          const demos = groups[scenario];
          const Icon = scenario === "concerning" ? Siren : scenario === "watch" ? Activity : ShieldCheck;
          return (
            <article className="competition-demo-card" key={scenario}>
              <header>
                <div className={`demo-scenario-icon ${scenario}`}>
                  <Icon size={18} />
                </div>
                <div>
                  <Badge tone={scenarioTone[scenario]}>{scenario}</Badge>
                  <h3>{copy.title}</h3>
                </div>
              </header>
              <ol>
                {copy.steps.map((step) => <li key={step}>{step}</li>)}
              </ol>
              <div className="demo-patient-list">
                {demos.map((demo) => (
                  <button type="button" key={demo.email} onClick={() => activate(demo)}>
                    <span>
                      <strong>{demo.fullName}</strong>
                      <small>{demo.description}</small>
                    </span>
                    <ArrowRight size={16} />
                  </button>
                ))}
              </div>
            </article>
          );
        })}
      </section>

      <section className="competition-demo-footer">
        <button type="button" className="secondary" onClick={() => activate(auth.demoAccounts.find((demo) => demo.email === "demo-weekend-spikes") ?? auth.demoAccounts[0], "/care-plan")}>
          <Utensils size={16} /> Show Nutrition handoff
        </button>
        <button type="button" className="secondary" onClick={() => activate(auth.demoAccounts.find((demo) => demo.email === "demo-high-variability") ?? auth.demoAccounts[0], "/monitoring")}>
          <Activity size={16} /> Show forecast confidence
        </button>
      </section>
    </div>
  );
}
