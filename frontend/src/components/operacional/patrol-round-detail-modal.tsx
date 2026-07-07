'use client';

import { Shield, User, MapPin, Calendar, Clock, CheckSquare, AlertCircle, XCircle, Play, Pause, FileText, List } from 'lucide-react';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import {
  PATROL_ROUND_STATUS_LABELS,
  INSPECTOR_ROLE_LABELS,
  CHECKPOINT_TYPE_LABELS,
  CHECKPOINT_STATUS_LABELS,
  type PatrolRound,
  type PatrolRoundStatus,
  type CheckpointStatus,
} from '@/types/operacional';
;

interface PatrolRoundDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  patrolRound: PatrolRound | null;
}

// Cores dos status
const STATUS_COLORS: Record<PatrolRoundStatus, string> = {
  agendada: 'bg-blue-500/10 text-blue-500 border-blue-500/20',
  em_andamento: 'bg-green-500/10 text-green-500 border-green-500/20',
  pausada: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  concluida: 'bg-gray-500/10 text-gray-500 border-gray-500/20',
  cancelada: 'bg-red-500/10 text-red-500 border-red-500/20',
};

const CHECKPOINT_STATUS_COLORS: Record<CheckpointStatus, string> = {
  conforme: 'bg-green-500/10 text-green-500 border-green-500/20',
  nao_conforme: 'bg-red-500/10 text-red-500 border-red-500/20',
  pendente: 'bg-yellow-500/10 text-yellow-500 border-yellow-500/20',
  com_ocorrencia: 'bg-orange-500/10 text-orange-500 border-orange-500/20',
};

const getStatusIcon = (status: PatrolRoundStatus) => {
  switch (status) {
    case 'agendada':
      return <Clock className="w-4 h-4" />;
    case 'em_andamento':
      return <Play className="w-4 h-4" />;
    case 'pausada':
      return <Pause className="w-4 h-4" />;
    case 'concluida':
      return <CheckSquare className="w-4 h-4" />;
    case 'cancelada':
      return <XCircle className="w-4 h-4" />;
    default:
      return <Clock className="w-4 h-4" />;
  }
};

export function PatrolRoundDetailModal({
  isOpen,
  onClose,
  patrolRound,
}: PatrolRoundDetailModalProps) {
  if (!patrolRound) return null;

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const formatDuration = (minutes: number | null) => {
    if (!minutes) return '-';
    const hours = Math.floor(minutes / 60);
    const mins = minutes % 60;
    return hours > 0 ? `${hours}h ${mins}min` : `${mins}min`;
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Detalhes da Ronda"
      description={`Código: ${patrolRound.code}`}
      size="xl"
    >
      <div className="space-y-6">
        {/* Header com Status */}
        <div className="flex flex-wrap items-center gap-3">
          <span
            className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-full text-sm font-medium border ${
              STATUS_COLORS[patrolRound.status]
            }`}
          >
            {getStatusIcon(patrolRound.status)}
            {PATROL_ROUND_STATUS_LABELS[patrolRound.status]}
          </span>
          {patrolRound.progress_percentage > 0 && (
            <span className="text-sm text-[hsl(var(--muted-foreground))]">
              Progresso: {patrolRound.progress_percentage}%
            </span>
          )}
        </div>

        {/* Informações do Inspetor */}
        <div className="bg-[hsl(var(--muted))] rounded-lg p-4">
          <div className="flex items-center gap-2 mb-2">
            <User className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
            <span className="text-sm font-medium text-[hsl(var(--foreground))]">
              Inspetor
            </span>
          </div>
          <p className="text-lg font-semibold text-[hsl(var(--foreground))]">
            {patrolRound.inspector_name}
          </p>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            {INSPECTOR_ROLE_LABELS[patrolRound.inspector_role]}
          </p>
        </div>

        {/* Datas e Duração */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Calendar className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                Agendada para
              </span>
            </div>
            <p className="text-[hsl(var(--foreground))]">
              {formatDate(patrolRound.scheduled_date)}
            </p>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Play className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                Iniciada em
              </span>
            </div>
            <p className="text-[hsl(var(--foreground))]">
              {formatDate(patrolRound.started_at)}
            </p>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                Duração
              </span>
            </div>
            <p className="text-[hsl(var(--foreground))]">
              {formatDuration(patrolRound.duration_minutes)}
            </p>
          </div>
        </div>

        {/* Estatísticas */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-1">
              <CheckSquare className="w-4 h-4 text-blue-500" />
              <span className="text-sm text-blue-500">Checkpoints</span>
            </div>
            <p className="font-data text-2xl font-semibold tabular-nums text-blue-500">
              {patrolRound.total_checkpoints}
            </p>
          </div>

          <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-1">
              <AlertCircle className="w-4 h-4 text-red-500" />
              <span className="text-sm text-red-500">Ocorrências</span>
            </div>
            <p className="font-data text-2xl font-semibold tabular-nums text-red-500">
              {patrolRound.total_occurrences}
            </p>
          </div>

          <div className="bg-orange-500/10 border border-orange-500/20 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-1">
              <FileText className="w-4 h-4 text-orange-500" />
              <span className="text-sm text-orange-500">Med. Discip.</span>
            </div>
            <p className="font-data text-2xl font-semibold tabular-nums text-orange-500">
              {patrolRound.total_disciplinary_actions}
            </p>
          </div>

          <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-1">
              <User className="w-4 h-4 text-green-500" />
              <span className="text-sm text-green-500">Funcionários</span>
            </div>
            <p className="font-data text-2xl font-semibold tabular-nums text-green-500">
              {patrolRound.total_employees_checked}
            </p>
          </div>
        </div>

        {/* Observações */}
        {patrolRound.observations && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <FileText className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                Observações
              </span>
            </div>
            <p className="text-[hsl(var(--foreground))] whitespace-pre-wrap">
              {patrolRound.observations}
            </p>
          </div>
        )}

        {/* Resumo (se concluída) */}
        {patrolRound.status === 'concluida' && patrolRound.summary && (
          <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <CheckSquare className="w-4 h-4 text-green-500" />
              <span className="text-sm font-medium text-green-500">
                Resumo da Conclusão
              </span>
            </div>
            <p className="text-[hsl(var(--foreground))] whitespace-pre-wrap">
              {patrolRound.summary}
            </p>
            <div className="mt-3 text-sm text-[hsl(var(--muted-foreground))]">
              Concluída em: {formatDate(patrolRound.completed_at)}
            </div>
          </div>
        )}

        {/* Checkpoints */}
        {patrolRound.checkpoints && patrolRound.checkpoints.length > 0 && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-4">
            <div className="flex items-center gap-2 mb-4">
              <List className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                Checkpoints ({patrolRound.checkpoints.length})
              </span>
            </div>
            <div className="space-y-3">
              {patrolRound.checkpoints.map((checkpoint) => (
                <div
                  key={checkpoint.id}
                  className="bg-[hsl(var(--muted))] rounded-lg p-3"
                >
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <span className="text-xs font-mono text-[hsl(var(--muted-foreground))]">
                          #{checkpoint.sequence}
                        </span>
                        <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                          {CHECKPOINT_TYPE_LABELS[checkpoint.checkpoint_type]}
                        </span>
                      </div>
                      {checkpoint.post_name && (
                        <div className="flex items-center gap-1 text-xs text-[hsl(var(--muted-foreground))]">
                          <MapPin className="w-3 h-3" />
                          {checkpoint.post_name}
                        </div>
                      )}
                      {checkpoint.employee_name && (
                        <div className="flex items-center gap-1 text-xs text-[hsl(var(--muted-foreground))]">
                          <User className="w-3 h-3" />
                          {checkpoint.employee_name}
                        </div>
                      )}
                    </div>
                    <span
                      className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${
                        CHECKPOINT_STATUS_COLORS[checkpoint.status] ||
                        'bg-gray-500/10 text-gray-500 border-gray-500/20'
                      }`}
                    >
                      {CHECKPOINT_STATUS_LABELS[checkpoint.status]}
                    </span>
                  </div>
                  {checkpoint.description && (
                    <p className="text-sm text-[hsl(var(--foreground))] mt-2">
                      {checkpoint.description}
                    </p>
                  )}
                  {checkpoint.occurrence_code && (
                    <div className="mt-2 text-xs text-orange-500">
                      Ocorrência: {checkpoint.occurrence_code}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Localização */}
        {(patrolRound.start_latitude || patrolRound.total_distance_km) && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-4">
            <div className="flex items-center gap-2 mb-2">
              <MapPin className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                Informações de Localização
              </span>
            </div>
            <div className="grid grid-cols-2 gap-4 text-sm">
              {patrolRound.total_distance_km && (
                <div>
                  <span className="text-[hsl(var(--muted-foreground))]">
                    Distância percorrida:
                  </span>
                  <p className="text-[hsl(var(--foreground))] font-medium">
                    {patrolRound.total_distance_km.toFixed(2)} km
                  </p>
                </div>
              )}
              {patrolRound.posts_to_visit && (
                <div>
                  <span className="text-[hsl(var(--muted-foreground))]">
                    Postos planejados:
                  </span>
                  <p className="text-[hsl(var(--foreground))] font-medium">
                    {patrolRound.posts_to_visit.length}
                  </p>
                </div>
              )}
              {patrolRound.posts_visited && (
                <div>
                  <span className="text-[hsl(var(--muted-foreground))]">
                    Postos visitados:
                  </span>
                  <p className="text-[hsl(var(--foreground))] font-medium">
                    {patrolRound.posts_visited.length}
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Metadados */}
        <div className="flex flex-wrap gap-4 text-xs text-[hsl(var(--muted-foreground))]">
          <span>Criado em: {formatDate(patrolRound.created_at)}</span>
          <span>Atualizado em: {formatDate(patrolRound.updated_at)}</span>
        </div>
      </div>

      <ModalFooter>
        <Button variant="outline" onClick={onClose}>
          Fechar
        </Button>
      </ModalFooter>
    </Modal>
  );
}
