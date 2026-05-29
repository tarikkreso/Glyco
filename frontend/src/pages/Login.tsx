import { useMemo, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { Card, ErrorState } from "../components/ui";
import { useAuth } from "../auth/auth";
import { useI18n } from "../i18n";

type FormValues = { email: string; password: string };

export function Login() {
  const auth = useAuth();
  const { language, setLanguage } = useI18n();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);
  const bs = language === "bs";

  const from = useMemo(() => {
    const state = location.state as any;
    return typeof state?.from === "string" && state.from !== "/" ? state.from : "/overview";
  }, [location.state]);

  const { register, handleSubmit } = useForm<FormValues>({
    defaultValues: { email: "", password: "" },
  });

  if (auth.isAuthenticated) return <Navigate to="/overview" replace />;

  return (
    <div className="auth-shell">
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
          <Link className="secondary button-link" to="/risk-check-demo">{bs ? "Provjera rizika" : "Risk check"}</Link>
          <Link className="primary button-link" to="/register">{bs ? "Kreiraj račun" : "Create account"}</Link>
        </div>
      </div>
      <div className="auth-page">
        <section className="auth-copy">
          <BadgeLike>{bs ? "Siguran prostor" : "Secure workspace"}</BadgeLike>
          <h1>{bs ? "Dobro došli nazad na vaš dijabetesni kontrolni panel." : "Welcome back to your diabetes support dashboard."}</h1>
          <p>{bs ? "Prijavite se da nastavite pratiti glukozu, prognoze, plan njege, izvještaje i smjernice agenta." : "Sign in to continue tracking glucose logs, forecasts, care plans, reports, and agent guidance."}</p>
        </section>

        <Card title={bs ? "Račun" : "Account"}>
          <form
            className="form-stack"
            onSubmit={handleSubmit((values) => {
              setError(null);
              const result = auth.login(values);
              if (!result.ok) {
                setError(result.error);
                return;
              }
              navigate(from, { replace: true });
            })}
          >
            <label>
              {bs ? "Email ili demo ID" : "Email or demo ID"}
              <input type="text" autoComplete="username" {...register("email")} />
            </label>
            <label>
              {bs ? "Lozinka" : "Password"}
              <input type="password" autoComplete="current-password" {...register("password")} />
            </label>
            <button className="primary" type="submit">{bs ? "Prijavi se" : "Sign in"}</button>
            <Link className="secondary button-link" to="/register">{bs ? "Kreiraj račun" : "Create account"}</Link>
          </form>

          {error && <ErrorState title={bs ? "Prijava nije uspjela" : "Could not sign in"} body={error} />}
        </Card>

        <div className="auth-bottom">
          <Link className="secondary button-link" to="/risk-check-demo">
            {bs ? "Isprobaj provjeru rizika (bez računa)" : "Try Risk Check (no account)"}
          </Link>
        </div>
      </div>
    </div>
  );
}

function BadgeLike({ children }: { children: string }) {
  return <span className="auth-eyebrow">{children}</span>;
}
