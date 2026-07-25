"""Fase 5.4 — Onda C (🔴): lote de pagamento + eSocial.

Ambas 🔴: o agente só PROPÕE. A execução real exige gate humano existente:
- lote: preparar_lote grava inter_payments 'preparado' (não move dinheiro); a
  execução (gerar_otp_lote + executar_lote com OTP no email do Jordan) é 100%
  humana e permanece INTACTA. Teto CONECTA_LIMITE_DIARIO_PAGAMENTOS respeitado.
- eSocial: marca esocial_transmissao_propostas 'pendente'; o humano dispara a
  transmissão via esocial_tasks. O agente NUNCA transmite ao gov.
"""
from __future__ import annotations

import os
import uuid
from typing import Any

from sqlalchemy import text

from ..tool_registry import ToolDef, register
from .base import ROLES_MONEY, propor

# ───────────────────────── lote de pagamento (🔴, dinheiro SAI) ──────────────

_ARGS_LOTE = {
    "type": "object",
    "properties": {
        "posto": {"type": "string", "description": "Posto/condomínio do lote."},
        "competencia": {"type": "string", "description": "Competência AAAA-MM."},
        "itens": {
            "type": "array",
            "description": "Beneficiários do lote.",
            "items": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string"},
                    "chave": {"type": "string", "description": "Chave PIX."},
                    "valor": {"type": "number", "minimum": 0.01},
                },
                "required": ["nome", "chave", "valor"],
            },
        },
    },
    "required": ["posto", "competencia", "itens"],
}


async def _propor_lote(
    db, user, scope, *, posto: str, competencia: str, itens: list[dict], **_
) -> dict[str, Any]:
    if not posto or not competencia or not itens:
        return {"erro": "posto, competencia e itens são obrigatórios"}
    total = sum(float(it.get("valor") or 0) for it in itens)
    if total <= 0:
        return {"erro": "total do lote deve ser > 0"}
    # Teto de PROPOSTA = mesmo teto diário do Inter (defesa em profundidade).
    teto = float(os.environ.get("CONECTA_LIMITE_DIARIO_PAGAMENTOS") or "100000")
    if total > teto:
        return {"erro": f"total do lote (R$ {total:.2f}) acima do teto (R$ {teto:.2f}); use o fluxo manual/OTP"}
    idem = f"lote:{posto}:{competencia}:{total:.2f}"

    async def _inserir(db) -> str:
        # Idempotência NATIVA (anti-lote-dobro, defesa em profundidade — molde
        # onda_a, achado da review T2): mesmo que o precheck do sino em base.propor
        # NÃO pegue (notificação antiga desativada/arquivada, ou outra origem
        # chamando com key distinta), NUNCA criamos um 2º lote 'preparado' para o
        # MESMO posto+competência — reutilizamos o lote_id existente (get-or-resume).
        # preparar_lote pula quem já foi PAGO (extrato), mas NÃO enxerga um lote
        # ainda 'preparado' → sem esta trava, um re-propose com o sino desativado
        # geraria um SEGUNDO lote de PIX preparados (risco de pagamento dobrado).
        # observacoes tem o formato fixo "Folha {competencia} — {nome} ({posto})"
        # gravado por preparar_lote (INTACTO); é o único elo além do lote_id. O
        # lote_id resgatado é o MESMO que o humano retoma via gerar_otp_lote →
        # executar_lote (o loop fecha pelo humano+OTP, nunca pelo agente).
        existente = (await db.execute(text(
            "SELECT lote_id::text FROM inter_payments "
            "WHERE status = 'preparado' AND categoria = 'folha' "
            "  AND observacoes LIKE :obs LIMIT 1"),
            {"obs": f"Folha {competencia} — %({posto})"})).scalar()
        if existente:
            return existente

        # preparar_lote SÓ grava inter_payments 'preparado' (não move dinheiro,
        # não gera OTP, não chama a API). A execução fica 100% humana.
        from modules.integrations.inter.services.folha_lote_service import preparar_lote
        res = await preparar_lote(db, posto=posto, competencia=competencia,
                                  itens=itens, user_id=str(getattr(user, "id", None)))
        return res["lote_id"]

    return await propor(
        db, user=user, scope=scope, dominio="lote_pagamento", gate="🔴",
        roles_aprovador=ROLES_MONEY, idempotency_key=idem,
        titulo="[Proposta 🔴] Lote de pagamento — exige OTP",
        corpo=f"Lote de {len(itens)} pagamento(s) para {posto} ({competencia}), total R$ {total:.2f}. "
              f"NADA foi pago — exige sua aprovação + OTP no fluxo do Financeiro.",
        action_url="/financeiro/pagamentos/lote",
        tool="propor_lote_pagamento",
        args={"posto": posto, "competencia": competencia, "total": total, "n": len(itens)},
        entity_type="inter_payments_lote", inserir=_inserir,
    )


LOTE_TOOL: ToolDef = register(ToolDef(
    "propor_lote_pagamento", "financeiro",
    "Propor um lote de pagamento de folha (grava inter_payments 'preparado'; o pagamento exige aprovação humana + OTP — o agente NUNCA paga).",
    _ARGS_LOTE, _propor_lote, scope_kind="org",
))


if __name__ == "__main__":
    import asyncio

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    class _U:
        # NOTA DIVERGÊNCIA schema×brief: o esqueleto do brief usava um id fictício
        # ("...00ff") como propositor, mas inter_payments.prepared_by tem FK ENFORCED
        # p/ users(id) (inter_payments_prepared_by_fkey) — preenchido dentro de
        # preparar_lote (INTACTO, não pode ser tocado). Em produção o propositor é
        # sempre um usuário autenticado real, então a FK está sempre satisfeita; só
        # o stub de teste a violaria. Por isso o id é resolvido em runtime (usuário
        # ativo REAL, de preferência NÃO-admin, p/ manter o pool de aprovadores admin
        # intacto e ainda provar que o propositor é excluído dos aprovadores).
        def __init__(self, uid: str) -> None:
            self.id = uid
        role = "funcionario"

    class _S:
        tier = "gestor"

    async def main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            lote_ids: list[str] = []
            esoc_ids: list[str] = []

            # propositor REAL (FK prepared_by); NÃO-admin p/ não encolher o pool
            # de aprovadores (ROLES_MONEY=('admin',)) → prova propositor-excluído.
            from modules.notifications.proativo import entrega
            admins = await entrega.resolver_usuarios_por_roles(db, ROLES_MONEY)
            assert admins, "esperado >=1 admin ativo no banco (aprovador de dinheiro)"
            prop_id = (await db.execute(text(
                "SELECT id::text FROM users WHERE is_active = true AND role <> 'admin' "
                "AND id <> ALL(cast(:a as uuid[])) LIMIT 1"), {"a": admins})).scalar()
            assert prop_id, "esperado >=1 usuário ativo NÃO-admin p/ propositor de teste"
            _U_ = _U(prop_id)

            try:
                # baseline: NENHUM pagamento pode sair (executado) por causa da proposta
                exec_antes = (await db.execute(text(
                    "SELECT count(*) FROM inter_payments WHERE status = 'executado'"))).scalar()

                itens = [{"nome": "__TESTE_5.4__ Fulano", "chave": "teste@teste", "valor": 1.00}]
                r = await _propor_lote(db, _U_, _S(),
                    posto="__TESTE_5.4__POSTO", competencia="2099-01", itens=itens)
                assert r["status"] == "pendente", r
                lote_id = r["entity_id"]
                lote_ids.append(lote_id)

                # (f) propositor EXCLUÍDO dos aprovadores (3 papéis: quem propõe não aprova)
                aps = r.get("aprovadores") or []
                assert prop_id not in aps, f"propositor não pode aprovar a si mesmo: {aps}"
                assert set(aps) == set(admins), (aps, admins)

                # RBAC (e): a tool só existe no belt de quem tem o módulo financeiro
                from ..tool_registry import tools_for_modules
                assert LOTE_TOOL.module == "financeiro", LOTE_TOOL.module
                assert "propor_lote_pagamento" in {t.name for t in tools_for_modules({"financeiro"})}
                assert "propor_lote_pagamento" not in {t.name for t in tools_for_modules({"comercial"})}, \
                    "propor_lote_pagamento vazou p/ módulo não-financeiro (RBAC quebrado)"

                # os pagamentos do lote nasceram 'preparado' (nunca 'executado')
                sts = [x for x in (await db.execute(text(
                    "SELECT DISTINCT status FROM inter_payments WHERE lote_id = :l"), {"l": lote_id})).scalars().all()]
                assert sts == ["preparado"], f"status inesperado no lote: {sts}"

                # PROVA 🔴: nenhum pagamento foi executado (nada de dinheiro sem OTP)
                exec_depois = (await db.execute(text(
                    "SELECT count(*) FROM inter_payments WHERE status = 'executado'"))).scalar()
                assert exec_depois == exec_antes, "pagamento executado sem OTP (VIOLAÇÃO 🔴)"

                # teto: lote acima do teto é recusado ANTES de gravar (inserir NÃO roda)
                grande = [{"nome": "x", "chave": "k", "valor": 10_000_000.0}]
                rg = await _propor_lote(db, _U_, _S(),
                    posto="__TESTE_5.4__POSTO2", competencia="2099-01", itens=grande)
                assert "erro" in rg and "teto" in rg["erro"], rg
                # o lote acima do teto NÃO gravou nenhum inter_payments preparado
                n_grande = (await db.execute(text(
                    "SELECT count(*) FROM inter_payments WHERE observacoes LIKE '%__TESTE_5.4__POSTO2%'"))).scalar()
                assert n_grande == 0, f"lote acima do teto gravou {n_grande} pagamento(s) (VIOLAÇÃO teto)"

                # idempotência SINO (mesmo posto/competência/total → duplicado, inserir não roda)
                r2 = await _propor_lote(db, _U_, _S(),
                    posto="__TESTE_5.4__POSTO", competencia="2099-01", itens=itens)
                assert r2.get("duplicado") is True, r2

                # idempotência NATIVA (anti-lote-dobro, "não confie só no sino"):
                # desativa a notificação do sino (simula alerta arquivado) e propõe
                # de novo — o precheck do sino filtra is_active=true, então NÃO acha
                # duplicado ali; quem barra o 2º lote é o SELECT-existing no _inserir.
                idem_key = f"lote:__TESTE_5.4__POSTO:2099-01:{1.00:.2f}"
                await db.execute(text(
                    "UPDATE communication_notifications SET is_active = false "
                    "WHERE extra_data->>'idempotency_key' = :k"), {"k": idem_key})
                await db.commit()
                r3 = await _propor_lote(db, _U_, _S(),
                    posto="__TESTE_5.4__POSTO", competencia="2099-01", itens=itens)
                if r3.get("entity_id") and r3["entity_id"] not in lote_ids:
                    lote_ids.append(r3["entity_id"])  # rede de segurança p/ limpeza
                assert r3["status"] == "pendente", r3
                assert r3["entity_id"] == lote_id, \
                    f"idempotência NATIVA falhou: criou 2º lote ({r3['entity_id']} != {lote_id})"
                n_lotes = (await db.execute(text(
                    "SELECT count(DISTINCT lote_id) FROM inter_payments "
                    "WHERE observacoes LIKE 'Folha 2099-01 — %(__TESTE_5.4__POSTO)'"))).scalar()
                assert n_lotes == 1, f"idempotência NATIVA falhou: {n_lotes} lotes 'preparado' (esperado 1)"

                # PROVA 🔴 (reforço): ainda 0 executado após todas as (re)propostas
                exec_fim = (await db.execute(text(
                    "SELECT count(*) FROM inter_payments WHERE status = 'executado'"))).scalar()
                assert exec_fim == exec_antes, "pagamento executado sem OTP (VIOLAÇÃO 🔴)"
                print("SUBTESTE lote PASS (preparado criado, 0 executado, teto, "
                      "idempotência [sino+NATIVA anti-lote-dobro], RBAC financeiro, propositor excluído)")
                # (o subteste de eSocial é acrescentado na Task 8)
                print("TODOS OS SUBTESTES DE onda_c.py PASSARAM")
            finally:
                for lid in lote_ids:
                    await db.execute(text("DELETE FROM inter_payments WHERE lote_id = :l"), {"l": lid})
                # rede de segurança: apaga QUALQUER pagamento marcado de teste, mesmo
                # que o teste tenha falhado antes de capturar o lote_id em lote_ids.
                await db.execute(text(
                    "DELETE FROM inter_payments WHERE observacoes LIKE '%__TESTE_5.4__POSTO%'"))
                # audit_logs (append-only p/ uso real; aqui é resíduo de TESTE — mesmo
                # padrão de limpeza de onda_a): 1 linha por propor() bem-sucedido,
                # sempre com details->>'entity_id' ∈ lote_ids (o lote_id do 'preparado').
                if lote_ids:
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'tool' = 'propor_lote_pagamento' "
                        "AND details->>'entity_id' = ANY(:i)"), {"i": lote_ids})
                ids = [x for x in (await db.execute(text(
                    "SELECT id::text FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' LIKE 'lote:__TESTE_5.4__%' "
                    "   OR extra_data->>'idempotency_key' LIKE 'esocial:__TESTE_5.4__%'"))).scalars().all()]
                if ids:
                    await db.execute(text("DELETE FROM communication_notifications WHERE id = ANY(:i)"), {"i": ids})
                if esoc_ids:
                    await db.execute(text("DELETE FROM esocial_transmissao_propostas WHERE id = ANY(:i)"), {"i": esoc_ids})
                await db.commit()
                # 0 remanescentes: tabela de PAGAMENTO + notif + audit (confirmado 2x)
                rem = (await db.execute(text(
                    "SELECT count(*) FROM inter_payments WHERE observacoes LIKE '%__TESTE_5.4__POSTO%'"))).scalar()
                rem_n = (await db.execute(text(
                    "SELECT count(*) FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' LIKE 'lote:__TESTE_5.4__%'"))).scalar()
                rem_a = (await db.execute(text(
                    "SELECT count(*) FROM audit_logs WHERE details->>'tool' = 'propor_lote_pagamento' "
                    "AND details->>'entity_id' = ANY(:i)"), {"i": lote_ids or ['-']})).scalar()
                assert rem == 0, f"remanescentes lote (inter_payments)={rem}"
                assert rem_n == 0, f"remanescentes notif={rem_n}"
                assert rem_a == 0, f"remanescentes audit={rem_a}"
                print(f"LIMPEZA OK — 0 remanescentes (inter_payments={rem}, notif={rem_n}, audit={rem_a})")
        await eng.dispose()

    asyncio.run(main())
