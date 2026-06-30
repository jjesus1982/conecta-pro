'use client';

import { useState, useEffect, useCallback } from 'react';
import {
  ArrowLeft, CalendarClock, AlertTriangle,
  CheckCircle, Clock, Inbox, Loader2,
} from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

// ─── Constantes ───────────────────────────────────────────────────────────────

const API_BASE = '/api/v1/people-management/hr';

function getAuthHeaders(): HeadersInit {
  const token =
    typeof window !== 'undefined'
      ? (localStorage.getItem('access_token') || localStorage.getItem('token'))
      : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// ─── Tipos ────────────────────────────────────────────────────────────────────

interface AvisoPrevio {
  id: string;
  employee_id: string;
  employee_name: string;
  tipo: 'trabalhado' | 'indenizado';
  notice_period_days: number;
  notice_start_date: string;
  last_working_day: string;
  status: 'ativo' | 'concluido' | 'cancelado';
  dias_restantes?: number;
}

interface Funcionario {
  id: string;
  nome: string;
  cargo?: string;
  data_admissao?: string;
  anos_servico: number;
}

// ─── Helpers ──────────────────────────────────────────────────────────────────

/** Art. 487 CLT: 30 dias + 3 dias por ano completo, máximo 90 dias. */
function calcularDiasAviso(anosServico: number): number {
  return Math.min(90, 30 + Math.floor(anosServico) * 3);
}

function formatarData(data: string | null | undefined): string {
  if (!data) return '—';
  try {
    const dateOnly = data.includes('T') ? data.split('T')[0] : data;
    const parts = (dateOnly ?? data).split('-');
    if (parts.length === 3) return `${parts[2]}/${parts[1]}/${parts[0]}`;
    return data;
  } catch {
    return data;
  }
}

function diasRestantes(lastDay: string | null | undefined): number | undefined {
  if (!lastDay) return undefined;
  try {
    const hoje = new Date();
    hoje.setHours(0, 0, 0, 0);
    const ultimo = new Date(lastDay + 'T00:00:00');
    return Math.ceil((ultimo.getTime() - hoje.getTime()) / 86_400_000);
  } catch {
    return undefined;
  }
}

function somarDias(dataISO: string, dias: number): string {
  try {
    const d = new Date(dataISO + 'T00:00:00');
    d.setDate(d.getDate() + dias);
    return d.toISOString().slice(0, 10);
  } catch {
    return dataISO;
  }
}

// ─── Sub-componentes ──────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: AvisoPrevio['status'] }) {
  const cfg = {
    ativo:     { label: 'Em andamento', cls: 'bg-blue-100 text-blue-800 border-blue-200'    },
    concluido: { label: 'Concluído',    cls: 'bg-green-100 text-green-800 border-green-200' },
    cancelado: { label: 'Cancelado',    cls: 'bg-gray-100 text-gray-500 border-gray-200'    },
  };
  const c = cfg[status] ?? cfg.ativo;
  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${c.cls}`}
    >
      {c.label}
    </span>
  );
}

function TipoBadge({ tipo }: { tipo: AvisoPrevio['tipo'] }) {
  return tipo === 'trabalhado' ? (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
      Trabalhado
    </span>
  ) : (
    <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-purple-50 text-purple-700 border border-purple-200">
      Indenizado
    </span>
  );
}

// ─── Página principal ─────────────────────────────────────────────────────────

export default function AvisoPrevioPage() {
  const router = useRouter();

  const [avisos, setAvisos]       = useState<AvisoPrevio[]>([]);
  const [funcionarios, setFuncs]  = useState<Funcionario[]>([]);
  const [loading, setLoading]     = useState(true);
  const [modalAberto, setModal]   = useState(false);
  const [salvando, setSalvando]   = useState(false);

  const [form, setForm] = useState({
    employee_id:        '',
    tipo:               'trabalhado' as 'trabalhado' | 'indenizado',
    notice_start_date:  new Date().toISOString().slice(0, 10),
  });

  const [diasCalculados, setDias] = useState(30);

  // ── Fetch avisos ──────────────────────────────────────────────────────────

  const fetchAvisos = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/terminations`, {
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const raw = await res.json();
      const lista: any[] = Array.isArray(raw) ? raw : raw?.items ?? raw?.data ?? [];

      const mapped: AvisoPrevio[] = lista
        .filter((t) => t.notice_period_days || t.notice_start_date)
        .map((t) => ({
          id:                 t.id,
          employee_id:        t.employee_id,
          employee_name:      t.employee_name ?? t.employee?.nome ?? 'Desconhecido',
          tipo:               (t.notice_type === 'indenizado' ? 'indenizado' : 'trabalhado') as 'trabalhado' | 'indenizado',
          notice_period_days: t.notice_period_days ?? 30,
          notice_start_date:  t.notice_start_date ?? '',
          last_working_day:   t.last_working_day ?? '',
          status:             (
            ['completed', 'concluido'].includes(t.status)
              ? 'concluido'
              : ['cancelled', 'cancelado'].includes(t.status)
              ? 'cancelado'
              : 'ativo'
          ) as AvisoPrevio['status'],
          dias_restantes: diasRestantes(t.last_working_day),
        }));

      setAvisos(mapped);
    } catch (err) {
      console.error('Erro ao buscar avisos:', err);
      toast.error('Erro ao carregar avisos prévios');
    } finally {
      setLoading(false);
    }
  }, []);

  // ── Fetch funcionários ────────────────────────────────────────────────────

  const fetchFuncionarios = useCallback(async () => {
    try {
      const res = await fetch(
        `/api/v1/people-management/hr/employees?page_size=100`,
        { headers: getAuthHeaders() },
      );
      if (!res.ok) return;
      const raw = await res.json();
      const lista: any[] = Array.isArray(raw) ? raw : raw?.items ?? raw?.data ?? [];
      setFuncs(
        lista.map((e: any) => {
          const admissao = e.data_admissao ?? e.hire_date;
          const anos = admissao
            ? Math.floor((Date.now() - new Date(admissao).getTime()) / (365.25 * 86_400_000))
            : 0;
          return {
            id:            e.id,
            nome:          e.nome ?? e.name ?? '',
            cargo:         e.cargo ?? e.position ?? '',
            data_admissao: admissao,
            anos_servico:  anos,
          };
        }),
      );
    } catch {
      /* silencioso — não bloqueia a página */
    }
  }, []);

  useEffect(() => {
    fetchAvisos();
    fetchFuncionarios();
  }, [fetchAvisos, fetchFuncionarios]);

  // ── Selecionar funcionário — recalcular dias ──────────────────────────────

  const onSelectFuncionario = (empId: string) => {
    const func = funcionarios.find((f) => f.id === empId);
    const dias = calcularDiasAviso(func?.anos_servico ?? 0);
    setForm((prev) => ({ ...prev, employee_id: empId }));
    setDias(dias);
  };

  // ── Abrir aviso prévio ────────────────────────────────────────────────────

  const abrirAviso = async () => {
    if (!form.employee_id) {
      toast.error('Selecione um funcionário');
      return;
    }
    setSalvando(true);
    try {
      const lastDay = somarDias(form.notice_start_date, diasCalculados);
      const body = {
        employee_id:        form.employee_id,
        type:               'voluntary',
        notice_type:        form.tipo,
        notice_period_days: diasCalculados,
        notice_start_date:  form.notice_start_date,
        last_working_day:   lastDay,
        status:             'notice_period',
      };

      const res = await fetch(`${API_BASE}/terminations`, {
        method:  'POST',
        headers: getAuthHeaders(),
        body:    JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => null);
        throw new Error(err?.detail ?? `HTTP ${res.status}`);
      }

      toast.success(`Aviso prévio aberto — ${diasCalculados} dias (Art. 487 CLT)`);
      setModal(false);
      await fetchAvisos();
    } catch (err: any) {
      toast.error(`Erro: ${err.message}`);
    } finally {
      setSalvando(false);
    }
  };

  // ── Concluir aviso ────────────────────────────────────────────────────────

  const concluirAviso = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/terminations/${id}/complete`, {
        method:  'POST',
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      toast.success('Aviso prévio concluído');
      await fetchAvisos();
    } catch (err: any) {
      toast.error(`Erro ao concluir: ${err.message}`);
    }
  };

  // ── Stats ─────────────────────────────────────────────────────────────────

  const ativos     = avisos.filter((a) => a.status === 'ativo').length;
  const vencendo   = avisos.filter(
    (a) => a.status === 'ativo' && (a.dias_restantes ?? 99) <= 7,
  ).length;
  const concluidos = avisos.filter((a) => a.status === 'concluido').length;

  const funcSelecionada = funcionarios.find((f) => f.id === form.employee_id);
  const ultimoDiaPreview = form.employee_id
    ? somarDias(form.notice_start_date, diasCalculados)
    : '';

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div className="space-y-6 p-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <CalendarClock className="h-6 w-6" />
              Aviso Prévio
            </h1>
            <p className="text-sm text-muted-foreground mt-0.5">
              Controle de avisos prévios trabalhados e indenizados — Art. 487 CLT
            </p>
          </div>
        </div>
        <Button onClick={() => { setForm({ employee_id: '', tipo: 'trabalhado', notice_start_date: new Date().toISOString().slice(0, 10) }); setDias(30); setModal(true); }}>
          <CalendarClock className="h-4 w-4 mr-2" />
          Novo Aviso Prévio
        </Button>
      </div>

      {/* Cards resumo */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-2xl font-bold text-blue-600">
              <Clock className="h-5 w-5" />
              {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : ativos}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Em andamento</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-2xl font-bold text-orange-500">
              <AlertTriangle className="h-5 w-5" />
              {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : vencendo}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Vencendo em 7 dias</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-6">
            <div className="flex items-center gap-2 text-2xl font-bold text-green-600">
              <CheckCircle className="h-5 w-5" />
              {loading ? <Loader2 className="h-5 w-5 animate-spin" /> : concluidos}
            </div>
            <p className="text-xs text-muted-foreground mt-1">Concluídos</p>
          </CardContent>
        </Card>
      </div>

      {/* Tabela */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Avisos Prévios</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Funcionário</TableHead>
                <TableHead>Tipo</TableHead>
                <TableHead>Início</TableHead>
                <TableHead>Último dia</TableHead>
                <TableHead>Dias</TableHead>
                <TableHead>Restam</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Ações</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-10 text-center">
                    <Loader2 className="h-5 w-5 animate-spin mx-auto text-muted-foreground" />
                  </TableCell>
                </TableRow>
              ) : avisos.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={8} className="py-10 text-center text-muted-foreground">
                    <Inbox className="h-8 w-8 mx-auto mb-2 opacity-40" />
                    Nenhum aviso prévio registrado
                  </TableCell>
                </TableRow>
              ) : (
                avisos.map((aviso) => (
                  <TableRow key={aviso.id}>
                    <TableCell className="font-medium">{aviso.employee_name}</TableCell>
                    <TableCell><TipoBadge tipo={aviso.tipo} /></TableCell>
                    <TableCell className="text-sm">{formatarData(aviso.notice_start_date)}</TableCell>
                    <TableCell className="text-sm">{formatarData(aviso.last_working_day)}</TableCell>
                    <TableCell className="text-sm">{aviso.notice_period_days}d</TableCell>
                    <TableCell>
                      {aviso.status === 'ativo' && aviso.dias_restantes !== undefined ? (
                        <span className={`text-xs font-semibold ${
                          aviso.dias_restantes <= 0
                            ? 'text-red-600'
                            : aviso.dias_restantes <= 7
                            ? 'text-orange-500'
                            : 'text-foreground'
                        }`}>
                          {aviso.dias_restantes <= 0 ? 'Vencido' : `${aviso.dias_restantes}d`}
                        </span>
                      ) : '—'}
                    </TableCell>
                    <TableCell><StatusBadge status={aviso.status} /></TableCell>
                    <TableCell className="text-right">
                      {aviso.status === 'ativo' && (
                        <Button
                          size="sm"
                          variant="outline"
                          className="h-7 px-2 text-xs"
                          onClick={() => concluirAviso(aviso.id)}
                        >
                          Concluir
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* Modal — novo aviso prévio */}
      <Dialog open={modalAberto} onOpenChange={setModal}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Novo Aviso Prévio</DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {/* Funcionário */}
            <div className="space-y-1.5">
              <Label>Funcionário</Label>
              <Select value={form.employee_id} onValueChange={onSelectFuncionario}>
                <SelectTrigger>
                  <SelectValue placeholder="Selecionar funcionário" />
                </SelectTrigger>
                <SelectContent>
                  {funcionarios.length === 0 ? (
                    <SelectItem value="__none__" disabled>
                      Nenhum funcionário ativo
                    </SelectItem>
                  ) : (
                    funcionarios.map((f) => (
                      <SelectItem key={f.id} value={f.id}>
                        {f.nome}{f.cargo ? ` — ${f.cargo}` : ''}
                      </SelectItem>
                    ))
                  )}
                </SelectContent>
              </Select>
            </div>

            {/* Tipo */}
            <div className="space-y-1.5">
              <Label>Tipo de Aviso</Label>
              <Select
                value={form.tipo}
                onValueChange={(v) => setForm((p) => ({ ...p, tipo: v as 'trabalhado' | 'indenizado' }))}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="trabalhado">Trabalhado — funcionário cumpre o prazo</SelectItem>
                  <SelectItem value="indenizado">Indenizado — empresa paga em dinheiro</SelectItem>
                </SelectContent>
              </Select>
            </div>

            {/* Data início */}
            <div className="space-y-1.5">
              <Label>Data de início do aviso</Label>
              <Input
                type="date"
                value={form.notice_start_date}
                onChange={(e) => setForm((p) => ({ ...p, notice_start_date: e.target.value }))}
              />
            </div>

            {/* Resumo calculado */}
            {form.employee_id && (
              <div className="rounded-lg border bg-muted/50 p-3 text-sm space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Funcionário</span>
                  <span className="font-medium">{funcSelecionada?.nome}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Anos de serviço</span>
                  <span>{funcSelecionada?.anos_servico ?? 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Dias de aviso (Art. 487 CLT)</span>
                  <span className="font-bold text-primary">{diasCalculados} dias</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Último dia de trabalho</span>
                  <span className="font-medium">{formatarData(ultimoDiaPreview)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Modalidade</span>
                  <TipoBadge tipo={form.tipo} />
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setModal(false)}>
              Cancelar
            </Button>
            <Button onClick={abrirAviso} disabled={salvando || !form.employee_id}>
              {salvando ? (
                <><Loader2 className="h-4 w-4 mr-2 animate-spin" /> Salvando...</>
              ) : (
                'Abrir Aviso Prévio'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
