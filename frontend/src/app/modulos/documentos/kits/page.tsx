'use client';

import { Package, Plus, Search, FileText, Copy, Edit, Trash2, ChevronRight, CheckCircle, AlertCircle } from 'lucide-react';
import { useState, useMemo } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  KIT_TYPE_LABELS,
} from '@/types/generated/ged/conectaPROMóduloGED.schemas';
import type {
  DocumentKitResponse,
  DocumentKitCreate,
  DocumentKitUpdate,
  KitType,
} from '@/types/generated/document-kits';
import { useToast } from '@/components/ui/use-toast';
import {
  useListKits as useListDocumentKits,
  useCreateKit as useCreateDocumentKit,
  useUpdateKit as useUpdateDocumentKit,
  useDeleteKit as useDeleteDocumentKit,
} from '@/hooks/document-kits/useDocumentKits';
import { useCondominio } from '@/contexts/CondominioContext';

// Categorias baseadas nos tipos validos do backend
const CATEGORIES = Object.entries(KIT_TYPE_LABELS).map(([value, label]) => ({
  value,
  label,
}));

export default function KitsPage() {
  const { condominioId: DEFAULT_CONDOMINIO_ID } = useCondominio();
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [selectedKit, setSelectedKit] = useState<DocumentKitResponse | null>(null);
  const [editingKit, setEditingKit] = useState<DocumentKitResponse | null>(null);
  const { toast } = useToast();

  // Form state - usando nomes do backend
  const [formData, setFormData] = useState({
    nome: '',
    descricao: '',
    tipo: 'ADMISSAO' as KitType,
  });

  // Hooks React Query - useListKits espera ListKitsParams (objeto)
  const { data: kitsData, isLoading: loading, error: queryError } = useListDocumentKits({
    condominio_id: DEFAULT_CONDOMINIO_ID,
    tipo: categoryFilter !== 'all' ? (categoryFilter as KitType) : undefined,
  });

  const createMutation = useCreateDocumentKit();
  const updateMutation = useUpdateDocumentKit();
  const deleteMutation = useDeleteDocumentKit();

  const kits = useMemo(() => kitsData?.items ?? [], [kitsData?.items]);
  const error = queryError ? 'Erro ao carregar kits. Tente novamente.' : null;

  // Filtrar kits por busca (categoria ja filtrada na API)
  const filteredKits = useMemo(() => {
    return kits.filter((kit) => {
      if (!search) return true;
      const matchesSearch = kit.nome.toLowerCase().includes(search.toLowerCase()) ||
        (kit.descricao ?? '').toLowerCase().includes(search.toLowerCase());
      return matchesSearch;
    });
  }, [kits, search]);

  // Criar novo kit
  const handleCreateKit = () => {
    if (!formData.nome.trim()) {
      toast({
        title: 'Erro',
        description: 'Nome do kit e obrigatorio',
        variant: 'destructive',
      });
      return;
    }

    const payload: DocumentKitCreate = {
      codigo: `KIT-${new Date().getFullYear()}-${Math.floor(Math.random() * 10000).toString().padStart(4, '0')}`,
      nome: formData.nome.trim(),
      descricao: formData.descricao.trim() || undefined,
      tipo: formData.tipo,
      condominio_id: DEFAULT_CONDOMINIO_ID,
    };

    createMutation.mutate(payload, {
      onSuccess: () => {
        setDialogOpen(false);
        setFormData({ nome: '', descricao: '', tipo: 'ADMISSAO' as KitType });
      },
    });
  };

  // Ver detalhes do kit
  const handleViewKit = (kit: DocumentKitResponse) => {
    setSelectedKit(kit);
  };

  // Abrir modal de edicao
  const handleEditKit = (kit: DocumentKitResponse) => {
    setEditingKit(kit);
    setFormData({
      nome: kit.nome,
      descricao: kit.descricao ?? '',
      tipo: kit.tipo,
    });
    setSelectedKit(null);
  };

  // Salvar edicao do kit
  const handleSaveKit = () => {
    if (!editingKit || !formData.nome.trim()) {
      toast({
        title: 'Erro',
        description: 'Nome do kit e obrigatorio',
        variant: 'destructive',
      });
      return;
    }

    const updateData: DocumentKitUpdate = {
      nome: formData.nome.trim(),
      descricao: formData.descricao.trim() || undefined,
      tipo: formData.tipo,
    };

    updateMutation.mutate(
      {
        kit_id: editingKit.id,
        data: updateData,
        condominio_id: editingKit.condominio_id,
      },
      {
        onSuccess: () => {
          setEditingKit(null);
          setFormData({ nome: '', descricao: '', tipo: 'ADMISSAO' as KitType });
        },
      }
    );
  };

  // Excluir kit
  const handleDeleteKit = (kit: DocumentKitResponse) => {
    if (!confirm(`Tem certeza que deseja excluir o kit "${kit.nome}"?`)) {
      return;
    }

    deleteMutation.mutate(
      { kit_id: kit.id, condominio_id: kit.condominio_id },
      {
        onSuccess: () => {
          setSelectedKit(null);
        },
      }
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold">Kits de Documentos</h1>
          <p className="text-muted-foreground">
            Conjuntos padronizados de documentos para processos especificos
          </p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="h-4 w-4 mr-2" />
              Novo Kit
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Criar Novo Kit</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="name">Nome do Kit</Label>
                <Input
                  id="name"
                  value={formData.nome}
                  onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
                  placeholder="Ex: Kit Admissão de Funcionario"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="description">Descricao</Label>
                <Textarea
                  id="description"
                  value={formData.descricao}
                  onChange={(e) => setFormData({ ...formData, descricao: e.target.value })}
                  placeholder="Descreva o proposito deste kit"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="category">Categoria</Label>
                <Select
                  value={formData.tipo}
                  onValueChange={(value) => setFormData({ ...formData, tipo: value as KitType })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione a categoria" />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIES.map((cat) => (
                      <SelectItem key={cat.value} value={cat.value}>
                        {cat.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setDialogOpen(false)} disabled={createMutation.isPending}>
                Cancelar
              </Button>
              <Button onClick={handleCreateKit} disabled={!formData.nome || createMutation.isPending}>
                {createMutation.isPending ? 'Criando...' : 'Criar Kit'}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      </div>

      {/* Search and Filters */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar kits..."
            className="pl-10"
          />
        </div>
        <Select value={categoryFilter} onValueChange={setCategoryFilter} aria-label="Category Filter">
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Todas as categorias" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todas as categorias</SelectItem>
            {CATEGORIES.map((cat) => (
              <SelectItem key={cat.value} value={cat.value}>
                {cat.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Erro */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <div className="flex-1">
            <p className="text-sm text-destructive">{error}</p>
          </div>
        </div>
      )}

      {/* Kits Grid */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      ) : !error && filteredKits.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Package className="h-16 w-16 mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium">Nenhum kit encontrado</h3>
          <p className="mt-2">
            {search || categoryFilter !== 'all' ? 'Tente ajustar os filtros' : 'Crie seu primeiro kit de documentos'}
          </p>
          {!search && categoryFilter === 'all' && (
            <Button className="mt-4" onClick={() => setDialogOpen(true)}>
              <Plus className="h-4 w-4 mr-2" />
              Criar Kit
            </Button>
          )}
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {filteredKits.map((kit) => (
            <Card
              key={kit.id}
              className="hover:bg-accent/50 transition-colors cursor-pointer"
              onClick={() => handleViewKit(kit)}
            >
              <CardContent className="pt-6">
                <div className="flex items-start gap-4">
                  <div className="p-3 rounded-lg bg-blue-100 dark:bg-blue-900">
                    <Package className="h-8 w-8 text-blue-600 dark:text-blue-300" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <h3 className="font-semibold truncate">{kit.nome}</h3>
                      {kit.status === 'ATIVO' && (
                        <Badge variant="secondary" className="text-xs bg-green-100 text-green-800">
                          Ativo
                        </Badge>
                      )}
                    </div>
                    {kit.codigo && (
                      <code className="text-xs text-muted-foreground">{kit.codigo}</code>
                    )}
                    <p className="text-sm text-muted-foreground line-clamp-2 mt-1">
                      {kit.descricao ?? 'Sem descricao'}
                    </p>
                    <div className="flex items-center gap-3 mt-3 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <FileText className="h-3 w-3" />
                        {kit.total_itens ?? 0} documentos
                      </span>
                      <span className="flex items-center gap-1">
                        <Copy className="h-3 w-3" />
                        {kit.uso_count ?? 0} usos
                      </span>
                    </div>
                    <div className="mt-2">
                      <Badge variant="outline" className="text-xs">
                        {CATEGORIES.find((c) => c.value === kit.tipo)?.label ?? kit.tipo}
                      </Badge>
                    </div>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Kit Details Dialog */}
      {selectedKit && (
        <Dialog open={!!selectedKit} onOpenChange={() => setSelectedKit(null)}>
          <DialogContent className="max-w-2xl">
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <Package className="h-5 w-5" />
                {selectedKit.nome}
              </DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <p className="text-muted-foreground">{selectedKit.descricao}</p>

              <div className="flex gap-4 text-sm">
                <Badge variant="outline">
                  {CATEGORIES.find((c) => c.value === selectedKit.tipo)?.label}
                </Badge>
                <span className="text-muted-foreground">
                  {selectedKit.total_itens ?? 0} documentos
                </span>
                <span className="text-muted-foreground">
                  {selectedKit.uso_count ?? 0} usos
                </span>
              </div>

              <div className="border rounded-lg">
                <div className="p-3 bg-muted font-medium text-sm">
                  Documentos do Kit
                </div>
                {selectedKit.total_itens === 0 ? (
                  <div className="p-4 text-center text-muted-foreground text-sm">
                    Nenhum documento adicionado ao kit ainda.
                  </div>
                ) : (
                  <div className="p-4 text-center text-muted-foreground text-sm">
                    {selectedKit.total_itens} documento(s) configurado(s).
                  </div>
                )}
              </div>
            </div>
            <div className="flex justify-between">
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleEditKit(selectedKit)}
                >
                  <Edit className="h-4 w-4 mr-2" />
                  Editar
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="text-red-600 hover:text-red-700"
                  onClick={() => handleDeleteKit(selectedKit)}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 className="h-4 w-4 mr-2" />
                  {deleteMutation.isPending ? 'Excluindo...' : 'Excluir'}
                </Button>
              </div>
              <Button onClick={() => setSelectedKit(null)}>
                <CheckCircle className="h-4 w-4 mr-2" />
                Fechar
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Modal de Edição */}
      {editingKit && (
        <Dialog open={!!editingKit} onOpenChange={() => setEditingKit(null)}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Editar Kit: {editingKit.nome}</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <div className="space-y-2">
                <Label htmlFor="edit-name">Nome do Kit</Label>
                <Input
                  id="edit-name"
                  value={formData.nome}
                  onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
                  placeholder="Ex: Kit Admissão de Funcionario"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="edit-description">Descricao</Label>
                <Textarea
                  id="edit-description"
                  value={formData.descricao}
                  onChange={(e) => setFormData({ ...formData, descricao: e.target.value })}
                  placeholder="Descreva o proposito deste kit"
                />
              </div>
              {editingKit.codigo && (
                <div className="text-sm text-muted-foreground">
                  Codigo: <code className="bg-muted px-1.5 py-0.5 rounded">{editingKit.codigo}</code>
                </div>
              )}
            </div>
            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => setEditingKit(null)} disabled={updateMutation.isPending}>
                Cancelar
              </Button>
              <Button onClick={handleSaveKit} disabled={!formData.nome || updateMutation.isPending}>
                {updateMutation.isPending ? 'Salvando...' : 'Salvar Alteracoes'}
              </Button>
            </div>
          </DialogContent>
        </Dialog>
      )}

      {/* Info Card */}
      <Card>
        <CardHeader>
          <CardTitle className="text-lg flex items-center gap-2">
            <Package className="h-5 w-5" />
            Sobre Kits de Documentos
          </CardTitle>
        </CardHeader>
        <CardContent className="text-sm text-muted-foreground space-y-2">
          <p>
            Kits de documentos sao conjuntos padronizados que facilitam a organizacao
            e coleta de documentos para processos especificos.
          </p>
          <ul className="list-disc list-inside space-y-1">
            <li>Crie kits personalizados para cada tipo de processo</li>
            <li>Defina documentos obrigatorios e opcionais</li>
            <li>Acompanhe o progresso de coleta de documentos</li>
            <li>Reutilize kits em multiplos processos</li>
          </ul>
        </CardContent>
      </Card>
    </div>
  );
}
