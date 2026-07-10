'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  CalendarCog,
  CalendarDays,
  Eye,
  Lock,
  Palmtree,
  Pencil,
  Plus,
  RefreshCw,
  Search,
  UserMinus,
  UserPlus,
  Users,
} from 'lucide-react';
import { toast } from 'sonner';
import { api } from '@/lib/api';
import { useAuth } from '@/hooks/useAuth';
import { PageHeader } from '@/components/ui/page-header';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Modal, ModalFooter } from '@/components/ui/modal';

// ── Tipos (contratos /operacional/grade/*) ──────────────────────────────────
interface GradePostoResumo {
  post_id: string;
  post_nome: string;
  pessoas_na_grade: number;
}

interface GradePostosResponse {
  mes: number;
  ano: number;
  somente_leitura: boolean;
  postos: GradePostoResumo[];
}

interface FeriasPeriodo {
  inicio: string;
  fim: string;
}

interface GradePessoa {
  employee_id: string;
  nome: string;
  cargo?: string | null;
  padrao: '12x36' | 'comercial';
  turno: 'diurno' | 'noturno';
  inicio: string;
  fim: string;
  paridade: 'pares' | 'impares' | null;
  turnos_no_mes: number;
  dias: number[];
  ferias: FeriasPeriodo[];
}

interface SemGradePessoa {
  employee_id: string;
  nome: string;
  cargo?: string | null;
}

interface GradePostoDetalhe {
  post_id: string;
  post_nome: string;
  mes: number;
  ano: number;
  somente_leitura: boolean;
  pessoas: GradePessoa[];
  sem_grade: SemGradePessoa[];
}

interface EmployeeItem {
  id: string;
  nome: string;
  cargo?: string | null;
}

interface GradeSaveResponse {
  ok: boolean;
  colaborador?: { nome?: string };
  turnos_cancelados?: number;
  turnos_criados?: number;
  dias_pulados_por_ferias?: number;
  meses_afetados?: string[];
  alocacao_criada?: boolean;
}

interface ConflitoGrade {
  dia?: string | number;
  posto?: string;
}

type ApiErr = {
  response?: {
    status?: number;
    data?: { detail?: string | { mensagem?: string; conflitos?: ConflitoGrade[] } };
  };
};

// ── Datas (fuso Manaus UTC-4: nunca new Date('YYYY-MM-DD') direto) ──────────
function parseShiftDate(value: string): Date {
  return /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : new Date(value);
}

function toLocalYMD(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function formatarDiaMes(value?: string | number): string {
  if (value === undefined || value === null) return '';
  if (typeof value === 'number') return String(value);
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) {
    const d = parseShiftDate(value);
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' });
  }
  return String(value);
}

const MESES_PT = [
  'Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho',
  'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro',
];

// ── Formulário de grade (compartilhado por editar/escalar/adicionar) ────────
interface GradeForm {
  padrao: '12x36' | 'comercial';
  turno: 'diurno' | 'noturno';
  paridade: 'pares' | 'impares';
  inicio: string;
  aPartirDe: string;
}

function formPadrao(amanha: string): GradeForm {
  return { padrao: '12x36', turno: 'diurno', paridade: 'pares', inicio: '', aPartirDe: amanha };
}

function placeholderInicio(form: GradeForm): string {
  if (form.padrao === 'comercial') return '08:00';
  return form.turno === 'noturno' ? '19:00' : '07:00';
}

function chipPadrao(p: GradePessoa): string {
  if (p.padrao === 'comercial') return `Comercial 44h · ${p.inicio}`;
  const turno = p.turno === 'noturno' ? 'Noturno' : 'Diurno';
  const paridade = p.paridade === 'impares' ? 'Dias ímpares' : p.paridade === 'pares' ? 'Dias pares' : '';
  return `12x36 · ${turno}${paridade ? ` · ${paridade}` : ''} · ${p.inicio}–${p.fim}`;
}

// ── Campos do formulário (reutilizados nos modais) ──────────────────────────
function CamposGrade({
  form,
  setForm,
  minData,
}: {
  form: GradeForm;
  setForm: (f: GradeForm) => void;
  minData: string;
}) {
  const radioClasse = (ativo: boolean) =>
    `flex items-center gap-2 rounded-lg border px-3 py-2 text-sm cursor-pointer transition-colors ${
      ativo
        ? 'border-[hsl(var(--primary))] bg-[hsl(var(--primary))]/10 text-[hsl(var(--foreground))]'
        : 'border-[hsl(var(--border))] text-[hsl(var(--muted-foreground))] hover:border-[hsl(var(--primary))]/50'
    }`;

  return (
    <div className="space-y-4">
      <div>
        <p className="mb-1.5 block text-sm font-medium text-[hsl(var(--muted-foreground))]">Padrão de escala</p>
        <div className="grid grid-cols-2 gap-2">
          <label className={radioClasse(form.padrao === '12x36')}>
            <input
              type="radio"
              name="padrao"
              className="accent-[hsl(var(--primary))]"
              checked={form.padrao === '12x36'}
              onChange={() => setForm({ ...form, padrao: '12x36' })}
            />
            12x36
          </label>
          <label className={radioClasse(form.padrao === 'comercial')}>
            <input
              type="radio"
              name="padrao"
              className="accent-[hsl(var(--primary))]"
              checked={form.padrao === 'comercial'}
              onChange={() => setForm({ ...form, padrao: 'comercial' })}
            />
            Comercial 44h
          </label>
        </div>
      </div>

      {form.padrao === '12x36' && (
        <>
          <div>
            <p className="mb-1.5 block text-sm font-medium text-[hsl(var(--muted-foreground))]">Turno</p>
            <div className="grid grid-cols-2 gap-2">
              <label className={radioClasse(form.turno === 'diurno')}>
                <input
                  type="radio"
                  name="turno"
                  className="accent-[hsl(var(--primary))]"
                  checked={form.turno === 'diurno'}
                  onChange={() => setForm({ ...form, turno: 'diurno' })}
                />
                Diurno 07:00–19:00
              </label>
              <label className={radioClasse(form.turno === 'noturno')}>
                <input
                  type="radio"
                  name="turno"
                  className="accent-[hsl(var(--primary))]"
                  checked={form.turno === 'noturno'}
                  onChange={() => setForm({ ...form, turno: 'noturno' })}
                />
                Noturno 19:00–07:00
              </label>
            </div>
          </div>
          <div>
            <p className="mb-1.5 block text-sm font-medium text-[hsl(var(--muted-foreground))]">Alternância</p>
            <div className="grid grid-cols-2 gap-2">
              <label className={radioClasse(form.paridade === 'pares')}>
                <input
                  type="radio"
                  name="paridade"
                  className="accent-[hsl(var(--primary))]"
                  checked={form.paridade === 'pares'}
                  onChange={() => setForm({ ...form, paridade: 'pares' })}
                />
                Dias pares
              </label>
              <label className={radioClasse(form.paridade === 'impares')}>
                <input
                  type="radio"
                  name="paridade"
                  className="accent-[hsl(var(--primary))]"
                  checked={form.paridade === 'impares'}
                  onChange={() => setForm({ ...form, paridade: 'impares' })}
                />
                Dias ímpares
              </label>
            </div>
          </div>
        </>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Input
          label="Hora de início (opcional)"
          placeholder={placeholderInicio(form)}
          value={form.inicio}
          onChange={(e) => setForm({ ...form, inicio: e.target.value })}
          inputMode="numeric"
        />
        <Input
          label="A partir de"
          type="date"
          min={minData}
          value={form.aPartirDe}
          onChange={(e) => setForm({ ...form, aPartirDe: e.target.value })}
        />
      </div>

      <p className="rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--muted))]/40 px-3 py-2 text-xs text-[hsl(var(--muted-foreground))]">
        Os turnos futuros desta pessoa neste posto serão redesenhados; presença já registrada nunca é
        tocada; férias aprovadas são respeitadas.
      </p>
    </div>
  );
}

// ── Mini-strip dos dias do mês ──────────────────────────────────────────────
function StripDias({ dias, mes, ano }: { dias: number[]; mes: number; ano: number }) {
  const totalDias = new Date(ano, mes, 0).getDate();
  const marcados = useMemo(() => new Set(dias), [dias]);
  return (
    <div className="flex flex-wrap gap-1">
      {Array.from({ length: totalDias }, (_, i) => i + 1).map((d) => (
        <span
          key={d}
          className={`inline-flex h-6 w-6 items-center justify-center rounded text-[10px] font-medium font-data tabular-nums ${
            marcados.has(d)
              ? 'bg-[hsl(var(--primary))]/15 text-[hsl(var(--primary))] border border-[hsl(var(--primary))]/40'
              : 'bg-[hsl(var(--muted))]/50 text-[hsl(var(--muted-foreground))]/60'
          }`}
        >
          {d}
        </span>
      ))}
    </div>
  );
}

// ── Página ──────────────────────────────────────────────────────────────────
export default function GradePorPessoaPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  // Datas divergem entre SSR e client (React #418) — renderizar só após mount
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  const hoje = useMemo(() => toLocalYMD(new Date()), []);
  const amanha = useMemo(() => {
    const d = new Date();
    d.setDate(d.getDate() + 1);
    return toLocalYMD(d);
  }, []);

  // Mês atual + mês seguinte
  const opcoesMes = useMemo(() => {
    const agora = new Date();
    const atual = { mes: agora.getMonth() + 1, ano: agora.getFullYear() };
    const prox = new Date(agora.getFullYear(), agora.getMonth() + 1, 1);
    const seguinte = { mes: prox.getMonth() + 1, ano: prox.getFullYear() };
    return [atual, seguinte].map((o) => ({
      ...o,
      valor: `${o.mes}-${o.ano}`,
      rotulo: `${MESES_PT[o.mes - 1]} ${o.ano}`,
    }));
  }, []);

  const [mesAno, setMesAno] = useState<string>('');
  useEffect(() => {
    const primeiro = opcoesMes[0];
    if (!mesAno && primeiro) setMesAno(primeiro.valor);
  }, [mesAno, opcoesMes]);
  const [mes, ano] = useMemo(() => {
    const valor = mesAno || opcoesMes[0]?.valor || '';
    const [m = 0, a = 0] = valor.split('-').map(Number);
    return [m, a];
  }, [mesAno, opcoesMes]);

  // Postos
  const [postos, setPostos] = useState<GradePostoResumo[]>([]);
  const [postoSelecionado, setPostoSelecionado] = useState<string>('');
  const [somenteLeitura, setSomenteLeitura] = useState(false);
  const [carregandoPostos, setCarregandoPostos] = useState(true);

  // Grade do posto
  const [grade, setGrade] = useState<GradePostoDetalhe | null>(null);
  const [carregandoGrade, setCarregandoGrade] = useState(false);
  const [erroGrade, setErroGrade] = useState<string | null>(null);

  const carregarPostos = useCallback(async () => {
    setCarregandoPostos(true);
    try {
      const res = await api.get<GradePostosResponse>('/api/v1/operacional/grade/postos');
      const lista = res.data?.postos || [];
      setPostos(lista);
      setSomenteLeitura(!!res.data?.somente_leitura);
      setPostoSelecionado((atual) => atual || lista[0]?.post_id || '');
    } catch {
      toast.error('Não foi possível carregar os postos da grade.');
    } finally {
      setCarregandoPostos(false);
    }
  }, []);

  const carregarGrade = useCallback(async (silencioso = false) => {
    if (!postoSelecionado) return;
    if (!silencioso) setCarregandoGrade(true);
    try {
      const res = await api.get<GradePostoDetalhe>(
        `/api/v1/operacional/grade/${postoSelecionado}?mes=${mes}&ano=${ano}`
      );
      setGrade(res.data);
      setSomenteLeitura(!!res.data?.somente_leitura);
      setErroGrade(null);
    } catch (err: unknown) {
      const e = err as ApiErr;
      const detail = e.response?.data?.detail;
      setGrade(null);
      setErroGrade(typeof detail === 'string' ? detail : 'Não foi possível carregar a grade deste posto.');
    } finally {
      if (!silencioso) setCarregandoGrade(false);
    }
  }, [postoSelecionado, mes, ano]);

  useEffect(() => {
    if (mounted) carregarPostos();
  }, [mounted, carregarPostos]);

  useEffect(() => {
    if (mounted) carregarGrade();
  }, [mounted, carregarGrade]);

  // ── Modal editar/escalar (PUT) ────────────────────────────────────────────
  const [alvoEdicao, setAlvoEdicao] = useState<{ employee_id: string; nome: string; cargo?: string | null } | null>(null);
  const [formEdicao, setFormEdicao] = useState<GradeForm>(() => formPadrao(amanha));
  const [salvandoEdicao, setSalvandoEdicao] = useState(false);
  const [conflitosEdicao, setConflitosEdicao] = useState<ConflitoGrade[]>([]);
  const [erroEdicao, setErroEdicao] = useState<string | null>(null);

  const abrirEdicao = (pessoa: { employee_id: string; nome: string; cargo?: string | null } & Partial<GradePessoa>) => {
    setAlvoEdicao({ employee_id: pessoa.employee_id, nome: pessoa.nome, cargo: pessoa.cargo });
    setFormEdicao({
      padrao: pessoa.padrao || '12x36',
      turno: pessoa.turno || 'diurno',
      paridade: pessoa.paridade === 'impares' ? 'impares' : 'pares',
      inicio: '',
      aPartirDe: amanha,
    });
    setConflitosEdicao([]);
    setErroEdicao(null);
  };

  const montarBody = (employeeId: string, form: GradeForm) => ({
    employee_id: employeeId,
    a_partir_de: form.aPartirDe,
    padrao: form.padrao,
    turno: form.padrao === '12x36' ? form.turno : 'diurno',
    paridade: form.padrao === '12x36' ? form.paridade : null,
    inicio: form.inicio.trim() || null,
  });

  const validarForm = (form: GradeForm): string | null => {
    if (!form.aPartirDe) return 'Informe a data "A partir de".';
    if (form.inicio.trim() && !/^\d{1,2}:\d{2}$/.test(form.inicio.trim())) {
      return 'Hora de início inválida — use o formato HH:MM (ex.: 07:00).';
    }
    return null;
  };

  const tratarErroEscrita = (
    err: unknown,
    setConflitos: (c: ConflitoGrade[]) => void,
    setErro: (m: string | null) => void
  ) => {
    const e = err as ApiErr;
    const status = e.response?.status;
    const detail = e.response?.data?.detail;
    if (status === 403) {
      toast.error('Você é líder de posto: apenas visualização. A edição da grade é do gestor.');
      return;
    }
    if (status === 409 && detail && typeof detail === 'object') {
      setConflitos(detail.conflitos || []);
      setErro(detail.mensagem || 'Conflito de turnos ao redesenhar a grade.');
      return;
    }
    if (typeof detail === 'string') {
      setErro(detail);
      return;
    }
    setErro('Erro ao salvar a grade. Tente novamente.');
  };

  const toastSucessoGrade = (res: GradeSaveResponse, nomeFallback: string) => {
    const nome = res.colaborador?.nome || nomeFallback;
    const partes = [`${res.turnos_criados ?? 0} turnos criados`, `${res.turnos_cancelados ?? 0} cancelados`];
    if ((res.dias_pulados_por_ferias ?? 0) > 0) {
      partes.push(`${res.dias_pulados_por_ferias} dias pulados por férias`);
    }
    toast.success(`Grade de ${nome} atualizada: ${partes.join(', ')}.`);
  };

  const salvarEdicao = async () => {
    if (!alvoEdicao || !postoSelecionado) return;
    const erroValidacao = validarForm(formEdicao);
    if (erroValidacao) {
      setErroEdicao(erroValidacao);
      return;
    }
    setSalvandoEdicao(true);
    setConflitosEdicao([]);
    setErroEdicao(null);
    try {
      const res = await api.put<GradeSaveResponse>(
        `/api/v1/operacional/grade/${postoSelecionado}/colaborador`,
        montarBody(alvoEdicao.employee_id, formEdicao)
      );
      toastSucessoGrade(res.data, alvoEdicao.nome);
      setAlvoEdicao(null);
      carregarGrade(true);
      carregarPostos();
    } catch (err: unknown) {
      tratarErroEscrita(err, setConflitosEdicao, setErroEdicao);
    } finally {
      setSalvandoEdicao(false);
    }
  };

  // ── Modal adicionar colaborador (POST) ────────────────────────────────────
  const [modalAdicionar, setModalAdicionar] = useState(false);
  const [buscaColab, setBuscaColab] = useState('');
  const [employees, setEmployees] = useState<EmployeeItem[]>([]);
  const [carregandoEmployees, setCarregandoEmployees] = useState(false);
  const [colabSelecionado, setColabSelecionado] = useState<EmployeeItem | null>(null);
  const [formAdicionar, setFormAdicionar] = useState<GradeForm>(() => formPadrao(amanha));
  const [criarAlocacao, setCriarAlocacao] = useState(true);
  const [setorAlocacao, setSetorAlocacao] = useState('');
  const [salvandoAdicionar, setSalvandoAdicionar] = useState(false);
  const [conflitosAdicionar, setConflitosAdicionar] = useState<ConflitoGrade[]>([]);
  const [erroAdicionar, setErroAdicionar] = useState<string | null>(null);

  const abrirAdicionar = async () => {
    setModalAdicionar(true);
    setBuscaColab('');
    setColabSelecionado(null);
    setFormAdicionar(formPadrao(amanha));
    setCriarAlocacao(true);
    setSetorAlocacao('');
    setConflitosAdicionar([]);
    setErroAdicionar(null);
    if (employees.length === 0) {
      setCarregandoEmployees(true);
      try {
        const res = await api.get('/api/v1/operacional/employees/?page=1&page_size=200');
        setEmployees(res.data?.items || []);
      } catch {
        setErroAdicionar('Não foi possível carregar a lista de colaboradores.');
      } finally {
        setCarregandoEmployees(false);
      }
    }
  };

  const employeesFiltrados = useMemo(() => {
    const termo = buscaColab.trim().toLowerCase();
    if (!termo) return employees;
    return employees.filter(
      (e) => e.nome?.toLowerCase().includes(termo) || (e.cargo || '').toLowerCase().includes(termo)
    );
  }, [employees, buscaColab]);

  const salvarAdicionar = async () => {
    if (!colabSelecionado || !postoSelecionado) return;
    const erroValidacao = validarForm(formAdicionar);
    if (erroValidacao) {
      setErroAdicionar(erroValidacao);
      return;
    }
    setSalvandoAdicionar(true);
    setConflitosAdicionar([]);
    setErroAdicionar(null);
    try {
      const body: Record<string, unknown> = {
        ...montarBody(colabSelecionado.id, formAdicionar),
        criar_alocacao: criarAlocacao,
      };
      if (criarAlocacao && setorAlocacao.trim()) body.setor = setorAlocacao.trim();
      const res = await api.post<GradeSaveResponse>(
        `/api/v1/operacional/grade/${postoSelecionado}/colaborador`,
        body
      );
      toastSucessoGrade(res.data, colabSelecionado.nome);
      if (res.data.alocacao_criada) {
        toast.success(`Alocação de ${colabSelecionado.nome} criada neste posto.`);
      }
      setModalAdicionar(false);
      carregarGrade(true);
      carregarPostos();
    } catch (err: unknown) {
      tratarErroEscrita(err, setConflitosAdicionar, setErroAdicionar);
    } finally {
      setSalvandoAdicionar(false);
    }
  };

  // ── Modal encerrar na grade (DELETE) ──────────────────────────────────────
  const [alvoEncerrar, setAlvoEncerrar] = useState<{ employee_id: string; nome: string } | null>(null);
  const [dataEncerrar, setDataEncerrar] = useState('');
  const [encerrando, setEncerrando] = useState(false);
  const [erroEncerrar, setErroEncerrar] = useState<string | null>(null);

  const abrirEncerrar = (pessoa: { employee_id: string; nome: string }) => {
    setAlvoEncerrar(pessoa);
    setDataEncerrar(amanha);
    setErroEncerrar(null);
  };

  const confirmarEncerrar = async () => {
    if (!alvoEncerrar || !postoSelecionado || !dataEncerrar) return;
    setEncerrando(true);
    setErroEncerrar(null);
    try {
      const res = await api.delete(
        `/api/v1/operacional/grade/${postoSelecionado}/colaborador/${alvoEncerrar.employee_id}?a_partir_de=${dataEncerrar}`
      );
      toast.success(
        `${alvoEncerrar.nome} encerrado na grade: ${res.data?.turnos_cancelados ?? 0} turnos cancelados.`
      );
      setAlvoEncerrar(null);
      carregarGrade(true);
      carregarPostos();
    } catch (err: unknown) {
      const e = err as ApiErr;
      const detail = e.response?.data?.detail;
      if (e.response?.status === 403) {
        toast.error('Você é líder de posto: apenas visualização. A edição da grade é do gestor.');
      } else if (typeof detail === 'string') {
        setErroEncerrar(detail);
      } else if (detail && typeof detail === 'object' && detail.mensagem) {
        setErroEncerrar(detail.mensagem);
      } else {
        setErroEncerrar('Erro ao encerrar o colaborador na grade.');
      }
    } finally {
      setEncerrando(false);
    }
  };

  // ── Bloco de conflitos (409) reutilizado nos modais ───────────────────────
  const BlocoConflitos = ({ conflitos, mensagem }: { conflitos: ConflitoGrade[]; mensagem: string | null }) => {
    if (!mensagem && conflitos.length === 0) return null;
    return (
      <div className="mt-3 rounded-lg border border-red-300 bg-red-500/10 px-3 py-2 text-sm text-red-700 dark:text-red-400">
        {mensagem && <p className="font-medium">{mensagem}</p>}
        {conflitos.length > 0 && (
          <ul className="mt-1 space-y-0.5 text-xs">
            {conflitos.map((c, i) => (
              <li key={i}>
                {formatarDiaMes(c.dia)} — {c.posto || 'posto não informado'}
              </li>
            ))}
          </ul>
        )}
      </div>
    );
  };

  // ── Render ──────────────────────────────────────────────────────────────
  if (authLoading || !mounted) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <CalendarCog className="w-12 h-12" />
        </div>
      </div>
    );
  }

  const pessoas = grade?.pessoas || [];
  const semGrade = grade?.sem_grade || [];

  return (
    <div className="min-h-screen bg-grid">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="Operacional"
          title="Grade por pessoa"
          subtitle="Defina turno, alternância e padrão de cada colaborador — mudanças valem do dia escolhido em diante e propagam para os meses futuros"
          icon={<CalendarCog className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional/escalas/visual">
                <Button variant="outline" size="sm">
                  <Eye className="w-4 h-4 mr-2" />
                  Ver grade visual
                </Button>
              </Link>
              {!somenteLeitura && (
                <Button variant="primary" size="sm" onClick={abrirAdicionar} disabled={!postoSelecionado}>
                  <UserPlus className="w-4 h-4 mr-2" />
                  Adicionar colaborador
                </Button>
              )}
            </>
          }
        />

        {somenteLeitura && (
          <div className="mb-4 flex items-center gap-2 rounded-xl border border-amber-300 bg-amber-500/10 px-4 py-3 text-sm text-amber-700 dark:text-amber-400">
            <Lock className="w-4 h-4 flex-shrink-0" />
            Você é líder de posto: visualização apenas; edição é do gestor.
          </div>
        )}

        {/* Seletores */}
        <div className="mb-6 flex flex-wrap items-end gap-3">
          <div className="min-w-[260px]">
            <label className="mb-1.5 block text-sm font-medium text-[hsl(var(--muted-foreground))]">Posto</label>
            <select
              value={postoSelecionado}
              onChange={(e) => setPostoSelecionado(e.target.value)}
              className="h-11 w-full rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--input))] px-3 text-sm text-[hsl(var(--foreground))] focus:border-[hsl(var(--primary))] focus:outline-none"
              disabled={carregandoPostos}
            >
              {postos.length === 0 && <option value="">{carregandoPostos ? 'Carregando…' : 'Nenhum posto'}</option>}
              {postos.map((p) => (
                <option key={p.post_id} value={p.post_id}>
                  {p.post_nome} ({p.pessoas_na_grade} na grade)
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-[180px]">
            <label className="mb-1.5 block text-sm font-medium text-[hsl(var(--muted-foreground))]">Mês</label>
            <select
              value={mesAno}
              onChange={(e) => setMesAno(e.target.value)}
              className="h-11 w-full rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--input))] px-3 text-sm text-[hsl(var(--foreground))] focus:border-[hsl(var(--primary))] focus:outline-none"
            >
              {opcoesMes.map((o) => (
                <option key={o.valor} value={o.valor}>
                  {o.rotulo}
                </option>
              ))}
            </select>
          </div>
          <Button variant="outline" size="sm" className="h-11" onClick={() => carregarGrade()} disabled={carregandoGrade}>
            <RefreshCw className={`w-4 h-4 ${carregandoGrade ? 'animate-spin' : ''}`} />
          </Button>
        </div>

        {erroGrade && (
          <Card className="mb-6">
            <CardContent className="py-6 text-center text-sm text-[hsl(var(--muted-foreground))]">
              {erroGrade}
            </CardContent>
          </Card>
        )}

        {carregandoGrade && !grade ? (
          <Card>
            <CardContent className="py-12 text-center">
              <RefreshCw className="w-6 h-6 text-[hsl(var(--primary))] mx-auto mb-2 animate-spin" />
              <p className="text-sm text-[hsl(var(--muted-foreground))]">Carregando grade…</p>
            </CardContent>
          </Card>
        ) : grade ? (
          <>
            {/* Pessoas na grade */}
            <Card className="mb-6">
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base">
                  <Users className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                  {grade.post_nome} — {MESES_PT[grade.mes - 1]} {grade.ano}
                  <Badge variant="secondary" className="ml-1">
                    {pessoas.length} {pessoas.length === 1 ? 'pessoa' : 'pessoas'}
                  </Badge>
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {pessoas.length === 0 ? (
                  <p className="py-4 text-center text-sm text-[hsl(var(--muted-foreground))]">
                    Nenhuma pessoa na grade deste posto neste mês.
                  </p>
                ) : (
                  pessoas.map((p) => (
                    <div
                      key={p.employee_id}
                      className="rounded-xl border border-[hsl(var(--border))] bg-[hsl(var(--card))] p-4 space-y-2"
                    >
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="text-sm font-semibold text-[hsl(var(--foreground))]">{p.nome}</span>
                        {p.cargo && (
                          <span className="text-xs text-[hsl(var(--muted-foreground))]">{p.cargo}</span>
                        )}
                        <span className="inline-flex items-center rounded-full border border-[hsl(var(--primary))]/40 bg-[hsl(var(--primary))]/10 px-2.5 py-0.5 text-xs font-medium text-[hsl(var(--primary))]">
                          {chipPadrao(p)}
                        </span>
                        <span className="font-data text-xs tabular-nums text-[hsl(var(--muted-foreground))]">
                          {p.turnos_no_mes} {p.turnos_no_mes === 1 ? 'turno' : 'turnos'} no mês
                        </span>
                        {p.ferias.map((f, i) => (
                          <span
                            key={i}
                            className="inline-flex items-center gap-1 rounded-full border border-orange-300 bg-orange-500/10 px-2.5 py-0.5 text-xs font-medium text-orange-700 dark:text-orange-400"
                          >
                            <Palmtree className="w-3 h-3" />
                            Férias {formatarDiaMes(f.inicio)}–{formatarDiaMes(f.fim)}
                          </span>
                        ))}
                      </div>
                      <StripDias dias={p.dias} mes={grade.mes} ano={grade.ano} />
                      {!somenteLeitura && (
                        <div className="flex flex-wrap gap-2 pt-1">
                          <Button variant="outline" size="sm" onClick={() => abrirEdicao(p)}>
                            <Pencil className="w-3.5 h-3.5 mr-1.5" />
                            Editar grade
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="text-red-600 hover:text-red-700"
                            onClick={() => abrirEncerrar(p)}
                          >
                            <UserMinus className="w-3.5 h-3.5 mr-1.5" />
                            Encerrar na grade
                          </Button>
                        </div>
                      )}
                    </div>
                  ))
                )}
              </CardContent>
            </Card>

            {/* Sem grade neste mês */}
            {semGrade.length > 0 && (
              <Card>
                <CardHeader className="pb-2">
                  <CardTitle className="flex items-center gap-2 text-base">
                    <CalendarDays className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                    Sem grade neste mês
                    <Badge variant="secondary" className="ml-1">{semGrade.length}</Badge>
                  </CardTitle>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Alocados neste posto, mas sem nenhum turno programado no mês.
                  </p>
                </CardHeader>
                <CardContent className="space-y-2">
                  {semGrade.map((p) => (
                    <div
                      key={p.employee_id}
                      className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[hsl(var(--border))] p-3"
                    >
                      <div className="min-w-0">
                        <span className="text-sm font-medium text-[hsl(var(--foreground))]">{p.nome}</span>
                        {p.cargo && (
                          <span className="ml-2 text-xs text-[hsl(var(--muted-foreground))]">{p.cargo}</span>
                        )}
                      </div>
                      {!somenteLeitura && (
                        <Button variant="outline" size="sm" onClick={() => abrirEdicao(p)}>
                          <Plus className="w-3.5 h-3.5 mr-1.5" />
                          Escalar
                        </Button>
                      )}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}
          </>
        ) : null}

        {/* Modal editar/escalar */}
        <Modal
          isOpen={!!alvoEdicao}
          onClose={() => setAlvoEdicao(null)}
          title={alvoEdicao ? `Grade de ${alvoEdicao.nome}` : 'Editar grade'}
          description={alvoEdicao?.cargo || undefined}
          size="lg"
        >
          <CamposGrade form={formEdicao} setForm={setFormEdicao} minData={hoje} />
          <BlocoConflitos conflitos={conflitosEdicao} mensagem={erroEdicao} />
          <ModalFooter>
            <Button variant="outline" onClick={() => setAlvoEdicao(null)} disabled={salvandoEdicao}>
              Cancelar
            </Button>
            <Button variant="primary" onClick={salvarEdicao} isLoading={salvandoEdicao}>
              Salvar grade
            </Button>
          </ModalFooter>
        </Modal>

        {/* Modal adicionar colaborador */}
        <Modal
          isOpen={modalAdicionar}
          onClose={() => setModalAdicionar(false)}
          title="Adicionar colaborador ao posto"
          description="Colaboradores ativos de toda a empresa — inclusive recém-admitidos ainda sem alocação"
          size="lg"
        >
          {!colabSelecionado ? (
            <div className="space-y-3">
              <Input
                label="Buscar colaborador"
                placeholder="Nome ou cargo…"
                value={buscaColab}
                onChange={(e) => setBuscaColab(e.target.value)}
                icon={<Search className="w-4 h-4" />}
              />
              {carregandoEmployees ? (
                <p className="py-4 text-center text-sm text-[hsl(var(--muted-foreground))]">
                  Carregando colaboradores…
                </p>
              ) : (
                <div className="max-h-72 overflow-y-auto rounded-lg border border-[hsl(var(--border))] divide-y divide-[hsl(var(--border))]">
                  {employeesFiltrados.length === 0 ? (
                    <p className="py-4 text-center text-sm text-[hsl(var(--muted-foreground))]">
                      Nenhum colaborador encontrado.
                    </p>
                  ) : (
                    employeesFiltrados.map((e) => (
                      <button
                        key={e.id}
                        type="button"
                        onClick={() => setColabSelecionado(e)}
                        className="flex w-full items-center justify-between gap-2 px-3 py-2.5 text-left text-sm hover:bg-[hsl(var(--muted))]/50 transition-colors"
                      >
                        <span className="font-medium text-[hsl(var(--foreground))]">{e.nome}</span>
                        {e.cargo && (
                          <span className="text-xs text-[hsl(var(--muted-foreground))]">{e.cargo}</span>
                        )}
                      </button>
                    ))
                  )}
                </div>
              )}
              {erroAdicionar && <p className="text-sm text-red-600">{erroAdicionar}</p>}
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex items-center justify-between gap-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--muted))]/40 px-3 py-2">
                <div>
                  <p className="text-sm font-semibold text-[hsl(var(--foreground))]">{colabSelecionado.nome}</p>
                  {colabSelecionado.cargo && (
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">{colabSelecionado.cargo}</p>
                  )}
                </div>
                <Button variant="ghost" size="sm" onClick={() => setColabSelecionado(null)}>
                  Trocar
                </Button>
              </div>
              <CamposGrade form={formAdicionar} setForm={setFormAdicionar} minData={hoje} />
              <label className="flex items-start gap-2 text-sm text-[hsl(var(--foreground))] cursor-pointer">
                <input
                  type="checkbox"
                  className="mt-0.5 accent-[hsl(var(--primary))]"
                  checked={criarAlocacao}
                  onChange={(e) => setCriarAlocacao(e.target.checked)}
                />
                Criar alocação neste posto (registra autoria)
              </label>
              {criarAlocacao && (
                <Input
                  label="Setor (opcional)"
                  placeholder="Ex.: PORTARIA, RONDISTA…"
                  value={setorAlocacao}
                  onChange={(e) => setSetorAlocacao(e.target.value)}
                />
              )}
              <BlocoConflitos conflitos={conflitosAdicionar} mensagem={erroAdicionar} />
              <ModalFooter>
                <Button variant="outline" onClick={() => setModalAdicionar(false)} disabled={salvandoAdicionar}>
                  Cancelar
                </Button>
                <Button variant="primary" onClick={salvarAdicionar} isLoading={salvandoAdicionar}>
                  Adicionar à grade
                </Button>
              </ModalFooter>
            </div>
          )}
        </Modal>

        {/* Modal encerrar na grade */}
        <Modal
          isOpen={!!alvoEncerrar}
          onClose={() => setAlvoEncerrar(null)}
          title={alvoEncerrar ? `Encerrar ${alvoEncerrar.nome} na grade` : 'Encerrar na grade'}
          description="Os turnos futuros deste colaborador neste posto serão cancelados a partir da data escolhida. Presença já registrada nunca é tocada."
          size="sm"
        >
          <Input
            label="A partir de"
            type="date"
            min={hoje}
            value={dataEncerrar}
            onChange={(e) => setDataEncerrar(e.target.value)}
          />
          {erroEncerrar && <p className="mt-2 text-sm text-red-600">{erroEncerrar}</p>}
          <ModalFooter>
            <Button variant="outline" onClick={() => setAlvoEncerrar(null)} disabled={encerrando}>
              Cancelar
            </Button>
            <Button variant="danger" onClick={confirmarEncerrar} isLoading={encerrando}>
              Encerrar na grade
            </Button>
          </ModalFooter>
        </Modal>
      </main>
    </div>
  );
}
