'use client';

import { UserX, AlertTriangle, DollarSign, Clock, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
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
import { toast } from 'sonner';
import { useAfastamentos, useAjudaMedicamento } from '@/hooks/sst';

function getStatusBadge(status: string) {
  const styles: Record<string, string> = {
    ativo: 'bg-yellow-100 text-yellow-800',
    encerrado: 'bg-green-100 text-green-800',
    prorrogado: 'bg-red-100 text-red-800',
  };
  const labels: Record<string, string> = {
    ativo: 'Ativo',
    encerrado: 'Encerrado',
    prorrogado: 'Prorrogado',
  };
  return (
    <Badge className={styles[status] || 'bg-gray-100 text-gray-800'}>
      {labels[status] || status}
    </Badge>
  );
}

function isVencido(data_fim_prevista: string | null, status: string): boolean {
  if (!data_fim_prevista || status !== 'ativo') return false;
  return new Date(data_fim_prevista) < new Date();
}

export default function AfastamentosPage() {
  const {
    data: afastamentosData,
    isLoading,
    error,
    refetch,
  } = useAfastamentos();
  const { data: ajudaData } = useAjudaMedicamento();

  const handleRefresh = async () => {
    try {
      await refetch();
      toast.success('Dados atualizados', { duration: 4000 });
    } catch {
      toast.error('Erro ao atualizar dados', { duration: 5000 });
    }
  };

  const afastamentos = afastamentosData?.afastamentos ?? [];
  const totalAfastados = afastamentos.filter((a) => a.status === 'ativo').length;
  const totalRegistros = afastamentosData?.total ?? 0;
  const taxaAfastamento =
    totalRegistros > 0
      ? ((totalAfastados / Math.max(totalRegistros, 1)) * 100).toFixed(1)
      : '0.0';
  const custoMensal = ajudaData?.custo_mensal_total ?? 0;

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2 text-[hsl(var(--foreground))]">
            <UserX className="h-6 w-6" />
            Afastamentos
          </h1>
          <p className="text-muted-foreground">
            Controle de afastamentos de colaboradores - SST
          </p>
        </div>
        <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Afastados Ativos</CardTitle>
            <UserX className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">{totalAfastados}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Taxa de Afastamento</CardTitle>
            <Clock className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{taxaAfastamento}%</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Custo Mensal Ajuda Medicamento</CardTitle>
            <DollarSign className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                {custoMensal.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar afastamentos</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Lista de Afastamentos</CardTitle>
          <CardDescription>
            Registro de todos os afastamentos de colaboradores.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : afastamentos.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <UserX className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum afastamento registrado</h3>
              <p className="mt-2">Nao ha afastamentos cadastrados no sistema.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Cargo</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Inicio</TableHead>
                  <TableHead>Fim Previsto</TableHead>
                  <TableHead>Dias</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {afastamentos.map((af) => (
                  <TableRow key={af.id}>
                    <TableCell>
                      <div className="font-medium">{af.employee_nome}</div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {af.employee_cargo}
                    </TableCell>
                    <TableCell className="text-sm">{af.tipo}</TableCell>
                    <TableCell className="text-sm">
                      {new Date(af.data_inicio).toLocaleDateString('pt-BR')}
                    </TableCell>
                    <TableCell className="text-sm">
                      <span className="flex items-center gap-1">
                        {af.data_fim_prevista
                          ? new Date(af.data_fim_prevista).toLocaleDateString('pt-BR')
                          : 'Indeterminado'}
                        {isVencido(af.data_fim_prevista, af.status) && (
                          <AlertTriangle className="h-4 w-4 text-red-500" />
                        )}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm">
                      {af.dias_previstos ?? '-'}
                    </TableCell>
                    <TableCell>{getStatusBadge(af.status)}</TableCell>
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
