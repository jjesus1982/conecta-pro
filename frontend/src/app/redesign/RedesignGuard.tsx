'use client';

import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState, type ReactNode } from 'react';

import { useAuth } from '@/hooks/useAuth';
import { SELF_SERVICE_ROUTE, temAcessoGestao } from '@/types/modules';

// Rotas públicas do redesign (não exigem token). `/redesign/login` continua aqui porque
// virou encaminhamento para `/login` — se o guard a protegesse, daria laço.
const PUBLIC = ['/redesign/login', '/redesign/splash'];

/**
 * Guard do redesign (client-side), em duas camadas:
 *
 * 1. AUTENTICAÇÃO — sem token → /login (tela única, com a identidade do redesign).
 * 2. AUTORIZAÇÃO — funcionário sem permissão de gestão → Portal do Funcionário.
 *
 * A camada 2 existe porque o /redesign nasceu sem ela: qualquer usuário logado via
 * primeiro acesso caía no painel de gestão e enxergava o menu administrativo (o dado
 * vinha zerado porque a API filtra, mas a navegação não barrava). /dashboard e /modulos
 * já faziam esse desvio; aqui a regra é mais estrita, pois pega também 'agente' e
 * qualquer papel sem permissão de módulo.
 */
export default function RedesignGuard({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const { user, isLoading, isAuthenticated } = useAuth();
  const [ok, setOk] = useState(false);

  const publica = PUBLIC.some((p) => pathname === p || pathname.startsWith(p + '/'));
  // Só bloqueia depois que o usuário carregou — antes disso não dá pra decidir.
  const semAcessoGestao = !publica && !isLoading && isAuthenticated && !temAcessoGestao(user);

  useEffect(() => {
    if (publica) {
      setOk(true);
      return;
    }
    let tok: string | null = null;
    try { tok = localStorage.getItem('access_token'); } catch { /* */ }
    if (!tok) {
      router.replace(`/login?redirect=${encodeURIComponent(pathname)}`);
      return;
    }
    setOk(true);
  }, [pathname, router, publica]);

  useEffect(() => {
    // Portal fica fora da árvore /redesign → navegação de página inteira.
    if (semAcessoGestao) window.location.replace(SELF_SERVICE_ROUTE);
  }, [semAcessoGestao]);

  if (!ok) return null;
  // Não renderiza o painel nem por um instante antes do desvio.
  if (semAcessoGestao) return null;
  return <>{children}</>;
}
