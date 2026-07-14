"""
Controller de Afastamentos (Leaves) — Departamento Pessoal.

Endpoint de listagem de afastamentos/licenças médicas.
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text as _sqltext
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/leaves", tags=["DP - Afastamentos"])


@router.get(
    "",
    summary="Listar Afastamentos",
    description="Retorna lista paginada de afastamentos e licenças médicas dos funcionários.",
)
async def list_leaves(
    current_user: CurrentActiveUser,
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> Any:
    """Lista afastamentos e licenças."""
    # Lê de sst_afastamentos — a MESMA tabela onde o POST grava (antes lia de time_justifications,
    # que está vazia, escondendo os afastamentos reais). Garante write/read consistentes.
    try:
        total = (await db.execute(_sqltext("SELECT count(*) FROM sst_afastamentos"))).scalar() or 0
        rows = (
            (
                await db.execute(
                    _sqltext(
                        "SELECT a.id, a.employee_id, "
                        "COALESCE(NULLIF(a.employee_nome, ''), e.nome) AS employee_nome, "
                        "a.tipo, a.data_inicio, a.data_fim_prevista, "
                        "a.cid, a.motivo, a.status FROM sst_afastamentos a "
                        "LEFT JOIN employees e ON e.id = a.employee_id "
                        "ORDER BY a.created_at DESC NULLS LAST OFFSET :off LIMIT :lim"
                    ),
                    {"off": (page - 1) * page_size, "lim": page_size},
                )
            )
            .mappings()
            .all()
        )
        return {
            "items": [
                {
                    "id": str(r["id"]),
                    "employee_id": str(r["employee_id"]) if r["employee_id"] else None,
                    "employee_nome": r["employee_nome"],
                    "type": r["tipo"],
                    "tipo": r["tipo"],
                    "data_inicio": str(r["data_inicio"]) if r["data_inicio"] else None,
                    "data_fim_prevista": str(r["data_fim_prevista"]) if r["data_fim_prevista"] else None,
                    "cid": r["cid"],
                    "motivo": r["motivo"],
                    "status": r["status"] or "ativo",
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": max(1, (total + page_size - 1) // page_size),
        }
    except Exception:
        return {"items": [], "total": 0, "page": 1, "page_size": 20, "total_pages": 1}


@router.post("", status_code=201, summary="Registrar licença/afastamento")
@router.post("/", include_in_schema=False, status_code=201)
async def criar_leave(data: dict, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> Any:
    """Registra licença/afastamento (tela dp/licencas) -> sst_afastamentos."""
    import uuid as _uuid

    emp = str(data.get("employee_id") or "").strip()
    if not emp:
        raise HTTPException(status_code=422, detail="employee_id é obrigatório")
    from datetime import date as _date

    def _ld(v):
        try:
            return _date.fromisoformat(str(v)[:10]) if v else None
        except Exception:  # noqa: BLE001
            return None

    nrow = (await db.execute(_sqltext("SELECT nome FROM employees WHERE id::text = :e"), {"e": emp})).first()
    nome = nrow[0] if nrow else "—"
    lid = str(_uuid.uuid4())

    tipo_af = data.get("leave_type") or data.get("tipo") or "licenca"
    cid_af = data.get("cid")
    di_af = _ld(data.get("start_date"))
    df_af = _ld(data.get("end_date"))
    # ESTABILIDADE ACIDENTÁRIA (art. 118 Lei 8.213): o registro via /leaves TAMBÉM tem
    # que derivar gera_estabilidade/estabilidade_ate — senão um acidente lançado por aqui
    # não aparece no painel de estabilidade e o colaborador pode ser demitido dentro do
    # período estável (reintegração + salários = passivo). Mesma regra do SSTService.
    from dateutil.relativedelta import relativedelta as _rd

    from modules.people_management.sst.services.sst_service import _deve_gerar_estabilidade

    gera_estab = _deve_gerar_estabilidade(tipo_af, cid_af)
    estab_ate = (df_af or di_af) + _rd(months=12) if (gera_estab and (df_af or di_af)) else None
    await db.execute(
        _sqltext(
            "INSERT INTO sst_afastamentos (id, employee_id, employee_nome, tipo, data_inicio, data_fim_prevista, "
            "cid, motivo, status, gera_estabilidade, estabilidade_ate, created_at, updated_at) VALUES "
            "(:id, :emp, :nome, :tipo, :di, :df, :cid, :motivo, 'ativo', :ge, :ea, NOW(), NOW())"
        ),
        {
            "id": lid,
            "emp": emp,
            "nome": nome,
            "tipo": tipo_af,
            "di": di_af,
            "df": df_af,
            "cid": cid_af,
            "motivo": data.get("notes") or data.get("motivo"),
            "ge": gera_estab,
            "ea": estab_ate,
        },
    )
    await db.commit()
    return {"id": lid, "message": "Licença registrada", "status": "ativo", "gera_estabilidade": gera_estab}
