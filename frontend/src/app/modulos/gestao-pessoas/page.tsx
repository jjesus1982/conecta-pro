'use client';

import { useRouter } from 'next/navigation';
import {
  Users,
  Heart,
  FolderOpen,
  Shield,
  ShieldCheck,
  Clock,
  UserCircle,
  Building2,
  ArrowRight,
  ExternalLink,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { PageHeader } from '@/components/ui/page-header';

interface SubModule {
  title: string;
  description: string;
  href: string;
  icon: React.ElementType;
  color: string;
  bgColor: string;
  external?: boolean;
}

const subModules: SubModule[] = [
  {
    title: 'Departamento Pessoal',
    description: 'Folha, admissoes, ferias, rescisoes e beneficios',
    href: '/modulos/dp',
    icon: Users,
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
  },
  {
    title: 'Recursos Humanos',
    description: 'CCT, cargos, beneficios, headcount e relatorios de RH',
    href: '/modulos/gestao-pessoas/rh',
    icon: Heart,
    color: 'text-pink-600',
    bgColor: 'bg-pink-50',
  },
  {
    title: 'GED - Kits Documentais',
    description: 'Kits documentais, certidoes, envio automatico',
    href: '/modulos/gestao-pessoas/ged',
    icon: FolderOpen,
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
  },
  {
    title: 'Operacional',
    description: 'Postos, escalas, campo e inteligencia operacional',
    href: '/modulos/operacional',
    icon: Shield,
    color: 'text-cyan-600',
    bgColor: 'bg-cyan-50',
  },
  {
    title: 'Saude e Seguranca',
    description: 'ASO, PCMSO, PPRA, EPIs e exames periodicos',
    href: '/modulos/gestao-pessoas/sst',
    icon: ShieldCheck,
    color: 'text-emerald-600',
    bgColor: 'bg-emerald-50',
  },
  {
    title: 'Ponto Eletrônico',
    description: 'Batida facial, geolocalizacao, offline e justificativas',
    href: '/modulos/gestao-pessoas/ponto',
    icon: Clock,
    color: 'text-violet-600',
    bgColor: 'bg-violet-50',
  },
  {
    title: 'Portal do Funcionario',
    description: 'Contracheques, ferias, documentos e assinatura digital',
    href: '/modulos/portal',
    icon: UserCircle,
    color: 'text-teal-600',
    bgColor: 'bg-teal-50',
  },
  {
    title: 'Area do Cliente',
    description: 'Portal externo: kits documentais, chamados e downloads',
    href: '/area-cliente',
    icon: Building2,
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
    external: true,
  },
];

export default function GestaoPessoasPage() {
  const router = useRouter();

  return (
    <div className="p-6 space-y-6">
      <PageHeader
        eyebrow="PESSOAS"
        title="Gestao de Pessoas"
        subtitle="Gerencie todos os processos de departamento pessoal, recursos humanos e documentacao"
        icon={<Users className="w-5 h-5" />}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
        {subModules.map((mod) => {
          const Icon = mod.icon;
          return (
            <Card
              key={mod.href}
              className="cursor-pointer hover:shadow-lg transition-all duration-200 border border-gray-200 hover:border-gray-300"
              onClick={() => {
                if (mod.external) {
                  window.open(mod.href, '_blank');
                } else {
                  router.push(mod.href);
                }
              }}
            >
              <CardContent className="p-6">
                <div className="flex items-start justify-between">
                  <div className={`p-3 rounded-lg ${mod.bgColor}`}>
                    <Icon className={`h-6 w-6 ${mod.color}`} />
                  </div>
                  {mod.external ? (
                    <ExternalLink className="h-5 w-5 text-gray-400" />
                  ) : (
                    <ArrowRight className="h-5 w-5 text-gray-400" />
                  )}
                </div>
                <h3 className="mt-4 text-lg font-semibold text-gray-900">
                  {mod.title}
                </h3>
                <p className="mt-2 text-sm text-gray-500">{mod.description}</p>
                {mod.external && (
                  <span className="mt-2 inline-block text-xs font-medium text-amber-600 bg-amber-50 px-2 py-0.5 rounded">
                    Portal Externo
                  </span>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      <div className="mt-8 p-4 bg-gray-50 rounded-lg border border-gray-200">
        <h2 className="text-sm font-medium text-gray-700">Acesso Rapido</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={() => router.push('/modulos/dp')}
            className="px-3 py-1.5 text-xs font-medium bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Folha de Pagamento
          </button>
          <button
            onClick={() => router.push('/modulos/gestao-pessoas/ged/kits')}
            className="px-3 py-1.5 text-xs font-medium bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Kits Documentais
          </button>
          <button
            onClick={() => router.push('/modulos/gestao-pessoas/ged/certidoes')}
            className="px-3 py-1.5 text-xs font-medium bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Certidoes (CND)
          </button>
          <button
            onClick={() => router.push('/modulos/rh')}
            className="px-3 py-1.5 text-xs font-medium bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Treinamentos
          </button>
          <button
            onClick={() => router.push('/modulos/gestao-pessoas/ponto/batida')}
            className="px-3 py-1.5 text-xs font-medium bg-white border border-gray-300 rounded-md hover:bg-gray-50 transition-colors"
          >
            Bater Ponto
          </button>
          <button
            onClick={() => window.open('/area-cliente', '_blank')}
            className="px-3 py-1.5 text-xs font-medium bg-amber-50 border border-amber-300 rounded-md hover:bg-amber-100 transition-colors text-amber-700"
          >
            Portal do Cliente
          </button>
        </div>
      </div>
    </div>
  );
}
