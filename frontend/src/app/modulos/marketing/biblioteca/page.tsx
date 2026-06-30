'use client';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { customInstance } from '@/lib/api-client';
import { Library, Copy, Check, Archive, Trash2, PenLine, RotateCcw, Pencil, Save, X, Send, Loader2 } from 'lucide-react';
import { useState } from 'react';
import Link from 'next/link';
import { toast } from 'sonner';

interface Item {
  id: string; formato: string; formato_label?: string; titulo?: string; conteudo: string;
  observacao?: string; briefing?: string; objetivo?: string; publico?: string; modelo?: string;
  status: string; created_at?: string;
}

const STATUS_TABS = [
  { id: 'aprovado', label: 'Aprovados' },
  { id: 'rascunho', label: 'Rascunhos' },
  { id: 'arquivado', label: 'Arquivados' },
];

const statusBadge: Record<string, string> = {
  aprovado: 'bg-green-100 text-green-700',
  rascunho: 'bg-amber-100 text-amber-700',
  arquivado: 'bg-gray-200 text-gray-600',
};

export default function BibliotecaPage() {
  const qc = useQueryClient();
  const [tab, setTab] = useState('aprovado');
  const [copiado, setCopiado] = useState<string | null>(null);
  const [editando, setEditando] = useState<string | null>(null);
  const [rascunhoEdit, setRascunhoEdit] = useState('');
  const [enviando, setEnviando] = useState<string | null>(null);
  const [numeroEnvio, setNumeroEnvio] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['mkt-content', tab],
    queryFn: () => customInstance({ url: `/api/v1/marketing/content/?status=${tab}`, method: 'GET' }),
    staleTime: 15_000,
  });
  const itens: Item[] = (data as any)?.items || [];

  const mudarStatus = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      customInstance({ url: `/api/v1/marketing/content/${id}/status`, method: 'PATCH', data: { status } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['mkt-content'] }); toast.success('Atualizado'); },
    onError: () => toast.error('Erro ao atualizar'),
  });

  const excluir = useMutation({
    mutationFn: (id: string) => customInstance({ url: `/api/v1/marketing/content/${id}`, method: 'DELETE' }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['mkt-content'] }); toast.success('Excluído'); },
    onError: () => toast.error('Erro ao excluir'),
  });

  const salvarEdicao = useMutation({
    mutationFn: ({ id, conteudo }: { id: string; conteudo: string }) =>
      customInstance({ url: `/api/v1/marketing/content/${id}`, method: 'PATCH', data: { conteudo } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['mkt-content'] }); setEditando(null); toast.success('Salvo'); },
    onError: () => toast.error('Erro ao salvar edição'),
  });

  const abrirEdicao = (item: Item) => { setEditando(item.id); setRascunhoEdit(item.conteudo); };

  const enviarWhatsapp = useMutation({
    mutationFn: ({ id, numero }: { id: string; numero: string }) =>
      customInstance({ url: `/api/v1/marketing/content/${id}/send-whatsapp`, method: 'POST', data: { numero } }),
    onSuccess: (r: any) => { setEnviando(null); setNumeroEnvio(''); toast.success(`Enviado pro WhatsApp ${r.numero}`); },
    onError: () => toast.error('Falha ao enviar pelo WhatsApp. Confira o número (DDI+DDD).'),
  });

  const copiar = (texto: string, id: string) => {
    navigator.clipboard.writeText(texto);
    setCopiado(id); toast.success('Copiado!');
    setTimeout(() => setCopiado(null), 1500);
  };

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold flex items-center gap-2"><Library className="h-6 w-6" />Biblioteca de Conteúdo</h1>
          <p className="text-gray-500">Peças aprovadas pelo agente Copywriter, prontas para reuso.</p>
        </div>
        <Link href="/modulos/marketing/copywriter" className="shrink-0 flex items-center gap-1.5 text-sm bg-cyan-600 text-white rounded-lg px-3 py-2 hover:bg-cyan-700">
          <PenLine className="h-4 w-4" />Gerar conteúdo
        </Link>
      </div>

      <div className="flex gap-2 border-b">
        {STATUS_TABS.map(t => (
          <button key={t.id} onClick={() => setTab(t.id)}
            className={`px-4 py-2 text-sm font-medium border-b-2 -mb-px ${tab === t.id ? 'border-cyan-600 text-cyan-700' : 'border-transparent text-gray-500 hover:text-gray-700'}`}>
            {t.label}
          </button>
        ))}
      </div>

      {isLoading && <p className="text-sm text-gray-400">Carregando...</p>}
      {!isLoading && itens.length === 0 && (
        <div className="bg-gray-50 rounded-xl border border-dashed p-10 text-center text-gray-400 text-sm">
          Nenhuma peça aqui ainda. Gere conteúdo no <b>Copywriter IA</b> e clique em "Aprovar e salvar".
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {itens.map(item => (
          <div key={item.id} className="bg-white rounded-xl border p-4 flex flex-col">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center gap-2">
                <span className="text-xs bg-cyan-50 text-cyan-700 px-2 py-0.5 rounded-full">{item.formato_label || item.formato}</span>
                <span className={`text-xs px-2 py-0.5 rounded-full ${statusBadge[item.status] || ''}`}>{item.status}</span>
              </div>
            </div>
            {item.titulo && <h3 className="font-semibold text-sm text-gray-800 mb-1">{item.titulo}</h3>}
            {editando === item.id ? (
              <textarea className="w-full border rounded-lg p-2 text-sm flex-1 min-h-[140px]" value={rascunhoEdit} onChange={e => setRascunhoEdit(e.target.value)} />
            ) : (
              <pre className="whitespace-pre-wrap font-sans text-sm text-gray-700 flex-1">{item.conteudo}</pre>
            )}
            {item.briefing && <p className="text-xs text-gray-400 mt-2 border-t pt-2">Briefing: {item.briefing}</p>}
            <div className="flex items-center gap-3 mt-3 pt-2 border-t text-xs">
              {editando === item.id ? (
                <>
                  <button onClick={() => salvarEdicao.mutate({ id: item.id, conteudo: rascunhoEdit })} disabled={!rascunhoEdit.trim() || salvarEdicao.isPending} className="flex items-center gap-1 text-green-600 hover:text-green-700 disabled:opacity-50">
                    <Save className="h-3.5 w-3.5" />Salvar
                  </button>
                  <button onClick={() => setEditando(null)} className="flex items-center gap-1 text-gray-500 hover:text-gray-700">
                    <X className="h-3.5 w-3.5" />Cancelar
                  </button>
                </>
              ) : (
                <>
              <button onClick={() => copiar(item.conteudo, item.id)} className="flex items-center gap-1 text-gray-500 hover:text-cyan-600">
                {copiado === item.id ? <><Check className="h-3.5 w-3.5" />Copiado</> : <><Copy className="h-3.5 w-3.5" />Copiar</>}
              </button>
              <button onClick={() => abrirEdicao(item)} className="flex items-center gap-1 text-gray-500 hover:text-cyan-600">
                <Pencil className="h-3.5 w-3.5" />Editar
              </button>
              <button onClick={() => { setEnviando(enviando === item.id ? null : item.id); setNumeroEnvio(''); }} className="flex items-center gap-1 text-gray-500 hover:text-green-600">
                <Send className="h-3.5 w-3.5" />WhatsApp
              </button>
              {item.status !== 'arquivado' ? (
                <button onClick={() => mudarStatus.mutate({ id: item.id, status: 'arquivado' })} className="flex items-center gap-1 text-gray-500 hover:text-amber-600">
                  <Archive className="h-3.5 w-3.5" />Arquivar
                </button>
              ) : (
                <button onClick={() => mudarStatus.mutate({ id: item.id, status: 'aprovado' })} className="flex items-center gap-1 text-gray-500 hover:text-green-600">
                  <RotateCcw className="h-3.5 w-3.5" />Restaurar
                </button>
              )}
              <button onClick={() => { if (confirm('Excluir esta peça?')) excluir.mutate(item.id); }} className="flex items-center gap-1 text-gray-500 hover:text-red-600 ml-auto">
                <Trash2 className="h-3.5 w-3.5" />Excluir
              </button>
                </>
              )}
            </div>
            {enviando === item.id && editando !== item.id && (
              <div className="flex items-center gap-2 mt-2 pt-2 border-t">
                <input className="flex-1 border rounded-lg p-1.5 text-xs" placeholder="Número com DDI+DDD (ex: 5592986465328)"
                  value={numeroEnvio} onChange={e => setNumeroEnvio(e.target.value)} />
                <button onClick={() => enviarWhatsapp.mutate({ id: item.id, numero: numeroEnvio })}
                  disabled={numeroEnvio.replace(/\D/g, '').length < 10 || enviarWhatsapp.isPending}
                  className="text-xs flex items-center gap-1 bg-green-600 text-white rounded-lg px-3 py-1.5 disabled:opacity-50">
                  {enviarWhatsapp.isPending ? <><Loader2 className="h-3.5 w-3.5 animate-spin" />Enviando</> : <><Send className="h-3.5 w-3.5" />Enviar</>}
                </button>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
