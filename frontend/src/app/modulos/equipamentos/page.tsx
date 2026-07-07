'use client';

import { Wrench, Package, Repeat, Settings, AlertTriangle, Box, ArrowRight } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
;
import { useRouter } from 'next/navigation';
import { useEquipmentStats, useEquipmentNeedingMaintenance } from '@/hooks/equipment';

const subPages = [
  {
    title: 'Patrimonio',
    description: 'Cadastro e controle de equipamentos do parque tecnologico',
    icon: Package,
    href: '/modulos/equipamentos/patrimonio',
    color: 'text-blue-600',
    bg: 'bg-blue-50',
  },
  {
    title: 'Comodatos',
    description: 'Gestao de equipamentos em comodato com clientes',
    icon: Repeat,
    href: '/modulos/equipamentos/comodatos',
    color: 'text-purple-600',
    bg: 'bg-purple-50',
  },
  {
    title: 'Manutencoes',
    description: 'Manutencoes preventivas e corretivas dos equipamentos',
    icon: Settings,
    href: '/modulos/equipamentos/manutencoes',
    color: 'text-orange-600',
    bg: 'bg-orange-50',
  },
];

export default function EquipamentosPage() {
  const router = useRouter();
  const { data: stats, isLoading: statsLoading } = useEquipmentStats();
  const { data: needingMaintenance } = useEquipmentNeedingMaintenance();

  const alertCount = needingMaintenance?.length ?? stats?.needs_maintenance ?? 0;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="font-display text-2xl font-bold flex items-center gap-2">
          <Wrench className="h-6 w-6" />
          Equipamentos
        </h1>
        <p className="text-muted-foreground">
          Controle de patrimonio, comodatos de equipamentos e gestao de manutencoes preventivas e corretivas.
        </p>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Equipamentos</CardTitle>
            <Box className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums">{stats?.total ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Estoque</CardTitle>
            <Package className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{stats?.in_stock ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Manutencao</CardTitle>
            <Settings className="h-4 w-4 text-orange-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-orange-600">{stats?.in_maintenance ?? 0}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Alertas</CardTitle>
            <AlertTriangle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {statsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{alertCount}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Sub-page navigation cards */}
      <div className="grid gap-4 md:grid-cols-3">
        {subPages.map((page) => (
          <Card
            key={page.href}
            className="cursor-pointer transition-all hover:shadow-md hover:border-primary/30"
            onClick={() => router.push(page.href)}
          >
            <CardContent className="flex items-center gap-4 p-6">
              <div className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-lg ${page.bg}`}>
                <page.icon className={`h-6 w-6 ${page.color}`} />
              </div>
              <div className="flex-1 min-w-0">
                <h3 className="font-semibold">{page.title}</h3>
                <p className="text-sm text-muted-foreground">{page.description}</p>
              </div>
              <ArrowRight className="h-5 w-5 shrink-0 text-muted-foreground" />
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
