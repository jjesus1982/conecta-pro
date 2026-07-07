'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { ArrowLeft, Building2, Phone, Mail, DollarSign, FileText, Users, Activity, AlertTriangle, Heart } from 'lucide-react';

export default function Cliente360Page() {
  const params = useParams();
  const router = useRouter();
  const clientId = params.id as string;

  const { data, isLoading, error } = useQuery({
    queryKey: ['crm-client-360', clientId],
    queryFn: () => customInstance({ url: `/api/v1/crm/clients/${clientId}/360`, method: 'GET' }),
    enabled: !!clientId,
    staleTime: 30_000,
  });

  if (isLoading) return <div className="p-8 text-center text-gray-500">Carregando visão 360°...</div>;
  if (error) return <div className="p-8 text-center text-red-500">Erro ao carregar cliente</div>;
  if (!data) return null;

  const d = data as any;
  const cliente = d.cliente || {};
  const contratos = d.contratos || [];
  const oportunidades = d.oportunidades || [];
  const contatos = d.contatos || [];
  const atividades = d.atividades || [];
  const nfse = d.nfse || [];

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-4">
        <button onClick={() => router.back()} className="p-2 hover:bg-gray-100 rounded-lg">
          <ArrowLeft className="h-5 w-5" />
        </button>
        <div className="flex-1">
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">{cliente.name}</h1>
          <p className="text-gray-500">CNPJ: {cliente.cnpj} | {cliente.crm_origin === 'converted_lead' ? `Lead: ${cliente.lead_name}` : 'Cliente direto'}</p>
        </div>
        <div className="flex gap-2">
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${cliente.status === 'active' ? 'bg-green-100 text-green-800' : 'bg-gray-100 text-gray-600'}`}>
            {cliente.status}
          </span>
          {cliente.is_defaulter && <span className="px-3 py-1 rounded-full text-sm bg-red-100 text-red-800">Inadimplente</span>}
          {cliente.is_vip && <span className="px-3 py-1 rounded-full text-sm bg-yellow-100 text-yellow-800">VIP</span>}
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm mb-1"><DollarSign className="h-4 w-4" /> MRR</div>
          <p className="font-data text-2xl font-semibold tabular-nums text-green-600">R$ {cliente.mrr?.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm mb-1"><Heart className="h-4 w-4" /> Health Score</div>
          <p className={`font-data text-2xl font-semibold tabular-nums ${(cliente.health_score ?? 0) >= 70 ? 'text-green-600' : (cliente.health_score ?? 0) >= 40 ? 'text-yellow-600' : 'text-red-600'}`}>
            {cliente.health_score ?? 0}
          </p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm mb-1"><FileText className="h-4 w-4" /> Contratos</div>
          <p className="font-data text-2xl font-semibold tabular-nums">{contratos.length}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm mb-1"><Users className="h-4 w-4" /> Contatos</div>
          <p className="font-data text-2xl font-semibold tabular-nums">{contatos.length}</p>
        </div>
        <div className="bg-white rounded-xl border p-4">
          <div className="flex items-center gap-2 text-gray-500 text-sm mb-1"><Activity className="h-4 w-4" /> NFS-e</div>
          <p className="font-data text-2xl font-semibold tabular-nums">{nfse.length}</p>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Contratos */}
        <div className="bg-white rounded-xl border p-4">
          <h2 className="font-semibold text-lg mb-3">Contratos Ativos</h2>
          {contratos.length === 0 ? <p className="text-gray-400 text-sm">Nenhum contrato ativo</p> : (
            <div className="space-y-2">
              {contratos.map((c: any) => (
                <div key={c.id} className="flex justify-between items-center p-2 bg-gray-50 rounded">
                  <span className="text-sm">{c.service_type}</span>
                  <span className="font-semibold text-green-600">R$ {c.monthly_value?.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}/mês</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Oportunidades */}
        <div className="bg-white rounded-xl border p-4">
          <h2 className="font-semibold text-lg mb-3">Oportunidades de Upsell</h2>
          {oportunidades.length === 0 ? <p className="text-gray-400 text-sm">Nenhuma oportunidade aberta</p> : (
            <div className="space-y-2">
              {oportunidades.map((o: any) => (
                <div key={o.id} className="flex justify-between items-center p-2 bg-blue-50 rounded">
                  <div>
                    <span className="text-sm font-medium">{o.title}</span>
                    <span className="ml-2 text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded">{o.stage}</span>
                  </div>
                  <span className="font-semibold">R$ {o.value?.toLocaleString('pt-BR')}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Contatos */}
        <div className="bg-white rounded-xl border p-4">
          <h2 className="font-semibold text-lg mb-3">Contatos</h2>
          {contatos.length === 0 ? <p className="text-gray-400 text-sm">Nenhum contato cadastrado</p> : (
            <div className="space-y-2">
              {contatos.map((ct: any) => (
                <div key={ct.id} className="p-2 bg-gray-50 rounded">
                  <div className="flex items-center gap-2">
                    <span className="font-medium text-sm">{ct.name}</span>
                    {ct.is_primary && <span className="text-xs bg-green-100 text-green-700 px-1.5 rounded">Principal</span>}
                  </div>
                  <div className="flex gap-3 text-xs text-gray-500 mt-1">
                    {ct.role && <span>{ct.role}</span>}
                    {ct.email && <span className="flex items-center gap-1"><Mail className="h-3 w-3" />{ct.email}</span>}
                    {ct.phone && <span className="flex items-center gap-1"><Phone className="h-3 w-3" />{ct.phone}</span>}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* NFS-e */}
        <div className="bg-white rounded-xl border p-4">
          <h2 className="font-semibold text-lg mb-3">NFS-e Emitidas</h2>
          {nfse.length === 0 ? <p className="text-gray-400 text-sm">Nenhuma NFS-e</p> : (
            <div className="space-y-2">
              {nfse.map((n: any, i: number) => (
                <div key={i} className="flex justify-between items-center p-2 bg-gray-50 rounded text-sm">
                  <span>NF {n.numero} — {n.competencia}</span>
                  <span className="font-semibold">R$ {n.valor?.toLocaleString('pt-BR', { minimumFractionDigits: 2 })}</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Atividades */}
        <div className="bg-white rounded-xl border p-4 lg:col-span-2">
          <h2 className="font-semibold text-lg mb-3">Timeline de Atividades</h2>
          {atividades.length === 0 ? <p className="text-gray-400 text-sm">Nenhuma atividade registrada</p> : (
            <div className="space-y-2">
              {atividades.map((a: any) => (
                <div key={a.id} className="flex gap-3 p-2 border-l-2 border-blue-300 pl-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-xs bg-gray-100 px-2 py-0.5 rounded uppercase">{a.type}</span>
                      <span className="font-medium text-sm">{a.subject}</span>
                    </div>
                    {a.description && <p className="text-xs text-gray-500 mt-1">{a.description}</p>}
                  </div>
                  <span className="text-xs text-gray-400 whitespace-nowrap">{a.created_at?.split('T')[0]}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
