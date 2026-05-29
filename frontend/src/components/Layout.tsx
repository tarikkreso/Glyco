import { Activity, BarChart3, ClipboardList, FileText, Home, Menu, MessageSquareText, PanelLeftClose, PanelLeftOpen, Settings, Share2, Utensils } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/auth";
import { GlobalQuickActions } from "./GlobalQuickActions";
import { ToastProvider } from "./ui";
import { useI18n } from "../i18n";

const nav = [
  { to: "/overview", labelKey: "nav.overview", icon: Home },
  { to: "/agent", labelKey: "nav.agent", icon: MessageSquareText },
  { to: "/monitoring", labelKey: "nav.monitoring", icon: Activity },
  { to: "/reports", labelKey: "nav.reports", icon: FileText },
  { to: "/care-plan", labelKey: "nav.carePlan", icon: ClipboardList },
  { to: "/family", labelKey: "nav.family", icon: Share2 },
  { to: "/profile", labelKey: "nav.profile", icon: Settings },
];

export function Layout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const auth = useAuth();
  const { language, setLanguage, t } = useI18n();
  const navigate = useNavigate();
  const initials = auth.session?.email.slice(0, 2).toUpperCase() ?? "SK";
  const isBosnian = language === "bs";

  return (
    <ToastProvider>
      <div className={`shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
        <aside className="sidebar">
          <div className="brand-mark">
            <div className="seal">
              <img src="/logo.png" alt="Glyco Logo" style={{ width: "24px", height: "24px", objectFit: "contain" }} />
            </div>
            <div>
              <strong>Glyco</strong>
              <span>{t("app.clinicalCenter")}</span>
            </div>
          </div>
          <button
            type="button"
            className="sidebar-collapse-button"
            onClick={() => setSidebarCollapsed((value) => !value)}
            aria-label={sidebarCollapsed ? (isBosnian ? "Proširi navigaciju" : "Expand navigation") : (isBosnian ? "Sažmi navigaciju" : "Collapse navigation")}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <nav>
            {nav.map((item) => {
              const Icon = item.icon;
              const label = t(item.labelKey);
              return <NavLink to={item.to} key={item.to} title={sidebarCollapsed ? label : undefined}><Icon size={19} /><span>{label}</span></NavLink>;
            })}
          </nav>
          <div className="sidebar-footer">
            <button
              type="button"
              className="sidebar-logout-button"
              onClick={() => {
                auth.logout();
                navigate("/login", { replace: true });
              }}
            >
              {t("app.logout")}
            </button>
          </div>
        </aside>
        <main>
          <header className="topbar">
              <div className="mobile-brand"><Menu size={18} /> Glyco</div>
            <div className="topbar-actions">
              <label className="language-switch">
                <span>{t("app.language")}</span>
                <select value={language} onChange={(event) => setLanguage(event.target.value as "en" | "bs")}>
                  <option value="en">EN</option>
                  <option value="bs">BS</option>
                </select>
              </label>
              <button type="button" className="topbar-account" onClick={() => navigate("/profile")} aria-label={t("app.openProfile")}>
                <span>{auth.session?.fullName || auth.session?.email}</span>
                <div className="avatar">{initials}</div>
              </button>
            </div>
          </header>
          <Outlet />
          <GlobalQuickActions />
        </main>
        <nav className="bottom-nav">
          {nav.slice(0, 5).map((item) => {
            const Icon = item.icon === ClipboardList ? Utensils : item.icon;
            return <NavLink to={item.to} key={item.to}><Icon size={17} /><span>{t(item.labelKey).split(" ")[0]}</span></NavLink>;
          })}
        </nav>
      </div>
    </ToastProvider>
  );
}
