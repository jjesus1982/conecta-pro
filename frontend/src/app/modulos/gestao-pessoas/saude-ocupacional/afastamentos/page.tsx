'use client';

import { UserX, AlertTriangle, DollarSign, Clock, Plus, RefreshCw, ShieldCheck, Undo2 } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Switch } from '@/components/ui/switch';
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
  useAfastamentos,
  useAjudaMedicamento,
  useCreateAfastamento,
  useRegistrarRetorno,
} from '@/hooks/sst';
import {
  AFASTAMENTO_TIPOS,
  apiErrorDetail,
  type Afastamento,
} from '@/lib/services/sst';
import { EmployeeSelect, type EmployeeOption } from '@/components/sst/EmployeeSelect';

const TIPO_LABELS: Record<string, string> = Object.fromEntries(
  AFASTAMENTO_TIPOS.map((t) => [t.value, t.label])
);

function getESocialBadge(esocialStatus?: string) {
  if (!esocialStatus) {
    return <span className="text-xs text-muted-foreground">—</span>;
  }
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

function getStatusBadge(status: string) {
  const styles: Record<string, string> = {
    ativo: 'bg-yellow-100 text-yellow-800',
    encerrado: 'bg-green-100 text-green-800',
    prorrogado: 'bg-red-100 text-red-800',
  };
  const labels: Record<string, string> = {
    ativo: 'Ativo',
    encerrado: 'Encerrado',
    prorrogado: 'Prorrogado',
  };
  return (
    <Badge className={styles[status] || 'bg-gray-100 text-gray-800'}>
      {labels[status] || status}
    </Badge>
  );
}

function isVencido(data_fim_prevista: string | null, status: string): boolean {
  if (!data_fim_prevista || status !== 'ativo') return false;
  return new Date(data_fim_prevista) < new Date();
}

const AFASTAMENTO_FORM_INICIAL = {
  employee_id: '',
  tipo: 'doenca',
  motivo: '',
  data_inicio: '',
  dias_previstos: '',
  atestado: true,
  cid: '',
  medico: '',
  crm: '',
};

export default function AfastamentosPage() {
  const {
    data: afastamentosData,
    isLoading,
    error,
    refetch,
  } = useAfastamentos();
  const { data: ajudaData } = useAjudaMedicamento();
  const createAfastamento = useCreateAfastamento();
  const registrarRetorno = useRegistrarRetorno();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({ ...AFASTAMENTO_FORM_INICIAL });
  const [selectedEmployee, setSelectedEmployee] = useState<EmployeeOption | null>(null);

  // Registrar retorno
  const [retornoAfastamento, setRetornoAfastamento] = useState<Afastamento | null>(null);
  const [dataRetorno, setDataRetorno] = useState('');

  const tipoSelecionado = AFASTAMENTO_TIPOS.find((t) => t.value === form.tipo);
  const formValido = !!form.employee_id && !!form.tipo && !!form.data_inicio;

  const resetForm = () => {
    setForm({ ...AFASTAMENTO_FORM_INICIAL });
    setSelectedEmployee(null);
  };

  const handleRegistrar = async () => {
    if (!formValido) return;
    try {
      const dias = parseInt(form.dias_previstos, 10);
      const result = await createAfastamento.mutateAsync({
        employee_id: form.employee_id,
        employee_nome: selectedEmployee?.nome ?? '',
        employee_cargo: selectedEmployee?.cargo ?? undefined,
        tipo: form.tipo,
        motivo: form.motivo.trim() || undefined,
        data_inicio: form.data_inicio,
        ...(Number.isFinite(dias) && dias > 0 ? { dias_previstos: dias } : {}),
        atestado: form.atestado,
        cid: form.cid.trim() || undefined,
        medico: form.medico.trim() || undefined,
        crm: form.crm.trim() || undefined,
      });
      if (result?.esocial?.transmissao_enfileirada) {
        toast.success('Afastamento registrado — S-2230 enfileirado ao eSocial (recibo real vem depois)', { duration: 6000 });
      } else {
        toast.success('Afastamento registrado', { duration: 4000 });
        const motivo = result?.esocial?.motivo || result?.esocial?.erro;
        if (motivo) toast.warning(`eSocial: ${motivo}`, { duration: 7000 });
      }
      if (result?.gera_estabilidade) {
        toast.info(
          `Este afastamento gera ESTABILIDADE CCT de 12 meses${result.estabilidade_ate ? ` (ate ${new Date(`${result.estabilidade_ate}T00:00:00`).toLocaleDateString('pt-BR')})` : ''}`,
          { duration: 8000 }
        );
      }
      setDialogOpen(false);
      resetForm();
    } catch (err) {
      toast.error(apiErrorDetail(err, 'Erro ao registrar afastamento'), { duration: 6000 });
    }
  };

  const handleRegistrarRetorno = async () => {
    if (!retornoAfastamento || !dataRetorno) return;
    try {
      const result = await registrarRetorno.mutateAsync({
        id: retornoAfastamento.id,
        data_retorno: dataRetorno,
      });
      if (result?.esocial?.transmissao_enfileirada) {
        toast.success('Retorno registrado — S-2230 de termino enfileirado ao eSocial', { duration: 6000 });
      } else {
        toast.success('Retorno registrado', { duration: 4000 });
      }
      if (result?.gera_estabilidade && result?.estabilidade_ate) {
        toast.info(
          `Estabilidade CCT recalculada ate ${new Date(`${result.estabilidade_ate}T00:00:00`).toLocaleDateString('pt-BR')}`,
          { duration: 8000 }
        );
      }
      setRetornoAfastamento(null);
      setDataRetorno('');
    } catch (err) {
      toast.error(apiErrorDetail(err, 'Erro ao registrar retorno'), { duration: 6000 });
    }
  };

  const handleRefresh = async () => {
    try {
      await refetch();
      toast.success('Dados atualizados', { duration: 4000 });
    } catch {
      toast.error('Erro ao atualizar dados', { duration: 5000 });
    }
  };

  const afastamentos = afastamentosData?.afastamentos ?? [];
  const totalAfastados = afastamentos.filter((a) => a.status === 'ativo').length;
  const totalRegistros = afastamentosData?.total ?? 0;
  const taxaAfastamento =
    totalRegistros > 0
      ? ((totalAfastados / Math.max(totalRegistros, 1)) * 100).toFixed(1)
      : '0.0';
  const custoMensal = ajudaData?.custo_mensal_total ?? 0;

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2 text-[hsl(var(--foreground))]">
            <UserX className="h-6 w-6" />
            Afastamentos
          </h1>
          <p className="text-muted-foreground">
            Controle de afastamentos de colaboradores - SST
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Registrar afastamento
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Afastados Ativos</CardTitle>
            <UserX className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{totalAfastados}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Taxa de Afastamento</CardTitle>
            <Clock className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{taxaAfastamento}%</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Custo Mensal Ajuda Medicamento</CardTitle>
            <DollarSign className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                {custoMensal.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar afastamentos</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Lista de Afastamentos</CardTitle>
          <CardDescription>
            Registro de todos os afastamentos de colaboradores.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : afastamentos.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <UserX className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum afastamento registrado</h3>
              <p className="mt-2">Nao ha afastamentos cadastrados no sistema.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Inicio</TableHead>
                  <TableHead>Fim Previsto</TableHead>
                  <TableHead>Dias</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>eSocial</TableHead>
                  <TableHead>Recibo S-2230</TableHead>
                  <TableHead className="w-[170px]">Acoes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {afastamentos.map((af) => (
                  <TableRow key={af.id}>
                    <TableCell>
                      <div className="font-medium">{af.employee_nome}</div>
                      <div className="text-xs text-muted-foreground">{af.employee_cargo}</div>
                    </TableCell>
                    <TableCell className="text-sm">
                      <div className="flex flex-col items-start gap-1">
                        <span>{TIPO_LABELS[af.tipo] || af.tipo}</span>
                        {af.gera_estabilidade && (
                          <Badge className="bg-violet-100 text-violet-800 flex items-center gap-1">
                            <ShieldCheck className="h-3 w-3" />
                            Estabilidade
                            {af.estabilidade_ate
                              ? ` ate ${new Date(`${af.estabilidade_ate}T00:00:00`).toLocaleDateString('pt-BR')}`
                              : ''}
                          </Badge>
                        )}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">
                      {new Date(af.data_inicio).toLocaleDateString('pt-BR')}
                    </TableCell>
                    <TableCell className="text-sm">
                      <span className="flex items-center gap-1">
                        {af.data_retorno
                          ? `Retornou ${new Date(af.data_retorno).toLocaleDateString('pt-BR')}`
                          : af.data_fim_prevista
                            ? new Date(af.data_fim_prevista).toLocaleDateString('pt-BR')
                            : 'Indeterminado'}
                        {isVencido(af.data_fim_prevista, af.status) && (
                          <AlertTriangle className="h-4 w-4 text-red-500" />
                        )}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm">
                      {af.dias_previstos ?? '-'}
                    </TableCell>
                    <TableCell>{getStatusBadge(af.status)}</TableCell>
                    <TableCell>{getESocialBadge(af.esocial_status)}</TableCell>
                    <TableCell className="text-sm font-mono">{af.recibo_s2230 || '—'}</TableCell>
                    <TableCell>
                      {af.status === 'ativo' ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => {
                            setRetornoAfastamento(af);
                            setDataRetorno('');
                          }}
                          title="Registrar a data real de retorno (S-2230 de termino)"
                        >
                          <Undo2 className="h-4 w-4 mr-2" />
                          Registrar retorno
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">Encerrado</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Dialog - Registrar afastamento */}
      <Dialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) resetForm();
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Registrar Afastamento</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="af_funcionario">Funcionario</Label>
              <EmployeeSelect
                id="af_funcionario"
                value={form.employee_id}
                onChange={(employeeId, employee) => {
                  setForm({ ...form, employee_id: employeeId });
                  setSelectedEmployee(employee);
                }}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="af_tipo">Tipo de afastamento</Label>
              <Select value={form.tipo} onValueChange={(v) => setForm({ ...form, tipo: v })}>
                <SelectTrigger id="af_tipo">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AFASTAMENTO_TIPOS.map((t) => (
                    <SelectItem key={t.value} value={t.value}>
                      {t.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {tipoSelecionado?.autoS2230
                  ? 'Este tipo transmite o S-2230 ao eSocial automaticamente (Tabela 18).'
                  : 'Este tipo NAO transmite automaticamente — exige classificacao humana no eSocial.'}
              </p>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="af_inicio">Data de inicio</Label>
                <Input
                  id="af_inicio"
                  type="date"
                  value={form.data_inicio}
                  onChange={(e) => setForm({ ...form, data_inicio: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="af_dias">Dias previstos (opcional)</Label>
                <Input
                  id="af_dias"
                  type="number"
                  min={1}
                  value={form.dias_previstos}
                  onChange={(e) => setForm({ ...form, dias_previstos: e.target.value })}
                  placeholder="Ex: 15"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="af_cid">CID (opcional)</Label>
                <Input
                  id="af_cid"
                  value={form.cid}
                  onChange={(e) => setForm({ ...form, cid: e.target.value })}
                  placeholder="Ex: M54.5"
                />
                <p className="text-xs text-muted-foreground">
                  CID de causa externa (V/W/X/Y) gera estabilidade CCT.
                </p>
              </div>
              <div className="flex items-center justify-between rounded-md border px-3 py-2 self-start mt-7">
                <Label htmlFor="af_atestado" className="cursor-pointer text-sm">Com atestado</Label>
                <Switch
                  id="af_atestado"
                  checked={form.atestado}
                  onCheckedChange={(checked) => setForm({ ...form, atestado: checked })}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="af_medico">Medico (opcional)</Label>
                <Input
                  id="af_medico"
                  value={form.medico}
                  onChange={(e) => setForm({ ...form, medico: e.target.value })}
                  placeholder="Nome do medico"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="af_crm">CRM (opcional)</Label>
                <Input
                  id="af_crm"
                  value={form.crm}
                  onChange={(e) => setForm({ ...form, crm: e.target.value })}
                  placeholder="CRM-AM 0000"
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="af_motivo">Motivo (opcional)</Label>
              <Textarea
                id="af_motivo"
                value={form.motivo}
                onChange={(e) => setForm({ ...form, motivo: e.target.value })}
                placeholder="Detalhes do afastamento"
                rows={2}
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDialogOpen(false);
                resetForm();
              }}
            >
              Cancelar
            </Button>
            <Button onClick={handleRegistrar} disabled={createAfastamento.isPending || !formValido}>
              {createAfastamento.isPending ? 'Registrando...' : 'Registrar afastamento'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog - Registrar retorno */}
      <Dialog
        open={!!retornoAfastamento}
        onOpenChange={(open) => {
          if (!open) {
            setRetornoAfastamento(null);
            setDataRetorno('');
          }
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Registrar Retorno</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            {retornoAfastamento && (
              <div className="rounded-md border bg-muted/40 px-3 py-2 text-sm">
                <span className="font-medium">{retornoAfastamento.employee_nome}</span>
                <span className="text-muted-foreground">
                  {' '}— {TIPO_LABELS[retornoAfastamento.tipo] || retornoAfastamento.tipo}, desde{' '}
                  {new Date(retornoAfastamento.data_inicio).toLocaleDateString('pt-BR')}
                </span>
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="af_retorno">Data do retorno</Label>
              <Input
                id="af_retorno"
                type="date"
                value={dataRetorno}
                onChange={(e) => setDataRetorno(e.target.value)}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              O retorno encerra o afastamento, recalcula a estabilidade CCT (quando aplicavel)
              e retransmite o S-2230 com o termino ao eSocial.
            </p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setRetornoAfastamento(null);
                setDataRetorno('');
              }}
            >
              Cancelar
            </Button>
            <Button onClick={handleRegistrarRetorno} disabled={registrarRetorno.isPending || !dataRetorno}>
              {registrarRetorno.isPending ? 'Registrando...' : 'Registrar retorno'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
