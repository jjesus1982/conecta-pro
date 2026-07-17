'use client';

/**
 * Painel de HOMOLOGAÇÃO — checklist por testador (dados eSocial, facial, ponto, escala).
 * Lê /people-management/portal/homologacao/painel. Base isolada (is_homologacao).
 */
import { useEffect, useState } from 'react';
import { api } from '@/lib/api';
import { CheckCircle2, XCircle, Loader2, Users } from 'lucide-react';

interface Testador {
  employee_id: string; nome: string; matricula: string; cargo: string;
  escala: string; turno: string; facial_cadastrada: boolean;
  batidas: number; turnos: number; dados_ok: number; dados_total: number; bateu_ponto: boolean;
}
interface Painel {
  total_testadores: number; com_facial: number; bateram_ponto: number; testadores: Testador[];
}

const Sim = () => <CheckCircle2 className="w-4 h-4 text-emerald-500 inline" />;
const Nao = () => <XCircle className="w-4 h-4 text-gray-300 inline" />;

export default function PainelHomologacao() {
  const [d, setD] = useState<Painel | null>(null);
  const [loading, setLoading] = useState(true);
  const [erro, setErro] = useState('');

  useEffect(() => {
    api.get('/api/v1/people-management/portal/homologacao/painel')
      .then((r) => setD(r.data))
      .catch(() => setErro('Não foi possível carregar o painel.'))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div className="p-8 text-center"><Loader2 className="w-6 h-6 animate-spin mx-auto text-[#F97316]" /></div>;
  if (erro) return <div className="p-6 text-red-600">{erro}</div>;

  return (
    <div className="p-4 max-w-4xl mx-auto">
      <div className="flex items-center gap-2 mb-1">
        <Users className="w-6 h-6 text-[#F97316]" />
        <h1 className="text-xl font-bold">Homologação — Conecta Base</h1>
      </div>
      <p className="text-sm text-gray-500 mb-4">
        {d?.total_testadores || 0} testadores · {d?.com_facial || 0} com rosto cadastrado · {d?.bateram_ponto || 0} bateram ponto
      </p>

      <div className="overflow-x-auto rounded-xl border border-gray-200 dark:border-gray-700">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 dark:bg-gray-800 text-left text-xs uppercase text-gray-500">
            <tr>
              <th className="px-3 py-2">Testador</th>
              <th className="px-3 py-2">Escala</th>
              <th className="px-3 py-2 text-center">Dados eSocial</th>
              <th className="px-3 py-2 text-center">Rosto</th>
              <th className="px-3 py-2 text-center">Ponto</th>
              <th className="px-3 py-2 text-center">Turnos</th>
            </tr>
          </thead>
          <tbody>
            {(d?.testadores || []).map((t) => (
              <tr key={t.employee_id} className="border-t border-gray-100 dark:border-gray-800">
                <td className="px-3 py-2">
                  <div className="font-medium">{t.nome}</div>
                  <div className="text-xs text-gray-400">{t.matricula} · {t.cargo}</div>
                </td>
                <td className="px-3 py-2 text-xs">{t.escala} · {t.turno}</td>
                <td className="px-3 py-2 text-center">
                  <span className={t.dados_ok >= t.dados_total ? 'text-emerald-600' : 'text-amber-600'}>
                    {t.dados_ok}/{t.dados_total}
                  </span>
                </td>
                <td className="px-3 py-2 text-center">{t.facial_cadastrada ? <Sim /> : <Nao />}</td>
                <td className="px-3 py-2 text-center">{t.bateu_ponto ? <><Sim /> <span className="text-xs text-gray-400">({t.batidas})</span></> : <Nao />}</td>
                <td className="px-3 py-2 text-center text-xs">{t.turnos}</td>
              </tr>
            ))}
            {(!d?.testadores || d.testadores.length === 0) && (
              <tr><td colSpan={6} className="px-3 py-6 text-center text-gray-400">Nenhum testador cadastrado ainda.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
