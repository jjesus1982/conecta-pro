'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { FileText, Calendar, FolderOpen, GraduationCap, Bell, LogOut, ShieldCheck, User } from 'lucide-react';

export default function PortalDashboardPage() {
  const router = useRouter();
  const [employeeName, setEmployeeName] = useState('');

  useEffect(() => {
    const token = localStorage.getItem('portal_token');
    if (!token) {
      router.push('/portal-funcionario/login');
      return;
    }
    setEmployeeName(localStorage.getItem('portal_employee_name') || 'Funcionario');
  }, [router]);

  const handleLogout = () => {
    localStorage.removeItem('portal_token');
    localStorage.removeItem('portal_refresh_token');
    localStorage.removeItem('portal_employee_name');
    router.push('/portal-funcionario/login');
  };

  const cards = [
    { icon: FileText, label: 'Contracheques', desc: 'Holerites e demonstrativos', href: '/portal-funcionario/contracheques', color: 'bg-blue-50 text-blue-600' },
    { icon: Calendar, label: 'Férias', desc: 'Saldo e solicitacoes', href: '/portal-funcionario/ferias', color: 'bg-green-50 text-green-600' },
    { icon: FolderOpen, label: 'Documentos', desc: 'Declaracoes e comprovantes', href: '/portal-funcionario/documentos', color: 'bg-purple-50 text-purple-600' },
    { icon: GraduationCap, label: 'Treinamentos', desc: 'Certificados e cursos', href: '/portal-funcionario/treinamentos', color: 'bg-orange-50 text-orange-600' },
    { icon: Bell, label: 'Notificações', desc: 'Avisos e comunicados', href: '/portal-funcionario/notificacoes', color: 'bg-pink-50 text-pink-600' },
    { icon: User, label: 'Meus Dados', desc: 'Dados pessoais e contato', href: '/portal-funcionario/dados-pessoais', color: 'bg-teal-50 text-teal-600' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-[#0A2540] text-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <ShieldCheck className="w-7 h-7 text-blue-300" />
            <div>
              <h1 className="text-lg font-bold">CONECTA PRO</h1>
              <p className="text-xs text-blue-300">Portal do Funcionario</p>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <span className="text-sm text-blue-200 hidden sm:block">{employeeName}</span>
            <button onClick={handleLogout} className="flex items-center gap-1.5 text-sm text-blue-300 hover:text-white transition" title="Sair">
              <LogOut className="w-4 h-4" /> Sair
            </button>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-5xl mx-auto px-6 py-8">
        <h2 className="font-display text-2xl font-bold text-gray-900 mb-1">Ola, {employeeName.split(' ')[0]}!</h2>
        <p className="text-gray-500 mb-8">O que voce precisa hoje?</p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {cards.map((card) => (
            <Link key={card.label} href={card.href} className="bg-white rounded-xl border border-gray-100 shadow-sm hover:shadow-md transition-all p-6 group">
              <div className={`w-12 h-12 rounded-xl flex items-center justify-center mb-4 ${card.color}`}>
                <card.icon className="w-6 h-6" />
              </div>
              <h3 className="font-semibold text-gray-900 group-hover:text-[#0A2540] transition">{card.label}</h3>
              <p className="text-sm text-gray-500 mt-1">{card.desc}</p>
            </Link>
          ))}
        </div>
      </main>

      <footer className="text-center py-6 text-xs text-gray-400">
        Conecta Mais &copy; {new Date().getFullYear()} &mdash; Seguranca e Tecnologia
      </footer>
    </div>
  );
}
