'use client';

import { useState, useEffect, type ReactNode } from 'react';
import {
  Search, Bell, Users, Shield, Handshake, CalendarDays, DollarSign, Megaphone,
  Trophy, Wrench, FolderKanban, HeartPulse, Clock, User, Headset, Calculator,
  Scale, BarChart3, LineChart, Package, Settings, Link2, Lock, Building2,
  Sparkles, Workflow, LogOut, LayoutGrid, type LucideIcon,
} from 'lucide-react';
import { rdLogout } from '@/components/redesign/session';

// Ícones fixos dos 4 KPIs (os VALORES vêm reais de GET /redesign/home).
const KPI_ICONS: LucideIcon[] = [Users, Shield, Handshake, CalendarDays];
type Kpi = { v: string; l: string };
type Alert = { title: string; meta: string; action: string; dot: string };

type Mod = { name: string; desc: string; Icon: LucideIcon; org?: boolean };
const GROUPS: { name: string; mods: Mod[] }[] = [
  {
    name: 'Negócios',
    mods: [
      { name: 'CRM', desc: 'Leads, propostas e contratos', Icon: Handshake, org: true },
      { name: 'Marketing', desc: 'Funil, campanhas e conteúdo', Icon: Megaphone },
      { name: 'Licitações', desc: 'Editais, propostas e disputas', Icon: Trophy },
      { name: 'Serviços', desc: 'Agendamentos e ordens', Icon: Wrench },
    ],
  },
  {
    name: 'Gestão de Pessoas',
    mods: [
      { name: 'Departamento Pessoal', desc: 'Folha, admissões, férias', Icon: Users },
      { name: 'Recursos Humanos', desc: 'Recrutamento e T&D', Icon: Users },
      { name: 'Gestão de Pessoas', desc: 'GED, ponto, RH, SST', Icon: FolderKanban },
      { name: 'Operacional', desc: 'Postos, escalas e campo', Icon: Shield, org: true },
      { name: 'Saúde Ocupacional', desc: 'PCMSO, exames, riscos', Icon: HeartPulse },
      { name: 'Ponto Eletrônico', desc: 'Batida, banco de horas', Icon: Clock },
      { name: 'Portal do Funcionário', desc: 'Contracheque e documentos', Icon: User },
      { name: 'Recrutamento', desc: 'Vagas e entrevistas', Icon: Users },
    ],
  },
  {
    name: 'Financeiro, Fiscal & Jurídico',
    mods: [
      { name: 'Financeiro', desc: 'Contas, caixa, compras', Icon: DollarSign, org: true },
      { name: 'Fiscal & Contábil', desc: 'NFS-e, impostos, SPED', Icon: Calculator },
      { name: 'Jurídico', desc: 'Processos, contratos, IA', Icon: Scale },
      { name: 'Empresas', desc: 'Multi-empresa, obrigações', Icon: Building2 },
    ],
  },
  {
    name: 'Inteligência & Patrimônio',
    mods: [
      { name: 'BI', desc: 'Business Intelligence', Icon: BarChart3 },
      { name: 'Analytics', desc: 'Métricas de uso', Icon: LineChart },
      { name: 'Relatórios', desc: 'Central de relatórios', Icon: BarChart3 },
      { name: 'Equipamentos', desc: 'Patrimônio e comodatos', Icon: Package },
      { name: 'Suprimentos', desc: 'Requisições e almoxarifado', Icon: Package },
      { name: 'Documentos', desc: 'GED, arquivos, kits', Icon: FolderKanban },
    ],
  },
  {
    name: 'Administração',
    mods: [
      { name: 'Configurações', desc: 'Usuários, permissões', Icon: Settings },
      { name: 'Integrações', desc: 'APIs, webhooks', Icon: Link2 },
      { name: 'Automações', desc: 'Workflows', Icon: Workflow },
      { name: 'Agendador', desc: 'Tarefas agendadas', Icon: Clock },
      { name: 'Segurança', desc: 'LGPD e auditoria', Icon: Lock },
      { name: 'Assistente IA', desc: 'IA geral do sistema', Icon: Sparkles, org: true },
      { name: 'Área do Cliente', desc: 'Portal externo', Icon: Headset },
      { name: 'Meu Espaço', desc: 'Área pessoal', Icon: User },
    ],
  },
];

// Nome do tile → slug do módulo (todos resolvem para um módulo existente)
const SLUG: Record<string, string> = {
  'CRM': 'crm', 'Marketing': 'marketing', 'Licitações': 'licitacoes', 'Serviços': 'servicos',
  'Departamento Pessoal': 'departamento-pessoal', 'Recursos Humanos': 'rh', 'Gestão de Pessoas': 'gestao-de-pessoas',
  'Operacional': 'operacional', 'Saúde Ocupacional': 'saude-ocupacional', 'Ponto Eletrônico': 'gestao-de-pessoas',
  'Portal do Funcionário': 'portal-do-funcionario', 'Recrutamento': 'recrutamento',
  'Financeiro': 'financeiro', 'Fiscal & Contábil': 'fiscal', 'Jurídico': 'juridico', 'Empresas': 'empresas',
  'BI': 'bi', 'Analytics': 'analytics', 'Relatórios': 'relatorios', 'Equipamentos': 'equipamentos',
  'Suprimentos': 'suprimentos', 'Documentos': 'documentos',
  'Configurações': 'configuracoes', 'Integrações': 'integracoes', 'Automações': 'automacoes',
  'Agendador': 'agendador', 'Segurança': 'seguranca', 'Assistente IA': 'assistente',
  'Área do Cliente': 'area-do-cliente', 'Meu Espaço': 'meu-espaco',
};

function Tile({ m }: { m: Mod }): ReactNode {
  const { Icon } = m;
  const slug = SLUG[m.name];
  return (
    <a className="rd-mod" href={slug ? `/redesign/${slug}` : undefined}>
      <div className={`rd-mod-ico ${m.org ? 'org' : 'navy'}`}>
        <Icon size={23} strokeWidth={2} />
      </div>
      <div className="nm">{m.name}</div>
      <div className="ds">{m.desc}</div>
    </a>
  );
}

export default function RedesignLauncher() {
  const [q, setQ] = useState('');
  const [kpis, setKpis] = useState<Kpi[] | null>(null);
  const [alerts, setAlerts] = useState<Alert[] | null>(null);
  const ql = q.trim().toLowerCase();
  const groups = ql
    ? GROUPS.map((g) => ({ ...g, mods: g.mods.filter((m) => m.name.toLowerCase().includes(ql) || m.desc.toLowerCase().includes(ql)) })).filter((g) => g.mods.length)
    : GROUPS;

  // KPIs e Pendências REAIS (GET /redesign/home). Sem dado → mantém skeleton/vazio honesto.
  useEffect(() => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
    if (!token) return;
    fetch('/api/v1/redesign/home', { headers: { Authorization: `Bearer ${token}` } })
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => {
        if (!d) return;
        if (Array.isArray(d.kpis)) setKpis(d.kpis);
        if (Array.isArray(d.alerts)) setAlerts(d.alerts);
      })
      .catch(() => {});
  }, []);

  const now = new Date();
  const hora = now.getHours();
  const saud = hora < 12 ? 'Bom dia' : hora < 18 ? 'Boa tarde' : 'Boa noite';
  const dataFmt = now.toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });

  return (
    <div className="rd-launch">
      {/* Topbar navy */}
      <header className="rd-launch-top">
        <div className="rd-launch-brand">
          <img src="/images/quadrante.png" alt="Conecta" />
          <span className="w">CONECTA</span>
          <span className="b">PRO</span>
        </div>
        <div className="rd-launch-search">
          <Search size={15} color="rgba(255,255,255,0.6)" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Buscar módulos…" />
        </div>
        <div className="rd-launch-actions">
          <div className="rd-launch-bell"><Bell size={19} /><span className="dot">3</span></div>
          <div className="rd-launch-user">
            <div className="av"><img src="/images/foto-jordan.jpg" alt="Jordan Jesus" /></div>
            <div>
              <div className="n">Jordan Jesus</div>
              <div className="r">admin</div>
            </div>
          </div>
          <a href="/modulos" title="Ir para o sistema clássico (para operações)"
            style={{ display: 'flex', alignItems: 'center', gap: 6, textDecoration: 'none', color: '#fff',
              background: 'rgba(255,255,255,0.1)', border: '1px solid rgba(255,255,255,0.16)', borderRadius: 10,
              padding: '8px 12px', fontSize: 12.5, fontWeight: 600, whiteSpace: 'nowrap' }}>
            <LayoutGrid size={16} /> Clássico
          </a>
          <button type="button" title="Sair" onClick={rdLogout} className="rd-launch-bell" style={{ background: 'transparent', border: 'none' }}><LogOut size={18} /></button>
        </div>
      </header>

      {/* Conteúdo */}
      <div className="rd-launch-body">
        <div className="rd-launch-inner">
          <div className="rd-launch-hi">
            <h1>{saud}, Jordan</h1>
            <p>{dataFmt.charAt(0).toUpperCase() + dataFmt.slice(1)} · selecione um módulo para começar</p>
          </div>

          {/* KPIs + Pendências (dados reais de /redesign/home) */}
          <div className="rd-launch-row">
            <div className="rd-kpi-row">
              {(kpis ?? [null, null, null, null]).map((k, i) => {
                const Icon = KPI_ICONS[i] ?? Users;
                return (
                  <div className="rd-kpi-h" key={k ? k.l : i}>
                    <div className="box"><Icon size={21} strokeWidth={2} /></div>
                    <div>
                      <div className="v">{k ? k.v : '—'}</div>
                      <div className="l">{k ? k.l : 'Carregando…'}</div>
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="rd-pend">
              <div className="rd-pend-h">
                <span className="t">Pendências</span>
                <span className="c">{alerts ? alerts.length : 0}</span>
              </div>
              {alerts === null ? (
                <div className="rd-pend-row"><div className="main"><div className="mt">Carregando…</div></div></div>
              ) : alerts.length === 0 ? (
                <div className="rd-pend-row"><div className="main"><div className="tt">Sem pendências</div><div className="mt">Nenhuma certidão vencida ou vencendo</div></div></div>
              ) : alerts.map((a) => (
                <div className="rd-pend-row" key={a.title}>
                  <span className="dot" style={{ background: a.dot }} />
                  <div className="main">
                    <div className="tt">{a.title}</div>
                    <div className="mt">{a.meta}</div>
                  </div>
                  <span className="ac">{a.action}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Grupos de módulos */}
          {groups.map((g) => (
            <div className="rd-group" key={g.name}>
              <div className="rd-group-h">
                <span className="bar" />
                <span className="lbl">{g.name}</span>
              </div>
              <div className="rd-mod-grid">
                {g.mods.map((m) => <Tile m={m} key={m.name} />)}
              </div>
            </div>
          ))}

          <div className="rd-launch-foot">
            <span>Conecta PRO v2.0</span>
            <span>By Conecta Mais® · erp.conectamais.pro</span>
          </div>
        </div>
      </div>
    </div>
  );
}
