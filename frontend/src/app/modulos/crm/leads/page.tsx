'use client';

import { Plus, Search, Filter, MoreHorizontal, Phone, Mail, User, Building2, TrendingUp, RefreshCw, AlertCircle, X, Pencil, CheckCircle2, XCircle } from 'lucide-react';
import { useState, useEffect } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent } from '@/components/ui/card';
import { useLeads, useLeadsStats, useCreateLead, useUpdateLead } from '@/hooks/useLeads';
import { cn, formatCurrency, formatDate } from '@/lib/utils';
import { LEAD_STATUS_LABELS, LEAD_SOURCE_LABELS, leadStatusConfig } from '@/constants/crm/leadStatus';
import { CnpjSearchButton } from '@/components/crm/CnpjSearchButton';
import type { CNPJEnrichment } from '@/types/crm/enrichment';

export default function LeadsPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined);
  const [showNovoLead, setShowNovoLead] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [novoLeadForm, setNovoLeadForm] = useState({ cnpj: '', nome: '', contato: '', email: '', telefone: '', source: 'other', expected_value: '' });
  const [savingLead, setSavingLead] = useState(false);
  const [openMenuId, setOpenMenuId] = useState<string | null>(null);
  const createLead = useCreateLead();
  const updateLead = useUpdateLead();

  // Fecha o menu de ações ao clicar fora
  useEffect(() => {
    if (!openMenuId) return;
    const close = () => setOpenMenuId(null);
    window.addEventListener('click', close);
    return () => window.removeEventListener('click', close);
  }, [openMenuId]);

  const resetForm = () => {
    setNovoLeadForm({ cnpj: '', nome: '', contato: '', email: '', telefone: '', source: 'other', expected_value: '' });
    setEditingId(null);
  };

  const abrirEdicao = (lead: Record<string, unknown>) => {
    setEditingId(String(lead.id));
    setNovoLeadForm({
      cnpj: '',
      nome: String(lead.name || lead.nome || ''),
      contato: String(lead.company || lead.contact_name || lead.contato || ''),
      email: String(lead.email || ''),
      telefone: String(lead.phone || lead.telefone || ''),
      source: String(lead.source || 'other'),
      expected_value: lead.expected_value != null ? String(lead.expected_value) : '',
    });
    setShowNovoLead(true);
  };

  const mudarStatus = async (id: string, status: string, label: string) => {
    setOpenMenuId(null);
    try {
      await updateLead.mutateAsync({ id, data: { status } });
      toast.success(`Lead marcado como "${label}"`);
      refetch();
    } catch (err) {
      toast.error('Não foi possível alterar o status. Tente novamente.');
    }
  };

  // Buscar leads do backend real
  const {
    data: leadsData,
    isLoading,
    isError,
    error,
    refetch,
  } = useLeads({
    search: search || undefined,
    status: statusFilter,
  });

  // Buscar estatísticas do backend real
  const { data: stats } = useLeadsStats();

  const leads = leadsData?.items || [];
  const total = leadsData?.total || 0;

  // Métricas (do stats ou calculadas)
  const statsAny = stats as Record<string, number> | undefined;
  const totalLeads = statsAny?.total || total;
  const leadsNovos = statsAny?.novos || leads.filter(l => l.status === 'new' || l.status === 'novo').length;
  const valorTotal = statsAny?.total_expected_value ?? statsAny?.valor_pipeline ?? leads.reduce((acc, lead) => acc + (lead.expected_value || lead.valor_estimado || 0), 0);

  return (
    <div className="space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-[hsl(var(--foreground))]">Leads</h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))]">
            Gerencie seus leads e oportunidades de negócio
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => refetch()}
            disabled={isLoading}
          >
            <RefreshCw className={cn('w-4 h-4', isLoading && 'animate-spin')} />
          </Button>
          <Button aria-label="Novo Lead" onClick={() => setShowNovoLead(true)}>
            <Plus className="w-4 h-4 mr-2" />
            Novo Lead
          </Button>
        </div>
      </div>

      {/* Modal Novo Lead */}
      {showNovoLead && (
        <Card className="border-primary/40">
          <CardContent className="pt-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-semibold text-lg">{editingId ? 'Editar Lead' : 'Novo Lead'}</h3>
              <Button variant="ghost" size="sm" onClick={() => { setShowNovoLead(false); resetForm(); }} aria-label="Fechar">
                <X className="w-4 h-4" />
              </Button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="sm:col-span-2">
                <label htmlFor="lead-cnpj" className="text-sm font-medium mb-1 block">CNPJ</label>
                <div className="flex gap-2">
                  <input
                    id="lead-cnpj"
                    name="cnpj"
                    type="text"
                    placeholder="00.000.000/0000-00"
                    aria-label="CNPJ"
                    value={novoLeadForm.cnpj}
                    onChange={e => setNovoLeadForm(p => ({ ...p, cnpj: e.target.value }))}
                    className="flex-1 px-3 py-2 border rounded-md text-sm"
                  />
                  <CnpjSearchButton
                    cnpj={novoLeadForm.cnpj}
                    onSuccess={(data: CNPJEnrichment) => {
                      setNovoLeadForm(p => ({
                        ...p,
                        nome: data.razao_social ?? p.nome,
                        contato: data.razao_social ?? p.contato,
                        telefone: data.telefone ?? p.telefone,
                      }));
                      toast.success('Dados preenchidos via Receita Federal');
                    }}
                    onError={(msg: string) => toast.error(msg)}
                  />
                </div>
              </div>
              <div>
                <label htmlFor="lead-nome" className="text-sm font-medium mb-1 block">Nome *</label>
                <input
                  id="lead-nome"
                  name="nome"
                  type="text"
                  placeholder="Nome do lead"
                  aria-label="Nome"
                  value={novoLeadForm.nome}
                  onChange={e => setNovoLeadForm(p => ({ ...p, nome: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label htmlFor="lead-contato" className="text-sm font-medium mb-1 block">Empresa / Contato *</label>
                <input
                  id="lead-contato"
                  name="contato"
                  type="text"
                  placeholder="Empresa ou contato"
                  aria-label="Empresa"
                  value={novoLeadForm.contato}
                  onChange={e => setNovoLeadForm(p => ({ ...p, contato: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label htmlFor="lead-email" className="text-sm font-medium mb-1 block">E-mail</label>
                <input
                  id="lead-email"
                  name="email"
                  type="email"
                  placeholder="email@empresa.com"
                  aria-label="Email"
                  value={novoLeadForm.email}
                  onChange={e => setNovoLeadForm(p => ({ ...p, email: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label htmlFor="lead-telefone" className="text-sm font-medium mb-1 block">Telefone</label>
                <input
                  id="lead-telefone"
                  name="telefone"
                  type="tel"
                  placeholder="(92) 99999-9999"
                  aria-label="Telefone"
                  value={novoLeadForm.telefone}
                  onChange={e => setNovoLeadForm(p => ({ ...p, telefone: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
              <div>
                <label htmlFor="lead-source" className="text-sm font-medium mb-1 block">Origem</label>
                <select
                  id="lead-source"
                  name="source"
                  aria-label="Origem"
                  value={novoLeadForm.source}
                  onChange={e => setNovoLeadForm(p => ({ ...p, source: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm bg-transparent"
                >
                  <option value="website">Website</option>
                  <option value="referral">Indicação</option>
                  <option value="social_media">Redes sociais</option>
                  <option value="cold_call">Ligação fria</option>
                  <option value="email_campaign">Campanha de e-mail</option>
                  <option value="event">Evento</option>
                  <option value="partner">Parceiro</option>
                  <option value="whatsapp">WhatsApp</option>
                  <option value="other">Outros</option>
                </select>
              </div>
              <div>
                <label htmlFor="lead-valor" className="text-sm font-medium mb-1 block">Valor estimado (R$)</label>
                <input
                  id="lead-valor"
                  name="expected_value"
                  type="number"
                  min="0"
                  step="0.01"
                  placeholder="0,00"
                  aria-label="Valor estimado"
                  value={novoLeadForm.expected_value}
                  onChange={e => setNovoLeadForm(p => ({ ...p, expected_value: e.target.value }))}
                  className="w-full px-3 py-2 border rounded-md text-sm"
                />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button
                disabled={savingLead || !novoLeadForm.nome.trim()}
                onClick={async () => {
                  setSavingLead(true);
                  // Mapeia chaves PT do form -> schema EN do backend (name/company/phone)
                  const payload = {
                    name: novoLeadForm.nome.trim(),
                    company: novoLeadForm.contato.trim() || undefined,
                    email: novoLeadForm.email.trim() || undefined,
                    phone: novoLeadForm.telefone.trim() || undefined,
                    source: novoLeadForm.source || 'other',
                    expected_value: novoLeadForm.expected_value
                      ? Number(novoLeadForm.expected_value)
                      : 0,
                  };
                  try {
                    if (editingId) {
                      await updateLead.mutateAsync({ id: editingId, data: payload });
                      toast.success('Lead atualizado com sucesso');
                    } else {
                      await createLead.mutateAsync(payload);
                      toast.success('Lead criado com sucesso');
                    }
                    setShowNovoLead(false);
                    resetForm();
                    refetch();
                  } catch (err) {
                    const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
                    const msg = Array.isArray(detail)
                      ? 'Verifique os campos obrigatórios e tente novamente.'
                      : (typeof detail === 'string' ? detail : 'Não foi possível salvar o lead. Tente novamente.');
                    toast.error(msg);
                  } finally {
                    setSavingLead(false);
                  }
                }}
              >
                {savingLead ? 'Salvando...' : (editingId ? 'Salvar alterações' : 'Criar Lead')}
              </Button>
              <Button variant="secondary" onClick={() => { setShowNovoLead(false); resetForm(); }}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Métricas */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-[hsl(var(--muted-foreground))]">Total de Leads</p>
                <p className="text-2xl font-bold text-[hsl(var(--foreground))]">
                  {isLoading ? '...' : totalLeads}
                </p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-navy-500/10 flex items-center justify-center">
                <User className="w-5 h-5 text-navy-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-[hsl(var(--muted-foreground))]">Leads Novos</p>
                <p className="text-2xl font-bold text-[hsl(var(--foreground))]">
                  {isLoading ? '...' : leadsNovos}
                </p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-brand-500/10 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-brand-400" />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardContent className="pt-4">
            <div className="flex items-center justify-between">
              <div>
                <p className="text-sm text-[hsl(var(--muted-foreground))]">Valor Estimado</p>
                <p className="text-2xl font-bold text-[hsl(var(--foreground))]">
                  {isLoading ? '...' : formatCurrency(valorTotal)}
                </p>
              </div>
              <div className="w-10 h-10 rounded-lg bg-emerald-500/10 flex items-center justify-center">
                <Building2 className="w-5 h-5 text-emerald-400" />
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filtros */}
      <div className="flex flex-col sm:flex-row gap-4">
        <div className="flex-1">
          <Input
            type="search"
            placeholder="Buscar leads..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            icon={<Search className="w-4 h-4" />}
          />
        </div>
        <div className="flex gap-2 flex-wrap">
          <Button
            variant={statusFilter === undefined ? 'primary' : 'secondary'}
            size="sm"
            onClick={() => setStatusFilter(undefined)}
          >
            Todos
          </Button>
          {Object.entries(LEAD_STATUS_LABELS).filter(([k]) => ['new','contacted','qualified','won'].includes(k)).map(([key, config]) => (
            <Button
              key={key}
              variant={statusFilter === key ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => setStatusFilter(key)}
              className="hidden sm:inline-flex"
            >
              {config.label}
            </Button>
          ))}
          <Button variant="secondary" size="sm" className="sm:hidden">
            <Filter className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {/* Erro */}
      {isError && (
        <div className="flex items-center gap-3 p-4 rounded-lg bg-[hsl(var(--destructive))]/10 border border-[hsl(var(--destructive))]/30">
          <AlertCircle className="w-5 h-5 text-[hsl(var(--destructive))]" />
          <div>
            <p className="font-medium text-[hsl(var(--destructive))]">Erro ao carregar leads</p>
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              {(error as Error)?.message || 'Tente novamente em alguns instantes'}
            </p>
          </div>
          <Button variant="secondary" size="sm" onClick={() => refetch()} className="ml-auto">
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Lista de leads */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            // Skeleton loading
            <div className="divide-y divide-[hsl(var(--border))]">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="p-4 flex items-center gap-4">
                  <div className="flex-1 space-y-2">
                    <div className="h-4 w-48 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                    <div className="h-3 w-32 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                  </div>
                  <div className="h-6 w-20 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                  <div className="h-4 w-24 bg-[hsl(var(--secondary))] rounded animate-shimmer" />
                </div>
              ))}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))]">
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Lead
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))] hidden md:table-cell">
                      Contato
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))] hidden lg:table-cell">
                      Origem
                    </th>
                    <th className="text-left p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Status
                    </th>
                    <th className="text-right p-4 text-sm font-medium text-[hsl(var(--muted-foreground))]">
                      Valor
                    </th>
                    <th className="w-12 p-4"></th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[hsl(var(--border))]">
                  {leads.map((lead) => {
                    const status = leadStatusConfig(lead.status);
                    return (
                      <tr
                        key={lead.id}
                        className="hover:bg-[hsl(var(--secondary))]/50 transition-colors cursor-pointer"
                        onClick={() => abrirEdicao(lead as unknown as Record<string, unknown>)}
                      >
                        <td className="p-4">
                          <div>
                            <p className="font-medium text-[hsl(var(--foreground))]">
                              {lead.name || lead.nome || '—'}
                            </p>
                            <p className="text-sm text-[hsl(var(--muted-foreground))]">
                              {lead.contact_name || lead.contato || lead.company || ''}
                            </p>
                          </div>
                        </td>
                        <td className="p-4 hidden md:table-cell">
                          <div className="space-y-1">
                            {lead.telefone && (
                              <div className="flex items-center gap-2 text-sm text-[hsl(var(--muted-foreground))]">
                                <Phone className="w-3 h-3" />
                                {lead.telefone}
                              </div>
                            )}
                            {lead.email && (
                              <div className="flex items-center gap-2 text-sm text-[hsl(var(--muted-foreground))]">
                                <Mail className="w-3 h-3" />
                                {lead.email}
                              </div>
                            )}
                          </div>
                        </td>
                        <td className="p-4 hidden lg:table-cell">
                          <span className="text-sm text-[hsl(var(--muted-foreground))]">
                            {LEAD_SOURCE_LABELS[lead.source ?? ''] || lead.source || lead.origem || '-'}
                          </span>
                        </td>
                        <td className="p-4">
                          <span className={cn(
                            'inline-flex px-2 py-1 text-xs font-medium rounded-full border',
                            status?.color
                          )}>
                            {status?.label}
                          </span>
                        </td>
                        <td className="p-4 text-right">
                          <span className="font-mono text-sm text-[hsl(var(--foreground))]">
                            {formatCurrency(lead.expected_value || lead.valor_estimado || 0)}
                          </span>
                        </td>
                        <td className="p-4">
                          <div className="relative flex justify-end">
                            <Button
                              variant="ghost"
                              size="sm"
                              aria-label="Ações do lead"
                              onClick={(e) => {
                                e.stopPropagation();
                                setOpenMenuId(openMenuId === lead.id ? null : lead.id);
                              }}
                            >
                              <MoreHorizontal className="w-4 h-4" />
                            </Button>
                            {openMenuId === lead.id && (
                              <div
                                className="absolute right-0 top-full mt-1 z-20 w-52 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--popover,var(--card)))] shadow-lg py-1 text-sm"
                                onClick={(e) => e.stopPropagation()}
                              >
                                <button
                                  className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[hsl(var(--secondary))]/60"
                                  onClick={() => { setOpenMenuId(null); abrirEdicao(lead as unknown as Record<string, unknown>); }}
                                >
                                  <Pencil className="w-4 h-4" /> Editar lead
                                </button>
                                <div className="my-1 border-t border-[hsl(var(--border))]" />
                                <p className="px-3 py-1 text-xs text-[hsl(var(--muted-foreground))]">Mudar status</p>
                                {[
                                  { s: 'contacted', label: 'Em contato', icon: Phone },
                                  { s: 'qualified', label: 'Qualificado', icon: CheckCircle2 },
                                  { s: 'won', label: 'Convertido (ganho)', icon: CheckCircle2 },
                                  { s: 'lost', label: 'Perdido', icon: XCircle },
                                ].filter(o => o.s !== lead.status).map(({ s, label, icon: Icon }) => (
                                  <button
                                    key={s}
                                    className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-[hsl(var(--secondary))]/60"
                                    onClick={() => mudarStatus(lead.id, s, label)}
                                  >
                                    <Icon className="w-4 h-4" /> {label}
                                  </button>
                                ))}
                              </div>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Empty state */}
          {!isLoading && !isError && leads.length === 0 && (
            <div className="text-center py-12">
              <User className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                Nenhum lead encontrado
              </h3>
              <p className="text-[hsl(var(--muted-foreground))] mt-1">
                {search || statusFilter
                  ? 'Tente ajustar os filtros ou adicione um novo lead'
                  : 'Comece adicionando seu primeiro lead'}
              </p>
              {!search && !statusFilter && (
                <Button className="mt-4">
                  <Plus className="w-4 h-4 mr-2" />
                  Adicionar Lead
                </Button>
              )}
            </div>
          )}
        </CardContent>
      </Card>

      {/* Paginação info */}
      {!isLoading && leads.length > 0 && (
        <div className="text-sm text-[hsl(var(--muted-foreground))] text-center">
          Mostrando {leads.length} de {total} leads
        </div>
      )}
    </div>
  );
}
