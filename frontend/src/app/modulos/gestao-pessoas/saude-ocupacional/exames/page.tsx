'use client';

import { Stethoscope, Calendar, FileCheck, AlertCircle, Clock, CheckCircle, Plus, RefreshCw, Search } from 'lucide-react';
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
import { toast } from 'sonner';
import {
  usePCMSOStatistics,
  useExpiringASOs,
  useScheduleExam,
} from '@/hooks/health-occupational';
import { useASOs, useRegistrarResultadoASO, useASOsRegularizacao, useAgendarASOsLote } from '@/hooks/sst';
import { apiErrorDetail, type ASOItem, type ASORegularizacaoItem } from '@/lib/services/sst';
import { EmployeeSelect, useActiveEmployees } from '@/components/sst/EmployeeSelect';

function getESocialBadge(esocialStatus: string) {
  const styles: Record<string, string> = {
    nao_transmitida: 'bg-gray-100 text-gray-800',
    transmitida: 'bg-blue-100 text-blue-800',
    aceita: 'bg-green-100 text-green-800',
    rejeitada: 'bg-red-100 text-red-800',
    erro: 'bg-red-100 text-red-800',
  };
  const labels: Record<string, string> = {
    nao_transmitida: 'Nao transmitida',
    transmitida: 'Transmitida',
    aceita: 'Aceita',
    rejeitada: 'Rejeitada',
    erro: 'Erro',
  };
  return (
    <Badge className={styles[esocialStatus] || 'bg-gray-100 text-gray-800'}>
      {labels[esocialStatus] || esocialStatus}
    </Badge>
  );
}

export default function ExamesPage() {
  const { data: stats, isLoading: statsLoading } = usePCMSOStatistics();
  const { data: expiringASOs, isLoading: asosLoading, error: asosError, refetch } = useExpiringASOs(30);
  const { data: esocialASOsData, isLoading: esocialASOsLoading, error: esocialASOsError } = useASOs();
  const scheduleExam = useScheduleExam();
  const registrarResultado = useRegistrarResultadoASO();
  const { data: employees } = useActiveEmployees();
  const { data: regularizacao, isLoading: regLoading } = useASOsRegularizacao();
  const agendarLote = useAgendarASOsLote();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [search, setSearch] = useState('');

  // Regularização em lote (ASOs vencidas)
  const [selecionados, setSelecionados] = useState<Set<string>>(new Set());
  const [loteDialogOpen, setLoteDialogOpen] = useState(false);
  const [loteForm, setLoteForm] = useState({
    data_agendamento: '',
    clinica: '',
    tipo: 'periodico',
  });

  const pendentes = regularizacao?.pendentes ?? [];

  const toggleSelecionado = (employeeId: string) => {
    setSelecionados((prev) => {
      const next = new Set(prev);
      if (next.has(employeeId)) next.delete(employeeId);
      else next.add(employeeId);
      return next;
    });
  };

  const toggleTodos = () => {
    setSelecionados((prev) =>
      prev.size === pendentes.length
        ? new Set()
        : new Set(pendentes.map((p: ASORegularizacaoItem) => p.employee_id))
    );
  };

  const handleAgendarLote = async () => {
    if (!loteForm.data_agendamento || selecionados.size === 0) return;
    try {
      const result = await agendarLote.mutateAsync(
        pendentes
          .filter((p: ASORegularizacaoItem) => selecionados.has(p.employee_id))
          .map((p: ASORegularizacaoItem) => ({
            employee_id: p.employee_id,
            data_agendamento: loteForm.data_agendamento,
            clinica: loteForm.clinica || undefined,
            tipo: loteForm.tipo,
          }))
      );
      if (result.total_erros > 0) {
        toast.warning(
          `${result.total_agendados} agendado(s); ${result.total_erros} com erro: ${result.erros
            .map((e) => e.erro)
            .join('; ')}`,
          { duration: 8000 }
        );
      } else {
        toast.success(
          `${result.total_agendados} exame(s) agendado(s) — regularizacao conclui apos registrar o resultado`,
          { duration: 6000 }
        );
      }
      setLoteDialogOpen(false);
      setSelecionados(new Set());
      setLoteForm({ data_agendamento: '', clinica: '', tipo: 'periodico' });
    } catch (error) {
      toast.error(apiErrorDetail(error, 'Erro ao agendar em lote'), { duration: 6000 });
    }
  };

  // Form state para agendar exame
  const [formData, setFormData] = useState({
    funcionario_id: '',
    tipo_exame: '',
    data_agendamento: '',
    clinica: '',
    observacoes: '',
  });

  // Registrar resultado de ASO (S-2220)
  const [resultadoASO, setResultadoASO] = useState<ASOItem | null>(null);
  const [resultadoForm, setResultadoForm] = useState({
    apto: 'true',
    restricoes: '',
    medico: '',
    crm: '',
    observacoes: '',
  });

  const employeeNomeById = (id?: string) =>
    (employees ?? []).find((e) => e.id === id)?.nome ?? null;

  const handleSchedule = async () => {
    if (!formData.funcionario_id || !formData.tipo_exame || !formData.data_agendamento) return;
    try {
      await scheduleExam.mutateAsync(formData as any);
      toast.success('Exame agendado com sucesso', { duration: 4000 });
      setDialogOpen(false);
      setFormData({
        funcionario_id: '',
        tipo_exame: '',
        data_agendamento: '',
        clinica: '',
        observacoes: '',
      });
      refetch();
    } catch (error) {
      toast.error(apiErrorDetail(error, 'Erro ao agendar exame. Tente novamente.'), { duration: 6000 });
    }
  };

  const openResultado = (aso: ASOItem) => {
    setResultadoForm({ apto: 'true', restricoes: '', medico: '', crm: '', observacoes: '' });
    setResultadoASO(aso);
  };

  const handleRegistrarResultado = async () => {
    if (!resultadoASO) return;
    try {
      const result = await registrarResultado.mutateAsync({
        asoId: resultadoASO.aso_id,
        data: {
          apto: resultadoForm.apto === 'true',
          restricoes: resultadoForm.restricoes
            ? resultadoForm.restricoes.split(',').map((r) => r.trim()).filter(Boolean)
            : [],
          medico: resultadoForm.medico || undefined,
          crm: resultadoForm.crm || undefined,
          observacoes: resultadoForm.observacoes || undefined,
        },
      });
      if (result?.esocial?.transmissao_enfileirada) {
        toast.success('Resultado registrado — S-2220 enfileirado no eSocial (recibo real vem depois)', { duration: 6000 });
      } else {
        toast.success('Resultado registrado', { duration: 4000 });
        const motivo = result?.esocial?.motivo || result?.esocial?.erro;
        if (motivo) toast.warning(`eSocial: ${motivo}`, { duration: 6000 });
      }
      setResultadoASO(null);
    } catch (error) {
      toast.error(apiErrorDetail(error, 'Erro ao registrar resultado do ASO'), { duration: 6000 });
    }
  };

  const asosList = Array.isArray(expiringASOs) ? expiringASOs : (expiringASOs as any)?.items ?? [];

  const esocialASOs: ASOItem[] = Array.isArray(esocialASOsData)
    ? (esocialASOsData as ASOItem[])
    : esocialASOsData?.asos ?? esocialASOsData?.items ?? [];

  const filteredASOs = search
    ? asosList.filter((aso: any) =>
        (aso.funcionario_nome || '').toLowerCase().includes(search.toLowerCase()) ||
        (aso.tipo || '').toLowerCase().includes(search.toLowerCase())
      )
    : asosList;

  const getStatusBadge = (status: string) => {
    const map: Record<string, string> = {
      valido: 'bg-green-100 text-green-800',
      vencendo: 'bg-yellow-100 text-yellow-800',
      vencido: 'bg-red-100 text-red-800',
      pendente: 'bg-blue-100 text-blue-800',
    };
    const labels: Record<string, string> = {
      valido: 'Valido',
      vencendo: 'Vencendo',
      vencido: 'Vencido',
      pendente: 'Pendente',
    };
    return <Badge className={map[status] || 'bg-gray-100 text-gray-800'}>{labels[status] || status}</Badge>;
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
            <Stethoscope className="h-6 w-6" />
            Exames Medicos - PCMSO
          </h1>
          <p className="text-muted-foreground">
            Controle de exames ocupacionais e Atestados de Saude Ocupacional conforme NR-7.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleRefresh} disabled={asosLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${asosLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                Agendar Exame
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Agendar Exame Medico</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="funcionario_id">Funcionario</Label>
                  <EmployeeSelect
                    id="funcionario_id"
                    value={formData.funcionario_id}
                    onChange={(employeeId) => setFormData({ ...formData, funcionario_id: employeeId })}
                    placeholder="Busque pelo nome do funcionario..."
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="tipo_exame">Tipo de Exame</Label>
                  <Select
                    value={formData.tipo_exame}
                    onValueChange={(v) => setFormData({ ...formData, tipo_exame: v })}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="Selecione o tipo" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="admissional">Admissional</SelectItem>
                      <SelectItem value="periodico">Periodico</SelectItem>
                      <SelectItem value="retorno_trabalho">Retorno ao Trabalho</SelectItem>
                      <SelectItem value="mudanca_funcao">Mudanca de Função</SelectItem>
                      <SelectItem value="demissional">Demissional</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="data_agendamento">Data do Agendamento</Label>
                  <Input
                    id="data_agendamento"
                    type="date"
                    value={formData.data_agendamento}
                    onChange={(e) => setFormData({ ...formData, data_agendamento: e.target.value })}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="clinica">Clinica</Label>
                  <Input
                    id="clinica"
                    value={formData.clinica}
                    onChange={(e) => setFormData({ ...formData, clinica: e.target.value })}
                    placeholder="Nome da clinica"
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
                <Button variant="outline" onClick={() => setDialogOpen(false)}>
                  Cancelar
                </Button>
                <Button
                  onClick={handleSchedule}
                  disabled={scheduleExam.isPending || !formData.funcionario_id || !formData.tipo_exame || !formData.data_agendamento}
                >
                  {scheduleExam.isPending ? 'Agendando...' : 'Agendar'}
                </Button>
              </DialogFooter>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Exames</CardTitle>
            <Stethoscope className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums">{(stats as any)?.total_exames_ano ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Agendados</CardTitle>
            <Calendar className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{(stats as any)?.exames_pendentes ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">ASOs Validos</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{(stats as any)?.exames_realizados ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">ASOs Vencendo (30d)</CardTitle>
            <Clock className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{(stats as any)?.asos_vencendo_30_dias ?? 0}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Regularização de ASOs vencidas */}
      {!regLoading && regularizacao && regularizacao.funcionarios_pendentes > 0 && (
        <Card className="border-red-200">
          <CardHeader>
            <div className="flex items-start justify-between gap-4">
              <div>
                <CardTitle className="text-base flex items-center gap-2 text-red-700">
                  <AlertCircle className="h-5 w-5" />
                  Regularizacao — {regularizacao.funcionarios_pendentes} funcionario(s) com ASO vencido
                </CardTitle>
                <CardDescription className="mt-1">
                  {regularizacao.registros_aso_vencidos_total} registro(s) de ASO vencidos no total
                  (inclui historicos). Fila priorizada: mais vencido primeiro.
                  {regularizacao.ja_agendados > 0 &&
                    ` ${regularizacao.ja_agendados} ja tem novo exame agendado.`}
                </CardDescription>
              </div>
              <Button
                onClick={() => setLoteDialogOpen(true)}
                disabled={selecionados.size === 0}
                className="shrink-0"
              >
                <Calendar className="h-4 w-4 mr-2" />
                Agendar em lote ({selecionados.size})
              </Button>
            </div>
            {/* Resumo por posto (logística) */}
            {regularizacao.resumo_por_posto.length > 0 && (
              <div className="flex flex-wrap gap-2 pt-3">
                {regularizacao.resumo_por_posto.map((g) => (
                  <Badge key={g.posto_nome} variant="outline" className="font-normal">
                    {g.posto_nome}: <span className="font-semibold ml-1">{g.pendentes}</span>
                  </Badge>
                ))}
              </div>
            )}
          </CardHeader>
          <CardContent className="p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-[44px]">
                    <input
                      type="checkbox"
                      aria-label="Selecionar todos"
                      className="h-4 w-4 accent-primary cursor-pointer"
                      checked={pendentes.length > 0 && selecionados.size === pendentes.length}
                      onChange={toggleTodos}
                    />
                  </TableHead>
                  <TableHead>Funcionario</TableHead>
                  <TableHead>Posto atual</TableHead>
                  <TableHead>Ultimo ASO</TableHead>
                  <TableHead>Venceu em</TableHead>
                  <TableHead>Dias vencido</TableHead>
                  <TableHead>Novo agendamento</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pendentes.map((p) => (
                  <TableRow key={p.employee_id} className={p.ja_agendado ? 'opacity-60' : ''}>
                    <TableCell>
                      <input
                        type="checkbox"
                        aria-label={`Selecionar ${p.nome}`}
                        className="h-4 w-4 accent-primary cursor-pointer"
                        checked={selecionados.has(p.employee_id)}
                        onChange={() => toggleSelecionado(p.employee_id)}
                      />
                    </TableCell>
                    <TableCell>
                      <div className="font-medium">{p.nome}</div>
                      <div className="text-xs text-muted-foreground">{p.cargo || ''}</div>
                    </TableCell>
                    <TableCell className="text-sm">{p.posto_nome}</TableCell>
                    <TableCell className="text-sm">{p.tipo_ultimo_aso || '—'}</TableCell>
                    <TableCell className="text-sm">
                      {new Date(`${p.data_validade}T12:00:00`).toLocaleDateString('pt-BR')}
                    </TableCell>
                    <TableCell>
                      <Badge
                        className={
                          p.dias_vencido > 180
                            ? 'bg-red-100 text-red-800'
                            : p.dias_vencido > 90
                              ? 'bg-orange-100 text-orange-800'
                              : 'bg-yellow-100 text-yellow-800'
                        }
                      >
                        {p.dias_vencido} dias
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm">
                      {p.ja_agendado && p.proxima_data_agendada ? (
                        <span className="text-green-700">
                          {new Date(`${p.proxima_data_agendada}T12:00:00`).toLocaleDateString('pt-BR')}
                        </span>
                      ) : (
                        <span className="text-xs text-muted-foreground">nao agendado</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* Dialog - Agendar em lote */}
      <Dialog open={loteDialogOpen} onOpenChange={setLoteDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Agendar exames em lote</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
              <span className="font-medium">{selecionados.size} funcionario(s) selecionado(s)</span>
              <span className="text-muted-foreground">
                {' '}
                — a data e a clinica abaixo valem para todos.
              </span>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="lote_data">Data do exame</Label>
                <Input
                  id="lote_data"
                  type="date"
                  min={new Date().toISOString().slice(0, 10)}
                  value={loteForm.data_agendamento}
                  onChange={(e) => setLoteForm({ ...loteForm, data_agendamento: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="lote_tipo">Tipo</Label>
                <Select
                  value={loteForm.tipo}
                  onValueChange={(v) => setLoteForm({ ...loteForm, tipo: v })}
                >
                  <SelectTrigger id="lote_tipo">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="periodico">Periodico</SelectItem>
                    <SelectItem value="retorno_trabalho">Retorno ao Trabalho</SelectItem>
                    <SelectItem value="mudanca_funcao">Mudanca de Funcao</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="lote_clinica">Clinica</Label>
              <Input
                id="lote_clinica"
                value={loteForm.clinica}
                onChange={(e) => setLoteForm({ ...loteForm, clinica: e.target.value })}
                placeholder="Nome da clinica (aplicada a todos os selecionados)"
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Agendar NAO regulariza: o ASO so fica em dia depois de registrar o resultado
              (realizado) apos o exame.
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setLoteDialogOpen(false)}>
              Cancelar
            </Button>
            <Button
              onClick={handleAgendarLote}
              disabled={agendarLote.isPending || !loteForm.data_agendamento || selecionados.size === 0}
            >
              {agendarLote.isPending
                ? 'Agendando...'
                : `Agendar ${selecionados.size} exame(s)`}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Alert - ASOs vencendo */}
      {!asosLoading && filteredASOs.length > 0 && (
        <Card className="border-yellow-200 bg-yellow-50/50">
          <CardHeader className="pb-3">
            <CardTitle className="text-sm font-medium flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-yellow-600" />
              ASOs com vencimento nos proximos 30 dias
            </CardTitle>
            <CardDescription>
              {filteredASOs.length} atestado(s) precisam de renovacao em breve.
            </CardDescription>
          </CardHeader>
        </Card>
      )}

      {/* Search Filter */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por nome do funcionario ou tipo de exame..."
                className="pl-10"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {asosError && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar ASOs</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table - ASOs com vencimento proximo */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">ASOs - Vencimento Proximo</CardTitle>
          <CardDescription>
            Lista de Atestados de Saude Ocupacional com vencimento nos proximos 30 dias.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {asosLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : filteredASOs.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileCheck className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum registro encontrado</h3>
              <p className="mt-2">Nao ha ASOs com vencimento proximo ou nenhum resultado para a busca.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Funcionario</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Data Emissao</TableHead>
                  <TableHead>Vencimento</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Clinica</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredASOs.map((aso: any) => (
                  <TableRow key={aso.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">{aso.funcionario_nome || 'N/A'}</div>
                        <div className="text-xs text-muted-foreground">{aso.funcionario_cargo || ''}</div>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{aso.tipo || aso.tipo_exame || '-'}</TableCell>
                    <TableCell className="text-sm">
                      {aso.data_emissao
                        ? new Date(aso.data_emissao).toLocaleDateString('pt-BR')
                        : '-'}
                    </TableCell>
                    <TableCell className="text-sm">
                      {aso.data_vencimento
                        ? new Date(aso.data_vencimento).toLocaleDateString('pt-BR')
                        : '-'}
                    </TableCell>
                    <TableCell>{getStatusBadge(aso.status || 'vencendo')}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {aso.clinica || '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* eSocial - S-2220 (ASOs) */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <FileCheck className="h-4 w-4" />
            eSocial — S-2220 (ASOs)
          </CardTitle>
          <CardDescription>
            Situacao de transmissao dos Atestados de Saude Ocupacional ao eSocial (evento S-2220).
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {esocialASOsLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : esocialASOsError ? (
            <div className="text-center py-8 text-muted-foreground text-sm">
              Erro ao carregar ASOs do eSocial.
            </div>
          ) : esocialASOs.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileCheck className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum ASO registrado</h3>
              <p className="mt-2">Nao ha ASOs para acompanhamento no eSocial.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Funcionario</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>eSocial</TableHead>
                  <TableHead>Recibo S-2220</TableHead>
                  <TableHead className="w-[190px]">Acoes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {esocialASOs.map((aso) => (
                  <TableRow key={aso.aso_id}>
                    <TableCell>
                      <div className="font-medium">
                        {aso.employee_nome || employeeNomeById(aso.employee_id) || (
                          <span className="font-mono text-xs text-muted-foreground">
                            {aso.aso_id.substring(0, 8)}...
                          </span>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{aso.tipo || '—'}</TableCell>
                    <TableCell className="text-sm">{aso.status || '—'}</TableCell>
                    <TableCell>{getESocialBadge(aso.esocial_status)}</TableCell>
                    <TableCell className="text-sm font-mono">{aso.recibo_s2220 || '—'}</TableCell>
                    <TableCell>
                      {aso.status !== 'realizado' ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => openResultado(aso)}
                          title="Registrar o resultado do exame (dispara o S-2220)"
                        >
                          <FileCheck className="h-4 w-4 mr-2" />
                          Registrar resultado
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">Resultado registrado</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Dialog - Registrar resultado de ASO (S-2220) */}
      <Dialog open={!!resultadoASO} onOpenChange={(open) => { if (!open) setResultadoASO(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar Resultado do ASO</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {resultadoASO && (
              <div className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
                <span className="font-medium">
                  {resultadoASO.employee_nome || employeeNomeById(resultadoASO.employee_id) || 'Funcionario nao identificado'}
                </span>
                <span className="text-muted-foreground"> — {resultadoASO.tipo || 'tipo nao informado'}</span>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="resultado_apto">Resultado</Label>
              <Select
                value={resultadoForm.apto}
                onValueChange={(v) => setResultadoForm({ ...resultadoForm, apto: v })}
              >
                <SelectTrigger id="resultado_apto">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="true">Apto</SelectItem>
                  <SelectItem value="false">Inapto</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="resultado_restricoes">Restricoes (separadas por virgula)</Label>
              <Input
                id="resultado_restricoes"
                value={resultadoForm.restricoes}
                onChange={(e) => setResultadoForm({ ...resultadoForm, restricoes: e.target.value })}
                placeholder="Ex: sem trabalho em altura, sem carga acima de 20kg"
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="resultado_medico">Medico</Label>
                <Input
                  id="resultado_medico"
                  value={resultadoForm.medico}
                  onChange={(e) => setResultadoForm({ ...resultadoForm, medico: e.target.value })}
                  placeholder="Nome do medico"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="resultado_crm">CRM</Label>
                <Input
                  id="resultado_crm"
                  value={resultadoForm.crm}
                  onChange={(e) => setResultadoForm({ ...resultadoForm, crm: e.target.value })}
                  placeholder="CRM-AM 0000"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="resultado_obs">Observacoes</Label>
              <Input
                id="resultado_obs"
                value={resultadoForm.observacoes}
                onChange={(e) => setResultadoForm({ ...resultadoForm, observacoes: e.target.value })}
                placeholder="Observacoes adicionais"
              />
            </div>
            <p className="text-xs text-muted-foreground">
              Ao salvar, o ASO vira &quot;realizado&quot; e o evento S-2220 e enfileirado ao eSocial
              (recibo real chega depois, via pull automatico).
            </p>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setResultadoASO(null)}>
              Cancelar
            </Button>
            <Button onClick={handleRegistrarResultado} disabled={registrarResultado.isPending}>
              {registrarResultado.isPending ? 'Salvando...' : 'Registrar resultado'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
