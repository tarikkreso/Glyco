import { PageHeader } from "../components/ui";
import { RiskCheckFlow } from "./RiskCheck";

export function RiskCheckDemo() {
  return (
    <div className="page narrow">
      <PageHeader
        title="Risk Check"
        subtitle="Try the diabetes risk check without creating an account."
        meta="Demo mode"
      />

      <RiskCheckFlow variant="demo" />
    </div>
  );
}
