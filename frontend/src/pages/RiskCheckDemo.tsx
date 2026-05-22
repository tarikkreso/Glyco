import { Link } from "react-router-dom";
import { RiskCheckFlow } from "./RiskCheck";

export function RiskCheckDemo() {
  return (
    <div className="public-page">
      <div className="public-nav">
        <Link to="/risk-check-demo" className="public-brand">
          <span className="seal">G</span>
          <strong>Glyco</strong>
        </Link>
        <div>
          <Link className="secondary button-link" to="/login">Sign in</Link>
          <Link className="primary button-link" to="/register">Create account</Link>
        </div>
      </div>

      <section className="public-hero">
        <div>
          <span className="auth-eyebrow">No account needed</span>
          <h1>Check your Type 2 diabetes risk first.</h1>
          <p>Run the existing Glyco risk calculation before signing up. If you want to keep the result and start monitoring, create an account after the snapshot.</p>
        </div>
        <div className="public-hero-points">
          <span>Private demo input</span>
          <span>Model-backed result</span>
          <span>Optional account after</span>
        </div>
      </section>

      <RiskCheckFlow variant="demo" />
    </div>
  );
}
