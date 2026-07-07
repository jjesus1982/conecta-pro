'use client';

import { Settings, Building2, ToggleRight, Mail, RefreshCw, Users, Zap, AlertCircle, ArrowRight } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
;
import Link from 'next/link';
import { useConfigDashboard } from '@/hooks/useConfig';

const subModules = [
  {
    title: 'Tenants',
    description: 'Gestao de tenants, planos e status',
    href: '/modulos/configuracoes/tenants',
    icon: Building2,
    color: 'text-blue-600 bg-blue-50',
  },
  {
    title: 'Feature Flags',
    description: 'Controle de features e rollout gradual',
    href: '/modulos/configuracoes/feature-flags',
    icon: ToggleRight,
    color: 'text-purple-600 bg-purple-50',
  },
  {
    title: 'Sistema',
    description: 'Configs globais e settings por tenant',
    href: '/modulos/configuracoes/configuracoes-sistema',
    icon: Settings,
    color: 'text-orange-600 bg-orange-50',
  },
  {
    title: 'Templates',
    description: 'Templates de notificacao multi-canal',
    href: '/modulos/configuracoes/templates-notificacao',
    icon: Mail,
    color: 'text-green-600 bg-green-50',
  },
  {
    title: 'Usuários & Permissões',
    description: 'Gerir módulos acessíveis por usuário',
    href: '/modulos/configuracoes/usuarios',
    icon: Users,
    color: 'text-indigo-600 bg-indigo-50',
  },
];

export default function ConfiguracoesPage() {
  const { data: dashboard, isLoading, error, refetch } = useConfigDashboard();

  const getStatusBadge = (status: string) => {
    const map: Record<string, string> = {
      active: 'bg-green-100 text-green-800',
      trial: 'bg-blue-100 text-blue-800',
      suspended: 'bg-yellow-100 text-yellow-800',
      canceled: 'bg-red-100 text-red-800',
    };
    const labels: Record<string, string> = {
      active: 'Ativo',
      trial: 'Trial',
      suspended: 'Suspenso',
      canceled: 'Cancelado',
    };
    return (
      <Badge className={map[status] || 'bg-gray-100 text-gray-800'}>
        {labels[status] || status}
      </Badge>
    );
  };

  const getPlanBadge = (plan: string) => {
    const map: Record<string, string> = {
      free: 'bg-gray-100 text-gray-800',
      starter: 'bg-blue-100 text-blue-800',
      pro: 'bg-purple-100 text-purple-800',
      enterprise: 'bg-amber-100 text-amber-800',
    };
    return (
      <Badge className={map[plan] || 'bg-gray-100 text-gray-800'}>
        {plan.charAt(0).toUpperCase() + plan.slice(1)}
      </Badge>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Settings className="h-6 w-6" />
            Configurações
          </h1>
          <p className="text-muted-foreground">
            Dashboard do modulo de configuracoes do sistema
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar dashboard</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Tenants</CardTitle>
            <Building2 className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums">
              {isLoading ? '...' : dashboard?.total_tenants ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Ativos</CardTitle>
            <Users className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
              {isLoading ? '...' : dashboard?.active_tenants ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Trial</CardTitle>
            <Zap className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">
              {isLoading ? '...' : dashboard?.trial_tenants ?? 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Feature Flags Ativas</CardTitle>
            <ToggleRight className="h-4 w-4 text-purple-600" />
          </CardHeader>
          <CardContent>
            <div className="font-data text-2xl font-semibold tabular-nums text-purple-600">
              {isLoading ? '...' : dashboard?.active_feature_flags ?? 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Sub-modules Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {subModules.map((mod) => (
          <Link key={mod.href} href={mod.href}>
            <Card className="hover:shadow-md transition-shadow cursor-pointer h-full">
              <CardContent className="pt-6">
                <div className="flex items-start gap-3">
                  <div className={`p-2 rounded-lg ${mod.color}`}>
                    <mod.icon className="h-5 w-5" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="font-semibold text-sm">{mod.title}</h3>
                    <p className="text-xs text-muted-foreground mt-1">{mod.description}</p>
                  </div>
                  <ArrowRight className="h-4 w-4 text-muted-foreground flex-shrink-0 mt-1" />
                </div>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>

      {/* Recent Tenants */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-lg">Tenants Recentes</CardTitle>
          <Link href="/modulos/configuracoes/tenants">
            <Button variant="outline" size="sm">
              Ver todos
              <ArrowRight className="h-4 w-4 ml-1" />
            </Button>
          </Link>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : !dashboard?.recent_tenants?.length ? (
            <div className="text-center py-12 text-muted-foreground">
              <Building2 className="h-12 w-12 mx-auto mb-3 opacity-50" />
              <p className="text-sm">Nenhum tenant encontrado</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Email</TableHead>
                  <TableHead>Plano</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Criado em</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {dashboard.recent_tenants.slice(0, 5).map((tenant) => (
                  <TableRow key={tenant.id}>
                    <TableCell className="font-medium">{tenant.nome}</TableCell>
                    <TableCell className="text-muted-foreground">{tenant.email}</TableCell>
                    <TableCell>{getPlanBadge(tenant.plan)}</TableCell>
                    <TableCell>{getStatusBadge(tenant.status)}</TableCell>
                    <TableCell className="text-muted-foreground text-sm">
                      {new Date(tenant.created_at).toLocaleDateString('pt-BR')}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
