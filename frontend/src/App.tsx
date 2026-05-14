import { Navigate, Route, Routes } from "react-router-dom";
import { Layout } from "./components/Layout";
import { Agent } from "./pages/Agent";
import { Overview } from "./pages/Overview";
import { RiskCheck } from "./pages/RiskCheck";
import { Monitoring } from "./pages/Monitoring";
import { Reports } from "./pages/Reports";
import { CarePlan } from "./pages/CarePlan";
import { FamilyView } from "./pages/FamilyView";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { RiskCheckDemo } from "./pages/RiskCheckDemo";
import { Onboarding } from "./pages/Onboarding";
import { RequireAuth } from "./auth/RequireAuth";
import { useAuth } from "./auth/auth";

function IndexRedirect() {
  const auth = useAuth();
  if (!auth.isAuthenticated) return <Navigate to="/login" replace />;
  if (!auth.session?.onboardingComplete) return <Navigate to="/onboarding" replace />;
  return <Navigate to="/overview" replace />;
}

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<IndexRedirect />} />

      <Route path="/login" element={<Login />} />
      <Route path="/register" element={<Register />} />
      <Route path="/risk-check-demo" element={<RiskCheckDemo />} />
      <Route path="/share/:token" element={<FamilyView />} />

      <Route
        path="/onboarding"
        element={
          <RequireAuth>
            <Onboarding />
          </RequireAuth>
        }
      />

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
        <Route path="/monitoring" element={<Monitoring />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/care-plan" element={<CarePlan />} />
        <Route path="/family" element={<FamilyView />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
