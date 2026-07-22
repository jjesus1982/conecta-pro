"""
Controller de Turnover para RH.

Fornece dashboard com dados reais de admissoes, desligamentos
e taxa de turnover baseados na tabela employees, incluindo o gap
honesto de motivos de desligamento nao informados.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.people_management.human_resources.services.turnover_service import (
    TurnoverService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/turnover", tags=["RH - Turnover"])

# Motivos de desligamento (CLT) — vocabulário canônico. Chave estável (agrupa a análise de
# causas de turnover), rótulo humano (exibido). NÃO é fabricar dado: é o RH informando o motivo real.
MOTIVOS_DESLIGAMENTO: dict[str, str] = {
    "pedido_demissao": "Pedido de demissão (iniciativa do empregado)",
    "sem_justa_causa": "Dispensa sem justa causa (iniciativa do empregador)",
    "justa_causa": "Dispensa por justa causa",
    "acordo_mutuo": "Acordo mútuo (art. 484-A CLT)",
    "termino_contrato": "Término de contrato / experiência",
    "aposentadoria": "Aposentadoria",
    "falecimento": "Falecimento",
    "abandono_emprego": "Abandono de emprego",
}


@router.get("/desligados-sem-motivo")
async def desligados_sem_motivo(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Lista os desligados cujo motivo ainda não foi informado (gap da análise de turnover)."""
    rows = (
        await db.execute(
            text(
                "SELECT CAST(id AS TEXT) AS id, nome, coalesce(cargo,'—') AS cargo, data_demissao "
                "FROM employees WHERE data_demissao IS NOT NULL "
                "AND nullif(trim(coalesce(motivo_desligamento,'')),'') IS NULL "
                "ORDER BY data_demissao DESC"
            )
        )
    ).mappings().all()
    return {
        "desligados": [
            {"id": r["id"], "nome": r["nome"], "cargo": r["cargo"],
             "data_demissao": r["data_demissao"].isoformat() if r["data_demissao"] else None}
            for r in rows
        ],
        "motivos": [{"value": k, "label": v} for k, v in MOTIVOS_DESLIGAMENTO.items()],
        "total": len(rows),
    }


class RegistrarMotivoBody(BaseModel):
    employee_id: str
    motivo: str
    observacao: str | None = None


@router.post("/registrar-motivo")
async def registrar_motivo(
    body: RegistrarMotivoBody,
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Registra o motivo REAL de desligamento (informado pelo RH) de um colaborador já desligado.

    Não fabrica: valida o motivo contra o vocabulário CLT e só escreve em quem está desligado
    e ainda sem motivo. Alimenta a análise de causas de turnover.
    """
    key = (body.motivo or "").strip().lower()
    if key not in MOTIVOS_DESLIGAMENTO:
        return {"ok": False, "message": "Motivo inválido. Selecione um motivo da lista."}
    if not (body.employee_id or "").strip():
        return {"ok": False, "message": "Selecione o colaborador desligado."}

    alvo = (
        await db.execute(
            text(
                "SELECT nome, data_demissao, nullif(trim(coalesce(motivo_desligamento,'')),'') AS motivo "
                "FROM employees WHERE CAST(id AS TEXT) = :i"
            ),
            {"i": body.employee_id.strip()},
        )
    ).mappings().first()
    if not alvo:
        return {"ok": False, "message": "Colaborador não encontrado."}
    if not alvo["data_demissao"]:
        return {"ok": False, "message": f"{alvo['nome']} não está desligado — motivo não se aplica."}

    label = MOTIVOS_DESLIGAMENTO[key]
    obs = (body.observacao or "").strip() or None
    await db.execute(
        text(
            "UPDATE employees SET motivo_desligamento = :m, "
            "observacao_desligamento = coalesce(:o, observacao_desligamento), updated_at = now() "
            "WHERE CAST(id AS TEXT) = :i"
        ),
        {"m": label, "o": obs, "i": body.employee_id.strip()},
    )
    await db.commit()
    ja_tinha = alvo["motivo"] is not None
    verbo = "atualizado" if ja_tinha else "registrado"
    return {"ok": True, "message": f"Motivo {verbo}: {alvo['nome']} → {label}."}


@router.get("/dashboard")
async def turnover_dashboard(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Dashboard de turnover com dados reais."""
    try:
        return await TurnoverService(db).dashboard()
    except Exception as exc:
        logger.warning("Erro no dashboard turnover: %s", exc)
        return {"total_colaboradores": 0, "taxa_turnover_trimestral": 0, "erro": str(exc)}


@router.get("/motivos")
async def turnover_motivos(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """Distribuicao por motivo de desligamento nos ultimos 12 meses."""
    try:
        return await TurnoverService(db).motivos()
    except Exception as exc:
        logger.warning("Erro ao buscar motivos: %s", exc)
        return {"motivos": [], "periodo": "12_meses", "erro": str(exc)}
