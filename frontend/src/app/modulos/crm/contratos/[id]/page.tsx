'use client';

import { useParams, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, FileSignature, Calendar, DollarSign, User, AlertCircle } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { customInstance } from '@/lib/api-client';
import { formatCurrency } from '@/lib/utils';

const STATUS_BADGE: Record<string, string> = {
  draft: 'bg-gray-100 text-gray-800',
  active: 'bg-green-100 text-green-800',
  suspended: 'bg-yellow-100 text-yellow-800',
  terminated: 'bg-red-100 text-red-800',
};

const STATUS_LABEL: Record<string, string> = {
  draft: 'Rascunho',
  active: 'Ativo',
  suspended: 'Suspenso',
  terminated: 'Encerrado',
};

const formatDate = (date: string | null | undefined) => {
  if (!date) return '-';
  try { return new Date(date).toLocaleDateString('pt-BR'); } catch { return date; }
};

export default function ContratoDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const { data: contract, isLoading, error } = useQuery({
    queryKey: ['crm-contract', id],
    queryFn: () => customInstance<Record<string, unknown>>({ url: `/api/v1/crm/contracts/${id}`, method: 'GET' }),
    enabled: !!id,
  });

  const c = contract as Record<string, unknown> | undefined;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="icon" onClick={() => router.back()}>
          <ArrowLeft className="h-4 w-4" />
        </Button>
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <FileSignature className="h-6 w-6" />
            {isLoading ? 'Carregando...' : ((c?.number || c?.numero || c?.contract_number) as string) || 'Contrato'}
          </h1>
          <p className="text-muted-foreground text-sm">Detalhes do contrato</p>
        </div>
      </div>

      {error && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive">Erro ao carregar contrato</p>
        </div>
      )}

      {isLoading ? (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : c ? (
        <div className="grid gap-6 md:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <FileSignature className="h-4 w-4" />
                Informações Gerais
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground text-xs mb-1">Número</p>
                  <p className="font-medium">{((c.number || c.numero || c.contract_number) as string) || '-'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs mb-1">Status</p>
                  <Badge className={STATUS_BADGE[(c.status as string) || ''] || 'bg-gray-100 text-gray-800'}>
                    {STATUS_LABEL[(c.status as string) || ''] || (c.status as string) || '-'}
                  </Badge>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs mb-1">Cliente</p>
                  <p>{((c.client_name || c.cliente) as string) || '-'}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs mb-1">Tipo</p>
                  <p>{((c.type || c.tipo || c.contract_type) as string) || '-'}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <DollarSign className="h-4 w-4" />
                Valores
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground text-xs mb-1">Valor Mensal</p>
                  <p className="font-medium text-lg">{formatCurrency((c.monthly_value || c.valor_mensal || 0) as number)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs mb-1">Valor Anual</p>
                  <p>{formatCurrency(((c.monthly_value || c.valor_mensal || 0) as number) * 12)}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <Calendar className="h-4 w-4" />
                Vigência
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-2 gap-4 text-sm">
                <div>
                  <p className="text-muted-foreground text-xs mb-1">Início</p>
                  <p>{formatDate((c.start_date || c.data_inicio) as string)}</p>
                </div>
                <div>
                  <p className="text-muted-foreground text-xs mb-1">Término</p>
                  <p>{formatDate((c.end_date || c.data_fim) as string)}</p>
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base flex items-center gap-2">
                <User className="h-4 w-4" />
                Responsável
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="text-sm">
                <p className="text-muted-foreground text-xs mb-1">Gestor do contrato</p>
                <p>{((c.owner_name || c.responsavel || c.manager) as string) || '-'}</p>
              </div>
            </CardContent>
          </Card>

          {c.description || c.descricao || c.observacoes ? (
            <Card className="md:col-span-2">
              <CardHeader>
                <CardTitle className="text-base">Observações</CardTitle>
              </CardHeader>
              <CardContent>
                <p className="text-sm text-muted-foreground">
                  {((c.description || c.descricao || c.observacoes) as string)}
                </p>
              </CardContent>
            </Card>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
