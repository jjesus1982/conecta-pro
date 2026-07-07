"""
Controller (endpoints) de Passagem de Turno.

Rotas (montadas sob /api/v1/operacional):
- POST /passagem-turno/           → registra a passagem do turno
- GET  /passagem-turno/           → lista passagens + a "anterior" (leitura do turno seguinte)
- POST /passagem-turno/{id}/lida  → confirma leitura da passagem

Tabela: operacional_passagens_turno (SQL raw async).
"""

import json
from datetime import date, datetime, timezone
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
from modules.operacional.shift_handover.schemas import (
    PassagemLidaResponse,
    PassagemTurnoCreate,
    PassagemTurnoListResponse,
    PassagemTurnoResponse,
)

router = APIRouter(prefix="/passagem-turno", tags=["Operacional - Passagem de Turno"])

_ITEM_COLUMNS = """
    pt.id::text AS id,
    pt.post_id::text AS post_id,
    p.name AS post_nome,
    pt.author_user_id::text AS author_user_id,
    pt.author_nome AS author_nome,
    pt.turno AS turno,
    pt.resumo AS resumo,
    pt.pendencias AS pendencias,
    pt.data_turno AS data_turno,
    pt.criada_em AS criada_em,
    pt.lida_por AS lida_por
"""


def _parse_lida_por(value: Any) -> list[dict[str, Any]]:
    """JSONB pode chegar como list (codec asyncpg) ou como str."""
    if value is None:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except (ValueError, TypeError):
            return []
    return value if isinstance(value, list) else []


def _row_to_response(row: Any) -> PassagemTurnoResponse:
    data = dict(row._mapping)
    data["lida_por"] = _parse_lida_por(data.get("lida_por"))
    return PassagemTurnoResponse(**data)


async def _resolve_post_id(
    db: AsyncSession,
    allowed_post_ids: list[str] | None,
    post_id: str | None,
) -> tuple[str, str]:
    """
    Resolve e valida o posto da passagem dentro do escopo.

    Returns:
        (post_id, post_nome)
    """
    if post_id is None:
        if allowed_post_ids is not None and len(allowed_post_ids) == 1:
            post_id = allowed_post_ids[0]
        else:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="post_id é obrigatório: seu escopo tem mais de um posto (ou todos).",
            )
    elif allowed_post_ids is not None and post_id not in allowed_post_ids:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Posto fora do seu escopo operacional.",
        )

    result = await db.execute(
        text("SELECT id::text AS id, name FROM posts WHERE id::text = :pid AND is_active = true"),
        {"pid": post_id},
    )
    post = result.first()
    if not post:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Posto {post_id} não encontrado ou inativo.",
        )
    return post.id, post.name


@router.post("/", response_model=PassagemTurnoResponse, status_code=status.HTTP_201_CREATED)
async def create_passagem_turno(
    data: PassagemTurnoCreate,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> PassagemTurnoResponse:
    """
    Registra a passagem de turno de um posto.

    Líder de 1 posto pode omitir post_id (resolvido automaticamente).
    Autor (author_user_id/author_nome) vem do usuário autenticado.
    """
    allowed = scope_post_ids_or_403(scope)
    post_id, post_nome = await _resolve_post_id(db, allowed, data.post_id)

    result = await db.execute(
        text(
            """
            INSERT INTO operacional_passagens_turno
                (post_id, author_user_id, author_nome, turno, resumo, pendencias, data_turno)
            VALUES
                (CAST(:post_id AS uuid), CAST(:author_user_id AS uuid), :author_nome,
                 :turno, :resumo, :pendencias, :data_turno)
            RETURNING
                id::text AS id, post_id::text AS post_id, author_user_id::text AS author_user_id,
                author_nome, turno, resumo, pendencias, data_turno, criada_em, lida_por
            """
        ),
        {
            "post_id": post_id,
            "author_user_id": scope.user_id,
            "author_nome": scope.user_name,
            "turno": data.turno,
            "resumo": data.resumo,
            "pendencias": data.pendencias,
            "data_turno": data.data_turno or date.today(),
        },
    )
    row = result.first()
    await db.commit()

    logger.info(
        "Passagem de turno registrada",
        action="create_passagem_turno",
        passagem_id=row.id,
        post_id=post_id,
        turno=data.turno,
        user_id=scope.user_id,
    )

    item = dict(row._mapping)
    item["post_nome"] = post_nome
    item["lida_por"] = _parse_lida_por(item.get("lida_por"))
    return PassagemTurnoResponse(**item)


@router.get("/", response_model=PassagemTurnoListResponse)
async def list_passagens_turno(
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
    post_id: str | None = Query(None, description="Filtrar por posto"),
    data: date | None = Query(None, description="Filtrar por data do turno (YYYY-MM-DD)"),
    limit: int = Query(20, ge=1, le=100, description="Máximo de itens"),
) -> PassagemTurnoListResponse:
    """
    Lista passagens de turno do escopo do usuário.

    `anterior` = passagem mais recente ANTERIOR à data filtrada (ou hoje) do
    mesmo posto — é o que o turno seguinte lê ao assumir.
    """
    allowed = scope_post_ids_or_403(scope)

    if post_id and allowed is not None and post_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Posto fora do seu escopo operacional.",
        )

    conditions = ["pt.is_active = true"]
    params: dict[str, Any] = {"limit": limit}
    if post_id:
        conditions.append("pt.post_id::text = :post_id")
        params["post_id"] = post_id
    elif allowed is not None:
        conditions.append("pt.post_id::text = ANY(:allowed)")
        params["allowed"] = allowed
    if data:
        conditions.append("pt.data_turno = :data")
        params["data"] = data

    result = await db.execute(
        text(
            f"""
            SELECT {_ITEM_COLUMNS}
            FROM operacional_passagens_turno pt
            JOIN posts p ON p.id = pt.post_id
            WHERE {" AND ".join(conditions)}
            ORDER BY pt.data_turno DESC, pt.criada_em DESC
            LIMIT :limit
            """
        ),
        params,
    )
    items = [_row_to_response(row) for row in result.fetchall()]

    # Passagem "anterior": só faz sentido quando o posto é determinável
    # (filtro explícito ou escopo de exatamente 1 posto).
    anterior: PassagemTurnoResponse | None = None
    target_post = post_id or (allowed[0] if allowed is not None and len(allowed) == 1 else None)
    if target_post:
        ref_date = data or date.today()
        prev_result = await db.execute(
            text(
                f"""
                SELECT {_ITEM_COLUMNS}
                FROM operacional_passagens_turno pt
                JOIN posts p ON p.id = pt.post_id
                WHERE pt.is_active = true
                  AND pt.post_id::text = :target_post
                  AND pt.data_turno < :ref_date
                ORDER BY pt.data_turno DESC, pt.criada_em DESC
                LIMIT 1
                """
            ),
            {"target_post": target_post, "ref_date": ref_date},
        )
        prev_row = prev_result.first()
        if prev_row:
            anterior = _row_to_response(prev_row)

    return PassagemTurnoListResponse(items=items, anterior=anterior)


@router.post("/{passagem_id}/lida", response_model=PassagemLidaResponse)
async def marcar_passagem_lida(
    passagem_id: str,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> PassagemLidaResponse:
    """
    Confirma a leitura da passagem: adiciona {user_id, nome, em} ao JSONB
    lida_por (idempotente — não duplica o mesmo usuário).
    """
    allowed = scope_post_ids_or_403(scope)

    result = await db.execute(
        text(
            """
            SELECT id::text AS id, post_id::text AS post_id, lida_por
            FROM operacional_passagens_turno
            WHERE id::text = :pid AND is_active = true
            """
        ),
        {"pid": passagem_id},
    )
    row = result.first()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Passagem de turno {passagem_id} não encontrada.",
        )
    if allowed is not None and row.post_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Passagem de posto fora do seu escopo operacional.",
        )

    lida_por = _parse_lida_por(row.lida_por)
    ja_lida = any(entry.get("user_id") == scope.user_id for entry in lida_por if isinstance(entry, dict))

    if not ja_lida:
        lida_por.append(
            {
                "user_id": scope.user_id,
                "nome": scope.user_name,
                "em": datetime.now(timezone.utc).isoformat(),
            }
        )
        await db.execute(
            text(
                """
                UPDATE operacional_passagens_turno
                SET lida_por = CAST(:lida_por AS jsonb)
                WHERE id::text = :pid
                """
            ),
            {"pid": passagem_id, "lida_por": json.dumps(lida_por, ensure_ascii=False)},
        )
        await db.commit()
        logger.info(
            "Passagem de turno marcada como lida",
            action="marcar_passagem_lida",
            passagem_id=passagem_id,
            user_id=scope.user_id,
        )

    return PassagemLidaResponse(id=row.id, ja_lida=ja_lida, lida_por=lida_por)
