'use client';

import { Calendar, ChevronRight, ChevronLeft, AlertCircle, CheckCircle, Eye, Loader } from 'lucide-react';
import { useState, useEffect } from 'react';
import { Modal, ModalFooter } from '@/components/ui/modal';
import { Button } from '@/components/ui/button';
;
import type { ScaleTemplate, ScaleTemplateApply, Scale, Post } from '@/types/operacional';
import { SCALE_TYPE_LABELS } from '@/types/operacional';

interface ApplyTemplateDialogProps {
  isOpen: boolean;
  onClose: () => void;
  template: ScaleTemplate | null;
  posts: Post[];
  onSubmit: (data: ScaleTemplateApply) => Promise<Scale | null>;
  onPreview?: (data: ScaleTemplateApply) => Promise<Scale | null>;
  isLoading?: boolean;
}

const monthNames = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro'
];

export function ApplyTemplateDialog({
  isOpen,
  onClose,
  template,
  posts,
  onSubmit,
  onPreview,
  isLoading = false,
}: ApplyTemplateDialogProps) {
  const [step, setStep] = useState(1);
  const [formData, setFormData] = useState<ScaleTemplateApply>({
    month: new Date().getMonth() + 1,
    year: new Date().getFullYear(),
    post_id: null,
  });
  const [previewScale, setPreviewScale] = useState<Scale | null>(null);
  const [isLoadingPreview, setIsLoadingPreview] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});

  // Reset form when modal opens/closes
  useEffect(() => {
    if (!isOpen) {
      setStep(1);
      setFormData({
        month: new Date().getMonth() + 1,
        year: new Date().getFullYear(),
        post_id: template?.post_id || null,
      });
      setPreviewScale(null);
      setErrors({});
    } else if (template?.post_id) {
      setFormData(prev => ({ ...prev, post_id: template.post_id }));
    }
  }, [isOpen, template]);

  const validate = (currentStep: number): boolean => {
    const newErrors: Record<string, string> = {};

    if (currentStep === 1) {
      if (!formData.month || formData.month < 1 || formData.month > 12) {
        newErrors.month = 'Mês inválido';
      }
      if (!formData.year || formData.year < 2020) {
        newErrors.year = 'Ano inválido';
      }
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleNext = async () => {
    if (!validate(step)) return;

    if (step === 1 && onPreview) {
      // Load preview when moving to step 2
      setIsLoadingPreview(true);
      try {
        const preview = await onPreview(formData);
        setPreviewScale(preview);
        setStep(2);
      } catch (error) {
        console.error('Erro ao gerar preview:', error);
      } finally {
        setIsLoadingPreview(false);
      }
    } else {
      setStep(step + 1);
    }
  };

  const handleBack = () => {
    setStep(step - 1);
  };

  const handleSubmit = async () => {
    try {
      const result = await onSubmit(formData);
      if (result) {
        onClose();
      }
    } catch (error) {
      console.error('Erro ao aplicar template:', error);
    }
  };

  const currentYear = new Date().getFullYear();
  const years = Array.from({ length: 5 }, (_, i) => currentYear + i);

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title="Aplicar Template"
      description={template?.name || 'Criar nova escala a partir do template'}
      size="lg"
    >
      <div className="space-y-6">
        {/* Steps Indicator */}
        <div className="flex items-center justify-center gap-2 mb-6">
          <div
            className={`flex items-center justify-center w-8 h-8 rounded-full ${
              step >= 1
                ? 'bg-blue-500 text-white'
                : 'bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]'
            }`}
          >
            {step > 1 ? <CheckCircle className="w-4 h-4" /> : '1'}
          </div>
          <div
            className={`h-1 w-12 ${
              step >= 2 ? 'bg-blue-500' : 'bg-[hsl(var(--muted))]'
            }`}
          />
          <div
            className={`flex items-center justify-center w-8 h-8 rounded-full ${
              step >= 2
                ? 'bg-blue-500 text-white'
                : 'bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]'
            }`}
          >
            {step > 2 ? <CheckCircle className="w-4 h-4" /> : '2'}
          </div>
          <div
            className={`h-1 w-12 ${
              step >= 3 ? 'bg-blue-500' : 'bg-[hsl(var(--muted))]'
            }`}
          />
          <div
            className={`flex items-center justify-center w-8 h-8 rounded-full ${
              step >= 3
                ? 'bg-blue-500 text-white'
                : 'bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))]'
            }`}
          >
            3
          </div>
        </div>

        {/* Step 1: Select Month/Year */}
        {step === 1 && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-[hsl(var(--foreground))]">
              Selecionar Período
            </h3>

            {/* Template Info */}
            {template && (
              <div className="bg-blue-500/10 border border-blue-500/20 rounded-lg p-4">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-lg bg-blue-500/20 flex items-center justify-center">
                    <Calendar className="w-5 h-5 text-blue-500" />
                  </div>
                  <div>
                    <h4 className="font-medium text-[hsl(var(--foreground))]">
                      {template.name}
                    </h4>
                    <p className="text-sm text-[hsl(var(--muted-foreground))]">
                      {SCALE_TYPE_LABELS[template.scale_type]}
                    </p>
                  </div>
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-2">
                  Mês *
                </label>
                <select
                  value={formData.month}
                  onChange={(e) =>
                    setFormData({ ...formData, month: Number(e.target.value) })
                  }
                  className={`w-full h-10 px-3 rounded-lg border bg-[hsl(var(--background))] text-sm ${
                    errors.month ? 'border-red-500' : 'border-[hsl(var(--border))]'
                  }`}
                >
                  {monthNames.map((name, index) => (
                    <option key={index} value={index + 1}>
                      {name}
                    </option>
                  ))}
                </select>
                {errors.month && (
                  <p className="text-red-500 text-xs mt-1 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />
                    {errors.month}
                  </p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-2">
                  Ano *
                </label>
                <select
                  value={formData.year}
                  onChange={(e) =>
                    setFormData({ ...formData, year: Number(e.target.value) })
                  }
                  className={`w-full h-10 px-3 rounded-lg border bg-[hsl(var(--background))] text-sm ${
                    errors.year ? 'border-red-500' : 'border-[hsl(var(--border))]'
                  }`}
                >
                  {years.map((year) => (
                    <option key={year} value={year}>
                      {year}
                    </option>
                  ))}
                </select>
                {errors.year && (
                  <p className="text-red-500 text-xs mt-1 flex items-center gap-1">
                    <AlertCircle className="w-3 h-3" />
                    {errors.year}
                  </p>
                )}
              </div>
            </div>

            {/* Post Selection (if template doesn't have one) */}
            {!template?.post_id && (
              <div>
                <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-2">
                  Posto (opcional)
                </label>
                <select
                  value={formData.post_id || ''}
                  onChange={(e) =>
                    setFormData({ ...formData, post_id: e.target.value || null })
                  }
                  className="w-full h-10 px-3 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-sm"
                >
                  <option value="">Mesmo posto do template</option>
                  {posts.map((post) => (
                    <option key={post.id} value={post.id}>
                      {post.name}
                    </option>
                  ))}
                </select>
              </div>
            )}
          </div>
        )}

        {/* Step 2: Preview */}
        {step === 2 && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-[hsl(var(--foreground))]">
              Preview da Escala
            </h3>

            {isLoadingPreview ? (
              <div className="flex items-center justify-center py-12">
                <Loader className="w-8 h-8 animate-spin text-[hsl(var(--primary))]" />
              </div>
            ) : previewScale ? (
              <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-4">
                <div className="mb-4">
                  <h4 className="font-medium text-[hsl(var(--foreground))] mb-1">
                    {monthNames[previewScale.month - 1]} {previewScale.year}
                  </h4>
                  <p className="text-sm text-[hsl(var(--muted-foreground))]">
                    {SCALE_TYPE_LABELS[previewScale.scale_type]}
                  </p>
                </div>

                <div className="grid grid-cols-3 gap-3">
                  <div className="bg-[hsl(var(--card))] rounded-lg p-3 text-center">
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                      {previewScale.total_shifts}
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Turnos</p>
                  </div>
                  <div className="bg-[hsl(var(--card))] rounded-lg p-3 text-center">
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                      {previewScale.total_hours.toFixed(0)}h
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Horas</p>
                  </div>
                  <div className="bg-[hsl(var(--card))] rounded-lg p-3 text-center">
                    <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                      {previewScale.fill_rate?.toFixed(0) || 0}%
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">Cobertura</p>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-[hsl(var(--muted-foreground))]">
                <Eye className="w-12 h-12 mx-auto mb-2 opacity-50" />
                <p>Preview não disponível</p>
              </div>
            )}
          </div>
        )}

        {/* Step 3: Confirm */}
        {step === 3 && (
          <div className="space-y-4">
            <h3 className="text-lg font-semibold text-[hsl(var(--foreground))]">
              Confirmar Aplicação
            </h3>

            <div className="bg-green-500/10 border border-green-500/20 rounded-lg p-4">
              <div className="flex items-start gap-3">
                <CheckCircle className="w-5 h-5 text-green-500 mt-1 flex-shrink-0" />
                <div>
                  <p className="font-medium text-[hsl(var(--foreground))] mb-2">
                    Tudo pronto para criar a escala!
                  </p>
                  <ul className="text-sm text-[hsl(var(--muted-foreground))] space-y-1">
                    <li>• Período: {monthNames[formData.month - 1]}/{formData.year}</li>
                    <li>• Template: {template?.name}</li>
                    <li>
                      • Tipo: {template?.scale_type && SCALE_TYPE_LABELS[template.scale_type]}
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            <div className="bg-[hsl(var(--muted))]/50 rounded-lg p-4 text-sm text-[hsl(var(--muted-foreground))]">
              <p>
                A escala será criada em modo <strong>rascunho</strong>. Você poderá revisar e
                fazer ajustes antes de enviá-la para aprovação.
              </p>
            </div>
          </div>
        )}
      </div>

      <ModalFooter>
        {step > 1 && (
          <Button variant="outline" onClick={handleBack} disabled={isLoading}>
            <ChevronLeft className="w-4 h-4 mr-1" />
            Voltar
          </Button>
        )}
        <Button variant="outline" onClick={onClose} disabled={isLoading}>
          Cancelar
        </Button>
        {step < 3 ? (
          <Button onClick={handleNext} disabled={isLoadingPreview}>
            {isLoadingPreview ? (
              <>
                <Loader className="w-4 h-4 mr-2 animate-spin" />
                Carregando...
              </>
            ) : (
              <>
                Próximo
                <ChevronRight className="w-4 h-4 ml-1" />
              </>
            )}
          </Button>
        ) : (
          <Button onClick={handleSubmit} disabled={isLoading}>
            {isLoading ? 'Criando...' : 'Criar Escala'}
          </Button>
        )}
      </ModalFooter>
    </Modal>
  );
}
