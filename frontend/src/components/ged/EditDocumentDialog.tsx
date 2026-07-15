'use client';

import { FileText, Calendar, Lock, CheckCircle, FileSignature } from 'lucide-react';
import { msgFromDetail } from '@/lib/string';
import { useEffect } from 'react';
import { useForm, Controller } from 'react-hook-form';
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
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { toast } from 'sonner';
import {
  type DocumentResponse,
  type DocumentType,
  type DocumentCategory,
  type DocumentConfidentiality,
  DOCUMENT_TYPES,
  DOCUMENT_CATEGORIES,
} from '@/types/generated/ged/conectaPROMóduloGED.schemas';
import { useUpdateDocument } from '@/hooks/ged/useGedDocuments';

const CONFIDENTIALITY_LEVELS: {
  value: DocumentConfidentiality;
  label: string;
  description: string;
}[] = [
  { value: 'publico', label: 'Público', description: 'Acesso irrestrito' },
  { value: 'interno', label: 'Interno', description: 'Apenas colaboradores' },
  { value: 'confidencial', label: 'Confidencial', description: 'Acesso restrito' },
  { value: 'restrito', label: 'Restrito', description: 'Apenas autorizados' },
  { value: 'secreto', label: 'Secreto', description: 'Máxima segurança' },
];

const DOCUMENT_TYPE_OPTIONS = Object.entries(DOCUMENT_TYPES).map(([key, value]) => ({
  value,
  label: key.charAt(0).toUpperCase() + key.slice(1).replace(/_/g, ' '),
}));

const DOCUMENT_CATEGORY_OPTIONS = Object.entries(DOCUMENT_CATEGORIES).map(([key, value]) => ({
  value,
  label: key.charAt(0).toUpperCase() + key.slice(1),
}));

interface FormData {
  title: string;
  description: string;
  document_type: DocumentType;
  category: DocumentCategory;
  confidentiality: DocumentConfidentiality;
  is_public: boolean;
  valid_from: string;
  valid_until: string;
  is_perpetual: boolean;
  requires_approval: boolean;
  requires_signature: boolean;
  signature_deadline: string;
  external_reference: string;
}

interface EditDocumentDialogProps {
  document: DocumentResponse | null;
  open: boolean;
  onClose: () => void;
  onUpdated?: () => void;
}

export function EditDocumentDialog({
  document,
  open,
  onClose,
  onUpdated,
}: EditDocumentDialogProps) {
  const updateMutation = useUpdateDocument();

  const {
    register,
    handleSubmit,
    control,
    reset,
    watch,
    formState: { isSubmitting },
  } = useForm<FormData>({
    defaultValues: {
      title: '',
      description: '',
      document_type: DOCUMENT_TYPES.outro,
      category: DOCUMENT_CATEGORIES.outro,
      confidentiality: 'interno',
      is_public: false,
      valid_from: '',
      valid_until: '',
      is_perpetual: false,
      requires_approval: false,
      requires_signature: false,
      signature_deadline: '',
      external_reference: '',
    },
  });

  const isPerpetual = watch('is_perpetual');
  const requiresSignature = watch('requires_signature');
  const requiresApproval = watch('requires_approval');
  const confidentiality = watch('confidentiality');
  const validUntil = watch('valid_until');

  useEffect(() => {
    if (document) {
      reset({
        title: document.title,
        description: document.description || '',
        document_type: document.document_type,
        category: document.category,
        confidentiality: document.confidentiality,
        is_public: document.is_public,
        valid_from: document.valid_from || '',
        valid_until: document.valid_until || '',
        is_perpetual: document.is_perpetual,
        requires_approval: document.requires_approval,
        requires_signature: document.requires_signature,
        signature_deadline: document.signature_deadline || '',
        external_reference: document.external_reference || '',
      });
    }
  }, [document, reset]);

  const onFormSubmit = async (data: FormData) => {
    if (!document) return;
    try {
      await updateMutation.mutateAsync({
        documentId: document.id,
        data,
      });
      toast.success('Documento atualizado com sucesso');
      onUpdated?.();
      onClose();
    } catch (error: unknown) {
      const err = error as { response?: { data?: { detail?: string } } };
      toast.error('Erro ao atualizar documento', {
        description: err.response?.msgFromDetail(data?.detail) || 'Erro desconhecido',
      });
    }
  };

  return (
    <Dialog open={open} onOpenChange={onClose}>
      <DialogContent className="max-w-3xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Editar Documento</DialogTitle>
          <DialogDescription>
            Atualize as informações e configurações do documento
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit(onFormSubmit)}>
          <Tabs defaultValue="basic" className="w-full">
            <TabsList className="grid w-full grid-cols-4">
              <TabsTrigger value="basic">
                <FileText className="h-4 w-4 mr-1" />
                Básico
              </TabsTrigger>
              <TabsTrigger value="validity">
                <Calendar className="h-4 w-4 mr-1" />
                Validade
              </TabsTrigger>
              <TabsTrigger value="security">
                <Lock className="h-4 w-4 mr-1" />
                Segurança
              </TabsTrigger>
              <TabsTrigger value="workflow">
                <CheckCircle className="h-4 w-4 mr-1" />
                Workflow
              </TabsTrigger>
            </TabsList>

            {/* Básico */}
            <TabsContent value="basic" className="space-y-4">
              <div>
                <Label>Título *</Label>
                <Input
                  aria-label="Título do documento"
                  maxLength={255}
                  {...register('title')}
                />
              </div>

              <div>
                <Label>Descrição</Label>
                <Textarea
                  maxLength={5000}
                  rows={4}
                  aria-label="Descrição do documento"
                  {...register('description')}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <Label>Tipo de Documento</Label>
                  <Controller
                    name="document_type"
                    control={control}
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {DOCUMENT_TYPE_OPTIONS.map((type) => (
                            <SelectItem key={type.value} value={type.value}>
                              {type.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                </div>

                <div>
                  <Label>Categoria</Label>
                  <Controller
                    name="category"
                    control={control}
                    render={({ field }) => (
                      <Select value={field.value} onValueChange={field.onChange}>
                        <SelectTrigger>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {DOCUMENT_CATEGORY_OPTIONS.map((cat) => (
                            <SelectItem key={cat.value} value={cat.value}>
                              {cat.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    )}
                  />
                </div>
              </div>

              <div>
                <Label>Referência Externa</Label>
                <Input
                  placeholder="Código ou referência externa"
                  maxLength={100}
                  aria-label="Referência externa"
                  {...register('external_reference')}
                />
              </div>
            </TabsContent>

            {/* Validade */}
            <TabsContent value="validity" className="space-y-4">
              <div className="flex items-center space-x-2">
                <Controller
                  name="is_perpetual"
                  control={control}
                  render={({ field }) => (
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  )}
                />
                <div>
                  <Label>Documento Perpétuo</Label>
                  <p className="text-sm text-gray-500">Sem data de expiração</p>
                </div>
              </div>

              {!isPerpetual && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <Label>Válido a partir de</Label>
                    <Input type="date" aria-label="Válido a partir de" {...register('valid_from')} />
                  </div>

                  <div>
                    <Label>Válido até</Label>
                    <Input type="date" aria-label="Válido até" {...register('valid_until')} />
                  </div>
                </div>
              )}

              {validUntil && !isPerpetual && (
                <div className="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                  <p className="text-sm text-yellow-800">
                    <strong>Atenção:</strong> Este documento expirará em{' '}
                    {new Date(validUntil).toLocaleDateString('pt-BR')}
                  </p>
                </div>
              )}
            </TabsContent>

            {/* Segurança */}
            <TabsContent value="security" className="space-y-4">
              <div>
                <Label>Nível de Confidencialidade</Label>
                <Controller
                  name="confidentiality"
                  control={control}
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger>
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {CONFIDENTIALITY_LEVELS.map((level) => (
                          <SelectItem key={level.value} value={level.value}>
                            <div>
                              <div className="font-medium">{level.label}</div>
                              <div className="text-xs text-gray-500">{level.description}</div>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  )}
                />
              </div>

              <div className="flex items-center space-x-2">
                <Controller
                  name="is_public"
                  control={control}
                  render={({ field }) => (
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  )}
                />
                <div>
                  <Label>Documento Público</Label>
                  <p className="text-sm text-gray-500">
                    Visível para todos os usuários do sistema
                  </p>
                </div>
              </div>

              {confidentiality !== 'publico' && (
                <div className="p-4 bg-blue-50 border border-blue-200 rounded-lg">
                  <p className="text-sm text-blue-800">
                    <Lock className="h-4 w-4 inline mr-1" />
                    Acesso controlado conforme nível de confidencialidade
                  </p>
                </div>
              )}
            </TabsContent>

            {/* Workflow */}
            <TabsContent value="workflow" className="space-y-4">
              <div className="flex items-center space-x-2">
                <Controller
                  name="requires_approval"
                  control={control}
                  render={({ field }) => (
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  )}
                />
                <div>
                  <Label>Requer Aprovação</Label>
                  <p className="text-sm text-gray-500">
                    Documento precisa ser aprovado antes de ser publicado
                  </p>
                </div>
              </div>

              <div className="flex items-center space-x-2">
                <Controller
                  name="requires_signature"
                  control={control}
                  render={({ field }) => (
                    <Switch checked={field.value} onCheckedChange={field.onChange} />
                  )}
                />
                <div>
                  <Label>Requer Assinatura Digital</Label>
                  <p className="text-sm text-gray-500">
                    Documento precisa ser assinado digitalmente
                  </p>
                </div>
              </div>

              {requiresSignature && (
                <div>
                  <Label>Prazo para Assinatura</Label>
                  <Input
                    type="datetime-local"
                    aria-label="Prazo para assinatura"
                    {...register('signature_deadline')}
                  />
                </div>
              )}

              {(requiresApproval || requiresSignature) && (
                <div className="p-4 bg-purple-50 border border-purple-200 rounded-lg">
                  <p className="text-sm text-purple-800">
                    <FileSignature className="h-4 w-4 inline mr-1" />
                    Workflows ativos neste documento
                  </p>
                </div>
              )}
            </TabsContent>
          </Tabs>

          <div className="flex justify-end gap-2 mt-4">
            <Button type="button" variant="outline" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="submit" disabled={isSubmitting}>
              {isSubmitting ? 'Salvando...' : 'Salvar Alterações'}
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
