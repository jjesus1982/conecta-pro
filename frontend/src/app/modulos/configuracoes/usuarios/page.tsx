'use client';

import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Shield, ShieldCheck, Users, RefreshCw, X, Save, Lock } from 'lucide-react';
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
  admin: 'Admin', super_admin: 'Super Admin', manager: 'Gestor',
  supervisor: 'Supervisor', operator: 'Operador', staff: 'Staff',
  agente: 'Agente', developer: 'Dev', client: 'Cliente', viewer: 'Viewer',
};

// ── Helpers ──────────────────────────────────────────────────────────────────

function roleBadgeClass(role: string): string {
  if (role === 'admin' || role === 'super_admin') return 'bg-purple-100 text-purple-800 border-purple-200';
  if (role === 'supervisor' || role === 'manager') return 'bg-blue-100 text-blue-800 border-blue-200';
  if (role === 'developer') return 'bg-amber-100 text-amber-800 border-amber-200';
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

  const { data, isLoading, error, refetch } = useQuery<UsersResponse>({
    queryKey: ['usuarios-admin', page],
    queryFn: () => fetchUsers(page),
    staleTime: 30_000,
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
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setSelected(u)}
                        className="text-xs"
                      >
                        {isJordan(u) ? 'Ver' : 'Editar'}
                      </Button>
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
