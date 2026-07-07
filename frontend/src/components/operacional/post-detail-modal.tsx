'use client';

;
import { MapPin, Clock, Users, Phone, Mail, Shield, Car, Calendar, DollarSign, FileText, AlertCircle, CheckCircle } from 'lucide-react';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import type { Post, PostType, PostStatus, ShiftType } from '@/types/operacional';
import {
  POST_TYPE_LABELS,
  POST_STATUS_LABELS,
  SHIFT_TYPE_LABELS,
} from '@/types/operacional';

interface PostDetailModalProps {
  post: Post | null;
  isOpen: boolean;
  onClose: () => void;
  onEdit?: () => void;
}

export function PostDetailModal({
  post,
  isOpen,
  onClose,
  onEdit,
}: PostDetailModalProps) {
  if (!post) return null;

  const getStatusColor = (status: PostStatus) => {
    switch (status) {
      case 'active':
        return 'bg-green-500/10 text-green-500 border-green-500/20';
      case 'inactive':
        return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
      case 'temporary':
        return 'bg-blue-500/10 text-blue-500 border-blue-500/20';
      case 'suspended':
        return 'bg-red-500/10 text-red-500 border-red-500/20';
      default:
        return 'bg-gray-500/10 text-gray-500 border-gray-500/20';
    }
  };

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(value);
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={post.name}
      description={post.code}
      size="lg"
    >
      <div className="space-y-6">
        {/* Header Info */}
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-4">
            <div className="w-16 h-16 rounded-xl bg-cyan-500/10 flex items-center justify-center">
              <MapPin className="w-8 h-8 text-cyan-500" />
            </div>
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span
                  className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium border ${getStatusColor(
                    post.status as PostStatus
                  )}`}
                >
                  {post.status === 'active' ? (
                    <CheckCircle className="w-3 h-3 mr-1" />
                  ) : (
                    <AlertCircle className="w-3 h-3 mr-1" />
                  )}
                  {POST_STATUS_LABELS[post.status as PostStatus] || post.status}
                </span>
                <span className="text-sm text-[hsl(var(--muted-foreground))]">
                  {POST_TYPE_LABELS[post.post_type as PostType] || post.post_type}
                </span>
              </div>
              {post.description && (
                <p className="text-sm text-[hsl(var(--muted-foreground))] max-w-md">
                  {post.description}
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Efetivo */}
        <div className="bg-[hsl(var(--muted))]/50 rounded-xl p-4">
          <h3 className="text-sm font-medium text-[hsl(var(--foreground))] mb-3 flex items-center gap-2">
            <Users className="w-4 h-4" />
            Efetivo
          </h3>
          <div className="grid grid-cols-3 gap-4">
            <div className="text-center">
              <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                {post.required_headcount}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Necessario</p>
            </div>
            <div className="text-center">
              <p className="font-data text-2xl font-semibold tabular-nums text-green-500">
                {post.current_headcount}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Alocados</p>
            </div>
            <div className="text-center">
              <p
                className={`font-data text-2xl font-semibold tabular-nums ${
                  post.vacancy_count > 0 ? 'text-orange-500' : 'text-green-500'
                }`}
              >
                {post.vacancy_count}
              </p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">Vagas</p>
            </div>
          </div>
          {post.vacancy_count > 0 && (
            <div className="mt-3 flex items-center gap-2 text-orange-500 text-sm">
              <AlertCircle className="w-4 h-4" />
              Este posto precisa de {post.vacancy_count} funcionario(s)
            </div>
          )}
        </div>

        {/* Informações Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Turno */}
          <div>
            <h3 className="text-sm font-medium text-[hsl(var(--foreground))] mb-3 flex items-center gap-2">
              <Clock className="w-4 h-4" />
              Turno e Horarios
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[hsl(var(--muted-foreground))]">Tipo de Turno</span>
                <span className="text-[hsl(var(--foreground))]">
                  {SHIFT_TYPE_LABELS[post.shift_type as ShiftType] || post.shift_type}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[hsl(var(--muted-foreground))]">Horas Diarias</span>
                <span className="text-[hsl(var(--foreground))]">{post.daily_hours}h</span>
              </div>
              {post.shift_start_time && (
                <div className="flex justify-between">
                  <span className="text-[hsl(var(--muted-foreground))]">Inicio</span>
                  <span className="text-[hsl(var(--foreground))]">{post.shift_start_time}</span>
                </div>
              )}
              {post.shift_end_time && (
                <div className="flex justify-between">
                  <span className="text-[hsl(var(--muted-foreground))]">Fim</span>
                  <span className="text-[hsl(var(--foreground))]">{post.shift_end_time}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-[hsl(var(--muted-foreground))]">Intervalo</span>
                <span className="text-[hsl(var(--foreground))]">
                  {post.break_duration_minutes} min
                </span>
              </div>
            </div>
          </div>

          {/* Requisitos */}
          <div>
            <h3 className="text-sm font-medium text-[hsl(var(--foreground))] mb-3 flex items-center gap-2">
              <Shield className="w-4 h-4" />
              Requisitos
            </h3>
            <div className="space-y-2">
              <div className="flex items-center gap-2">
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                    post.requires_armed
                      ? 'bg-red-500/10 text-red-500'
                      : 'bg-gray-500/10 text-gray-400'
                  }`}
                >
                  <Shield className="w-4 h-4" />
                </div>
                <span
                  className={`text-sm ${
                    post.requires_armed
                      ? 'text-[hsl(var(--foreground))]'
                      : 'text-[hsl(var(--muted-foreground))]'
                  }`}
                >
                  {post.requires_armed ? 'Requer Armamento' : 'Nao requer armamento'}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <div
                  className={`w-8 h-8 rounded-lg flex items-center justify-center ${
                    post.requires_vehicle
                      ? 'bg-blue-500/10 text-blue-500'
                      : 'bg-gray-500/10 text-gray-400'
                  }`}
                >
                  <Car className="w-4 h-4" />
                </div>
                <span
                  className={`text-sm ${
                    post.requires_vehicle
                      ? 'text-[hsl(var(--foreground))]'
                      : 'text-[hsl(var(--muted-foreground))]'
                  }`}
                >
                  {post.requires_vehicle ? 'Requer Veiculo' : 'Nao requer veiculo'}
                </span>
              </div>
              {post.requires_experience_months > 0 && (
                <div className="flex items-center gap-2 text-sm">
                  <Calendar className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                  <span className="text-[hsl(var(--foreground))]">
                    Minimo {post.requires_experience_months} meses de experiencia
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Valores */}
          <div>
            <h3 className="text-sm font-medium text-[hsl(var(--foreground))] mb-3 flex items-center gap-2">
              <DollarSign className="w-4 h-4" />
              Valores
            </h3>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[hsl(var(--muted-foreground))]">Valor Hora</span>
                <span className="text-[hsl(var(--foreground))]">
                  {formatCurrency(post.hourly_rate)}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-[hsl(var(--muted-foreground))]">Custo Mensal</span>
                <span className="text-[hsl(var(--foreground))] font-medium">
                  {formatCurrency(post.monthly_cost)}
                </span>
              </div>
              {post.night_shift_bonus_percent > 0 && (
                <div className="flex justify-between">
                  <span className="text-[hsl(var(--muted-foreground))]">Adicional Noturno</span>
                  <span className="text-[hsl(var(--foreground))]">
                    {post.night_shift_bonus_percent}%
                  </span>
                </div>
              )}
              {post.hazard_pay_percent > 0 && (
                <div className="flex justify-between">
                  <span className="text-[hsl(var(--muted-foreground))]">Periculosidade</span>
                  <span className="text-[hsl(var(--foreground))]">
                    {post.hazard_pay_percent}%
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Contatos */}
          <div>
            <h3 className="text-sm font-medium text-[hsl(var(--foreground))] mb-3 flex items-center gap-2">
              <Phone className="w-4 h-4" />
              Contatos
            </h3>
            <div className="space-y-2 text-sm">
              {post.supervisor_name && (
                <div className="flex justify-between">
                  <span className="text-[hsl(var(--muted-foreground))]">Supervisor</span>
                  <span className="text-[hsl(var(--foreground))]">{post.supervisor_name}</span>
                </div>
              )}
              {post.supervisor_phone && (
                <div className="flex justify-between">
                  <span className="text-[hsl(var(--muted-foreground))]">Tel. Supervisor</span>
                  <span className="text-[hsl(var(--foreground))]">{post.supervisor_phone}</span>
                </div>
              )}
              {post.emergency_contact && (
                <div className="flex justify-between">
                  <span className="text-[hsl(var(--muted-foreground))]">Emergencia</span>
                  <span className="text-[hsl(var(--foreground))]">{post.emergency_contact}</span>
                </div>
              )}
              {post.emergency_phone && (
                <div className="flex justify-between">
                  <span className="text-[hsl(var(--muted-foreground))]">Tel. Emergencia</span>
                  <span className="text-[hsl(var(--foreground))]">{post.emergency_phone}</span>
                </div>
              )}
              {!post.supervisor_name && !post.emergency_contact && (
                <p className="text-[hsl(var(--muted-foreground))] italic">
                  Nenhum contato cadastrado
                </p>
              )}
            </div>
          </div>
        </div>

        {/* Localizacao */}
        {(post.address || post.city) && (
          <div>
            <h3 className="text-sm font-medium text-[hsl(var(--foreground))] mb-3 flex items-center gap-2">
              <MapPin className="w-4 h-4" />
              Localizacao
            </h3>
            <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-3 text-sm">
              {post.address && <p className="text-[hsl(var(--foreground))]">{post.address}</p>}
              {(post.city || post.state || post.zip_code) && (
                <p className="text-[hsl(var(--muted-foreground))]">
                  {[post.city, post.state, post.zip_code].filter(Boolean).join(' - ')}
                </p>
              )}
            </div>
          </div>
        )}

        {/* Observações */}
        {post.notes && (
          <div>
            <h3 className="text-sm font-medium text-[hsl(var(--foreground))] mb-3 flex items-center gap-2">
              <FileText className="w-4 h-4" />
              Observações
            </h3>
            <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-3">
              <p className="text-sm text-[hsl(var(--foreground))] whitespace-pre-wrap">
                {post.notes}
              </p>
            </div>
          </div>
        )}

        {/* Datas */}
        <div className="text-xs text-[hsl(var(--muted-foreground))] flex items-center justify-between pt-4 border-t border-[hsl(var(--border))]">
          <span>Criado em: {formatDate(post.created_at)}</span>
          <span>Atualizado em: {formatDate(post.updated_at)}</span>
        </div>
      </div>

      <ModalFooter>
        <Button variant="outline" onClick={onClose}>
          Fechar
        </Button>
        {onEdit && (
          <Button variant="primary" onClick={onEdit}>
            Editar Posto
          </Button>
        )}
      </ModalFooter>
    </Modal>
  );
}
