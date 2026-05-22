import { useMemo, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { Card, ErrorState } from "../components/ui";
import { useAuth } from "../auth/auth";

type FormValues = { email: string; password: string };

export function Login() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);

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
          <Link className="secondary button-link" to="/risk-check-demo">Risk check</Link>
          <Link className="primary button-link" to="/register">Create account</Link>
        </div>
      </div>
      <div className="auth-page">
        <section className="auth-copy">
          <BadgeLike>Secure workspace</BadgeLike>
          <h1>Welcome back to your diabetes support dashboard.</h1>
          <p>Sign in to continue tracking glucose logs, forecasts, care plans, reports, and agent guidance.</p>
        </section>

        <Card title="Account">
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
              Email or demo ID
              <input type="text" autoComplete="username" {...register("email")} />
            </label>
            <label>
              Password
              <input type="password" autoComplete="current-password" {...register("password")} />
            </label>
            <button className="primary" type="submit">Sign in</button>
            <Link className="secondary button-link" to="/register">Create account</Link>
          </form>

          {error && <ErrorState title="Could not sign in" body={error} />}
        </Card>

        <div className="auth-bottom">
          <Link className="secondary button-link" to="/risk-check-demo">
            Try Risk Check (no account)
          </Link>
        </div>
      </div>
    </div>
  );
}

function BadgeLike({ children }: { children: string }) {
  return <span className="auth-eyebrow">{children}</span>;
}
