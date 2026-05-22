import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Agent } from "./pages/Agent";
import { Overview } from "./pages/Overview";
import { RiskCheck } from "./pages/RiskCheck";
import { Monitoring } from "./pages/Monitoring";
import { Reports } from "./pages/Reports";
import { CarePlan } from "./pages/CarePlan";
import { FamilyView } from "./pages/FamilyView";
import { MetricDetail } from "./pages/MetricDetail";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Navigate to="/overview" replace />} />
        <Route path="/overview" element={<Overview />} />
        <Route path="/agent" element={<Agent />} />
        <Route path="/risk-check" element={<RiskCheck />} />
        <Route path="/monitoring" element={<Monitoring />} />
        <Route path="/metric/:metricId" element={<MetricDetail />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/care-plan" element={<CarePlan />} />
        <Route path="/family" element={<FamilyView />} />
      </Route>
      <Route path="/share/:token" element={<FamilyView isPublic={true} />} />
    </Routes>
  );
}
