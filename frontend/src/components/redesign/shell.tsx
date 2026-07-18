'use client';

import { useEffect, useState, type ReactNode } from 'react';
import { PanelLeftClose, PanelLeft, Search, Bell } from 'lucide-react';

export type NavItem = { key: string; label: string; icon: ReactNode; href?: string };

// ── ModuleShell: sidebar navy recolhível + topbar branca + conteúdo ──────────
export function ModuleShell({
  brand = 'PRO',
  nav,
  active,
  onNav,
  crumb,
  cta,
  user = { name: 'Jordan Jesus', role: 'admin' },
  children,
}: {
  brand?: string;
  nav: NavItem[];
  active: string;
  onNav?: (key: string) => void;
  crumb: ReactNode;
  cta?: ReactNode;
  user?: { name: string; role: string };
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  useEffect(() => {
    const v = typeof window !== 'undefined' ? localStorage.getItem('rd-sidebar-collapsed') : null;
    if (v === '1') setCollapsed(true);
  }, []);
  const toggle = () => {
    setCollapsed((c) => {
      const n = !c;
      try { localStorage.setItem('rd-sidebar-collapsed', n ? '1' : '0'); } catch { /* */ }
      return n;
    });
  };
  const initials = user.name.split(' ').map((n) => n[0]).slice(0, 2).join('').toUpperCase();

  return (
    <div className="rd-shell">
      <aside className={`rd-sidebar${collapsed ? ' collapsed' : ''}`}>
        <div className="rd-brand">
          <div className="rd-brand-mark">C</div>
          <div className="rd-brand-name">CONECTA <b>{brand}</b></div>
        </div>
        <nav className="rd-nav">
          {nav.map((it) => (
            <button key={it.key} type="button"
              className={`rd-nav-item${it.key === active ? ' active' : ''}`}
              onClick={() => onNav?.(it.key)} title={it.label}>
              {it.icon}<span>{it.label}</span>
            </button>
          ))}
        </nav>
        <div className="rd-side-foot">
          <div className="rd-avatar">{initials}</div>
          {!collapsed && (
            <div>
              <div className="n">{user.name}</div>
              <div className="r">{user.role}</div>
            </div>
          )}
        </div>
      </aside>

      <div className="rd-main">
        <header className="rd-topbar">
          <button type="button" className="rd-icon-btn" onClick={toggle} aria-label="Recolher menu"
            style={{ border: 'none', background: 'transparent' }}>
            {collapsed ? <PanelLeft size={18} /> : <PanelLeftClose size={18} />}
          </button>
          <div className="rd-crumb">{crumb}</div>
          <div className="rd-search">
            <Search size={16} color="var(--placeholder)" />
            <input placeholder="Buscar…" />
          </div>
          <button type="button" className="rd-icon-btn" aria-label="Notificações">
            <Bell size={18} />
            <span className="rd-dot-badge">3</span>
          </button>
          {cta}
        </header>
        <main className="rd-content">{children}</main>
      </div>
    </div>
  );
}

// ── Primitivos ───────────────────────────────────────────────────────────────
export function KpiCard({ icon, value, label, delta, trend = 'flat' }:
  { icon: ReactNode; value: ReactNode; label: string; delta?: string; trend?: 'up' | 'flat' | 'down' }) {
  return (
    <div className="rd-kpi">
      <div className="rd-kpi-ico">{icon}</div>
      <div className="rd-kpi-v">{value}</div>
      <div className="rd-kpi-l">{label}</div>
      {delta && <div className={`rd-kpi-delta rd-${trend}`}>{delta}</div>}
    </div>
  );
}

const BADGE_CLASS: Record<string, string> = {
  success: 'rd-b-success', warning: 'rd-b-warning', error: 'rd-b-error',
  info: 'rd-b-info', orange: 'rd-b-orange', neutral: 'rd-b-neutral',
};
export function StatusBadge({ tone = 'neutral', dot = true, children }:
  { tone?: keyof typeof BADGE_CLASS; dot?: boolean; children: ReactNode }) {
  return <span className={`rd-badge ${BADGE_CLASS[tone]}${dot ? '' : ' plain'}`}>{children}</span>;
}

export function ModuleTile({ icon, name, sub, onClick }:
  { icon: ReactNode; name: string; sub?: string; onClick?: () => void }) {
  return (
    <button type="button" className="rd-tile" onClick={onClick}>
      <div className="rd-tile-ico">{icon}</div>
      <div className="rd-tile-name">{name}</div>
      {sub && <div className="rd-tile-sub">{sub}</div>}
    </button>
  );
}

export function Btn({ variant = 'primary', children, ...p }:
  { variant?: 'primary' | 'navy' | 'outline' | 'ghost' | 'danger' } & React.ButtonHTMLAttributes<HTMLButtonElement>) {
  const cls: Record<string, string> = {
    primary: 'rd-btn-primary', navy: 'rd-btn-navy', outline: 'rd-btn-outline',
    ghost: 'rd-btn-ghost', danger: 'rd-btn-danger',
  };
  return <button className={`rd-btn ${cls[variant]}`} {...p}>{children}</button>;
}
