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
import { useASOs } from '@/hooks/sst';
import type { ASOItem } from '@/lib/services/sst';

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

  const [dialogOpen, setDialogOpen] = useState(false);
  const [search, setSearch] = useState('');

  // Form state para agendar exame
  const [formData, setFormData] = useState({
    funcionario_id: '',
    tipo_exame: '',
    data_agendamento: '',
    clinica: '',
    observacoes: '',
  });

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
      toast.error('Erro ao agendar exame. Tente novamente.', { duration: 5000 });
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
                  <Label htmlFor="funcionario_id">ID do Funcionario</Label>
                  <Input
                    id="funcionario_id"
                    value={formData.funcionario_id}
                    onChange={(e) => setFormData({ ...formData, funcionario_id: e.target.value })}
                    placeholder="ID do funcionario"
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
                  <TableHead>ASO ID</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>eSocial</TableHead>
                  <TableHead>Recibo S-2220</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {esocialASOs.map((aso) => (
                  <TableRow key={aso.aso_id}>
                    <TableCell className="text-sm font-mono">
                      {aso.aso_id.length > 8 ? `${aso.aso_id.substring(0, 8)}...` : aso.aso_id}
                    </TableCell>
                    <TableCell className="text-sm">{aso.tipo || '—'}</TableCell>
                    <TableCell className="text-sm">{aso.status || '—'}</TableCell>
                    <TableCell>{getESocialBadge(aso.esocial_status)}</TableCell>
                    <TableCell className="text-sm font-mono">{aso.recibo_s2220 || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
