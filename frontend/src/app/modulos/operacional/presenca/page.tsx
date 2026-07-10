'use client';

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  ArrowRightLeft,
  Fingerprint,
  Hand,
  Loader2,
  MapPin,
  MapPinOff,
  Plus,
  RefreshCw,
  ScanFace,
  UserCheck,
  UserPlus,
  UserX,
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
  setor?: string | null;
  shift_id?: string | null;
  turno_inicio?: string | null;
  turno_fim?: string | null;
  status: StatusPresenca;
  presenca_em?: string | null;
  fonte?: 'ponto' | 'manual' | null;
  facial_match?: boolean | null;
  dentro_geofence?: boolean | null;
  falta_registrada?: boolean;
  substituicao?: 'pending' | 'confirmed' | null;
}

interface ExtraPresenca {
  employee_id: string;
  nome: string;
  setor?: string | null;
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
  saidas_noturno_ontem?: number;
}

interface PresencaHoje {
  data?: string;
  atualizado_em?: string;
  batidas_sincronizadas_ate?: string | null;
  resumo?: ResumoPresenca;
  postos?: PostoPresenca[];
  sem_posto?: FuncionarioPresenca[];
}

// ── Tipos (contrato falta → substituto) ─────────────────────────────────────
type MotivoFalta = 'falta' | 'atestado' | 'emergencia' | 'pessoal' | 'outro';

const MOTIVOS_FALTA: { valor: MotivoFalta; rotulo: string }[] = [
  { valor: 'falta', rotulo: 'Falta sem aviso' },
  { valor: 'atestado', rotulo: 'Atestado' },
  { valor: 'emergencia', rotulo: 'Emergência' },
  { valor: 'pessoal', rotulo: 'Pessoal' },
  { valor: 'outro', rotulo: 'Outro' },
];

interface SubstitutoFuncionario {
  employee_id: string;
  nome: string;
  cargo?: string | null;
  posto_atual?: string | null;
  mesmo_posto?: boolean;
  disponibilidade?: string | null;
}

interface SubstitutoDiarista {
  diarista_id: number;
  nome: string;
  cpf?: string | null;
  pix_ok?: boolean;
  funcoes?: string[];
  tem_funcao_sugerida?: boolean;
}

interface PrecoDiaria {
  funcao: string;
  turno: string;
  valor: number;
}

interface DiariaSugestao {
  funcao_sugerida?: string | null;
  turno_sugerido?: string | null;
  valor_sugerido?: number | null;
  funcoes_disponiveis?: string[];
  precos?: PrecoDiaria[];
}

interface SugestoesSubstituto {
  substitution_id: string;
  status?: string;
  posto?: string;
  data?: string;
  faltoso?: { nome?: string; cargo?: string };
  turno?: { inicio?: string; fim?: string };
  funcionarios?: SubstitutoFuncionario[];
  diaristas?: SubstitutoDiarista[];
  diaria?: DiariaSugestao;
}

// detail axios: string OU objeto { mensagem, conflitos }
function detalheErro(err: unknown, fallback: string): string {
  const e = err as { response?: { data?: { detail?: unknown } } };
  const d = e.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (d && typeof d === 'object') {
    const mensagem = (d as { mensagem?: unknown }).mensagem;
    if (typeof mensagem === 'string') return mensagem;
  }
  return fallback;
}

const brl = (v: number | null | undefined) =>
  v === null || v === undefined || Number.isNaN(Number(v))
    ? '—'
    : Number(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

// máscara ###.###.###-##
const cpfMask = (v: string) =>
  v
    .replace(/\D/g, '')
    .slice(0, 11)
    .replace(/(\d{3})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d)/, '$1.$2')
    .replace(/(\d{3})(\d{1,2})$/, '$1-$2');

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

// Chip de setor (allocations.setor) — cores por setor conhecido
const SETOR_CHIP: Record<string, string> = {
  RONDISTA: 'bg-amber-200 text-amber-900',
  PORTARIA: 'bg-blue-100 text-blue-800',
  'SERVICOS GERAIS': 'bg-gray-100 text-gray-700',
  INSALUBRIDADE: 'bg-purple-100 text-purple-800',
};

function ChipSetor({ setor }: { setor?: string | null }) {
  if (!setor) return null;
  const classe = SETOR_CHIP[setor.toUpperCase()] || 'bg-gray-100 text-gray-700';
  return (
    <span className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-semibold uppercase ${classe}`}>
      {setor}
    </span>
  );
}

function formatarHora(raw?: string | null): string {
  if (!raw) return '';
  // Aceita ISO datetime ou "HH:MM[:SS]"
  const d = new Date(raw);
  if (!Number.isNaN(d.getTime()) && raw.includes('T')) {
    return d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
  }
  const m = String(raw).match(/^(\d{1,2}):(\d{2})/);
  if (m) return `${(m[1] || '').padStart(2, '0')}:${m[2] || ''}`;
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
  onRegistrarFalta,
  onEscalarSubstituto,
  abrindoSub,
}: {
  f: FuncionarioPresenca;
  onMarcar: (f: FuncionarioPresenca) => void;
  onRegistrarFalta: (f: FuncionarioPresenca) => void;
  onEscalarSubstituto: (f: FuncionarioPresenca) => void;
  abrindoSub?: boolean;
}) {
  const podeMarcar =
    !!f.shift_id && (f.status === 'atrasado' || f.status === 'aguardando' || f.status === 'ausente');
  const podeRegistrarFalta =
    !!f.shift_id &&
    (f.status === 'atrasado' || f.status === 'aguardando' || f.status === 'ausente') &&
    !f.presenca_em &&
    !f.falta_registrada;
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-[hsl(var(--border))] p-2.5">
      <div className="flex flex-wrap items-center gap-2">
        <Badge className={STATUS_BADGE[f.status] || 'bg-gray-100 text-gray-700'}>
          {STATUS_LABEL[f.status] || f.status}
        </Badge>
        <span className="min-w-0 truncate text-sm font-medium">{f.nome}</span>
        {f.cargo && <span className="text-xs text-muted-foreground">{f.cargo}</span>}
        <ChipSetor setor={f.setor} />
        {f.falta_registrada && (
          <span className="inline-flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-800">
            <UserX className="h-3 w-3" /> Falta registrada
          </span>
        )}
        {f.substituicao === 'confirmed' && (
          <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-semibold text-green-800">
            <ArrowRightLeft className="h-3 w-3" /> Substituto escalado
          </span>
        )}
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
      {(podeMarcar || podeRegistrarFalta || f.substituicao === 'pending') && (
        <div className="flex flex-wrap gap-2">
          {podeMarcar && (
            <Button size="sm" variant="outline" onClick={() => onMarcar(f)}>
              <Hand className="mr-1 h-4 w-4" /> Marcar presente (manual)
            </Button>
          )}
          {podeRegistrarFalta && (
            <Button
              size="sm"
              variant="outline"
              className="border-red-300 text-red-700 hover:bg-red-50"
              onClick={() => onRegistrarFalta(f)}
            >
              <UserX className="mr-1 h-4 w-4" /> Registrar falta
            </Button>
          )}
          {f.substituicao === 'pending' && !!f.shift_id && (
            <Button
              size="sm"
              className="bg-amber-500 text-white hover:bg-amber-600"
              onClick={() => onEscalarSubstituto(f)}
              disabled={abrindoSub}
            >
              {abrindoSub ? (
                <Loader2 className="mr-1 h-4 w-4 animate-spin" />
              ) : (
                <ArrowRightLeft className="mr-1 h-4 w-4" />
              )}{' '}
              Escalar substituto
            </Button>
          )}
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

  // Falta → substituto (Dialog 1: registrar falta)
  const [faltaAlvo, setFaltaAlvo] = useState<FuncionarioPresenca | null>(null);
  const [motivoFalta, setMotivoFalta] = useState<MotivoFalta>('falta');
  const [detalhesFalta, setDetalhesFalta] = useState('');
  const [enviandoFalta, setEnviandoFalta] = useState(false);
  // abrindoSubDe: shift em que estamos reobtendo a substituição aberta (POST idempotente)
  const [abrindoSubDe, setAbrindoSubDe] = useState<string | null>(null);

  // Falta → substituto (Dialog 2: escolher substituto)
  const [subId, setSubId] = useState<string | null>(null);
  const [sugestoes, setSugestoes] = useState<SugestoesSubstituto | null>(null);
  const [carregandoSugestoes, setCarregandoSugestoes] = useState(false);
  const [abaSub, setAbaSub] = useState<'funcionarios' | 'diaristas'>('funcionarios');
  const [funcaoSel, setFuncaoSel] = useState('');
  const [escalandoFuncId, setEscalandoFuncId] = useState<string | null>(null);
  const [escalandoDiaristaId, setEscalandoDiaristaId] = useState<number | null>(null);

  // Cadastro rápido de diarista (inline, na aba Diaristas)
  const cadDiaristaVazio = { nome: '', cpf: '', pix: '', telefone: '' };
  const [cadDiaristaAberto, setCadDiaristaAberto] = useState(false);
  const [cadDiarista, setCadDiarista] = useState(cadDiaristaVazio);
  const [salvandoDiarista, setSalvandoDiarista] = useState(false);
  const [novoDiaristaId, setNovoDiaristaId] = useState<number | null>(null);

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

  // ── Falta → substituto ─────────────────────────────────────────────────────
  const carregarSugestoes = useCallback(async (substitutionId: string) => {
    setCarregandoSugestoes(true);
    try {
      const res = await api.get(`/api/v1/operacional/presenca/substitutos/${substitutionId}`);
      const dadosSub: SugestoesSubstituto = res.data || {};
      setSugestoes(dadosSub);
      setFuncaoSel(
        dadosSub.diaria?.funcao_sugerida || dadosSub.diaria?.funcoes_disponiveis?.[0] || ''
      );
    } catch (err: unknown) {
      toast.error(detalheErro(err, 'Erro ao buscar sugestões de substituto.'));
    } finally {
      setCarregandoSugestoes(false);
    }
  }, []);

  const abrirSubstitutos = useCallback(
    (substitutionId: string) => {
      setSubId(substitutionId);
      setSugestoes(null);
      setAbaSub('funcionarios');
      setCadDiaristaAberto(false);
      setCadDiarista(cadDiaristaVazio);
      setNovoDiaristaId(null);
      carregarSugestoes(substitutionId);
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [carregarSugestoes]
  );

  const abrirRegistrarFalta = (f: FuncionarioPresenca) => {
    setFaltaAlvo(f);
    setMotivoFalta('falta');
    setDetalhesFalta('');
  };

  const registrarFalta = async () => {
    if (!faltaAlvo?.shift_id) return;
    setEnviandoFalta(true);
    try {
      const payload: Record<string, unknown> = { motivo: motivoFalta };
      if (detalhesFalta.trim()) payload.detalhes = detalhesFalta.trim();
      const res = await api.post(
        `/api/v1/operacional/presenca/falta/${faltaAlvo.shift_id}`,
        payload
      );
      const substitutionId: string | undefined = res.data?.substitution_id;
      toast.success(
        res.data?.ja_existia
          ? `Falta de ${faltaAlvo.nome} já estava registrada — abrindo a busca de substituto.`
          : `Falta de ${faltaAlvo.nome} registrada.`
      );
      setFaltaAlvo(null);
      carregar(true);
      if (substitutionId) abrirSubstitutos(substitutionId);
    } catch (err: unknown) {
      const e = err as { response?: { status?: number } };
      if (e.response?.status === 409) {
        toast.error('Este funcionário já tem presença registrada hoje — não é possível registrar falta.');
        carregar(true);
      } else if (e.response?.status === 403) {
        toast.error('Você não tem permissão para registrar falta neste posto.');
      } else {
        toast.error(detalheErro(err, 'Erro ao registrar a falta.'));
      }
    } finally {
      setEnviandoFalta(false);
    }
  };

  // "Escalar substituto" numa falta já registrada: o POST de falta é IDEMPOTENTE —
  // repetir com motivo 'falta' devolve a substituição aberta (substitution_id).
  const escalarSubstitutoPendente = async (f: FuncionarioPresenca) => {
    if (!f.shift_id) return;
    setAbrindoSubDe(f.shift_id);
    try {
      const res = await api.post(`/api/v1/operacional/presenca/falta/${f.shift_id}`, {
        motivo: 'falta',
      });
      const substitutionId: string | undefined = res.data?.substitution_id;
      if (substitutionId) {
        abrirSubstitutos(substitutionId);
      } else {
        toast.error('Não foi possível localizar a substituição aberta.');
      }
    } catch (err: unknown) {
      toast.error(detalheErro(err, 'Erro ao abrir a busca de substituto.'));
    } finally {
      setAbrindoSubDe(null);
    }
  };

  const fecharSubstitutos = () => {
    setSubId(null);
    setSugestoes(null);
    setCadDiaristaAberto(false);
    setCadDiarista(cadDiaristaVazio);
    setNovoDiaristaId(null);
  };

  const escalarFuncionario = async (s: SubstitutoFuncionario) => {
    if (!subId) return;
    setEscalandoFuncId(s.employee_id);
    try {
      const res = await api.post(`/api/v1/operacional/presenca/substituir/${subId}`, {
        tipo: 'funcionario',
        employee_id: s.employee_id,
      });
      const nomeSub = res.data?.substituto || s.nome;
      const nomeFaltoso = sugestoes?.faltoso?.nome || 'o faltoso';
      toast.success(`${nomeSub} escalado no lugar de ${nomeFaltoso}`);
      fecharSubstitutos();
      carregar(true);
    } catch (err: unknown) {
      toast.error(detalheErro(err, 'Erro ao escalar o substituto.'));
    } finally {
      setEscalandoFuncId(null);
    }
  };

  // Reprecificação client-side pela tabela: função ≠ AGENTE DE PORTARIA usa turno ÚNICO
  const turnoParaFuncao = (funcao: string): string =>
    funcao !== 'AGENTE DE PORTARIA' ? 'ÚNICO' : sugestoes?.diaria?.turno_sugerido || 'DIURNO';

  const valorFuncaoSel = useMemo(() => {
    const d = sugestoes?.diaria;
    if (!d || !funcaoSel) return null;
    const t = funcaoSel !== 'AGENTE DE PORTARIA' ? 'ÚNICO' : d.turno_sugerido || 'DIURNO';
    const p = (d.precos || []).find((x) => x.funcao === funcaoSel && x.turno === t);
    return p ? p.valor : null;
  }, [sugestoes, funcaoSel]);

  const escalarDiarista = async (d: SubstitutoDiarista) => {
    if (!subId) return;
    setEscalandoDiaristaId(d.diarista_id);
    try {
      const body: Record<string, unknown> = { tipo: 'diarista', diarista_id: d.diarista_id };
      if (funcaoSel) {
        body.funcao = funcaoSel;
        body.turno = turnoParaFuncao(funcaoSel);
      }
      const res = await api.post(`/api/v1/operacional/presenca/substituir/${subId}`, body);
      toast.success(`Diária de ${brl(res.data?.valor_diaria)} lançada — pagamento dia 15`);
      fecharSubstitutos();
      carregar(true);
    } catch (err: unknown) {
      toast.error(detalheErro(err, 'Erro ao escalar o diarista.'));
    } finally {
      setEscalandoDiaristaId(null);
    }
  };

  const cadastrarDiarista = async () => {
    const cpfDig = cadDiarista.cpf.replace(/\D/g, '');
    if (!cadDiarista.nome.trim() || !cpfDig || !cadDiarista.pix.trim()) {
      toast.error('Nome, CPF e chave PIX são obrigatórios.');
      return;
    }
    setSalvandoDiarista(true);
    try {
      const body: Record<string, unknown> = {
        nome: cadDiarista.nome.trim(),
        cpf: cpfDig,
        pix: cadDiarista.pix.trim(),
      };
      if (cadDiarista.telefone.trim()) body.telefone = cadDiarista.telefone.trim();
      const res = await api.post('/api/v1/operacional/diarias/diaristas', body);
      if (res.data?.ok === false) {
        toast.error(res.data?.mensagem || 'Não foi possível cadastrar o diarista.');
        return;
      }
      toast.success(`Diarista ${cadDiarista.nome.trim()} cadastrado.`);
      setNovoDiaristaId(typeof res.data?.id === 'number' ? res.data.id : null);
      setCadDiarista(cadDiaristaVazio);
      setCadDiaristaAberto(false);
      if (subId) carregarSugestoes(subId);
    } catch (err: unknown) {
      toast.error(detalheErro(err, 'Erro ao cadastrar o diarista.'));
    } finally {
      setSalvandoDiarista(false);
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
        <div className="space-y-1">
          <div className="flex flex-wrap gap-2">
            <ChipResumo rotulo="esperados" valor={resumo.esperados ?? 0} classe="bg-slate-100 text-slate-800" />
            <ChipResumo rotulo="presentes" valor={resumo.presentes ?? 0} classe="bg-green-100 text-green-800" />
            <ChipResumo rotulo="atrasados" valor={resumo.atrasados ?? 0} classe="bg-amber-100 text-amber-800" />
            <ChipResumo rotulo="ausentes" valor={resumo.ausentes ?? 0} classe="bg-red-100 text-red-800" />
            <ChipResumo rotulo="aguardando" valor={resumo.aguardando ?? 0} classe="bg-gray-100 text-gray-700" />
            <ChipResumo rotulo="extras" valor={totalExtras} classe="bg-blue-100 text-blue-800" />
          </div>
          {(resumo.saidas_noturno_ontem ?? 0) > 0 && (
            <p className="text-xs text-muted-foreground">
              {resumo.saidas_noturno_ontem}{' '}
              {resumo.saidas_noturno_ontem === 1
                ? 'batida da madrugada atribuída'
                : 'batidas da madrugada atribuídas'}{' '}
              ao turno noturno de ontem (saída, não presença de hoje).
            </p>
          )}
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
                <LinhaFuncionario
                  key={`${f.employee_id}-${f.shift_id || ''}`}
                  f={f}
                  onMarcar={setAlvo}
                  onRegistrarFalta={abrirRegistrarFalta}
                  onEscalarSubstituto={escalarSubstitutoPendente}
                  abrindoSub={!!f.shift_id && abrindoSubDe === f.shift_id}
                />
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
                      <ChipSetor setor={ex.setor} />
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
              <LinhaFuncionario
                key={`${f.employee_id}-${f.shift_id || 'sp'}`}
                f={f}
                onMarcar={setAlvo}
                onRegistrarFalta={abrirRegistrarFalta}
                onEscalarSubstituto={escalarSubstitutoPendente}
                abrindoSub={!!f.shift_id && abrindoSubDe === f.shift_id}
              />
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

      {/* Dialog 1 — Registrar falta */}
      <Dialog open={!!faltaAlvo} onOpenChange={(aberto) => !aberto && setFaltaAlvo(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <UserX className="h-5 w-5 text-red-600" /> Registrar falta
            </DialogTitle>
            <DialogDescription>
              {faltaAlvo
                ? `${faltaAlvo.nome}${faltaAlvo.cargo ? ` — ${faltaAlvo.cargo}` : ''}`
                : ''}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="mb-1 block text-sm font-medium">Motivo</label>
              <div className="space-y-1.5">
                {MOTIVOS_FALTA.map((m) => (
                  <label
                    key={m.valor}
                    className={`flex cursor-pointer items-center gap-2 rounded-lg border p-2 text-sm ${
                      motivoFalta === m.valor
                        ? 'border-red-400 bg-red-50 text-red-900'
                        : 'border-[hsl(var(--border))]'
                    }`}
                  >
                    <input
                      type="radio"
                      name="motivo-falta"
                      className="accent-red-600"
                      checked={motivoFalta === m.valor}
                      onChange={() => setMotivoFalta(m.valor)}
                    />
                    {m.rotulo}
                  </label>
                ))}
              </div>
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium">Detalhes (opcional)</label>
              <Textarea
                value={detalhesFalta}
                onChange={(e) => setDetalhesFalta(e.target.value)}
                placeholder="Ex.: avisou por telefone às 06:40"
                rows={2}
              />
            </div>
            <p className="rounded bg-amber-50 px-2 py-1.5 text-xs text-amber-800">
              O turno vira falta e abre a busca de substituto. Ninguém é pago/punido
              automaticamente.
            </p>
          </div>
          <DialogFooter className="gap-2">
            <Button variant="ghost" onClick={() => setFaltaAlvo(null)} disabled={enviandoFalta}>
              Cancelar
            </Button>
            <Button
              className="bg-red-600 text-white hover:bg-red-700"
              onClick={registrarFalta}
              isLoading={enviandoFalta}
            >
              Registrar falta
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog 2 — Substituto do dia */}
      <Dialog open={!!subId} onOpenChange={(aberto) => !aberto && fecharSubstitutos()}>
        <DialogContent className="max-h-[90vh] max-w-lg overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ArrowRightLeft className="h-5 w-5 text-amber-600" /> Substituto do dia
            </DialogTitle>
            <DialogDescription>
              {sugestoes
                ? [
                    sugestoes.faltoso?.nome &&
                      `No lugar de ${sugestoes.faltoso.nome}${sugestoes.faltoso?.cargo ? ` (${sugestoes.faltoso.cargo})` : ''}`,
                    sugestoes.posto,
                    sugestoes.turno?.inicio &&
                      `${formatarHora(sugestoes.turno.inicio)}–${formatarHora(sugestoes.turno.fim)}`,
                  ]
                    .filter(Boolean)
                    .join(' · ')
                : 'Carregando dados da substituição…'}
            </DialogDescription>
          </DialogHeader>

          {/* Abas */}
          <div className="flex gap-2">
            <button
              onClick={() => setAbaSub('funcionarios')}
              className={`rounded px-3 py-1.5 text-sm ${
                abaSub === 'funcionarios' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'
              }`}
            >
              Colaboradores de folga
            </button>
            <button
              onClick={() => setAbaSub('diaristas')}
              className={`rounded px-3 py-1.5 text-sm ${
                abaSub === 'diaristas' ? 'bg-blue-600 text-white' : 'bg-gray-100 text-gray-700'
              }`}
            >
              Diaristas
            </button>
          </div>

          {carregandoSugestoes && (
            <div className="flex items-center justify-center gap-2 py-6 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Buscando sugestões…
            </div>
          )}

          {/* Aba: colaboradores de folga */}
          {!carregandoSugestoes && sugestoes && abaSub === 'funcionarios' && (
            <div className="space-y-2">
              {(sugestoes.funcionarios || []).length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  Ninguém do mesmo cargo está de folga hoje.
                </p>
              ) : (
                (sugestoes.funcionarios || []).map((s) => (
                  <div
                    key={s.employee_id}
                    className="flex flex-wrap items-center gap-2 rounded-lg border border-[hsl(var(--border))] p-2.5"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="truncate text-sm font-medium">{s.nome}</span>
                        {s.mesmo_posto && (
                          <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-800">
                            mesmo posto
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-muted-foreground">
                        {[s.cargo, s.posto_atual, s.disponibilidade].filter(Boolean).join(' · ')}
                      </p>
                    </div>
                    <Button
                      size="sm"
                      onClick={() => escalarFuncionario(s)}
                      isLoading={escalandoFuncId === s.employee_id}
                      disabled={escalandoFuncId !== null}
                    >
                      Escalar
                    </Button>
                  </div>
                ))
              )}
            </div>
          )}

          {/* Aba: diaristas */}
          {!carregandoSugestoes && sugestoes && abaSub === 'diaristas' && (
            <div className="space-y-3">
              {/* Banner da diária automática */}
              <div className="rounded-lg border border-blue-200 bg-blue-50 p-2.5 text-sm text-blue-900">
                <p className="text-xs font-semibold uppercase text-blue-700">
                  Diária automática pela tabela
                </p>
                <p>
                  {[
                    sugestoes.diaria?.funcao_sugerida,
                    sugestoes.diaria?.turno_sugerido,
                    sugestoes.diaria?.valor_sugerido != null
                      ? brl(sugestoes.diaria.valor_sugerido)
                      : null,
                  ]
                    .filter(Boolean)
                    .join(' · ') || 'Sem preço sugerido para este turno.'}
                </p>
              </div>

              {/* Select de função — reprecifica client-side pela tabela */}
              {(sugestoes.diaria?.funcoes_disponiveis || []).length > 0 && (
                <div className="flex flex-wrap items-end gap-2">
                  <div className="flex-1">
                    <label className="mb-1 block text-xs text-muted-foreground">Função</label>
                    <select
                      value={funcaoSel}
                      onChange={(e) => setFuncaoSel(e.target.value)}
                      className="w-full rounded border bg-white px-2 py-1.5 text-sm"
                    >
                      {(sugestoes.diaria?.funcoes_disponiveis || []).map((f) => (
                        <option key={f} value={f}>
                          {f}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div className="pb-1 text-right">
                    <p className="text-xs text-muted-foreground">Valor</p>
                    <p className="text-base font-bold text-blue-700">{brl(valorFuncaoSel)}</p>
                  </div>
                </div>
              )}

              {/* Lista de diaristas */}
              {(sugestoes.diaristas || []).length === 0 ? (
                <p className="py-3 text-center text-sm text-muted-foreground">
                  Nenhum diarista cadastrado disponível.
                </p>
              ) : (
                (sugestoes.diaristas || []).map((d) => (
                  <div
                    key={d.diarista_id}
                    className={`flex flex-wrap items-center gap-2 rounded-lg border p-2.5 ${
                      novoDiaristaId === d.diarista_id
                        ? 'border-green-400 bg-green-50'
                        : 'border-[hsl(var(--border))]'
                    }`}
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="truncate text-sm font-medium">{d.nome}</span>
                        {novoDiaristaId === d.diarista_id && (
                          <span className="inline-flex items-center rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-semibold text-green-800">
                            novo
                          </span>
                        )}
                        {d.tem_funcao_sugerida && (
                          <span className="inline-flex items-center rounded-full bg-blue-100 px-2 py-0.5 text-[10px] font-semibold text-blue-800">
                            já fez a função
                          </span>
                        )}
                        {d.pix_ok === false && (
                          <span className="inline-flex items-center rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-semibold text-red-800">
                            sem PIX
                          </span>
                        )}
                      </div>
                      {(d.funcoes || []).length > 0 && (
                        <p className="text-xs text-muted-foreground">{(d.funcoes || []).join(' · ')}</p>
                      )}
                    </div>
                    <Button
                      size="sm"
                      onClick={() => escalarDiarista(d)}
                      isLoading={escalandoDiaristaId === d.diarista_id}
                      disabled={escalandoDiaristaId !== null}
                    >
                      Escalar diarista
                    </Button>
                  </div>
                ))
              )}

              {/* Cadastro rápido de diarista */}
              {!cadDiaristaAberto ? (
                <button
                  onClick={() => setCadDiaristaAberto(true)}
                  className="flex items-center gap-1 text-sm font-medium text-blue-700"
                >
                  <Plus className="h-4 w-4" /> Cadastrar novo diarista
                </button>
              ) : (
                <div className="space-y-2 rounded-lg border border-[hsl(var(--border))] p-3">
                  <p className="text-sm font-medium">Novo diarista</p>
                  <input
                    value={cadDiarista.nome}
                    onChange={(e) => setCadDiarista((f) => ({ ...f, nome: e.target.value }))}
                    placeholder="Nome completo *"
                    className="w-full rounded border px-3 py-2 text-sm"
                  />
                  <input
                    value={cadDiarista.cpf}
                    inputMode="numeric"
                    onChange={(e) => setCadDiarista((f) => ({ ...f, cpf: cpfMask(e.target.value) }))}
                    placeholder="CPF * — 000.000.000-00"
                    className="w-full rounded border px-3 py-2 text-sm"
                  />
                  <input
                    value={cadDiarista.pix}
                    onChange={(e) => setCadDiarista((f) => ({ ...f, pix: e.target.value }))}
                    placeholder="Chave PIX *"
                    className="w-full rounded border px-3 py-2 text-sm"
                  />
                  <input
                    value={cadDiarista.telefone}
                    inputMode="tel"
                    onChange={(e) => setCadDiarista((f) => ({ ...f, telefone: e.target.value }))}
                    placeholder="Telefone (opcional)"
                    className="w-full rounded border px-3 py-2 text-sm"
                  />
                  <div className="flex gap-2">
                    <Button
                      size="sm"
                      onClick={cadastrarDiarista}
                      isLoading={salvandoDiarista}
                      className="bg-blue-600 text-white hover:bg-blue-700"
                    >
                      <Plus className="mr-1 h-4 w-4" /> Cadastrar
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => {
                        setCadDiaristaAberto(false);
                        setCadDiarista(cadDiaristaVazio);
                      }}
                      disabled={salvandoDiarista}
                    >
                      Cancelar
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    CPF e chave PIX são obrigatórios para o Financeiro pagar a diária.
                  </p>
                </div>
              )}
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
