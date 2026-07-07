'use client';

import { useState, useEffect } from 'react';
import {
  AlertTriangle, TrendingUp, Users, Scale, Landmark, Loader2, Info,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';

const API_BASE = '/api/v1/juridico/riscos';

function getAuthHeaders() {
  const token = typeof window !== 'undefined' ? (localStorage.getItem('access_token') || localStorage.getItem('token')) : null;
  return { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) };
}
const fmt = (v: number | null | undefined) => (v == null ? '—' : `R$ ${(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}`);
const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v || 0).toLocaleString('pt-BR', { minimumFractionDigits: 2 })}%`);

const sevBadge = (nivel: string) => {
  const n = (nivel || '').toLowerCase();
  if (n === 'alto') return <Badge className="bg-red-600 text-white">alto</Badge>;
  if (n === 'atencao' || n === 'atenção') return <Badge className="bg-yellow-500 text-white">atenção</Badge>;
  if (n === 'baixo') return <Badge className="bg-green-500 text-white">baixo</Badge>;
  return <Badge variant="outline">{nivel || '—'}</Badge>;
};

const TIPO_LABEL: Record<string, string> = {
  diferenca_piso_retroativa: 'Diferença de piso (retroativa)',
  fgts_multa_40: 'FGTS + multa 40%',
  aviso_previo: 'Aviso prévio',
  ferias_prop_mais_terco: 'Férias prop. + 1/3',
  decimo_terceiro_prop: '13º proporcional',
  horas_extras_noturno: 'Horas extras / noturno',
  adicionais_risco: 'Adicionais de risco',
};

export default function RiscosJuridicosPage() {
  const [dash, setDash] = useState<any>(null);
  const [trab, setTrab] = useState<any>(null);
  const [trib, setTrib] = useState<any>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    (async () => {
      try {
        const get = (p: string) => fetch(`${API_BASE}${p}`, { headers: getAuthHeaders() }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
        const [d, tr, tb] = await Promise.all([get('/dashboard'), get('/trabalhista'), get('/tributario')]);
        setDash(d);
        setTrab(tr);
        setTrib(tb);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  if (loading) return <div className="flex items-center justify-center h-64"><Loader2 className="h-6 w-6 animate-spin" /></div>;

  const detalhado: any[] = trab?.detalhado || [];
  const porTipo: Record<string, number> = trab?.por_tipo || {};
  const enq = trib?.enquadramento || {};
  const comp = trib?.comparativo_carga || {};
  const ret = trib?.retencoes_aplicaveis || {};
  const riscosTrib: any[] = trib?.riscos || [];

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <AlertTriangle className="h-7 w-7 text-red-600" />
        <div>
          <h1 className="font-display text-2xl font-bold text-[hsl(var(--foreground))]">Riscos Jurídicos</h1>
          <p className="text-sm text-muted-foreground">{dash?.titulo || 'Trabalhista + Tributário'}{dash?.referencia ? ` · referência ${dash.referencia}` : ''}</p>
        </div>
      </div>

      {dash?.escalonar_geral && (
        <div className="flex items-start gap-2 rounded-md border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-800">
          <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
          <span>Há riscos que recomendam análise/validação com jurídico e contador.</span>
        </div>
      )}

      {/* ================= TRABALHISTA ================= */}
      <section className="space-y-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-gray-800"><Scale className="h-5 w-5 text-blue-600" /> Trabalhista</h2>

        {!trab ? (
          <Card><CardContent className="py-6 text-center text-muted-foreground">Sem dados trabalhistas disponíveis.</CardContent></Card>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card><CardContent className="pt-6">
                <div className="text-xs text-muted-foreground">Exposição total estimada</div>
                <div className="font-data text-2xl font-semibold tabular-nums text-red-600 mt-1">{fmt(trab.total_exposicao_estimada)}</div>
              </CardContent></Card>
              <Card><CardContent className="pt-6">
                <Users className="h-5 w-5 text-blue-600" />
                <div className="font-data text-2xl font-semibold tabular-nums mt-2">{trab.funcionarios_com_risco ?? 0}</div>
                <div className="text-xs text-muted-foreground">Funcionários com risco</div>
              </CardContent></Card>
              <Card><CardContent className="pt-6">
                <div className="font-data text-2xl font-semibold tabular-nums mt-2">{trab.afastamentos_estabilidade ?? 0}</div>
                <div className="text-xs text-muted-foreground">Afastamentos c/ estabilidade</div>
              </CardContent></Card>
              <Card><CardContent className="pt-6">
                <div className="font-data text-2xl font-semibold tabular-nums mt-2">{trab.afastamentos_acidentarios ?? 0}</div>
                <div className="text-xs text-muted-foreground">Afastamentos acidentários</div>
              </CardContent></Card>
            </div>

            {/* Por tipo de verba */}
            {Object.keys(porTipo).length > 0 && (
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-base">Exposição por tipo de verba</CardTitle></CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 text-sm">
                    {Object.entries(porTipo).map(([k, v]) => (
                      <div key={k} className="flex justify-between border rounded-md px-3 py-2">
                        <span className="text-muted-foreground">{TIPO_LABEL[k] || k}</span>
                        <span className="font-semibold">{fmt(v)}</span>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Tabela por funcionário */}
            <Card>
              <CardHeader className="pb-2"><CardTitle className="text-base">Exposição por funcionário ({detalhado.length})</CardTitle></CardHeader>
              <CardContent>
                {detalhado.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Sem registros.</p>
                ) : (
                  <Table>
                    <TableHeader>
                      <TableRow>
                        <TableHead>Funcionário</TableHead>
                        <TableHead>Cargo</TableHead>
                        <TableHead>Meses</TableHead>
                        <TableHead>Exposição estimada</TableHead>
                        <TableHead>Tipos</TableHead>
                      </TableRow>
                    </TableHeader>
                    <TableBody>
                      {detalhado.map((f: any) => {
                        const tipos = Object.entries(f.verbas || {})
                          .filter(([, val]: any) => val && (val.valor ?? 0) > 0)
                          .map(([k]) => k);
                        return (
                          <TableRow key={f.employee_id}>
                            <TableCell className="font-medium">{f.nome}</TableCell>
                            <TableCell className="text-sm">{f.cargo || '—'}</TableCell>
                            <TableCell className="text-sm">{f.meses_de_casa ?? '—'}</TableCell>
                            <TableCell className="font-semibold text-red-600">{fmt(f.exposicao_estimada)}</TableCell>
                            <TableCell>
                              <div className="flex gap-1 flex-wrap">
                                {tipos.length === 0 ? <span className="text-xs text-muted-foreground">—</span> :
                                  tipos.map((t) => <Badge key={t} variant="outline" className="text-xs">{TIPO_LABEL[t] || t}</Badge>)}
                              </div>
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                )}
              </CardContent>
            </Card>

            {Array.isArray(trab.itens_requer_analise) && trab.itens_requer_analise.length > 0 && (
              <div className="text-xs text-muted-foreground border rounded-md px-3 py-2">
                <div className="font-medium mb-1 flex items-center gap-1"><Info className="h-3.5 w-3.5" /> Itens que requerem análise humana:</div>
                <ul className="list-disc list-inside space-y-0.5">
                  {trab.itens_requer_analise.map((it: string, i: number) => <li key={i}>{it}</li>)}
                </ul>
              </div>
            )}

            <p className="text-xs text-muted-foreground italic">{trab.rotulo || 'estimativa de exposição, não provisão contábil'}</p>
          </>
        )}
      </section>

      {/* ================= TRIBUTÁRIO ================= */}
      <section className="space-y-4">
        <h2 className="flex items-center gap-2 text-lg font-semibold text-gray-800"><Landmark className="h-5 w-5 text-emerald-600" /> Tributário</h2>

        {!trib ? (
          <Card><CardContent className="py-6 text-center text-muted-foreground">Sem dados tributários disponíveis.</CardContent></Card>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <Card><CardContent className="pt-6">
                <TrendingUp className="h-5 w-5 text-emerald-600" />
                <div className="text-xl font-bold mt-2">{fmt(enq.faturamento_anualizado)}</div>
                <div className="text-xs text-muted-foreground">Faturamento anualizado</div>
              </CardContent></Card>
              <Card><CardContent className="pt-6">
                <div className="font-data text-2xl font-semibold tabular-nums mt-2">{pct(enq.ocupacao_teto_pct)}</div>
                <div className="text-xs text-muted-foreground">Ocupação do teto Simples</div>
              </CardContent></Card>
              <Card><CardContent className="pt-6">
                <div className="text-xl font-bold mt-2">{fmt(enq.teto_simples_anual)}</div>
                <div className="text-xs text-muted-foreground">Teto Simples anual</div>
              </CardContent></Card>
              <Card><CardContent className="pt-6">
                <div className="text-xl font-bold mt-2">{fmt(enq.margem_ate_teto)}</div>
                <div className="text-xs text-muted-foreground">Margem até o teto</div>
                <div className="mt-1">{enq.pode_simples ? <Badge className="bg-green-500 text-white text-xs">pode Simples</Badge> : <Badge className="bg-red-500 text-white text-xs">excede teto</Badge>}</div>
              </CardContent></Card>
            </div>

            {/* Comparativo de carga */}
            {(comp.simples_anexo_iv || comp.lucro_real) && (
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-base">Comparativo de carga — Simples (Anexo IV) vs Lucro Real</CardTitle></CardHeader>
                <CardContent className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                  <div className="border rounded-md p-3">
                    <div className="font-semibold mb-1">Simples Nacional (Anexo IV)</div>
                    <div className="flex justify-between"><span className="text-muted-foreground">Alíquota ilustrativa</span><span>{pct(comp.simples_anexo_iv?.aliquota_ilustrativa_pct)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">Carga anual estimada</span><span className="font-semibold">{fmt(comp.simples_anexo_iv?.carga_anual_estimada)}</span></div>
                    {comp.simples_anexo_iv?.observacao && <div className="text-xs text-muted-foreground mt-2">{comp.simples_anexo_iv.observacao}</div>}
                  </div>
                  <div className="border rounded-md p-3">
                    <div className="font-semibold mb-1">Lucro Real</div>
                    <div className="flex justify-between"><span className="text-muted-foreground">PIS/COFINS (não cumul.)</span><span>{pct(comp.lucro_real?.pis_cofins_nao_cumulativo_pct)}</span></div>
                    <div className="flex justify-between"><span className="text-muted-foreground">PIS/COFINS anual est.</span><span className="font-semibold">{fmt(comp.lucro_real?.pis_cofins_anual_estimado)}</span></div>
                    {comp.lucro_real?.irpj_csll && <div className="text-xs text-muted-foreground mt-1">IRPJ/CSLL: {comp.lucro_real.irpj_csll}</div>}
                    {comp.lucro_real?.observacao && <div className="text-xs text-muted-foreground mt-2">{comp.lucro_real.observacao}</div>}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Retenções */}
            {Object.keys(ret).length > 0 && (
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-base">Retenções na fonte</CardTitle></CardHeader>
                <CardContent>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-sm">
                    {ret.iss && (
                      <div className="border rounded-md px-3 py-2">
                        <div className="font-medium">ISS</div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Contratos c/ retenção</span><span>{ret.iss.contratos_com_retencao ?? 0}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">ISS destacado NFS-e</span><span className="font-semibold">{fmt(ret.iss.iss_destacado_nfse)}</span></div>
                      </div>
                    )}
                    {ret.inss && (
                      <div className="border rounded-md px-3 py-2">
                        <div className="font-medium">INSS</div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Contratos c/ retenção</span><span>{ret.inss.contratos_com_retencao ?? 0}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">INSS retido NFS-e</span><span className="font-semibold">{fmt(ret.inss.inss_retido_nfse)}</span></div>
                      </div>
                    )}
                    {ret.csll && (
                      <div className="border rounded-md px-3 py-2">
                        <div className="font-medium">CSLL</div>
                        <div className="flex justify-between"><span className="text-muted-foreground">Contratos c/ retenção</span><span>{ret.csll.contratos_com_retencao ?? 0}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">CSLL retido NFS-e</span><span className="font-semibold">{fmt(ret.csll.csll_retido_nfse)}</span></div>
                      </div>
                    )}
                    {ret.pis_cofins && (
                      <div className="border rounded-md px-3 py-2">
                        <div className="font-medium">PIS/COFINS</div>
                        <div className="flex justify-between"><span className="text-muted-foreground">PIS retido NFS-e</span><span className="font-semibold">{fmt(ret.pis_cofins.pis_retido_nfse)}</span></div>
                        <div className="flex justify-between"><span className="text-muted-foreground">COFINS retido NFS-e</span><span className="font-semibold">{fmt(ret.pis_cofins.cofins_retido_nfse)}</span></div>
                      </div>
                    )}
                  </div>
                </CardContent>
              </Card>
            )}

            {/* Riscos tributários */}
            {riscosTrib.length > 0 && (
              <Card>
                <CardHeader className="pb-2"><CardTitle className="text-base">Riscos identificados ({riscosTrib.length})</CardTitle></CardHeader>
                <CardContent className="space-y-2">
                  {riscosTrib.map((r: any, i: number) => (
                    <div key={i} className="border rounded-md px-3 py-2">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-medium text-sm">{r.tema}</span>
                        {sevBadge(r.nivel)}
                      </div>
                      {r.descricao && <p className="text-xs text-muted-foreground mt-1">{r.descricao}</p>}
                    </div>
                  ))}
                </CardContent>
              </Card>
            )}

            <p className="text-xs text-muted-foreground italic">{trib.rotulo || 'estimativa p/ decisão, validar com contador'}</p>
          </>
        )}
      </section>

      {/* Disclaimer geral */}
      {(dash?.disclaimer || trab?.disclaimer || trib?.disclaimer) && (
        <div className="border-t pt-3 text-xs text-muted-foreground italic">
          {dash?.disclaimer || trab?.disclaimer || trib?.disclaimer}
        </div>
      )}
    </div>
  );
}
