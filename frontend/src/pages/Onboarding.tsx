import { useNavigate } from "react-router-dom";
import { PageHeader } from "../components/ui";
import { useAuth } from "../auth/auth";
import { RiskCheckFlow } from "./RiskCheck";
import { useI18n } from "../i18n";

export function Onboarding() {
  const auth = useAuth();
  const { language } = useI18n();
  const navigate = useNavigate();
  const bs = language === "bs";

  return (
    <div className="page narrow onboarding-page">
      <PageHeader
        title={bs ? "Postavite početno stanje" : "Set Up Your Baseline"}
        subtitle={bs ? "Dovršite jednu vođenu provjeru rizika kako bi Glyco personalizirao vaš pregled od prvog ekrana." : "Complete one guided risk check so Glyco can personalize your dashboard from the first screen."}
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
