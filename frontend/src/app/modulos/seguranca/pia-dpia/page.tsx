'use client';

import { FileText, Search, RefreshCw, Plus, MoreHorizontal, Eye, AlertCircle, Loader2 } from 'lucide-react';
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
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
;
import { usePIA, useCreateSimplePIA, useCreateCompletePIA } from '@/hooks/security-lgpd';
import { PIAFormModal } from '@/components/seguranca/pia-form-modal';
import { PIADetailModal } from '@/components/seguranca/pia-detail-modal';

interface PIAItem {
  id: string;
  title: string;
  pia_type: 'simple' | 'complete';
  status: 'draft' | 'in_progress' | 'completed' | 'archived';
  risk_level: 'low' | 'medium' | 'high' | 'critical';
  responsible: string;
  created_at: string;
  description?: string;
  data_types?: string;
  processing_purpose?: string;
}

const statusLabels: Record<string, string> = {
  draft: 'Rascunho',
  in_progress: 'Em Andamento',
  completed: 'Concluida',
  archived: 'Arquivada',
};

const statusVariants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  draft: 'secondary',
  in_progress: 'default',
  completed: 'outline',
  archived: 'secondary',
};

const riskLabels: Record<string, string> = {
  low: 'Baixo',
  medium: 'Medio',
  high: 'Alto',
  critical: 'Critico',
};

const riskVariants: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  low: 'outline',
  medium: 'secondary',
  high: 'default',
  critical: 'destructive',
};

const typeLabels: Record<string, string> = {
  simple: 'Simples',
  complete: 'Completa',
};

export default function PIADPIAPage() {
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [riskFilter, setRiskFilter] = useState('all');
  const [formModalOpen, setFormModalOpen] = useState(false);
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [selectedPIA, setSelectedPIA] = useState<PIAItem | null>(null);
  const [piaType, setPiaType] = useState<'simple' | 'complete'>('simple');

  // Buscar lista de PIAs (usa ID vazio com enabled=false para lista)
  const { data: piaData, isLoading, refetch } = usePIA('', false);
  const createSimplePIA = useCreateSimplePIA();
  const createCompletePIA = useCreateCompletePIA();

  const items: PIAItem[] = (piaData as any)?.data?.items || (piaData as any)?.items || [];

  const filteredItems = items.filter((item) => {
    const matchesSearch =
      !search ||
      item.title.toLowerCase().includes(search.toLowerCase()) ||
      item.responsible?.toLowerCase().includes(search.toLowerCase());
    const matchesStatus = statusFilter === 'all' || item.status === statusFilter;
    const matchesRisk = riskFilter === 'all' || item.risk_level === riskFilter;
    return matchesSearch && matchesStatus && matchesRisk;
  });

  const totalAssessments = items.length;
  const inProgress = items.filter((i) => i.status === 'in_progress').length;
  const highRisk = items.filter(
    (i) => i.risk_level === 'high' || i.risk_level === 'critical'
  ).length;

  const handleOpenForm = (type: 'simple' | 'complete') => {
    setPiaType(type);
    setFormModalOpen(true);
  };

  const handleSubmitPIA = async (formData: {
    title: string;
    description: string;
    responsible: string;
    data_types: string;
    processing_purpose: string;
  }) => {
    const dataCategories = formData.data_types
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);

    if (piaType === 'simple') {
      await createSimplePIA.mutateAsync({
        projectName: formData.title,
        description: formData.description,
        dataCategories,
      });
    } else {
      const purposes = formData.processing_purpose
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
      await createCompletePIA.mutateAsync({
        projectName: formData.title,
        description: formData.description,
        dataCategories,
        processingPurposes: purposes,
        dataSubjects: [],
        riskFactors: [],
      });
    }

    setFormModalOpen(false);
    refetch();
  };

  const handleViewDetail = (pia: PIAItem) => {
    setSelectedPIA(pia);
    setDetailModalOpen(true);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-display text-2xl font-bold flex items-center gap-2">
            <FileText className="h-6 w-6" />
            PIA / DPIA
          </h1>
          <p className="text-muted-foreground">
            Avaliacao de Impacto a Protecao de Dados
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Atualizar
          </Button>
          <Button variant="outline" onClick={() => handleOpenForm('simple')}>
            <Plus className="h-4 w-4 mr-2" />
            PIA Simples
          </Button>
          <Button onClick={() => handleOpenForm('complete')}>
            <Plus className="h-4 w-4 mr-2" />
            PIA Completa
          </Button>
        </div>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Avaliacoes</CardTitle>
            <FileText className="h-4 w-4 text-blue-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-blue-600">{totalAssessments}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Em Andamento</CardTitle>
            <RefreshCw className="h-4 w-4 text-amber-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-amber-600">{inProgress}</div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Alto Risco</CardTitle>
            <AlertCircle className="h-4 w-4 text-red-600" />
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            ) : (
              <div className="font-data text-2xl font-semibold tabular-nums text-red-600">{highRisk}</div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex items-center gap-4">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Buscar por titulo ou responsavel..."
            className="pl-10"
          />
        </div>
        <Select value={statusFilter} onValueChange={setStatusFilter} aria-label="Status Filter">
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os Status</SelectItem>
            <SelectItem value="draft">Rascunho</SelectItem>
            <SelectItem value="in_progress">Em Andamento</SelectItem>
            <SelectItem value="completed">Concluida</SelectItem>
            <SelectItem value="archived">Arquivada</SelectItem>
          </SelectContent>
        </Select>
        <Select value={riskFilter} onValueChange={setRiskFilter} aria-label="Risk Filter">
          <SelectTrigger className="w-[180px]">
            <SelectValue placeholder="Risco" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos os Riscos</SelectItem>
            <SelectItem value="low">Baixo</SelectItem>
            <SelectItem value="medium">Medio</SelectItem>
            <SelectItem value="high">Alto</SelectItem>
            <SelectItem value="critical">Critico</SelectItem>
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="flex items-center justify-center py-12">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : filteredItems.length === 0 ? (
            <div className="text-center py-12 text-muted-foreground">
              <FileText className="h-12 w-12 mx-auto mb-4 opacity-50" />
              <p className="font-medium">Nenhuma avaliacao encontrada</p>
              <p className="text-sm mt-1">Crie uma nova PIA para comecar</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Titulo</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Nivel Risco</TableHead>
                  <TableHead>Responsavel</TableHead>
                  <TableHead>Data</TableHead>
                  <TableHead className="w-[60px]">Ações</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredItems.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-medium">{item.title}</TableCell>
                    <TableCell>
                      <Badge variant={item.pia_type === 'complete' ? 'default' : 'secondary'}>
                        {typeLabels[item.pia_type] || item.pia_type}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={statusVariants[item.status] || 'secondary'}>
                        {statusLabels[item.status] || item.status}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant={riskVariants[item.risk_level] || 'secondary'}>
                        {riskLabels[item.risk_level] || item.risk_level}
                      </Badge>
                    </TableCell>
                    <TableCell>{item.responsible}</TableCell>
                    <TableCell>
                      {item.created_at
                        ? new Date(item.created_at).toLocaleDateString('pt-BR')
                        : '-'}
                    </TableCell>
                    <TableCell>
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant="ghost" size="icon" className="h-8 w-8">
                            <MoreHorizontal className="h-4 w-4" />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align="end">
                          <DropdownMenuItem onClick={() => handleViewDetail(item)}>
                            <Eye className="h-4 w-4 mr-2" />
                            Visualizar
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

      {/* Modals */}
      <PIAFormModal
        isOpen={formModalOpen}
        onClose={() => setFormModalOpen(false)}
        onSubmit={handleSubmitPIA}
        isLoading={createSimplePIA.isPending || createCompletePIA.isPending}
        piaType={piaType}
      />

      <PIADetailModal
        isOpen={detailModalOpen}
        onClose={() => setDetailModalOpen(false)}
        pia={selectedPIA}
      />
    </div>
  );
}
