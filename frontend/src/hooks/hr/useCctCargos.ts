/**
 * useCctCargos — Cargos da CCT 2026 SINDECOMPRESTS (fonte única de cargos).
 *
 * Consome GET /api/v1/people-management/hr/cct/cargos, que retorna:
 *   { cargos: [{ id, cargo_nome, piso_salarial, ... }], total, sindicato, vigencia }
 *
 * Usado por todos os cadastros/edições de funcionário para popular o dropdown
 * de cargo em vez de listas hardcoded / texto livre.
 */
'use client';

import { useState, useEffect } from 'react';

const API_BASE = '/api/v1/people-management/hr';

function getAuthHeaders(): Record<string, string> {
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

export interface CctCargo {
  id: string;
  cargo_nome?: string;
  nome?: string;
  name?: string;
  piso_salarial?: number;
  adicional_insalubridade_percentual?: number;
  adicional_periculosidade_percentual?: number;
  adicional_noturno_percentual?: number;
  jornada_semanal_horas?: number;
}

/** Nome legível de um cargo CCT, tolerante às variações de campo do backend. */
export function cargoLabel(c: CctCargo): string {
  return c.cargo_nome ?? c.nome ?? c.name ?? '';
}

export function useCctCargos() {
  const [cargos, setCargos] = useState<CctCargo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    fetch(`${API_BASE}/cct/cargos`, { headers: getAuthHeaders() })
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        const lista: CctCargo[] = Array.isArray(d) ? d : (d.cargos ?? d.data ?? []);
        setCargos(lista);
      })
      .catch((e) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Erro ao carregar cargos CCT');
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { cargos, loading, error };
}
