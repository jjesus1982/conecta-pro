'use client';

import { AlertTriangle, ShieldAlert, MapPin, CheckCircle, Clock, Plus, RefreshCw, Search, Edit, Eye } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import {
  usePPRAStatistics,
  useRiskMappings,
  useRiskCategories,
  useCreateRiskMapping,
  useUpdateRiskMapping,
} from '@/hooks/health-occupational';

export default function RiscosPage() {
  const { data: stats, isLoading: statsLoading } = usePPRAStatistics();
  const { data: categories } = useRiskCategories();

  const [sectorFilter, setSectorFilter] = useState<string>('');
  const mappingsFilters = sectorFilter ? { setor: sectorFilter } : undefined;
  const { data: mappingsData, isLoading: mappingsLoading, error: mappingsError, refetch } = useRiskMappings(mappingsFilters);

  const createMapping = useCreateRiskMapping();
  const updateMapping = useUpdateRiskMapping();

  const [search, setSearch] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<any | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    setor: '',
    funcao: '',
    agente_risco: '',
    categoria: '',
    nivel_risco: '',
    fonte_geradora: '',
    meio_propagacao: '',
    medidas_existentes: '',
    observacoes: '',
  });

  const resetForm = () => {
    setFormData({
      setor: '',
      funcao: '',
      agente_risco: '',
      categoria: '',
      nivel_risco: '',
      fonte_geradora: '',
      meio_propagacao: '',
      medidas_existentes: '',
      observacoes: '',
    });
    setEditItem(null);
  };

  const openCreate = () => {
    resetForm();
    setDialogOpen(true);
  };

  const openEdit = (item: any) => {
    setEditItem(item);
    setFormData({
      setor: item.setor || '',
      funcao: item.funcao || '',
      agente_risco: item.agente_risco || '',
      categoria: item.categoria || '',
      nivel_risco: item.nivel_risco || '',
      fonte_geradora: item.fonte_geradora || '',
      meio_propagacao: item.meio_propagacao || '',
      medidas_existentes: item.medidas_existentes || '',
      observacoes: item.observacoes || '',
    });
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    if (!formData.setor || !formData.agente_risco || !formData.categoria) return;
    try {
      if (editItem) {
        await updateMapping.mutateAsync({ mappingId: editItem.id, data: formData as any });
        toast.success('Mapeamento atualizado com sucesso', { duration: 4000 });
      } else {
        await createMapping.mutateAsync(formData as any);
        toast.success('Mapeamento de risco cadastrado com sucesso', { duration: 4000 });
      }
      setDialogOpen(false);
      resetForm();
      refetch();
    } catch (error) {
      toast.error('Erro ao salvar mapeamento. Tente novamente.', { duration: 5000 });
    }
  };

  const mappingsList = Array.isArray(mappingsData) ? mappingsData : (mappingsData as any)?.items ?? [];
  const categoriesList = Array.isArray(categories) ? categories : (categories as any)?.items ?? [];

  const filteredMappings = search
    ? mappingsList.filter((m: any) =>
        (m.setor || '').toLowerCase().includes(search.toLowerCase()) ||
        (m.agente_risco || '').toLowerCase().includes(search.toLowerCase()) ||
        (m.funcao || '').toLowerCase().includes(search.toLowerCase())
      )
    : mappingsList;

  const getRiskBadge = (nivel: string) => {
    const map: Record<string, string> = {
      trivial: 'bg-green-100 text-green-800',
      toleravel: 'bg-blue-100 text-blue-800',
      moderado: 'bg-yellow-100 text-yellow-800',
      substancial: 'bg-orange-100 text-orange-800',
      intoleravel: 'bg-red-100 text-red-800',
      baixo: 'bg-green-100 text-green-800',
      medio: 'bg-yellow-100 text-yellow-800',
      alto: 'bg-orange-100 text-orange-800',
      critico: 'bg-red-100 text-red-800',
    };
    const labels: Record<string, string> = {
      trivial: 'Trivial',
      toleravel: 'Toleravel',
      moderado: 'Moderado',
      substancial: 'Substancial',
      intoleravel: 'Intoleravel',
      baixo: 'Baixo',
      medio: 'Medio',
      alto: 'Alto',
      critico: 'Critico',
    };
    return (
      <Badge className={map[nivel] || 'bg-gray-100 text-gray-800'}>
        {labels[nivel] || nivel || 'N/A'}
      </Badge>
    );
  };

  const getCategoryBadge = (categoria: string) => {
    const map: Record<string, string> = {
      fisico: 'bg-blue-100 text-blue-800',
      quimico: 'bg-purple-100 text-purple-800',
      biologico: 'bg-green-100 text-green-800',
      ergonomico: 'bg-orange-100 text-orange-800',
      acidente: 'bg-red-100 text-red-800',
    };
    const labels: Record<string, string> = {
      fisico: 'Fisico',
      quimico: 'Quimico',
      biologico: 'Biologico',
      ergonomico: 'Ergonomico',
      acidente: 'Acidente',
    };
    return (
      <Badge variant="outline" className={map[categoria] || ''}>
        {labels[categoria] || categoria || '-'}
      </Badge>
    );
  };

  const handleRefresh = async () => {
    try {
      await refetch();
      toast.success('Dados atualizados', { duration: 4000 });
    } catch {
      toast.error('Erro ao atualizar dados', { duration: 5000 });
    }
  };

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <AlertTriangle className="h-6 w-6" />
            Riscos Ocupacionais - PPRA/PGR
          </h1>
          <p className="text-muted-foreground">
            Mapeamento e gestao de riscos ocupacionais, medidas de controle e analise por setor conforme NR-9.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleRefresh} disabled={mappingsLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${mappingsLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Mapeamento
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Riscos</CardTitle>
            <ShieldAlert className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="text-2xl font-bold">{(stats as any)?.total_riscos_identificados ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Mapeamentos Ativos</CardTitle>
            <MapPin className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="text-2xl font-bold text-blue-600">{(stats as any)?.total_mapeamentos_ativos ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Riscos Alto Nível</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="text-2xl font-bold text-green-600">{(stats as any)?.riscos_alto_nivel ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Medidas Pendentes</CardTitle>
            <Clock className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="text-2xl font-bold text-orange-600">{(stats as any)?.medidas_pendentes ?? 0}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por setor, funcao ou agente de risco..."
                className="pl-10"
              />
            </div>
            <div>
              <Input
                value={sectorFilter}
                onChange={(e) => setSectorFilter(e.target.value)}
                placeholder="Filtrar por setor"
                className="w-[200px]"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {mappingsError && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar mapeamentos de riscos</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table - Risk Mappings */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mapeamento de Riscos</CardTitle>
          <CardDescription>
            Lista de riscos ocupacionais identificados e classificados por setor e funcao.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {mappingsLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : filteredMappings.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <AlertTriangle className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum registro encontrado</h3>
              <p className="mt-2">Tente ajustar os filtros ou crie um novo mapeamento de risco.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Setor</TableHead>
                  <TableHead>Função</TableHead>
                  <TableHead>Agente de Risco</TableHead>
                  <TableHead>Categoria</TableHead>
                  <TableHead>Nivel</TableHead>
                  <TableHead>Fonte Geradora</TableHead>
                  <TableHead className="w-[100px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredMappings.map((mapping: any) => (
                  <TableRow key={mapping.id}>
                    <TableCell>
                      <div className="font-medium">{mapping.setor || '-'}</div>
                    </TableCell>
                    <TableCell className="text-sm">{mapping.funcao || '-'}</TableCell>
                    <TableCell>
                      <div>
                        <div className="text-sm font-medium">{mapping.agente_risco || '-'}</div>
                        {mapping.meio_propagacao && (
                          <div className="text-xs text-muted-foreground">{mapping.meio_propagacao}</div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>{getCategoryBadge(mapping.categoria)}</TableCell>
                    <TableCell>{getRiskBadge(mapping.nivel_risco)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {mapping.fonte_geradora || '-'}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8"
                          onClick={() => openEdit(mapping)}
                        >
                          <Edit className="h-4 w-4" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Dialog - Create/Edit Risk Mapping */}
      <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm(); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editItem ? 'Editar Mapeamento' : 'Novo Mapeamento de Risco'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4 max-h-[60vh] overflow-y-auto">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="setor">Setor</Label>
                <Input
                  id="setor"
                  value={formData.setor}
                  onChange={(e) => setFormData({ ...formData, setor: e.target.value })}
                  placeholder="Ex: Producao"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="funcao">Função</Label>
                <Input
                  id="funcao"
                  value={formData.funcao}
                  onChange={(e) => setFormData({ ...formData, funcao: e.target.value })}
                  placeholder="Ex: Operador"
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="agente_risco">Agente de Risco</Label>
              <Input
                id="agente_risco"
                value={formData.agente_risco}
                onChange={(e) => setFormData({ ...formData, agente_risco: e.target.value })}
                placeholder="Ex: Ruido continuo"
              />
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="categoria">Categoria</Label>
                <Select
                  value={formData.categoria}
                  onValueChange={(v) => setFormData({ ...formData, categoria: v })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {categoriesList.length > 0 ? (
                      categoriesList.map((cat: any) => (
                        <SelectItem key={cat.id || cat.value || cat} value={cat.value || cat.id || cat}>
                          {cat.label || cat.nome || cat}
                        </SelectItem>
                      ))
                    ) : (
                      <>
                        <SelectItem value="fisico">Fisico</SelectItem>
                        <SelectItem value="quimico">Quimico</SelectItem>
                        <SelectItem value="biologico">Biologico</SelectItem>
                        <SelectItem value="ergonomico">Ergonomico</SelectItem>
                        <SelectItem value="acidente">Acidente</SelectItem>
                      </>
                    )}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="nivel_risco">Nivel de Risco</Label>
                <Select
                  value={formData.nivel_risco}
                  onValueChange={(v) => setFormData({ ...formData, nivel_risco: v })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="trivial">Trivial</SelectItem>
                    <SelectItem value="toleravel">Toleravel</SelectItem>
                    <SelectItem value="moderado">Moderado</SelectItem>
                    <SelectItem value="substancial">Substancial</SelectItem>
                    <SelectItem value="intoleravel">Intoleravel</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="fonte_geradora">Fonte Geradora</Label>
              <Input
                id="fonte_geradora"
                value={formData.fonte_geradora}
                onChange={(e) => setFormData({ ...formData, fonte_geradora: e.target.value })}
                placeholder="Ex: Maquinas industriais"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="meio_propagacao">Meio de Propagacao</Label>
              <Input
                id="meio_propagacao"
                value={formData.meio_propagacao}
                onChange={(e) => setFormData({ ...formData, meio_propagacao: e.target.value })}
                placeholder="Ex: Ar"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="medidas_existentes">Medidas de Controle Existentes</Label>
              <Input
                id="medidas_existentes"
                value={formData.medidas_existentes}
                onChange={(e) => setFormData({ ...formData, medidas_existentes: e.target.value })}
                placeholder="Ex: Uso de protetor auricular"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="observacoes">Observações</Label>
              <Input
                id="observacoes"
                value={formData.observacoes}
                onChange={(e) => setFormData({ ...formData, observacoes: e.target.value })}
                placeholder="Observações adicionais"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setDialogOpen(false); resetForm(); }}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={createMapping.isPending || updateMapping.isPending || !formData.setor || !formData.agente_risco || !formData.categoria}
            >
              {(createMapping.isPending || updateMapping.isPending) ? 'Salvando...' : editItem ? 'Salvar' : 'Cadastrar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
