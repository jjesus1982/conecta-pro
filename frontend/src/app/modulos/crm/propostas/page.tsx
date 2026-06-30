'use client';

import { FileText, Search, RefreshCw, Plus, MoreHorizontal, Eye, Edit, Trash2, AlertCircle, DollarSign, Clock, CheckCircle, XCircle, Send, ThumbsUp, FileDown } from 'lucide-react';
import { useState, useMemo } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ConfirmModal } from '@/components/ui/modal';
import { toast } from 'sonner';
import {
  useProposals, useProposalStats, useCreateProposal, useUpdateProposal, useDeleteProposal,
} from '@/hooks/crm';
import { formatCurrency, formatDate } from '@/lib/utils';

interface ItemForm { name: string; description: string; unit: string; quantity: number; unit_price: number; }

const emptyItem = (): ItemForm => ({ name: '', description: '', unit: 'un', quantity: 1, unit_price: 0 });

const emptyForm = () => ({
  title: '', proposal_type: 'product', client_name: '', client_document: '', client_company: '',
  client_phone: '', client_email: '', client_address: '', valid_until: '', payment_terms: '',
  installments: 1, billing_type: 'one_time', notes: '',
});

// Campo de moeda BRL estilo "caixa eletrônico": digita só números, formata 11.966,70 sozinho.
const brlInput = (n: number) => (n ? n.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '');
const parseBrlInput = (s: string) => { const d = (s || '').replace(/\D/g, ''); return d ? parseInt(d, 10) / 100 : 0; };
// Quantidade: aceita inteiro ou decimal (vírgula ou ponto), e permite apagar.
const qtyInput = (n: number) => (n ? String(n).replace('.', ',') : '');
const parseQty = (s: string) => { const v = (s || '').replace(/[^\d.,]/g, '').replace(',', '.'); return v ? (Number(v) || 0) : 0; };
const STAGE_LABEL: Record<string, string> = { qualification: 'Qualificação', needs_analysis: 'Análise', proposal: 'Proposta', negotiation: 'Negociação', closed_won: 'Ganho', closed_lost: 'Perdido' };

export default function PropostasPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: proposalsData, isLoading, error, refetch } = useProposals({
    status: statusFilter !== 'all' ? statusFilter : undefined,
    search: search || undefined, skip: page * pageSize, limit: pageSize,
  } as any);
  const { data: statsData } = useProposalStats();

  const queryClient = useQueryClient();
  const createMutation = useCreateProposal();
  const updateMutation = useUpdateProposal();
  const deleteMutation = useDeleteProposal();

  const approveMutation = useMutation({
    mutationFn: (id: string) => customInstance({ url: `/api/v1/crm/proposals/${id}/approve`, method: 'POST', data: { action: 'approve' } }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['proposals'] }); toast.success('Proposta aprovada'); },
    onError: () => toast.error('Erro ao aprovar'),
  });
  const rejectMutation = useMutation({
    mutationFn: ({ id, comments }: { id: string; comments?: string }) => customInstance({ url: `/api/v1/crm/proposals/${id}/approve`, method: 'POST', data: { action: 'reject', comments: comments || '' } }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['proposals'] }); toast.success('Proposta rejeitada'); },
    onError: () => toast.error('Erro ao rejeitar'),
  });
  const sendMutation = useMutation({
    mutationFn: (id: string) => customInstance({ url: `/api/v1/crm/proposals/${id}/send`, method: 'POST' }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['proposals'] }); toast.success('Proposta enviada'); },
    onError: () => toast.error('Erro ao enviar'),
  });
  const acceptMutation = useMutation({
    mutationFn: (id: string) => customInstance({ url: `/api/v1/crm/proposals/${id}/accept`, method: 'POST' }),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ['proposals'] }); toast.success('Proposta aceita'); },
    onError: () => toast.error('Erro ao aceitar'),
  });

  const [formOpen, setFormOpen] = useState(false);
  const [editItem, setEditItem] = useState<any | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedItem, setSelectedItem] = useState<any | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{ title: string; message: string; action: () => Promise<void>; variant: 'danger' | 'warning' | 'info'; } | null>(null);

  const [form, setForm] = useState(emptyForm());
  const [items, setItems] = useState<ItemForm[]>([emptyItem()]);
  const [editItemsLoaded, setEditItemsLoaded] = useState(false);
  const [vinculoOpp, setVinculoOpp] = useState('');

  // Deals (oportunidades) abertos — para vincular a proposta a um deal existente (ex.: do lead qualificado).
  const { data: oppsData } = useQuery({
    queryKey: ['open-opps-for-proposal'],
    queryFn: () => customInstance({ url: '/api/v1/crm/opportunities/?is_open=true&page_size=100', method: 'GET' }),
    staleTime: 30_000,
  });
  const deals = (oppsData as any)?.items || [];

  // Clientes cadastrados (para auto-preencher)
  const { data: clientsData } = useQuery({
    queryKey: ['clients-for-proposal'],
    queryFn: () => customInstance({ url: '/api/v1/crm/clients/', method: 'GET' }),
    staleTime: 120_000,
  });
  const clientes = (clientsData as any)?.items || (Array.isArray(clientsData) ? clientsData : []);
  const autofillCliente = (id: string) => {
    const c = clientes.find((x: any) => x.id === id);
    if (!c) return;
    setForm(f => ({
      ...f,
      client_name: c.name || c.trading_name || '',
      client_document: c.cnpj || c.document_number || '',
      client_email: c.email || '',
      client_phone: c.phone || c.mobile || '',
      client_address: c.endereco_texto || '',
    }));
    toast.success(`Cliente "${c.name}" carregado`);
  };

  // Modelos de proposta (templates) — pré-preenchem título/descrição/condições.
  const { data: templatesData } = useQuery({
    queryKey: ['proposal-templates'],
    queryFn: () => customInstance({ url: '/api/v1/crm/proposals/templates', method: 'GET' }),
    staleTime: 300_000,
  });
  const templates = (Array.isArray(templatesData) ? templatesData : (templatesData as any)?.items) || [];
  const aplicarTemplate = (id: string) => {
    const t = templates.find((x: any) => x.id === id);
    if (!t) return;
    setForm(f => ({
      ...f,
      title: t.default_title || f.title,
      proposal_type: t.proposal_type || f.proposal_type,
      payment_terms: t.payment_terms || f.payment_terms,
      notes: t.default_description || t.terms_conditions || f.notes,
    }));
    toast.success(`Modelo "${t.name}" aplicado`);
  };

  const propostas = (proposalsData as any)?.items || (Array.isArray(proposalsData) ? proposalsData : []);
  const total = (proposalsData as any)?.total || propostas.length;
  const pStats = statsData as any;
  const stats = {
    total: pStats?.proposals_total || total,
    rascunho: pStats?.proposals_pending || propostas.filter((p: any) => (p.status === 'draft')).length,
    enviadas: pStats?.proposals_sent || propostas.filter((p: any) => (p.status === 'sent')).length,
    aprovadas: pStats?.proposals_accepted || propostas.filter((p: any) => (p.status === 'accepted')).length,
  };

  const liveSubtotal = useMemo(
    () => items.reduce((s, it) => s + (Number(it.quantity) || 0) * (Number(it.unit_price) || 0), 0),
    [items],
  );

  const setItem = (i: number, patch: Partial<ItemForm>) =>
    setItems(prev => prev.map((it, idx) => (idx === i ? { ...it, ...patch } : it)));
  const addItem = () => setItems(prev => [...prev, emptyItem()]);
  const removeItem = (i: number) => setItems(prev => prev.length > 1 ? prev.filter((_, idx) => idx !== i) : prev);

  const resetForm = () => { setForm(emptyForm()); setItems([emptyItem()]); setVinculoOpp(''); };

  const openCreate = () => { setEditItem(null); resetForm(); setFormOpen(true); };
  const openEdit = async (p: any) => {
    setEditItem(p);
    setEditItemsLoaded(false);
    setForm({
      title: p.title || '', proposal_type: p.proposal_type || 'product', client_name: p.client_name || '',
      client_document: p.client_document || '', client_company: p.client_company || '', client_phone: p.client_phone || '',
      client_email: p.client_email || '', client_address: p.client_address || '', valid_until: p.valid_until || '',
      payment_terms: p.payment_terms || '', installments: p.installments || 1, billing_type: p.billing_type || 'one_time', notes: p.notes || '',
    });
    setItems([emptyItem()]);
    setFormOpen(true);
    // Busca os ITENS REAIS (a listagem só traz a contagem). Flag de segurança evita apagar itens por erro de load.
    try {
      const full: any = await customInstance({ url: `/api/v1/crm/proposals/${p.id}`, method: 'GET' });
      const its = full?.items || [];
      if (its.length) setItems(its.map((it: any) => ({ name: it.name || '', description: it.description || '', unit: it.unit || 'un', quantity: it.quantity || 0, unit_price: it.unit_price || 0 })));
      setEditItemsLoaded(true);
    } catch {
      toast.error('Não consegui carregar os itens — edição de itens desabilitada nesta proposta');
      setEditItemsLoaded(false);
    }
  };

  const buildPayload = () => {
    const validItems = items.filter(it => it.name.trim()).map((it, idx) => ({
      name: it.name.trim(), description: it.description.trim() || null, unit: it.unit || 'un',
      quantity: Number(it.quantity) || 0, unit_price: Number(it.unit_price) || 0, sort_order: idx,
    }));
    return {
      title: form.title.trim(), proposal_type: form.proposal_type, client_name: form.client_name.trim(),
      client_document: form.client_document.trim() || null, client_company: form.client_company.trim() || null,
      client_phone: form.client_phone.trim() || null, client_email: form.client_email.trim() || null,
      client_address: form.client_address.trim() || null, valid_until: form.valid_until || null,
      payment_terms: form.payment_terms.trim() || null, installments: Number(form.installments) || 1,
      billing_type: form.billing_type, notes: form.notes.trim() || null, items: validItems,
      opportunity_id: vinculoOpp || null,
    };
  };

  const handleSave = async () => {
    if (!form.title.trim()) return toast.error('Informe o título da proposta');
    if (!form.client_name.trim()) return toast.error('Informe o cliente');
    const validItems = items.filter(it => it.name.trim());
    if (!editItem && validItems.length === 0) return toast.error('Adicione pelo menos 1 item');
    try {
      if (editItem) {
        const payload = buildPayload();
        const { items: novosItens, ...header } = payload;
        await updateMutation.mutateAsync({ proposalId: editItem.id, data: header as any });
        // Só substitui itens se foram carregados com segurança (evita apagar por erro de load).
        if (editItemsLoaded) {
          await customInstance({ url: `/api/v1/crm/proposals/${editItem.id}/items`, method: 'PUT', data: novosItens });
        }
      } else {
        await createMutation.mutateAsync({ data: buildPayload() as any });
      }
      resetForm(); setEditItem(null); setFormOpen(false);
      toast.success(editItem ? 'Proposta atualizada' : 'Proposta criada');
    } catch (e: any) {
      toast.error('Erro ao salvar: ' + (e?.response?.data?.detail || e?.message || 'verifique os campos'));
    }
  };

  const openConfirm = (title: string, message: string, action: () => Promise<void>, variant: 'danger' | 'warning' | 'info' = 'warning') => {
    setConfirmAction({ title, message, action, variant }); setConfirmOpen(true);
  };

  const [pdfLoading, setPdfLoading] = useState<string | null>(null);
  const gerarPdf = async (p: any) => {
    setPdfLoading(p.id);
    try {
      const blob = await customInstance<Blob>({ url: `/api/v1/crm/proposals/${p.id}/pdf`, method: 'GET', responseType: 'blob' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `orcamento_${(p.number || p.id).replace(/\//g, '-')}.pdf`;
      document.body.appendChild(a); a.click(); a.remove();
      window.open(url, '_blank');
      setTimeout(() => window.URL.revokeObjectURL(url), 15000);
      toast.success('PDF gerado');
    } catch {
      toast.error('Erro ao gerar PDF');
    } finally {
      setPdfLoading(null);
    }
  };

  const getStatusBadge = (status: string) => {
    const map: Record<string, string> = { draft: 'bg-gray-100 text-gray-800', pending_approval: 'bg-yellow-100 text-yellow-800', approved: 'bg-emerald-100 text-emerald-800', sent: 'bg-blue-100 text-blue-800', accepted: 'bg-green-100 text-green-800', rejected: 'bg-red-100 text-red-800' };
    const labels: Record<string, string> = { draft: 'Rascunho', pending_approval: 'Aguardando Aprovação', approved: 'Aprovada', sent: 'Enviada', accepted: 'Aceita', rejected: 'Rejeitada' };
    return <Badge className={map[status] || 'bg-gray-100 text-gray-800'}>{labels[status] || status}</Badge>;
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><FileText className="h-6 w-6" />Propostas</h1>
          <p className="text-muted-foreground">Orçamentos com itens, cálculo automático e cliente</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}><RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />Atualizar</Button>
          <Button onClick={openCreate}><Plus className="h-4 w-4 mr-2" />Nova Proposta</Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        {[['Total', stats.total, 'text-foreground', FileText], ['Rascunho', stats.rascunho, 'text-gray-600', Clock], ['Enviadas', stats.enviadas, 'text-blue-600', FileText], ['Aprovadas', stats.aprovadas, 'text-green-600', DollarSign]].map(([label, val, color, Icon]: any, i) => (
          <Card key={i}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{label}</CardTitle><Icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent><div className={`text-2xl font-bold ${color}`}>{val}</div></CardContent>
          </Card>
        ))}
      </div>

      <Card><CardContent className="pt-6"><div className="flex flex-col md:flex-row gap-4">
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={search} onChange={(e) => { setSearch(e.target.value); setPage(0); }} placeholder="Buscar por título, cliente..." className="pl-10" />
        </div>
        <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(0); }}>
          <SelectTrigger className="w-[180px]"><SelectValue placeholder="Status" /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os status</SelectItem><SelectItem value="draft">Rascunho</SelectItem>
            <SelectItem value="pending_approval">Aguardando Aprovação</SelectItem><SelectItem value="approved">Aprovada</SelectItem>
            <SelectItem value="sent">Enviada</SelectItem><SelectItem value="accepted">Aceita</SelectItem><SelectItem value="rejected">Rejeitada</SelectItem>
          </SelectContent>
        </Select>
      </div></CardContent></Card>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" /><p className="text-sm text-destructive flex-1">Erro ao carregar propostas</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>Tentar novamente</Button>
        </div>
      )}

      {/* Builder */}
      {formOpen && (
        <Card>
          <CardHeader><CardTitle className="text-lg">{editItem ? 'Editar Proposta' : 'Nova Proposta (Orçamento)'}</CardTitle></CardHeader>
          <CardContent className="space-y-6">
            {/* Modelo de proposta (pré-preenche o formulário) */}
            {!editItem && templates.length > 0 && (
              <div className="grid gap-1.5">
                <label className="text-sm font-medium">Começar a partir de um modelo (opcional)</label>
                <Select value="none" onValueChange={(v) => v !== 'none' && aplicarTemplate(v)}>
                  <SelectTrigger><SelectValue placeholder="Escolher um modelo…" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">— Em branco —</SelectItem>
                    {templates.map((t: any) => (
                      <SelectItem key={t.id} value={t.id}>{t.name} · {t.validity_days}d</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">Preenche título, condições de pagamento e observações. Você ajusta os itens normalmente.</p>
              </div>
            )}
            {/* Cabeçalho */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="grid gap-1.5"><label className="text-sm font-medium">Título *</label>
                <Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Ex: Cerca Elétrica — Laranjeiras Village" /></div>
              <div className="grid gap-1.5"><label className="text-sm font-medium">Tipo</label>
                <Select value={form.proposal_type} onValueChange={(v) => setForm({ ...form, proposal_type: v })}>
                  <SelectTrigger><SelectValue /></SelectTrigger>
                  <SelectContent><SelectItem value="product">Produto</SelectItem><SelectItem value="service">Serviço</SelectItem><SelectItem value="project">Projeto</SelectItem><SelectItem value="subscription">Assinatura</SelectItem></SelectContent>
                </Select></div>
            </div>

            {/* Vincular a deal existente (unifica lead -> proposta num só deal) */}
            {!editItem && deals.length > 0 && (
              <div className="grid gap-1.5">
                <label className="text-sm font-medium">Vincular a uma oportunidade existente (opcional)</label>
                <Select value={vinculoOpp || 'none'} onValueChange={(v) => setVinculoOpp(v === 'none' ? '' : v)}>
                  <SelectTrigger><SelectValue placeholder="Criar um novo deal" /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">— Criar um novo deal —</SelectItem>
                    {deals.map((o: any) => (
                      <SelectItem key={o.id} value={o.id}>{(o.company_name || o.title)} · {STAGE_LABEL[o.stage] || o.stage} · {formatCurrency(o.value)}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">Vincule ao deal do lead qualificado para ter <b>um único deal</b> que avança no Kanban (em vez de criar outro).</p>
              </div>
            )}

            {/* Cliente */}
            <div className="border rounded-lg p-4 space-y-3">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-2">
                <p className="text-sm font-semibold text-muted-foreground">DADOS DO CLIENTE</p>
                {!editItem && clientes.length > 0 && (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-muted-foreground">Cliente cadastrado:</span>
                    <Select onValueChange={autofillCliente}>
                      <SelectTrigger className="w-[260px] h-8 text-sm"><SelectValue placeholder="Selecionar para preencher..." /></SelectTrigger>
                      <SelectContent>
                        {clientes.map((c: any) => (<SelectItem key={c.id} value={c.id}>{c.name}{c.cnpj ? ` — ${c.cnpj}` : ''}</SelectItem>))}
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </div>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div className="grid gap-1.5"><label className="text-sm font-medium">Cliente *</label>
                  <Input value={form.client_name} onChange={(e) => setForm({ ...form, client_name: e.target.value })} placeholder="Razão social / nome" /></div>
                <div className="grid gap-1.5"><label className="text-sm font-medium">CNPJ/CPF</label>
                  <Input value={form.client_document} onChange={(e) => setForm({ ...form, client_document: e.target.value })} placeholder="00.000.000/0000-00" /></div>
                <div className="grid gap-1.5"><label className="text-sm font-medium">Contato</label>
                  <Input value={form.client_company} onChange={(e) => setForm({ ...form, client_company: e.target.value })} placeholder="Nome do contato (síndico/administrador)" /></div>
                <div className="grid gap-1.5"><label className="text-sm font-medium">Telefone</label>
                  <Input value={form.client_phone} onChange={(e) => setForm({ ...form, client_phone: e.target.value })} placeholder="(92) 9....." /></div>
                <div className="grid gap-1.5"><label className="text-sm font-medium">E-mail</label>
                  <Input type="email" value={form.client_email} onChange={(e) => setForm({ ...form, client_email: e.target.value })} placeholder="email@cliente.com" /></div>
                <div className="grid gap-1.5"><label className="text-sm font-medium">Endereço</label>
                  <Input value={form.client_address} onChange={(e) => setForm({ ...form, client_address: e.target.value })} placeholder="Endereço do cliente" /></div>
              </div>
            </div>

            {/* Itens */}
            <div className="border rounded-lg p-4 space-y-3">
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-muted-foreground">ITENS DO ORÇAMENTO</p>
                {editItem && !editItemsLoaded && <span className="text-xs text-amber-600">Carregando itens... (ou proposta fechada — itens não editáveis)</span>}
              </div>
              <div className="hidden md:grid grid-cols-12 gap-2 text-xs font-medium text-muted-foreground px-1">
                <div className="col-span-4">Descrição</div><div className="col-span-2">Marca/Modelo</div><div className="col-span-1">Un</div>
                <div className="col-span-1">Qtd</div><div className="col-span-2">Valor Unit.</div><div className="col-span-1 text-right">Total</div><div className="col-span-1" />
              </div>
              {items.map((it, i) => (
                <div key={i} className="grid grid-cols-12 gap-2 items-center">
                  <Input className="col-span-12 md:col-span-4" disabled={!!editItem && !editItemsLoaded} value={it.name} onChange={(e) => setItem(i, { name: e.target.value })} placeholder="Descrição do item" />
                  <Input className="col-span-6 md:col-span-2" disabled={!!editItem && !editItemsLoaded} value={it.description} onChange={(e) => setItem(i, { description: e.target.value })} placeholder="Marca/Modelo" />
                  <Input className="col-span-2 md:col-span-1" disabled={!!editItem && !editItemsLoaded} value={it.unit} onChange={(e) => setItem(i, { unit: e.target.value })} placeholder="un" />
                  <Input className="col-span-2 md:col-span-1" disabled={!!editItem && !editItemsLoaded} inputMode="decimal" value={qtyInput(it.quantity)} onChange={(e) => setItem(i, { quantity: parseQty(e.target.value) })} placeholder="1" />
                  <Input className="col-span-4 md:col-span-2 text-right" disabled={!!editItem && !editItemsLoaded} inputMode="numeric" value={brlInput(it.unit_price)} onChange={(e) => setItem(i, { unit_price: parseBrlInput(e.target.value) })} placeholder="0,00" />
                  <div className="col-span-6 md:col-span-1 text-right text-sm font-medium">{formatCurrency((Number(it.quantity) || 0) * (Number(it.unit_price) || 0))}</div>
                  <div className="col-span-6 md:col-span-1 flex justify-end">
                    {(!editItem || editItemsLoaded) && <Button variant="ghost" size="icon" className="h-8 w-8 text-destructive" onClick={() => removeItem(i)}><Trash2 className="h-4 w-4" /></Button>}
                  </div>
                </div>
              ))}
              {(!editItem || editItemsLoaded) && <Button variant="outline" size="sm" onClick={addItem}><Plus className="h-4 w-4 mr-1" />Adicionar item</Button>}
              <div className="flex justify-end pt-2 border-t">
                <div className="text-right"><span className="text-sm text-muted-foreground mr-3">VALOR TOTAL</span>
                  <span className="text-2xl font-bold text-green-600">{formatCurrency(liveSubtotal)}</span></div>
              </div>
            </div>

            {/* Condições */}
            <div className="border rounded-lg p-4 space-y-3">
              <p className="text-sm font-semibold text-muted-foreground">CONDIÇÕES</p>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="grid gap-1.5"><label className="text-sm font-medium">Cobrança</label>
                  <Select value={form.billing_type} onValueChange={(v) => setForm({ ...form, billing_type: v })}>
                    <SelectTrigger><SelectValue /></SelectTrigger>
                    <SelectContent><SelectItem value="one_time">Pagamento único</SelectItem><SelectItem value="recurring">Recorrente (mensal)</SelectItem></SelectContent>
                  </Select></div>
                <div className="grid gap-1.5"><label className="text-sm font-medium">Parcelas</label>
                  <Input type="number" min={1} value={form.installments} onChange={(e) => setForm({ ...form, installments: Number(e.target.value) })} /></div>
                <div className="grid gap-1.5"><label className="text-sm font-medium">Válida até</label>
                  <Input type="date" value={form.valid_until} onChange={(e) => setForm({ ...form, valid_until: e.target.value })} /></div>
              </div>
              <div className="grid gap-1.5"><label className="text-sm font-medium">Condições de pagamento</label>
                <Input value={form.payment_terms} onChange={(e) => setForm({ ...form, payment_terms: e.target.value })} placeholder="Ex: 50% de entrada + saldo em 2x (PIX/boleto)" /></div>
              <div className="grid gap-1.5"><label className="text-sm font-medium">Observações</label>
                <textarea className="w-full border rounded-lg p-2 text-sm h-20" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Garantia, exclusões, etc." /></div>
            </div>

            <div className="flex justify-end gap-2">
              <Button variant="outline" onClick={() => { setFormOpen(false); setEditItem(null); resetForm(); }}>Cancelar</Button>
              <Button onClick={handleSave} disabled={createMutation.isPending || updateMutation.isPending}>
                {(createMutation.isPending || updateMutation.isPending) && <RefreshCw className="h-4 w-4 mr-2 animate-spin" />}
                {editItem ? 'Salvar alterações' : 'Criar Proposta'}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Table */}
      <Card><CardContent className="p-0">
        {isLoading ? (
          <div className="flex items-center justify-center py-12"><div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" /></div>
        ) : propostas.length === 0 ? (
          <div className="text-center py-12 text-muted-foreground">
            <FileText className="h-16 w-16 mx-auto mb-4 opacity-50" /><h3 className="text-lg font-medium">Nenhuma proposta encontrada</h3>
            <p className="mt-2">Crie uma nova proposta para começar</p>
            <Button className="mt-4" onClick={openCreate}><Plus className="h-4 w-4 mr-2" />Nova Proposta</Button>
          </div>
        ) : (
          <Table>
            <TableHeader><TableRow>
              <TableHead>Título</TableHead><TableHead>Cliente</TableHead><TableHead>Itens</TableHead><TableHead>Valor</TableHead><TableHead>Status</TableHead><TableHead>Data</TableHead><TableHead className="w-[80px]">Ações</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {propostas.map((p: any) => (
                <TableRow key={p.id}>
                  <TableCell><div className="font-medium">{p.title || '-'}</div><div className="text-xs text-muted-foreground">{p.number}</div></TableCell>
                  <TableCell className="text-sm text-muted-foreground">{p.client_name || '-'}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{p.item_count ?? (p.items?.length ?? 0)}</TableCell>
                  <TableCell className="text-sm font-medium">{formatCurrency(p.total ?? 0)}</TableCell>
                  <TableCell>{getStatusBadge(p.status)}</TableCell>
                  <TableCell className="text-sm text-muted-foreground">{formatDate(p.created_at)}</TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild><Button variant="ghost" size="icon" className="h-8 w-8"><MoreHorizontal className="h-4 w-4" /></Button></DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => { setSelectedItem(p); setDetailOpen(true); }}><Eye className="h-4 w-4 mr-2" />Ver detalhes</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => gerarPdf(p)} disabled={pdfLoading === p.id}><FileDown className="h-4 w-4 mr-2" />Gerar PDF</DropdownMenuItem>
                        <DropdownMenuItem onClick={() => openEdit(p)}><Edit className="h-4 w-4 mr-2" />Editar</DropdownMenuItem>
                        <DropdownMenuSeparator />
                        {p.status === 'pending_approval' && (<>
                          <DropdownMenuItem className="text-green-600" onClick={() => approveMutation.mutate(p.id)}><CheckCircle className="h-4 w-4 mr-2" />Aprovar</DropdownMenuItem>
                          <DropdownMenuItem className="text-red-600" onClick={() => openConfirm('Rejeitar Proposta', `Rejeitar "${p.title}"?`, async () => { await rejectMutation.mutateAsync({ id: p.id }); }, 'warning')}><XCircle className="h-4 w-4 mr-2" />Rejeitar</DropdownMenuItem>
                          <DropdownMenuSeparator /></>)}
                        {p.status === 'approved' && (<><DropdownMenuItem className="text-blue-600" onClick={() => sendMutation.mutate(p.id)}><Send className="h-4 w-4 mr-2" />Enviar ao Cliente</DropdownMenuItem><DropdownMenuSeparator /></>)}
                        {p.status === 'sent' && (<><DropdownMenuItem className="text-green-600" onClick={() => acceptMutation.mutate(p.id)}><ThumbsUp className="h-4 w-4 mr-2" />Aceitar</DropdownMenuItem><DropdownMenuSeparator /></>)}
                        <DropdownMenuItem className="text-destructive" onClick={() => openConfirm('Deletar Proposta', `Deletar "${p.title}" permanentemente?`, () => deleteMutation.mutateAsync({ proposalId: p.id }), 'danger')}><Trash2 className="h-4 w-4 mr-2" />Deletar</DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent></Card>

      {total > pageSize && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">Mostrando {page * pageSize + 1}-{Math.min((page + 1) * pageSize, total)} de {total}</p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}>Anterior</Button>
            <Button variant="outline" size="sm" onClick={() => setPage(page + 1)} disabled={(page + 1) * pageSize >= total}>Próximo</Button>
          </div>
        </div>
      )}

      {/* Detalhe */}
      {detailOpen && selectedItem && (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle className="text-lg">Proposta {selectedItem.number}</CardTitle>
            <div className="flex gap-2">
              <Button size="sm" onClick={() => gerarPdf(selectedItem)} disabled={pdfLoading === selectedItem.id}>
                <FileDown className="h-4 w-4 mr-2" />{pdfLoading === selectedItem.id ? 'Gerando...' : 'Gerar PDF'}
              </Button>
              <Button variant="outline" size="sm" onClick={() => { setDetailOpen(false); setSelectedItem(null); }}>Fechar</Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-sm">
              <div><p className="text-muted-foreground">Título</p><p className="font-medium">{selectedItem.title || '-'}</p></div>
              <div><p className="text-muted-foreground">Cliente</p><p className="font-medium">{selectedItem.client_name || '-'}</p></div>
              <div><p className="text-muted-foreground">CNPJ/CPF</p><p className="font-medium">{selectedItem.client_document || '-'}</p></div>
              <div><p className="text-muted-foreground">Contato</p><p className="font-medium">{selectedItem.client_company || '-'}</p></div>
              <div><p className="text-muted-foreground">Status</p>{getStatusBadge(selectedItem.status)}</div>
              <div><p className="text-muted-foreground">Válida até</p><p className="font-medium">{selectedItem.valid_until ? formatDate(selectedItem.valid_until) : '-'}</p></div>
            </div>
            {selectedItem.items?.length > 0 && (
              <div className="border rounded-lg overflow-hidden">
                <Table>
                  <TableHeader><TableRow><TableHead>Item</TableHead><TableHead>Marca/Modelo</TableHead><TableHead className="text-right">Qtd</TableHead><TableHead className="text-right">Unit.</TableHead><TableHead className="text-right">Total</TableHead></TableRow></TableHeader>
                  <TableBody>
                    {selectedItem.items.map((it: any, i: number) => (
                      <TableRow key={i}><TableCell>{it.name}</TableCell><TableCell className="text-muted-foreground">{it.description || '-'}</TableCell><TableCell className="text-right">{it.quantity} {it.unit}</TableCell><TableCell className="text-right">{formatCurrency(it.unit_price)}</TableCell><TableCell className="text-right font-medium">{formatCurrency(it.total ?? 0)}</TableCell></TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
            <div className="flex justify-end gap-6 text-sm">
              <div className="text-right"><p className="text-muted-foreground">Subtotal</p><p className="font-medium">{formatCurrency(selectedItem.subtotal ?? 0)}</p></div>
              <div className="text-right"><p className="text-muted-foreground">TOTAL</p><p className="text-xl font-bold text-green-600">{formatCurrency(selectedItem.total ?? 0)}</p></div>
            </div>
            {selectedItem.payment_terms && <div className="text-sm"><p className="text-muted-foreground">Pagamento</p><p>{selectedItem.payment_terms}</p></div>}
            {selectedItem.notes && <div className="text-sm"><p className="text-muted-foreground">Observações</p><p className="whitespace-pre-wrap">{selectedItem.notes}</p></div>}
          </CardContent>
        </Card>
      )}

      {confirmAction && (
        <ConfirmModal isOpen={confirmOpen} onClose={() => setConfirmOpen(false)} onConfirm={async () => { await confirmAction.action(); setConfirmOpen(false); }} title={confirmAction.title} message={confirmAction.message} variant={confirmAction.variant} isLoading={deleteMutation.isPending} />
      )}
    </div>
  );
}
