/**
 * Hook React Query para o Brand Voice do condominio do usuario logado.
 *
 * Endpoint backend: GET /api/v1/marketing/brand-voice/
 * Cobertura: 401 (sem auth), 404 (sem condominio ou sem brand voice cadastrado), 200 (ok).
 *
 * Reflete o submodulo backend modules/marketing/brand_voice/.
 */
import { useQuery } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';

// ==================================================================
// Tipos (espelham os schemas Pydantic)
// ==================================================================

export interface PersonalityTrait {
  label: string;
  description: string;
}

export interface ToneRule {
  title: string;
  description: string;
}

export interface BrandVoice {
  id: string;
  condominio_id: string;
  personality: PersonalityTrait[];
  tone_of_voice: ToneRule[];
  keywords: string[];
  avoid_list: string[];
  slogan: string | null;
  updated_by_user_id: string | null;
  created_at: string;
  updated_at: string;
}

// ==================================================================
// Query keys
// ==================================================================

export const brandVoiceKeys = {
  all: ['brand-voice'] as const,
  current: () => [...brandVoiceKeys.all, 'current'] as const,
};

// ==================================================================
// Queries
// ==================================================================

/**
 * Busca o brand voice do condominio do usuario logado.
 *
 * - Cache 10min (brand voice muda raramente)
 * - NAO retry em 401 ou 404 (sao casos esperados — auth perdida ou nao cadastrado)
 * - Em 404, o componente cai pro FALLBACK_BRAND_VOICE pra nao quebrar UX
 */
export function useBrandVoice() {
  return useQuery({
    queryKey: brandVoiceKeys.current(),
    queryFn: () =>
      customInstance<BrandVoice>({
        url: '/api/v1/marketing/brand-voice/',
        method: 'GET',
      }),
    staleTime: 1000 * 60 * 10,
    retry: (failureCount, error: unknown) => {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 404 || status === 401) return false;
      return failureCount < 2;
    },
  });
}

// ==================================================================
// Fallback estatico (matches frontend/.../brand-voice/page.tsx original)
// Usado quando API retorna 404 (brand voice ainda nao cadastrado) ou
// quando o backend ainda nao foi deployado.
// ==================================================================

export const FALLBACK_BRAND_VOICE: Omit<BrandVoice, 'id' | 'condominio_id' | 'updated_by_user_id' | 'created_at' | 'updated_at'> = {
  personality: [
    { label: 'Profissional', description: 'Transmitimos expertise em segurança patrimonial' },
    { label: 'Confiável', description: 'Dados e resultados comprovados, não promessas' },
    { label: 'Tecnológico', description: 'Inovação com portaria remota e monitoramento inteligente' },
    { label: 'Próximo', description: 'Atendimento humanizado, acessível e transparente' },
  ],
  tone_of_voice: [
    { title: 'Formal mas acessível', description: 'sem jargões excessivos' },
    { title: 'Direto e objetivo', description: 'o síndico não tem tempo' },
    { title: 'Orientado a solução', description: '"como resolver" não "o que vender"' },
    { title: 'Empático', description: 'entendemos as dores do gestor condominial' },
  ],
  keywords: [
    'segurança',
    'tranquilidade',
    'tecnologia',
    'economia',
    'eficiência',
    'monitoramento 24h',
    'portaria inteligente',
    'patrimônio protegido',
    'gestão profissional',
    'Manaus',
  ],
  avoid_list: [
    'Linguagem agressiva ou alarmista',
    'Promessas de "segurança 100%"',
    'Comparação direta com concorrentes',
    'Termos técnicos sem explicação',
    'Informalidade excessiva (gírias, emojis demais)',
  ],
  slogan: 'Conecta Mais — Segurança inteligente para quem valoriza o patrimônio',
};
