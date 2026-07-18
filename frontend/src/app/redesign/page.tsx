'use client';

import { useState } from 'react';
import {
  Home, Shield, Users, Wallet, Landmark, FolderArchive, ShieldCheck, Settings,
  MapPin, Building2, CalendarDays, Plus, ArrowRight, AlertTriangle,
} from 'lucide-react';
import { ModuleShell, KpiCard, ModuleTile, StatusBadge, Btn, type NavItem } from '@/components/redesign/shell';

const NAV: NavItem[] = [
  { key: 'inicio', label: 'Início', icon: <Home size={18} /> },
  { key: 'operacional', label: 'Operacional', icon: <Shield size={18} /> },
  { key: 'rh', label: 'Gestão RH', icon: <Users size={18} /> },
  { key: 'financeiro', label: 'Financeiro', icon: <Wallet size={18} /> },
  { key: 'fiscal', label: 'Fiscal Contábil', icon: <Landmark size={18} /> },
  { key: 'ged', label: 'GED', icon: <FolderArchive size={18} /> },
  { key: 'compliance', label: 'Compliance', icon: <ShieldCheck size={18} /> },
  { key: 'config', label: 'Configurações', icon: <Settings size={18} /> },
];

const PENDENCIAS = [
  { titulo: 'Alvará de Funcionamento', meta: 'Vencida desde 27/02', tone: 'error' as const, cta: 'Resolver' },
  { titulo: 'Certidão Estadual', meta: 'Vence em 22 dias', tone: 'warning' as const, cta: 'Ver' },
  { titulo: 'CRF — FGTS', meta: 'Vence em 22 dias', tone: 'warning' as const, cta: 'Ver' },
];

const ATIVIDADE = [
  { dot: 'var(--success)', titulo: 'Escala publicada · Posto Centro', meta: 'há 2 horas' },
  { dot: 'var(--info)', titulo: 'Admissão · Maria Silva', meta: 'há 4 horas' },
  { dot: 'var(--warning)', titulo: 'Documento vencendo · CRF FGTS', meta: 'ontem' },
];

const SEMANA = ['S', 'T', 'Q', 'Q', 'S', 'S', 'D'];

export default function RedesignHome() {
  const [active, setActive] = useState('inicio');
  return (
    <ModuleShell
      brand="PRO"
      nav={NAV}
      active={active}
      onNav={setActive}
      crumb={<><b>Início</b></>}
      cta={<Btn variant="primary"><Plus size={16} /> Nova escala</Btn>}
    >
      {/* Saudação */}
      <div>
        <div className="rd-page-title">Bom dia, Jordan</div>
        <div className="rd-page-sub">Sábado, 18 de julho de 2026 · <span style={{ color: 'var(--orange-txt)', fontWeight: 700 }}>3 pendências</span></div>
      </div>

      {/* KPIs */}
      <div className="rd-kpis">
        <KpiCard icon={<Users size={20} />} value="51" label="Colaboradores" delta="▲ +3" trend="up" />
        <KpiCard icon={<MapPin size={20} />} value="9" label="Postos ativos" delta="= estável" trend="flat" />
        <KpiCard icon={<Building2 size={20} />} value="10" label="Clientes pagantes" delta="▲ +1" trend="up" />
        <KpiCard icon={<CalendarDays size={20} />} value="19" label="Escalas" delta="2 pendentes" trend="flat" />
      </div>

      {/* Acesso rápido */}
      <div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div className="rd-section-h">Acesso rápido</div>
          <a href="#" style={{ fontSize: 13, fontWeight: 600 }}>Ver todos →</a>
        </div>
        <div className="rd-tiles">
          <ModuleTile icon={<Shield size={22} />} name="Operacional" sub="9 postos" />
          <ModuleTile icon={<Users size={22} />} name="Gestão RH" sub="51 pessoas" />
          <ModuleTile icon={<Wallet size={22} />} name="Financeiro" sub="Contas · fluxo" />
          <ModuleTile icon={<FolderArchive size={22} />} name="GED" sub="2.539 docs" />
        </div>
      </div>

      {/* Duas colunas: pendências + atividade / escalas */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr)', gap: 'var(--gap)', alignItems: 'start' }}>
        {/* Pendências */}
        <div className="rd-card rd-card-pad">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
            <div className="rd-section-h" style={{ fontSize: 16, display: 'flex', alignItems: 'center', gap: 8 }}>
              <AlertTriangle size={17} color="var(--warning)" /> Pendências
            </div>
            <a href="#" style={{ fontSize: 12.5, fontWeight: 600 }}>Resolver pendências →</a>
          </div>
          <div className="rd-list">
            {PENDENCIAS.map((p, i) => (
              <div className="rd-list-item" key={i}>
                <span className="rd-list-dot" style={{ background: p.tone === 'error' ? 'var(--error)' : 'var(--warning)' }} />
                <div className="rd-list-main">
                  <div className="rd-list-title">{p.titulo}</div>
                  <div className="rd-list-meta">{p.meta}</div>
                </div>
                <StatusBadge tone={p.tone} dot={false}>{p.cta}</StatusBadge>
              </div>
            ))}
          </div>
        </div>

        {/* Direita: escalas da semana + atividade */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--gap)' }}>
          <div className="rd-card rd-card-pad">
            <div className="rd-label" style={{ marginBottom: 10 }}>Escalas da semana</div>
            <div style={{ display: 'flex', gap: 6 }}>
              {SEMANA.map((d, i) => (
                <div key={i} style={{
                  flex: 1, textAlign: 'center', padding: '10px 0', borderRadius: 10,
                  background: i === 5 ? 'var(--navy)' : 'var(--fill)',
                  color: i === 5 ? '#fff' : 'var(--ink-weak)', fontWeight: 700, fontSize: 12,
                }}>{d}</div>
              ))}
            </div>
          </div>
          <div className="rd-card rd-card-pad">
            <div className="rd-label" style={{ marginBottom: 6 }}>Atividade recente</div>
            <div className="rd-list">
              {ATIVIDADE.map((a, i) => (
                <div className="rd-list-item" key={i}>
                  <span className="rd-list-dot" style={{ background: a.dot }} />
                  <div className="rd-list-main">
                    <div className="rd-list-title" style={{ fontSize: 13 }}>{a.titulo}</div>
                    <div className="rd-list-meta">{a.meta}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </ModuleShell>
  );
}
