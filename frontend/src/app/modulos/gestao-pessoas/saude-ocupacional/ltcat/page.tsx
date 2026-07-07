'use client';

import { useState } from 'react';
import { FileText, Building2, AlertTriangle, RefreshCw, ShieldCheck, Clock, UserCheck, Pencil } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
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
import { useLTCATStatus, useUpdateLTCAT } from '@/hooks/sst';
import type { LTCATStatusValor, LTCATUpdatePayload } from '@/lib/services/sst';

const STATUS_CONFIG: Record<string, { label: string; className: string }> = {
  vigente: { label: 'Vigente', className: 'bg-green-100 text-green-800' },
  pendente_elaboracao: { label: 'Pendente Elaboracao', className: 'bg-yellow-100 text-yellow-800' },
  em_elaboracao: { label: 'Em Elaboracao', className: 'bg-blue-100 text-blue-800' },
  vencido: { label: 'Vencido', className: 'bg-red-100 text-red-800' },
};

const STATUS_OPTIONS: { value: LTCATStatusValor; label: string }[] = [
  { value: 'pendente_elaboracao', label: 'Pendente Elaboracao' },
  { value: 'em_elaboracao', label: 'Em Elaboracao' },
  { value: 'vigente', label: 'Vigente' },
  { value: 'vencido', label: 'Vencido' },
];

const TIPO_RISCO_CONFIG: Record<string, { label: string; className: string }> = {
  fisico: { label: 'Fisico', className: 'bg-blue-100 text-blue-800' },
  'f\u00edsico': { label: 'Fisico', className: 'bg-blue-100 text-blue-800' },
  quimico: { label: 'Quimico', className: 'bg-purple-100 text-purple-800' },
  'qu\u00edmico': { label: 'Quimico', className: 'bg-purple-100 text-purple-800' },
  biologico: { label: 'Biologico', className: 'bg-green-100 text-green-800' },
  'biol\u00f3gico': { label: 'Biologico', className: 'bg-green-100 text-green-800' },
  ergonomico: { label: 'Ergonomico', className: 'bg-orange-100 text-orange-800' },
  'ergon\u00f4mico': { label: 'Ergonomico', className: 'bg-orange-100 text-orange-800' },
  acidente: { label: 'Acidente', className: 'bg-red-100 text-red-800' },
};

function getTipoRiscoBadge(tipo: string) {
  const config = TIPO_RISCO_CONFIG[tipo.toLowerCase()] ?? {
    label: tipo,
    className: 'bg-gray-100 text-gray-800',
  };
  return <Badge className={config.className}>{config.label}</Badge>;
}

function getStatusBadge(status: string) {
  const config = STATUS_CONFIG[status] ?? {
    label: status,
    className: 'bg-gray-100 text-gray-800',
  };
  return <Badge className={config.className}>{config.label}</Badge>;
}

export default function LTCATPage() {
  const { data, isLoading, error, refetch } = useLTCATStatus();
  const updateLTCAT = useUpdateLTCAT();

  const [editOpen, setEditOpen] = useState(false);
  const [editForm, setEditForm] = useState<{
    status: string;
    responsavel_tecnico: string;
    registro_conselho: string;
    validade_inicio: string;
    validade_fim: string;
    observacoes: string;
  }>({
    status: '',
    responsavel_tecnico: '',
    registro_conselho: '',
    validade_inicio: '',
    validade_fim: '',
    observacoes: '',
  });

  const openEdit = () => {
    const responsavel = data?.responsavel_tecnico ?? '';
    setEditForm({
      status: STATUS_CONFIG[data?.status ?? ''] ? (data?.status as string) : '',
      responsavel_tecnico: responsavel.startsWith('aguardando dado') ? '' : responsavel,
      registro_conselho: data?.registro_conselho ?? '',
      validade_inicio: '',
      validade_fim: '',
      observacoes: data?.observacoes ?? '',
    });
    setEditOpen(true);
  };

  const handleSaveEdit = async () => {
    const payload: LTCATUpdatePayload = {};
    if (editForm.status) payload.status = editForm.status as LTCATStatusValor;
    if (editForm.responsavel_tecnico.trim()) payload.responsavel_tecnico = editForm.responsavel_tecnico.trim();
    if (editForm.registro_conselho.trim()) payload.registro_conselho = editForm.registro_conselho.trim();
    if (editForm.validade_inicio) payload.validade_inicio = editForm.validade_inicio;
    if (editForm.validade_fim) payload.validade_fim = editForm.validade_fim;
    if (editForm.observacoes.trim()) payload.observacoes = editForm.observacoes.trim();

    if (Object.keys(payload).length === 0) {
      toast.error('Preencha ao menos um campo para atualizar', { duration: 5000 });
      return;
    }

    try {
      await updateLTCAT.mutateAsync(payload);
      toast.success('LTCAT atualizado com sucesso', { duration: 4000 });
      setEditOpen(false);
      refetch();
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Erro ao atualizar LTCAT', { duration: 6000 });
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

  const fatoresRisco = data?.fatores_risco ?? [];
  const postosAvaliados = data?.postos_avaliados ?? 0;
  const totalAgentes = fatoresRisco.length;

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))] flex items-center gap-2">
            <FileText className="h-6 w-6" />
            LTCAT - Laudo Tecnico das Condicoes Ambientais do Trabalho
          </h1>
          <div className="flex items-center gap-2 mt-1">
            <Badge variant="outline" className="text-xs">NR-15 / Lei 8.213</Badge>
            <Badge variant="outline" className="text-xs">IN INSS 128/2022</Badge>
            <p className="text-muted-foreground text-sm">
              Avaliacao dos agentes de risco nos postos de trabalho
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={openEdit} disabled={isLoading}>
            <Pencil className="h-4 w-4 mr-2" />
            Editar LTCAT
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Postos Avaliados</CardTitle>
            <Building2 className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{postosAvaliados}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Agentes de Risco</CardTitle>
            <AlertTriangle className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-orange-600">{totalAgentes}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Status LTCAT</CardTitle>
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              getStatusBadge(data?.status ?? 'desconhecido')
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Responsavel Tecnico</CardTitle>
            <UserCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div>
                <p className="text-sm font-medium truncate" title={data?.responsavel_tecnico ?? ''}>
                  {data?.responsavel_tecnico ?? '—'}
                </p>
                {data?.registro_conselho && (
                  <p className="text-xs text-muted-foreground font-mono truncate">
                    {data.registro_conselho}
                  </p>
                )}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Info Banner */}
      {data && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="p-4">
            <div className="grid gap-2 md:grid-cols-3 text-sm">
              <div>
                <span className="text-muted-foreground">Empresa:</span>{' '}
                <span className="font-medium">{data.empresa}</span>
              </div>
              <div>
                <span className="text-muted-foreground">CNPJ:</span>{' '}
                <span className="font-medium">{data.cnpj}</span>
              </div>
              <div className="flex items-center gap-1">
                <Clock className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="text-muted-foreground">Vigencia:</span>{' '}
                <span className="font-medium">{data.vigencia}</span>
              </div>
            </div>
            {data.observacoes && (
              <p className="text-sm text-muted-foreground mt-2">
                <span className="font-medium text-foreground">Observacoes:</span> {data.observacoes}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar dados do LTCAT</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Fatores de Risco Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Fatores de Risco Identificados</CardTitle>
          <CardDescription>
            Agentes nocivos mapeados nos postos de trabalho conforme NR-15 e legislacao previdenciaria.
            {data?.fonte_fatores_risco && (
              <span className="block text-xs mt-1">Fonte: {data.fonte_fatores_risco}</span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : fatoresRisco.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileText className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum fator de risco mapeado</h3>
              <p className="mt-2">O LTCAT ainda nao possui fatores de risco cadastrados.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Agente de Risco</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Nivel</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {fatoresRisco.map((fator, idx) => (
                  <TableRow key={`${fator.agente}-${idx}`}>
                    <TableCell className="font-medium">{fator.agente}</TableCell>
                    <TableCell>{getTipoRiscoBadge(fator.tipo)}</TableCell>
                    <TableCell>
                      {fator.nivel ? (
                        <Badge variant="outline" className="text-xs">
                          {fator.nivel}
                        </Badge>
                      ) : (
                        <span className="text-muted-foreground">—</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Proxima Acao */}
      {data?.proxima_acao && (
        <Card className="border-yellow-200 bg-yellow-50/50">
          <CardContent className="p-4 flex items-start gap-3">
            <AlertTriangle className="h-5 w-5 text-yellow-600 mt-0.5 shrink-0" />
            <div>
              <p className="font-medium text-sm">Proxima Acao Necessaria</p>
              <p className="text-sm text-muted-foreground mt-1">{data.proxima_acao}</p>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Dialog - Editar LTCAT */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Editar LTCAT</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="ltcat_status">Status</Label>
              <Select
                value={editForm.status}
                onValueChange={(v) => setEditForm({ ...editForm, status: v })}
              >
                <SelectTrigger id="ltcat_status">
                  <SelectValue placeholder="Selecione o status" />
                </SelectTrigger>
                <SelectContent>
                  {STATUS_OPTIONS.map((opt) => (
                    <SelectItem key={opt.value} value={opt.value}>
                      {opt.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="ltcat_responsavel">Responsavel Tecnico</Label>
                <Input
                  id="ltcat_responsavel"
                  value={editForm.responsavel_tecnico}
                  onChange={(e) => setEditForm({ ...editForm, responsavel_tecnico: e.target.value })}
                  placeholder="Nome do responsavel tecnico"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ltcat_registro">Registro no Conselho</Label>
                <Input
                  id="ltcat_registro"
                  value={editForm.registro_conselho}
                  onChange={(e) => setEditForm({ ...editForm, registro_conselho: e.target.value })}
                  placeholder="Ex: CREA/AM 12345"
                />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="ltcat_validade_inicio">Validade - Inicio</Label>
                <Input
                  id="ltcat_validade_inicio"
                  type="date"
                  value={editForm.validade_inicio}
                  onChange={(e) => setEditForm({ ...editForm, validade_inicio: e.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="ltcat_validade_fim">Validade - Fim</Label>
                <Input
                  id="ltcat_validade_fim"
                  type="date"
                  value={editForm.validade_fim}
                  onChange={(e) => setEditForm({ ...editForm, validade_fim: e.target.value })}
                />
              </div>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ltcat_observacoes">Observacoes</Label>
              <Textarea
                id="ltcat_observacoes"
                value={editForm.observacoes}
                onChange={(e) => setEditForm({ ...editForm, observacoes: e.target.value })}
                placeholder="Observacoes sobre o laudo"
                rows={3}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditOpen(false)}>
              Cancelar
            </Button>
            <Button onClick={handleSaveEdit} disabled={updateLTCAT.isPending}>
              {updateLTCAT.isPending ? 'Salvando...' : 'Salvar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
