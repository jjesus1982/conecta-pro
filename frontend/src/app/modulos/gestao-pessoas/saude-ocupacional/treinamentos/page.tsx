'use client';

import {
  GraduationCap,
  AlertCircle,
  CheckCircle,
  Clock,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  FileCheck,
} from 'lucide-react';
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
import { useTreinamentos, useCriarTreinamento, useExcluirTreinamento } from '@/hooks/sst';
import {
  apiErrorDetail,
  TREINAMENTO_NORMAS,
  type TreinamentoNR,
} from '@/lib/services/sst';
import { EmployeeSelect } from '@/components/sst/EmployeeSelect';

const NORMA_LABELS: Record<string, string> = Object.fromEntries(
  TREINAMENTO_NORMAS.map((n) => [n.value, n.label])
);

function getSituacaoBadge(situacao: string) {
  const styles: Record<string, string> = {
    em_dia: 'bg-green-100 text-green-800',
    vencendo: 'bg-yellow-100 text-yellow-800',
    vencido: 'bg-red-100 text-red-800',
  };
  const labels: Record<string, string> = {
    em_dia: 'Em dia',
    vencendo: 'Vencendo (30d)',
    vencido: 'Vencido',
  };
  return (
    <Badge className={styles[situacao] || 'bg-gray-100 text-gray-800'}>
      {labels[situacao] || situacao}
    </Badge>
  );
}

export default function TreinamentosNRPage() {
  const [normaFiltro, setNormaFiltro] = useState<string>('todas');
  const [situacaoFiltro, setSituacaoFiltro] = useState<string>('todas');
  const [search, setSearch] = useState('');

  const { data, isLoading, error, refetch, isFetching } = useTreinamentos(
    normaFiltro !== 'todas' ? { norma: normaFiltro } : undefined
  );
  const criar = useCriarTreinamento();
  const excluir = useExcluirTreinamento();

  const [dialogOpen, setDialogOpen] = useState(false);
  const [excluindo, setExcluindo] = useState<TreinamentoNR | null>(null);
  const [formData, setFormData] = useState({
    employee_id: '',
    norma: '',
    descricao: '',
    data_realizacao: '',
    validade_meses: '12',
    certificado_path: '',
  });

  const treinamentos = data?.treinamentos ?? [];

  const filtrados = treinamentos.filter((t) => {
    if (situacaoFiltro !== 'todas' && t.situacao !== situacaoFiltro) return false;
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (t.employee_nome || '').toLowerCase().includes(q) ||
      (t.norma || '').toLowerCase().includes(q) ||
      (t.descricao || '').toLowerCase().includes(q)
    );
  });

  const handleRegistrar = async () => {
    if (!formData.employee_id || !formData.norma || !formData.data_realizacao) return;
    try {
      await criar.mutateAsync({
        employee_id: formData.employee_id,
        norma: formData.norma,
        descricao: formData.descricao || undefined,
        data_realizacao: formData.data_realizacao,
        validade_meses: parseInt(formData.validade_meses, 10) || 12,
        certificado_path: formData.certificado_path || undefined,
      });
      toast.success('Treinamento registrado — compliance NR-1 atualizado', { duration: 4000 });
      setDialogOpen(false);
      setFormData({
        employee_id: '',
        norma: '',
        descricao: '',
        data_realizacao: '',
        validade_meses: '12',
        certificado_path: '',
      });
    } catch (err) {
      toast.error(apiErrorDetail(err, 'Erro ao registrar treinamento'), { duration: 6000 });
    }
  };

  const handleExcluir = async () => {
    if (!excluindo) return;
    try {
      await excluir.mutateAsync(excluindo.id);
      toast.success('Registro de treinamento excluido', { duration: 4000 });
      setExcluindo(null);
    } catch (err) {
      toast.error(apiErrorDetail(err, 'Erro ao excluir treinamento'), { duration: 6000 });
    }
  };

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <GraduationCap className="h-6 w-6" />
            Treinamentos NR
          </h1>
          <p className="text-muted-foreground">
            Capacitacoes NR-1, NR-6, brigada e primeiros socorros — 4º pilar do compliance NR-1.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                Registrar Treinamento
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Registrar Treinamento Realizado</DialogTitle>
              </DialogHeader>
              <div className="space-y-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="tr_funcionario">Funcionario</Label>
                  <EmployeeSelect
                    id="tr_funcionario"
                    value={formData.employee_id}
                    onChange={(employeeId) => setFormData({ ...formData, employee_id: employeeId })}
                    placeholder="Busque pelo nome do funcionario..."
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="tr_norma">Norma / Tipo</Label>
                  <Select
                    value={formData.norma}
                    onValueChange={(v) => setFormData({ ...formData, norma: v })}
                  >
                    <SelectTrigger id="tr_norma">
                      <SelectValue placeholder="Selecione a norma" />
                    </SelectTrigger>
                    <SelectContent>
                      {TREINAMENTO_NORMAS.map((n) => (
                        <SelectItem key={n.value} value={n.value}>
                          {n.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="tr_data">Data de Realizacao</Label>
                    <Input
                      id="tr_data"
                      type="date"
                      max={new Date().toISOString().slice(0, 10)}
                      value={formData.data_realizacao}
                      onChange={(e) => setFormData({ ...formData, data_realizacao: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="tr_validade">Validade (meses)</Label>
                    <Input
                      id="tr_validade"
                      type="number"
                      min={1}
                      max={120}
                      value={formData.validade_meses}
                      onChange={(e) => setFormData({ ...formData, validade_meses: e.target.value })}
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="tr_descricao">Descricao</Label>
                  <Input
                    id="tr_descricao"
                    value={formData.descricao}
                    onChange={(e) => setFormData({ ...formData, descricao: e.target.value })}
                    placeholder="Ex: Integracao NR-1 — riscos do posto e medidas de controle"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="tr_certificado">Certificado (caminho/URL — opcional)</Label>
                  <Input
                    id="tr_certificado"
                    value={formData.certificado_path}
                    onChange={(e) => setFormData({ ...formData, certificado_path: e.target.value })}
                    placeholder="Link ou caminho do certificado digitalizado"
                  />
                </div>
                <p className="text-xs text-muted-foreground">
                  O vencimento e calculado automaticamente (realizacao + validade). Registre apenas
                  treinamentos que ACONTECERAM — data futura e recusada pelo sistema.
                </p>
              </div>
              <DialogFooter>
                <Button variant="outline" onClick={() => setDialogOpen(false)}>
                  Cancelar
                </Button>
                <Button
                  onClick={handleRegistrar}
                  disabled={
                    criar.isPending ||
                    !formData.employee_id ||
                    !formData.norma ||
                    !formData.data_realizacao
                  }
                >
                  {criar.isPending ? 'Registrando...' : 'Registrar'}
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
            <CardTitle className="text-sm font-medium">Total Registros</CardTitle>
            <FileCheck className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums">{data?.total ?? 0}</div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em dia</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                {data?.em_dia ?? 0}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Vencendo (30d)</CardTitle>
            <Clock className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">
                {data?.vencendo_30d ?? 0}
              </div>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Vencidos</CardTitle>
            <AlertCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">
                {data?.vencidos ?? 0}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Filtros */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por funcionario, norma ou descricao..."
                className="pl-10"
              />
            </div>
            <Select value={normaFiltro} onValueChange={setNormaFiltro}>
              <SelectTrigger className="md:w-[260px]">
                <SelectValue placeholder="Norma" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas as normas</SelectItem>
                {TREINAMENTO_NORMAS.map((n) => (
                  <SelectItem key={n.value} value={n.value}>
                    {n.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={situacaoFiltro} onValueChange={setSituacaoFiltro}>
              <SelectTrigger className="md:w-[180px]">
                <SelectValue placeholder="Situacao" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="todas">Todas situacoes</SelectItem>
                <SelectItem value="em_dia">Em dia</SelectItem>
                <SelectItem value="vencendo">Vencendo (30d)</SelectItem>
                <SelectItem value="vencido">Vencido</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error ? (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">
            {apiErrorDetail(error, 'Erro ao carregar treinamentos')}
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      ) : null}

      {/* Tabela */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Registros de Treinamento</CardTitle>
          <CardDescription>
            Fonte real: sst_treinamentos. Funcionario sem NR-1 valido aparece como pendencia no
            painel de compliance NR-1.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : filtrados.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <GraduationCap className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum treinamento registrado</h3>
              <p className="mt-2">
                Aguardando dado real — registre os treinamentos realizados para fechar o 4º pilar do
                compliance NR-1.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Funcionario</TableHead>
                  <TableHead>Norma</TableHead>
                  <TableHead>Realizacao</TableHead>
                  <TableHead>Vencimento</TableHead>
                  <TableHead>Situacao</TableHead>
                  <TableHead>Certificado</TableHead>
                  <TableHead className="w-[70px]">Acoes</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtrados.map((t) => (
                  <TableRow key={t.id}>
                    <TableCell>
                      <div className="font-medium">{t.employee_nome || '—'}</div>
                      {t.descricao && (
                        <div className="text-xs text-muted-foreground truncate max-w-[280px]">
                          {t.descricao}
                        </div>
                      )}
                    </TableCell>
                    <TableCell className="text-sm">{NORMA_LABELS[t.norma] || t.norma}</TableCell>
                    <TableCell className="text-sm">
                      {new Date(`${t.data_realizacao}T12:00:00`).toLocaleDateString('pt-BR')}
                      <span className="text-xs text-muted-foreground"> ({t.validade_meses}m)</span>
                    </TableCell>
                    <TableCell className="text-sm">
                      {new Date(`${t.vencimento}T12:00:00`).toLocaleDateString('pt-BR')}
                    </TableCell>
                    <TableCell>{getSituacaoBadge(t.situacao)}</TableCell>
                    <TableCell className="text-sm">
                      {t.certificado_path ? (
                        <a
                          href={t.certificado_path}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-primary underline underline-offset-2"
                        >
                          ver
                        </a>
                      ) : (
                        <span className="text-xs text-muted-foreground">sem anexo</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setExcluindo(t)}
                        title="Excluir registro (correcao de lancamento)"
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Dialog - confirmar exclusao */}
      <Dialog open={!!excluindo} onOpenChange={(open) => { if (!open) setExcluindo(null); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir registro de treinamento?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {excluindo
              ? `${excluindo.employee_nome || 'Funcionario'} — ${NORMA_LABELS[excluindo.norma] || excluindo.norma} realizado em ${new Date(`${excluindo.data_realizacao}T12:00:00`).toLocaleDateString('pt-BR')}. Esta acao remove o registro do compliance NR-1.`
              : ''}
          </p>
          <DialogFooter>
            <Button variant="outline" onClick={() => setExcluindo(null)}>
              Cancelar
            </Button>
            <Button variant="destructive" onClick={handleExcluir} disabled={excluir.isPending}>
              {excluir.isPending ? 'Excluindo...' : 'Excluir'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
