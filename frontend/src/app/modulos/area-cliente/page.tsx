'use client';

import { useRouter } from 'next/navigation';
import {
  Building2,
  Shield,
  ExternalLink,
  Key,
  Ticket,
  FolderOpen,
  ArrowRight,
  Settings,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

interface SubModule {
  title: string;
  description: string;
  href: string;
  icon: React.ElementType;
  color: string;
  bgColor: string;
  external?: boolean;
}

const adminModules: SubModule[] = [
  {
    title: 'Gerenciamento de Acessos',
    description: 'Provisionar credenciais, ativar/desativar e auditar acessos de clientes ao portal',
    href: '/modulos/area-cliente/gerenciamento',
    icon: Key,
    color: 'text-indigo-600',
    bgColor: 'bg-indigo-50',
  },
];

const portalModules: SubModule[] = [
  {
    title: 'Portal do Cliente',
    description: 'Acessar o portal externo onde clientes consultam kits, abrem chamados e baixam documentos',
    href: '/area-cliente',
    icon: Building2,
    color: 'text-amber-600',
    bgColor: 'bg-amber-50',
    external: true,
  },
  {
    title: 'Kits Documentais',
    description: 'Kits mensais entregues aos clientes com holerite, VT, VA, folha de ponto',
    href: '/area-cliente/kits',
    icon: FolderOpen,
    color: 'text-emerald-600',
    bgColor: 'bg-emerald-50',
    external: true,
  },
  {
    title: 'Chamados',
    description: 'Tickets de suporte abertos pelos clientes do portal',
    href: '/area-cliente/chamados',
    icon: Ticket,
    color: 'text-blue-600',
    bgColor: 'bg-blue-50',
    external: true,
  },
  {
    title: 'Configurações do Portal',
    description: 'Configurações gerais do portal externo do cliente',
    href: '/area-cliente/configuracoes',
    icon: Settings,
    color: 'text-gray-600',
    bgColor: 'bg-gray-50',
    external: true,
  },
];

export default function AreaClientePage() {
  const router = useRouter();

  function handleNavigation(mod: SubModule) {
    if (mod.external) {
      window.open(mod.href, '_blank');
    } else {
      router.push(mod.href);
    }
  }

  return (
    <div className="p-6 space-y-8 pb-28">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))] flex items-center gap-2">
          <Shield className="h-6 w-6 text-indigo-600" />
          Area do Cliente
        </h1>
        <p className="text-gray-500 mt-1">
          Gerencie o acesso dos clientes ao portal e acompanhe kits documentais e chamados
        </p>
      </div>

      {/* Admin Section */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Administracao</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {adminModules.map((mod) => {
            const Icon = mod.icon;
            return (
              <Card
                key={mod.href}
                className="cursor-pointer hover:shadow-lg transition-all duration-200 border border-gray-200 hover:border-indigo-300"
                onClick={() => handleNavigation(mod)}
              >
                <CardContent className="p-6">
                  <div className="flex items-start justify-between">
                    <div className={`p-3 rounded-lg ${mod.bgColor}`}>
                      <Icon className={`h-6 w-6 ${mod.color}`} />
                    </div>
                    <ArrowRight className="h-5 w-5 text-gray-400" />
                  </div>
                  <h3 className="mt-4 text-lg font-semibold text-gray-900">{mod.title}</h3>
                  <p className="mt-2 text-sm text-gray-500">{mod.description}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Portal Section */}
      <div>
        <h2 className="text-lg font-semibold text-gray-900 mb-1">Portal Externo</h2>
        <p className="text-sm text-gray-500 mb-4">
          Estes links abrem o portal do cliente em uma nova aba
        </p>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {portalModules.map((mod) => {
            const Icon = mod.icon;
            return (
              <Card
                key={mod.href}
                className="cursor-pointer hover:shadow-lg transition-all duration-200 border border-gray-200 hover:border-amber-300"
                onClick={() => handleNavigation(mod)}
              >
                <CardContent className="p-5">
                  <div className="flex items-start justify-between">
                    <div className={`p-2.5 rounded-lg ${mod.bgColor}`}>
                      <Icon className={`h-5 w-5 ${mod.color}`} />
                    </div>
                    <ExternalLink className="h-4 w-4 text-gray-400" />
                  </div>
                  <h3 className="mt-3 text-base font-semibold text-gray-900">{mod.title}</h3>
                  <p className="mt-1.5 text-xs text-gray-500 line-clamp-2">{mod.description}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      </div>

      {/* Quick access */}
      <div className="p-4 bg-gray-50 rounded-lg border border-gray-200">
        <h2 className="text-sm font-medium text-gray-700">Acesso Rapido</h2>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            variant="outline"
            size="sm"
            className="text-xs"
            onClick={() => router.push('/modulos/area-cliente/gerenciamento')}
          >
            <Key className="h-3 w-3 mr-1" /> Gerenciar Acessos
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-xs bg-amber-50 border-amber-300 hover:bg-amber-100 text-amber-700"
            onClick={() => window.open('/area-cliente', '_blank')}
          >
            <ExternalLink className="h-3 w-3 mr-1" /> Abrir Portal do Cliente
          </Button>
          <Button
            variant="outline"
            size="sm"
            className="text-xs"
            onClick={() => router.push('/modulos/gestao-pessoas/ged/kits')}
          >
            <FolderOpen className="h-3 w-3 mr-1" /> Kits Documentais (Admin)
          </Button>
        </div>
      </div>
    </div>
  );
}
