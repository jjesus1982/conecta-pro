'use client';

import { useState, useEffect, useCallback } from 'react';
import { msgFromDetail } from '@/lib/string';
import { Briefcase, Plus, Search, RefreshCw, Edit2, Trash2, Globe, XCircle, AlertCircle, Pause, Play, Copy, ChevronLeft, ChevronRight } from 'lucide-react';
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

const API_BASE = '/api/v1/recruitment/job-positions';
const PAGE_SIZE = 15;

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const statusConfig: Record<string, { label: string; color: string }> = {
  draft: { label: 'Rascunho', color: 'bg-gray-500/20 text-gray-500 border-gray-500/30' },
  open: { label: 'Aberta', color: 'bg-green-500/20 text-green-500 border-green-500/30' },
  paused: { label: 'Pausada', color: 'bg-yellow-500/20 text-yellow-500 border-yellow-500/30' },
  closed: { label: 'Fechada', color: 'bg-red-500/20 text-red-500 border-red-500/30' },
  filled: { label: 'Preenchida', color: 'bg-blue-500/20 text-blue-500 border-blue-500/30' },
  cancelled: { label: 'Cancelada', color: 'bg-gray-500/20 text-gray-500 border-gray-500/30' },
};

const positionTypeLabels: Record<string, string> = {
  clt: 'CLT',
  pj: 'PJ',
  temporario: 'Temporario',
  estagio: 'Estagio',
  trainee: 'Trainee',
  freelancer: 'Freelancer',
  terceirizado: 'Terceirizado',
};

const departmentOptions = [
  'operacional', 'administrativo', 'financeiro', 'rh', 'comercial',
  'ti', 'logistica', 'juridico', 'marketing', 'diretoria',
];

const emptyForm = {
  title: '',
  description: '',
  position_type: 'clt',
  position_level: '',
  department: '',
  city: '',
  state: '',
  work_model: '',
  salary_min: '',
  salary_max: '',
  vacancies: 1,
  requirements: '',
  responsibilities: '',
  benefits: '',
};

export default function VagasPage() {
  const [positions, setPositions] = useState<any[]>([]);
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

  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));

  const fetchPositions = useCallback(async () => {
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
      setPositions(data.items || []);
      setTotalItems(data.total || 0);
    } catch (err: any) {
      toast.error('Erro ao carregar vagas', { description: err.message, duration: 4000 });
      setPositions([]);
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

  useEffect(() => { fetchPositions(); }, [fetchPositions]);
  useEffect(() => { fetchStats(); }, [fetchStats]);

  const openCreate = () => {
    setEditingId(null);
    setFormData({ ...emptyForm });
    setDialogOpen(true);
  };

  const openEdit = (item: any) => {
    setEditingId(item.id);
    setFormData({
      title: item.title || '',
      description: item.description || '',
      position_type: item.position_type || 'clt',
      position_level: item.position_level || '',
      department: item.department || '',
      city: item.city || '',
      state: item.state || '',
      work_model: item.work_model || '',
      salary_min: item.salary_min != null ? String(item.salary_min) : '',
      salary_max: item.salary_max != null ? String(item.salary_max) : '',
      vacancies: item.vacancies || 1,
      requirements: item.requirements || '',
      responsibilities: item.responsibilities || '',
      benefits: item.benefits || '',
    });
    setDialogOpen(true);
  };

  const handleSave = async () => {
    if (!formData.title.trim()) {
      toast.error('Titulo e obrigatorio', { duration: 4000 });
      return;
    }
    setSaving(true);
    try {
      const body: any = {
        ...formData,
        vacancies: Number(formData.vacancies) || 1,
        salary_min: formData.salary_min ? Number(formData.salary_min) : null,
        salary_max: formData.salary_max ? Number(formData.salary_max) : null,
      };
      // Remove empty strings
      Object.keys(body).forEach(k => { if (body[k] === '') body[k] = null; });

      const url = editingId ? `${API_BASE}/${editingId}` : `${API_BASE}/`;
      const method = editingId ? 'PUT' : 'POST';
      const res = await fetch(url, {
        method,
        headers: getAuthHeaders(),
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(msgFromDetail(errData.detail) || `Erro ${res.status}`);
      }
      toast.success(editingId ? 'Vaga atualizada com sucesso' : 'Vaga criada com sucesso', { duration: 4000 });
      setDialogOpen(false);
      fetchPositions();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao salvar vaga', { description: err.message, duration: 5000 });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm('Tem certeza que deseja excluir esta vaga?')) return;
    try {
      const res = await fetch(`${API_BASE}/${id}`, { method: 'DELETE', headers: getAuthHeaders() });
      if (!res.ok && res.status !== 204) throw new Error(`Erro ${res.status}`);
      toast.success('Vaga excluida com sucesso', { duration: 4000 });
      fetchPositions();
      fetchStats();
    } catch (err: any) {
      toast.error('Erro ao excluir vaga', { description: err.message, duration: 5000 });
    }
  };

  const handleAction = async (id: string, action: 'publish' | 'pause' | 'reopen' | 'close' | 'duplicate', label: string) => {
    try {
      const res = await fetch(`${API_BASE}/${id}/${action}`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({}),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(msgFromDetail(errData.detail) || `Erro ${res.status}`);
      }
      toast.success(`Vaga ${label} com sucesso`, { duration: 4000 });
      fetchPositions();
      fetchStats();
    } catch (err: any) {
      toast.error(`Erro ao ${label.toLowerCase()} vaga`, { description: err.message, duration: 5000 });
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
            <Briefcase className="h-6 w-6" />
            Vagas
          </h1>
          <p className="text-muted-foreground">Gerencie as vagas e posicoes abertas</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => { fetchPositions(); fetchStats(); }} disabled={loading}>
            <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          </Button>
          <Button onClick={openCreate}>
            <Plus className="h-4 w-4 mr-2" />
            Nova Vaga
          </Button>
        </div>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Total</p>
            <p className="font-data text-2xl font-semibold tabular-nums">{stats?.total_positions ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Abertas</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats?.open_positions ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Preenchidas</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-blue-600">{stats?.filled_positions ?? 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="pt-4">
            <p className="text-sm text-muted-foreground">Fechadas</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-red-600">{stats?.closed_positions ?? 0}</p>
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
            placeholder="Buscar vagas por titulo ou departamento..."
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setCurrentPage(1); }}>
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os status</SelectItem>
            <SelectItem value="draft">Rascunho</SelectItem>
            <SelectItem value="open">Aberta</SelectItem>
            <SelectItem value="paused">Pausada</SelectItem>
            <SelectItem value="closed">Fechada</SelectItem>
            <SelectItem value="filled">Preenchida</SelectItem>
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
          ) : positions.length === 0 ? (
            <div className="text-center py-12">
              <Briefcase className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
              <h3 className="text-lg font-medium">Nenhum registro encontrado</h3>
              <p className="text-muted-foreground mt-1">
                {searchTerm ? 'Tente ajustar a busca' : 'Crie sua primeira vaga'}
              </p>
              {!searchTerm && (
                <Button className="mt-4" onClick={openCreate}>
                  <Plus className="h-4 w-4 mr-2" />
                  Nova Vaga
                </Button>
              )}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Titulo</TableHead>
                  <TableHead>Departamento</TableHead>
                  <TableHead>Local</TableHead>
                  <TableHead>Contrato</TableHead>
                  <TableHead>Vagas</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Criado em</TableHead>
                  <TableHead className="text-right">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {positions.map((position: any) => {
                  const st = statusConfig[position.status] ?? { label: position.status || 'Rascunho', color: 'bg-gray-500/20 text-gray-500 border-gray-500/30' };
                  return (
                    <TableRow key={position.id} className="cursor-pointer" onClick={() => openDetail(position)}>
                      <TableCell>
                        <div>
                          <p className="font-medium">{position.title}</p>
                          {position.code && (
                            <p className="text-xs text-muted-foreground">{position.code}</p>
                          )}
                        </div>
                      </TableCell>
                      <TableCell>{position.department || '-'}</TableCell>
                      <TableCell>
                        {[position.city, position.state].filter(Boolean).join(', ') || '-'}
                      </TableCell>
                      <TableCell>
                        <span className="text-sm">{positionTypeLabels[position.position_type] || position.position_type || '-'}</span>
                      </TableCell>
                      <TableCell>
                        <span className="font-medium">{position.vacancies ?? '-'}</span>
                        {position.filled_count > 0 && (
                          <span className="text-xs text-muted-foreground ml-1">({position.filled_count} preenchida{position.filled_count > 1 ? 's' : ''})</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline" className={st.color}>
                          {st.label}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <span className="text-sm text-muted-foreground">
                          {position.created_at ? new Date(position.created_at).toLocaleDateString('pt-BR') : '-'}
                        </span>
                      </TableCell>
                      <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                        <div className="flex items-center justify-end gap-1">
                          <Button variant="ghost" size="sm" title="Editar" onClick={() => openEdit(position)}>
                            <Edit2 className="h-4 w-4" />
                          </Button>
                          {(position.status === 'draft') && (
                            <Button variant="ghost" size="sm" title="Publicar" onClick={() => handleAction(position.id, 'publish', 'publicada')}>
                              <Globe className="h-4 w-4 text-green-600" />
                            </Button>
                          )}
                          {(position.status === 'open') && (
                            <Button variant="ghost" size="sm" title="Pausar" onClick={() => handleAction(position.id, 'pause', 'pausada')}>
                              <Pause className="h-4 w-4 text-yellow-600" />
                            </Button>
                          )}
                          {(position.status === 'paused') && (
                            <Button variant="ghost" size="sm" title="Reabrir" onClick={() => handleAction(position.id, 'reopen', 'reaberta')}>
                              <Play className="h-4 w-4 text-green-600" />
                            </Button>
                          )}
                          {['open', 'paused'].includes(position.status) && (
                            <Button variant="ghost" size="sm" title="Fechar" onClick={() => handleAction(position.id, 'close', 'fechada')}>
                              <XCircle className="h-4 w-4 text-orange-600" />
                            </Button>
                          )}
                          <Button variant="ghost" size="sm" title="Duplicar" onClick={() => handleAction(position.id, 'duplicate', 'duplicada')}>
                            <Copy className="h-4 w-4 text-blue-600" />
                          </Button>
                          <Button
                            variant="ghost" size="sm" title="Excluir"
                            onClick={() => handleDelete(position.id)}
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
            Mostrando {((currentPage - 1) * PAGE_SIZE) + 1} a {Math.min(currentPage * PAGE_SIZE, totalItems)} de {totalItems} vagas
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
            <DialogTitle>{editingId ? 'Editar Vaga' : 'Criar Nova Vaga'}</DialogTitle>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="title">Titulo *</Label>
              <Input
                id="title"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                placeholder="Ex: Vigilante Patrimonial"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="description">Descricao</Label>
              <Textarea
                id="description"
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                placeholder="Descricao detalhada da vaga"
                rows={3}
              />
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Tipo de Contrato</Label>
                <Select value={formData.position_type} onValueChange={(v) => setFormData({ ...formData, position_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="clt">CLT</SelectItem>
                    <SelectItem value="pj">PJ</SelectItem>
                    <SelectItem value="temporario">Temporario</SelectItem>
                    <SelectItem value="estagio">Estagio</SelectItem>
                    <SelectItem value="trainee">Trainee</SelectItem>
                    <SelectItem value="freelancer">Freelancer</SelectItem>
                    <SelectItem value="terceirizado">Terceirizado</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Nivel</Label>
                <Select value={formData.position_level} onValueChange={(v) => setFormData({ ...formData, position_level: v })}>
                  <SelectTrigger><SelectValue placeholder="Selecione" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="estagiario">Estagiario</SelectItem>
                    <SelectItem value="junior">Junior</SelectItem>
                    <SelectItem value="pleno">Pleno</SelectItem>
                    <SelectItem value="senior">Senior</SelectItem>
                    <SelectItem value="especialista">Especialista</SelectItem>
                    <SelectItem value="coordenador">Coordenador</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Departamento</Label>
                <Select value={formData.department} onValueChange={(v) => setFormData({ ...formData, department: v })}>
                  <SelectTrigger><SelectValue placeholder="Selecione" /></SelectTrigger>
                  <SelectContent>
                    {departmentOptions.map(d => (
                      <SelectItem key={d} value={d}>{d.charAt(0).toUpperCase() + d.slice(1)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label>Modelo de Trabalho</Label>
                <Select value={formData.work_model} onValueChange={(v) => setFormData({ ...formData, work_model: v })}>
                  <SelectTrigger><SelectValue placeholder="Selecione" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="presencial">Presencial</SelectItem>
                    <SelectItem value="remoto">Remoto</SelectItem>
                    <SelectItem value="hibrido">Hibrido</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>
            <div className="grid grid-cols-3 gap-4">
              <div className="space-y-2">
                <Label>Cidade</Label>
                <Input value={formData.city} onChange={(e) => setFormData({ ...formData, city: e.target.value })} placeholder="Manaus" />
              </div>
              <div className="space-y-2">
                <Label>Estado</Label>
                <Input value={formData.state} onChange={(e) => setFormData({ ...formData, state: e.target.value })} placeholder="AM" maxLength={2} />
              </div>
              <div className="space-y-2">
                <Label>N. de Vagas</Label>
                <Input type="number" min={1} value={formData.vacancies} onChange={(e) => setFormData({ ...formData, vacancies: parseInt(e.target.value) || 1 })} />
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label>Salario Minimo (R$)</Label>
                <Input type="number" min={0} value={formData.salary_min} onChange={(e) => setFormData({ ...formData, salary_min: e.target.value })} placeholder="0.00" />
              </div>
              <div className="space-y-2">
                <Label>Salario Maximo (R$)</Label>
                <Input type="number" min={0} value={formData.salary_max} onChange={(e) => setFormData({ ...formData, salary_max: e.target.value })} placeholder="0.00" />
              </div>
            </div>
            <div className="space-y-2">
              <Label>Requisitos</Label>
              <Textarea value={formData.requirements} onChange={(e) => setFormData({ ...formData, requirements: e.target.value })} placeholder="Requisitos da vaga" rows={2} />
            </div>
            <div className="space-y-2">
              <Label>Responsabilidades</Label>
              <Textarea value={formData.responsibilities} onChange={(e) => setFormData({ ...formData, responsibilities: e.target.value })} placeholder="Responsabilidades da funcao" rows={2} />
            </div>
            <div className="space-y-2">
              <Label>Benefícios</Label>
              <Textarea value={formData.benefits} onChange={(e) => setFormData({ ...formData, benefits: e.target.value })} placeholder="Benefícios oferecidos" rows={2} />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDialogOpen(false)}>Cancelar</Button>
            <Button onClick={handleSave} disabled={!formData.title || saving}>
              {saving ? 'Salvando...' : editingId ? 'Salvar Alteracoes' : 'Criar Vaga'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Detail Dialog */}
      <Dialog open={detailOpen} onOpenChange={setDetailOpen}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>Detalhes da Vaga</DialogTitle>
          </DialogHeader>
          {detailItem && (
            <div className="space-y-3 py-2 text-sm">
              <div><span className="font-medium">Codigo:</span> {detailItem.code || '-'}</div>
              <div><span className="font-medium">Titulo:</span> {detailItem.title}</div>
              <div><span className="font-medium">Status:</span> <Badge variant="outline" className={statusConfig[detailItem.status]?.color}>{statusConfig[detailItem.status]?.label || detailItem.status}</Badge></div>
              <div><span className="font-medium">Tipo:</span> {positionTypeLabels[detailItem.position_type] || detailItem.position_type}</div>
              {detailItem.department && <div><span className="font-medium">Departamento:</span> {detailItem.department}</div>}
              {detailItem.position_level && <div><span className="font-medium">Nivel:</span> {detailItem.position_level}</div>}
              {detailItem.city && <div><span className="font-medium">Local:</span> {[detailItem.city, detailItem.state].filter(Boolean).join(', ')}</div>}
              {detailItem.work_model && <div><span className="font-medium">Modelo:</span> {detailItem.work_model}</div>}
              <div><span className="font-medium">Vagas:</span> {detailItem.vacancies} ({detailItem.filled_count || 0} preenchidas)</div>
              {(detailItem.salary_min || detailItem.salary_max) && (
                <div><span className="font-medium">Salario:</span> R$ {detailItem.salary_min || '0'} - R$ {detailItem.salary_max || '0'}</div>
              )}
              {detailItem.description && <div><span className="font-medium">Descricao:</span><p className="mt-1 text-muted-foreground whitespace-pre-line">{detailItem.description}</p></div>}
              {detailItem.requirements && <div><span className="font-medium">Requisitos:</span><p className="mt-1 text-muted-foreground whitespace-pre-line">{detailItem.requirements}</p></div>}
              {detailItem.responsibilities && <div><span className="font-medium">Responsabilidades:</span><p className="mt-1 text-muted-foreground whitespace-pre-line">{detailItem.responsibilities}</p></div>}
              <div><span className="font-medium">Criado em:</span> {detailItem.created_at ? new Date(detailItem.created_at).toLocaleString('pt-BR') : '-'}</div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
}
