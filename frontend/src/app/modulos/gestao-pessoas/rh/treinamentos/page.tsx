'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { ArrowLeft, GraduationCap, Clock, Users, CheckCircle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

const API_BASE = '/api/v1/people-management/human-resources/training';

function getAuthHeaders() {
  let token: string | null = null;
  if (typeof window !== 'undefined') {
    try {
      token = localStorage.getItem('access_token') || localStorage.getItem('token');
    } catch {
      token = null;
    }
  }
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

interface Treinamento {
  id: string;
  title?: string;
  titulo?: string;
  name?: string;
  description?: string;
  descricao?: string;
  status?: string;
  is_active?: boolean;
  is_mandatory?: boolean;
  carga_horaria?: number;
  duration_hours?: number;
  total_inscritos?: number;
  enrolled_count?: number;
  completed_count?: number;
  total_concluintes?: number;
  instructor?: string;
  instructor_name?: string;
  instrutor?: string;
  provider?: string;
  start_date?: string;
  end_date?: string;
  category?: string;
  categoria?: string;
}

const STATUS_BADGE: Record<string, string> = {
  active: 'bg-green-100 text-green-700 border-green-200',
  ativo: 'bg-green-100 text-green-700 border-green-200',
  completed: 'bg-blue-100 text-blue-700 border-blue-200',
  concluido: 'bg-blue-100 text-blue-700 border-blue-200',
  pending: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  pendente: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  cancelled: 'bg-red-100 text-red-700 border-red-200',
  cancelado: 'bg-red-100 text-red-700 border-red-200',
};

export default function PageTreinamentos() {
  const [treinamentos, setTreinamentos] = useState<Treinamento[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_BASE}/courses`, { headers: getAuthHeaders() })
      .then((r) => r.json())
      .then((d) => {
        const lista = Array.isArray(d)
          ? d
          : (d.items ?? d.courses ?? d.treinamentos ?? d.data ?? []);
        setTreinamentos(lista);
      })
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  const normTitle = (t: Treinamento) => t.title ?? t.titulo ?? t.name ?? '—';
  const normHoras = (t: Treinamento) => t.carga_horaria ?? t.duration_hours;
  const normInscritos = (t: Treinamento) => t.total_inscritos ?? t.enrolled_count ?? 0;
  const normConcluintes = (t: Treinamento) => t.total_concluintes ?? t.completed_count ?? 0;
  const normStatus = (t: Treinamento) => {
    if (t.status) return t.status;
    if (t.is_active !== undefined) return t.is_active ? 'ativo' : 'inativo';
    return 'ativo';
  };
  const normInstrutor = (t: Treinamento) =>
    t.instructor_name ?? t.instructor ?? t.instrutor ?? t.provider;

  const ativos = treinamentos.filter(
    (t) => normStatus(t) === 'active' || normStatus(t) === 'ativo'
  ).length;
  const totalInscritos = treinamentos.reduce((s, t) => s + normInscritos(t), 0);
  const totalHoras = treinamentos.reduce((s, t) => s + (normHoras(t) ?? 0), 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 animate-spin text-[#F97316]" />
        <span className="ml-3 text-gray-500">Carregando treinamentos...</span>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#F8F9FB] p-6">
      <div className="flex items-center gap-3 mb-6">
        <Link
          href="/modulos/gestao-pessoas/rh"
          className="flex items-center gap-1 text-gray-400 hover:text-[#1E3A5F] transition-colors"
        >
          <ArrowLeft className="w-4 h-4" /> Voltar
        </Link>
        <span className="text-gray-300">|</span>
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Treinamentos</h1>
        <span className="ml-auto px-3 py-1 rounded-full text-sm font-medium bg-orange-100 text-orange-700 border border-orange-200">
          {treinamentos.length} cursos
        </span>
      </div>

      {/* Métricas */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <Card className="border border-gray-100">
          <CardContent className="p-5">
            <div className="w-10 h-10 bg-blue-50 rounded-lg flex items-center justify-center mb-3">
              <GraduationCap className="w-5 h-5 text-blue-600" />
            </div>
            <p className="text-sm text-gray-500">Total de cursos</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-[hsl(var(--foreground))] mt-1">{treinamentos.length}</p>
          </CardContent>
        </Card>
        <Card className="border border-gray-100">
          <CardContent className="p-5">
            <div className="w-10 h-10 bg-green-50 rounded-lg flex items-center justify-center mb-3">
              <CheckCircle className="w-5 h-5 text-green-600" />
            </div>
            <p className="text-sm text-gray-500">Ativos</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-green-600 mt-1">{ativos}</p>
          </CardContent>
        </Card>
        <Card className="border border-gray-100">
          <CardContent className="p-5">
            <div className="w-10 h-10 bg-orange-50 rounded-lg flex items-center justify-center mb-3">
              <Users className="w-5 h-5 text-[#F97316]" />
            </div>
            <p className="text-sm text-gray-500">Total inscritos</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-[#F97316] mt-1">{totalInscritos}</p>
          </CardContent>
        </Card>
        <Card className="border border-gray-100">
          <CardContent className="p-5">
            <div className="w-10 h-10 bg-purple-50 rounded-lg flex items-center justify-center mb-3">
              <Clock className="w-5 h-5 text-purple-600" />
            </div>
            <p className="text-sm text-gray-500">Carga horária total</p>
            <p className="font-data text-2xl font-semibold tabular-nums text-purple-600 mt-1">{totalHoras}h</p>
          </CardContent>
        </Card>
      </div>

      {/* Grid de cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {treinamentos.map((t, i) => {
          const inscritos = normInscritos(t);
          const concluintes = normConcluintes(t);
          const pctConclusao = inscritos > 0 ? Math.round((concluintes / inscritos) * 100) : 0;
          const status = normStatus(t);

          return (
            <Card
              key={t.id ?? i}
              className="border border-gray-100 hover:border-[#F97316] hover:shadow-md transition-all"
            >
              <CardContent className="p-5">
                <div className="flex items-start justify-between mb-3">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    <div className="w-10 h-10 bg-orange-50 rounded-lg flex items-center justify-center shrink-0">
                      <GraduationCap className="w-5 h-5 text-[#F97316]" />
                    </div>
                    <div className="min-w-0">
                      <p className="font-semibold text-gray-900 leading-tight line-clamp-2">
                        {normTitle(t)}
                      </p>
                      {t.category || t.categoria ? (
                        <p className="text-xs text-gray-400 mt-0.5">
                          {t.category ?? t.categoria}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <span
                    className={`ml-2 px-2 py-0.5 rounded-full text-xs font-medium border shrink-0 ${
                      STATUS_BADGE[status] ?? 'bg-gray-100 text-gray-700 border-gray-200'
                    }`}
                  >
                    {status}
                  </span>
                </div>

                {t.description || t.descricao ? (
                  <p className="text-sm text-gray-500 mb-3 line-clamp-2">
                    {t.description ?? t.descricao}
                  </p>
                ) : null}

                <div className="grid grid-cols-2 gap-2 mb-3">
                  {normHoras(t) != null && (
                    <div className="bg-gray-50 rounded px-3 py-2">
                      <p className="text-xs text-gray-400">Carga horária</p>
                      <p className="text-sm font-semibold text-gray-700">{normHoras(t)}h</p>
                    </div>
                  )}
                  {inscritos > 0 && (
                    <div className="bg-blue-50 rounded px-3 py-2">
                      <p className="text-xs text-gray-400">Inscritos</p>
                      <p className="text-sm font-semibold text-blue-700">{inscritos}</p>
                    </div>
                  )}
                </div>

                {inscritos > 0 && (
                  <div>
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>Conclusão</span>
                      <span>{concluintes}/{inscritos} ({pctConclusao}%)</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full ${
                          pctConclusao >= 80
                            ? 'bg-green-500'
                            : pctConclusao >= 50
                              ? 'bg-[#F97316]'
                              : 'bg-red-400'
                        }`}
                        style={{ width: `${pctConclusao}%` }}
                      />
                    </div>
                  </div>
                )}

                {normInstrutor(t) && (
                  <p className="text-xs text-gray-400 mt-3">
                    Instrutor: <span className="text-gray-600">{normInstrutor(t)}</span>
                  </p>
                )}
              </CardContent>
            </Card>
          );
        })}

        {treinamentos.length === 0 && (
          <div className="col-span-3 text-center py-16 text-gray-400">
            <GraduationCap className="w-12 h-12 mx-auto mb-3 opacity-30" />
            <p>Nenhum treinamento cadastrado</p>
          </div>
        )}
      </div>
    </div>
  );
}
