import { Navigate, Route, Routes } from "react-router-dom";
import { RequireAuth } from "./auth/RequireAuth";
import { Layout } from "./components/Layout";
import { Agent } from "./pages/Agent";
import { Login } from "./pages/Login";
import { Overview } from "./pages/Overview";
import { ProfileSettings } from "./pages/ProfileSettings";
import { RiskCheck } from "./pages/RiskCheck";
import { RiskCheckDemo } from "./pages/RiskCheckDemo";
import { Register } from "./pages/Register";
import { Monitoring } from "./pages/Monitoring";
import { Reports } from "./pages/Reports";
import { CarePlan } from "./pages/CarePlan";
import { FamilyView } from "./pages/FamilyView";
import { MetricDetail } from "./pages/MetricDetail";

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/risk-check-demo" replace />} />
      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/risk-check-demo" element={<RiskCheckDemo />} />
      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route path="/overview" element={<Overview />} />
        <Route path="/agent" element={<Agent />} />
        <Route path="/risk-check" element={<RiskCheck />} />
        <Route path="/profile" element={<ProfileSettings />} />
        <Route path="/monitoring" element={<Monitoring />} />
        <Route path="/metric/:metricId" element={<MetricDetail />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/care-plan" element={<CarePlan />} />
        <Route path="/family" element={<FamilyView />} />
      </Route>
      <Route path="/share/:token" element={<FamilyView isPublic={true} />} />
      <Route path="*" element={<Navigate to="/risk-check-demo" replace />} />
    </Routes>
  );
}
