"""Fase 5.3 — Entrega RBAC no SINO real.

Resolve destinatários por ROLE (sobrevive a troca de pessoa; molde
_destinatarios_operacionais) e materializa no sino communication_notifications
(molde _enviar_alerta: tenant_id=uid, TZ Manaus, extra_data com correlation_id
p/ auditoria/dedup). READ-ONLY exceto a criação da notificação. NÃO aciona ação.

O destinatário vem SEMPRE de `regra.roles_destino` (server-side, ver regras.py)
— NUNCA do achado/LLM. Esta é a matriz RBAC: financeiro (caixa/aging) tem
roles_destino=("admin",) e portanto SÓ chega a admin, nunca a gerente
operacional/supervisor/funcionário.
"""
from __future__ import annotations

import json
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

_NOW = "(now() AT TIME ZONE 'America/Manaus')"


async def resolver_usuarios_por_roles(db: AsyncSession, roles: tuple[str, ...]) -> list[str]:
    """Resolve ids de `users` ATIVOS cujo role está em `roles` — 1 conta por
    PESSOA (DISTINCT ON lower(name), prefere @conectamais.pro em empate).
    Mesmo molde de `_destinatarios_operacionais` (notification_triggers.py),
    generalizado para qualquer conjunto de roles."""
    if not roles:
        return []
    rows = (await db.execute(text(
        "SELECT DISTINCT ON (lower(name)) id::text FROM users "
        "WHERE lower(coalesce(role,'')) = ANY(:roles) "
        "  AND coalesce(is_active, true) = true "
        "ORDER BY lower(name), (lower(coalesce(email,'')) LIKE '%@conectamais.pro') DESC"),
        {"roles": [r.lower() for r in roles]})).fetchall()
    return [r[0] for r in rows]


async def enviar_individual(db: AsyncSession, *, user_ids: list[str], title: str,
                            body: str, familia: str, severidade: str,
                            correlation_id: str, action_url: str,
                            reference_type: str = "proativo",
                            reference_id: str | None = None,
                            idempotency_key: str | None = None) -> list[str]:
    """Materializa o alerta no sino (communication_notifications), 1 linha por
    destinatário. `user_ids` já deve vir de `resolver_usuarios_por_roles` com os
    roles de destino — esta função não decide RBAC, só grava.
    tenant_id = uid (users não tem coluna tenant_id; o sino filtra por
    tenant_id == user.id). extra_data carrega correlation_id + (opcional)
    idempotency_key p/ rastreio/dedup/auditoria. reference_type/reference_id
    ligam a notificação à entidade proposta (ex.: 'proposta_acao' + entity_id).

    Idempotência ATÔMICA: `ON CONFLICT DO NOTHING` casa com o índice único parcial
    `uq_notif_idempotency_user (user_id, extra_data->>'idempotency_key')` — re-criar
    o mesmo (destinatário, idempotency_key) é bloqueado pelo banco (retorna 0 linhas,
    filtrado abaixo), enquanto destinatários distintos passam. Rows sem
    idempotency_key (5.3 e anteriores) ficam fora do índice parcial → conflito
    nunca dispara, comportamento legado preservado."""
    criados: list[str] = []
    for uid in user_ids:
        extra = json.dumps({"correlation_id": correlation_id, "familia": familia,
                            "severidade": severidade, "origem": "proativo",
                            "idempotency_key": idempotency_key})
        row = (await db.execute(text(
            f"INSERT INTO communication_notifications "
            f"(id, tenant_id, user_id, title, body, type, reference_type, "
            f" reference_id, action_url, extra_data, is_active, sent_at, created_at) "
            f"VALUES (gen_random_uuid(), :tid, :uid, :title, :body, 'alerta', "
            f" :rtype, :rid, :url, CAST(:extra AS jsonb), true, {_NOW}, {_NOW}) "
            f"ON CONFLICT DO NOTHING "
            f"RETURNING id::text"),
            {"tid": str(uid), "uid": str(uid), "title": title, "body": body,
             "rtype": reference_type, "rid": reference_id,
             "url": action_url, "extra": extra})).scalar()
        if row:  # None quando ON CONFLICT DO NOTHING suprimiu a duplicata (destinatário, key)
            criados.append(row)
    return criados


if __name__ == "__main__":
    import asyncio
    import os

    from sqlalchemy import text as _t
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        criados: list[str] = []
        async with Session() as db:
            try:
                # resolução por role: admin != gerente_operacional/supervisor
                admins = await resolver_usuarios_por_roles(db, ("admin",))
                gestores = await resolver_usuarios_por_roles(db, ("gerente_operacional", "supervisor"))
                assert admins, "esperado >=1 admin"
                assert set(admins).isdisjoint(set(gestores)), \
                    "admin e gerente_operacional/supervisor devem ser papéis disjuntos"

                # entrega financeira → SÓ admins (matriz RBAC: roles_destino=("admin",))
                criados = await enviar_individual(
                    db, user_ids=admins, title="[TESTE] Caixa baixo",
                    body="teste rbac", familia="financeiro", severidade="critico",
                    correlation_id="caixa_baixo:__TESTE_RBAC__:2026-07",
                    action_url="/x")
                await db.commit()
                assert len(criados) == len(admins)

                # PROVA NEGATIVA no banco: nenhuma notif financeira de teste para não-admin
                ids_gestores = [str(g) for g in gestores]
                if ids_gestores:
                    vaz = (await db.execute(_t(
                        "SELECT count(*) FROM communication_notifications "
                        "WHERE user_id = ANY(:g) "
                        "AND extra_data->>'correlation_id' = 'caixa_baixo:__TESTE_RBAC__:2026-07'"),
                        {"g": ids_gestores})).scalar()
                    assert vaz == 0, f"vazou financeiro p/ gestor: {vaz}"

                # entrega operacional → alcança admin+gerente_operacional+supervisor,
                # e NÃO alcança quem está fora desse conjunto (funcionário/agente/etc.)
                op_roles = ("admin", "gerente_operacional", "supervisor")
                op_dest = await resolver_usuarios_por_roles(db, op_roles)
                fora_op = await resolver_usuarios_por_roles(db, ("funcionario", "agente", "lider"))
                assert set(op_dest).isdisjoint(set(fora_op))
                criados_op = await enviar_individual(
                    db, user_ids=op_dest, title="[TESTE] Posto descoberto",
                    body="teste rbac operacional", familia="operacional", severidade="critico",
                    correlation_id="posto_descoberto:__TESTE_RBAC_OP__:2026-07",
                    action_url="/y")
                await db.commit()
                criados.extend(criados_op)
                assert len(criados_op) == len(op_dest)

                got_op = set((await db.execute(_t(
                    "SELECT user_id::text FROM communication_notifications "
                    "WHERE extra_data->>'correlation_id' = 'posto_descoberto:__TESTE_RBAC_OP__:2026-07'"
                ))).scalars().all())
                assert got_op == set(op_dest), (got_op, set(op_dest))
                if fora_op:
                    vaz_op = (await db.execute(_t(
                        "SELECT count(*) FROM communication_notifications "
                        "WHERE user_id = ANY(:f) "
                        "AND extra_data->>'correlation_id' = 'posto_descoberto:__TESTE_RBAC_OP__:2026-07'"),
                        {"f": [str(x) for x in fora_op]})).scalar()
                    assert vaz_op == 0, f"vazou operacional p/ fora do conjunto: {vaz_op}"

                print(f"OK entrega — {len(admins)} admin(s) financeiro, "
                      f"{len(op_dest)} destinatário(s) operacional, 0 vazamento RBAC")
            finally:
                if criados:
                    await db.execute(_t(
                        "DELETE FROM communication_notifications WHERE id = ANY(:ids)"),
                        {"ids": criados})
                    await db.commit()
                rem = (await db.execute(_t(
                    "SELECT count(*) FROM communication_notifications "
                    "WHERE extra_data->>'correlation_id' IN "
                    "('caixa_baixo:__TESTE_RBAC__:2026-07', 'posto_descoberto:__TESTE_RBAC_OP__:2026-07')"
                ))).scalar()
                assert rem == 0, f"remanescentes={rem}"
        await eng.dispose()

    asyncio.run(main())
