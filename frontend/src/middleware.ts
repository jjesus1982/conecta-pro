import { NextResponse } from 'next/server';
import type { NextRequest } from 'next/server';

/**
 * Rotas que exigem autenticação.
 * O middleware redireciona para /login se não houver token.
 */
const PROTECTED_PREFIXES = ['/modulos', '/dashboard'];

/**
 * Rotas públicas que nunca devem ser bloqueadas.
 */
const PUBLIC_PATHS = [
  '/login',
  '/cadastro',
  '/forgot-password',
  '/reset-password',
  '/offline',
  '/area-cliente',
  '/auth/callback',
  '/modulos/configuracoes/usuarios',
];

function isPublic(pathname: string): boolean {
  return PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(p + '/'));
}

function isProtected(pathname: string): boolean {
  return PROTECTED_PREFIXES.some((p) => pathname === p || pathname.startsWith(p + '/'));
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Ignorar assets, API routes e arquivos estáticos
  if (
    pathname.startsWith('/_next') ||
    pathname.startsWith('/api') ||
    pathname.includes('.') // favicon.ico, sw.js, etc.
  ) {
    return NextResponse.next();
  }

  // Rotas públicas — sempre permitir
  if (isPublic(pathname)) {
    return NextResponse.next();
  }

  // Rotas protegidas — verificar token
  if (isProtected(pathname)) {
    const token =
      request.cookies.get('auth_token')?.value ||
      request.headers.get('authorization')?.replace('Bearer ', '');

    if (!token) {
      const loginUrl = new URL('/login', request.url);
      // `pathname + search`, não só `pathname`. Origem: 17/09/2026 — a cobrança de assinatura
      // manda `/modulos/meu-espaco?t=assinar` por WhatsApp para quem quase nunca está logado.
      // Guardando só o caminho, a pessoa logava e caía na home com 12 abas, e a aba de
      // assinar — o motivo do link existir — se perdia no caminho.
      loginUrl.searchParams.set('redirect', pathname + (request.nextUrl.search || ''));
      return NextResponse.redirect(loginUrl);
    }
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all paths except:
     * - _next/static (static files)
     * - _next/image (image optimization)
     * - favicon.ico
     */
    '/((?!_next/static|_next/image|favicon.ico).*)',
  ],
};
