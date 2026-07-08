'use client';

import { FileWarning, AlertTriangle, BarChart3, CalendarClock, Plus, RefreshCw, Send, X } from 'lucide-react';
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
import { useCATs, useCreateAfastamento, useCreateCAT, useTaxaAcidente, useTransmitirCAT } from '@/hooks/sst';
import { apiErrorDetail, type CATCreateResponse, type CATItem } from '@/lib/services/sst';
import { EmployeeSelect, useActiveEmployees, type EmployeeOption } from '@/components/sst/EmployeeSelect';

const CAT_TIPOS = [
  { value: 'tipico', label: 'Tipico (no local de trabalho)' },
  { value: 'trajeto', label: 'Trajeto (casa-trabalho)' },
  { value: 'doenca', label: 'Doenca ocupacional' },
] as const;

const CAT_TIPO_AFASTAMENTO: Record<string, string> = {
  tipico: 'acidente_trabalho',
  trajeto: 'acidente_trajeto',
  doenca: 'doenca',
};

function getGravidadeBadge(gravidade: string) {
  const styles: Record<string, string> = {
    leve: 'bg-green-100 text-green-800',
    medio: 'bg-yellow-100 text-yellow-800',
    grave: 'bg-orange-100 text-orange-800',
    critico: 'bg-red-100 text-red-800',
  };
  const labels: Record<string, string> = {
    leve: 'Leve',
    medio: 'Medio',
    grave: 'Grave',
    critico: 'Critico',
  };
  return (
    <Badge className={styles[gravidade] || 'bg-gray-100 text-gray-800'}>
      {labels[gravidade] || gravidade}
    </Badge>
  );
}

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

/** Compara datas locais (YYYY-MM-DD) sem fuso: -1 antes, 0 igual, 1 depois */
function compararComHoje(dataISO: string): number {
  const hoje = new Date();
  const hojeStr = `${hoje.getFullYear()}-${String(hoje.getMonth() + 1).padStart(2, '0')}-${String(hoje.getDate()).padStart(2, '0')}`;
  if (hojeStr < dataISO) return -1;
  if (hojeStr === dataISO) return 0;
  return 1;
}

function getPrazoCell(cat: CATItem) {
  if (!cat.deadline_transmissao) {
    return <span className="text-muted-foreground">—</span>;
  }
  const dataFormatada = new Date(`${cat.deadline_transmissao}T00:00:00`).toLocaleDateString('pt-BR');
  const naoTransmitida = cat.esocial_status === 'nao_transmitida';
  const comparacao = compararComHoje(cat.deadline_transmissao);

  if (naoTransmitida && comparacao > 0) {
    return (
      <span className="flex items-center gap-1 font-medium text-red-600">
        <AlertTriangle className="h-4 w-4" />
        {dataFormatada}
      </span>
    );
  }
  if (naoTransmitida && comparacao === 0) {
    return <span className="font-medium text-yellow-600">{dataFormatada}</span>;
  }
  return <span>{dataFormatada}</span>;
}

function getStatusBadge(status: string) {
  const styles: Record<string, string> = {
    aberta: 'bg-blue-100 text-blue-800',
    em_analise: 'bg-yellow-100 text-yellow-800',
    encerrada: 'bg-green-100 text-green-800',
    cancelada: 'bg-gray-100 text-gray-800',
  };
  const labels: Record<string, string> = {
    aberta: 'Aberta',
    em_analise: 'Em Analise',
    encerrada: 'Encerrada',
    cancelada: 'Cancelada',
  };
  return (
    <Badge className={styles[status] || 'bg-gray-100 text-gray-800'}>
      {labels[status] || status}
    </Badge>
  );
}

const CAT_FORM_INICIAL = {
  employee_id: '',
  tipo_acidente: 'tipico',
  data_acidente: '',
  hora_acidente: '',
  local: '',
  descricao: '',
  gravidade: 'leve',
  houve_afastamento: false,
  dias_afastamento: '',
};

export default function CATPage() {
  const { data: catsData, isLoading: catsLoading, error: catsError, refetch } = useCATs();
  const { data: taxaData, isLoading: taxaLoading } = useTaxaAcidente();
  const transmitirCAT = useTransmitirCAT();
  const createCAT = useCreateCAT();
  const createAfastamento = useCreateAfastamento();
  const { data: employees } = useActiveEmployees();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [form, setForm] = useState({ ...CAT_FORM_INICIAL });
  const [selectedEmployee, setSelectedEmployee] = useState<EmployeeOption | null>(null);
  const [ultimaCAT, setUltimaCAT] = useState<CATCreateResponse | null>(null);

  const employeeNomeById = (id: string) =>
    (employees ?? []).find((e) => e.id === id)?.nome ?? null;

  const formValido =
    !!form.employee_id &&
    !!form.data_acidente &&
    !!form.local.trim() &&
    form.descricao.trim().length >= 10;

  const handleAbrirCAT = async () => {
    if (!formValido) return;
    // A hora nao tem campo proprio no S-2210 do backend (que persiste a DATA);
    // registramos a hora dentro da descricao para nao perder o dado.
    const descricao = form.hora_acidente
      ? `[Hora do acidente: ${form.hora_acidente}] ${form.descricao.trim()}`
      : form.descricao.trim();
    try {
      const result = await createCAT.mutateAsync({
        employee_id: form.employee_id,
        tipo_acidente: form.tipo_acidente,
        data_acidente: form.data_acidente,
        local: form.local.trim(),
        descricao,
        gravidade: form.gravidade,
      });
      setUltimaCAT(result);
      if (result?.esocial?.transmissao_enfileirada) {
        toast.success('CAT aberta — S-2210 enfileirado ao eSocial (recibo real vem depois)', { duration: 6000 });
      } else {
        toast.success('CAT aberta', { duration: 4000 });
        const motivo = result?.esocial?.motivo || result?.esocial?.erro;
        if (motivo) toast.warning(`eSocial: ${motivo}`, { duration: 6000 });
      }

      // Houve afastamento? Registra tambem o afastamento (S-2230) vinculado ao acidente.
      if (form.houve_afastamento) {
        try {
          const dias = parseInt(form.dias_afastamento, 10);
          await createAfastamento.mutateAsync({
            employee_id: form.employee_id,
            employee_nome: selectedEmployee?.nome ?? '',
            employee_cargo: selectedEmployee?.cargo ?? undefined,
            tipo: CAT_TIPO_AFASTAMENTO[form.tipo_acidente] ?? 'acidente_trabalho',
            motivo: `Afastamento decorrente de CAT (${form.tipo_acidente}) em ${form.data_acidente}`,
            data_inicio: form.data_acidente,
            ...(Number.isFinite(dias) && dias > 0 ? { dias_previstos: dias } : {}),
          });
          toast.success('Afastamento registrado a partir da CAT (S-2230)', { duration: 5000 });
        } catch (error) {
          toast.error(apiErrorDetail(error, 'CAT criada, mas o afastamento falhou — registre na tela de Afastamentos'), { duration: 8000 });
        }
      }

      setDialogOpen(false);
      setForm({ ...CAT_FORM_INICIAL });
      setSelectedEmployee(null);
    } catch (error) {
      toast.error(apiErrorDetail(error, 'Erro ao abrir CAT'), { duration: 6000 });
    }
  };

  const handleTransmitir = async (catId: string) => {
    try {
      const result = await transmitirCAT.mutateAsync(catId);
      if (result?.esocial?.transmissao_enfileirada) {
        toast.success('Transmissao enfileirada — aguardando protocolo real', { duration: 5000 });
      } else {
        const motivo = result?.esocial?.motivo || result?.esocial?.erro || 'Transmissao nao enfileirada';
        toast.error(motivo, { duration: 6000 });
      }
    } catch (error) {
      toast.error(apiErrorDetail(error, 'Erro ao transmitir CAT ao eSocial'), { duration: 6000 });
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

  const cats = catsData?.cats ?? [];
  const totalCATs = catsData?.total ?? 0;
  const taxaAcidente = taxaData?.taxa_acidente_percentual ?? 0;
  const totalColaboradores = taxaData?.total_colaboradores ?? 0;

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2 text-[hsl(var(--foreground))]">
            <FileWarning className="h-6 w-6" />
            CAT - Comunicacao de Acidente de Trabalho
          </h1>
          <p className="text-muted-foreground">
            Registro e acompanhamento de acidentes de trabalho
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            CAT: prazo legal de 1 dia util apos o acidente (Lei 8.213/91)
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleRefresh} disabled={catsLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${catsLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => setDialogOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Abrir CAT
          </Button>
        </div>
      </div>

      {/* DESTAQUE - CAT recem-aberta: prazo legal de transmissao */}
      {ultimaCAT && (
        <Card className="border-orange-300 bg-orange-50/60 dark:border-orange-500/40 dark:bg-orange-500/10">
          <CardHeader className="pb-3">
            <div className="flex items-start justify-between gap-2">
              <CardTitle className="text-sm font-medium flex items-center gap-2">
                <CalendarClock className="h-4 w-4 text-orange-600" />
                CAT aberta — prazo legal de transmissao
              </CardTitle>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6"
                onClick={() => setUltimaCAT(null)}
                aria-label="Fechar destaque"
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-2 pt-0">
            <div className="flex flex-wrap items-center gap-x-6 gap-y-2 text-sm">
              <div>
                <span className="text-muted-foreground">Funcionario: </span>
                <span className="font-medium">
                  {employeeNomeById(ultimaCAT.employee_id) || ultimaCAT.employee_id}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Transmitir ate: </span>
                <span className="font-data text-base font-bold text-orange-700 dark:text-orange-400">
                  {ultimaCAT.deadline_transmissao
                    ? new Date(`${ultimaCAT.deadline_transmissao}T00:00:00`).toLocaleDateString('pt-BR')
                    : 'data do acidente nao informada'}
                </span>
                <span className="ml-1 text-xs text-muted-foreground">(1º dia util apos o acidente)</span>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-muted-foreground">eSocial:</span>
                {ultimaCAT.esocial?.transmissao_enfileirada ? (
                  <Badge className="bg-blue-100 text-blue-800">S-2210 enfileirado</Badge>
                ) : (
                  <Badge className="bg-red-100 text-red-800">Nao enfileirado</Badge>
                )}
              </div>
            </div>
            <p className="text-xs text-muted-foreground">{ultimaCAT.prazo_legal}</p>
            {!ultimaCAT.esocial?.transmissao_enfileirada && (ultimaCAT.esocial?.motivo || ultimaCAT.esocial?.erro) && (
              <p className="text-xs text-destructive">{ultimaCAT.esocial?.motivo || ultimaCAT.esocial?.erro}</p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total de CATs</CardTitle>
            <FileWarning className="h-4 w-4" style={{ color: '#FF6B35' }} />
          </CardHeader>
          <CardContent>
            {catsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums" style={{ color: '#FF6B35' }}>{totalCATs}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Taxa de Acidente</CardTitle>
            <BarChart3 className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {taxaLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{taxaAcidente.toFixed(2)}%</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Colaboradores</CardTitle>
            <BarChart3 className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {taxaLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{totalColaboradores}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {catsError && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar CATs</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Registro de CATs</CardTitle>
          <CardDescription>
            Lista de Comunicacoes de Acidente de Trabalho registradas.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {catsLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : cats.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileWarning className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhuma CAT registrada</h3>
              <p className="mt-2">Nao ha Comunicacoes de Acidente de Trabalho no sistema.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Funcionario</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead>Local</TableHead>
                  <TableHead>Gravidade</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>eSocial</TableHead>
                  <TableHead>Recibo</TableHead>
                  <TableHead>Prazo</TableHead>
                  <TableHead className="w-[180px]">Acoes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cats.map((cat) => (
                  <TableRow key={cat.cat_id}>
                    <TableCell>
                      <div className="font-medium">
                        {employeeNomeById(cat.employee_id) || (
                          <span className="font-mono text-xs text-muted-foreground">
                            {cat.cat_id.length > 12 ? `${cat.cat_id.substring(0, 12)}...` : cat.cat_id}
                          </span>
                        )}
                      </div>
                      <div className="font-mono text-xs text-muted-foreground">
                        {cat.cat_id.length > 22 ? `${cat.cat_id.substring(0, 22)}...` : cat.cat_id}
                      </div>
                    </TableCell>
                    <TableCell className="text-sm">{cat.tipo}</TableCell>
                    <TableCell className="text-sm">
                      {new Date(cat.data).toLocaleDateString('pt-BR')}
                    </TableCell>
                    <TableCell className="text-sm">{cat.local}</TableCell>
                    <TableCell>{getGravidadeBadge(cat.gravidade)}</TableCell>
                    <TableCell>{getStatusBadge(cat.status)}</TableCell>
                    <TableCell>{getESocialBadge(cat.esocial_status)}</TableCell>
                    <TableCell className="text-sm font-mono">
                      {cat.recibo_esocial || '—'}
                    </TableCell>
                    <TableCell className="text-sm">{getPrazoCell(cat)}</TableCell>
                    <TableCell>
                      {['nao_transmitida', 'erro', 'rejeitada'].includes(cat.esocial_status) && !cat.recibo_esocial ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleTransmitir(cat.cat_id)}
                          disabled={transmitirCAT.isPending}
                          title="Transmitir S-2210 ao eSocial"
                        >
                          <Send className="h-4 w-4 mr-2" />
                          {transmitirCAT.isPending && transmitirCAT.variables === cat.cat_id
                            ? 'Enviando...'
                            : 'Transmitir ao eSocial'}
                        </Button>
                      ) : (
                        <span className="text-xs text-muted-foreground">
                          {cat.recibo_esocial ? 'Recibo real recebido' : 'Aguardando recibo'}
                        </span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Dialog - Abrir CAT */}
      <Dialog
        open={dialogOpen}
        onOpenChange={(open) => {
          setDialogOpen(open);
          if (!open) {
            setForm({ ...CAT_FORM_INICIAL });
            setSelectedEmployee(null);
          }
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>Abrir CAT</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="cat_funcionario">Funcionario</Label>
              <EmployeeSelect
                id="cat_funcionario"
                value={form.employee_id}
                onChange={(employeeId, employee) => {
                  setForm({ ...form, employee_id: employeeId });
                  setSelectedEmployee(employee);
                }}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="cat_data">Data do acidente</Label>
                <Input
                  id="cat_data"
                  type="date"
                  value={form.data_acidente}
                  onChange={(e) => setForm({ ...form, data_acidente: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cat_hora">Hora do acidente</Label>
                <Input
                  id="cat_hora"
                  type="time"
                  value={form.hora_acidente}
                  onChange={(e) => setForm({ ...form, hora_acidente: e.target.value })}
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="cat_tipo">Tipo</Label>
                <Select
                  value={form.tipo_acidente}
                  onValueChange={(v) => setForm({ ...form, tipo_acidente: v })}
                >
                  <SelectTrigger id="cat_tipo">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CAT_TIPOS.map((t) => (
                      <SelectItem key={t.value} value={t.value}>
                        {t.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="cat_gravidade">Gravidade</Label>
                <Select
                  value={form.gravidade}
                  onValueChange={(v) => setForm({ ...form, gravidade: v })}
                >
                  <SelectTrigger id="cat_gravidade">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="leve">Leve</SelectItem>
                    <SelectItem value="medio">Medio</SelectItem>
                    <SelectItem value="grave">Grave</SelectItem>
                    <SelectItem value="critico">Critico</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="cat_local">Local do acidente</Label>
              <Input
                id="cat_local"
                value={form.local}
                onChange={(e) => setForm({ ...form, local: e.target.value })}
                placeholder="Ex: Portaria do Condominio X, Av. Torres, Manaus-AM"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="cat_descricao">Descricao (minimo 10 caracteres)</Label>
              <Textarea
                id="cat_descricao"
                value={form.descricao}
                onChange={(e) => setForm({ ...form, descricao: e.target.value })}
                placeholder="Descreva o que aconteceu, como e em que circunstancias"
                rows={3}
              />
            </div>
            <div className="flex items-center justify-between rounded-md border px-3 py-2">
              <div>
                <Label htmlFor="cat_afastamento" className="cursor-pointer">Houve afastamento?</Label>
                <p className="text-xs text-muted-foreground">
                  Registra tambem o afastamento (S-2230) a partir da data do acidente.
                </p>
              </div>
              <Switch
                id="cat_afastamento"
                checked={form.houve_afastamento}
                onCheckedChange={(checked) => setForm({ ...form, houve_afastamento: checked })}
              />
            </div>
            {form.houve_afastamento && (
              <div className="space-y-2">
                <Label htmlFor="cat_dias">Dias previstos de afastamento (opcional)</Label>
                <Input
                  id="cat_dias"
                  type="number"
                  min={1}
                  value={form.dias_afastamento}
                  onChange={(e) => setForm({ ...form, dias_afastamento: e.target.value })}
                  placeholder="Ex: 15"
                />
              </div>
            )}
            <p className="text-xs text-muted-foreground">
              Ao abrir, o S-2210 e enfileirado ao eSocial automaticamente. Prazo legal:
              1 dia util apos o acidente (Lei 8.213/91, Art. 22).
            </p>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setDialogOpen(false);
                setForm({ ...CAT_FORM_INICIAL });
                setSelectedEmployee(null);
              }}
            >
              Cancelar
            </Button>
            <Button onClick={handleAbrirCAT} disabled={createCAT.isPending || !formValido}>
              {createCAT.isPending ? 'Abrindo...' : 'Abrir CAT'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
