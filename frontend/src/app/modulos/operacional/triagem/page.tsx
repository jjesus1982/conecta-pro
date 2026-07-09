'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import {
  AlertCircle,
  AlertTriangle,
  ArrowLeft,
  Bot,
  CalendarDays,
  CalendarX,
  CheckCircle2,
  MessageSquare,
  Plane,
  RefreshCw,
  ShieldAlert,
  Star,
  UserCheck,
  UserMinus,
  Wrench,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
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

// ── Movimentações programadas (chave nova do painel — pode faltar) ──────────
interface MovimentacaoItem {
  data?: string; // 'YYYY-MM-DD'
  tipo?: string; // fim_alocacao | inicio_ferias | retorno_ferias | vaga
  descricao?: string;
}

// ── Presença 30 dias (chave nova do painel — pode faltar; taxa pode ser null)
interface Presenca30dPosto {
  post_nome?: string;
  dias_esperados?: number;
  dias_presentes?: number;
  taxa?: number | null;
}

interface Presenca30d {
  geral?: {
    esperados?: number;
    presentes?: number;
    taxa?: number | null;
  };
  por_posto?: Presenca30dPosto[];
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
  movimentacoes?: MovimentacaoItem[];
  presenca_30d?: Presenca30d;
}

// ── Presença agora (contrato /operacional/presenca/hoje) ─────────────────────
interface PresencaFuncionario {
  employee_id: string;
  nome: string;
  status: 'presente' | 'atrasado' | 'ausente' | 'aguardando';
}

interface PresencaPosto {
  post_id: string;
  post_nome: string;
  esperados?: number;
  presentes?: number;
  atrasados?: number;
  ausentes?: number;
  aguardando?: number;
  funcionarios?: PresencaFuncionario[];
}

interface PresencaHoje {
  atualizado_em?: string;
  resumo?: {
    esperados?: number;
    presentes?: number;
    atrasados?: number;
    ausentes?: number;
    aguardando?: number;
    extras?: number;
  };
  postos?: PresencaPosto[];
}

// ── IA disciplinar (contrato /operacional/medidas-administrativas/ia/recomendar)
const CATEGORIAS_MOTIVO: Array<{ valor: string; rotulo: string }> = [
  { valor: 'falta', rotulo: 'Falta' },
  { valor: 'atraso', rotulo: 'Atraso' },
  { valor: 'insubordinacao', rotulo: 'Insubordinação' },
  { valor: 'indisciplina', rotulo: 'Indisciplina' },
  { valor: 'dano_patrimonio', rotulo: 'Dano ao patrimônio' },
  { valor: 'negligencia', rotulo: 'Negligência' },
  { valor: 'embriaguez', rotulo: 'Embriaguez' },
  { valor: 'abandono_emprego', rotulo: 'Abandono de emprego' },
  { valor: 'ato_improbidade', rotulo: 'Ato de improbidade' },
  { valor: 'violacao_segredo', rotulo: 'Violação de segredo' },
  { valor: 'desistencia_habitual', rotulo: 'Desídia habitual' },
  { valor: 'ofensa_fisica', rotulo: 'Ofensa física' },
  { valor: 'ofensa_moral', rotulo: 'Ofensa moral' },
  { valor: 'jogos_azar', rotulo: 'Jogos de azar' },
  { valor: 'perda_habilitacao', rotulo: 'Perda de habilitação' },
  { valor: 'outros', rotulo: 'Outros' },
];

const MEDIDA_LABEL: Record<string, string> = {
  advertencia_verbal: 'Advertência verbal',
  advertencia_escrita: 'Advertência escrita',
  suspensao: 'Suspensão',
  demissao_justa_causa: 'Demissão por justa causa',
};

interface RecomendacaoIA {
  recommended_action: string;
  confidence_score: number;
  reasoning: string;
  previous_warnings: number;
  previous_suspensions: number;
  last_incident_date?: string | null;
  alternative_actions?: string[];
  legal_references?: string[];
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

// Ícone/cor por tipo de movimentação programada
const MOVIMENTACAO_TIPO: Record<string, { rotulo: string; Icone: LucideIcon; texto: string }> = {
  fim_alocacao: { rotulo: 'Fim de alocação', Icone: UserMinus, texto: 'text-red-600' },
  inicio_ferias: { rotulo: 'Início de férias', Icone: Plane, texto: 'text-blue-600' },
  retorno_ferias: { rotulo: 'Retorno de férias', Icone: UserCheck, texto: 'text-green-600' },
  vaga: { rotulo: 'Vaga em aberto', Icone: AlertCircle, texto: 'text-amber-600' },
};

function dataLocalISO(offsetDias = 0): string {
  const d = new Date();
  d.setDate(d.getDate() + offsetDias);
  const mes = String(d.getMonth() + 1).padStart(2, '0');
  const dia = String(d.getDate()).padStart(2, '0');
  return `${d.getFullYear()}-${mes}-${dia}`;
}

function rotuloDataMovimentacao(iso: string): string {
  if (iso === dataLocalISO(0)) return 'Hoje';
  if (iso === dataLocalISO(1)) return 'Amanhã';
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString('pt-BR', { weekday: 'short', day: '2-digit', month: '2-digit' });
}

// Cor da taxa de presença: ≥90% verde, 75–89% âmbar, <75% vermelho
function corTaxaPresenca(taxa?: number | null): string {
  if (typeof taxa !== 'number') return 'text-muted-foreground';
  if (taxa >= 90) return 'text-green-600';
  if (taxa >= 75) return 'text-amber-600';
  return 'text-red-600';
}

function formatarTaxa(taxa?: number | null): string {
  if (typeof taxa !== 'number') return '—';
  return `${Math.round(taxa)}%`;
}

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

  // Presença agora
  const [presenca, setPresenca] = useState<PresencaHoje | null>(null);
  const [presencaErro, setPresencaErro] = useState(false);

  // Modais
  const [ocorrenciaAlvo, setOcorrenciaAlvo] = useState<OcorrenciaItem | null>(null);
  const [modo, setModo] = useState<'resolver' | 'comentar' | null>(null);
  const [acaoCorretiva, setAcaoCorretiva] = useState('');
  const [notasResolucao, setNotasResolucao] = useState('');
  const [comentario, setComentario] = useState('');
  const [enviando, setEnviando] = useState(false);

  // IA disciplinar
  const [iaAlvo, setIaAlvo] = useState<OcorrenciaItem | null>(null);
  const [iaEmployeeId, setIaEmployeeId] = useState<string | null>(null);
  const [iaIncidentDate, setIaIncidentDate] = useState<string | null>(null);
  const [iaCategoria, setIaCategoria] = useState('outros');
  const [iaDescricao, setIaDescricao] = useState('');
  const [iaCarregandoDetalhe, setIaCarregandoDetalhe] = useState(false);
  const [iaGerando, setIaGerando] = useState(false);
  const [iaResultado, setIaResultado] = useState<RecomendacaoIA | null>(null);

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

  const carregarPresenca = useCallback(async () => {
    try {
      const res = await api.get('/api/v1/operacional/presenca/hoje');
      setPresenca(res.data || {});
      setPresencaErro(false);
    } catch {
      setPresenca(null);
      setPresencaErro(true);
    }
  }, []);

  useEffect(() => {
    carregar();
    carregarPresenca();
  }, [carregar, carregarPresenca]);

  const abrirSugestaoIA = async (o: OcorrenciaItem) => {
    setIaAlvo(o);
    setIaResultado(null);
    setIaEmployeeId(null);
    setIaCategoria('outros');
    setIaDescricao('');
    setIaIncidentDate(null);
    setIaCarregandoDetalhe(true);
    try {
      // O painel não traz o funcionário — buscar o detalhe da ocorrência
      const res = await api.get(`/api/v1/operacional/occurrences/${o.id}`);
      const det = res.data || {};
      setIaEmployeeId(det.employee_involved_id || null);
      const cat = String(det.category || '').toLowerCase();
      if (CATEGORIAS_MOTIVO.some((c) => c.valor === cat)) setIaCategoria(cat);
      setIaDescricao(String(det.description || det.title || o.title || o.titulo || ''));
      const quando = det.occurred_at || o.occurred_at || o.created_at;
      if (quando) {
        const d = new Date(String(quando));
        if (!Number.isNaN(d.getTime())) setIaIncidentDate(d.toISOString().slice(0, 10));
      }
    } catch {
      toast.error('Não foi possível carregar os detalhes da ocorrência.');
      setIaAlvo(null);
    } finally {
      setIaCarregandoDetalhe(false);
    }
  };

  const gerarRecomendacao = async () => {
    if (!iaAlvo || !iaEmployeeId) return;
    if (iaDescricao.trim().length < 10) {
      toast.error('Descreva o incidente (mínimo 10 caracteres)');
      return;
    }
    setIaGerando(true);
    try {
      const res = await api.post('/api/v1/operacional/medidas-administrativas/ia/recomendar', {
        employee_id: iaEmployeeId,
        reason_category: iaCategoria,
        reason_description: iaDescricao.trim(),
        incident_date: iaIncidentDate || new Date().toISOString().slice(0, 10),
      });
      setIaResultado(res.data as RecomendacaoIA);
    } catch (err: unknown) {
      const e = err as { response?: { data?: { detail?: unknown } } };
      const detail = e.response?.data?.detail;
      toast.error(typeof detail === 'string' ? detail : 'A IA não conseguiu gerar a recomendação agora.');
    } finally {
      setIaGerando(false);
    }
  };

  const fecharIA = () => {
    setIaAlvo(null);
    setIaResultado(null);
    setIaEmployeeId(null);
  };

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
  // Chaves novas do painel — defensivo: se faltarem, a seção não renderiza
  const movimentacoes = Array.isArray(painel?.movimentacoes) ? painel.movimentacoes : null;
  const presenca30d =
    painel?.presenca_30d && typeof painel.presenca_30d === 'object' ? painel.presenca_30d : null;

  const movimentacoesPorData = useMemo(() => {
    // Backend entrega ordenado por data — preservar a ordem ao agrupar
    const grupos: Array<{ data: string; itens: MovimentacaoItem[] }> = [];
    for (const m of movimentacoes || []) {
      if (!m || typeof m.data !== 'string' || !m.data) continue;
      const grupo = grupos.find((g) => g.data === m.data);
      if (grupo) grupo.itens.push(m);
      else grupos.push({ data: m.data, itens: [m] });
    }
    return grupos;
  }, [movimentacoes]);

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
          {/* Presença agora */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center justify-between gap-2 text-base">
                <span className="flex items-center gap-2">
                  <UserCheck className="h-4 w-4 text-green-600" /> Presença agora
                </span>
                <Link
                  href="/modulos/operacional/presenca"
                  className="text-xs font-normal text-blue-600 hover:underline"
                >
                  Ver quadro completo →
                </Link>
              </CardTitle>
            </CardHeader>
            <CardContent>
              {presencaErro ? (
                <p className="text-sm text-muted-foreground">
                  Presença ao vivo indisponível no momento.
                </p>
              ) : !presenca ? (
                <p className="text-sm text-muted-foreground">Carregando presença…</p>
              ) : (
                <>
                  <div className="flex flex-wrap gap-1.5">
                    <Badge className="bg-slate-100 text-slate-800">
                      {presenca.resumo?.esperados ?? 0} esperados
                    </Badge>
                    <Badge className="bg-green-100 text-green-800">
                      {presenca.resumo?.presentes ?? 0} presentes
                    </Badge>
                    <Badge className="bg-amber-100 text-amber-800">
                      {presenca.resumo?.atrasados ?? 0} atrasados
                    </Badge>
                    <Badge className="bg-red-100 text-red-800">
                      {presenca.resumo?.ausentes ?? 0} ausentes
                    </Badge>
                    <Badge className="bg-gray-100 text-gray-700">
                      {presenca.resumo?.aguardando ?? 0} aguardando
                    </Badge>
                    {(presenca.resumo?.extras ?? 0) > 0 && (
                      <Badge className="bg-blue-100 text-blue-800">
                        {presenca.resumo?.extras} extras
                      </Badge>
                    )}
                  </div>
                  {(() => {
                    const criticos = (presenca.postos || [])
                      .map((p) => ({
                        posto: p.post_nome,
                        pendentes: (p.funcionarios || []).filter(
                          (f) => f.status === 'ausente' || f.status === 'atrasado',
                        ),
                      }))
                      .filter((p) => p.pendentes.length > 0);
                    if (criticos.length === 0) {
                      return (
                        <p className="mt-2 text-xs text-muted-foreground">
                          Nenhum ausente ou atrasado nos postos agora.
                        </p>
                      );
                    }
                    return (
                      <ul className="mt-2 space-y-1">
                        {criticos.map((p) => (
                          <li key={p.posto} className="rounded bg-amber-50 px-2 py-1 text-xs text-amber-900">
                            <span className="font-semibold">{p.posto}: </span>
                            {p.pendentes
                              .map((f) => `${f.nome} (${f.status === 'ausente' ? 'ausente' : 'atrasado'})`)
                              .join(', ')}
                          </li>
                        ))}
                      </ul>
                    );
                  })()}
                </>
              )}
            </CardContent>
          </Card>

          {/* Presença — últimos 30 dias (só renderiza se o backend já enviar a chave) */}
          {presenca30d && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <UserCheck className="h-4 w-4 text-blue-600" /> Presença — últimos 30 dias
                </CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex items-baseline gap-2">
                  <p
                    className={`font-data text-3xl font-bold tabular-nums ${corTaxaPresenca(presenca30d.geral?.taxa)}`}
                  >
                    {formatarTaxa(presenca30d.geral?.taxa)}
                  </p>
                  {typeof presenca30d.geral?.taxa === 'number' ? (
                    <span className="text-xs text-muted-foreground">
                      {presenca30d.geral?.presentes ?? 0}/{presenca30d.geral?.esperados ?? 0} presenças
                      esperadas
                    </span>
                  ) : (
                    <span className="text-xs text-muted-foreground">sem histórico suficiente</span>
                  )}
                </div>
                {(presenca30d.por_posto || []).length > 0 && (
                  <div className="mt-3 overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b text-left text-xs text-muted-foreground">
                          <th className="py-2 pr-2 font-medium">Posto</th>
                          <th className="py-2 pr-2 text-center font-medium">Presentes/Esperados</th>
                          <th className="py-2 text-center font-medium">Taxa</th>
                        </tr>
                      </thead>
                      <tbody>
                        {(presenca30d.por_posto || []).map((p, i) => (
                          <tr key={i} className="border-b last:border-0">
                            <td className="py-2 pr-2">{p.post_nome || '—'}</td>
                            <td className="py-2 pr-2 text-center tabular-nums">
                              {p.dias_presentes ?? 0}/{p.dias_esperados ?? 0}
                            </td>
                            <td
                              className={`py-2 text-center font-semibold tabular-nums ${corTaxaPresenca(p.taxa)}`}
                            >
                              {formatarTaxa(p.taxa)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
                <p className="mt-2 text-[11px] text-muted-foreground">
                  histórico conta a partir das escalas reais (08/07)
                </p>
              </CardContent>
            </Card>
          )}

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

          {/* Movimentações programadas (só renderiza se o backend já enviar a chave) */}
          {movimentacoes !== null && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <CalendarDays className="h-4 w-4 text-blue-600" /> Movimentações programadas
                  <span className="text-xs font-normal text-muted-foreground">próximos 45 dias</span>
                </CardTitle>
              </CardHeader>
              <CardContent>
                {movimentacoesPorData.length === 0 ? (
                  <p className="flex items-center gap-2 text-sm text-muted-foreground">
                    <CheckCircle2 className="h-4 w-4 text-green-600" /> Nenhuma movimentação programada
                    nos próximos 45 dias.
                  </p>
                ) : (
                  <div className="space-y-3">
                    {movimentacoesPorData.map((grupo) => {
                      const destaque =
                        grupo.data === dataLocalISO(0) || grupo.data === dataLocalISO(1);
                      return (
                        <div key={grupo.data} className="flex gap-3">
                          <div className="w-24 shrink-0 pt-0.5">
                            <Badge
                              className={
                                destaque
                                  ? 'bg-blue-600 text-white hover:bg-blue-600'
                                  : 'bg-slate-100 text-slate-700 hover:bg-slate-100'
                              }
                            >
                              {rotuloDataMovimentacao(grupo.data)}
                            </Badge>
                          </div>
                          <ul
                            className={`flex-1 space-y-1 border-l pl-3 ${
                              destaque ? 'border-blue-300' : 'border-[hsl(var(--border))]'
                            }`}
                          >
                            {grupo.itens.map((m, i) => {
                              const cfg = MOVIMENTACAO_TIPO[m.tipo || ''];
                              const Icone = cfg?.Icone || AlertCircle;
                              return (
                                <li key={i} className="flex items-start gap-2 text-sm">
                                  <Icone
                                    className={`mt-0.5 h-4 w-4 shrink-0 ${cfg?.texto || 'text-muted-foreground'}`}
                                  />
                                  <span className={destaque ? 'font-medium' : ''}>
                                    {m.descricao || cfg?.rotulo || m.tipo || 'Movimentação'}
                                  </span>
                                </li>
                              );
                            })}
                          </ul>
                        </div>
                      );
                    })}
                  </div>
                )}
              </CardContent>
            </Card>
          )}

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
                        <div className="flex shrink-0 flex-wrap gap-2">
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
                          <Button size="sm" variant="outline" onClick={() => abrirSugestaoIA(o)}>
                            <Bot className="mr-1 h-4 w-4" /> Sugerir medida (IA)
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

      {/* Modal Sugerir medida (IA) */}
      <Dialog open={!!iaAlvo} onOpenChange={(aberto) => !aberto && fecharIA()}>
        <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Bot className="h-5 w-5 text-violet-600" /> Sugerir medida administrativa (IA)
            </DialogTitle>
            <DialogDescription>{iaAlvo?.title || iaAlvo?.titulo || ''}</DialogDescription>
          </DialogHeader>

          {iaCarregandoDetalhe ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Carregando detalhes da ocorrência…
            </p>
          ) : !iaEmployeeId ? (
            <p className="rounded bg-amber-50 px-3 py-2 text-sm text-amber-900">
              Esta ocorrência não tem funcionário vinculado. A IA precisa do funcionário para
              analisar o histórico disciplinar — vincule o funcionário na ocorrência antes.
            </p>
          ) : iaResultado ? (
            <div className="space-y-3">
              <div className="rounded-lg border border-violet-200 bg-violet-50 p-3">
                <p className="text-xs text-muted-foreground">Medida recomendada</p>
                <p className="text-lg font-bold">
                  {MEDIDA_LABEL[iaResultado.recommended_action] || iaResultado.recommended_action}
                </p>
                <p className="text-xs text-muted-foreground">
                  Confiança: {Math.round((iaResultado.confidence_score ?? 0) * 100)}%
                </p>
              </div>
              <div>
                <p className="text-sm font-medium">Justificativa</p>
                <p className="whitespace-pre-wrap text-sm text-muted-foreground">{iaResultado.reasoning}</p>
              </div>
              <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                <Badge variant="secondary">{iaResultado.previous_warnings} advertência(s) anteriores</Badge>
                <Badge variant="secondary">{iaResultado.previous_suspensions} suspensão(ões) anteriores</Badge>
              </div>
              {(iaResultado.alternative_actions || []).length > 0 && (
                <div>
                  <p className="text-sm font-medium">Alternativas</p>
                  <p className="text-sm text-muted-foreground">
                    {(iaResultado.alternative_actions || [])
                      .map((a) => MEDIDA_LABEL[a] || a)
                      .join(', ')}
                  </p>
                </div>
              )}
              {(iaResultado.legal_references || []).length > 0 && (
                <div>
                  <p className="text-sm font-medium">Referências legais</p>
                  <ul className="list-inside list-disc text-sm text-muted-foreground">
                    {(iaResultado.legal_references || []).map((ref, i) => (
                      <li key={i}>{ref}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="rounded bg-amber-50 px-3 py-2 text-xs text-amber-900">
                Recomendação gerada por IA a partir do histórico — a decisão é humana e deve
                considerar o contexto completo.
              </p>
            </div>
          ) : (
            <div className="space-y-3">
              <div>
                <label className="mb-1 block text-sm font-medium">Categoria do motivo</label>
                <select
                  value={iaCategoria}
                  onChange={(e) => setIaCategoria(e.target.value)}
                  className="w-full rounded-md border border-[hsl(var(--border))] bg-transparent px-3 py-2 text-sm"
                >
                  {CATEGORIAS_MOTIVO.map((c) => (
                    <option key={c.valor} value={c.valor}>
                      {c.rotulo}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium">Descrição do incidente</label>
                <Textarea
                  value={iaDescricao}
                  onChange={(e) => setIaDescricao(e.target.value)}
                  placeholder="O que aconteceu? (mínimo 10 caracteres)"
                  rows={3}
                />
              </div>
              <p className="text-xs text-muted-foreground">
                A IA analisa o histórico disciplinar real do funcionário e sugere a medida conforme a CLT.
              </p>
            </div>
          )}

          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={fecharIA} disabled={iaGerando}>
              Fechar
            </Button>
            {iaEmployeeId && !iaResultado && !iaCarregandoDetalhe && (
              <Button
                onClick={gerarRecomendacao}
                isLoading={iaGerando}
                disabled={iaDescricao.trim().length < 10}
              >
                Gerar recomendação
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
