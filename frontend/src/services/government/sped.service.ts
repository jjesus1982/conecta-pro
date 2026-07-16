/**
 * Service Layer - SPED
 *
 * Endpoints: SPED Fiscal, SPED Contábil, EFD-Reinf
 */

import api from '@/lib/api';
import type {
  DefinirBalancoRequest,
  DefinirDRERequest,
  GerarR1000Request,
  GerarR2010Request,
  GerarR2099Request,
  GerarR4010Request,
  GerarR4020Request,
  ImportarReinfRequest,
  StandardResponse,
} from '@/types/generated/government';

// Tipos locais para a camada de serviço
export interface DocumentoFiscalParams {
  tipo_documento: string;
  numero: string;
  data_emissao: string;
  valor_total: number;
  impostos: Record<string, number>;
  itens: Array<{
    produto_id: string;
    quantidade: number;
    valor_unitario: number;
  }>;
}

export interface InventarioParams {
  data_referencia: string;
  produtos: Array<{
    codigo: string;
    descricao: string;
    quantidade: number;
    valor_unitario: number;
  }>;
}

export interface LancamentoContabilParams {
  data_lancamento: string;
  historico: string;
  lancamentos: Array<{
    conta_contabil: string;
    tipo: 'debito' | 'credito';
    valor: number;
  }>;
}

/**
 * Adiciona documento fiscal ao SPED Fiscal
 */
export async function adicionarDocumentoFiscal(
  params: DocumentoFiscalParams
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/sped-fiscal/documentos',
    {
      tipo_documento: params.tipo_documento,
      numero: params.numero,
      data_emissao: params.data_emissao,
      valor_total: params.valor_total,
      impostos: params.impostos,
      itens: params.itens,
    }
  );
  return data;
}

/**
 * Adiciona inventário ao SPED Fiscal
 */
export async function adicionarInventario(
  params: InventarioParams
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/sped-fiscal/inventario',
    {
      data_referencia: params.data_referencia,
      produtos: params.produtos,
    }
  );
  return data;
}

/**
 * Adiciona produto ao cadastro SPED Fiscal
 */
export async function adicionarProduto(params: {
  codigo: string;
  descricao: string;
  ncm: string;
  unidade: string;
}): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/sped-fiscal/produtos',
    {
      codigo: params.codigo,
      descricao: params.descricao,
      ncm: params.ncm,
      unidade: params.unidade,
    }
  );
  return data;
}

/**
 * Gera arquivo SPED Fiscal.
 * O endpoint exige {periodo_inicio, periodo_fim} e devolve JSON {success, data:{total_registros...}}
 * — a tela seleciona mês/ano, então convertemos aqui (antes mandava mes/ano_referencia e o
 * backend respondia 422 sempre; e responseType blob quebrava o retorno JSON).
 */
export async function gerarArquivoSpedFiscal(params: {
  mes_referencia: string;
  ano_referencia: number;
}): Promise<StandardResponse> {
  const mes = Number(params.mes_referencia);
  const ano = Number(params.ano_referencia);
  const ultimoDia = new Date(ano, mes, 0).getDate();
  const mm = String(mes).padStart(2, '0');
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/sped-fiscal/gerar',
    {
      periodo_inicio: `${ano}-${mm}-01`,
      periodo_fim: `${ano}-${mm}-${String(ultimoDia).padStart(2, '0')}`,
    }
  );
  return data;
}

/**
 * Adiciona conta contábil ao plano de contas
 */
export async function adicionarContaContabil(params: {
  codigo: string;
  nome: string;
  tipo: string;
  nivel: number;
}): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/sped-contabil/contas',
    {
      codigo: params.codigo,
      nome: params.nome,
      tipo: params.tipo,
      nivel: params.nivel,
    }
  );
  return data;
}

/**
 * Adiciona lançamento contábil
 */
export async function adicionarLancamento(
  params: LancamentoContabilParams
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/sped-contabil/lancamentos',
    {
      data_lancamento: params.data_lancamento,
      historico: params.historico,
      lancamentos: params.lancamentos,
    }
  );
  return data;
}

/**
 * Define balanço patrimonial
 */
export async function definirBalanco(
  params: DefinirBalancoRequest
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/sped-contabil/balanco',
    params
  );
  return data;
}

/**
 * Define DRE (Demonstração do Resultado do Exercício)
 */
export async function definirDRE(
  params: DefinirDRERequest
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/sped-contabil/dre',
    params
  );
  return data;
}

/**
 * Gera arquivo SPED Contábil
 */
export async function gerarArquivoSpedContabil(params: {
  mes_referencia: string;
  ano_referencia: number;
}): Promise<StandardResponse> {
  // Endpoint exige ano_referencia + periodo_inicio/fim e devolve JSON (não blob) — ver
  // gerarArquivoSpedFiscal. ECD é anual: período = ano inteiro até o fim do mês escolhido.
  const mes = Number(params.mes_referencia);
  const ano = Number(params.ano_referencia);
  const ultimoDia = new Date(ano, mes, 0).getDate();
  const mm = String(mes).padStart(2, '0');
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/sped-contabil/gerar',
    {
      ano_referencia: ano,
      periodo_inicio: `${ano}-01-01`,
      periodo_fim: `${ano}-${mm}-${String(ultimoDia).padStart(2, '0')}`,
    }
  );
  return data;
}

/**
 * Gera evento R-1000 da EFD-Reinf (Informações do Contribuinte)
 */
export async function gerarR1000(
  params: GerarR1000Request
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/efd-reinf/r1000',
    params
  );
  return data;
}

/**
 * Gera evento R-2010 da EFD-Reinf (Retenção de Contribuição Previdenciária)
 */
export async function gerarR2010(
  params: GerarR2010Request
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/efd-reinf/r2010',
    params
  );
  return data;
}

/**
 * Gera evento R-2099 da EFD-Reinf (Fechamento)
 */
export async function gerarR2099(
  params: GerarR2099Request
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/efd-reinf/r2099',
    params
  );
  return data;
}

/**
 * Gera evento R-4010 da EFD-Reinf (Pagamento/Crédito)
 */
export async function gerarR4010(
  params: GerarR4010Request
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/efd-reinf/r4010',
    params
  );
  return data;
}

/**
 * Gera evento R-4020 da EFD-Reinf (Pagamento/Crédito Diverso)
 */
export async function gerarR4020(
  params: GerarR4020Request
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/efd-reinf/r4020',
    params
  );
  return data;
}

/**
 * Importa arquivo EFD-Reinf
 */
export async function importarReinf(
  params: ImportarReinfRequest
): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/efd-reinf/importar',
    params
  );
  return data;
}

/**
 * Valida arquivo SPED antes de gerar
 */
export async function validarSped(params: {
  tipo: 'fiscal' | 'contabil' | 'reinf';
  mes_referencia: string;
  ano_referencia: number;
}): Promise<StandardResponse> {
  const { data } = await api.post<StandardResponse>(
    '/api/v1/government/sped/validar',
    params
  );
  return data;
}

const spedService = {
  adicionarDocumentoFiscal,
  adicionarInventario,
  adicionarProduto,
  gerarArquivoSpedFiscal,
  adicionarContaContabil,
  adicionarLancamento,
  definirBalanco,
  definirDRE,
  gerarArquivoSpedContabil,
  gerarR1000,
  gerarR2010,
  gerarR2099,
  gerarR4010,
  gerarR4020,
  importarReinf,
  validarSped,
};

export default spedService;
