import { Activity, BarChart3, ClipboardList, FileText, HeartPulse, Home, Menu, MessageSquareText, Share2, Utensils } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

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
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand-mark">
          <div className="seal"><BarChart3 size={18} /></div>
          <div>
            <strong>Glyco</strong>
            <span>Clinical Center</span>
          </div>
        </div>
        <nav>
          {nav.map((item) => {
            const Icon = item.icon;
            return <NavLink to={item.to} key={item.to}><Icon size={19} />{item.label}</NavLink>;
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
          <input aria-label="Search" placeholder="Search..." />
          <div className="avatar">SK</div>
        </header>
        <Outlet />
      </main>
      <nav className="bottom-nav">
        {nav.slice(0, 5).map((item) => {
          const Icon = item.icon === ClipboardList ? Utensils : item.icon;
          return <NavLink to={item.to} key={item.to}><Icon size={17} /><span>{item.label.split(" ")[0]}</span></NavLink>;
        })}
      </nav>
    </div>
  );
}
