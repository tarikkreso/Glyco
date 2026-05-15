import { Activity, BarChart3, ClipboardList, FileText, HeartPulse, Home, Menu, MessageSquareText, PanelLeftClose, PanelLeftOpen, Share2, Utensils } from "lucide-react";
import { useState } from "react";
import { NavLink, Outlet } from "react-router-dom";
import { GlobalLogNewData } from "./GlobalLogNewData";
import { ToastProvider } from "./ui";

const nav = [
  { to: "/overview", label: "Overview", icon: Home },
  { to: "/agent", label: "Agent", icon: MessageSquareText },
  { to: "/risk-check", label: "Risk Check", icon: HeartPulse },
  { to: "/monitoring", label: "Monitoring", icon: Activity },
  { to: "/reports", label: "Reports", icon: FileText },
  { to: "/care-plan", label: "Care Plan", icon: ClipboardList },
  { to: "/family", label: "Family View", icon: Share2 },
];

export function Layout() {
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

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
            <span>Logout</span>
          </div>
        </aside>
        <main>
          <header className="topbar">
            <div className="mobile-brand"><Menu size={18} /> Glyco</div>
            <div className="avatar">SK</div>
          </header>
          <Outlet />
          <GlobalLogNewData />
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
