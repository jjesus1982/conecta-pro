'use client';
import { useQuery, useMutation } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { PenLine, Sparkles, Copy, Check, Loader2, BookmarkPlus, Library } from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';
import { PageHeader } from '@/components/ui/page-header';

interface Variacao { titulo: string; conteudo: string; observacao?: string; }
interface GenResult { variacoes: Variacao[]; modelo?: string; fallback?: boolean; formato_label?: string; status?: string; }

export default function CopywriterPage() {
  const [formato, setFormato] = useState('instagram_post');
  const [briefing, setBriefing] = useState('');
  const [objetivo, setObjetivo] = useState('');
  const [publico, setPublico] = useState('');
  const [nVariacoes, setNVariacoes] = useState(3);
  const [resultado, setResultado] = useState<GenResult | null>(null);
  const [copiado, setCopiado] = useState<number | null>(null);
  const [salvos, setSalvos] = useState<Record<number, boolean>>({});

  const { data: formatosData } = useQuery({
    queryKey: ['copywriter-formats'],
    queryFn: () => customInstance({ url: '/api/v1/marketing/copywriter/formats', method: 'GET' }),
    staleTime: 300_000,
  });
  const formatos = (formatosData as any)?.formatos || [];

  const gerar = useMutation({
    mutationFn: () => customInstance({
      url: '/api/v1/marketing/copywriter/generate',
      method: 'POST',
      data: { formato, briefing, objetivo: objetivo || null, publico: publico || null, n_variacoes: nVariacoes },
    }),
    onSuccess: (data: any) => {
      setResultado(data);
      toast.success(`${data.variacoes?.length || 0} rascunho(s) gerado(s) — revise e aprove`);
    },
    onError: () => toast.error('Erro ao gerar conteúdo. Tente novamente.'),
  });

  const salvar = useMutation({
    mutationFn: (v: Variacao) => customInstance({
      url: '/api/v1/marketing/content/',
      method: 'POST',
      data: {
        formato, formato_label: resultado?.formato_label, titulo: v.titulo, conteudo: v.conteudo,
        observacao: v.observacao || null, briefing, objetivo: objetivo || null, publico: publico || null,
        modelo: resultado?.modelo || null, status: 'aprovado',
      },
    }),
  });

  const aprovarESalvar = (v: Variacao, i: number) => {
    salvar.mutate(v, {
      onSuccess: () => { setSalvos(s => ({ ...s, [i]: true })); toast.success('Salvo na biblioteca (aprovado)'); },
      onError: () => toast.error('Erro ao salvar na biblioteca'),
    });
  };

  const copiar = (texto: string, i: number) => {
    navigator.clipboard.writeText(texto);
    setCopiado(i);
    toast.success('Copiado!');
    setTimeout(() => setCopiado(null), 1500);
  };

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <PageHeader
        eyebrow="MARKETING"
        title="Copywriter IA"
        subtitle="Gera conteúdo na voz da marca Conecta Mais. Você revisa e aprova — nada é publicado automaticamente."
        icon={<PenLine className="h-5 w-5" />}
        actions={
          <Link href="/modulos/marketing/biblioteca" className="shrink-0 flex items-center gap-1.5 text-sm border rounded-lg px-3 py-2 hover:bg-gray-50">
            <Library className="h-4 w-4" />Biblioteca
          </Link>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Formulário */}
        <div className="lg:col-span-2 bg-white rounded-xl border p-5 space-y-4 h-fit">
          <div>
            <label className="text-sm font-medium block mb-1">Formato</label>
            <select className="w-full border rounded-lg p-2 text-sm" value={formato} onChange={e => setFormato(e.target.value)}>
              {formatos.map((f: any) => <option key={f.id} value={f.id}>{f.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-sm font-medium block mb-1">Briefing <span className="text-red-500">*</span></label>
            <textarea className="w-full border rounded-lg p-2 text-sm h-28" placeholder="Sobre o que é a peça? Ex: portaria remota para condomínios, benefícios, diferenciais..."
              value={briefing} onChange={e => setBriefing(e.target.value)} />
          </div>
          <div>
            <label className="text-sm font-medium block mb-1">Objetivo</label>
            <input className="w-full border rounded-lg p-2 text-sm" placeholder="Ex: gerar leads no WhatsApp" value={objetivo} onChange={e => setObjetivo(e.target.value)} />
          </div>
          <div>
            <label className="text-sm font-medium block mb-1">Público-alvo</label>
            <input className="w-full border rounded-lg p-2 text-sm" placeholder="Ex: síndicos de condomínios de médio porte" value={publico} onChange={e => setPublico(e.target.value)} />
          </div>
          <div>
            <label className="text-sm font-medium block mb-1">Variações: {nVariacoes}</label>
            <input type="range" min={1} max={5} value={nVariacoes} onChange={e => setNVariacoes(Number(e.target.value))} className="w-full" />
          </div>
          <button
            disabled={!briefing.trim() || gerar.isPending}
            onClick={() => gerar.mutate()}
            className="w-full bg-cyan-600 hover:bg-cyan-700 disabled:opacity-50 text-white rounded-lg p-2.5 text-sm font-medium flex items-center justify-center gap-2">
            {gerar.isPending ? <><Loader2 className="h-4 w-4 animate-spin" />Gerando...</> : <><Sparkles className="h-4 w-4" />Gerar conteúdo</>}
          </button>
        </div>

        {/* Resultados */}
        <div className="lg:col-span-3 space-y-4">
          {!resultado && !gerar.isPending && (
            <div className="bg-gray-50 rounded-xl border border-dashed p-10 text-center text-gray-400 text-sm">
              Preencha o briefing e clique em <b>Gerar conteúdo</b>. As variações aparecem aqui para você revisar e aprovar.
            </div>
          )}
          {resultado && (
            <>
              <div className="flex items-center gap-2 text-xs text-gray-500">
                <span className="bg-amber-100 text-amber-700 px-2 py-0.5 rounded-full font-medium">RASCUNHO — aguardando sua aprovação</span>
                {resultado.modelo && <span>· {resultado.fallback ? 'fallback local' : resultado.modelo}</span>}
              </div>
              {resultado.variacoes.map((v, i) => (
                <div key={i} className="bg-white rounded-xl border p-4">
                  <div className="flex items-center justify-between mb-2">
                    <h3 className="font-semibold text-sm text-cyan-700">{v.titulo}</h3>
                    <div className="flex items-center gap-3">
                      <button onClick={() => copiar(v.conteudo, i)} className="text-xs flex items-center gap-1 text-gray-500 hover:text-cyan-600">
                        {copiado === i ? <><Check className="h-3.5 w-3.5" />Copiado</> : <><Copy className="h-3.5 w-3.5" />Copiar</>}
                      </button>
                      <button onClick={() => aprovarESalvar(v, i)} disabled={salvos[i] || salvar.isPending}
                        className="text-xs flex items-center gap-1 text-gray-500 hover:text-green-600 disabled:text-green-600 disabled:opacity-100">
                        {salvos[i] ? <><Check className="h-3.5 w-3.5" />Salvo</> : <><BookmarkPlus className="h-3.5 w-3.5" />Aprovar e salvar</>}
                      </button>
                    </div>
                  </div>
                  <pre className="whitespace-pre-wrap font-sans text-sm text-gray-800">{v.conteudo}</pre>
                  {v.observacao && <p className="text-xs text-gray-400 mt-2 border-t pt-2">💡 {v.observacao}</p>}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
