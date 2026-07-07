'use client';

import { useState, useEffect, useCallback } from 'react';
import { FileText, Plus, Search, RefreshCw, AlertCircle, ChevronRight as ChevronRightIcon, XCircle, Send, Clock, CheckCircle, Ban, Star, ChevronLeft, ChevronRight } from 'lucide-react';
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

const API_BASE = '/api/v1/recruitment/applications';
const PAGE_SIZE = 15;

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const statusConfig: Record<string, { label: string; color: string }> = {
  inscrito: { label: 'Inscrito', color: 'bg-blue-500/20 text-blue-500 border-blue-500/30' },
  triagem: { label: 'Triagem', color: 'bg-cyan-500/20 text-cyan-500 border-cyan-500/30' },
  triagem_reprovado: { label: 'Triagem Reprovado', color: 'bg-gray-500/20 text-gray-500 border-gray-500/30' },
  entrevista_rh: { label: 'Entrevista RH', color: 'bg-purple-500/20 text-purple-500 border-purple-500/30' },
  entrevista_tecnica: { label: 'Entrevista Tecnica', color: 'bg-indigo-500/20 text-indigo-500 border-indigo-500/30' },
  entrevista_gestor: { label: 'Entrevista Gestor', color: 'bg-violet-500/20 text-violet-500 border-violet-500/30' },
  teste: { label: 'Teste', color: 'bg-orange-500/20 text-orange-500 border-orange-500/30' },
  referencias: { label: 'Referencias', color: 'bg-amber-500/20 text-amber-500 border-amber-500/30' },
  proposta: { label: 'Proposta', color: 'bg-yellow-500/20 text-yellow-500 border-yellow-500/30' },
  proposta_recusada: { label: 'Proposta Recusada', color: 'bg-red-500/20 text-red-500 border-red-500/30' },
  contratado: { label: 'Contratado', color: 'bg-green-500/20 text-green-500 border-green-500/30' },
  reprovado: { label: 'Reprovado', color: 'bg-red-500/20 text-red-500 border-red-500/30' },
  desistiu: { label: 'Desistiu', color: 'bg-gray-500/20 text-gray-500 border-gray-500/30' },
};

const terminalStatuses = ['contratado', 'reprovado', 'desistiu', 'triagem_reprovado', 'proposta_recusada'];

export default function CandidaturasPage() {
  const [applications, setApplications] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalItems, setTotalItems] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [stats, setStats] = useState<any>(null);

  const [createOpen, setCreateOpen] = useState(false);
  const [createData, setCreateData] = useState({ job_position_id: '', candidate_id: '', cover_letter: '', salary_expectation: '' });
  const [saving, setSaving] = useState(false);

  const [detailOpen, setDetailOpen] = useState(false);
  const [detailItem, setDetailItem] = useState<any>(null);

  const [rejectOpen, setRejectOpen] = useState(false);
  const [rejectId, setRejectId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState('perfil_inadequado');
  const [rejectDetails, setRejectDetails] = useState('');

  const [proposalOpen, setProposalOpen] = useState(false);
  const [proposalId, setProposalId] = useState<string | null>(null);
  const [proposalData, setProposalData] = useState({ amount: '', benefits: '', notes: '' });

  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));

  const fetchApplications = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        skip: String((currentPage - 1) * PAGE_SIZE),
        limit: String(PAGE_SIZE),
        order_by: 'applied_at',
        order_desc: 'true',
      });
      if (statusFilter !== 'all') params.set('status', statusFilter);

      const res = await fetch(`${API_BASE}/?${params}`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      const data = await res.json();
      setApplications(data.items || []);
      setTotalItems(data.total || 0);
    } catch (err: any) {
      toast.error('Erro ao carregar candidaturas', { description: err.message, duration: 4000 });
      setApplications([]);
    } finally {
      setLoading(false);
    }
  }, [currentPage, statusFilter]);

  const fetchStats = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/stats`, { headers: getAuthHeaders() });
      if (res.ok) setStats(await res.json());
    } catch { /* silent */ }
  }, []);

  useEffect(() => { fetchApplications(); }, [fetchApplications]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  const handleCreate = async () => {
    if (!createData.job_position_id || !createData.candidate_id) {
      toast.error('ID da vaga e ID do candidato sao obrigatorios', { duration: 4000 });
      return;
    }
    setSaving(true);
    try {
      const body: any = {
        job_position_id: createData.job_position_id,
        candidate_id: createData.candidate_id,
        cover_letter: createData.cover_letter || null,
        salary_expectation: createData.salary_expectation ? Number(createData.salary_expectation) : null,
      };
      const res = await fetch(`${API_BASE}/`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Erro ${res.status}`);
      }
      toast.success('Candidatura criada com sucesso', { duration: 4000 });
      setCreateOpen(false);
      setCreateData({ job_position_id: '', candidate_id: '', cover_letter: '', salary_expectation: '' });
      fetchApplications();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao criar candidatura', { description: err.message, duration: 5000 });
    } finally {
      setSaving(false);
    }
  };

  const handleAdvance = async (id: string, currentStatus: string) => {
    const statusOrder = ['inscrito', 'triagem', 'entrevista_rh', 'entrevista_tecnica', 'entrevista_gestor', 'teste', 'referencias', 'proposta'];
    const idx = statusOrder.indexOf(currentStatus);
    const nextStatus = idx >= 0 && idx < statusOrder.length - 1 ? statusOrder[idx + 1] : null;
    if (!nextStatus) {
      toast.error('Candidatura ja esta na ultima etapa antes da contratacao', { duration: 4000 });
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/${id}/advance`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ new_status: nextStatus, notes: null }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Erro ${res.status}`);
      }
      toast.success(`Candidatura avancada para: ${statusConfig[nextStatus]?.label || nextStatus}`, { duration: 4000 });
      fetchApplications();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao avancar candidatura', { description: err.message, duration: 5000 });
    }
  };

  const handleReject = async () => {
    if (!rejectId) return;
    try {
      const res = await fetch(`${API_BASE}/${rejectId}/reject`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ reason: rejectReason, details: rejectDetails || null, send_notification: true }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Erro ${res.status}`);
      }
      toast.success('Candidatura rejeitada', { duration: 4000 });
      setRejectOpen(false);
      setRejectId(null);
      setRejectDetails('');
      fetchApplications();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao rejeitar candidatura', { description: err.message, duration: 5000 });
    }
  };

  const handleSendProposal = async () => {
    if (!proposalId || !proposalData.amount) {
      toast.error('Valor da proposta e obrigatorio', { duration: 4000 });
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/${proposalId}/proposal`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          amount: Number(proposalData.amount),
          benefits: proposalData.benefits ? proposalData.benefits.split(',').map(b => b.trim()) : [],
          notes: proposalData.notes || null,
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Erro ${res.status}`);
      }
      toast.success('Proposta enviada com sucesso', { duration: 4000 });
      setProposalOpen(false);
      setProposalId(null);
      setProposalData({ amount: '', benefits: '', notes: '' });
      fetchApplications();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao enviar proposta', { description: err.message, duration: 5000 });
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Tem certeza que deseja excluir esta candidatura?')) return;
    try {
      const res = await fetch(`${API_BASE}/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
      if (!res.ok && res.status !== 204) throw new Error(`Erro ${res.status}`);
      toast.success('Candidatura excluida', { duration: 4000 });
      fetchApplications();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao excluir candidatura', { description: err.message, duration: 5000 });
    }
  };

  const handleToggleFavorite = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/${id}/toggle-favorite`, { method: 'POST', headers: getAuthHeaders(), body: '{}' });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      toast.success('Favorito atualizado', { duration: 4000 });
      fetchApplications();
    } catch (err: any) {
      toast.error('Erro ao atualizar favorito', { description: err.message, duration: 5000 });
    }
  };

  // Client-side filter for search (search by displayed fields)
  const filtered = searchTerm
    ? applications.filter((a: any) =>
        a.candidate_id?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        a.job_position_id?.toLowerCase().includes(searchTerm.toLowerCase()) ||
        a.status?.toLowerCase().includes(searchTerm.toLowerCase())
      )
    : applications;

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <FileText className="h-6 w-6" />
            Candidaturas
          </h1>
          <p className="text-muted-foreground">Acompanhe candidaturas e etapas do processo seletivo</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { fetchApplications(); fetchStats(); }} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${loading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4 mr-2" />
            Nova Candidatura
          </Button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total</p>
            <p className="font-data text-2xl font-semibold tabular-nums">{stats?.total_applications ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Em Andamento</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-cyan-600">{stats?.active_applications ?? stats?.in_process ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Contratados</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats?.hired ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Rejeitados</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-red-600">{stats?.rejected ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Taxa Conversao</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-purple-600">{stats?.conversion_rate ? `${(stats.conversion_rate * 100).toFixed(1)}%` : '0%'}</p>
          </CardContent>
        </Card>
      </div>

      {/* Search & Filters */}
      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Buscar por ID da vaga ou candidato..."
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setCurrentPage(1); }}>
          <SelectTrigger className="w-[200px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os status</SelectItem>
            {Object.entries(statusConfig).map(([value, { label }]) => (
              <SelectItem key={value} value={value}>{label}</SelectItem>
            ))}
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
                    <div className="h-4 w-56 bg-muted rounded animate-pulse" />
                    <div className="h-3 w-40 bg-muted rounded animate-pulse" />
                  </div>
                  <div className="h-6 w-24 bg-muted rounded animate-pulse" />
                </div>
              ))}
            </div>
          ) : filtered.length === 0 ? (
            <div className="text-center py-12">
              <FileText className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium">Nenhum registro encontrado</h3>
              <p className="text-muted-foreground mt-1">
                {searchTerm || statusFilter !== 'all' ? 'Tente ajustar os filtros' : 'Ainda nao existem candidaturas registradas'}
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID Candidato</TableHead>
                  <TableHead>ID Vaga</TableHead>
                  <TableHead>Etapa</TableHead>
                  <TableHead>Score</TableHead>
                  <TableHead>Data Inscricao</TableHead>
                  <TableHead>Última Atualização</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filtered.map((app: any) => {
                  const st = statusConfig[app.status] ?? { label: app.status || 'Inscrito', color: 'bg-blue-500/20 text-blue-500 border-blue-500/30' };
                  const isActive = !terminalStatuses.includes(app.status);

                  return (
                    <TableRow key={app.id} className="cursor-pointer" onClick={() => { setDetailItem(app); setDetailOpen(true); }}>
                      <TableCell>
                        <p className="font-mono text-xs">{app.candidate_id?.substring(0, 8) || '-'}...</p>
                      </TableCell>
                      <TableCell>
                        <p className="font-mono text-xs">{app.job_position_id?.substring(0, 8) || '-'}...</p>
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={st.color}>
                          {st.label}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {app.ai_match_score != null ? (
                          <span className="text-sm font-medium">{Number(app.ai_match_score).toFixed(0)}%</span>
                        ) : app.rating != null ? (
                          <span className="text-sm font-medium">{app.rating}</span>
                        ) : (
                          <span className="text-sm text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-muted-foreground">
                          {app.applied_at || app.created_at ? new Date(app.applied_at || app.created_at).toLocaleDateString('pt-BR') : '-'}
                        </span>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-muted-foreground">
                          {app.updated_at ? new Date(app.updated_at).toLocaleDateString('pt-BR') : '-'}
                        </span>
                      </TableCell>
                      <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                        {isActive ? (
                          <div className="flex items-center justify-end gap-1">
                            <Button variant="ghost" size="sm" title="Favoritar" onClick={() => handleToggleFavorite(app.id)}>
                              <Star className={`h-4 w-4 ${app.is_favorite ? 'text-yellow-500 fill-yellow-500' : 'text-gray-400'}`} />
                            </Button>
                            <Button variant="ghost" size="sm" title="Avancar etapa" onClick={() => handleAdvance(app.id, app.status)}>
                              <ChevronRightIcon className="h-4 w-4 text-green-600" />
                            </Button>
                            {['referencias', 'teste', 'entrevista_gestor'].includes(app.status) && (
                              <Button variant="ghost" size="sm" title="Enviar proposta" onClick={() => { setProposalId(app.id); setProposalOpen(true); }}>
                                <Send className="h-4 w-4 text-blue-600" />
                              </Button>
                            )}
                            <Button variant="ghost" size="sm" title="Rejeitar" onClick={() => { setRejectId(app.id); setRejectOpen(true); }}
                              className="text-red-500 hover:text-red-600 hover:bg-red-500/10">
                              <XCircle className="h-4 w-4" />
                            </Button>
                          </div>
                        ) : (
                          <span className="text-xs text-muted-foreground">Finalizada</span>
                        )}
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
            Mostrando {((currentPage - 1) * PAGE_SIZE) + 1} a {Math.min(currentPage * PAGE_SIZE, totalItems)} de {totalItems} candidaturas
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

      {/* Create Dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Nova Candidatura</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>ID da Vaga *</Label>
              <Input value={createData.job_position_id} onChange={(e) => setCreateData({ ...createData, job_position_id: e.target.value })} placeholder="UUID da vaga" />
            </div>
            <div className="space-y-2">
              <Label>ID do Candidato *</Label>
              <Input value={createData.candidate_id} onChange={(e) => setCreateData({ ...createData, candidate_id: e.target.value })} placeholder="UUID do candidato" />
            </div>
            <div className="space-y-2">
              <Label>Carta de Apresentacao</Label>
              <Input value={createData.cover_letter} onChange={(e) => setCreateData({ ...createData, cover_letter: e.target.value })} placeholder="Opcional" />
            </div>
            <div className="space-y-2">
              <Label>Pretensao Salarial (R$)</Label>
              <Input type="number" min={0} value={createData.salary_expectation} onChange={(e) => setCreateData({ ...createData, salary_expectation: e.target.value })} placeholder="Opcional" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)}>Cancelar</Button>
            <Button onClick={handleCreate} disabled={!createData.job_position_id || !createData.candidate_id || saving}>
              {saving ? 'Criando...' : 'Criar Candidatura'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reject Dialog */}
      <Dialog open={rejectOpen} onOpenChange={setRejectOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Rejeitar Candidatura</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Motivo *</Label>
              <Select value={rejectReason} onValueChange={setRejectReason} aria-label="Reject Reason">
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="perfil_inadequado">Perfil inadequado</SelectItem>
                  <SelectItem value="experiencia_insuficiente">Experiencia insuficiente</SelectItem>
                  <SelectItem value="pretensao_incompativel">Pretensao incompativel</SelectItem>
                  <SelectItem value="desempenho_entrevista">Desempenho em entrevista</SelectItem>
                  <SelectItem value="documentacao_irregular">Documentacao irregular</SelectItem>
                  <SelectItem value="outros">Outros</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Detalhes</Label>
              <Input value={rejectDetails} onChange={(e) => setRejectDetails(e.target.value)} placeholder="Detalhes adicionais (opcional)" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRejectOpen(false)}>Cancelar</Button>
            <Button variant="destructive" onClick={handleReject}>Rejeitar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Proposal Dialog */}
      <Dialog open={proposalOpen} onOpenChange={setProposalOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Enviar Proposta</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Valor da Proposta (R$) *</Label>
              <Input type="number" min={1} value={proposalData.amount} onChange={(e) => setProposalData({ ...proposalData, amount: e.target.value })} placeholder="Ex: 2500" />
            </div>
            <div className="space-y-2">
              <Label>Benefícios (separados por vírgula)</Label>
              <Input value={proposalData.benefits} onChange={(e) => setProposalData({ ...proposalData, benefits: e.target.value })} placeholder="VT, VR, Plano de Saúde" />
            </div>
            <div className="space-y-2">
              <Label>Observações</Label>
              <Input value={proposalData.notes} onChange={(e) => setProposalData({ ...proposalData, notes: e.target.value })} placeholder="Notas adicionais" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setProposalOpen(false)}>Cancelar</Button>
            <Button onClick={handleSendProposal} disabled={!proposalData.amount}>Enviar Proposta</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Detalhes da Candidatura</DialogTitle>
          </DialogHeader>
          {detailItem && (
            <div className="space-y-3 py-2 text-sm">
              <div><span className="font-medium">ID:</span> <span className="font-mono text-xs">{detailItem.id}</span></div>
              <div><span className="font-medium">Status:</span> <Badge variant="outline" className={statusConfig[detailItem.status]?.color}>{statusConfig[detailItem.status]?.label || detailItem.status}</Badge></div>
              <div><span className="font-medium">Etapa Atual:</span> {detailItem.current_step || detailItem.status || '-'}</div>
              <div><span className="font-medium">ID Vaga:</span> <span className="font-mono text-xs">{detailItem.job_position_id}</span></div>
              <div><span className="font-medium">ID Candidato:</span> <span className="font-mono text-xs">{detailItem.candidate_id}</span></div>
              {detailItem.ai_match_score != null && <div><span className="font-medium">Score IA:</span> {Number(detailItem.ai_match_score).toFixed(1)}%</div>}
              {detailItem.rating != null && <div><span className="font-medium">Rating:</span> {detailItem.rating}</div>}
              {detailItem.salary_expectation && <div><span className="font-medium">Pretensao:</span> R$ {Number(detailItem.salary_expectation).toLocaleString('pt-BR')}</div>}
              {detailItem.cover_letter && <div><span className="font-medium">Carta:</span><p className="mt-1 text-muted-foreground">{detailItem.cover_letter}</p></div>}
              {detailItem.recruiter_notes && <div><span className="font-medium">Notas do Recrutador:</span><p className="mt-1 text-muted-foreground">{detailItem.recruiter_notes}</p></div>}
              {detailItem.rejection_reason && <div><span className="font-medium">Motivo Rejeicao:</span> {detailItem.rejection_reason}</div>}
              <div><span className="font-medium">Inscrito em:</span> {detailItem.applied_at ? new Date(detailItem.applied_at).toLocaleString('pt-BR') : detailItem.created_at ? new Date(detailItem.created_at).toLocaleString('pt-BR') : '-'}</div>
              <div><span className="font-medium">Atualizado em:</span> {detailItem.updated_at ? new Date(detailItem.updated_at).toLocaleString('pt-BR') : '-'}</div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
