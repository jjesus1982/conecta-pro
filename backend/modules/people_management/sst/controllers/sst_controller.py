"""Controller SST — Endpoints completos com wiring real.

Endpoints:
- GET  /sst/dashboard
- GET  /sst/afastamentos
- POST /sst/afastamentos                  (gatilho eSocial S-2230)
- GET  /sst/afastamentos/{id}
- PUT  /sst/afastamentos/{id}/retorno     (gatilho eSocial S-2230 término)
- GET  /sst/nr1/dashboard
- GET  /sst/nr1/colaboradores-risco
- GET  /sst/nr1/compliance                (painel "calçado NR-1" por funcionário)
- GET  /sst/nr1/compliance/pdf            (relatório padrão-ouro p/ auditor fiscal)
- GET  /sst/pcmso/status
- GET  /sst/pcmso/esteira                 (esteira PREVENTIVA — projeção 12m dos periódicos)
- GET  /sst/ppra/status
- GET  /sst/asos/vencendo
- GET  /sst/asos/sem-aso
- GET  /sst/asos/regularizacao            (plano das ASOs vencidas, priorizado)
- POST /sst/asos/agendar-lote             (agendamento em massa p/ regularização)
- POST /sst/treinamentos                  (4º pilar NR-1 — treinamento realizado)
- GET  /sst/treinamentos                  (filtros: employee_id, norma, vencendo_em_dias)
- DELETE /sst/treinamentos/{id}
- POST /sst/cat                           (gatilho eSocial S-2210 + prazo 1 dia útil)
- POST /sst/cat/{cat_id}/transmitir       (botão Transmitir ao eSocial)
- PUT  /sst/aso/{id}/resultado            (gatilho eSocial S-2220)
- POST /sst/aso/{id}/anexo                (upload do ASO digitalizado — PDF/JPG/PNG, max 10MB)
- GET  /sst/aso/{id}/anexo                (download do documento; 404 honesto se nao anexado)
- POST /sst/aso/retroativo                (carga retroativa: exame em papel pre-sistema; ANEXO OBRIGATORIO)
- POST /sst/epi                           (gera FICHA DE EPI pendente de assinatura)
- POST /sst/epi/fichas/gerar
- GET  /sst/epi/fichas
- GET  /sst/epi/fichas/minhas             (Portal do Funcionário)
- GET  /sst/epi/fichas/{id}/pdf
- POST /sst/epi/fichas/{id}/assinar       (assinatura digital do FUNCIONÁRIO)
- GET  /sst/ltcat/status                  (fonte real: sst_ltcat)
- PUT  /sst/ltcat
- GET  /sst/ppp/{employee_id}?transmit=true (S-2240 real)
- GET  /sst/ppp/{employee_id}/pdf         (PPP padrão-ouro — doc oficial p/ INSS)
- GET  /sst/prontuario/{employee_id}      (Prontuário SST 360 — dossiê completo)
- GET  /sst/estabilidade/ativos
- GET  /sst/ajuda-medicamento/ativos
- GET  /sst/cipa/membros
- GET  /sst/cipa/reunioes
- POST /sst/cipa/reunioes
"""

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.employee_portal.auth import CurrentEmployeeId
from modules.people_management.sst.schemas.sst_schemas import (
    ASO_TIPOS_VALIDOS,
    ASOAgendarLoteItem,
    ASOCreate,
    ASOResultUpdate,
    CATCreate,
    EPIDeliveryCreate,
    RiskCreate,
    TreinamentoNRCreate,
)
from modules.people_management.sst.services.ficha_epi_service import FichaEPIService
from modules.people_management.sst.services.sst_service import SSTService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sst", tags=["SST — Saude e Seguranca do Trabalho"])

# Tipos de afastamento com código na Tabela 18 do eSocial (S-2230) — os demais
# exigem classificação humana e NÃO são enfileirados (honestidade > automação)
_TIPOS_S2230_MAPEAVEIS = {"doenca", "acidente_trabalho", "acidente_trajeto", "licenca_maternidade"}


def _proximo_dia_util(d: date) -> date:
    """Próximo dia útil após d (sáb/dom pulados; feriados nacionais não modelados)."""
    nd = d + timedelta(days=1)
    while nd.weekday() >= 5:
        nd += timedelta(days=1)
    return nd


def _enfileirar_transmissao(task: Any, ref_id: str, evento: str) -> dict[str, Any]:
    """Enfileira a transmissão eSocial via Celery (fila gov.esocial).

    HONESTO: a resposta informa apenas que a transmissão foi ENFILEIRADA —
    protocolo/recibo REAIS são gravados pela task e pelo pull de recibos.
    NUNCA dizemos 'enviado' sem recibo/protocolo real.
    """
    try:
        r = task.delay(str(ref_id))
        return {
            "evento": evento,
            "transmissao_enfileirada": True,
            "task_id": str(r.id),
            "nota": (
                "Transmissão ENFILEIRADA (fila gov.esocial). Protocolo/recibo reais "
                "serão gravados pela task e pelo beat esocial-pull-recibos."
            ),
        }
    except Exception as exc:  # broker indisponível etc. — nunca fingir sucesso
        logger.error("Enfileiramento %s (%s) falhou: %s", evento, ref_id, exc)
        return {"evento": evento, "transmissao_enfileirada": False, "erro": str(exc)}


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


@router.get("/calendario-legal")
async def get_calendario_legal(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Calendário Legal SST — radar único de TODOS os vencimentos legais.

    Agrega PCMSO, LTCAT, PGR, CAs dos EPIs do catálogo, treinamentos NR,
    ASOs e fichas de EPI pendentes — tudo por FATO no banco (itens sem data
    aparecem como 'sem_data', honestos, nunca fabricados).
    """
    from modules.people_management.sst.services.calendario_legal_service import (
        montar_calendario_legal,
    )

    return await montar_calendario_legal(db)


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
    """Registra novo afastamento com regras CCT 2026 automaticas.

    GATILHO eSocial: tipos mapeáveis na Tabela 18 (doenca, acidente_trabalho,
    acidente_trajeto, licenca_maternidade) enfileiram o S-2230 automaticamente.
    """
    service = SSTService(db)
    result = await service.registrar_afastamento(data)
    await db.commit()

    tipo = str(result.get("tipo") or "").lower()
    if tipo in _TIPOS_S2230_MAPEAVEIS:
        from modules.people_management.sst.tasks.esocial_tasks import (
            transmit_afastamento_to_esocial,
        )

        result["esocial"] = _enfileirar_transmissao(
            transmit_afastamento_to_esocial, result["id"], "S-2230"
        )
    else:
        result["esocial"] = {
            "evento": "S-2230",
            "transmissao_enfileirada": False,
            "motivo": (
                f"Tipo '{tipo}' sem código na Tabela 18 do eSocial — classificação "
                "humana necessária (não será fabricada)."
            ),
        }
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
    """Registra retorno de afastamento (calcula estabilidade CCT).

    GATILHO eSocial: RE-TRANSMITE o S-2230, que agora inclui <fimAfastamento>
    (comportamento do gerador quando status=encerrado — S-2230 de término).
    """
    service = SSTService(db)
    result = await service.registrar_retorno(afastamento_id, data.get("data_retorno", ""))
    if not result:
        raise HTTPException(status_code=404, detail="Afastamento nao encontrado")
    await db.commit()

    tipo = str(result.get("tipo") or "").lower()
    if tipo in _TIPOS_S2230_MAPEAVEIS:
        from modules.people_management.sst.tasks.esocial_tasks import (
            transmit_afastamento_to_esocial,
        )

        result["esocial"] = _enfileirar_transmissao(
            transmit_afastamento_to_esocial, afastamento_id, "S-2230 (término/fimAfastamento)"
        )
    else:
        result["esocial"] = {
            "evento": "S-2230",
            "transmissao_enfileirada": False,
            "motivo": f"Tipo '{tipo}' sem código na Tabela 18 do eSocial.",
        }
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


@router.get("/nr1/compliance")
async def get_nr1_compliance(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Painel 'CALÇADO NR-1' por funcionário ativo — score HONESTO.

    Checks por funcionário: ASO em dia (vencimento real), EPIs com ficha
    ASSINADA digitalmente, exposição a riscos mapeada (gp_risks) e
    treinamentos NR (só se houver tabela — guard). Inclui os ASOs vencidos
    como pendência visível. 'Calçado' = todos os checks aplicáveis OK.
    """
    service = SSTService(db)
    return await service.get_nr1_compliance()


@router.get("/nr1/compliance/pdf")
async def get_nr1_compliance_pdf(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Relatório de Compliance NR-1 em PDF padrão-ouro (marca Conecta Mais).

    Snapshot do painel get_nr1_compliance (resumo geral + tabela por
    funcionário: ASO/EPI/Riscos/Treinamentos/score/situação) com data/hora
    de emissão — para entregar a auditor fiscal.
    """
    from modules.people_management.sst.services.nr1_compliance_pdf import montar_nr1_compliance_pdf

    service = SSTService(db)
    compliance = await service.get_nr1_compliance()
    pdf = montar_nr1_compliance_pdf(compliance)
    nome = f"compliance-nr1-{date.today().isoformat()}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nome}"'},
    )


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


@router.get("/pcmso/esteira")
async def get_pcmso_esteira(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    horizonte_meses: int = Query(12, ge=1, le=24, description="Horizonte da projeção em meses"),
) -> Any:
    """Esteira PCMSO Preventiva — agenda projetada dos exames periódicos.

    Para CADA funcionário ativo: último ASO realizado → próximo vencimento
    (12 meses, NR-7); sem ASO → pendente imediato. Inclui os exames previstos
    da função (sst_pcmso.exames_por_funcao) e resumos por mês e por posto.
    Projeção calculada AO VIVO — NADA é gravado (fonte da verdade = gp_asos).
    """
    from modules.people_management.sst.services.esteira_pcmso_service import (
        EsteiraPCMSOService,
    )

    service = EsteiraPCMSOService(db)
    return await service.projetar_agenda(horizonte_meses)


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
# REGULARIZAÇÃO DE ASOs VENCIDAS
# ================================================================


@router.get("/asos/regularizacao")
async def listar_asos_regularizacao(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Plano de regularização das ASOs vencidas — lista priorizada.

    Mais vencido primeiro, com dias_vencido, posto atual REAL (allocations →
    posts, para logística das clínicas), flag ja_agendado e resumo por posto.
    NADA aqui marca ASO como ok — regularizar = agendar + realizar de verdade.
    """
    service = SSTService(db)
    return await service.listar_asos_regularizacao()


@router.post("/asos/agendar-lote", status_code=201)
async def agendar_asos_lote(
    itens: list[ASOAgendarLoteItem],
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Agenda ASOs em massa (regularização) — reusa a lógica do POST /sst/aso.

    Cada item vira um gp_asos status='agendado'. HONESTO: agendar NÃO
    regulariza — o ASO só fica em dia após registrar o resultado (realizado).
    """
    from modules.people_management.sst.models.aso import ASOModel

    if not itens:
        raise HTTPException(status_code=422, detail="Lista de agendamentos vazia")

    hoje = date.today()
    agendados: list[dict[str, Any]] = []
    erros: list[dict[str, Any]] = []
    for item in itens:
        if item.tipo not in ASO_TIPOS_VALIDOS:
            erros.append({"employee_id": item.employee_id, "erro": f"tipo inválido '{item.tipo}'"})
            continue
        try:
            dt = date.fromisoformat(item.data_agendamento[:10])
        except ValueError:
            erros.append({"employee_id": item.employee_id, "erro": "data_agendamento inválida (YYYY-MM-DD)"})
            continue
        if dt < hoje:
            erros.append({"employee_id": item.employee_id, "erro": "data_agendamento no passado"})
            continue
        emp = (
            await db.execute(
                text("SELECT nome FROM employees WHERE id::text = :eid"),
                {"eid": item.employee_id},
            )
        ).first()
        if not emp:
            erros.append({"employee_id": item.employee_id, "erro": "funcionário não encontrado"})
            continue
        aso = ASOModel(
            aso_id=str(uuid4()),
            employee_id=item.employee_id,
            tipo=item.tipo,
            data_agendamento=dt,
            clinica=item.clinica,
            status="agendado",
        )
        db.add(aso)
        agendados.append(
            {
                "aso_id": aso.aso_id,
                "employee_id": item.employee_id,
                "employee_nome": emp[0],
                "tipo": item.tipo,
                "data_agendamento": item.data_agendamento,
                "clinica": item.clinica,
                "status": "agendado",
            }
        )
    if agendados:
        await db.flush()
        await db.commit()

    return {
        "total_recebidos": len(itens),
        "total_agendados": len(agendados),
        "total_erros": len(erros),
        "agendados": agendados,
        "erros": erros,
        "nota": "Agendamento em lote NÃO regulariza — registre o resultado (realizado) após o exame.",
    }


# ================================================================
# TREINAMENTOS NR (sst_treinamentos) — 4º pilar do compliance NR-1
# ================================================================


@router.post("/treinamentos", status_code=201)
async def registrar_treinamento(
    data: TreinamentoNRCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Registra treinamento NR REALIZADO (NR-1, NR-6, brigada, 1ºs socorros).

    vencimento = data_realizacao + validade_meses (calculado, nunca digitado).
    Dado real: só registre treinamentos que aconteceram (data futura é barrada).
    """
    service = SSTService(db)
    try:
        return await service.criar_treinamento(
            data.model_dump(),
            created_by=getattr(current_user, "email", None) or getattr(current_user, "username", None),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/treinamentos")
async def listar_treinamentos(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    employee_id: str | None = Query(None),
    norma: str | None = Query(None, description="NR-1|NR-6|brigada|primeiros_socorros|outro"),
    vencendo_em_dias: int | None = Query(
        None, ge=0, le=365,
        description="Só vencidos + os que vencem nos próximos N dias",
    ),
) -> Any:
    """Lista treinamentos NR (fonte real: sst_treinamentos) com situação calculada."""
    service = SSTService(db)
    items = await service.listar_treinamentos(employee_id, norma, vencendo_em_dias)
    return {
        "total": len(items),
        "em_dia": sum(1 for t in items if t["situacao"] == "em_dia"),
        "vencendo_30d": sum(1 for t in items if t["situacao"] == "vencendo"),
        "vencidos": sum(1 for t in items if t["situacao"] == "vencido"),
        "treinamentos": items,
    }


@router.delete("/treinamentos/{treinamento_id}")
async def excluir_treinamento(
    treinamento_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Exclui um registro de treinamento (correção de lançamento errado)."""
    service = SSTService(db)
    if not await service.excluir_treinamento(treinamento_id):
        raise HTTPException(status_code=404, detail="Treinamento não encontrado")
    return {"id": treinamento_id, "excluido": True}


# ================================================================
# CAT
# ================================================================


@router.post("/cat", status_code=201)
async def abrir_cat(
    data: CATCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Abre CAT (Comunicacao de Acidente de Trabalho).

    GATILHO eSocial: enfileira a transmissão do S-2210 (fila gov.esocial).
    PRAZO LEGAL: a CAT deve ser comunicada até o 1º dia útil após o acidente
    (Lei 8.213/91 Art. 22) — deadline_transmissao calculado e retornado.
    """
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
    await db.commit()  # a task Celery lê a CAT em outro processo — precisa estar persistida

    from modules.people_management.sst.tasks.esocial_tasks import transmit_cat_to_esocial

    deadline = _proximo_dia_util(cat.data_acidente) if cat.data_acidente else None
    return {
        "cat_id": cat.cat_id,
        "employee_id": cat.employee_id,
        "tipo": cat.tipo_acidente,
        "data": str(cat.data_acidente),
        "local": cat.local,
        "gravidade": cat.gravidade,
        "status": cat.status,
        "esocial_status": cat.esocial_status,
        "deadline_transmissao": str(deadline) if deadline else None,
        "prazo_legal": (
            "CAT: 1 dia útil após o acidente (Lei 8.213/91 Art. 22). "
            "Cálculo pula sáb/dom; feriados nacionais não modelados."
        ),
        "esocial": _enfileirar_transmissao(transmit_cat_to_esocial, cat.cat_id, "S-2210"),
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
        query = (
            "SELECT cat_id, employee_id, tipo_acidente, data_acidente, local, gravidade, status, "
            "esocial_status, numero_recibo_esocial, esocial_protocolo, esocial_transmitida_em FROM gp_cats"
        )
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
                "esocial_status": r[7],
                "recibo_esocial": r[8],
                "esocial_protocolo": r[9],
                "esocial_transmitida_em": str(r[10]) if r[10] else None,
                "deadline_transmissao": str(_proximo_dia_util(r[3])) if r[3] else None,
            }
            for r in result.fetchall()
        ]
    except Exception as exc:
        logger.warning("SST listar CATs: %s", exc)
        cats = []
    return {"total": len(cats), "cats": cats}


@router.post("/cat/{cat_id}/transmitir")
async def transmitir_cat(
    cat_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Botão 'Transmitir ao eSocial' — (re)enfileira o S-2210 da CAT.

    Útil para reprocessar CATs com esocial_status='erro'/'rejeitada' após
    correção do dado. Resposta honesta: apenas ENFILEIRA (recibo real vem depois).
    """
    row = (
        await db.execute(
            text("SELECT cat_id, esocial_status, numero_recibo_esocial FROM gp_cats WHERE cat_id = :c"),
            {"c": cat_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="CAT nao encontrada")
    if row[2]:
        return {
            "cat_id": cat_id,
            "esocial_status": row[1],
            "recibo_esocial": row[2],
            "esocial": {
                "evento": "S-2210",
                "transmissao_enfileirada": False,
                "motivo": "CAT já possui recibo REAL do eSocial — nada a retransmitir.",
            },
        }

    from modules.people_management.sst.tasks.esocial_tasks import transmit_cat_to_esocial

    return {
        "cat_id": cat_id,
        "esocial_status": row[1],
        "esocial": _enfileirar_transmissao(transmit_cat_to_esocial, cat_id, "S-2210"),
    }


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
        query = (
            "SELECT aso_id, employee_id, tipo, status, data_agendamento, data_realizacao, apto, "
            "esocial_status, recibo_s2220, esocial_protocolo, arquivo_nome, retroativo FROM gp_asos"
        )
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
                "esocial_status": r[7],
                "recibo_s2220": r[8],
                "esocial_protocolo": r[9],
                "arquivo_nome": r[10],
                "retroativo": bool(r[11]),
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
    """Registra resultado de ASO realizado.

    GATILHO eSocial: status vira 'realizado' → enfileira o S-2220 (Monitoramento
    da Saúde do Trabalhador) na fila gov.esocial.
    """
    from sqlalchemy import text as sql_text

    try:
        result = await db.execute(
            sql_text(
                "UPDATE gp_asos SET apto = :apto, restricoes = :rest, medico = :med, "
                "crm = :crm, status = 'realizado', data_realizacao = CURRENT_DATE "
                "WHERE aso_id = :aid"
            ),
            {"apto": data.apto, "rest": str(data.restricoes), "med": data.medico, "crm": data.crm, "aid": aso_id},
        )
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="ASO nao encontrado")
        await db.commit()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"ASO nao encontrado: {exc}") from exc

    from modules.people_management.sst.tasks.esocial_tasks import transmit_aso_to_esocial

    return {
        "aso_id": aso_id,
        "status": "realizado",
        "apto": data.apto,
        "esocial": _enfileirar_transmissao(transmit_aso_to_esocial, aso_id, "S-2220"),
    }


# ================================================================
# ANEXO DO ASO (documento digitalizado) + CARGA RETROATIVA
# ================================================================
# Fato de negócio (CEO): TODOS os funcionários fizeram exames admissionais
# antes de contratar — em PAPEL, pré-sistema. "Sem ASO" no compliance =
# documento não digitalizado, não exame não feito. Daqui pra frente o papel
# sobe digitalizado (anexo) e o histórico entra pela carga retroativa.

_ASO_UPLOAD_DIR = "/app/uploads/asos"  # volume ./uploads — persiste ao recreate
_ASO_ANEXO_TIPOS = {
    ".pdf": "application/pdf",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}
_ASO_ANEXO_MAX_BYTES = 10 * 1024 * 1024  # 10MB


def _somar_meses(d: date, meses: int) -> date:
    """Soma meses preservando o dia (clampa no fim do mês — 31/jan+1m=28/fev)."""
    import calendar

    total = d.month - 1 + meses
    ano, mes = d.year + total // 12, total % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def _gravar_anexo_aso(aso_id: str, nome_original: str, conteudo: bytes) -> tuple[str, str]:
    """Valida e grava o anexo em /app/uploads/asos/{aso_id}.{ext}.

    Retorna (arquivo_path, arquivo_nome). 422 honesto para tipo/tamanho
    inválido. Dir criado com dono erp:erp (best-effort — volume pode nascer root).
    """
    import os
    import re
    import shutil

    if not re.fullmatch(r"[A-Za-z0-9-]{1,64}", aso_id):  # uuid4 — nunca vira path traversal
        raise HTTPException(status_code=422, detail="aso_id invalido")

    ext = os.path.splitext(nome_original)[1].lower()
    if ext not in _ASO_ANEXO_TIPOS:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo de arquivo nao aceito ({ext or 'sem extensao'}) — envie PDF, JPG ou PNG",
        )
    if len(conteudo) == 0:
        raise HTTPException(status_code=422, detail="Arquivo vazio — digitalize o ASO e tente de novo")
    if len(conteudo) > _ASO_ANEXO_MAX_BYTES:
        raise HTTPException(
            status_code=422,
            detail=f"Arquivo com {len(conteudo) / (1024 * 1024):.1f}MB — o limite e 10MB",
        )

    os.makedirs(_ASO_UPLOAD_DIR, exist_ok=True)
    caminho = os.path.join(_ASO_UPLOAD_DIR, f"{aso_id}{ext}")
    with open(caminho, "wb") as fh:
        fh.write(conteudo)
    for alvo in (_ASO_UPLOAD_DIR, caminho):
        try:
            shutil.chown(alvo, user="erp", group="erp")
        except (LookupError, PermissionError, OSError):
            pass  # fora do container não existe user erp — não é erro
    return caminho, nome_original[:255]


@router.post("/aso/retroativo", status_code=201)
async def carga_retroativa_aso(
    current_user: CurrentActiveUser,
    employee_id: str = Form(...),
    tipo: str = Form("admissional"),
    data_realizacao: date = Form(...),
    clinica: str | None = Form(None),
    medico: str | None = Form(None),
    crm: str | None = Form(None),
    apto: bool = Form(True),
    file: UploadFile | None = File(None),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Carga retroativa de ASO feito em PAPEL antes do sistema.

    Cria gp_asos status='realizado', retroativo=true, data_validade=+12 meses
    (admissional/periodico zeram o relógio NR-7). ANEXO OBRIGATÓRIO no mesmo
    multipart — sem o documento digitalizado não há prova, não há registro.
    Conta normalmente no compliance NR-1 (é gp_asos realizado com validade).
    """
    if file is None:
        raise HTTPException(
            status_code=422,
            detail=(
                "Carga retroativa exige o documento digitalizado — o exame foi feito "
                "em papel; sem o anexo nao ha prova (doutrina: nunca registrar fato sem documento)"
            ),
        )
    if tipo not in ASO_TIPOS_VALIDOS:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo invalido '{tipo}' — validos: {', '.join(ASO_TIPOS_VALIDOS)}",
        )
    if data_realizacao > date.today():
        raise HTTPException(
            status_code=422,
            detail="Carga retroativa e para exame JA realizado — data_realizacao nao pode ser futura",
        )

    emp_nome = (
        await db.execute(text("SELECT nome FROM employees WHERE id::text = :eid"), {"eid": employee_id})
    ).scalar()
    if not emp_nome:
        raise HTTPException(status_code=404, detail="Funcionario nao encontrado")

    # NR-7: exame clínico zera o relógio — validade 12 meses (demissional não gera validade)
    data_validade = None if tipo == "demissional" else _somar_meses(data_realizacao, 12)

    from modules.people_management.sst.models.aso import ASOModel

    aso_id = str(uuid4())
    conteudo = await file.read()
    caminho, nome_arquivo = _gravar_anexo_aso(aso_id, file.filename or "documento", conteudo)

    aso = ASOModel(
        aso_id=aso_id,
        employee_id=employee_id,
        tipo=tipo,
        status="realizado",
        data_realizacao=data_realizacao,
        data_validade=data_validade,
        clinica=clinica,
        medico=medico,
        crm=crm,
        apto=apto,
        retroativo=True,
        arquivo_path=caminho,
        arquivo_nome=nome_arquivo,
        arquivo_subido_em=datetime.now(UTC),
    )
    db.add(aso)
    await db.commit()

    return {
        "aso_id": aso_id,
        "employee_id": employee_id,
        "employee_nome": emp_nome,
        "tipo": tipo,
        "status": "realizado",
        "retroativo": True,
        "data_realizacao": str(data_realizacao),
        "data_validade": str(data_validade) if data_validade else None,
        "arquivo_nome": nome_arquivo,
        "esocial": {
            "transmissao_enfileirada": False,
            "motivo": (
                "ASO retroativo (papel, pre-sistema) — S-2220 nao e enfileirado "
                "automaticamente; transmissao de historico e decisao humana"
            ),
        },
    }


@router.post("/aso/{aso_id}/anexo", status_code=201)
async def anexar_documento_aso(
    aso_id: str,
    current_user: CurrentActiveUser,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Anexa o ASO digitalizado (PDF/JPG/PNG, max 10MB) a um ASO existente.

    Reenvio substitui o anexo anterior (mesmo aso_id no volume ./uploads).
    """
    existe = (
        await db.execute(text("SELECT aso_id FROM gp_asos WHERE aso_id = :aid"), {"aid": aso_id})
    ).scalar()
    if not existe:
        raise HTTPException(status_code=404, detail="ASO nao encontrado")

    conteudo = await file.read()
    caminho, nome_arquivo = _gravar_anexo_aso(aso_id, file.filename or "documento", conteudo)

    await db.execute(
        text(
            "UPDATE gp_asos SET arquivo_path = :p, arquivo_nome = :n, "
            "arquivo_subido_em = now() WHERE aso_id = :aid"
        ),
        {"p": caminho, "n": nome_arquivo, "aid": aso_id},
    )
    await db.commit()
    return {
        "aso_id": aso_id,
        "arquivo_nome": nome_arquivo,
        "arquivo_path": caminho,
        "tamanho_bytes": len(conteudo),
    }


@router.get("/aso/{aso_id}/anexo")
async def baixar_anexo_aso(
    aso_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Baixa o documento digitalizado do ASO — 404 honesto se não anexado."""
    import os

    row = (
        await db.execute(
            text("SELECT arquivo_path, arquivo_nome FROM gp_asos WHERE aso_id = :aid"),
            {"aid": aso_id},
        )
    ).first()
    if row is None:
        raise HTTPException(status_code=404, detail="ASO nao encontrado")
    caminho, nome = row[0], row[1]
    if not caminho:
        raise HTTPException(
            status_code=404, detail="ASO sem documento digitalizado — anexe o arquivo primeiro"
        )
    if not os.path.isfile(caminho):
        raise HTTPException(
            status_code=404,
            detail="Anexo registrado mas arquivo ausente no volume ./uploads — reenvie o documento",
        )

    ext = os.path.splitext(caminho)[1].lower()
    with open(caminho, "rb") as fh:
        conteudo = fh.read()
    safe_nome = (nome or f"aso-{aso_id}{ext}").replace('"', "").replace("\n", " ")
    return Response(
        content=conteudo,
        media_type=_ASO_ANEXO_TIPOS.get(ext, "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{safe_nome}"'},
    )


# ================================================================
# EPI CRUD (endpoints originais preservados)
# ================================================================


@router.post("/epi", status_code=201)
async def registrar_entrega_epi(
    data: EPIDeliveryCreate,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Registra entrega de EPI e gera a FICHA DE EPI digital (NR-6).

    Fluxo NR-1/NR-6: entrega → ficha em PDF padrão-ouro (assinatura só do
    FUNCIONÁRIO) → status pendente_assinatura → funcionário assina digitalmente.
    """
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
    await db.commit()

    # Gera a ficha de EPI (pendente de assinatura) cobrindo esta entrega
    ficha_info: dict[str, Any]
    try:
        ficha = await FichaEPIService(db).gerar_ficha(str(data.employee_id), [epi.delivery_id])
        ficha_info = {
            "ficha_id": ficha["ficha_id"],
            "status": ficha["status"],
            "pdf": f"/people-management/sst/epi/fichas/{ficha['ficha_id']}/pdf",
        }
    except ValueError as exc:  # honesto: entrega registrada, ficha não gerada
        ficha_info = {"ficha_id": None, "status": "nao_gerada", "erro": str(exc)}

    return {
        "delivery_id": epi.delivery_id,
        "employee_id": epi.employee_id,
        "epi": data.epi_nome,
        "quantidade": data.quantidade,
        "data_entrega": str(epi.data_entrega) if hasattr(epi, "data_entrega") else None,
        "status": "entregue",
        "ficha_epi": ficha_info,
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
        query = (
            "SELECT d.delivery_id, d.employee_id, d.epi_nome, d.quantidade, d.epi_ca, d.nr, "
            "d.ficha_epi_id, f.status AS ficha_status "
            "FROM gp_epi_deliveries d LEFT JOIN sst_fichas_epi f ON f.id = d.ficha_epi_id"
        )
        params: dict[str, Any] = {}
        if employee_id:
            query += " WHERE d.employee_id = :eid"
            params["eid"] = employee_id
        result = await db.execute(sql_text(query), params)
        epis = [
            {
                "delivery_id": r[0],
                "employee_id": r[1],
                "epi": r[2],
                "quantidade": r[3],
                "ca": r[4],
                "status": r[5],
                "ficha_epi_id": str(r[6]) if r[6] else None,
                "ficha_status": r[7] or "sem_ficha",
            }
            for r in result.fetchall()
        ]
    except Exception as exc:
        logger.warning("SST listar EPIs: %s", exc)
        epis = []
    return {"total": len(epis), "epis": epis}


# ================================================================
# FICHA DE EPI DIGITAL (NR-1/NR-6) — assinada pelo FUNCIONÁRIO
# ================================================================


@router.post("/epi/fichas/gerar", status_code=201)
async def gerar_ficha_epi(
    data: dict,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Gera ficha de EPI consolidando as entregas SEM ficha de um funcionário.

    Body: {"employee_id": "<uuid>", "delivery_ids": ["<opcional>"]}.
    Útil para regularizar o legado (entregas antigas sem ficha assinada).
    """
    employee_id = data.get("employee_id")
    if not employee_id:
        raise HTTPException(status_code=422, detail="employee_id é obrigatório")
    try:
        ficha = await FichaEPIService(db).gerar_ficha(str(employee_id), data.get("delivery_ids"))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    ficha["pdf"] = f"/people-management/sst/epi/fichas/{ficha['ficha_id']}/pdf"
    return ficha


@router.get("/epi/fichas")
async def listar_fichas_epi(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    status: str | None = Query(None, description="pendente_assinatura|assinada"),
    employee_id: str | None = Query(None),
) -> Any:
    """Lista fichas de EPI (status honesto: pendente_assinatura|assinada)."""
    fichas = await FichaEPIService(db).listar_fichas(status, employee_id)
    return {
        "total": len(fichas),
        "pendentes_assinatura": sum(1 for f in fichas if f["status"] == "pendente_assinatura"),
        "assinadas": sum(1 for f in fichas if f["status"] == "assinada"),
        "fichas": fichas,
    }


@router.get("/epi/fichas/minhas")
async def minhas_fichas_epi(
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Fichas de EPI do funcionário logado no Portal (para assinar)."""
    fichas = await FichaEPIService(db).listar_fichas(None, str(employee_id))
    return {"total": len(fichas), "fichas": fichas}


@router.get("/epi/fichas/{ficha_id}/pdf")
async def download_ficha_epi_pdf(
    ficha_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Download do PDF padrão-ouro da ficha (bloco de autenticidade se assinada)."""
    try:
        pdf, nome = await FichaEPIService(db).pdf_ficha(ficha_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{nome}"'},
    )


@router.post("/epi/fichas/{ficha_id}/assinar")
async def assinar_ficha_epi(
    ficha_id: str,
    request: Request,
    employee_id: CurrentEmployeeId,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Funcionário assina a PRÓPRIA ficha digitalmente (token do Portal).

    REUSA a infra de assinatura do Portal do Funcionário: hash SHA-256 gravado
    em portal_digital_signatures (document_type='ficha_epi') + IP/User-Agent.
    Nunca marca 'assinada' sem hash real.
    """
    try:
        ficha = await FichaEPIService(db).assinar_ficha(
            ficha_id,
            signer_employee_id=str(employee_id),
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    ficha["pdf"] = f"/people-management/sst/epi/fichas/{ficha['ficha_id']}/pdf"
    return ficha


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
        fonte_geradora=data.fonte_geradora,
        medidas_controle=data.medidas_controle or [],
        epi_recomendado=data.epi_recomendado or [],
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
        "fonte_geradora": data.fonte_geradora,
        "medidas_controle": data.medidas_controle or [],
        "epi_recomendado": data.epi_recomendado or [],
        "status": "identificado",
    }


def _as_list(value: Any) -> list[Any]:
    """jsonb pode voltar como str (asyncpg sem codec) ou lista."""
    if value is None:
        return []
    if isinstance(value, str):
        import json as _json

        try:
            parsed = _json.loads(value)
            return parsed if isinstance(parsed, list) else [parsed]
        except (ValueError, TypeError):
            return [value]
    if isinstance(value, list):
        return value
    return [value]


@router.get("/riscos")
async def listar_riscos(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    posto_id: str | None = Query(None),
    nivel: str | None = Query(None, description="baixo|medio|alto|critico"),
    categoria: str | None = Query(None, description="fisico|quimico|biologico|ergonomico|acidente"),
) -> Any:
    """Lista riscos ocupacionais (gp_risks) com nome legível do posto.

    posto_nome vem por LEFT JOIN em posts/condominios; se o posto_id for
    órfão (não existe em nenhuma das tabelas), posto_nome=None e o frontend
    exibe o id truncado com aviso honesto — nunca fabricamos o local.
    """
    from sqlalchemy import text as sql_text

    try:
        query = (
            "SELECT r.risk_id, r.posto_id, COALESCE(p.name, c.nome) AS posto_nome, "
            "r.categoria, r.descricao, r.nivel, r.status, r.fonte_geradora, "
            "r.medidas_controle, r.epi_recomendado "
            "FROM gp_risks r "
            "LEFT JOIN posts p ON p.id::text = r.posto_id "
            "LEFT JOIN condominios c ON c.id::text = r.posto_id "
            "WHERE 1=1"
        )
        params: dict[str, Any] = {}
        if posto_id:
            query += " AND r.posto_id = :pid"
            params["pid"] = posto_id
        if nivel:
            query += " AND r.nivel = :nivel"
            params["nivel"] = nivel
        if categoria:
            query += " AND r.categoria = :categoria"
            params["categoria"] = categoria
        query += (
            " ORDER BY CASE r.nivel WHEN 'critico' THEN 0 WHEN 'alto' THEN 1 "
            "WHEN 'medio' THEN 2 ELSE 3 END, r.created_at DESC"
        )
        result = await db.execute(sql_text(query), params)
        riscos = [
            {
                "risk_id": r[0],
                "posto_id": r[1],
                "posto_nome": r[2],
                "categoria": r[3],
                "descricao": r[4],
                "nivel": r[5],
                "status": r[6],
                "fonte_geradora": r[7],
                "medidas_controle": _as_list(r[8]),
                "epi_recomendado": _as_list(r[9]),
            }
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
    """Status do LTCAT lido de TABELA REAL (sst_ltcat) — fim do hardcode.

    Fatores de risco vêm do mapa real (gp_risks). Campos responsavel/validade
    são editáveis via PUT /sst/ltcat.
    """
    result = await db.execute(text("SELECT count(*) FROM posts WHERE is_active = true"))
    total_postos = result.scalar() or 0

    ltcat = (
        await db.execute(
            text(
                "SELECT id, status, responsavel_tecnico, registro_conselho, validade_inicio, "
                "validade_fim, observacoes, updated_at FROM sst_ltcat ORDER BY created_at DESC LIMIT 1"
            )
        )
    ).mappings().first()
    if not ltcat:
        raise HTTPException(
            status_code=404,
            detail="Nenhum registro em sst_ltcat — rode a migração 2026-07-07_sst_ondaB_FORWARD.sql",
        )

    riscos = (
        await db.execute(
            text(
                "SELECT categoria, descricao, nivel FROM gp_risks WHERE status <> 'encerrado' "
                "ORDER BY categoria, nivel"
            )
        )
    ).mappings().all()

    vigencia = None
    if ltcat["validade_inicio"] and ltcat["validade_fim"]:
        vigencia = f"{ltcat['validade_inicio']} a {ltcat['validade_fim']}"

    status = ltcat["status"]
    if status == "vigente" and ltcat["validade_fim"] and ltcat["validade_fim"] < date.today():
        status = "vencido"  # derivação honesta pela data real

    proxima_acao = {
        "pendente_elaboracao": "Contratar engenheiro de segurança do trabalho para elaboração",
        "em_elaboracao": "Acompanhar elaboração com o responsável técnico",
        "vigente": "Manter laudo atualizado; revisar a cada alteração de ambiente",
        "vencido": "Renovar o LTCAT — laudo fora da validade",
    }.get(status, "Revisar registro do LTCAT")

    return {
        "documento": "LTCAT - Laudo Técnico das Condições Ambientais de Trabalho",
        "base_legal": "Lei 8.213/91 Art. 58 + IN INSS 128/2022",
        "empresa": "CONECTAMAIS ELETRONICA LTDA",
        "cnpj": "35.710.481/0001-03",
        "ltcat_id": str(ltcat["id"]),
        "vigencia": vigencia or "aguardando dado (validade não definida)",
        "responsavel_tecnico": ltcat["responsavel_tecnico"] or "aguardando dado (não definido)",
        "registro_conselho": ltcat["registro_conselho"],
        "postos_avaliados": total_postos,
        "status": status,
        "observacoes": ltcat["observacoes"],
        "fatores_risco": [
            {"agente": r["descricao"], "tipo": r["categoria"], "nivel": r["nivel"]} for r in riscos
        ],
        "fonte_fatores_risco": "gp_risks (mapa real de riscos)",
        "proxima_acao": proxima_acao,
    }


@router.put("/ltcat")
async def atualizar_ltcat(
    data: dict,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Atualiza o registro do LTCAT (responsável, validade, status, observações).

    Campos aceitos: status (pendente_elaboracao|em_elaboracao|vigente|vencido),
    responsavel_tecnico, registro_conselho, validade_inicio, validade_fim,
    observacoes. Campos não enviados não são alterados.
    """
    permitidos = {
        "status", "responsavel_tecnico", "registro_conselho",
        "validade_inicio", "validade_fim", "observacoes",
    }
    status_validos = {"pendente_elaboracao", "em_elaboracao", "vigente", "vencido"}
    campos = {k: v for k, v in data.items() if k in permitidos}
    if not campos:
        raise HTTPException(status_code=422, detail=f"Nenhum campo editável enviado. Aceitos: {sorted(permitidos)}")
    if "status" in campos and campos["status"] not in status_validos:
        raise HTTPException(status_code=422, detail=f"status inválido. Válidos: {sorted(status_validos)}")
    for k in ("validade_inicio", "validade_fim"):
        if campos.get(k):
            try:
                campos[k] = date.fromisoformat(str(campos[k]))
            except ValueError as exc:
                raise HTTPException(status_code=422, detail=f"{k} inválida (use YYYY-MM-DD)") from exc

    sets = ", ".join(f"{k} = :{k}" for k in campos)
    result = await db.execute(
        text(
            f"UPDATE sst_ltcat SET {sets}, updated_at = NOW() "  # noqa: S608 — chaves whitelisted
            "WHERE id = (SELECT id FROM sst_ltcat ORDER BY created_at DESC LIMIT 1) "
            "RETURNING id, status, responsavel_tecnico, registro_conselho, validade_inicio, validade_fim, observacoes"
        ),
        campos,
    )
    row = result.mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail="Nenhum registro em sst_ltcat para atualizar")
    await db.commit()
    return {
        "ltcat_id": str(row["id"]),
        "status": row["status"],
        "responsavel_tecnico": row["responsavel_tecnico"],
        "registro_conselho": row["registro_conselho"],
        "validade_inicio": str(row["validade_inicio"]) if row["validade_inicio"] else None,
        "validade_fim": str(row["validade_fim"]) if row["validade_fim"] else None,
        "observacoes": row["observacoes"],
    }


@router.get("/prontuario/{employee_id}")
async def get_prontuario_sst(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Prontuário SST 360 — dossiê completo de saúde ocupacional do funcionário.

    Agrega em UMA resposta: identificação (posto atual real), compliance NR-1
    (4 checks + score), ASOs (histórico + vencimento), EPIs (entregas + fichas
    c/ assinatura), riscos da FUNÇÃO (PGR GES + Tabela 24), treinamentos NR,
    afastamentos (estabilidade CCT + eSocial S-2230) e CATs (recibos S-2210).
    Cada bloco é isolado: um domínio falho vem com {"erro": ...} sem derrubar
    o restante. Campos com `fonte` marcada; vazios são honestos.
    """
    service = SSTService(db)
    prontuario = await service.get_prontuario(employee_id)
    if prontuario is None:
        raise HTTPException(status_code=404, detail="Funcionário não encontrado")
    return prontuario


@router.get("/ppp/{employee_id}")
async def gerar_ppp(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    transmit: bool = Query(
        False,
        description="true = transmite DE VERDADE o S-2240 deste funcionário ao eSocial "
        "(ambiente ESOCIAL_AMBIENTE, default produção restrita)",
    ),
) -> Any:
    """Gera PPP (Perfil Profissiográfico Previdenciário) de um funcionário.

    Documento obrigatório conforme Lei 8.213/91 Art. 58 e IN INSS 128/2022.
    Com transmit=true, chama transmitir_evento_sst('S-2240', employee_id) —
    transmissão REAL; dados obrigatórios ausentes aparecem HONESTOS na resposta
    (ValueError do gerador da Onda A), nunca protocolo fabricado.
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

    esocial: dict[str, Any]
    if transmit:
        from modules.people_management.hr.services.esocial_service import transmitir_evento_sst

        try:
            esocial = await transmitir_evento_sst(db, "S-2240", employee_id)
            await db.commit()
        except ValueError as exc:
            # HONESTO: dado obrigatório ausente — nada foi transmitido, nada fabricado
            esocial = {"status": "nao_transmitido", "erros": [str(exc)], "protocolo": None, "recibo": None}
        except RuntimeError as exc:
            esocial = {"status": "erro_infraestrutura", "erros": [str(exc)], "protocolo": None, "recibo": None}
    else:
        esocial = {
            "status": "nao_transmitido",
            "nota": "Use ?transmit=true para transmitir o S-2240 real deste funcionário.",
        }

    return {
        "documento": "PPP - Perfil Profissiográfico Previdenciário",
        "base_legal": "Lei 8.213/91 Art. 58 § 4º + IN INSS 128/2022",
        "esocial_evento": "S-2240",
        "esocial": esocial,
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


@router.get("/ppp/{employee_id}/pdf")
async def gerar_ppp_pdf(
    employee_id: str,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """PPP em PDF padrão-ouro (marca Conecta Mais) — documento oficial p/ INSS.

    Renderiza o mesmo dict do GET /sst/ppp/{employee_id} (sem transmitir ao
    eSocial) nas seções clássicas do PPP: dados administrativos, lotação e
    atribuições, exposição a fatores de risco, exames médicos e responsáveis.
    Assinatura: só da EMPRESA (incluir_empresa=True — doc da empresa).
    """
    from modules.people_management.sst.services.ppp_pdf import montar_ppp_pdf

    ppp = await gerar_ppp(employee_id, current_user, db, transmit=False)

    # CBO: employees não tem coluna cbo hoje — _cbo mapeia pelo cargo (folha oficial)
    pdf = montar_ppp_pdf(ppp, None)
    nome_func = (ppp.get("funcionario") or {}).get("nome") or employee_id
    slug = "".join(c if c.isalnum() else "-" for c in str(nome_func).lower()).strip("-")[:40]
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="ppp-{slug}.pdf"'},
    )
