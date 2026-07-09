'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Shield, ShieldCheck, Users, RefreshCw, X, Save, Lock, UserCheck, UserX, Clock, AlertTriangle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { customInstance } from '@/lib/api-client';

// ── Types ────────────────────────────────────────────────────────────────────

interface UserItem {
  id: string;
  email: string;
  name: string;
  role: string;
  permissions: string[];
  is_active: boolean;
}

interface UsersResponse {
  users: UserItem[];
  total: number;
  page: number;
  per_page: number;
}

interface ModuloConfig {
  slug: string;
  label: string;
  icon: string;
  warning?: string;
  jordanOnly?: boolean;
}

// ── Constantes ───────────────────────────────────────────────────────────────

const MODULOS: ModuloConfig[] = [
  { slug: 'module:financeiro', label: 'Financeiro', icon: '$', warning: 'Exclusivo Jordan', jordanOnly: true },
  { slug: 'module:fiscal', label: 'Fiscal', icon: '📄' },
  { slug: 'module:dp', label: 'DP & Folha', icon: '👥' },
  { slug: 'module:operacional', label: 'Operacional', icon: '🏢' },
  { slug: 'module:crm', label: 'CRM', icon: '🤝' },
  { slug: 'module:ged', label: 'GED', icon: '📁' },
  { slug: 'module:dev', label: 'Desenvolvimento', icon: '💻' },
];

const JORDAN_EMAIL = 'jjesus@conectamais.pro';

const ROLE_LABEL: Record<string, string> = {
  admin: 'Admin', super_admin: 'Super Admin', manager: 'Gestor', gestor: 'Gestor',
  supervisor: 'Supervisor', operator: 'Operador', operador: 'Operador', staff: 'Staff',
  agente: 'Agente', developer: 'Dev', client: 'Cliente', viewer: 'Viewer',
  funcionario: 'Funcionário', pending: 'Pendente',
  administrador: 'Admin Operacional', gerente_operacional: 'Gerente Operacional',
  inspetor: 'Inspetor', lider: 'Líder', lider_posto: 'Líder de Posto',
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function roleBadgeClass(role: string): string {
  if (role === 'admin' || role === 'super_admin') return 'bg-purple-100 text-purple-800 border-purple-200';
  if (role === 'supervisor' || role === 'manager' || role === 'gestor') return 'bg-blue-100 text-blue-800 border-blue-200';
  if (role === 'developer') return 'bg-amber-100 text-amber-800 border-amber-200';
  if (role === 'pending') return 'bg-amber-100 text-amber-800 border-amber-300';
  return 'bg-gray-100 text-gray-700 border-gray-200';
}

function isJordan(u: UserItem): boolean {
  return u.email === JORDAN_EMAIL;
}

// ── API calls ─────────────────────────────────────────────────────────────────

async function fetchUsers(page: number): Promise<UsersResponse> {
  return customInstance<UsersResponse>({
    url: '/api/v1/users/',
    method: 'GET',
    params: { page, per_page: 30 },
  });
}

async function patchPermissions(userId: string, permissions: string[]): Promise<UserItem> {
  return customInstance<UserItem>({
    url: `/api/v1/users/${userId}/permissions`,
    method: 'PATCH',
    data: { permissions },
  });
}

// ── Aprovação de cadastros pendentes ─────────────────────────────────────────

interface PendingUser {
  id: string;
  email: string;
  name: string;
  role: string;
  phone?: string | null;
  created_at?: string | null;
}

interface Perfil {
  value: string;
  label: string;
  description?: string;
}

interface EmployeeLite {
  id: string;
  nome: string;
  cargo?: string | null;
  matricula?: string | null;
}

async function fetchPending(): Promise<PendingUser[]> {
  const res = await customInstance<PendingUser[] | { users?: PendingUser[] }>({
    url: '/api/v1/users/pending',
    method: 'GET',
  });
  return Array.isArray(res) ? res : res?.users ?? [];
}

// GET /users/perfis nasce no deploy do backend — parsing defensivo de formato
async function fetchPerfis(): Promise<Perfil[]> {
  const res = await customInstance<unknown>({ url: '/api/v1/users/perfis', method: 'GET' });
  const raw = Array.isArray(res)
    ? res
    : (res as { perfis?: unknown[]; roles?: unknown[] })?.perfis ??
      (res as { roles?: unknown[] })?.roles ??
      [];
  return (raw as unknown[])
    .map((p): Perfil | null => {
      if (typeof p === 'string') return { value: p, label: ROLE_LABEL[p] ?? p };
      if (p && typeof p === 'object') {
        const obj = p as Record<string, unknown>;
        const value = (obj.value ?? obj.slug ?? obj.id ?? obj.perfil) as string | undefined;
        if (!value) return null;
        const label = (obj.label ?? obj.nome ?? obj.name) as string | undefined;
        const description = (obj.description ?? obj.descricao) as string | undefined;
        return { value, label: label ?? ROLE_LABEL[value] ?? value, description };
      }
      return null;
    })
    .filter((p): p is Perfil => p !== null && p.value !== 'pending');
}

async function fetchEmployeesLite(): Promise<EmployeeLite[]> {
  const res = await customInstance<{ items?: EmployeeLite[] } | EmployeeLite[]>({
    url: '/api/v1/people-management/hr/employees',
    method: 'GET',
    params: { page_size: 100 },
  });
  const items = Array.isArray(res) ? res : res?.items ?? [];
  return items.filter((e) => e?.id && e?.nome);
}

async function aprovarUsuario(userId: string, perfil: string, employeeId?: string): Promise<unknown> {
  return customInstance({
    url: `/api/v1/users/${userId}/aprovar`,
    method: 'POST',
    data: { perfil, ...(employeeId ? { employee_id: employeeId } : {}) },
  });
}

async function setUserActive(userId: string, active: boolean): Promise<unknown> {
  return customInstance({
    url: `/api/v1/users/${userId}/${active ? 'activate' : 'deactivate'}`,
    method: 'PATCH',
  });
}

function apiErrorDetail(err: unknown, fallback: string): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  const status = (err as { response?: { status?: number } })?.response?.status;
  if (status === 404 || status === 405) {
    return 'Endpoint ainda não disponível no backend (aguardando deploy da liberação).';
  }
  return fallback;
}

// Perfis que exigem vínculo com funcionário-líder
function perfilExigeFuncionario(perfil: string): boolean {
  return perfil === 'lider_posto' || perfil === 'lider';
}

// ── Card de usuário pendente ──────────────────────────────────────────────────

interface PendingRowProps {
  user: PendingUser;
  perfis: Perfil[];
  perfisError: boolean;
  employees: EmployeeLite[];
  employeesError: boolean;
}

function PendingRow({ user, perfis, perfisError, employees, employeesError }: PendingRowProps) {
  const [perfil, setPerfil] = useState('');
  const [employeeId, setEmployeeId] = useState('');
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['usuarios-pendentes'] });
    queryClient.invalidateQueries({ queryKey: ['usuarios-admin'] });
  };

  const aprovar = useMutation({
    mutationFn: () => aprovarUsuario(user.id, perfil, perfilExigeFuncionario(perfil) ? employeeId || undefined : undefined),
    onSuccess: invalidate,
    onError: (err: unknown) => setError(apiErrorDetail(err, 'Erro ao aprovar usuário.')),
  });

  const recusar = useMutation({
    mutationFn: () => setUserActive(user.id, false),
    onSuccess: invalidate,
    onError: (err: unknown) => setError(apiErrorDetail(err, 'Erro ao recusar usuário.')),
  });

  const precisaFuncionario = perfilExigeFuncionario(perfil);
  const podeAprovar =
    !!perfil && !perfisError && (!precisaFuncionario || !!employeeId) && !aprovar.isPending && !recusar.isPending;

  return (
    <div className="rounded-lg border border-amber-200 bg-white px-4 py-3">
      <div className="flex flex-wrap items-center gap-3">
        <div className="min-w-[200px] flex-1">
          <p className="text-sm font-semibold text-gray-800">{user.name}</p>
          <p className="text-xs text-gray-500">{user.email}</p>
          {user.created_at && (
            <p className="text-[11px] text-gray-400">
              Solicitado em {new Date(user.created_at).toLocaleDateString('pt-BR')}
            </p>
          )}
        </div>

        {/* Perfil */}
        <select
          value={perfil}
          onChange={(e) => { setPerfil(e.target.value); setError(null); }}
          disabled={perfisError || perfis.length === 0}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1E3A5F] disabled:opacity-60"
          aria-label="Perfil de acesso"
        >
          <option value="">
            {perfisError ? 'Perfis indisponíveis' : 'Selecionar perfil…'}
          </option>
          {perfis.map((p) => (
            <option key={p.value} value={p.value} title={p.description}>
              {p.label}
            </option>
          ))}
        </select>

        {/* Funcionário-líder (só p/ perfil líder de posto) */}
        {precisaFuncionario && (
          employeesError || employees.length === 0 ? (
            <input
              type="text"
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              placeholder="ID do funcionário-líder"
              className="w-56 rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1E3A5F]"
            />
          ) : (
            <select
              value={employeeId}
              onChange={(e) => setEmployeeId(e.target.value)}
              className="max-w-[260px] rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1E3A5F]"
              aria-label="Funcionário-líder"
            >
              <option value="">Funcionário-líder…</option>
              {employees.map((e) => (
                <option key={e.id} value={e.id}>
                  {e.nome}{e.cargo ? ` — ${e.cargo}` : ''}
                </option>
              ))}
            </select>
          )
        )}

        <div className="flex gap-2">
          <Button
            size="sm"
            disabled={!podeAprovar}
            onClick={() => { setError(null); aprovar.mutate(); }}
            className="bg-green-600 hover:bg-green-700 text-white"
          >
            <UserCheck className="h-4 w-4 mr-1" />
            {aprovar.isPending ? 'Aprovando…' : 'Aprovar'}
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={aprovar.isPending || recusar.isPending}
            onClick={() => {
              if (window.confirm(`Recusar o cadastro de ${user.name}? A conta será desativada.`)) {
                setError(null);
                recusar.mutate();
              }
            }}
            className="border-red-300 text-red-700 hover:bg-red-50"
          >
            <UserX className="h-4 w-4 mr-1" />
            {recusar.isPending ? 'Recusando…' : 'Recusar'}
          </Button>
        </div>
      </div>

      {precisaFuncionario && (employeesError || employees.length === 0) && (
        <p className="mt-2 text-xs text-amber-700">
          Lista de funcionários indisponível — informe o ID do funcionário manualmente.
        </p>
      )}
      {error && (
        <div className="mt-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}
    </div>
  );
}

// ── Seção Pendentes ───────────────────────────────────────────────────────────

function PendingSection() {
  const { data: pending, isLoading, error } = useQuery<PendingUser[]>({
    queryKey: ['usuarios-pendentes'],
    queryFn: fetchPending,
    staleTime: 15_000,
    retry: 1,
  });

  const perfisQuery = useQuery<Perfil[]>({
    queryKey: ['usuarios-perfis'],
    queryFn: fetchPerfis,
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const temPendentes = (pending?.length ?? 0) > 0;
  const algumLider = temPendentes; // pré-carrega lista quando há pendentes (select de líder)

  const employeesQuery = useQuery<EmployeeLite[]>({
    queryKey: ['usuarios-employees-lite'],
    queryFn: fetchEmployeesLite,
    enabled: algumLider,
    staleTime: 5 * 60_000,
    retry: 1,
  });

  const count = pending?.length ?? 0;

  return (
    <Card className="border-amber-300">
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Clock className="h-4 w-4 text-amber-600" />
          Pendentes ({isLoading ? '…' : count})
          {count > 0 && (
            <Badge className="bg-amber-100 text-amber-800 border-amber-300 text-xs">
              aguardando aprovação
            </Badge>
          )}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {error ? (
          <div className="flex items-center gap-2 rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
            <AlertTriangle className="h-4 w-4 flex-shrink-0" />
            Erro ao carregar cadastros pendentes. Verifique sua permissão de administrador.
          </div>
        ) : isLoading ? (
          <div className="flex items-center justify-center py-6">
            <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-amber-500" />
          </div>
        ) : count === 0 ? (
          <p className="text-sm text-gray-400 py-2">Nenhum cadastro aguardando aprovação.</p>
        ) : (
          <>
            {perfisQuery.isError && (
              <div className="flex items-center gap-2 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-800">
                <AlertTriangle className="h-4 w-4 flex-shrink-0" />
                Não foi possível carregar os perfis (GET /users/perfis) — o endpoint pode ainda
                não estar no ar. A aprovação fica bloqueada até o backend ser atualizado.
              </div>
            )}
            {(pending ?? []).map((u) => (
              <PendingRow
                key={u.id}
                user={u}
                perfis={perfisQuery.data ?? []}
                perfisError={perfisQuery.isError}
                employees={employeesQuery.data ?? []}
                employeesError={employeesQuery.isError}
              />
            ))}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── Drawer de edição de permissões ────────────────────────────────────────────

interface PermDrawerProps {
  user: UserItem;
  onClose: () => void;
  onSaved: (updated: UserItem) => void;
}

function PermDrawer({ user, onClose, onSaved }: PermDrawerProps) {
  const [selected, setSelected] = useState<Set<string>>(new Set(user.permissions));
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: (perms: string[]) => patchPermissions(user.id, perms),
    onSuccess: (updated) => {
      queryClient.invalidateQueries({ queryKey: ['usuarios-admin'] });
      onSaved(updated);
      onClose();
    },
    onError: (err: unknown) => {
      const detail = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detail ?? 'Erro ao salvar permissões.');
    },
  });

  function toggle(slug: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(slug) ? next.delete(slug) : next.add(slug);
      return next;
    });
    setError(null);
  }

  const isProtected = isJordan(user);

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="fixed inset-0 bg-black/30" onClick={onClose} />
      <div className="relative z-10 w-full max-w-md bg-white shadow-xl flex flex-col h-full">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b bg-[#1E3A5F]">
          <div>
            <h2 className="text-white font-semibold text-base">{user.name}</h2>
            <p className="text-blue-200 text-xs">{user.email}</p>
          </div>
          <button onClick={onClose} className="text-white hover:text-blue-200 transition-colors">
            <X className="h-5 w-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto px-6 py-5 space-y-4">
          {isProtected ? (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 flex items-center gap-3">
              <ShieldCheck className="h-5 w-5 text-amber-600 flex-shrink-0" />
              <div>
                <p className="text-sm font-semibold text-amber-800">Acesso Total (CEO)</p>
                <p className="text-xs text-amber-700">Permissões de Jordan Jesus não podem ser alteradas.</p>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-600">
              Selecione os módulos que <strong>{user.name}</strong> pode acessar:
            </p>
          )}

          <div className="space-y-2">
            {MODULOS.map((mod) => {
              const locked = isProtected || mod.jordanOnly;
              const checked = isProtected
                ? mod.slug === 'module:financeiro' || selected.has(mod.slug)
                : selected.has(mod.slug);

              return (
                <label
                  key={mod.slug}
                  className={`flex items-center gap-3 rounded-lg border px-4 py-3 transition-colors ${
                    locked
                      ? 'bg-gray-50 cursor-not-allowed opacity-70'
                      : 'cursor-pointer hover:bg-blue-50 hover:border-blue-300'
                  } ${checked && !locked ? 'border-blue-400 bg-blue-50' : 'border-gray-200'}`}
                >
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-[#1E3A5F]"
                    checked={checked}
                    disabled={locked}
                    onChange={() => !locked && toggle(mod.slug)}
                  />
                  <span className="text-lg leading-none">{mod.icon}</span>
                  <span className="flex-1 text-sm font-medium text-gray-800">{mod.label}</span>
                  {mod.jordanOnly && (
                    <span className="flex items-center gap-1 text-xs text-amber-700 font-medium">
                      <Lock className="h-3 w-3" />
                      Exclusivo CEO
                    </span>
                  )}
                  {!mod.jordanOnly && checked && !locked && (
                    <Badge className="bg-green-100 text-green-800 border-green-200 text-xs">Ativo</Badge>
                  )}
                </label>
              );
            })}
          </div>

          {error && (
            <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">
              {error}
            </div>
          )}
        </div>

        {/* Footer */}
        {!isProtected && (
          <div className="border-t px-6 py-4 flex gap-3">
            <Button variant="outline" onClick={onClose} disabled={mutation.isPending} className="flex-1">
              Cancelar
            </Button>
            <Button
              onClick={() => mutation.mutate([...selected])}
              disabled={mutation.isPending}
              className="flex-1 bg-[#1E3A5F] hover:bg-[#16304f] text-white"
            >
              <Save className="h-4 w-4 mr-2" />
              {mutation.isPending ? 'Salvando…' : 'Salvar'}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Página principal ──────────────────────────────────────────────────────────

export default function UsuariosPage() {
  const [page] = useState(1);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState<UserItem | null>(null);
  const [activeError, setActiveError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const { data, isLoading, error, refetch } = useQuery<UsersResponse>({
    queryKey: ['usuarios-admin', page],
    queryFn: () => fetchUsers(page),
    staleTime: 30_000,
  });

  const toggleActive = useMutation({
    mutationFn: ({ userId, active }: { userId: string; active: boolean }) =>
      setUserActive(userId, active),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['usuarios-admin'] });
      setActiveError(null);
    },
    onError: (err: unknown) =>
      setActiveError(apiErrorDetail(err, 'Erro ao alterar status do usuário.')),
  });

  const users = data?.users ?? [];
  const filtered = search
    ? users.filter(
        (u) =>
          u.name.toLowerCase().includes(search.toLowerCase()) ||
          u.email.toLowerCase().includes(search.toLowerCase()),
      )
    : users;

  function modBadges(perms: string[], userEmail: string) {
    if (userEmail === JORDAN_EMAIL) {
      return (
        <Badge className="bg-amber-100 text-amber-800 border-amber-200 text-xs">
          <ShieldCheck className="h-3 w-3 mr-1" /> Acesso Total
        </Badge>
      );
    }
    if (perms.length === 0) {
      return <span className="text-xs text-gray-400">Sem módulos</span>;
    }
    return (
      <div className="flex flex-wrap gap-1">
        {perms.map((p) => {
          const mod = MODULOS.find((m) => m.slug === p);
          return mod ? (
            <Badge key={p} className="bg-blue-100 text-blue-800 border-blue-200 text-xs">
              {mod.icon} {mod.label}
            </Badge>
          ) : null;
        })}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Shield className="h-6 w-6 text-[#1E3A5F]" />
            Gestão de Permissões
          </h1>
          <p className="text-muted-foreground text-sm">
            Controle quais módulos cada usuário pode acessar. Apenas Jordan pode editar.
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Cadastros pendentes de aprovação */}
      <PendingSection />

      {/* Search */}
      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Buscar por nome ou email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="w-full max-w-sm rounded-md border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1E3A5F]"
        />
        <Badge variant="outline" className="self-center">
          {filtered.length} usuário{filtered.length !== 1 ? 's' : ''}
        </Badge>
      </div>

      {/* Error */}
      {error && (
        <div className="rounded border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
          Erro ao carregar usuários. Verifique se você tem permissão de administrador.
        </div>
      )}
      {activeError && (
        <div className="rounded border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-700">
          {activeError}
        </div>
      )}

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Users className="h-4 w-4" />
            Usuários do Sistema
          </CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-[#1E3A5F]" />
            </div>
          ) : filtered.length === 0 ? (
            <div className="py-12 text-center text-sm text-gray-400">Nenhum usuário encontrado.</div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow className="bg-gray-50">
                  <TableHead>Nome</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Módulos com acesso</TableHead>
                  <TableHead>Ativo</TableHead>
                  <TableHead className="w-24"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((u) => (
                  <TableRow key={u.id} className="hover:bg-gray-50">
                    <TableCell className="font-medium text-sm">
                      {u.name}
                      {isJordan(u) && (
                        <span className="ml-2 text-xs text-amber-600 font-semibold">(CEO)</span>
                      )}
                    </TableCell>
                    <TableCell className="text-sm text-gray-600">{u.email}</TableCell>
                    <TableCell>
                      <Badge className={`text-xs ${roleBadgeClass(u.role)}`}>
                        {ROLE_LABEL[u.role] ?? u.role}
                      </Badge>
                    </TableCell>
                    <TableCell>{modBadges(u.permissions, u.email)}</TableCell>
                    <TableCell>
                      <Badge
                        className={
                          u.is_active
                            ? 'bg-green-100 text-green-800 border-green-200 text-xs'
                            : 'bg-red-100 text-red-800 border-red-200 text-xs'
                        }
                      >
                        {u.is_active ? 'Ativo' : 'Inativo'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex gap-1.5">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => setSelected(u)}
                          className="text-xs"
                        >
                          {isJordan(u) ? 'Ver' : 'Editar'}
                        </Button>
                        {!isJordan(u) && (
                          <Button
                            size="sm"
                            variant="outline"
                            disabled={toggleActive.isPending}
                            onClick={() => {
                              const acao = u.is_active ? 'Desativar' : 'Ativar';
                              if (window.confirm(`${acao} o usuário ${u.name}?`)) {
                                toggleActive.mutate({ userId: u.id, active: !u.is_active });
                              }
                            }}
                            className={`text-xs ${
                              u.is_active
                                ? 'border-red-300 text-red-700 hover:bg-red-50'
                                : 'border-green-300 text-green-700 hover:bg-green-50'
                            }`}
                          >
                            {u.is_active ? 'Desativar' : 'Ativar'}
                          </Button>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Drawer */}
      {selected && (
        <PermDrawer
          user={selected}
          onClose={() => setSelected(null)}
          onSaved={(updated) => setSelected(updated)}
        />
      )}
    </div>
  );
}
