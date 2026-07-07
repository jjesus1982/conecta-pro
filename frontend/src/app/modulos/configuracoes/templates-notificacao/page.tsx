'use client';

import { Mail, Search, RefreshCw, Plus, MoreHorizontal, AlertCircle, Eye, Edit, Copy, Power, PowerOff, Trash2, MessageSquare, Bell, Smartphone } from 'lucide-react';
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
  useNotificationTemplates,
  useCreateNotificationTemplate,
  useUpdateNotificationTemplate,
  useDeleteNotificationTemplate,
  useActivateNotificationTemplate,
  useDeactivateNotificationTemplate,
  useRenderNotificationTemplate,
  useCloneNotificationTemplate,
} from '@/hooks/useConfig';
import { TemplateFormModal } from '@/components/configuracoes/template-form-modal';
import { TemplatePreviewModal } from '@/components/configuracoes/template-preview-modal';
import type { NotificationTemplateResponse } from '@/types/generated/config/conectaPROCONFIGModuleAPI.schemas';

const getChannelLabel = (channel: string): string => {
  const labels: Record<string, string> = {
    email: 'E-mail',
    sms: 'SMS',
    push: 'Push Notification',
    whatsapp: 'WhatsApp',
    in_app: 'In-App',
  };
  return labels[channel] || channel;
};

const getCategoryLabel = (category: string): string => {
  const labels: Record<string, string> = {
    system: 'Sistema',
    operational: 'Operacional',
    financial: 'Financeiro',
    marketing: 'Marketing',
    security: 'Segurança',
    hr: 'RH',
  };
  return labels[category] || category;
};

export default function TemplatesNotificacaoPage() {
  const [search, setSearch] = useState('');
  const [channelFilter, setChannelFilter] = useState('all');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');
  const [page, setPage] = useState(0);
  const pageSize = 20;

  const { data: templatesData, isLoading, error, refetch } = useNotificationTemplates({
    skip: page * pageSize,
    limit: pageSize,
    search: search || undefined,
    channel: channelFilter !== 'all' ? channelFilter : undefined,
    category: categoryFilter !== 'all' ? categoryFilter : undefined,
    status: statusFilter !== 'all' ? statusFilter : undefined,
  });

  const createMutation = useCreateNotificationTemplate();
  const updateMutation = useUpdateNotificationTemplate();
  const deleteMutation = useDeleteNotificationTemplate();
  const activateMutation = useActivateNotificationTemplate();
  const deactivateMutation = useDeactivateNotificationTemplate();
  const renderMutation = useRenderNotificationTemplate();
  const cloneMutation = useCloneNotificationTemplate();

  const [formOpen, setFormOpen] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [editTemplate, setEditTemplate] = useState<NotificationTemplateResponse | null>(null);
  const [selectedTemplate, setSelectedTemplate] = useState<NotificationTemplateResponse | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAction, setConfirmAction] = useState<{
    title: string;
    message: string;
    action: () => Promise<any>;
    variant: 'danger' | 'warning' | 'info';
  } | null>(null);

  const templates = templatesData?.items || [];
  const total = templatesData?.total || 0;

  const stats = {
    total,
    active: templates.filter((t) => t.ativo).length,
    byChannel: templates.reduce<Record<string, number>>((acc, t) => {
      acc[t.channel] = (acc[t.channel] || 0) + 1;
      return acc;
    }, {}),
  };

  const openConfirm = (title: string, message: string, action: () => Promise<any>, variant: 'danger' | 'warning' | 'info' = 'warning') => {
    setConfirmAction({ title, message, action, variant });
    setConfirmOpen(true);
  };

  const handleCreate = async (data: any) => {
    await createMutation.mutateAsync(data);
    setFormOpen(false);
  };

  const handleUpdate = async (data: any) => {
    if (!editTemplate) return;
    await updateMutation.mutateAsync({ id: editTemplate.id, data });
    setFormOpen(false);
    setEditTemplate(null);
  };

  const getChannelBadge = (channel: string) => {
    const map: Record<string, { class: string; icon: typeof Mail }> = {
      email: { class: 'bg-blue-100 text-blue-800', icon: Mail },
      sms: { class: 'bg-green-100 text-green-800', icon: MessageSquare },
      push: { class: 'bg-purple-100 text-purple-800', icon: Bell },
      whatsapp: { class: 'bg-emerald-100 text-emerald-800', icon: Smartphone },
      in_app: { class: 'bg-orange-100 text-orange-800', icon: Bell },
    };
    const config = map[channel] || { class: 'bg-gray-100 text-gray-800', icon: Mail };
    const Icon = config.icon;
    return (
      <Badge className={config.class}>
        <Icon className="h-3 w-3 mr-1" />
        {getChannelLabel(channel)}
      </Badge>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Mail className="h-6 w-6" />
            Templates de Notificacao
          </h1>
          <p className="text-muted-foreground">Templates multi-canal para notificacoes do sistema</p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
            <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
            Atualizar
          </Button>
          <Button onClick={() => { setEditTemplate(null); setFormOpen(true); }}>
            <Plus className="h-4 w-4 mr-2" />
            Novo Template
          </Button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total</CardTitle>
            <Mail className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">{stats.total}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativos</CardTitle>
            <Power className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">{stats.active}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Email</CardTitle>
            <Mail className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{stats.byChannel['email'] || 0}</div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Push/SMS</CardTitle>
            <Bell className="h-4 w-4 text-purple-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-purple-600">
              {(stats.byChannel['push'] || 0) + (stats.byChannel['sms'] || 0)}
            </div>
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
                onChange={(e) => { setSearch(e.target.value); setPage(0); }}
                placeholder="Buscar por nome ou codigo..."
                className="pl-10"
              />
            </div>
            <Select value={channelFilter} onValueChange={(v) => { setChannelFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[150px]">
                <SelectValue placeholder="Canal" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos canais</SelectItem>
                <SelectItem value="email">E-mail</SelectItem>
                <SelectItem value="sms">SMS</SelectItem>
                <SelectItem value="push">Push</SelectItem>
                <SelectItem value="whatsapp">WhatsApp</SelectItem>
                <SelectItem value="in_app">In-App</SelectItem>
              </SelectContent>
            </Select>
            <Select value={categoryFilter} onValueChange={(v) => { setCategoryFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[160px]">
                <SelectValue placeholder="Categoria" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas</SelectItem>
                <SelectItem value="system">Sistema</SelectItem>
                <SelectItem value="operational">Operacional</SelectItem>
                <SelectItem value="financial">Financeiro</SelectItem>
                <SelectItem value="marketing">Marketing</SelectItem>
                <SelectItem value="security">Seguranca</SelectItem>
                <SelectItem value="hr">RH</SelectItem>
              </SelectContent>
            </Select>
            <Select value={statusFilter} onValueChange={(v) => { setStatusFilter(v); setPage(0); }}>
              <SelectTrigger className="w-[140px]">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todos</SelectItem>
                <SelectItem value="active">Ativos</SelectItem>
                <SelectItem value="inactive">Inativos</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar templates</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>Tentar novamente</Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : templates.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Mail className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum template encontrado</h3>
              <p className="mt-2">Crie um novo template para comecar</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome / Codigo</TableHead>
                  <TableHead>Canal</TableHead>
                  <TableHead>Categoria</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Versao</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {templates.map((tpl) => (
                  <TableRow key={tpl.id}>
                    <TableCell>
                      <div>
                        <div className="font-medium">{tpl.nome}</div>
                        <div className="text-xs text-muted-foreground font-mono">{tpl.codigo}</div>
                      </div>
                    </TableCell>
                    <TableCell>{getChannelBadge(tpl.channel)}</TableCell>
                    <TableCell className="text-sm">{getCategoryLabel(tpl.category || 'system')}</TableCell>
                    <TableCell>
                      <Badge className={tpl.ativo ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-800'}>
                        {tpl.ativo ? 'Ativo' : 'Inativo'}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">v{tpl.version ?? 1}</TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setSelectedTemplate(tpl); setPreviewOpen(true); }}>
                            <Eye className="h-4 w-4 mr-2" />
                            Preview
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() => { setEditTemplate(tpl); setFormOpen(true); }}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuItem onClick={() =>
                            openConfirm('Clonar Template', `Clonar "${tpl.nome}"?`, () => cloneMutation.mutateAsync(tpl.id), 'info')
                          }>
                            <Copy className="h-4 w-4 mr-2" />
                            Clonar
                          </DropdownMenuItem>
                          <DropdownMenuSeparator />
                          {tpl.ativo ? (
                            <DropdownMenuItem onClick={() =>
                              openConfirm('Desativar Template', `Desativar "${tpl.nome}"?`, () => deactivateMutation.mutateAsync(tpl.id), 'warning')
                            }>
                              <PowerOff className="h-4 w-4 mr-2" />
                              Desativar
                            </DropdownMenuItem>
                          ) : (
                            <DropdownMenuItem onClick={() =>
                              openConfirm('Ativar Template', `Ativar "${tpl.nome}"?`, () => activateMutation.mutateAsync(tpl.id), 'info')
                            }>
                              <Power className="h-4 w-4 mr-2" />
                              Ativar
                            </DropdownMenuItem>
                          )}
                          <DropdownMenuSeparator />
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() =>
                              openConfirm('Deletar Template', `Deletar "${tpl.nome}" permanentemente?`, () => deleteMutation.mutateAsync(tpl.id), 'danger')
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

      {/* Pagination */}
      {total > pageSize && (
        <div className="flex items-center justify-between">
          <p className="text-sm text-muted-foreground">
            Mostrando {page * pageSize + 1}-{Math.min((page + 1) * pageSize, total)} de {total}
          </p>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" onClick={() => setPage(Math.max(0, page - 1))} disabled={page === 0}>
              Anterior
            </Button>
            <Button variant="outline" size="sm" onClick={() => setPage(page + 1)} disabled={(page + 1) * pageSize >= total}>
              Proximo
            </Button>
          </div>
        </div>
      )}

      {/* Modals */}
      <TemplateFormModal
        isOpen={formOpen}
        onClose={() => { setFormOpen(false); setEditTemplate(null); }}
        template={editTemplate}
        onSubmit={editTemplate ? handleUpdate : handleCreate}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      <TemplatePreviewModal
        isOpen={previewOpen}
        onClose={() => { setPreviewOpen(false); setSelectedTemplate(null); }}
        template={selectedTemplate}
        onRender={(async (variables: Record<string, unknown>) => {
          if (!selectedTemplate) return null;
          const result = await renderMutation.mutateAsync({
            id: selectedTemplate.id,
            render: { variables },
          });
          return result as any;
        }) as any}
        isLoading={renderMutation.isPending}
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
          isLoading={activateMutation.isPending || deactivateMutation.isPending || cloneMutation.isPending || deleteMutation.isPending}
        />
      )}
    </div>
  );
}
