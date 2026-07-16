'use client';

import { X, Plus, Tag, Hash, Search } from 'lucide-react';
import { msgFromDetail } from '@/lib/string';
import { useState, useEffect } from 'react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { toast } from 'sonner';
import { documentTagService } from '@/services/ged';
import type { DocumentTagResponse } from '@/types/generated/ged/schemas/documentTagResponse';
import type { TagType } from '@/types/generated/ged/schemas/tagType';

interface DocumentTagManagerProps {
  documentId?: string;
  selectedTags?: DocumentTagResponse[];
  open: boolean;
  onClose: () => void;
  onTagsUpdated?: (tags: DocumentTagResponse[]) => void;
}

const TAG_COLORS = [
  { value: '#EF4444', label: 'Vermelho' },
  { value: '#F97316', label: 'Laranja' },
  { value: '#EAB308', label: 'Amarelo' },
  { value: '#22C55E', label: 'Verde' },
  { value: '#3B82F6', label: 'Azul' },
  { value: '#6366F1', label: 'Índigo' },
  { value: '#A855F7', label: 'Roxo' },
  { value: '#EC4899', label: 'Rosa' },
  { value: '#6B7280', label: 'Cinza' },
];

const TAG_TYPES: { value: TagType; label: string }[] = [
  { value: 'sistema', label: 'Sistema' },
  { value: 'categoria', label: 'Categoria' },
  { value: 'projeto', label: 'Projeto' },
  { value: 'cliente', label: 'Cliente' },
  { value: 'departamento', label: 'Departamento' },
  { value: 'status', label: 'Status' },
  { value: 'prioridade', label: 'Prioridade' },
  { value: 'usuario', label: 'Usuário' },
];

export function DocumentTagManager({
  documentId,
  selectedTags = [],
  open,
  onClose,
  onTagsUpdated,
}: DocumentTagManagerProps) {
  const [allTags, setAllTags] = useState<DocumentTagResponse[]>([]);
  const [documentTags, setDocumentTags] = useState<DocumentTagResponse[]>(selectedTags);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);

  // Form state
  const [newTagName, setNewTagName] = useState('');
  const [newTagDescription, setNewTagDescription] = useState('');
  const [newTagType, setNewTagType] = useState<TagType>('usuario');
  const [newTagColor, setNewTagColor] = useState('#6B7280');

  useEffect(() => {
    if (open) {
      loadTags();
      if (documentId) {
        loadDocumentTags();
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps -- Intentional deps
  }, [open, documentId]);

  const loadTags = async () => {
    setLoading(true);
    try {
      const response = await documentTagService.getTags();
      const items = Array.isArray(response) ? response : (response.items ?? []);
      setAllTags(items);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error('Erro ao carregar tags', {
        description: msgFromDetail(err.response?.data?.detail) || 'Erro desconhecido',
      });
    } finally {
      setLoading(false);
    }
  };

  const loadDocumentTags = async () => {
    if (!documentId) return;
    try {
      const response = await documentTagService.getTags();
      const items: DocumentTagResponse[] = Array.isArray(response) ? response : (response.items ?? []);
      setDocumentTags(items);
    } catch (error: unknown) {
      toast.error('Erro ao carregar tags do documento');
    }
  };

  const handleCreateTag = async () => {
    if (!newTagName.trim()) {
      toast.error('Nome da tag é obrigatório');
      return;
    }

    try {
      const newTag = await documentTagService.createTag({
        name: newTagName,
        description: newTagDescription || undefined,
        tag_type: newTagType,
        color: newTagColor,
      });

      toast.success('Tag criada com sucesso');
      setAllTags([...allTags, newTag]);
      setNewTagName('');
      setNewTagDescription('');
      setNewTagType('usuario');
      setNewTagColor('#6B7280');
      setShowCreateForm(false);
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error('Erro ao criar tag', {
        description: msgFromDetail(err.response?.data?.detail) || 'Erro desconhecido',
      });
    }
  };

  const handleAddTag = async (tag: DocumentTagResponse) => {
    if (!documentId) {
      // Modo seleção apenas
      setDocumentTags([...documentTags, tag]);
      onTagsUpdated?.([...documentTags, tag]);
      return;
    }

    try {
      await documentTagService.addTagToDocument(documentId, tag.id);
      setDocumentTags([...documentTags, tag]);
      onTagsUpdated?.([...documentTags, tag]);
      toast.success('Tag adicionada');
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error('Erro ao adicionar tag', {
        description: msgFromDetail(err.response?.data?.detail) || 'Erro desconhecido',
      });
    }
  };

  const handleRemoveTag = async (tag: DocumentTagResponse) => {
    if (!documentId) {
      // Modo seleção apenas
      const updated = documentTags.filter((t) => t.id !== tag.id);
      setDocumentTags(updated);
      onTagsUpdated?.(updated);
      return;
    }

    try {
      await documentTagService.removeTagFromDocument(documentId, tag.id);
      const updated = documentTags.filter((t) => t.id !== tag.id);
      setDocumentTags(updated);
      onTagsUpdated?.(updated);
      toast.success('Tag removida');
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error('Erro ao remover tag', {
        description: msgFromDetail(err.response?.data?.detail) || 'Erro desconhecido',
      });
    }
  };

  const filteredTags = allTags.filter(
    (tag) =>
      tag.name.toLowerCase().includes(search.toLowerCase()) &&
      !documentTags.some((dt) => dt.id === tag.id)
  );

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Gerenciar Tags</DialogTitle>
          <DialogDescription>
            Adicione ou remova tags para organizar seus documentos
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Tags selecionadas */}
          <div>
            <Label>Tags do Documento</Label>
            <div className="flex flex-wrap gap-2 mt-2 p-3 border rounded-lg min-h-[60px]">
              {documentTags.length === 0 ? (
                <p className="text-sm text-gray-400">Nenhuma tag selecionada</p>
              ) : (
                documentTags.map((tag) => (
                  <Badge
                    key={tag.id}
                    style={{ backgroundColor: tag.color }}
                    className="flex items-center gap-1"
                  >
                    <Hash className="h-3 w-3" />
                    {tag.name}
                    <button
                      onClick={() => handleRemoveTag(tag)}
                      className="ml-1 hover:bg-white/20 rounded-full p-0.5"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </Badge>
                ))
              )}
            </div>
          </div>

          {/* Buscar tags existentes */}
          <div>
            <Label>Adicionar Tags Existentes</Label>
            <div className="relative mt-2">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
              <Input
                placeholder="Buscar tags..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>

            <div className="flex flex-wrap gap-2 mt-3 max-h-40 overflow-y-auto p-2 border rounded-lg">
              {loading ? (
                <p className="text-sm text-gray-400">Carregando...</p>
              ) : filteredTags.length === 0 ? (
                <p className="text-sm text-gray-400">
                  {search ? 'Nenhuma tag encontrada' : 'Todas as tags já foram adicionadas'}
                </p>
              ) : (
                filteredTags.map((tag) => (
                  <button
                    key={tag.id}
                    onClick={() => handleAddTag(tag)}
                    className="transition-transform hover:scale-105"
                  >
                    <Badge style={{ backgroundColor: tag.color }} className="cursor-pointer">
                      <Hash className="h-3 w-3 mr-1" />
                      {tag.name}
                      {tag.usage_count > 0 && (
                        <span className="ml-1 opacity-75">({tag.usage_count})</span>
                      )}
                    </Badge>
                  </button>
                ))
              )}
            </div>
          </div>

          {/* Criar nova tag */}
          {showCreateForm ? (
            <div className="space-y-3 p-4 border rounded-lg bg-gray-50">
              <div className="flex items-center justify-between">
                <Label className="font-semibold">Criar Nova Tag</Label>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowCreateForm(false)}
                >
                  <X className="h-4 w-4" />
                </Button>
              </div>

              <div>
                <Label>Nome *</Label>
                <Input
                  placeholder="Nome da tag"
                  value={newTagName}
                  onChange={(e) => setNewTagName(e.target.value)}
                  maxLength={50}
                />
              </div>

              <div>
                <Label>Descrição</Label>
                <Textarea
                  placeholder="Descrição opcional"
                  value={newTagDescription}
                  onChange={(e) => setNewTagDescription(e.target.value)}
                  maxLength={500}
                  rows={2}
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label>Tipo</Label>
                  <Select value={newTagType} onValueChange={(v) => setNewTagType(v as TagType)}>
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {TAG_TYPES.map((type) => (
                        <SelectItem key={type.value} value={type.value}>
                          {type.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>

                <div>
                  <Label>Cor</Label>
                  <Select value={newTagColor} onValueChange={setNewTagColor} aria-label="New Tag Color">
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {TAG_COLORS.map((color) => (
                        <SelectItem key={color.value} value={color.value}>
                          <div className="flex items-center gap-2">
                            <div
                              className="w-4 h-4 rounded-full"
                              style={{ backgroundColor: color.value }}
                            />
                            {color.label}
                          </div>
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Button onClick={handleCreateTag} className="w-full">
                <Tag className="h-4 w-4 mr-2" />
                Criar Tag
              </Button>
            </div>
          ) : (
            <Button
              variant="outline"
              onClick={() => setShowCreateForm(true)}
              className="w-full"
            >
              <Plus className="h-4 w-4 mr-2" />
              Criar Nova Tag
            </Button>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-4">
          <Button variant="outline" onClick={onClose}>
            Fechar
          </Button>
          <Button onClick={onClose}>Concluir</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
