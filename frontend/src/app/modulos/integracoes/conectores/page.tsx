'use client';

import { Plug, Search, RefreshCw, MoreHorizontal, Eye, AlertCircle } from 'lucide-react';
import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
;
import { useConnectors, useIntegrationAccounts } from '@/hooks/integrations';
import { ConnectorDetailModal } from '@/components/integracoes/connector-detail-modal';

export default function ConectoresPage() {
  const [search, setSearch] = useState('');
  const [selectedConnector, setSelectedConnector] = useState<any | null>(null);
  const [detailOpen, setDetailOpen] = useState(false);

  const { data: connectorsData, isLoading, error, refetch } = useConnectors();
  const { data: accountsData } = useIntegrationAccounts();

  const connectors = connectorsData?.connectors || [];
  const accounts = accountsData?.items || [];

  const filteredConnectors = Array.isArray(connectors)
    ? connectors.filter((c: any) =>
        c.name?.toLowerCase().includes(search.toLowerCase()) ||
        c.type?.toLowerCase().includes(search.toLowerCase())
      )
    : [];

  const getActiveAccountsCount = (connectorName: string) => {
    if (!Array.isArray(accounts)) return 0;
    return accounts.filter(
      (a: any) => a.connector_name === connectorName && a.status === 'active'
    ).length;
  };

  const getStatusBadge = (status: string) => {
    const map: Record<string, string> = {
      healthy: 'bg-green-100 text-green-800',
      degraded: 'bg-yellow-100 text-yellow-800',
      offline: 'bg-red-100 text-red-800',
    };
    const labels: Record<string, string> = {
      healthy: 'Saudavel',
      degraded: 'Degradado',
      offline: 'Offline',
    };
    return (
      <Badge className={map[status] || 'bg-gray-100 text-gray-800'}>
        {labels[status] || status}
      </Badge>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <Plug className="h-6 w-6" />
            Conectores
          </h1>
          <p className="text-muted-foreground">
            Conectores de integracao disponíveis e seu estado de saude
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isLoading}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Search */}
      <Card>
        <CardContent className="pt-6">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Buscar por nome ou tipo..."
              className="pl-10"
            />
          </div>
        </CardContent>
      </Card>

      {/* Error */}
      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">
            Erro ao carregar conectores
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
            </div>
          ) : filteredConnectors.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <Plug className="h-16 w-16 mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-medium">Nenhum conector encontrado</h3>
              <p className="mt-2">Tente ajustar o filtro de busca</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Nome</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Contas Ativas</TableHead>
                  <TableHead className="w-[80px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredConnectors.map((connector: any) => (
                  <TableRow key={connector.name}>
                    <TableCell>
                      <div>
                        <div className="font-medium">{connector.name}</div>
                        {connector.description && (
                          <div className="text-xs text-muted-foreground truncate max-w-[300px]">
                            {connector.description}
                          </div>
                        )}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{connector.type || '-'}</Badge>
                    </TableCell>
                    <TableCell>{getStatusBadge(connector.status)}</TableCell>
                    <TableCell className="text-sm">
                      {getActiveAccountsCount(connector.name)}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem
                            onClick={() => {
                              setSelectedConnector(connector);
                              setDetailOpen(true);
                            }}
                          >
                            <Eye className="h-4 w-4 mr-2" />
                            Ver detalhes
                          </DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Detail Modal */}
      <ConnectorDetailModal
        isOpen={detailOpen}
        onClose={() => {
          setDetailOpen(false);
          setSelectedConnector(null);
        }}
        connector={selectedConnector}
      />
    </div>
  );
}
