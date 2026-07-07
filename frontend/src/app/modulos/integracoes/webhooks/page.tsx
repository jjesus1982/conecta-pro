'use client';

import { Webhook, Search, RefreshCw, Plus, MoreHorizontal, Eye, Edit, Zap, Key, Trash2, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ConfirmModal } from '@/components/ui/modal';
;
import {
  useWebhooks,
  useCreateWebhook,
  useUpdateWebhook,
  useTestWebhook,
  useRegenerateWebhookSecret,
} from '@/hooks/integrations';
import { WebhookFormModal } from '@/components/integracoes/webhook-form-modal';
import { WebhookDetailModal } from '@/components/integracoes/webhook-detail-modal';

export default function WebhooksPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  const { data: webhooksData, isLoading, error, refetch } = useWebhooks({
    search: search || undefined,
    status: statusFilter !== 'all' ? statusFilter as 'active' | 'paused' | 'disabled' | 'failing' : undefined,
  } as any);

  const createMutation = useCreateWebhook();
  const updateMutation = useUpdateWebhook();
  const testMutation = useTestWebhook();
  const regenerateSecretMutation = useRegenerateWebhookSecret();

  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [editWebhook, setEditWebhook] = useState<any | null>(null);
  const [selectedWebhook, setSelectedWebhook] = useState<any | null>(null);

  // Confirm modal state
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<void>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  const webhooks = webhooksData?.items || [];

  const stats = {
    total: webhooks.length,
    active: webhooks.filter((w: any) => w.status === 'active').length,
    errors: webhooks.filter((w: any) => w.status === 'error').length,
  };

  const openConfirm = (
    title: string,
    message: string,
    action: () => Promise<void>,
    variant: 'danger' | 'warning' | 'info' = 'warning'
  ) => {
    setConfirmAction({ title, message, action, variant });
    setConfirmOpen(true);
  };

  const handleCreate = async (data: any) => {
    await createMutation.mutateAsync(data);
    setFormOpen(false);
  };

  const handleUpdate = async (data: any) => {
    if (!editWebhook) return;
    await updateMutation.mutateAsync({ webhookId: editWebhook.id, data });
    setFormOpen(false);
    setEditWebhook(null);
  };

  const getStatusBadge = (status: string) => {
    const map: Record<string, string> = {
      active: 'bg-green-100 text-green-800',
      inactive: 'bg-gray-100 text-gray-800',
      error: 'bg-red-100 text-red-800',
    };
    const labels: Record<string, string> = {
      active: 'Ativo',
      inactive: 'Inativo',
      error: 'Erro',
    };
    return <Badge className={map[status] || 'bg-gray-100 text-gray-800'}>{labels[status] || status}</Badge>;
  };

  const truncateUrl = (url: string, maxLen = 45) => {
    if (url.length <= maxLen) return url;
    return url.substring(0, maxLen) + '...';
  };

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return '-';
    return new Date(dateStr).toLocaleString('pt-BR');
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Webhook className="h-6 w-6" />
            Webhooks
          </h1>
          <p className="text-muted-foreground">Gerencie endpoints de webhook para notificacoes e automacoes</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => { setEditWebhook(null); setFormOpen(true); }}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Webhook
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <Webhook className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativos</CardTitle>
            <Zap className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats.active}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Erros recentes</CardTitle>
            <AlertCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{stats.errors}</div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por nome ou URL..."
                className="pl-10"
              />
            </div>
            <Select value={statusFilter} onValueChange={(v) => setStatusFilter(v)}>
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos os status</SelectItem>
                <SelectItem value="active">Ativo</SelectItem>
                <SelectItem value="inactive">Inativo</SelectItem>
                <SelectItem value="error">Erro</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar webhooks</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : webhooks.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Webhook className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum webhook encontrado</h3>
              <p className="mt-2">Crie um novo webhook para receber notificacoes de eventos</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>URL</TableHead>
                  <TableHead>Eventos</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Ultimo disparo</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {webhooks.map((webhook: any) => (
                  <TableRow key={webhook.id}>
                    <TableCell>
                      <div className="font-medium">{webhook.name}</div>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-muted-foreground font-mono" title={webhook.url}>
                        {truncateUrl(webhook.url)}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">
                        {Array.isArray(webhook.events) ? webhook.events.length : 0} evento(s)
                      </Badge>
                    </TableCell>
                    <TableCell>{getStatusBadge(webhook.status)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {formatDate(webhook.last_triggered_at)}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedWebhook(webhook); setDetailOpen(true); }}>
                            <Eye className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setEditWebhook(webhook); setFormOpen(true); }}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() =>
                            openConfirm(
                              'Testar Webhook',
                              `Enviar requisicao de teste para "${webhook.name}"?`,
                              async () => { await testMutation.mutateAsync({ webhookId: webhook.id, data: { event: 'test' } }); },
                              'info'
                            )
                          }>
                            <Zap className="h-4 w-4 mr-2" />
                            Testar
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() =>
                            openConfirm(
                              'Regenerar Secret',
                              `Regenerar o secret de "${webhook.name}"? O secret atual sera invalidado.`,
                              async () => { await regenerateSecretMutation.mutateAsync(webhook.id); },
                              'warning'
                            )
                          }>
                            <Key className="h-4 w-4 mr-2" />
                            Regenerar Secret
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() =>
                              openConfirm(
                                'Deletar Webhook',
                                `Deletar "${webhook.name}" permanentemente? Esta acao nao pode ser desfeita.`,
                                async () => {
                                  await updateMutation.mutateAsync({ webhookId: webhook.id, data: { status: 'disabled' as const } });
                                },
                                'danger'
                              )
                            }
                          >
                            <Trash2 className="h-4 w-4 mr-2" />
                            Deletar
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Modals */}
      <WebhookFormModal
        isOpen={formOpen}
        onClose={() => { setFormOpen(false); setEditWebhook(null); }}
        webhook={editWebhook}
        onSubmit={editWebhook ? handleUpdate : handleCreate}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      <WebhookDetailModal
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedWebhook(null); }}
        webhook={selectedWebhook}
      />

      {confirmAction && (
        <ConfirmModal
          isOpen={confirmOpen}
          onClose={() => setConfirmOpen(false)}
          onConfirm={async () => {
            await confirmAction.action();
            setConfirmOpen(false);
          }}
          title={confirmAction.title}
          message={confirmAction.message}
          variant={confirmAction.variant}
          isLoading={testMutation.isPending || regenerateSecretMutation.isPending || updateMutation.isPending}
        />
      )}
    </div>
  );
}
