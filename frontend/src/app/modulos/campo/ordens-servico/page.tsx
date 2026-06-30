'use client';

/**
 * Ordens de Serviço — módulo Campo.
 * Lista as OS (inclui as abertas pelo José Luís via WhatsApp), com filtros,
 * detalhe e ações de fluxo (agendar / concluir / cancelar). Ao mudar o status,
 * o cliente que abriu pelo WhatsApp é avisado automaticamente (task proativa).
 */

import { useMemo, useState } from 'react';
import {
  ClipboardList, Search, RefreshCw, MoreHorizontal, CalendarClock,
  CheckCircle2, XCircle, Eye, MessageCircle, AlertTriangle,
} from 'lucide-react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Textarea } from '@/components/ui/textarea';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { toast } from 'sonner';

import {
  useOrdens, useOrdem, useAgendarOrdem, useConcluirOrdem, useCancelarOrdem,
} from '@/hooks/campo/useOrdemServico';
import {
  osStatusConfig, osPrioridadeConfig, osTipoLabel,
  OS_STATUS_OPTIONS, OS_PRIORIDADE_OPTIONS, OS_TIPO_OPTIONS,
} from '@/constants/campo/osStatus';
import { formatDate } from '@/lib/utils';

const PAGE_SIZE = 20;
const ALL = 'all';

function fmt(d?: string | null) {
  if (!d) return '—';
  try { return formatDate(d); } catch { return '—'; }
}

type ActionType = 'agendar' | 'concluir' | 'cancelar';

export default function OrdensServicoCampoPage() {
  const [busca, setBusca] = useState('');
  const [status, setStatus] = useState<string>(ALL);
  const [prioridade, setPrioridade] = useState<string>(ALL);
  const [tipo, setTipo] = useState<string>(ALL);
  const [page, setPage] = useState(1);

  // detalhe + ações
  const [detailId, setDetailId] = useState<string | null>(null);
  const [action, setAction] = useState<{ os: any; type: ActionType } | null>(null);
  const [form, setForm] = useState<{ data?: string; hora?: string; texto?: string }>({});

  const params = useMemo(
    () => ({
      busca: busca.trim() || undefined,
      status: status === ALL ? undefined : status,
      prioridade: prioridade === ALL ? undefined : prioridade,
      tipo: tipo === ALL ? undefined : tipo,
      page,
      page_size: PAGE_SIZE,
    }),
    [busca, status, prioridade, tipo, page],
  );

  const { data, isLoading, isError, error, refetch, isFetching } = useOrdens(params);
  const items: any[] = data?.items ?? [];
  const total: number = data?.total ?? 0;
  const pages: number = data?.pages ?? 1;

  const { data: detalhe, isLoading: detalheLoading } = useOrdem(detailId ?? '');

  const agendar = useAgendarOrdem();
  const concluir = useConcluirOrdem();
  const cancelar = useCancelarOrdem();
  const acting = agendar.isPending || concluir.isPending || cancelar.isPending;

  const temFiltro = busca || status !== ALL || prioridade !== ALL || tipo !== ALL;
  const limparFiltros = () => { setBusca(''); setStatus(ALL); setPrioridade(ALL); setTipo(ALL); setPage(1); };

  const abrirAcao = (os: any, type: ActionType) => {
    setForm({});
    setAction({ os, type });
  };

  const confirmarAcao = async () => {
    if (!action) return;
    const { os, type } = action;
    try {
      if (type === 'agendar') {
        if (!form.data || !form.hora) { toast.error('Informe a data e o horário do agendamento'); return; }
        await agendar.mutateAsync({
          ordemId: os.id,
          data: { data_agendada: form.data, horario_inicio_previsto: form.hora },
        });
        toast.success(`OS ${os.numero} agendada — o cliente é avisado no WhatsApp`);
      } else if (type === 'concluir') {
        await concluir.mutateAsync({
          ordemId: os.id,
          data: { solucao_aplicada: form.texto || undefined },
        });
        toast.success(`OS ${os.numero} concluída — o cliente é avisado no WhatsApp`);
      } else if (type === 'cancelar') {
        if (!form.texto || form.texto.trim().length < 5) {
          toast.error('Informe o motivo do cancelamento (mín. 5 caracteres)'); return;
        }
        await cancelar.mutateAsync({ ordemId: os.id, data: { motivo: form.texto.trim() } });
        toast.success(`OS ${os.numero} cancelada`);
      }
      setAction(null);
    } catch (e: any) {
      toast.error(e?.response?.data?.detail || e?.message || 'Não foi possível concluir a ação');
    }
  };

  // Alinhado às transições válidas do backend (ordem_servico_service): agendar só de
  // aberta/rascunho/reagendada; concluir/cancelar de qualquer status ativo (a mesa pode
  // fechar uma OS resolvida sem depender do app de campo). Evita botões que dariam 400.
  const FINALIZADOS = ['concluida', 'cancelada', 'rascunho', 'rejeitada'];
  const podeAgendar = (s: string) => ['aberta', 'rascunho', 'reagendada'].includes(s);
  const podeConcluir = (s: string) => !FINALIZADOS.includes(s);
  const podeCancelar = (s: string) => !['concluida', 'cancelada'].includes(s);

  return (
    <div className="p-4 md:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-blue-500/10 text-blue-400">
            <ClipboardList className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl md:text-2xl font-bold">Ordens de Serviço</h1>
            <p className="text-sm text-muted-foreground">
              Campo · {total} {total === 1 ? 'ordem' : 'ordens'}
              {temFiltro ? ' (filtradas)' : ''}
            </p>
          </div>
        </div>
        <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Filtros */}
      <Card>
        <CardContent className="p-4 flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              placeholder="Buscar por número, título, cliente…"
              value={busca}
              onChange={(e) => { setBusca(e.target.value); setPage(1); }}
              className="pl-9"
            />
          </div>
          <Select value={status} onValueChange={(v) => { setStatus(v); setPage(1); }}>
            <SelectTrigger className="w-[180px]"><SelectValue placeholder="Status" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Todos os status</SelectItem>
              {OS_STATUS_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={prioridade} onValueChange={(v) => { setPrioridade(v); setPage(1); }}>
            <SelectTrigger className="w-[160px]"><SelectValue placeholder="Prioridade" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Toda prioridade</SelectItem>
              {OS_PRIORIDADE_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
          <Select value={tipo} onValueChange={(v) => { setTipo(v); setPage(1); }}>
            <SelectTrigger className="w-[180px]"><SelectValue placeholder="Tipo" /></SelectTrigger>
            <SelectContent>
              <SelectItem value={ALL}>Todos os tipos</SelectItem>
              {OS_TIPO_OPTIONS.map((o) => <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>)}
            </SelectContent>
          </Select>
          {temFiltro && (
            <Button variant="ghost" size="sm" onClick={limparFiltros}>Limpar</Button>
          )}
        </CardContent>
      </Card>

      {/* Tabela */}
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-base">Ordens</CardTitle>
        </CardHeader>
        <CardContent>
          {isError ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <AlertTriangle className="h-8 w-8 text-red-400 mb-2" />
              <p className="text-sm text-muted-foreground mb-3">
                {(error as any)?.message || 'Erro ao carregar as ordens de serviço.'}
              </p>
              <Button variant="outline" size="sm" onClick={() => refetch()}>Tentar novamente</Button>
            </div>
          ) : isLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-12 rounded-lg bg-muted/40 animate-pulse" />
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-center">
              <ClipboardList className="h-10 w-10 text-muted-foreground/50 mb-2" />
              <p className="text-sm text-muted-foreground">
                {temFiltro ? 'Nenhuma OS encontrada com esses filtros.' : 'Nenhuma ordem de serviço ainda.'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Número</TableHead>
                    <TableHead>Título</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Status</TableHead>
                    <TableHead>Prioridade</TableHead>
                    <TableHead>Local</TableHead>
                    <TableHead>Agendada</TableHead>
                    <TableHead>Aberta</TableHead>
                    <TableHead className="text-right">Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {items.map((os) => {
                    const st = osStatusConfig(os.status);
                    const pr = osPrioridadeConfig(os.prioridade);
                    return (
                      <TableRow key={os.id} className="cursor-pointer" onClick={() => setDetailId(os.id)}>
                        <TableCell className="font-mono text-xs whitespace-nowrap">{os.numero}</TableCell>
                        <TableCell className="max-w-[260px] truncate">{os.titulo || '—'}</TableCell>
                        <TableCell className="whitespace-nowrap text-sm">{osTipoLabel(os.tipo)}</TableCell>
                        <TableCell>
                          <Badge className={`border ${st.color}`}>{st.label}</Badge>
                        </TableCell>
                        <TableCell>
                          <Badge className={`border ${pr.color}`}>{pr.label}</Badge>
                        </TableCell>
                        <TableCell className="max-w-[180px] truncate text-sm">
                          {os.cidade || os.endereco_servico || '—'}
                        </TableCell>
                        <TableCell className="whitespace-nowrap text-sm">{fmt(os.data_agendada)}</TableCell>
                        <TableCell className="whitespace-nowrap text-sm">{fmt(os.created_at)}</TableCell>
                        <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="icon" className="h-8 w-8">
                                <MoreHorizontal className="h-4 w-4" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => setDetailId(os.id)}>
                                <Eye className="h-4 w-4 mr-2" /> Ver detalhes
                              </DropdownMenuItem>
                              <DropdownMenuSeparator />
                              {podeAgendar(os.status) && (
                                <DropdownMenuItem onClick={() => abrirAcao(os, 'agendar')}>
                                  <CalendarClock className="h-4 w-4 mr-2" /> Agendar
                                </DropdownMenuItem>
                              )}
                              {podeConcluir(os.status) && (
                                <DropdownMenuItem onClick={() => abrirAcao(os, 'concluir')}>
                                  <CheckCircle2 className="h-4 w-4 mr-2" /> Concluir
                                </DropdownMenuItem>
                              )}
                              {podeCancelar(os.status) && (
                                <DropdownMenuItem className="text-red-400" onClick={() => abrirAcao(os, 'cancelar')}>
                                  <XCircle className="h-4 w-4 mr-2" /> Cancelar
                                </DropdownMenuItem>
                              )}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          )}

          {/* Paginação */}
          {!isLoading && !isError && items.length > 0 && (
            <div className="flex items-center justify-between pt-4 text-sm text-muted-foreground">
              <span>Página {page} de {pages} · {total} no total</span>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
                  Anterior
                </Button>
                <Button variant="outline" size="sm" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
                  Próxima
                </Button>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Dialog de detalhe */}
      <Dialog open={!!detailId} onOpenChange={(o) => !o && setDetailId(null)}>
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ClipboardList className="h-5 w-5" />
              {detalhe?.numero || 'Ordem de Serviço'}
            </DialogTitle>
            <DialogDescription>Detalhes da ordem de serviço</DialogDescription>
          </DialogHeader>
          {detalheLoading ? (
            <div className="space-y-2">
              {Array.from({ length: 5 }).map((_, i) => <div key={i} className="h-5 rounded bg-muted/40 animate-pulse" />)}
            </div>
          ) : detalhe ? (
            <div className="space-y-3 text-sm">
              <div className="flex flex-wrap gap-2">
                <Badge className={`border ${osStatusConfig(detalhe.status).color}`}>{osStatusConfig(detalhe.status).label}</Badge>
                <Badge className={`border ${osPrioridadeConfig(detalhe.prioridade).color}`}>{osPrioridadeConfig(detalhe.prioridade).label}</Badge>
                <Badge variant="outline">{osTipoLabel(detalhe.tipo)}</Badge>
                {detalhe.ticket_sistema === 'whatsapp' && (
                  <Badge className="border bg-green-500/20 text-green-400 border-green-500/30">
                    <MessageCircle className="h-3 w-3 mr-1" /> WhatsApp
                  </Badge>
                )}
              </div>
              <Linha label="Título" value={detalhe.titulo} />
              <Linha label="Cliente" value={(detalhe as any).cliente_nome || (detalhe as any).contato_nome} />
              <Linha label="Contato" value={(detalhe as any).contato_telefone || (detalhe as any).cliente_telefone} />
              <Linha label="Local" value={detalhe.endereco_servico} />
              <Linha label="Problema relatado" value={(detalhe as any).problema_relatado} />
              <Linha label="Descrição" value={detalhe.descricao} pre />
              <Linha label="Solução aplicada" value={(detalhe as any).solucao_aplicada} pre />
              <div className="grid grid-cols-2 gap-2">
                <Linha label="Aberta em" value={fmt((detalhe as any).data_abertura || detalhe.created_at)} />
                <Linha label="Agendada" value={fmt(detalhe.data_agendada)} />
                <Linha label="Técnico" value={(detalhe as any).tecnico_nome} />
                <Linha label="SLA" value={(detalhe as any).sla_horas ? `${(detalhe as any).sla_horas}h` : null} />
              </div>
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">Não foi possível carregar a OS.</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setDetailId(null)}>Fechar</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Dialog de ação (agendar / concluir / cancelar) */}
      <Dialog open={!!action} onOpenChange={(o) => !o && setAction(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>
              {action?.type === 'agendar' && 'Agendar OS'}
              {action?.type === 'concluir' && 'Concluir OS'}
              {action?.type === 'cancelar' && 'Cancelar OS'}
              {action ? ` ${action.os.numero}` : ''}
            </DialogTitle>
            <DialogDescription>
              {action?.type === 'agendar' && 'Defina a data (e horário) da visita técnica. O cliente é avisado no WhatsApp.'}
              {action?.type === 'concluir' && 'Registre a solução aplicada. O cliente é avisado da conclusão no WhatsApp.'}
              {action?.type === 'cancelar' && 'Informe o motivo do cancelamento.'}
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-3">
            {action?.type === 'agendar' && (
              <div className="flex gap-2">
                <Input type="date" value={form.data || ''} onChange={(e) => setForm((f) => ({ ...f, data: e.target.value }))} />
                <Input type="time" value={form.hora || ''} onChange={(e) => setForm((f) => ({ ...f, hora: e.target.value }))} className="w-32" />
              </div>
            )}
            {action?.type === 'concluir' && (
              <Textarea
                placeholder="Solução aplicada (opcional)…"
                value={form.texto || ''}
                onChange={(e) => setForm((f) => ({ ...f, texto: e.target.value }))}
              />
            )}
            {action?.type === 'cancelar' && (
              <Textarea
                placeholder="Motivo do cancelamento…"
                value={form.texto || ''}
                onChange={(e) => setForm((f) => ({ ...f, texto: e.target.value }))}
              />
            )}
          </div>

          <DialogFooter>
            <Button variant="outline" onClick={() => setAction(null)} disabled={acting}>Voltar</Button>
            <Button
              onClick={confirmarAcao}
              disabled={acting}
              variant={action?.type === 'cancelar' ? 'destructive' : 'default'}
            >
              {acting ? 'Processando…' : 'Confirmar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function Linha({ label, value, pre }: { label: string; value?: string | null; pre?: boolean }) {
  if (!value) return null;
  return (
    <div>
      <span className="text-xs text-muted-foreground">{label}</span>
      <p className={pre ? 'whitespace-pre-wrap' : ''}>{value}</p>
    </div>
  );
}
