import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { Card, ErrorState, PageHeader } from "../components/ui";
import { useAuth } from "../auth/auth";

type FormValues = { email: string; password: string };

export function Register() {
  const auth = useAuth();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const { register, handleSubmit } = useForm<FormValues>({
    defaultValues: { email: "", password: "" },
  });

  if (auth.isAuthenticated) return <Navigate to={auth.session?.onboardingComplete ? "/overview" : "/onboarding"} replace />;

  return (
    <div className="auth-shell">
      <div className="auth-page">
        <PageHeader
          title="Create account"
          subtitle="Set up your profile so Glyco can track changes over time."
        />

        <Card title="Registration">
          <form
            className="form-stack"
            onSubmit={handleSubmit((values) => {
              setError(null);
              const result = auth.register(values);
              if (!result.ok) {
                setError(result.error);
                return;
              }
              navigate("/onboarding", { replace: true });
            })}
          >
            <label>
              Email
              <input type="email" autoComplete="email" {...register("email")} />
            </label>
            <label>
              Password
              <input type="password" autoComplete="new-password" {...register("password")} />
            </label>
            <button className="primary" type="submit">Register</button>
            <Link className="secondary button-link" to="/login">Already have an account</Link>
          </form>

          {error && <ErrorState title="Could not register" body={error} />}
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
