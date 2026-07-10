'use client';

import dynamic from 'next/dynamic';
import { Megaphone, Search, Plus, Eye, Edit2, Trash2, ArrowLeft, ChevronLeft, ChevronRight, RefreshCw, Send, Clock, CheckCircle, CheckCheck, FileText, Users, AlertTriangle, Calendar } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ConfirmModal } from '@/components/ui/modal';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { useAuth } from '@/hooks/useAuth';
import { useAnnouncements, useAnnouncementMutations } from '@/hooks/useAnnouncements';
import {
  type Announcement,
  type AnnouncementStatus,
  type AnnouncementPriority,
  type AnnouncementCategory,
  ANNOUNCEMENT_STATUS_LABELS,
  ANNOUNCEMENT_PRIORITY_LABELS,
  ANNOUNCEMENT_CATEGORY_LABELS,
} from '@/lib/services/announcements';
const AnnouncementFormModal = dynamic(() => import('@/components/operacional/announcement-form-modal').then(m => m.AnnouncementFormModal), { ssr: false });
const AnnouncementDetailModal = dynamic(() => import('@/components/operacional/announcement-detail-modal').then(m => m.AnnouncementDetailModal), { ssr: false });
import api from '@/lib/api';

// Cores dos status
const STATUS_COLORS: Record<AnnouncementStatus, string> = {
  rascunho: 'bg-gray-500/10 text-gray-500',
  agendado: 'bg-blue-500/10 text-blue-500',
  publicado: 'bg-green-500/10 text-green-500',
  arquivado: 'bg-purple-500/10 text-purple-500',
};

// Cores das prioridades
const PRIORITY_COLORS: Record<AnnouncementPriority, string> = {
  baixa: 'bg-gray-500/10 text-gray-500',
  normal: 'bg-blue-500/10 text-blue-500',
  alta: 'bg-orange-500/10 text-orange-500',
  urgente: 'bg-red-500/10 text-red-500',
};

// Icones dos status
const getStatusIcon = (status: AnnouncementStatus) => {
  switch (status) {
    case 'rascunho':
      return <FileText className="w-4 h-4" />;
    case 'agendado':
      return <Clock className="w-4 h-4" />;
    case 'publicado':
      return <CheckCircle className="w-4 h-4" />;
    case 'arquivado':
      return <FileText className="w-4 h-4" />;
    default:
      return <FileText className="w-4 h-4" />;
  }
};

// Templates rapidos de comunicado
const ANNOUNCEMENT_TEMPLATES = [
  { id: 't1', title: 'Escala Extra — Feriado', body: 'Informamos que havera escala extra no proximo feriado. Todos os colaboradores escalados devem confirmar presenca ate [DATA].', category: 'operacional', priority: 'alta' },
  { id: 't2', title: 'Reuniao Obrigatoria', body: 'Convocamos todos os colaboradores para reuniao obrigatoria em [DATA] as [HORA] no [LOCAL].', category: 'administrativa', priority: 'alta' },
  { id: 't3', title: 'Atualização de EPI', body: 'Lembramos que os EPIs devem ser renovados. Compareça ao almoxarifado com sua matricula ate [DATA].', category: 'operacional', priority: 'normal' },
  { id: 't4', title: 'Aviso de Pagamento', body: 'Informamos que o pagamento referente a [MES] sera processado em [DATA].', category: 'administrativa', priority: 'normal' },
] as const;

export default function ComunicadosPage() {
  const router = useRouter();
  const { isLoading: authLoading, isAuthenticated } = useAuth();
  const {
    announcements,
    total,
    page,
    pageSize,
    totalPages,
    isLoading,
    error,
    filters,
    setFilters,
    setPage,
    refresh,
  } = useAnnouncements({ initialPageSize: 10 });
  const { deleteAnnouncement, publishAnnouncement, isLoading: isMutating } = useAnnouncementMutations();

  const [searchTerm, setSearchTerm] = useState('');
  const [selectedStatus, setSelectedStatus] = useState<AnnouncementStatus | ''>('');
  const [selectedPriority, setSelectedPriority] = useState<AnnouncementPriority | ''>('');
  const [selectedCategory, setSelectedCategory] = useState<AnnouncementCategory | ''>('');

  // Modal states
  const [selectedAnnouncement, setSelectedAnnouncement] = useState<Announcement | null>(null);
  const [showFormModal, setShowFormModal] = useState(false);
  const [showDetailModal, setShowDetailModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [showPublishModal, setShowPublishModal] = useState(false);
  const [editAnnouncement, setEditAnnouncement] = useState<Announcement | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);

  // Template state
  const [templateToUse, setTemplateToUse] = useState<typeof ANNOUNCEMENT_TEMPLATES[number] | null>(null);

  // Read confirmation state
  const [readIds, setReadIds] = useState<Set<string>>(new Set());

  // Redirecionar se nao autenticado
  useEffect(() => {
    if (!authLoading && !isAuthenticated) {
      router.push('/login');
    }
  }, [authLoading, isAuthenticated, router]);

  // Debounce search
  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters({
        ...filters,
        search: searchTerm || undefined,
        status: selectedStatus || undefined,
        priority: selectedPriority || undefined,
        category: selectedCategory || undefined,
      });
    }, 300);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- debounce filter sync
  }, [searchTerm, selectedStatus, selectedPriority, selectedCategory]);

  // Handlers
  const handleNew = () => {
    setEditAnnouncement(null);
    setTemplateToUse(null);
    setShowFormModal(true);
  };

  const handleView = (announcement: Announcement) => {
    setSelectedAnnouncement(announcement);
    setShowDetailModal(true);
  };

  const handleEdit = (announcement: Announcement) => {
    setEditAnnouncement(announcement);
    setShowFormModal(true);
  };

  const handlePublishClick = (announcement: Announcement) => {
    setSelectedAnnouncement(announcement);
    setShowPublishModal(true);
  };

  const handlePublish = async () => {
    if (!selectedAnnouncement) return;

    setIsPublishing(true);
    const result = await publishAnnouncement(selectedAnnouncement.id);

    if (result) {
      setShowPublishModal(false);
      setSelectedAnnouncement(null);
      refresh();
    }

    setIsPublishing(false);
  };

  const handleDelete = async () => {
    if (!selectedAnnouncement) return;

    setIsDeleting(true);
    const success = await deleteAnnouncement(selectedAnnouncement.id);

    if (success) {
      setShowDeleteModal(false);
      setSelectedAnnouncement(null);
      refresh();
    }

    setIsDeleting(false);
  };

  const confirmDelete = (announcement: Announcement) => {
    setSelectedAnnouncement(announcement);
    setShowDeleteModal(true);
  };

  // Endpoint real de confirmação de leitura (announcement_controller: POST /comunicados/{id}/confirmar).
  // O body AnnouncementAcknowledgeRequest é obrigatório (campos opcionais) — enviar {}.
  const handleMarkAsRead = async (id: string) => {
    try {
      await api.post(`/api/v1/operacional/comunicacao/comunicados/${id}/confirmar`, {});
      setReadIds(prev => new Set([...prev, id]));
      refresh();
    } catch (err) {
      // Não marca como lido se a API falhou — sem atualização otimista dissimulada
      console.error('Erro ao confirmar leitura do comunicado:', err);
    }
  };

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString('pt-BR', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  // Estatisticas simples
  const stats = {
    total: total,
    rascunhos: announcements.filter(a => a.status === 'rascunho').length,
    publicados: announcements.filter(a => a.status === 'publicado').length,
    agendados: announcements.filter(a => a.status === 'agendado').length,
  };

  // Verifica se ha filtros ativos
  const hasActiveFilters = !!(searchTerm || selectedStatus || selectedPriority || selectedCategory);

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-[hsl(var(--background))]">
        <div className="animate-pulse-slow text-[hsl(var(--primary))]">
          <Megaphone className="w-12 h-12" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-grid">
      {/* Main content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="OPERACIONAL"
          title="Comunicados"
          subtitle={`${total} comunicados — ${readIds.size} lidos de ${total} total`}
          icon={<Megaphone className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/operacional">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Operacional
                </Button>
              </Link>
              <Button variant="outline" onClick={refresh} disabled={isLoading}>
                <RefreshCw className={`w-4 h-4 mr-2 ${isLoading ? 'animate-spin' : ''}`} />
                Atualizar
              </Button>
              <Button variant="primary" onClick={handleNew}>
                <Plus className="w-4 h-4 mr-2" />
                Novo Comunicado
              </Button>
            </>
          }
        />

        {/* Stats Cards */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
          <StatCard
            icon={<Megaphone className="w-4 h-4" />}
            color="#3b82f6"
            label="Total"
            value={stats.total}
          />
          <StatCard
            icon={<FileText className="w-4 h-4" />}
            color="#6b7280"
            label="Rascunhos"
            value={stats.rascunhos}
          />
          <StatCard
            icon={<CheckCircle className="w-4 h-4" />}
            color="#22c55e"
            label="Publicados"
            value={stats.publicados}
          />
          <StatCard
            icon={<Calendar className="w-4 h-4" />}
            color="#3b82f6"
            label="Agendados"
            value={stats.agendados}
          />
        </div>

        {/* Templates Rapidos — exibidos apenas quando nao ha filtros ativos */}
        {!hasActiveFilters && (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
            <div className="flex items-center gap-2 mb-3">
              <FileText className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <h2 className="text-sm font-semibold text-[hsl(var(--foreground))]">Templates Rapidos</h2>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-2">
              {ANNOUNCEMENT_TEMPLATES.map(t => (
                <button
                  key={t.id}
                  onClick={() => {
                    setTemplateToUse(t);
                    setEditAnnouncement(null);
                    setShowFormModal(true);
                  }}
                  className="text-left p-3 rounded-lg border border-[hsl(var(--border))] hover:border-[hsl(var(--primary))]/50 hover:bg-[hsl(var(--primary))]/5 transition-all"
                >
                  <p className="text-xs font-medium text-[hsl(var(--foreground))] line-clamp-2">{t.title}</p>
                  <p className="text-xs text-[hsl(var(--muted-foreground))] mt-1 line-clamp-2">{t.body.substring(0, 60)}...</p>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Filters */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
          <div className="flex flex-col lg:flex-row gap-4">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <Input
                placeholder="Buscar por titulo ou conteudo..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="pl-10"
              />
            </div>
            <div className="flex flex-wrap gap-2">
              <select
                value={selectedStatus}
                onChange={(e) => setSelectedStatus(e.target.value as AnnouncementStatus | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todos os Status</option>
                {Object.entries(ANNOUNCEMENT_STATUS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <select
                value={selectedPriority}
                onChange={(e) => setSelectedPriority(e.target.value as AnnouncementPriority | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todas Prioridades</option>
                {Object.entries(ANNOUNCEMENT_PRIORITY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
              <select
                value={selectedCategory}
                onChange={(e) => setSelectedCategory(e.target.value as AnnouncementCategory | '')}
                className="px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Todas Categorias</option>
                {Object.entries(ANNOUNCEMENT_CATEGORY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>

        {/* Error state */}
        {error && (
          <div className="bg-red-500/10 border border-red-500/20 rounded-xl p-4 mb-6 flex items-center gap-3">
            <AlertTriangle className="w-5 h-5 text-red-500" />
            <p className="text-red-500">{error}</p>
            <Button variant="outline" size="sm" onClick={refresh} className="ml-auto">
              Tentar novamente
            </Button>
          </div>
        )}

        {/* Loading state */}
        {isLoading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-pulse-slow text-[hsl(var(--primary))]">
              <Megaphone className="w-8 h-8" />
            </div>
          </div>
        )}

        {/* Table */}
        {!isLoading && !error && (
          <>
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]">
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Titulo
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Categoria
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Prioridade
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Destinatarios
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Criado em
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Status
                      </th>
                      <th className="px-4 py-3 text-left text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Leituras
                      </th>
                      <th className="px-4 py-3 text-right text-xs font-medium text-[hsl(var(--muted-foreground))] uppercase">
                        Ações
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[hsl(var(--border))]">
                    {announcements.map((announcement) => (
                      <tr
                        key={announcement.id}
                        className="hover:bg-[hsl(var(--muted))]/50 transition-colors cursor-pointer"
                        onClick={() => handleView(announcement)}
                      >
                        <td className="px-4 py-3">
                          <div>
                            <p className="text-sm font-medium text-[hsl(var(--foreground))] line-clamp-1">
                              {announcement.title}
                            </p>
                            <p className="text-xs text-[hsl(var(--muted-foreground))] line-clamp-1">
                              {announcement.content.substring(0, 50)}...
                            </p>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--muted-foreground))]">
                            {ANNOUNCEMENT_CATEGORY_LABELS[announcement.category]}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center px-2 py-1 rounded-full text-xs font-medium ${
                              PRIORITY_COLORS[announcement.priority]
                            }`}
                          >
                            {ANNOUNCEMENT_PRIORITY_LABELS[announcement.priority]}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <div className="flex items-center gap-1">
                            <Users className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                            <span className="text-sm text-[hsl(var(--muted-foreground))]">
                              {announcement.target_type === 'all' ? 'Todos' : 'Selecionados'}
                            </span>
                          </div>
                        </td>
                        <td className="px-4 py-3">
                          <span className="text-sm text-[hsl(var(--foreground))]">
                            {formatDate(announcement.created_at)}
                          </span>
                        </td>
                        <td className="px-4 py-3">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${
                              STATUS_COLORS[announcement.status]
                            }`}
                          >
                            {getStatusIcon(announcement.status)}
                            {ANNOUNCEMENT_STATUS_LABELS[announcement.status]}
                          </span>
                        </td>
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                          <div className="flex flex-col gap-1.5">
                            {readIds.has(announcement.id) ? (
                              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-green-500/10 text-green-500 w-fit">
                                <CheckCheck className="w-3 h-3" />
                                Lido
                              </span>
                            ) : (
                              <button
                                onClick={() => handleMarkAsRead(announcement.id)}
                                className="text-xs px-2 py-1 rounded bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-colors whitespace-nowrap w-fit"
                                title="Marcar como lido"
                              >
                                <CheckCheck className="w-3 h-3 inline mr-1" />
                                Marcar lido
                              </button>
                            )}
                            {/* Rótulo único: read_count é sempre contagem de LEITURAS */}
                            <div className="flex items-center gap-1">
                              <CheckCircle className="w-3 h-3 text-green-500" />
                              <span className="text-xs text-[hsl(var(--muted-foreground))]">
                                {announcement.read_count ?? 0}
                                {(announcement as any).target_count != null
                                  ? `/${(announcement as any).target_count}`
                                  : ''} leituras
                              </span>
                            </div>
                          </div>
                        </td>
                        <td className="px-4 py-3" onClick={(e) => e.stopPropagation()}>
                          <div className="flex items-center justify-end gap-1">
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => handleView(announcement)}
                              title="Ver Detalhes"
                            >
                              <Eye className="w-4 h-4" />
                            </Button>
                            {announcement.status === 'rascunho' && (
                              <>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handleEdit(announcement)}
                                  title="Editar"
                                >
                                  <Edit2 className="w-4 h-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => handlePublishClick(announcement)}
                                  title="Publicar"
                                  className="text-green-500 hover:text-green-600"
                                >
                                  <Send className="w-4 h-4" />
                                </Button>
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() => confirmDelete(announcement)}
                                  className="text-red-500 hover:text-red-600"
                                  title="Excluir"
                                >
                                  <Trash2 className="w-4 h-4" />
                                </Button>
                              </>
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
            {announcements.length === 0 && !isLoading && (
              <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl mt-4">
                <Megaphone className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
                <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
                  Nenhum comunicado encontrado
                </h3>
                <p className="text-[hsl(var(--muted-foreground))] mt-1">
                  Ajuste os filtros ou crie um novo comunicado
                </p>
                <Button variant="primary" className="mt-4" onClick={handleNew}>
                  <Plus className="w-4 h-4 mr-2" />
                  Novo Comunicado
                </Button>
              </div>
            )}

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between mt-4">
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
          </>
        )}
      </main>

      {/* Form Modal */}
      <AnnouncementFormModal
        isOpen={showFormModal}
        onClose={() => {
          setShowFormModal(false);
          setEditAnnouncement(null);
          setTemplateToUse(null);
        }}
        onSuccess={refresh}
        editData={editAnnouncement}
      />

      {/* Detail Modal */}
      <AnnouncementDetailModal
        isOpen={showDetailModal}
        onClose={() => {
          setShowDetailModal(false);
          setSelectedAnnouncement(null);
        }}
        announcement={selectedAnnouncement}
        onEdit={handleEdit}
        onPublish={handlePublishClick}
      />

      {/* Publish Modal */}
      <ConfirmModal
        isOpen={showPublishModal}
        onClose={() => {
          setShowPublishModal(false);
          setSelectedAnnouncement(null);
        }}
        onConfirm={handlePublish}
        title="Publicar Comunicado"
        message={`Tem certeza que deseja publicar o comunicado "${selectedAnnouncement?.title}"? Após publicado, todos os destinatários serão notificados.`}
        confirmText="Publicar"
        isLoading={isPublishing}
        variant="info"
      />

      {/* Delete Modal */}
      <ConfirmModal
        isOpen={showDeleteModal}
        onClose={() => {
          setShowDeleteModal(false);
          setSelectedAnnouncement(null);
        }}
        onConfirm={handleDelete}
        title="Excluir Comunicado"
        message={`Tem certeza que deseja excluir o comunicado "${selectedAnnouncement?.title}"? Esta acao nao pode ser desfeita.`}
        confirmText="Excluir"
        isLoading={isDeleting}
        variant="danger"
      />
    </div>
  );
}
