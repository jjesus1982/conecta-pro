'use client';

import { useQuery } from '@tanstack/react-query';
import {
  AlertCircle,
  AlertTriangle,
  CalendarClock,
  CheckCircle2,
  HelpCircle,
  RefreshCw,
} from 'lucide-react';
import { useMemo, useState } from 'react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  apiErrorDetail,
  sstService,
  type CalendarioLegalCriticidade,
  type CalendarioLegalItem,
} from '@/lib/services/sst';

const CATEGORIA_LABELS: Record<string, string> = {
  pcmso: 'PCMSO (NR-7)',
  ltcat: 'LTCAT',
  pgr: 'PGR (NR-1)',
  epi_ca: 'CA de EPI (NR-6)',
  treinamento_nr: 'Treinamento NR',
  aso: 'ASO (NR-7)',
  ficha_epi: 'Ficha de EPI (NR-6)',
};

const CRITICIDADE_CONFIG: Record<
  CalendarioLegalCriticidade,
  { label: string; badge: string; border: string; Icon: typeof AlertCircle; iconColor: string }
> = {
  vencido: {
    label: 'Vencido',
    badge: 'bg-red-100 text-red-800',
    border: 'border-l-red-500',
    Icon: AlertCircle,
    iconColor: 'text-red-600',
  },
  atencao: {
    label: 'Vence em ate 30 dias',
    badge: 'bg-amber-100 text-amber-800',
    border: 'border-l-amber-500',
    Icon: AlertTriangle,
    iconColor: 'text-amber-600',
  },
  ok: {
    label: 'Em dia',
    badge: 'bg-green-100 text-green-800',
    border: 'border-l-green-500',
    Icon: CheckCircle2,
    iconColor: 'text-green-600',
  },
  sem_data: {
    label: 'Sem data registrada',
    badge: 'bg-gray-100 text-gray-700',
    border: 'border-l-gray-400',
    Icon: HelpCircle,
    iconColor: 'text-gray-500',
  },
};

const ORDEM: Record<CalendarioLegalCriticidade, number> = {
  vencido: 0,
  atencao: 1,
  ok: 2,
  sem_data: 3,
};

function formatDias(item: CalendarioLegalItem): string {
  if (item.dias_restantes === null) return 'sem data registrada no banco';
  if (item.dias_restantes < 0) {
    const d = Math.abs(item.dias_restantes);
    return `vencido ha ${d} dia${d === 1 ? '' : 's'}`;
  }
  if (item.dias_restantes === 0) return 'vence HOJE';
  return `faltam ${item.dias_restantes} dia${item.dias_restantes === 1 ? '' : 's'}`;
}

export default function CalendarioLegalPage() {
  const [categoria, setCategoria] = useState<string>('all');

  const { data, isLoading, error, refetch, isFetching } = useQuery({
    queryKey: ['sst', 'calendario-legal'],
    queryFn: () => sstService.getCalendarioLegal(),
    staleTime: 5 * 60 * 1000,
  });

  const itens = useMemo(() => {
    const lista = (data?.itens ?? []).filter(
      (i) => categoria === 'all' || i.categoria === categoria,
    );
    return [...lista].sort((a, b) => {
      const ord = (ORDEM[a.criticidade] ?? 9) - (ORDEM[b.criticidade] ?? 9);
      if (ord !== 0) return ord;
      return (a.vencimento ?? '9999-12-31').localeCompare(b.vencimento ?? '9999-12-31');
    });
  }, [data, categoria]);

  const categoriasPresentes = useMemo(() => {
    const set = new Set((data?.itens ?? []).map((i) => i.categoria));
    return Array.from(set);
  }, [data]);

  const resumo = data?.resumo;

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <CalendarClock className="h-6 w-6" />
            Calendario Legal SST
          </h1>
          <p className="text-muted-foreground">
            Radar unico de TODOS os vencimentos legais do modulo: PCMSO, LTCAT, PGR, CAs de EPI,
            treinamentos NR, ASOs e fichas de EPI. Tudo por fato no banco — itens sem data aparecem
            como &quot;sem data registrada&quot; (honesto), nunca inventados.
          </p>
        </div>
        <Button variant="outline" onClick={() => refetch()} disabled={isFetching}>
          <RefreshCw className={`h-4 w-4 mr-2 ${isFetching ? 'animate-spin' : ''}`} />
          Atualizar
        </Button>
      </div>

      {/* Resumo */}
      <div className="grid gap-4 md:grid-cols-4">
        {(['vencido', 'atencao', 'ok', 'sem_data'] as CalendarioLegalCriticidade[]).map((crit) => {
          const cfg = CRITICIDADE_CONFIG[crit];
          return (
            <Card key={crit}>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">{cfg.label}</CardTitle>
                <cfg.Icon className={`h-4 w-4 ${cfg.iconColor}`} />
              </CardHeader>
              <CardContent>
                {isLoading ? (
                  <div className="h-8 w-16 animate-pulse rounded bg-muted" />
                ) : (
                  <div className={`font-data text-2xl font-semibold tabular-nums ${cfg.iconColor}`}>
                    {resumo?.[crit] ?? 0}
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {/* Filtro por categoria */}
      <Card>
        <CardContent className="pt-6">
          <div className="flex items-center gap-4">
            <Select value={categoria} onValueChange={setCategoria}>
              <SelectTrigger className="w-[260px]" aria-label="Filtro de categoria">
                <SelectValue placeholder="Categoria" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">Todas as categorias</SelectItem>
                {categoriasPresentes.map((cat) => (
                  <SelectItem key={cat} value={cat}>
                    {CATEGORIA_LABELS[cat] ?? cat}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {data?.gerado_em && (
              <span className="text-xs text-muted-foreground">
                Gerado em {new Date(`${data.gerado_em}T12:00:00`).toLocaleDateString('pt-BR')} —{' '}
                {data.total} item(ns) no radar
              </span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Erro */}
      {error != null && (
        <div className="bg-destructive/10 border border-destructive/20 rounded-lg p-4 flex items-center gap-3">
          <AlertCircle className="h-5 w-5 text-destructive" />
          <p className="text-sm text-destructive flex-1">
            {apiErrorDetail(error, 'Erro ao carregar o calendario legal')}
          </p>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        </div>
      )}

      {/* Linha do tempo (ordenada por urgencia) */}
      {isLoading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
        </div>
      ) : itens.length === 0 ? (
        <Card>
          <CardContent className="text-center py-12 text-muted-foreground">
            <CalendarClock className="h-16 w-16 mx-auto mb-4 opacity-50" />
            <h3 className="text-lg font-medium">Nenhum item no radar</h3>
            <p className="mt-2">Nao ha vencimentos legais registrados para esta categoria.</p>
          </CardContent>
        </Card>
      ) : (
        <div className="space-y-3">
          {itens.map((item, idx) => {
            const cfg = CRITICIDADE_CONFIG[item.criticidade] ?? CRITICIDADE_CONFIG.sem_data;
            return (
              <Card
                key={`${item.categoria}-${item.titulo}-${idx}`}
                className={`border-l-4 ${cfg.border}`}
              >
                <CardHeader className="pb-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <CardTitle className="text-base flex items-center gap-2">
                      <cfg.Icon className={`h-4 w-4 shrink-0 ${cfg.iconColor}`} />
                      {item.titulo}
                    </CardTitle>
                    <div className="flex items-center gap-2">
                      <Badge variant="outline">
                        {CATEGORIA_LABELS[item.categoria] ?? item.categoria}
                      </Badge>
                      <Badge className={cfg.badge}>{cfg.label}</Badge>
                    </div>
                  </div>
                  <CardDescription className="tabular-nums">
                    {item.vencimento
                      ? `Vencimento: ${new Date(`${item.vencimento}T12:00:00`).toLocaleDateString('pt-BR')} — ${formatDias(item)}`
                      : formatDias(item)}
                  </CardDescription>
                </CardHeader>
                <CardContent className="pt-0 space-y-1">
                  <p className="text-sm">{item.acao_sugerida}</p>
                  <p className="text-xs text-muted-foreground font-mono">Fonte: {item.fonte}</p>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
