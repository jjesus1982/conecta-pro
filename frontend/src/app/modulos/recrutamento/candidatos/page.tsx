'use client';

import { useState, useEffect, useCallback } from 'react';
import { UserPlus, Plus, Search, RefreshCw, Edit2, Trash2, ShieldBan, ShieldCheck, AlertCircle, Mail, Phone, User, Archive, ChevronLeft, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

const API_BASE = '/api/v1/recruitment/candidates';
const PAGE_SIZE = 15;

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const statusConfig: Record<string, { label: string; color: string }> = {
  ativo: { label: 'Ativo', color: 'bg-green-500/20 text-green-500 border-green-500/30' },
  inativo: { label: 'Inativo', color: 'bg-gray-500/20 text-gray-500 border-gray-500/30' },
  bloqueado: { label: 'Bloqueado', color: 'bg-red-500/20 text-red-500 border-red-500/30' },
  contratado: { label: 'Contratado', color: 'bg-blue-500/20 text-blue-500 border-blue-500/30' },
  arquivado: { label: 'Arquivado', color: 'bg-yellow-500/20 text-yellow-500 border-yellow-500/30' },
};

const sourceLabels: Record<string, string> = {
  site: 'Site',
  linkedin: 'LinkedIn',
  indicacao: 'Indicacao',
  banco_talentos: 'Banco de Talentos',
  feira_emprego: 'Feira de Emprego',
  agencia: 'Agencia',
  headhunter: 'Headhunter',
  rede_social: 'Rede Social',
  email: 'E-mail',
  presencial: 'Presencial',
  outro: 'Outro',
};

const emptyForm = {
  name: '',
  email: '',
  phone: '',
  whatsapp: '',
  cpf: '',
  city: '',
  state: '',
  headline: '',
  salary_expectation: '',
  source: 'site',
  availability: '',
};

export default function CandidatosPage() {
  const [candidates, setCandidates] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalItems, setTotalItems] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [stats, setStats] = useState<any>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({ ...emptyForm });

  const [detailOpen, setDetailOpen] = useState(false);
  const [detailItem, setDetailItem] = useState<any>(null);

  const [blockDialogOpen, setBlockDialogOpen] = useState(false);
  const [blockId, setBlockId] = useState<string | null>(null);
  const [blockReason, setBlockReason] = useState('');

  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));

  const fetchCandidates = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        skip: String((currentPage - 1) * PAGE_SIZE),
        limit: String(PAGE_SIZE),
        order_by: 'created_at',
        order_desc: 'true',
      });
      if (searchTerm) params.set('search', searchTerm);
      if (statusFilter !== 'all') params.set('status', statusFilter);

      const res = await fetch(`${API_BASE}/?${params}`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      const data = await res.json();
      setCandidates(data.items || []);
      setTotalItems(data.total || 0);
    } catch (err: any) {
      toast.error('Erro ao carregar candidatos', { description: err.message, duration: 4000 });
      setCandidates([]);
    } finally {
      setLoading(false);
    }
  }, [currentPage, searchTerm, statusFilter]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/stats`, { headers: getAuthHeaders() });
      if (res.ok) setStats(await res.json());
    } catch { /* silent */ }
  }, []);

  useEffect(() => { fetchCandidates(); }, [fetchCandidates]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  const openCreate = () => {
    setEditingId(null);
    setFormData({ ...emptyForm });
    setDialogOpen(true);
  };

  const openEdit = (item: any) => {
    setEditingId(item.id);
    setFormData({
      name: item.name || '',
      email: item.email || '',
      phone: item.phone || '',
      whatsapp: item.whatsapp || '',
      cpf: item.cpf || '',
      city: item.city || '',
      state: item.state || '',
      headline: item.headline || '',
      salary_expectation: item.salary_expectation != null ? String(item.salary_expectation) : '',
      source: item.source || 'site',
      availability: item.availability || '',
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!formData.name.trim() || !formData.email.trim()) {
      toast.error('Nome e e-mail sao obrigatorios', { duration: 4000 });
      return;
    }
    setSaving(true);
    try {
      const body: any = {
        ...formData,
        salary_expectation: formData.salary_expectation ? Number(formData.salary_expectation) : null,
      };
      Object.keys(body).forEach(k => { if (body[k] === '') body[k] = null; });
      // Ensure required fields are not null
      body.name = formData.name;
      body.email = formData.email;

      const url = editingId ? `${API_BASE}/${editingId}` : `${API_BASE}/`;
      const method = editingId ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method,
        headers: getAuthHeaders(),
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Erro ${res.status}`);
      }
      toast.success(editingId ? 'Candidato atualizado com sucesso' : 'Candidato cadastrado com sucesso', { duration: 4000 });
      setDialogOpen(false);
      fetchCandidates();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao salvar candidato', { description: err.message, duration: 5000 });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Tem certeza que deseja excluir este candidato?')) return;
    try {
      const res = await fetch(`${API_BASE}/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
      if (!res.ok && res.status !== 204) throw new Error(`Erro ${res.status}`);
      toast.success('Candidato excluido com sucesso', { duration: 4000 });
      fetchCandidates();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao excluir candidato', { description: err.message, duration: 5000 });
    }
  };

  const handleBlock = async () => {
    if (!blockId || !blockReason.trim()) {
      toast.error('Motivo do bloqueio e obrigatorio (min 5 caracteres)', { duration: 4000 });
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/${blockId}/block`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ reason: blockReason }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Erro ${res.status}`);
      }
      toast.success('Candidato bloqueado com sucesso', { duration: 4000 });
      setBlockDialogOpen(false);
      setBlockReason('');
      setBlockId(null);
      fetchCandidates();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao bloquear candidato', { description: err.message, duration: 5000 });
    }
  };

  const handleUnblock = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/${id}/unblock`, { method: 'POST', headers: getAuthHeaders(), body: '{}' });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      toast.success('Candidato desbloqueado com sucesso', { duration: 4000 });
      fetchCandidates();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao desbloquear candidato', { description: err.message, duration: 5000 });
    }
  };

  const handleArchive = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/${id}/archive`, { method: 'POST', headers: getAuthHeaders(), body: '{}' });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      toast.success('Candidato arquivado com sucesso', { duration: 4000 });
      fetchCandidates();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao arquivar candidato', { description: err.message, duration: 5000 });
    }
  };

  const handleActivate = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/${id}/activate`, { method: 'POST', headers: getAuthHeaders(), body: '{}' });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      toast.success('Candidato ativado com sucesso', { duration: 4000 });
      fetchCandidates();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao ativar candidato', { description: err.message, duration: 5000 });
    }
  };

  const openDetail = (item: any) => {
    setDetailItem(item);
    setDetailOpen(true);
  };

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <UserPlus className="h-6 w-6" />
            Candidatos
          </h1>
          <p className="text-muted-foreground">Base de candidatos cadastrados no sistema</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { fetchCandidates(); fetchStats(); }} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Candidato
          </Button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total</p>
            <p className="font-data text-2xl font-semibold tabular-nums">{stats?.total_candidates ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Ativos</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats?.active_candidates ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Bloqueados</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-red-600">{stats?.blocked_candidates ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Contratados</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-blue-600">{stats?.hired_candidates ?? 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Search & Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchTerm}
            onChange={(e) => { setSearchTerm(e.target.value); setCurrentPage(1); }}
            placeholder="Buscar candidatos por nome, e-mail ou telefone..."
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setCurrentPage(1); }}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os status</SelectItem>
            <SelectItem value="ativo">Ativo</SelectItem>
            <SelectItem value="inativo">Inativo</SelectItem>
            <SelectItem value="bloqueado">Bloqueado</SelectItem>
            <SelectItem value="contratado">Contratado</SelectItem>
            <SelectItem value="arquivado">Arquivado</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {loading ? (
            <div className="divide-y">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="p-4 flex items-center gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-48 bg-muted rounded animate-pulse" />
                    <div className="h-3 w-32 bg-muted rounded animate-pulse" />
                  </div>
                  <div className="h-6 w-20 bg-muted rounded animate-pulse" />
                </div>
              ))}
            </div>
          ) : candidates.length === 0 ? (
            <div className="text-center py-12">
              <UserPlus className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium">Nenhum registro encontrado</h3>
              <p className="text-muted-foreground mt-1">
                {searchTerm ? 'Tente ajustar a busca' : 'Cadastre seu primeiro candidato'}
              </p>
              {!searchTerm && (
                <Button className="mt-4" onClick={openCreate}>
                  <Plus className="h-4 w-4 mr-2" />
                  Novo Candidato
                </Button>
              )}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Candidato</TableHead>
                  <TableHead>Contato</TableHead>
                  <TableHead>Titulo</TableHead>
                  <TableHead>Origem</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Cadastro</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {candidates.map((candidate: any) => {
                  const st = statusConfig[candidate.status] ?? { label: candidate.status || 'Ativo', color: 'bg-green-500/20 text-green-500 border-green-500/30' };
                  return (
                    <TableRow key={candidate.id} className="cursor-pointer" onClick={() => openDetail(candidate)}>
                      <TableCell>
                        <div className="flex items-center gap-3">
                          <div className="h-9 w-9 rounded-full bg-primary/10 flex items-center justify-center flex-shrink-0">
                            <User className="h-4 w-4 text-primary" />
                          </div>
                          <div>
                            <p className="font-medium">{candidate.name}</p>
                            {candidate.cpf && (
                              <p className="text-xs text-muted-foreground">{candidate.cpf}</p>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div className="space-y-1">
                          {candidate.email && (
                            <div className="flex items-center gap-1 text-sm text-muted-foreground">
                              <Mail className="h-3 w-3" />
                              <span className="truncate max-w-[180px]">{candidate.email}</span>
                            </div>
                          )}
                          {candidate.phone && (
                            <div className="flex items-center gap-1 text-sm text-muted-foreground">
                              <Phone className="h-3 w-3" />
                              {candidate.phone}
                            </div>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm">{candidate.headline || candidate.current_position || '-'}</span>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-muted-foreground">{sourceLabels[candidate.source] || candidate.source || '-'}</span>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={st.color}>
                          {st.label}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-muted-foreground">
                          {candidate.created_at ? new Date(candidate.created_at).toLocaleDateString('pt-BR') : '-'}
                        </span>
                      </TableCell>
                      <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1">
                          <Button variant="ghost" size="sm" title="Editar" onClick={() => openEdit(candidate)}>
                            <Edit2 className="h-4 w-4" />
                          </Button>
                          {candidate.status === 'bloqueado' ? (
                            <Button variant="ghost" size="sm" title="Desbloquear" onClick={() => handleUnblock(candidate.id)}>
                              <ShieldCheck className="h-4 w-4 text-green-600" />
                            </Button>
                          ) : candidate.status !== 'contratado' ? (
                            <Button variant="ghost" size="sm" title="Bloquear" onClick={() => { setBlockId(candidate.id); setBlockDialogOpen(true); }}>
                              <ShieldBan className="h-4 w-4 text-orange-600" />
                            </Button>
                          ) : null}
                          {candidate.status === 'ativo' && (
                            <Button variant="ghost" size="sm" title="Arquivar" onClick={() => handleArchive(candidate.id)}>
                              <Archive className="h-4 w-4 text-yellow-600" />
                            </Button>
                          )}
                          {['inativo', 'arquivado'].includes(candidate.status) && (
                            <Button variant="ghost" size="sm" title="Ativar" onClick={() => handleActivate(candidate.id)}>
                              <ShieldCheck className="h-4 w-4 text-green-600" />
                            </Button>
                          )}
                          <Button
                            variant="ghost" size="sm" title="Excluir"
                            onClick={() => handleDelete(candidate.id)}
                            className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
                          >
                            <Trash2 className="h-4 w-4" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Pagination */}
      {!loading && totalItems > PAGE_SIZE && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Mostrando {((currentPage - 1) * PAGE_SIZE) + 1} a {Math.min(currentPage * PAGE_SIZE, totalItems)} de {totalItems} candidatos
          </p>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setCurrentPage(p => p - 1)} disabled={currentPage <= 1}>
              <ChevronLeft className="h-4 w-4" />
            </Button>
            <span className="text-sm">{currentPage} / {totalPages}</span>
            <Button variant="outline" size="sm" onClick={() => setCurrentPage(p => p + 1)} disabled={currentPage >= totalPages}>
              <ChevronRight className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

      {/* Create/Edit Dialog */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{editingId ? 'Editar Candidato' : 'Cadastrar Novo Candidato'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Nome Completo *</Label>
              <Input value={formData.name} onChange={(e) => setFormData({ ...formData, name: e.target.value })} placeholder="Nome do candidato" />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>E-mail *</Label>
                <Input type="email" value={formData.email} onChange={(e) => setFormData({ ...formData, email: e.target.value })} placeholder="email@exemplo.com" />
              </div>
              <div className="space-y-2">
                <Label>Telefone</Label>
                <Input value={formData.phone} onChange={(e) => setFormData({ ...formData, phone: e.target.value })} placeholder="(92) 99999-9999" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>WhatsApp</Label>
                <Input value={formData.whatsapp} onChange={(e) => setFormData({ ...formData, whatsapp: e.target.value })} placeholder="(92) 99999-9999" />
              </div>
              <div className="space-y-2">
                <Label>CPF</Label>
                <Input value={formData.cpf} onChange={(e) => setFormData({ ...formData, cpf: e.target.value })} placeholder="000.000.000-00" />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Cidade</Label>
                <Input value={formData.city} onChange={(e) => setFormData({ ...formData, city: e.target.value })} placeholder="Manaus" />
              </div>
              <div className="space-y-2">
                <Label>Estado</Label>
                <Input value={formData.state} onChange={(e) => setFormData({ ...formData, state: e.target.value })} placeholder="AM" maxLength={2} />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Titulo / Cargo Atual</Label>
              <Input value={formData.headline} onChange={(e) => setFormData({ ...formData, headline: e.target.value })} placeholder="Ex: Vigilante Patrimonial" />
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Pretensao Salarial (R$)</Label>
                <Input type="number" min={0} value={formData.salary_expectation} onChange={(e) => setFormData({ ...formData, salary_expectation: e.target.value })} placeholder="0.00" />
              </div>
              <div className="space-y-2">
                <Label>Origem</Label>
                <Select value={formData.source} onValueChange={(v) => setFormData({ ...formData, source: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(sourceLabels).map(([value, label]) => (
                      <SelectItem key={value} value={value}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Disponibilidade</Label>
                <Input value={formData.availability} onChange={(e) => setFormData({ ...formData, availability: e.target.value })} placeholder="Imediata" />
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancelar</Button>
            <Button onClick={handleSave} disabled={!formData.name || !formData.email || saving}>
              {saving ? 'Salvando...' : editingId ? 'Salvar Alteracoes' : 'Cadastrar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Block Dialog */}
      <Dialog open={blockDialogOpen} onOpenChange={setBlockDialogOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Bloquear Candidato</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Motivo do Bloqueio *</Label>
              <Input value={blockReason} onChange={(e) => setBlockReason(e.target.value)} placeholder="Informe o motivo (minimo 5 caracteres)" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setBlockDialogOpen(false); setBlockReason(''); }}>Cancelar</Button>
            <Button variant="destructive" onClick={handleBlock} disabled={blockReason.length < 5}>Bloquear</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Detalhes do Candidato</DialogTitle>
          </DialogHeader>
          {detailItem && (
            <div className="space-y-3 py-2 text-sm">
              <div><span className="font-medium">Nome:</span> {detailItem.name}</div>
              <div><span className="font-medium">E-mail:</span> {detailItem.email}</div>
              <div><span className="font-medium">Status:</span> <Badge variant="outline" className={statusConfig[detailItem.status]?.color}>{statusConfig[detailItem.status]?.label || detailItem.status}</Badge></div>
              {detailItem.phone && <div><span className="font-medium">Telefone:</span> {detailItem.phone}</div>}
              {detailItem.whatsapp && <div><span className="font-medium">WhatsApp:</span> {detailItem.whatsapp}</div>}
              {detailItem.cpf && <div><span className="font-medium">CPF:</span> {detailItem.cpf}</div>}
              {detailItem.city && <div><span className="font-medium">Local:</span> {[detailItem.city, detailItem.state].filter(Boolean).join(', ')}</div>}
              {detailItem.headline && <div><span className="font-medium">Titulo:</span> {detailItem.headline}</div>}
              {detailItem.current_company && <div><span className="font-medium">Empresa Atual:</span> {detailItem.current_company}</div>}
              {detailItem.current_position && <div><span className="font-medium">Cargo Atual:</span> {detailItem.current_position}</div>}
              {detailItem.salary_expectation && <div><span className="font-medium">Pretensao Salarial:</span> R$ {Number(detailItem.salary_expectation).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</div>}
              {detailItem.source && <div><span className="font-medium">Origem:</span> {sourceLabels[detailItem.source] || detailItem.source}</div>}
              {detailItem.availability && <div><span className="font-medium">Disponibilidade:</span> {detailItem.availability}</div>}
              {detailItem.tags?.length > 0 && <div><span className="font-medium">Tags:</span> {detailItem.tags.join(', ')}</div>}
              {detailItem.linkedin_url && <div><span className="font-medium">LinkedIn:</span> <a href={detailItem.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">{detailItem.linkedin_url}</a></div>}
              <div><span className="font-medium">Cadastrado em:</span> {detailItem.created_at ? new Date(detailItem.created_at).toLocaleString('pt-BR') : '-'}</div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
