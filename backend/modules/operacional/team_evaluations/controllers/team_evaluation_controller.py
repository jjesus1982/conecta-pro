"""
Controller (endpoints) de Avaliação de Equipe.

Rotas (montadas sob /api/v1/operacional):
- GET  /avaliacoes/equipe      → funcionários avaliáveis (alocação ativa no escopo)
- POST /avaliacoes/            → cria/atualiza avaliação (1 por avaliador/funcionário/dia)
- GET  /avaliacoes/consolidado → média/tendência por funcionário no período
- GET  /avaliacoes/            → lista bruta

Tabela: operacional_avaliacoes_equipe (SQL raw async).
"""

from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.logging import logger
from modules.operacional.scope import (
    OperationalScope,
    get_operational_scope,
    scope_post_ids_or_403,
)
from modules.operacional.team_evaluations.schemas import (
    AvaliacaoCreate,
    AvaliacaoResponse,
    ConsolidadoFuncionario,
    EquipeMembro,
)

router = APIRouter(prefix="/avaliacoes", tags=["Operacional - Avaliação de Equipe"])


def _check_post_in_scope(post_id: str, allowed: list[str] | None) -> None:
    if allowed is not None and post_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Posto fora do seu escopo operacional.",
        )


async def _resolve_allocation_post(
    db: AsyncSession,
    employee_id: str,
    post_id: str | None,
    allowed: list[str] | None,
) -> str:
    """
    Valida (ou deriva) o posto da avaliação pela alocação ativa do funcionário.

    Raises:
        HTTPException 422 se o funcionário não tem alocação ativa no posto/escopo.
    """
    conditions = [
        "a.employee_id::text = :eid",
        "a.status = 'active'",
        "a.is_active = true",
    ]
    params: dict[str, Any] = {"eid": employee_id}
    if post_id:
        conditions.append("a.post_id::text = :post_id")
        params["post_id"] = post_id
    elif allowed is not None:
        conditions.append("a.post_id::text = ANY(:allowed)")
        params["allowed"] = allowed

    result = await db.execute(
        text(
            f"""
            SELECT a.post_id::text AS post_id
            FROM allocations a
            WHERE {" AND ".join(conditions)}
            ORDER BY a.is_primary DESC, a.created_at DESC
            LIMIT 1
            """
        ),
        params,
    )
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Funcionário não possui alocação ativa "
                + (f"no posto {post_id}." if post_id else "em posto do seu escopo.")
            ),
        )
    return row.post_id


@router.post("/", response_model=AvaliacaoResponse, status_code=status.HTTP_201_CREATED)
async def criar_avaliacao(
    data: AvaliacaoCreate,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> AvaliacaoResponse:
    """
    Registra avaliação de um funcionário da equipe (nota 1-5).

    Anti-duplicata: 1 avaliação por (funcionário, avaliador, competência) —
    repetir no mesmo dia atualiza a existente.
    """
    allowed = scope_post_ids_or_403(scope)
    if data.post_id:
        _check_post_in_scope(data.post_id, allowed)

    # Funcionário existe e está ativo?
    emp_result = await db.execute(
        text("SELECT id::text AS id, nome, cargo FROM employees WHERE id::text = :eid AND status = 'ativo'"),
        {"eid": data.employee_id},
    )
    employee = emp_result.first()
    if not employee:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Funcionário {data.employee_id} não encontrado ou inativo.",
        )

    # Honestidade: só avalia quem TEM alocação ativa no posto/escopo.
    post_id = await _resolve_allocation_post(db, data.employee_id, data.post_id, allowed)
    competencia = data.competencia or date.today()

    existing = await db.execute(
        text(
            """
            SELECT id::text AS id
            FROM operacional_avaliacoes_equipe
            WHERE employee_id::text = :eid
              AND avaliador_user_id::text = :uid
              AND competencia = :competencia
              AND is_active = true
            """
        ),
        {"eid": data.employee_id, "uid": scope.user_id, "competencia": competencia},
    )
    existing_row = existing.first()

    if existing_row:
        result = await db.execute(
            text(
                """
                UPDATE operacional_avaliacoes_equipe
                SET nota = :nota,
                    observacao = :observacao,
                    post_id = CAST(:post_id AS uuid),
                    avaliador_nome = :avaliador_nome
                WHERE id::text = :id
                RETURNING
                    id::text AS id, post_id::text AS post_id, employee_id::text AS employee_id,
                    avaliador_user_id::text AS avaliador_user_id, avaliador_nome,
                    nota, observacao, competencia, criada_em
                """
            ),
            {
                "id": existing_row.id,
                "nota": data.nota,
                "observacao": data.observacao,
                "post_id": post_id,
                "avaliador_nome": scope.user_name,
            },
        )
        atualizada = True
    else:
        result = await db.execute(
            text(
                """
                INSERT INTO operacional_avaliacoes_equipe
                    (post_id, employee_id, avaliador_user_id, avaliador_nome,
                     nota, observacao, competencia)
                VALUES
                    (CAST(:post_id AS uuid), CAST(:employee_id AS uuid), CAST(:avaliador_user_id AS uuid),
                     :avaliador_nome, :nota, :observacao, :competencia)
                RETURNING
                    id::text AS id, post_id::text AS post_id, employee_id::text AS employee_id,
                    avaliador_user_id::text AS avaliador_user_id, avaliador_nome,
                    nota, observacao, competencia, criada_em
                """
            ),
            {
                "post_id": post_id,
                "employee_id": data.employee_id,
                "avaliador_user_id": scope.user_id,
                "avaliador_nome": scope.user_name,
                "nota": data.nota,
                "observacao": data.observacao,
                "competencia": competencia,
            },
        )
        atualizada = False

    row = result.first()
    await db.commit()

    post_result = await db.execute(
        text("SELECT name FROM posts WHERE id::text = :pid"), {"pid": post_id}
    )
    post_row = post_result.first()

    logger.info(
        "Avaliação de equipe registrada",
        action="criar_avaliacao_equipe",
        avaliacao_id=row.id,
        employee_id=data.employee_id,
        post_id=post_id,
        nota=data.nota,
        atualizada=atualizada,
        user_id=scope.user_id,
    )

    item = dict(row._mapping)
    item["post_nome"] = post_row.name if post_row else None
    item["employee_nome"] = employee.nome
    item["atualizada"] = atualizada
    return AvaliacaoResponse(**item)


def _tendencia(notas: list[int]) -> str:
    """Compara a média da metade recente vs metade antiga do período."""
    if len(notas) < 2:
        return "sem_dados"
    meio = len(notas) // 2
    antiga = notas[:meio]
    recente = notas[meio:]
    diff = (sum(recente) / len(recente)) - (sum(antiga) / len(antiga))
    if diff > 0.2:
        return "subindo"
    if diff < -0.2:
        return "caindo"
    return "estavel"


