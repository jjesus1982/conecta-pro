'use client';

import { HardHat, Package, Truck, AlertCircle, BarChart3, Plus, RefreshCw, Search, Edit, Eye, FileSignature, Download } from 'lucide-react';
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
import { useEntregasEPI, useFichasEPI, useGerarFichaEPI, useRegistrarEntregaEPI } from '@/hooks/sst';
import { apiErrorDetail, sstService, type EPIEntregaItem } from '@/lib/services/sst';
import { EmployeeSelect, useActiveEmployees } from '@/components/sst/EmployeeSelect';
import { RolloutAssinaturasSection } from './rollout-assinaturas';

function getFichaStatusBadge(status: string) {
  const config: Record<string, { label: string; className: string }> = {
    pendente_assinatura: { label: 'Pendente de assinatura', className: 'bg-yellow-100 text-yellow-800' },
    assinada: { label: 'Assinada', className: 'bg-green-100 text-green-800' },
    sem_ficha: { label: 'Sem ficha', className: 'bg-gray-100 text-gray-800' },
  };
  const item = config[status] ?? { label: status, className: 'bg-gray-100 text-gray-800' };
  return <Badge className={item.className}>{item.label}</Badge>;
}

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

  // Fichas de EPI
  const { data: fichasData, isLoading: fichasLoading, error: fichasError, refetch: refetchFichas } = useFichasEPI();
  const gerarFicha = useGerarFichaEPI();
  const [fichaDialogOpen, setFichaDialogOpen] = useState(false);
  const [fichaEmployeeId, setFichaEmployeeId] = useState('');
  const [downloadingFichaId, setDownloadingFichaId] = useState<string | null>(null);
  const [gerandoFichaEmployeeId, setGerandoFichaEmployeeId] = useState<string | null>(null);

  // Entregas de EPI
  const { data: entregasData, isLoading: entregasLoading, error: entregasError, refetch: refetchEntregas } = useEntregasEPI();
  const registrarEntrega = useRegistrarEntregaEPI();
  const { data: employees } = useActiveEmployees();
  const [entregaForm, setEntregaForm] = useState({
    employee_id: '',
    epi_catalogo_id: '',
    quantidade: '1',
  });

  const employeeNomeById = (id: string) =>
    (employees ?? []).find((e) => e.id === id)?.nome ?? null;

  const handleGerarFicha = async (employeeId?: string) => {
    const targetId = (employeeId ?? fichaEmployeeId).trim();
    if (!targetId) return;
    setGerandoFichaEmployeeId(targetId);
    try {
      await gerarFicha.mutateAsync({ employee_id: targetId });
      toast.success('Ficha de EPI gerada com sucesso', { duration: 4000 });
      setFichaDialogOpen(false);
      setFichaEmployeeId('');
      refetchFichas();
      refetchEntregas();
    } catch (error) {
      toast.error(apiErrorDetail(error, 'Erro ao gerar ficha de EPI'), { duration: 6000 });
    } finally {
      setGerandoFichaEmployeeId(null);
    }
  };

  const handleRegistrarEntrega = async () => {
    const epiSelecionado = epiList.find(
      (epi: any) => String(epi.id) === entregaForm.epi_catalogo_id
    );
    const quantidade = parseInt(entregaForm.quantidade, 10);
    if (!entregaForm.employee_id || !epiSelecionado || !quantidade || quantidade < 1) return;
    try {
      const result = await registrarEntrega.mutateAsync({
        employee_id: entregaForm.employee_id,
        epi_nome: epiSelecionado.nome,
        quantidade,
        epi_ca: epiSelecionado.ca_numero || undefined,
      });
      if (result.ficha_epi?.ficha_id) {
        toast.success('Entrega registrada — ficha de EPI gerada (pendente de assinatura)', { duration: 5000 });
      } else {
        toast.success('Entrega registrada', { duration: 4000 });
        if (result.ficha_epi?.erro) {
          toast.warning(`Ficha nao gerada: ${result.ficha_epi.erro}`, { duration: 6000 });
        }
      }
      setEntregaForm({ employee_id: '', epi_catalogo_id: '', quantidade: '1' });
      refetchEntregas();
      refetchFichas();
    } catch (error) {
      toast.error(apiErrorDetail(error, 'Erro ao registrar entrega de EPI'), { duration: 6000 });
    }
  };

  const handleDownloadFichaPdf = async (fichaId: string) => {
    setDownloadingFichaId(fichaId);
    try {
      const blob = await sstService.downloadFichaEPIPdf(fichaId);
      const url = window.URL.createObjectURL(blob);
      window.open(url, '_blank');
      setTimeout(() => window.URL.revokeObjectURL(url), 60_000);
    } catch {
      toast.error('Erro ao baixar PDF da ficha de EPI', { duration: 5000 });
    } finally {
      setDownloadingFichaId(null);
    }
  };

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
              <>
                {/* FATO: CAs do catalogo (health_epi_catalog.ca_validade) vencidos ou a vencer em 90d — nunca entregas */}
                <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{(stats as any)?.cas_vencendo ?? 0}</div>
                {((stats as any)?.cas_sem_validade ?? 0) > 0 && (
                  <p className="mt-1 text-xs text-muted-foreground">
                    {(stats as any).cas_sem_validade} CA(s) sem validade registrada
                  </p>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tabs: Catalogo / Estoque */}
      <Tabs defaultValue="catalogo" className="space-y-4">
        <TabsList>
          <TabsTrigger value="catalogo">Catalogo de EPIs</TabsTrigger>
          <TabsTrigger value="estoque">Estoque</TabsTrigger>
          <TabsTrigger value="fichas">Entregas &amp; Fichas</TabsTrigger>
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
                          <div className="flex items-center gap-1 flex-wrap">
                            {getStockBadge(item.quantidade ?? 0, item.quantidade_minima ?? item.minimo ?? 5)}
                            {item.ficha_status ? getFichaStatusBadge(item.ficha_status) : null}
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

        {/* Tab: Entregas & Fichas */}
        <TabsContent value="fichas" className="space-y-4">
          {/* Registrar entrega de EPI */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Truck className="h-4 w-4" />
                Registrar Entrega de EPI
              </CardTitle>
              <CardDescription>
                A entrega gera automaticamente a ficha de EPI (NR-6), pendente de assinatura do funcionario.
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 md:grid-cols-[2fr_2fr_100px_150px_auto] md:items-end">
                <div className="space-y-2">
                  <Label htmlFor="entrega_funcionario">Funcionario</Label>
                  <EmployeeSelect
                    id="entrega_funcionario"
                    value={entregaForm.employee_id}
                    onChange={(employeeId) => setEntregaForm({ ...entregaForm, employee_id: employeeId })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="entrega_epi">EPI (catalogo)</Label>
                  <Select
                    value={entregaForm.epi_catalogo_id}
                    onValueChange={(v) => setEntregaForm({ ...entregaForm, epi_catalogo_id: v })}
                  >
                    <SelectTrigger id="entrega_epi">
                      <SelectValue placeholder="Selecione o EPI" />
                    </SelectTrigger>
                    <SelectContent>
                      {epiList.length === 0 ? (
                        <SelectItem value="__vazio__" disabled>
                          Nenhum EPI no catalogo
                        </SelectItem>
                      ) : (
                        epiList.map((epi: any) => (
                          <SelectItem key={epi.id} value={String(epi.id)}>
                            {epi.nome}{epi.ca_numero ? ` (CA ${epi.ca_numero})` : ''}
                          </SelectItem>
                        ))
                      )}
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="entrega_qtd">Qtd.</Label>
                  <Input
                    id="entrega_qtd"
                    type="number"
                    min={1}
                    value={entregaForm.quantidade}
                    onChange={(e) => setEntregaForm({ ...entregaForm, quantidade: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="entrega_data">Data da entrega</Label>
                  <Input
                    id="entrega_data"
                    type="date"
                    value={new Date().toISOString().substring(0, 10)}
                    disabled
                    title="A data da entrega e registrada pelo servidor na data de hoje"
                  />
                </div>
                <Button
                  onClick={handleRegistrarEntrega}
                  disabled={
                    registrarEntrega.isPending ||
                    !entregaForm.employee_id ||
                    !entregaForm.epi_catalogo_id ||
                    !(parseInt(entregaForm.quantidade, 10) >= 1)
                  }
                >
                  {registrarEntrega.isPending ? 'Registrando...' : 'Registrar entrega'}
                </Button>
              </div>
              <p className="mt-2 text-xs text-muted-foreground">
                A data da entrega e gravada pelo servidor no dia do registro (hoje).
              </p>
            </CardContent>
          </Card>

          {/* Entregas registradas */}
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Entregas de EPI</CardTitle>
              <CardDescription>
                Entregas registradas e a situacao da ficha de cada uma. Funcionarios com entregas sem ficha podem gerar a ficha aqui.
              </CardDescription>
            </CardHeader>
            <CardContent className="p-0">
              {entregasLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              ) : entregasError ? (
                <div className="px-6 py-8 text-sm text-destructive flex items-center gap-2">
                  <AlertCircle className="h-4 w-4" />
                  {apiErrorDetail(entregasError, 'Erro ao carregar entregas de EPI')}
                  <Button variant="outline" size="sm" onClick={() => refetchEntregas()}>
                    Tentar novamente
                  </Button>
                </div>
              ) : (entregasData?.epis ?? []).length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <Truck className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium">Nenhuma entrega registrada</h3>
                  <p className="mt-2">Registre a primeira entrega de EPI no formulario acima.</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Funcionario</TableHead>
                      <TableHead>EPI</TableHead>
                      <TableHead>Qtd.</TableHead>
                      <TableHead>CA</TableHead>
                      <TableHead>Ficha</TableHead>
                      <TableHead className="w-[160px]">Acoes</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(entregasData?.epis ?? []).map((entrega: EPIEntregaItem) => (
                      <TableRow key={entrega.delivery_id}>
                        <TableCell className="font-medium">
                          {employeeNomeById(entrega.employee_id) || (
                            <span className="font-mono text-xs text-muted-foreground">
                              {entrega.employee_id.substring(0, 8)}...
                            </span>
                          )}
                        </TableCell>
                        <TableCell className="text-sm">{entrega.epi}</TableCell>
                        <TableCell className="text-sm tabular-nums">{entrega.quantidade}</TableCell>
                        <TableCell className="text-sm font-mono">{entrega.ca || '—'}</TableCell>
                        <TableCell>{getFichaStatusBadge(entrega.ficha_status)}</TableCell>
                        <TableCell>
                          {entrega.ficha_status === 'sem_ficha' ? (
                            <Button
                              variant="outline"
                              size="sm"
                              onClick={() => handleGerarFicha(entrega.employee_id)}
                              disabled={gerarFicha.isPending}
                              title="Gera a ficha consolidando as entregas sem ficha deste funcionario"
                            >
                              <FileSignature className="h-4 w-4 mr-2" />
                              {gerandoFichaEmployeeId === entrega.employee_id ? 'Gerando...' : 'Gerar ficha'}
                            </Button>
                          ) : (
                            <span className="text-xs text-muted-foreground">—</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Stats das fichas */}
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Pendentes de Assinatura</CardTitle>
                <FileSignature className="h-4 w-4 text-yellow-600" />
              </CardHeader>
              <CardContent>
                {fichasLoading ? (
                  <div className="h-8 w-16 animate-pulse rounded bg-muted" />
                ) : (
                  <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">
                    {fichasData?.pendentes_assinatura ?? 0}
                  </div>
                )}
              </CardContent>
            </Card>
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Assinadas</CardTitle>
                <FileSignature className="h-4 w-4 text-green-600" />
              </CardHeader>
              <CardContent>
                {fichasLoading ? (
                  <div className="h-8 w-16 animate-pulse rounded bg-muted" />
                ) : (
                  <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                    {fichasData?.assinadas ?? 0}
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          {/* Error */}
          {fichasError && (
            <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
              <AlertCircle className="h-5 w-5 text-destructive" />
              <p className="text-sm text-destructive flex-1">Erro ao carregar fichas de EPI</p>
              <Button variant="outline" size="sm" onClick={() => refetchFichas()}>
                Tentar novamente
              </Button>
            </div>
          )}

          <Card>
            <CardHeader className="flex flex-row items-center justify-between space-y-0">
              <div>
                <CardTitle className="text-base">Fichas de Entrega de EPI</CardTitle>
                <CardDescription>
                  Fichas consolidadas de entrega de EPI por funcionario, conforme NR-6.
                </CardDescription>
              </div>
              <Button onClick={() => setFichaDialogOpen(true)}>
                <Plus className="h-4 w-4 mr-2" />
                Gerar ficha
              </Button>
            </CardHeader>
            <CardContent className="p-0">
              {fichasLoading ? (
                <div className="flex items-center justify-center py-12">
                  <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
                </div>
              ) : (fichasData?.fichas ?? []).length === 0 ? (
                <div className="text-center py-12 text-muted-foreground">
                  <FileSignature className="h-16 w-16 mx-auto mb-4 opacity-50" />
                  <h3 className="text-lg font-medium">Nenhuma ficha gerada</h3>
                  <p className="mt-2">Gere uma ficha para consolidar as entregas de EPI de um funcionario.</p>
                </div>
              ) : (
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Funcionario</TableHead>
                      <TableHead>Itens</TableHead>
                      <TableHead>Criada em</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="w-[80px]">PDF</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {(fichasData?.fichas ?? []).map((ficha) => (
                      <TableRow key={ficha.ficha_id}>
                        <TableCell className="font-medium">{ficha.employee_nome || '—'}</TableCell>
                        <TableCell className="text-sm tabular-nums">{ficha.itens?.length ?? 0}</TableCell>
                        <TableCell className="text-sm">
                          {ficha.created_at
                            ? new Date(ficha.created_at).toLocaleDateString('pt-BR')
                            : '—'}
                        </TableCell>
                        <TableCell>{getFichaStatusBadge(ficha.status)}</TableCell>
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="icon"
                            className="h-8 w-8"
                            onClick={() => handleDownloadFichaPdf(ficha.ficha_id)}
                            disabled={downloadingFichaId === ficha.ficha_id}
                            title="Baixar PDF da ficha"
                          >
                            <Download className="h-4 w-4" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              )}
            </CardContent>
          </Card>

          {/* Rollout de Assinaturas — acesso ao Portal do Funcionario */}
          <RolloutAssinaturasSection />
        </TabsContent>
      </Tabs>

      {/* Dialog - Gerar Ficha de EPI */}
      <Dialog open={fichaDialogOpen} onOpenChange={(open) => { setFichaDialogOpen(open); if (!open) setFichaEmployeeId(''); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Gerar Ficha de EPI</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="ficha_employee_id">Funcionario</Label>
              <EmployeeSelect
                id="ficha_employee_id"
                value={fichaEmployeeId}
                onChange={(employeeId) => setFichaEmployeeId(employeeId)}
                placeholder="Busque pelo nome do funcionario..."
              />
              <p className="text-xs text-muted-foreground">
                Consolida as entregas de EPI ainda sem ficha para este funcionario.
              </p>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setFichaDialogOpen(false); setFichaEmployeeId(''); }}>
              Cancelar
            </Button>
            <Button onClick={() => handleGerarFicha()} disabled={gerarFicha.isPending || !fichaEmployeeId.trim()}>
              {gerarFicha.isPending ? 'Gerando...' : 'Gerar ficha'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

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
