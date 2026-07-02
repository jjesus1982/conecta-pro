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

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.bidding.agents.analyst_agent import AnalystAgent
from modules.bidding.agents.assessor_agent import AssessorAgent, CompanyProfile
from modules.bidding.agents.base_agent import AgentStatus
from modules.bidding.agents.compiler_agent import CompilerAgent
from modules.bidding.agents.orchestrator import PipelineOrchestrator
from modules.bidding.agents.pricer_agent import PricerAgent
from modules.bidding.agents.scout_agent import ScoutAgent, ScoutSearchParams
from modules.bidding.agents.sentinel_agent import SentinelAgent
from modules.bidding.models.analysis import BiddingAnalysis
from modules.bidding.models.certificate import Certificate, CertificateStatus
from modules.bidding.agents.warrior_agent import WarriorAgent
from modules.bidding.schemas.analysis import AnalystRequest
from modules.bidding.schemas.assessment import AssessorRequest
from modules.bidding.schemas.opportunity import ScoutRequest
from modules.bidding.schemas.pipeline import PipelineRequest
from modules.bidding.schemas.pricing import PricerRequest

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
@router.get("/status")
async def list_agents_status(current_user: CurrentActiveUser):
    """Lista todos os agentes e seus status de implementacao."""
    return {
        "agents": AGENTS_REGISTRY,
        "total": len(AGENTS_REGISTRY),
        "operational": sum(1 for a in AGENTS_REGISTRY if a["status"] == AgentStatus.OPERATIONAL.value),
        "development": sum(1 for a in AGENTS_REGISTRY if a["status"] == AgentStatus.DEVELOPMENT.value),
        "planned": sum(1 for a in AGENTS_REGISTRY if a["status"] == AgentStatus.PLANNED.value),
    }


# ============================================================
# Scout - Busca de oportunidades
# ============================================================
@router.post("/scout/buscar", status_code=201)
async def scout_buscar(current_user: CurrentActiveUser, request: ScoutRequest):
    """Busca oportunidades de licitacao nos portais configurados."""
    try:
        search_params = ScoutSearchParams(
            keywords=request.keywords or ["vigilancia", "seguranca patrimonial", "portaria"],
            ufs=[request.uf] if request.uf else ["AM"],
            modalidades=[request.modalidade] if request.modalidade else None,
            valor_minimo=request.valor_min,
            valor_maximo=request.valor_max,
            portais=request.portais
            if hasattr(request, "portais") and request.portais
            else ["pncp", "comprasnet", "licitacoes_e", "ecompras_am"],
        )
        result = await scout_agent.run(search_params=search_params)
        if result.success:
            opportunities = result.data if isinstance(result.data, list) else result.data.get("opportunities", [])
            return {
                "status": "success",
                "agent": "scout",
                "opportunities": opportunities,
                "total": len(opportunities),
                "portal": request.portal or "todos",
            }
        return {
            "status": "error",
            "agent": "scout",
            "message": result.error or "Erro na busca",
        }
    except Exception as e:
        logger.error(f"Erro no agente Scout: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao executar agente Scout: {str(e)}",
        )


@router.get("/scout/portais")
async def scout_portais(current_user: CurrentActiveUser):
    """Lista portais de licitacao disponiveis para busca."""
    return {
        "portais": [
            {
                "id": "pncp",
                "nome": "Portal Nacional de Contratacoes Publicas",
                "url": "https://pncp.gov.br",
                "status": "disponivel",
                "tipo": "federal",
            },
            {
                "id": "comprasnet",
                "nome": "ComprasNet / Compras.gov.br",
                "url": "https://www.gov.br/compras",
                "status": "disponivel",
                "tipo": "federal",
            },
            {
                "id": "bec",
                "nome": "Bolsa Eletronica de Compras (SP)",
                "url": "https://www.bec.sp.gov.br",
                "status": "planejado",
                "tipo": "estadual",
            },
            {
                "id": "licitacoes_e",
                "nome": "Licitacoes-e (BB)",
                "url": "https://www.licitacoes-e.com.br",
                "status": "planejado",
                "tipo": "banco",
            },
            {
                "id": "e_compras_am",
                "nome": "e-Compras Amazonas",
                "url": "https://www.e-compras.am.gov.br",
                "status": "planejado",
                "tipo": "estadual",
            },
        ],
        "total": 5,
    }


# ============================================================
# Analyst - Analise de editais
# ============================================================
@router.post("/analyst/analisar", status_code=201)
async def analyst_analisar(current_user: CurrentActiveUser, request: AnalystRequest):
    """Analisa edital extraindo requisitos, prazos, riscos e oportunidades."""
    try:
        if not request.tender_id and not request.edital_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe tender_id ou edital_text para analise",
            )
        result = await analyst_agent.run(
            edital_text=request.edital_text or "",
        )
        if result.success:
            return {
                "status": "success",
                "agent": "analyst",
                "analysis": result.data,
            }
        return {
            "status": "error",
            "agent": "analyst",
            "message": result.error or "Erro na analise",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no agente Analyst: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao executar agente Analyst: {str(e)}",
        )


# ============================================================
# Assessor - Avaliacao Go/No-Go
# ============================================================
@router.post("/assessor/avaliar", status_code=201)
async def assessor_avaliar(
    current_user: CurrentActiveUser,
    request: AssessorRequest,
    db: AsyncSession = Depends(get_db),
):
    """Avalia viabilidade de participacao (Go/No-Go) com scoring multidimensional."""
    try:
        if not request.tender_id and not request.analysis_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe tender_id ou analysis_id para avaliacao",
            )
        # Carregar a analise REAL de bidding_analyses (por analysis_id ou tender_id)
        analysis = await _carregar_analise_real(db, request.analysis_id, request.tender_id)
        if analysis is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Analise nao encontrada para o analysis_id/tender_id informado",
            )
        # Perfil da empresa com dados REAIS (colaboradores, documentos validos)
        company_profile = await _montar_company_profile(db)
        result = await assessor_agent.run(
            analysis=analysis,
            company_profile=company_profile,
        )
        if result.success:
            return {
                "status": "success",
                "agent": "assessor",
                "assessment": result.data,
            }
        return {
            "status": "error",
            "agent": "assessor",
            "message": result.error or "Erro na avaliacao",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no agente Assessor: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao executar agente Assessor: {str(e)}",
        )


# ============================================================
# Pricer - Precificacao
# ============================================================
@router.post("/pricer/calcular", status_code=201)
async def pricer_calcular(current_user: CurrentActiveUser, request: PricerRequest):
    """Calcula precificacao com composicao de custos, BDI e cenarios."""
    try:
        pricing_input = {
            "regime_tributario": request.regime_tributario or "simples",
            "bdi_percentual": request.bdi_percentual,
            "cenario": request.cenario or "moderado",
        }
        result = await pricer_agent.run(pricing_input=pricing_input)
        if result.success:
            return {
                "status": "success",
                "agent": "pricer",
                "pricing": result.data,
            }
        return {
            "status": "error",
            "agent": "pricer",
            "message": result.error or "Erro na precificacao",
        }
    except Exception as e:
        logger.error(f"Erro no agente Pricer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao executar agente Pricer: {str(e)}",
        )


# ============================================================
# Pipeline - Execucao completa
# ============================================================
@router.post("/pipeline", status_code=201)
async def run_pipeline(current_user: CurrentActiveUser, request: PipelineRequest):
    """Executa pipeline completo: analise -> avaliacao -> precificacao."""
    try:
        if not request.tender_id and not request.edital_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Informe tender_id ou edital_text para o pipeline",
            )
        if request.edital_text:
            # Analise de edital direto (ANALYST + ASSESSOR)
            pipeline_result = await orchestrator.run_analysis_only(
                edital_text=request.edital_text,
            )
        else:
            # Pipeline completo com busca (SCOUT → ANALYST → ASSESSOR → PRICER)
            pipeline_result = await orchestrator.run_full_pipeline()
        return {
            "status": pipeline_result.status_geral,
            "agent": "pipeline",
            "pipeline": {
                "pipeline_id": pipeline_result.pipeline_id,
                "status": pipeline_result.status_geral,
                "etapas": [
                    {"nome": e.step.value, "status": e.status, "duracao_ms": e.duration_ms}
                    for e in pipeline_result.steps_executados
                ],
                "analise": pipeline_result.analise,
                "avaliacao": pipeline_result.avaliacao,
                "precificacao": pipeline_result.precificacao,
                "score_final": pipeline_result.score_final,
                "recomendacao": pipeline_result.recomendacao_final,
            },
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro no pipeline de agentes: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao executar pipeline: {str(e)}",
        )


# ============================================================
# Sentinel - Monitoramento de certidoes
# ============================================================
@router.get("/sentinel/tipos")
async def sentinel_tipos(current_user: CurrentActiveUser):
    """Lista tipos de certidoes monitoradas pelo agente Sentinel."""
    return {
        "tipos": CERTIFICATE_TYPES,
        "total": len(CERTIFICATE_TYPES),
    }


@router.post("/sentinel/verificar", status_code=201)
async def sentinel_verificar(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)):
    """Verifica status atual de todas as certidoes da empresa."""
    try:
        # Carregar certidoes/documentos REAIS de bidding_certificates
        documentos_reais = await _carregar_documentos_sentinel(db)
        result = await sentinel_agent.run(documentos=documentos_reais or None, cnpj=EMPRESA_CNPJ)
        if result.success:
            return {
                "status": "success",
                "agent": "sentinel",
                "verificacao": result.data,
            }
        return {
            "status": "error",
            "agent": "sentinel",
            "message": result.error or "Erro na verificacao",
        }
    except Exception as e:
        logger.error(f"Erro no agente Sentinel: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao executar agente Sentinel: {str(e)}",
        )


@router.get("/sentinel/alertas")
async def sentinel_alertas(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)):
    """Retorna certidoes proximas do vencimento ou vencidas."""
    try:
        # Carregar certidoes/documentos REAIS de bidding_certificates
        documentos_reais = await _carregar_documentos_sentinel(db)
        result = await sentinel_agent.run(documentos=documentos_reais or None, cnpj=EMPRESA_CNPJ)
        if result.success:
            documentos = result.data.get("documentos", [])
            alertas = [d for d in documentos if d.get("nivel_alerta") in ("urgente", "critico", "atencao")]
            return {
                "status": "success",
                "agent": "sentinel",
                "alertas": alertas,
                "total": len(alertas),
                "apto_licitar": result.data.get("apto_licitar", False),
            }
        return {
            "status": "error",
            "agent": "sentinel",
            "message": result.error or "Erro ao consultar alertas",
        }
    except Exception as e:
        logger.error(f"Erro ao consultar alertas: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao consultar alertas: {str(e)}",
        )


# ============================================================
# Warrior - Robo de disputa
# ============================================================
@router.get("/warrior/status")
async def warrior_status(current_user: CurrentActiveUser):
    """Retorna status do robo de disputa (Warrior)."""
    return {
        "status": warrior_agent.AGENT_STATUS.value,
        "agent": "warrior",
        "message": "Warrior disponivel para simulacao de disputas",
        "modos": ["simulacao"],
        "portais_reais": [],
    }


@router.post("/warrior/simular", status_code=201)
async def warrior_simular(
    current_user: CurrentActiveUser,
    valor_referencia: float = 100000.0,
    estrategia: str = "moderado",
    piso_minimo: float | None = None,
    num_rodadas: int = 10,
    concorrentes: int = 3,
):
    """Simula uma disputa de pregao eletronico."""
    try:
        result = await warrior_agent.run(
            valor_referencia=valor_referencia,
            estrategia=estrategia,
            piso_minimo=piso_minimo or valor_referencia * 0.7,
            num_rodadas=num_rodadas,
            concorrentes=concorrentes,
        )
        if result.success:
            return {"status": "success", "agent": "warrior", "simulacao": result.data}
        return {"status": "error", "agent": "warrior", "message": result.error or "Erro na simulacao"}
    except Exception as e:
        logger.error(f"Erro no Warrior: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro na simulacao: {str(e)}")


# ============================================================
# Compiler - Geracao de documentos
# ============================================================
@router.post("/compiler/gerar", status_code=201)
async def compiler_gerar(
    current_user: CurrentActiveUser,
    edital_numero: str = "001/2026",
    objeto: str = "Contratacao de servicos de vigilancia patrimonial",
    valor_total: float = 100000.0,
    regime_tributario: str = "simples",
):
    """Gera documentos de proposta (carta, planilha, declaracoes)."""
    try:
        result = await compiler_agent.run(
            analysis_data={"numero_edital": edital_numero, "objeto": objeto, "modalidade": "Pregao Eletronico"},
            pricing_data={"valor_total": valor_total, "regime_tributario": regime_tributario},
        )
        if result.success:
            return {"status": "success", "agent": "compiler", "documentos": result.data}
        return {"status": "error", "agent": "compiler", "message": result.error or "Erro na geracao"}
    except Exception as e:
        logger.error(f"Erro no Compiler: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Erro na geracao: {str(e)}")
