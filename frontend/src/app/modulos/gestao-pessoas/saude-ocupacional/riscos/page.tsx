'use client';

import { AlertTriangle, ShieldAlert, MapPin, CheckCircle, Clock, Plus, RefreshCw, Search } from 'lucide-react';
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
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
import { usePPRAStatistics } from '@/hooks/health-occupational';
import { sstService, type RiscoOcupacional, type RiscoCreate } from '@/lib/services/sst';

const NIVEIS = ['baixo', 'medio', 'alto', 'critico'] as const;
const CATEGORIAS = ['fisico', 'quimico', 'biologico', 'ergonomico', 'acidente'] as const;

const NIVEL_LABELS: Record<string, string> = {
  baixo: 'Baixo',
  medio: 'Médio',
  alto: 'Alto',
  critico: 'Crítico',
};

const NIVEL_CLASSES: Record<string, string> = {
  baixo: 'bg-green-100 text-green-800',
  medio: 'bg-yellow-100 text-yellow-800',
  alto: 'bg-orange-100 text-orange-800',
  critico: 'bg-red-100 text-red-800',
};

const CATEGORIA_LABELS: Record<string, string> = {
  fisico: 'Físico',
  quimico: 'Químico',
  biologico: 'Biológico',
  ergonomico: 'Ergonômico',
  acidente: 'Acidente',
};

const CATEGORIA_CLASSES: Record<string, string> = {
  fisico: 'bg-blue-100 text-blue-800',
  quimico: 'bg-purple-100 text-purple-800',
  biologico: 'bg-green-100 text-green-800',
  ergonomico: 'bg-orange-100 text-orange-800',
  acidente: 'bg-red-100 text-red-800',
};

const STATUS_LABELS: Record<string, string> = {
  identificado: 'Identificado',
  controlado: 'Controlado',
  encerrado: 'Encerrado',
};

const STATUS_CLASSES: Record<string, string> = {
  identificado: 'bg-yellow-100 text-yellow-800',
  controlado: 'bg-green-100 text-green-800',
  encerrado: 'bg-gray-100 text-gray-800',
};

const ALL = '__all__';

export default function RiscosPage() {
  const queryClient = useQueryClient();
  const { data: stats, isLoading: statsLoading } = usePPRAStatistics();

  const [nivelFilter, setNivelFilter] = useState<string>(ALL);
  const [categoriaFilter, setCategoriaFilter] = useState<string>(ALL);
  const [search, setSearch] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);

  const {
    data: riscosData,
    isLoading: riscosLoading,
    error: riscosError,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['sst', 'riscos', nivelFilter, categoriaFilter],
    queryFn: () =>
      sstService.listRiscos({
        ...(nivelFilter !== ALL ? { nivel: nivelFilter } : {}),
        ...(categoriaFilter !== ALL ? { categoria: categoriaFilter } : {}),
      }),
    staleTime: 5 * 60 * 1000,
  });

  // Postos para o seletor por nome (só carrega com o dialog aberto)
  const { data: postosData } = useQuery({
    queryKey: ['sst', 'postos-select'],
    queryFn: () => sstService.listPostos(),
    enabled: dialogOpen,
    staleTime: 10 * 60 * 1000,
  });

  const createRisco = useMutation({
    mutationFn: (data: RiscoCreate) => sstService.createRisco(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['sst', 'riscos'] });
      queryClient.invalidateQueries({ queryKey: ['ppra', 'statistics'] });
    },
  });

  const [formData, setFormData] = useState({
    posto_id: '',
    categoria: '',
    nivel: 'medio',
    descricao: '',
    fonte_geradora: '',
    medidas_controle: '',
    epi_recomendado: '',
  });

  const resetForm = () =>
    setFormData({
      posto_id: '',
      categoria: '',
      nivel: 'medio',
      descricao: '',
      fonte_geradora: '',
      medidas_controle: '',
      epi_recomendado: '',
    });

  const handleSubmit = async () => {
    if (!formData.posto_id || !formData.categoria || !formData.descricao) return;
    try {
      await createRisco.mutateAsync({
        posto_id: formData.posto_id,
        categoria: formData.categoria,
        nivel: formData.nivel,
        descricao: formData.descricao,
        fonte_geradora: formData.fonte_geradora || undefined,
        medidas_controle: formData.medidas_controle
          ? formData.medidas_controle.split(',').map((s) => s.trim()).filter(Boolean)
          : undefined,
        epi_recomendado: formData.epi_recomendado
          ? formData.epi_recomendado.split(',').map((s) => s.trim()).filter(Boolean)
          : undefined,
      });
      toast.success('Mapeamento de risco cadastrado com sucesso', { duration: 4000 });
      setDialogOpen(false);
      resetForm();
    } catch {
      toast.error('Erro ao salvar mapeamento. Tente novamente.', { duration: 5000 });
    }
  };

  const riscos: RiscoOcupacional[] = riscosData?.riscos ?? [];
  const postos = postosData?.items ?? [];

  const filteredRiscos = search
    ? riscos.filter((r) => {
        const q = search.toLowerCase();
        return (
          (r.descricao || '').toLowerCase().includes(q) ||
          (r.posto_nome || '').toLowerCase().includes(q) ||
          (r.fonte_geradora || '').toLowerCase().includes(q) ||
          (r.categoria || '').toLowerCase().includes(q)
        );
      })
    : riscos;

  const handleRefresh = async () => {
    try {
      await refetch();
      toast.success('Dados atualizados', { duration: 4000 });
    } catch {
      toast.error('Erro ao atualizar dados', { duration: 5000 });
    }
  };

  const renderPosto = (r: RiscoOcupacional) => {
    if (r.posto_nome) {
      return <div className="font-medium">{r.posto_nome}</div>;
    }
    return (
      <div>
        <code className="text-xs text-muted-foreground">{(r.posto_id || '').slice(0, 8)}…</code>
        <div className="text-xs text-amber-600 flex items-center gap-1">
          <AlertTriangle className="h-3 w-3" />
          posto não vinculado
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <AlertTriangle className="h-6 w-6" />
            Riscos Ocupacionais - PPRA/PGR
          </h1>
          <p className="text-muted-foreground">
            Mapeamento e gestão de riscos ocupacionais, medidas de controle e análise por posto conforme NR-9.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleRefresh} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => { resetForm(); setDialogOpen(true); }}>
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
              <div className="font-data text-2xl font-semibold tabular-nums">{(stats as any)?.total_riscos_identificados ?? 0}</div>
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
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{(stats as any)?.total_mapeamentos_ativos ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Riscos Alto Nível</CardTitle>
            <AlertTriangle className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-orange-600">{(stats as any)?.riscos_alto_nivel ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Riscos Controlados</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {riscosLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                {riscos.filter((r) => r.status === 'controlado').length}
              </div>
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
                placeholder="Buscar por descrição, posto ou fonte geradora..."
                className="pl-10"
              />
            </div>
            <Select value={nivelFilter} onValueChange={setNivelFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Nível de risco" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Todos os níveis</SelectItem>
                {NIVEIS.map((n) => (
                  <SelectItem key={n} value={n}>{NIVEL_LABELS[n]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={categoriaFilter} onValueChange={setCategoriaFilter}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Categoria" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL}>Todas as categorias</SelectItem>
                {CATEGORIAS.map((c) => (
                  <SelectItem key={c} value={c}>{CATEGORIA_LABELS[c]}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {riscosError ? (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar mapeamentos de riscos</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      ) : null}

      {/* Table - Riscos */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Mapeamento de Riscos</CardTitle>
          <CardDescription>
            {riscosData
              ? `${filteredRiscos.length} de ${riscosData.total} riscos ocupacionais identificados — o quê, onde e como controlar.`
              : 'Riscos ocupacionais identificados por posto de trabalho.'}
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {riscosLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : filteredRiscos.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <AlertTriangle className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum registro encontrado</h3>
              <p className="mt-2">Tente ajustar os filtros ou crie um novo mapeamento de risco.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Posto / Local</TableHead>
                  <TableHead>Categoria</TableHead>
                  <TableHead>Risco (agente / descrição)</TableHead>
                  <TableHead>Nível</TableHead>
                  <TableHead>Medidas de Controle</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredRiscos.map((r) => (
                  <TableRow key={r.risk_id}>
                    <TableCell>{renderPosto(r)}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className={CATEGORIA_CLASSES[r.categoria] || ''}>
                        {CATEGORIA_LABELS[r.categoria] || r.categoria || '-'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="text-sm font-medium">{r.descricao || '-'}</div>
                      {r.fonte_geradora && (
                        <div className="text-xs text-muted-foreground">Fonte: {r.fonte_geradora}</div>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge className={NIVEL_CLASSES[r.nivel] || 'bg-gray-100 text-gray-800'}>
                        {NIVEL_LABELS[r.nivel] || r.nivel || 'N/A'}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-[280px]">
                      {r.medidas_controle && r.medidas_controle.length > 0 ? (
                        <ul className="text-xs text-muted-foreground list-disc pl-4 space-y-0.5">
                          {r.medidas_controle.map((m, i) => (
                            <li key={i}>{m}</li>
                          ))}
                        </ul>
                      ) : (
                        <span className="text-xs text-muted-foreground">—</span>
                      )}
                      {r.epi_recomendado && r.epi_recomendado.length > 0 && (
                        <div className="text-xs text-blue-700 mt-1">EPI: {r.epi_recomendado.join(', ')}</div>
                      )}
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className={STATUS_CLASSES[r.status] || ''}>
                        {STATUS_LABELS[r.status] || r.status || '-'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Dialog - Novo Mapeamento */}
      <Dialog open={dialogOpen} onOpenChange={(open) => { setDialogOpen(open); if (!open) resetForm(); }}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Novo Mapeamento de Risco</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4 max-h-[60vh] overflow-y-auto">
            <div className="space-y-2">
              <Label htmlFor="posto_id">Posto de Trabalho</Label>
              <Select
                value={formData.posto_id}
                onValueChange={(v) => setFormData({ ...formData, posto_id: v })}
              >
                <SelectTrigger id="posto_id">
                  <SelectValue placeholder={postos.length ? 'Selecione o posto' : 'Carregando postos...'} />
                </SelectTrigger>
                <SelectContent>
                  {postos.map((p) => (
                    <SelectItem key={p.id} value={p.id}>
                      {p.name}{p.code ? ` (${p.code})` : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="categoria">Categoria</Label>
                <Select
                  value={formData.categoria}
                  onValueChange={(v) => setFormData({ ...formData, categoria: v })}
                >
                  <SelectTrigger id="categoria">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {CATEGORIAS.map((c) => (
                      <SelectItem key={c} value={c}>{CATEGORIA_LABELS[c]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="nivel">Nível de Risco</Label>
                <Select
                  value={formData.nivel}
                  onValueChange={(v) => setFormData({ ...formData, nivel: v })}
                >
                  <SelectTrigger id="nivel">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {NIVEIS.map((n) => (
                      <SelectItem key={n} value={n}>{NIVEL_LABELS[n]}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="descricao">Descrição do Risco</Label>
              <Input
                id="descricao"
                value={formData.descricao}
                onChange={(e) => setFormData({ ...formData, descricao: e.target.value })}
                placeholder="Ex: Trabalho em pé prolongado 12h"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="fonte_geradora">Fonte Geradora</Label>
              <Input
                id="fonte_geradora"
                value={formData.fonte_geradora}
                onChange={(e) => setFormData({ ...formData, fonte_geradora: e.target.value })}
                placeholder="Ex: Jornada 12x36 em pé"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="medidas_controle">Medidas de Controle (separadas por vírgula)</Label>
              <Input
                id="medidas_controle"
                value={formData.medidas_controle}
                onChange={(e) => setFormData({ ...formData, medidas_controle: e.target.value })}
                placeholder="Ex: Tapete antifadiga, Pausas regulares"
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="epi_recomendado">EPIs Recomendados (separados por vírgula)</Label>
              <Input
                id="epi_recomendado"
                value={formData.epi_recomendado}
                onChange={(e) => setFormData({ ...formData, epi_recomendado: e.target.value })}
                placeholder="Ex: Calçado ergonômico"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setDialogOpen(false); resetForm(); }}>
              Cancelar
            </Button>
            <Button
              onClick={handleSubmit}
              disabled={createRisco.isPending || !formData.posto_id || !formData.categoria || !formData.descricao}
            >
              {createRisco.isPending ? 'Salvando...' : 'Cadastrar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
