'use client';

import { useState, useEffect } from 'react';
import { useParams, useRouter } from 'next/navigation';
import {
  Loader2, ArrowLeft, Send, CheckCircle, XCircle,
  Download, FileText, Building2, User, Eye, Calendar, AlertCircle, PenTool,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';

const API_BASE = '/api/v1/ged';

function getAuthHeaders() {
  let token: string | null = null;
  try {
    token = localStorage.getItem('access_token') || localStorage.getItem('token');
  } catch {
    token = null;
  }
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  } as HeadersInit;
}

function showToast(msg: string, type: 'success' | 'error' = 'success') {
  const el = document.createElement('div');
  el.className = `fixed top-4 right-4 z-[9999] px-4 py-3 rounded-lg shadow-lg text-sm font-medium text-white transition-opacity ${type === 'error' ? 'bg-red-500' : 'bg-emerald-500'}`;
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { el.style.opacity = '0'; setTimeout(() => el.remove(), 300); }, 3000);
}

function formatRefMonth(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso + (iso.length === 10 ? 'T12:00:00' : ''));
  return new Intl.DateTimeFormat('pt-BR', { month: '2-digit', year: 'numeric' }).format(d);
}

interface KitDocument {
  id: string;
  name: string;
  document_type: string;
  signed: boolean;
  origin: string;
  category: 'employee' | 'company';
  employee_name?: string | null;
  file_path?: string;
  created_at?: string;
}

interface KitDetail {
  id: string;
  client_name: string;
  client_id: string;
  reference_month: string;
  status: string;
  completion_percentage: number;
  total_documents: number;
  documents_signed: number;
  documents: KitDocument[];
  created_at: string;
}

interface ChecklistItem {
  tipo: string;
  categoria: string;
  status: 'pronto' | 'pendente';
  nome?: string;
}

interface Checklist {
  total: number;
  prontos: number;
  pendentes: number;
  percentual: number;
  checklist: ChecklistItem[];
}

interface SignaturePendency {
  document_id: string;
  document_type: string;
  document_name?: string;
  employee_name?: string | null;
  situacao: string;
}

interface SignatureStatus {
  assinaveis: number;
  com_solicitacao: number;
  assinados: number;
  pendentes: number;
  sem_solicitacao: number;
  pode_fechar: boolean;
  pendencias: SignaturePendency[];
}

const statusColors: Record<string, string> = {
  em_montagem: 'bg-amber-500/10 text-amber-500 border border-amber-500/30',
  completo: 'bg-blue-500/10 text-blue-500 border border-blue-500/30',
  enviado: 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30',
  conferido: 'bg-purple-500/10 text-purple-500 border border-purple-500/30',
  aprovado: 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30',
};

const statusLabels: Record<string, string> = {
  em_montagem: 'Em Montagem',
  completo: 'Completo',
  enviado: 'Enviado',
  conferido: 'Conferido',
  aprovado: 'Aprovado',
};

const typeLabels: Record<string, string> = {
  folha_ponto: 'Folha de Ponto',
  contracheque: 'Contracheque',
  comprovante_va: 'Vale Alimentação',
  comprovante_vr: 'Vale Refeição',
  comprovante_vt: 'Vale Transporte',
  escala_mes: 'Escala do Mês',
  cnd_federal: 'CND Federal',
  cnd_estadual: 'CND Estadual',
  cnd_municipal: 'CND Municipal',
  cnd_trabalhista: 'CND Trabalhista',
  cndt_trabalhista: 'CNDT Trabalhista',
  crf_fgts: 'CRF FGTS',
  cnd_caixa: 'CRF FGTS (CEF)',
  cnd_receita: 'CND Receita Federal',
  cnd_sefaz: 'CND SEFAZ',
  cnd_prefeitura: 'CND Prefeitura',
  nfse: 'NFS-e',
  folha_pagamento: 'Folha de Pagamento',
  folhas_ponto_consolidado: 'Folhas de Ponto (Consolidado)',
  contracheques_consolidado: 'Contracheques (Consolidado)',
  recibo_vt_va: 'Recibo VT/VA',
  comprovante_salario: 'Extrato Bancário',
  comprovante_fgts: 'Comprovante FGTS',
  boleto_nfse: 'Boleto NFS-e',
  dctf_declaracao: 'DCTFWeb',
  dctf_extrato: 'EFD-Reinf',
  dctf_recibo: 'DARF IRRF',
  gfd_fgts: 'INSS Patronal',
  relatorio_gfd_fgts: 'ISS Retido',
};

const originLabels: Record<string, string> = {
  dp: 'Depto Pessoal',
  rh: 'Recursos Humanos',
  fiscal: 'Fiscal',
  contabil: 'Contábil',
  financeiro: 'Financeiro',
  operacoes: 'Operacional',
  banco: 'Banco',
  sistema: 'Sistema',
};

export default function KitDetailPage() {
  const params = useParams();
  const router = useRouter();
  const kitId = params.id as string;
  const [kit, setKit] = useState<KitDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'employee' | 'company'>('company');
  const [exporting, setExporting] = useState(false);
  const [checklist, setChecklist] = useState<Checklist | null>(null);
  const [sig, setSig] = useState<SignatureStatus | null>(null);
  const [requestingSig, setRequestingSig] = useState(false);

  useEffect(() => { if (kitId) { fetchKit(); fetchSignatures(); } }, [kitId]);

  async function fetchSignatures() {
    try {
      const res = await fetch(`${API_BASE}/kits/${kitId}/assinaturas`, { headers: getAuthHeaders() });
      if (res.ok) setSig(await res.json());
    } catch {
      // status de assinatura é opcional — falha silenciosa
    }
  }

  async function handleRequestSignatures() {
    setRequestingSig(true);
    try {
      const res = await fetch(`${API_BASE}/kits/${kitId}/solicitar-assinaturas`, {
        method: 'POST', headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        showToast(`${data.solicitadas} nova(s) solicitação(ões); ${data.ja_existentes} já existiam`);
        if (data.status) setSig(data.status);
        fetchKit();
      } else {
        showToast('Erro ao solicitar assinaturas', 'error');
      }
    } catch {
      showToast('Erro de conexão ao solicitar assinaturas', 'error');
    } finally {
      setRequestingSig(false);
    }
  }

  async function fetchKit() {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/kits/${kitId}`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setKit(data);
        if (!data.documents || data.documents.length === 0) {
          fetchChecklist();
        }
      } else {
        showToast('Erro ao carregar kit', 'error');
      }
    } catch {
      showToast('Erro de conexão', 'error');
    } finally {
      setLoading(false);
    }
  }

  async function fetchChecklist() {
    try {
      const res = await fetch(`/api/v1/ged/kit-real/${kitId}/checklist`, { headers: getAuthHeaders() });
      if (res.ok) setChecklist(await res.json());
    } catch {
      // checklist é opcional — falha silenciosa
    }
  }

  async function handleSendKit() {
    if (!confirm('Confirma o envio deste kit ao cliente?')) return;
    try {
      const res = await fetch(`${API_BASE}/kits/${kitId}/send`, { method: 'POST', headers: getAuthHeaders() });
      if (res.ok) { showToast('Kit enviado com sucesso'); fetchKit(); fetchSignatures(); }
      else {
        const e = await res.json().catch(() => null);
        const detail = e?.detail;
        const msg = typeof detail === 'string' ? detail : (detail?.message || 'Erro ao enviar');
        showToast(msg, 'error');
        if (detail?.assinaturas) setSig(detail.assinaturas);
      }
    } catch { showToast('Erro de conexão', 'error'); }
  }

  async function handleApproveKit() {
    if (!confirm('Confirma a aprovação deste kit?')) return;
    try {
      const res = await fetch(`${API_BASE}/kits/${kitId}/approve`, { method: 'POST', headers: getAuthHeaders() });
      if (res.ok) { showToast('Kit aprovado com sucesso'); fetchKit(); }
      else { const e = await res.json().catch(() => null); showToast(e?.detail || 'Erro ao aprovar', 'error'); }
    } catch { showToast('Erro de conexão', 'error'); }
  }

  async function handleDownloadZip() {
    setExporting(true);
    try {
      const res = await fetch(`${API_BASE}/kits/${kitId}/download-zip`, { headers: getAuthHeaders() });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `kit-${kit?.client_name || kitId}.zip`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        showToast('Download ZIP iniciado');
      } else {
        showToast('Erro ao gerar ZIP', 'error');
      }
    } catch {
      showToast('Erro de conexão ao baixar ZIP', 'error');
    } finally {
      setExporting(false);
    }
  }

  async function handleDownloadDoc(doc: KitDocument) {
    if (!doc.file_path) { showToast('Arquivo não disponível', 'error'); return; }
    try {
      const res = await fetch(`/api/v1/people-management/ged/documents/${doc.id}/download`, { headers: getAuthHeaders() });
      if (res.ok) {
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = doc.name || `doc-${doc.id}.pdf`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
      } else {
        showToast('Arquivo não encontrado', 'error');
      }
    } catch {
      showToast('Erro ao baixar documento', 'error');
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <Loader2 className="h-8 w-8 animate-spin text-[hsl(var(--muted-foreground))]" />
        <span className="ml-2 text-[hsl(var(--muted-foreground))]">Carregando kit...</span>
      </div>
    );
  }

  if (!kit) {
    return (
      <div className="p-6 text-center">
        <p className="text-[hsl(var(--muted-foreground))] mb-4">Kit não encontrado.</p>
        <button onClick={() => router.push('/modulos/gestao-pessoas/ged/kits')} className="text-blue-400 hover:underline">
          ← Voltar para Kits
        </button>
      </div>
    );
  }

  const employeeDocs = (kit.documents || []).filter((d) => d.category === 'employee');
  const companyDocs = (kit.documents || []).filter((d) => d.category === 'company');
  const activeDocs = activeTab === 'employee' ? employeeDocs : companyDocs;
  const isUsingChecklist = (kit.documents || []).length === 0 && checklist;
  const companyLabel = isUsingChecklist
    ? `${checklist!.checklist.filter((i) => i.categoria === 'empresa').length} esperados`
    : String(companyDocs.length);
  const employeeLabel = isUsingChecklist
    ? `${checklist!.checklist.filter((i) => i.categoria !== 'empresa').length} esperados`
    : String(employeeDocs.length);

  return (
    <div className="p-6 space-y-6">
      <button onClick={() => router.push('/modulos/gestao-pessoas/ged/kits')} className="flex items-center gap-2 text-sm text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]">
        <ArrowLeft className="h-4 w-4" />Voltar para Kits
      </button>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">{kit.client_name}</h1>
            <span className={`inline-flex px-2.5 py-1 text-xs font-medium rounded-full ${statusColors[kit.status] || 'bg-gray-500/10 text-[hsl(var(--muted-foreground))] border border-gray-500/30'}`}>
              {statusLabels[kit.status] || kit.status}
            </span>
          </div>
          <p className="text-[hsl(var(--muted-foreground))] mt-1">
            Referência: {formatRefMonth(kit.reference_month)} | {kit.documents?.length || kit.total_documents} documentos | {kit.documents_signed} assinados
          </p>
          <span className="inline-block mt-1 text-xs text-orange-500 bg-orange-500/10 border border-orange-500/30 rounded px-2 py-0.5">
            GED — Montagem de Kit para Cliente
          </span>
        </div>
        <div className="flex flex-wrap gap-2">
          {sig && sig.assinaveis > 0 && (
            <button onClick={handleRequestSignatures} disabled={requestingSig} className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-violet-600 text-white rounded-lg hover:bg-violet-700 disabled:opacity-50">
              {requestingSig ? <Loader2 className="h-4 w-4 animate-spin" /> : <PenTool className="h-4 w-4" />}Solicitar assinaturas
            </button>
          )}
          <button onClick={handleSendKit} disabled={kit.status === 'enviado' || kit.status === 'aprovado'} className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50">
            <Send className="h-4 w-4" />Enviar
          </button>
          <button onClick={handleApproveKit} disabled={kit.status === 'aprovado'} className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-green-600 text-white rounded-lg hover:bg-green-700 disabled:opacity-50">
            <CheckCircle className="h-4 w-4" />Aprovar
          </button>
          <button onClick={handleDownloadZip} disabled={exporting} className="flex items-center gap-2 px-3 py-2 text-sm font-medium bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg hover:bg-[hsl(var(--secondary))] disabled:opacity-50">
            {exporting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" />}
            ZIP
          </button>
        </div>
      </div>

      {/* Progresso */}
      <Card className="border border-[hsl(var(--border))]">
        <CardContent className="p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium text-[hsl(var(--foreground))]">Progresso do Kit</span>
            <span className="font-data text-sm font-semibold tabular-nums text-[hsl(var(--foreground))]">{Math.round(kit.completion_percentage)}%</span>
          </div>
          <div className="w-full bg-[hsl(var(--secondary))] rounded-full h-3">
            <div className="bg-blue-600 h-3 rounded-full transition-all duration-500" style={{ width: `${kit.completion_percentage}%` }} />
          </div>
          <div className="flex justify-between mt-2 text-xs text-[hsl(var(--muted-foreground))]">
            <span>{kit.documents_signed} assinados</span>
            <span>{kit.documents?.length || kit.total_documents} total</span>
          </div>
        </CardContent>
      </Card>

      {/* Assinaturas do funcionário nos documentos do kit */}
      {sig && sig.assinaveis > 0 && (
        <Card className="border border-[hsl(var(--border))]">
          <CardContent className="p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium text-[hsl(var(--foreground))] flex items-center gap-2">
                <PenTool className="h-4 w-4 text-violet-500" /> Assinaturas do funcionário
              </span>
              <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${sig.pode_fechar ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30' : 'bg-amber-500/10 text-amber-500 border border-amber-500/30'}`}>
                {sig.pode_fechar ? 'Todas assinadas' : `${sig.pendentes} pendente(s)`}
              </span>
            </div>
            <div className="text-xs text-[hsl(var(--muted-foreground))] mb-3">
              {sig.assinados}/{sig.assinaveis} documentos assinados
              {sig.sem_solicitacao > 0 && ` • ${sig.sem_solicitacao} sem solicitação (clique em "Solicitar assinaturas")`}
              {!sig.pode_fechar && ' • o kit só pode ser entregue quando não houver pendências'}
            </div>
            {sig.pendencias.length > 0 && (
              <ul className="space-y-1 max-h-48 overflow-y-auto">
                {sig.pendencias.slice(0, 30).map((p) => (
                  <li key={p.document_id} className="flex items-center gap-2 text-xs">
                    <XCircle className="h-3.5 w-3.5 text-amber-500 flex-shrink-0" />
                    <span className="text-[hsl(var(--foreground))]">{p.employee_name || '—'}</span>
                    <span className="text-[hsl(var(--muted-foreground))]">— {typeLabels[p.document_type] || p.document_type?.replace(/_/g, ' ')}</span>
                    <span className="ml-auto text-[10px] px-1.5 py-0.5 rounded bg-[hsl(var(--secondary))] text-[hsl(var(--muted-foreground))]">
                      {p.situacao === 'sem_solicitacao' ? 'sem solicitação' : 'aguardando'}
                    </span>
                  </li>
                ))}
                {sig.pendencias.length > 30 && (
                  <li className="text-xs text-[hsl(var(--muted-foreground))] italic">
                    +{sig.pendencias.length - 30} pendência(s)…
                  </li>
                )}
              </ul>
            )}
          </CardContent>
        </Card>
      )}

      {/* Tabs */}
      <div className="flex border-b border-[hsl(var(--border))]">
        <button onClick={() => setActiveTab('company')} className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'company' ? 'border-blue-500 text-blue-400' : 'border-transparent text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'}`}>
          <Building2 className="h-4 w-4" />Empresa ({companyLabel})
        </button>
        <button onClick={() => setActiveTab('employee')} className={`flex items-center gap-2 px-4 py-3 text-sm font-medium border-b-2 transition-colors ${activeTab === 'employee' ? 'border-blue-500 text-blue-400' : 'border-transparent text-[hsl(var(--muted-foreground))] hover:text-[hsl(var(--foreground))]'}`}>
          <User className="h-4 w-4" />Funcionário ({employeeLabel})
        </button>
      </div>

      {/* Tabela de documentos ou checklist de montagem */}
      {(kit.documents || []).length === 0 && checklist ? (
        <Card className="border border-[hsl(var(--border))]">
          <CardContent className="p-4">
            <div className="flex items-center gap-2 mb-4 text-amber-500 bg-amber-500/10 border border-amber-500/30 rounded-lg px-4 py-3">
              <AlertCircle className="h-4 w-4 flex-shrink-0" />
              <span className="text-sm font-medium">
                Kit em montagem — {checklist.prontos}/{checklist.total} documentos coletados ({checklist.percentual}%)
              </span>
            </div>
            <div className="space-y-2">
              {checklist.checklist.map((item, idx) => (
                <div key={idx} className="flex items-center justify-between py-2 border-b border-[hsl(var(--border))] last:border-0">
                  <div className="flex items-center gap-3">
                    {item.status === 'pronto' ? (
                      <CheckCircle className="h-4 w-4 text-emerald-500 flex-shrink-0" />
                    ) : (
                      <XCircle className="h-4 w-4 text-[hsl(var(--muted-foreground))] flex-shrink-0" />
                    )}
                    <span className="text-sm text-[hsl(var(--foreground))]">
                      {typeLabels[item.tipo] || item.nome || item.tipo?.replace(/_/g, ' ') || '—'}
                    </span>
                  </div>
                  <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${item.status === 'pronto' ? 'bg-emerald-500/10 text-emerald-500 border border-emerald-500/30' : 'bg-gray-500/10 text-[hsl(var(--muted-foreground))] border border-gray-500/30'}`}>
                    {item.status === 'pronto' ? 'Pronto' : 'Pendente'}
                  </span>
                </div>
              ))}
            </div>
          </CardContent>
        </Card>
      ) : (
        <Card className="border border-[hsl(var(--border))]">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-[hsl(var(--border))] bg-[hsl(var(--secondary))]">
                    {activeTab === 'employee' && (
                      <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Funcionário</th>
                    )}
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Documento</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Tipo</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Assinado</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Origem</th>
                    <th className="text-left py-3 px-4 font-medium text-[hsl(var(--muted-foreground))]">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {activeDocs.length === 0 ? (
                    <tr><td colSpan={activeTab === 'employee' ? 6 : 5} className="py-8 text-center text-[hsl(var(--muted-foreground))]">Nenhum documento nesta categoria</td></tr>
                  ) : (
                    activeDocs.map((doc) => (
                      <tr key={doc.id} className="border-b border-[hsl(var(--border))] hover:bg-[hsl(var(--secondary))]">
                        {activeTab === 'employee' && (
                          <td className="py-3 px-4 text-xs text-[hsl(var(--muted-foreground))] whitespace-nowrap">{doc.employee_name || '—'}</td>
                        )}
                        <td className="py-3 px-4 font-medium text-[hsl(var(--foreground))] max-w-[220px] truncate" title={doc.name}>{doc.name || '—'}</td>
                        <td className="py-3 px-4 text-[hsl(var(--muted-foreground))] text-xs">
                          <span className="inline-flex px-2 py-0.5 rounded bg-[hsl(var(--secondary))] text-[hsl(var(--foreground))]">
                            {typeLabels[doc.document_type] || doc.document_type?.replace(/_/g, ' ') || '—'}
                          </span>
                        </td>
                        <td className="py-3 px-4">
                          {doc.signed ? <CheckCircle className="h-5 w-5 text-emerald-500" /> : <XCircle className="h-5 w-5 text-[hsl(var(--muted-foreground))]" />}
                        </td>
                        <td className="py-3 px-4 text-[hsl(var(--muted-foreground))] text-xs">{originLabels[doc.origin] || doc.origin || '—'}</td>
                        <td className="py-3 px-4">
                          <button onClick={() => handleDownloadDoc(doc)} className="p-1 rounded hover:bg-[hsl(var(--secondary))]" title="Baixar documento">
                            <Download className="h-4 w-4 text-[hsl(var(--muted-foreground))]" />
                          </button>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
