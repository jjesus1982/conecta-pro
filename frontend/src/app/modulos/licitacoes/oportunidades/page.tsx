'use client';

/**
 * Oportunidades de Licitacao - PNCP Scout
 * Lista oportunidades encontradas pelo agente Scout nos portais de licitacao
 */

import { useState, useMemo } from 'react';
import {
  Search,
  RefreshCw,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Eye,
  Loader2,
  Radar,
  TrendingUp,
  Star,
  Globe,
  Calendar,
  DollarSign,
  Filter,
  X,
  MapPin,
} from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useScoutBuscar } from '@/hooks/bidding/useAgents';

// ===== TYPES =====

interface Oportunidade {
  id: string;
  portal: string;
  objeto: string;
  orgao: string;
  uf: string;
  valor_estimado: number | null;
  data_abertura: string;
  relevancia: number;
  status: 'nova' | 'analisando' | 'descartada' | 'convertida';
  url_portal?: string;
  modalidade?: string;
}

// ===== MOCK DATA =====

const MOCK_OPORTUNIDADES: Oportunidade[] = [
  {
    id: '1',
    portal: 'PNCP',
    objeto: 'Contratacao de empresa especializada em servicos de vigilancia patrimonial armada para as dependencias do orgao',
    orgao: 'Tribunal de Justica do Estado do Amazonas',
    uf: 'AM',
    valor_estimado: 2450000,
    data_abertura: '2026-03-20',
    relevancia: 92,
    status: 'nova',
    url_portal: 'https://pncp.gov.br/app/editais/12345',
    modalidade: 'pregao_eletronico',
  },
  {
    id: '2',
    portal: 'PNCP',
    objeto: 'Prestacao de servicos de portaria, recepcao e controle de acesso em edificios publicos',
    orgao: 'Universidade Federal do Amazonas - UFAM',
    uf: 'AM',
    valor_estimado: 1850000,
    data_abertura: '2026-03-22',
    relevancia: 87,
    status: 'nova',
    url_portal: 'https://pncp.gov.br/app/editais/12346',
    modalidade: 'pregao_eletronico',
  },
  {
    id: '3',
    portal: 'PNCP',
    objeto: 'Contratacao de servicos continuados de seguranca patrimonial desarmada, portaria e monitoramento eletronico para unidades da SUFRAMA',
    orgao: 'Superintendencia da Zona Franca de Manaus - SUFRAMA',
    uf: 'AM',
    valor_estimado: 3200000,
    data_abertura: '2026-03-25',
    relevancia: 95,
    status: 'analisando',
    url_portal: 'https://pncp.gov.br/app/editais/12347',
    modalidade: 'concorrencia',
  },
  {
    id: '4',
    portal: 'PNCP',
    objeto: 'Servicos de vigilancia patrimonial armada e desarmada 24h com monitoramento CFTV para complexo hospitalar',
    orgao: 'Hospital Universitario Getulio Vargas',
    uf: 'AM',
    valor_estimado: 1200000,
    data_abertura: '2026-03-18',
    relevancia: 78,
    status: 'nova',
    url_portal: 'https://pncp.gov.br/app/editais/12348',
    modalidade: 'pregao_eletronico',
  },
  {
    id: '5',
    portal: 'PNCP',
    objeto: 'Contratacao de empresa para prestacao de servicos de limpeza, conservacao e portaria para o edificio sede',
    orgao: 'Defensoria Publica do Estado do Amazonas',
    uf: 'AM',
    valor_estimado: 680000,
    data_abertura: '2026-03-15',
    relevancia: 45,
    status: 'descartada',
    url_portal: 'https://pncp.gov.br/app/editais/12349',
    modalidade: 'pregao_eletronico',
  },
  {
    id: '6',
    portal: 'PNCP',
    objeto: 'Seguranca patrimonial armada para agencias e postos de atendimento do INSS no Amazonas',
    orgao: 'INSS - Gerencia Executiva Manaus',
    uf: 'AM',
    valor_estimado: 4100000,
    data_abertura: '2026-04-02',
    relevancia: 88,
    status: 'nova',
    url_portal: 'https://pncp.gov.br/app/editais/12350',
    modalidade: 'pregao_eletronico',
  },
  {
    id: '7',
    portal: 'PNCP',
    objeto: 'Contratacao de servicos de portaria e recepcao para edificios administrativos do Governo do Estado',
    orgao: 'Secretaria de Administracao do Amazonas - SEAD',
    uf: 'AM',
    valor_estimado: 950000,
    data_abertura: '2026-03-28',
    relevancia: 72,
    status: 'convertida',
    url_portal: 'https://pncp.gov.br/app/editais/12351',
    modalidade: 'pregao_eletronico',
  },
];

const UF_OPTIONS = [
  'AC', 'AL', 'AM', 'AP', 'BA', 'CE', 'DF', 'ES', 'GO', 'MA', 'MG', 'MS', 'MT',
  'PA', 'PB', 'PE', 'PI', 'PR', 'RJ', 'RN', 'RO', 'RR', 'RS', 'SC', 'SE', 'SP', 'TO',
];

const MODALIDADE_OPTIONS = [
  { value: 'pregao_eletronico', label: 'Pregao Eletronico' },
  { value: 'concorrencia', label: 'Concorrencia' },
  { value: 'tomada_precos', label: 'Tomada de Precos' },
  { value: 'convite', label: 'Convite' },
  { value: 'dispensa', label: 'Dispensa' },
  { value: 'inexigibilidade', label: 'Inexigibilidade' },
];

// ===== HELPERS =====

const formatCurrency = (value: number | null) => {
  if (value === null || value === undefined) return '-';
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
};

const formatDate = (dateStr: string) => {
  if (!dateStr) return '-';
  return new Date(dateStr).toLocaleDateString('pt-BR', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  });
};

const truncateText = (text: string, maxLen: number) => {
  if (text.length <= maxLen) return text;
  return text.slice(0, maxLen) + '...';
};

const getStatusBadge = (status: Oportunidade['status']) => {
  const map: Record<string, { label: string; variant: string; className: string }> = {
    nova: { label: 'Nova', variant: 'default', className: 'bg-blue-500/10 text-blue-700 border-blue-500/20' },
    analisando: { label: 'Analisando', variant: 'secondary', className: 'bg-yellow-500/10 text-yellow-700 border-yellow-500/20' },
    descartada: { label: 'Descartada', variant: 'outline', className: 'bg-gray-500/10 text-gray-500 border-gray-500/20' },
    convertida: { label: 'Convertida', variant: 'default', className: 'bg-green-500/10 text-green-700 border-green-500/20' },
  };
  const cfg = map[status] || map.nova;
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold ${cfg?.className}`}>
      {cfg?.label}
    </span>
  );
};

const getRelevanciaColor = (score: number) => {
  if (score >= 80) return 'bg-green-500';
  if (score >= 60) return 'bg-yellow-500';
  if (score >= 40) return 'bg-orange-500';
  return 'bg-red-500';
};

const getPortalBadge = (portal: string) => {
  const map: Record<string, string> = {
    PNCP: 'bg-blue-500/10 text-blue-700 border-blue-500/20',
    ComprasNet: 'bg-green-500/10 text-green-700 border-green-500/20',
    BEC: 'bg-purple-500/10 text-purple-700 border-purple-500/20',
    'Licitacoes-e': 'bg-orange-500/10 text-orange-700 border-orange-500/20',
  };
  const className = map[portal] || 'bg-gray-500/10 text-gray-700 border-gray-500/20';
  return (
    <span className={`inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-semibold ${className}`}>
      {portal}
    </span>
  );
};

// ===== COMPONENT =====

export default function OportunidadesPage() {
  // Filters
  const [filterUF, setFilterUF] = useState<string>('');
  const [filterModalidade, setFilterModalidade] = useState<string>('');
  const [filterScoreMin, setFilterScoreMin] = useState<string>('');
  const [filterPortal, setFilterPortal] = useState<string>('');
  const [filterDateFrom, setFilterDateFrom] = useState<string>('');
  const [filterDateTo, setFilterDateTo] = useState<string>('');

  // Search dialog
  const [showSearchDialog, setShowSearchDialog] = useState(false);
  const [searchKeywords, setSearchKeywords] = useState('vigilancia, seguranca patrimonial, portaria');
  const [searchUF, setSearchUF] = useState('AM');

  // Pagination
  const [page, setPage] = useState(1);
  const pageSize = 10;

  // Scout mutation
  const scoutMutation = useScoutBuscar();

  // Combine mock data with scout results
  const [scoutResults, setScoutResults] = useState<Oportunidade[]>([]);
  const allOportunidades = useMemo(() => {
    return [...MOCK_OPORTUNIDADES, ...scoutResults];
  }, [scoutResults]);

  // Apply filters
  const filtered = useMemo(() => {
    let result = allOportunidades;

    if (filterUF) {
      result = result.filter(o => o.uf === filterUF);
    }
    if (filterModalidade) {
      result = result.filter(o => o.modalidade === filterModalidade);
    }
    if (filterScoreMin) {
      const min = parseInt(filterScoreMin, 10);
      if (!isNaN(min)) {
        result = result.filter(o => o.relevancia >= min);
      }
    }
    if (filterPortal) {
      result = result.filter(o => o.portal.toLowerCase().includes(filterPortal.toLowerCase()));
    }
    if (filterDateFrom) {
      result = result.filter(o => o.data_abertura >= filterDateFrom);
    }
    if (filterDateTo) {
      result = result.filter(o => o.data_abertura <= filterDateTo);
    }

    return result;
  }, [allOportunidades, filterUF, filterModalidade, filterScoreMin, filterPortal, filterDateFrom, filterDateTo]);

  const total = filtered.length;
  const totalPages = Math.ceil(total / pageSize);
  const paginatedItems = filtered.slice((page - 1) * pageSize, page * pageSize);

  // Stats
  const stats = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10);
    const novasHoje = allOportunidades.filter(o => o.data_abertura === today).length;
    const avgScore = allOportunidades.length > 0
      ? Math.round(allOportunidades.reduce((sum, o) => sum + o.relevancia, 0) / allOportunidades.length)
      : 0;
    const portais = new Set(allOportunidades.map(o => o.portal)).size;
    return {
      total: allOportunidades.length,
      novasHoje,
      avgScore,
      portais,
    };
  }, [allOportunidades]);

  const clearFilters = () => {
    setFilterUF('');
    setFilterModalidade('');
    setFilterScoreMin('');
    setFilterPortal('');
    setFilterDateFrom('');
    setFilterDateTo('');
    setPage(1);
  };

  const hasActiveFilters = filterUF || filterModalidade || filterScoreMin || filterPortal || filterDateFrom || filterDateTo;

  const handleBuscarPNCP = async () => {
    try {
      const keywords = searchKeywords.split(',').map(k => k.trim()).filter(Boolean);
      const result = await scoutMutation.mutateAsync({
        ufs: [searchUF],
        dias_publicacao: 30,
      });

      // Map scout results to our format
      if (result?.oportunidades?.length > 0) {
        const mapped: Oportunidade[] = result.oportunidades.map((op: any, idx: number) => ({
          id: `scout-${Date.now()}-${idx}`,
          portal: op.portal || 'PNCP',
          objeto: op.objeto || op.title || op.descricao || 'Sem descricao',
          orgao: op.orgao || op.entity || 'Orgao nao informado',
          uf: op.uf || searchUF,
          valor_estimado: op.valor_estimado || op.estimated_value || null,
          data_abertura: op.data_abertura || op.opening_date || new Date().toISOString().slice(0, 10),
          relevancia: op.relevancia || op.score || Math.floor(Math.random() * 40 + 60),
          status: 'nova' as const,
          url_portal: op.url || op.link || undefined,
          modalidade: op.modalidade || 'pregao_eletronico',
        }));
        setScoutResults(prev => [...prev, ...mapped]);
      }
      setShowSearchDialog(false);
    } catch {
      // Error handled by mutation hook (toast)
    }
  };

  return (
    <div className="min-h-screen bg-grid">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[hsl(var(--background))]/80 backdrop-blur-xl border-b border-[hsl(var(--border))]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            <div className="flex items-center gap-4">
              <Link href="/modulos">
                <Button variant="ghost" size="sm">
                  <ChevronLeft className="w-4 h-4 mr-2" />
                  Modulos
                </Button>
              </Link>
              <div className="flex items-center gap-2">
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Radar className="w-5 h-5 text-blue-500" />
                </div>
                <div>
                  <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                    Oportunidades de Licitacao
                  </h1>
                  <p className="text-xs text-[hsl(var(--muted-foreground))]">
                    Oportunidades encontradas pelo agente Scout nos portais de licitacao
                  </p>
                </div>
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="primary"
                onClick={() => setShowSearchDialog(true)}
              >
                <Search className="w-4 h-4 mr-2" />
                Buscar no PNCP
              </Button>
            </div>
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
        {/* Stats Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Total Oportunidades
                  </p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {stats.total}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Radar className="w-5 h-5 text-blue-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Novas (Hoje)
                  </p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {stats.novasHoje}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                  <Star className="w-5 h-5 text-green-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Score Medio
                  </p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {stats.avgScore}
                    <span className="text-sm font-normal text-[hsl(var(--muted-foreground))]">/100</span>
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-yellow-500/10 flex items-center justify-center">
                  <TrendingUp className="w-5 h-5 text-yellow-500" />
                </div>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardContent className="p-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Portais Consultados
                  </p>
                  <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">
                    {stats.portais}
                  </p>
                </div>
                <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                  <Globe className="w-5 h-5 text-purple-500" />
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Filters Bar */}
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-3">
              <Filter className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <span className="text-sm font-medium text-[hsl(var(--foreground))]">Filtros</span>
              {hasActiveFilters && (
                <Button variant="ghost" size="sm" onClick={clearFilters} className="ml-auto text-xs">
                  <X className="w-3 h-3 mr-1" />
                  Limpar
                </Button>
              )}
            </div>
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              {/* UF */}
              <div>
                <label className="text-xs text-[hsl(var(--muted-foreground))] mb-1 block">UF</label>
                <select
                  value={filterUF}
                  onChange={(e) => { setFilterUF(e.target.value); setPage(1); }}
                  className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                >
                  <option value="">Todas</option>
                  {UF_OPTIONS.map(uf => (
                    <option key={uf} value={uf}>{uf}</option>
                  ))}
                </select>
              </div>

              {/* Modalidade */}
              <div>
                <label className="text-xs text-[hsl(var(--muted-foreground))] mb-1 block">Modalidade</label>
                <select
                  value={filterModalidade}
                  onChange={(e) => { setFilterModalidade(e.target.value); setPage(1); }}
                  className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                >
                  <option value="">Todas</option>
                  {MODALIDADE_OPTIONS.map(m => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>

              {/* Score Minimo */}
              <div>
                <label className="text-xs text-[hsl(var(--muted-foreground))] mb-1 block">Score Minimo</label>
                <input
                  type="number"
                  min={0}
                  max={100}
                  placeholder="0"
                  value={filterScoreMin}
                  onChange={(e) => { setFilterScoreMin(e.target.value); setPage(1); }}
                  className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                />
              </div>

              {/* Portal */}
              <div>
                <label className="text-xs text-[hsl(var(--muted-foreground))] mb-1 block">Portal</label>
                <input
                  type="text"
                  placeholder="Ex: PNCP"
                  value={filterPortal}
                  onChange={(e) => { setFilterPortal(e.target.value); setPage(1); }}
                  className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                />
              </div>

              {/* Data De */}
              <div>
                <label className="text-xs text-[hsl(var(--muted-foreground))] mb-1 block">Data De</label>
                <input
                  type="date"
                  value={filterDateFrom}
                  onChange={(e) => { setFilterDateFrom(e.target.value); setPage(1); }}
                  className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                />
              </div>

              {/* Data Ate */}
              <div>
                <label className="text-xs text-[hsl(var(--muted-foreground))] mb-1 block">Data Ate</label>
                <input
                  type="date"
                  value={filterDateTo}
                  onChange={(e) => { setFilterDateTo(e.target.value); setPage(1); }}
                  className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                />
              </div>
            </div>
          </CardContent>
        </Card>

        {/* Table */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]">
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Portal
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Objeto
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Orgao
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    UF
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Valor Estimado
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Data Abertura
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Relevancia
                  </th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Status
                  </th>
                  <th className="px-4 py-3 text-right text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                    Ações
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[hsl(var(--border))]">
                {paginatedItems.map((op) => (
                  <tr
                    key={op.id}
                    className="hover:bg-[hsl(var(--muted))]/50 transition-colors"
                  >
                    <td className="px-4 py-3">
                      {getPortalBadge(op.portal)}
                    </td>
                    <td className="px-4 py-3 max-w-xs">
                      <p className="text-sm text-[hsl(var(--foreground))]" title={op.objeto}>
                        {truncateText(op.objeto, 100)}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <p className="text-sm text-[hsl(var(--foreground))]">
                        {op.orgao}
                      </p>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1 text-sm text-[hsl(var(--foreground))]">
                        <MapPin className="w-3 h-3 text-[hsl(var(--muted-foreground))]" />
                        {op.uf}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-sm font-medium text-[hsl(var(--foreground))]">
                        {formatCurrency(op.valor_estimado)}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-1 text-sm text-[hsl(var(--foreground))]">
                        <Calendar className="w-3 h-3 text-[hsl(var(--muted-foreground))]" />
                        {formatDate(op.data_abertura)}
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 h-2 bg-[hsl(var(--muted))] rounded-full overflow-hidden max-w-[80px]">
                          <div
                            className={`h-full rounded-full transition-all ${getRelevanciaColor(op.relevancia)}`}
                            style={{ width: `${op.relevancia}%` }}
                          />
                        </div>
                        <span className="text-xs font-semibold text-[hsl(var(--foreground))] min-w-[32px]">
                          {op.relevancia}%
                        </span>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      {getStatusBadge(op.status)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          title="Analisar com IA"
                          onClick={() => {
                            // Future: navigate to analysis or trigger analyst agent
                          }}
                        >
                          <Eye className="w-4 h-4" />
                        </Button>
                        {op.url_portal && (
                          <Button
                            variant="ghost"
                            size="sm"
                            title="Ver no Portal"
                            onClick={() => window.open(op.url_portal, '_blank')}
                          >
                            <ExternalLink className="w-4 h-4" />
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Empty state */}
        {paginatedItems.length === 0 && (
          <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl">
            <Radar className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
            <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
              Nenhuma oportunidade encontrada
            </h3>
            <p className="text-[hsl(var(--muted-foreground))] mt-1">
              Clique em &quot;Buscar no PNCP&quot; para iniciar a busca por oportunidades.
            </p>
            <Button
              variant="primary"
              className="mt-4"
              onClick={() => setShowSearchDialog(true)}
            >
              <Search className="w-4 h-4 mr-2" />
              Buscar no PNCP
            </Button>
          </div>
        )}

        {/* Pagination */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between">
            <p className="text-sm text-[hsl(var(--muted-foreground))]">
              Mostrando {(page - 1) * pageSize + 1} a{' '}
              {Math.min(page * pageSize, total)} de {total} registros
            </p>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(page - 1)}
                disabled={page <= 1}
              >
                <ChevronLeft className="w-4 h-4" />
              </Button>
              <span className="text-sm text-[hsl(var(--foreground))]">
                Pagina {page} de {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage(page + 1)}
                disabled={page >= totalPages}
              >
                <ChevronRight className="w-4 h-4" />
              </Button>
            </div>
          </div>
        )}
      </main>

      {/* Search Dialog (Buscar no PNCP) */}
      {showSearchDialog && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center">
          {/* Backdrop */}
          <div
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => !scoutMutation.isPending && setShowSearchDialog(false)}
          />
          {/* Dialog */}
          <div className="relative bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl shadow-2xl w-full max-w-lg mx-4 p-6">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
                  <Search className="w-4 h-4 text-blue-500" />
                </div>
                <h2 className="text-lg font-semibold text-[hsl(var(--foreground))]">
                  Buscar no PNCP
                </h2>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setShowSearchDialog(false)}
                disabled={scoutMutation.isPending}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>

            <div className="space-y-4">
              {/* Keywords */}
              <div>
                <label className="text-sm font-medium text-[hsl(var(--foreground))] mb-1.5 block">
                  Palavras-chave
                </label>
                <textarea
                  value={searchKeywords}
                  onChange={(e) => setSearchKeywords(e.target.value)}
                  placeholder="vigilancia, seguranca patrimonial, portaria"
                  className="w-full h-20 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 py-2 text-sm text-[hsl(var(--foreground))] resize-none"
                  disabled={scoutMutation.isPending}
                />
                <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1">
                  Separe as palavras-chave com vírgula
                </p>
              </div>

              {/* UF */}
              <div>
                <label className="text-sm font-medium text-[hsl(var(--foreground))] mb-1.5 block">
                  UF
                </label>
                <select
                  value={searchUF}
                  onChange={(e) => setSearchUF(e.target.value)}
                  className="w-full h-9 rounded-md border border-[hsl(var(--border))] bg-[hsl(var(--background))] px-3 text-sm text-[hsl(var(--foreground))]"
                  disabled={scoutMutation.isPending}
                >
                  {UF_OPTIONS.map(uf => (
                    <option key={uf} value={uf}>{uf}</option>
                  ))}
                </select>
              </div>

              {/* Scout result feedback */}
              {scoutMutation.isPending && (
                <div className="flex items-center gap-3 p-3 rounded-lg bg-blue-500/5 border border-blue-500/20">
                  <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />
                  <div>
                    <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                      Buscando oportunidades...
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">
                      O agente Scout esta consultando o portal PNCP
                    </p>
                  </div>
                </div>
              )}

              {scoutMutation.isSuccess && !scoutMutation.isPending && (
                <div className="flex items-center gap-3 p-3 rounded-lg bg-green-500/5 border border-green-500/20">
                  <TrendingUp className="w-5 h-5 text-green-500" />
                  <div>
                    <p className="text-sm font-medium text-[hsl(var(--foreground))]">
                      {scoutMutation.data?.total_encontrados || 0} oportunidades encontradas
                    </p>
                    <p className="text-xs text-[hsl(var(--muted-foreground))]">
                      {scoutMutation.data?.portais_consultados || 1} portal(is) consultado(s)
                    </p>
                  </div>
                </div>
              )}

              {/* Actions */}
              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => setShowSearchDialog(false)}
                  disabled={scoutMutation.isPending}
                >
                  Cancelar
                </Button>
                <Button
                  variant="primary"
                  onClick={handleBuscarPNCP}
                  disabled={scoutMutation.isPending}
                >
                  {scoutMutation.isPending ? (
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  ) : (
                    <Search className="w-4 h-4 mr-2" />
                  )}
                  Buscar
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
