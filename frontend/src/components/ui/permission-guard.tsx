'use client';

import { ReactNode } from 'react';
import { usePermission, Permission, OperacionalRole } from '@/hooks/usePermission';

interface PermissionGuardProps {
  children: ReactNode;
  /** Permissao ou lista de permissoes (basta ter uma) */
  permission?: Permission | Permission[];
  /** Role ou lista de roles (basta ter um) */
  role?: string | string[];
  /** Role minimo na hierarquia */
  minimumRole?: OperacionalRole;
  /** Conteudo a exibir quando nao tem permissao */
  fallback?: ReactNode;
  /** Se true, exibe loading enquanto verifica */
  showLoading?: boolean;
}

/**
 * Componente para proteger elementos da UI baseado em permissoes.
 *
 * @example
 * // Proteger por permissao
 * <PermissionGuard permission={Permission.POSTS_CREATE}>
 *   <Button>Novo Posto</Button>
 * </PermissionGuard>
 *
 * @example
 * // Proteger por multiplas permissoes (OR)
 * <PermissionGuard permission={[Permission.POSTS_CREATE, Permission.POSTS_EDIT]}>
 *   <Button>Gerenciar Posto</Button>
 * </PermissionGuard>
 *
 * @example
 * // Proteger por role
 * <PermissionGuard role="admin">
 *   <Button>Configurações Admin</Button>
 * </PermissionGuard>
 *
 * @example
 * // Proteger por role minimo
 * <PermissionGuard minimumRole={OperacionalRole.SUPERVISOR}>
 *   <Button>Aprovar Escala</Button>
 * </PermissionGuard>
 */
export function PermissionGuard({
  children,
  permission,
  role,
  minimumRole,
  fallback = null,
  showLoading = false,
}: PermissionGuardProps) {
  const { hasPermission, hasRole, hasMinimumRole, isLoading } = usePermission();

  // Loading state
  if (isLoading && showLoading) {
    return (
      <div className="animate-pulse bg-[hsl(var(--muted))] rounded h-8 w-24" />
    );
  }

  // Verificar permissao
  if (permission !== undefined) {
    const allowed = hasPermission(permission);
    if (!allowed) return <>{fallback}</>;
  }

  // Verificar role
  if (role !== undefined) {
    const allowed = hasRole(role);
    if (!allowed) return <>{fallback}</>;
  }

  // Verificar role minimo
  if (minimumRole !== undefined) {
    const allowed = hasMinimumRole(minimumRole);
    if (!allowed) return <>{fallback}</>;
  }

  return <>{children}</>;
}

/**
 * Componente para proteger paginas inteiras.
 * Redireciona para pagina de acesso negado quando nao tem permissao.
 */
interface PageGuardProps {
  children: ReactNode;
  permission?: Permission | Permission[];
  role?: string | string[];
  minimumRole?: OperacionalRole;
  /** Mensagem customizada de acesso negado */
  deniedMessage?: string;
}

export function PageGuard({
  children,
  permission,
  role,
  minimumRole,
  deniedMessage = 'Voce nao tem permissao para acessar esta pagina.',
}: PageGuardProps) {
  const { hasPermission, hasRole, hasMinimumRole, isLoading, isAuthenticated } = usePermission();

  // Loading
  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <svg
            className="w-12 h-12"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
            />
          </svg>
        </div>
      </div>
    );
  }

  // Nao autenticado - o useAuth deve redirecionar
  if (!isAuthenticated) {
    return null;
  }

  // Verificar permissoes
  let hasAccess = true;

  if (permission !== undefined) {
    hasAccess = hasPermission(permission);
  }

  if (hasAccess && role !== undefined) {
    hasAccess = hasRole(role);
  }

  if (hasAccess && minimumRole !== undefined) {
    hasAccess = hasMinimumRole(minimumRole);
  }

  // Sem acesso
  if (!hasAccess) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="text-center max-w-md mx-auto px-4">
          <div className="w-16 h-16 mx-auto mb-4 rounded-full bg-red-500/10 flex items-center justify-center">
            <svg
              className="w-8 h-8 text-red-500"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>
          <h1 className="text-xl font-bold text-[hsl(var(--foreground))] mb-2">
            Acesso Negado
          </h1>
          <p className="text-[hsl(var(--muted-foreground))] mb-6">
            {deniedMessage}
          </p>
          <a
            href="/redesign"
            className="inline-flex items-center justify-center px-4 py-2 rounded-lg bg-[hsl(var(--primary))] text-white hover:opacity-90 transition-opacity"
          >
            Voltar ao Dashboard
          </a>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
