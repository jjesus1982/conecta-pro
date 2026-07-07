'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Shield,
  Search,
  RefreshCw,
  Upload,
  MoreHorizontal,
  Trash2,
  AlertCircle,
  CheckCircle2,
  Clock,
  XCircle,
  RefreshCcw,
  ExternalLink,
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  Loader2,
  AlertTriangle,
  FileWarning,
  Bot,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ConfirmModal } from '@/components/ui/modal';
import { toast } from 'sonner';
import {
  useListarCertidoes,
  useCriarCertidao,
  useRemoverCertidao,
  useRenovarCertidoes,
} from '@/hooks/bidding/useCertificates';
import {
  useSentinelVerificar,
  useSentinelAlertas,
} from '@/hooks/bidding/useAgents';
import { CertificateUploadModal } from '@/components/licitacoes/CertificateUploadModal';
import { formatDate } from '@/lib/utils';

// ──────────────────────────────────────────────
// Types for Sentinel data
// ──────────────────────────────────────────────

interface DocumentoMonitorado {
  tipo: string;
  nome_exibicao: string;
  cnpj_empresa: string;
  data_emissao: string | null;
  data_validade: string | null;
  validade_padrao_dias: number;
  status: 'valido' | 'vencendo' | 'vencido' | 'nao_possui' | 'renovando' | 'erro_consulta';
  nivel_alerta: 'ok' | 'atencao' | 'urgente' | 'critico';
  dias_para_vencimento: number | null;
  url_consulta: string | null;
  ultima_consulta: string | null;
  proximo_check: string | null;
  erro_consulta: string | null;
  arquivo_path: string | null;
  arquivo_hash: string | null;
  observacoes: string | null;
}

interface SentinelData {
  total_documentos: number;
  validos: number;
  vencendo: number;
  vencidos: number;
  nao_possui: number;
  alertas_criticos: string[];
  alertas_urgentes: string[];
  alertas_atencao: string[];
  documentos: DocumentoMonitorado[];
  apto_licitar: boolean;
  motivo_inaptidao: string[];
  verificado_em: string | null;
  proxima_verificacao: string | null;
}

// ──────────────────────────────────────────────
// Helper components
// ──────────────────────────────────────────────

function StatusBadge({ status, nivelAlerta }: { status: string; nivelAlerta: string }) {
  const config: Record<string, { label: string; variant: 'success' | 'warning' | 'destructive' | 'secondary' | 'outline' }> = {
    valido: { label: 'Valida', variant: 'success' },
    vencendo: nivelAlerta === 'atencao'
      ? { label: 'Atencao', variant: 'warning' }
      : nivelAlerta === 'urgente'
      ? { label: 'Urgente', variant: 'destructive' }
      : { label: 'Critico', variant: 'destructive' },
    vencido: { label: 'Vencida', variant: 'destructive' },
    nao_possui: { label: 'Nao possui', variant: 'outline' },
    renovando: { label: 'Renovando', variant: 'secondary' },
    erro_consulta: { label: 'Erro', variant: 'destructive' },
  };

  const { label, variant } = config[status] || { label: status, variant: 'outline' as const };

  return <Badge variant={variant}>{label}</Badge>;
}

function DiasRestantesCell({ dias }: { dias: number | null }) {
  if (dias === null || dias === undefined) {
    return <span className="text-sm text-gray-400 font-medium">--</span>;
  }

  let colorClass = 'text-green-600';
  if (dias < 0) colorClass = 'text-red-600 font-bold';
  else if (dias < 30) colorClass = 'text-red-500 font-semibold';
  else if (dias <= 60) colorClass = 'text-yellow-600 font-semibold';

  return (
    <span className={`text-sm ${colorClass}`}>
      {dias < 0 ? `${Math.abs(dias)}d atrasado` : `${dias}d`}
    </span>
  );
}

// ──────────────────────────────────────────────
// Main page
// ──────────────────────────────────────────────

export default function CertidoesPage() {
  const [search, setSearch] = useState('');
  const [tipoFilter, setTipoFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  // Existing certificate CRUD hooks
  const { data: certidoesData, isLoading: certidoesLoading, error: certidoesError, refetch: refetchCertidoes } = useListarCertidoes({
    tipo: tipoFilter !== 'all' ? tipoFilter : undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
    page,
    size: pageSize,
  });

  const criarMutation = useCriarCertidao();
  const removerMutation = useRemoverCertidao();
  const renovarMutation = useRenovarCertidoes();

  // Sentinel agent hooks
  const sentinelVerificar = useSentinelVerificar();
  const sentinelAlertas = useSentinelAlertas();

  // State
  const [uploadOpen, setUploadOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  // Sentinel data from the verificar endpoint
  const sentinelData = sentinelVerificar.data as SentinelData | undefined;
  const alertasData = sentinelAlertas.data as SentinelData | undefined;

  // Load sentinel data on mount
  useEffect(() => {
    sentinelVerificar.mutate(undefined);
    sentinelAlertas.mutate({ dias: 60 });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Merge sentinel + alertas for the best available data
  const activeData = sentinelData || alertasData;

  // KPI values
  const kpis = useMemo(() => {
    if (!activeData) {
      return { total: 0, validos: 0, vencendo: 0, criticos: 0 };
    }
    return {
      total: activeData.total_documentos,
      validos: activeData.validos,
      vencendo: activeData.vencendo,
      criticos: activeData.vencidos + activeData.nao_possui,
    };
  }, [activeData]);

  // Filter sentinel documents for table display
  const documentos = useMemo(() => {
    if (!activeData?.documentos) return [];
    let filtered = activeData.documentos;

    if (search) {
      const q = search.toLowerCase();
      filtered = filtered.filter(
        (d) =>
          d.nome_exibicao.toLowerCase().includes(q) ||
          d.tipo.toLowerCase().includes(q)
      );
    }

    if (tipoFilter !== 'all') {
      filtered = filtered.filter((d) => d.tipo.includes(tipoFilter));
    }

    if (statusFilter !== 'all') {
      const statusMap: Record<string, string[]> = {
        valida: ['valido'],
        vencendo: ['vencendo'],
        vencida: ['vencido'],
        pendente: ['nao_possui'],
      };
      const allowed = statusMap[statusFilter] || [statusFilter];
      filtered = filtered.filter((d) => allowed.includes(d.status));
    }

    return filtered;
  }, [activeData, search, tipoFilter, statusFilter]);

  // Alerts combined
  const allAlertas = useMemo(() => {
    const data = alertasData || sentinelData;
    if (!data) return { criticos: [] as string[], urgentes: [] as string[], atencao: [] as string[] };
    return {
      criticos: data.alertas_criticos || [],
      urgentes: data.alertas_urgentes || [],
      atencao: data.alertas_atencao || [],
    };
  }, [alertasData, sentinelData]);

  const isLoading = sentinelVerificar.isPending || sentinelAlertas.isPending;
  const hasError = sentinelVerificar.isError || sentinelAlertas.isError;

  // Handlers
  const openConfirm = (
    title: string,
    message: string,
    action: () => Promise<void>,
    variant: 'danger' | 'warning' | 'info' = 'warning'
  ) => {
    setConfirmAction({ title, message, action, variant });
    setConfirmOpen(true);
  };

  const handleUploadSubmit = async (data: any) => {
    try {
      await criarMutation.mutateAsync(data);
      setUploadOpen(false);
      // Refresh sentinel after upload
      sentinelVerificar.mutate(undefined);
    } catch (err) {
      // Error handled by mutation
    }
  };

  const handleVerificarAgora = () => {
    sentinelVerificar.mutate(undefined, {
      onSuccess: (data: any) => {
        toast.success(
          `Verificacao concluida: ${data.validos} validas, ${data.vencendo} vencendo, ${data.vencidos} vencidas`
        );
        // Also refresh alertas
        sentinelAlertas.mutate({ dias: 60 });
        refetchCertidoes();
      },
    });
  };

  const handleRenovarTodas = async () => {
    try {
      await renovarMutation.mutateAsync({ cnpj: '' });
      toast.success('Renovacao iniciada');
      // Refresh after renewal
      setTimeout(() => sentinelVerificar.mutate(undefined), 2000);
    } catch (err) {
      // Error handled by mutation
    }
  };

  const formatTipo = (tipo: string) => {
    const labels: Record<string, string> = {
      cnd_federal: 'Federal',
      cnd_estadual: 'Estadual',
      cnd_municipal: 'Municipal',
      crf_fgts: 'FGTS',
      cndt_trabalhista: 'Trabalhista',
      sicaf: 'SICAF',
      autorizacao_pf: 'Policia Federal',
      alvara_funcionamento: 'Alvara',
      certificado_digital: 'Cert. Digital',
      iso_9001: 'ISO 9001',
      iso_14001: 'ISO 14001',
      seguro_responsabilidade: 'Seguro RC',
      registro_crea: 'CREA',
      balanco_patrimonial: 'Balanco',
    };
    return labels[tipo] || tipo;
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-amber-500 to-orange-600 flex items-center justify-center">
              <Shield className="h-5 w-5 text-white" />
            </div>
            Gestao de Certidoes e Documentos de Habilitacao
          </h1>
          <p className="text-muted-foreground mt-1 flex items-center gap-1.5">
            <Bot className="h-3.5 w-3.5" />
            Monitoramento automatico pelo agente SENTINEL -- alertas de vencimento e controle de aptidao
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            onClick={handleVerificarAgora}
            disabled={isLoading}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <RefreshCw className="h-4 w-4 mr-2" />
            )}
            Verificar Agora
          </Button>
          <Button
            variant="outline"
            onClick={handleRenovarTodas}
            disabled={renovarMutation.isPending}
          >
            <RefreshCcw className="h-4 w-4 mr-2" />
            Renovar Todas
          </Button>
          <Button onClick={() => setUploadOpen(true)}>
            <Upload className="h-4 w-4 mr-2" />
            Upload Certidao
          </Button>
        </div>
      </div>

      {/* Apto para Licitar Banner */}
      {activeData && (
        <div
          className={`rounded-xl p-5 flex items-center justify-between ${
            activeData.apto_licitar
              ? 'bg-green-500/10 border-2 border-green-500/30'
              : 'bg-red-500/10 border-2 border-red-500/30'
          }`}
        >
          <div className="flex items-center gap-4">
            {activeData.apto_licitar ? (
              <ShieldCheck className="h-10 w-10 text-green-600" />
            ) : (
              <ShieldX className="h-10 w-10 text-red-600" />
            )}
            <div>
              <div className="flex items-center gap-3">
                <h2 className={`font-display text-2xl font-bold ${activeData.apto_licitar ? 'text-green-700' : 'text-red-700'}`}>
                  Apto para Licitar: {activeData.apto_licitar ? 'SIM' : 'NAO'}
                </h2>
                <Badge variant={activeData.apto_licitar ? 'success' : 'destructive'} className="text-sm px-3 py-1">
                  {activeData.apto_licitar ? 'Regular' : 'Irregular'}
                </Badge>
              </div>
              {!activeData.apto_licitar && activeData.motivo_inaptidao.length > 0 && (
                <p className="text-sm text-red-600 mt-1">
                  {activeData.motivo_inaptidao.length} pendencia(s): {activeData.motivo_inaptidao[0]}
                  {activeData.motivo_inaptidao.length > 1 && ` (+${activeData.motivo_inaptidao.length - 1})`}
                </p>
              )}
              {activeData.verificado_em && (
                <p className="text-xs text-muted-foreground mt-1">
                  Ultima verificacao: {new Date(activeData.verificado_em).toLocaleString('pt-BR')}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Loading state for banner */}
      {!activeData && isLoading && (
        <div className="rounded-xl p-5 bg-muted/50 border-2 border-muted flex items-center justify-center gap-3">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
          <span className="text-muted-foreground">Consultando agente SENTINEL...</span>
        </div>
      )}

      {/* KPI Cards Row */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total de Certidoes</CardTitle>
            <Shield className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-3xl font-semibold tabular-nums">{kpis.total}</div>
            <p className="text-xs text-muted-foreground mt-1">documentos monitorados</p>
          </CardContent>
        </Card>

        <Card className="border-green-500/20">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Validas</CardTitle>
            <CheckCircle2 className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-3xl font-semibold tabular-nums text-green-600">{kpis.validos}</div>
            <p className="text-xs text-muted-foreground mt-1">certidoes em dia</p>
          </CardContent>
        </Card>

        <Card className="border-yellow-500/20">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Vencendo em 30 dias</CardTitle>
            <Clock className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-3xl font-semibold tabular-nums text-yellow-600">{kpis.vencendo}</div>
            <p className="text-xs text-muted-foreground mt-1">requerem atencao</p>
          </CardContent>
        </Card>

        <Card className="border-red-500/20">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Vencidas / Nao cadastradas</CardTitle>
            <XCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-3xl font-semibold tabular-nums text-red-600">{kpis.criticos}</div>
            <p className="text-xs text-muted-foreground mt-1">acao imediata necessaria</p>
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
                placeholder="Buscar certidao por nome ou tipo..."
                className="pl-10"
              />
            </div>
            <Select value={tipoFilter} onValueChange={(v) => setTipoFilter(v)}>
              <SelectTrigger className="w-[200px]">
                <SelectValue placeholder="Tipo" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os tipos</SelectItem>
                <SelectItem value="federal">Federal</SelectItem>
                <SelectItem value="estadual">Estadual</SelectItem>
                <SelectItem value="municipal">Municipal</SelectItem>
                <SelectItem value="trabalhista">Trabalhista</SelectItem>
                <SelectItem value="fgts">FGTS</SelectItem>
                <SelectItem value="sicaf">SICAF</SelectItem>
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v)}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os status</SelectItem>
                <SelectItem value="valida">Valida</SelectItem>
                <SelectItem value="vencendo">Vencendo</SelectItem>
                <SelectItem value="vencida">Vencida</SelectItem>
                <SelectItem value="pendente">Nao possui</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {hasError && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">
            Erro ao consultar agente SENTINEL. Verifique a conexao com o backend.
          </p>
          <Button variant="outline" size="sm" onClick={handleVerificarAgora}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Certidoes Table */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Certidoes Monitoradas
            {documentos.length > 0 && (
              <Badge variant="secondary" className="ml-2">{documentos.length}</Badge>
            )}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : documentos.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Shield className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhuma certidao encontrada</h3>
              <p className="mt-2">Clique em &quot;Verificar Agora&quot; para consultar o SENTINEL</p>
              <Button className="mt-4" onClick={handleVerificarAgora}>
                <RefreshCw className="h-4 w-4 mr-2" />
                Verificar Agora
              </Button>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome da Certidao</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Data Emissao</TableHead>
                  <TableHead>Data Validade</TableHead>
                  <TableHead>Dias Restantes</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Consultar</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {documentos.map((doc, idx) => (
                  <TableRow
                    key={`${doc.tipo}-${idx}`}
                    className={
                      doc.status === 'vencido' || doc.status === 'nao_possui'
                        ? 'bg-red-500/5'
                        : doc.nivel_alerta === 'urgente' || doc.nivel_alerta === 'critico'
                        ? 'bg-yellow-500/5'
                        : ''
                    }
                  >
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {doc.nivel_alerta === 'critico' && (
                          <ShieldAlert className="h-4 w-4 text-red-500 flex-shrink-0" />
                        )}
                        {doc.nivel_alerta === 'urgente' && (
                          <AlertTriangle className="h-4 w-4 text-yellow-500 flex-shrink-0" />
                        )}
                        {doc.nivel_alerta === 'atencao' && (
                          <Clock className="h-4 w-4 text-yellow-600 flex-shrink-0" />
                        )}
                        {doc.nivel_alerta === 'ok' && (
                          <CheckCircle2 className="h-4 w-4 text-green-500 flex-shrink-0" />
                        )}
                        <span className="text-sm font-medium">{doc.nome_exibicao}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-xs">
                        {formatTipo(doc.tipo)}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {doc.data_emissao
                        ? new Date(doc.data_emissao).toLocaleDateString('pt-BR')
                        : '--'}
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {doc.data_validade
                        ? new Date(doc.data_validade).toLocaleDateString('pt-BR')
                        : '--'}
                    </TableCell>
                    <TableCell>
                      <DiasRestantesCell dias={doc.dias_para_vencimento} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge status={doc.status} nivelAlerta={doc.nivel_alerta} />
                    </TableCell>
                    <TableCell>
                      {doc.url_consulta ? (
                        <a
                          href={doc.url_consulta}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-primary hover:underline"
                        >
                          <ExternalLink className="h-3 w-3" />
                          Consultar
                        </a>
                      ) : (
                        <span className="text-xs text-muted-foreground">--</span>
                      )}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => setUploadOpen(true)}>
                            <Upload className="h-4 w-4 mr-2" />
                            Upload PDF
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onClick={() =>
                              openConfirm(
                                'Renovar Certidao',
                                `Solicitar renovacao automatica de "${doc.nome_exibicao}"?`,
                                async () => {
                                  await renovarMutation.mutateAsync({ cnpj: doc.cnpj_empresa });
                                  sentinelVerificar.mutate(undefined);
                                },
                                'info'
                              )
                            }
                          >
                            <RefreshCcw className="h-4 w-4 mr-2" />
                            Renovar
                          </DropdownMenuItem>
                          {doc.url_consulta && (
                            <DropdownMenuItem
                              onClick={() => window.open(doc.url_consulta!, '_blank')}
                            >
                              <ExternalLink className="h-4 w-4 mr-2" />
                              Abrir Portal
                            </DropdownMenuItem>
                          )}
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Alertas Section */}
      {(allAlertas.criticos.length > 0 || allAlertas.urgentes.length > 0 || allAlertas.atencao.length > 0) && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base flex items-center gap-2">
              <AlertCircle className="h-4 w-4 text-red-500" />
              Alertas do SENTINEL
              <Badge variant="destructive" className="ml-2">
                {allAlertas.criticos.length + allAlertas.urgentes.length + allAlertas.atencao.length}
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {/* Critical alerts */}
            {allAlertas.criticos.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-red-600 flex items-center gap-1.5">
                  <XCircle className="h-4 w-4" />
                  Criticos ({allAlertas.criticos.length})
                </h4>
                <div className="space-y-1.5">
                  {allAlertas.criticos.map((alerta, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-2 p-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-sm"
                    >
                      <ShieldX className="h-4 w-4 text-red-600 flex-shrink-0" />
                      <span className="text-red-700">{alerta}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Urgent alerts */}
            {allAlertas.urgentes.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-orange-600 flex items-center gap-1.5">
                  <AlertTriangle className="h-4 w-4" />
                  Urgentes ({allAlertas.urgentes.length})
                </h4>
                <div className="space-y-1.5">
                  {allAlertas.urgentes.map((alerta, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-2 p-2.5 rounded-lg bg-orange-500/10 border border-orange-500/20 text-sm"
                    >
                      <FileWarning className="h-4 w-4 text-orange-600 flex-shrink-0" />
                      <span className="text-orange-700">{alerta}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Attention alerts */}
            {allAlertas.atencao.length > 0 && (
              <div className="space-y-2">
                <h4 className="text-sm font-semibold text-yellow-600 flex items-center gap-1.5">
                  <Clock className="h-4 w-4" />
                  Atencao ({allAlertas.atencao.length})
                </h4>
                <div className="space-y-1.5">
                  {allAlertas.atencao.map((alerta, idx) => (
                    <div
                      key={idx}
                      className="flex items-center gap-2 p-2.5 rounded-lg bg-yellow-500/10 border border-yellow-500/20 text-sm"
                    >
                      <Clock className="h-4 w-4 text-yellow-600 flex-shrink-0" />
                      <span className="text-yellow-700">{alerta}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* Modals */}
      <CertificateUploadModal
        isOpen={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSubmit={handleUploadSubmit}
        isLoading={criarMutation.isPending}
      />

      {confirmAction && (
        <ConfirmModal
          isOpen={confirmOpen}
          onClose={() => setConfirmOpen(false)}
          onConfirm={async () => {
            await confirmAction.action();
            setConfirmOpen(false);
          }}
          title={confirmAction.title}
          message={confirmAction.message}
          variant={confirmAction.variant}
          isLoading={removerMutation.isPending || renovarMutation.isPending}
        />
      )}
    </div>
  );
}
