'use client';

import dynamic from 'next/dynamic';
import { MapPin, Search, Plus, Filter, Eye, Edit2, Trash2, Users, Clock, ArrowLeft, ChevronLeft, ChevronRight, AlertCircle, CheckCircle, RefreshCw } from 'lucide-react';
import { useEffect, useState, useRef, useCallback } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConfirmModal } from '@/components/ui/modal';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { useAuth } from '@/hooks/useAuth';
import { usePosts, usePostStats, useDeletePost } from '@/hooks/operacional/usePosts';
import { getErrorMessage } from '@/lib/api';

const PostDetailModal = dynamic(() => import('@/components/operacional/post-detail-modal').then(m => m.PostDetailModal), { ssr: false });
const PostFormModal = dynamic(() => import('@/components/operacional/post-form-modal').then(m => m.PostFormModal), { ssr: false });
import { ResponsiveTable, Column } from '@/components/ResponsiveTable';
import { ExportButton } from '@/components/ui/export-button';
import { formatDataForExport } from '@/utils/export';
import type { Post, PostType, PostStatus, ShiftType } from '@/types/operacional';
import {
  POST_TYPE_LABELS,
  POST_STATUS_LABELS,
  SHIFT_TYPE_LABELS,
} from '@/types/operacional';

interface PostFilters {
  search?: string;
  post_type?: PostType;
  status?: PostStatus;
  shift_type?: ShiftType;
  requires_armed?: boolean;
  requires_vehicle?: boolean;
}

interface PostStats {
  total: number;
  filled: number;
  with_vacancy: number;
  total_headcount: number;
}

export default function PostosPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const {
    data: postsData,
    isLoading,
    error: queryError,
    refetch: refresh,
  } = usePosts();

  // Garantir que posts é sempre um array
  // API retorna { items: [...], total: N, page: N }
  const posts = Array.isArray(postsData)
    ? postsData
    : postsData?.items && Array.isArray(postsData.items)
    ? postsData.items
    : [];
  const total = postsData?.total || posts.length;
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const totalPages = Math.ceil(total / pageSize);
  const [filters, setFilters] = useState<PostFilters>({});

  // Stats REAIS do backend (GET /operacional/posts/stats): filled/with_vacancy
  // vêm da comparação alocações×quadro por posto — o cálculo local por status
  // ('active' = preenchido) era semanticamente errado e mostrava "Com vagas: 0".
  const { data: statsData } = usePostStats();
  const stats: PostStats | null = statsData
    ? {
        total: (statsData as any).total ?? total,
        filled: (statsData as any).filled ?? 0,
        with_vacancy: (statsData as any).with_vacancy ?? 0,
        total_headcount: (statsData as any).total_headcount ?? 0,
      }
    : posts.length > 0
    ? {
        // Fallback local só enquanto /posts/stats não responde
        total: total,
        filled: posts.filter((p: Post) => p.status === 'active').length,
        with_vacancy: posts.filter((p: Post) => p.status !== 'active').length,
        total_headcount: posts.reduce((sum: number, p: Post) => sum + (p.required_headcount || 0), 0),
      }
    : null;
  const deletePostMutation = useDeletePost();

  const [searchTerm, setSearchTerm] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  // Modal states
  const [selectedPost, setSelectedPost] = useState<Post | null>(null);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showFormModal, setShowFormModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  // Redirecionar se nao autenticado
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Debounce search - com proteção contra loops
  const lastSearchRef = useRef<string | undefined>(undefined);

  useEffect(() => {
    const newSearch = searchTerm || undefined;

    // Só atualiza se o valor realmente mudou
    if (lastSearchRef.current === newSearch) {
      return;
    }

    const timer = setTimeout(() => {
      lastSearchRef.current = newSearch;
      setFilters((prev) => {
        // Evita criar novo objeto se o valor é o mesmo
        if (prev.search === newSearch) {
          return prev;
        }
        return { ...prev, search: newSearch };
      });
    }, 300);

    return () => clearTimeout(timer);
  }, [searchTerm, setFilters]);

  // Handlers
  const handleView = (post: Post) => {
    setSelectedPost(post);
    setShowDetailModal(true);
  };

  const handleEdit = (post: Post) => {
    setSelectedPost(post);
    setShowFormModal(true);
    setShowDetailModal(false);
  };

  const handleCreate = () => {
    setSelectedPost(null);
    setShowFormModal(true);
  };

  const handleDelete = (post: Post) => {
    setSelectedPost(post);
    setDeleteError(null);
    setShowDeleteModal(true);
  };

  const confirmDelete = async () => {
    if (!selectedPost) return;

    setIsDeleting(true);
    setDeleteError(null);

    try {
      await deletePostMutation.mutateAsync({ postId: selectedPost.id });
      setShowDeleteModal(false);
      setSelectedPost(null);
      refresh();
    } catch (err) {
      setDeleteError(getErrorMessage(err));
    } finally {
      setIsDeleting(false);
    }
  };

  const handleFormSuccess = () => {
    refresh();
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <MapPin className="w-12 h-12" />
        </div>
      </div>
    );
  }

  const getStatusColor = (status: PostStatus) => {
    switch (status) {
      case 'active':
        return 'bg-green-500/10 text-green-500';
      case 'inactive':
        return 'bg-gray-500/10 text-gray-500';
      case 'temporary':
        return 'bg-blue-500/10 text-blue-500';
      case 'suspended':
        return 'bg-red-500/10 text-red-500';
      default:
        return 'bg-gray-500/10 text-gray-500';
    }
  };

  return (
    <div className="min-h-screen bg-grid">
      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Postos de Trabalho"
          subtitle={`${total} postos cadastrados`}
          icon={<MapPin className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Operacional
                </Button>
              </Link>
              <Button variant="primary" size="sm" onClick={handleCreate}>
                <Plus className="w-4 h-4 mr-2" />
                Novo Posto
              </Button>
            </>
          }
        />

        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatCard
            icon={<MapPin className="w-4 h-4" />}
            color="#06b6d4"
            label="Total de Postos"
            value={stats?.total || 0}
          />
          <StatCard
            icon={<CheckCircle className="w-4 h-4" />}
            color="#22c55e"
            label="Preenchidos"
            value={stats?.filled || 0}
          />
          <StatCard
            icon={<AlertCircle className="w-4 h-4" />}
            color="#f97316"
            label="Com vagas"
            value={stats?.with_vacancy || 0}
          />
          <StatCard
            icon={<Users className="w-4 h-4" />}
            color="#3b82f6"
            label="Vagas totais"
            value={stats?.total_headcount || 0}
          />
        </div>

        {/* Search and Filters */}
        <div className="flex flex-col sm:flex-row gap-4 mb-6">
          <div className="flex-1">
            <Input
              type="search"
              placeholder="Buscar por nome, codigo ou endereco..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              icon={<Search className="w-4 h-4" />}
            />
          </div>
          <Button
            variant="outline"
            onClick={() => setShowFilters(!showFilters)}
            className={showFilters ? 'border-[hsl(var(--primary))]' : ''}
          >
            <Filter className="w-4 h-4 mr-2" />
            Filtros
            {Object.keys(filters).filter((k) => k !== 'search' && filters[k as keyof typeof filters]).length > 0 && (
              <span className="ml-2 w-5 h-5 rounded-full bg-[hsl(var(--primary))] text-white text-xs flex items-center justify-center">
                {Object.keys(filters).filter((k) => k !== 'search' && filters[k as keyof typeof filters]).length}
              </span>
            )}
          </Button>
          <Button variant="outline" onClick={() => refresh()} disabled={isLoading}>
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
          <ExportButton
            data={formatDataForExport(posts, {
              code: 'Código',
              name: 'Nome',
              post_type: 'Tipo',
              status: 'Status',
              shift_type: 'Turno',
              headcount: 'Vagas',
              filled_count: 'Preenchidas',
              address: 'Endereço',
              city: 'Cidade',
              state: 'Estado',
            })}
            filename="postos"
            pdfTitle="Relatório de Postos de Trabalho"
            formats={['excel', 'pdf', 'csv']}
          />
        </div>

        {/* Filters Panel */}
        {showFilters && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="font-medium text-[hsl(var(--foreground))]">Filtros</h3>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => {
                  setFilters({});
                  setSearchTerm('');
                }}
              >
                Limpar filtros
              </Button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Tipo de Posto
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))]"
                  value={filters.post_type || ''}
                  onChange={(e) =>
                    setFilters({ ...filters, post_type: (e.target.value || undefined) as PostType | undefined })
                  }
                >
                  <option value="">Todos</option>
                  {Object.entries(POST_TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Status
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))]"
                  value={filters.status || ''}
                  onChange={(e) =>
                    setFilters({ ...filters, status: (e.target.value || undefined) as PostStatus | undefined })
                  }
                >
                  <option value="">Todos</option>
                  {Object.entries(POST_STATUS_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Turno
                </label>
                <select
                  className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))]"
                  value={filters.shift_type || ''}
                  onChange={(e) =>
                    setFilters({ ...filters, shift_type: (e.target.value || undefined) as ShiftType | undefined })
                  }
                >
                  <option value="">Todos</option>
                  {Object.entries(SHIFT_TYPE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm text-[hsl(var(--muted-foreground))] mb-1 block">
                  Requisitos
                </label>
                <div className="flex gap-2">
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={filters.requires_armed === true}
                      onChange={(e) =>
                        setFilters({ ...filters, requires_armed: e.target.checked ? true : undefined })
                      }
                      className="rounded border-[hsl(var(--border))]"
                    />
                    Armado
                  </label>
                  <label className="flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={filters.requires_vehicle === true}
                      onChange={(e) =>
                        setFilters({ ...filters, requires_vehicle: e.target.checked ? true : undefined })
                      }
                      className="rounded border-[hsl(var(--border))]"
                    />
                    Veiculo
                  </label>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Error state */}
        {queryError && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertCircle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{queryError.detail?.[0]?.msg ?? 'Erro ao carregar postos'}</p>
            <Button variant="outline" size="sm" onClick={() => refresh()} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <MapPin className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Posts Table */}
        {!isLoading && !queryError && (
          <>
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-[hsl(var(--muted))]">
                    <tr>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Posto
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Tipo
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Turno
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Efetivo
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Status
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase tracking-wider">
                        Ações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[hsl(var(--border))]">
                    {posts.map((post) => (
                      <tr
                        key={post.id}
                        className="hover:bg-[hsl(var(--muted))]/50 transition-colors cursor-pointer"
                        onClick={() => handleView(post)}
                      >
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-3">
                            <div className="w-10 h-10 rounded-lg bg-cyan-500/10 flex items-center justify-center flex-shrink-0">
                              <MapPin className="w-5 h-5 text-cyan-500" />
                            </div>
                            <div>
                              <p className="font-medium text-[hsl(var(--foreground))]">
                                {post.name}
                              </p>
                              <p className="text-xs text-[hsl(var(--muted-foreground))]">
                                {post.code}
                              </p>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {POST_TYPE_LABELS[post.post_type as PostType] || post.post_type}
                          </span>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-2">
                            <Clock className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                            <span className="text-sm text-[hsl(var(--foreground))]">
                              {SHIFT_TYPE_LABELS[post.shift_type as ShiftType] || post.shift_type}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <div className="flex items-center gap-2">
                            <Users className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                            <span
                              className={`text-sm font-medium ${
                                post.vacancy_count > 0
                                  ? 'text-orange-500'
                                  : 'text-green-500'
                              }`}
                            >
                              {post.current_headcount}/{post.required_headcount}
                            </span>
                            {post.vacancy_count > 0 && (
                              <span className="text-xs text-orange-500">
                                ({post.vacancy_count} vagas)
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="px-4 py-4">
                          <span
                            className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${getStatusColor(
                              post.status as PostStatus
                            )}`}
                          >
                            {POST_STATUS_LABELS[post.status as PostStatus] || post.status}
                          </span>
                        </td>
                        <td className="px-4 py-4 text-right" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleView(post)}
                              title="Visualizar"
                            >
                              <Eye className="w-4 h-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleEdit(post)}
                              title="Editar"
                            >
                              <Edit2 className="w-4 h-4" />
                            </Button>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleDelete(post)}
                              title="Excluir"
                              className="text-red-500 hover:text-red-600 hover:bg-red-500/10"
                            >
                              <Trash2 className="w-4 h-4" />
                            </Button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Empty state */}
              {posts.length === 0 && !isLoading && (
                <div className="text-center py-12">
                  <MapPin className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                  <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                    Nenhum posto encontrado
                  </h3>
                  <p className="text-[hsl(var(--muted-foreground))] mt-1 mb-4">
                    {searchTerm || Object.keys(filters).length > 1
                      ? 'Tente ajustar os filtros de busca'
                      : 'Comece criando um novo posto de trabalho'}
                  </p>
                  {!searchTerm && Object.keys(filters).length <= 1 && (
                    <Button variant="primary" onClick={handleCreate}>
                      <Plus className="w-4 h-4 mr-2" />
                      Criar Primeiro Posto
                    </Button>
                  )}
                </div>
              )}
            </div>

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Mostrando {(page - 1) * pageSize + 1} a{' '}
                  {Math.min(page * pageSize, total)} de {total} postos
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
          </>
        )}
      </main>

      {/* Modals */}
      <PostDetailModal
        post={selectedPost}
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedPost(null);
        }}
        onEdit={() => selectedPost && handleEdit(selectedPost)}
      />

      <PostFormModal
        post={selectedPost}
        isOpen={showFormModal}
        onClose={() => {
          setShowFormModal(false);
          setSelectedPost(null);
        }}
        onSuccess={handleFormSuccess}
      />

      <ConfirmModal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setSelectedPost(null);
          setDeleteError(null);
        }}
        onConfirm={confirmDelete}
        title="Excluir Posto"
        message={
          deleteError
            ? deleteError
            : `Tem certeza que deseja excluir o posto "${selectedPost?.name}"? Esta acao nao pode ser desfeita.`
        }
        confirmText="Excluir"
        cancelText="Cancelar"
        variant="danger"
        isLoading={isDeleting}
      />
    </div>
  );
}
