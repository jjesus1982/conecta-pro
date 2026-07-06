'use client';

import { useState } from 'react';
import {
  FileText,
  Building2,
  Calculator,
  ChevronDown,
  ChevronUp,
  CheckCircle2,
  XCircle,
  AlertCircle,
  Send,
  Sparkles,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { PageHeader } from '@/components/ui/page-header';
import apiClient from '@/lib/api-client';

// ─── Types ───────────────────────────────────────────────────────────────────

interface TributosResult {
  valor_servico: number;
  pis: number;
  cofins: number;
  iss: number;
  inss_retido: boolean;
  valor_liquido: number;
}

interface NFSeMultiResult {
  sucesso: boolean;
  empresa_emissora: string;
  motivo_selecao_empresa: string;
  liminares_aplicadas: string[];
  tributos: TributosResult;
  xml_preview: string | null;
  xml_gerado?: string | null;
  mensagem: string;
  ambiente: string;
}

// ─── Constants ───────────────────────────────────────────────────────────────

const TIPOS_SERVICO = [
  { value: 'vigilancia', label: 'Vigilância Patrimonial', empresa: 'patrimonial' },
  { value: 'portaria_presencial', label: 'Portaria Presencial', empresa: 'patrimonial' },
  { value: 'portaria_24h', label: 'Portaria 24h', empresa: 'patrimonial' },
  { value: 'portaria_12x36', label: 'Portaria 12x36', empresa: 'patrimonial' },
  { value: 'limpeza', label: 'Limpeza e Conservação', empresa: 'patrimonial' },
  { value: 'jardinagem', label: 'Jardinagem', empresa: 'patrimonial' },
  { value: 'facilities', label: 'Facilities', empresa: 'patrimonial' },
  { value: 'recepcao', label: 'Recepção', empresa: 'patrimonial' },
  { value: 'zeladoria', label: 'Zeladoria', empresa: 'patrimonial' },
  { value: 'portaria_remota', label: 'Portaria Remota', empresa: 'eletronica' },
  { value: 'monitoramento', label: 'Monitoramento', empresa: 'eletronica' },
  { value: 'cftv', label: 'CFTV / Câmeras', empresa: 'eletronica' },
  { value: 'alarmes', label: 'Alarmes', empresa: 'eletronica' },
  { value: 'controle_acesso', label: 'Controle de Acesso', empresa: 'eletronica' },
  { value: 'automacao', label: 'Automação', empresa: 'eletronica' },
  { value: 'seguranca_eletronica', label: 'Segurança Eletrônica', empresa: 'eletronica' },
];

const MESES = [
  { value: 1, label: 'Janeiro' }, { value: 2, label: 'Fevereiro' },
  { value: 3, label: 'Março' }, { value: 4, label: 'Abril' },
  { value: 5, label: 'Maio' }, { value: 6, label: 'Junho' },
  { value: 7, label: 'Julho' }, { value: 8, label: 'Agosto' },
  { value: 9, label: 'Setembro' }, { value: 10, label: 'Outubro' },
  { value: 11, label: 'Novembro' }, { value: 12, label: 'Dezembro' },
];

const LIMINARES_OPTIONS = [
  {
    id: 'pis_cofins_zero',
    label: 'PIS/COFINS = 0',
    description: 'Liminar judicial isenta PIS e COFINS (Patrimonial)',
  },
  {
    id: 'inss_nao_retido',
    label: 'INSS não retido',
    description: 'Liminar impede retenção do INSS pelo tomador (Patrimonial)',
  },
];

// ─── Helper ──────────────────────────────────────────────────────────────────

function formatCurrency(value: number): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
  }).format(value);
}

function getEmpresaLabel(slug: string): string {
  if (slug === 'conecta_eletronica') return 'Conecta Eletrônica';
  if (slug === 'conecta_patrimonial') return 'Conecta Patrimonial';
  return slug;
}

function getLiminarLabel(liminar: string): string {
  const map: Record<string, string> = {
    pis_cofins_zero: 'PIS/COFINS = 0',
    inss_nao_retido: 'INSS não retido',
  };
  return map[liminar] ?? liminar;
}

// ─── Page ────────────────────────────────────────────────────────────────────

export default function NFSeMultiPage() {
  const [form, setForm] = useState({
    tipo_servico: 'vigilancia',
    descricao_servico: '',
    valor_servico: '',
    tomador_cnpj_cpf: '',
    tomador_razao_social: '',
    tomador_email: '',
    competencia_ano: 2026,
    competencia_mes: 3,
    forcar_liminares: [] as string[],
  });

  const [resultado, setResultado] = useState<NFSeMultiResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [erro, setErro] = useState<string | null>(null);
  const [xmlAberto, setXmlAberto] = useState(false);

  const tipoSelecionado = TIPOS_SERVICO.find((t) => t.value === form.tipo_servico);

  function handleLiminarToggle(liminarId: string) {
    setForm((prev) => ({
      ...prev,
      forcar_liminares: prev.forcar_liminares.includes(liminarId)
        ? prev.forcar_liminares.filter((l) => l !== liminarId)
        : [...prev.forcar_liminares, liminarId],
    }));
  }

  async function handleCalcular(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setErro(null);
    setResultado(null);

    try {
      const payload = {
        tipo_servico: form.tipo_servico,
        descricao_servico: form.descricao_servico,
        valor_servico: parseFloat(form.valor_servico.replace(',', '.')),
        tomador_cnpj_cpf: form.tomador_cnpj_cpf.replace(/\D/g, ''),
        tomador_razao_social: form.tomador_razao_social,
        tomador_email: form.tomador_email || undefined,
        competencia_ano: form.competencia_ano,
        competencia_mes: form.competencia_mes,
        forcar_liminares: form.forcar_liminares,
      };

      const resp = await apiClient<NFSeMultiResult>({ url: '/api/v1/fiscal/nfse-multi/preparar', method: 'POST', data: payload });
      setResultado(resp);
    } catch (err: any) {
      setErro(err?.response?.data?.detail ?? 'Erro ao calcular NFS-e. Tente novamente.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <PageHeader
        eyebrow="FISCAL"
        title="Emissão NFS-e Inteligente"
        subtitle="Seleciona automaticamente a empresa emissora e aplica liminares judiciais"
        icon={<FileText className="h-5 w-5" />}
        actions={
          <Badge variant="outline" className="bg-amber-50 text-amber-700 border-amber-200">
            Ambiente: Homologação
          </Badge>
        }
      />

      {/* Formulário */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base flex items-center gap-2">
            <Calculator className="h-4 w-4" />
            Dados da NFS-e
          </CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleCalcular} className="space-y-5">
            {/* Tipo de Serviço + preview empresa */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">
                  Tipo de Serviço <span className="text-red-500">*</span>
                </label>
                <select
                  value={form.tipo_servico}
                  onChange={(e) => setForm((p) => ({ ...p, tipo_servico: e.target.value }))}
                  className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                >
                  <optgroup label="Patrimonial / Humano">
                    {TIPOS_SERVICO.filter((t) => t.empresa === 'patrimonial').map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </optgroup>
                  <optgroup label="Eletrônico / Tecnologia">
                    {TIPOS_SERVICO.filter((t) => t.empresa === 'eletronica').map((t) => (
                      <option key={t.value} value={t.value}>{t.label}</option>
                    ))}
                  </optgroup>
                </select>
                {tipoSelecionado && (
                  <p className="text-xs text-muted-foreground mt-1">
                    Empresa detectada:{' '}
                    <span className={
                      tipoSelecionado.empresa === 'eletronica'
                        ? 'text-green-700 font-medium'
                        : 'text-blue-700 font-medium'
                    }>
                      {tipoSelecionado.empresa === 'eletronica'
                        ? 'Conecta Eletrônica'
                        : 'Conecta Patrimonial'}
                    </span>
                  </p>
                )}
              </div>

              <div>
                <label className="text-sm font-medium mb-1 block">
                  Valor do Serviço (R$) <span className="text-red-500">*</span>
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  value={form.valor_servico}
                  onChange={(e) => setForm((p) => ({ ...p, valor_servico: e.target.value }))}
                  placeholder="50000.00"
                  className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>
            </div>

            {/* Descrição */}
            <div>
              <label className="text-sm font-medium mb-1 block">
                Descrição do Serviço <span className="text-red-500">*</span>
              </label>
              <textarea
                value={form.descricao_servico}
                onChange={(e) => setForm((p) => ({ ...p, descricao_servico: e.target.value }))}
                placeholder="Serviços de vigilância patrimonial - Competência 03/2026"
                rows={2}
                className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 resize-none"
                required
              />
            </div>

            {/* Tomador */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">
                  CNPJ/CPF do Tomador <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={form.tomador_cnpj_cpf}
                  onChange={(e) => setForm((p) => ({ ...p, tomador_cnpj_cpf: e.target.value }))}
                  placeholder="00.000.000/0001-00"
                  className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">
                  Razão Social do Tomador <span className="text-red-500">*</span>
                </label>
                <input
                  type="text"
                  value={form.tomador_razao_social}
                  onChange={(e) => setForm((p) => ({ ...p, tomador_razao_social: e.target.value }))}
                  placeholder="Cliente Exemplo Ltda"
                  className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                  required
                />
              </div>
            </div>

            {/* Competência */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <div>
                <label className="text-sm font-medium mb-1 block">Mês</label>
                <select
                  value={form.competencia_mes}
                  onChange={(e) => setForm((p) => ({ ...p, competencia_mes: parseInt(e.target.value) }))}
                  className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {MESES.map((m) => (
                    <option key={m.value} value={m.value}>{m.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium mb-1 block">Ano</label>
                <select
                  value={form.competencia_ano}
                  onChange={(e) => setForm((p) => ({ ...p, competencia_ano: parseInt(e.target.value) }))}
                  className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                >
                  {[2025, 2026, 2027].map((a) => (
                    <option key={a} value={a}>{a}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-sm font-medium mb-1 block">E-mail do Tomador (opcional)</label>
                <input
                  type="email"
                  value={form.tomador_email}
                  onChange={(e) => setForm((p) => ({ ...p, tomador_email: e.target.value }))}
                  placeholder="financeiro@cliente.com.br"
                  className="w-full border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
                />
              </div>
            </div>

            {/* Liminares (debug) */}
            <div className="border rounded-lg p-4 bg-amber-50 border-amber-200">
              <p className="text-sm font-medium text-amber-800 mb-3 flex items-center gap-1">
                <AlertCircle className="h-4 w-4" />
                Forçar Liminares para Teste (debug)
              </p>
              <div className="space-y-2">
                {LIMINARES_OPTIONS.map((opt) => (
                  <label key={opt.id} className="flex items-start gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={form.forcar_liminares.includes(opt.id)}
                      onChange={() => handleLiminarToggle(opt.id)}
                      className="mt-0.5"
                    />
                    <span className="text-sm">
                      <span className="font-medium text-amber-900">{opt.label}</span>
                      <span className="text-amber-700 ml-1">— {opt.description}</span>
                    </span>
                  </label>
                ))}
              </div>
            </div>

            {/* Erro */}
            {erro && (
              <div className="flex items-center gap-2 p-3 bg-red-50 border border-red-200 rounded-lg text-red-700 text-sm">
                <XCircle className="h-4 w-4 shrink-0" />
                {erro}
              </div>
            )}

            <Button type="submit" disabled={loading} className="w-full md:w-auto">
              {loading ? (
                <span className="flex items-center gap-2">
                  <span className="animate-spin h-4 w-4 border-2 border-white border-t-transparent rounded-full" />
                  Calculando...
                </span>
              ) : (
                <span className="flex items-center gap-2">
                  <Sparkles className="h-4 w-4" />
                  Calcular e Pré-visualizar
                </span>
              )}
            </Button>
          </form>
        </CardContent>
      </Card>

      {/* Resultado */}
      {resultado && (
        <div className="space-y-4">
          {/* Status + Empresa */}
          <Card className={resultado.sucesso ? 'border-green-200' : 'border-amber-200'}>
            <CardContent className="pt-4">
              <div className="flex flex-wrap items-center gap-3">
                {resultado.sucesso ? (
                  <CheckCircle2 className="h-5 w-5 text-green-600" />
                ) : (
                  <AlertCircle className="h-5 w-5 text-amber-600" />
                )}
                <div className="flex-1">
                  <p className="font-medium text-sm">{resultado.mensagem}</p>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {resultado.motivo_selecao_empresa}
                  </p>
                </div>

                {/* Badge empresa */}
                <Badge
                  className={
                    resultado.empresa_emissora === 'conecta_eletronica'
                      ? 'bg-green-100 text-green-800 border-green-200'
                      : 'bg-blue-100 text-blue-800 border-blue-200'
                  }
                  variant="outline"
                >
                  <Building2 className="h-3 w-3 mr-1" />
                  {getEmpresaLabel(resultado.empresa_emissora)}
                </Badge>

                {/* Liminares aplicadas */}
                {resultado.liminares_aplicadas.map((lim) => (
                  <Badge
                    key={lim}
                    variant="outline"
                    className="bg-yellow-50 text-yellow-800 border-yellow-300"
                  >
                    {getLiminarLabel(lim)}
                  </Badge>
                ))}
              </div>
            </CardContent>
          </Card>

          {/* Tabela de tributos */}
          {resultado.sucesso && resultado.tributos && (
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Tributos Calculados</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="border-b">
                        <th className="text-left py-2 font-medium text-muted-foreground">Tributo</th>
                        <th className="text-right py-2 font-medium text-muted-foreground">Alíquota</th>
                        <th className="text-right py-2 font-medium text-muted-foreground">Valor</th>
                        <th className="text-center py-2 font-medium text-muted-foreground">Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      <tr>
                        <td className="py-2 font-medium">PIS</td>
                        <td className="text-right text-muted-foreground">0,65%</td>
                        <td className="text-right">{formatCurrency(resultado.tributos.pis)}</td>
                        <td className="text-center">
                          {resultado.tributos.pis === 0 && resultado.liminares_aplicadas.includes('pis_cofins_zero')
                            ? <span title="Zerado por liminar"><CheckCircle2 className="h-4 w-4 text-green-600 mx-auto" /></span>
                            : <span className="text-muted-foreground">—</span>
                          }
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2 font-medium">COFINS</td>
                        <td className="text-right text-muted-foreground">3,00%</td>
                        <td className="text-right">{formatCurrency(resultado.tributos.cofins)}</td>
                        <td className="text-center">
                          {resultado.tributos.cofins === 0 && resultado.liminares_aplicadas.includes('pis_cofins_zero')
                            ? <span title="Zerado por liminar"><CheckCircle2 className="h-4 w-4 text-green-600 mx-auto" /></span>
                            : <span className="text-muted-foreground">—</span>
                          }
                        </td>
                      </tr>
                      <tr>
                        <td className="py-2 font-medium">ISS</td>
                        <td className="text-right text-muted-foreground">5,00%</td>
                        <td className="text-right">{formatCurrency(resultado.tributos.iss)}</td>
                        <td className="text-center"><span className="text-muted-foreground">—</span></td>
                      </tr>
                      <tr>
                        <td className="py-2 font-medium">INSS (Retenção Tomador)</td>
                        <td className="text-right text-muted-foreground">11,00%</td>
                        <td className="text-right text-muted-foreground">
                          {resultado.tributos.inss_retido ? 'Retido' : 'Não retido'}
                        </td>
                        <td className="text-center">
                          {!resultado.tributos.inss_retido
                            ? <span title="Liminar: não retido"><CheckCircle2 className="h-4 w-4 text-green-600 mx-auto" /></span>
                            : <span className="text-muted-foreground">—</span>
                          }
                        </td>
                      </tr>
                    </tbody>
                    <tfoot>
                      <tr className="border-t-2 bg-green-50">
                        <td colSpan={2} className="py-3 font-bold text-green-800">
                          Valor Líquido a Receber
                        </td>
                        <td className="text-right py-3 font-data font-semibold tabular-nums text-green-800 text-lg">
                          {formatCurrency(resultado.tributos.valor_liquido)}
                        </td>
                        <td />
                      </tr>
                    </tfoot>
                  </table>
                </div>
              </CardContent>
            </Card>
          )}

          {/* XML Preview */}
          {resultado.xml_gerado && (
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">XML NFS-e (Sistema Nacional ABRASF)</CardTitle>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setXmlAberto((p) => !p)}
                  >
                    {xmlAberto ? (
                      <><ChevronUp className="h-4 w-4 mr-1" /> Recolher</>
                    ) : (
                      <><ChevronDown className="h-4 w-4 mr-1" /> Expandir</>
                    )}
                  </Button>
                </div>
              </CardHeader>
              {xmlAberto && (
                <CardContent>
                  <textarea
                    readOnly
                    value={resultado.xml_gerado}
                    rows={20}
                    className="w-full font-mono text-xs border rounded-md p-3 bg-gray-50 resize-y"
                  />
                </CardContent>
              )}
            </Card>
          )}

          {/* Botão Emitir */}
          <Card className="border-dashed border-2 border-gray-300 bg-gray-50">
            <CardContent className="pt-4 text-center">
              <Button
                disabled
                className="opacity-60"
                size="lg"
              >
                <Send className="h-4 w-4 mr-2" />
                Emitir NFS-e no Gov.br
              </Button>
              <p className="text-xs text-muted-foreground mt-2">
                Transmissão ao Sistema Nacional NFS-e em desenvolvimento — ambiente homologação
              </p>
            </CardContent>
          </Card>
        </div>
      )}
    </div>
  );
}
