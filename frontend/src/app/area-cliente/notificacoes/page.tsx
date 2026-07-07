'use client';

import { useEffect, useState } from 'react';
import { Bell, Loader2, CheckCheck, Calendar, UserMinus, AlertTriangle, FileText, ShieldCheck } from 'lucide-react';
import { avisos, type Aviso } from '@/services/portal/portalApi';

const ICON: Record<string, typeof Bell> = {
  escala: Calendar, falta: UserMinus, advertencia: AlertTriangle, kit: FileText, certidao: ShieldCheck, aviso: Bell,
};

export default function NotificacoesPage() {
  const [loading, setLoading] = useState(true);
  const [lista, setLista] = useState<Aviso[]>([]);

  const carregar = async () => {
    try { setLista((await avisos.listar()).avisos); } catch { /* 401 */ } finally { setLoading(false); }
  };
  useEffect(() => { carregar(); }, []);

  const marcar = async (a: Aviso) => {
    if (a.lida) return;
    try { await avisos.marcarLida(a.id); setLista((l) => l.map((x) => x.id === a.id ? { ...x, lida: true } : x)); } catch { /* ignore */ }
  };

  if (loading) return <div className="flex items-center justify-center h-96 text-gray-500"><Loader2 className="w-6 h-6 animate-spin mr-2" /> Carregando avisos…</div>;

  return (
    <div className="space-y-6 max-w-3xl">
      <div>
        <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))] flex items-center gap-2"><Bell className="w-7 h-7 text-indigo-600" /> Notificações</h1>
        <p className="text-sm text-gray-500 mt-1">Avisos da Conecta Mais sobre sua operação — escala, faltas, documentos e mais.</p>
      </div>

      {lista.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-10 text-center">
          <CheckCheck className="w-10 h-10 text-emerald-500 mx-auto mb-3" />
          <p className="text-gray-700 font-medium">Tudo em dia!</p>
          <p className="text-sm text-gray-400 mt-1">Você não tem avisos no momento.</p>
        </div>
      ) : (
        <div className="space-y-2">
          {lista.map((a) => {
            const Icon = ICON[a.tipo] || Bell;
            return (
              <button key={a.id} onClick={() => marcar(a)}
                className={`w-full text-left flex gap-3 p-4 rounded-xl border transition ${a.lida ? 'bg-white border-gray-200' : 'bg-indigo-50 border-indigo-200'}`}>
                <span className={`w-10 h-10 rounded-lg flex items-center justify-center shrink-0 ${a.lida ? 'bg-gray-100 text-gray-400' : 'bg-indigo-600 text-white'}`}><Icon className="w-5 h-5" /></span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className={`text-sm ${a.lida ? 'font-medium text-gray-700' : 'font-semibold text-gray-900'}`}>{a.titulo}</p>
                    {!a.lida && <span className="w-2 h-2 rounded-full bg-indigo-600 shrink-0" />}
                  </div>
                  <p className="text-sm text-gray-600 mt-0.5 whitespace-pre-line">{a.mensagem}</p>
                  {a.criado_em && <p className="text-xs text-gray-400 mt-1">{new Date(a.criado_em).toLocaleString('pt-BR')}</p>}
                </div>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}
