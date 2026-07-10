'use client';

import { useState, useEffect, useMemo } from 'react';
import { ShieldCheck, ArrowLeft, Inbox, Loader2, X, AlertTriangle, Search, ChevronLeft, ChevronRight as ChevronRightIcon, RefreshCw, Send } from 'lucide-react';
import { toast } from 'sonner';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';

const API_BASE_GOV = '/api/v1/government';
const API_BASE_HR = '/api/v1/people-management/hr';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const statusConfig: Record<string, { label: string; className: string }> = {
  pendente: { label: 'Pendente', className: 'bg-yellow-500 text-white' },
  enviado: { label: 'Enviado', className: 'bg-blue-500 text-white' },
  aceito: { label: 'Aceito', className: 'bg-green-500 text-white' },
  rejeitado: { label: 'Rejeitado', className: 'bg-red-500 text-white' },
  processando: { label: 'Processando', className: 'bg-cyan-500 text-white' },
  pending: { label: 'Pendente', className: 'bg-yellow-500 text-white' },
  sent: { label: 'Enviado', className: 'bg-blue-500 text-white' },
  accepted: { label: 'Aceito', className: 'bg-green-500 text-white' },
  rejected: { label: 'Rejeitado', className: 'bg-red-500 text-white' },
  processing: { label: 'Processando', className: 'bg-cyan-500 text-white' },
  error: { label: 'Erro', className: 'bg-red-600 text-white' },
  erro: { label: 'Erro', className: 'bg-red-600 text-white' },
};

const tipoConfig: Record<string, { label: string; description: string }> = {
  'S-1000': { label: 'S-1000', description: 'Informações do Empregador' },
  'S-1200': { label: 'S-1200', description: 'Remuneracao do Trabalhador' },
  'S-1210': { label: 'S-1210', description: 'Pagamentos de Rendimentos' },
  'S-2190': { label: 'S-2190', description: 'Registro Preliminar' },
  'S-2200': { label: 'S-2200', description: 'Cadastramento Inicial / Admissão' },
  'S-2205': { label: 'S-2205', description: 'Alteracao de Dados Cadastrais' },
  'S-2206': { label: 'S-2206', description: 'Alteracao de Contrato' },
  'S-2230': { label: 'S-2230', description: 'Afastamento Temporario' },
  'S-2299': { label: 'S-2299', description: 'Desligamento' },
  'S-2300': { label: 'S-2300', description: 'Trabalhador Sem Vinculo' },
  'S-2399': { label: 'S-2399', description: 'Termino TSV' },
  'S-2500': { label: 'S-2500', description: 'Processo Trabalhista' },
  'S-3000': { label: 'S-3000', description: 'Exclusão de Eventos' },
};

const PAGE_SIZE = 12;

export default function ESocialPage() {
  const router = useRouter();
  const [eventos, setEventos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [showConfirm, setShowConfirm] = useState(false);
  const [sending, setSending] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [sortField, setSortField] = useState<string>('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [filtroTipo, setFiltroTipo] = useState<string>('todos');
  const [refreshKey, setRefreshKey] = useState(0);
  const [resumoBackend, setResumoBackend] = useState<{ pendentes: number; enviados: number; aceitos: number; rejeitados: number } | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        // Fonte REAL unificada: transmissões próprias (gp_asos/sst_afastamentos/
        // gp_cats/sst_s2240 — protocolo/recibo do governo) + espelho oficial.
        const res = await fetch(`${API_BASE_HR}/esocial/events?limit=2000`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          const items = Array.isArray(data) ? data : data.items || data.eventos || data.events || [];

          const normalized = items.map((e: any) => ({
            id: e.id,
            evento: e.evento || e.event_name || e.descricao || e.description || 'N/A',
            tipo: e.tipo || e.event_type || e.tipo_evento || e.code || 'N/A',
            colaborador: e.colaborador || e.employee_name || e.nome || e.worker_name || 'N/A',
            cpf: e.cpf || e.worker_cpf || '',
            status: e.status || 'pendente',
            data: e.data || e.date || e.created_at || e.event_date,
            protocolo: e.protocolo || e.protocol || e.receipt || '',
            recibo: e.recibo || '',
            origem: e.origem || '',
            lote: e.lote || e.batch_id || '',
            mensagem_retorno: e.mensagem_retorno || e.return_message || e.error_message || '',
          }));

          setEventos(normalized);
          setResumoBackend(data.resumo || null);
          if (normalized.length > 0) {
            toast.info(`${normalized.length} evento${normalized.length !== 1 ? 's' : ''} eSocial carregado${normalized.length !== 1 ? 's' : ''}`, { duration: 3000 });
          }
        } else {
          setEventos([]);
          setResumoBackend(null);
        }
      } catch {
        toast.error('Erro ao carregar eventos eSocial', { duration: 5000 });
        setEventos([]);
        setResumoBackend(null);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [refreshKey]);

  useEffect(() => { setCurrentPage(1); }, [searchTerm, filtroStatus, filtroTipo]);

  const handleSendPending = async () => {
    const pendingEvents = eventos.filter(e => e.status === 'pendente' || e.status === 'pending');
    if (pendingEvents.length === 0) {
      toast.info('Nenhum evento pendente para enviar', { duration: 3000 });
      setShowConfirm(false);
      return;
    }
    setSending(true);
    try {
      const res = await fetch(`${API_BASE_GOV}/esocial/eventos/enviar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: JSON.stringify({ event_ids: pendingEvents.map(e => e.id).filter(Boolean) }),
      });
      if (res.ok) {
        setShowConfirm(false);
        toast.success(`${pendingEvents.length} evento${pendingEvents.length !== 1 ? 's' : ''} enviado${pendingEvents.length !== 1 ? 's' : ''} com sucesso!`, { duration: 4000 });
        setRefreshKey(k => k + 1);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(err?.detail || 'Erro ao enviar eventos', { duration: 5000 });
      }
    } catch {
      toast.error('Erro de conexão ao enviar eventos', { duration: 5000 });
    } finally {
      setSending(false);
    }
  };

  // Get unique tipos for filter
  const uniqueTipos = useMemo(() => {
    const tipos = new Set(eventos.map(e => e.tipo).filter(Boolean));
    return Array.from(tipos).sort();
  }, [eventos]);

  // Filtered + searched + sorted
  const filteredData = useMemo(() => {
    let items = [...eventos];
    if (filtroStatus !== 'todos') {
      items = items.filter(e => e.status === filtroStatus);
    }
    if (filtroTipo !== 'todos') {
      items = items.filter(e => e.tipo === filtroTipo);
    }
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter(e =>
        (e.evento || '').toLowerCase().includes(term) ||
        (e.colaborador || '').toLowerCase().includes(term) ||
        (e.tipo || '').toLowerCase().includes(term) ||
        (e.cpf || '').includes(term) ||
        (e.protocolo || '').toLowerCase().includes(term)
      );
    }
    if (sortField) {
      items = [...items].sort((a, b) => {
        const va = String(a[sortField] || '').toLowerCase();
        const vb = String(b[sortField] || '').toLowerCase();
        return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      });
    }
    return items;
  }, [eventos, filtroStatus, filtroTipo, searchTerm, sortField, sortDir]);

  const totalPages = Math.max(1, Math.ceil(filteredData.length / PAGE_SIZE));
  const paginatedData = filteredData.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const sortIcon = (field: string) => {
    if (sortField !== field) return ' ↕';
    return sortDir === 'asc' ? ' ↑' : ' ↓';
  };

  // Counts by status — usa o resumo do backend quando disponível (fonte real),
  // com fallback para a contagem local dos eventos carregados.
  const countByStatus = (s: string) => eventos.filter(e => e.status === s).length;
  const pendentes = resumoBackend?.pendentes ?? (countByStatus('pendente') + countByStatus('pending'));
  const enviados = resumoBackend?.enviados ?? (countByStatus('enviado') + countByStatus('sent') + countByStatus('processando') + countByStatus('processing'));
  const aceitos = resumoBackend?.aceitos ?? (countByStatus('aceito') + countByStatus('accepted'));
  const rejeitados = resumoBackend?.rejeitados ?? (countByStatus('rejeitado') + countByStatus('rejected') + countByStatus('erro') + countByStatus('error'));

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<ShieldCheck className="h-5 w-5" />}
        title="eSocial - Eventos"
        subtitle="Gestão de eventos e obrigações do eSocial"
        actions={(
          <>
            <Button type="button" variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setRefreshKey(k => k + 1)}>
              <RefreshCw className="h-4 w-4" />
            </Button>
            <Button type="button" size="sm" disabled={pendentes === 0} onClick={() => setShowConfirm(true)}>
              <Send className="h-4 w-4 mr-1" /> Enviar Pendentes ({pendentes})
            </Button>
          </>
        )}
      />

      {/* Confirm send dialog */}
      {showConfirm && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle className="flex items-center gap-2"><AlertTriangle className="h-5 w-5 text-yellow-500" /> Confirmar Envio de Eventos Pendentes</CardTitle>
              <Button type="button" variant="ghost" size="sm" onClick={() => setShowConfirm(false)}><X className="h-4 w-4" /></Button>
            </div>
          </CardHeader>
          <CardContent>
            <p className="text-sm font-medium mb-2">{pendentes} evento{pendentes !== 1 ? 's' : ''} pendente{pendentes !== 1 ? 's' : ''}</p>
            <p className="text-sm text-muted-foreground mb-4">Os eventos serao enviados ao governo federal via eSocial. Confirme que os dados estao corretos antes de prosseguir.</p>
            <div className="flex gap-2">
              <Button type="button" size="sm" disabled={sending} onClick={handleSendPending}>
                {sending ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Send className="h-4 w-4 mr-1" />}
                {sending ? 'Enviando...' : 'Confirmar Envio'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => setShowConfirm(false)}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
      ) : (
        <>
          {/* Status summary cards */}
          <div className="grid gap-4 md:grid-cols-4">
            <StatCard
              icon={<AlertTriangle className="h-4 w-4" />}
              label="Pendentes"
              value={<span className="text-yellow-600">{pendentes}</span>}
              color="#ca8a04"
              onClick={() => setFiltroStatus(filtroStatus === 'pendente' ? 'todos' : 'pendente')}
            />
            <StatCard
              icon={<Send className="h-4 w-4" />}
              label="Enviados"
              value={<span className="text-blue-600">{enviados}</span>}
              color="#2563eb"
              onClick={() => setFiltroStatus(filtroStatus === 'enviado' ? 'todos' : 'enviado')}
            />
            <StatCard
              icon={<ShieldCheck className="h-4 w-4" />}
              label="Aceitos"
              value={<span className="text-green-600">{aceitos}</span>}
              color="#16a34a"
              onClick={() => setFiltroStatus(filtroStatus === 'aceito' ? 'todos' : 'aceito')}
            />
            <StatCard
              icon={<X className="h-4 w-4" />}
              label="Rejeitados"
              value={<span className="text-red-600">{rejeitados}</span>}
              color="#dc2626"
              onClick={() => setFiltroStatus(filtroStatus === 'rejeitado' ? 'todos' : 'rejeitado')}
            />
          </div>

          {/* Filter badges - by tipo */}
          {uniqueTipos.length > 0 && (
            <div className="flex gap-2 flex-wrap items-center">
              <span className="text-sm text-muted-foreground mr-1">Tipo:</span>
              <Badge
                className={`cursor-pointer ${filtroTipo === 'todos' ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}
                onClick={() => setFiltroTipo('todos')}
              >
                Todos
              </Badge>
              {uniqueTipos.map(tipo => {
                const info = tipoConfig[tipo];
                return (
                  <Badge
                    key={tipo}
                    className={`cursor-pointer ${filtroTipo === tipo ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}
                    onClick={() => setFiltroTipo(filtroTipo === tipo ? 'todos' : tipo)}
                    title={info?.description || tipo}
                  >
                    {tipo}
                  </Badge>
                );
              })}
            </div>
          )}

          {/* Events Table */}
          <Card>
            <CardHeader>
              <div className="flex items-center justify-between">
                <CardTitle>Eventos eSocial</CardTitle>
                <div className="relative w-64">
                  <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                  <input
                    type="text"
                    value={searchTerm}
                    onChange={e => setSearchTerm(e.target.value)}
                    placeholder="Buscar por evento, colaborador..."
                    className="w-full pl-9 pr-3 py-2 border rounded-md text-sm"
                  />
                </div>
              </div>
            </CardHeader>
            <CardContent>
              {filteredData.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
                  <Inbox className="h-12 w-12 mb-3" />
                  <p className="font-medium">Nenhum evento eSocial encontrado</p>
                  <p className="text-sm text-muted-foreground mt-1">
                    {searchTerm || filtroStatus !== 'todos' || filtroTipo !== 'todos'
                      ? 'Tente outra busca ou limpe os filtros.'
                      : 'Os eventos serão gerados a partir de admissões, desligamentos e outras obrigações.'}
                  </p>
                </div>
              ) : (
                <>
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('evento')}>Evento{sortIcon('evento')}</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('tipo')}>Tipo{sortIcon('tipo')}</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('colaborador')}>Colaborador{sortIcon('colaborador')}</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('status')}>Status{sortIcon('status')}</TableHead>
                        <TableHead className="cursor-pointer select-none" onClick={() => handleSort('data')}>Data{sortIcon('data')}</TableHead>
                        <TableHead>Protocolo</TableHead>
                        <TableHead>Ações</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {paginatedData.map((item, i) => {
                        const st = statusConfig[item.status] || { label: item.status || 'N/A', className: 'bg-gray-500 text-white' };
                        const tipoInfo = tipoConfig[item.tipo];
                        return (
                          <TableRow key={item.id || i}>
                            <TableCell className="font-medium max-w-[250px] truncate" title={item.evento}>{item.evento}</TableCell>
                            <TableCell>
                              <code className="text-xs bg-muted px-1.5 py-0.5 rounded" title={tipoInfo?.description || item.tipo}>
                                {item.tipo}
                              </code>
                            </TableCell>
                            <TableCell>{item.colaborador}</TableCell>
                            <TableCell><Badge className={st.className}>{st.label}</Badge></TableCell>
                            <TableCell>{item.data ? (() => { try { const p = String(item.data).split('T')[0]?.split('-'); return p && p.length === 3 ? `${p[2]}/${p[1]}/${p[0]}` : '-'; } catch { return '-'; } })() : '-'}</TableCell>
                            <TableCell>
                              {item.protocolo ? (
                                <code className="text-xs bg-green-50 text-green-700 px-1.5 py-0.5 rounded">{item.protocolo}</code>
                              ) : (
                                <span className="text-xs text-muted-foreground">-</span>
                              )}
                            </TableCell>
                            <TableCell>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  if (item.mensagem_retorno) {
                                    toast.info(item.mensagem_retorno, { duration: 5000 });
                                  } else {
                                    toast.info(`Evento ${item.tipo} - ${tipoInfo?.description || item.evento}`, { duration: 3000 });
                                  }
                                }}
                              >
                                Detalhes
                              </Button>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>

                  {/* Pagination */}
                  <div className="flex items-center justify-between mt-4 text-sm">
                    <span className="text-muted-foreground">
                      {filteredData.length} registro{filteredData.length !== 1 ? 's' : ''} — Pagina {currentPage} de {totalPages}
                    </span>
                    <div className="flex gap-1">
                      <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)}>
                        <ChevronLeft className="h-4 w-4" />
                      </Button>
                      {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                        const page = totalPages <= 5 ? i + 1 : Math.max(1, Math.min(currentPage - 2, totalPages - 4)) + i;
                        return (
                          <Button key={page} variant={currentPage === page ? 'default' : 'outline'} size="sm" onClick={() => setCurrentPage(page)}>
                            {page}
                          </Button>
                        );
                      })}
                      <Button variant="outline" size="sm" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => p + 1)}>
                        <ChevronRightIcon className="h-4 w-4" />
                      </Button>
                    </div>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
