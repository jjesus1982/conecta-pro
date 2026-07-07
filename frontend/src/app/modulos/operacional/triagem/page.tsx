'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  ArrowLeft,
  CalendarX,
  CheckCircle2,
  MessageSquare,
  RefreshCw,
  ShieldAlert,
  Star,
  Wrench,
} from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

// ── Tipos (defensivos — campos podem variar levemente no backend) ────────────
interface OcorrenciaItem {
  id: string;
  title?: string;
  titulo?: string;
  severity?: string;
  severidade?: string;
  occurrence_type?: string;
  post_name?: string;
  posto?: string;
  posto_nome?: string;
  occurred_at?: string | null;
  created_at?: string | null;
  criado_em?: string | null;
  employee_name?: string | null;
  funcionario_nome?: string | null;
}

interface PainelTriagem {
  ocorrencias?: {
    abertas_total?: number;
    por_severidade?: Record<string, number>;
    por_posto?: Array<Record<string, unknown>>;
    lista?: OcorrenciaItem[];
  };
  passagens_hoje?: Array<Record<string, unknown>>;
  avaliacoes_semana?: {
    total?: number;
    media_geral?: number | null;
    por_posto?: Array<Record<string, unknown>>;
  };
  escalas?: {
    sem_vigencia?: Array<Record<string, unknown>>;
    drafts?: Array<Record<string, unknown>>;
  };
}

const SEVERIDADE_BADGE: Record<string, string> = {
  leve: 'bg-green-100 text-green-800',
  moderada: 'bg-yellow-100 text-yellow-800',
  grave: 'bg-orange-100 text-orange-800',
  gravissima: 'bg-red-100 text-red-800',
};

const SEVERIDADE_LABEL: Record<string, string> = {
  leve: 'Leve',
  moderada: 'Moderada',
  grave: 'Grave',
  gravissima: 'Gravíssima',
};

const MIN_ACAO = 10;

function str(obj: Record<string, unknown>, ...keys: string[]): string {
  for (const k of keys) {
    const v = obj[k];
    if (typeof v === 'string' && v) return v;
    if (typeof v === 'number') return String(v);
  }
  return '';
}

function formatarQuando(raw?: string | null): string {
  if (!raw) return '';
  const d = new Date(raw);
  if (Number.isNaN(d.getTime())) return String(raw);
  return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export default function TriagemPage() {
  const [painel, setPainel] = useState<PainelTriagem | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [acessoNegado, setAcessoNegado] = useState(false);
  const [erroCarga, setErroCarga] = useState<string | null>(null);

  // Modais
  const [ocorrenciaAlvo, setOcorrenciaAlvo] = useState<OcorrenciaItem | null>(null);
  const [modo, setModo] = useState<'resolver' | 'comentar' | null>(null);
  const [acaoCorretiva, setAcaoCorretiva] = useState('');
  const [notasResolucao, setNotasResolucao] = useState('');
  const [comentario, setComentario] = useState('');
  const [enviando, setEnviando] = useState(false);

  const carregar = useCallback(async () => {
    setCarregando(true);
    setErroCarga(null);
    try {
      const res = await api.get('/api/v1/operacional/triagem/painel');
      setPainel(res.data || {});
      setAcessoNegado(false);
    } catch (err: unknown) {
      const e = err as { response?: { status?: number } };
      if (e.response?.status === 403) {
        setAcessoNegado(true);
      } else {
        setErroCarga('Não foi possível carregar o painel de triagem.');
      }
    } finally {
      setCarregando(false);
    }
  }, []);

  useEffect(() => {
    carregar();
  }, [carregar]);

  const fecharModal = () => {
    setModo(null);
    setOcorrenciaAlvo(null);
    setAcaoCorretiva('');
    setNotasResolucao('');
    setComentario('');
  };

  const resolver = async () => {
    if (!ocorrenciaAlvo) return;
    if (acaoCorretiva.trim().length < MIN_ACAO) {
      toast.error(`Descreva a ação corretiva (mínimo ${MIN_ACAO} caracteres)`);
      return;
    }
    setEnviando(true);
    try {
      const payload: Record<string, unknown> = { corrective_action: acaoCorretiva.trim() };
      if (notasResolucao.trim()) payload.resolution_notes = notasResolucao.trim();
      await api.post(`/api/v1/operacional/occurrences/${ocorrenciaAlvo.id}/resolve`, payload);
      toast.success('Ocorrência tratada');
      fecharModal();
      carregar();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: unknown } } };
      const detail = e.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Erro ao tratar a ocorrência.');
    } finally {
      setEnviando(false);
    }
  };

  const comentar = async () => {
    if (!ocorrenciaAlvo) return;
    if (!comentario.trim()) {
      toast.error('Escreva o comentário');
      return;
    }
    setEnviando(true);
    try {
      await api.post(`/api/v1/operacional/occurrences/${ocorrenciaAlvo.id}/comments`, {
        content: comentario.trim(),
      });
      toast.success('Comentário registrado');
      fecharModal();
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: unknown } } };
      const detail = e.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'Erro ao comentar.');
    } finally {
      setEnviando(false);
    }
  };

  const ocorrencias = painel?.ocorrencias;
  const listaOcorrencias = ocorrencias?.lista || [];
  const porSeveridade = ocorrencias?.por_severidade || {};
  const semVigencia = painel?.escalas?.sem_vigencia || [];
  const drafts = painel?.escalas?.drafts || [];
  const passagensHoje = painel?.passagens_hoje || [];
  const avaliacoes = painel?.avaliacoes_semana;

  const severidadesOrdenadas = useMemo(
    () =>
      ['gravissima', 'grave', 'moderada', 'leve']
        .filter((s) => (porSeveridade[s] ?? 0) > 0)
        .map((s) => ({ sev: s, qtd: porSeveridade[s] as number })),
    [porSeveridade],
  );

  if (acessoNegado) {
    return (
      <div className="mx-auto w-full max-w-lg p-4">
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-12 text-center">
            <ShieldAlert className="h-10 w-10 text-amber-500" />
            <p className="font-semibold">Acesso restrito à gestão operacional</p>
            <p className="text-sm text-muted-foreground">
              Este painel é exclusivo para gestores. Se você precisa dele, fale com a administração.
            </p>
            <Link href="/modulos/operacional">
              <Button variant="outline">Voltar ao Operacional</Button>
            </Link>
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 p-4 pb-24">
      <div className="flex items-center gap-2">
        <Link href="/modulos/operacional">
          <Button variant="ghost" size="icon" aria-label="Voltar">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="flex items-center gap-2 text-xl font-bold">
            <AlertTriangle className="h-5 w-5 text-amber-500" />
            Triagem Operacional
          </h1>
          <p className="text-sm text-muted-foreground">
            Ocorrências, passagens e avaliações que precisam de atenção da gestão
          </p>
        </div>
        <Button variant="ghost" size="icon" aria-label="Atualizar" onClick={carregar} disabled={carregando}>
          <RefreshCw className={`h-4 w-4 ${carregando ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {erroCarga && (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">{erroCarga}</CardContent>
        </Card>
      )}

      {carregando && !painel ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">Carregando painel…</CardContent>
        </Card>
      ) : painel ? (
        <>
          {/* Cards de topo */}
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  <AlertTriangle className="h-4 w-4" /> Ocorrências abertas
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{ocorrencias?.abertas_total ?? 0}</p>
                <div className="mt-2 flex flex-wrap gap-1">
                  {severidadesOrdenadas.length === 0 ? (
                    <span className="text-xs text-muted-foreground">Nenhuma pendente</span>
                  ) : (
                    severidadesOrdenadas.map(({ sev, qtd }) => (
                      <Badge key={sev} className={SEVERIDADE_BADGE[sev] || 'bg-gray-100 text-gray-800'}>
                        {SEVERIDADE_LABEL[sev] || sev}: {qtd}
                      </Badge>
                    ))
                  )}
                </div>
              </CardContent>
            </Card>

            <Card className={semVigencia.length > 0 ? 'border-amber-400' : ''}>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  <CalendarX className="h-4 w-4" /> Postos sem escala vigente
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">{semVigencia.length}</p>
                {semVigencia.length === 0 ? (
                  <p className="mt-2 text-xs text-muted-foreground">Todos os postos com escala vigente</p>
                ) : (
                  <ul className="mt-2 space-y-1">
                    {semVigencia.map((p, i) => (
                      <li key={i} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">
                        {str(p, 'nome', 'name', 'post_name', 'posto') || 'Posto sem identificação'}
                      </li>
                    ))}
                  </ul>
                )}
                {drafts.length > 0 && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    {drafts.length} escala(s) em rascunho aguardando publicação
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-sm font-medium text-muted-foreground">
                  <Star className="h-4 w-4" /> Avaliações da semana
                </CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-3xl font-bold">
                  {typeof avaliacoes?.media_geral === 'number' ? avaliacoes.media_geral.toFixed(1) : '—'}
                  <span className="text-base font-normal text-muted-foreground"> / 5</span>
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {avaliacoes?.total ?? 0} avaliação(ões) registradas na semana
                </p>
              </CardContent>
            </Card>
          </div>

          {/* Ocorrências abertas */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Ocorrências abertas</CardTitle>
            </CardHeader>
            <CardContent>
              {listaOcorrencias.length === 0 ? (
                <p className="flex items-center gap-2 text-sm text-muted-foreground">
                  <CheckCircle2 className="h-4 w-4 text-green-600" /> Nenhuma ocorrência aberta.
                </p>
              ) : (
                <div className="space-y-3">
                  {listaOcorrencias.map((o) => {
                    const sev = (o.severity || o.severidade || '').toLowerCase();
                    return (
                      <div
                        key={o.id}
                        className="flex flex-col gap-2 rounded-lg border border-[hsl(var(--border))] p-3 md:flex-row md:items-center md:justify-between"
                      >
                        <div className="min-w-0">
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge className={SEVERIDADE_BADGE[sev] || 'bg-gray-100 text-gray-800'}>
                              {SEVERIDADE_LABEL[sev] || sev || '—'}
                            </Badge>
                            <span className="text-xs text-muted-foreground">
                              {o.post_name || o.posto_nome || o.posto || ''}
                            </span>
                            <span className="text-xs text-muted-foreground">
                              {formatarQuando(o.occurred_at || o.created_at || o.criado_em)}
                            </span>
                          </div>
                          <p className="mt-1 truncate font-medium">{o.title || o.titulo || 'Ocorrência'}</p>
                          {(o.employee_name || o.funcionario_nome) && (
                            <p className="text-xs text-muted-foreground">
                              Funcionário: {o.employee_name || o.funcionario_nome}
                            </p>
                          )}
                        </div>
                        <div className="flex shrink-0 gap-2">
                          <Button
                            size="sm"
                            onClick={() => {
                              setOcorrenciaAlvo(o);
                              setModo('resolver');
                            }}
                          >
                            <Wrench className="mr-1 h-4 w-4" /> Tratar
                          </Button>
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => {
                              setOcorrenciaAlvo(o);
                              setModo('comentar');
                            }}
                          >
                            <MessageSquare className="mr-1 h-4 w-4" /> Comentar
                          </Button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Passagens de hoje */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Passagens de turno de hoje</CardTitle>
            </CardHeader>
            <CardContent>
              {passagensHoje.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nenhuma passagem registrada hoje.</p>
              ) : (
                <div className="space-y-2">
                  {passagensHoje.map((p, i) => (
                    <div key={str(p, 'id') || i} className="rounded-lg border border-[hsl(var(--border))] p-3">
                      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                        <Badge variant="secondary">{str(p, 'turno') || 'turno'}</Badge>
                        <span>{str(p, 'post_name', 'posto_nome', 'posto')}</span>
                        <span>{formatarQuando(str(p, 'data_turno', 'created_at', 'criado_em') || null)}</span>
                        {(str(p, 'autor_nome', 'registrado_por_nome')) && (
                          <span>por {str(p, 'autor_nome', 'registrado_por_nome')}</span>
                        )}
                      </div>
                      {str(p, 'resumo') && <p className="mt-1 text-sm">{str(p, 'resumo')}</p>}
                      {str(p, 'pendencias') && (
                        <p className="mt-1 text-sm text-amber-700">
                          <span className="font-semibold">Pendências: </span>
                          {str(p, 'pendencias')}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          {/* Avaliações por posto */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Avaliações por posto (semana)</CardTitle>
            </CardHeader>
            <CardContent>
              {!avaliacoes?.por_posto || avaliacoes.por_posto.length === 0 ? (
                <p className="text-sm text-muted-foreground">Ainda sem avaliações nesta semana.</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b text-left text-xs text-muted-foreground">
                        <th className="py-2 pr-2 font-medium">Posto</th>
                        <th className="py-2 pr-2 text-center font-medium">Média</th>
                        <th className="py-2 text-center font-medium">Total</th>
                      </tr>
                    </thead>
                    <tbody>
                      {avaliacoes.por_posto.map((p, i) => {
                        const media = p['media'] ?? p['media_geral'];
                        const total = p['total'] ?? p['total_avaliacoes'];
                        return (
                          <tr key={i} className="border-b last:border-0">
                            <td className="py-2 pr-2">{str(p, 'posto', 'post_name', 'posto_nome', 'nome') || '—'}</td>
                            <td className="py-2 pr-2 text-center font-semibold">
                              {typeof media === 'number' ? media.toFixed(1) : '—'}
                            </td>
                            <td className="py-2 text-center">{typeof total === 'number' ? total : '—'}</td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </CardContent>
          </Card>
        </>
      ) : null}

      {/* Modal Tratar */}
      <Dialog open={modo === 'resolver'} onOpenChange={(aberto) => !aberto && fecharModal()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Tratar ocorrência</DialogTitle>
            <DialogDescription>
              {ocorrenciaAlvo?.title || ocorrenciaAlvo?.titulo || ''}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium">
                Ação corretiva <span className="text-red-500">*</span>
              </label>
              <Textarea
                value={acaoCorretiva}
                onChange={(e) => setAcaoCorretiva(e.target.value)}
                placeholder="O que foi feito para tratar a ocorrência?"
                rows={3}
              />
              {acaoCorretiva.trim().length < MIN_ACAO && (
                <p className="mt-1 text-xs text-amber-600">
                  Mínimo {MIN_ACAO} caracteres (faltam {Math.max(0, MIN_ACAO - acaoCorretiva.trim().length)})
                </p>
              )}
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Notas de resolução (opcional)</label>
              <Textarea
                value={notasResolucao}
                onChange={(e) => setNotasResolucao(e.target.value)}
                placeholder="Contexto adicional"
                rows={2}
              />
            </div>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={fecharModal} disabled={enviando}>
              Cancelar
            </Button>
            <Button onClick={resolver} isLoading={enviando} disabled={acaoCorretiva.trim().length < MIN_ACAO}>
              Concluir tratamento
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Modal Comentar */}
      <Dialog open={modo === 'comentar'} onOpenChange={(aberto) => !aberto && fecharModal()}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Comentar ocorrência</DialogTitle>
            <DialogDescription>
              {ocorrenciaAlvo?.title || ocorrenciaAlvo?.titulo || ''}
            </DialogDescription>
          </DialogHeader>
          <Textarea
            value={comentario}
            onChange={(e) => setComentario(e.target.value)}
            placeholder="Escreva o comentário para o registro da ocorrência…"
            rows={3}
          />
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={fecharModal} disabled={enviando}>
              Cancelar
            </Button>
            <Button onClick={comentar} isLoading={enviando} disabled={!comentario.trim()}>
              Enviar comentário
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
