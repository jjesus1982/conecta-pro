'use client';

import { Bell, Megaphone, Search, Plus, Eye, Edit, Trash2, AlertCircle, ArrowLeft, RefreshCw } from 'lucide-react';
import { useState, useMemo } from 'react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
;
import { toast } from 'sonner';
import { ComunicadoFormModal } from '@/components/campo/comunicado-form-modal';
import { ComunicadoDetailModal } from '@/components/campo/comunicado-detail-modal';

interface Comunicado {
  id: string;
  titulo: string;
  mensagem: string;
  tipo: string;
  destinatarios: string;
  data_envio: string;
  status: string;
}

export default function ComunicadosPage() {
  const [comunicados, setComunicados] = useState<Comunicado[]>([]);
  const [search, setSearch] = useState('');
  const [tipoFilter, setTipoFilter] = useState('all');
  const [page, setPage] = useState(1);

  // Modals
  const [formOpen, setFormOpen] = useState(false);
  const [detailOpen, setDetailOpen] = useState(false);
  const [selectedComunicado, setSelectedComunicado] = useState<Comunicado | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const ITEMS_PER_PAGE = 10;

  // Stats
  const stats = useMemo(() => ({
    total: comunicados.length,
    informativos: comunicados.filter((c) => c.tipo === 'informativo').length,
    urgentes: comunicados.filter((c) => c.tipo === 'urgente').length,
  }), [comunicados]);

  // Filtros
  const filteredComunicados = useMemo(() => {
    let results = [...comunicados];

    if (search) {
      const term = search.toLowerCase();
      results = results.filter(
        (c) =>
          c.titulo.toLowerCase().includes(term) ||
          c.destinatarios.toLowerCase().includes(term) ||
          c.mensagem.toLowerCase().includes(term)
      );
    }

    if (tipoFilter !== 'all') {
      results = results.filter((c) => c.tipo === tipoFilter);
    }

    return results;
  }, [comunicados, search, tipoFilter]);

  // Paginacao
  const totalPages = Math.max(1, Math.ceil(filteredComunicados.length / ITEMS_PER_PAGE));
  const paginatedComunicados = filteredComunicados.slice(
    (page - 1) * ITEMS_PER_PAGE,
    page * ITEMS_PER_PAGE
  );

  const getTipoBadge = (tipo: string) => {
    const tipoMap: Record<string, { label: string; className: string }> = {
      informativo: { label: 'Informativo', className: 'bg-blue-100 text-blue-800' },
      urgente: { label: 'Urgente', className: 'bg-red-100 text-red-800' },
      operacional: { label: 'Operacional', className: 'bg-violet-100 text-violet-800' },
    };
    const config = tipoMap[tipo] || { label: tipo || '-', className: 'bg-gray-100 text-gray-800' };
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  const getStatusBadge = (status: string) => {
    const statusMap: Record<string, { label: string; className: string }> = {
      enviado: { label: 'Enviado', className: 'bg-green-100 text-green-800' },
      pendente: { label: 'Pendente', className: 'bg-yellow-100 text-yellow-800' },
      rascunho: { label: 'Rascunho', className: 'bg-gray-100 text-gray-800' },
    };
    const config = statusMap[status] || { label: status || 'Pendente', className: 'bg-gray-100 text-gray-800' };
    return <Badge className={config.className}>{config.label}</Badge>;
  };

  const formatDate = (date: string | null | undefined) => {
    if (!date) return '-';
    return new Date(date).toLocaleDateString('pt-BR');
  };

  // CRUD handlers
  const handleCreate = () => {
    setSelectedComunicado(null);
    setFormOpen(true);
  };

  const handleEdit = (comunicado: Comunicado) => {
    setSelectedComunicado(comunicado);
    setFormOpen(true);
  };

  const handleViewDetail = (comunicado: Comunicado) => {
    setSelectedComunicado(comunicado);
    setDetailOpen(true);
  };

  const handleDelete = (comunicado: Comunicado) => {
    setComunicados((prev) => prev.filter((c) => c.id !== comunicado.id));
    toast.success('Comunicado removido com sucesso');
  };

  const handleSubmit = (data: any) => {
    setIsSubmitting(true);

    try {
      if (selectedComunicado) {
        // Update
        setComunicados((prev) =>
          prev.map((c) =>
            c.id === selectedComunicado.id
              ? { ...c, ...data }
              : c
          )
        );
        toast.success('Comunicado atualizado com sucesso');
      } else {
        // Create
        const newComunicado: Comunicado = {
          id: crypto.randomUUID(),
          titulo: data.titulo,
          mensagem: data.mensagem,
          tipo: data.tipo,
          destinatarios: data.destinatarios,
          data_envio: data.data_envio,
          status: 'pendente',
        };
        setComunicados((prev) => [newComunicado, ...prev]);
        toast.success('Comunicado criado com sucesso');
      }
      setFormOpen(false);
      setSelectedComunicado(null);
    } catch {
      toast.error('Erro ao salvar comunicado');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="min-h-screen bg-grid">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
        <PageHeader
          eyebrow="CAMPO"
          title="Comunicados"
          subtitle="Gestao de comunicados em campo"
          icon={<Bell className="w-5 h-5" />}
          actions={
            <>
              <Link href="/modulos/campo">
                <Button variant="ghost" size="sm">
                  <ArrowLeft className="w-4 h-4 mr-2" />
                  Campo
                </Button>
              </Link>
              <Button variant="primary" size="sm" onClick={handleCreate}>
                <Plus className="w-4 h-4 mr-2" />
                Novo Comunicado
              </Button>
            </>
          }
        />

        {/* Stats Cards */}
        <div className="grid grid-cols-3 gap-4 mb-6">
          <StatCard
            icon={<Megaphone className="w-4 h-4" />}
            color="#f59e0b"
            label="Total"
            value={stats.total}
          />
          <StatCard
            icon={<Bell className="w-4 h-4" />}
            color="#3b82f6"
            label="Informativos"
            value={stats.informativos}
          />
          <StatCard
            icon={<AlertCircle className="w-4 h-4" />}
            color="#ef4444"
            label="Urgentes"
            value={stats.urgentes}
          />
        </div>

        {/* Filters */}
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 mb-6">
          <div className="flex flex-wrap items-center gap-4">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[hsl(var(--muted-foreground))]" />
              <Input
                placeholder="Buscar por titulo, destinatarios ou mensagem..."
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1); }}
                className="pl-9"
              />
            </div>
            <div className="w-[200px]">
              <Select value={tipoFilter} onValueChange={(v) => { setTipoFilter(v); setPage(1); }}>
                <SelectTrigger>
                  <SelectValue placeholder="Tipo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">Todos</SelectItem>
                  <SelectItem value="informativo">Informativo</SelectItem>
                  <SelectItem value="urgente">Urgente</SelectItem>
                  <SelectItem value="operacional">Operacional</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        {/* Table */}
        {paginatedComunicados.length > 0 ? (
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl overflow-hidden mb-6">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--muted))]/30">
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Titulo</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Tipo</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Data Envio</th>
                    <th className="text-left px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Destinatarios</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Status</th>
                    <th className="text-center px-4 py-3 text-xs font-semibold text-[hsl(var(--muted-foreground))] uppercase">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {paginatedComunicados.map((comunicado, index) => (
                    <tr
                      key={comunicado.id}
                      className={`border-b border-[hsl(var(--border))]/50 hover:bg-[hsl(var(--muted))]/20 transition-colors ${
                        index % 2 === 0 ? '' : 'bg-[hsl(var(--muted))]/10'
                      }`}
                    >
                      <td className="px-4 py-3 text-sm font-medium text-[hsl(var(--foreground))]">
                        {comunicado.titulo}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {getTipoBadge(comunicado.tipo)}
                      </td>
                      <td className="px-4 py-3 text-sm text-[hsl(var(--muted-foreground))]">
                        {formatDate(comunicado.data_envio)}
                      </td>
                      <td className="px-4 py-3 text-sm text-[hsl(var(--muted-foreground))]">
                        {comunicado.destinatarios || '-'}
                      </td>
                      <td className="px-4 py-3 text-center">
                        {getStatusBadge(comunicado.status)}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex items-center justify-center gap-1">
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleViewDetail(comunicado)}
                            title="Visualizar"
                          >
                            <Eye className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleEdit(comunicado)}
                            title="Editar"
                          >
                            <Edit className="w-4 h-4" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => handleDelete(comunicado)}
                            title="Remover"
                            className="text-red-500 hover:text-red-700"
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

            {/* Pagination */}
            {totalPages > 1 && (
              <div className="flex items-center justify-between px-4 py-3 border-t border-[hsl(var(--border))]">
                <p className="text-sm text-[hsl(var(--muted-foreground))]">
                  Mostrando {(page - 1) * ITEMS_PER_PAGE + 1} a{' '}
                  {Math.min(page * ITEMS_PER_PAGE, filteredComunicados.length)} de{' '}
                  {filteredComunicados.length} registros
                </p>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    disabled={page === 1}
                  >
                    Anterior
                  </Button>
                  <span className="text-sm text-[hsl(var(--foreground))]">
                    {page} / {totalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                  >
                    Proximo
                  </Button>
                </div>
              </div>
            )}
          </div>
        ) : (
          /* Empty State */
          <div className="text-center py-12 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl">
            <Megaphone className="w-12 h-12 text-[hsl(var(--muted-foreground))] mx-auto mb-4" />
            <h3 className="text-lg font-medium text-[hsl(var(--foreground))]">
              Nenhum comunicado encontrado
            </h3>
            <p className="text-[hsl(var(--muted-foreground))] mt-1">
              {search || tipoFilter !== 'all'
                ? 'Nenhum comunicado corresponde aos filtros aplicados.'
                : 'Crie o primeiro comunicado para enviar a equipe em campo.'}
            </p>
            {search || tipoFilter !== 'all' ? (
              <Button
                variant="outline"
                size="sm"
                className="mt-4"
                onClick={() => {
                  setSearch('');
                  setTipoFilter('all');
                  setPage(1);
                }}
              >
                Limpar Filtros
              </Button>
            ) : (
              <Button variant="primary" size="sm" className="mt-4" onClick={handleCreate}>
                <Plus className="w-4 h-4 mr-2" />
                Novo Comunicado
              </Button>
            )}
          </div>
        )}
      </main>

      {/* Form Modal */}
      <ComunicadoFormModal
        isOpen={formOpen}
        onClose={() => { setFormOpen(false); setSelectedComunicado(null); }}
        comunicado={selectedComunicado}
        onSubmit={handleSubmit}
        isLoading={isSubmitting}
      />

      {/* Detail Modal */}
      <ComunicadoDetailModal
        isOpen={detailOpen}
        onClose={() => { setDetailOpen(false); setSelectedComunicado(null); }}
        comunicado={selectedComunicado}
      />
    </div>
  );
}
