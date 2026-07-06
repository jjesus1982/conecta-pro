'use client';

import dynamic from 'next/dynamic';
import { Users, Search, Plus, Eye, Edit2, ArrowLeft, ChevronLeft, ChevronRight, RefreshCw, Star, Calendar, DollarSign, Clock, CheckCircle, XCircle, Filter, Sparkles, TrendingUp, Phone, Mail } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { PageHeader } from '@/components/ui/page-header';
import { Input } from '@/components/ui/input';
import { useAuth } from '@/hooks/useAuth';
import { useDiarists } from '@/hooks/operacional/useDiarists';
const DiaristFormModal = dynamic(() => import('@/components/operacional/diarist-form-modal').then(m => m.DiaristFormModal), { ssr: false });
import {
  type Diarist,
  type DiaristStatus,
  type DiaristType,
  DIARIST_TYPE_LABELS,
  DIARIST_STATUS_LABELS,
} from '@/lib/services/diarists';

const STATUS_COLORS: Record<DiaristStatus, string> = {
  ativo: 'bg-green-500/10 text-green-500',
  inativo: 'bg-gray-500/10 text-gray-500',
  bloqueado: 'bg-red-500/10 text-red-500',
  em_avaliacao: 'bg-yellow-500/10 text-yellow-500',
};

const TYPE_COLORS: Record<DiaristType, string> = {
  limpeza: 'bg-blue-500/10 text-blue-500',
  portaria: 'bg-purple-500/10 text-purple-500',
  manutencao: 'bg-orange-500/10 text-orange-500',
  jardinagem: 'bg-green-500/10 text-green-500',
  outros: 'bg-gray-500/10 text-gray-500',
};

export default function DiaristasPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();

  const { data, isLoading, error, refetch } = useDiarists();
  const diarists: Diarist[] = (data?.items as unknown as Diarist[]) ?? [];
  const total = diarists.length;
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const totalPages = Math.ceil(total / pageSize);

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<DiaristStatus | ''>('');
  const [selectedType, setSelectedType] = useState<DiaristType | ''>('');
  const [showFormModal, setShowFormModal] = useState(false);

  // Stats
  const [stats, setStats] = useState<{
    total: number;
    ativos: number;
    media_avaliacao: number;
    total_diarias_mes: number;
  } | null>(null);

  // Dados agora vêm do hook useDiarists via React Query

  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Debounce search - reset page on filter change
  useEffect(() => {
    const timer = setTimeout(() => {
      if (isAuthenticated) {
        setPage(1);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [searchTerm, selectedStatus, selectedType, isAuthenticated]);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL',
    }).format(value);
  };

  const renderStars = (rating: number) => {
    const stars = [];
    const fullStars = Math.floor(rating);
    const hasHalf = rating - fullStars >= 0.5;

    for (let i = 0; i < 5; i++) {
      if (i < fullStars) {
        stars.push(
          <Star key={i} className="w-4 h-4 fill-yellow-500 text-yellow-500" />
        );
      } else if (i === fullStars && hasHalf) {
        stars.push(
          <Star key={i} className="w-4 h-4 fill-yellow-500/50 text-yellow-500" />
        );
      } else {
        stars.push(
          <Star key={i} className="w-4 h-4 text-gray-300" />
        );
      }
    }
    return stars;
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Users className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Diaristas"
          subtitle={`${total} cadastrados`}
          icon={<Users className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Operacional
                </Button>
              </Link>
              <Link href="/modulos/operacional/diaristas/escala">
                <Button variant="outline" size="sm">
                  <Calendar className="w-4 h-4 mr-2" />
                  Escala Diaria
                </Button>
              </Link>
              <Link href="/modulos/operacional/diaristas/fechamento">
                <Button variant="outline" size="sm">
                  <DollarSign className="w-4 h-4 mr-2" />
                  Fechamento
                </Button>
              </Link>
              <Button variant="outline" size="sm" onClick={() => { refetch(); }} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Atualizar
              </Button>
              <Button variant="primary" size="sm" onClick={() => setShowFormModal(true)}>
                <Plus className="w-4 h-4 mr-2" />
                Novo Diarista
              </Button>
            </>
          }
        />

        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center">
                <Users className="w-5 h-5 text-cyan-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">{total}</p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Total</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-green-500/10 flex items-center justify-center">
                <CheckCircle className="w-5 h-5 text-green-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {diarists.filter(d => d.status === 'ativo').length}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Ativos</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-yellow-500/10 flex items-center justify-center">
                <Star className="w-5 h-5 text-yellow-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {diarists.length > 0
                    ? (diarists.reduce((acc, d) => acc + d.media_avaliacao, 0) / diarists.length).toFixed(1)
                    : '0.0'}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Media Avaliacao</p>
              </div>
            </div>
          </div>

          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-lg bg-purple-500/10 flex items-center justify-center">
                <Sparkles className="w-5 h-5 text-purple-500" />
              </div>
              <div>
                <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))]">
                  {diarists.reduce((acc, d) => acc + d.total_diarias, 0)}
                </p>
                <p className="text-xs text-[hsl(var(--muted-foreground))]">Diarias Realizadas</p>
              </div>
            </div>
          </div>
        </div>

        {/* Filters */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <Input
                placeholder="Buscar por nome, CPF, telefone..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value as DiaristStatus | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Status</option>
                {Object.entries(DIARIST_STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
              <select
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value as DiaristType | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Tipos</option>
                {Object.entries(DIARIST_TYPE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>{label}</option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <XCircle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{error.detail?.map(e => e.msg).join(', ') ?? 'Erro ao carregar diaristas'}</p>
            <Button variant="outline" size="sm" onClick={() => { refetch(); }} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Loading */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <Users className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Grid de Diaristas */}
        {!isLoading && !error && (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
              {diarists.map((diarist) => (
                <div
                  key={diarist.id}
                  className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 hover:border-[hsl(var(--primary))]/50 transition-colors cursor-pointer"
                >
                  <div className="flex items-start gap-4">
                    {/* Avatar */}
                    <div className="w-14 h-14 rounded-full bg-gradient-to-br from-cyan-500 to-blue-600 flex items-center justify-center text-white font-semibold text-lg flex-shrink-0">
                      {diarist.nome.charAt(0).toUpperCase()}
                    </div>

                    <div className="flex-1 min-w-0">
                      {/* Nome e Status */}
                      <div className="flex items-start justify-between gap-2 mb-1">
                        <h3 className="font-semibold text-[hsl(var(--foreground))] truncate">
                          {diarist.nome}
                        </h3>
                        <span className={`px-2 py-0.5 rounded-full text-xs font-medium flex-shrink-0 ${STATUS_COLORS[diarist.status]}`}>
                          {DIARIST_STATUS_LABELS[diarist.status]}
                        </span>
                      </div>

                      {/* Tipo e Especialidades */}
                      <div className="flex items-center gap-2 mb-2">
                        <span className={`px-2 py-0.5 rounded-full text-xs ${TYPE_COLORS[diarist.tipo]}`}>
                          {DIARIST_TYPE_LABELS[diarist.tipo]}
                        </span>
                        {diarist.especialidades?.length > 0 && (
                          <span className="text-xs text-[hsl(var(--muted-foreground))]">
                            +{diarist.especialidades.length} especialidades
                          </span>
                        )}
                      </div>

                      {/* Avaliacao */}
                      <div className="flex items-center gap-2 mb-2">
                        <div className="flex items-center gap-0.5">
                          {renderStars(diarist.media_avaliacao)}
                        </div>
                        <span className="text-sm text-[hsl(var(--muted-foreground))]">
                          ({diarist.total_avaliacoes})
                        </span>
                      </div>

                      {/* Contato */}
                      <div className="flex items-center gap-3 text-xs text-[hsl(var(--muted-foreground))] mb-3">
                        {diarist.celular && (
                          <span className="flex items-center gap-1">
                            <Phone className="w-3 h-3" />
                            {diarist.celular}
                          </span>
                        )}
                        {diarist.email && (
                          <span className="flex items-center gap-1 truncate">
                            <Mail className="w-3 h-3" />
                            {diarist.email}
                          </span>
                        )}
                      </div>

                      {/* Metricas */}
                      <div className="grid grid-cols-3 gap-2 pt-3 border-t border-[hsl(var(--border))]">
                        <div className="text-center">
                          <p className="text-sm font-semibold text-[hsl(var(--foreground))]">
                            {diarist.total_diarias}
                          </p>
                          <p className="text-xs text-[hsl(var(--muted-foreground))]">Diarias</p>
                        </div>
                        <div className="text-center">
                          <p className="text-sm font-semibold text-[hsl(var(--foreground))]">
                            {diarist.taxa_comparecimento.toFixed(0)}%
                          </p>
                          <p className="text-xs text-[hsl(var(--muted-foreground))]">Presenca</p>
                        </div>
                        <div className="text-center">
                          <p className="text-sm font-semibold text-green-500">
                            {formatCurrency(diarist.valor_diaria)}
                          </p>
                          <p className="text-xs text-[hsl(var(--muted-foreground))]">Diaria</p>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex items-center justify-end gap-2 mt-4 pt-3 border-t border-[hsl(var(--border))]">
                    <Button variant="ghost" size="sm">
                      <Eye className="w-4 h-4 mr-1" />
                      Ver
                    </Button>
                    <Button variant="ghost" size="sm">
                      <Calendar className="w-4 h-4 mr-1" />
                      Agendar
                    </Button>
                    <Button variant="ghost" size="sm">
                      <Edit2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              ))}
            </div>

            {/* Empty State */}
            {diarists.length === 0 && (
              <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl">
                <Users className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhum diarista encontrado
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Ajuste os filtros ou cadastre um novo diarista
                </p>
                <Button variant="primary" className="mt-4" onClick={() => setShowFormModal(true)}>
                  <Plus className="w-4 h-4 mr-2" />
                  Novo Diarista
                </Button>
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-6">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Mostrando {(page - 1) * pageSize + 1} a {Math.min(page * pageSize, total)} de {total}
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => p - 1)}
                    disabled={page <= 1}
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </Button>
                  <span className="text-sm text-[hsl(var(--foreground))]">
                    {page} de {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage(p => p + 1)}
                    disabled={page >= totalPages}
                  >
                    <ChevronRight className="w-4 h-4" />
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </main>

      {/* Modal de Novo Diarista */}
      <DiaristFormModal
        isOpen={showFormModal}
        onClose={() => setShowFormModal(false)}
        onSuccess={() => {
          refetch();
        }}
      />
    </div>
  );
}
