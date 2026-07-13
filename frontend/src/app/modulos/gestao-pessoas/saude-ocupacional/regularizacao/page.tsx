'use client';

import Link from 'next/link';
import {
  ShieldAlert,
  AlertTriangle,
  RefreshCw,
  Stethoscope,
  HardHat,
  GraduationCap,
  Users,
  CheckCircle2,
  XCircle,
  Clock,
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
import { useRegularizacaoDescalcos } from '@/hooks/sst';

function ProgressBar({
  label,
  ok,
  total,
  pct,
  icon,
  href,
  hrefLabel,
}: {
  label: string;
  ok: number;
  total: number;
  pct: number;
  icon: React.ReactNode;
  href: string;
  hrefLabel: string;
}) {
  const cor = pct >= 80 ? 'bg-green-500' : pct >= 40 ? 'bg-yellow-500' : 'bg-red-500';
  const texto = pct >= 80 ? 'text-green-600' : pct >= 40 ? 'text-yellow-600' : 'text-red-600';
  return (
    <Card>
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            {icon}
            {label}
          </CardTitle>
          <span className={`font-data text-lg font-semibold tabular-nums ${texto}`}>
            {pct.toFixed(0)}%
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-2">
        <div className="h-2.5 w-full rounded-full bg-muted overflow-hidden">
          <div
            className={`h-full rounded-full transition-all ${cor}`}
            style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span className="font-data tabular-nums">
            {ok} de {total} regularizados
          </span>
          <Link
            href={href}
            className="text-primary hover:underline underline-offset-4 font-medium"
          >
            {hrefLabel}
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}

function StatusBadge({ ok, label }: { ok: boolean; label: string }) {
  return ok ? (
    <Badge className="bg-green-100 text-green-800 gap-1">
      <CheckCircle2 className="h-3 w-3" />
      {label}
    </Badge>
  ) : (
    <Badge className="bg-red-100 text-red-800 gap-1">
      <XCircle className="h-3 w-3" />
      {label}
    </Badge>
  );
}

const EXAMES_HREF = '/modulos/gestao-pessoas/saude-ocupacional/exames';
const EPI_HREF = '/modulos/gestao-pessoas/saude-ocupacional/epi';
const TREINO_HREF = '/modulos/gestao-pessoas/saude-ocupacional/treinamentos';

export default function RegularizacaoSSTPage() {
  const { data, isLoading, error, refetch, isFetching } = useRegularizacaoDescalcos();

  const handleRefresh = async () => {
    try {
      await refetch();
      toast.success('Painel atualizado', { duration: 3000 });
    } catch {
      toast.error('Erro ao atualizar o painel', { duration: 5000 });
    }
  };

  const resumo = data?.resumo;
  const descalcos = data?.descalcos ?? [];
  const total = resumo?.coorte_onda_2026 ?? 0;
  const vencidos = data?.aso_vencidos;

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2 text-[hsl(var(--foreground))]">
            <ShieldAlert className="h-6 w-6" />
            Regularização SST
          </h1>
          <p className="text-muted-foreground">
            Acompanhamento dos &quot;descalços&quot; — ASO admissional, entrega de EPI e treinamento NR
          </p>
        </div>
        <Button variant="outline" onClick={handleRefresh} disabled={isFetching}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Prioridade */}
      {resumo?.prioridade && (
        <div className="rounded-lg border border-amber-300 bg-amber-50/60 p-4 flex items-start gap-3">
          <Clock className="h-5 w-5 text-amber-600 mt-0.5 shrink-0" />
          <div className="text-sm">
            <p className="font-medium text-amber-900">Prioridade</p>
            <p className="text-amber-800">{resumo.prioridade}</p>
          </div>
        </div>
      )}

      {/* Barra de progresso geral (onda de admissões 2026) */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="font-display text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            Progresso da regularização — onda de admissões 2026 ({total} funcionários)
          </h2>
          {resumo && (
            <span className="text-xs text-muted-foreground font-data tabular-nums">
              {resumo.regularizados_total}/{total} totalmente regularizados ·{' '}
              {resumo.pct_regularizado_total.toFixed(0)}%
            </span>
          )}
        </div>
        <div className="grid gap-4 md:grid-cols-3">
          <ProgressBar
            label="ASO admissional"
            ok={resumo?.aso_ok ?? 0}
            total={total}
            pct={resumo?.pct_aso ?? 0}
            icon={<Stethoscope className="h-4 w-4 text-blue-600" />}
            href={EXAMES_HREF}
            hrefLabel="Carga retroativa de ASO →"
          />
          <ProgressBar
            label="Entrega de EPI (ficha assinada)"
            ok={resumo?.epi_ok ?? 0}
            total={total}
            pct={resumo?.pct_epi ?? 0}
            icon={<HardHat className="h-4 w-4 text-orange-600" />}
            href={EPI_HREF}
            hrefLabel="Gerar ficha de EPI →"
          />
          <ProgressBar
            label="Treinamento NR obrigatório"
            ok={resumo?.treinamento_ok ?? 0}
            total={total}
            pct={resumo?.pct_treinamento ?? 0}
            icon={<GraduationCap className="h-4 w-4 text-purple-600" />}
            href={TREINO_HREF}
            hrefLabel="Registrar treinamento →"
          />
        </div>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar o painel de regularização</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Tabela dos descalços */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <Users className="h-4 w-4" />
                Funcionários a regularizar
                {resumo ? (
                  <Badge className="bg-red-100 text-red-800">{resumo.descalcos}</Badge>
                ) : null}
              </CardTitle>
              <CardDescription>
                Ativos admitidos em 2026 sem ASO admissional. Cada status reflete o fato no banco;
                a lista some conforme a regularização é registrada de verdade.
              </CardDescription>
            </div>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : descalcos.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <CheckCircle2 className="h-16 w-16 mx-auto mb-4 text-green-500 opacity-70" />
              <h3 className="text-lg font-medium">Nenhum descalço pendente</h3>
              <p className="mt-2">Todos os admitidos em 2026 já têm ASO admissional registrado.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Matrícula</TableHead>
                  <TableHead>Nome</TableHead>
                  <TableHead>Cargo</TableHead>
                  <TableHead>Posto</TableHead>
                  <TableHead className="text-center">Dias em aberto</TableHead>
                  <TableHead>ASO</TableHead>
                  <TableHead>EPI</TableHead>
                  <TableHead>Treinamento</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {descalcos.map((c) => (
                  <TableRow key={c.employee_id}>
                    <TableCell className="font-data tabular-nums text-sm">{c.matricula || '—'}</TableCell>
                    <TableCell className="font-medium">
                      <Link
                        href={`/modulos/gestao-pessoas/saude-ocupacional/prontuario/${c.employee_id}`}
                        className="hover:text-primary hover:underline underline-offset-4"
                        title={`Abrir Prontuário SST 360 de ${c.nome}`}
                      >
                        {c.nome}
                      </Link>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{c.cargo || '—'}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{c.posto}</TableCell>
                    <TableCell className="text-center">
                      <span
                        className={`font-data text-sm font-semibold tabular-nums ${
                          (c.dias_pendente ?? 0) > 90 ? 'text-red-600' : 'text-amber-600'
                        }`}
                      >
                        {c.dias_pendente ?? '—'}
                      </span>
                    </TableCell>
                    <TableCell>
                      <StatusBadge ok={c.aso_ok} label={c.aso_ok ? 'ASO OK' : 'Sem ASO'} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge ok={c.epi_ok} label={c.epi_ok ? 'EPI OK' : 'Sem ficha'} />
                    </TableCell>
                    <TableCell>
                      <StatusBadge
                        ok={c.treinamento_ok}
                        label={
                          c.treinamento_ok
                            ? 'Treino OK'
                            : `${c.treinamentos_feitos}/${c.treinamentos_obrigatorios}`
                        }
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Bloco de ASOs vencidos (renovação) */}
      <Card className="border-orange-200">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-base flex items-center gap-2">
                <RefreshCw className="h-4 w-4 text-orange-600" />
                ASOs vencidos — renovação periódica
                {vencidos ? (
                  <Badge className="bg-orange-100 text-orange-800">
                    {vencidos.funcionarios_pendentes ?? 0}
                  </Badge>
                ) : null}
              </CardTitle>
              <CardDescription>
                Funcionários ativos cujo último ASO já venceu (NR-7 — exame periódico). Agende a
                renovação em lote pela tela de Exames.
              </CardDescription>
            </div>
            <Link
              href={EXAMES_HREF}
              className="text-sm font-medium text-primary hover:underline underline-offset-4 whitespace-nowrap"
            >
              Agendar renovação →
            </Link>
          </div>
        </CardHeader>
        {vencidos && (vencidos.resumo_por_posto?.length ?? 0) > 0 && (
          <CardContent className="pt-0">
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {vencidos.resumo_por_posto!.slice(0, 6).map((g) => (
                <div
                  key={g.posto_nome}
                  className="flex items-center justify-between rounded-md border px-3 py-2 text-sm"
                >
                  <span className="truncate text-muted-foreground">{g.posto_nome}</span>
                  <span className="font-data tabular-nums font-semibold text-orange-600">
                    {g.pendentes}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        )}
      </Card>

      {/* Nota de honestidade */}
      {data && (
        <Card className="border-blue-200 bg-blue-50/50">
          <CardContent className="p-4 text-sm text-muted-foreground space-y-1">
            <p className="font-medium text-foreground">Como o painel avança</p>
            <p>{data.nota}</p>
            <p>
              Treinamentos NR obrigatórios avaliados: {data.cursos_obrigatorios.join(', ')}.
            </p>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
