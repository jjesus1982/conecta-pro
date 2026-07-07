'use client';

import { FileWarning, AlertTriangle, BarChart3, RefreshCw } from 'lucide-react';
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
import { useCATs, useTaxaAcidente } from '@/hooks/sst';

function getGravidadeBadge(gravidade: string) {
  const styles: Record<string, string> = {
    leve: 'bg-green-100 text-green-800',
    medio: 'bg-yellow-100 text-yellow-800',
    grave: 'bg-orange-100 text-orange-800',
    critico: 'bg-red-100 text-red-800',
  };
  const labels: Record<string, string> = {
    leve: 'Leve',
    medio: 'Medio',
    grave: 'Grave',
    critico: 'Critico',
  };
  return (
    <Badge className={styles[gravidade] || 'bg-gray-100 text-gray-800'}>
      {labels[gravidade] || gravidade}
    </Badge>
  );
}

function getStatusBadge(status: string) {
  const styles: Record<string, string> = {
    aberta: 'bg-blue-100 text-blue-800',
    em_analise: 'bg-yellow-100 text-yellow-800',
    encerrada: 'bg-green-100 text-green-800',
    cancelada: 'bg-gray-100 text-gray-800',
  };
  const labels: Record<string, string> = {
    aberta: 'Aberta',
    em_analise: 'Em Analise',
    encerrada: 'Encerrada',
    cancelada: 'Cancelada',
  };
  return (
    <Badge className={styles[status] || 'bg-gray-100 text-gray-800'}>
      {labels[status] || status}
    </Badge>
  );
}

export default function CATPage() {
  const { data: catsData, isLoading: catsLoading, error: catsError, refetch } = useCATs();
  const { data: taxaData, isLoading: taxaLoading } = useTaxaAcidente();

  const handleRefresh = async () => {
    try {
      await refetch();
      toast.success('Dados atualizados', { duration: 4000 });
    } catch {
      toast.error('Erro ao atualizar dados', { duration: 5000 });
    }
  };

  const cats = catsData?.cats ?? [];
  const totalCATs = catsData?.total ?? 0;
  const taxaAcidente = taxaData?.taxa_acidente_percentual ?? 0;
  const totalColaboradores = taxaData?.total_colaboradores ?? 0;

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2 text-[hsl(var(--foreground))]">
            <FileWarning className="h-6 w-6" />
            CAT - Comunicacao de Acidente de Trabalho
          </h1>
          <p className="text-muted-foreground">
            Registro e acompanhamento de acidentes de trabalho
          </p>
        </div>
        <Button variant="outline" onClick={handleRefresh} disabled={catsLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${catsLoading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total de CATs</CardTitle>
            <FileWarning className="h-4 w-4" style={{ color: '#FF6B35' }} />
          </CardHeader>
          <CardContent>
            {catsLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums" style={{ color: '#FF6B35' }}>{totalCATs}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Taxa de Acidente</CardTitle>
            <BarChart3 className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {taxaLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{taxaAcidente.toFixed(2)}%</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Colaboradores</CardTitle>
            <BarChart3 className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {taxaLoading ? (
              <div className="h-8 w-16 animate-pulse rounded bg-muted" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{totalColaboradores}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Error */}
      {catsError && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">Erro ao carregar CATs</p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Registro de CATs</CardTitle>
          <CardDescription>
            Lista de Comunicacoes de Acidente de Trabalho registradas.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-0">
          {catsLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : cats.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileWarning className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhuma CAT registrada</h3>
              <p className="mt-2">Nao ha Comunicacoes de Acidente de Trabalho no sistema.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>CAT ID</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead>Local</TableHead>
                  <TableHead>Gravidade</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {cats.map((cat) => (
                  <TableRow key={cat.cat_id}>
                    <TableCell className="text-sm font-mono">
                      {cat.cat_id.length > 8
                        ? `${cat.cat_id.substring(0, 8)}...`
                        : cat.cat_id}
                    </TableCell>
                    <TableCell className="text-sm">{cat.tipo}</TableCell>
                    <TableCell className="text-sm">
                      {new Date(cat.data).toLocaleDateString('pt-BR')}
                    </TableCell>
                    <TableCell className="text-sm">{cat.local}</TableCell>
                    <TableCell>{getGravidadeBadge(cat.gravidade)}</TableCell>
                    <TableCell>{getStatusBadge(cat.status)}</TableCell>
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
