import { Module, ModuleCategory } from '@/types/modules';

// Definicao de todos os modulos do sistema — 9 modulos organizados
// Reorganizacao visual (frontend only) — backend continua com modulos originais
// Sessao 23: Gestao de Pessoas com 5 cards separados (DP, RH, GED, Operacoes, Portal)
export const modules: Module[] = [
  // =================================================================
  // 1a. CRM — Gestao de relacionamento com clientes
  // =================================================================
  {
    id: 'crm',
    title: 'CRM',
    description: 'Leads, oportunidades, propostas e contratos',
    icon: 'Handshake',
    href: '/modulos/crm',
    color: 'cyan',
    permissions: ['module:crm'],
    enabled: true,
    subModules: [
      { id: 'cmo-ia', title: 'Consultor Comercial IA', href: '/modulos/crm/consultor', icon: 'Bot', permissions: ['module:crm'] },
      { id: 'crm-dashboard', title: 'Dashboard', href: '/modulos/crm', icon: 'LayoutDashboard', permissions: ['module:crm'] },
      { id: 'clientes', title: 'Clientes', href: '/modulos/crm/clientes', icon: 'Building2', permissions: ['module:crm'] },
      { id: 'leads', title: 'Leads', href: '/modulos/crm/leads', icon: 'UserPlus', permissions: ['module:crm'] },
      { id: 'oportunidades', title: 'Oportunidades', href: '/modulos/crm/oportunidades', icon: 'Target', permissions: ['module:crm'] },
      { id: 'propostas', title: 'Propostas', href: '/modulos/crm/propostas', icon: 'FileText', permissions: ['module:crm'] },
      { id: 'contratos', title: 'Contratos', href: '/modulos/crm/contratos', icon: 'FileSignature', permissions: ['module:crm'] },
      { id: 'contatos', title: 'Contatos', href: '/modulos/crm/contatos', icon: 'Contact', permissions: ['module:crm'] },
      { id: 'crm-atividades', title: 'Atividades & Tarefas', href: '/modulos/crm/atividades', icon: 'Activity', permissions: ['module:crm'] },
      { id: 'comissoes', title: 'Comissões', href: '/modulos/crm/comissoes', icon: 'Coins', permissions: ['module:crm'] },
      { id: 'crm-precificacao', title: 'Precificação', href: '/modulos/crm/precificacao', icon: 'Tag', permissions: ['module:crm'] },
      { id: 'crm-growth', title: 'Growth (Automação)', href: '/modulos/crm/growth', icon: 'Zap', permissions: ['module:crm'] },
    ],
  },

  // =================================================================
  // 1b. MARKETING DIGITAL
  // =================================================================

  // =================================================================
  // 1c. LICITAÇÕES
  // =================================================================

  // =================================================================
  // 2. DEPARTAMENTO PESSOAL (DP) — Card separado dentro de Gestao de Pessoas
  // =================================================================
  {
    id: 'dp',
    title: 'Departamento Pessoal',
    description: 'Folha, admissões, demissões, férias e benefícios',
    icon: 'Users',
    href: '/modulos/dp',
    color: 'orange',
    permissions: ['module:dp'],
    enabled: true,
    subModules: [
      { id: 'dp-consultor-ia', title: 'Consultor de Pessoas IA', href: '/modulos/gestao-pessoas/consultor', icon: 'Bot', permissions: ['module:dp'] },
      { id: 'dp-colaboradores', title: 'Colaboradores', href: '/modulos/dp/funcionarios', icon: 'UserCheck', permissions: ['module:dp'] },
      { id: 'dp-admissao', title: 'Admissão', href: '/modulos/dp/admissao', icon: 'UserPlus', permissions: ['module:dp'] },
      { id: 'dp-rescisao', title: 'Rescisão', href: '/modulos/dp/rescisao', icon: 'UserMinus', permissions: ['module:dp'] },
      { id: 'dp-contratos', title: 'Contratos', href: '/modulos/dp/contratos', icon: 'FileSignature', permissions: ['module:dp'] },
      { id: 'dp-folha', title: 'Folha Salarial', href: '/modulos/dp/folha', icon: 'DollarSign', permissions: ['module:dp'] },
      { id: 'dp-ponto', title: 'Ponto Eletrônico', href: '/modulos/dp/ponto', icon: 'Clock', permissions: ['module:dp'] },
      { id: 'dp-fechamento-ponto', title: 'Fechamento de Ponto', href: '/modulos/dp/fechamento-ponto', icon: 'Lock', permissions: ['module:dp'] },
      { id: 'dp-ferias', title: 'Férias', href: '/modulos/dp/ferias', icon: 'Plane', permissions: ['module:dp'] },
      { id: 'dp-beneficios', title: 'Benefícios', href: '/modulos/dp/beneficios', icon: 'Gift', permissions: ['module:dp'] },
      { id: 'dp-licencas', title: 'Licenças', href: '/modulos/dp/licencas', icon: 'FileText', permissions: ['module:dp'] },
      { id: 'dp-reembolsos', title: 'Reembolsos', href: '/modulos/dp/reembolsos', icon: 'Receipt', permissions: ['module:dp'] },
      { id: 'dp-esocial', title: 'eSocial', href: '/modulos/dp/esocial', icon: 'Database', permissions: ['module:dp'] },
      { id: 'dp-documentos', title: 'Documentos DP', href: '/modulos/dp/documentos', icon: 'FolderOpen', permissions: ['module:dp'] },
      { id: 'dp-prestadores-pj', title: 'Prestadores PJ', href: '/modulos/dp/prestadores-pj', icon: 'Link2', permissions: ['module:dp'] },
      { id: 'dp-ativacao-ponto', title: 'Ativação do Ponto', href: '/modulos/dp/ativacao-ponto', icon: 'Fingerprint', permissions: ['module:dp'] },
      { id: 'dp-monitor-ponto', title: 'Monitor do Ponto (ao vivo)', href: '/modulos/dp/monitor-ponto', icon: 'Activity', permissions: ['module:dp'] },
    ],
  },

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
  {
    id: 'ged',
    title: 'GED — Documentos & Kits',
    description: 'Central de gestão de documentos e montagem dos kits mensais por condomínio',
    icon: 'FolderOpen',
    href: '/modulos/gestao-pessoas/ged',
    color: 'green',
    permissions: ['module:ged'],
    enabled: true,
    subModules: [
      // Fluxo enxuto, focado na montagem dos kits + gestão documental
      { id: 'ged-dashboard', title: 'Kits por Condomínio', href: '/modulos/gestao-pessoas/ged', icon: 'LayoutDashboard', permissions: ['module:ged'] },
      { id: 'ged-montar', title: 'Montar / Cronograma', href: '/modulos/gestao-pessoas/ged/montar-kit', icon: 'Wand2', permissions: ['module:ged'] },
      { id: 'ged-consultor', title: 'Consultor GED IA', href: '/modulos/gestao-pessoas/ged/consultor', icon: 'Bot', permissions: ['module:ged'] },
      { id: 'ged-certidoes', title: 'Certidões (CND)', href: '/modulos/gestao-pessoas/ged/certidoes', icon: 'Award', permissions: ['module:ged'] },
      { id: 'ged-documentos', title: 'Documentos', href: '/modulos/gestao-pessoas/ged/documentos', icon: 'FileText', permissions: ['module:ged'] },
      { id: 'ged-envios', title: 'Envios ao Cliente', href: '/modulos/gestao-pessoas/ged/envios', icon: 'Send', permissions: ['module:ged'] },
      { id: 'ged-configuracoes', title: 'Configurações', href: '/modulos/gestao-pessoas/ged/configuracoes', icon: 'Settings', permissions: ['role:admin'] },
    ],
  },

  // =================================================================
  // 5. OPERACOES — Card separado dentro de Gestao de Pessoas
  // =================================================================
  {
    id: 'operacoes',
    title: 'Operacional',
    description: 'Postos, escalas, campo e inteligencia operacional',
    icon: 'Shield',
    href: '/modulos/operacional',
    color: 'cyan',
    permissions: ['module:operacional'],
    enabled: true,
    subModules: [
      { id: 'coo-ia', title: 'Consultor Operacional IA', href: '/modulos/operacional/consultor', icon: 'Bot', permissions: ['module:operacional'] },
      // --- Postos e Escalas ---
      { id: 'postos', title: 'Postos', href: '/modulos/operacional/postos', icon: 'MapPin', permissions: ['module:operacional'] },
      { id: 'escalas', title: 'Escalas', href: '/modulos/operacional/escalas', icon: 'CalendarDays', permissions: ['module:operacional'] },
      { id: 'grade-pessoa', title: 'Grade por pessoa', href: '/modulos/operacional/escalas/grade', icon: 'CalendarCog', permissions: ['module:operacional'] },
      { id: 'alocacoes', title: 'Alocacoes', href: '/modulos/operacional/alocacoes', icon: 'Users', permissions: ['module:operacional'] },
      { id: 'turnos', title: 'Turnos', href: '/modulos/operacional/turnos', icon: 'Clock', permissions: ['module:operacional'] },
      { id: 'substituicoes', title: 'Substituicoes', href: '/modulos/operacional/substituicoes', icon: 'RefreshCw', permissions: ['module:operacional'] },
      { id: 'diaristas', title: 'Diaristas', href: '/modulos/operacional/diaristas', icon: 'UserCheck', permissions: ['module:operacional'] },
      { id: 'diarias', title: 'Lancamento de Diarias', href: '/modulos/operacional/diarias', icon: 'CalendarPlus', permissions: ['module:operacional'] },
      { id: 'banco-horas', title: 'Banco de Horas', href: '/modulos/operacional/banco-horas', icon: 'Clock', permissions: ['module:operacional'] },
      // --- Dia a dia do lider (mobile-first) ---
      { id: 'presenca-hoje', title: 'Presenca Hoje', href: '/modulos/operacional/presenca', icon: 'UserCheck', permissions: ['module:operacional'] },
      { id: 'instrucoes-posto', title: 'Instrucoes do Posto', href: '/modulos/operacional/instrucoes-posto', icon: 'FileText', permissions: ['module:operacional'] },
      { id: 'ocorrencia-rapida', title: 'Ocorrencia Rapida', href: '/modulos/operacional/ocorrencia-rapida', icon: 'Zap', permissions: ['module:operacional'] },
      { id: 'ronda-mobile', title: 'Ronda (mobile)', href: '/modulos/operacional/ronda-mobile', icon: 'MapPin', permissions: ['module:operacional'] },
      { id: 'passagem-turno', title: 'Passagem de Turno', href: '/modulos/operacional/passagem-turno', icon: 'RefreshCw', permissions: ['module:operacional'] },
      { id: 'avaliacao-equipe', title: 'Avaliacao de Equipe', href: '/modulos/operacional/avaliacao-equipe', icon: 'Users', permissions: ['module:operacional'] },
      { id: 'triagem', title: 'Triagem (Gestao)', href: '/modulos/operacional/triagem', icon: 'Activity', permissions: ['module:operacional'] },
      // --- Ocorrencias e Disciplinar ---
      { id: 'ocorrencias', title: 'Ocorrencias', href: '/modulos/operacional/ocorrencias', icon: 'AlertTriangle', permissions: ['module:operacional'] },
      { id: 'medidas-administrativas', title: 'Medidas Administrativas', href: '/modulos/operacional/medidas-administrativas', icon: 'AlertTriangle', permissions: ['module:operacional'] },
      // --- Campo e Rondas ---
      { id: 'ordens-servico-campo', title: 'Ordens de Servico', href: '/modulos/campo/ordens-servico', icon: 'ClipboardList', permissions: ['module:operacional'] },
      { id: 'rondas', title: 'Rondas', href: '/modulos/operacional/rondas', icon: 'Route', permissions: ['module:operacional'] },
      { id: 'checkin', title: 'Check-in/out', href: '/modulos/campo/checkin', icon: 'LogIn', permissions: ['module:operacional'] },
      { id: 'monitoramento', title: 'Monitoramento Campo', href: '/modulos/campo/monitoramento', icon: 'Monitor', permissions: ['module:operacional'] },
      { id: 'comunicados-campo', title: 'Comunicados Campo', href: '/modulos/campo/comunicados', icon: 'Megaphone', permissions: ['module:operacional'] },
      // --- Tempo Real ---
      { id: 'cobertura', title: 'Cobertura ao Vivo', href: '/modulos/operacional/cobertura', icon: 'Activity', permissions: ['module:operacional'] },
      { id: 'kpi', title: 'KPI & Tendencias', href: '/modulos/operacional/kpi', icon: 'TrendingUp', permissions: ['module:operacional'] },
      // --- Comunicacao ---
      { id: 'comunicados', title: 'Comunicados', href: '/modulos/operacional/comunicados', icon: 'Bell', permissions: ['module:operacional'] },
      { id: 'notificacoes', title: 'Notificacoes', href: '/modulos/operacional/notificacoes', icon: 'Bell', permissions: ['module:operacional'] },
      // --- IA Operacional ---
      { id: 'ai-command-center', title: 'Central IA', href: '/modulos/operacional/ai-command-center', icon: 'Zap', permissions: ['module:operacional'] },
      { id: 'agentes-ia', title: 'Colaboradores (Operacional)', href: '/modulos/operacional/colaboradores', icon: 'Bot', permissions: ['module:operacional'] },
    ],
  },

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
      { id: 'ac-gerenciamento', title: 'Gerenciamento de Acessos', href: '/modulos/area-cliente/gerenciamento', icon: 'Key', permissions: ['role:admin'] },
    ],
  },

  // =================================================================
  // 10. FINANCEIRO (antigo: Financial + Suprimentos + boletos)
  // =================================================================
  {
    id: 'financeiro',
    title: 'Financeiro',
    description: 'Contas, fluxo de caixa, compras e estoque',
    icon: 'DollarSign',
    href: '/modulos/financeiro',
    color: 'green',
    permissions: ['module:financeiro'],
    enabled: true,
    subModules: [
      { id: 'dashboard-financeiro', title: 'Dashboard Financeiro', href: '/modulos/financeiro/dashboard', icon: 'LayoutDashboard', permissions: ['module:financeiro'] },
      { id: 'contratos', title: 'Contratos', href: '/modulos/financeiro/contratos', icon: 'FileText', permissions: ['module:financeiro'] },
      { id: 'contas-pagar', title: 'Contas a Pagar', href: '/modulos/financeiro/contas-pagar', icon: 'TrendingDown', permissions: ['module:financeiro'] },
      { id: 'contas-receber', title: 'Contas a Receber', href: '/modulos/financeiro/contas-receber', icon: 'TrendingUp', permissions: ['module:financeiro'] },
      { id: 'fluxo-caixa', title: 'Fluxo de Caixa', href: '/modulos/financeiro/fluxo-caixa', icon: 'Activity', permissions: ['module:financeiro'] },
      { id: 'conciliacao', title: 'Conciliacao Bancaria', href: '/modulos/financeiro/conciliacao', icon: 'CheckCircle2', permissions: ['module:financeiro'] },
      { id: 'boletos', title: 'Boletos', href: '/modulos/financeiro/boletos', icon: 'CreditCard', permissions: ['module:financeiro'] },
      { id: 'cobrancas', title: 'Cobrancas', href: '/modulos/financeiro/cobrancas', icon: 'DollarSign', permissions: ['module:financeiro'] },
      // --- Banco Inter ---
      { id: 'inter-painel', title: 'Banco Inter', href: '/modulos/financeiro/inter', icon: 'Building2', permissions: ['module:financeiro'] },
      { id: 'inter-pagamentos', title: 'Pagamentos & Transferências', href: '/modulos/financeiro/inter/pagamentos', icon: 'Send', permissions: ['module:financeiro'] },
      { id: 'pagamentos-diaristas', title: 'Pagamentos de Diaristas (VT+VR)', href: '/modulos/financeiro/pagamentos-diaristas', icon: 'Coins', permissions: ['module:financeiro'] },
      { id: 'pagamentos-pj', title: 'Folha de Pagamento PJ', href: '/modulos/financeiro/pagamentos-pj', icon: 'Briefcase', permissions: ['module:financeiro'] },
      { id: 'fornecedores', title: 'Fornecedores', href: '/modulos/financeiro/fornecedores', icon: 'Truck', permissions: ['module:financeiro'] },
      // --- Suprimentos ---
      { id: 'notas-recebidas', title: 'Notas Recebidas', href: '/modulos/financeiro/nfse-entrada', icon: 'Receipt', permissions: ['module:financeiro'] },
      { id: 'compras', title: 'Compras', href: '/modulos/financeiro/compras', icon: 'ShoppingCart', permissions: ['module:financeiro'] },
      { id: 'estoque', title: 'Estoque', href: '/modulos/financeiro/estoque', icon: 'Package', permissions: ['module:financeiro'] },
      // --- Custos e Precificacao ---
      { id: 'custos', title: 'Custos', href: '/modulos/financeiro/custos', icon: 'PieChart', permissions: ['module:financeiro'] },
      { id: 'custeio', title: 'Custeio ABC', href: '/modulos/financeiro/custeio', icon: 'Calculator', permissions: ['module:financeiro'] },
      // --- Contabilidade e Relatorios ---
      { id: 'contabilidade', title: 'Contabilidade', href: '/modulos/financeiro/contabilidade', icon: 'Calculator', permissions: ['module:financeiro'] },
    ],
  },

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
  {
    id: 'config',
    title: 'Configuracoes',
    description: 'Usuarios, permissoes e sistema',
    icon: 'Settings',
    href: '/modulos/configuracoes',
    color: 'red',
    permissions: ['role:admin'],
    enabled: true,
    subModules: [
      { id: 'dashboard-config', title: 'Dashboard', href: '/modulos/configuracoes', icon: 'LayoutDashboard', permissions: ['role:admin'] },
      { id: 'tenants', title: 'Tenants', href: '/modulos/configuracoes/tenants', icon: 'Building2', permissions: ['role:admin'] },
      { id: 'usuarios-permissoes', title: 'Usuários & Permissões', href: '/modulos/configuracoes/usuarios', icon: 'Shield', permissions: ['role:admin'] },
    ],
  },
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
