'use client';

import { Shield, ShieldCheck, ChevronLeft, ChevronRight, Menu, X, UserPlus, Target, Building2, Contact, FileText, FileSignature, ClipboardList, Calendar, CalendarDays, MapPin, UserCheck, AlertTriangle, Route, LogIn, Monitor, Bell, TrendingDown, TrendingUp, Activity, Receipt, CheckCircle2, FileSpreadsheet, FileCode, Award, File, Folder, Package, Repeat, Settings, Camera, Fingerprint, Video, Webhook, LayoutDashboard, ClipboardCheck, PieChart, Users, Lock, Building, Eye, Database, Clock, Megaphone, ShoppingCart, Calculator, Trash2, Key, RefreshCw, ToggleRight, Landmark, DollarSign, CreditCard, Wallet, Server, Zap, Plug, Truck, Plane, Handshake, Bot, HardHat, Stethoscope, Tag, BarChart2, BarChart3, Scale, ArrowRightLeft, Play, GitBranch, Mail, FileSearch, FileCheck, Briefcase, FolderOpen, Wrench, Coins, Filter, Magnet, Volume2, Trophy, Swords, PenLine, Library, BookUser, CalendarClock, Send, ShieldAlert, CalendarPlus } from 'lucide-react';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import Image from 'next/image';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { useAuth } from '@/hooks/useAuth';
import { getModuleByPath, modules } from '@/config/modules';
import { canAccessModule, hasModuleAccess, isSelfServiceUser, SELF_SERVICE_ROUTE } from '@/types/modules';
import { cn } from '@/lib/utils';
import { ThemeToggle } from '@/components/ThemeToggle';
import { SearchTrigger } from '@/components/SearchTrigger';
import { NotificationBell } from '@/features/notifications';
import { QuickActions } from '@/components/QuickActions';
import { WebSocketProvider, useWebSocketContext } from '@/components/WebSocketProvider';

// Mapeamento de icones para modulos e submodulos
const iconMap: Record<string, React.ElementType> = {
  UserPlus, Target, Building2, Contact, FileText,
  FileSignature, ClipboardList, Calendar, CalendarDays, CalendarPlus,
  MapPin, UserCheck, AlertTriangle, Route, LogIn,
  Monitor, Bell, TrendingDown, TrendingUp, Activity,
  Receipt, CheckCircle2, FileSpreadsheet, FileCode,
  Award, File, Folder, Package, Repeat, Settings,
  Camera, Fingerprint, Video, Webhook, LayoutDashboard,
  ClipboardCheck, PieChart, Users, Lock, Building, Eye, Database,
  Clock, Megaphone, ShieldCheck, ShoppingCart, Calculator, Trash2, Key,
  RefreshCw, ToggleRight, Landmark, DollarSign, CreditCard,
  Wallet, Server, Zap, Plug, Truck, Plane,
  // Novos icones para reorganizacao
  Handshake, Bot, HardHat, Stethoscope, Tag, BarChart2, BarChart3,
  Scale, ArrowRightLeft, Play, GitBranch, Mail, FileSearch, FileCheck,
  Briefcase, FolderOpen, Wrench, Shield,
  // CRM / Marketing / Licitacoes
  Coins, Filter, Magnet, Volume2, Trophy, Swords, PenLine, Library,
  // SST — Prontuário 360
  BookUser,
  // SST — Calendário Legal
  CalendarClock,
  // SST — Regularização
  ShieldAlert,
  // Financeiro — Pagamentos & Transferências
  Send,
};

// ---------------------------------------------------------------------------
// AlertsBadge — must render inside WebSocketProvider
// ---------------------------------------------------------------------------
function AlertsBadge() {
  const { unreadCount, alerts, markAllRead, isConnected } = useWebSocketContext();
  const [open, setOpen] = useState(false);

  if (!isConnected && unreadCount === 0) return null;

  return (
    <div className="relative">
      <button
        onClick={() => {
          setOpen(!open);
          if (open) markAllRead();
        }}
        className="relative w-9 h-9 flex items-center justify-center rounded-lg hover:bg-accent transition-colors"
        title="Alertas críticos"
      >
        <Bell className="w-4 h-4" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500 text-white text-[10px] font-bold flex items-center justify-center animate-pulse">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
        {isConnected && unreadCount === 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-2 h-2 rounded-full bg-green-500" />
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-11 w-80 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl shadow-xl z-50 overflow-hidden">
          <div className="flex items-center justify-between px-4 py-3 border-b border-[hsl(var(--border))]">
            <span className="text-sm font-semibold">Alertas ao Vivo</span>
            <div className="flex items-center gap-2">
              <span className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-gray-400'}`} />
              <span className="text-xs text-muted-foreground">
                {isConnected ? 'Conectado' : 'Desconectado'}
              </span>
            </div>
          </div>
          <div className="max-h-72 overflow-y-auto">
            {alerts.length === 0 ? (
              <p className="text-center text-sm text-muted-foreground py-8">Nenhum alerta</p>
            ) : (
              alerts.slice(0, 10).map((alert) => (
                <div
                  key={alert.id}
                  className={`px-4 py-3 border-b border-[hsl(var(--border))] last:border-0 ${!alert.read ? 'bg-red-500/5' : ''}`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span
                      className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        alert.severity === 'critical'
                          ? 'bg-red-500'
                          : alert.severity === 'warning'
                          ? 'bg-yellow-500'
                          : 'bg-blue-500'
                      }`}
                    />
                    <span className="text-xs font-medium">{alert.title}</span>
                  </div>
                  <p className="text-xs text-muted-foreground">{alert.message}</p>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// PendingApprovalScreen — usuário role=pending: cadastro em análise
// ---------------------------------------------------------------------------
function PendingApprovalScreen({ userName, onLogout }: { userName?: string; onLogout: () => void }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))] p-4">
      <div className="max-w-md w-full text-center">
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-8 shadow-sm">
          <div className="w-16 h-16 mx-auto mb-5 rounded-2xl bg-amber-500/10 flex items-center justify-center">
            <Clock className="w-8 h-8 text-amber-500" />
          </div>
          <h1 className="font-display text-xl font-bold text-[hsl(var(--foreground))] mb-2">
            Cadastro em análise
          </h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))] leading-relaxed mb-1">
            {userName ? `Olá, ${userName.split(' ')[0]}! ` : ''}Sua conta foi criada e aguarda
            aprovação de um administrador.
          </p>
          <p className="text-sm text-[hsl(var(--muted-foreground))] leading-relaxed mb-6">
            Assim que o acesso for liberado, os módulos aparecerão aqui automaticamente no seu
            próximo login.
          </p>
          <div className="flex items-center justify-center gap-2 mb-6">
            <span className="inline-block w-2 h-2 rounded-full bg-amber-500 animate-pulse" />
            <span className="text-xs font-semibold uppercase tracking-wider text-amber-600">
              Aguardando aprovação
            </span>
          </div>
          <Button variant="outline" onClick={onLogout} className="w-full">
            Sair da conta
          </Button>
        </div>
        <p className="mt-4 text-[11px] text-[hsl(var(--muted-foreground))]/60">
          Conecta PRO — erp.conectamais.pro
        </p>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// NoAccessScreen — módulo sem permissão: tela honesta de acesso negado
// ---------------------------------------------------------------------------
function NoAccessScreen({ moduleTitle, onBack }: { moduleTitle: string; onBack: () => void }) {
  return (
    <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))] p-4">
      <div className="max-w-md w-full text-center">
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-8 shadow-sm">
          <div className="w-16 h-16 mx-auto mb-5 rounded-2xl bg-red-500/10 flex items-center justify-center">
            <Lock className="w-8 h-8 text-red-500" />
          </div>
          <h1 className="font-display text-xl font-bold text-[hsl(var(--foreground))] mb-2">
            Sem acesso a este módulo
          </h1>
          <p className="text-sm text-[hsl(var(--muted-foreground))] leading-relaxed mb-6">
            Seu perfil não tem permissão para acessar <strong>{moduleTitle}</strong>. Se você
            precisa deste acesso, solicite a liberação a um administrador.
          </p>
          <Button onClick={onBack} className="w-full">
            Voltar ao início
          </Button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ModulosLayout
// ---------------------------------------------------------------------------
export default function ModulosLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const { isAuthenticated, isLoading, user, logout } = useAuth();
  const [sidebarOpen, setSidebarOpen] = useState(true);

  // Espião de hydration: o React #418 residual é INTERMITENTE (não reproduz em bancada).
  // Quando ocorrer numa sessão real, gravamos o component stack em localStorage.__h418
  // para diagnóstico posterior (ler no console: JSON.parse(localStorage.__h418)).
  useEffect(() => {
    const orig = console.error;
    console.error = (...args: unknown[]) => {
      try {
        const flat = args.map((a) => (a instanceof Error ? `${a.message}\n${a.stack}` : String(a))).join(' | ');
        if (flat.includes('418') || /hydrat/i.test(flat)) {
          const prev = JSON.parse(localStorage.getItem('__h418') || '[]');
          prev.push({ t: new Date().toISOString(), path: window.location.pathname, detail: flat.slice(0, 1500) });
          localStorage.setItem('__h418', JSON.stringify(prev.slice(-10)));
        }
      } catch { /* nunca interferir no fluxo */ }
      orig.apply(console, args as []);
    };
    return () => { console.error = orig; };
  }, []);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [wsToken, setWsToken] = useState<string | null>(null);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'https://erp.conectamais.pro';

  // Buscar módulo atual
  const currentModule = getModuleByPath(pathname);

  // Gating por permissões (user.permissions: 'all' | 'module:X'; role admin = tudo)
  const isPending = !isLoading && isAuthenticated && user?.role === 'pending';
  // Funcionário self-service: só a própria área (/modulos/meu-espaco), sem sidebar de gestão.
  const isSelfService = !isLoading && isAuthenticated && isSelfServiceUser(user);
  const inSelfServiceArea = pathname.startsWith(SELF_SERVICE_ROUTE);
  const hasAccessToCurrent =
    !currentModule || (!!user && canAccessModule(user, currentModule));
  // Primeiro módulo que o usuário pode ver (para o redirect de /modulos)
  const firstAccessibleModule =
    user && !isPending ? modules.find((m) => canAccessModule(user, m)) : undefined;

  // Redirecionar se não autenticado
  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [isLoading, isAuthenticated, router]);

  // Funcionário self-service: força a própria área se tentar qualquer rota de gestão.
  useEffect(() => {
    if (isSelfService && !inSelfServiceArea) {
      router.replace(SELF_SERVICE_ROUTE);
    }
  }, [isSelfService, inSelfServiceArea, router]);

  // Redirecionar /modulos → primeiro módulo acessível (fallback client-side
  // caso nginx intercepte o server redirect)
  useEffect(() => {
    if (!isLoading && isAuthenticated && pathname === '/modulos' && !isPending && !isSelfService) {
      router.replace(firstAccessibleModule?.href ?? '/dashboard');
    }
  }, [isLoading, isAuthenticated, pathname, router, isPending, isSelfService, firstAccessibleModule]);

  // Sync WS token from localStorage whenever auth state changes
  useEffect(() => {
    setWsToken(localStorage.getItem('access_token'));
  }, [isAuthenticated]);

  // Icone dinamico do modulo atual
  const ModuleIcon = currentModule ? (iconMap[currentModule.icon] || Shield) : Shield;

  // Auth ainda carregando: spinner
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Shield className="w-12 h-12" />
        </div>
      </div>
    );
  }

  // Usuário pendente: TUDO bloqueado — cadastro em análise
  if (isPending) {
    return <PendingApprovalScreen userName={user?.name} onLogout={logout} />;
  }

  // Funcionário self-service: renderiza a própria área SEM a sidebar de gestão.
  // (fora dela, o useEffect acima já redirecionou p/ SELF_SERVICE_ROUTE.)
  if (isSelfService) {
    if (inSelfServiceArea) {
      return <>{children}</>;
    }
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (!currentModule) {
    // /modulos sem submodulo: aguardar redirect do useEffect acima
    if (pathname === '/modulos') {
      return (
        <div className="min-h-screen flex items-center justify-center">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      );
    }
    // Rota sem módulo mapeado no menu: erro honesto em vez de spinner infinito
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))] p-4">
        <div className="max-w-md w-full text-center">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-2xl p-8 shadow-sm">
            <div className="w-16 h-16 mx-auto mb-5 rounded-2xl bg-amber-500/10 flex items-center justify-center">
              <AlertTriangle className="w-8 h-8 text-amber-500" />
            </div>
            <h1 className="font-display text-xl font-bold text-[hsl(var(--foreground))] mb-2">
              Página fora do menu
            </h1>
            <p className="text-sm text-[hsl(var(--muted-foreground))] leading-relaxed mb-6">
              A rota <code className="text-xs">{pathname}</code> não está mapeada em nenhum
              módulo do menu. Volte ao início ou acesse pelo menu de módulos.
            </p>
            <Button onClick={() => router.push('/dashboard')} className="w-full">
              Voltar ao início
            </Button>
          </div>
        </div>
      </div>
    );
  }

  // Rota direta para módulo sem permissão: tela honesta de acesso negado
  if (isAuthenticated && user && !hasAccessToCurrent) {
    return (
      <NoAccessScreen
        moduleTitle={currentModule.title}
        onBack={() => router.push('/dashboard')}
      />
    );
  }

  // Submódulos visíveis para o usuário (ex.: itens 'role:admin' somem p/ não-admin)
  const visibleSubModules = currentModule.subModules.filter((s) =>
    hasModuleAccess(user, s.permissions),
  );

  return (
    <WebSocketProvider token={wsToken} apiUrl={apiUrl}>
      <div className="flex bg-[hsl(var(--background))]" style={{ height: '100vh', overflow: 'hidden' }}>
        {/* Sidebar - Desktop */}
        <aside
          className={cn(
            'hidden lg:flex flex-col fixed inset-y-0 left-0 z-40',
            'bg-[hsl(var(--card))] border-r border-[hsl(var(--border))]',
            'transition-all duration-300 ease-in-out',
            sidebarOpen ? 'w-64' : 'w-16'
          )}
        >
          {/* Header */}
          <div className="h-14 flex items-center justify-between px-4 border-b border-[hsl(var(--border))]">
            {sidebarOpen ? (
              <button
                onClick={() => router.push('/dashboard')}
                className="flex items-center gap-2.5 text-[hsl(var(--foreground))] hover:text-[hsl(var(--primary))] transition-colors duration-200"
              >
                <Image
                  src="/images/logo-icon.png"
                  alt="Conecta PRO"
                  width={28}
                  height={28}
                  className="flex-shrink-0"
                />
                <span className="font-display text-sm font-semibold tracking-tight">Conecta&nbsp;<span style={{ color: '#f97707' }}>PRO</span></span>
              </button>
            ) : (
              <button
                onClick={() => setSidebarOpen(true)}
                className="mx-auto hover:opacity-80 transition-opacity duration-200"
                title="Expandir menu"
              >
                <Image
                  src="/images/logo-icon.png"
                  alt="Conecta PRO"
                  width={28}
                  height={28}
                />
              </button>
            )}
            {sidebarOpen && (
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setSidebarOpen(false)}
                className="transition-colors duration-200"
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
            )}
          </div>

          {/* Module title */}
          <div className={cn(
            'border-b border-[hsl(var(--border))]',
            sidebarOpen ? 'px-4 py-4 gradient-brand-subtle' : 'px-2 py-4'
          )}>
            {sidebarOpen ? (
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-xl bg-brand-500/10 flex items-center justify-center flex-shrink-0">
                  <ModuleIcon className="w-[18px] h-[18px] text-brand-500" />
                </div>
                <div className="min-w-0">
                  <h2 className="font-display font-semibold text-[hsl(var(--foreground))] text-sm">
                    {currentModule.title}
                  </h2>
                  <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5 line-clamp-1">
                    {currentModule.description}
                  </p>
                </div>
              </div>
            ) : (
              <div className="w-9 h-9 mx-auto rounded-xl bg-brand-500/10 flex items-center justify-center">
                <ModuleIcon className="w-[18px] h-[18px] text-brand-500" />
              </div>
            )}
          </div>

          {/* Navigation */}
          <nav className="flex-1 overflow-y-auto py-4" data-tour="sidebar-nav">
            <div className={cn('flex flex-col gap-1 px-2', sidebarOpen ? 'gap-1' : 'gap-3')}>
              {(() => {
                let lastGroup: string | undefined;
                return visibleSubModules.map((subModule) => {
                  const Icon = iconMap[subModule.icon] || FileText;
                  const isActive = pathname === subModule.href;
                  const showGroupHeader = sidebarOpen && subModule.group && subModule.group !== lastGroup;
                  if (subModule.group) lastGroup = subModule.group;

                  return (
                    <div key={subModule.id}>
                      {showGroupHeader && (
                        <div className="px-3 pt-3 pb-1 first:pt-0">
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/60">
                            {subModule.group}
                          </span>
                        </div>
                      )}
                      {/* Link (não button+router.push): navegação nativa que
                          funciona para qualquer href, inclusive cross-módulo
                          (ex.: /modulos/campo/* a partir do Operacional) */}
                      {sidebarOpen ? (
                        <Link
                          href={subModule.href}
                          className={cn(
                            'relative w-full flex items-center gap-3 px-3 py-2.5 rounded-xl',
                            'text-sm font-medium transition-all duration-200',
                            isActive
                              ? 'bg-[hsl(var(--primary))]/5 text-[hsl(var(--primary))]'
                              : 'text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--secondary))]/80 hover:text-[hsl(var(--foreground))]'
                          )}
                        >
                          {isActive && (
                            <span
                              className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full"
                              style={{ background: 'linear-gradient(180deg, hsl(var(--primary)), #f97707)' }}
                            />
                          )}
                          <Icon className="w-[18px] h-[18px] flex-shrink-0" />
                          <span className="flex-1 text-left">{subModule.title}</span>
                          {subModule.badge !== undefined && (
                            <span className="px-1.5 py-0.5 text-xs bg-brand-500/15 text-brand-500 rounded-md font-semibold">
                              {subModule.badge}
                            </span>
                          )}
                        </Link>
                      ) : (
                        <Link
                          href={subModule.href}
                          className={cn(
                            'relative w-full flex flex-col items-center justify-center py-2.5 rounded-xl',
                            'transition-all duration-200',
                            isActive
                              ? 'text-[hsl(var(--primary))] bg-[hsl(var(--primary))]/5'
                              : 'text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--secondary))]/80 hover:text-[hsl(var(--foreground))]'
                          )}
                          title={subModule.title}
                        >
                          <Icon className="w-[18px] h-[18px]" />
                          {isActive && (
                            <span className="absolute bottom-1 w-1 h-1 rounded-full bg-brand-500" />
                          )}
                        </Link>
                      )}
                    </div>
                  );
                });
              })()}
            </div>
          </nav>

          {/* Footer with user info + ThemeToggle */}
          <div className={cn(
            'p-3 border-t border-[hsl(var(--border))]',
            sidebarOpen ? 'flex items-center gap-3' : 'flex flex-col items-center gap-2'
          )}>
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 text-xs font-semibold text-white"
              style={{ background: 'linear-gradient(135deg, hsl(var(--primary)), #f97707)' }}
              title={user?.name || ''}
            >
              {user?.name?.charAt(0)?.toUpperCase() || 'U'}
            </div>
            {sidebarOpen && (
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-[hsl(var(--foreground))] truncate">
                  {user?.name || 'Usuario'}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))] truncate">
                  {user?.role || ''}
                </p>
              </div>
            )}
            <ThemeToggle />
          </div>
        </aside>

        {/* Mobile menu overlay */}
        {mobileMenuOpen && (
          <div
            className="fixed inset-0 z-40 bg-black/50 lg:hidden"
            onClick={() => setMobileMenuOpen(false)}
          />
        )}

        {/* Sidebar - Mobile */}
        <aside
          className={cn(
            'fixed inset-y-0 left-0 z-50 w-72 lg:hidden',
            'bg-[hsl(var(--card))] border-r border-[hsl(var(--border))]',
            'transform transition-transform duration-200 ease-out',
            mobileMenuOpen ? 'translate-x-0' : '-translate-x-full'
          )}
          aria-hidden={!mobileMenuOpen}
          role={mobileMenuOpen ? 'dialog' : undefined}
          aria-modal={mobileMenuOpen ? true : undefined}
          aria-label="Menu de navegação"
        >
          {/* Subtle gradient overlay at top */}
          <div className="absolute top-0 left-0 right-0 h-32 pointer-events-none opacity-[0.05] gradient-brand rounded-none" />

          {/* Header mobile */}
          <div className="relative h-16 flex items-center justify-between px-4 border-b border-[hsl(var(--border))]">
            <button
              onClick={() => {
                setMobileMenuOpen(false);
                router.push('/dashboard');
              }}
              className="flex items-center gap-2.5 text-[hsl(var(--foreground))] hover:text-[hsl(var(--primary))] transition-colors duration-200"
            >
              <Image
                src="/images/logo-icon.png"
                alt="Conecta PRO"
                width={24}
                height={24}
                className="flex-shrink-0"
              />
              <span className="font-display text-sm font-semibold tracking-tight">Conecta&nbsp;<span style={{ color: '#f97707' }}>PRO</span></span>
            </button>
            <button
              onClick={() => setMobileMenuOpen(false)}
              className="w-8 h-8 flex items-center justify-center rounded-lg bg-brand-500 text-white transition-colors duration-200 hover:bg-brand-500/90"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Module title mobile */}
          <div className="relative px-4 py-4 border-b border-[hsl(var(--border))] gradient-brand-subtle">
            <div className="flex items-center gap-3">
              <div className="w-9 h-9 rounded-xl bg-brand-500/10 flex items-center justify-center flex-shrink-0">
                <ModuleIcon className="w-[18px] h-[18px] text-brand-500" />
              </div>
              <div className="min-w-0">
                <h2 className="font-semibold text-[hsl(var(--foreground))] text-sm">
                  {currentModule.title}
                </h2>
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-0.5 line-clamp-1">
                  {currentModule.description}
                </p>
              </div>
            </div>
          </div>

          {/* Navigation mobile */}
          <nav className="relative flex-1 overflow-y-auto py-4">
            <div className="flex flex-col gap-1 px-2">
              {(() => {
                let lastGroup: string | undefined;
                return visibleSubModules.map((subModule) => {
                  const Icon = iconMap[subModule.icon] || FileText;
                  const isActive = pathname === subModule.href;
                  const showGroupHeader = subModule.group && subModule.group !== lastGroup;
                  if (subModule.group) lastGroup = subModule.group;

                  return (
                    <div key={subModule.id}>
                      {showGroupHeader && (
                        <div className="px-3 pt-3 pb-1 first:pt-0">
                          <span className="text-[10px] font-semibold uppercase tracking-wider text-[hsl(var(--muted-foreground))]/60">
                            {subModule.group}
                          </span>
                        </div>
                      )}
                      <Link
                        href={subModule.href}
                        onClick={() => setMobileMenuOpen(false)}
                        className={cn(
                          'relative w-full flex items-center gap-3 px-3 py-2.5 rounded-xl',
                          'text-sm font-medium transition-all duration-200',
                          isActive
                            ? 'bg-[hsl(var(--primary))]/5 text-[hsl(var(--primary))]'
                            : 'text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--secondary))]/80 hover:text-[hsl(var(--foreground))]'
                        )}
                      >
                        {isActive && (
                          <span
                            className="absolute left-0 top-1/2 -translate-y-1/2 w-[3px] h-5 rounded-r-full"
                            style={{ background: 'linear-gradient(180deg, hsl(var(--primary)), #f97707)' }}
                          />
                        )}
                        <Icon className="w-[18px] h-[18px] flex-shrink-0" />
                        <span>{subModule.title}</span>
                      </Link>
                    </div>
                  );
                });
              })()}
            </div>
          </nav>
        </aside>

        {/* Main content */}
        <div
          className={cn(
            'flex-1 flex flex-col transition-all duration-300',
            sidebarOpen ? 'lg:ml-64' : 'lg:ml-16'
          )}
          style={{ overflow: 'hidden' }}
        >
          {/* Header - Desktop e Mobile */}
          <header className="flex-shrink-0 z-30 h-14 flex items-center gap-3 px-4 bg-[hsl(var(--background))]/80 backdrop-blur-sm shadow-sm">
            {/* Mobile menu toggle */}
            <Button
              variant="ghost"
              size="sm"
              className="lg:hidden"
              onClick={() => setMobileMenuOpen(true)}
            >
              <Menu className="w-5 h-5" />
            </Button>

            {/* Logo + Title mobile */}
            <div className="flex items-center gap-2 flex-1 lg:hidden">
              <Image
                src="/images/logo-icon.png"
                alt="Conecta PRO"
                width={24}
                height={24}
                className="flex-shrink-0"
              />
              <span className="font-medium text-[hsl(var(--foreground))]">
                {currentModule.title}
              </span>
            </div>

            {/* Search trigger */}
            <div className="flex-1 max-w-md" data-tour="global-search">
              <SearchTrigger />
            </div>

            {/* Actions */}
            <div className="flex items-center gap-2">
              <AlertsBadge />
              <QuickActions />
              <NotificationBell />
              <ThemeToggle />
            </div>
          </header>

          {/* Page content */}
          <main className="flex-1 overflow-y-auto p-4 lg:p-6" style={{ overflowY: 'auto' }}>
            {children}
          </main>
        </div>
      </div>
    </WebSocketProvider>
  );
}
