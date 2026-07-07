'use client';

import { Pill, DollarSign, Users, BookOpen, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { toast } from 'sonner';
import { useAjudaMedicamento } from '@/hooks/sst';

export default function AjudaMedicamentoPage() {
  const { data, isLoading, error, refetch } = useAjudaMedicamento();

  const handleRefresh = async () => {
    try {
      await refetch();
      toast.success('Dados atualizados', { duration: 4000 });
    } catch {
      toast.error('Erro ao atualizar dados', { duration: 5000 });
    }
  };

  const colaboradores = data?.colaboradores ?? [];
  const total = data?.total ?? 0;
  const valorUnitario = data?.valor_unitario ?? 300;
  const custoMensal = data?.custo_mensal_total ?? 0;

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2 text-[hsl(var(--foreground))]">
            <Pill className="h-6 w-6" />
            Ajuda Medicamento
          </h1>
          <p className="text-muted-foreground">
            Benefício previsto em convenção coletiva para colaboradores afastados
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
            <CardTitle className="text-sm font-medium">Total Beneficiarios</CardTitle>
            <Users className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{total}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Valor Unitario</CardTitle>
            <DollarSign className="h-4 w-4 text-green-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-green-600">
                {valorUnitario.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Custo Mensal Total</CardTitle>
            <DollarSign className="h-4 w-4" style={{ color: '#FF6B35' }} />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums" style={{ color: '#FF6B35' }}>
                {custoMensal.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Legal Reference */}
      <Card className="border-blue-200 bg-blue-50/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-blue-600" />
            Fundamentacao Legal
          </CardTitle>
          <CardDescription>
            CCT 2026 - Clausula 15a SINDECOMPRESTS: Auxilio medicamento mensal no valor de R$ 300,00
            para colaboradores afastados por doenca ocupacional ou acidente de trabalho.
          </CardDescription>
        </CardHeader>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <Pill className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar dados de ajuda medicamento</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Colaboradores com Ajuda Medicamento</CardTitle>
          <CardDescription>
            Lista de colaboradores recebendo o beneficio de ajuda medicamento.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : colaboradores.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Pill className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum beneficiario ativo</h3>
              <p className="mt-2">Nao ha colaboradores recebendo ajuda medicamento no momento.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Cargo</TableHead>
                  <TableHead>Data Início Afastamento</TableHead>
                  <TableHead>Valor Mensal</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {colaboradores.map((col) => (
                  <TableRow key={col.employee_id}>
                    <TableCell>
                      <div className="font-medium">{col.nome}</div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {col.cargo}
                    </TableCell>
                    <TableCell className="text-sm">
                      {new Date(col.data_inicio_afastamento).toLocaleDateString('pt-BR')}
                    </TableCell>
                    <TableCell className="text-sm font-medium">
                      {col.valor_mensal.toLocaleString('pt-BR', {
                        style: 'currency',
                        currency: 'BRL',
                      })}
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
