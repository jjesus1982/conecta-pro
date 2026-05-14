'use client';
import { Volume2, MessageCircle, Target, Heart } from 'lucide-react';
import { useBrandVoice, FALLBACK_BRAND_VOICE } from '@/hooks/marketing';

export default function BrandVoicePage() {
  const { data, isLoading, isError } = useBrandVoice();

  // Loading skeleton enquanto fetch nao retornou
  if (isLoading) {
    return (
      <div className="p-6 space-y-6 max-w-4xl mx-auto">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2">
            <Volume2 className="h-6 w-6" />Brand Voice — Conecta Mais
          </h1>
          <p className="text-gray-500">Carregando diretrizes...</p>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {[0, 1, 2, 3].map(i => (
            <div key={i} className="bg-white rounded-xl border p-6 animate-pulse">
              <div className="h-6 bg-gray-200 rounded w-1/3 mb-4" />
              <div className="space-y-2">
                <div className="h-4 bg-gray-200 rounded" />
                <div className="h-4 bg-gray-200 rounded w-5/6" />
                <div className="h-4 bg-gray-200 rounded w-4/6" />
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  // API falhou (404 = brand voice nao cadastrado, 401 = sem auth, network, etc) →
  // cai no FALLBACK_BRAND_VOICE pra UX nao quebrar.
  const brandVoice = data ?? FALLBACK_BRAND_VOICE;
  const isUsingFallback = !data && isError;

  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <Volume2 className="h-6 w-6" />Brand Voice — Conecta Mais
        </h1>
        <p className="text-gray-500">Tom de voz e diretrizes de comunicação da marca</p>
        {isUsingFallback && (
          <p className="text-xs text-amber-600 mt-1">
            ⓘ Conteúdo padrão (brand voice ainda não cadastrado no banco)
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Personalidade */}
        <div className="bg-white rounded-xl border p-6">
          <h2 className="font-semibold text-lg flex items-center gap-2 mb-4 text-gray-900">
            <Target className="h-5 w-5 text-cyan-600" />Personalidade
          </h2>
          <ul className="space-y-2 text-sm text-gray-700">
            {brandVoice.personality.map(trait => (
              <li key={trait.label} className="flex gap-2">
                <span className="font-medium text-cyan-600">{trait.label}:</span>
                <span>{trait.description}</span>
              </li>
            ))}
          </ul>
        </div>

        {/* Tom de Voz */}
        <div className="bg-white rounded-xl border p-6">
          <h2 className="font-semibold text-lg flex items-center gap-2 mb-4 text-gray-900">
            <MessageCircle className="h-5 w-5 text-green-600" />Tom de Voz
          </h2>
          <ul className="space-y-2 text-sm text-gray-700">
            {brandVoice.tone_of_voice.map(rule => (
              <li key={rule.title}>
                <span className="font-medium">{rule.title}</span>
                {rule.description && <> — {rule.description}</>}
              </li>
            ))}
          </ul>
        </div>

        {/* Palavras-chave */}
        <div className="bg-white rounded-xl border p-6">
          <h2 className="font-semibold text-lg mb-4 text-gray-900">Palavras-chave da Marca</h2>
          <div className="flex flex-wrap gap-2">
            {brandVoice.keywords.map(w => (
              <span
                key={w}
                className="bg-cyan-50 text-cyan-700 px-3 py-1 rounded-full text-sm"
              >
                {w}
              </span>
            ))}
          </div>
        </div>

        {/* Evitar */}
        <div className="bg-white rounded-xl border p-6">
          <h2 className="font-semibold text-lg flex items-center gap-2 mb-4 text-gray-900">
            <Heart className="h-5 w-5 text-red-500" />Evitar
          </h2>
          <ul className="space-y-2 text-sm text-gray-600">
            {brandVoice.avoid_list.map(item => (
              <li key={item}>❌ {item}</li>
            ))}
          </ul>
        </div>
      </div>

      {/* Slogan */}
      {brandVoice.slogan && (
        <div className="bg-gradient-to-r from-cyan-600 to-blue-600 rounded-xl p-6 text-white">
          <h2 className="font-semibold text-lg mb-2">Slogan</h2>
          <p className="text-2xl font-bold">&quot;{brandVoice.slogan}&quot;</p>
        </div>
      )}
    </div>
  );
}
