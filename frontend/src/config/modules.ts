import { Module, ModuleCategory } from '@/types/modules';

// Definicao de todos os modulos do sistema — 9 modulos organizados
// Reorganizacao visual (frontend only) — backend continua com modulos originais
// Sessao 23: Gestao de Pessoas com 5 cards separados (DP, RH, GED, Operacoes, Portal)
export const modules: Module[] = [
  // =================================================================
  // 1a. CRM — Gestao de relacionamento com clientes
  // =================================================================

  // =================================================================
  // 1b. MARKETING DIGITAL
  // =================================================================

  // =================================================================
  // 1c. LICITAÇÕES
  // =================================================================

  // =================================================================
  // 2. DEPARTAMENTO PESSOAL (DP) — Card separado dentro de Gestao de Pessoas
  // =================================================================

  // =================================================================
  // 3. RECURSOS HUMANOS (RH) — Card separado dentro de Gestao de Pessoas
  // =================================================================

  // =================================================================
  // 3b. RH — GESTÃO DE PESSOAS (novo módulo em /gestao-pessoas/rh)
  // =================================================================

  // =================================================================
  // 3c. GESTAO DE PESSOAS — Hub pai (portal /modulos/gestao-pessoas)
  // =================================================================

  // =================================================================
  // 4. GED - KITS DOCUMENTAIS — Card separado dentro de Gestao de Pessoas
  // =================================================================

  // =================================================================
  // 5. OPERACOES — Card separado dentro de Gestao de Pessoas
  // =================================================================

  // =================================================================
  // 6. SAUDE E SEGURANCA DO TRABALHO (SST) — Card separado dentro de Gestao de Pessoas
  // =================================================================

  // =================================================================
  // 7. PONTO ELETRONICO — Card separado dentro de Gestao de Pessoas
  // =================================================================
  {
    id: 'ponto',
    title: 'Ponto Eletronico',
    description: 'Batida facial, geolocalizacao, offline e justificativas',
    icon: 'Clock',
    href: '/modulos/gestao-pessoas/ponto',
    color: 'blue',
    permissions: ['module:dp'],
    enabled: true,
    subModules: [
      { id: 'ponto-dashboard', title: 'Dashboard Ponto', href: '/modulos/gestao-pessoas/ponto', icon: 'LayoutDashboard', permissions: ['module:dp'] },
      { id: 'ponto-batida', title: 'Bater Ponto', href: '/modulos/gestao-pessoas/ponto/batida', icon: 'Fingerprint', permissions: ['module:dp'] },
    ],
  },

  // =================================================================
  // 8. PORTAL DO FUNCIONARIO — Card separado dentro de Gestao de Pessoas
  // =================================================================

  // =================================================================
  // 9. AREA DO CLIENTE — Portal externo para clientes/condominios
  // =================================================================
  {
    id: 'area-cliente',
    title: 'Area do Cliente',
    description: 'Portal externo: kits documentais, chamados e downloads',
    icon: 'Building2',
    href: '/area-cliente',
    color: 'amber',
    permissions: ['module:ged'],
    enabled: true,
    external: true,
    subModules: [
      { id: 'ac-dashboard', title: 'Dashboard', href: '/area-cliente', icon: 'LayoutDashboard', permissions: ['module:ged'] },
      { id: 'ac-kits', title: 'Kits Documentais', href: '/area-cliente/kits', icon: 'Package', permissions: ['module:ged'] },
      { id: 'ac-chamados', title: 'Chamados', href: '/area-cliente/chamados', icon: 'MessageSquare', permissions: ['module:ged'] },
      { id: 'ac-configuracoes', title: 'Configuracoes', href: '/area-cliente/configuracoes', icon: 'Settings', permissions: ['role:admin'] },
    ],
  },

  // =================================================================
  // 10. FINANCEIRO (antigo: Financial + Suprimentos + boletos)
  // =================================================================

  // =================================================================
  // 8. FISCAL & CONTABIL (antigos: Fiscal + Empresas)
  // =================================================================

  // =================================================================
  // JURIDICO (Central de Contratos + Compliance + LGPD)
  // =================================================================

  // =================================================================
  // 9. INTELIGENCIA (Relatorios + Analytics)
  // =================================================================

  // =================================================================
  // 10. EQUIPAMENTOS & PATRIMONIO
  // =================================================================

  // =================================================================
  // 11. ADMINISTRATIVO (Integracoes + Seguranca + Agendador + Automacoes)
  // =================================================================

  // =================================================================
  // 12. CONFIGURACOES
  // =================================================================
];

// Agrupar modulos por categoria — 5 categorias
// Operacoes agora dentro de Gestao de Pessoas (nao mais em Negocios)
export const moduleCategories: ModuleCategory[] = [
  {
    id: 'negocios',
    title: 'Negócios',
    modules: modules.filter(m => ['crm', 'marketing', 'licitacoes'].includes(m.id)),
  },
  {
    id: 'pessoas',
    title: 'Gestão de Pessoas',
    modules: modules.filter(m => ['dp', 'rh', 'ged', 'operacoes', 'sst', 'ponto', 'portal-funcionario', 'area-cliente'].includes(m.id)),
  },
  {
    id: 'financeiro',
    title: 'Financeiro, Fiscal & Jurídico',
    modules: modules.filter(m => ['financeiro', 'fiscal', 'juridico'].includes(m.id)),
  },
  {
    id: 'inteligencia',
    title: 'Inteligência & Patrimônio',
    modules: modules.filter(m => ['inteligencia', 'patrimonio'].includes(m.id)),
  },
  {
    id: 'administracao',
    title: 'Administração',
    modules: modules.filter(m => ['administrativo', 'config'].includes(m.id)),
  },
];

// Buscar modulo por ID
export function getModuleById(id: string): Module | undefined {
  return modules.find(m => m.id === id);
}

// Buscar modulo por path — match mais especifico primeiro
export function getModuleByPath(path: string): Module | undefined {
  // 1. Tentar match direto pelo href do modulo
  let best: Module | undefined;
  let bestLen = 0;

  for (const m of modules) {
    if (path.startsWith(m.href) && m.href.length > bestLen) {
      best = m;
      bestLen = m.href.length;
    }
  }

  if (best) return best;

  // 2. Fallback: buscar pelo href dos submodules
  for (const m of modules) {
    for (const sub of m.subModules) {
      if (path === sub.href || path.startsWith(sub.href + '/')) {
        return m;
      }
    }
  }

  // 3. Fallback cross-módulo: o path é PAI de um submodule conhecido.
  //    Ex.: '/modulos/campo' não é href de nenhum módulo, mas
  //    '/modulos/campo/checkin' pertence a Operacoes → devolve Operacoes.
  //    (sem isso o layout ficava em spinner infinito nessas rotas)
  if (path !== '/modulos') {
    for (const m of modules) {
      for (const sub of m.subModules) {
        if (sub.href.startsWith(path + '/')) {
          return m;
        }
      }
    }
  }

  return undefined;
}
