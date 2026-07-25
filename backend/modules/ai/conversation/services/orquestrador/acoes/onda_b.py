"""Fase 5.4 — Onda B: substituição de posto (propor→humano).

O agente PROPÕE um substituto; a proposta cai em op_substituicao_propostas
'pendente'. O gestor aprova e aplica MANUALMENTE. NUNCA escreve allocations
(operacional READ-ONLY para o agente).
"""
from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy import text

from ..tool_registry import ToolDef, register
from .base import ROLES_KIT_OP, propor

_ARGS_SUBST = {
    "type": "object",
    "properties": {
        "post_id": {"type": "string", "description": "ID do posto a cobrir."},
        "data": {"type": "string", "description": "Data da cobertura AAAA-MM-DD."},
        "ausente_employee_id": {"type": "string", "description": "Quem faltará/faltou."},
        "substituto_employee_id": {"type": "string", "description": "Substituto proposto."},
        "motivo": {"type": "string", "maxLength": 500},
    },
    "required": ["post_id", "data", "ausente_employee_id", "substituto_employee_id"],
}


async def _propor_substituicao(
    db, user, scope, *, post_id: str, data: str, ausente_employee_id: str,
    substituto_employee_id: str, motivo: str = "", **_
) -> dict[str, Any]:
    if not (post_id and data and ausente_employee_id and substituto_employee_id):
        return {"erro": "post_id, data, ausente e substituto são obrigatórios"}
    if ausente_employee_id == substituto_employee_id:
        return {"erro": "substituto não pode ser a própria pessoa ausente"}
    try:
        data_date = date.fromisoformat(data)
    except (TypeError, ValueError):
        return {"erro": "data inválida (esperado AAAA-MM-DD)"}
    idem = f"substituicao:{post_id}:{data}:{ausente_employee_id}"

    async def _inserir(db) -> str:
        # Idempotência NATIVA (defesa em profundidade, molde cobrança/kit em
        # onda_a.py): mesmo que o precheck do sino em base.propor não pegue
        # (ex.: notificação antiga desativada), NUNCA duplicamos o PENDENTE na
        # tabela nativa — SELECT-existing antes do INSERT, sobre o mesmo grão
        # da idempotency_key (post_id, data, ausente).
        # `data` é coluna `date`; asyncpg exige o TIPO NATIVO no bind (mesmo
        # padrão de vencimento em onda_a.py — texto cru quebra: "'str' object
        # has no attribute 'toordinal'"). Por isso usamos data_date (parseado
        # acima), não a string recebida do LLM.
        existente = (await db.execute(text(
            "SELECT id FROM op_substituicao_propostas "
            "WHERE status = 'pendente' AND post_id = :pid AND data = :dt "
            "  AND ausente_employee_id = :aus LIMIT 1"),
            {"pid": post_id, "dt": data_date, "aus": ausente_employee_id})).scalar()
        if existente:
            return existente

        sid = str(uuid.uuid4())
        await db.execute(text("""
            INSERT INTO op_substituicao_propostas
                (id, post_id, data, ausente_employee_id, substituto_employee_id,
                 motivo, status, proposto_por)
            VALUES (:id, :pid, :dt, :aus, :sub, :mot, 'pendente', :prop)
        """), {"id": sid, "pid": post_id, "dt": data_date, "aus": ausente_employee_id,
               "sub": substituto_employee_id, "mot": motivo or None,
               "prop": str(getattr(user, "id", None))})
        return sid

    return await propor(
        db, user=user, scope=scope, dominio="substituicao", gate="🔵",
        roles_aprovador=ROLES_KIT_OP, idempotency_key=idem,
        titulo="[Proposta] Substituição de posto",
        corpo=f"Cobrir posto {post_id} em {data}: propor {substituto_employee_id} no lugar de {ausente_employee_id}. {motivo or ''}".strip(),
        action_url="/operacional/escala",
        tool="propor_substituicao",
        args={"post_id": post_id, "data": data, "ausente_employee_id": ausente_employee_id,
              "substituto_employee_id": substituto_employee_id},
        entity_type="op_substituicao_proposta", inserir=_inserir,
    )


SUBSTITUICAO_TOOL: ToolDef = register(ToolDef(
    "propor_substituicao", "operacional",
    "Propor um substituto para cobrir um posto (fica PENDENTE; o gestor aprova e aplica a escala à mão — o agente NUNCA altera a escala).",
    _ARGS_SUBST, _propor_substituicao, scope_kind="org",
))

SUBSTITUICAO_TOOLS = [SUBSTITUICAO_TOOL]


if __name__ == "__main__":
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    class _U:
        id = "00000000-0000-0000-0000-0000000000ff"
        role = "gerente_operacional"

    class _S:
        tier = "gestor"

    async def main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            sub_ids: list[str] = []
            try:
                # snapshot de allocations/posts: substituição NUNCA pode mexer nisto
                aloc_antes = (await db.execute(text("SELECT count(*) FROM allocations"))).scalar()
                posts_antes = (await db.execute(text("SELECT count(*) FROM posts"))).scalar()

                r = await _propor_substituicao(db, _U(), _S(),
                    post_id="__TESTE_5.4__POSTO", data="2099-01-01",
                    ausente_employee_id="EMP-A", substituto_employee_id="EMP-B",
                    motivo="__TESTE_5.4__")
                assert r["status"] == "pendente", r
                sid = r["entity_id"]
                sub_ids.append(sid)
                st = (await db.execute(text(
                    "SELECT status FROM op_substituicao_propostas WHERE id = :i"), {"i": sid})).scalar()
                assert st == "pendente", st

                # escala INTOCADA (allocations E posts)
                aloc_depois = (await db.execute(text("SELECT count(*) FROM allocations"))).scalar()
                posts_depois = (await db.execute(text("SELECT count(*) FROM posts"))).scalar()
                assert aloc_depois == aloc_antes, "allocations mudou (operacional deveria ser read-only)"
                assert posts_depois == posts_antes, "posts mudou (operacional deveria ser read-only)"
                print("SUBTESTE substituição: pendente criado + escala (allocations/posts) INTOCADA PASS")

                # idempotência (sino)
                r2 = await _propor_substituicao(db, _U(), _S(),
                    post_id="__TESTE_5.4__POSTO", data="2099-01-01",
                    ausente_employee_id="EMP-A", substituto_employee_id="EMP-B")
                assert r2.get("duplicado") is True, r2
                print("SUBTESTE substituição: idempotência (sino) — 2 chamadas = 1 pendente PASS")

                # idempotência NATIVA (defesa em profundidade, "não confie só no sino"):
                # desativa a notificação e propõe de novo com o MESMO grão — quem tem
                # que barrar a 2ª linha é o SELECT-existing dentro do próprio _inserir.
                await db.execute(text(
                    "UPDATE communication_notifications SET is_active = false "
                    "WHERE extra_data->>'idempotency_key' = :k"),
                    {"k": "substituicao:__TESTE_5.4__POSTO:2099-01-01:EMP-A"})
                await db.commit()
                r3 = await _propor_substituicao(db, _U(), _S(),
                    post_id="__TESTE_5.4__POSTO", data="2099-01-01",
                    ausente_employee_id="EMP-A", substituto_employee_id="EMP-B",
                    motivo="__TESTE_5.4__ (sino desativado)")
                if r3.get("entity_id") and r3["entity_id"] not in sub_ids:
                    sub_ids.append(r3["entity_id"])
                assert r3["status"] == "pendente", r3
                assert str(r3["entity_id"]) == str(sid), \
                    f"idempotência NATIVA falhou: criou 2ª linha ({r3['entity_id']} != {sid})"
                n_pend = (await db.execute(text(
                    "SELECT count(*) FROM op_substituicao_propostas "
                    "WHERE post_id = '__TESTE_5.4__POSTO' AND status = 'pendente'"))).scalar()
                assert n_pend == 1, f"idempotência NATIVA falhou: esperado 1 pendente, veio {n_pend}"
                print("SUBTESTE substituição: idempotência NATIVA (sino desativado, tabela nativa não duplica) PASS")

                # RBAC de módulo: a tool só aparece no belt de 'operacional'.
                from ..tool_registry import tools_for_modules
                assert SUBSTITUICAO_TOOL.module == "operacional", SUBSTITUICAO_TOOL.module
                nomes_operacional = {t.name for t in tools_for_modules({"operacional"})}
                nomes_financeiro = {t.name for t in tools_for_modules({"financeiro"})}
                assert "propor_substituicao" in nomes_operacional, nomes_operacional
                assert "propor_substituicao" not in nomes_financeiro, \
                    "propor_substituicao vazou p/ módulo 'financeiro' (RBAC de módulo quebrado)"
                print("SUBTESTE substituição: RBAC de módulo (só 'operacional' vê a tool) PASS")

                # aprovador correto (e): propositor REAL (admin) excluído do conjunto
                # de aprovadores — ROLES_KIT_OP = ('admin', 'gerente_operacional').
                from modules.notifications.proativo import entrega
                assert ROLES_KIT_OP == ("admin", "gerente_operacional"), ROLES_KIT_OP
                aprovadores_possiveis = await entrega.resolver_usuarios_por_roles(db, ROLES_KIT_OP)
                assert aprovadores_possiveis, "esperado >=1 admin/gerente_operacional ativo no banco"

                class _UAdmin:
                    def __init__(self, uid: str) -> None:
                        self.id = uid
                    role = "admin"

                r4 = await _propor_substituicao(db, _UAdmin(aprovadores_possiveis[0]), _S(),
                    post_id="__TESTE_5.4__POSTO2", data="2099-01-02",
                    ausente_employee_id="EMP-C", substituto_employee_id="EMP-D",
                    motivo="__TESTE_5.4__ (propositor admin real)")
                if r4.get("entity_id"):
                    sub_ids.append(r4["entity_id"])
                if len(aprovadores_possiveis) >= 2:
                    assert r4["status"] == "pendente", r4
                    aps = r4.get("aprovadores") or []
                    assert aprovadores_possiveis[0] not in aps, \
                        f"propositor não pode aprovar a própria proposta: {aps}"
                    assert set(aps) == set(aprovadores_possiveis) - {aprovadores_possiveis[0]}, \
                        (aps, aprovadores_possiveis)
                    print(f"SUBTESTE substituição: aprovador correto (propositor excluído; "
                          f"{len(aprovadores_possiveis)} possíveis → {len(aps)} aprovadores) PASS")
                else:
                    assert "erro" in r4, r4
                    print("SUBTESTE substituição: aprovador correto (fail-closed: propositor==único possível) PASS")

                print("TESTE substituição PASS (pendente criado, escala intocada, idempotente [sino+nativa], "
                      "RBAC módulo, aprovador correto)")
                print("TODOS OS TESTES DE onda_b.py PASSARAM")
            finally:
                if sub_ids:
                    await db.execute(text("DELETE FROM op_substituicao_propostas WHERE id = ANY(:i)"), {"i": sub_ids})
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"),
                        {"i": sub_ids})
                ids = [x for x in (await db.execute(text(
                    "SELECT id::text FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' LIKE 'substituicao:__TESTE_5.4__%'"))).scalars().all()]
                if ids:
                    await db.execute(text("DELETE FROM communication_notifications WHERE id = ANY(:i)"), {"i": ids})
                await db.commit()
                rem = (await db.execute(text(
                    "SELECT count(*) FROM op_substituicao_propostas WHERE post_id LIKE '__TESTE_5.4__POSTO%'"))).scalar()
                rem_audit = (await db.execute(text(
                    "SELECT count(*) FROM audit_logs WHERE details->>'tool' = 'propor_substituicao' "
                    "AND details->>'entity_id' = ANY(:i)"), {"i": sub_ids})).scalar()
                assert rem == 0, f"remanescentes subst={rem}"
                assert rem_audit == 0, f"remanescentes audit_logs={rem_audit}"
                print("LIMPEZA OK — 0 remanescentes (op_substituicao_propostas/notif/audit)")
        await eng.dispose()

    asyncio.run(main())
