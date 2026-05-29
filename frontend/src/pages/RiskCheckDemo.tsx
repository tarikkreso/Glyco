import { Link } from "react-router-dom";
import { RiskCheckFlow } from "./RiskCheck";
import { useI18n } from "../i18n";

export function RiskCheckDemo() {
  const { language, setLanguage } = useI18n();
  const bs = language === "bs";
  return (
    <div className="public-page">
      <div className="public-nav">
        <Link to="/risk-check-demo" className="public-brand">
          <span className="seal">G</span>
          <strong>Glyco</strong>
        </Link>
        <div>
          <select className="language-switch" value={language} onChange={(event) => setLanguage(event.target.value as "en" | "bs") }>
            <option value="en">EN</option>
            <option value="bs">BS</option>
          </select>
          <Link className="secondary button-link" to="/login">{bs ? "Prijava" : "Sign in"}</Link>
          <Link className="primary button-link" to="/register">{bs ? "Kreiraj račun" : "Create account"}</Link>
        </div>
      </div>

      <section className="public-hero">
        <div>
          <span className="auth-eyebrow">{bs ? "Nije potreban račun" : "No account needed"}</span>
          <h1>{bs ? "Prvo provjerite rizik za dijabetes tipa 2." : "Check your Type 2 diabetes risk first."}</h1>
          <p>{bs ? "Pokrenite postojeći Glyco izračun rizika prije registracije. Ako želite sačuvati rezultat i početi s praćenjem, kreirajte račun nakon pregleda." : "Run the existing Glyco risk calculation before signing up. If you want to keep the result and start monitoring, create an account after the snapshot."}</p>
        </div>
        <div className="public-hero-points">
          <span>{bs ? "Privatni demo unos" : "Private demo input"}</span>
          <span>{bs ? "Rezultat temeljen na modelu" : "Model-backed result"}</span>
          <span>{bs ? "Opcionalan račun nakon toga" : "Optional account after"}</span>
        </div>
      </section>

      <RiskCheckFlow variant="demo" />
    </div>
  );
}
