import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/ui";
import { useAuth } from "../auth/auth";
import { RiskCheckFlow } from "./RiskCheck";

export function Onboarding() {
  const auth = useAuth();
  const navigate = useNavigate();

  return (
    <div className="page narrow">
      <PageHeader
        title="Onboarding"
        subtitle="Enter your baseline profile and run your first risk check to start tracking."
        meta={auth.session?.email}
      />

      <RiskCheckFlow
        variant="onboarding"
        onComplete={() => {
          auth.completeOnboarding();
          navigate("/overview", { replace: true });
        }}
      />
    </div>
  );
}
