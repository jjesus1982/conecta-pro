'use client';

import { useState, useEffect } from 'react';
import {
  Scale, FileText, Bot, AlertTriangle, PenLine, Search, Building2,
  Clock, ShieldCheck, TrendingUp, Loader2, ArrowRight,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';

const API_BASE = '/api/v1/juridico';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}
const fmt = (v: number | null | undefined) => (v == null ? '—' : `R$ ${(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`);

const ATALHOS = [
  { label: 'Central de Contratos', desc: 'Vigência, reajustes e assinaturas', href: '/modulos/juridico/contratos', icon: FileText, color: 'text-blue-600' },
  { label: 'Consultor IA', desc: 'Perguntas jurídicas trabalhista/cível/tributária', href: '/modulos/juridico/consultor', icon: Bot, color: 'text-indigo-600' },
  { label: 'Riscos', desc: 'Exposição trabalhista e tributária', href: '/modulos/juridico/riscos', icon: AlertTriangle, color: 'text-red-600' },
  { label: 'Pareceres', desc: 'Pareceres jurídicos emitidos', href: '/modulos/juridico/pareceres', icon: PenLine, color: 'text-purple-600' },
  { label: 'Análise', desc: 'Análise de cláusulas e documentos', href: '/modulos/juridico/analise', icon: Search, color: 'text-emerald-600' },
  { label: 'Escritório & ROI', desc: 'Custos, produtividade e retorno', href: '/modulos/juridico/escritorio', icon: Building2, color: 'text-orange-600' },
];

export default function EscritorioJuridicoHub() {
  const router = useRouter();
  const [dash, setDash] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const d = await fetch(`${API_BASE}/dashboard`, { headers: getAuthHeaders() })
          .then((r) => (r.ok ? r.json() : null))
          .catch(() => null);
        setDash(d);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const c = dash?.cards || {};
  const ct = c.contratos || {};
  const consultas = c.consultas_ia || c.consultas || {};
  const pareceres = c.pareceres || {};
  const analises = c.analises || {};
  const prazos = c.prazos || {};
  const certidoes = c.certidoes || {};

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <Scale className="h-8 w-8 text-blue-700" />
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Escritório Jurídico IA — Conecta Mais</h1>
          <p className="text-sm text-muted-foreground">
            Visão consolidada {dash?.referencia ? `· referência ${dash.referencia}` : ''}
            {dash?.pendencias_totais != null ? ` · ${dash.pendencias_totais} pendências` : ''}
          </p>
        </div>
      </div>

      {!dash && (
        <Card>
          <CardContent className="py-8 text-center text-muted-foreground">
            Não foi possível carregar o painel jurídico agora. Tente novamente mais tarde.
          </CardContent>
        </Card>
      )}

      {dash && (
        <>
          {/* KPIs por área */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {/* Contratos */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base"><FileText className="h-4 w-4 text-blue-600" /> Contratos</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Ativos</span><span className="font-semibold">{ct.ativos ?? 0} / {ct.total ?? 0}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Valor mensal ativo</span><span className="font-semibold text-green-600">{fmt(ct.valor_mensal_ativo)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Carteira ativa</span><span className="font-semibold">{fmt(ct.valor_carteira_ativa)}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Vencendo em 30d</span><span className="font-semibold text-yellow-600">{ct.vencendo_30d ?? 0}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Vencidos</span><span className="font-semibold text-red-600">{ct.vencidos ?? 0}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Assinaturas pendentes</span><span className="font-semibold text-orange-600">{ct.assinaturas_pendentes ?? 0}</span></div>
              </CardContent>
            </Card>

            {/* Consultas IA */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base"><Bot className="h-4 w-4 text-indigo-600" /> Consultas IA</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Total</span><span className="font-semibold">{consultas.total ?? 0}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Escalonadas</span><span className="font-semibold text-orange-600">{consultas.escalonadas ?? 0}</span></div>
              </CardContent>
            </Card>

            {/* Pareceres */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base"><PenLine className="h-4 w-4 text-purple-600" /> Pareceres</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Total</span><span className="font-semibold">{pareceres.total ?? 0}</span></div>
              </CardContent>
            </Card>

            {/* Análises */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base"><Search className="h-4 w-4 text-emerald-600" /> Análises</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Total</span><span className="font-semibold">{analises.total ?? 0}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Com cláusulas críticas</span><span className="font-semibold text-red-600">{analises.com_clausulas_criticas ?? 0}</span></div>
              </CardContent>
            </Card>

            {/* Prazos */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base"><Clock className="h-4 w-4 text-yellow-600" /> Prazos</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Abertos</span><span className="font-semibold">{prazos.abertos ?? 0}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Atrasados</span><span className="font-semibold text-red-600">{prazos.atrasados ?? 0}</span></div>
              </CardContent>
            </Card>

            {/* Certidões */}
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="flex items-center gap-2 text-base"><ShieldCheck className="h-4 w-4 text-green-600" /> Certidões</CardTitle>
              </CardHeader>
              <CardContent className="space-y-1 text-sm">
                <div className="flex justify-between"><span className="text-muted-foreground">Válidas</span><span className="font-semibold text-green-600">{certidoes.validas ?? 0}</span></div>
                <div className="flex justify-between"><span className="text-muted-foreground">Vencidas</span><span className="font-semibold text-red-600">{certidoes.vencidas ?? 0}</span></div>
              </CardContent>
            </Card>
          </div>
        </>
      )}

      {/* Atalhos */}
      <div>
        <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">Áreas do escritório</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {ATALHOS.map((a) => (
            <Card key={a.href} className="hover:shadow-md transition-shadow cursor-pointer" onClick={() => router.push(a.href)}>
              <CardContent className="pt-6 flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <a.icon className={`h-6 w-6 ${a.color}`} />
                  <div>
                    <div className="font-semibold">{a.label}</div>
                    <div className="text-xs text-muted-foreground">{a.desc}</div>
                  </div>
                </div>
                <Button variant="ghost" size="sm" className="shrink-0" onClick={(e) => { e.stopPropagation(); router.push(a.href); }}>
                  <ArrowRight className="h-4 w-4" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </div>
  );
}
