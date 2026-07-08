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
    permissions: ['crm:read'],
    enabled: true,
    subModules: [
      { id: 'cmo-ia', title: 'Consultor Comercial IA', href: '/modulos/crm/consultor', icon: 'Bot', permissions: ['crm:read'] },
      { id: 'crm-dashboard', title: 'Dashboard', href: '/modulos/crm', icon: 'LayoutDashboard', permissions: ['crm:read'] },
      { id: 'clientes', title: 'Clientes', href: '/modulos/crm/clientes', icon: 'Building2', permissions: ['crm:clientes'] },
      { id: 'leads', title: 'Leads', href: '/modulos/crm/leads', icon: 'UserPlus', permissions: ['crm:leads'] },
      { id: 'oportunidades', title: 'Oportunidades', href: '/modulos/crm/oportunidades', icon: 'Target', permissions: ['crm:oportunidades'] },
      { id: 'propostas', title: 'Propostas', href: '/modulos/crm/propostas', icon: 'FileText', permissions: ['crm:propostas'] },
      { id: 'contratos', title: 'Contratos', href: '/modulos/crm/contratos', icon: 'FileSignature', permissions: ['crm:read'] },
      { id: 'contatos', title: 'Contatos', href: '/modulos/crm/contatos', icon: 'Contact', permissions: ['crm:contatos'] },
      { id: 'crm-atividades', title: 'Atividades & Tarefas', href: '/modulos/crm/atividades', icon: 'Activity', permissions: ['crm:read'] },
      { id: 'comissoes', title: 'Comissões', href: '/modulos/crm/comissoes', icon: 'Coins', permissions: ['crm:read'] },
      { id: 'crm-precificacao', title: 'Precificação', href: '/modulos/crm/precificacao', icon: 'Tag', permissions: ['crm:read'] },
      { id: 'crm-growth', title: 'Growth (Automação)', href: '/modulos/crm/growth', icon: 'Zap', permissions: ['crm:read'] },
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
    permissions: ['crm:read'],
    enabled: true,
    subModules: [
      { id: 'mkt-funil', title: 'Funil', href: '/modulos/marketing/funil', icon: 'Filter', permissions: ['crm:read'] },
      { id: 'mkt-estrategista', title: 'Estrategista IA', href: '/modulos/marketing/estrategista', icon: 'Target', permissions: ['crm:read'] },
      { id: 'mkt-campanhas', title: 'Campanhas', href: '/modulos/marketing/campanhas', icon: 'Megaphone', permissions: ['crm:read'] },
      { id: 'mkt-lead-magnet', title: 'Lead Magnet', href: '/modulos/marketing/lead-magnet', icon: 'Magnet', permissions: ['crm:read'] },
      { id: 'mkt-brand-voice', title: 'Brand Voice', href: '/modulos/marketing/brand-voice', icon: 'Volume2', permissions: ['crm:read'] },
      { id: 'mkt-copywriter', title: 'Copywriter IA', href: '/modulos/marketing/copywriter', icon: 'PenLine', permissions: ['crm:read'] },
      { id: 'mkt-biblioteca', title: 'Biblioteca', href: '/modulos/marketing/biblioteca', icon: 'Library', permissions: ['crm:read'] },
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
    permissions: ['bidding:tenders:read'],
    enabled: true,
    subModules: [
      { id: 'licitacoes-dashboard', title: 'Dashboard', href: '/modulos/licitacoes', icon: 'LayoutDashboard', permissions: ['bidding:tenders:read'] },
      { id: 'editais', title: 'Editais', href: '/modulos/licitacoes/editais', icon: 'FileSearch', permissions: ['bidding:tenders:read'] },
      { id: 'propostas-licitacao', title: 'Propostas', href: '/modulos/licitacoes/propostas', icon: 'FileCheck', permissions: ['bidding:proposals:read'] },
      { id: 'documentos-licitacao', title: 'Documentos', href: '/modulos/licitacoes/documentos', icon: 'FolderOpen', permissions: ['bidding:documents:read'] },
      { id: 'resultados-licitacao', title: 'Resultados', href: '/modulos/licitacoes/resultados', icon: 'Trophy', permissions: ['bidding:tenders:read'] },
      { id: 'disputas-licitacao', title: 'Disputas', href: '/modulos/licitacoes/disputas', icon: 'Swords', permissions: ['bidding:tenders:read'] },
      { id: 'ia-licitacoes', title: 'IA Hub', href: '/modulos/licitacoes/ia', icon: 'Bot', permissions: ['bidding:tenders:read'] },
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
    permissions: ['operacional:read'],
    enabled: true,
    subModules: [
      { id: 'dp-consultor-ia', title: 'Consultor de Pessoas IA', href: '/modulos/gestao-pessoas/consultor', icon: 'Bot', permissions: ['operacional:read'] },
      { id: 'dp-colaboradores', title: 'Colaboradores', href: '/modulos/dp/funcionarios', icon: 'UserCheck', permissions: ['operacional:read'] },
      { id: 'dp-admissao', title: 'Admissão', href: '/modulos/dp/admissao', icon: 'UserPlus', permissions: ['operacional:read'] },
      { id: 'dp-rescisao', title: 'Rescisão', href: '/modulos/dp/rescisao', icon: 'UserMinus', permissions: ['operacional:read'] },
      { id: 'dp-contratos', title: 'Contratos', href: '/modulos/dp/contratos', icon: 'FileSignature', permissions: ['operacional:read'] },
      { id: 'dp-folha', title: 'Folha Salarial', href: '/modulos/dp/folha', icon: 'DollarSign', permissions: ['operacional:read'] },
      { id: 'dp-ponto', title: 'Ponto Eletrônico', href: '/modulos/dp/ponto', icon: 'Clock', permissions: ['operacional:read'] },
      { id: 'dp-ferias', title: 'Férias', href: '/modulos/dp/ferias', icon: 'Plane', permissions: ['operacional:read'] },
      { id: 'dp-beneficios', title: 'Benefícios', href: '/modulos/dp/beneficios', icon: 'Gift', permissions: ['operacional:read'] },
      { id: 'dp-licencas', title: 'Licenças', href: '/modulos/dp/licencas', icon: 'FileText', permissions: ['operacional:read'] },
      { id: 'dp-reembolsos', title: 'Reembolsos', href: '/modulos/dp/reembolsos', icon: 'Receipt', permissions: ['operacional:read'] },
      { id: 'dp-esocial', title: 'eSocial', href: '/modulos/dp/esocial', icon: 'Database', permissions: ['operacional:read'] },
      { id: 'dp-documentos', title: 'Documentos DP', href: '/modulos/dp/documentos', icon: 'FolderOpen', permissions: ['operacional:read'] },
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
    permissions: ['operacional:read'],
    enabled: true,
    subModules: [
      { id: 'chro-ia', title: 'Consultor de Pessoas IA', href: '/modulos/gestao-pessoas/consultor', icon: 'Bot', permissions: ['operacional:read'] },
      { id: 'rh-vagas', title: 'Vagas', href: '/modulos/recrutamento/vagas', icon: 'Briefcase', permissions: ['operacional:read'], group: 'Recrutamento' },
      { id: 'rh-candidatos', title: 'Candidatos', href: '/modulos/recrutamento/candidatos', icon: 'Users', permissions: ['operacional:read'], group: 'Recrutamento' },
      { id: 'rh-candidaturas', title: 'Candidaturas', href: '/modulos/recrutamento/candidaturas', icon: 'FileText', permissions: ['operacional:read'], group: 'Recrutamento' },
      { id: 'rh-entrevistas', title: 'Entrevistas', href: '/modulos/recrutamento/entrevistas', icon: 'Calendar', permissions: ['operacional:read'], group: 'Recrutamento' },
      { id: 'rh-cursos', title: 'Cursos', href: '/modulos/rh/cursos', icon: 'BookOpen', permissions: ['operacional:read'], group: 'Desenvolvimento' },
      { id: 'rh-treinamentos', title: 'Treinamentos', href: '/modulos/rh/treinamentos', icon: 'GraduationCap', permissions: ['operacional:read'], group: 'Desenvolvimento' },
      { id: 'rh-certificados', title: 'Certificados', href: '/modulos/rh/certificados', icon: 'Award', permissions: ['operacional:read'], group: 'Desenvolvimento' },
      { id: 'rh-avaliacoes', title: 'Avaliacoes 360', href: '/modulos/rh/avaliacoes', icon: 'Star', permissions: ['operacional:read'], group: 'Avaliacao' },
      { id: 'rh-carreira', title: 'Plano de Carreira', href: '/modulos/rh/carreira', icon: 'TrendingUp', permissions: ['operacional:read'], group: 'Avaliacao' },
      { id: 'rh-clima', title: 'Clima Organizacional', href: '/modulos/rh/clima', icon: 'Heart', permissions: ['operacional:read'], group: 'Avaliacao' },
      { id: 'rh-turnover', title: 'Previsao Turnover', href: '/modulos/rh/turnover', icon: 'TrendingDown', permissions: ['operacional:read'], group: 'Avaliacao' },
      { id: 'rh-onboarding', title: 'Onboarding', href: '/modulos/rh/onboarding', icon: 'UserPlus', permissions: ['operacional:read'] },
      { id: 'rh-dashboard', title: 'Dashboard RH', href: '/modulos/rh/dashboard', icon: 'LayoutDashboard', permissions: ['operacional:read'] },
      { id: 'rh-ia', title: 'IA de Pessoas', href: '/modulos/rh/ia', icon: 'Bot', permissions: ['operacional:read'] },
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
    permissions: ['operacional:read'],
    enabled: true,
    subModules: [
      { id: 'rh-gp-dashboard', title: 'Dashboard RH', href: '/modulos/gestao-pessoas/rh', icon: 'LayoutDashboard', permissions: ['operacional:read'] },
      { id: 'rh-gp-cct', title: 'CCT', href: '/modulos/gestao-pessoas/rh/cct', icon: 'FileText', permissions: ['operacional:read'] },
      { id: 'rh-gp-cargos', title: 'Cargos', href: '/modulos/gestao-pessoas/rh/cargos', icon: 'Briefcase', permissions: ['operacional:read'] },
      { id: 'rh-gp-beneficios', title: 'Beneficios', href: '/modulos/gestao-pessoas/rh/beneficios', icon: 'Package', permissions: ['operacional:read'] },
      { id: 'rh-gp-treinamentos', title: 'Treinamentos', href: '/modulos/gestao-pessoas/rh/treinamentos', icon: 'GraduationCap', permissions: ['operacional:read'] },
      { id: 'rh-gp-desempenho', title: 'Desempenho', href: '/modulos/gestao-pessoas/rh/desempenho', icon: 'ClipboardCheck', permissions: ['operacional:read'] },
      { id: 'rh-gp-clima', title: 'Clima', href: '/modulos/gestao-pessoas/rh/clima', icon: 'Activity', permissions: ['operacional:read'] },
      { id: 'rh-gp-relatorios', title: 'Relatorios', href: '/modulos/gestao-pessoas/rh/relatorios', icon: 'BarChart3', permissions: ['operacional:read'] },
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
    permissions: ['operacional:read'],
    enabled: true,
    subModules: [
      { id: 'gp-dp', title: 'Departamento Pessoal', href: '/modulos/dp', icon: 'Users', permissions: ['operacional:read'] },
      { id: 'gp-rh', title: 'Recursos Humanos', href: '/modulos/gestao-pessoas/rh', icon: 'Heart', permissions: ['operacional:read'] },
      { id: 'gp-ged', title: 'GED - Kits Documentais', href: '/modulos/gestao-pessoas/ged', icon: 'FolderOpen', permissions: ['ged:read'] },
      { id: 'gp-operacoes', title: 'Operacional', href: '/modulos/operacional', icon: 'Shield', permissions: ['operacional:read'] },
      { id: 'gp-sst', title: 'Saude e Seguranca', href: '/modulos/gestao-pessoas/sst', icon: 'ShieldCheck', permissions: ['operacional:read'] },
      { id: 'gp-ponto', title: 'Ponto Eletronico', href: '/modulos/gestao-pessoas/ponto', icon: 'Clock', permissions: ['operacional:read'] },
      { id: 'gp-portal', title: 'Portal do Funcionario', href: '/modulos/portal', icon: 'UserCircle', permissions: ['operacional:read'] },
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
    permissions: ['ged:read'],
    enabled: true,
    subModules: [
      // Fluxo enxuto, focado na montagem dos kits + gestão documental
      { id: 'ged-dashboard', title: 'Kits por Condomínio', href: '/modulos/gestao-pessoas/ged', icon: 'LayoutDashboard', permissions: ['ged:read'] },
      { id: 'ged-montar', title: 'Montar / Cronograma', href: '/modulos/gestao-pessoas/ged/montar-kit', icon: 'Wand2', permissions: ['ged:read'] },
      { id: 'ged-consultor', title: 'Consultor GED IA', href: '/modulos/gestao-pessoas/ged/consultor', icon: 'Bot', permissions: ['ged:read'] },
      { id: 'ged-certidoes', title: 'Certidões (CND)', href: '/modulos/gestao-pessoas/ged/certidoes', icon: 'Award', permissions: ['ged:read'] },
      { id: 'ged-documentos', title: 'Documentos', href: '/modulos/gestao-pessoas/ged/documentos', icon: 'FileText', permissions: ['ged:read'] },
      { id: 'ged-envios', title: 'Envios ao Cliente', href: '/modulos/gestao-pessoas/ged/envios', icon: 'Send', permissions: ['ged:read'] },
      { id: 'ged-configuracoes', title: 'Configurações', href: '/modulos/gestao-pessoas/ged/configuracoes', icon: 'Settings', permissions: ['ged:admin'] },
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
    permissions: ['operacional:read'],
    enabled: true,
    subModules: [
      { id: 'coo-ia', title: 'Consultor Operacional IA', href: '/modulos/operacional/consultor', icon: 'Bot', permissions: ['operacional:read'] },
      // --- Postos e Escalas ---
      { id: 'postos', title: 'Postos', href: '/modulos/operacional/postos', icon: 'MapPin', permissions: ['operacional:postos'] },
      { id: 'escalas', title: 'Escalas', href: '/modulos/operacional/escalas', icon: 'CalendarDays', permissions: ['operacional:escalas'] },
      { id: 'escalas-visual', title: 'Editor Visual', href: '/modulos/operacional/escalas/visual', icon: 'CalendarDays', permissions: ['operacional:escalas'] },
      { id: 'alocacoes', title: 'Alocacoes', href: '/modulos/operacional/alocacoes', icon: 'Users', permissions: ['operacional:alocacoes'] },
      { id: 'turnos', title: 'Turnos', href: '/modulos/operacional/turnos', icon: 'Clock', permissions: ['operacional:turnos'] },
      { id: 'substituicoes', title: 'Substituicoes', href: '/modulos/operacional/substituicoes', icon: 'RefreshCw', permissions: ['operacional:read'] },
      { id: 'diaristas', title: 'Diaristas', href: '/modulos/operacional/diaristas', icon: 'UserCheck', permissions: ['operacional:read'] },
      { id: 'banco-horas', title: 'Banco de Horas', href: '/modulos/operacional/banco-horas', icon: 'Clock', permissions: ['operacional:read'] },
      // --- Dia a dia do lider (mobile-first) ---
      { id: 'presenca-hoje', title: 'Presenca Hoje', href: '/modulos/operacional/presenca', icon: 'UserCheck', permissions: ['operacional:read'] },
      { id: 'ocorrencia-rapida', title: 'Ocorrencia Rapida', href: '/modulos/operacional/ocorrencia-rapida', icon: 'Zap', permissions: ['operacional:read'] },
      { id: 'passagem-turno', title: 'Passagem de Turno', href: '/modulos/operacional/passagem-turno', icon: 'RefreshCw', permissions: ['operacional:read'] },
      { id: 'avaliacao-equipe', title: 'Avaliacao de Equipe', href: '/modulos/operacional/avaliacao-equipe', icon: 'Users', permissions: ['operacional:read'] },
      { id: 'triagem', title: 'Triagem (Gestao)', href: '/modulos/operacional/triagem', icon: 'Activity', permissions: ['operacional:read'] },
      // --- Ocorrencias e Disciplinar ---
      { id: 'ocorrencias', title: 'Ocorrencias', href: '/modulos/operacional/ocorrencias', icon: 'AlertTriangle', permissions: ['operacional:ocorrencias'] },
      { id: 'disciplinar', title: 'Processos Disciplinares', href: '/modulos/operacional/disciplinar', icon: 'FileText', permissions: ['operacional:disciplinar'] },
      { id: 'medidas-administrativas', title: 'Medidas Administrativas', href: '/modulos/operacional/medidas-administrativas', icon: 'AlertTriangle', permissions: ['operacional:disciplinar'] },
      // --- Campo e Rondas ---
      { id: 'ordens-servico-campo', title: 'Ordens de Servico', href: '/modulos/campo/ordens-servico', icon: 'ClipboardList', permissions: ['campo:checkin'] },
      { id: 'rondas', title: 'Rondas', href: '/modulos/operacional/rondas', icon: 'Route', permissions: ['operacional:rondas'] },
      { id: 'checkin', title: 'Check-in/out', href: '/modulos/campo/checkin', icon: 'LogIn', permissions: ['campo:checkin'] },
      { id: 'monitoramento', title: 'Monitoramento Campo', href: '/modulos/campo/monitoramento', icon: 'Monitor', permissions: ['campo:monitoramento'] },
      { id: 'comunicados-campo', title: 'Comunicados Campo', href: '/modulos/campo/comunicados', icon: 'Megaphone', permissions: ['campo:comunicados'] },
      // --- Tempo Real ---
      { id: 'cobertura', title: 'Cobertura ao Vivo', href: '/modulos/operacional/cobertura', icon: 'Activity', permissions: ['operacional:postos'] },
      { id: 'mapa', title: 'Mapa ao Vivo', href: '/modulos/operacional/mapa', icon: 'MapPin', permissions: ['operacional:postos'] },
      { id: 'kpi', title: 'KPI & Tendencias', href: '/modulos/operacional/kpi', icon: 'TrendingUp', permissions: ['operacional:read'] },
      // --- Comunicacao ---
      { id: 'comunicados', title: 'Comunicados', href: '/modulos/operacional/comunicados', icon: 'Bell', permissions: ['operacional:comunicados'] },
      { id: 'notificacoes', title: 'Notificacoes', href: '/modulos/operacional/notificacoes', icon: 'Bell', permissions: ['operacional:notificacoes'] },
      // --- IA Operacional ---
      { id: 'ai-command-center', title: 'Central IA', href: '/modulos/operacional/ai-command-center', icon: 'Zap', permissions: ['operacional:read'] },
      { id: 'agentes-ia', title: 'Agentes IA', href: '/modulos/operacional/agentes', icon: 'Bot', permissions: ['operacional:read'] },
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
    permissions: ['operacional:read'],
    enabled: true,
    subModules: [
      { id: 'sst-consultor-ia', title: 'Consultor de Pessoas IA', href: '/modulos/gestao-pessoas/consultor', icon: 'Bot', permissions: ['operacional:read'] },
      { id: 'sst-dashboard', title: 'Dashboard SST', href: '/modulos/gestao-pessoas/saude-ocupacional', icon: 'LayoutDashboard', permissions: ['operacional:read'] },
      { id: 'sst-exames', title: 'Exames / ASOs', href: '/modulos/gestao-pessoas/saude-ocupacional/exames', icon: 'Stethoscope', permissions: ['operacional:read'] },
      { id: 'sst-treinamentos', title: 'Treinamentos NR', href: '/modulos/gestao-pessoas/saude-ocupacional/treinamentos', icon: 'GraduationCap', permissions: ['operacional:read'] },
      { id: 'sst-epis', title: 'EPIs (NR-6)', href: '/modulos/gestao-pessoas/saude-ocupacional/epi', icon: 'HardHat', permissions: ['operacional:read'] },
      { id: 'sst-riscos', title: 'Riscos (PPRA/PGR)', href: '/modulos/gestao-pessoas/saude-ocupacional/riscos', icon: 'AlertTriangle', permissions: ['operacional:read'] },
      { id: 'sst-afastamentos', title: 'Afastamentos', href: '/modulos/gestao-pessoas/saude-ocupacional/afastamentos', icon: 'UserMinus', permissions: ['operacional:read'] },
      { id: 'sst-cat', title: 'CAT', href: '/modulos/gestao-pessoas/saude-ocupacional/cat', icon: 'FileWarning', permissions: ['operacional:read'] },
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
    permissions: ['operacional:read'],
    enabled: true,
    subModules: [
      { id: 'ponto-dashboard', title: 'Dashboard Ponto', href: '/modulos/gestao-pessoas/ponto', icon: 'LayoutDashboard', permissions: ['operacional:read'] },
      { id: 'ponto-batida', title: 'Bater Ponto', href: '/modulos/gestao-pessoas/ponto/batida', icon: 'Fingerprint', permissions: ['operacional:read'] },
      { id: 'ponto-espelho', title: 'Espelho de Ponto', href: '/modulos/gestao-pessoas/ponto/espelho', icon: 'FileText', permissions: ['operacional:read'] },
      { id: 'ponto-justificativas', title: 'Justificativas', href: '/modulos/gestao-pessoas/ponto/justificativas', icon: 'MessageSquare', permissions: ['operacional:read'] },
      { id: 'ponto-atrasos', title: 'Atrasos e Faltas', href: '/modulos/gestao-pessoas/ponto/atrasos', icon: 'AlertTriangle', permissions: ['operacional:read'] },
      { id: 'ponto-banco-horas', title: 'Banco de Horas', href: '/modulos/gestao-pessoas/ponto/banco-horas', icon: 'Clock', permissions: ['operacional:read'] },
      { id: 'ponto-fechamento', title: 'Fechamento Mensal', href: '/modulos/gestao-pessoas/ponto/fechamento', icon: 'CheckCircle', permissions: ['operacional:read'] },
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
    permissions: ['operacional:read'],
    enabled: true,
    subModules: [
      { id: 'portal-contracheque', title: 'Contracheques', href: '/modulos/portal/contracheque', icon: 'FileText', permissions: ['operacional:read'] },
      { id: 'portal-ferias', title: 'Ferias', href: '/modulos/portal/ferias', icon: 'Palmtree', permissions: ['operacional:read'] },
      { id: 'portal-documentos', title: 'Documentos', href: '/modulos/portal/documentos', icon: 'FolderOpen', permissions: ['operacional:read'] },
      { id: 'portal-treinamentos', title: 'Treinamentos', href: '/modulos/portal/treinamentos', icon: 'GraduationCap', permissions: ['operacional:read'] },
      { id: 'portal-assinatura', title: 'Assinatura Digital', href: '/modulos/portal/assinatura', icon: 'PenTool', permissions: ['operacional:read'] },
      { id: 'portal-notificacoes', title: 'Notificacoes', href: '/modulos/portal/notificacoes', icon: 'Bell', permissions: ['operacional:read'] },
      { id: 'portal-dados', title: 'Meus Dados', href: '/modulos/portal/dados-pessoais', icon: 'User', permissions: ['operacional:read'] },
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
    permissions: ['ged:read'],
    enabled: true,
    external: true,
    subModules: [
      { id: 'ac-dashboard', title: 'Dashboard', href: '/area-cliente', icon: 'LayoutDashboard', permissions: ['ged:read'] },
      { id: 'ac-kits', title: 'Kits Documentais', href: '/area-cliente/kits', icon: 'Package', permissions: ['ged:read'] },
      { id: 'ac-chamados', title: 'Chamados', href: '/area-cliente/chamados', icon: 'MessageSquare', permissions: ['ged:read'] },
      { id: 'ac-configuracoes', title: 'Configuracoes', href: '/area-cliente/configuracoes', icon: 'Settings', permissions: ['ged:admin'] },
      { id: 'ac-gerenciamento', title: 'Gerenciamento de Acessos', href: '/modulos/area-cliente/gerenciamento', icon: 'Key', permissions: ['ged:admin'] },
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
    permissions: ['financial:read'],
    enabled: true,
    subModules: [
      { id: 'cfo-ia', title: 'CFO IA', href: '/modulos/financeiro/cfo', icon: 'Bot', permissions: ['financial:read'] },
      { id: 'dashboard-financeiro', title: 'Dashboard Financeiro', href: '/modulos/financeiro/dashboard', icon: 'LayoutDashboard', permissions: ['financial:read'] },
      { id: 'contratos', title: 'Contratos', href: '/modulos/financeiro/contratos', icon: 'FileText', permissions: ['financial:read'] },
      { id: 'contas-pagar', title: 'Contas a Pagar', href: '/modulos/financeiro/contas-pagar', icon: 'TrendingDown', permissions: ['financial:contas-pagar'] },
      { id: 'contas-receber', title: 'Contas a Receber', href: '/modulos/financeiro/contas-receber', icon: 'TrendingUp', permissions: ['financial:contas-receber'] },
      { id: 'fluxo-caixa', title: 'Fluxo de Caixa', href: '/modulos/financeiro/fluxo-caixa', icon: 'Activity', permissions: ['financial:fluxo'] },
      { id: 'conciliacao', title: 'Conciliacao Bancaria', href: '/modulos/financeiro/conciliacao', icon: 'CheckCircle2', permissions: ['financial:conciliacao'] },
      { id: 'boletos', title: 'Boletos', href: '/modulos/financeiro/boletos', icon: 'CreditCard', permissions: ['financial:faturamento'] },
      { id: 'cobrancas', title: 'Cobrancas', href: '/modulos/financeiro/cobrancas', icon: 'DollarSign', permissions: ['financial:faturamento'] },
      { id: 'fornecedores', title: 'Fornecedores', href: '/modulos/financeiro/fornecedores', icon: 'Truck', permissions: ['financial:fornecedores'] },
      // --- Suprimentos ---
      { id: 'compras', title: 'Compras', href: '/modulos/financeiro/compras', icon: 'ShoppingCart', permissions: ['financial:compras'] },
      { id: 'estoque', title: 'Estoque', href: '/modulos/financeiro/estoque', icon: 'Package', permissions: ['financial:estoque'] },
      // --- Custos e Precificacao ---
      { id: 'custos', title: 'Custos', href: '/modulos/financeiro/custos', icon: 'PieChart', permissions: ['financial:custeio'] },
      { id: 'custeio', title: 'Custeio ABC', href: '/modulos/financeiro/custeio', icon: 'Calculator', permissions: ['financial:custeio'] },
      { id: 'orcamentos', title: 'Orcamentos', href: '/modulos/financeiro/orcamentos', icon: 'Target', permissions: ['financial:read'] },
      // --- Contabilidade e Relatorios ---
      { id: 'contabilidade', title: 'Contabilidade', href: '/modulos/financeiro/contabilidade', icon: 'Calculator', permissions: ['financial:contabilidade'] },
      { id: 'faturamento', title: 'Faturamento', href: '/modulos/financeiro/faturamento', icon: 'Receipt', permissions: ['financial:faturamento'] },
      { id: 'relatorios-fin', title: 'Relatorios', href: '/modulos/financeiro/relatorios', icon: 'BarChart2', permissions: ['financial:read'] },
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
    permissions: ['government:read'],
    enabled: true,
    subModules: [
      { id: 'fiscal-ia', title: 'Consultor Fiscal IA', href: '/modulos/fiscal/consultor', icon: 'Bot', permissions: ['government:read'] },
      // --- Notas Fiscais ---
      { id: 'nfe', title: 'NF-e', href: '/modulos/financeiro/fiscal', icon: 'Receipt', permissions: ['government:nfse'], group: 'Notas Fiscais' },
      { id: 'nfse', title: 'NFS-e', href: '/modulos/fiscal/nfse', icon: 'FileText', permissions: ['government:nfse'], group: 'Notas Fiscais' },
      { id: 'nfse-multi', title: 'NFS-e Multi-Empresa', href: '/modulos/fiscal/nfse-multi', icon: 'FileText', permissions: ['government:nfse'], group: 'Notas Fiscais' },
      // --- Certidoes (CNDs) ---
      { id: 'certidoes', title: 'Painel de Certidoes', href: '/modulos/fiscal/certidoes', icon: 'Award', permissions: ['government:certidoes'], group: 'Certidoes' },
      { id: 'cnd-federal', title: 'CND Federal', href: '/modulos/fiscal/certidoes/federal', icon: 'Landmark', permissions: ['government:certidoes'], group: 'Certidoes' },
      { id: 'cnd-estadual', title: 'CND Estadual', href: '/modulos/fiscal/certidoes/estadual', icon: 'Map', permissions: ['government:certidoes'], group: 'Certidoes' },
      { id: 'cnd-municipal', title: 'CND Municipal', href: '/modulos/fiscal/certidoes/municipal', icon: 'Building', permissions: ['government:certidoes'], group: 'Certidoes' },
      { id: 'crf-fgts', title: 'CRF/FGTS', href: '/modulos/fiscal/certidoes/fgts', icon: 'ShieldCheck', permissions: ['government:certidoes'], group: 'Certidoes' },
      { id: 'cndt', title: 'CNDT (Trabalhista)', href: '/modulos/fiscal/certidoes/trabalhista', icon: 'Users', permissions: ['government:certidoes'], group: 'Certidoes' },
      // --- Obrigacoes ---
      { id: 'esocial', title: 'eSocial', href: '/modulos/fiscal/esocial', icon: 'Users', permissions: ['government:esocial'], group: 'Obrigacoes' },
      { id: 'sped', title: 'SPED', href: '/modulos/fiscal/sped', icon: 'Database', permissions: ['government:sped'], group: 'Obrigacoes' },
      { id: 'dctfweb', title: 'DCTFWeb', href: '/modulos/fiscal/dctfweb', icon: 'FileSpreadsheet', permissions: ['government:dctfweb'], group: 'Obrigacoes' },
      { id: 'reinf', title: 'EFD-Reinf', href: '/modulos/fiscal/reinf', icon: 'FileCode', permissions: ['government:reinf'], group: 'Obrigacoes' },
      // --- Multi-Empresa ---
      { id: 'empresas-gestao', title: 'Gestao Empresas', href: '/modulos/empresas', icon: 'Building2', permissions: ['empresas:read'], group: 'Multi-Empresa' },
      { id: 'liminares', title: 'Liminares', href: '/modulos/empresas/liminares', icon: 'Scale', permissions: ['empresas:read'], group: 'Multi-Empresa' },
      { id: 'rentabilidade', title: 'Rentabilidade', href: '/modulos/empresas/rentabilidade', icon: 'TrendingUp', permissions: ['empresas:read'], group: 'Multi-Empresa' },
      { id: 'dashboard-empresas', title: 'Dashboard Multi-CNPJ', href: '/modulos/empresas/dashboard', icon: 'LayoutDashboard', permissions: ['empresas:read'], group: 'Multi-Empresa' },
      { id: 'demonstrativos', title: 'Demonstrativos', href: '/modulos/empresas/demonstrativos', icon: 'BarChart2', permissions: ['empresas:read'], group: 'Multi-Empresa' },
      { id: 'obrigacoes-empresa', title: 'Obrigacoes', href: '/modulos/empresas/obrigacoes', icon: 'CalendarDays', permissions: ['empresas:read'], group: 'Multi-Empresa' },
      { id: 'migrador', title: 'Migrador Contratos', href: '/modulos/empresas/migrador', icon: 'ArrowRightLeft', permissions: ['empresas:read'], group: 'Multi-Empresa' },
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
    permissions: ['operacional:read'],
    enabled: true,
    subModules: [
      { id: 'juridico-hub', title: 'Visao Geral', href: '/modulos/juridico', icon: 'LayoutDashboard', permissions: ['operacional:read'], group: 'Escritorio' },
      { id: 'juridico-processos', title: 'Processos & Defesa', href: '/modulos/juridico/processos', icon: 'Gavel', permissions: ['operacional:read'], group: 'Escritorio' },
      { id: 'juridico-det', title: 'Monitoramento DET', href: '/modulos/juridico/det', icon: 'Landmark', permissions: ['operacional:read'], group: 'Escritorio' },
      { id: 'juridico-consultor', title: 'Consultor Juridico IA', href: '/modulos/juridico/consultor', icon: 'Bot', permissions: ['operacional:read'], group: 'Escritorio' },
      { id: 'juridico-pareceres', title: 'Pareceres (IA)', href: '/modulos/juridico/pareceres', icon: 'FileSignature', permissions: ['operacional:read'], group: 'Escritorio' },
      { id: 'juridico-riscos', title: 'Riscos (Trabalhista/Tributario)', href: '/modulos/juridico/riscos', icon: 'AlertTriangle', permissions: ['operacional:read'], group: 'Escritorio' },
      { id: 'juridico-escritorio', title: 'Escritorio & ROI', href: '/modulos/juridico/escritorio', icon: 'Building2', permissions: ['operacional:read'], group: 'Escritorio' },
      { id: 'juridico-conhecimento', title: 'Base de Conhecimento', href: '/modulos/juridico/conhecimento', icon: 'BookOpen', permissions: ['operacional:read'], group: 'Escritorio' },
      { id: 'juridico-contratos', title: 'Central de Contratos', href: '/modulos/juridico/contratos', icon: 'FileText', permissions: ['operacional:read'], group: 'Contratos' },
      { id: 'juridico-analise', title: 'Analise de Contratos (IA)', href: '/modulos/juridico/analise', icon: 'Search', permissions: ['operacional:read'], group: 'Contratos' },
      { id: 'juridico-certidoes', title: 'Certidoes (CND/FGTS)', href: '/modulos/fiscal/certidoes', icon: 'Award', permissions: ['government:certidoes'], group: 'Compliance' },
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
    permissions: ['reports:read'],
    enabled: true,
    subModules: [
      { id: 'dashboards', title: 'Dashboards', href: '/modulos/relatorios/dashboards', icon: 'LayoutDashboard', permissions: ['reports:dashboards'] },
      { id: 'rel-operacional', title: 'Operacional', href: '/modulos/relatorios/operacional', icon: 'ClipboardCheck', permissions: ['reports:operacional'] },
      { id: 'rel-financeiro', title: 'Financeiro', href: '/modulos/relatorios/financeiro', icon: 'PieChart', permissions: ['reports:financeiro'] },
      { id: 'rel-comercial', title: 'Comercial', href: '/modulos/relatorios/comercial', icon: 'TrendingUp', permissions: ['reports:comercial'] },
      { id: 'analytics', title: 'Analytics', href: '/modulos/analytics', icon: 'Activity', permissions: ['reports:read'] },
      { id: 'rel-operacional-detalhado', title: 'Relatorios Operacionais', href: '/modulos/operacional/relatorios', icon: 'FileText', permissions: ['operacional:read'] },
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
    permissions: ['equipment:patrimonio'],
    enabled: true,
    subModules: [
      { id: 'patrimonio-equip', title: 'Patrimonio', href: '/modulos/equipamentos/patrimonio', icon: 'Package', permissions: ['equipment:patrimonio'] },
      { id: 'comodatos', title: 'Comodatos', href: '/modulos/equipamentos/comodatos', icon: 'Repeat', permissions: ['equipment:comodatos'] },
      { id: 'manutencoes', title: 'Manutencoes', href: '/modulos/equipamentos/manutencoes', icon: 'Wrench', permissions: ['equipment:manutencoes'] },
      // --- GED Generico (arquivos e pastas) ---
      { id: 'arquivos', title: 'Arquivos', href: '/modulos/documentos/arquivos', icon: 'File', permissions: ['ged:arquivos'], group: 'Documentos Gerais' },
      { id: 'pastas', title: 'Pastas', href: '/modulos/documentos/pastas', icon: 'Folder', permissions: ['ged:pastas'], group: 'Documentos Gerais' },
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
    permissions: ['integrations:read'],
    enabled: true,
    subModules: [
      // --- Integracoes ---
      { id: 'conectores', title: 'Conectores', href: '/modulos/integracoes/conectores', icon: 'Plug', permissions: ['integrations:conectores'] },
      { id: 'api-keys', title: 'API Keys', href: '/modulos/integracoes/api-keys', icon: 'Key', permissions: ['integrations:api-keys'] },
      { id: 'webhooks', title: 'Webhooks', href: '/modulos/integracoes/webhooks', icon: 'Webhook', permissions: ['integrations:webhooks'] },
      { id: 'logs-integracao', title: 'Logs', href: '/modulos/integracoes/logs', icon: 'FileText', permissions: ['integrations:logs'] },
      { id: 'sync', title: 'Sincronizacao', href: '/modulos/integracoes/sync', icon: 'RefreshCw', permissions: ['integrations:sync'] },
      { id: 'solides', title: 'Solides', href: '/modulos/integracoes/solides', icon: 'Zap', permissions: ['integrations:solides'] },
      // --- Seguranca & LGPD ---
      { id: 'auditoria', title: 'Auditoria', href: '/modulos/seguranca/auditoria', icon: 'Eye', permissions: ['security:auditoria'] },
      { id: 'consentimento', title: 'Consentimento', href: '/modulos/seguranca/consentimento', icon: 'CheckCircle2', permissions: ['security:consentimento'] },
      { id: 'pia-dpia', title: 'PIA/DPIA', href: '/modulos/seguranca/pia-dpia', icon: 'FileText', permissions: ['security:pia'] },
      { id: 'esquecimento', title: 'Esquecimento', href: '/modulos/seguranca/esquecimento', icon: 'Trash2', permissions: ['security:esquecimento'] },
      { id: 'mascaramento', title: 'Mascaramento', href: '/modulos/seguranca/mascaramento', icon: 'Eye', permissions: ['security:mascaramento'] },
      { id: 'criptografia', title: 'Criptografia', href: '/modulos/seguranca/criptografia', icon: 'Lock', permissions: ['security:criptografia'] },
      // --- Agendador ---
      { id: 'tarefas-agendador', title: 'Tarefas Agendadas', href: '/modulos/agendador/tarefas', icon: 'Clock', permissions: ['config:read'] },
      { id: 'execucoes-agendador', title: 'Execucoes', href: '/modulos/agendador/execucoes', icon: 'Play', permissions: ['config:read'] },
      // --- Automacoes ---
      { id: 'workflows', title: 'Workflows', href: '/modulos/automacoes/workflows', icon: 'GitBranch', permissions: ['config:read'] },
      { id: 'execucoes-workflow', title: 'Execucoes Workflow', href: '/modulos/automacoes/execucoes', icon: 'Play', permissions: ['config:read'] },
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
    permissions: ['config:read'],
    enabled: true,
    subModules: [
      { id: 'ceo-ia', title: 'Consultor Executivo IA', href: '/modulos/configuracoes/consultor', icon: 'Bot', permissions: ['config:read'] },
      { id: 'dashboard-config', title: 'Dashboard', href: '/modulos/configuracoes', icon: 'LayoutDashboard', permissions: ['config:read'] },
      { id: 'tenants', title: 'Tenants', href: '/modulos/configuracoes/tenants', icon: 'Building2', permissions: ['config:tenants'] },
      { id: 'feature-flags', title: 'Feature Flags', href: '/modulos/configuracoes/feature-flags', icon: 'ToggleRight', permissions: ['config:flags'] },
      { id: 'sistema', title: 'Sistema', href: '/modulos/configuracoes/configuracoes-sistema', icon: 'Settings', permissions: ['config:system'] },
      { id: 'templates', title: 'Templates', href: '/modulos/configuracoes/templates-notificacao', icon: 'Mail', permissions: ['config:templates'] },
      { id: 'integracoes-config', title: 'Integrações', href: '/modulos/configuracoes/integracoes', icon: 'Plug', permissions: ['config:integrations'] },
      { id: 'usuarios-permissoes', title: 'Usuários & Permissões', href: '/modulos/configuracoes/usuarios', icon: 'Shield', permissions: ['config:read'] },
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
      if (path.startsWith(sub.href)) {
        return m;
      }
    }
  }

  return undefined;
}
