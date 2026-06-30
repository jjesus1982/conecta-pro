"""Controller SST — Endpoints completos com wiring real.

Endpoints:
- GET  /sst/dashboard
- GET  /sst/afastamentos
- POST /sst/afastamentos
- GET  /sst/afastamentos/{id}
- PUT  /sst/afastamentos/{id}/retorno
- GET  /sst/nr1/dashboard
- GET  /sst/nr1/colaboradores-risco
- GET  /sst/pcmso/status
- GET  /sst/ppra/status
- GET  /sst/asos/vencendo
- GET  /sst/asos/sem-aso
- POST /sst/cat
- GET  /sst/estabilidade/ativos
- GET  /sst/ajuda-medicamento/ativos
- GET  /sst/cipa/membros
- GET  /sst/cipa/reunioes
- POST /sst/cipa/reunioes
"""

import logging
from datetime import date
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.sst.schemas.sst_schemas import (
    ASOCreate,
    ASOResultUpdate,
    CATCreate,
    EPIDeliveryCreate,
    RiskCreate,
)
from modules.people_management.sst.services.sst_service import SSTService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sst", tags=["SST — Saude e Seguranca do Trabalho"])


# ================================================================
# DASHBOARD
# ================================================================


@router.get("/dashboard")
async def get_dashboard(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard SST com dados reais dos colaboradores."""
    service = SSTService(db)
    return await service.get_dashboard()


# ================================================================
# AFASTAMENTOS
# ================================================================


@router.get("/afastamentos")
async def listar_afastamentos(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None, description="Filtro: ativo, encerrado"),
) -> Any:
    """Lista afastamentos (com dados reais dos 5 colaboradores Solides)."""
    service = SSTService(db)
    items = await service.listar_afastamentos(status)
    return {"total": len(items), "afastamentos": items}


@router.post("/afastamentos", status_code=201)
async def registrar_afastamento(
    data: dict,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Registra novo afastamento com regras CCT 2026 automaticas."""
    service = SSTService(db)
    result = await service.registrar_afastamento(data)
    await db.commit()
    return result


@router.get("/afastamentos/{afastamento_id}")
async def get_afastamento(
    afastamento_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Detalhe de um afastamento."""
    service = SSTService(db)
    result = await service.get_afastamento(afastamento_id)
    if not result:
        raise HTTPException(status_code=404, detail="Afastamento nao encontrado")
    return result


@router.put("/afastamentos/{afastamento_id}/retorno")
async def registrar_retorno(
    afastamento_id: str,
    data: dict,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Registra retorno de afastamento (calcula estabilidade CCT)."""
    service = SSTService(db)
    result = await service.registrar_retorno(afastamento_id, data.get("data_retorno", ""))
    if not result:
        raise HTTPException(status_code=404, detail="Afastamento nao encontrado")
    await db.commit()
    return result


# ================================================================
# NR-1
# ================================================================


@router.get("/nr1/dashboard")
async def get_nr1_dashboard(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard NR-1 — indice de risco calculado dinamicamente."""
    service = SSTService(db)
    return await service.get_dashboard_nr1()


@router.get("/nr1/colaboradores-risco")
async def listar_colaboradores_risco(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Colaboradores por nivel de risco NR-1."""
    service = SSTService(db)
    items = await service.listar_colaboradores_risco()
    return {"total": len(items), "colaboradores": items}


# ================================================================
# PCMSO / PPRA
# ================================================================


@router.get("/pcmso/status")
async def get_pcmso_status(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Status PCMSO (CCT 2026 Clausula 23a — obrigatorio)."""
    service = SSTService(db)
    return await service.get_pcmso_status()


@router.get("/ppra/status")
async def get_ppra_status(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Status PPRA (CCT 2026 Clausula 23a — obrigatorio)."""
    service = SSTService(db)
    return await service.get_ppra_status()


# ================================================================
# ASOs
# ================================================================


@router.get("/asos/vencendo")
async def listar_asos_vencendo(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    dias: int = Query(30, ge=1, le=90, description="Dias de antecedencia"),
) -> Any:
    """ASOs proximos do vencimento."""
    service = SSTService(db)
    items = await service.verificar_vencimentos_aso(dias)
    return {"total": len(items), "asos_vencendo": items}


@router.get("/asos/sem-aso")
async def listar_sem_aso(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Colaboradores sem ASO periodico."""
    service = SSTService(db)
    items = await service.listar_sem_aso()
    return {"total": len(items), "colaboradores": items}


# ================================================================
# CAT
# ================================================================


@router.post("/cat", status_code=201)
async def abrir_cat(
    data: CATCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Abre CAT (Comunicacao de Acidente de Trabalho)."""
    from modules.people_management.sst.models.cat import CATModel

    cat = CATModel(
        cat_id=str(uuid4()),
        employee_id=data.employee_id,
        tipo_acidente=data.tipo_acidente,
        data_acidente=__import__("datetime").datetime.strptime(str(data.data_acidente)[:10], "%Y-%m-%d").date()
        if data.data_acidente
        else None,
        local=data.local,
        descricao=data.descricao,
        gravidade=data.gravidade,
        testemunhas=data.testemunhas,
        status="aberta",
    )
    db.add(cat)
    await db.flush()
    return {
        "cat_id": cat.cat_id,
        "employee_id": cat.employee_id,
        "tipo": cat.tipo_acidente,
        "data": str(cat.data_acidente),
        "local": cat.local,
        "gravidade": cat.gravidade,
        "status": cat.status,
    }


@router.get("/cat")
async def listar_cats(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str | None = Query(None),
) -> Any:
    """Lista CATs registradas."""
    from sqlalchemy import text as sql_text

    try:
        query = "SELECT cat_id, employee_id, tipo_acidente, data_acidente, local, gravidade, status FROM gp_cats"
        params: dict[str, Any] = {}
        if employee_id:
            query += " WHERE employee_id::text = :eid"
            params["eid"] = employee_id
        query += " ORDER BY data_acidente DESC"
        result = await db.execute(sql_text(query), params)
        cats = [
            {
                "cat_id": r[0],
                "employee_id": str(r[1]),
                "tipo": r[2],
                "data": str(r[3]),
                "local": r[4],
                "gravidade": r[5],
                "status": r[6],
            }
            for r in result.fetchall()
        ]
    except Exception as exc:
        logger.warning("SST listar CATs: %s", exc)
        cats = []
    return {"total": len(cats), "cats": cats}


@router.get("/cat/taxa-acidente")
async def calcular_taxa_acidente(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Calcula taxa de acidente de trabalho no periodo."""
    from sqlalchemy import text as sql_text

    total_colab = 0
    try:
        r = await db.execute(sql_text("SELECT count(*) FROM employees WHERE status = 'ativo'"))
        total_colab = r.scalar() or 0
    except Exception as exc:
        logger.warning("SST dashboard: falha ao contar employees: %s", exc)

    total_cats = 0
    try:
        r = await db.execute(sql_text("SELECT count(*) FROM gp_cats"))
        total_cats = r.scalar() or 0
    except Exception as exc:
        logger.warning("SST dashboard: falha ao contar CATs: %s", exc)

    service = SSTService(db)
    dashboard = await service.get_dashboard()
    afastados = dashboard["afastados_ativos"]
    taxa = round((total_cats / total_colab * 100) if total_colab > 0 else 0, 2)

    return {
        "total_colaboradores": total_colab,
        "total_cats": total_cats,
        "afastados_ativos": afastados,
        "taxa_acidente_percentual": taxa,
        "periodo": "2026",
    }


# ================================================================
# ASO CRUD (endpoints originais preservados)
# ================================================================


@router.post("/aso", status_code=201)
async def agendar_aso(
    data: ASOCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Agenda um ASO."""
    from modules.people_management.sst.models.aso import ASOModel

    aso = ASOModel(
        aso_id=str(uuid4()),
        employee_id=data.employee_id,
        tipo=data.tipo,
        data_agendamento=data.data_agendamento,
        clinica=data.clinica,
        status="agendado",
    )
    db.add(aso)
    await db.flush()
    return {
        "aso_id": aso.aso_id,
        "employee_id": aso.employee_id,
        "tipo": data.tipo,
        "status": "agendado",
        "data_agendamento": data.data_agendamento,
    }


@router.get("/aso")
async def listar_asos(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str | None = Query(None),
) -> Any:
    """Lista ASOs."""
    from sqlalchemy import text as sql_text

    try:
        query = "SELECT aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, apto FROM gp_asos"
        params: dict[str, Any] = {}
        if employee_id:
            query += " WHERE employee_id = :eid"
            params["eid"] = employee_id
        query += " ORDER BY data_agendamento DESC"
        result = await db.execute(sql_text(query), params)
        asos = [
            {
                "aso_id": r[0],
                "employee_id": r[1],
                "tipo": r[2],
                "status": r[3],
                "data_agendamento": str(r[4]) if r[4] else None,
                "data_realizacao": str(r[5]) if r[5] else None,
                "apto": r[6],
            }
            for r in result.fetchall()
        ]
    except Exception as exc:
        logger.warning("SST listar ASOs: %s", exc)
        asos = []
    return {"total": len(asos), "asos": asos}


@router.put("/aso/{aso_id}/resultado")
async def registrar_resultado_aso(
    aso_id: str,
    data: ASOResultUpdate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Registra resultado de ASO realizado."""
    from sqlalchemy import text as sql_text

    try:
        await db.execute(
            sql_text(
                "UPDATE gp_asos SET apto = :apto, restricoes = :rest, medico = :med, "
                "crm = :crm, status = 'realizado', data_realizacao = CURRENT_DATE "
                "WHERE aso_id = :aid"
            ),
            {"apto": data.apto, "rest": str(data.restricoes), "med": data.medico, "crm": data.crm, "aid": aso_id},
        )
        await db.commit()
        return {"aso_id": aso_id, "status": "realizado", "apto": data.apto}
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"ASO nao encontrado: {exc}") from exc


# ================================================================
# EPI CRUD (endpoints originais preservados)
# ================================================================


@router.post("/epi", status_code=201)
async def registrar_entrega_epi(
    data: EPIDeliveryCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Registra entrega de EPI."""
    from modules.people_management.sst.models.epi import EPIDeliveryModel

    epi = EPIDeliveryModel(
        delivery_id=str(uuid4()),
        employee_id=data.employee_id,
        epi_nome=data.epi_nome,
        quantidade=data.quantidade,
        epi_ca=data.epi_ca,
        data_entrega=date.today(),
    )
    db.add(epi)
    await db.flush()
    return {
        "delivery_id": epi.delivery_id,
        "employee_id": epi.employee_id,
        "epi": data.epi_nome,
        "quantidade": data.quantidade,
        "data_entrega": str(epi.data_entrega) if hasattr(epi, "data_entrega") else None,
        "status": "entregue",
    }


@router.get("/epi")
async def listar_epis(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str | None = Query(None),
) -> Any:
    """Lista entregas de EPI."""
    from sqlalchemy import text as sql_text

    try:
        query = "SELECT delivery_id, employee_id, epi_nome, quantidade, epi_ca, nr FROM gp_epi_deliveries"
        params: dict[str, Any] = {}
        if employee_id:
            query += " WHERE employee_id = :eid"
            params["eid"] = employee_id
        result = await db.execute(sql_text(query), params)
        epis = [
            {"delivery_id": r[0], "employee_id": r[1], "epi": r[2], "quantidade": r[3], "ca": r[4], "status": r[5]}
            for r in result.fetchall()
        ]
    except Exception as exc:
        logger.warning("SST listar EPIs: %s", exc)
        epis = []
    return {"total": len(epis), "epis": epis}


# ================================================================
# RISCOS CRUD (endpoints originais preservados)
# ================================================================


@router.post("/risco", status_code=201)
async def mapear_risco(
    data: RiskCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Mapeia um risco ocupacional."""
    from modules.people_management.sst.models.risk import RiskModel

    risco = RiskModel(
        risk_id=str(uuid4()),
        posto_id=data.posto_id,
        categoria=data.categoria,
        descricao=data.descricao,
        nivel=data.nivel,
        status="identificado",
    )
    db.add(risco)
    await db.flush()
    return {
        "risk_id": risco.risk_id,
        "posto_id": risco.posto_id,
        "categoria": data.categoria,
        "descricao": data.descricao,
        "nivel": data.nivel,
        "status": "identificado",
    }


@router.get("/riscos")
async def listar_riscos(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    posto_id: str | None = Query(None),
) -> Any:
    """Lista riscos ocupacionais."""
    from sqlalchemy import text as sql_text

    try:
        query = "SELECT risk_id, posto_id, categoria, descricao, nivel, status FROM gp_risks"
        params: dict[str, Any] = {}
        if posto_id:
            query += " WHERE posto_id = :pid"
            params["pid"] = posto_id
        result = await db.execute(sql_text(query), params)
        riscos = [
            {"risk_id": r[0], "posto_id": r[1], "categoria": r[2], "descricao": r[3], "nivel": r[4], "status": r[5]}
            for r in result.fetchall()
        ]
    except Exception as exc:
        logger.warning("SST listar riscos: %s", exc)
        riscos = []
    return {"total": len(riscos), "riscos": riscos}


# ================================================================
# ESTABILIDADE (CCT Clausula 29a)
# ================================================================


@router.get("/estabilidade/ativos")
async def listar_estabilidade_ativos(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Colaboradores em estabilidade pos-acidente (CCT 2026 Clausula 29a)."""
    service = SSTService(db)
    items = await service.listar_estabilidade_ativos()
    return {"total": len(items), "colaboradores": items}


# ================================================================
# AJUDA MEDICAMENTO (CCT Clausula 15a)
# ================================================================


@router.get("/ajuda-medicamento/ativos")
async def listar_ajuda_medicamento(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Colaboradores recebendo ajuda medicamento R$ 300/mes (CCT 2026)."""
    service = SSTService(db)
    items = await service.listar_ajuda_medicamento_ativos()
    return {
        "total": len(items),
        "valor_unitario": 300.00,
        "custo_mensal_total": round(len(items) * 300.00, 2),
        "clausula_cct": "15a — Ajuda medicamento ate R$ 300/mes (acidente trabalho)",
        "colaboradores": items,
    }


# ================================================================
# CIPA (NR-5)
# ================================================================


@router.get("/cipa/membros")
async def listar_cipa_membros(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista membros da CIPA."""
    from sqlalchemy import text as sql_text

    try:
        result = await db.execute(
            sql_text(
                "SELECT membro_id, employee_id, employee_nome, funcao, representacao, "
                "data_posse, data_fim_mandato, status FROM sst_cipa_membros "
                "WHERE status = 'ativo' ORDER BY funcao"
            )
        )
        membros = [
            {
                "membro_id": r[0],
                "employee_id": r[1],
                "nome": r[2],
                "funcao": r[3],
                "representacao": r[4],
                "data_posse": str(r[5]) if r[5] else None,
                "data_fim_mandato": str(r[6]) if r[6] else None,
                "status": r[7],
            }
            for r in result.fetchall()
        ]
    except Exception as exc:
        logger.warning("SST listar membros CIPA: %s", exc)
        membros = []
    return {"total": len(membros), "membros": membros}


@router.get("/cipa/reunioes")
async def listar_cipa_reunioes(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista reunioes da CIPA."""
    from sqlalchemy import text as sql_text

    try:
        result = await db.execute(
            sql_text(
                "SELECT reuniao_id, data_reuniao, tipo, pauta, status FROM sst_cipa_reunioes ORDER BY data_reuniao DESC"
            )
        )
        reunioes = [
            {"reuniao_id": r[0], "data": str(r[1]), "tipo": r[2], "pauta": r[3], "status": r[4]}
            for r in result.fetchall()
        ]
    except Exception as exc:
        logger.warning("SST listar reunioes CIPA: %s", exc)
        reunioes = []
    return {"total": len(reunioes), "reunioes": reunioes}


@router.post("/cipa/reunioes", status_code=201)
async def registrar_reuniao_cipa(
    data: dict,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Registra reuniao da CIPA."""
    from sqlalchemy import text as sql_text

    reuniao_id = str(uuid4())
    data_reuniao = date.fromisoformat(data.get("data_reuniao"))
    await db.execute(
        sql_text(
            "INSERT INTO sst_cipa_reunioes (reuniao_id, data_reuniao, tipo, pauta, status, created_at) "
            "VALUES (:rid, :data, :tipo, :pauta, :status, NOW())"
        ),
        {
            "rid": reuniao_id,
            "data": data_reuniao,
            "tipo": data.get("tipo", "ordinaria"),
            "pauta": data.get("pauta", ""),
            "status": "agendada",
        },
    )
    await db.commit()
    return {"reuniao_id": reuniao_id, "status": "agendada"}


# =============================================================================
# LTCAT — Laudo Técnico das Condições Ambientais de Trabalho
# =============================================================================


@router.get("/ltcat/status")
async def ltcat_status(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Retorna status do LTCAT vigente."""
    result = await db.execute(text("SELECT count(*) FROM posts WHERE is_active = true"))
    total_postos = result.scalar() or 0

    return {
        "documento": "LTCAT - Laudo Técnico das Condições Ambientais de Trabalho",
        "base_legal": "Lei 8.213/91 Art. 58 + IN INSS 128/2022",
        "empresa": "CONECTAMAIS ELETRONICA LTDA",
        "cnpj": "35.710.481/0001-03",
        "vigencia": "2026-01-01 a 2026-12-31",
        "responsavel_tecnico": "A definir (Engenheiro de Segurança)",
        "postos_avaliados": total_postos,
        "status": "pendente_elaboracao",
        "fatores_risco": [
            {"agente": "Ruído", "tipo": "físico", "nr_referencia": "NR-15 Anexo 1"},
            {"agente": "Calor", "tipo": "físico", "nr_referencia": "NR-15 Anexo 3"},
            {"agente": "Jornada prolongada", "tipo": "ergonômico", "nr_referencia": "NR-17"},
            {"agente": "Risco de agressão", "tipo": "acidente", "nr_referencia": "NR-1"},
        ],
        "proxima_acao": "Contratar engenheiro de segurança para elaboração",
    }


@router.get("/ppp/{employee_id}")
async def gerar_ppp(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Gera PPP (Perfil Profissiográfico Previdenciário) de um funcionário.

    Documento obrigatório conforme Lei 8.213/91 Art. 58 e IN INSS 128/2022.
    Alimenta o evento S-2240 do eSocial.
    """
    # Buscar dados do funcionário
    result = await db.execute(
        text("SELECT id, nome, cpf, cargo, data_admissao, data_demissao FROM employees WHERE id = :eid"),
        {"eid": employee_id},
    )
    emp = result.mappings().first()
    if not emp:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Funcionário não encontrado")

    # Buscar ASOs
    asos_result = await db.execute(
        text(
            "SELECT tipo, data_agendamento, status FROM gp_asos WHERE employee_id = :eid ORDER BY data_agendamento DESC LIMIT 5"
        ),
        {"eid": employee_id},
    )
    asos = [dict(r) for r in asos_result.mappings().all()]

    return {
        "documento": "PPP - Perfil Profissiográfico Previdenciário",
        "base_legal": "Lei 8.213/91 Art. 58 § 4º + IN INSS 128/2022",
        "esocial_evento": "S-2240",
        "empresa": {
            "razao_social": "CONECTAMAIS ELETRONICA LTDA",
            "cnpj": "35.710.481/0001-03",
            "cnae": "8011-1/01 - Atividades de vigilância e segurança privada",
        },
        "funcionario": {
            "nome": emp["nome"],
            "cpf": emp["cpf"],
            "cargo": emp["cargo"],
            "data_admissao": str(emp["data_admissao"]) if emp["data_admissao"] else None,
            "data_demissao": str(emp["data_demissao"]) if emp["data_demissao"] else None,
        },
        "atividades": [
            {
                "periodo": f"{emp['data_admissao'] or 'admissão'} até presente",
                "cargo": emp["cargo"],
                "setor": "Operacional",
                "descricao": "Atividades de vigilância, controle de acesso e ronda patrimonial",
            }
        ],
        "fatores_risco": [
            {
                "agente": "Jornada prolongada",
                "tipo": "ergonômico",
                "intensidade": "Habitual",
                "tecnica_utilizada": "Avaliação qualitativa NR-17",
                "epi_epc": "N/A",
            },
            {
                "agente": "Risco de agressão",
                "tipo": "acidente",
                "intensidade": "Eventual",
                "tecnica_utilizada": "Análise preliminar de risco",
                "epi_epc": "Colete balístico (quando aplicável)",
            },
        ],
        "exames_medicos": asos,
        "responsavel_tecnico": {
            "nome": "A definir",
            "registro": "CREA/CRM",
            "especialidade": "Engenharia de Segurança / Medicina do Trabalho",
        },
        "observacoes": "PPP deve ser mantido atualizado e entregue ao funcionário na rescisão (Art. 58 § 4º Lei 8.213/91).",
    }
