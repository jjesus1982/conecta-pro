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
  {
    id: 'marketing',
    title: 'Marketing',
    description: 'Funil, campanhas e geração de leads',
    icon: 'Megaphone',
    href: '/modulos/marketing/funil',
    color: 'purple',
    permissions: ['module:crm'],
    enabled: true,
    subModules: [
      { id: 'mkt-funil', title: 'Funil', href: '/modulos/marketing/funil', icon: 'Filter', permissions: ['module:crm'] },
      { id: 'mkt-estrategista', title: 'Estrategista IA', href: '/modulos/marketing/estrategista', icon: 'Target', permissions: ['module:crm'] },
      { id: 'mkt-campanhas', title: 'Campanhas', href: '/modulos/marketing/campanhas', icon: 'Megaphone', permissions: ['module:crm'] },
      { id: 'mkt-lead-magnet', title: 'Lead Magnet', href: '/modulos/marketing/lead-magnet', icon: 'Magnet', permissions: ['module:crm'] },
      { id: 'mkt-brand-voice', title: 'Brand Voice', href: '/modulos/marketing/brand-voice', icon: 'Volume2', permissions: ['module:crm'] },
      { id: 'mkt-copywriter', title: 'Copywriter IA', href: '/modulos/marketing/copywriter', icon: 'PenLine', permissions: ['module:crm'] },
      { id: 'mkt-biblioteca', title: 'Biblioteca', href: '/modulos/marketing/biblioteca', icon: 'Library', permissions: ['module:crm'] },
    ],
  },

  // =================================================================
  // 1c. LICITAÇÕES
  // =================================================================
  {
    id: 'licitacoes',
    title: 'Licitações',
    description: 'Editais, propostas e disputas',
    icon: 'Scale',
    href: '/modulos/licitacoes',
    color: 'orange',
    permissions: ['module:crm'],
    enabled: true,
    subModules: [
      { id: 'licitacoes-dashboard', title: 'Dashboard', href: '/modulos/licitacoes', icon: 'LayoutDashboard', permissions: ['module:crm'] },
      { id: 'editais', title: 'Editais', href: '/modulos/licitacoes/editais', icon: 'FileSearch', permissions: ['module:crm'] },
      { id: 'propostas-licitacao', title: 'Propostas', href: '/modulos/licitacoes/propostas', icon: 'FileCheck', permissions: ['module:crm'] },
      { id: 'documentos-licitacao', title: 'Documentos', href: '/modulos/licitacoes/documentos', icon: 'FolderOpen', permissions: ['module:crm'] },
      { id: 'resultados-licitacao', title: 'Resultados', href: '/modulos/licitacoes/resultados', icon: 'Trophy', permissions: ['module:crm'] },
      { id: 'disputas-licitacao', title: 'Disputas', href: '/modulos/licitacoes/disputas', icon: 'Swords', permissions: ['module:crm'] },
      { id: 'ia-licitacoes', title: 'IA Hub', href: '/modulos/licitacoes/ia', icon: 'Bot', permissions: ['module:crm'] },
    ],
  },

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
      { id: 'dp-ferias', title: 'Férias', href: '/modulos/dp/ferias', icon: 'Plane', permissions: ['module:dp'] },
      { id: 'dp-beneficios', title: 'Benefícios', href: '/modulos/dp/beneficios', icon: 'Gift', permissions: ['module:dp'] },
      { id: 'dp-licencas', title: 'Licenças', href: '/modulos/dp/licencas', icon: 'FileText', permissions: ['module:dp'] },
      { id: 'dp-reembolsos', title: 'Reembolsos', href: '/modulos/dp/reembolsos', icon: 'Receipt', permissions: ['module:dp'] },
      { id: 'dp-esocial', title: 'eSocial', href: '/modulos/dp/esocial', icon: 'Database', permissions: ['module:dp'] },
      { id: 'dp-documentos', title: 'Documentos DP', href: '/modulos/dp/documentos', icon: 'FolderOpen', permissions: ['module:dp'] },
    ],
  },

  // =================================================================
  // 3. RECURSOS HUMANOS (RH) — Card separado dentro de Gestao de Pessoas
  // =================================================================
  {
    id: 'rh',
    title: 'Recursos Humanos',
    description: 'Recrutamento, treinamentos, avaliacoes e desenvolvimento',
    icon: 'Users',
    href: '/modulos/rh',
    color: 'purple',
    permissions: ['module:dp'],
    enabled: true,
    subModules: [
      { id: 'chro-ia', title: 'Consultor de Pessoas IA', href: '/modulos/gestao-pessoas/consultor', icon: 'Bot', permissions: ['module:dp'] },
      { id: 'rh-vagas', title: 'Vagas', href: '/modulos/recrutamento/vagas', icon: 'Briefcase', permissions: ['module:dp'], group: 'Recrutamento' },
      { id: 'rh-candidatos', title: 'Candidatos', href: '/modulos/recrutamento/candidatos', icon: 'Users', permissions: ['module:dp'], group: 'Recrutamento' },
      { id: 'rh-candidaturas', title: 'Candidaturas', href: '/modulos/recrutamento/candidaturas', icon: 'FileText', permissions: ['module:dp'], group: 'Recrutamento' },
      { id: 'rh-entrevistas', title: 'Entrevistas', href: '/modulos/recrutamento/entrevistas', icon: 'Calendar', permissions: ['module:dp'], group: 'Recrutamento' },
      { id: 'rh-cursos', title: 'Cursos', href: '/modulos/rh/cursos', icon: 'BookOpen', permissions: ['module:dp'], group: 'Desenvolvimento' },
      { id: 'rh-treinamentos', title: 'Treinamentos', href: '/modulos/rh/treinamentos', icon: 'GraduationCap', permissions: ['module:dp'], group: 'Desenvolvimento' },
      { id: 'rh-certificados', title: 'Certificados', href: '/modulos/rh/certificados', icon: 'Award', permissions: ['module:dp'], group: 'Desenvolvimento' },
      { id: 'rh-avaliacoes', title: 'Avaliacoes 360', href: '/modulos/rh/avaliacoes', icon: 'Star', permissions: ['module:dp'], group: 'Avaliacao' },
      { id: 'rh-carreira', title: 'Plano de Carreira', href: '/modulos/rh/carreira', icon: 'TrendingUp', permissions: ['module:dp'], group: 'Avaliacao' },
      { id: 'rh-clima', title: 'Clima Organizacional', href: '/modulos/rh/clima', icon: 'Heart', permissions: ['module:dp'], group: 'Avaliacao' },
      { id: 'rh-turnover', title: 'Previsao Turnover', href: '/modulos/rh/turnover', icon: 'TrendingDown', permissions: ['module:dp'], group: 'Avaliacao' },
      { id: 'rh-onboarding', title: 'Onboarding', href: '/modulos/rh/onboarding', icon: 'UserPlus', permissions: ['module:dp'] },
      { id: 'rh-dashboard', title: 'Dashboard RH', href: '/modulos/rh/dashboard', icon: 'LayoutDashboard', permissions: ['module:dp'] },
      { id: 'rh-ia', title: 'IA de Pessoas', href: '/modulos/rh/ia', icon: 'Bot', permissions: ['module:dp'] },
    ],
  },

  // =================================================================
  // 3b. RH — GESTÃO DE PESSOAS (novo módulo em /gestao-pessoas/rh)
  // =================================================================
  {
    id: 'rh-gp',
    title: 'Recursos Humanos',
    description: 'CCT, cargos, beneficios, treinamentos e relatorios',
    icon: 'Users',
    href: '/modulos/gestao-pessoas/rh',
    color: 'blue',
    permissions: ['module:dp'],
    enabled: true,
    subModules: [
      { id: 'rh-gp-dashboard', title: 'Dashboard RH', href: '/modulos/gestao-pessoas/rh', icon: 'LayoutDashboard', permissions: ['module:dp'] },
      { id: 'rh-gp-cct', title: 'CCT', href: '/modulos/gestao-pessoas/rh/cct', icon: 'FileText', permissions: ['module:dp'] },
      { id: 'rh-gp-cargos', title: 'Cargos', href: '/modulos/gestao-pessoas/rh/cargos', icon: 'Briefcase', permissions: ['module:dp'] },
      { id: 'rh-gp-beneficios', title: 'Beneficios', href: '/modulos/gestao-pessoas/rh/beneficios', icon: 'Package', permissions: ['module:dp'] },
      { id: 'rh-gp-treinamentos', title: 'Treinamentos', href: '/modulos/gestao-pessoas/rh/treinamentos', icon: 'GraduationCap', permissions: ['module:dp'] },
      { id: 'rh-gp-desempenho', title: 'Desempenho', href: '/modulos/gestao-pessoas/rh/desempenho', icon: 'ClipboardCheck', permissions: ['module:dp'] },
      { id: 'rh-gp-clima', title: 'Clima', href: '/modulos/gestao-pessoas/rh/clima', icon: 'Activity', permissions: ['module:dp'] },
      { id: 'rh-gp-relatorios', title: 'Relatorios', href: '/modulos/gestao-pessoas/rh/relatorios', icon: 'BarChart3', permissions: ['module:dp'] },
    ],
  },

  // =================================================================
  // 3c. GESTAO DE PESSOAS — Hub pai (portal /modulos/gestao-pessoas)
  // =================================================================
  {
    id: 'gestao-pessoas',
    title: 'Gestao de Pessoas',
    description: 'Hub de DP, RH, GED, Operacional, SST, Ponto e Portal',
    icon: 'Users',
    href: '/modulos/gestao-pessoas',
    color: 'blue',
    permissions: ['module:dp', 'module:operacional', 'module:sst', 'module:ged'],
    enabled: true,
    subModules: [
      { id: 'gp-dp', title: 'Departamento Pessoal', href: '/modulos/dp', icon: 'Users', permissions: ['module:dp'] },
      { id: 'gp-rh', title: 'Recursos Humanos', href: '/modulos/gestao-pessoas/rh', icon: 'Heart', permissions: ['module:dp'] },
      { id: 'gp-ged', title: 'GED - Kits Documentais', href: '/modulos/gestao-pessoas/ged', icon: 'FolderOpen', permissions: ['module:ged'] },
      { id: 'gp-operacoes', title: 'Operacional', href: '/modulos/operacional', icon: 'Shield', permissions: ['module:operacional'] },
      { id: 'gp-sst', title: 'Saude e Seguranca', href: '/modulos/gestao-pessoas/sst', icon: 'ShieldCheck', permissions: ['module:sst'] },
      { id: 'gp-ponto', title: 'Ponto Eletronico', href: '/modulos/gestao-pessoas/ponto', icon: 'Clock', permissions: ['module:dp'] },
      { id: 'gp-portal', title: 'Portal do Funcionario', href: '/modulos/portal', icon: 'UserCircle', permissions: ['module:dp'] },
    ],
  },

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
  {
    id: 'sst',
    title: 'Saude Ocupacional',
    description: 'PCMSO, PPRA/PGR, EPIs, Afastamentos, CAT e CCT 2026',
    icon: 'HeartPulse',
    href: '/modulos/gestao-pessoas/saude-ocupacional',
    color: 'red',
    permissions: ['module:sst'],
    enabled: true,
    subModules: [
      { id: 'sst-consultor-ia', title: 'Consultor de Pessoas IA', href: '/modulos/gestao-pessoas/consultor', icon: 'Bot', permissions: ['module:sst'] },
      { id: 'sst-dashboard', title: 'Dashboard SST', href: '/modulos/gestao-pessoas/saude-ocupacional', icon: 'LayoutDashboard', permissions: ['module:sst'] },
      { id: 'sst-regularizacao', title: 'Regularização', href: '/modulos/gestao-pessoas/saude-ocupacional/regularizacao', icon: 'ShieldAlert', permissions: ['module:sst'] },
      { id: 'sst-prontuario', title: 'Prontuário SST', href: '/modulos/gestao-pessoas/saude-ocupacional/prontuario', icon: 'BookUser', permissions: ['module:sst'] },
      { id: 'sst-calendario-legal', title: 'Calendário Legal', href: '/modulos/gestao-pessoas/saude-ocupacional/calendario-legal', icon: 'CalendarClock', permissions: ['module:sst'] },
      { id: 'sst-exames', title: 'Exames / ASOs', href: '/modulos/gestao-pessoas/saude-ocupacional/exames', icon: 'Stethoscope', permissions: ['module:sst'] },
      { id: 'sst-treinamentos', title: 'Treinamentos NR', href: '/modulos/gestao-pessoas/saude-ocupacional/treinamentos', icon: 'GraduationCap', permissions: ['module:sst'] },
      { id: 'sst-epis', title: 'EPIs (NR-6)', href: '/modulos/gestao-pessoas/saude-ocupacional/epi', icon: 'HardHat', permissions: ['module:sst'] },
      { id: 'sst-riscos', title: 'Riscos (PPRA/PGR)', href: '/modulos/gestao-pessoas/saude-ocupacional/riscos', icon: 'AlertTriangle', permissions: ['module:sst'] },
      { id: 'sst-afastamentos', title: 'Afastamentos', href: '/modulos/gestao-pessoas/saude-ocupacional/afastamentos', icon: 'UserMinus', permissions: ['module:sst'] },
      { id: 'sst-cat', title: 'CAT', href: '/modulos/gestao-pessoas/saude-ocupacional/cat', icon: 'FileWarning', permissions: ['module:sst'] },
      { id: 'sst-transmissao-esocial', title: 'Transmissão eSocial', href: '/modulos/gestao-pessoas/saude-ocupacional/transmissao', icon: 'Send', permissions: ['module:sst'] },
    ],
  },

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
      { id: 'ponto-espelho', title: 'Espelho de Ponto', href: '/modulos/gestao-pessoas/ponto/espelho', icon: 'FileText', permissions: ['module:dp'] },
      { id: 'ponto-justificativas', title: 'Justificativas', href: '/modulos/gestao-pessoas/ponto/justificativas', icon: 'MessageSquare', permissions: ['module:dp'] },
      { id: 'ponto-atrasos', title: 'Atrasos e Faltas', href: '/modulos/gestao-pessoas/ponto/atrasos', icon: 'AlertTriangle', permissions: ['module:dp'] },
      { id: 'ponto-banco-horas', title: 'Banco de Horas', href: '/modulos/gestao-pessoas/ponto/banco-horas', icon: 'Clock', permissions: ['module:dp'] },
      { id: 'ponto-fechamento', title: 'Fechamento Mensal', href: '/modulos/gestao-pessoas/ponto/fechamento', icon: 'CheckCircle', permissions: ['module:dp'] },
    ],
  },

  // =================================================================
  // 8. PORTAL DO FUNCIONARIO — Card separado dentro de Gestao de Pessoas
  // =================================================================
  {
    id: 'portal-funcionario',
    title: 'Portal do Funcionario',
    description: 'Acesso do funcionario a contracheques e documentos',
    icon: 'Users',
    href: '/modulos/portal',
    color: 'blue',
    permissions: ['module:dp'],
    enabled: true,
    subModules: [
      { id: 'portal-contracheque', title: 'Contracheques', href: '/modulos/portal/contracheque', icon: 'FileText', permissions: ['module:dp'] },
      { id: 'portal-ferias', title: 'Ferias', href: '/modulos/portal/ferias', icon: 'Palmtree', permissions: ['module:dp'] },
      { id: 'portal-documentos', title: 'Documentos', href: '/modulos/portal/documentos', icon: 'FolderOpen', permissions: ['module:dp'] },
      { id: 'portal-treinamentos', title: 'Treinamentos', href: '/modulos/portal/treinamentos', icon: 'GraduationCap', permissions: ['module:dp'] },
      { id: 'portal-assinatura', title: 'Assinatura Digital', href: '/modulos/portal/assinatura', icon: 'PenTool', permissions: ['module:dp'] },
      { id: 'portal-notificacoes', title: 'Notificacoes', href: '/modulos/portal/notificacoes', icon: 'Bell', permissions: ['module:dp'] },
      { id: 'portal-dados', title: 'Meus Dados', href: '/modulos/portal/dados-pessoais', icon: 'User', permissions: ['module:dp'] },
    ],
  },

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
      { id: 'cfo-ia', title: 'CFO IA', href: '/modulos/financeiro/cfo', icon: 'Bot', permissions: ['module:financeiro'] },
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
      { id: 'fornecedores', title: 'Fornecedores', href: '/modulos/financeiro/fornecedores', icon: 'Truck', permissions: ['module:financeiro'] },
      // --- Suprimentos ---
      { id: 'compras', title: 'Compras', href: '/modulos/financeiro/compras', icon: 'ShoppingCart', permissions: ['module:financeiro'] },
      { id: 'estoque', title: 'Estoque', href: '/modulos/financeiro/estoque', icon: 'Package', permissions: ['module:financeiro'] },
      // --- Custos e Precificacao ---
      { id: 'custos', title: 'Custos', href: '/modulos/financeiro/custos', icon: 'PieChart', permissions: ['module:financeiro'] },
      { id: 'custeio', title: 'Custeio ABC', href: '/modulos/financeiro/custeio', icon: 'Calculator', permissions: ['module:financeiro'] },
      { id: 'orcamentos', title: 'Orcamentos', href: '/modulos/financeiro/orcamentos', icon: 'Target', permissions: ['module:financeiro'] },
      // --- Contabilidade e Relatorios ---
      { id: 'contabilidade', title: 'Contabilidade', href: '/modulos/financeiro/contabilidade', icon: 'Calculator', permissions: ['module:financeiro'] },
      { id: 'faturamento', title: 'Faturamento', href: '/modulos/financeiro/faturamento', icon: 'Receipt', permissions: ['module:financeiro'] },
      { id: 'relatorios-fin', title: 'Relatorios', href: '/modulos/financeiro/relatorios', icon: 'BarChart2', permissions: ['module:financeiro'] },
    ],
  },

  // =================================================================
  // 8. FISCAL & CONTABIL (antigos: Fiscal + Empresas)
  // =================================================================
  {
    id: 'fiscal',
    title: 'Fiscal & Contabil',
    description: 'NFS-e, impostos, SPED, multi-empresa e demonstrativos',
    icon: 'Landmark',
    href: '/modulos/fiscal',
    color: 'orange',
    permissions: ['module:fiscal'],
    enabled: true,
    subModules: [
      { id: 'fiscal-ia', title: 'Consultor Fiscal IA', href: '/modulos/fiscal/consultor', icon: 'Bot', permissions: ['module:fiscal'] },
      // --- Notas Fiscais ---
      { id: 'nfe', title: 'NF-e', href: '/modulos/financeiro/fiscal', icon: 'Receipt', permissions: ['module:fiscal'], group: 'Notas Fiscais' },
      { id: 'nfse', title: 'NFS-e', href: '/modulos/fiscal/nfse', icon: 'FileText', permissions: ['module:fiscal'], group: 'Notas Fiscais' },
      { id: 'nfse-multi', title: 'NFS-e Multi-Empresa', href: '/modulos/fiscal/nfse-multi', icon: 'FileText', permissions: ['module:fiscal'], group: 'Notas Fiscais' },
      // --- Certidoes (CNDs) ---
      { id: 'certidoes', title: 'Painel de Certidoes', href: '/modulos/fiscal/certidoes', icon: 'Award', permissions: ['module:fiscal'], group: 'Certidoes' },
      { id: 'cnd-federal', title: 'CND Federal', href: '/modulos/fiscal/certidoes/federal', icon: 'Landmark', permissions: ['module:fiscal'], group: 'Certidoes' },
      { id: 'cnd-estadual', title: 'CND Estadual', href: '/modulos/fiscal/certidoes/estadual', icon: 'Map', permissions: ['module:fiscal'], group: 'Certidoes' },
      { id: 'cnd-municipal', title: 'CND Municipal', href: '/modulos/fiscal/certidoes/municipal', icon: 'Building', permissions: ['module:fiscal'], group: 'Certidoes' },
      { id: 'crf-fgts', title: 'CRF/FGTS', href: '/modulos/fiscal/certidoes/fgts', icon: 'ShieldCheck', permissions: ['module:fiscal'], group: 'Certidoes' },
      { id: 'cndt', title: 'CNDT (Trabalhista)', href: '/modulos/fiscal/certidoes/trabalhista', icon: 'Users', permissions: ['module:fiscal'], group: 'Certidoes' },
      // --- Obrigacoes ---
      { id: 'esocial', title: 'eSocial', href: '/modulos/fiscal/esocial', icon: 'Users', permissions: ['module:fiscal'], group: 'Obrigacoes' },
      { id: 'sped', title: 'SPED', href: '/modulos/fiscal/sped', icon: 'Database', permissions: ['module:fiscal'], group: 'Obrigacoes' },
      { id: 'dctfweb', title: 'DCTFWeb', href: '/modulos/fiscal/dctfweb', icon: 'FileSpreadsheet', permissions: ['module:fiscal'], group: 'Obrigacoes' },
      { id: 'reinf', title: 'EFD-Reinf', href: '/modulos/fiscal/reinf', icon: 'FileCode', permissions: ['module:fiscal'], group: 'Obrigacoes' },
      // --- Multi-Empresa ---
      { id: 'empresas-gestao', title: 'Gestao Empresas', href: '/modulos/empresas', icon: 'Building2', permissions: ['module:fiscal'], group: 'Multi-Empresa' },
      { id: 'liminares', title: 'Liminares', href: '/modulos/empresas/liminares', icon: 'Scale', permissions: ['module:fiscal'], group: 'Multi-Empresa' },
      { id: 'rentabilidade', title: 'Rentabilidade', href: '/modulos/empresas/rentabilidade', icon: 'TrendingUp', permissions: ['module:fiscal'], group: 'Multi-Empresa' },
      { id: 'dashboard-empresas', title: 'Dashboard Multi-CNPJ', href: '/modulos/empresas/dashboard', icon: 'LayoutDashboard', permissions: ['module:fiscal'], group: 'Multi-Empresa' },
      { id: 'demonstrativos', title: 'Demonstrativos', href: '/modulos/empresas/demonstrativos', icon: 'BarChart2', permissions: ['module:fiscal'], group: 'Multi-Empresa' },
      { id: 'obrigacoes-empresa', title: 'Obrigacoes', href: '/modulos/empresas/obrigacoes', icon: 'CalendarDays', permissions: ['module:fiscal'], group: 'Multi-Empresa' },
      { id: 'migrador', title: 'Migrador Contratos', href: '/modulos/empresas/migrador', icon: 'ArrowRightLeft', permissions: ['module:fiscal'], group: 'Multi-Empresa' },
    ],
  },

  // =================================================================
  // JURIDICO (Central de Contratos + Compliance + LGPD)
  // =================================================================
  {
    id: 'juridico',
    title: 'Juridico',
    description: 'Escritorio Juridico IA: contratos, consultor, pareceres, riscos e compliance',
    icon: 'Scale',
    href: '/modulos/juridico',
    color: 'blue',
    permissions: ['module:juridico'],
    enabled: true,
    subModules: [
      { id: 'juridico-hub', title: 'Visao Geral', href: '/modulos/juridico', icon: 'LayoutDashboard', permissions: ['module:juridico'], group: 'Escritorio' },
      { id: 'juridico-processos', title: 'Processos & Defesa', href: '/modulos/juridico/processos', icon: 'Gavel', permissions: ['module:juridico'], group: 'Escritorio' },
      { id: 'juridico-det', title: 'Monitoramento DET', href: '/modulos/juridico/det', icon: 'Landmark', permissions: ['module:juridico'], group: 'Escritorio' },
      { id: 'juridico-consultor', title: 'Consultor Juridico IA', href: '/modulos/juridico/consultor', icon: 'Bot', permissions: ['module:juridico'], group: 'Escritorio' },
      { id: 'juridico-pareceres', title: 'Pareceres (IA)', href: '/modulos/juridico/pareceres', icon: 'FileSignature', permissions: ['module:juridico'], group: 'Escritorio' },
      { id: 'juridico-riscos', title: 'Riscos (Trabalhista/Tributario)', href: '/modulos/juridico/riscos', icon: 'AlertTriangle', permissions: ['module:juridico'], group: 'Escritorio' },
      { id: 'juridico-escritorio', title: 'Escritorio & ROI', href: '/modulos/juridico/escritorio', icon: 'Building2', permissions: ['module:juridico'], group: 'Escritorio' },
      { id: 'juridico-conhecimento', title: 'Base de Conhecimento', href: '/modulos/juridico/conhecimento', icon: 'BookOpen', permissions: ['module:juridico'], group: 'Escritorio' },
      { id: 'juridico-contratos', title: 'Central de Contratos', href: '/modulos/juridico/contratos', icon: 'FileText', permissions: ['module:juridico'], group: 'Contratos' },
      { id: 'juridico-analise', title: 'Analise de Contratos (IA)', href: '/modulos/juridico/analise', icon: 'Search', permissions: ['module:juridico'], group: 'Contratos' },
      { id: 'juridico-certidoes', title: 'Certidoes (CND/FGTS)', href: '/modulos/fiscal/certidoes', icon: 'Award', permissions: ['module:juridico'], group: 'Compliance' },
    ],
  },

  // =================================================================
  // 9. INTELIGENCIA (Relatorios + Analytics)
  // =================================================================
  {
    id: 'inteligencia',
    title: 'Inteligencia',
    description: 'Dashboards, KPIs, relatorios e analytics',
    icon: 'BarChart3',
    href: '/modulos/relatorios',
    color: 'blue',
    permissions: ['role:admin'],
    enabled: true,
    subModules: [
      { id: 'dashboards', title: 'Dashboards', href: '/modulos/relatorios/dashboards', icon: 'LayoutDashboard', permissions: ['role:admin'] },
      { id: 'rel-operacional', title: 'Operacional', href: '/modulos/relatorios/operacional', icon: 'ClipboardCheck', permissions: ['role:admin'] },
      { id: 'rel-financeiro', title: 'Financeiro', href: '/modulos/relatorios/financeiro', icon: 'PieChart', permissions: ['role:admin'] },
      { id: 'rel-comercial', title: 'Comercial', href: '/modulos/relatorios/comercial', icon: 'TrendingUp', permissions: ['role:admin'] },
      { id: 'analytics', title: 'Analytics', href: '/modulos/analytics', icon: 'Activity', permissions: ['role:admin'] },
      { id: 'rel-operacional-detalhado', title: 'Relatorios Operacionais', href: '/modulos/operacional/relatorios', icon: 'FileText', permissions: ['role:admin'] },
    ],
  },

  // =================================================================
  // 10. EQUIPAMENTOS & PATRIMONIO
  // =================================================================
  {
    id: 'patrimonio',
    title: 'Equipamentos & Patrimonio',
    description: 'Equipamentos, comodatos e manutencoes',
    icon: 'Package',
    href: '/modulos/equipamentos',
    color: 'yellow',
    permissions: ['module:operacional'],
    enabled: true,
    subModules: [
      { id: 'patrimonio-equip', title: 'Patrimonio', href: '/modulos/equipamentos/patrimonio', icon: 'Package', permissions: ['module:operacional'] },
      { id: 'comodatos', title: 'Comodatos', href: '/modulos/equipamentos/comodatos', icon: 'Repeat', permissions: ['module:operacional'] },
      { id: 'manutencoes', title: 'Manutencoes', href: '/modulos/equipamentos/manutencoes', icon: 'Wrench', permissions: ['module:operacional'] },
      // --- GED Generico (arquivos e pastas) ---
      { id: 'arquivos', title: 'Arquivos', href: '/modulos/documentos/arquivos', icon: 'File', permissions: ['module:operacional'], group: 'Documentos Gerais' },
      { id: 'pastas', title: 'Pastas', href: '/modulos/documentos/pastas', icon: 'Folder', permissions: ['module:operacional'], group: 'Documentos Gerais' },
    ],
  },

  // =================================================================
  // 11. ADMINISTRATIVO (Integracoes + Seguranca + Agendador + Automacoes)
  // =================================================================
  {
    id: 'administrativo',
    title: 'Administrativo',
    description: 'Integracoes, seguranca, LGPD, automacoes e agendador',
    icon: 'Settings',
    href: '/modulos/integracoes',
    color: 'red',
    permissions: ['role:admin'],
    enabled: true,
    subModules: [
      // --- Integracoes ---
      { id: 'conectores', title: 'Conectores', href: '/modulos/integracoes/conectores', icon: 'Plug', permissions: ['role:admin'] },
      { id: 'api-keys', title: 'API Keys', href: '/modulos/integracoes/api-keys', icon: 'Key', permissions: ['role:admin'] },
      { id: 'webhooks', title: 'Webhooks', href: '/modulos/integracoes/webhooks', icon: 'Webhook', permissions: ['role:admin'] },
      { id: 'logs-integracao', title: 'Logs', href: '/modulos/integracoes/logs', icon: 'FileText', permissions: ['role:admin'] },
      { id: 'sync', title: 'Sincronizacao', href: '/modulos/integracoes/sync', icon: 'RefreshCw', permissions: ['role:admin'] },
      { id: 'solides', title: 'Solides', href: '/modulos/integracoes/solides', icon: 'Zap', permissions: ['role:admin'] },
      // --- Seguranca & LGPD ---
      { id: 'auditoria', title: 'Auditoria', href: '/modulos/seguranca/auditoria', icon: 'Eye', permissions: ['role:admin'] },
      { id: 'consentimento', title: 'Consentimento', href: '/modulos/seguranca/consentimento', icon: 'CheckCircle2', permissions: ['role:admin'] },
      { id: 'pia-dpia', title: 'PIA/DPIA', href: '/modulos/seguranca/pia-dpia', icon: 'FileText', permissions: ['role:admin'] },
      { id: 'esquecimento', title: 'Esquecimento', href: '/modulos/seguranca/esquecimento', icon: 'Trash2', permissions: ['role:admin'] },
      { id: 'mascaramento', title: 'Mascaramento', href: '/modulos/seguranca/mascaramento', icon: 'Eye', permissions: ['role:admin'] },
      { id: 'criptografia', title: 'Criptografia', href: '/modulos/seguranca/criptografia', icon: 'Lock', permissions: ['role:admin'] },
      // --- Agendador ---
      { id: 'tarefas-agendador', title: 'Tarefas Agendadas', href: '/modulos/agendador/tarefas', icon: 'Clock', permissions: ['role:admin'] },
      { id: 'execucoes-agendador', title: 'Execucoes', href: '/modulos/agendador/execucoes', icon: 'Play', permissions: ['role:admin'] },
      // --- Automacoes ---
      { id: 'workflows', title: 'Workflows', href: '/modulos/automacoes/workflows', icon: 'GitBranch', permissions: ['role:admin'] },
      { id: 'execucoes-workflow', title: 'Execucoes Workflow', href: '/modulos/automacoes/execucoes', icon: 'Play', permissions: ['role:admin'] },
    ],
  },

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
      { id: 'ceo-ia', title: 'Consultor Executivo IA', href: '/modulos/configuracoes/consultor', icon: 'Bot', permissions: ['role:admin'] },
      { id: 'dashboard-config', title: 'Dashboard', href: '/modulos/configuracoes', icon: 'LayoutDashboard', permissions: ['role:admin'] },
      { id: 'tenants', title: 'Tenants', href: '/modulos/configuracoes/tenants', icon: 'Building2', permissions: ['role:admin'] },
      { id: 'feature-flags', title: 'Feature Flags', href: '/modulos/configuracoes/feature-flags', icon: 'ToggleRight', permissions: ['role:admin'] },
      { id: 'sistema', title: 'Sistema', href: '/modulos/configuracoes/configuracoes-sistema', icon: 'Settings', permissions: ['role:admin'] },
      { id: 'templates', title: 'Templates', href: '/modulos/configuracoes/templates-notificacao', icon: 'Mail', permissions: ['role:admin'] },
      { id: 'integracoes-config', title: 'Integrações', href: '/modulos/configuracoes/integracoes', icon: 'Plug', permissions: ['role:admin'] },
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
