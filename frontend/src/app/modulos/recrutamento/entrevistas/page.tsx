'use client';

import { useState, useEffect, useCallback } from 'react';
import { Calendar, Plus, Search, RefreshCw, AlertCircle, Clock, CheckCircle, XCircle, Star, CalendarClock, Video, MapPin, Phone as PhoneIcon, Edit2, Trash2, Play, ChevronLeft, ChevronRight } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
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

const API_BASE = '/api/v1/recruitment/interviews';
const PAGE_SIZE = 15;

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const statusConfig: Record<string, { label: string; color: string }> = {
  agendada: { label: 'Agendada', color: 'bg-blue-500/20 text-blue-500 border-blue-500/30' },
  confirmada: { label: 'Confirmada', color: 'bg-cyan-500/20 text-cyan-500 border-cyan-500/30' },
  em_andamento: { label: 'Em Andamento', color: 'bg-purple-500/20 text-purple-500 border-purple-500/30' },
  realizada: { label: 'Realizada', color: 'bg-green-500/20 text-green-500 border-green-500/30' },
  cancelada: { label: 'Cancelada', color: 'bg-red-500/20 text-red-500 border-red-500/30' },
  reagendada: { label: 'Reagendada', color: 'bg-yellow-500/20 text-yellow-500 border-yellow-500/30' },
  no_show: { label: 'Ausente', color: 'bg-orange-500/20 text-orange-500 border-orange-500/30' },
  adiada: { label: 'Adiada', color: 'bg-gray-500/20 text-gray-500 border-gray-500/30' },
};

const typeConfig: Record<string, { label: string; icon: any }> = {
  telefone: { label: 'Telefone', icon: PhoneIcon },
  video: { label: 'Video', icon: Video },
  presencial: { label: 'Presencial', icon: MapPin },
  tecnica: { label: 'Tecnica', icon: CheckCircle },
  comportamental: { label: 'Comportamental', icon: Star },
  case: { label: 'Case', icon: AlertCircle },
  painel: { label: 'Painel', icon: Calendar },
  dinamica: { label: 'Dinamica', icon: Play },
};

const emptyForm = {
  application_id: '',
  interview_type: 'video',
  format: 'video',
  scheduled_date: '',
  scheduled_time: '',
  duration_minutes: 60,
  location: '',
  meeting_url: '',
};

export default function EntrevistasPage() {
  const [interviews, setInterviews] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalItems, setTotalItems] = useState(0);
  const [currentPage, setCurrentPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState('all');
  const [stats, setStats] = useState<any>(null);

  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [formData, setFormData] = useState({ ...emptyForm });

  const [detailOpen, setDetailOpen] = useState(false);
  const [detailItem, setDetailItem] = useState<any>(null);

  const [cancelOpen, setCancelOpen] = useState(false);
  const [cancelId, setCancelId] = useState<string | null>(null);
  const [cancelReason, setCancelReason] = useState('');

  const [completeOpen, setCompleteOpen] = useState(false);
  const [completeId, setCompleteId] = useState<string | null>(null);
  const [completeData, setCompleteData] = useState({ result: 'aprovado', score: '', feedback: '' });

  const [rescheduleOpen, setRescheduleOpen] = useState(false);
  const [rescheduleId, setRescheduleId] = useState<string | null>(null);
  const [rescheduleData, setRescheduleData] = useState({ new_date: '', new_time: '', reason: '' });

  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));

  const fetchInterviews = useCallback(async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        skip: String((currentPage - 1) * PAGE_SIZE),
        limit: String(PAGE_SIZE),
        order_by: 'scheduled_date',
        order_desc: 'true',
      });
      if (statusFilter !== 'all') params.set('status', statusFilter);

      const res = await fetch(`${API_BASE}/?${params}`, { headers: getAuthHeaders() });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      const data = await res.json();
      setInterviews(data.items || []);
      setTotalItems(data.total || 0);
    } catch (err: any) {
      toast.error('Erro ao carregar entrevistas', { description: err.message, duration: 4000 });
      setInterviews([]);
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

  useEffect(() => { fetchInterviews(); }, [fetchInterviews]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  const openCreate = () => {
    setEditingId(null);
    setFormData({ ...emptyForm });
    setDialogOpen(true);
  };

  const openEdit = (item: any) => {
    setEditingId(item.id);
    setFormData({
      application_id: item.application_id || '',
      interview_type: item.interview_type || 'video',
      format: item.format || 'video',
      scheduled_date: item.scheduled_date || '',
      scheduled_time: item.scheduled_time ? String(item.scheduled_time).substring(0, 5) : '',
      duration_minutes: item.duration_minutes || 60,
      location: item.location || '',
      meeting_url: item.meeting_url || '',
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!formData.application_id || !formData.scheduled_date || !formData.scheduled_time) {
      toast.error('Candidatura, data e hora sao obrigatorios', { duration: 4000 });
      return;
    }
    setSaving(true);
    try {
      const body: any = {
        application_id: formData.application_id,
        interview_type: formData.interview_type,
        format: formData.format,
        scheduled_date: formData.scheduled_date,
        scheduled_time: formData.scheduled_time + ':00',
        duration_minutes: Number(formData.duration_minutes) || 60,
        location: formData.location || null,
        meeting_url: formData.meeting_url || null,
      };

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
      toast.success(editingId ? 'Entrevista atualizada com sucesso' : 'Entrevista agendada com sucesso', { duration: 4000 });
      setDialogOpen(false);
      fetchInterviews();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao salvar entrevista', { description: err.message, duration: 5000 });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Tem certeza que deseja excluir esta entrevista?')) return;
    try {
      const res = await fetch(`${API_BASE}/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
      if (!res.ok && res.status !== 204) throw new Error(`Erro ${res.status}`);
      toast.success('Entrevista excluida com sucesso', { duration: 4000 });
      fetchInterviews();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao excluir entrevista', { description: err.message, duration: 5000 });
    }
  };

  const handleCancel = async () => {
    if (!cancelId || cancelReason.length < 5) {
      toast.error('Motivo do cancelamento e obrigatorio (min 5 caracteres)', { duration: 4000 });
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/${cancelId}/cancel`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ reason: cancelReason }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Erro ${res.status}`);
      }
      toast.success('Entrevista cancelada', { duration: 4000 });
      setCancelOpen(false);
      setCancelReason('');
      setCancelId(null);
      fetchInterviews();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao cancelar entrevista', { description: err.message, duration: 5000 });
    }
  };

  const handleComplete = async () => {
    if (!completeId) return;
    try {
      const body: any = {
        result: completeData.result,
        score: completeData.score ? Number(completeData.score) : null,
        feedback: completeData.feedback || null,
      };
      const res = await fetch(`${API_BASE}/${completeId}/complete`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Erro ${res.status}`);
      }
      toast.success('Entrevista concluida', { duration: 4000 });
      setCompleteOpen(false);
      setCompleteId(null);
      setCompleteData({ result: 'aprovado', score: '', feedback: '' });
      fetchInterviews();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao concluir entrevista', { description: err.message, duration: 5000 });
    }
  };

  const handleReschedule = async () => {
    if (!rescheduleId || !rescheduleData.new_date || !rescheduleData.new_time) {
      toast.error('Data e hora sao obrigatorios para reagendar', { duration: 4000 });
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/${rescheduleId}/reschedule`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({
          new_date: rescheduleData.new_date,
          new_time: rescheduleData.new_time + ':00',
          reason: rescheduleData.reason || null,
        }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Erro ${res.status}`);
      }
      toast.success('Entrevista reagendada com sucesso', { duration: 4000 });
      setRescheduleOpen(false);
      setRescheduleId(null);
      setRescheduleData({ new_date: '', new_time: '', reason: '' });
      fetchInterviews();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao reagendar entrevista', { description: err.message, duration: 5000 });
    }
  };

  const handleStart = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/${id}/start`, { method: 'POST', headers: getAuthHeaders(), body: '{}' });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      toast.success('Entrevista iniciada', { duration: 4000 });
      fetchInterviews();
    } catch (err: any) {
      toast.error('Erro ao iniciar entrevista', { description: err.message, duration: 5000 });
    }
  };

  const handleNoShow = async (id: string) => {
    try {
      const res = await fetch(`${API_BASE}/${id}/no-show`, { method: 'POST', headers: getAuthHeaders(), body: '{}' });
      if (!res.ok) throw new Error(`Erro ${res.status}`);
      toast.success('Marcado como ausente', { duration: 4000 });
      fetchInterviews();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao marcar ausencia', { description: err.message, duration: 5000 });
    }
  };

  const formatScheduledDate = (item: any) => {
    if (item.scheduled_date) {
      const date = new Date(item.scheduled_date + 'T00:00:00');
      const dateStr = date.toLocaleDateString('pt-BR');
      const timeStr = item.scheduled_time ? String(item.scheduled_time).substring(0, 5) : '';
      return { date: dateStr, time: timeStr };
    }
    if (item.scheduled_at) {
      const dt = new Date(item.scheduled_at);
      return { date: dt.toLocaleDateString('pt-BR'), time: dt.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) };
    }
    return { date: '-', time: '' };
  };

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Calendar className="h-6 w-6" />
            Entrevistas
          </h1>
          <p className="text-muted-foreground">Agenda de entrevistas e avaliacoes de candidatos</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { fetchInterviews(); fetchStats(); }} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Agendar Entrevista
          </Button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total</p>
            <p className="font-data text-2xl font-semibold tabular-nums">{stats?.total_interviews ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Agendadas</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-blue-600">{stats?.scheduled ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Realizadas</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats?.completed ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Canceladas</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-red-600">{stats?.cancelled ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Ausentes</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-orange-600">{stats?.no_show ?? 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* Filter */}
      <div className="flex flex-col sm:flex-row gap-3">
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
          ) : interviews.length === 0 ? (
            <div className="text-center py-12">
              <Calendar className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium">Nenhum registro encontrado</h3>
              <p className="text-muted-foreground mt-1">
                {statusFilter !== 'all' ? 'Tente ajustar o filtro' : 'Agende sua primeira entrevista'}
              </p>
              {statusFilter === 'all' && (
                <Button className="mt-4" onClick={openCreate}>
                  <Plus className="h-4 w-4 mr-2" />
                  Agendar Entrevista
                </Button>
              )}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>ID Candidatura</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Data / Hora</TableHead>
                  <TableHead>Duracao</TableHead>
                  <TableHead>Local / Link</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Resultado</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {interviews.map((interview: any) => {
                  const st = statusConfig[interview.status] ?? { label: interview.status || 'Agendada', color: 'bg-blue-500/20 text-blue-500 border-blue-500/30' };
                  const tp = typeConfig[interview.interview_type] ?? { label: interview.interview_type || 'Video', icon: Video };
                  const TypeIcon = tp.icon;
                  const { date, time } = formatScheduledDate(interview);
                  const isScheduled = ['agendada', 'confirmada'].includes(interview.status);
                  const isInProgress = interview.status === 'em_andamento';

                  return (
                    <TableRow key={interview.id} className="cursor-pointer" onClick={() => { setDetailItem(interview); setDetailOpen(true); }}>
                      <TableCell>
                        <p className="font-mono text-xs">{interview.application_id?.substring(0, 8) || '-'}...</p>
                      </TableCell>
                      <TableCell>
                        <div className="flex items-center gap-1">
                          <TypeIcon className="h-4 w-4 text-muted-foreground" />
                          <span className="text-sm">{tp.label}</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <div>
                          <p className="text-sm font-medium">{date}</p>
                          {time && <p className="text-xs text-muted-foreground">{time}</p>}
                        </div>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm">{interview.duration_minutes ?? 60} min</span>
                      </TableCell>
                      <TableCell>
                        {interview.meeting_url ? (
                          <a href={interview.meeting_url} target="_blank" rel="noopener noreferrer" className="text-xs text-blue-600 underline truncate max-w-[150px] block" onClick={(e) => e.stopPropagation()}>
                            Link da reuniao
                          </a>
                        ) : interview.location ? (
                          <span className="text-sm truncate max-w-[150px] block">{interview.location}</span>
                        ) : (
                          <span className="text-sm text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={st.color}>
                          {st.label}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {interview.result ? (
                          <span className={`text-sm font-medium ${interview.result === 'aprovado' ? 'text-green-600' : interview.result === 'reprovado' ? 'text-red-600' : 'text-yellow-600'}`}>
                            {interview.result === 'aprovado' ? 'Aprovado' : interview.result === 'reprovado' ? 'Reprovado' : interview.result === 'aprovado_com_ressalvas' ? 'Com Ressalvas' : 'Pendente'}
                          </span>
                        ) : (
                          <span className="text-sm text-muted-foreground">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1">
                          {isScheduled && (
                            <>
                              <Button variant="ghost" size="sm" title="Iniciar" onClick={() => handleStart(interview.id)}>
                                <Play className="h-4 w-4 text-green-600" />
                              </Button>
                              <Button variant="ghost" size="sm" title="Reagendar" onClick={() => { setRescheduleId(interview.id); setRescheduleOpen(true); }}>
                                <CalendarClock className="h-4 w-4 text-blue-600" />
                              </Button>
                              <Button variant="ghost" size="sm" title="Ausente" onClick={() => handleNoShow(interview.id)}>
                                <AlertCircle className="h-4 w-4 text-orange-600" />
                              </Button>
                              <Button variant="ghost" size="sm" title="Cancelar" onClick={() => { setCancelId(interview.id); setCancelOpen(true); }}
                                className="text-red-500 hover:text-red-600 hover:bg-red-500/10">
                                <XCircle className="h-4 w-4" />
                              </Button>
                            </>
                          )}
                          {isInProgress && (
                            <Button variant="ghost" size="sm" title="Concluir" onClick={() => { setCompleteId(interview.id); setCompleteOpen(true); }}>
                              <CheckCircle className="h-4 w-4 text-green-600" />
                            </Button>
                          )}
                          <Button variant="ghost" size="sm" title="Editar" onClick={() => openEdit(interview)}>
                            <Edit2 className="h-4 w-4" />
                          </Button>
                          <Button variant="ghost" size="sm" title="Excluir" onClick={() => handleDelete(interview.id)}
                            className="text-red-500 hover:text-red-600 hover:bg-red-500/10">
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
            Mostrando {((currentPage - 1) * PAGE_SIZE) + 1} a {Math.min(currentPage * PAGE_SIZE, totalItems)} de {totalItems} entrevistas
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
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>{editingId ? 'Editar Entrevista' : 'Agendar Nova Entrevista'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>ID da Candidatura *</Label>
              <Input value={formData.application_id} onChange={(e) => setFormData({ ...formData, application_id: e.target.value })} placeholder="UUID da candidatura" disabled={!!editingId} />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Tipo</Label>
                <Select value={formData.interview_type} onValueChange={(v) => setFormData({ ...formData, interview_type: v, format: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(typeConfig).map(([value, { label }]) => (
                      <SelectItem key={value} value={value}>{label}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Duracao (min)</Label>
                <Input type="number" min={15} step={15} value={formData.duration_minutes} onChange={(e) => setFormData({ ...formData, duration_minutes: parseInt(e.target.value) || 60 })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Data *</Label>
                <Input type="date" value={formData.scheduled_date} onChange={(e) => setFormData({ ...formData, scheduled_date: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label>Hora *</Label>
                <Input type="time" value={formData.scheduled_time} onChange={(e) => setFormData({ ...formData, scheduled_time: e.target.value })} />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Local</Label>
              <Input value={formData.location} onChange={(e) => setFormData({ ...formData, location: e.target.value })} placeholder="Endereco ou sala" />
            </div>
            <div className="space-y-2">
              <Label>Link da Reuniao</Label>
              <Input value={formData.meeting_url} onChange={(e) => setFormData({ ...formData, meeting_url: e.target.value })} placeholder="https://meet.google.com/..." />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancelar</Button>
            <Button onClick={handleSave} disabled={!formData.application_id || !formData.scheduled_date || !formData.scheduled_time || saving}>
              {saving ? 'Salvando...' : editingId ? 'Salvar Alteracoes' : 'Agendar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Cancel Dialog */}
      <Dialog open={cancelOpen} onOpenChange={setCancelOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Cancelar Entrevista</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Motivo do Cancelamento *</Label>
              <Input value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder="Informe o motivo (minimo 5 caracteres)" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => { setCancelOpen(false); setCancelReason(''); }}>Voltar</Button>
            <Button variant="destructive" onClick={handleCancel} disabled={cancelReason.length < 5}>Cancelar Entrevista</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Complete Dialog */}
      <Dialog open={completeOpen} onOpenChange={setCompleteOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Concluir Entrevista</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label>Resultado *</Label>
              <Select value={completeData.result} onValueChange={(v) => setCompleteData({ ...completeData, result: v })}>
                <SelectTrigger><SelectValue /></SelectTrigger>
                <SelectContent>
                  <SelectItem value="aprovado">Aprovado</SelectItem>
                  <SelectItem value="reprovado">Reprovado</SelectItem>
                  <SelectItem value="aprovado_com_ressalvas">Aprovado com Ressalvas</SelectItem>
                  <SelectItem value="pendente_avaliacao">Pendente de Avaliacao</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>Nota (0-100)</Label>
              <Input type="number" min={0} max={100} value={completeData.score} onChange={(e) => setCompleteData({ ...completeData, score: e.target.value })} placeholder="Opcional" />
            </div>
            <div className="space-y-2">
              <Label>Feedback</Label>
              <Textarea value={completeData.feedback} onChange={(e) => setCompleteData({ ...completeData, feedback: e.target.value })} placeholder="Feedback sobre o candidato" rows={3} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCompleteOpen(false)}>Cancelar</Button>
            <Button onClick={handleComplete}>Concluir</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Reschedule Dialog */}
      <Dialog open={rescheduleOpen} onOpenChange={setRescheduleOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Reagendar Entrevista</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Nova Data *</Label>
                <Input type="date" value={rescheduleData.new_date} onChange={(e) => setRescheduleData({ ...rescheduleData, new_date: e.target.value })} />
              </div>
              <div className="space-y-2">
                <Label>Nova Hora *</Label>
                <Input type="time" value={rescheduleData.new_time} onChange={(e) => setRescheduleData({ ...rescheduleData, new_time: e.target.value })} />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Motivo</Label>
              <Input value={rescheduleData.reason} onChange={(e) => setRescheduleData({ ...rescheduleData, reason: e.target.value })} placeholder="Motivo do reagendamento (opcional)" />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRescheduleOpen(false)}>Cancelar</Button>
            <Button onClick={handleReschedule} disabled={!rescheduleData.new_date || !rescheduleData.new_time}>Reagendar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Detalhes da Entrevista</DialogTitle>
          </DialogHeader>
          {detailItem && (
            <div className="space-y-3 py-2 text-sm">
              <div><span className="font-medium">ID:</span> <span className="font-mono text-xs">{detailItem.id}</span></div>
              <div><span className="font-medium">Status:</span> <Badge variant="outline" className={statusConfig[detailItem.status]?.color}>{statusConfig[detailItem.status]?.label || detailItem.status}</Badge></div>
              <div><span className="font-medium">Tipo:</span> {typeConfig[detailItem.interview_type]?.label || detailItem.interview_type}</div>
              <div><span className="font-medium">ID Candidatura:</span> <span className="font-mono text-xs">{detailItem.application_id}</span></div>
              {(() => { const { date, time } = formatScheduledDate(detailItem); return <div><span className="font-medium">Data/Hora:</span> {date} {time}</div>; })()}
              <div><span className="font-medium">Duracao:</span> {detailItem.duration_minutes || 60} min</div>
              {detailItem.location && <div><span className="font-medium">Local:</span> {detailItem.location}</div>}
              {detailItem.meeting_url && <div><span className="font-medium">Link:</span> <a href={detailItem.meeting_url} target="_blank" rel="noopener noreferrer" className="text-blue-600 underline">{detailItem.meeting_url}</a></div>}
              {detailItem.result && <div><span className="font-medium">Resultado:</span> {detailItem.result}</div>}
              {detailItem.score != null && <div><span className="font-medium">Nota:</span> {detailItem.score}/100</div>}
              {detailItem.feedback && <div><span className="font-medium">Feedback:</span><p className="mt-1 text-muted-foreground">{detailItem.feedback}</p></div>}
              {detailItem.cancellation_reason && <div><span className="font-medium">Motivo Cancelamento:</span> {detailItem.cancellation_reason}</div>}
              <div><span className="font-medium">Criado em:</span> {detailItem.created_at ? new Date(detailItem.created_at).toLocaleString('pt-BR') : '-'}</div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
