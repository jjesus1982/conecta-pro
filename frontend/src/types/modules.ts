;

// Definição de um módulo do sistema
export interface Module {
  id: string;
  title: string;
  description: string;
  icon: string; // Nome do ícone Lucide
  href: string;
  color: 'cyan' | 'green' | 'orange' | 'purple' | 'red' | 'blue' | 'yellow' | 'pink' | 'amber' | 'teal';
  permissions: string[];
  subModules: SubModule[];
  badge?: string | number;
  enabled: boolean;
  external?: boolean;
}

// Sub-módulo (aparece na sidebar após clicar no card)
export interface SubModule {
  id: string;
  title: string;
  href: string;
  icon: string;
  permissions: string[];
  badge?: number;
  group?: string;
}

// Configuração de módulos por categoria
export interface ModuleCategory {
  id: string;
  title: string;
  modules: Module[];
}

// Roles de usuário
export type UserRole =
  | 'admin'
  | 'gerente'
  | 'supervisor'
  | 'operacional'
  | 'financeiro'
  | 'rh'
  | 'comercial'
  | 'cliente';

// Mapeamento de permissões por role
export const rolePermissions: Record<UserRole, string[]> = {
  admin: ['*'], // Acesso total
  gerente: [
    'crm:*',
    'financial:read',
    'financial:write',
    'operacional:*',
    'reports:*',
    'bidding:*', // Licitações - acesso completo
  ],
  supervisor: [
    'crm:read',
    'operacional:*',
    'campo:*',
    'reports:read',
    'bidding:read', // Licitações - leitura
  ],
  operacional: [
    'campo:read',
    'campo:write',
    'operacional:read',
  ],
  financeiro: [
    'financial:*',
    'government:*',
    'reports:financial',
    'bidding:*', // Licitações - acesso completo
  ],
  rh: [
    'users:*',
    'operacional:rh',
    'reports:rh',
  ],
  comercial: [
    'crm:*',
    'services:*',
    'reports:comercial',
    'bidding:read', // Licitações - leitura
  ],
  cliente: [
    'portal:*',
  ],
};

// ───────────────────────────────────────────────────────────────────────────
// Gating real por permissões module:X — fonte: user.permissions do backend
// (GET /auth/me → permissions: ['all'] | ['module:financeiro', 'module:dp', ...])
// ───────────────────────────────────────────────────────────────────────────

// Shape mínimo do usuário autenticado (compatível com useAuth().user)
export interface AccessUser {
  role?: string | null;
  permissions?: string[] | null;
}

// Roles com acesso total ao ERP
export const ADMIN_ROLES = ['admin', 'super_admin'];

// Área self-service do funcionário (login Google, role='funcionario').
// Estes usuários NUNCA veem módulos de gestão — só a própria área.
export const SELF_SERVICE_ROUTE = '/modulos/meu-espaco';

/** true se o usuário é funcionário self-service (role 'funcionario' ou permissão 'self:portal'). */
export function isSelfServiceUser(user: AccessUser | null | undefined): boolean {
  if (!user) return false;
  const role = user.role ?? '';
  const perms = user.permissions ?? [];
  // Admin/wildcard nunca é tratado como self-service (pode ter self:portal por engano).
  if (perms.includes('all') || perms.includes('*') || ADMIN_ROLES.includes(role)) return false;
  return role === 'funcionario' || perms.includes('self:portal');
}

/**
 * Verifica acesso a um conjunto de permissões requeridas (any-of).
 *
 * Regras:
 * - role 'pending' → NUNCA tem acesso (cadastro em análise)
 * - permissions contém 'all' ou '*' → acesso total
 * - role admin/super_admin → acesso total
 * - 'role:admin' nas permissões requeridas = restrito a admins
 *   (só satisfeito pelos atalhos acima)
 * - caso contrário: precisa ter ao menos um dos 'module:X' requeridos
 */
export function hasModuleAccess(
  user: AccessUser | null | undefined,
  requiredPermissions: string[],
): boolean {
  if (!user) return false;

  const role = user.role ?? '';
  if (role === 'pending') return false;

  const perms = user.permissions ?? [];
  if (perms.includes('all') || perms.includes('*')) return true;
  if (ADMIN_ROLES.includes(role)) return true;

  if (!requiredPermissions || requiredPermissions.length === 0) return true;

  // Funcionário self-service: só acessa o que exige exatamente 'self:portal'.
  // NENHUM módulo de gestão (module:X / role:admin).
  if (isSelfServiceUser(user)) {
    return requiredPermissions.includes('self:portal') && perms.includes('self:portal');
  }

  return requiredPermissions.some(
    (req) => req !== 'role:admin' && perms.includes(req),
  );
}

/** Acesso a um módulo inteiro (respeita enabled). */
export function canAccessModule(
  user: AccessUser | null | undefined,
  module: Pick<Module, 'permissions' | 'enabled'>,
): boolean {
  if (!module.enabled) return false;
  return hasModuleAccess(user, module.permissions);
}

// Verificar se usuário tem permissão (LEGADO — baseado em role estático)
export function hasPermission(userRole: UserRole, requiredPermissions: string[]): boolean {
  const userPermissions = rolePermissions[userRole];

  // Role desconhecida (ex: "pending") — sem acesso
  if (!userPermissions) return false;

  // Admin tem acesso total
  if (userPermissions.includes('*')) return true;

  // Verificar se tem alguma das permissões requeridas
  return requiredPermissions.some((required) => {
    return userPermissions.some((userPerm) => {
      // Permissão exata
      if (userPerm === required) return true;

      // Permissão com wildcard (ex: crm:* permite crm:read)
      if (userPerm.endsWith(':*')) {
        const prefix = userPerm.slice(0, -1); // Remove *
        return required.startsWith(prefix);
      }

      return false;
    });
  });
}
