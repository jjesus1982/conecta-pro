'use client';

/**
 * PRONTUÁRIO SST 360 — dossiê completo de saúde ocupacional por funcionário.
 *
 * O que se abre quando o fiscal pergunta "me mostra o do João": identificação,
 * compliance NR-1 (4 checks + score), ASOs, EPIs (entregas + fichas c/
 * assinatura), riscos da função (PGR GES + Tabela 24), treinamentos NR,
 * afastamentos (estabilidade CCT + eSocial) e CATs (recibos S-2210).
 * Fonte marcada em cada card; vazios honestos; bloco falho não derruba o resto.
 */

import { useState } from 'react';
import Link from 'next/link';
import { useParams } from 'next/navigation';
import {
  AlertTriangle,
  ArrowLeft,
  Biohazard,
  FileDown,
  FileSignature,
  FileWarning,
  GraduationCap,
  HardHat,
  HeartPulse,
  MapPin,
  RefreshCw,
  ShieldAlert,
  ShieldCheck,
  Stethoscope,
  UserMinus,
} from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
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
import { useProntuarioSST } from '@/hooks/sst';
import { sstService } from '@/lib/services/sst';
import type { NR1Funcionario } from '@/lib/services/sst';

// =============================================================================
// HELPERS
// =============================================================================

function fmtData(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso.length <= 10 ? `${iso}T12:00:00` : iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString('pt-BR');
}

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

function BlocoErro({ erro }: { erro: string }) {
  return (
    <div className="flex items-center gap-2 rounded-md border border-destructive/20 bg-destructive/10 px-3 py-2 text-sm text-destructive">
      <AlertTriangle className="h-4 w-4 shrink-0" />
      <span>Bloco indisponível (erro honesto do backend): {erro}</span>
    </div>
  );
}

function Vazio({ mensagem }: { mensagem: string }) {
  return <p className="py-4 text-center text-sm text-muted-foreground">{mensagem}</p>;
}

function FonteNota({ fonte }: { fonte?: string }) {
  if (!fonte) return null;
  return <p className="mt-2 text-[11px] text-muted-foreground/70">Fonte: {fonte}</p>;
}

function okBadge(ok: boolean | null | undefined, labelOk: string, labelNok: string) {
  if (ok === null || ok === undefined) {
    return <Badge variant="outline" className="text-gray-600">Sem fonte</Badge>;
  }
  return (
    <Badge className={ok ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}>
      {ok ? labelOk : labelNok}
    </Badge>
  );
}

function esocialBadge(status?: string | null) {
  const map: Record<string, string> = {
    nao_transmitida: 'bg-gray-100 text-gray-800',
    transmitida: 'bg-blue-100 text-blue-800',
    aceita: 'bg-green-100 text-green-800',
    rejeitada: 'bg-red-100 text-red-800',
    erro: 'bg-red-100 text-red-800',
  };
  if (!status) return <span className="text-xs text-muted-foreground">—</span>;
  return <Badge className={map[status] ?? 'bg-gray-100 text-gray-800'}>{status.replace(/_/g, ' ')}</Badge>;
}

const CHECK_LABELS: { key: keyof NR1Funcionario['checks']; label: string }[] = [
  { key: 'aso', label: 'ASO (NR-7)' },
  { key: 'epi', label: 'Fichas de EPI (NR-6)' },
  { key: 'riscos', label: 'Riscos mapeados (PGR)' },
  { key: 'treinamentos', label: 'Treinamentos NR' },
];

// =============================================================================
// PÁGINA
// =============================================================================

export default function ProntuarioSSTPage() {
  const params = useParams();
  const employeeId = params.employeeId as string;
  const { data, isLoading, error, refetch } = useProntuarioSST(employeeId);
  const [pppBaixando, setPppBaixando] = useState(false);
  const [fichaBaixando, setFichaBaixando] = useState<string | null>(null);

  const handleBaixarPPP = async () => {
    setPppBaixando(true);
    try {
      const blob = await sstService.downloadPPPPdf(employeeId);
      const slug = (data?.identificacao?.nome ?? employeeId)
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '-')
        .slice(0, 40);
      baixarBlob(blob, `ppp-${slug}.pdf`);
      toast.success('PPP baixado', { duration: 4000 });
    } catch {
      toast.error('Erro ao gerar o PPP em PDF', { duration: 5000 });
    } finally {
      setPppBaixando(false);
    }
  };

  const handleBaixarFichaEPI = async (fichaId: string) => {
    setFichaBaixando(fichaId);
    try {
      const blob = await sstService.downloadFichaEPIPdf(fichaId);
      baixarBlob(blob, `ficha-epi-${fichaId.slice(0, 8)}.pdf`);
      toast.success('Ficha de EPI baixada', { duration: 4000 });
    } catch {
      toast.error('Erro ao gerar a Ficha de EPI em PDF', { duration: 5000 });
    } finally {
      setFichaBaixando(null);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6 pb-28">
        <div className="h-8 w-72 animate-pulse rounded bg-muted" />
        <div className="grid gap-4 md:grid-cols-2">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-48 animate-pulse rounded-lg bg-muted" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !data) {
    const status = (error as { response?: { status?: number } })?.response?.status;
    return (
      <div className="space-y-6 pb-28">
        <Link
          href="/modulos/gestao-pessoas/saude-ocupacional/prontuario"
          className="inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Voltar à busca
        </Link>
        <div className="flex items-center gap-3 rounded-lg border border-destructive/20 bg-destructive/10 p-4">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="flex-1 text-sm text-destructive">
            {status === 404
              ? 'Funcionário não encontrado.'
              : 'Erro ao carregar o prontuário SST.'}
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      </div>
    );
  }

  const ident = data.identificacao;
  const comp = data.compliance;
  const asos = data.asos;
  const epis = data.epis;
  const riscos = data.riscos_funcao;
  const treinos = data.treinamentos;
  const afs = data.afastamentos;
  const cats = data.cats;

  return (
    <div className="space-y-6 pb-28">
      {/* ============ CABEÇALHO — identificação + situação ============ */}
      <div>
        <Link
          href="/modulos/gestao-pessoas/saude-ocupacional/prontuario"
          className="mb-2 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Prontuários SST
        </Link>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="font-display flex items-center gap-2 text-2xl font-bold text-[hsl(var(--foreground))]">
              <HeartPulse className="h-6 w-6" />
              {ident.nome}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-muted-foreground">
              <span>{ident.cargo || 'Cargo não informado'}</span>
              {ident.matricula && (
                <span className="font-data tabular-nums">mat. {ident.matricula}</span>
              )}
              <span>Admissão: {fmtData(ident.data_admissao)}</span>
              {ident.data_demissao && <span>Demissão: {fmtData(ident.data_demissao)}</span>}
              <span className="inline-flex items-center gap-1">
                <MapPin className="h-3.5 w-3.5" />
                {ident.posto_atual?.nome ?? 'Sem posto ativo'}
              </span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {comp.calcado === true && (
              <Badge className="bg-green-100 text-green-800 text-sm">
                <ShieldCheck className="mr-1 h-3.5 w-3.5" /> Calçado
              </Badge>
            )}
            {comp.calcado === false && (
              <Badge className="bg-red-100 text-red-800 text-sm">
                <ShieldAlert className="mr-1 h-3.5 w-3.5" /> Descalçado
              </Badge>
            )}
            {ident.status !== 'ativo' && (
              <Badge variant="outline">status: {ident.status}</Badge>
            )}
            <Button onClick={handleBaixarPPP} disabled={pppBaixando}>
              <FileDown className={`mr-2 h-4 w-4 ${pppBaixando ? 'animate-pulse' : ''}`} />
              {pppBaixando ? 'Gerando...' : 'PPP PDF'}
            </Button>
            <Button variant="outline" size="icon" onClick={() => refetch()} title="Atualizar">
              <RefreshCw className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>

      {/* ============ COMPLIANCE NR-1 ============ */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="font-display flex items-center gap-2 text-base">
            <ShieldCheck className="h-4 w-4" /> Situação de Compliance NR-1
          </CardTitle>
          <CardDescription>Os 4 checks + score — fatos no banco, nada estimado</CardDescription>
        </CardHeader>
        <CardContent>
          {comp.erro ? (
            <BlocoErro erro={comp.erro} />
          ) : comp.checks ? (
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <div>
                <p className="text-xs text-muted-foreground">Score</p>
                <p
                  className={`font-data text-3xl font-semibold tabular-nums ${
                    (comp.score ?? 0) >= 80
                      ? 'text-green-600'
                      : (comp.score ?? 0) >= 50
                        ? 'text-yellow-600'
                        : 'text-red-600'
                  }`}
                >
                  {comp.score ?? '—'}
                </p>
              </div>
              {CHECK_LABELS.map(({ key, label }) => {
                const check = comp.checks![key];
                return (
                  <div key={key} className="space-y-1">
                    <p className="text-xs text-muted-foreground">{label}</p>
                    {okBadge(check.ok, 'OK', 'Pendente')}
                    <p className="text-xs text-muted-foreground">{check.situacao}</p>
                  </div>
                );
              })}
            </div>
          ) : (
            <Vazio mensagem={comp.nota ?? 'Compliance não avaliado para este funcionário.'} />
          )}
          <FonteNota fonte={comp.fonte} />
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        {/* ============ ASOs ============ */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="font-display flex items-center gap-2 text-base">
              <Stethoscope className="h-4 w-4" /> ASOs — Exames Ocupacionais
            </CardTitle>
            <CardDescription>
              {asos.erro
                ? 'Bloco com erro'
                : asos.proximo_vencimento
                  ? `Próximo vencimento: ${fmtData(asos.proximo_vencimento)}${asos.vencido ? ' (VENCIDO)' : ''}`
                  : 'Sem ASO com validade registrada'}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 px-6 pb-4">
            {asos.erro ? (
              <BlocoErro erro={asos.erro} />
            ) : (asos.historico ?? []).length === 0 ? (
              <Vazio mensagem="Nenhum ASO registrado — aguardando dado (gp_asos)." />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Realização</TableHead>
                    <TableHead>Validade</TableHead>
                    <TableHead>Apto</TableHead>
                    <TableHead>Clínica</TableHead>
                    <TableHead>eSocial S-2220</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(asos.historico ?? []).map((a) => (
                    <TableRow key={a.aso_id}>
                      <TableCell className="text-sm capitalize">{a.tipo || '—'}</TableCell>
                      <TableCell className="text-sm">{a.status || '—'}</TableCell>
                      <TableCell className="font-data text-sm tabular-nums">
                        {fmtData(a.data_realizacao ?? a.data_agendamento)}
                      </TableCell>
                      <TableCell>
                        <span
                          className={`font-data text-sm tabular-nums ${a.vencido ? 'font-semibold text-red-600' : ''}`}
                        >
                          {fmtData(a.data_validade)}
                        </span>
                      </TableCell>
                      <TableCell>
                        {a.apto === null ? (
                          <span className="text-xs text-muted-foreground">—</span>
                        ) : (
                          okBadge(a.apto, 'Apto', 'Inapto')
                        )}
                      </TableCell>
                      <TableCell className="max-w-[160px] truncate text-sm text-muted-foreground">
                        {a.clinica || '—'}
                      </TableCell>
                      <TableCell>
                        <div className="flex flex-col gap-0.5">
                          {esocialBadge(a.esocial_status)}
                          {a.recibo_s2220 && (
                            <span className="font-data text-[11px] text-muted-foreground">
                              recibo {a.recibo_s2220}
                            </span>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            <FonteNota fonte={asos.fonte} />
          </CardContent>
        </Card>

        {/* ============ EPIs ============ */}
        <Card className="lg:col-span-2">
          <CardHeader className="pb-3">
            <CardTitle className="font-display flex items-center gap-2 text-base">
              <HardHat className="h-4 w-4" /> EPIs — Entregas e Fichas (NR-6)
            </CardTitle>
            <CardDescription>
              {epis.erro ? (
                'Bloco com erro'
              ) : (
                <>
                  <span className="font-data tabular-nums">{epis.total_entregas ?? 0}</span>{' '}
                  entrega(s) ·{' '}
                  <span className="font-data tabular-nums">
                    {epis.fichas_assinadas ?? 0}/{epis.total_fichas ?? 0}
                  </span>{' '}
                  ficha(s) assinada(s)
                </>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 p-0 px-6 pb-4">
            {epis.erro ? (
              <BlocoErro erro={epis.erro} />
            ) : (
              <>
                {(epis.entregas ?? []).length === 0 ? (
                  <Vazio mensagem="Nenhuma entrega de EPI registrada — aguardando dado (gp_epi_deliveries)." />
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>EPI</TableHead>
                        <TableHead>CA</TableHead>
                        <TableHead>Qtd</TableHead>
                        <TableHead>Entrega</TableHead>
                        <TableHead>Validade</TableHead>
                        <TableHead>Ficha</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {(epis.entregas ?? []).map((e) => (
                        <TableRow key={e.delivery_id}>
                          <TableCell className="text-sm font-medium">{e.epi_nome}</TableCell>
                          <TableCell className="font-data text-sm tabular-nums">
                            {e.ca || '—'}
                          </TableCell>
                          <TableCell className="font-data text-sm tabular-nums">
                            {e.quantidade}
                          </TableCell>
                          <TableCell className="font-data text-sm tabular-nums">
                            {fmtData(e.data_entrega)}
                          </TableCell>
                          <TableCell className="font-data text-sm tabular-nums">
                            {fmtData(e.data_validade)}
                          </TableCell>
                          <TableCell>
                            {e.ficha_status === 'assinada' ? (
                              <Badge className="bg-green-100 text-green-800">Assinada</Badge>
                            ) : e.ficha_status === 'pendente_assinatura' ? (
                              <Badge className="bg-yellow-100 text-yellow-800">
                                Pendente assinatura
                              </Badge>
                            ) : (
                              <Badge className="bg-red-100 text-red-800">Sem ficha</Badge>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                )}

                {(epis.fichas ?? []).length > 0 && (
                  <div className="space-y-2">
                    <p className="flex items-center gap-1.5 text-sm font-medium">
                      <FileSignature className="h-4 w-4" /> Fichas de EPI
                    </p>
                    {(epis.fichas ?? []).map((f) => (
                      <div
                        key={f.ficha_id}
                        className="flex flex-wrap items-center justify-between gap-2 rounded-md border p-3"
                      >
                        <div className="min-w-0">
                          <div className="flex items-center gap-2">
                            {f.status === 'assinada' ? (
                              <Badge className="bg-green-100 text-green-800">Assinada</Badge>
                            ) : (
                              <Badge className="bg-yellow-100 text-yellow-800">
                                Pendente assinatura
                              </Badge>
                            )}
                            <span className="font-data text-xs tabular-nums text-muted-foreground">
                              {(f.itens ?? []).length} item(ns) · criada em{' '}
                              {fmtData(f.created_at)}
                            </span>
                          </div>
                          {f.assinado_em && (
                            <p className="mt-1 font-data text-[11px] tabular-nums text-muted-foreground">
                              Assinada em {fmtData(f.assinado_em)} · hash{' '}
                              {(f.assinatura_hash ?? '').slice(0, 16)}…
                            </p>
                          )}
                        </div>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleBaixarFichaEPI(f.ficha_id)}
                          disabled={fichaBaixando === f.ficha_id}
                        >
                          <FileDown
                            className={`mr-1 h-3.5 w-3.5 ${fichaBaixando === f.ficha_id ? 'animate-pulse' : ''}`}
                          />
                          Ficha EPI PDF
                        </Button>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
            <FonteNota fonte={epis.fonte} />
          </CardContent>
        </Card>

        {/* ============ RISCOS DA FUNÇÃO ============ */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="font-display flex items-center gap-2 text-base">
              <Biohazard className="h-4 w-4" /> Riscos da Função (PGR)
            </CardTitle>
            <CardDescription>
              {riscos.erro
                ? 'Bloco com erro'
                : riscos.funcao_token
                  ? `Função ${riscos.funcao_token} — ${riscos.total ?? 0} risco(s) vigente(s)`
                  : (riscos.nota ?? 'Cargo sem token de função no PGR')}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {riscos.erro ? (
              <BlocoErro erro={riscos.erro} />
            ) : (riscos.riscos ?? []).length === 0 ? (
              <Vazio
                mensagem={
                  riscos.funcao_token
                    ? 'Nenhum risco vigente atribuído a esta função (gp_risks).'
                    : 'Cargo não mapeado no PGR — nenhum risco atribuível (honesto, não mascarado).'
                }
              />
            ) : (
              (riscos.riscos ?? []).map((r) => (
                <div key={r.risk_id} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="capitalize">
                      {r.categoria}
                    </Badge>
                    <Badge
                      className={
                        r.nivel === 'critico' || r.nivel === 'alto'
                          ? 'bg-red-100 text-red-800'
                          : r.nivel === 'medio'
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-green-100 text-green-800'
                      }
                    >
                      {r.nivel}
                    </Badge>
                    {r.cod_agente_nocivo && (
                      <span className="font-data text-xs tabular-nums text-muted-foreground">
                        Tabela 24: {r.cod_agente_nocivo}
                      </span>
                    )}
                  </div>
                  <p className="mt-1.5 text-sm">{r.descricao}</p>
                  {r.medicao && (
                    <p className="mt-1 text-xs text-muted-foreground">Medição: {r.medicao}</p>
                  )}
                  {(r.epi_recomendado ?? []).length > 0 && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      EPI: {r.epi_recomendado.join(', ')}
                    </p>
                  )}
                </div>
              ))
            )}
            <FonteNota fonte={riscos.fonte} />
          </CardContent>
        </Card>

        {/* ============ TREINAMENTOS ============ */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="font-display flex items-center gap-2 text-base">
              <GraduationCap className="h-4 w-4" /> Treinamentos NR
            </CardTitle>
            <CardDescription>
              {treinos.erro ? (
                'Bloco com erro'
              ) : (
                <>
                  <span className="font-data tabular-nums">{treinos.total ?? 0}</span>{' '}
                  registro(s)
                </>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0 px-6 pb-4">
            {treinos.erro ? (
              <BlocoErro erro={treinos.erro} />
            ) : (treinos.treinamentos ?? []).length === 0 ? (
              <Vazio mensagem="Nenhum treinamento registrado — aguardando dado (sst_treinamentos)." />
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Norma</TableHead>
                    <TableHead>Realização</TableHead>
                    <TableHead>Vencimento</TableHead>
                    <TableHead>Situação</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(treinos.treinamentos ?? []).map((t) => (
                    <TableRow key={t.id}>
                      <TableCell className="text-sm font-medium">{t.norma}</TableCell>
                      <TableCell className="font-data text-sm tabular-nums">
                        {fmtData(t.data_realizacao)}
                      </TableCell>
                      <TableCell className="font-data text-sm tabular-nums">
                        {fmtData(t.vencimento)}
                      </TableCell>
                      <TableCell>
                        <Badge
                          className={
                            t.situacao === 'em_dia'
                              ? 'bg-green-100 text-green-800'
                              : t.situacao === 'vencendo'
                                ? 'bg-yellow-100 text-yellow-800'
                                : 'bg-red-100 text-red-800'
                          }
                        >
                          {t.situacao.replace(/_/g, ' ')}
                        </Badge>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            <FonteNota fonte={treinos.fonte} />
          </CardContent>
        </Card>

        {/* ============ AFASTAMENTOS ============ */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="font-display flex items-center gap-2 text-base">
              <UserMinus className="h-4 w-4" /> Afastamentos
            </CardTitle>
            <CardDescription>
              {afs.erro ? (
                'Bloco com erro'
              ) : afs.estabilidade_vigente_ate ? (
                <span className="font-medium text-amber-700 dark:text-amber-400">
                  Estabilidade CCT vigente até {fmtData(afs.estabilidade_vigente_ate)}
                </span>
              ) : (
                <>
                  <span className="font-data tabular-nums">{afs.total ?? 0}</span> registro(s)
                  · sem estabilidade vigente
                </>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {afs.erro ? (
              <BlocoErro erro={afs.erro} />
            ) : (afs.afastamentos ?? []).length === 0 ? (
              <Vazio mensagem="Nenhum afastamento registrado — aguardando dado (sst_afastamentos)." />
            ) : (
              (afs.afastamentos ?? []).map((a) => (
                <div key={a.id} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="capitalize">
                      {a.tipo.replace(/_/g, ' ')}
                    </Badge>
                    <Badge
                      className={
                        a.status === 'ativo'
                          ? 'bg-red-100 text-red-800'
                          : 'bg-gray-100 text-gray-800'
                      }
                    >
                      {a.status}
                    </Badge>
                    {a.gera_estabilidade && (
                      <Badge className="bg-amber-100 text-amber-800">
                        Estabilidade até {fmtData(a.estabilidade_ate)}
                      </Badge>
                    )}
                  </div>
                  <p className="mt-1.5 font-data text-sm tabular-nums">
                    {fmtData(a.data_inicio)} →{' '}
                    {a.data_retorno
                      ? `retorno ${fmtData(a.data_retorno)}`
                      : a.data_fim_prevista
                        ? `previsto ${fmtData(a.data_fim_prevista)}`
                        : 'sem data de retorno'}
                    {a.cid ? ` · CID ${a.cid}` : ''}
                  </p>
                  {a.motivo && <p className="mt-1 text-xs text-muted-foreground">{a.motivo}</p>}
                  <div className="mt-1.5 flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground">eSocial S-2230:</span>
                    {esocialBadge(a.esocial_status)}
                    {a.recibo_s2230 && (
                      <span className="font-data tabular-nums text-muted-foreground">
                        recibo {a.recibo_s2230}
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
            <FonteNota fonte={afs.fonte} />
          </CardContent>
        </Card>

        {/* ============ CATs ============ */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="font-display flex items-center gap-2 text-base">
              <FileWarning className="h-4 w-4" /> CATs — Acidentes de Trabalho
            </CardTitle>
            <CardDescription>
              {cats.erro ? (
                'Bloco com erro'
              ) : (
                <>
                  <span className="font-data tabular-nums">{cats.total ?? 0}</span> registro(s)
                </>
              )}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {cats.erro ? (
              <BlocoErro erro={cats.erro} />
            ) : (cats.cats ?? []).length === 0 ? (
              <Vazio mensagem="Nenhuma CAT registrada — sem acidentes de trabalho no banco (gp_cats)." />
            ) : (
              (cats.cats ?? []).map((c) => (
                <div key={c.cat_id} className="rounded-md border p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline" className="capitalize">
                      {c.tipo_acidente}
                    </Badge>
                    <Badge
                      className={
                        c.gravidade === 'grave' || c.gravidade === 'critico'
                          ? 'bg-red-100 text-red-800'
                          : 'bg-yellow-100 text-yellow-800'
                      }
                    >
                      {c.gravidade}
                    </Badge>
                    <span className="font-data text-xs tabular-nums text-muted-foreground">
                      {fmtData(c.data_acidente)}
                      {c.hora_acidente ? ` ${c.hora_acidente}` : ''}
                    </span>
                  </div>
                  <p className="mt-1.5 text-sm">{c.descricao}</p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    Local: {c.local}
                    {c.parte_corpo ? ` · Parte do corpo: ${c.parte_corpo}` : ''}
                    {c.afastamento_dias ? ` · ${c.afastamento_dias} dia(s) de afastamento` : ''}
                  </p>
                  <div className="mt-1.5 flex items-center gap-2 text-xs">
                    <span className="text-muted-foreground">eSocial S-2210:</span>
                    {esocialBadge(c.esocial_status)}
                    {c.recibo_esocial && (
                      <span className="font-data tabular-nums text-muted-foreground">
                        recibo {c.recibo_esocial}
                      </span>
                    )}
                    {c.numero_cat_inss && (
                      <span className="font-data tabular-nums text-muted-foreground">
                        CAT INSS {c.numero_cat_inss}
                      </span>
                    )}
                  </div>
                </div>
              ))
            )}
            <FonteNota fonte={cats.fonte} />
          </CardContent>
        </Card>
      </div>

      {/* Nota de honestidade */}
      <Card className="border-blue-200 bg-blue-50/50 dark:border-blue-900 dark:bg-blue-950/20">
        <CardContent className="p-4 text-sm text-muted-foreground">
          <p className="font-medium text-foreground">Nota de honestidade dos dados</p>
          <p>
            Cada card indica a tabela-fonte real. Blocos vazios significam ausência de registro
            no banco (aguardando dado), nunca valor estimado. Um domínio com erro é exibido como
            erro — não derruba o restante do prontuário. Gerado em {fmtData(data.gerado_em)}.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
