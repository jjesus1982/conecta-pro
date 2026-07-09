"""
Controller (endpoints) das Instruções de Posto (post orders).

Rotas (montadas sob /api/v1/operacional):
- GET /instrucoes-posto/            → postos ativos do escopo + situação das instruções
- GET /instrucoes-posto/{post_id}   → instruções do posto (líder só do escopo; gestor qualquer)
- PUT /instrucoes-posto/{post_id}   → SÓ GESTOR — upsert versionado (histórico jsonb, últimas 10)

Regras HONESTAS:
- Posto sem registro → conteudo=None, versao=0 ("sem instruções cadastradas"),
  nunca fabricar texto.
- Líder de posto (scope.post_ids) só enxerga os postos dele — 403 fora do escopo.
- Cada edição empurra a versão vigente para `historico` (jsonb) e incrementa `versao`.
"""

import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from core.logging import logger
from modules.operacional.post_orders.schemas import (
    InstrucoesPostoListItem,
    InstrucoesPostoListResponse,
    InstrucoesPostoResponse,
    InstrucoesPostoUpdate,
)
from modules.operacional.scope import (
    OperationalScope,
    get_operational_scope,
    scope_post_ids_or_403,
)

router = APIRouter(prefix="/instrucoes-posto", tags=["Operacional - Instruções de Posto"])

TITULO_PADRAO = "Instruções do posto"
HISTORICO_MAX = 10


async def _post_ou_404(db: AsyncSession, post_id: str):
    """Retorna (id, name) do posto ou 404. Comparação por ::text evita erro de cast UUID."""
    row = (
        await db.execute(
            text("SELECT id::text AS id, name FROM posts WHERE id::text = :pid"),
            {"pid": post_id},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Posto não encontrado.")
    return row


def _fora_do_escopo_403(scope: OperationalScope, post_id: str) -> None:
    """403 se o usuário é escopado (líder) e o posto não é dele."""
    allowed = scope_post_ids_or_403(scope)
    if allowed is not None and post_id not in allowed:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Posto fora do seu escopo operacional.",
        )


@router.get("/", response_model=InstrucoesPostoListResponse)
async def listar_instrucoes_postos(
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> InstrucoesPostoListResponse:
    """Lista os postos ativos do escopo com a situação das instruções de cada um."""
    allowed = scope_post_ids_or_403(scope)

    conditions = ["p.is_active = TRUE"]
    params: dict = {}
    if allowed is not None:
        conditions.append("p.id::text = ANY(:allowed)")
        params["allowed"] = allowed

    result = await db.execute(
        text(
            f"""
            SELECT p.id::text AS post_id,
                   p.name AS post_nome,
                   (po.id IS NOT NULL AND COALESCE(po.conteudo, '') <> '') AS tem_instrucoes,
                   COALESCE(po.versao, 0) AS versao,
                   po.updated_at
            FROM posts p
            LEFT JOIN operacional_post_orders po ON po.post_id = p.id
            WHERE {" AND ".join(conditions)}
            ORDER BY p.name
            """
        ),
        params,
    )
    items = [
        InstrucoesPostoListItem(
            post_id=row.post_id,
            post_nome=row.post_nome,
            tem_instrucoes=bool(row.tem_instrucoes),
            versao=int(row.versao or 0),
            updated_at=row.updated_at,
        )
        for row in result.fetchall()
    ]
    return InstrucoesPostoListResponse(total=len(items), items=items)


@router.get("/{post_id}", response_model=InstrucoesPostoResponse)
async def obter_instrucoes_posto(
    post_id: str,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> InstrucoesPostoResponse:
    """
    Instruções vigentes do posto. Líder só do escopo (403 fora); gestor qualquer.
    Sem registro → conteudo=None e versao=0 (sem instruções cadastradas).
    """
    _fora_do_escopo_403(scope, post_id)
    posto = await _post_ou_404(db, post_id)

    row = (
        await db.execute(
            text(
                """
                SELECT titulo, conteudo, versao, updated_at, updated_by_nome
                FROM operacional_post_orders
                WHERE post_id::text = :pid
                """
            ),
            {"pid": post_id},
        )
    ).first()

    if not row:
        return InstrucoesPostoResponse(
            post_id=posto.id,
            post_nome=posto.name,
            titulo=TITULO_PADRAO,
            conteudo=None,
            versao=0,
        )

    return InstrucoesPostoResponse(
        post_id=posto.id,
        post_nome=posto.name,
        titulo=row.titulo or TITULO_PADRAO,
        conteudo=row.conteudo,
        versao=int(row.versao or 0),
        updated_at=row.updated_at,
        updated_by_nome=row.updated_by_nome,
    )


@router.put("/{post_id}", response_model=InstrucoesPostoResponse)
async def atualizar_instrucoes_posto(
    post_id: str,
    body: InstrucoesPostoUpdate,
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> InstrucoesPostoResponse:
    """
    Upsert das instruções do posto — SÓ GESTOR (scope.is_manager).

    Se já existe registro, a versão vigente vai para `historico` (jsonb, mantém
    as últimas 10) e `versao` é incrementada. updated_by_nome = usuário atual.
    """
    if not scope.is_manager:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Somente a gestão edita as instruções do posto.",
        )
    posto = await _post_ou_404(db, post_id)
    editor_nome = scope.user_name or "gestor"

    atual = (
        await db.execute(
            text(
                """
                SELECT titulo, conteudo, versao, updated_at, updated_by_nome,
                       historico::text AS historico
                FROM operacional_post_orders
                WHERE post_id::text = :pid
                FOR UPDATE
                """
            ),
            {"pid": post_id},
        )
    ).first()

    if atual:
        # Empurra a versão vigente para o histórico (mantém só as últimas 10)
        try:
            historico = json.loads(atual.historico) if atual.historico else []
            if not isinstance(historico, list):
                historico = []
        except (TypeError, ValueError):
            historico = []
        historico.append(
            {
                "versao": int(atual.versao or 1),
                "titulo": atual.titulo or TITULO_PADRAO,
                "conteudo": atual.conteudo,
                "updated_at": atual.updated_at.isoformat() if atual.updated_at else None,
                "updated_by_nome": atual.updated_by_nome,
            }
        )
        historico = historico[-HISTORICO_MAX:]

        nova_versao = int(atual.versao or 1) + 1
        novo_titulo = body.titulo if body.titulo else (atual.titulo or TITULO_PADRAO)
        await db.execute(
            text(
                """
                UPDATE operacional_post_orders
                SET titulo = :titulo,
                    conteudo = :conteudo,
                    versao = :versao,
                    historico = CAST(:historico AS jsonb),
                    updated_by_nome = :editor,
                    updated_at = NOW()
                WHERE post_id::text = :pid
                """
            ),
            {
                "titulo": novo_titulo,
                "conteudo": body.conteudo,
                "versao": nova_versao,
                "historico": json.dumps(historico, ensure_ascii=False),
                "editor": editor_nome,
                "pid": post_id,
            },
        )
    else:
        nova_versao = 1
        novo_titulo = body.titulo or TITULO_PADRAO
        await db.execute(
            text(
                """
                INSERT INTO operacional_post_orders
                    (post_id, titulo, conteudo, versao, historico, updated_by_nome)
                VALUES
                    (CAST(:pid AS uuid), :titulo, :conteudo, 1, '[]'::jsonb, :editor)
                """
            ),
            {
                "pid": post_id,
                "titulo": novo_titulo,
                "conteudo": body.conteudo,
                "editor": editor_nome,
            },
        )

    await db.commit()
    logger.info(
        f"Instruções do posto {posto.name} ({post_id}) atualizadas para v{nova_versao} por {editor_nome}"
    )

    row = (
        await db.execute(
            text(
                """
                SELECT titulo, conteudo, versao, updated_at, updated_by_nome
                FROM operacional_post_orders
                WHERE post_id::text = :pid
                """
            ),
            {"pid": post_id},
        )
    ).first()
    return InstrucoesPostoResponse(
        post_id=posto.id,
        post_nome=posto.name,
        titulo=(row.titulo if row else novo_titulo) or TITULO_PADRAO,
        conteudo=row.conteudo if row else body.conteudo,
        versao=int(row.versao) if row else nova_versao,
        updated_at=row.updated_at if row else None,
        updated_by_nome=row.updated_by_nome if row else editor_nome,
    )
