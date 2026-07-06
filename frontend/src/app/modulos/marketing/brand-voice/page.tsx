'use client';
import { Volume2, MessageCircle, Target, Heart, XCircle } from 'lucide-react';
import { PageHeader } from '@/components/ui/page-header';

export default function BrandVoicePage() {
  return (
    <div className="p-6 space-y-6 max-w-4xl mx-auto">
      <PageHeader
        eyebrow="MARKETING"
        title="Brand Voice — Conecta Mais"
        subtitle="Tom de voz e diretrizes de comunicação da marca"
        icon={<Volume2 className="h-5 w-5" />}
      />

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-xl border p-6">
          <h2 className="font-display text-lg flex items-center gap-2 mb-4"><Target className="h-5 w-5 text-cyan-600" />Personalidade</h2>
          <ul className="space-y-2 text-sm">
            <li className="flex gap-2"><span className="font-medium text-cyan-600">Profissional:</span> Transmitimos expertise em segurança patrimonial</li>
            <li className="flex gap-2"><span className="font-medium text-cyan-600">Confiável:</span> Dados e resultados comprovados, não promessas</li>
            <li className="flex gap-2"><span className="font-medium text-cyan-600">Tecnológico:</span> Inovação com portaria remota e monitoramento inteligente</li>
            <li className="flex gap-2"><span className="font-medium text-cyan-600">Próximo:</span> Atendimento humanizado, acessível e transparente</li>
          </ul>
        </div>

        <div className="bg-white rounded-xl border p-6">
          <h2 className="font-display text-lg flex items-center gap-2 mb-4"><MessageCircle className="h-5 w-5 text-green-600" />Tom de Voz</h2>
          <ul className="space-y-2 text-sm">
            <li><span className="font-medium">Formal mas acessível</span> — sem jargões excessivos</li>
            <li><span className="font-medium">Direto e objetivo</span> — o síndico não tem tempo</li>
            <li><span className="font-medium">Orientado a solução</span> — "como resolver" não "o que vender"</li>
            <li><span className="font-medium">Empático</span> — entendemos as dores do gestor condominial</li>
          </ul>
        </div>

        <div className="bg-white rounded-xl border p-6">
          <h2 className="font-display text-lg mb-4">Palavras-chave da Marca</h2>
          <div className="flex flex-wrap gap-2">
            {['segurança', 'tranquilidade', 'tecnologia', 'economia', 'eficiência', 'monitoramento 24h', 'portaria inteligente', 'patrimônio protegido', 'gestão profissional', 'Manaus'].map(w => (
              <span key={w} className="bg-cyan-50 text-cyan-700 px-3 py-1 rounded-full text-sm">{w}</span>
            ))}
          </div>
        </div>

        <div className="bg-white rounded-xl border p-6">
          <h2 className="font-display text-lg flex items-center gap-2 mb-4"><Heart className="h-5 w-5 text-red-500" />Evitar</h2>
          <ul className="space-y-2 text-sm text-gray-600">
            <li className="flex items-start gap-2"><XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />Linguagem agressiva ou alarmista</li>
            <li className="flex items-start gap-2"><XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />Promessas de "segurança 100%"</li>
            <li className="flex items-start gap-2"><XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />Comparação direta com concorrentes</li>
            <li className="flex items-start gap-2"><XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />Termos técnicos sem explicação</li>
            <li className="flex items-start gap-2"><XCircle className="h-4 w-4 text-red-500 shrink-0 mt-0.5" />Informalidade excessiva (gírias, emojis demais)</li>
          </ul>
        </div>
      </div>

      <div className="bg-gradient-to-r from-cyan-600 to-blue-600 rounded-xl p-6 text-white">
        <h2 className="font-display text-lg mb-2">Slogan</h2>
        <p className="font-display text-2xl">"Conecta Mais — Segurança inteligente para quem valoriza o patrimônio"</p>
      </div>
    </div>
  );
}
