'use client';

import { Shield, AlertTriangle, BookOpen, Users, RefreshCw } from 'lucide-react';
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
import { useEstabilidade } from '@/hooks/sst';

export default function EstabilidadePage() {
  const { data, isLoading, error, refetch } = useEstabilidade();

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

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))] flex items-center gap-2">
            <Shield className="h-6 w-6" />
            Estabilidade Pos-Acidente
          </h1>
          <p className="text-muted-foreground">
            Controle de colaboradores em periodo de estabilidade provisoria
          </p>
        </div>
        <Button variant="outline" onClick={handleRefresh} disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Legal Reference */}
      <Card className="border-blue-200 bg-blue-50/50">
        <CardHeader className="pb-3">
          <CardTitle className="text-sm font-medium flex items-center gap-2">
            <BookOpen className="h-4 w-4 text-blue-600" />
            Fundamentacao Legal
          </CardTitle>
          <CardDescription>
            CCT 2026 - Clausula 29a: Estabilidade de 12 meses apos retorno de acidente de trabalho
            ou doenca ocupacional. O colaborador nao pode ser dispensado sem justa causa durante o
            periodo de estabilidade.
          </CardDescription>
        </CardHeader>
      </Card>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Colaboradores em Estabilidade</CardTitle>
            <Users className="h-4 w-4" style={{ color: '#FF6B35' }} />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums" style={{ color: '#FF6B35' }}>{total}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Vencendo em 30 dias</CardTitle>
            <AlertTriangle className="h-4 w-4 text-yellow-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-yellow-600">
                {colaboradores.filter((c) => c.dias_restantes <= 30).length}
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar dados de estabilidade</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Colaboradores em Estabilidade</CardTitle>
          <CardDescription>
            Lista de colaboradores com estabilidade provisoria ativa.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : colaboradores.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Shield className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum colaborador em estabilidade</h3>
              <p className="mt-2">
                Nao ha colaboradores em periodo de estabilidade provisoria no momento.
                Isso indica que nao houve afastamentos recentes por acidente de trabalho.
              </p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Cargo</TableHead>
                  <TableHead>Tipo Afastamento</TableHead>
                  <TableHead>Data Retorno</TableHead>
                  <TableHead>Estabilidade Ate</TableHead>
                  <TableHead>Dias Restantes</TableHead>
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
                    <TableCell className="text-sm">{col.tipo_afastamento}</TableCell>
                    <TableCell className="text-sm">
                      {col.data_retorno
                        ? new Date(col.data_retorno).toLocaleDateString('pt-BR')
                        : 'Nao retornou'}
                    </TableCell>
                    <TableCell className="text-sm">
                      {new Date(col.estabilidade_ate).toLocaleDateString('pt-BR')}
                    </TableCell>
                    <TableCell>
                      {col.dias_restantes <= 30 ? (
                        <Badge className="bg-yellow-100 text-yellow-800">
                          {col.dias_restantes} dias
                        </Badge>
                      ) : (
                        <span className="text-sm">{col.dias_restantes} dias</span>
                      )}
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
