'use client';

import { useState, useEffect } from 'react';
import {
  Users, UserPlus, UserMinus, FileText, Clock, DollarSign,
  Gift, Sun, ShieldCheck, FolderOpen, ArrowRight, CalendarDays, Loader2, Bell,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';

const API_BASE = '/api/v1/people-management/hr';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

export default function DPDashboardPage() {
  const router = useRouter();
  const [stats, setStats] = useState({ employees: 0, admissions: 0, vacations: 0, payroll: '0,00', payrollCompetencia: '' });
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function load() {
      try {
        const [empRes, admRes] = await Promise.all([
          fetch(`${API_BASE}/employees?page_size=1`, { headers: getAuthHeaders() }),
          fetch(`${API_BASE}/admissions?status=documents_pending&page_size=1`, { headers: getAuthHeaders() }),
        ]);
        let empCount = 0, admCount = 0;
        if (empRes.ok) {
          const d = await empRes.json();
          empCount = d.total || (d.items || d || []).length;
        }
        if (admRes.ok) {
          const d = await admRes.json();
          admCount = d.total || (d.items || d || []).length;
        }
        // Férias em andamento: solicitações APROVADAS cujo período cobre hoje (hr_vacation_requests)
        let vacCount = 0;
        try {
          const vacRes = await fetch(`${API_BASE}/vacations?status=APPROVED&page_size=100`, { headers: getAuthHeaders() });
          if (vacRes.ok) {
            const vacData = await vacRes.json();
            const today = new Date().toISOString().slice(0, 10);
            vacCount = (vacData.items || []).filter(
              (v: any) => v.start_date && v.end_date && v.start_date <= today && v.end_date >= today
            ).length;
          }
        } catch { /* ignore */ }
        // Folha: LÍQUIDO real da última competência importada (hr_payslips) —
        // NUNCA somar salario_base como se fosse folha (dado incompleto, não é folha).
        let payrollTotal = 0;
        let payrollCompetencia = '';
        try {
          const folhaRes = await fetch(`${API_BASE}/payroll/summary`, { headers: getAuthHeaders() });
          if (folhaRes.ok) {
            const f = await folhaRes.json();
            if (f.fonte === 'hr_payslips') {
              payrollTotal = f.total_liquido || 0;
              payrollCompetencia = f.competencia || '';
            }
          }
        } catch { /* ignore */ }
        setStats({
          employees: empCount,
          admissions: admCount,
          vacations: vacCount,
          payroll: payrollTotal.toLocaleString('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
          payrollCompetencia,
        });
      } catch { /* fallback */ } finally { setLoading(false); }
    }
    load();
  }, []);

  const statCards = [
    { title: 'Colaboradores Ativos', value: loading ? '...' : stats.employees, subtitle: 'Status ativo no sistema', icon: Users, color: '#2563eb' },
    { title: 'Admissões Pendentes', value: loading ? '...' : stats.admissions, subtitle: 'Processos em aberto', icon: UserPlus, color: '#16a34a' },
    { title: 'Férias em Andamento', value: loading ? '...' : stats.vacations, subtitle: 'Colaboradores em férias', icon: Sun, color: '#ea580c' },
    {
      title: stats.payrollCompetencia ? `Folha líquida (${stats.payrollCompetencia})` : 'Folha líquida (R$)',
      value: loading ? '...' : stats.payroll,
      subtitle: stats.payrollCompetencia ? 'Líquido real — holerites importados' : 'Aguardando folha importada',
      icon: DollarSign, color: '#9333ea',
    },
  ];

  const navCards = [
    { title: 'Funcionários', description: 'Cadastro completo e dados para eSocial', icon: Users, href: '/modulos/dp/funcionarios', color: 'text-blue-600', bgColor: 'bg-blue-50' },
    { title: 'Admissão', description: 'Processos de admissão de colaboradores', icon: UserPlus, href: '/modulos/dp/admissao', color: 'text-green-600', bgColor: 'bg-green-50' },
    { title: 'Rescisão', description: 'Processos de desligamento e rescisão', icon: UserMinus, href: '/modulos/dp/rescisao', color: 'text-red-600', bgColor: 'bg-red-50' },
    { title: 'Aviso Prévio', description: 'Avisos trabalhados e indenizados — Art. 487 CLT', icon: Bell, href: '/modulos/dp/aviso-previo', color: 'text-amber-600', bgColor: 'bg-amber-50' },
    { title: 'Contratos', description: 'Contratos de trabalho dos colaboradores', icon: FileText, href: '/modulos/dp/contratos', color: 'text-blue-600', bgColor: 'bg-blue-50' },
    { title: 'Ponto Eletrônico', description: 'Registro e controle de ponto', icon: Clock, href: '/modulos/dp/ponto', color: 'text-cyan-600', bgColor: 'bg-cyan-50' },
    { title: 'Folha Salarial', description: 'Folha de pagamento e encargos', icon: DollarSign, href: '/modulos/dp/folha', color: 'text-purple-600', bgColor: 'bg-purple-50' },
    { title: 'Benefícios', description: 'Gestão de benefícios dos colaboradores', icon: Gift, href: '/modulos/dp/beneficios', color: 'text-pink-600', bgColor: 'bg-pink-50' },
    { title: 'Férias', description: 'Programação e controle de férias', icon: Sun, href: '/modulos/dp/ferias', color: 'text-orange-600', bgColor: 'bg-orange-50' },
    { title: 'Licenças', description: 'Licenças e afastamentos', icon: CalendarDays, href: '/modulos/dp/licencas', color: 'text-yellow-600', bgColor: 'bg-yellow-50' },
    { title: 'eSocial', description: 'Eventos e obrigações do eSocial', icon: ShieldCheck, href: '/modulos/dp/esocial', color: 'text-indigo-600', bgColor: 'bg-indigo-50' },
    { title: 'Documentos', description: 'Documentos dos colaboradores', icon: FolderOpen, href: '/modulos/dp/documentos', color: 'text-slate-600', bgColor: 'bg-slate-50' },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        icon={<Users className="h-5 w-5" />}
        title="Departamento Pessoal"
        subtitle="Gestão completa de colaboradores, folha, ponto e benefícios"
      />

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {statCards.map((card) => (
          <StatCard
            key={card.title}
            icon={<card.icon className="h-4 w-4" />}
            label={card.title}
            value={card.value}
            sub={card.subtitle}
            color={card.color}
          />
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-5">
        {navCards.map((card) => (
          <Card
            key={card.title}
            className="cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => router.push(card.href)}
          >
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{card.title}</CardTitle>
              <card.icon className={`h-5 w-5 ${card.color}`} />
            </CardHeader>
            <CardContent>
              <p className="text-sm text-muted-foreground">{card.description}</p>
              <div className="flex items-center gap-1 mt-3 text-xs text-primary">
                <span>Acessar</span>
                <ArrowRight className="h-3 w-3" />
              </div>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
