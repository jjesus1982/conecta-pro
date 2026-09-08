"""
Controller de Agentes IA - Licitacoes
======================================
Endpoints para interacao com os agentes de inteligencia artificial
do modulo de licitacoes: Scout, Analyst, Assessor, Pricer, Sentinel, Warrior.
"""

import logging
import re
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from modules.bidding.agents.analyst_agent import AnalystAgent
from modules.bidding.agents.assessor_agent import AssessorAgent, CompanyProfile
from modules.bidding.agents.compiler_agent import CompilerAgent
from modules.bidding.agents.orchestrator import PipelineOrchestrator
from modules.bidding.agents.pricer_agent import PricerAgent
from modules.bidding.agents.scout_agent import ScoutAgent
from modules.bidding.agents.sentinel_agent import SentinelAgent
from modules.bidding.models.analysis import BiddingAnalysis
from modules.bidding.models.certificate import Certificate, CertificateStatus
from modules.bidding.agents.warrior_agent import WarriorAgent

logger = logging.getLogger(__name__)

# CNPJ da empresa (Jordan Santos de Jesus Ltda) — usado nas verificacoes reais.
EMPRESA_CNPJ = "35.710.481/0001-03"
EMPRESA_CNPJ_DIGITS = "35710481000103"

router = APIRouter(prefix="/agents", tags=["Licitacoes - Agentes IA"])

# Instanciar agentes
scout_agent = ScoutAgent()
analyst_agent = AnalystAgent()
assessor_agent = AssessorAgent()
pricer_agent = PricerAgent()
sentinel_agent = SentinelAgent()
compiler_agent = CompilerAgent()
warrior_agent = WarriorAgent()
orchestrator = PipelineOrchestrator()

# ============================================================
# Registro de agentes e seus status de implementacao
# ============================================================
AGENTS_REGISTRY = [
    {
        "name": "scout",
        "description": "Busca automatizada de oportunidades em portais de licitacao",
        "status": scout_agent.AGENT_STATUS.value,
        "capabilities": ["busca_pncp", "busca_comprasnet", "busca_bec", "filtro_segmento"],
    },
    {
        "name": "analyst",
        "description": "Analise automatica de editais com extracao de requisitos e riscos",
        "status": analyst_agent.AGENT_STATUS.value,
        "capabilities": ["extracao_requisitos", "analise_riscos", "resumo_edital", "classificacao"],
    },
    {
        "name": "assessor",
        "description": "Avaliacao Go/No-Go com scoring multidimensional",
        "status": assessor_agent.AGENT_STATUS.value,
        "capabilities": ["scoring_financeiro", "scoring_tecnico", "scoring_estrategico", "analise_concorrencia"],
    },
    {
        "name": "pricer",
        "description": "Precificacao inteligente com composicao de custos e cenarios",
        "status": pricer_agent.AGENT_STATUS.value,
        "capabilities": ["composicao_custos", "calculo_bdi", "cenarios", "comparativo_mercado"],
    },
    {
        "name": "sentinel",
        "description": "Monitoramento de certidoes e documentos de habilitacao",
        "status": sentinel_agent.AGENT_STATUS.value,
        "capabilities": ["monitoramento_certidoes", "alertas_vencimento", "renovacao_automatica"],
    },
    {
        "name": "warrior",
        "description": "Robo de disputa para pregoes eletronicos",
        "status": warrior_agent.AGENT_STATUS.value,
        "capabilities": ["lances_automaticos", "estrategia_disputa", "monitoramento_sessao", "simulacao"],
    },
    {
        "name": "compiler",
        "description": "Geracao automatica de documentos de proposta",
        "status": compiler_agent.AGENT_STATUS.value,
        "capabilities": ["carta_proposta", "planilha_custos", "declaracoes", "checklist_habilitacao"],
    },
]

# Tipos de certidoes monitoradas pelo Sentinel
CERTIFICATE_TYPES = [
    {"tipo": "CND_FEDERAL", "descricao": "Certidao Negativa de Debitos Federais (RFB/PGFN)", "validade_dias": 180},
    {"tipo": "CND_ESTADUAL", "descricao": "Certidao Negativa de Debitos Estaduais (SEFAZ)", "validade_dias": 90},
    {"tipo": "CND_MUNICIPAL", "descricao": "Certidao Negativa de Debitos Municipais", "validade_dias": 90},
    {"tipo": "CRF_FGTS", "descricao": "Certificado de Regularidade do FGTS", "validade_dias": 30},
    {"tipo": "CNDT_TRABALHISTA", "descricao": "Certidao Negativa de Debitos Trabalhistas (TST)", "validade_dias": 180},
    {"tipo": "SICAF", "descricao": "Registro no SICAF", "validade_dias": 360},
    {"tipo": "CEIS", "descricao": "Consulta ao Cadastro de Empresas Inidoneas e Suspensas", "validade_dias": 0},
    {"tipo": "CNEP", "descricao": "Cadastro Nacional de Empresas Punidas", "validade_dias": 0},
    {"tipo": "ATESTADO_CAPACIDADE", "descricao": "Atestado de Capacidade Tecnica", "validade_dias": 0},
    {"tipo": "BALANCO_PATRIMONIAL", "descricao": "Balanco Patrimonial e DRE", "validade_dias": 365},
]


def _planned_response(agent_name: str) -> dict:
    """Retorna resposta padrao para agentes em desenvolvimento."""
    return {
        "status": "planned",
        "agent": agent_name,
        "message": "Agent em desenvolvimento",
    }


# ============================================================
# Helpers de dados reais (bidding_certificates / bidding_analyses)
# ============================================================

# Mapeia o `tipo` armazenado em bidding_certificates (varia de caixa/abreviacao)
# para o value esperado pelo SENTINEL (TipoDocumentoMonitorado).
_CERT_TIPO_TO_SENTINEL: dict[str, str] = {
    "cnd_federal": "cnd_federal",
    "cnd_estadual": "cnd_estadual",
    "cnd_municipal": "cnd_municipal",
    "crf_fgts": "crf_fgts",
    "fgts": "crf_fgts",
    "cnd_trabalhista": "cndt_trabalhista",
    "cndt": "cndt_trabalhista",
    "cndt_trabalhista": "cndt_trabalhista",
    "sicaf": "sicaf",
    "alvara": "alvara_funcionamento",
    "alvara_funcionamento": "alvara_funcionamento",
    "certificado_digital": "certificado_digital",
    "balanco_patrimonial": "balanco_patrimonial",
    "seguro_responsabilidade": "seguro_responsabilidade",
}

# Mapeia o `tipo` do certificado para a chave usada em documentos_validos
# do CompanyProfile (consumida pelo ASSESSOR).
_CERT_TIPO_TO_PROFILE_DOC: dict[str, str] = {
    "cnd_federal": "cnd_federal",
    "cnd_estadual": "cnd_estadual",
    "cnd_municipal": "cnd_municipal",
    "crf_fgts": "crf_fgts",
    "fgts": "crf_fgts",
    "cnd_trabalhista": "cndt_trabalhista",
    "cndt": "cndt_trabalhista",
    "cndt_trabalhista": "cndt_trabalhista",
    "sicaf": "sicaf",
    "certidao_falencia": "certidao_falencia",
    "balanco_patrimonial": "balanco_patrimonial",
}


def _parse_valor_estimado(valor) -> float | None:
    """
    Converte valor_estimado (que no banco pode vir como string "R$ 1.800.000,00",
    Decimal ou float) em float. Retorna None se nao for possivel.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float, Decimal)):
        return float(valor)
    texto = str(valor)
    # Remove tudo que nao for digito, virgula ou ponto
    limpo = re.sub(r"[^\d,.-]", "", texto)
    if not limpo:
        return None
    # Formato BR: 1.800.000,00 -> remove pontos de milhar, troca virgula por ponto
    if "," in limpo:
        limpo = limpo.replace(".", "").replace(",", ".")
    try:
        return float(limpo)
    except ValueError:
        return None


def _normalizar_analysis(row: BiddingAnalysis, valor_estimado_raw) -> dict:
    """
    Converte um registro real de bidding_analyses no formato de dict esperado
    pelo ASSESSOR (assessor_agent.execute).

    O ASSESSOR espera:
      - requisitos_habilitacao: list[{"categoria","descricao"}]
      - red_flags: list[{"severidade","descricao"}]
      - documentos_necessarios: list[{"nome","obrigatorio"}]
    Os dados de seed em bidding_analyses guardam requisitos como
    dict[categoria -> list[str]] e red_flags/documentos como list[str].
    Esta funcao adapta ambos os formatos preservando o conteudo REAL.
    """
    # --- requisitos_habilitacao ---
    req_norm: list[dict] = []
    raw_req = row.requisitos_habilitacao
    if isinstance(raw_req, dict):
        for categoria, itens in raw_req.items():
            if isinstance(itens, list):
                for item in itens:
                    if isinstance(item, dict):
                        req_norm.append(
                            {
                                "categoria": item.get("categoria", categoria),
                                "descricao": item.get("descricao", str(item)),
                            }
                        )
                    else:
                        req_norm.append({"categoria": categoria, "descricao": str(item)})
            elif itens:
                req_norm.append({"categoria": categoria, "descricao": str(itens)})
    elif isinstance(raw_req, list):
        for item in raw_req:
            if isinstance(item, dict):
                req_norm.append(item)
            else:
                req_norm.append({"categoria": "geral", "descricao": str(item)})

    # --- red_flags ---
    rf_norm: list[dict] = []
    raw_rf = row.red_flags
    if isinstance(raw_rf, list):
        for rf in raw_rf:
            if isinstance(rf, dict):
                rf_norm.append(rf)
            else:
                rf_norm.append({"severidade": "media", "descricao": str(rf)})

    # --- documentos_necessarios ---
    docs_norm: list[dict] = []
    raw_docs = row.documentos_necessarios
    if isinstance(raw_docs, list):
        for doc in raw_docs:
            if isinstance(doc, dict):
                docs_norm.append(doc)
            else:
                docs_norm.append({"nome": str(doc), "obrigatorio": True})

    return {
        "segmento": row.objeto_resumido or "",
        "modalidade": row.modalidade_identificada or "",
        "criterio_julgamento": row.criterio_julgamento or "",
        "valor_estimado": _parse_valor_estimado(valor_estimado_raw),
        "requisitos_habilitacao": req_norm,
        "red_flags": rf_norm,
        "documentos_necessarios": docs_norm,
        "recomendacao_participacao": row.recomendacao_participacao,
    }


async def _carregar_analise_real(db: AsyncSession, analysis_id: UUID | None, tender_id: UUID | None) -> dict | None:
    """
    Carrega a analise REAL de bidding_analyses por analysis_id (prioridade) ou
    tender_id. Retorna o dict normalizado para o ASSESSOR, ou None se nao achar.
    Le valor_estimado como coluna crua (o banco guarda como texto).
    """
    # valor_estimado eh lido como coluna crua para evitar cast do ORM (Numeric vs texto)
    if analysis_id is not None:
        stmt = select(BiddingAnalysis, BiddingAnalysis.valor_estimado).where(BiddingAnalysis.id == analysis_id)
    elif tender_id is not None:
        stmt = (
            select(BiddingAnalysis, BiddingAnalysis.valor_estimado)
            .where(BiddingAnalysis.tender_id == tender_id)
            .order_by(BiddingAnalysis.created_at.desc())
        )
    else:
        return None

    result = await db.execute(stmt)
    row = result.first()
    if row is None:
        return None
    analise_obj, valor_raw = row[0], row[1]
    return _normalizar_analysis(analise_obj, valor_raw)


async def _montar_company_profile(db: AsyncSession) -> CompanyProfile:
    """
    Monta o CompanyProfile a partir de DADOS REAIS onde ha fonte:
      - quantidade_colaboradores: count de employees ativos
      - documentos_validos: certificados em bidding_certificates com status valido
    Campos sem fonte real (capital social, patrimonio, indices, historico)
    permanecem None (nao informado) — o ASSESSOR tolera e nao fabrica score.
    """
    # Colaboradores ativos (dado real)
    try:
        from sqlalchemy import text

        emp_result = await db.execute(text("SELECT count(*) FROM employees WHERE status = 'ativo'"))
        qtd_colab = int(emp_result.scalar() or 0)
    except Exception as exc:  # tabela pode nao existir em outros ambientes
        logger.warning(f"Nao foi possivel contar colaboradores ativos: {exc}")
        qtd_colab = 0

    # Documentos validos reais (bidding_certificates com status valido)
    docs_validos: list[str] = []
    try:
        cert_result = await db.execute(
            select(Certificate.tipo).where(
                Certificate.ativo,
                func.lower(Certificate.status) == CertificateStatus.VALID.value,
            )
        )
        for (tipo_raw,) in cert_result.all():
            if not tipo_raw:
                continue
            chave = _CERT_TIPO_TO_PROFILE_DOC.get(str(tipo_raw).lower())
            if chave and chave not in docs_validos:
                docs_validos.append(chave)
    except Exception as exc:
        logger.warning(f"Nao foi possivel carregar documentos validos: {exc}")

    return CompanyProfile(
        quantidade_colaboradores=qtd_colab,
        documentos_validos=docs_validos,
        # Financeiros/historico ficam None (defaults do model) — honestidade.
    )


async def _carregar_documentos_sentinel(db: AsyncSession) -> list[dict]:
    """
    Carrega os certificados REAIS de bidding_certificates no formato de input
    do SENTINEL (execute(documentos=[...])). Cada item:
      {"tipo": <TipoDocumentoMonitorado value>, "data_emissao": iso, "data_validade": iso}
    Somente tipos mapeaveis para o SENTINEL sao incluidos.
    """
    documentos: list[dict] = []
    try:
        result = await db.execute(
            select(
                Certificate.tipo,
                Certificate.data_emissao,
                Certificate.data_validade,
                Certificate.status,
            ).where(Certificate.ativo)
        )
    except Exception as exc:
        logger.warning(f"Nao foi possivel carregar certificados reais para o Sentinel: {exc}")
        return documentos

    for tipo_raw, data_emissao, data_validade, _cert_status in result.all():
        if not tipo_raw:
            continue
        tipo_sentinel = _CERT_TIPO_TO_SENTINEL.get(str(tipo_raw).lower())
        if not tipo_sentinel:
            continue
        doc = {"tipo": tipo_sentinel}
        if data_emissao is not None:
            doc["data_emissao"] = data_emissao.date().isoformat() if hasattr(data_emissao, "date") else str(data_emissao)[:10]
        if data_validade is not None:
            doc["data_validade"] = (
                data_validade.date().isoformat() if hasattr(data_validade, "date") else str(data_validade)[:10]
            )
        documentos.append(doc)

    return documentos


# ============================================================
# Status geral dos agentes
# ============================================================
# ============================================================
# Scout - Busca de oportunidades
# ============================================================
# ============================================================
# Analyst - Analise de editais
# ============================================================
# ============================================================
# Assessor - Avaliacao Go/No-Go
# ============================================================
# ============================================================
# Pricer - Precificacao
# ============================================================
# ============================================================
# Pipeline - Execucao completa
# ============================================================
# ============================================================
# Sentinel - Monitoramento de certidoes
# ============================================================
# ============================================================
# Warrior - Robo de disputa
# ============================================================
# ============================================================
# Compiler - Geracao de documentos
# ============================================================
