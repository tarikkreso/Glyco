import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/ui";
import { useAuth } from "../auth/auth";
import { RiskCheckFlow } from "./RiskCheck";

export function Onboarding() {
  const auth = useAuth();
  const navigate = useNavigate();

  return (
    <div className="page narrow onboarding-page">
      <PageHeader
        title="Set Up Your Baseline"
        subtitle="Complete one guided risk check so Glyco can personalize your dashboard from the first screen."
        meta={auth.session?.email}
      />

      <RiskCheckFlow
        variant="onboarding"
        userId={auth.session?.userId ?? 1}
        onComplete={() => {
          navigate("/overview", { replace: true });
        }}
      />
    </div>
  );
}
