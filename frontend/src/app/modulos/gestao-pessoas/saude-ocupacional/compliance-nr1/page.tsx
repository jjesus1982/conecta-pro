'use client';

import { useState } from 'react';
import {
  ShieldCheck,
  ShieldAlert,
  AlertTriangle,
  RefreshCw,
  FileSignature,
  PackageX,
  Users,
  FileDown,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { toast } from 'sonner';
import { useNR1Compliance } from '@/hooks/sst';
import { sstService } from '@/lib/services/sst';
import type { NR1Funcionario } from '@/lib/services/sst';

function baixarBlob(blob: Blob, nomeArquivo: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = nomeArquivo;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

function getASOBadge(check: NR1Funcionario['checks']['aso']) {
  const config: Record<string, { label: string; className: string }> = {
    em_dia: { label: 'ASO em dia', className: 'bg-green-100 text-green-800' },
    vencido: { label: 'ASO vencido', className: 'bg-red-100 text-red-800' },
    sem_aso: { label: 'Sem ASO', className: 'bg-gray-100 text-gray-800' },
  };
  const item = config[check.situacao] ?? {
    label: check.situacao,
    className: check.ok ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800',
  };
  return <Badge className={item.className}>{item.label}</Badge>;
}

function getEPIBadge(check: NR1Funcionario['checks']['epi']) {
  const config: Record<string, { label: string; className: string }> = {
    fichas_assinadas: { label: 'Fichas assinadas', className: 'bg-green-100 text-green-800' },
    ficha_pendente: { label: 'Ficha pendente', className: 'bg-yellow-100 text-yellow-800' },
    sem_ficha: { label: 'Sem ficha', className: 'bg-red-100 text-red-800' },
    sem_entrega_registrada: { label: 'Sem entrega registrada', className: 'bg-gray-100 text-gray-800' },
  };
  const item = config[check.situacao] ?? {
    label: check.situacao,
    className: check.ok ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800',
  };
  return <Badge className={item.className}>{item.label}</Badge>;
}

function getRiscosBadge(check: NR1Funcionario['checks']['riscos']) {
  const config: Record<string, { label: string; className: string }> = {
    mapa_vigente: { label: 'Mapa vigente', className: 'bg-green-100 text-green-800' },
  };
  const item = config[check.situacao] ?? {
    label: check.situacao,
    className: check.ok ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800',
  };
  return <Badge className={item.className}>{item.label}</Badge>;
}

function getTreinamentosBadge(check: NR1Funcionario['checks']['treinamentos']) {
  if (check.ok === null) {
    return (
      <Badge variant="outline" className="text-gray-600 border-gray-300">
        Sem fonte
      </Badge>
    );
  }
  return (
    <Badge className={check.ok ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}>
      {check.situacao}
    </Badge>
  );
}

function getScoreCell(score: number) {
  const cor = score >= 80 ? 'text-green-600' : score >= 50 ? 'text-yellow-600' : 'text-red-600';
  const barra = score >= 80 ? 'bg-green-500' : score >= 50 ? 'bg-yellow-500' : 'bg-red-500';
  return (
    <div className="flex items-center gap-2 min-w-[110px]">
      <div className="h-1.5 w-16 rounded-full bg-muted overflow-hidden">
        <div className={`h-full rounded-full ${barra}`} style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
      </div>
      <span className={`font-data text-sm font-semibold tabular-nums ${cor}`}>{score}</span>
    </div>
  );
}

function getCalcadoBadge(calcado: boolean) {
  return calcado ? (
    <Badge className="bg-green-100 text-green-800">Calcado</Badge>
  ) : (
    <Badge className="bg-red-100 text-red-800">Descalcado</Badge>
  );
}

export default function ComplianceNR1Page() {
  const { data, isLoading, error, refetch } = useNR1Compliance();
  const [exportando, setExportando] = useState(false);
  const [pppBaixando, setPppBaixando] = useState<string | null>(null);

  const handleRefresh = async () => {
    try {
      await refetch();
      toast.success('Dados atualizados', { duration: 4000 });
    } catch {
      toast.error('Erro ao atualizar dados', { duration: 5000 });
    }
  };

  const handleExportarRelatorio = async () => {
    setExportando(true);
    try {
      const blob = await sstService.downloadNR1CompliancePdf();
      baixarBlob(blob, `compliance-nr1-${new Date().toISOString().slice(0, 10)}.pdf`);
      toast.success('Relatório de Compliance NR-1 exportado', { duration: 4000 });
    } catch {
      toast.error('Erro ao exportar o relatório PDF', { duration: 5000 });
    } finally {
      setExportando(false);
    }
  };

  const handleBaixarPPP = async (employeeId: string, nome: string) => {
    setPppBaixando(employeeId);
    try {
      const blob = await sstService.downloadPPPPdf(employeeId);
      const slug = nome.toLowerCase().replace(/[^a-z0-9]+/g, '-').slice(0, 40);
      baixarBlob(blob, `ppp-${slug}.pdf`);
      toast.success(`PPP de ${nome} baixado`, { duration: 4000 });
    } catch {
      toast.error('Erro ao gerar o PPP em PDF', { duration: 5000 });
    } finally {
      setPppBaixando(null);
    }
  };

  const resumo = data?.resumo;
  const funcionarios = data?.funcionarios ?? [];
  const fonteRiscos = funcionarios[0]?.checks?.riscos?.fonte;

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2 text-[hsl(var(--foreground))]">
            <ShieldCheck className="h-6 w-6" />
            Compliance NR-1
          </h1>
          <p className="text-muted-foreground">
            Painel calcado por funcionario — score honesto por fatos no banco
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button onClick={handleExportarRelatorio} disabled={exportando || isLoading}>
            <FileDown className={`h-4 w-4 mr-2 ${exportando ? 'animate-pulse' : ''}`} />
            {exportando ? 'Gerando PDF...' : 'Exportar relatório PDF'}
          </Button>
          <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card className="border-green-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Calcados</CardTitle>
            <Users className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                {resumo?.calcados ?? 0}/{resumo?.total_funcionarios_ativos ?? 0}
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              {resumo ? `${resumo.descalcados} descalcado(s)` : '—'}
            </p>
          </CardContent>
        </Card>

        <Card className="border-red-200">
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">ASOs Vencidos</CardTitle>
            <ShieldAlert className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">
                {resumo?.asos_vencidos_registros ?? 0}
              </div>
            )}
            <p className="text-xs text-red-600 mt-1">
              {resumo && resumo.asos_vencidos_registros > 0
                ? `Pendencia: ${resumo.funcionarios_aso_vencido} funcionario(s) afetado(s)`
                : 'Sem pendencia'}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Fichas EPI Pendentes</CardTitle>
            <FileSignature className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">
                {resumo?.fichas_epi_pendentes_assinatura ?? 0}
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">Pendentes de assinatura</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Entregas sem Ficha</CardTitle>
            <PackageX className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-orange-600">
                {resumo?.entregas_epi_sem_ficha ?? 0}
              </div>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              {resumo ? `${resumo.riscos_mapeados_vigentes} risco(s) mapeado(s) vigente(s)` : '—'}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar o painel de compliance NR-1</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Tabela por funcionario */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Compliance por Funcionario</CardTitle>
          <CardDescription>
            Cada check reflete o fato registrado no banco: ASO (NR-7), fichas de EPI (NR-6), riscos (PGR) e treinamentos.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : funcionarios.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <ShieldCheck className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum funcionario ativo</h3>
              <p className="mt-2">Nao ha funcionarios ativos para avaliar o compliance NR-1.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Cargo</TableHead>
                  <TableHead>ASO</TableHead>
                  <TableHead>EPI</TableHead>
                  <TableHead>Riscos</TableHead>
                  <TableHead>Treinamentos</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Situacao</TableHead>
                  <TableHead>PPP</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {funcionarios.map((f) => (
                  <TableRow key={f.employee_id}>
                    <TableCell className="font-medium">{f.nome}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{f.cargo || '—'}</TableCell>
                    <TableCell>{getASOBadge(f.checks.aso)}</TableCell>
                    <TableCell>{getEPIBadge(f.checks.epi)}</TableCell>
                    <TableCell>{getRiscosBadge(f.checks.riscos)}</TableCell>
                    <TableCell>{getTreinamentosBadge(f.checks.treinamentos)}</TableCell>
                    <TableCell>{getScoreCell(f.score)}</TableCell>
                    <TableCell>{getCalcadoBadge(f.calcado)}</TableCell>
                    <TableCell>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => handleBaixarPPP(f.employee_id, f.nome)}
                        disabled={pppBaixando === f.employee_id}
                        title="Baixar PPP (Perfil Profissiográfico Previdenciário) em PDF"
                      >
                        <FileDown className={`h-3.5 w-3.5 mr-1 ${pppBaixando === f.employee_id ? 'animate-pulse' : ''}`} />
                        PPP PDF
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Nota de honestidade */}
      {data && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="p-4 text-sm text-muted-foreground space-y-1">
            <p className="font-medium text-foreground">Nota de honestidade dos dados</p>
            <p>
              Riscos: {fonteRiscos || 'aguardando dado (fonte nao informada pelo backend)'}.
            </p>
            <p>
              Treinamentos: {resumo?.treinamentos_fonte || 'aguardando dado (fonte nao informada pelo backend)'}.
            </p>
            <p>
              O score e calculado exclusivamente sobre registros existentes no banco — nenhum valor e estimado ou preenchido automaticamente.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
