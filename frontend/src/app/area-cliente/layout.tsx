'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { Shield, Home, FolderOpen, MessageSquare, Settings, LogOut, ShieldCheck } from 'lucide-react';

const navLinks = [
  { href: '/area-cliente', label: 'Início', icon: Home },
  { href: '/area-cliente/operacao', label: 'Minha Operação', icon: ShieldCheck },
  { href: '/area-cliente/kits', label: 'Meus Kits', icon: FolderOpen },
  { href: '/area-cliente/chamados', label: 'Chamados', icon: MessageSquare },
  { href: '/area-cliente/configuracoes', label: 'Configurações', icon: Settings },
];

export default function AreaClienteLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [clientName, setClientName] = useState<string>('');
  const [isChecking, setIsChecking] = useState(true);

  useEffect(() => {
    const token = localStorage.getItem('portal_token');
    const name = localStorage.getItem('portal_client_name');

    if (!token && !pathname.startsWith('/area-cliente/login')) {
      router.push('/area-cliente/login');
      return;
    }

    if (name) {
      setClientName(name);
    }
    setIsChecking(false);
  }, [pathname, router]);

  if (pathname.startsWith('/area-cliente/login')) {
    return <>{children}</>;
  }

  if (isChecking) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-indigo-600" />
      </div>
    );
  }

  function handleLogout() {
    localStorage.removeItem('portal_token');
    localStorage.removeItem('portal_client_name');
    localStorage.removeItem('portal_client_id');
    router.push('/area-cliente/login');
  }

  function isActive(href: string) {
    if (href === '/area-cliente') return pathname === '/area-cliente';
    return pathname.startsWith(href);
  }

  return (
    <div className="min-h-screen flex flex-col bg-gray-50">
      {/* Top Navigation */}
      <header className="bg-indigo-700 text-white shadow-lg">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-3">
              <Shield className="h-8 w-8 text-indigo-200" />
              <div>
                <span className="text-lg font-bold">Conecta PRO</span>
                <span className="text-indigo-200 mx-2">|</span>
                <span className="text-indigo-200 text-sm">Área do Cliente</span>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <span className="text-sm text-indigo-200">
                Olá, <span className="text-white font-medium">{clientName || 'Cliente'}</span>
              </span>
              <button
                onClick={handleLogout}
                className="flex items-center gap-1.5 text-sm text-indigo-200 hover:text-white transition-colors"
              >
                <LogOut className="h-4 w-4" />
                Sair
              </button>
            </div>
          </div>
        </div>

        {/* Horizontal Nav Links */}
        <nav className="bg-indigo-800">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex space-x-1">
              {navLinks.map((link) => {
                const Icon = link.icon;
                const active = isActive(link.href);
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`flex items-center gap-2 px-4 py-3 text-sm font-medium transition-colors border-b-2 ${
                      active
                        ? 'border-white text-white bg-indigo-900/40'
                        : 'border-transparent text-indigo-300 hover:text-white hover:border-indigo-400'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    {link.label}
                  </Link>
                );
              })}
            </div>
          </div>
        </nav>
      </header>

      {/* Main Content */}
      <main className="flex-1 max-w-7xl mx-auto w-full px-4 sm:px-6 lg:px-8 py-8">
        {children}
      </main>

      {/* Footer */}
      <footer className="bg-white border-t border-gray-200 py-4">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 text-center text-sm text-gray-500">
          &copy; 2026 Conecta PRO Segurança Patrimonial. Todos os direitos reservados.
        </div>
      </footer>
    </div>
  );
}
