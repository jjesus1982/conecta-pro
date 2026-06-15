// Status, tipo e prioridade de Ordens de Serviço (módulo Campo) — labels PT-BR + cores

export const OS_STATUS_LABELS: Record<string, { label: string; color: string }> = {
  rascunho: { label: 'Rascunho', color: 'bg-gray-500/20 text-gray-400 border-gray-500/30' },
  aberta: { label: 'Aberta', color: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  agendada: { label: 'Agendada', color: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30' },
  aguardando_peca: { label: 'Aguardando peça', color: 'bg-amber-500/20 text-amber-400 border-amber-500/30' },
  aguardando_cliente: { label: 'Aguardando cliente', color: 'bg-amber-500/20 text-amber-400 border-amber-500/30' },
  em_deslocamento: { label: 'Em deslocamento', color: 'bg-indigo-500/20 text-indigo-400 border-indigo-500/30' },
  em_andamento: { label: 'Em andamento', color: 'bg-purple-500/20 text-purple-400 border-purple-500/30' },
  pausada: { label: 'Pausada', color: 'bg-orange-500/20 text-orange-400 border-orange-500/30' },
  concluida: { label: 'Concluída', color: 'bg-emerald-500/20 text-emerald-400 border-emerald-500/30' },
  cancelada: { label: 'Cancelada', color: 'bg-red-500/20 text-red-400 border-red-500/30' },
  reagendada: { label: 'Reagendada', color: 'bg-cyan-500/20 text-cyan-400 border-cyan-500/30' },
};

export const OS_PRIORIDADE_LABELS: Record<string, { label: string; color: string }> = {
  baixa: { label: 'Baixa', color: 'bg-gray-500/20 text-gray-400 border-gray-500/30' },
  normal: { label: 'Normal', color: 'bg-blue-500/20 text-blue-400 border-blue-500/30' },
  alta: { label: 'Alta', color: 'bg-amber-500/20 text-amber-400 border-amber-500/30' },
  urgente: { label: 'Urgente', color: 'bg-orange-500/20 text-orange-400 border-orange-500/30' },
  emergencia: { label: 'Emergência', color: 'bg-red-500/20 text-red-400 border-red-500/30' },
};

export const OS_TIPO_LABELS: Record<string, string> = {
  instalacao: 'Instalação',
  manutencao_preventiva: 'Manut. preventiva',
  manutencao_corretiva: 'Manut. corretiva',
  visita_tecnica: 'Visita técnica',
  visita_comercial: 'Visita comercial',
  vistoria: 'Vistoria',
  suporte: 'Suporte',
  retirada: 'Retirada',
  troca: 'Troca',
  ativacao: 'Ativação',
  desativacao: 'Desativação',
  outro: 'Outro',
};

const FALLBACK = { label: '—', color: 'bg-gray-500/20 text-gray-400 border-gray-500/30' };

export const osStatusConfig = (status?: string | null) =>
  OS_STATUS_LABELS[status ?? ''] ?? { ...FALLBACK, label: status || '—' };

export const osPrioridadeConfig = (p?: string | null) =>
  OS_PRIORIDADE_LABELS[p ?? ''] ?? { ...FALLBACK, label: p || '—' };

export const osTipoLabel = (t?: string | null) => OS_TIPO_LABELS[t ?? ''] ?? (t || '—');

// Opções para filtros (Select)
export const OS_STATUS_OPTIONS = Object.entries(OS_STATUS_LABELS).map(([value, v]) => ({ value, label: v.label }));
export const OS_PRIORIDADE_OPTIONS = Object.entries(OS_PRIORIDADE_LABELS).map(([value, v]) => ({ value, label: v.label }));
export const OS_TIPO_OPTIONS = Object.entries(OS_TIPO_LABELS).map(([value, label]) => ({ value, label }));
