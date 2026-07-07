'use client';

import { Plus, Search, FileText, Loader, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import { useRouter } from 'next/navigation';
;
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConfirmModal } from '@/components/ui/modal';
import { TemplateCard } from './TemplateCard';
import { CreateTemplateDialog } from './CreateTemplateDialog';
import { ApplyTemplateDialog } from './ApplyTemplateDialog';
import { EditTemplateDialog } from './EditTemplateDialog';
import { useTemplates, useTemplateOperations } from '@/hooks/useScaleTemplates';
import { useScales } from '@/hooks/useScales';
import { usePosts } from '@/hooks/usePosts';
import type {
  ScaleTemplate,
  ScaleTemplateCreate,
  ScaleTemplateApply,
  ScaleTemplateUpdate,
} from '@/types/operacional';

// Loading skeleton component - definido fora do componente para evitar recriação durante render
const SkeletonCard = () => (
  <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6 animate-pulse">
    <div className="h-6 bg-[hsl(var(--muted))] rounded w-3/4 mb-2" />
    <div className="h-4 bg-[hsl(var(--muted))] rounded w-1/2 mb-4" />
    <div className="h-8 bg-[hsl(var(--muted))] rounded w-1/3 mb-4" />
    <div className="grid grid-cols-3 gap-3 mb-4">
      <div className="h-20 bg-[hsl(var(--muted))] rounded" />
      <div className="h-20 bg-[hsl(var(--muted))] rounded" />
      <div className="h-20 bg-[hsl(var(--muted))] rounded" />
    </div>
    <div className="h-10 bg-[hsl(var(--muted))] rounded" />
  </div>
);

export function TemplateManager() {
  const router = useRouter();
  const { templates, total, isLoading, refresh } = useTemplates();
  const { scales } = useScales(1, 100);
  const { posts } = usePosts({ initialPageSize: 100 });
  const {
    createTemplate,
    updateTemplate,
    deleteTemplate,
    applyTemplate,
    previewTemplate,
    isLoading: operationLoading,
  } = useTemplateOperations();

  // Modal states
  const [showCreateDialog, setShowCreateDialog] = useState(false);
  const [showEditDialog, setShowEditDialog] = useState(false);
  const [showApplyDialog, setShowApplyDialog] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [selectedTemplate, setSelectedTemplate] = useState<ScaleTemplate | null>(null);

  // Filter states
  const [searchTerm, setSearchTerm] = useState('');

  // Handlers
  const handleCreate = async (data: ScaleTemplateCreate) => {
    const result = await createTemplate(data);
    if (result) {
      setShowCreateDialog(false);
      refresh();
    }
  };

  const handleUse = (template: ScaleTemplate) => {
    setSelectedTemplate(template);
    setShowApplyDialog(true);
  };

  const handleEdit = (template: ScaleTemplate) => {
    setSelectedTemplate(template);
    setShowEditDialog(true);
  };

  const handleEditSubmit = async (id: string, data: ScaleTemplateUpdate) => {
    const result = await updateTemplate(id, data);
    if (result) {
      setShowEditDialog(false);
      setSelectedTemplate(null);
      refresh();
    }
  };

  const handleDeleteClick = (template: ScaleTemplate) => {
    setSelectedTemplate(template);
    setShowDeleteModal(true);
  };

  const handleDeleteConfirm = async () => {
    if (!selectedTemplate) return;
    const success = await deleteTemplate(selectedTemplate.id);
    if (success) {
      setShowDeleteModal(false);
      setSelectedTemplate(null);
      refresh();
    }
  };

  const handleApply = async (data: ScaleTemplateApply) => {
    if (!selectedTemplate) return null;
    const result = await applyTemplate(selectedTemplate.id, data);
    if (result) {
      setShowApplyDialog(false);
      setSelectedTemplate(null);
      // Redirect to the new scale
      router.push(`/modulos/operacional/escalas/${result.id}`);
    }
    return result;
  };

  const handlePreview = async (data: ScaleTemplateApply) => {
    if (!selectedTemplate) return null;
    return await previewTemplate(selectedTemplate.id, data);
  };

  // Filter templates
  const filteredTemplates = templates.filter((template) => {
    if (!searchTerm) return true;
    const search = searchTerm.toLowerCase();
    return (
      template.name.toLowerCase().includes(search) ||
      template.description?.toLowerCase().includes(search) ||
      template.post_name?.toLowerCase().includes(search)
    );
  });

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">
            Templates de Escalas
          </h2>
          <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1">
            {total} {total === 1 ? 'template disponível' : 'templates disponíveis'}
          </p>
        </div>
        <Button onClick={() => setShowCreateDialog(true)}>
          <Plus className="w-4 h-4 mr-2" />
          Novo Template
        </Button>
      </div>

      {/* Search */}
      <div className="relative">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[hsl(var(--muted-foreground))]" />
        <Input
          placeholder="Buscar templates..."
          className="pl-9"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
        />
      </div>

      {/* Templates Grid */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          <SkeletonCard />
          <SkeletonCard />
          <SkeletonCard />
        </div>
      ) : filteredTemplates.length === 0 ? (
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-12 text-center">
          {searchTerm ? (
            <>
              <Search className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))] mb-2">
                Nenhum template encontrado
              </h3>
              <p className="text-sm text-[hsl(var(--muted-foreground))] mb-4">
                Tente ajustar sua busca
              </p>
            </>
          ) : (
            <>
              <FileText className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))] mb-2">
                Nenhum template criado ainda
              </h3>
              <p className="text-sm text-[hsl(var(--muted-foreground))] mb-4">
                Crie templates a partir de escalas existentes para reutilizar padrões
              </p>
              <Button onClick={() => setShowCreateDialog(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Criar Primeiro Template
              </Button>
            </>
          )}
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {filteredTemplates.map((template) => (
            <TemplateCard
              key={template.id}
              template={template}
              onUse={handleUse}
              onEdit={handleEdit}
              onDelete={handleDeleteClick}
            />
          ))}
        </div>
      )}

      {/* Create Template Dialog */}
      <CreateTemplateDialog
        isOpen={showCreateDialog}
        onClose={() => setShowCreateDialog(false)}
        scales={scales}
        onSubmit={handleCreate}
        isLoading={operationLoading}
      />

      {/* Edit Template Dialog */}
      <EditTemplateDialog
        isOpen={showEditDialog}
        onClose={() => {
          setShowEditDialog(false);
          setSelectedTemplate(null);
        }}
        template={selectedTemplate}
        onSubmit={handleEditSubmit}
        isLoading={operationLoading}
      />

      {/* Apply Template Dialog */}
      <ApplyTemplateDialog
        isOpen={showApplyDialog}
        onClose={() => {
          setShowApplyDialog(false);
          setSelectedTemplate(null);
        }}
        template={selectedTemplate}
        posts={posts}
        onSubmit={handleApply}
        onPreview={handlePreview}
        isLoading={operationLoading}
      />

      {/* Delete Confirmation Modal */}
      <ConfirmModal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setSelectedTemplate(null);
        }}
        onConfirm={handleDeleteConfirm}
        title="Excluir Template"
        message={`Tem certeza que deseja excluir o template "${selectedTemplate?.name}"? Esta ação não pode ser desfeita.`}
        confirmText="Excluir"
        variant="danger"
        isLoading={operationLoading}
      />
    </div>
  );
}
