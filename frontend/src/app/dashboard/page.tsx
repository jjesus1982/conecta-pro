'use client';

import { Users, Briefcase, Shield, Smartphone, DollarSign, Landmark, FolderOpen, Wrench, Plug, BarChart3, Settings, Bell, Search, LogOut, User, TrendingUp, TrendingDown, Wifi, WifiOff, Loader2, Handshake, Megaphone, Scale, XCircle, AlertTriangle } from 'lucide-react';
import { useEffect, useState, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Image from 'next/image';
import { format } from 'date-fns';
import { ptBR } from 'date-fns/locale';
import { ModuleCard } from '@/components/ui/module-card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/hooks/useAuth';
import { moduleCategories, modules } from '@/config/modules';
import { canAccessModule, isSelfServiceUser, SELF_SERVICE_ROUTE } from '@/types/modules';
import { cn } from '@/lib/utils';
import {
  fetchAllDashboardStats,
  fetchIntegrationSummary,
  fetchCertificateAlerts,
  fetchKitStats,
  fetchGedStats,
  type DashboardStats,
  type IntegrationSummary,
  type CertificateAlert,
  type KitStats,
  type GedStats,
} from '@/services/dashboard/dashboardStatsService';

// Mapeamento de ícones
const iconMap: Record<string, React.ElementType> = {
  Users, Briefcase, Shield, Smartphone, DollarSign, Landmark,
  FolderOpen, Wrench, Plug, BarChart3, Settings, Handshake,
  Megaphone, Scale,
};

export default function DashboardPage() {
  const router = useRouter();
  const { user, isLoading, isAuthenticated, logout } = useAuth();
  const [search, setSearch] = useState('');
  const [stats, setStats] = useState<DashboardStats | null>(null);
  const [integrations, setIntegrations] = useState<IntegrationSummary | null>(null);
  const [certAlerts, setCertAlerts] = useState<CertificateAlert[]>([]);
  const [kitStats, setKitStats] = useState<KitStats | null>(null);
  const [gedStats, setGedStats] = useState<GedStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  // Buscar dados reais do backend
  const loadRealData = useCallback(async () => {
    setStatsLoading(true);
    const [statsData, intgData, certs, kits, ged] = await Promise.all([
      fetchAllDashboardStats(),
      fetchIntegrationSummary(),
      fetchCertificateAlerts(),
      fetchKitStats(),
      fetchGedStats(),
    ]);
    setStats(statsData);
    setIntegrations(intgData);
    setCertAlerts(certs);
    setKitStats(kits);
    setGedStats(ged);
    setStatsLoading(false);
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      loadRealData();
    }
  }, [isAuthenticated, loadRealData]);

  const greeting = (() => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Bom dia';
    if (hour < 18) return 'Boa tarde';
    return 'Boa noite';
  })();

  // Redirecionar se não autenticado
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isLoading, isAuthenticated, router]);

  // Funcionário self-service: nunca vê o dashboard de gestão — vai p/ sua área.
  useEffect(() => {
    if (!isLoading && isAuthenticated && isSelfServiceUser(user)) {
      router.replace(SELF_SERVICE_ROUTE);
    }
  }, [isLoading, isAuthenticated, user, router]);

  // Filtrar módulos por busca e permissão
  const filteredCategories = moduleCategories.map(category => ({
    ...category,
    modules: category.modules.filter(module => {
      // Filtro de busca
      const matchesSearch = search === '' ||
        module.title.toLowerCase().includes(search.toLowerCase()) ||
        module.description.toLowerCase().includes(search.toLowerCase());

      // Filtro de permissão REAL — user.permissions do backend ('all' | 'module:X')
      const hasAccess = canAccessModule(user, module);

      return matchesSearch && hasAccess;
    }),
  })).filter(category => category.modules.length > 0);

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Shield className="w-12 h-12" />
        </div>
      </div>
    );
  }

  const todayFormatted = format(new Date(), "EEEE, d 'de' MMMM 'de' yyyy", { locale: ptBR });

  return (
    <div className="min-h-screen bg-grid noise" style={{ backgroundSize: '60px 60px', opacity: undefined }}>
      {/* Top gradient accent line */}
      <div className="h-[2px] w-full gradient-brand" />

      {/* Header */}
      <header className="sticky top-0 z-50 bg-[hsl(var(--background))]/60 backdrop-blur-2xl shadow-sm border-b border-[hsl(var(--border))]/50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <div className="flex items-center gap-2.5">
              <Image
                src="/images/logo.png"
                alt="Conecta PRO"
                width={32}
                height={32}
                className="rounded-lg"
              />
              <span className="font-semibold text-[hsl(var(--foreground))] tracking-tight">
                Conecta PRO
              </span>
            </div>

            {/* Search - Desktop */}
            <div className="hidden md:block w-96">
              <Input
                type="search"
                placeholder="Buscar módulos..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                icon={<Search className="w-4 h-4" />}
              />
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="sm" className="relative">
                <Bell className="w-5 h-5" />
                <span className="absolute -top-1 -right-1 w-4 h-4 bg-[hsl(var(--destructive))] rounded-full text-[10px] flex items-center justify-center text-white">
                  3
                </span>
              </Button>

              <div className="flex items-center gap-3 ml-2 pl-4 border-l border-[hsl(var(--border))]">
                <div className="hidden sm:block text-right">
                  <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                    {user?.name || 'Usuário'}
                  </p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    {user?.role || 'admin'}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={logout}
                  className="text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--destructive))]"
                >
                  <LogOut className="w-4 h-4" />
                </Button>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 sm:py-8">
        {/* Welcome */}
        <div className="mb-6 sm:mb-8 animate-slide-up gradient-brand-subtle rounded-2xl p-4 sm:p-6">
          <h1 className="font-display text-xl sm:text-2xl md:text-3xl font-bold text-[hsl(var(--foreground))]">
            {greeting}, <span className="text-[hsl(var(--primary))]">{user?.name?.split(' ')[0] || 'Usuário'}</span>
          </h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))] mt-1.5 capitalize">
            {todayFormatted}
          </p>
          <p className="text-[hsl(var(--muted-foreground))] mt-1">
            Selecione um módulo para começar
          </p>
        </div>

        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4 mb-6 sm:mb-8 animate-slide-up">
          {[
            { key: 'employees', label: 'Colaboradores', icon: Users, color: '#111b57', value: stats?.employees },
            { key: 'posts', label: 'Postos Ativos', icon: Shield, color: '#f97707', value: stats?.active_posts },
            { key: 'clients', label: 'Clientes Pagantes', icon: Briefcase, color: '#10b981', value: stats?.clients },
            { key: 'scales', label: 'Escalas', icon: BarChart3, color: '#8b5cf6', value: stats?.scales },
          ].map((stat) => (
            <div key={stat.key} className="card-shine bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-3.5 sm:p-5 transition-shadow hover:shadow-sm">
              <div className="flex items-center gap-2 sm:gap-3">
                <div className="w-9 h-9 sm:w-11 sm:h-11 rounded-xl flex items-center justify-center" style={{ backgroundColor: `${stat.color}15` }}>
                  <stat.icon className="w-5 h-5" style={{ color: stat.color }} />
                </div>
                <div>
                  {statsLoading ? (
                    <div className="w-12 h-8 rounded animate-shimmer" />
                  ) : (
                    <p className="text-2xl sm:text-3xl font-extrabold text-[hsl(var(--foreground))]">
                      {stat.value ?? '—'}
                    </p>
                  )}
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">{stat.label}</p>
                </div>
              </div>
            </div>
          ))}

          {/* Integration Status Card */}
          {integrations && integrations.total > 0 && (
            <div className="col-span-2 lg:col-span-4 card-shine bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-3.5 sm:p-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 sm:w-11 sm:h-11 rounded-xl bg-navy-600/10 flex items-center justify-center">
                    <Plug className="w-5 h-5 text-navy-600" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-[hsl(var(--foreground))]">Integrações Externas</p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">{integrations.total} integrações configuradas</p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="flex items-center gap-1.5">
                    <Wifi className="w-3.5 h-3.5 text-emerald-500" />
                    <span className="text-sm font-bold text-emerald-500">{integrations.online}</span>
                    <span className="text-xs text-[hsl(var(--muted-foreground))]">Online</span>
                  </div>
                  {integrations.offline > 0 && (
                    <div className="flex items-center gap-1.5">
                      <WifiOff className="w-3.5 h-3.5 text-red-500" />
                      <span className="text-sm font-bold text-red-500">{integrations.offline}</span>
                      <span className="text-xs text-[hsl(var(--muted-foreground))]">Offline</span>
                    </div>
                  )}
                  {(integrations.homologacao ?? 0) > 0 && (
                    <div className="flex items-center gap-1.5">
                      <Wifi className="w-3.5 h-3.5 text-blue-400" />
                      <span className="text-sm font-bold text-blue-400">{integrations.homologacao}</span>
                      <span className="text-xs text-[hsl(var(--muted-foreground))]">Homologa&ccedil;&atilde;o</span>
                    </div>
                  )}
                  {integrations.degraded > 0 && (
                    <div className="flex items-center gap-1.5">
                      <Wifi className="w-3.5 h-3.5 text-amber-500" />
                      <span className="text-sm font-bold text-amber-500">{integrations.degraded}</span>
                      <span className="text-xs text-[hsl(var(--muted-foreground))]">Inst&aacute;vel</span>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Critical Alerts */}
        {!statsLoading && certAlerts.length > 0 && (
          <div className="mb-6 space-y-2 animate-slide-up">
            {certAlerts.map((cert) => {
              const isExpired = cert.dias_para_vencer <= 0;
              const isCritical = cert.dias_para_vencer <= 7 && cert.dias_para_vencer > 0;
              return (
                <div
                  key={cert.id}
                  className={`flex items-center gap-3 px-4 py-3 rounded-xl border ${
                    isExpired
                      ? 'bg-red-50 border-red-200'
                      : isCritical
                        ? 'bg-red-50 border-red-200'
                        : 'bg-amber-50 border-amber-200'
                  }`}
                >
                  {isExpired || isCritical
                    ? <XCircle className="w-5 h-5 text-red-500 shrink-0" />
                    : <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0" />}
                  <div className="flex-1 min-w-0">
                    <p className={`text-sm font-medium ${isExpired || isCritical ? 'text-red-800' : 'text-amber-800'}`}>
                      {cert.nome || cert.tipo}
                      {isExpired
                        ? ` — Vencida desde ${new Date(cert.data_validade).toLocaleDateString('pt-BR')}`
                        : ` — Vence em ${cert.dias_para_vencer} dia(s)`}
                    </p>
                  </div>
                  <button
                    onClick={() => router.push('/modulos/gestao-pessoas/ged/certidoes')}
                    className={`text-xs font-medium px-3 py-1 rounded-lg ${
                      isExpired || isCritical
                        ? 'bg-red-100 text-red-700 hover:bg-red-200'
                        : 'bg-amber-100 text-amber-700 hover:bg-amber-200'
                    }`}
                  >
                    {isExpired ? 'Regularizar' : 'Ver'}
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Module Status Grid */}
        {!statsLoading && (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 mb-6 sm:mb-8 animate-slide-up">
            <div
              onClick={() => router.push('/modulos/gestao-pessoas')}
              className="card-shine bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-4 cursor-pointer hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-2 mb-2">
                <Users className="w-4 h-4 text-blue-600" />
                <span className="text-sm font-semibold">Gestao RH</span>
              </div>
              <p className="font-data text-2xl font-semibold tabular-nums">{stats?.employees ?? 0}</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">funcionarios ativos</p>
            </div>

            <div
              onClick={() => router.push('/modulos/gestao-pessoas/ged')}
              className="card-shine bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-4 cursor-pointer hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-2 mb-2">
                <FolderOpen className="w-4 h-4 text-amber-600" />
                <span className="text-sm font-semibold">GED</span>
              </div>
              <p className="font-data text-2xl font-semibold tabular-nums">{kitStats?.kits_ativos ?? 0}</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">kits ativos | {gedStats?.total_documents ?? 0} docs</p>
            </div>

            <div
              onClick={() => router.push('/modulos/financeiro/dashboard')}
              className="card-shine bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-4 cursor-pointer hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-2 mb-2">
                <DollarSign className="w-4 h-4 text-green-600" />
                <span className="text-sm font-semibold">Financeiro</span>
              </div>
              <p className="font-data text-2xl font-semibold tabular-nums">{stats?.clients ?? 0}</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">clientes pagantes</p>
            </div>

            <div
              onClick={() => router.push('/modulos/operacional')}
              className="card-shine bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-4 cursor-pointer hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-2 mb-2">
                <Shield className="w-4 h-4 text-cyan-600" />
                <span className="text-sm font-semibold">Operacional</span>
              </div>
              <p className="font-data text-2xl font-semibold tabular-nums">{stats?.active_posts ?? 0}</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">postos | {stats?.scales ?? 0} escalas</p>
            </div>

            <div
              onClick={() => router.push('/modulos/gestao-pessoas/ged/certidoes')}
              className="card-shine bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-4 cursor-pointer hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-2 mb-2">
                <Landmark className="w-4 h-4 text-red-600" />
                <span className="text-sm font-semibold">Compliance</span>
              </div>
              <p className="font-data text-2xl font-semibold tabular-nums text-red-600">{certAlerts.length}</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                {certAlerts.filter(c => c.dias_para_vencer <= 0).length > 0
                  ? `${certAlerts.filter(c => c.dias_para_vencer <= 0).length} vencida(s)!`
                  : 'alertas ativos'}
              </p>
            </div>

            <div
              onClick={() => router.push('/modulos/integracoes')}
              className="card-shine bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-4 cursor-pointer hover:shadow-md transition-shadow"
            >
              <div className="flex items-center gap-2 mb-2">
                <Plug className="w-4 h-4 text-purple-600" />
                <span className="text-sm font-semibold">Integracoes</span>
              </div>
              <p className="font-data text-2xl font-semibold tabular-nums">{integrations?.online ?? 0}/{integrations?.total ?? 0}</p>
              <p className="text-xs text-[hsl(var(--muted-foreground))]">online | Gov.br ativo</p>
            </div>
          </div>
        )}

        {/* Search - Mobile */}
        <div className="md:hidden mb-6">
          <Input
            type="search"
            placeholder="Buscar módulos..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            icon={<Search className="w-4 h-4" />}
            className="rounded-2xl h-12"
          />
        </div>

        {/* Module categories */}
        <div className="space-y-8 sm:space-y-10 stagger">
          {filteredCategories.map((category) => (
            <section key={category.id} className="animate-slide-up">
              <div className="flex items-center gap-3 mb-5">
                <div className="w-[3px] h-6 rounded-full gradient-brand" />
                <h2 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                  {category.title}
                </h2>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 sm:gap-5">
                {category.modules.map((module) => {
                  const Icon = iconMap[module.icon] || Shield;
                  return (
                    <ModuleCard
                      key={module.id}
                      id={module.id}
                      title={module.title}
                      description={module.description}
                      icon={Icon}
                      href={module.href}
                      color={module.color}
                      badge={module.badge}
                      disabled={!module.enabled}
                      external={module.external}
                    />
                  );
                })}
              </div>
            </section>
          ))}
        </div>

        {/* Empty state */}
        {filteredCategories.length === 0 && (
          user?.role === 'pending' ? (
            <div className="text-center py-16 max-w-md mx-auto">
              <div className="w-14 h-14 mx-auto mb-4 rounded-2xl bg-amber-500/10 flex items-center justify-center">
                <AlertTriangle className="w-7 h-7 text-amber-500" />
              </div>
              <h3 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                Cadastro em análise
              </h3>
              <p className="text-[hsl(var(--muted-foreground))] mt-2 text-sm leading-relaxed">
                Sua conta aguarda aprovação de um administrador. Os módulos aparecerão aqui
                assim que o acesso for liberado.
              </p>
            </div>
          ) : search ? (
            <div className="text-center py-16">
              <Search className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                Nenhum módulo encontrado
              </h3>
              <p className="text-[hsl(var(--muted-foreground))] mt-1">
                Tente buscar por outro termo
              </p>
            </div>
          ) : (
            <div className="text-center py-16 max-w-md mx-auto">
              <Shield className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
              <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                Nenhum módulo liberado
              </h3>
              <p className="text-[hsl(var(--muted-foreground))] mt-1 text-sm">
                Seu perfil ainda não tem módulos liberados. Solicite acesso a um administrador.
              </p>
            </div>
          )
        )}
      </main>

      {/* Footer */}
      <footer className="mt-auto">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="border-t border-[hsl(var(--border))]/50 pt-4 flex flex-col sm:flex-row items-center justify-between gap-2 text-[11px] text-[hsl(var(--muted-foreground))]/60">
            <span>Conecta PRO v2.0.0</span>
            <span>{new Date().getFullYear()} erp.conectamais.pro</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
