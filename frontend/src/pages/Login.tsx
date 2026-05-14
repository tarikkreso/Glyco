import { useMemo, useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { Card, ErrorState, PageHeader } from "../components/ui";
import { useAuth } from "../auth/auth";

type FormValues = { email: string; password: string };

export function Login() {
  const auth = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [error, setError] = useState<string | null>(null);

  const from = useMemo(() => {
    const state = location.state as any;
    return typeof state?.from === "string" ? state.from : "/";
  }, [location.state]);

  const { register, handleSubmit } = useForm<FormValues>({
    defaultValues: { email: "", password: "" },
  });

  if (auth.isAuthenticated) return <Navigate to={auth.session?.onboardingComplete ? "/overview" : "/onboarding"} replace />;

  return (
    <div className="auth-shell">
      <div className="auth-page">
        <PageHeader
          title="Sign in"
          subtitle="Access your Glyco dashboard and monitoring history."
        />

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
              Email
              <input type="email" autoComplete="email" {...register("email")} />
            </label>
            <label>
              Password
              <input type="password" autoComplete="current-password" {...register("password")} />
            </label>
            <button className="primary" type="submit">Sign in</button>
            <Link className="secondary button-link" to="/register">Create an account</Link>
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
