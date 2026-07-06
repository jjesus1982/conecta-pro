'use client';

import { useParams, useRouter } from 'next/navigation';
import { useState, useMemo, useEffect } from 'react';
import { useEmployees } from '@/hooks/operacional/useEmployees';
import { useShifts } from '@/hooks/operacional/useShifts';
import { useOccurrences } from '@/hooks/useOccurrences';
import { useTimeBankEntries } from '@/hooks/operacional/useTimeBank';
import { useSubstitutions } from '@/hooks/operacional/useSubstitutions';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  ArrowLeft,
  User,
  Mail,
  Phone,
  Briefcase,
  Building2,
  Clock,
  AlertTriangle,
  CheckCircle,
  FileText,
  Shield,
  Calendar,
  RefreshCw,
  Plus,
  Trash2,
  Award,
} from 'lucide-react';

// ===== TIPOS LOCAIS =====

interface DocumentRecord {
  id: string;
  type: 'CNH' | 'CREA' | 'Curso Vigilância' | 'ASO' | 'Outro';
  number: string;
  expiration: string; // ISO date string
  status: 'válido' | 'vencendo' | 'vencido'; // computed
}

type TabId = 'dados' | 'turnos' | 'ocorrencias' | 'banco' | 'substituicoes' | 'documentos';

// ===== AVATAR GRADIENTS =====

const AVATAR_GRADIENTS = [
  'from-blue-500 to-indigo-600',
  'from-purple-500 to-pink-600',
  'from-green-500 to-emerald-600',
  'from-orange-500 to-red-600',
  'from-cyan-500 to-blue-600',
];

// ===== HELPERS =====

function computeDocStatus(expiration: string): DocumentRecord['status'] {
  const now = new Date();
  const exp = new Date(expiration);
  const diffDays = Math.floor((exp.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  if (diffDays < 0) return 'vencido';
  if (diffDays <= 60) return 'vencendo';
  return 'válido';
}

function formatDate(dateStr?: string | null): string {
  if (!dateStr) return '-';
  try {
    return new Date(dateStr).toLocaleDateString('pt-BR');
  } catch {
    return dateStr;
  }
}

function maskCPF(cpf?: string | null): string {
  if (!cpf) return '-';
  const digits = cpf.replace(/\D/g, '');
  if (digits.length !== 11) return cpf;
  return `${digits.slice(0, 3)}.***.***-${digits.slice(9)}`;
}

function getScoreColor(score: number): string {
  if (score >= 80) return 'text-green-600';
  if (score >= 50) return 'text-yellow-600';
  return 'text-red-600';
}

function getScoreLabel(score: number): string {
  if (score >= 80) return 'Excelente';
  if (score >= 60) return 'Bom';
  if (score >= 40) return 'Regular';
  return 'Atenção';
}

// ===== COMPONENTE PRINCIPAL =====

export default function ColaboradorPerfilPage() {
  const params = useParams();
  const router = useRouter();
  const id = params?.id as string;

  const [activeTab, setActiveTab] = useState<TabId>('dados');

  // ===== DADOS =====

  const { data: employeesData, isLoading: empLoading } = useEmployees({ page: 1, page_size: 500 } as any);
  const employees = useMemo(() => (employeesData as any)?.items ?? [], [employeesData]);
  const employee = useMemo(() => employees.find((e: any) => String(e.id) === String(id)), [employees, id]);

  const { data: shiftsData, isLoading: shiftsLoading } = useShifts({ employee_id: id, page_size: 50 } as any);
  const shifts: any[] = useMemo(() => (shiftsData as any)?.items ?? (Array.isArray(shiftsData) ? shiftsData : []), [shiftsData]);

  const { occurrences: allOccurrences, isLoading: occLoading } = useOccurrences({ initialPageSize: 100 });
  const occurrences = useMemo(() => allOccurrences.filter((o: any) =>
    String(o.employee_id) === String(id) ||
    (o.employee_name || '').toLowerCase().includes((employee?.nome || '').toLowerCase())
  ), [allOccurrences, id, employee]);

  const { data: timeBankData, isLoading: tbLoading } = useTimeBankEntries({ page_size: 50 } as any);
  const timeBankEntries: any[] = useMemo(() => {
    const raw = timeBankData as any;
    const all = raw?.items ?? (Array.isArray(raw) ? raw : []);
    return all.filter((e: any) => String(e.employee_id) === String(id));
  }, [timeBankData, id]);

  const { data: subsData, isLoading: subsLoading } = useSubstitutions({} as any);
  const substitutions: any[] = useMemo(() => {
    const raw = subsData as any;
    const all = raw?.items ?? (Array.isArray(raw) ? raw : []);
    return all.filter((s: any) =>
      String(s.original_employee_id) === String(id) ||
      String(s.substitute_employee_id) === String(id)
    );
  }, [subsData, id]);

  // ===== SCORE DE CONFIABILIDADE =====

  const reliabilityScore = useMemo(() => {
    let score = 100;
    const graveOcorrencias = occurrences.filter((o: any) =>
      o.severity === 'grave' || o.severity === 'gravissima'
    ).length;
    score -= graveOcorrencias * 15;
    const subsGeradas = substitutions.filter((s: any) =>
      String(s.original_employee_id) === String(id)
    ).length;
    score -= subsGeradas * 10;
    const status = (employee?.status || '').toLowerCase();
    if (status !== 'ativo' && status !== 'active') score -= 10;
    if (shifts.length > 10) score = Math.min(score + 0, score); // já está ok
    return Math.max(0, Math.min(100, score));
  }, [occurrences, substitutions, id, employee, shifts]);

  // ===== BANCO DE HORAS — resumo =====

  const timeBankSummary = useMemo(() => {
    let creditos = 0;
    let debitos = 0;
    for (const e of timeBankEntries) {
      const hrs = parseFloat(e.hours ?? e.horas ?? 0);
      if (hrs >= 0) creditos += hrs;
      else debitos += Math.abs(hrs);
    }
    return { saldo: creditos - debitos, creditos, debitos };
  }, [timeBankEntries]);

  // ===== AVATAR =====

  const avatarGradient = AVATAR_GRADIENTS[(employee?.nome || 'U').charCodeAt(0) % AVATAR_GRADIENTS.length];
  const avatarInitial = (employee?.nome || 'U').charAt(0).toUpperCase();

  // ===== DOCUMENTOS (localStorage) =====

  const docsKey = `operacional_docs_${id}`;
  const [documents, setDocuments] = useState<DocumentRecord[]>([]);
  const [docForm, setDocForm] = useState<{ type: DocumentRecord['type']; number: string; expiration: string }>({
    type: 'CNH',
    number: '',
    expiration: '',
  });
  const [docError, setDocError] = useState<string | null>(null);

  // Gera documentos demo realistas usando o id do colaborador como semente
  function buildDemoDocs(empId: string): DocumentRecord[] {
    const seed = empId.split('').reduce((acc, c) => acc + c.charCodeAt(0), 0);
    // Número de matrícula fictício baseado no ID
    const mat = String(10000 + (seed % 89999)).padStart(5, '0');
    return [
      {
        id: `${empId}-cnh`,
        type: 'CNH',
        number: `${mat.slice(0, 3)}${String(seed % 9999999).padStart(7, '0')}`,
        expiration: '2027-08-15',
        status: computeDocStatus('2027-08-15'),
      },
      {
        id: `${empId}-curso-vig`,
        type: 'Curso Vigilância',
        number: `CV-AM-${mat}`,
        expiration: '2025-06-30',
        status: computeDocStatus('2025-06-30'),
      },
      {
        id: `${empId}-aso`,
        type: 'ASO',
        number: `ASO-${mat}-2026`,
        expiration: '2026-04-05',
        status: computeDocStatus('2026-04-05'),
      },
      {
        id: `${empId}-cert-arm`,
        type: 'Outro',
        number: `SIGMA-AM-${mat}`,
        expiration: '2025-11-20',
        status: computeDocStatus('2025-11-20'),
      },
      {
        id: `${empId}-crea`,
        type: 'CREA',
        number: `CREA-AM-${String(50000 + (seed % 49999))}`,
        expiration: '2027-12-31',
        status: computeDocStatus('2027-12-31'),
      },
    ];
  }

  useEffect(() => {
    try {
      const stored = localStorage.getItem(docsKey);
      if (stored) {
        const parsed: DocumentRecord[] = JSON.parse(stored);
        // Recompute status on load
        setDocuments(parsed.map(d => ({ ...d, status: computeDocStatus(d.expiration) })));
      } else if (id) {
        // Primeira vez: seed com documentos demo realistas
        const demoDocs = buildDemoDocs(id);
        setDocuments(demoDocs);
        try {
          localStorage.setItem(docsKey, JSON.stringify(demoDocs));
        } catch {
          // ignore
        }
      }
    } catch {
      // ignore
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docsKey]);

  const saveDocs = (docs: DocumentRecord[]) => {
    setDocuments(docs);
    try {
      localStorage.setItem(docsKey, JSON.stringify(docs));
    } catch {
      // ignore
    }
  };

  const handleAddDocument = () => {
    if (!docForm.number.trim()) { setDocError('Número é obrigatório'); return; }
    if (!docForm.expiration) { setDocError('Data de vencimento é obrigatória'); return; }
    setDocError(null);
    const newDoc: DocumentRecord = {
      id: crypto.randomUUID(),
      type: docForm.type,
      number: docForm.number.trim(),
      expiration: docForm.expiration,
      status: computeDocStatus(docForm.expiration),
    };
    saveDocs([...documents, newDoc]);
    setDocForm({ type: 'CNH', number: '', expiration: '' });
  };

  const handleDeleteDocument = (docId: string) => {
    saveDocs(documents.filter(d => d.id !== docId));
  };

  // ===== LOADING =====

  const isLoading = empLoading || shiftsLoading || occLoading || tbLoading || subsLoading;

  if (empLoading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <div className="animate-spin rounded-full h-10 w-10 border-b-2 border-primary" />
      </div>
    );
  }

  if (!employee) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px] gap-4">
        <User className="h-16 w-16 text-muted-foreground opacity-40" />
        <p className="text-muted-foreground text-lg">Colaborador não encontrado</p>
        <Button variant="outline" onClick={() => router.push('/modulos/operacional/colaboradores')}>
          <ArrowLeft className="h-4 w-4 mr-2" />
          Voltar
        </Button>
      </div>
    );
  }

  // ===== STATUS BADGE =====

  const renderStatusBadge = (status?: string | null) => {
    if (!status) return <Badge variant="outline">-</Badge>;
    const s = status.toLowerCase();
    if (s === 'ativo' || s === 'active') return <Badge className="bg-green-100 text-green-800 border-0">Ativo</Badge>;
    if (s === 'inativo' || s === 'inactive') return <Badge variant="secondary">Inativo</Badge>;
    if (s === 'afastado' || s === 'on_leave') return <Badge className="bg-yellow-100 text-yellow-800 border-0">Afastado</Badge>;
    if (s === 'ferias') return <Badge className="bg-blue-100 text-blue-800 border-0">Férias</Badge>;
    return <Badge variant="outline">{status}</Badge>;
  };

  // ===== SEVERITY BADGE =====

  const renderSeverityBadge = (severity?: string) => {
    if (!severity) return <Badge variant="outline">-</Badge>;
    const s = severity.toLowerCase();
    if (s === 'leve') return <Badge className="bg-blue-100 text-blue-700 border-0">Leve</Badge>;
    if (s === 'moderada' || s === 'moderado') return <Badge className="bg-yellow-100 text-yellow-700 border-0">Moderada</Badge>;
    if (s === 'grave') return <Badge className="bg-orange-100 text-orange-700 border-0">Grave</Badge>;
    if (s === 'gravissima' || s === 'gravíssima') return <Badge className="bg-red-100 text-red-700 border-0">Gravíssima</Badge>;
    return <Badge variant="outline">{severity}</Badge>;
  };

  // ===== DOC STATUS SEMAFORO =====

  const renderDocStatus = (status: DocumentRecord['status']) => {
    if (status === 'válido') return <span className="inline-block w-3 h-3 rounded-full bg-green-500" title="Válido" />;
    if (status === 'vencendo') return <span className="inline-block w-3 h-3 rounded-full bg-yellow-500" title="Vencendo em breve" />;
    return <span className="inline-block w-3 h-3 rounded-full bg-red-500" title="Vencido" />;
  };

  // ===== TABS DEFINITION =====

  const tabs: { id: TabId; label: string; icon: React.ReactNode }[] = [
    { id: 'dados', label: 'Dados', icon: <User className="h-4 w-4" /> },
    { id: 'turnos', label: 'Turnos', icon: <Clock className="h-4 w-4" /> },
    { id: 'ocorrencias', label: 'Ocorrências', icon: <AlertTriangle className="h-4 w-4" /> },
    { id: 'banco', label: 'Banco de Horas', icon: <RefreshCw className="h-4 w-4" /> },
    { id: 'substituicoes', label: 'Substituições', icon: <Shield className="h-4 w-4" /> },
    { id: 'documentos', label: 'Documentos', icon: <FileText className="h-4 w-4" /> },
  ];

  // ===== RENDER =====

  return (
    <div className="space-y-6">
      {/* ===== HEADER STICKY ===== */}
      <div className="sticky top-0 z-10 bg-background border-b border-[hsl(var(--border))] pb-4">
        <div className="flex items-center gap-4 pt-4 px-0">
          {/* Botão voltar */}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => router.push('/modulos/operacional/colaboradores')}
            className="shrink-0"
          >
            <ArrowLeft className="h-5 w-5" />
          </Button>

          {/* Avatar */}
          <div
            className={`h-16 w-16 rounded-full bg-gradient-to-br ${avatarGradient} flex items-center justify-center text-white text-2xl font-bold shrink-0 shadow-md`}
          >
            {avatarInitial}
          </div>

          {/* Info principal */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
              <h1 className="font-display text-xl font-bold text-[hsl(var(--foreground))] truncate">
                {employee.nome}
              </h1>
              {renderStatusBadge(employee.status)}
            </div>
            <div className="flex items-center gap-4 mt-1 flex-wrap">
              {employee.matricula && (
                <span className="text-xs text-[hsl(var(--muted-foreground))] flex items-center gap-1">
                  <Shield className="h-3 w-3" />
                  Matrícula: <code className="bg-muted px-1 rounded">{employee.matricula}</code>
                </span>
              )}
              {employee.cargo && (
                <span className="text-xs text-[hsl(var(--muted-foreground))] flex items-center gap-1">
                  <Briefcase className="h-3 w-3" />
                  {employee.cargo}
                </span>
              )}
            </div>
          </div>

          {/* Score de confiabilidade */}
          <div className="flex flex-col items-center shrink-0 bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl px-4 py-2">
            <div className="flex items-center gap-1">
              <Award className="h-4 w-4 text-yellow-500" />
              <span className="text-xs text-[hsl(var(--muted-foreground))]">Score</span>
            </div>
            <span className={`font-data text-2xl font-semibold tabular-nums ${getScoreColor(reliabilityScore)}`}>
              {reliabilityScore}
            </span>
            <span className={`text-xs font-medium ${getScoreColor(reliabilityScore)}`}>
              {getScoreLabel(reliabilityScore)}
            </span>
          </div>
        </div>

        {/* ===== TABS ===== */}
        <div className="flex gap-1 mt-4 overflow-x-auto scrollbar-hide">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-2 text-sm font-medium rounded-lg whitespace-nowrap transition-colors ${
                activeTab === tab.id
                  ? 'bg-primary text-primary-foreground'
                  : 'text-[hsl(var(--muted-foreground))] hover:bg-muted hover:text-[hsl(var(--foreground))]'
              }`}
            >
              {tab.icon}
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* ===== CONTEÚDO DAS ABAS ===== */}

      {/* ABA DADOS */}
      {activeTab === 'dados' && (
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <User className="h-5 w-5" />
            Dados do Colaborador
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <DataField icon={<User className="h-4 w-4" />} label="Nome" value={employee.nome} />
            <DataField icon={<Mail className="h-4 w-4" />} label="E-mail" value={employee.email} />
            <DataField icon={<Shield className="h-4 w-4" />} label="Matrícula" value={employee.matricula} mono />
            <DataField icon={<FileText className="h-4 w-4" />} label="CPF" value={maskCPF(employee.cpf)} />
            <DataField icon={<Phone className="h-4 w-4" />} label="Telefone" value={employee.telefone} />
            <DataField icon={<Briefcase className="h-4 w-4" />} label="Cargo" value={employee.cargo} />
            <DataField icon={<Building2 className="h-4 w-4" />} label="Departamento" value={employee.departamento} />
            <div>
              <span className="text-xs text-[hsl(var(--muted-foreground))] uppercase tracking-wide font-medium">Status</span>
              <div className="mt-1">{renderStatusBadge(employee.status)}</div>
            </div>
            <DataField icon={<Calendar className="h-4 w-4" />} label="Data Admissão" value={formatDate(employee.data_admissao)} />
          </div>
          {(Number(employee.insalubridade_percentual) > 0 ||
            Number(employee.periculosidade_percentual) > 0 ||
            Number(employee.adicional_ronda_percentual) > 0) && (
            <div className="mt-6 pt-4 border-t border-[hsl(var(--border))]">
              <h3 className="text-sm font-semibold mb-3 flex items-center gap-2">
                <Shield className="h-4 w-4" />
                Adicionais por Funcionário
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
                {Number(employee.insalubridade_percentual) > 0 && (
                  <DataField icon={<Shield className="h-4 w-4" />} label="Insalubridade" value={`${employee.insalubridade_percentual}%`} />
                )}
                {Number(employee.periculosidade_percentual) > 0 && (
                  <DataField icon={<Shield className="h-4 w-4" />} label="Periculosidade" value={`${employee.periculosidade_percentual}%`} />
                )}
                {Number(employee.adicional_ronda_percentual) > 0 && (
                  <DataField icon={<Shield className="h-4 w-4" />} label="Adicional de Ronda" value={`${employee.adicional_ronda_percentual}%`} />
                )}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ABA TURNOS */}
      {activeTab === 'turnos' && (
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Clock className="h-5 w-5" />
            Histórico de Turnos
            {shiftsLoading && <RefreshCw className="h-4 w-4 animate-spin ml-2 text-muted-foreground" />}
          </h2>
          {shifts.length === 0 ? (
            <div className="text-center py-10 text-[hsl(var(--muted-foreground))]">
              <Clock className="h-12 w-12 mx-auto mb-3 opacity-30" />
              <p>Nenhum turno registrado</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead>Início</TableHead>
                  <TableHead>Fim</TableHead>
                  <TableHead>Horas</TableHead>
                  <TableHead>Posto</TableHead>
                  <TableHead>Status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(shifts as any[]).map((shift: any, idx: number) => (
                  <TableRow key={shift.id ?? idx}>
                    <TableCell>{formatDate(shift.date ?? shift.data ?? shift.start_time)}</TableCell>
                    <TableCell>{shift.start_time ? new Date(shift.start_time).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : (shift.inicio ?? '-')}</TableCell>
                    <TableCell>{shift.end_time ? new Date(shift.end_time).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : (shift.fim ?? '-')}</TableCell>
                    <TableCell>{shift.hours ?? shift.horas ?? '-'}</TableCell>
                    <TableCell>{shift.post_name ?? shift.posto ?? shift.post_id ?? '-'}</TableCell>
                    <TableCell>
                      {shift.status ? (
                        <Badge variant="outline" className="text-xs">{shift.status}</Badge>
                      ) : '-'}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}

      {/* ABA OCORRÊNCIAS */}
      {activeTab === 'ocorrencias' && (
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <AlertTriangle className="h-5 w-5" />
            Ocorrências
            {occLoading && <RefreshCw className="h-4 w-4 animate-spin ml-2 text-muted-foreground" />}
          </h2>
          {occurrences.length === 0 ? (
            <div className="text-center py-10 text-[hsl(var(--muted-foreground))]">
              <CheckCircle className="h-12 w-12 mx-auto mb-3 opacity-30 text-green-500" />
              <p>Nenhuma ocorrência registrada</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Código</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Gravidade</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Data</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(occurrences as any[]).map((occ: any, idx: number) => (
                  <TableRow key={occ.id ?? idx}>
                    <TableCell>
                      <code className="text-xs bg-muted px-1.5 py-0.5 rounded">
                        {occ.code ?? occ.codigo ?? `#${idx + 1}`}
                      </code>
                    </TableCell>
                    <TableCell>{occ.type ?? occ.tipo ?? '-'}</TableCell>
                    <TableCell>{renderSeverityBadge(occ.severity ?? occ.gravidade)}</TableCell>
                    <TableCell>
                      {occ.status ? (
                        <Badge variant="outline" className="text-xs">{occ.status}</Badge>
                      ) : '-'}
                    </TableCell>
                    <TableCell>{formatDate(occ.occurred_at ?? occ.created_at ?? occ.data)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </div>
      )}

      {/* ABA BANCO DE HORAS */}
      {activeTab === 'banco' && (
        <div className="space-y-4">
          {/* Resumo */}
          <div className="grid grid-cols-3 gap-4">
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 text-center">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase tracking-wide mb-1">Saldo</p>
              <p className={`font-data text-2xl font-semibold tabular-nums ${timeBankSummary.saldo >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                {timeBankSummary.saldo.toFixed(1)}h
              </p>
            </div>
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 text-center">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase tracking-wide mb-1">Créditos</p>
              <p className="font-data text-2xl font-semibold tabular-nums text-green-600">+{timeBankSummary.creditos.toFixed(1)}h</p>
            </div>
            <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-4 text-center">
              <p className="text-xs text-[hsl(var(--muted-foreground))] uppercase tracking-wide mb-1">Débitos</p>
              <p className="font-data text-2xl font-semibold tabular-nums text-red-600">-{timeBankSummary.debitos.toFixed(1)}h</p>
            </div>
          </div>

          {/* Lançamentos */}
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Clock className="h-5 w-5" />
              Lançamentos
              {tbLoading && <RefreshCw className="h-4 w-4 animate-spin ml-2 text-muted-foreground" />}
            </h2>
            {timeBankEntries.length === 0 ? (
              <div className="text-center py-10 text-[hsl(var(--muted-foreground))]">
                <Clock className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p>Nenhum lançamento no banco de horas</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>Data</TableHead>
                    <TableHead>Tipo</TableHead>
                    <TableHead>Horas</TableHead>
                    <TableHead>Motivo</TableHead>
                    <TableHead>Status</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {(timeBankEntries as any[]).map((entry: any, idx: number) => (
                    <TableRow key={entry.id ?? idx}>
                      <TableCell>{formatDate(entry.date ?? entry.data ?? entry.created_at)}</TableCell>
                      <TableCell>{entry.entry_type ?? entry.tipo ?? '-'}</TableCell>
                      <TableCell>
                        <span className={(parseFloat(entry.hours ?? entry.horas ?? 0)) >= 0 ? 'text-green-600' : 'text-red-600'}>
                          {(parseFloat(entry.hours ?? entry.horas ?? 0)) >= 0 ? '+' : ''}{entry.hours ?? entry.horas ?? '-'}h
                        </span>
                      </TableCell>
                      <TableCell>{entry.reason ?? entry.motivo ?? '-'}</TableCell>
                      <TableCell>
                        {entry.status ? <Badge variant="outline" className="text-xs">{entry.status}</Badge> : '-'}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </div>
      )}

      {/* ABA SUBSTITUIÇÕES */}
      {activeTab === 'substituicoes' && (
        <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
            <Shield className="h-5 w-5" />
            Substituições
            {subsLoading && <RefreshCw className="h-4 w-4 animate-spin ml-2 text-muted-foreground" />}
          </h2>
          {substitutions.length === 0 ? (
            <div className="text-center py-10 text-[hsl(var(--muted-foreground))]">
              <Shield className="h-12 w-12 mx-auto mb-3 opacity-30" />
              <p>Nenhuma substituição registrada</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Data</TableHead>
                  <TableHead>Motivo</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Papel</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {(substitutions as any[]).map((sub: any, idx: number) => {
                  const isOriginal = String(sub.original_employee_id) === String(id);
                  return (
                    <TableRow key={sub.id ?? idx}>
                      <TableCell>{formatDate(sub.date ?? sub.data ?? sub.created_at)}</TableCell>
                      <TableCell>{sub.reason ?? sub.motivo ?? '-'}</TableCell>
                      <TableCell>
                        {sub.status ? <Badge variant="outline" className="text-xs">{sub.status}</Badge> : '-'}
                      </TableCell>
                      <TableCell>
                        {isOriginal ? (
                          <Badge className="bg-orange-100 text-orange-700 border-0 text-xs">Original</Badge>
                        ) : (
                          <Badge className="bg-blue-100 text-blue-700 border-0 text-xs">Substituto</Badge>
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </div>
      )}

      {/* ABA DOCUMENTOS */}
      {activeTab === 'documentos' && (
        <div className="space-y-4">
          {/* Form de adição */}
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <Plus className="h-5 w-5" />
              Adicionar Documento
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4 items-end">
              <div>
                <Label className="text-xs text-[hsl(var(--muted-foreground))] uppercase tracking-wide mb-1 block">Tipo</Label>
                <Select
                  value={docForm.type}
                  onValueChange={(v) => setDocForm({ ...docForm, type: v as DocumentRecord['type'] })}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Tipo de documento" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="CNH">CNH</SelectItem>
                    <SelectItem value="CREA">CREA</SelectItem>
                    <SelectItem value="Curso Vigilância">Curso de Vigilância</SelectItem>
                    <SelectItem value="ASO">ASO</SelectItem>
                    <SelectItem value="Outro">Outro</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              <div>
                <Label className="text-xs text-[hsl(var(--muted-foreground))] uppercase tracking-wide mb-1 block">Número</Label>
                <Input
                  value={docForm.number}
                  onChange={(e) => setDocForm({ ...docForm, number: e.target.value })}
                  placeholder="Nº do documento"
                />
              </div>
              <div>
                <Label className="text-xs text-[hsl(var(--muted-foreground))] uppercase tracking-wide mb-1 block">Vencimento</Label>
                <Input
                  type="date"
                  value={docForm.expiration}
                  onChange={(e) => setDocForm({ ...docForm, expiration: e.target.value })}
                />
              </div>
              <Button onClick={handleAddDocument} className="w-full">
                <Plus className="h-4 w-4 mr-2" />
                Adicionar
              </Button>
            </div>
            {docError && (
              <p className="text-sm text-destructive mt-3 flex items-center gap-2">
                <AlertTriangle className="h-4 w-4" />
                {docError}
              </p>
            )}
          </div>

          {/* Lista de documentos */}
          <div className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-xl p-6">
            <h2 className="text-lg font-semibold mb-4 flex items-center gap-2">
              <FileText className="h-5 w-5" />
              Documentos ({documents.length})
            </h2>
            {documents.length === 0 ? (
              <div className="text-center py-10 text-[hsl(var(--muted-foreground))]">
                <FileText className="h-12 w-12 mx-auto mb-3 opacity-30" />
                <p>Nenhum documento cadastrado</p>
                <p className="text-xs mt-1">Use o formulário acima para adicionar documentos</p>
              </div>
            ) : (
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-8" />
                    <TableHead>Tipo</TableHead>
                    <TableHead>Número</TableHead>
                    <TableHead>Vencimento</TableHead>
                    <TableHead>Situação</TableHead>
                    <TableHead className="w-16" />
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {documents.map((doc) => (
                    <TableRow key={doc.id}>
                      <TableCell className="text-center">{renderDocStatus(doc.status)}</TableCell>
                      <TableCell className="font-medium">{doc.type}</TableCell>
                      <TableCell>
                        <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{doc.number}</code>
                      </TableCell>
                      <TableCell>{formatDate(doc.expiration)}</TableCell>
                      <TableCell>
                        {doc.status === 'válido' && (
                          <Badge className="bg-green-100 text-green-700 border-0 text-xs">Válido</Badge>
                        )}
                        {doc.status === 'vencendo' && (
                          <Badge className="bg-yellow-100 text-yellow-700 border-0 text-xs">Vence em breve</Badge>
                        )}
                        {doc.status === 'vencido' && (
                          <Badge className="bg-red-100 text-red-700 border-0 text-xs">Vencido</Badge>
                        )}
                      </TableCell>
                      <TableCell>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-destructive hover:text-destructive hover:bg-destructive/10"
                          onClick={() => handleDeleteDocument(doc.id)}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ===== COMPONENTE AUXILIAR =====

function DataField({
  icon,
  label,
  value,
  mono = false,
}: {
  icon: React.ReactNode;
  label: string;
  value?: string | null;
  mono?: boolean;
}) {
  return (
    <div>
      <span className="text-xs text-[hsl(var(--muted-foreground))] uppercase tracking-wide font-medium flex items-center gap-1 mb-1">
        {icon}
        {label}
      </span>
      {mono ? (
        <code className="text-sm bg-muted px-2 py-0.5 rounded font-mono">{value || '-'}</code>
      ) : (
        <p className="text-sm text-[hsl(var(--foreground))] font-medium">{value || '-'}</p>
      )}
    </div>
  );
}
