import { Activity, BarChart3, ClipboardList, FileText, Home, Menu, MessageSquareText, PanelLeftClose, PanelLeftOpen, Settings, Share2, Utensils } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { useAuth } from "../auth/auth";
import { GlobalQuickActions } from "./GlobalQuickActions";
import { ToastProvider } from "./ui";

const nav = [
  { to: "/overview", label: "Overview", icon: Home },
  { to: "/agent", label: "Agent", icon: MessageSquareText },
  { to: "/monitoring", label: "Monitoring", icon: Activity },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/care-plan", label: "Care Plan", icon: ClipboardList },
  { to: "/family", label: "Family View", icon: Share2 },
  { to: "/profile", label: "Profile", icon: Settings },
];

export function Layout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const auth = useAuth();
  const navigate = useNavigate();
  const initials = auth.session?.email.slice(0, 2).toUpperCase() ?? "SK";

  return (
    <ToastProvider>
      <div className={`shell ${sidebarCollapsed ? "sidebar-collapsed" : ""}`}>
        <aside className="sidebar">
          <div className="brand-mark">
            <div className="seal"><BarChart3 size={18} /></div>
            <div>
              <strong>Glyco</strong>
              <span>Clinical Center</span>
            </div>
          </div>
          <button
            type="button"
            className="sidebar-collapse-button"
            onClick={() => setSidebarCollapsed((value) => !value)}
            aria-label={sidebarCollapsed ? "Expand navigation" : "Collapse navigation"}
          >
            {sidebarCollapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <nav>
            {nav.map((item) => {
              const Icon = item.icon;
              return <NavLink to={item.to} key={item.to} title={sidebarCollapsed ? item.label : undefined}><Icon size={19} /><span>{item.label}</span></NavLink>;
            })}
          </nav>
          <div className="sidebar-footer">
            <span>Help Center</span>
            <button
              type="button"
              className="link-button"
              onClick={() => {
                auth.logout();
                navigate("/login", { replace: true });
              }}
            >
              Logout
            </button>
          </div>
        </aside>
        <main>
          <header className="topbar">
            <div className="mobile-brand"><Menu size={18} /> Glyco</div>
            <button type="button" className="topbar-account" onClick={() => navigate("/profile")} aria-label="Open profile settings">
              <span>{auth.session?.fullName || auth.session?.email}</span>
              <div className="avatar">{initials}</div>
            </button>
          </header>
          <Outlet />
          <GlobalQuickActions />
        </main>
        <nav className="bottom-nav">
          {nav.slice(0, 5).map((item) => {
            const Icon = item.icon === ClipboardList ? Utensils : item.icon;
            return <NavLink to={item.to} key={item.to}><Icon size={17} /><span>{item.label.split(" ")[0]}</span></NavLink>;
          })}
        </nav>
      </div>
    </ToastProvider>
  );
}
