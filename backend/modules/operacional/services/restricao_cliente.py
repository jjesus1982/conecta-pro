"""DGX T3 (24/09/2026) — restrição de colaborador por cliente.

"Esta pessoa não pode trabalhar neste cliente." No DGX é a seção «Restrição de Colaboradores» do
cadastro do cliente, e a APROVAÇÃO da movimentação recusa com «Colaborador tem restrição nesse
cliente» — medido no trial em 24/09. Aqui a mesma parede vale nos três caminhos que põem gente
num posto: movimentação (F5 `alocar`), cobertura (F8 `registrar`) e substituto de falta
(`escalar_substituto`). Uma linha = uma restrição viva; encerrar não apaga (fica o histórico).

O elo posto/condomínio → cliente é o da casa: `posts.client_id` e `condominios.client_id`.
"""

from __future__ import annotations

from sqlalchemy import text

_DDL = (
    "CREATE TABLE IF NOT EXISTS op_restricoes_cliente ("
    " id uuid PRIMARY KEY DEFAULT gen_random_uuid(), employee_id uuid NOT NULL, client_id uuid NOT NULL,"
    " motivo text NOT NULL, solicitado_por varchar(120), ativo boolean NOT NULL DEFAULT true,"
    " criado_em timestamp NOT NULL DEFAULT (now() AT TIME ZONE 'America/Manaus'), criado_por uuid,"
    " encerrado_em timestamp, encerrado_motivo text, encerrado_por uuid)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_op_restricoes_cliente_viva ON op_restricoes_cliente (employee_id, client_id) WHERE ativo",
)


class RestricaoErro(ValueError):  # noqa: N818 — nome em PT-BR, padrão da casa
    def __init__(self, status: int, msg: str):
        super().__init__(msg)
        self.status = status


async def _ensure(db) -> None:
    for s in _DDL:
        await db.execute(text(s))


async def motivo_restricao(db, employee_id: str, client_id: str | None) -> str | None:
    """Motivo da restrição viva do colaborador nesse cliente, ou None. Cliente vazio = sem parede."""
    if not employee_id or not client_id:
        return None
    await _ensure(db)
    return (
        await db.execute(
            text(
                "SELECT motivo FROM op_restricoes_cliente WHERE ativo AND employee_id = CAST(:e AS uuid) "
                "AND client_id = CAST(:c AS uuid) LIMIT 1"
            ),
            {"e": employee_id, "c": client_id},
        )
    ).scalar()


async def client_do_posto(db, post_id: str | None) -> str | None:
    if not post_id:
        return None
    return (
        await db.execute(text("SELECT client_id::text FROM posts WHERE id = CAST(:p AS uuid)"), {"p": post_id})
    ).scalar()


async def client_do_condominio(db, condominio_id: str | None) -> str | None:
    if not condominio_id:
        return None
    return (
        await db.execute(
            text("SELECT client_id::text FROM condominios WHERE id = CAST(:c AS uuid)"), {"c": condominio_id}
        )
    ).scalar()


async def exigir_livre(db, employee_id: str, *, post_id: str | None = None, condominio_id: str | None = None) -> None:
    """Levanta RestricaoErro(422) se o colaborador tem restrição viva no cliente do posto/condomínio."""
    client_id = await client_do_posto(db, post_id) or await client_do_condominio(db, condominio_id)
    motivo = await motivo_restricao(db, employee_id, client_id)
    if motivo:
        nome = (
            await db.execute(text("SELECT nome FROM employees WHERE id = CAST(:e AS uuid)"), {"e": employee_id})
        ).scalar() or "O colaborador"
        cli = (
            await db.execute(text("SELECT name FROM clients WHERE id = CAST(:c AS uuid)"), {"c": client_id})
        ).scalar() or "esse cliente"
        raise RestricaoErro(422, f"{nome} tem restrição em {cli}: {motivo}. Encerre a restrição antes de alocar.")


async def incluir(
    db, *, employee_id: str, client_id: str, motivo: str, solicitado_por: str | None = None, user_id: str | None = None
) -> dict:
    await _ensure(db)
    motivo = (motivo or "").strip()
    if not employee_id or not client_id:
        raise RestricaoErro(400, "Colaborador e cliente são obrigatórios.")
    if len(motivo) < 5:
        raise RestricaoErro(400, "Descreva o motivo (mínimo 5 caracteres) — é o que o DP vai ler daqui a um ano.")
    if await motivo_restricao(db, employee_id, client_id):
        raise RestricaoErro(409, "Já existe restrição viva desse colaborador nesse cliente.")
    rid = (
        await db.execute(
            text(
                "INSERT INTO op_restricoes_cliente (employee_id, client_id, motivo, solicitado_por, criado_por) "
                "VALUES (CAST(:e AS uuid), CAST(:c AS uuid), :m, :s, CAST(:u AS uuid)) RETURNING id::text"
            ),
            {"e": employee_id, "c": client_id, "m": motivo, "s": (solicitado_por or "").strip() or None, "u": user_id},
        )
    ).scalar()
    aloc = (
        await db.execute(
            text(
                "SELECT count(*) FROM employee_alocacoes a JOIN condominios c ON c.id = a.condominio_id "
                "WHERE a.ativo AND a.employee_id = CAST(:e AS uuid) AND c.client_id = CAST(:c AS uuid)"
            ),
            {"e": employee_id, "c": client_id},
        )
    ).scalar()
    await db.commit()
    return {"id": rid, "alocado_hoje_no_cliente": int(aloc or 0)}


async def encerrar(db, *, restricao_id: str, motivo: str | None = None, user_id: str | None = None) -> dict:
    await _ensure(db)
    n = (
        await db.execute(
            text(
                "UPDATE op_restricoes_cliente SET ativo=false, encerrado_em=(now() AT TIME ZONE 'America/Manaus'), "
                "encerrado_motivo=:m, encerrado_por=CAST(:u AS uuid) WHERE id = CAST(:i AS uuid) AND ativo RETURNING id"
            ),
            {"i": restricao_id, "m": (motivo or "").strip() or None, "u": user_id},
        )
    ).rowcount
    if not n:
        raise RestricaoErro(404, "Restrição não encontrada ou já encerrada.")
    await db.commit()
    return {"id": restricao_id}
