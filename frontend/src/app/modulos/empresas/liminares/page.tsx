'use client';

import { useState } from 'react';
import type { FC } from 'react';
import Link from 'next/link';
import {
  ArrowLeft,
  Scale,
  Plus,
  X,
  CheckCircle,
  Clock,
  AlertTriangle,
  XCircle,
  Info,
  Building2,
  type LucideProps,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

// ─── Tipos ──────────────────────────────────────────────────────────────────

type LiminarStatus = 'a_solicitar' | 'aguardando' | 'concedida' | 'cassada';

interface Liminar {
  id: string;
  empresa: string;
  tipo: string;
  descricao: string;
  status: LiminarStatus;
  fundamento: string;
  processo?: string;
  data_concessao?: string;
  validade?: string;
}

interface NovaLiminarForm {
  empresa: string;
  tipo: string;
  descricao: string;
  fundamento: string;
  processo: string;
}

// ─── Dados Mock ─────────────────────────────────────────────────────────────

const LIMINARES_INICIAIS: Liminar[] = [
  {
    id: '1',
    empresa: 'Conecta Mais Patrimonial',
    tipo: 'PIS/COFINS = 0',
    descricao: 'Não cobrança de PIS e COFINS nas notas de serviço',
    status: 'a_solicitar',
    fundamento: 'Bitributação - LC 123/2006',
    processo: '',
    data_concessao: '',
    validade: '',
  },
  {
    id: '2',
    empresa: 'Conecta Mais Patrimonial',
    tipo: 'INSS Não Retido',
    descricao: 'Não retenção de INSS na nota de serviço de vigilância',
    status: 'a_solicitar',
    fundamento: 'CPP já incluso no DAS - LC 123/2006, Art. 18',
    processo: '',
    data_concessao: '',
    validade: '',
  },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────

type LucideIcon = FC<LucideProps>;

const STATUS_CONFIG: Record<LiminarStatus, { label: string; color: string; icon: LucideIcon }> = {
  a_solicitar: { label: 'A Solicitar', color: 'bg-yellow-100 text-yellow-700', icon: Clock },
  aguardando: { label: 'Aguardando', color: 'bg-blue-100 text-blue-700', icon: Clock },
  concedida: { label: 'Concedida', color: 'bg-green-100 text-green-700', icon: CheckCircle },
  cassada: { label: 'Cassada', color: 'bg-red-100 text-red-700', icon: XCircle },
};

const FORM_EMPTY: NovaLiminarForm = {
  empresa: '',
  tipo: '',
  descricao: '',
  fundamento: '',
  processo: '',
};

// ─── Componente Principal ──────────────────────────────────────────────────

export default function LiminaresPage() {
  const [liminares, setLiminares] = useState<Liminar[]>(LIMINARES_INICIAIS);
  const [showModal, setShowModal] = useState(false);
  const [form, setForm] = useState<NovaLiminarForm>(FORM_EMPTY);
  const [filterStatus, setFilterStatus] = useState<LiminarStatus | 'todas'>('todas');

  const filtradas = filterStatus === 'todas'
    ? liminares
    : liminares.filter((l) => l.status === filterStatus);

  const handleSave = () => {
    if (!form.empresa || !form.tipo) return;
    const nova: Liminar = {
      id: Date.now().toString(),
      empresa: form.empresa,
      tipo: form.tipo,
      descricao: form.descricao,
      fundamento: form.fundamento,
      processo: form.processo,
      status: 'a_solicitar',
    };
    setLiminares((prev) => [...prev, nova]);
    setForm(FORM_EMPTY);
    setShowModal(false);
  };

  const handleStatusChange = (id: string, status: LiminarStatus) => {
    setLiminares((prev) => prev.map((l) => (l.id === id ? { ...l, status } : l)));
  };

  const countByStatus = (s: LiminarStatus) => liminares.filter((l) => l.status === s).length;

  return (
    <div className="min-h-screen bg-gray-50 p-4 md:p-8">
      {/* Header */}
      <div className="mb-6">
        <Link
          href="/modulos/empresas"
          className="flex items-center gap-2 text-sm text-gray-500 hover:text-[#111b57] mb-4 transition-colors w-fit"
        >
          <ArrowLeft className="h-4 w-4" />
          Voltar para Multi-Empresa
        </Link>
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h1 className="font-display text-2xl md:text-3xl font-bold text-[#111b57] flex items-center gap-3">
              <Scale className="h-8 w-8 text-[#f97707]" />
              Liminares Judiciais
            </h1>
            <p className="text-gray-500 mt-1">
              Gestão de liminares tributárias e decisões judiciais
            </p>
          </div>
          <button
            onClick={() => setShowModal(true)}
            className="flex items-center gap-2 bg-[#111b57] hover:bg-[#1a47f5] text-white font-semibold px-5 py-2.5 rounded-lg text-sm transition-colors"
          >
            <Plus className="h-4 w-4" />
            Nova Liminar
          </button>
        </div>
      </div>

      {/* Info Banner */}
      <div className="bg-blue-50 border border-blue-200 rounded-xl p-4 flex gap-3 mb-6">
        <Info className="h-5 w-5 text-blue-600 shrink-0 mt-0.5" />
        <p className="text-sm text-blue-700">
          <strong>Liminares concedidas</strong> são aplicadas automaticamente em todas as NFS-e
          emitidas pela empresa correspondente. Mantenha as informações atualizadas.
        </p>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        {(
          [
            { status: 'todas' as const, label: 'Total', count: liminares.length, color: 'border-gray-200', text: 'text-gray-700', bg: '' },
            { status: 'a_solicitar' as const, label: 'A Solicitar', count: countByStatus('a_solicitar'), color: 'border-yellow-200', text: 'text-yellow-700', bg: 'bg-yellow-50' },
            { status: 'aguardando' as const, label: 'Aguardando', count: countByStatus('aguardando'), color: 'border-blue-200', text: 'text-blue-700', bg: 'bg-blue-50' },
            { status: 'concedida' as const, label: 'Concedidas', count: countByStatus('concedida'), color: 'border-green-200', text: 'text-green-700', bg: 'bg-green-50' },
          ] as const
        ).map((kpi) => (
          <button
            key={kpi.status}
            onClick={() => setFilterStatus(kpi.status)}
            className={cn(
              'text-left border rounded-xl p-4 transition-all',
              kpi.bg || 'bg-white',
              kpi.color,
              filterStatus === kpi.status ? 'ring-2 ring-[#1a47f5]' : 'hover:shadow-sm'
            )}
          >
            <p className="text-xs text-gray-500 mb-1">{kpi.label}</p>
            <p className={cn('font-data text-2xl font-semibold tabular-nums', kpi.text)}>{kpi.count}</p>
          </button>
        ))}
      </div>

      {/* Table */}
      <Card className="border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                <th className="text-left py-3 px-4 font-semibold text-gray-600">Empresa</th>
                <th className="text-left py-3 px-4 font-semibold text-gray-600">Tipo</th>
                <th className="text-left py-3 px-4 font-semibold text-gray-600 hidden md:table-cell">Descrição</th>
                <th className="text-left py-3 px-4 font-semibold text-gray-600 hidden lg:table-cell">Fundamento</th>
                <th className="text-left py-3 px-4 font-semibold text-gray-600 hidden lg:table-cell">Processo</th>
                <th className="text-left py-3 px-4 font-semibold text-gray-600">Status</th>
                <th className="text-left py-3 px-4 font-semibold text-gray-600 hidden sm:table-cell">Data Concessão</th>
                <th className="text-left py-3 px-4 font-semibold text-gray-600"></th>
              </tr>
            </thead>
            <tbody>
              {filtradas.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-12 text-center text-gray-400">
                    Nenhuma liminar encontrada
                  </td>
                </tr>
              ) : (
                filtradas.map((lim, idx) => {
                  const cfg = STATUS_CONFIG[lim.status];
                  const Icon = cfg.icon;
                  return (
                    <tr
                      key={lim.id}
                      className={cn(
                        'border-b border-gray-100 hover:bg-gray-50 transition-colors',
                        idx % 2 === 0 ? '' : 'bg-gray-50/50'
                      )}
                    >
                      <td className="py-3 px-4">
                        <div className="flex items-center gap-2">
                          <Building2 className="h-4 w-4 text-gray-400 shrink-0" />
                          <span className="font-medium text-gray-800 text-xs leading-tight">
                            {lim.empresa.replace('Conecta Mais ', '')}
                          </span>
                        </div>
                      </td>
                      <td className="py-3 px-4">
                        <span className="font-semibold text-gray-800">{lim.tipo}</span>
                      </td>
                      <td className="py-3 px-4 hidden md:table-cell">
                        <span className="text-gray-600 text-xs">{lim.descricao}</span>
                      </td>
                      <td className="py-3 px-4 hidden lg:table-cell">
                        <span className="text-gray-500 text-xs">{lim.fundamento}</span>
                      </td>
                      <td className="py-3 px-4 hidden lg:table-cell">
                        <span className="text-gray-500 text-xs font-mono">
                          {lim.processo || '—'}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <span className={cn('flex items-center gap-1.5 text-xs font-semibold px-2 py-1 rounded-full w-fit', cfg.color)}>
                          <Icon className="h-3 w-3" />
                          {cfg.label}
                        </span>
                      </td>
                      <td className="py-3 px-4 hidden sm:table-cell">
                        <span className="text-gray-500 text-xs">
                          {lim.data_concessao || '—'}
                        </span>
                      </td>
                      <td className="py-3 px-4">
                        <select
                          value={lim.status}
                          onChange={(e) => handleStatusChange(lim.id, e.target.value as LiminarStatus)}
                          className="text-xs border border-gray-200 rounded-lg px-2 py-1 bg-white focus:outline-none focus:ring-1 focus:ring-[#1a47f5]"
                        >
                          <option value="a_solicitar">A Solicitar</option>
                          <option value="aguardando">Aguardando</option>
                          <option value="concedida">Concedida</option>
                          <option value="cassada">Cassada</option>
                        </select>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Info cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6">
        <div className="bg-yellow-50 border border-yellow-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <AlertTriangle className="h-4 w-4 text-yellow-600" />
            <p className="font-semibold text-yellow-800 text-sm">PIS/COFINS = 0</p>
          </div>
          <p className="text-xs text-yellow-700">
            Empresas do Simples Nacional já recolhem PIS e COFINS dentro do DAS.
            A liminar impede a bitributação nas notas de prestação de serviço.
          </p>
        </div>
        <div className="bg-purple-50 border border-purple-200 rounded-xl p-4">
          <div className="flex items-center gap-2 mb-2">
            <Scale className="h-4 w-4 text-purple-600" />
            <p className="font-semibold text-purple-800 text-sm">INSS Não Retido</p>
          </div>
          <p className="text-xs text-purple-700">
            No Simples Nacional, a CPP (Contribuição Patronal) já está incluída no DAS.
            A liminar evita retenção adicional de 11% nas notas de vigilância.
          </p>
        </div>
      </div>

      {/* Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <Card className="w-full max-w-lg shadow-2xl">
            <CardContent className="p-6">
              <div className="flex items-center justify-between mb-5">
                <h3 className="text-lg font-bold text-[#111b57]">Nova Liminar</h3>
                <button
                  onClick={() => { setShowModal(false); setForm(FORM_EMPTY); }}
                  className="text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Empresa *</label>
                  <select
                    value={form.empresa}
                    onChange={(e) => setForm((f) => ({ ...f, empresa: e.target.value }))}
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5] bg-white"
                  >
                    <option value="">Selecione...</option>
                    <option value="Conecta Mais Eletrônica">Conecta Mais Eletrônica</option>
                    <option value="Conecta Mais Patrimonial">Conecta Mais Patrimonial</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Tipo de Liminar *</label>
                  <input
                    type="text"
                    value={form.tipo}
                    onChange={(e) => setForm((f) => ({ ...f, tipo: e.target.value }))}
                    placeholder="Ex: ISS Reduzido, IRRF Suspenso..."
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5]"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Descrição</label>
                  <textarea
                    value={form.descricao}
                    onChange={(e) => setForm((f) => ({ ...f, descricao: e.target.value }))}
                    rows={2}
                    placeholder="Descreva o benefício da liminar..."
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5] resize-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Fundamento Legal</label>
                  <input
                    type="text"
                    value={form.fundamento}
                    onChange={(e) => setForm((f) => ({ ...f, fundamento: e.target.value }))}
                    placeholder="Ex: LC 123/2006, Art. 18"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5]"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Número do Processo</label>
                  <input
                    type="text"
                    value={form.processo}
                    onChange={(e) => setForm((f) => ({ ...f, processo: e.target.value }))}
                    placeholder="Ex: 0001234-56.2024.8.04.0001"
                    className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-[#1a47f5] font-mono"
                  />
                </div>
              </div>

              <div className="flex gap-3 mt-6">
                <button
                  onClick={() => { setShowModal(false); setForm(FORM_EMPTY); }}
                  className="flex-1 border border-gray-200 text-gray-600 hover:bg-gray-50 font-semibold py-2.5 rounded-lg text-sm transition-colors"
                >
                  Cancelar
                </button>
                <button
                  onClick={handleSave}
                  disabled={!form.empresa || !form.tipo}
                  className="flex-1 bg-[#111b57] hover:bg-[#1a47f5] disabled:opacity-50 text-white font-semibold py-2.5 rounded-lg text-sm transition-colors"
                >
                  Salvar Liminar
                </button>
              </div>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
