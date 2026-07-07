'use client';

import { Settings, Search, RefreshCw, Plus, MoreHorizontal, AlertCircle, Edit, Trash2, RotateCcw, Shield, Database, Zap } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
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
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ConfirmModal } from '@/components/ui/modal';
;
import {
  useSystemConfigs,
  useCreateSystemConfig,
  useUpdateSystemConfig,
  useDeleteSystemConfig,
  useTenantSettings,
  useCreateTenantSetting,
  useUpdateTenantSettingValue,
  useResetTenantSetting,
  useDeleteTenantSetting,
  useTenants,
} from '@/hooks/useConfig';
import { ConfigValueEditor } from '@/components/configuracoes/config-value-editor';
import { SystemConfigFormModal } from '@/components/configuracoes/system-config-form-modal';
import type { SystemConfigResponse, TenantSettingsResponse } from '@/types/generated/config/conectaPROCONFIGModuleAPI.schemas';

const getSystemCategoryLabel = (category: string): string => {
  const labels: Record<string, string> = {
    system: 'Sistema',
    application: 'Aplicação',
    integrations: 'Integrações',
    security: 'Segurança',
    performance: 'Performance',
    maintenance: 'Manutenção',
    features: 'Funcionalidades',
  };
  return labels[category] || category;
};

const isConfigSensitive = (config: any): boolean => {
  const sensitiveKeys = ['api_key', 'secret', 'password', 'token', 'credential', 'private_key'];
  return sensitiveKeys.some((key) => config.chave?.toLowerCase().includes(key.toLowerCase()));
};

const maskSensitiveValue = (value: any): string => {
  const str = String(value);
  if (str.length <= 8) return '***';
  return str.substring(0, 4) + '***' + str.substring(str.length - 4);
};

const getTenantCategoryLabel = (category: string): string => {
  const labels: Record<string, string> = {
    general: 'Geral',
    appearance: 'Aparência',
    notifications: 'Notificações',
    integrations: 'Integrações',
    security: 'Segurança',
    features: 'Funcionalidades',
    billing: 'Faturamento',
  };
  return labels[category] || category;
};

export default function ConfiguracoesSistemaPage() {
  const [activeTab, setActiveTab] = useState('system');

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Settings className="h-6 w-6" />
          Configurações do Sistema
        </h1>
        <p className="text-muted-foreground">Configs globais e settings por tenant</p>
      </div>

      <Tabs value={activeTab} onValueChange={setActiveTab} className="w-full">
        <TabsList className="grid w-full grid-cols-2 max-w-md">
          <TabsTrigger value="system">Sistema</TabsTrigger>
          <TabsTrigger value="tenant">Tenant</TabsTrigger>
        </TabsList>

        <TabsContent value="system">
          <SystemConfigTab />
        </TabsContent>

        <TabsContent value="tenant">
          <TenantSettingsTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

// ==================== System Config Tab ====================

function SystemConfigTab() {
  const [search, setSearch] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('all');
  const [formOpen, setFormOpen] = useState(false);
  const [editConfig, setEditConfig] = useState<SystemConfigResponse | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const [editingValues, setEditingValues] = useState<Record<string, unknown>>({});

  const { data: configsData, isLoading, error, refetch } = useSystemConfigs({
    search: search || undefined,
    category: categoryFilter !== 'all' ? categoryFilter : undefined,
  });

  const createMutation = useCreateSystemConfig();
  const updateMutation = useUpdateSystemConfig();
  const deleteMutation = useDeleteSystemConfig();

  const configs = configsData?.items || [];

  // Group by category
  const grouped = configs.reduce<Record<string, SystemConfigResponse[]>>((acc, cfg) => {
    const cat = cfg.category || 'general';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(cfg);
    return acc;
  }, {});

  const handleInlineUpdate = async (config: SystemConfigResponse, newValue: unknown) => {
    await updateMutation.mutateAsync({
      id: config.id,
      data: { valor: newValue },
    });
  };

  return (
    <div className="space-y-4 mt-4">
      {/* Filters */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar por chave ou descricao..."
                className="pl-10"
              />
            </div>
            <Select value={categoryFilter} onValueChange={setCategoryFilter} aria-label="Category Filter">
              <SelectTrigger className="w-[180px]">
                <SelectValue placeholder="Categoria" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas categorias</SelectItem>
                <SelectItem value="system">Sistema</SelectItem>
                <SelectItem value="application">Aplicacao</SelectItem>
                <SelectItem value="integrations">Integracoes</SelectItem>
                <SelectItem value="security">Seguranca</SelectItem>
                <SelectItem value="performance">Performance</SelectItem>
                <SelectItem value="maintenance">Manutencao</SelectItem>
                <SelectItem value="features">Funcionalidades</SelectItem>
              </SelectContent>
            </Select>
            <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
              <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
            <Button onClick={() => { setEditConfig(null); setFormOpen(true); }}>
              <Plus className="h-4 w-4 mr-2" />
              Nova Config
            </Button>
          </div>
        </CardContent>
      </Card>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar configuracoes</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>Tentar novamente</Button>
        </div>
      )}

      {/* Loading */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : configs.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Settings className="h-16 w-16 mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium">Nenhuma configuracao encontrada</h3>
        </div>
      ) : (
        Object.entries(grouped).map(([category, items]) => (
          <Card key={category}>
            <CardHeader>
              <CardTitle className="text-base">{getSystemCategoryLabel(category)}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {items.map((config) => {
                const sensitive = isConfigSensitive(config);
                return (
                  <div key={config.id} className="flex items-start justify-between gap-4 py-3 border-b last:border-0">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <code className="text-sm font-mono">{config.chave}</code>
                        {config.admin_only && <Badge variant="outline" className="text-xs">Admin</Badge>}
                        {config.cacheable && <Badge variant="outline" className="text-xs"><Database className="h-3 w-3 mr-1" />Cache</Badge>}
                        {config.requires_restart && <Badge variant="outline" className="text-xs text-orange-600"><Zap className="h-3 w-3 mr-1" />Restart</Badge>}
                      </div>
                      {config.descricao && (
                        <p className="text-xs text-muted-foreground mt-1">{config.descricao}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <div className="w-48">
                        {sensitive ? (
                          <div className="flex items-center gap-1">
                            <Shield className="h-3 w-3 text-muted-foreground" />
                            <span className="text-sm text-muted-foreground font-mono">{maskSensitiveValue(config.valor)}</span>
                          </div>
                        ) : (
                          <ConfigValueEditor
                            value={editingValues[config.id] ?? config.valor}
                            valueType={config.value_type}
                            onChange={(v) => {
                              setEditingValues({ ...editingValues, [config.id]: v });
                              handleInlineUpdate(config, v);
                            }}
                          />
                        )}
                      </div>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => { setEditConfig(config); setFormOpen(true); }}>
                            <Edit className="h-4 w-4 mr-2" />
                            Editar
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            className="text-destructive"
                            onClick={() => { setDeleteId(config.id); setConfirmOpen(true); }}
                          >
                            <Trash2 className="h-4 w-4 mr-2" />
                            Deletar
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        ))
      )}

      {/* Modals */}
      <SystemConfigFormModal
        isOpen={formOpen}
        onClose={() => { setFormOpen(false); setEditConfig(null); }}
        config={editConfig}
        onSubmit={async (data) => {
          if (editConfig) {
            await updateMutation.mutateAsync({ id: editConfig.id, data });
          } else {
            await createMutation.mutateAsync(data);
          }
          setFormOpen(false);
          setEditConfig(null);
        }}
        isLoading={createMutation.isPending || updateMutation.isPending}
      />

      <ConfirmModal
        isOpen={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={async () => {
          if (deleteId) {
            await deleteMutation.mutateAsync(deleteId);
          }
          setConfirmOpen(false);
          setDeleteId(null);
        }}
        title="Deletar Configuracao"
        message="Tem certeza que deseja deletar esta configuracao?"
        variant="danger"
        isLoading={deleteMutation.isPending}
      />
    </div>
  );
}

// ==================== Tenant Settings Tab ====================

function TenantSettingsTab() {
  const [selectedTenantId, setSelectedTenantId] = useState('');
  const [search, setSearch] = useState('');
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [actionItem, setActionItem] = useState<{ id: string; type: 'reset' | 'delete' } | null>(null);

  const { data: tenantsData } = useTenants({ limit: 100 });
  const { data: settingsData, isLoading, refetch } = useTenantSettings(selectedTenantId, {
    search: search || undefined,
  });
  const updateValueMutation = useUpdateTenantSettingValue();
  const resetMutation = useResetTenantSetting();
  const deleteMutation = useDeleteTenantSetting();

  const tenants = tenantsData?.items || [];
  const settings = settingsData?.items || [];

  // Group by category
  const grouped = settings.reduce<Record<string, TenantSettingsResponse[]>>((acc, s) => {
    const cat = s.category || 'general';
    if (!acc[cat]) acc[cat] = [];
    acc[cat].push(s);
    return acc;
  }, {});

  return (
    <div className="space-y-4 mt-4">
      {/* Tenant Selector */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex flex-col md:flex-row gap-4">
            <div className="w-[300px]">
              <Label className="text-xs text-muted-foreground mb-1 block">Selecione o Tenant</Label>
              <Select value={selectedTenantId} onValueChange={setSelectedTenantId} aria-label="Selected Tenant Id">
                <SelectTrigger>
                  <SelectValue placeholder="Escolha um tenant..." />
                </SelectTrigger>
                <SelectContent>
                  {tenants.map((t) => (
                    <SelectItem key={t.id} value={t.id}>{t.nome}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Buscar configuracao..."
                className="pl-10"
                disabled={!selectedTenantId}
              />
            </div>
            <Button variant="outline" onClick={() => refetch()} disabled={isLoading || !selectedTenantId}>
              <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
              Atualizar
            </Button>
          </div>
        </CardContent>
      </Card>

      {!selectedTenantId ? (
        <div className="text-center py-12 text-muted-foreground">
          <Settings className="h-16 w-16 mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium">Selecione um tenant</h3>
          <p className="mt-2">Escolha um tenant acima para ver suas configuracoes</p>
        </div>
      ) : isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : settings.length === 0 ? (
        <div className="text-center py-12 text-muted-foreground">
          <Settings className="h-16 w-16 mx-auto mb-4 opacity-50" />
          <h3 className="text-lg font-medium">Nenhuma configuracao encontrada</h3>
        </div>
      ) : (
        Object.entries(grouped).map(([category, items]) => (
          <Card key={category}>
            <CardHeader>
              <CardTitle className="text-base">{getTenantCategoryLabel(category)}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {items.map((setting) => (
                <div key={setting.id} className="flex items-start justify-between gap-4 py-3 border-b last:border-0">
                  <div className="flex-1 min-w-0">
                    <code className="text-sm font-mono">{setting.chave}</code>
                    {setting.descricao && (
                      <p className="text-xs text-muted-foreground mt-1">{setting.descricao}</p>
                    )}
                    {setting.is_custom && (
                      <Badge variant="outline" className="text-xs mt-1">Customizado</Badge>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    <div className="w-48">
                      <ConfigValueEditor
                        value={setting.valor}
                        valueType={setting.value_type}
                        onChange={async (v) => {
                          await updateValueMutation.mutateAsync({ id: setting.id, value: { valor: v } });
                        }}
                      />
                    </div>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon" className="h-8 w-8">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem onClick={() => { setActionItem({ id: setting.id, type: 'reset' }); setConfirmOpen(true); }}>
                          <RotateCcw className="h-4 w-4 mr-2" />
                          Resetar
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive"
                          onClick={() => { setActionItem({ id: setting.id, type: 'delete' }); setConfirmOpen(true); }}
                        >
                          <Trash2 className="h-4 w-4 mr-2" />
                          Deletar
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        ))
      )}

      <ConfirmModal
        isOpen={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        onConfirm={async () => {
          if (actionItem) {
            if (actionItem.type === 'reset') {
              await resetMutation.mutateAsync(actionItem.id);
            } else {
              await deleteMutation.mutateAsync(actionItem.id);
            }
          }
          setConfirmOpen(false);
          setActionItem(null);
        }}
        title={actionItem?.type === 'reset' ? 'Resetar Configuracao' : 'Deletar Configuracao'}
        message={actionItem?.type === 'reset'
          ? 'Deseja resetar esta configuracao para o valor padrao?'
          : 'Tem certeza que deseja deletar esta configuracao?'
        }
        variant={actionItem?.type === 'reset' ? 'warning' : 'danger'}
        isLoading={resetMutation.isPending || deleteMutation.isPending}
      />
    </div>
  );
}
