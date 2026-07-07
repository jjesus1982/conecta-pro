'use client';

import { HardHat, Package, Truck, AlertCircle, BarChart3, Plus, RefreshCw, Search, Edit, Eye } from 'lucide-react';
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
  DialogTrigger,
} from '@/components/ui/dialog';
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
  useEPIStatistics,
  useEPIList,
  useEPICategories,
  useEPIInventory,
  useCreateEPI,
  useUpdateEPI,
} from '@/hooks/health-occupational';

export default function EPIPage() {
  const { data: stats, isLoading: statsLoading } = useEPIStatistics();
  const { data: categories } = useEPICategories();
  const [categoryFilter, setCategoryFilter] = useState<string>('all');

  const epiListFilters = categoryFilter !== 'all' ? { categoria: categoryFilter as any } : undefined;
  const { data: epiData, isLoading: epiLoading, error: epiError, refetch } = useEPIList(epiListFilters);
  const { data: inventoryData, isLoading: inventoryLoading } = useEPIInventory();

  const createEPI = useCreateEPI();
  const updateEPI = useUpdateEPI();

  const [search, setSearch] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editItem, setEditItem] = useState<any | null>(null);

  // Form state
  const [formData, setFormData] = useState({
    nome: '',
    descricao: '',
    categoria: '',
    ca_numero: '',
    validade_ca: '',
    fabricante: '',
  });

  const resetForm = () => {
    setFormData({
      nome: '',
      descricao: '',
      categoria: '',
      ca_numero: '',
      validade_ca: '',
      fabricante: '',
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
      nome: item.nome || '',
      descricao: item.descricao || '',
      categoria: item.categoria || '',
      ca_numero: item.ca_numero || '',
      validade_ca: item.validade_ca || '',
      fabricante: item.fabricante || '',
    });
    setDialogOpen(true);
  };

  const handleSubmit = async () => {
    if (!formData.nome || !formData.categoria) return;
    try {
      if (editItem) {
        await updateEPI.mutateAsync({ epiId: editItem.id, data: formData as any });
        toast.success('EPI atualizado com sucesso', { duration: 4000 });
      } else {
        await createEPI.mutateAsync(formData as any);
        toast.success('EPI cadastrado com sucesso', { duration: 4000 });
      }
      setDialogOpen(false);
      resetForm();
      refetch();
    } catch (error) {
      toast.error('Erro ao salvar EPI. Tente novamente.', { duration: 5000 });
    }
  };

  const epiList = Array.isArray(epiData) ? epiData : (epiData as any)?.epis ?? (epiData as any)?.items ?? [];
  const inventoryList = Array.isArray(inventoryData) ? inventoryData : (inventoryData as any)?.itens ?? (inventoryData as any)?.items ?? [];
  const categoriesList = Array.isArray(categories) ? categories : (categories as any)?.categorias ?? (categories as any)?.items ?? [];

  const filteredEPIs = search
    ? epiList.filter((epi: any) =>
        (epi.nome || '').toLowerCase().includes(search.toLowerCase()) ||
        (epi.ca_numero || '').toLowerCase().includes(search.toLowerCase()) ||
        (epi.fabricante || '').toLowerCase().includes(search.toLowerCase())
      )
    : epiList;

  const getStatusBadge = (ativo: boolean) => {
    return ativo
      ? <Badge className="bg-green-100 text-green-800">Ativo</Badge>
      : <Badge className="bg-gray-100 text-gray-800">Inativo</Badge>;
  };

  const getStockBadge = (quantidade: number, minimo: number) => {
    if (quantidade <= 0) return <Badge className="bg-red-100 text-red-800">Sem Estoque</Badge>;
    if (quantidade <= minimo) return <Badge className="bg-yellow-100 text-yellow-800">Estoque Baixo</Badge>;
    return <Badge className="bg-green-100 text-green-800">Normal</Badge>;
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
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <HardHat className="h-6 w-6" />
            Equipamentos de Protecao - EPI
          </h1>
          <p className="text-muted-foreground">
            Gestao de equipamentos de protecao individual, controle de entregas e estoque conforme NR-6.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleRefresh} disabled={epiLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${epiLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Novo EPI
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total EPIs</CardTitle>
            <HardHat className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums">{(stats as any)?.total_epis_ativos ?? (stats as any)?.total_epis ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Entregas Ativas</CardTitle>
            <Truck className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{(stats as any)?.entregas_ano ?? (stats as any)?.total_entregas ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Estoque Baixo</CardTitle>
            <AlertCircle className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{(stats as any)?.itens_baixo_estoque ?? (stats as any)?.estoque_baixo ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">CAs Vencendo</CardTitle>
            <BarChart3 className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{(stats as any)?.assinaturas_pendentes ?? (stats as any)?.cas_vencendo ?? 0}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tabs: Catalogo / Estoque */}
      <Tabs defaultValue="catalogo" className="space-y-4">
        <TabsList>
          <TabsTrigger value="catalogo">Catalogo de EPIs</TabsTrigger>
          <TabsTrigger value="estoque">Estoque</TabsTrigger>
        </TabsList>

        {/* Tab: Catalogo */}
        <TabsContent value="catalogo" className="space-y-4">
          {/* Filters */}
          <Card>
            <CardContent className="pt-6">
              <div className="flex flex-col md:flex-row gap-4">
                <div className="flex-1 relative">
                  <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Buscar por nome, CA ou fabricante..."
                    className="pl-10"
                  />
                </div>
                <Select value={categoryFilter} onValueChange={setCategoryFilter} aria-label="Category Filter">
                  <SelectTrigger className="w-[200px]">
                    <SelectValue placeholder="Categoria" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas as categorias</SelectItem>
                    {categoriesList.map((cat: any) => (
                      <SelectItem key={cat.id || cat.value || cat} value={cat.value || cat.id || cat}>
                        {cat.label || cat.nome || cat}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {/* Error */}
          {epiError && (
            <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
              <AlertCircle className="h-5 w-5 text-destructive" />
              <p className="text-sm text-destructive flex-1">Erro ao carregar EPIs</p>
              <Button variant="outline" size="sm" onClick={() => refetch()}>
                Tentar novamente
              </Button>
            </div>
          )}

          {/* Table - EPI Catalog */}
          <Card>
            <CardContent className="p-0">
              {epiLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              ) : filteredEPIs.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <HardHat className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium">Nenhum registro encontrado</h3>
                  <p className="mt-2">Tente ajustar os filtros ou cadastre um novo EPI.</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Nome</TableHead>
                      <TableHead>Categoria</TableHead>
                      <TableHead>CA</TableHead>
                      <TableHead>Fabricante</TableHead>
                      <TableHead>Validade CA</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="w-[100px]">Ações</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {filteredEPIs.map((epi: any) => (
                      <TableRow key={epi.id}>
                        <TableCell>
                          <div>
                            <div className="font-medium">{epi.nome}</div>
                            {epi.descricao && (
                              <div className="text-xs text-muted-foreground truncate max-w-[200px]">
                                {epi.descricao}
                              </div>
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="text-sm">{epi.categoria || '-'}</TableCell>
                        <TableCell className="text-sm font-mono">{epi.ca_numero || '-'}</TableCell>
                        <TableCell className="text-sm">{epi.fabricante || '-'}</TableCell>
                        <TableCell className="text-sm">
                          {epi.validade_ca
                            ? new Date(epi.validade_ca).toLocaleDateString('pt-BR')
                            : '-'}
                        </TableCell>
                        <TableCell>{getStatusBadge(epi.ativo !== false)}</TableCell>
                        <TableCell>
                          <div className="flex items-center gap-1">
                            <Button
                              variant="ghost"
                              size="icon"
                              className="h-8 w-8"
                              onClick={() => openEdit(epi)}
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
        </TabsContent>

        {/* Tab: Estoque */}
        <TabsContent value="estoque" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Visao Geral do Estoque</CardTitle>
              <CardDescription>
                Controle de quantidades em estoque por item de EPI.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {inventoryLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              ) : inventoryList.length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Package className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium">Nenhum registro encontrado</h3>
                  <p className="mt-2">Nao ha itens de estoque cadastrados.</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>EPI</TableHead>
                      <TableHead>Categoria</TableHead>
                      <TableHead>Quantidade</TableHead>
                      <TableHead>Minimo</TableHead>
                      <TableHead>Lote</TableHead>
                      <TableHead>Situação</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {inventoryList.map((item: any) => (
                      <TableRow key={item.id || item.epi_id}>
                        <TableCell>
                          <div className="font-medium">{item.epi_nome || item.nome || 'N/A'}</div>
                        </TableCell>
                        <TableCell className="text-sm">{item.categoria || '-'}</TableCell>
                        <TableCell className="text-sm font-bold">{item.quantidade ?? 0}</TableCell>
                        <TableCell className="text-sm">{item.quantidade_minima ?? item.minimo ?? 0}</TableCell>
                        <TableCell className="text-sm font-mono">{item.lote || '-'}</TableCell>
                        <TableCell>
                          {getStockBadge(item.quantidade ?? 0, item.quantidade_minima ?? item.minimo ?? 5)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* Dialog - Create/Edit EPI */}
      <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm(); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editItem ? 'Editar EPI' : 'Novo EPI'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="nome">Nome</Label>
              <Input
                id="nome"
                value={formData.nome}
                onChange={(e) => setFormData({ ...formData, nome: e.target.value })}
                placeholder="Nome do EPI"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="descricao">Descricao</Label>
              <Input
                id="descricao"
                value={formData.descricao}
                onChange={(e) => setFormData({ ...formData, descricao: e.target.value })}
                placeholder="Descricao do EPI"
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
                        <SelectItem value="cabeca">Protecao da Cabeca</SelectItem>
                        <SelectItem value="olhos">Protecao dos Olhos</SelectItem>
                        <SelectItem value="auditiva">Protecao Auditiva</SelectItem>
                        <SelectItem value="respiratoria">Protecao Respiratoria</SelectItem>
                        <SelectItem value="maos">Protecao das Maos</SelectItem>
                        <SelectItem value="pes">Protecao dos Pes</SelectItem>
                        <SelectItem value="corpo">Protecao do Corpo</SelectItem>
                        <SelectItem value="queda">Protecao contra Queda</SelectItem>
                      </>
                    )}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="ca_numero">Numero do CA</Label>
                <Input
                  id="ca_numero"
                  value={formData.ca_numero}
                  onChange={(e) => setFormData({ ...formData, ca_numero: e.target.value })}
                  placeholder="Ex: 12345"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="fabricante">Fabricante</Label>
                <Input
                  id="fabricante"
                  value={formData.fabricante}
                  onChange={(e) => setFormData({ ...formData, fabricante: e.target.value })}
                  placeholder="Nome do fabricante"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="validade_ca">Validade do CA</Label>
                <Input
                  id="validade_ca"
                  type="date"
                  value={formData.validade_ca}
                  onChange={(e) => setFormData({ ...formData, validade_ca: e.target.value })}
                />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setDialogOpen(false); resetForm(); }}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={createEPI.isPending || updateEPI.isPending || !formData.nome || !formData.categoria}
            >
              {(createEPI.isPending || updateEPI.isPending) ? 'Salvando...' : editItem ? 'Salvar' : 'Cadastrar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
