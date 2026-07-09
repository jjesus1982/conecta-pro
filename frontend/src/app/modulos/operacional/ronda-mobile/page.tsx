'use client';

/**
 * Ronda Mobile — execução de ronda com checkpoint georreferenciado.
 *
 * Mobile-first: o supervisor/líder executa a ronda pelo celular.
 * Backend: /api/v1/operacional/rondas (inspection_rounds).
 */

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Clock,
  Flag,
  Loader2,
  MapPin,
  MapPinOff,
  Pause,
  Play,
  Plus,
  Route,
  Zap,
} from 'lucide-react';
import { toast } from 'sonner';
import axios from 'axios';
import { api } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Textarea } from '@/components/ui/textarea';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

// ── Constantes ───────────────────────────────────────────────────────────────
const RONDAS_URL = '/api/v1/operacional/rondas';
const POSTS_URL = '/api/v1/operacional/posts';
// Tenant único do sistema (mesmo valor das rondas existentes no banco)
const TENANT_ID = '00000000-0000-0000-0000-000000000000';

const CHECKPOINT_TYPES = [
  { value: 'verificacao_posto', label: 'Verificação de posto' },
  { value: 'verificacao_funcionario', label: 'Verificação de funcionário' },
  { value: 'observacao_geral', label: 'Observação geral' },
];

const CHECKPOINT_STATUS = [
  { value: 'conforme', label: 'Conforme' },
  { value: 'nao_conforme', label: 'Não conforme' },
];

// ── Tipos (espelham os schemas Pydantic do backend) ─────────────────────────
interface PostoAtivo {
  id: string;
  name: string;
  code?: string;
  address?: string | null;
}

interface Checkpoint {
  id: string;
  post_id: string | null;
  post_name: string | null;
  checkpoint_type: string;
  status: string;
  observations: string | null;
  latitude: number | null;
  longitude: number | null;
  sequence: number;
  created_at: string;
}

interface Ronda {
  id: string;
  code: string;
  status: string;
  inspector_name: string;
  scheduled_date: string | null;
  started_at: string | null;
  completed_at: string | null;
  duration_minutes: number | null;
  posts_to_visit: string[] | null;
  posts_visited: string[] | null;
  total_checkpoints: number;
  total_occurrences: number;
  summary: string | null;
  progress_percentage: number;
  checkpoints?: Checkpoint[] | null;
}

interface RondaResumo {
  id: string;
  code: string;
  status: string;
  scheduled_date: string | null;
  started_at: string | null;
  completed_at: string | null;
  total_checkpoints: number;
  total_occurrences: number;
  progress_percentage: number;
  created_at: string;
}

interface GeoFix {
  latitude: number;
  longitude: number;
  accuracy: number; // metros — só exibido na UI (backend não tem campo accuracy)
}

// ── Helpers ──────────────────────────────────────────────────────────────────
function detalheErro(error: unknown): string {
  if (axios.isAxiosError(error)) {
    const d = (error.response?.data as { detail?: unknown } | undefined)?.detail;
    if (typeof d === 'string') return d;
    if (Array.isArray(d)) {
      return d
        .map((item) => (typeof item === 'object' && item && 'msg' in item ? String((item as { msg: unknown }).msg) : String(item)))
        .join('; ');
    }
    return error.message || 'Erro de conexão com o servidor';
  }
  return error instanceof Error ? error.message : 'Erro desconhecido';
}

/** Pede a posição atual. Resolve null se negado/indisponível/timeout — nunca inventa coordenadas. */
function pedirLocalizacao(): Promise<GeoFix | null> {
  return new Promise((resolve) => {
    if (typeof navigator === 'undefined' || !navigator.geolocation) {
      resolve(null);
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) =>
        resolve({
          latitude: pos.coords.latitude,
          longitude: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        }),
      () => resolve(null),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 30000 }
    );
  });
}

function ehHoje(iso: string | null): boolean {
  if (!iso) return false;
  const d = new Date(iso);
  const hoje = new Date();
  return (
    d.getFullYear() === hoje.getFullYear() &&
    d.getMonth() === hoje.getMonth() &&
    d.getDate() === hoje.getDate()
  );
}

function fmtDuracao(totalSeg: number): string {
  const h = Math.floor(totalSeg / 3600);
  const m = Math.floor((totalSeg % 3600) / 60);
  const s = totalSeg % 60;
  const pad = (n: number) => String(n).padStart(2, '0');
  return h > 0 ? `${pad(h)}:${pad(m)}:${pad(s)}` : `${pad(m)}:${pad(s)}`;
}

const STATUS_LABEL: Record<string, string> = {
  agendada: 'Agendada',
  em_andamento: 'Em andamento',
  pausada: 'Pausada',
  concluida: 'Concluída',
  cancelada: 'Cancelada',
};

const STATUS_COR: Record<string, string> = {
  agendada: 'bg-blue-100 text-blue-700',
  em_andamento: 'bg-green-100 text-green-700',
  pausada: 'bg-yellow-100 text-yellow-700',
  concluida: 'bg-gray-100 text-gray-600',
  cancelada: 'bg-red-100 text-red-600',
};

// ── Cronômetro (desde started_at) ────────────────────────────────────────────
function Cronometro({ desde }: { desde: string }) {
  const [agora, setAgora] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setAgora(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const seg = Math.max(0, Math.floor((agora - new Date(desde).getTime()) / 1000));
  return (
    <span className="font-mono text-3xl font-bold tabular-nums">{fmtDuracao(seg)}</span>
  );
}

// ── Página ───────────────────────────────────────────────────────────────────
export default function RondaMobilePage() {
  const { user, isLoading: authLoading } = useAuth();

  const [rondas, setRondas] = useState<RondaResumo[]>([]);
  const [rondasCarregadas, setRondasCarregadas] = useState(false);
  const [rondaAtiva, setRondaAtiva] = useState<Ronda | null>(null);
  const [rondaConcluida, setRondaConcluida] = useState<Ronda | null>(null);

  const [postos, setPostos] = useState<PostoAtivo[]>([]);
  const [postosCarregados, setPostosCarregados] = useState(false);

  // Nova ronda
  const [criandoRonda, setCriandoRonda] = useState(false); // tela de seleção aberta
  const [postosSelecionados, setPostosSelecionados] = useState<string[]>([]);
  const [salvandoRonda, setSalvandoRonda] = useState(false);

  // Checkpoint
  const [checkpointAberto, setCheckpointAberto] = useState(false);
  const [buscandoGps, setBuscandoGps] = useState(false);
  const [gpsFix, setGpsFix] = useState<GeoFix | null>(null);
  const [gpsFalhou, setGpsFalhou] = useState(false);
  const [cpPostoId, setCpPostoId] = useState('');
  const [cpTipo, setCpTipo] = useState('verificacao_posto');
  const [cpStatus, setCpStatus] = useState('conforme');
  const [cpObs, setCpObs] = useState('');
  const [salvandoCheckpoint, setSalvandoCheckpoint] = useState(false);

  // Concluir
  const [concluirAberto, setConcluirAberto] = useState(false);
  const [resumoFinal, setResumoFinal] = useState('');
  const [acaoEmCurso, setAcaoEmCurso] = useState<string | null>(null);

  const postoNome = useCallback(
    (id: string) => postos.find((p) => p.id === id)?.name || `Posto ${id.slice(0, 8)}…`,
    [postos]
  );

  // ── Carregamento inicial ───────────────────────────────────────────────────
  const carregarPostos = useCallback(async () => {
    try {
      const res = await api.get(`${POSTS_URL}?status=active&page=1&page_size=100`);
      const items: PostoAtivo[] = res.data?.items ?? (Array.isArray(res.data) ? res.data : []);
      setPostos(items);
    } catch (error) {
      toast.error(`Erro ao carregar postos: ${detalheErro(error)}`);
    } finally {
      setPostosCarregados(true);
    }
  }, []);

  const carregarDetalheRonda = useCallback(async (id: string): Promise<Ronda | null> => {
    try {
      const res = await api.get(`${RONDAS_URL}/${id}`);
      return res.data as Ronda;
    } catch (error) {
      toast.error(`Erro ao carregar ronda: ${detalheErro(error)}`);
      return null;
    }
  }, []);

  const carregarMinhasRondas = useCallback(async () => {
    if (!user?.id) return;
    try {
      const res = await api.get(
        `${RONDAS_URL}/minhas-rondas?inspector_id=${user.id}&tenant_id=${TENANT_ID}&limit=50`
      );
      const lista: RondaResumo[] = Array.isArray(res.data) ? res.data : [];
      setRondas(lista);
      // Se há ronda em andamento/pausada, abrir direto o modo execução
      const ativa = lista.find((r) => r.status === 'em_andamento' || r.status === 'pausada');
      if (ativa) {
        const detalhe = await carregarDetalheRonda(ativa.id);
        if (detalhe) setRondaAtiva(detalhe);
      }
    } catch (error) {
      toast.error(`Erro ao carregar rondas: ${detalheErro(error)}`);
    } finally {
      setRondasCarregadas(true);
    }
  }, [user?.id, carregarDetalheRonda]);

  const jaCarregou = useRef(false);
  useEffect(() => {
    if (authLoading || !user?.id || jaCarregou.current) return;
    jaCarregou.current = true;
    carregarMinhasRondas();
    carregarPostos();
  }, [authLoading, user?.id, carregarMinhasRondas, carregarPostos]);

  const rondasHoje = useMemo(
    () =>
      rondas.filter(
        (r) =>
          ehHoje(r.scheduled_date) || ehHoje(r.started_at) || ehHoje(r.created_at)
      ),
    [rondas]
  );

  // ── Criar + iniciar ronda ──────────────────────────────────────────────────
  const criarEIniciarRonda = useCallback(async () => {
    if (!user?.id) return;
    if (postosSelecionados.length === 0) {
      toast.error('Selecione pelo menos um posto para a ronda');
      return;
    }
    setSalvandoRonda(true);
    try {
      // 1) Criar (InspectionRoundCreate)
      const criacao = await api.post(`${RONDAS_URL}/`, {
        tenant_id: TENANT_ID,
        inspector_id: user.id,
        inspector_name: user.name || user.email,
        inspector_role: 'supervisor_operacional',
        scheduled_date: new Date().toISOString(),
        posts_to_visit: postosSelecionados,
      });
      const nova = criacao.data as Ronda;

      // 2) Localização de partida (opcional e honesta)
      const fix = await pedirLocalizacao();
      if (!fix) {
        toast.warning('Sem localização — ronda iniciada sem coordenadas de partida');
      }

      // 3) Iniciar (StartRoundRequest: latitude/longitude opcionais)
      const inicio = await api.post(
        `${RONDAS_URL}/${nova.id}/iniciar`,
        fix ? { latitude: fix.latitude, longitude: fix.longitude } : {}
      );
      setRondaAtiva(inicio.data as Ronda);
      setCriandoRonda(false);
      setPostosSelecionados([]);
      toast.success(`Ronda ${nova.code} iniciada`);
    } catch (error) {
      toast.error(detalheErro(error));
    } finally {
      setSalvandoRonda(false);
    }
  }, [user, postosSelecionados]);

  // ── Checkpoint ─────────────────────────────────────────────────────────────
  const abrirCheckpoint = useCallback(async () => {
    setGpsFix(null);
    setGpsFalhou(false);
    setCpPostoId('');
    setCpTipo('verificacao_posto');
    setCpStatus('conforme');
    setCpObs('');
    setCheckpointAberto(true);
    setBuscandoGps(true);
    const fix = await pedirLocalizacao();
    setBuscandoGps(false);
    if (fix) {
      setGpsFix(fix);
    } else {
      setGpsFalhou(true);
      toast.warning('GPS indisponível ou negado — o checkpoint será registrado SEM localização');
    }
  }, []);

  const salvarCheckpoint = useCallback(async () => {
    if (!rondaAtiva) return;
    if (!cpPostoId) {
      toast.error('Selecione o posto do checkpoint');
      return;
    }
    setSalvandoCheckpoint(true);
    try {
      // CheckpointCreate: post_id, post_name, checkpoint_type, status,
      // observations, latitude, longitude (sem campo accuracy no backend)
      await api.post(`${RONDAS_URL}/${rondaAtiva.id}/checkpoints`, {
        post_id: cpPostoId,
        post_name: postoNome(cpPostoId),
        checkpoint_type: cpTipo,
        status: cpStatus,
        observations: cpObs.trim() || null,
        latitude: gpsFix?.latitude ?? null,
        longitude: gpsFix?.longitude ?? null,
      });
      toast.success(
        gpsFix
          ? `Checkpoint registrado (GPS ±${Math.round(gpsFix.accuracy)}m)`
          : 'Checkpoint registrado SEM localização'
      );
      setCheckpointAberto(false);
      const detalhe = await carregarDetalheRonda(rondaAtiva.id);
      if (detalhe) setRondaAtiva(detalhe);
    } catch (error) {
      toast.error(detalheErro(error));
    } finally {
      setSalvandoCheckpoint(false);
    }
  }, [rondaAtiva, cpPostoId, cpTipo, cpStatus, cpObs, gpsFix, postoNome, carregarDetalheRonda]);

  // ── Pausar / Retomar / Concluir ────────────────────────────────────────────
  const acaoRonda = useCallback(
    async (acao: 'pausar' | 'retomar') => {
      if (!rondaAtiva) return;
      setAcaoEmCurso(acao);
      try {
        const res = await api.post(`${RONDAS_URL}/${rondaAtiva.id}/${acao}`);
        setRondaAtiva(res.data as Ronda);
        toast.success(acao === 'pausar' ? 'Ronda pausada' : 'Ronda retomada');
      } catch (error) {
        toast.error(detalheErro(error));
      } finally {
        setAcaoEmCurso(null);
      }
    },
    [rondaAtiva]
  );

  const concluirRonda = useCallback(async () => {
    if (!rondaAtiva) return;
    setAcaoEmCurso('concluir');
    try {
      const fix = await pedirLocalizacao();
      // CompleteRoundRequest: summary, latitude, longitude (todos opcionais)
      const res = await api.post(`${RONDAS_URL}/${rondaAtiva.id}/concluir`, {
        summary: resumoFinal.trim() || null,
        latitude: fix?.latitude ?? null,
        longitude: fix?.longitude ?? null,
      });
      const concluida = res.data as Ronda;
      setRondaConcluida(concluida);
      setRondaAtiva(null);
      setConcluirAberto(false);
      setResumoFinal('');
      toast.success(`Ronda ${concluida.code} concluída`);
    } catch (error) {
      toast.error(detalheErro(error));
    } finally {
      setAcaoEmCurso(null);
    }
  }, [rondaAtiva, resumoFinal]);

  // ── Render ─────────────────────────────────────────────────────────────────
  if (authLoading || (!rondasCarregadas && user)) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!user) {
    return (
      <div className="mx-auto max-w-md p-4">
        <Card>
          <CardContent className="py-8 text-center text-sm text-muted-foreground">
            Faça login para executar rondas.
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── Tela: ronda concluída (resumo) ────────────────────────────────────────
  if (rondaConcluida) {
    const c = rondaConcluida;
    return (
      <div className="mx-auto max-w-md space-y-4 p-4 pb-24">
        <Card className="border-green-300">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-lg">
              <CheckCircle2 className="h-6 w-6 text-green-600" />
              Ronda {c.code} concluída
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid grid-cols-2 gap-3 text-center">
              <div className="rounded-lg bg-muted p-3">
                <div className="text-2xl font-bold">{c.total_checkpoints}</div>
                <div className="text-xs text-muted-foreground">Checkpoints</div>
              </div>
              <div className="rounded-lg bg-muted p-3">
                <div className="text-2xl font-bold">
                  {c.duration_minutes != null ? `${c.duration_minutes} min` : '—'}
                </div>
                <div className="text-xs text-muted-foreground">Duração</div>
              </div>
            </div>
            {(c.posts_visited?.length ?? 0) > 0 && (
              <div className="text-sm">
                <span className="font-medium">Postos visitados:</span>{' '}
                {(c.posts_visited ?? []).map((id) => postoNome(id)).join(', ')}
              </div>
            )}
            {c.summary && (
              <p className="rounded-md bg-muted p-3 text-sm">{c.summary}</p>
            )}
            <Button
              className="h-12 w-full"
              onClick={() => {
                setRondaConcluida(null);
                carregarMinhasRondas();
              }}
            >
              Voltar às minhas rondas
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // ── Tela: ronda em andamento ──────────────────────────────────────────────
  if (rondaAtiva) {
    const r = rondaAtiva;
    const visitados = new Set(r.posts_visited ?? []);
    const pausada = r.status === 'pausada';

    return (
      <div className="mx-auto max-w-md space-y-4 p-4 pb-24">
        {/* Card fixo: status + cronômetro */}
        <Card className={pausada ? 'border-yellow-400' : 'border-green-400'}>
          <CardContent className="py-4">
            <div className="flex items-center justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <Route className="h-5 w-5 text-muted-foreground" />
                  <span className="font-semibold">{r.code}</span>
                  <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${STATUS_COR[r.status] || ''}`}>
                    {STATUS_LABEL[r.status] || r.status}
                  </span>
                </div>
                <div className="mt-1 text-xs text-muted-foreground">
                  {r.total_checkpoints} checkpoint{r.total_checkpoints === 1 ? '' : 's'} registrado{r.total_checkpoints === 1 ? '' : 's'}
                </div>
              </div>
              <div className="text-right">
                {r.started_at ? (
                  <Cronometro desde={r.started_at} />
                ) : (
                  <span className="text-sm text-muted-foreground">não iniciada</span>
                )}
                <div className="text-[10px] text-muted-foreground">desde o início</div>
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Postos a visitar */}
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Postos da ronda</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {(r.posts_to_visit?.length ?? 0) === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhum posto definido nesta ronda.</p>
            ) : (
              (r.posts_to_visit ?? []).map((id) => {
                const visitado = visitados.has(id);
                return (
                  <div
                    key={id}
                    className={`flex items-center justify-between rounded-lg border p-3 ${
                      visitado ? 'border-green-300 bg-green-50' : ''
                    }`}
                  >
                    <span className="text-sm font-medium">{postoNome(id)}</span>
                    {visitado ? (
                      <span className="flex items-center gap-1 text-xs font-medium text-green-700">
                        <CheckCircle2 className="h-4 w-4" /> Visitado
                      </span>
                    ) : (
                      <span className="text-xs text-muted-foreground">Pendente</span>
                    )}
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>

        {/* Botão gigante de checkpoint */}
        {!pausada && !checkpointAberto && (
          <Button
            className="h-20 w-full text-lg font-bold"
            onClick={abrirCheckpoint}
          >
            <MapPin className="mr-2 h-7 w-7" />
            REGISTRAR CHECKPOINT
          </Button>
        )}

        {/* Mini-form de checkpoint */}
        {checkpointAberto && (
          <Card className="border-primary">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Novo checkpoint</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {/* Status do GPS — honesto */}
              {buscandoGps ? (
                <div className="flex items-center gap-2 rounded-md bg-muted p-2 text-sm">
                  <Loader2 className="h-4 w-4 animate-spin" /> Obtendo localização…
                </div>
              ) : gpsFix ? (
                <div className="flex items-center gap-2 rounded-md bg-green-50 p-2 text-sm text-green-700">
                  <MapPin className="h-4 w-4" />
                  {gpsFix.latitude.toFixed(5)}, {gpsFix.longitude.toFixed(5)} (±{Math.round(gpsFix.accuracy)}m)
                </div>
              ) : gpsFalhou ? (
                <div className="flex items-center gap-2 rounded-md bg-yellow-50 p-2 text-sm text-yellow-800">
                  <MapPinOff className="h-4 w-4" />
                  Sem localização — será registrado sem coordenadas
                </div>
              ) : null}

              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">Posto *</label>
                <Select value={cpPostoId} onValueChange={setCpPostoId}>
                  <SelectTrigger className="h-12">
                    <SelectValue placeholder="Selecione o posto" />
                  </SelectTrigger>
                  <SelectContent>
                    {(r.posts_to_visit?.length ? r.posts_to_visit : postos.map((p) => p.id)).map((id) => (
                      <SelectItem key={id} value={id}>
                        {postoNome(id)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Tipo</label>
                  <Select value={cpTipo} onValueChange={setCpTipo}>
                    <SelectTrigger className="h-12">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CHECKPOINT_TYPES.map((t) => (
                        <SelectItem key={t.value} value={t.value}>
                          {t.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <label className="mb-1 block text-xs font-medium text-muted-foreground">Situação</label>
                  <Select value={cpStatus} onValueChange={setCpStatus}>
                    <SelectTrigger className="h-12">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {CHECKPOINT_STATUS.map((s) => (
                        <SelectItem key={s.value} value={s.value}>
                          {s.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Observação (opcional)
                </label>
                <Textarea
                  value={cpObs}
                  onChange={(e) => setCpObs(e.target.value)}
                  placeholder="Ex.: portão principal verificado, tudo em ordem"
                  rows={2}
                />
              </div>

              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="h-12 flex-1"
                  onClick={() => setCheckpointAberto(false)}
                  disabled={salvandoCheckpoint}
                >
                  Cancelar
                </Button>
                <Button
                  className="h-12 flex-1"
                  onClick={salvarCheckpoint}
                  disabled={salvandoCheckpoint || buscandoGps}
                >
                  {salvandoCheckpoint ? <Loader2 className="h-4 w-4 animate-spin" /> : 'Salvar checkpoint'}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Atalho ocorrência */}
        <Link href="/modulos/operacional/ocorrencia-rapida" className="block">
          <Button variant="outline" className="h-12 w-full">
            <Zap className="mr-2 h-5 w-5 text-orange-500" />
            Registrar ocorrência
          </Button>
        </Link>

        {/* Pausar / Retomar / Concluir */}
        <div className="flex gap-2">
          {pausada ? (
            <Button
              variant="outline"
              className="h-12 flex-1"
              onClick={() => acaoRonda('retomar')}
              disabled={acaoEmCurso !== null}
            >
              {acaoEmCurso === 'retomar' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <Play className="mr-2 h-4 w-4" /> Retomar
                </>
              )}
            </Button>
          ) : (
            <Button
              variant="outline"
              className="h-12 flex-1"
              onClick={() => acaoRonda('pausar')}
              disabled={acaoEmCurso !== null}
            >
              {acaoEmCurso === 'pausar' ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <>
                  <Pause className="mr-2 h-4 w-4" /> Pausar
                </>
              )}
            </Button>
          )}
          <Button
            variant="destructive"
            className="h-12 flex-1"
            onClick={() => setConcluirAberto(true)}
            disabled={acaoEmCurso !== null}
          >
            <Flag className="mr-2 h-4 w-4" /> Concluir
          </Button>
        </div>

        {/* Form de conclusão */}
        {concluirAberto && (
          <Card className="border-red-300">
            <CardHeader className="pb-2">
              <CardTitle className="text-base">Concluir ronda</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div>
                <label className="mb-1 block text-xs font-medium text-muted-foreground">
                  Resumo da ronda (opcional)
                </label>
                <Textarea
                  value={resumoFinal}
                  onChange={(e) => setResumoFinal(e.target.value)}
                  placeholder="Como foi a ronda? Algo relevante a registrar?"
                  rows={3}
                />
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  className="h-12 flex-1"
                  onClick={() => setConcluirAberto(false)}
                  disabled={acaoEmCurso === 'concluir'}
                >
                  Voltar
                </Button>
                <Button
                  variant="destructive"
                  className="h-12 flex-1"
                  onClick={concluirRonda}
                  disabled={acaoEmCurso === 'concluir'}
                >
                  {acaoEmCurso === 'concluir' ? (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  ) : (
                    'Confirmar conclusão'
                  )}
                </Button>
              </div>
            </CardContent>
          </Card>
        )}
      </div>
    );
  }

  // ── Tela: nova ronda (seleção de postos) ──────────────────────────────────
  if (criandoRonda) {
    return (
      <div className="mx-auto max-w-md space-y-4 p-4 pb-24">
        <button
          onClick={() => setCriandoRonda(false)}
          className="flex items-center gap-1 text-sm text-muted-foreground"
        >
          <ArrowLeft className="h-4 w-4" /> Voltar
        </button>
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Postos a visitar</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {!postosCarregados ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : postos.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">
                Nenhum posto ativo cadastrado — cadastre postos em Operacional → Postos.
              </p>
            ) : (
              postos.map((p) => {
                const sel = postosSelecionados.includes(p.id);
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() =>
                      setPostosSelecionados((prev) =>
                        sel ? prev.filter((id) => id !== p.id) : [...prev, p.id]
                      )
                    }
                    className={`flex w-full items-center justify-between rounded-lg border p-3 text-left transition-colors ${
                      sel ? 'border-primary bg-primary/10' : 'hover:bg-muted'
                    }`}
                  >
                    <div>
                      <div className="text-sm font-medium">{p.name}</div>
                      {p.address && (
                        <div className="text-xs text-muted-foreground">{p.address}</div>
                      )}
                    </div>
                    {sel && <CheckCircle2 className="h-5 w-5 shrink-0 text-primary" />}
                  </button>
                );
              })
            )}
          </CardContent>
        </Card>
        <Button
          className="h-14 w-full text-base font-bold"
          onClick={criarEIniciarRonda}
          disabled={salvandoRonda || postosSelecionados.length === 0}
        >
          {salvandoRonda ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <>
              <Play className="mr-2 h-5 w-5" />
              Iniciar ronda ({postosSelecionados.length} posto{postosSelecionados.length === 1 ? '' : 's'})
            </>
          )}
        </Button>
      </div>
    );
  }

  // ── Tela inicial: minhas rondas de hoje ───────────────────────────────────
  return (
    <div className="mx-auto max-w-md space-y-4 p-4 pb-24">
      <div>
        <h1 className="text-xl font-bold">Ronda mobile</h1>
        <p className="text-sm text-muted-foreground">
          {user.name || user.email} — rondas de hoje
        </p>
      </div>

      <Button
        className="h-16 w-full text-lg font-bold"
        onClick={() => setCriandoRonda(true)}
      >
        <Plus className="mr-2 h-6 w-6" />
        Iniciar nova ronda
      </Button>

      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Minhas rondas de hoje</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {rondasHoje.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              Nenhuma ronda registrada hoje.
            </p>
          ) : (
            rondasHoje.map((r) => (
              <button
                key={r.id}
                type="button"
                className="flex w-full items-center justify-between rounded-lg border p-3 text-left hover:bg-muted"
                onClick={async () => {
                  const detalhe = await carregarDetalheRonda(r.id);
                  if (!detalhe) return;
                  if (detalhe.status === 'em_andamento' || detalhe.status === 'pausada') {
                    setRondaAtiva(detalhe);
                  } else if (detalhe.status === 'agendada') {
                    // Iniciar ronda agendada
                    try {
                      const fix = await pedirLocalizacao();
                      const res = await api.post(
                        `${RONDAS_URL}/${detalhe.id}/iniciar`,
                        fix ? { latitude: fix.latitude, longitude: fix.longitude } : {}
                      );
                      setRondaAtiva(res.data as Ronda);
                      toast.success(`Ronda ${detalhe.code} iniciada`);
                    } catch (error) {
                      toast.error(detalheErro(error));
                    }
                  } else {
                    setRondaConcluida(detalhe);
                  }
                }}
              >
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold">{r.code}</span>
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUS_COR[r.status] || ''}`}>
                      {STATUS_LABEL[r.status] || r.status}
                    </span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-xs text-muted-foreground">
                    <Clock className="h-3 w-3" />
                    {r.started_at
                      ? new Date(r.started_at).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
                      : 'não iniciada'}
                    <span>· {r.total_checkpoints} checkpoint{r.total_checkpoints === 1 ? '' : 's'}</span>
                    {r.total_occurrences > 0 && (
                      <span className="flex items-center gap-0.5 text-orange-600">
                        <AlertTriangle className="h-3 w-3" /> {r.total_occurrences}
                      </span>
                    )}
                  </div>
                </div>
              </button>
            ))
          )}
        </CardContent>
      </Card>

      <Link href="/modulos/operacional/ocorrencia-rapida" className="block">
        <Button variant="outline" className="h-12 w-full">
          <Zap className="mr-2 h-5 w-5 text-orange-500" />
          Registrar ocorrência
        </Button>
      </Link>
    </div>
  );
}
