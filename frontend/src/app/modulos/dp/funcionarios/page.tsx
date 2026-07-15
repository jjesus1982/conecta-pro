'use client';

import { useState, useEffect, useMemo, useCallback } from 'react';
import { msgFromDetail } from '@/lib/string';
import { useRouter, useSearchParams } from 'next/navigation';
import {
  Users, ArrowLeft, Search, Loader2, AlertTriangle, CheckCircle2, XCircle, Edit, Save, X,
  ChevronLeft, ChevronRight, User, FileText, MapPin, Building2, CreditCard, Shield, RefreshCw,
  Minus, Plus, Trash2, Pencil,
} from 'lucide-react';
import { toast } from 'sonner';
import { validateCPF } from '@/utils/validators';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';
import { BotaoGerarContrato } from '@/app/modulos/gestao-pessoas/dp/components/BotaoGerarContrato';
import { BotaoAvisoPrevioFerias } from '@/app/modulos/gestao-pessoas/dp/components/BotaoAvisoPrevioFerias';
import { useCctCargos, cargoLabel } from '@/hooks/hr/useCctCargos';

const API_BASE = '/api/v1/people-management/hr';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}

// Campos obrigatórios para eSocial S-2200
const ESOCIAL_FIELDS = [
  'nome', 'cpf', 'data_nascimento', 'sexo', 'estado_civil', 'nome_mae',
  'rg', 'pis', 'ctps_numero', 'nacionalidade', 'naturalidade',
  'cep', 'logradouro', 'cidade', 'uf',
] as const;

function calcCompleteness(emp: Record<string, unknown>): { percent: number; missing: string[] } {
  const missing: string[] = [];
  for (const f of ESOCIAL_FIELDS) {
    if (!emp[f] || String(emp[f]).trim() === '') missing.push(f);
  }
  const percent = Math.round(((ESOCIAL_FIELDS.length - missing.length) / ESOCIAL_FIELDS.length) * 100);
  return { percent, missing };
}

const FIELD_LABELS: Record<string, string> = {
  nome: 'Nome', cpf: 'CPF', data_nascimento: 'Data de Nascimento', sexo: 'Sexo',
  estado_civil: 'Estado Civil', nome_mae: 'Nome da Mãe', nome_pai: 'Nome do Pai',
  rg: 'RG', rg_orgao: 'Órgão Emissor RG', rg_uf: 'UF RG', pis: 'PIS/PASEP',
  ctps_numero: 'CTPS Número', ctps_serie: 'CTPS Série', ctps_uf: 'CTPS UF', ctps_data_emissao: 'CTPS Data Emissão',
  nacionalidade: 'Nacionalidade', naturalidade: 'Naturalidade',
  email: 'Email', telefone: 'Telefone', celular: 'Celular',
  contato_emergencia: 'Contato Emergência', telefone_emergencia: 'Tel. Emergência',
  cep: 'CEP', logradouro: 'Logradouro', numero: 'Número', complemento: 'Complemento',
  bairro: 'Bairro', cidade: 'Cidade', uf: 'UF',
  cargo: 'Cargo', departamento: 'Departamento', salario_base: 'Salário Base',
  insalubridade_percentual: 'Insalubridade (%)', periculosidade_percentual: 'Periculosidade (%)', adicional_ronda_percentual: 'Adicional de Ronda (%)',
  tipo_contrato: 'Tipo Contrato', regime_trabalho: 'Regime', data_admissao: 'Data Admissão',
  banco: 'Banco', agencia: 'Agência', conta: 'Conta', tipo_conta: 'Tipo Conta', pix: 'Chave PIX',
  titulo_eleitor: 'Título Eleitor', certificado_reservista: 'Cert. Reservista',
  cnh_numero: 'CNH', cnh_categoria: 'Categoria CNH', cnh_validade: 'Validade CNH',
  curso_vigilante: 'Curso Vigilante', curso_vigilante_validade: 'Validade Curso',
  cnv: 'CNV', cnv_validade: 'Validade CNV',
  observacoes: 'Observações',
};

const UFS = ['AC','AL','AM','AP','BA','CE','DF','ES','GO','MA','MG','MS','MT','PA','PB','PE','PI','PR','RJ','RN','RO','RR','RS','SC','SE','SP','TO'];

const PAGE_SIZE = 15;

type Tab = 'pessoal' | 'documentos' | 'endereco' | 'profissional' | 'bancario' | 'vigilancia' | 'deducoes';

export default function FuncionariosPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [employees, setEmployees] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [filterComplete, setFilterComplete] = useState<'all' | 'incomplete' | 'complete'>('all');
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editData, setEditData] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>('pessoal');
  const [validationErrors, setValidationErrors] = useState<Record<string, string>>({});
  const [cepLoading, setCepLoading] = useState(false);
  // Gap 3: Deductions
  const [deductions, setDeductions] = useState<any[]>([]);
  const [deductionsLoading, setDeductionsLoading] = useState(false);
  const [showDeductionForm, setShowDeductionForm] = useState(false);
  const [deductionSaving, setDeductionSaving] = useState(false);
  // ID da dedução em edição (null = criando nova); deductionDeletingId trava o botão excluir
  const [deductionEditingId, setDeductionEditingId] = useState<string | null>(null);
  const [deductionDeletingId, setDeductionDeletingId] = useState<string | null>(null);
  const [deductionForm, setDeductionForm] = useState({ tipo: 'consignado', descricao: '', valor: '', percentual: '', base_calculo: 'fixo', total_parcelas: '', data_inicio: '', data_fim: '' });
  // Gap 6: Full profile
  const [profileData, setProfileData] = useState<Record<string, any> | null>(null);
  // Cargos da CCT (fonte única de cargos — SINDECOMPRESTS)
  const { cargos: cctCargos, loading: cargosLoading } = useCctCargos();

  const loadDeductions = async (empId: string) => {
    setDeductionsLoading(true);
    try {
      const res = await fetch(`${API_BASE}/employees/${empId}/deductions`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setDeductions(data.items || []);
      } else { setDeductions([]); }
    } catch { setDeductions([]); }
    finally { setDeductionsLoading(false); }
  };

  const resetDeductionForm = () => {
    setDeductionForm({ tipo: 'consignado', descricao: '', valor: '', percentual: '', base_calculo: 'fixo', total_parcelas: '', data_inicio: '', data_fim: '' });
    setDeductionEditingId(null);
    setShowDeductionForm(false);
  };

  // Abre o formulário preenchido para editar uma dedução existente
  const openEditDeduction = (d: any) => {
    setDeductionForm({
      tipo: d.tipo || 'consignado',
      descricao: d.descricao || '',
      valor: d.valor != null ? String(d.valor) : '',
      percentual: d.percentual != null ? String(d.percentual) : '',
      base_calculo: d.base_calculo || 'fixo',
      total_parcelas: d.total_parcelas != null ? String(d.total_parcelas) : '',
      data_inicio: d.data_inicio || '',
      data_fim: d.data_fim || '',
    });
    setDeductionEditingId(d.id);
    setShowDeductionForm(true);
  };

  // Cria (POST) ou edita (PATCH) conforme deductionEditingId
  const handleCreateDeduction = async () => {
    if (!editingId) return;
    if (!deductionForm.descricao || !deductionForm.data_inicio) {
      toast.error('Descrição e data de início são obrigatórios', { duration: 5000 });
      return;
    }
    setDeductionSaving(true);
    try {
      const payload: Record<string, unknown> = {
        tipo: deductionForm.tipo,
        descricao: deductionForm.descricao,
        base_calculo: deductionForm.base_calculo,
        data_inicio: deductionForm.data_inicio,
        // Enviados explicitamente (inclusive limpando) — PATCH aceita null
        valor: deductionForm.valor ? parseFloat(deductionForm.valor) : null,
        percentual: deductionForm.percentual ? parseFloat(deductionForm.percentual) : null,
        total_parcelas: deductionForm.total_parcelas ? parseInt(deductionForm.total_parcelas) : null,
        data_fim: deductionForm.data_fim || null,
      };
      const isEdit = !!deductionEditingId;
      const url = isEdit
        ? `${API_BASE}/employees/${editingId}/deductions/${deductionEditingId}`
        : `${API_BASE}/employees/${editingId}/deductions`;
      // No POST não mandamos nulls (o schema de criação não exige); no PATCH mandamos tudo
      if (!isEdit) {
        for (const k of ['valor', 'percentual', 'total_parcelas', 'data_fim']) {
          if (payload[k] == null) delete payload[k];
        }
      }
      const res = await fetch(url, {
        method: isEdit ? 'PATCH' : 'POST', headers: getAuthHeaders(), body: JSON.stringify(payload),
      });
      if (res.ok) {
        toast.success(isEdit ? 'Dedução atualizada com sucesso!' : 'Dedução criada com sucesso!', { duration: 4000 });
        resetDeductionForm();
        await loadDeductions(editingId);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(msgFromDetail(err?.detail) || (isEdit ? 'Erro ao editar dedução' : 'Erro ao criar dedução'), { duration: 5000 });
      }
    } catch { toast.error('Erro de conexão', { duration: 5000 }); }
    finally { setDeductionSaving(false); }
  };

  // Soft-delete (marca ativo=false) preservando a trilha de auditoria
  const handleDeleteDeduction = async (d: any) => {
    if (!editingId) return;
    if (!confirm(`Excluir a dedução "${d.descricao || d.tipo}"?\n\nA dedução será desativada (não some da trilha de auditoria) e deixará de descontar na folha.`)) return;
    setDeductionDeletingId(d.id);
    try {
      const res = await fetch(`${API_BASE}/employees/${editingId}/deductions/${d.id}`, {
        method: 'DELETE', headers: getAuthHeaders(),
      });
      if (res.ok) {
        toast.success('Dedução excluída (desativada).', { duration: 4000 });
        await loadDeductions(editingId);
      } else {
        const err = await res.json().catch(() => null);
        toast.error(msgFromDetail(err?.detail) || 'Erro ao excluir dedução', { duration: 5000 });
      }
    } catch { toast.error('Erro de conexão', { duration: 5000 }); }
    finally { setDeductionDeletingId(null); }
  };

  const loadProfile = async (empId: string) => {
    try {
      const res = await fetch(`${API_BASE}/employees/${empId}/profile`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        // BUG-06: API retorna {employee, benefits, current_contract, documents}
        // mas template espera campos flat — mapear aqui
        setProfileData({
          benefits_count: Array.isArray(data.benefits) ? data.benefits.length : 0,
          contract_type: data.current_contract?.type ?? null,
          contract_start_date: data.current_contract?.start_date ?? null,
          base_salary: data.current_contract?.base_salary ?? data.employee?.salario_base ?? null,
        });
      }
    } catch { /* ignore */ }
  };

  const loadEmployees = useCallback(async (retry = 0) => {
    setLoading(true);
    setLoadError(false);
    try {
      const res = await fetch(`${API_BASE}/employees?page_size=100`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setEmployees(data.items || data || []);
      } else if (res.status >= 500 && retry < 2) {
        // Bug #2: Retry on 5xx
        await new Promise(r => setTimeout(r, 2000));
        return loadEmployees(retry + 1);
      } else {
        setLoadError(true);
        toast.error(`Erro ao carregar funcionários (HTTP ${res.status})`, { duration: 5000 });
      }
    } catch {
      if (retry < 2) {
        await new Promise(r => setTimeout(r, 2000));
        return loadEmployees(retry + 1);
      }
      setLoadError(true);
      toast.error('Erro de conexão ao carregar funcionários', { duration: 5000 });
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadEmployees(); }, [loadEmployees]);

  // Abrir funcionário via query param ?funcionario=id (vindo de /funcionarios/[id])
  useEffect(() => {
    const funcionarioId = searchParams?.get('funcionario');
    if (funcionarioId && employees.length > 0 && !editingId) {
      const emp = employees.find(e => e.id === funcionarioId);
      if (emp) startEditing(emp);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, employees]);

  const enriched = useMemo(() =>
    employees.map(e => ({ ...e, ...calcCompleteness(e) })),
  [employees]);

  const filtered = useMemo(() => {
    let items = enriched;
    if (searchTerm.trim()) {
      const term = searchTerm.toLowerCase();
      items = items.filter(e => (e.nome || '').toLowerCase().includes(term) || (e.cpf || '').includes(term));
    }
    if (filterComplete === 'incomplete') items = items.filter(e => e.percent < 100);
    if (filterComplete === 'complete') items = items.filter(e => e.percent === 100);
    return items.sort((a, b) => a.percent - b.percent);
  }, [enriched, searchTerm, filterComplete]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const paginated = filtered.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);

  // Bug #3: KPIs computed from enriched (auto-updates when employees reload)
  const statsComplete = enriched.filter(e => e.percent === 100).length;
  const statsIncomplete = enriched.filter(e => e.percent < 100).length;
  const avgPercent = enriched.length ? Math.round(enriched.reduce((s, e) => s + e.percent, 0) / enriched.length) : 0;

  const startEditing = (emp: any) => {
    setEditingId(emp.id);
    const data: Record<string, string> = {};
    for (const key of Object.keys(FIELD_LABELS)) {
      data[key] = emp[key] != null ? String(emp[key]) : '';
    }
    setEditData(data);
    setValidationErrors({});
    setActiveTab('pessoal');
    setDeductions([]);
    setProfileData(null);
    // Load deductions and profile in background
    loadDeductions(emp.id);
    loadProfile(emp.id);
    // Scroll to form
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  // Bug #6: ViaCEP autocomplete
  const handleCepBlur = async () => {
    const cep = (editData.cep || '').replace(/\D/g, '');
    if (cep.length !== 8) return;
    setCepLoading(true);
    try {
      const res = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
      if (res.ok) {
        const data = await res.json();
        if (!data.erro) {
          setEditData(p => ({
            ...p,
            logradouro: data.logradouro || p.logradouro,
            bairro: data.bairro || p.bairro,
            cidade: data.localidade || p.cidade,
            uf: data.uf || p.uf,
            complemento: data.complemento || p.complemento,
          }));
          toast.success('Endereço preenchido pelo CEP', { duration: 3000 });
        }
      }
    } catch { /* ViaCEP offline — usuário preenche manual */ }
    finally { setCepLoading(false); }
  };

  // Bug #1: CPF validation + Bug #10: Inline validation messages
  const validateForm = (): boolean => {
    const errors: Record<string, string> = {};
    if (editData.cpf && !validateCPF(editData.cpf)) {
      errors.cpf = 'CPF inválido';
    }
    if (editData.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(editData.email)) {
      errors.email = 'Email inválido';
    }
    setValidationErrors(errors);
    if (Object.keys(errors).length > 0) {
      toast.error('Corrija os erros antes de salvar', { duration: 4000 });
      // Navigate to tab with error
      if (errors.cpf) setActiveTab('pessoal');
      else if (errors.email) setActiveTab('pessoal');
      return false;
    }
    return true;
  };

  const handleSave = async () => {
    if (!editingId) return;
    if (!validateForm()) return;
    setSaving(true);
    try {
      const original = employees.find(e => e.id === editingId) || {};
      const payload: Record<string, unknown> = {};
      for (const [key, val] of Object.entries(editData)) {
        const origVal = original[key] != null ? String(original[key]) : '';
        if (val !== origVal && val !== '') {
          payload[key] = val;
        }
      }
      if (Object.keys(payload).length === 0) {
        toast.info('Nenhuma alteração detectada', { duration: 3000 });
        setSaving(false);
        return;
      }
      const res = await fetch(`${API_BASE}/employees/${editingId}`, {
        method: 'PATCH', headers: getAuthHeaders(), body: JSON.stringify(payload),
      });
      if (res.ok) {
        toast.success('Dados atualizados com sucesso!', { duration: 4000 });
        setEditingId(null);
        setValidationErrors({});
        await loadEmployees(); // Bug #3: Reloads data → KPIs recalculate
      } else if (res.status >= 500) {
        toast.error('Erro no servidor. Tente novamente em instantes.', { duration: 5000 });
      } else {
        const err = await res.json().catch(() => null);
        toast.error(msgFromDetail(err?.detail) || 'Erro ao salvar', { duration: 5000 });
      }
    } catch { toast.error('Erro de conexão', { duration: 5000 }); }
    finally { setSaving(false); }
  };

  const renderField = (key: string, type: string = 'text', options?: string[]) => {
    const isRequired = ESOCIAL_FIELDS.includes(key as any);
    const isEmpty = isRequired && !editData[key];
    const hasError = !!validationErrors[key];

    return (
      <div key={key}>
        <label className="text-sm font-medium mb-1 block">
          {FIELD_LABELS[key] || key}
          {isRequired && <span className="text-red-500 ml-1">*</span>}
        </label>
        {options ? (
          <select value={editData[key] || ''} onChange={e => { setEditData(p => ({ ...p, [key]: e.target.value })); setValidationErrors(p => ({ ...p, [key]: '' })); }}
            className={`w-full px-3 py-2 border rounded-md text-sm ${hasError ? 'border-red-500 bg-red-50' : isEmpty ? 'border-yellow-400 bg-yellow-50' : ''}`}>
            <option value="">Selecione</option>
            {options.map(o => <option key={o} value={o}>{o}</option>)}
          </select>
        ) : (
          <input type={type} value={editData[key] || ''}
            {...(type === 'number' ? { step: '0.01', min: '0' } : {})}
            onChange={e => { setEditData(p => ({ ...p, [key]: e.target.value })); setValidationErrors(p => ({ ...p, [key]: '' })); }}
            onBlur={key === 'cep' ? handleCepBlur : key === 'cpf' ? () => { if (editData.cpf && !validateCPF(editData.cpf)) setValidationErrors(p => ({ ...p, cpf: 'CPF inválido' })); } : undefined}
            className={`w-full px-3 py-2 border rounded-md text-sm ${hasError ? 'border-red-500 bg-red-50' : isEmpty ? 'border-yellow-400 bg-yellow-50' : ''}`} />
        )}
        {/* Bug #10: Inline validation errors */}
        {hasError && <p className="text-red-500 text-xs mt-1">{validationErrors[key]}</p>}
        {isEmpty && !hasError && <p className="text-yellow-600 text-xs mt-1">Obrigatório para eSocial</p>}
        {key === 'cep' && cepLoading && <p className="text-blue-500 text-xs mt-1">Buscando endereço...</p>}
      </div>
    );
  };

  // Cargo vinculado à CCT (fonte única). Ao selecionar, guarda cct_cargo_id + nome do cargo.
  const renderCargoCct = () => {
    const currentName = editData.cargo || '';
    // Casa por id, ou por nome caso o registro ainda não tenha cct_cargo_id.
    const selById = cctCargos.find(c => String(c.id) === editData.cct_cargo_id);
    const selByName = cctCargos.find(c => cargoLabel(c).toLowerCase() === currentName.toLowerCase());
    const sel = selById ?? selByName;
    return (
      <div key="cargo">
        <label className="text-sm font-medium mb-1 block">Cargo (CCT SINDECOMPRESTS)</label>
        <select
          value={sel ? String(sel.id) : ''}
          disabled={cargosLoading}
          onChange={e => {
            const id = e.target.value;
            const cargo = cctCargos.find(c => String(c.id) === id);
            setEditData(p => ({ ...p, cct_cargo_id: id, cargo: cargo ? cargoLabel(cargo) : '' }));
            setValidationErrors(p => ({ ...p, cargo: '' }));
          }}
          className="w-full px-3 py-2 border rounded-md text-sm"
        >
          <option value="">
            {cargosLoading ? 'Carregando cargos...' : (currentName && !sel ? currentName : 'Selecione o cargo')}
          </option>
          {cctCargos.map(c => (
            <option key={String(c.id)} value={String(c.id)}>{cargoLabel(c)}</option>
          ))}
        </select>
        {sel?.piso_salarial != null && (
          <p className="text-xs text-gray-500 mt-1">
            Piso CCT: {sel.piso_salarial.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}
          </p>
        )}
      </div>
    );
  };

  const tabs: { key: Tab; label: string; icon: typeof User }[] = [
    { key: 'pessoal', label: 'Pessoal', icon: User },
    { key: 'documentos', label: 'Documentos', icon: FileText },
    { key: 'endereco', label: 'Endereço', icon: MapPin },
    { key: 'profissional', label: 'Profissional', icon: Building2 },
    { key: 'bancario', label: 'Bancário', icon: CreditCard },
    { key: 'vigilancia', label: 'Vigilância', icon: Shield },
    { key: 'deducoes', label: 'Deduções', icon: Minus },
  ];

  return (
    <div className="space-y-6 pb-28">
      {/* Header */}
      <PageHeader
        icon={<Users className="h-5 w-5" />}
        title="Cadastro de Funcionários"
        subtitle="Complete os dados para eSocial e obrigações trabalhistas"
        actions={(
          <Button variant="ghost" size="sm" onClick={() => router.push('/modulos/dp')}>
            <ArrowLeft className="h-4 w-4" />
          </Button>
        )}
      />

      {/* Stats — Bug #3: These auto-update because they depend on enriched which depends on employees */}
      <div className="grid gap-4 md:grid-cols-4">
        <StatCard label="Total" value={enriched.length} />
        <StatCard
          label="Cadastro Completo"
          value={<span className="text-green-600">{statsComplete}</span>}
          color="#16a34a"
          onClick={() => setFilterComplete('complete')}
        />
        <StatCard
          label="Dados Incompletos"
          value={<span className="text-yellow-600">{statsIncomplete}</span>}
          color="#ca8a04"
          onClick={() => setFilterComplete('incomplete')}
        />
        <StatCard
          label="Completude Média"
          value={<span className={avgPercent >= 80 ? 'text-green-600' : avgPercent >= 50 ? 'text-yellow-600' : 'text-red-600'}>{avgPercent}%</span>}
        />
      </div>

      {/* Bug #2: Error state with retry */}
      {loadError && !loading && (
        <Card className="border-red-200 bg-red-50">
          <CardContent className="pt-6 flex items-center justify-between">
            <p className="text-sm text-red-700">Erro ao carregar dados. O servidor pode estar temporariamente indisponível.</p>
            <Button variant="outline" size="sm" onClick={() => loadEmployees()}>
              <RefreshCw className="h-4 w-4 mr-1" /> Tentar Novamente
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Edit Form */}
      {editingId && (
        <Card>
          <CardHeader>
            <div className="flex items-center justify-between">
              {/* Bug #9: Show full name without truncation */}
              <CardTitle className="text-base truncate max-w-[70%]" title={editData.nome || 'Sem nome'}>
                Editar Funcionário — {editData.nome || 'Sem nome'}
              </CardTitle>
              <Button variant="ghost" size="sm" onClick={() => { setEditingId(null); setValidationErrors({}); }}><X className="h-4 w-4" /></Button>
            </div>
            <div className="flex gap-1 mt-2 flex-wrap">
              {tabs.map(t => (
                <Button key={t.key} variant={activeTab === t.key ? 'default' : 'outline'} size="sm"
                  onClick={() => setActiveTab(t.key)} className="text-xs">
                  <t.icon className="h-3.5 w-3.5 mr-1" /> {t.label}
                </Button>
              ))}
            </div>
          </CardHeader>
          <CardContent>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {activeTab === 'pessoal' && (<>
                {renderField('nome')}
                {renderField('cpf')}
                {renderField('data_nascimento', 'date')}
                {renderField('sexo', 'text', ['M', 'F'])}
                {renderField('estado_civil', 'text', ['solteiro', 'casado', 'divorciado', 'viuvo', 'uniao_estavel'])}
                {renderField('nacionalidade', 'text', ['Brasileira', 'Estrangeira'])}
                {renderField('naturalidade')}
                {renderField('nome_mae')}
                {renderField('nome_pai')}
                {renderField('email')}
                {renderField('telefone')}
                {renderField('celular')}
                {renderField('contato_emergencia')}
                {renderField('telefone_emergencia')}
              </>)}
              {activeTab === 'documentos' && (<>
                {renderField('rg')}
                {renderField('rg_orgao')}
                {renderField('rg_uf', 'text', UFS)}
                {renderField('pis')}
                {renderField('ctps_numero')}
                {renderField('ctps_serie')}
                {renderField('ctps_uf', 'text', UFS)}
                {renderField('ctps_data_emissao', 'date')}
                {renderField('titulo_eleitor')}
                {renderField('certificado_reservista')}
                {renderField('cnh_numero')}
                {renderField('cnh_categoria', 'text', ['A', 'B', 'AB', 'C', 'D', 'E'])}
                {renderField('cnh_validade', 'date')}
              </>)}
              {activeTab === 'endereco' && (<>
                {renderField('cep')}
                {renderField('logradouro')}
                {renderField('numero')}
                {renderField('complemento')}
                {renderField('bairro')}
                {renderField('cidade')}
                {renderField('uf', 'text', UFS)}
              </>)}
              {activeTab === 'profissional' && (<>
                {renderCargoCct()}
                {renderField('departamento', 'text', ['Operações', 'Administrativo', 'Comercial', 'Financeiro'])}
                {renderField('salario_base', 'number')}
                {renderField('insalubridade_percentual', 'number')}
                {renderField('periculosidade_percentual', 'number')}
                {renderField('adicional_ronda_percentual', 'number')}
                {renderField('tipo_contrato', 'text', ['CLT', 'Temporário', 'Experiência'])}
                {renderField('regime_trabalho', 'text', ['CLT', 'Estatutário', 'Temporário'])}
                {renderField('data_admissao', 'date')}
                {renderField('observacoes')}
              </>)}
              {activeTab === 'bancario' && (<>
                {renderField('banco')}
                {renderField('agencia')}
                {renderField('conta')}
                {renderField('tipo_conta', 'text', ['Corrente', 'Poupança', 'Salário'])}
                {renderField('pix')}
              </>)}
              {activeTab === 'vigilancia' && (<>
                {renderField('curso_vigilante')}
                {renderField('curso_vigilante_validade', 'date')}
                {renderField('cnv')}
                {renderField('cnv_validade', 'date')}
              </>)}
              {activeTab === 'deducoes' && (
                <div className="col-span-full space-y-4">
                  <div className="flex items-center justify-between">
                    <p className="text-sm font-medium">Deduções do funcionário (consignados, pensões, empréstimos)</p>
                    <Button size="sm" variant="outline" onClick={() => { setDeductionEditingId(null); setDeductionForm({ tipo: 'consignado', descricao: '', valor: '', percentual: '', base_calculo: 'fixo', total_parcelas: '', data_inicio: '', data_fim: '' }); setShowDeductionForm(true); }}>
                      <Plus className="h-4 w-4 mr-1" /> Nova Dedução
                    </Button>
                  </div>
                  {showDeductionForm && (
                    <div className="border rounded-md p-4 bg-muted/30 space-y-3">
                      <p className="text-sm font-semibold">{deductionEditingId ? 'Editar Dedução' : 'Nova Dedução'}</p>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                        <div>
                          <label className="text-sm font-medium mb-1 block">Tipo *</label>
                          <select value={deductionForm.tipo} onChange={e => setDeductionForm(p => ({ ...p, tipo: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm">
                            <option value="consignado">Consignado</option>
                            <option value="pensao_alimenticia">Pensão Alimentícia</option>
                            <option value="emprestimo">Emprestimo</option>
                            <option value="outros">Outros</option>
                          </select>
                        </div>
                        <div>
                          <label className="text-sm font-medium mb-1 block">Descrição *</label>
                          <input type="text" value={deductionForm.descricao} onChange={e => setDeductionForm(p => ({ ...p, descricao: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Ex: Emprestimo BMG" />
                        </div>
                        <div>
                          <label className="text-sm font-medium mb-1 block">Base Cálculo</label>
                          <select value={deductionForm.base_calculo} onChange={e => setDeductionForm(p => ({ ...p, base_calculo: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm">
                            <option value="fixo">Valor Fixo</option>
                            <option value="bruto">% Salário Bruto</option>
                            <option value="liquido">% Salário Líquido</option>
                          </select>
                        </div>
                        <div>
                          <label className="text-sm font-medium mb-1 block">Valor (R$)</label>
                          <input type="number" step="0.01" value={deductionForm.valor} onChange={e => setDeductionForm(p => ({ ...p, valor: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="0.00" />
                        </div>
                        <div>
                          <label className="text-sm font-medium mb-1 block">Percentual (%)</label>
                          <input type="number" step="0.01" max="100" value={deductionForm.percentual} onChange={e => setDeductionForm(p => ({ ...p, percentual: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="0.00" />
                        </div>
                        <div>
                          <label className="text-sm font-medium mb-1 block">Total Parcelas</label>
                          <input type="number" min="1" value={deductionForm.total_parcelas} onChange={e => setDeductionForm(p => ({ ...p, total_parcelas: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" placeholder="Ex: 36" />
                        </div>
                        <div>
                          <label className="text-sm font-medium mb-1 block">Data Início *</label>
                          <input type="date" value={deductionForm.data_inicio} onChange={e => setDeductionForm(p => ({ ...p, data_inicio: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
                        </div>
                        <div>
                          <label className="text-sm font-medium mb-1 block">Data Fim</label>
                          <input type="date" value={deductionForm.data_fim} onChange={e => setDeductionForm(p => ({ ...p, data_fim: e.target.value }))} className="w-full px-3 py-2 border rounded-md text-sm" />
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button size="sm" disabled={deductionSaving} onClick={handleCreateDeduction}>
                          {deductionSaving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                          {deductionSaving ? 'Salvando...' : (deductionEditingId ? 'Salvar Alterações' : 'Criar Dedução')}
                        </Button>
                        <Button variant="outline" size="sm" onClick={resetDeductionForm}>Cancelar</Button>
                      </div>
                    </div>
                  )}
                  {deductionsLoading ? (
                    <div className="flex items-center justify-center py-6"><Loader2 className="h-6 w-6 animate-spin text-muted-foreground" /></div>
                  ) : deductions.length === 0 ? (
                    <p className="text-sm text-muted-foreground py-4 text-center">Nenhuma dedução cadastrada para este funcionário.</p>
                  ) : (
                    <div className="border rounded-md overflow-hidden">
                      <table className="w-full text-sm">
                        <thead className="bg-muted/50">
                          <tr>
                            <th className="text-left px-3 py-2 font-medium">Tipo</th>
                            <th className="text-left px-3 py-2 font-medium">Descrição</th>
                            <th className="text-right px-3 py-2 font-medium">Valor</th>
                            <th className="text-right px-3 py-2 font-medium">Percentual</th>
                            <th className="text-center px-3 py-2 font-medium">Parcelas</th>
                            <th className="text-left px-3 py-2 font-medium">Periodo</th>
                            <th className="text-center px-3 py-2 font-medium">Ativo</th>
                            <th className="text-right px-3 py-2 font-medium">Ações</th>
                          </tr>
                        </thead>
                        <tbody>
                          {deductions.map((d: any, i: number) => (
                            <tr key={d.id || i} className="border-t">
                              <td className="px-3 py-2 capitalize">{String(d.tipo || '-').replace(/_/g, ' ')}</td>
                              <td className="px-3 py-2">{d.descricao || '-'}</td>
                              <td className="px-3 py-2 text-right">{d.valor != null ? `R$ ${Number(d.valor).toFixed(2)}` : '-'}</td>
                              <td className="px-3 py-2 text-right">{d.percentual != null ? `${d.percentual}%` : '-'}</td>
                              <td className="px-3 py-2 text-center">{d.parcela_atual && d.total_parcelas ? `${d.parcela_atual}/${d.total_parcelas}` : d.total_parcelas || '-'}</td>
                              <td className="px-3 py-2">{d.data_inicio || '-'} {d.data_fim ? `a ${d.data_fim}` : ''}</td>
                              <td className="px-3 py-2 text-center">{d.ativo ? <CheckCircle2 className="h-4 w-4 text-green-600 inline" /> : <XCircle className="h-4 w-4 text-red-500 inline" />}</td>
                              <td className="px-3 py-2 text-right whitespace-nowrap">
                                <Button variant="ghost" size="sm" className="h-7 w-7 p-0" title="Editar dedução" onClick={() => openEditDeduction(d)}>
                                  <Pencil className="h-4 w-4" />
                                </Button>
                                <Button variant="ghost" size="sm" className="h-7 w-7 p-0 text-red-500 hover:text-red-600" title="Excluir dedução" disabled={deductionDeletingId === d.id} onClick={() => handleDeleteDeduction(d)}>
                                  {deductionDeletingId === d.id ? <Loader2 className="h-4 w-4 animate-spin" /> : <Trash2 className="h-4 w-4" />}
                                </Button>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                  {/* Gap 6: Profile summary */}
                  {profileData && (
                    <div className="border rounded-md p-3 bg-blue-50/50 space-y-2">
                      <p className="text-sm font-medium text-blue-800">Resumo do Perfil Completo</p>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-sm">
                        {profileData.benefits_count != null && <div><span className="text-muted-foreground">Benefícios ativos:</span><br /><span className="font-bold">{profileData.benefits_count}</span></div>}
                        {profileData.contract_type && <div><span className="text-muted-foreground">Tipo contrato:</span><br /><span className="font-bold">{profileData.contract_type}</span></div>}
                        {profileData.contract_start_date && <div><span className="text-muted-foreground">Inicio contrato:</span><br /><span className="font-bold">{profileData.contract_start_date}</span></div>}
                        {profileData.base_salary != null && <div><span className="text-muted-foreground">Salário base:</span><br /><span className="font-bold">R$ {Number(profileData.base_salary).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span></div>}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
            <div className="flex gap-2 mt-4 flex-wrap">
              <Button size="sm" disabled={saving} onClick={handleSave}>
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Save className="h-4 w-4 mr-1" />}
                {saving ? 'Salvando...' : 'Salvar Alterações'}
              </Button>
              <Button variant="outline" size="sm" onClick={() => { setEditingId(null); setValidationErrors({}); }}>Cancelar</Button>
              {editingId && <BotaoGerarContrato employeeId={editingId} />}
              {editingId && <BotaoAvisoPrevioFerias employeeId={editingId} />}
            </div>
          </CardContent>
        </Card>
      )}

      {/* List */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Funcionários</CardTitle>
            <div className="flex gap-2 items-center">
              <div className="flex gap-1">
                <Badge className={`cursor-pointer ${filterComplete === 'all' ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-muted text-muted-foreground'}`} onClick={() => { setFilterComplete('all'); setCurrentPage(1); }}>Todos</Badge>
                <Badge className={`cursor-pointer ${filterComplete === 'incomplete' ? 'bg-yellow-500 text-white hover:bg-yellow-600' : 'bg-muted text-muted-foreground'}`} onClick={() => { setFilterComplete('incomplete'); setCurrentPage(1); }}>Incompletos</Badge>
                <Badge className={`cursor-pointer ${filterComplete === 'complete' ? 'bg-green-500 text-white hover:bg-green-600' : 'bg-muted text-muted-foreground'}`} onClick={() => { setFilterComplete('complete'); setCurrentPage(1); }}>Completos</Badge>
              </div>
              <div className="relative w-56">
                <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
                <input type="text" value={searchTerm} onChange={e => { setSearchTerm(e.target.value); setCurrentPage(1); }}
                  placeholder="Buscar nome ou CPF..." className="w-full pl-9 pr-3 py-2 border rounded-md text-sm" />
              </div>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          {loading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></div>
          ) : filtered.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Users className="h-12 w-12 mb-3" />
              <p className="font-medium">Nenhum funcionário encontrado</p>
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Nome</TableHead>
                    <TableHead>CPF</TableHead>
                    <TableHead>Cargo</TableHead>
                    <TableHead>Completude eSocial</TableHead>
                    <TableHead>Campos Faltantes</TableHead>
                    <TableHead>Ações</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {paginated.map((emp) => (
                    <TableRow key={emp.id} className={emp.percent < 100 ? 'bg-yellow-50/50' : ''}>
                      <TableCell className="font-medium max-w-[200px]" title={emp.nome}>{emp.nome || '-'}</TableCell>
                      <TableCell className="text-sm">{emp.cpf || '-'}</TableCell>
                      <TableCell className="text-sm">{emp.cargo || '-'}</TableCell>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          {emp.percent === 100 ? (
                            <CheckCircle2 className="h-4 w-4 text-green-600 shrink-0" />
                          ) : (
                            <AlertTriangle className="h-4 w-4 text-yellow-500 shrink-0" />
                          )}
                          <div className="w-20 bg-muted rounded-full h-2">
                            <div className={`h-2 rounded-full ${emp.percent === 100 ? 'bg-green-500' : emp.percent >= 60 ? 'bg-yellow-500' : 'bg-red-500'}`}
                              style={{ width: `${emp.percent}%` }} />
                          </div>
                          <span className="text-xs text-muted-foreground">{emp.percent}%</span>
                        </div>
                      </TableCell>
                      <TableCell>
                        {emp.missing.length > 0 ? (
                          <span className="text-xs text-yellow-700">
                            {emp.missing.slice(0, 3).map((f: string) => FIELD_LABELS[f] || f).join(', ')}
                            {emp.missing.length > 3 && ` +${emp.missing.length - 3}`}
                          </span>
                        ) : (
                          <span className="text-xs text-green-600">Completo</span>
                        )}
                      </TableCell>
                      <TableCell>
                        <Button variant="outline" size="sm" onClick={() => startEditing(emp)}>
                          <Edit className="h-3.5 w-3.5 mr-1" /> Editar
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <div className="flex items-center justify-between mt-4 text-sm">
                <span className="text-muted-foreground">{filtered.length} funcionário{filtered.length !== 1 ? 's' : ''} — Página {currentPage}/{totalPages}</span>
                <div className="flex gap-1">
                  <Button variant="outline" size="sm" disabled={currentPage <= 1} onClick={() => setCurrentPage(p => p - 1)}><ChevronLeft className="h-4 w-4" /></Button>
                  <Button variant="outline" size="sm" disabled={currentPage >= totalPages} onClick={() => setCurrentPage(p => p + 1)}><ChevronRight className="h-4 w-4" /></Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
