'use client';

import { X, Megaphone, Save, Loader2, AlertTriangle, Users, Calendar, FileText } from 'lucide-react';
import { useState, useEffect, useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAnnouncementMutations } from '@/hooks/useAnnouncements';
import type {
  Announcement,
  AnnouncementCreate,
  AnnouncementPriority,
  AnnouncementCategory,
  AnnouncementTargetType,
} from '@/lib/services/announcements';
import {
  ANNOUNCEMENT_PRIORITY_LABELS,
  ANNOUNCEMENT_CATEGORY_LABELS,
  ANNOUNCEMENT_TARGET_TYPE_LABELS,
} from '@/lib/services/announcements';

interface AnnouncementFormModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
  editData?: Announcement | null;
  // Template rápido: preenche o form ao abrir (só quando NÃO é edição)
  template?: { id: string; title: string; body: string; category: string; priority: string } | null;
}

// Default form data
const defaultFormData: AnnouncementCreate = {
  title: '',
  content: '',
  target_type: 'all',
  priority: 'normal',
  category: 'informativo',
  requires_acknowledgment: false,
};

// Form state factory
const createFormData = (editData?: Announcement | null): AnnouncementCreate => {
  if (!editData) return defaultFormData;

  return {
    title: editData.title,
    content: editData.content,
    target_type: editData.target_type,
    target_ids: editData.target_ids ?? undefined,
    target_roles: editData.target_roles ?? undefined,
    priority: editData.priority,
    category: editData.category,
    requires_acknowledgment: editData.requires_acknowledgment,
    publish_at: editData.publish_at ?? undefined,
    expires_at: editData.expires_at ?? undefined,
  };
};

export function AnnouncementFormModal({
  isOpen,
  onClose,
  onSuccess,
  editData,
  template,
}: AnnouncementFormModalProps) {
  const { createAnnouncement, updateAnnouncement, isLoading, error } = useAnnouncementMutations();

  const formKey = useMemo(() => {
    return editData?.id || (template ? `tpl-${template.id}` : 'new');
  }, [editData, template]);

  const [formData, setFormData] = useState<AnnouncementCreate>(defaultFormData);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      if (editData) {
        setFormData(createFormData(editData));
      } else if (template) {
        // Prefill a partir do template rápido (título/conteúdo/categoria/prioridade)
        setFormData({
          ...defaultFormData,
          title: template.title,
          content: template.body,
          category: template.category as AnnouncementCreate['category'],
          priority: template.priority as AnnouncementCreate['priority'],
        });
      } else {
        setFormData(defaultFormData);
      }
      setFormError(null);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- Intentional deps
  }, [isOpen, formKey]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setFormError(null);

    // Validation
    if (!formData.title.trim()) {
      setFormError('Titulo e obrigatorio');
      return;
    }
    if (formData.title.length < 3) {
      setFormError('Titulo deve ter pelo menos 3 caracteres');
      return;
    }
    if (!formData.content.trim()) {
      setFormError('Conteudo e obrigatorio');
      return;
    }
    if (formData.content.length < 10) {
      setFormError('Conteudo deve ter pelo menos 10 caracteres');
      return;
    }

    let result: Announcement | null = null;

    if (editData) {
      result = await updateAnnouncement(editData.id, formData);
    } else {
      result = await createAnnouncement(formData);
    }

    if (result) {
      onSuccess();
      onClose();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl shadow-xl m-4">
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center justify-between p-4 border-b border-[hsl(var(--border))] bg-[hsl(var(--card))]">
          <div className="flex items-center gap-2">
            <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
              <Megaphone className="w-5 h-5 text-blue-500" />
            </div>
            <div>
              <h2 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                {editData ? 'Editar Comunicado' : 'Novo Comunicado'}
              </h2>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                {editData ? 'Atualize as informacoes' : 'Preencha os dados do comunicado'}
              </p>
            </div>
          </div>
          <Button variant="ghost" size="sm" onClick={onClose}>
            <X className="w-4 h-4" />
          </Button>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="p-4 space-y-4">
          {/* Error */}
          {(formError || error) && (
            <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 text-red-500" />
              <p className="text-sm text-red-500">{formError || error}</p>
            </div>
          )}

          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">
              Titulo *
            </label>
            <Input
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="Digite o titulo do comunicado"
              maxLength={200}
            />
            <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
              {formData.title.length}/200 caracteres
            </p>
          </div>

          {/* Content */}
          <div>
            <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">
              Conteudo *
            </label>
            <textarea
              value={formData.content}
              onChange={(e) => setFormData({ ...formData, content: e.target.value })}
              placeholder="Digite o conteudo do comunicado..."
              rows={6}
              className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] resize-none focus:outline-none focus:ring-2 focus:ring-[hsl(var(--primary))]"
            />
          </div>

          {/* Row: Priority, Category */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">
                Prioridade
              </label>
              <select
                value={formData.priority}
                onChange={(e) =>
                  setFormData({ ...formData, priority: e.target.value as AnnouncementPriority })
                }
                className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))]"
              >
                {Object.entries(ANNOUNCEMENT_PRIORITY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">
                Categoria
              </label>
              <select
                value={formData.category}
                onChange={(e) =>
                  setFormData({ ...formData, category: e.target.value as AnnouncementCategory })
                }
                className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))]"
              >
                {Object.entries(ANNOUNCEMENT_CATEGORY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Target Type */}
          <div>
            <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">
              <Users className="w-4 h-4 inline mr-1" />
              Destinatarios
            </label>
            <select
              value={formData.target_type}
              onChange={(e) =>
                setFormData({ ...formData, target_type: e.target.value as AnnouncementTargetType })
              }
              className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))]"
            >
              {Object.entries(ANNOUNCEMENT_TARGET_TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>

          {/* Row: Publish At, Expires At */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">
                <Calendar className="w-4 h-4 inline mr-1" />
                Agendar Publicacao
              </label>
              <Input
                type="datetime-local"
                value={formData.publish_at?.slice(0, 16) || ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    publish_at: e.target.value ? new Date(e.target.value).toISOString() : undefined,
                  })
                }
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-[hsl(var(--foreground))] mb-1">
                Data de Expiracao
              </label>
              <Input
                type="datetime-local"
                value={formData.expires_at?.slice(0, 16) || ''}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    expires_at: e.target.value ? new Date(e.target.value).toISOString() : undefined,
                  })
                }
              />
            </div>
          </div>

          {/* Requires Acknowledgment */}
          <div className="flex items-center gap-2">
            <input
              type="checkbox"
              id="requires_acknowledgment"
              checked={formData.requires_acknowledgment}
              onChange={(e) =>
                setFormData({ ...formData, requires_acknowledgment: e.target.checked })
              }
              className="w-4 h-4 rounded border-[hsl(var(--border))]"
            />
            <label
              htmlFor="requires_acknowledgment"
              className="text-sm text-[hsl(var(--foreground))]"
            >
              Exigir confirmacao de leitura
            </label>
          </div>

          {/* Actions */}
          <div className="flex items-center justify-end gap-2 pt-4 border-t border-[hsl(var(--border))]">
            <Button type="button" variant="outline" onClick={onClose} disabled={isLoading}>
              Cancelar
            </Button>
            <Button type="submit" variant="primary" disabled={isLoading}>
              {isLoading ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  Salvando...
                </>
              ) : (
                <>
                  <Save className="w-4 h-4 mr-2" />
                  {editData ? 'Atualizar' : 'Salvar como Rascunho'}
                </>
              )}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
