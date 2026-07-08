'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Fingerprint,
  Hand,
  MapPin,
  MapPinOff,
  RefreshCw,
  ScanFace,
  UserCheck,
  UserPlus,
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

// ── Tipos (contrato /operacional/presenca/hoje) ─────────────────────────────
type StatusPresenca = 'presente' | 'atrasado' | 'ausente' | 'aguardando';

interface FuncionarioPresenca {
  employee_id: string;
  nome: string;
  cargo?: string | null;
  shift_id?: string | null;
  turno_inicio?: string | null;
  turno_fim?: string | null;
  status: StatusPresenca;
  presenca_em?: string | null;
  fonte?: 'ponto' | 'manual' | null;
  facial_match?: boolean | null;
  dentro_geofence?: boolean | null;
}

interface ExtraPresenca {
  employee_id: string;
  nome: string;
  presenca_em?: string | null;
  fonte?: string | null;
}

interface PostoPresenca {
  post_id: string;
  post_nome: string;
  esperados: number;
  presentes: number;
  atrasados: number;
  ausentes: number;
  aguardando: number;
  funcionarios: FuncionarioPresenca[];
  extras?: ExtraPresenca[];
}

interface ResumoPresenca {
  esperados?: number;
  presentes?: number;
  atrasados?: number;
  ausentes?: number;
  aguardando?: number;
  extras?: number;
}

interface PresencaHoje {
  data?: string;
  atualizado_em?: string;
  batidas_sincronizadas_ate?: string | null;
  resumo?: ResumoPresenca;
  postos?: PostoPresenca[];
  sem_posto?: FuncionarioPresenca[];
}

const STATUS_BADGE: Record<StatusPresenca, string> = {
  presente: 'bg-green-100 text-green-800',
  atrasado: 'bg-amber-100 text-amber-800',
  ausente: 'bg-red-100 text-red-800',
  aguardando: 'bg-gray-100 text-gray-700',
};

const STATUS_LABEL: Record<StatusPresenca, string> = {
  presente: 'Presente',
  atrasado: 'Atrasado',
  ausente: 'Ausente',
  aguardando: 'Aguardando',
};

function formatarHora(raw?: string | null): string {
  if (!raw) return '';
  // Aceita ISO datetime ou "HH:MM[:SS]"
  const d = new Date(raw);
  if (!Number.isNaN(d.getTime()) && raw.includes('T')) {
    return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }
  const m = String(raw).match(/^(\d{1,2}):(\d{2})/);
  if (m) return `${m[1].padStart(2, '0')}:${m[2]}`;
  return String(raw);
}

function FonteIcone({ fonte }: { fonte?: string | null }) {
  if (fonte === 'ponto') {
    return (
      <span title="Batida Sólides (ponto eletrônico)" className="inline-flex items-center text-muted-foreground">
        <Fingerprint className="h-3.5 w-3.5" />
      </span>
    );
  }
  if (fonte === 'manual') {
    return (
      <span title="Presença marcada manualmente" className="inline-flex items-center text-muted-foreground">
        <Hand className="h-3.5 w-3.5" />
      </span>
    );
  }
  return null;
}

function ChipResumo({ rotulo, valor, classe }: { rotulo: string; valor: number; classe: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-medium ${classe}`}>
      <span className="text-sm font-bold">{valor}</span> {rotulo}
    </span>
  );
}

function LinhaFuncionario({
  f,
  onMarcar,
}: {
  f: FuncionarioPresenca;
  onMarcar: (f: FuncionarioPresenca) => void;
}) {
  const podeMarcar =
    !!f.shift_id && (f.status === 'atrasado' || f.status === 'aguardando' || f.status === 'ausente');
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-[hsl(var(--border))] p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge className={STATUS_BADGE[f.status] || 'bg-gray-100 text-gray-700'}>
          {STATUS_LABEL[f.status] || f.status}
        </Badge>
        <span className="min-w-0 truncate text-sm font-medium">{f.nome}</span>
        {f.cargo && <span className="text-xs text-muted-foreground">{f.cargo}</span>}
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        {(f.turno_inicio || f.turno_fim) && (
          <span>
            Turno {formatarHora(f.turno_inicio)}–{formatarHora(f.turno_fim)}
          </span>
        )}
        {f.presenca_em && (
          <span className="inline-flex items-center gap-1">
            Presença às {formatarHora(f.presenca_em)} <FonteIcone fonte={f.fonte} />
          </span>
        )}
      </div>
      {(f.facial_match === false || f.dentro_geofence === false) && (
        <div className="flex flex-wrap gap-2">
          {f.facial_match === false && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-800">
              <ScanFace className="h-3.5 w-3.5" /> batida sem confirmação facial
            </span>
          )}
          {f.dentro_geofence === false && (
            <span className="inline-flex items-center gap-1 rounded bg-amber-50 px-2 py-0.5 text-xs text-amber-800">
              <MapPinOff className="h-3.5 w-3.5" /> fora do geofence
            </span>
          )}
        </div>
      )}
      {podeMarcar && (
        <div>
          <Button size="sm" variant="outline" onClick={() => onMarcar(f)}>
            <Hand className="mr-1 h-4 w-4" /> Marcar presente (manual)
          </Button>
        </div>
      )}
    </div>
  );
}

export default function PresencaPage() {
  const [dados, setDados] = useState<PresencaHoje | null>(null);
  const [carregando, setCarregando] = useState(true);
  const [erroCarga, setErroCarga] = useState<string | null>(null);
  const [atualizadoLocal, setAtualizadoLocal] = useState<Date | null>(null);

  // Check-in manual
  const [alvo, setAlvo] = useState<FuncionarioPresenca | null>(null);
  const [observacao, setObservacao] = useState('');
  const [enviando, setEnviando] = useState(false);

  const carregandoRef = useRef(false);

  const carregar = useCallback(async (silencioso = false) => {
    if (carregandoRef.current) return;
    carregandoRef.current = true;
    if (!silencioso) setCarregando(true);
    try {
      const res = await api.get('/api/v1/operacional/presenca/hoje');
      setDados(res.data || {});
      setAtualizadoLocal(new Date());
      setErroCarga(null);
    } catch {
      if (!silencioso) setErroCarga('Não foi possível carregar a presença de hoje.');
    } finally {
      carregandoRef.current = false;
      if (!silencioso) setCarregando(false);
    }
  }, []);

  useEffect(() => {
    carregar();
    const timer = setInterval(() => carregar(true), 60_000);
    return () => clearInterval(timer);
  }, [carregar]);

  const marcarPresente = async () => {
    if (!alvo?.shift_id) return;
    setEnviando(true);
    try {
      const payload: Record<string, unknown> = {};
      if (observacao.trim()) payload.observacao = observacao.trim();
      await api.post(`/api/v1/operacional/presenca/checkin-manual/${alvo.shift_id}`, payload);
      toast.success(`Presença de ${alvo.nome} registrada`);
      setAlvo(null);
      setObservacao('');
      carregar(true);
    } catch (err: unknown) {
      const e = err as { response?: { status?: number; data?: { detail?: unknown } } };
      if (e.response?.status === 409) {
        toast.error('Este funcionário já tem presença registrada hoje.');
        carregar(true);
      } else if (e.response?.status === 403) {
        toast.error('Você não tem permissão para marcar presença neste posto.');
      } else {
        const detail = e.response?.data?.detail;
        toast.error(typeof detail === 'string' ? detail : 'Erro ao registrar a presença.');
      }
    } finally {
      setEnviando(false);
    }
  };

  const resumo = dados?.resumo || {};
  const postos = dados?.postos || [];
  const semPosto = dados?.sem_posto || [];
  const horaAtualizacao = dados?.atualizado_em
    ? formatarHora(dados.atualizado_em)
    : atualizadoLocal
      ? atualizadoLocal.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' })
      : '';
  const horaSync = dados?.batidas_sincronizadas_ate ? formatarHora(dados.batidas_sincronizadas_ate) : null;
  // Se a última batida sincronizada do Sólides for antiga, o quadro pode estar defasado
  const syncDefasado = (() => {
    if (!dados?.batidas_sincronizadas_ate) return false;
    const t = new Date(dados.batidas_sincronizadas_ate).getTime();
    return Number.isFinite(t) && Date.now() - t > 90 * 60 * 1000;
  })();
  const totalExtras =
    resumo.extras ?? postos.reduce((acc, p) => acc + (p.extras?.length || 0), 0);
  const semTurnos = postos.length === 0 && semPosto.length === 0;

  return (
    <div className="mx-auto w-full max-w-5xl space-y-4 p-4 pb-24">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Link href="/modulos/operacional">
          <Button variant="ghost" size="icon" aria-label="Voltar">
            <ArrowLeft className="h-5 w-5" />
          </Button>
        </Link>
        <div className="flex-1">
          <h1 className="flex items-center gap-2 text-xl font-bold">
            <UserCheck className="h-5 w-5 text-green-600" />
            Presença Hoje
          </h1>
          <p className="text-sm text-muted-foreground">
            Quem está no posto agora, por batida de ponto ou marcação manual
            {horaAtualizacao && ` — atualizado às ${horaAtualizacao}`}
            {horaSync && ` · batidas Sólides sincronizadas até ${horaSync}`}
          </p>
          {syncDefasado && (
            <p className="mt-1 text-xs font-medium text-amber-600">
              ⚠ Sincronização de batidas defasada — atrasos/ausências podem ser apenas atraso do
              sync, não do funcionário.
            </p>
          )}
        </div>
        <Button
          variant="ghost"
          size="icon"
          aria-label="Atualizar"
          onClick={() => carregar()}
          disabled={carregando}
        >
          <RefreshCw className={`h-4 w-4 ${carregando ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {/* Resumo */}
      {dados && (
        <div className="flex flex-wrap gap-2">
          <ChipResumo rotulo="esperados" valor={resumo.esperados ?? 0} classe="bg-slate-100 text-slate-800" />
          <ChipResumo rotulo="presentes" valor={resumo.presentes ?? 0} classe="bg-green-100 text-green-800" />
          <ChipResumo rotulo="atrasados" valor={resumo.atrasados ?? 0} classe="bg-amber-100 text-amber-800" />
          <ChipResumo rotulo="ausentes" valor={resumo.ausentes ?? 0} classe="bg-red-100 text-red-800" />
          <ChipResumo rotulo="aguardando" valor={resumo.aguardando ?? 0} classe="bg-gray-100 text-gray-700" />
          <ChipResumo rotulo="extras" valor={totalExtras} classe="bg-blue-100 text-blue-800" />
        </div>
      )}

      {erroCarga && (
        <Card>
          <CardContent className="py-6 text-center text-sm text-muted-foreground">{erroCarga}</CardContent>
        </Card>
      )}

      {carregando && !dados ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Carregando presença…
          </CardContent>
        </Card>
      ) : dados && semTurnos ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Nenhum turno programado hoje.
          </CardContent>
        </Card>
      ) : null}

      {/* Um card por posto */}
      {postos.map((posto) => (
        <Card key={posto.post_id}>
          <CardHeader className="pb-2">
            <CardTitle className="flex flex-wrap items-center justify-between gap-2 text-base">
              <span className="flex items-center gap-2">
                <MapPin className="h-4 w-4 text-muted-foreground" />
                {posto.post_nome}
              </span>
              <span className="flex flex-wrap gap-1 text-xs font-normal">
                <Badge className="bg-green-100 text-green-800">{posto.presentes} presente(s)</Badge>
                {posto.atrasados > 0 && (
                  <Badge className="bg-amber-100 text-amber-800">{posto.atrasados} atrasado(s)</Badge>
                )}
                {posto.ausentes > 0 && (
                  <Badge className="bg-red-100 text-red-800">{posto.ausentes} ausente(s)</Badge>
                )}
                {posto.aguardando > 0 && (
                  <Badge className="bg-gray-100 text-gray-700">{posto.aguardando} aguardando</Badge>
                )}
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {(posto.funcionarios || []).length === 0 ? (
              <p className="text-sm text-muted-foreground">Nenhum funcionário escalado neste posto hoje.</p>
            ) : (
              (posto.funcionarios || []).map((f) => (
                <LinhaFuncionario key={`${f.employee_id}-${f.shift_id || ''}`} f={f} onMarcar={setAlvo} />
              ))
            )}

            {(posto.extras || []).length > 0 && (
              <div className="rounded-lg border border-blue-200 bg-blue-50/50 p-2.5">
                <p className="mb-1 flex items-center gap-1 text-xs font-semibold text-blue-800">
                  <UserPlus className="h-3.5 w-3.5" /> Extras (batida sem turno previsto hoje)
                </p>
                <div className="space-y-1">
                  {(posto.extras || []).map((ex) => (
                    <div key={ex.employee_id} className="flex flex-wrap items-center gap-2 text-sm">
                      <Badge className="bg-blue-100 text-blue-800">Extra</Badge>
                      <span className="font-medium">{ex.nome}</span>
                      {ex.presenca_em && (
                        <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                          às {formatarHora(ex.presenca_em)} <FonteIcone fonte={ex.fonte} />
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      ))}

      {/* Sem posto */}
      {semPosto.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-base">Sem posto vinculado</CardTitle>
            <p className="text-xs text-muted-foreground">
              Batidas ou turnos de hoje que não puderam ser ligados a um posto.
            </p>
          </CardHeader>
          <CardContent className="space-y-2">
            {semPosto.map((f) => (
              <LinhaFuncionario key={`${f.employee_id}-${f.shift_id || 'sp'}`} f={f} onMarcar={setAlvo} />
            ))}
          </CardContent>
        </Card>
      )}

      {/* Dialog check-in manual */}
      <Dialog open={!!alvo} onOpenChange={(aberto) => !aberto && setAlvo(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Marcar presença manual</DialogTitle>
            <DialogDescription>
              {alvo ? `${alvo.nome} — a presença ficará registrada como marcação manual, com seu usuário.` : ''}
            </DialogDescription>
          </DialogHeader>
          <div>
            <label className="mb-1 block text-sm font-medium">Observação (opcional)</label>
            <Textarea
              value={observacao}
              onChange={(e) => setObservacao(e.target.value)}
              placeholder="Ex.: chegou no posto, relógio de ponto sem sinal"
              rows={2}
            />
          </div>
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setAlvo(null)} disabled={enviando}>
              Cancelar
            </Button>
            <Button onClick={marcarPresente} isLoading={enviando}>
              Confirmar presença
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
