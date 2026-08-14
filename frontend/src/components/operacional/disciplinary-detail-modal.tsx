'use client';

import { CheckCircle, XCircle, Send, FileSignature, Loader2, Calendar, User, AlertTriangle, Brain, Scale, ShieldCheck, ShieldAlert } from 'lucide-react';
import { useState } from 'react';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
import { disciplinaryService } from '@/services/disciplinary';
import { getErrorMessage } from '@/lib/api';
import {
  ACTION_TYPE_LABELS,
  STATUS_LABELS,
  REASON_CATEGORY_LABELS,
  STATUS_COLORS,
  type DisciplinaryAction,
} from '@/types/disciplinary';

interface DisciplinaryDetailModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  action: DisciplinaryAction | null;
  onOpenSignature?: (action: DisciplinaryAction) => void;
}

export function DisciplinaryDetailModal({
  isOpen,
  onClose,
  onSuccess,
  action,
  onOpenSignature,
}: DisciplinaryDetailModalProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showApproveForm, setShowApproveForm] = useState(false);
  const [showRejectForm, setShowRejectForm] = useState(false);
  const [approvalComments, setApprovalComments] = useState('');
  const [rejectionReason, setRejectionReason] = useState('');

  // IA Validation States
  const [isValidatingCompliance, setIsValidatingCompliance] = useState(false);
  const [isCheckingProportionality, setIsCheckingProportionality] = useState(false);
  const [complianceResult, setComplianceResult] = useState<{
    compliant: boolean;
    issues: string[];
    suggestions: string[];
  } | null>(null);
  const [proportionalityResult, setProportionalityResult] = useState<{
    proportional: boolean;
    analysis: string;
  } | null>(null);

  if (!action) return null;

  const handleSubmit = async () => {
    setIsLoading(true);
    setError(null);

    try {
      await disciplinaryService.submit(action.id);
      onSuccess();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleApprove = async () => {
    setIsLoading(true);
    setError(null);

    try {
      await disciplinaryService.approve(action.id, approvalComments || undefined);
      onSuccess();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleReject = async () => {
    if (!rejectionReason.trim()) {
      setError('Motivo da rejeição é obrigatório');
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      await disciplinaryService.reject(action.id, rejectionReason);
      onSuccess();
      onClose();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleValidateCompliance = async () => {
    setIsValidatingCompliance(true);
    setError(null);
    setComplianceResult(null);

    try {
      const result = await disciplinaryService.validateCompliance(action);
      setComplianceResult(result);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsValidatingCompliance(false);
    }
  };

  const handleCheckProportionality = async () => {
    setIsCheckingProportionality(true);
    setError(null);
    setProportionalityResult(null);

    try {
      const result = await disciplinaryService.checkProportionality(action);
      setProportionalityResult(result);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsCheckingProportionality(false);
    }
  };

  const formatDate = (date: string | null | undefined) => {
    if (!date) return '-';
    return new Date(date).toLocaleDateString('pt-BR');
  };

  const formatDateTime = (date: string | null | undefined) => {
    if (!date) return '-';
    return new Date(date).toLocaleString('pt-BR');
  };

  const statusColor = STATUS_COLORS[action.status] || 'bg-gray-500/10 text-gray-500';

  const canSubmit = action.status === 'rascunho';
  const canApprove = action.status === 'pendente_aprovacao';
  const canSign = action.status === 'pendente_assinatura' || action.status === 'aprovada';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={action.code}
      description={STATUS_LABELS[action.status] || action.status}
      size="xl"
    >
      <div className="space-y-6">
        {error && (
          <div className="bg-red-500/10 border border-red-500/50 text-red-500 px-4 py-3 rounded-lg text-sm">
            {error}
          </div>
        )}

        {/* Status Badge */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle className="w-5 h-5 text-yellow-500" />
            <span className="font-semibold text-lg">
              {ACTION_TYPE_LABELS[action.action_type] || action.action_type}
            </span>
          </div>
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${statusColor}`}>
            {STATUS_LABELS[action.status]}
          </span>
        </div>

        {/* Dados do Funcionário */}
        <div className="border border-[hsl(var(--border))] rounded-lg p-4 space-y-3">
          <h3 className="font-medium flex items-center gap-2">
            <User className="w-4 h-4" />
            Dados do Funcionário
          </h3>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <span className="text-[hsl(var(--muted-foreground))]">Nome:</span>
              <p className="font-medium">{action.employee_name || '-'}</p>
            </div>
            <div>
              <span className="text-[hsl(var(--muted-foreground))]">CPF:</span>
              <p className="font-medium">{action.employee_cpf || '-'}</p>
            </div>
            <div>
              <span className="text-[hsl(var(--muted-foreground))]">Cargo:</span>
              <p className="font-medium">{action.employee_position || '-'}</p>
            </div>
            <div>
              <span className="text-[hsl(var(--muted-foreground))]">Admissão:</span>
              <p className="font-medium">{formatDate(action.employee_admission_date)}</p>
            </div>
          </div>
        </div>

        {/* Motivo */}
        <div className="border border-[hsl(var(--border))] rounded-lg p-4 space-y-3">
          <h3 className="font-medium flex items-center gap-2">
            <Calendar className="w-4 h-4" />
            Motivo da Medida
          </h3>
          <div className="space-y-3 text-sm">
            <div className="grid grid-cols-2 gap-4">
              <div>
                <span className="text-[hsl(var(--muted-foreground))]">Categoria:</span>
                <p className="font-medium">
                  {REASON_CATEGORY_LABELS[action.reason_category] || action.reason_category}
                </p>
              </div>
              <div>
                <span className="text-[hsl(var(--muted-foreground))]">Data do Incidente:</span>
                <p className="font-medium">{formatDate(action.incident_date)}</p>
              </div>
            </div>
            <div>
              <span className="text-[hsl(var(--muted-foreground))]">Descrição:</span>
              <p className="mt-1 p-3 bg-[hsl(var(--muted))] rounded-lg whitespace-pre-wrap">
                {action.reason_description}
              </p>
            </div>
          </div>
        </div>

        {/* Suspensão (se aplicável) */}
        {action.action_type === 'suspensao' && action.suspension_days && (
          <div className="border border-yellow-500/30 bg-yellow-500/5 rounded-lg p-4 space-y-3">
            <h3 className="font-medium text-yellow-500">Período de Suspensão</h3>
            <div className="grid grid-cols-3 gap-4 text-sm">
              <div>
                <span className="text-[hsl(var(--muted-foreground))]">Dias:</span>
                <p className="font-medium">{action.suspension_days}</p>
              </div>
              <div>
                <span className="text-[hsl(var(--muted-foreground))]">Início:</span>
                <p className="font-medium">{formatDate(action.suspension_start_date)}</p>
              </div>
              <div>
                <span className="text-[hsl(var(--muted-foreground))]">Término:</span>
                <p className="font-medium">{formatDate(action.suspension_end_date)}</p>
              </div>
            </div>
          </div>
        )}

        {/* Assinaturas */}
        {(action.employee_signed_at || action.supervisor_signed_at || action.hr_signed_at) && (
          <div className="border border-[hsl(var(--border))] rounded-lg p-4 space-y-3">
            <h3 className="font-medium flex items-center gap-2">
              <FileSignature className="w-4 h-4" />
              Assinaturas
            </h3>
            <div className="space-y-2 text-sm">
              {action.employee_signed_at && (
                <div className="flex items-center gap-2 text-green-500">
                  <CheckCircle className="w-4 h-4" />
                  <span>Funcionário assinou em {formatDateTime(action.employee_signed_at)}</span>
                </div>
              )}
              {action.employee_refused_sign && (
                <div className="flex items-center gap-2 text-red-500">
                  <XCircle className="w-4 h-4" />
                  <span>Funcionário recusou assinar (testemunhas registradas)</span>
                </div>
              )}
              {action.supervisor_signed_at && (
                <div className="flex items-center gap-2 text-green-500">
                  <CheckCircle className="w-4 h-4" />
                  <span>Supervisor assinou em {formatDateTime(action.supervisor_signed_at)}</span>
                </div>
              )}
              {action.hr_signed_at && (
                <div className="flex items-center gap-2 text-green-500">
                  <CheckCircle className="w-4 h-4" />
                  <span>RH assinou em {formatDateTime(action.hr_signed_at)}</span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Validacao IA */}
        <div className="border border-[hsl(var(--border))] rounded-lg p-4 space-y-4">
          <h3 className="font-medium flex items-center gap-2">
            <Brain className="w-4 h-4 text-purple-500" />
            Validacao por IA
          </h3>

          <div className="flex flex-wrap gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleValidateCompliance}
              disabled={isValidatingCompliance}
            >
              {isValidatingCompliance ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <ShieldCheck className="w-4 h-4 mr-2 text-blue-500" />
              )}
              Validar Conformidade CLT
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleCheckProportionality}
              disabled={isCheckingProportionality}
            >
              {isCheckingProportionality ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Scale className="w-4 h-4 mr-2 text-orange-500" />
              )}
              Verificar Proporcionalidade
            </Button>
          </div>

          {/* Resultado Conformidade CLT */}
          {complianceResult && (
            <div className={`p-3 rounded-lg ${complianceResult.compliant ? 'bg-green-500/10 border border-green-500/30' : 'bg-red-500/10 border border-red-500/30'}`}>
              <div className="flex items-center gap-2 mb-2">
                {complianceResult.compliant ? (
                  <ShieldCheck className="w-5 h-5 text-green-500" />
                ) : (
                  <ShieldAlert className="w-5 h-5 text-red-500" />
                )}
                <span className={`font-medium ${complianceResult.compliant ? 'text-green-500' : 'text-red-500'}`}>
                  {complianceResult.compliant ? 'Conforme com a CLT' : 'Problemas de Conformidade'}
                </span>
              </div>
              {complianceResult.issues.length > 0 && (
                <div className="mt-2">
                  <p className="text-sm font-medium text-red-500">Problemas encontrados:</p>
                  <ul className="list-disc list-inside text-sm text-[hsl(var(--muted-foreground))]">
                    {complianceResult.issues.map((issue, i) => (
                      <li key={i}>{issue}</li>
                    ))}
                  </ul>
                </div>
              )}
              {complianceResult.suggestions.length > 0 && (
                <div className="mt-2">
                  <p className="text-sm font-medium text-blue-500">Sugestoes:</p>
                  <ul className="list-disc list-inside text-sm text-[hsl(var(--muted-foreground))]">
                    {complianceResult.suggestions.map((suggestion, i) => (
                      <li key={i}>{suggestion}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}

          {/* Resultado Proporcionalidade */}
          {proportionalityResult && (
            <div className={`p-3 rounded-lg ${proportionalityResult.proportional ? 'bg-green-500/10 border border-green-500/30' : 'bg-yellow-500/10 border border-yellow-500/30'}`}>
              <div className="flex items-center gap-2 mb-2">
                <Scale className={`w-5 h-5 ${proportionalityResult.proportional ? 'text-green-500' : 'text-yellow-500'}`} />
                <span className={`font-medium ${proportionalityResult.proportional ? 'text-green-500' : 'text-yellow-500'}`}>
                  {proportionalityResult.proportional ? 'Medida Proporcional' : 'Verificar Proporcionalidade'}
                </span>
              </div>
              <p className="text-sm text-[hsl(var(--muted-foreground))]">{proportionalityResult.analysis}</p>
            </div>
          )}
        </div>

        {/* Formulário de Aprovação */}
        {showApproveForm && (
          <div className="border border-green-500/30 bg-green-500/5 rounded-lg p-4 space-y-3">
            <h3 className="font-medium text-green-500">Aprovar Medida</h3>
            <div className="space-y-2">
              <label className="block text-sm text-[hsl(var(--muted-foreground))]">
                Comentários (opcional)
              </label>
              <textarea
                value={approvalComments}
                onChange={(e) => setApprovalComments(e.target.value)}
                placeholder="Observações sobre a aprovação..."
                rows={3}
                className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] resize-none"
              />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowApproveForm(false)}>
                Cancelar
              </Button>
              <Button
                size="sm"
                className="bg-green-500 hover:bg-green-600"
                onClick={handleApprove}
                disabled={isLoading}
              >
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Confirmar Aprovação'}
              </Button>
            </div>
          </div>
        )}

        {/* Formulário de Rejeição */}
        {showRejectForm && (
          <div className="border border-red-500/30 bg-red-500/5 rounded-lg p-4 space-y-3">
            <h3 className="font-medium text-red-500">Rejeitar Medida</h3>
            <div className="space-y-2">
              <label className="block text-sm text-[hsl(var(--muted-foreground))]">
                Motivo da Rejeição *
              </label>
              <textarea
                value={rejectionReason}
                onChange={(e) => setRejectionReason(e.target.value)}
                placeholder="Informe o motivo da rejeição..."
                rows={3}
                className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] resize-none"
              />
            </div>
            <div className="flex gap-2">
              <Button variant="outline" size="sm" onClick={() => setShowRejectForm(false)}>
                Cancelar
              </Button>
              <Button
                size="sm"
                variant="danger"
                onClick={handleReject}
                disabled={isLoading}
              >
                {isLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Confirmar Rejeição'}
              </Button>
            </div>
          </div>
        )}

        <ModalFooter>
          <Button variant="outline" onClick={onClose}>
            Fechar
          </Button>

          {canSubmit && (
            <Button onClick={handleSubmit} disabled={isLoading}>
              {isLoading ? (
                <Loader2 className="w-4 h-4 mr-2 animate-spin" />
              ) : (
                <Send className="w-4 h-4 mr-2" />
              )}
              Submeter para Aprovação
            </Button>
          )}

          {canApprove && !showApproveForm && !showRejectForm && (
            <>
              <Button
                variant="danger"
                onClick={() => setShowRejectForm(true)}
              >
                <XCircle className="w-4 h-4 mr-2" />
                Rejeitar
              </Button>
              <Button
                className="bg-green-500 hover:bg-green-600"
                onClick={() => setShowApproveForm(true)}
              >
                <CheckCircle className="w-4 h-4 mr-2" />
                Aprovar
              </Button>
            </>
          )}

          {canSign && onOpenSignature && (
            <Button
              variant="primary"
              onClick={() => {
                onClose();
                onOpenSignature(action);
              }}
            >
              <FileSignature className="w-4 h-4 mr-2" />
              Assinar Documento
            </Button>
          )}
        </ModalFooter>
      </div>
    </Modal>
  );
}
