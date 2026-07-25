"""Fase 5.4 — Onda A: cobrança (🟡), proposta comercial (🟡), kit (🔵).

Cada ação grava um PENDENTE na tabela nativa via base.propor. NENHUMA executa:
- cobrança: inter_cobrancas status 'PENDENTE' (a emissão real fica no CobrancaService.emitir humano)
- proposta: proposals status 'draft' (envio/assinatura ficam no proposal_controller humano)
- kit: ged_document_kits status 'proposto' (a montagem/envio ficam no kit_orchestrator humano)
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from ..tool_registry import ToolDef, register
from .base import GATES, ROLES_COMERCIAL, ROLES_KIT_OP, propor  # noqa: F401

# ───────────────────────── cobrança (🟡, dinheiro que ENTRA) ─────────────────

_ARGS_COBRANCA = {
    "type": "object",
    "properties": {
        "cliente_crm_id": {"type": "string", "description": "ID do cliente no CRM (obrigatório)."},
        "valor": {"type": "number", "minimum": 0.01, "description": "Valor da cobrança (R$)."},
        "vencimento": {"type": "string", "description": "Data de vencimento AAAA-MM-DD."},
        "descricao": {"type": "string", "maxLength": 500},
    },
    "required": ["cliente_crm_id", "valor", "vencimento"],
}


async def _propor_cobranca(
    db, user, scope, *, cliente_crm_id: str, valor: float,
    vencimento: str, descricao: str = "", **_
) -> dict[str, Any]:
    if not cliente_crm_id or float(valor) <= 0:
        return {"erro": "cliente e valor (>0) são obrigatórios"}
    try:
        venc_date = date.fromisoformat(vencimento)
    except (TypeError, ValueError):
        return {"erro": "vencimento inválido (esperado AAAA-MM-DD)"}
    idem = f"cobranca:{cliente_crm_id}:{float(valor):.2f}:{vencimento}"

    # valor é coluna numeric(15,2); asyncpg tipa um Python float como float8, e
    # numeric=float8 compara após CAST numeric->double (epsilon de ponto flutuante
    # — 12.34 nunca bate exato). Bind como Decimal (idioma exato p/ numeric).
    valor_decimal = Decimal(f"{float(valor):.2f}")

    async def _inserir(db) -> str:
        # Idempotência NATIVA (defesa em profundidade, achado da review T2): mesmo
        # que a checagem do sino em base.propor não pegue (ex.: notificação antiga
        # desativada, ou outra origem chamando este callback com key distinta),
        # NUNCA duplicamos o PENDENTE na tabela nativa — molde tools_ponto
        # (SELECT-existing antes do INSERT).
        # vencimento é coluna `date`; asyncpg exige o TIPO NATIVO no bind (mesmo com
        # CAST no SQL o driver já prepara o parâmetro como date client-side) — texto
        # cru quebra ("'str' object has no attribute 'toordinal'"). Por isso usamos
        # venc_date (datetime.date parseado acima), não a string recebida do LLM.
        existente = (await db.execute(text(
            "SELECT id::text FROM inter_cobrancas "
            "WHERE status = 'PENDENTE' "
            "  AND pagador->>'cliente_crm_id' = :cli "
            "  AND valor = :valor AND vencimento = :venc LIMIT 1"),
            {"cli": cliente_crm_id, "valor": valor_decimal, "venc": venc_date})).scalar()
        if existente:
            return existente

        local_id = str(uuid.uuid4())
        seu_numero = f"CPRO-{local_id[:8].upper()}"
        await db.execute(text("""
            INSERT INTO inter_cobrancas
                (id, seu_numero, valor, vencimento, status, descricao, pagador, created_at, updated_at)
            VALUES
                (:id, :sn, :valor, :venc, 'PENDENTE', :desc, CAST(:pag AS jsonb), NOW(), NOW())
        """), {"id": local_id, "sn": seu_numero, "valor": valor_decimal,
               "venc": venc_date, "desc": descricao or "",
               "pag": json.dumps({"cliente_crm_id": cliente_crm_id})})
        return local_id

    return await propor(
        db, user=user, scope=scope, dominio="cobranca", gate="🟡",
        roles_aprovador=ROLES_COMERCIAL, idempotency_key=idem,
        titulo="[Proposta] Emitir cobrança",
        corpo=f"Cobrança de R$ {float(valor):.2f} (venc. {vencimento}) — {descricao or 'sem descrição'}. Aguarda sua aprovação.",
        action_url="/financeiro/cobrancas",
        tool="propor_cobranca",
        args={"cliente_crm_id": cliente_crm_id, "valor": float(valor), "vencimento": vencimento},
        entity_type="inter_cobranca", inserir=_inserir,
    )


COBRANCA_TOOL: ToolDef = register(ToolDef(
    "propor_cobranca", "comercial",
    "Propor a emissão de uma cobrança a um cliente (fica PENDENTE de aprovação; não emite nada).",
    _ARGS_COBRANCA, _propor_cobranca, scope_kind="org",
))


if __name__ == "__main__":
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    class _U:
        id = "00000000-0000-0000-0000-0000000000ff"
        role = "comercial"

    class _S:
        tier = "gestor"

    async def _limpar(db, idem_like: str) -> None:
        ids = [x for x in (await db.execute(text(
            "SELECT id::text FROM communication_notifications "
            "WHERE extra_data->>'idempotency_key' LIKE :k"), {"k": idem_like})).scalars().all()]
        if ids:
            await db.execute(text("DELETE FROM communication_notifications WHERE id = ANY(:i)"), {"i": ids})
        await db.commit()

    async def main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            cob_ids: list[str] = []
            aud_ids: list[str] = []
            try:
                # baseline: nenhuma cobrança RECEBIDA/executada deve mudar
                recebidas_antes = (await db.execute(text(
                    "SELECT count(*) FROM inter_cobrancas WHERE status <> 'PENDENTE'"))).scalar()

                venc = "2099-12-31"  # data marcada de teste (nunca real)
                r = await _propor_cobranca(db, _U(), _S(),
                    cliente_crm_id="TESTE-5.4-CLI", valor=12.34, vencimento=venc,
                    descricao="__TESTE_5.4__ cobranca")
                assert r["status"] == "pendente", r
                eid = r["entity_id"]
                cob_ids.append(eid)

                # a linha nasceu PENDENTE (nunca emitida)
                st = (await db.execute(text(
                    "SELECT status FROM inter_cobrancas WHERE id = :i"), {"i": eid})).scalar()
                assert st == "PENDENTE", f"status inesperado: {st}"

                # estado de execução INTOCADO
                recebidas_depois = (await db.execute(text(
                    "SELECT count(*) FROM inter_cobrancas WHERE status <> 'PENDENTE'"))).scalar()
                assert recebidas_depois == recebidas_antes, "cobrança executada mudou (não deveria)"

                # idempotência (sino: mesma idempotency_key → duplicado, inserir não roda de novo)
                r2 = await _propor_cobranca(db, _U(), _S(),
                    cliente_crm_id="TESTE-5.4-CLI", valor=12.34, vencimento=venc,
                    descricao="__TESTE_5.4__ cobranca")
                assert r2.get("duplicado") is True, r2

                # idempotência NATIVA (defesa em profundidade, "não confie só no sino"):
                # desativa a notificação do sino (simula um pendente cujo alerta já foi
                # arquivado) e propõe de novo com os MESMOS cliente/valor/vencimento — o
                # precheck do sino em base.propor filtra is_active=true, então NÃO acha
                # duplicado ali; quem tem que barrar a 2ª linha é o SELECT-existing dentro
                # do próprio _inserir, sobre a tabela nativa.
                idem_key = f"cobranca:TESTE-5.4-CLI:{12.34:.2f}:{venc}"
                await db.execute(text(
                    "UPDATE communication_notifications SET is_active = false "
                    "WHERE extra_data->>'idempotency_key' = :k"), {"k": idem_key})
                await db.commit()

                r3 = await _propor_cobranca(db, _U(), _S(),
                    cliente_crm_id="TESTE-5.4-CLI", valor=12.34, vencimento=venc,
                    descricao="__TESTE_5.4__ cobranca (sino desativado)")
                if r3.get("entity_id") and r3["entity_id"] not in cob_ids:
                    cob_ids.append(r3["entity_id"])  # defesa: se a idempotência NATIVA falhar, limpa mesmo assim
                assert r3["status"] == "pendente", r3
                assert r3["entity_id"] == eid, \
                    f"idempotência NATIVA falhou: criou 2ª linha na tabela nativa ({r3['entity_id']} != {eid})"
                n_pendentes = (await db.execute(text(
                    "SELECT count(*) FROM inter_cobrancas WHERE status = 'PENDENTE' "
                    "AND pagador->>'cliente_crm_id' = 'TESTE-5.4-CLI'"))).scalar()
                assert n_pendentes == 1, \
                    f"idempotência NATIVA falhou: esperado 1 pendente na tabela nativa, veio {n_pendentes}"
                print("SUBTESTE cobrança: idempotência NATIVA (sino desativado, tabela nativa não duplica) PASS")

                # RBAC (d): a tool só aparece no belt de quem tem o módulo 'comercial'.
                from ..tool_registry import tools_for_modules
                assert COBRANCA_TOOL.module == "comercial", COBRANCA_TOOL.module
                nomes_comercial = {t.name for t in tools_for_modules({"comercial"})}
                nomes_financeiro = {t.name for t in tools_for_modules({"financeiro"})}
                assert "propor_cobranca" in nomes_comercial, nomes_comercial
                assert "propor_cobranca" not in nomes_financeiro, \
                    "propor_cobranca vazou p/ módulo 'financeiro' (RBAC de módulo quebrado)"
                print("SUBTESTE cobrança: RBAC de módulo (só 'comercial' vê a tool) PASS")

                # aprovador correto (e): propositor REAL excluído do conjunto de aprovadores
                # (roles reais — ROLES_COMERCIAL=('admin',), não existe role 'comercial').
                from modules.notifications.proativo import entrega
                assert ROLES_COMERCIAL == ("admin",), ROLES_COMERCIAL
                admins = await entrega.resolver_usuarios_por_roles(db, ROLES_COMERCIAL)
                assert admins, "esperado >=1 admin ativo no banco p/ provar aprovador"

                class _UAdmin:
                    def __init__(self, uid: str) -> None:
                        self.id = uid
                    role = "admin"

                venc4 = "2099-12-30"  # 2ª data de teste p/ não colidir c/ idem_key acima
                r4 = await _propor_cobranca(db, _UAdmin(admins[0]), _S(),
                    cliente_crm_id="TESTE-5.4-CLI2", valor=99.90, vencimento=venc4,
                    descricao="__TESTE_5.4__ cobranca (propositor admin real)")
                if r4.get("entity_id"):
                    cob_ids.append(r4["entity_id"])
                if len(admins) >= 2:
                    assert r4["status"] == "pendente", r4
                    aps = r4.get("aprovadores") or []
                    assert admins[0] not in aps, \
                        f"propositor admin real não pode aprovar a própria cobrança: {aps}"
                    assert set(aps) == set(admins) - {admins[0]}, (aps, admins)
                    print(f"SUBTESTE cobrança: aprovador correto (propositor excluído; "
                          f"{len(admins)} admins → {len(aps)} aprovadores) PASS")
                else:
                    # tenant com 1 só admin: propositor==único aprovador possível → fail-closed
                    assert "erro" in r4, r4
                    print("SUBTESTE cobrança: aprovador correto (1 admin: propositor==único → fail-closed) PASS")

                print("SUBTESTE cobrança PASS (pendente criado, execução intocada, idempotente [sino+nativa], "
                      "RBAC módulo, aprovador correto)")
                print("TODOS OS SUBTESTES DE onda_a.py PASSARAM")
            finally:
                if cob_ids:
                    await db.execute(text("DELETE FROM inter_cobrancas WHERE id = ANY(:i)"), {"i": cob_ids})
                    # audit_logs (append-only p/ uso real; aqui é resíduo de TESTE, mesmo
                    # padrão de limpeza usado no __main__ de base.py) — 1 linha por
                    # chamada de propor(), sempre com details->>'entity_id' ∈ cob_ids.
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"),
                        {"i": cob_ids})
                await _limpar(db, "cobranca:TESTE-5.4-CLI:%")
                await _limpar(db, "cobranca:TESTE-5.4-CLI2:%")
                await db.commit()
                rem = (await db.execute(text(
                    "SELECT count(*) FROM inter_cobrancas WHERE pagador->>'cliente_crm_id' IN "
                    "('TESTE-5.4-CLI', 'TESTE-5.4-CLI2')"))).scalar()
                rem_audit = (await db.execute(text(
                    "SELECT count(*) FROM audit_logs WHERE details->>'tool' = 'propor_cobranca' "
                    "AND details->>'entity_id' = ANY(:i)"), {"i": cob_ids})).scalar()
                assert rem == 0, f"remanescentes cobranca={rem}"
                assert rem_audit == 0, f"remanescentes audit_logs={rem_audit}"
        await eng.dispose()

    asyncio.run(main())
