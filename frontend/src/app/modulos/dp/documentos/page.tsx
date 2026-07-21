'use client';

import { useState, useEffect, useMemo, useRef } from 'react';
import { msgFromDetail } from '@/lib/string';
import { abrirPdf } from '@/lib/pdf';
import { FolderOpen, ArrowLeft, Inbox, Loader2, Eye, Download, X, Save, Upload, Search, Filter, ChevronLeft, ChevronRight as ChevronRightIcon, FileUp } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { toast } from 'sonner';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PageHeader } from '@/components/ui/page-header';

const API_BASE = '/api/v1/people-management/hr';
const GED_UPLOAD_URL = '/api/v1/ged/documents/upload';
const GED_FUNCIONARIOS_FOLDER = 'abcbebd2-88af-419e-8907-43b11f38f90b';
const ACCEPT_TYPES = '.pdf,.doc,.docx,.jpg,.jpeg,.png,.xlsx,.xls';
const MAX_SIZE_MB = 10;

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

// Mapa de exibição alinhado ao vocabulário REAL de hr_employee_documents.status.
// Hoje o banco grava 'draft' (→ Rascunho). Demais chaves cobrem estados futuros.
const statusConfig: Record<string, { label: string; className: string }> = {
  draft: { label: 'Rascunho', className: 'bg-yellow-500 text-white' },
  active: { label: 'Ativo', className: 'bg-green-500 text-white' },
  valid: { label: 'Valido', className: 'bg-green-500 text-white' },
  valido: { label: 'Valido', className: 'bg-green-500 text-white' },
  expired: { label: 'Vencido', className: 'bg-red-500 text-white' },
  vencido: { label: 'Vencido', className: 'bg-red-500 text-white' },
  pending: { label: 'Pendente', className: 'bg-yellow-500 text-white' },
  pendente: { label: 'Pendente', className: 'bg-yellow-500 text-white' },
  archived: { label: 'Arquivado', className: 'bg-gray-500 text-white' },
};

// Chaves exibidas como chips de filtro — refletem os status que REALMENTE ocorrem no banco.
const STATUS_CHIPS = ['draft', 'active', 'expired', 'archived'];

const PAGE_SIZE = 15;

export default function DocumentosPage() {
  const router = useRouter();
  const [documentos, setDocumentos] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalItems, setTotalItems] = useState(0);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [employees, setEmployees] = useState<any[]>([]);
  const [formData, setFormData] = useState({ employee_id: '', document_type: 'RG', file_name: '', expiry_date: '', notes: '' });
  const [formErrors, setFormErrors] = useState<Record<string, string>>({});
  const [refreshKey, setRefreshKey] = useState(0);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [filtroStatus, setFiltroStatus] = useState<string>('todos');
  const [sortField, setSortField] = useState<string>('');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('desc');
  const [arquivo, setArquivo] = useState<File | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load documents from API
  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const res = await fetch(`${API_BASE}/documents?page=${currentPage}&page_size=${PAGE_SIZE}`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          setDocumentos(data.items || []);
          setTotalItems(data.total || 0);
        } else {
          setDocumentos([]);
          setTotalItems(0);
        }
      } catch {
        setDocumentos([]);
        setTotalItems(0);
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [currentPage, refreshKey]);

  // Load employees for the form
  useEffect(() => {
    async function loadEmployees() {
      try {
        const res = await fetch(`${API_BASE}/employees?page_size=100`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          setEmployees(data.items || data || []);
        }
      } catch { /* skip */ }
    }
    loadEmployees();
  }, []);

  // Reset page on search/filter change
  useEffect(() => { setCurrentPage(1); }, [searchTerm, filtroStatus]);

  // Filtered + searched + sorted
  const filteredData = useMemo(() => {
    let items = [...documentos];
    if (filtroStatus !== 'todos') {
      items = items.filter(d => String(d.status || '').toLowerCase() === filtroStatus.toLowerCase());
    }
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter(d =>
        (d.title || '').toLowerCase().includes(term) ||
        (d.type || '').toLowerCase().includes(term) ||
        (d.employee_name || '').toLowerCase().includes(term) ||
        (d.file_name || '').toLowerCase().includes(term) ||
        (d.id || '').toLowerCase().includes(term)
      );
    }
    if (sortField) {
      items = [...items].sort((a, b) => {
        const va = String(a[sortField] || '').toLowerCase();
        const vb = String(b[sortField] || '').toLowerCase();
        return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
      });
    }
    return items;
  }, [documentos, filtroStatus, searchTerm, sortField, sortDir]);

  const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    } else {
      setSortField(field);
      setSortDir('asc');
    }
  };

  const sortIcon = (field: string) => {
    if (sortField !== field) return ' ↕';
    return sortDir === 'asc' ? ' ↑' : ' ↓';
  };

  const handleFileSelect = (file: File) => {
    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      toast.error(`Arquivo muito grande. Máximo: ${MAX_SIZE_MB}MB`, { duration: 5000 });
      return;
    }
    setArquivo(file);
    setFormErrors(p => ({ ...p, arquivo: '' }));
  };

  const resetForm = () => {
    setFormData({ employee_id: '', document_type: 'RG', file_name: '', expiry_date: '', notes: '' });
    setFormErrors({});
    setArquivo(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="space-y-6 pb-28">
      <PageHeader
        icon={<FolderOpen className="h-5 w-5" />}
        title="Documentos de Colaboradores"
        subtitle="Gestão de documentos dos colaboradores"
        actions={(
          <>
            <Button type="button" variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
              <ArrowLeft className="h-4 w-4" />
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => setFiltroStatus('todos')}>
              <Filter className="h-4 w-4 mr-1" /> Todos
            </Button>
            <Button type="button" size="sm" onClick={() => setShowForm(true)}>
              <Upload className="h-4 w-4 mr-1" /> Upload Documento
            </Button>
          </>
        )}
      />

      {/* Status filter badges */}
      <div className="flex gap-2 flex-wrap">
        {STATUS_CHIPS.map((key) => {
          const val = statusConfig[key]!;
          return (
            <Badge
              key={key}
              className={`cursor-pointer ${filtroStatus === key ? val.className : 'bg-muted text-muted-foreground'}`}
              onClick={() => setFiltroStatus(filtroStatus === key ? 'todos' : key)}
            >
              {val.label}
            </Badge>
          );
        })}
      </div>

      {showForm && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              <CardTitle>Novo Documento</CardTitle>
              <Button type="button" variant="ghost" size="sm" onClick={() => setShowForm(false)}><X className="h-4 w-4" /></Button>
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Colaborador *</label>
                <select value={formData.employee_id} onChange={e => { setFormData(p => ({ ...p, employee_id: e.target.value })); setFormErrors(p => ({ ...p, employee_id: '' })); }} className={`w-full px-3 py-2 border rounded-md text-sm ${formErrors.employee_id ? 'border-red-500' : ''}`}>
                  <option value="">Selecione o colaborador</option>
                  {employees.map((emp: any) => (
                    <option key={emp.id} value={emp.id}>{emp.nome || emp.name}</option>
                  ))}
                </select>
                {formErrors.employee_id && <p className="text-red-500 text-xs mt-1">{formErrors.employee_id}</p>}
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Tipo de Documento</label>
                <select value={formData.document_type} onChange={e => setFormData(p => ({ ...p, document_type: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm">
                  <option value="RG">RG</option>
                  <option value="CPF">CPF</option>
                  <option value="CTPS">CTPS</option>
                  <option value="Comprovante_Residencia">Comprovante de Residencia</option>
                  <option value="Certificado">Certificado</option>
                  <option value="Certidao">Certidao</option>
                  <option value="CNH">CNH</option>
                  <option value="Titulo_Eleitor">Titulo de Eleitor</option>
                  <option value="Outro">Outro</option>
                </select>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Arquivo *</label>
                <div
                  className={`w-full border-2 border-dashed rounded-md p-4 text-center cursor-pointer transition-colors ${dragOver ? 'border-primary bg-primary/5' : formErrors.arquivo ? 'border-red-500' : 'border-muted-foreground/30 hover:border-primary/50'}`}
                  onClick={() => fileInputRef.current?.click()}
                  onDragOver={e => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={e => { e.preventDefault(); setDragOver(false); const f = e.dataTransfer.files[0]; if (f) handleFileSelect(f); }}
                >
                  {arquivo ? (
                    <div className="flex items-center justify-center gap-2 text-sm">
                      <FileUp className="h-4 w-4 text-primary" />
                      <span className="font-medium text-primary truncate max-w-[200px]">{arquivo.name}</span>
                      <span className="text-muted-foreground">({(arquivo.size / 1024).toFixed(0)} KB)</span>
                      <button type="button" className="ml-1 text-muted-foreground hover:text-destructive" onClick={e => { e.stopPropagation(); setArquivo(null); if (fileInputRef.current) fileInputRef.current.value = ''; }}>
                        <X className="h-3 w-3" />
                      </button>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center gap-1 text-muted-foreground">
                      <Upload className="h-6 w-6" />
                      <p className="text-sm">Clique ou arraste o arquivo aqui</p>
                      <p className="text-xs">PDF, DOC, DOCX, JPG, PNG, XLSX — máx. {MAX_SIZE_MB}MB</p>
                    </div>
                  )}
                </div>
                <input ref={fileInputRef} type="file" accept={ACCEPT_TYPES} className="hidden" onChange={e => { const f = e.target.files?.[0]; if (f) handleFileSelect(f); }} />
                {formErrors.arquivo && <p className="text-red-500 text-xs mt-1">{formErrors.arquivo}</p>}
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Data de Validade</label>
                <input type="date" value={formData.expiry_date} onChange={e => setFormData(p => ({ ...p, expiry_date: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
              </div>
              <div className="md:col-span-2">
                <label className="text-sm font-medium mb-1 block">Observações</label>
                <textarea value={formData.notes} onChange={e => setFormData(p => ({ ...p, notes: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" rows={3} placeholder="Observações adicionais" />
              </div>
            </div>
            <div className="flex gap-2 mt-4">
              <Button type="button" size="sm" disabled={saving} onClick={async () => {
                const errors: Record<string, string> = {};
                if (!formData.employee_id) errors.employee_id = 'Colaborador é obrigatório';
                if (!arquivo) errors.arquivo = 'Selecione um arquivo';
                if (Object.keys(errors).length > 0) { setFormErrors(errors); toast.error('Corrija os campos destacados', { duration: 5000 }); return; }
                setSaving(true);
                try {
                  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
                  const fd = new FormData();
                  const file = arquivo as File;
                  fd.append('file', file);
                  fd.append('title', file.name);
                  fd.append('folder_id', GED_FUNCIONARIOS_FOLDER);
                  fd.append('category', 'rh');
                  fd.append('document_type', formData.document_type.toLowerCase());
                  if (formData.employee_id) fd.append('employee_id', formData.employee_id);
                  if (formData.expiry_date) fd.append('valid_until', formData.expiry_date);
                  if (formData.notes) fd.append('description', formData.notes);
                  const res = await fetch(GED_UPLOAD_URL, {
                    method: 'POST',
                    headers: token ? { Authorization: `Bearer ${token}` } : {},
                    body: fd,
                  });
                  if (res.ok) {
                    setShowForm(false);
                    resetForm();
                    setRefreshKey(k => k + 1);
                    toast.success('Documento enviado com sucesso!', { duration: 4000 });
                  } else {
                    const err = await res.json().catch(() => null);
                    toast.error(msgFromDetail(err?.detail) || 'Erro ao enviar documento', { duration: 5000 });
                  }
                } catch { toast.error('Erro de conexão', { duration: 5000 }); } finally { setSaving(false); }
              }}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {saving ? 'Salvando...' : 'Registrar Documento'}
              </Button>
              <Button type="button" variant="outline" size="sm" onClick={() => { setShowForm(false); resetForm(); }}>Cancelar</Button>
            </div>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Documentos</CardTitle>
            <div className="relative w-64">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
              <input
                type="text"
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                placeholder="Buscar por titulo, tipo..."
                className="w-full pl-9 pr-3 py-2 border rounded-md text-sm"
              />
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
          ) : filteredData.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Inbox className="h-12 w-12 mb-3" />
              <p className="font-medium">Nenhum documento encontrado</p>
              <p className="text-sm text-muted-foreground mt-1">
                {searchTerm ? 'Tente outra busca.' : 'Clique em "Upload Documento" para adicionar.'}
              </p>
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('title')}>Titulo{sortIcon('title')}</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('type')}>Tipo{sortIcon('type')}</TableHead>
                    <TableHead className="cursor-pointer select-none" onClick={() => handleSort('status')}>Status{sortIcon('status')}</TableHead>
                    <TableHead>ID</TableHead>
                    <TableHead>Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {filteredData.map((item, i) => {
                    const st = statusConfig[String(item.status || '').toLowerCase()] || { label: item.status || 'N/A', className: 'bg-gray-500 text-white' };
                    return (
                      <TableRow key={item.id || i}>
                        <TableCell className="font-medium">{item.title || '-'}</TableCell>
                        <TableCell>{item.type || '-'}</TableCell>
                        <TableCell><Badge className={st.className}>{st.label}</Badge></TableCell>
                        <TableCell className="text-xs text-muted-foreground">{item.id ? item.id.slice(0, 8) + '...' : '-'}</TableCell>
                        <TableCell>
                          <div className="flex gap-1">
                            <Button type="button" variant="outline" size="sm" title="Visualizar"
                              onClick={() => abrirPdf(`${API_BASE}/documents/${item.id}/download`)}><Eye className="h-3 w-3" /></Button>
                            <Button type="button" variant="outline" size="sm" title="Baixar"
                              onClick={() => abrirPdf(`${API_BASE}/documents/${item.id}/download`, { download: true, nome: (item.file_name || item.title || 'documento') + '.pdf' })}><Download className="h-3 w-3" /></Button>
                          </div>
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>

              {/* Pagination */}
              <div className="flex items-center justify-between mt-4 text-sm">
                <span className="text-muted-foreground">
                  {totalItems} registro{totalItems !== 1 ? 's' : ''} — Pagina {currentPage} de {totalPages}
                </span>
                <div className="flex gap-1">
                  <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)}>
                    <ChevronLeft className="h-4 w-4" />
                  </Button>
                  {Array.from({ length: Math.min(totalPages, 5) }, (_, i) => {
                    const page = totalPages <= 5 ? i + 1 : Math.max(1, Math.min(currentPage - 2, totalPages - 4)) + i;
                    return (
                      <Button key={page} variant={currentPage === page ? 'default' : 'outline'} size="sm" onClick={() => setCurrentPage(page)}>
                        {page}
                      </Button>
                    );
                  })}
                  <Button variant="outline" size="sm" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => p + 1)}>
                    <ChevronRightIcon className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
