'use client';

import { useState, useEffect } from 'react';
import { ArrowLeft, Plus, Trash2, Loader2, DollarSign, Users } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { PageHeader } from '@/components/ui/page-header';
import { StatCard } from '@/components/ui/stat-card';

const API_HR = '/api/v1/people-management/hr';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? localStorage.getItem('access_token') : null;
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

const RUBRICA_TYPES = [
  { value: 'Emprestimo Consignado', label: 'Empréstimo Consignado', desconto: true },
  { value: 'Pensao Alimenticia', label: 'Pensão Alimentícia', desconto: true },
  { value: 'Vale Refeicao', label: 'Vale Refeição', desconto: false },
  { value: 'Plano Saude', label: 'Plano de Saúde', desconto: true },
  { value: 'Plano Odontologico', label: 'Plano Odontológico', desconto: true },
  { value: 'Seguro Vida', label: 'Seguro de Vida', desconto: true },
  { value: 'VT', label: 'Vale Transporte', desconto: false },
  { value: 'Outros', label: 'Outros Descontos', desconto: true },
];

const fmt = (v: number) => `R$ ${(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`;

interface Benefit {
  id: string;
  employee_id: string;
  employee_name: string;
  type: string;
  provider: string | null;
  plan_name: string | null;
  employee_contribution: number;
  company_contribution: number;
  notes: string | null;
}

interface Employee {
  id: string;
  nome: string;
  cargo: string;
  salario_base: number;
}

export default function RubricasPage() {
  const router = useRouter();
  const [benefits, setBenefits] = useState<Benefit[]>([]);
  const [employees, setEmployees] = useState<Employee[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  // Form state
  const [selectedEmployee, setSelectedEmployee] = useState('');
  const [selectedType, setSelectedType] = useState('');
  const [valor, setValor] = useState('');
  const [provider, setProvider] = useState('');
  const [notes, setNotes] = useState('');

  useEffect(() => {
    loadData();
  }, []);

  async function loadData() {
    setLoading(true);
    try {
      const [empRes, benRes] = await Promise.all([
        fetch(`${API_HR}/employees?page_size=100`, { headers: getAuthHeaders() }),
        fetch(`${API_HR}/payroll/benefits`, { headers: getAuthHeaders() }),
      ]);
      if (empRes.ok) {
        const d = await empRes.json();
        setEmployees(d.items || []);
      }
      if (benRes.ok) {
        const d = await benRes.json();
        setBenefits(d.items || []);
      }
    } catch {
      /* fallback */
    } finally {
      setLoading(false);
    }
  }

  async function handleAdd() {
    if (!selectedEmployee || !selectedType || !valor) return;

    setSaving(true);
    try {
      const params = new URLSearchParams({
        employee_id: selectedEmployee,
        type: selectedType,
        employee_contribution: valor,
        company_contribution: '0',
        provider,
        plan_name: selectedType,
        notes,
      });

      const res = await fetch(`${API_HR}/payroll/benefits?${params}`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });

      if (res.ok) {
        setSelectedEmployee('');
        setSelectedType('');
        setValor('');
        setProvider('');
        setNotes('');
        await loadData();
      }
    } catch {
      /* fallback */
    } finally {
      setSaving(false);
    }
  }

  async function handleDelete(id: string) {
    if (!confirm('Desativar esta rubrica?')) return;
    try {
      await fetch(`${API_HR}/payroll/benefits/${id}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      await loadData();
    } catch {
      /* fallback */
    }
  }

  // Group benefits by employee
  const grouped = benefits.reduce(
    (acc, b) => {
      const key = b.employee_name || b.employee_id;
      if (!acc[key]) acc[key] = [];
      acc[key].push(b);
      return acc;
    },
    {} as Record<string, Benefit[]>
  );

  const totalDescontos = benefits.reduce((a, b) => a + b.employee_contribution, 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      {/* Header */}
      <PageHeader
        icon={<DollarSign className="h-5 w-5" />}
        title="Rubricas por Funcionário"
        subtitle="Cadastrar descontos e benefícios individuais"
        actions={(
          <Button type="button" variant="outline" size="sm" onClick={() => router.push('/modulos/dp/folha')}>
            <ArrowLeft className="h-4 w-4 mr-1" /> Voltar
          </Button>
        )}
      />

      {/* Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <StatCard label="Rubricas Ativas" value={benefits.length} />
        <StatCard label="Funcionários com Rubricas" value={Object.keys(grouped).length} />
        <StatCard label="Total Descontos/mes" value={<span className="text-red-600">{fmt(totalDescontos)}</span>} color="#dc2626" />
      </div>

      {/* Add Form */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Plus className="h-5 w-5" />
            Nova Rubrica de Desconto
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
            <div>
              <label htmlFor="field-employee" className="block text-sm text-muted-foreground mb-1">Funcionário *</label>
              <select
                id="field-employee"
                value={selectedEmployee}
                onChange={(e) => setSelectedEmployee(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Selecione...</option>
                {employees.map((e) => (
                  <option key={e.id} value={e.id}>
                    {e.nome} ({e.cargo})
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="field-type" className="block text-sm text-muted-foreground mb-1">Tipo *</label>
              <select
                id="field-type"
                value={selectedType}
                onChange={(e) => setSelectedType(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-[hsl(var(--border))] bg-[hsl(var(--background))] text-[hsl(var(--foreground))] text-sm"
              >
                <option value="">Selecione...</option>
                {RUBRICA_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="field-valor" className="block text-sm text-muted-foreground mb-1">Valor (R$) *</label>
              <Input
                id="field-valor"
                type="number"
                step="0.01"
                min="0"
                value={valor}
                onChange={(e) => setValor(e.target.value)}
                placeholder="0.00"
              />
            </div>
            <div>
              <label htmlFor="field-provider" className="block text-sm text-muted-foreground mb-1">Fornecedor/Banco</label>
              <Input
                id="field-provider"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                placeholder="Opcional"
              />
            </div>
            <div className="flex items-end">
              <Button
                type="button"
                onClick={handleAdd}
                disabled={saving || !selectedEmployee || !selectedType || !valor}
                className="w-full"
              >
                {saving ? <Loader2 className="h-4 w-4 animate-spin mr-1" /> : <Plus className="h-4 w-4 mr-1" />}
                Cadastrar
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Benefits Table */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Users className="h-5 w-5" />
            Rubricas Cadastradas — {benefits.length}
          </CardTitle>
        </CardHeader>
        <CardContent>
          {benefits.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <DollarSign className="h-12 w-12 mx-auto mb-3 opacity-30" />
              <p className="font-medium">Nenhuma rubrica individual cadastrada</p>
              <p className="text-sm mt-1">Use o formulario acima para cadastrar descontos por funcionario.</p>
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Funcionário</TableHead>
                  <TableHead>Tipo</TableHead>
                  <TableHead>Fornecedor</TableHead>
                  <TableHead className="text-right">Desconto</TableHead>
                  <TableHead className="text-right">Empresa</TableHead>
                  <TableHead className="w-10"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {benefits.map((b) => (
                  <TableRow key={b.id}>
                    <TableCell className="font-medium">{b.employee_name}</TableCell>
                    <TableCell>{b.type}</TableCell>
                    <TableCell className="text-muted-foreground">{b.provider || '-'}</TableCell>
                    <TableCell className="text-right text-red-600">{fmt(b.employee_contribution)}</TableCell>
                    <TableCell className="text-right text-green-600">{fmt(b.company_contribution)}</TableCell>
                    <TableCell>
                      <Button type="button" variant="ghost" size="sm" onClick={() => handleDelete(b.id)}>
                        <Trash2 className="h-4 w-4 text-red-500" />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
