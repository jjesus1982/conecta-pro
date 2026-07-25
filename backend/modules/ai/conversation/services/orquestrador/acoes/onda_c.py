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
import re
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
    # FIX anti-dup do lote: o schema da tool descreve `competencia` como "AAAA-MM",
    # mas folha_lote_service._ja_pago_competencia faz `competencia.split("/")`
    # esperando "MM/AAAA" — com "2026-07" a trava anti-duplo-pagamento cai
    # silenciosamente no `except: return None`. Convertemos AQUI (folha_lote_service
    # é INTOCADO), no formato canônico "MM/AAAA", ANTES de passar adiante. O mesmo
    # `competencia_fmt` alimenta preparar_lote (→ observacoes "Folha MM/AAAA — ...")
    # E o SELECT-existing nativo abaixo (que casa por essa mesma observacoes) — os
    # dois TÊM de usar o mesmo formato, senão a anti-dup nativa nunca casaria.
    competencia_fmt = competencia
    if re.match(r"^\d{4}-\d{2}$", competencia):
        aaaa, mm = competencia.split("-")
        competencia_fmt = f"{mm}/{aaaa}"
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
            {"obs": f"Folha {competencia_fmt} — %({posto})"})).scalar()
        if existente:
            return existente

        # preparar_lote SÓ grava inter_payments 'preparado' (não move dinheiro,
        # não gera OTP, não chama a API). A execução fica 100% humana.
        from modules.integrations.inter.services.folha_lote_service import preparar_lote
        res = await preparar_lote(db, posto=posto, competencia=competencia_fmt,
                                  itens=itens, user_id=str(getattr(user, "id", None)))
        return res["lote_id"]

    return await propor(
        db, user=user, scope=scope, dominio="lote_pagamento", gate="🔴",
        roles_aprovador=ROLES_MONEY, idempotency_key=idem,
        titulo="[Proposta 🔴] Lote de pagamento — exige OTP",
        corpo=f"Lote de {len(itens)} pagamento(s) para {posto} ({competencia}), total R$ {total:.2f}. "
              f"NADA foi pago — exige sua aprovação + OTP no fluxo do Financeiro.",
        action_url="/financeiro/inter/pagamentos",
        tool="propor_lote_pagamento",
        args={"posto": posto, "competencia": competencia, "total": total, "n": len(itens)},
        entity_type="inter_payments_lote", inserir=_inserir,
    )


LOTE_TOOL: ToolDef = register(ToolDef(
    "propor_lote_pagamento", "dp",
    "Propor um lote de pagamento de folha (grava inter_payments 'preparado'; o pagamento exige aprovação humana + OTP — o agente NUNCA paga).",
    _ARGS_LOTE, _propor_lote, scope_kind="org",
))


# ───────────────────── transmissão eSocial (🔴, ATO LEGAL ao gov) ────────────
#
# eSocial tem DUAS vias:
#   • SST/gov (S-2200 admissão, S-2210 CAT, S-2220 ASO, S-2230 afastamento,
#     S-2240 cond. ambientais, S-2299 desligamento) — transmissão REAL ao gov
#     com certificado. É ESTA que o humano aprova + transmite. Função humana:
#     modules.people_management.hr.services.esocial_service.transmitir_evento_sst
#     (disparada pelas tasks sst.transmit_*_to_esocial). O agente NUNCA a chama.
#   • payroll_integration (S-1200 folha) = via PORTTE — FORA DE ESCOPO, NÃO tocar.
#
# O agente só grava uma PROPOSTA 'proposto' em esocial_transmissao_propostas +
# base.propor (audit + sino p/ diretoria). ZERO chamada de transmissão/assinatura.
_EVENTOS_SST = ("S-2200", "S-2210", "S-2220", "S-2230", "S-2240", "S-2299")

_ARGS_ESOCIAL = {
    "type": "object",
    "properties": {
        "tipo_evento": {
            "type": "string",
            "description": "Evento SST/gov a transmitir (S-2200 admissão, S-2210 CAT, "
                           "S-2220 ASO, S-2230 afastamento, S-2240 cond. ambientais, "
                           "S-2299 desligamento). S-1200/folha é do Portte — NÃO aceito.",
            "enum": list(_EVENTOS_SST),
        },
        "referencia": {
            "type": "string",
            "description": "Identificador natural do evento (ex.: matrícula+competência ou "
                           "id da fonte). Chave de idempotência junto com tipo_evento.",
        },
        "empresa_id": {
            "type": "string",
            "description": "CNPJ (empresas.id) dono do evento — eSocial é por CNPJ.",
        },
        "employee_id": {
            "type": "string",
            "description": "Empregado do evento (opcional — nem todo evento é por empregado).",
        },
        "payload": {
            "type": "object",
            "description": "Dados do evento que o humano revisa antes de transmitir.",
        },
    },
    "required": ["tipo_evento", "referencia", "empresa_id"],
}


async def _propor_esocial(
    db, user, scope, *, tipo_evento: str, referencia: str, empresa_id: str,
    employee_id: str | None = None, payload: dict | None = None, **_
) -> dict[str, Any]:
    import json

    tipo_evento = (tipo_evento or "").strip().upper()
    referencia = (referencia or "").strip()
    empresa_id = (empresa_id or "").strip()
    if not tipo_evento or not referencia or not empresa_id:
        return {"erro": "tipo_evento, referencia e empresa_id são obrigatórios"}
    # Só a via SST/gov. S-1200 (folha) é do Portte — recusa explícita (fora de escopo).
    if tipo_evento not in _EVENTOS_SST:
        return {"erro": f"tipo_evento {tipo_evento!r} fora de escopo — o agente só propõe "
                        f"eventos SST/gov {list(_EVENTOS_SST)} (S-1200/folha é do Portte, NÃO toca)"}
    # idem sino: referencia-primeiro (marca de teste vem na referencia).
    idem = f"esocial:{referencia}:{tipo_evento}"

    async def _inserir(db) -> str:
        # Idempotência NATIVA (anti-dupla-proposta, defesa em profundidade — molde
        # onda_a/T7): mesmo que o precheck do sino em base.propor NÃO pegue
        # (notificação arquivada/desativada, ou outra origem com key distinta),
        # NUNCA criamos uma 2ª proposta 'proposto' para o MESMO (tipo_evento,
        # referencia) — reutilizamos a existente (get-or-resume). O índice único
        # parcial uq_esocial_prop_idem é a última linha de defesa sob concorrência.
        existente = (await db.execute(text(
            "SELECT id::text FROM esocial_transmissao_propostas "
            "WHERE tipo_evento = :t AND referencia = :r AND status = 'proposto' LIMIT 1"),
            {"t": tipo_evento, "r": referencia})).scalar()
        if existente:
            return existente
        # ÚNICO INSERT: proposta 'proposto'. ZERO transmissão ao gov — nenhuma
        # chamada a transmitir_evento_sst / transmit_*_to_esocial / assinatura /
        # envio. A transmissão real fica 100% humana no fluxo existente.
        novo = (await db.execute(text(
            "INSERT INTO esocial_transmissao_propostas "
            "(tipo_evento, referencia, empresa_id, employee_id, status, payload, "
            " proposto_por, correlation_id) "
            "VALUES (:t, :r, cast(:e as uuid), cast(:emp as uuid), 'proposto', "
            "        cast(:p as jsonb), cast(:pp as uuid), :cid) "
            "RETURNING id::text"),
            {"t": tipo_evento, "r": referencia, "e": empresa_id,
             "emp": employee_id or None, "p": json.dumps(payload or {}),
             "pp": str(getattr(user, "id", None)), "cid": idem})).scalar()
        return novo

    return await propor(
        db, user=user, scope=scope, dominio="esocial_transmissao", gate="🔴",
        roles_aprovador=ROLES_MONEY, idempotency_key=idem,
        titulo="[Proposta 🔴] Transmissão eSocial — ato legal",
        corpo=f"Evento {tipo_evento} (ref {referencia}) proposto para transmissão ao eSocial. "
              f"NADA foi transmitido ao governo — exige sua aprovação + transmissão humana "
              f"no fluxo do eSocial (SST).",
        action_url="/dp/esocial",
        tool="propor_esocial",
        args={"tipo_evento": tipo_evento, "referencia": referencia,
              "empresa_id": empresa_id, "employee_id": employee_id},
        entity_type="esocial_transmissao_proposta", inserir=_inserir,
    )


ESOCIAL_TOOL: ToolDef = register(ToolDef(
    "propor_esocial", "dp",
    "Propor a transmissão de um evento SST ao eSocial (grava proposta 'proposto'; a "
    "assinatura + transmissão real ao governo exige aprovação humana da diretoria — o "
    "agente NUNCA transmite ao gov).",
    _ARGS_ESOCIAL, _propor_esocial, scope_kind="org",
))


#: Export da Onda C (🔴): ambas as tools são de risco máximo (dinheiro / ato legal).
ONDA_C_TOOLS = [LOTE_TOOL, ESOCIAL_TOOL]


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

                # RBAC (e): a tool só existe no belt de quem tem o módulo 'dp' (folha é
                # DP-preparada; propor≠ler caixa, LGPD intacta). NÃO vaza p/ financeiro.
                from ..tool_registry import tools_for_modules
                assert LOTE_TOOL.module == "dp", LOTE_TOOL.module
                assert "propor_lote_pagamento" in {t.name for t in tools_for_modules({"dp"})}
                assert "propor_lote_pagamento" not in {t.name for t in tools_for_modules({"financeiro"})}, \
                    "propor_lote_pagamento vazou p/ módulo 'financeiro' (RBAC quebrado)"

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
                # observacoes agora é "Folha 01/2099 — ..." (competencia "2099-01"
                # AAAA-MM convertida p/ MM/AAAA antes de preparar_lote) — prova a conversão.
                n_lotes = (await db.execute(text(
                    "SELECT count(DISTINCT lote_id) FROM inter_payments "
                    "WHERE observacoes LIKE 'Folha 01/2099 — %(__TESTE_5.4__POSTO)'"))).scalar()
                assert n_lotes == 1, f"idempotência NATIVA falhou: {n_lotes} lotes 'preparado' (esperado 1)"

                # PROVA 🔴 (reforço): ainda 0 executado após todas as (re)propostas
                exec_fim = (await db.execute(text(
                    "SELECT count(*) FROM inter_payments WHERE status = 'executado'"))).scalar()
                assert exec_fim == exec_antes, "pagamento executado sem OTP (VIOLAÇÃO 🔴)"
                print("SUBTESTE lote PASS (preparado criado, 0 executado, teto, "
                      "idempotência [sino+NATIVA anti-lote-dobro], RBAC financeiro, propositor excluído)")

                # ───────────────── SUBTESTE eSocial (Task 8, 🔴 ato legal) ──────────
                # empresa_id REAL (eSocial é por CNPJ); sem FK na tabela nova, mas
                # usamos dado real (nunca fabricar).
                emp_id = (await db.execute(text(
                    "SELECT id::text FROM empresas LIMIT 1"))).scalar()
                assert emp_id, "esperado >=1 empresa (CNPJ) cadastrada"

                # PROVA 🔴 (baseline fonte REAL): quantos S-2230 já foram transmitidos
                # ao gov (recibo_s2230 preenchido). O agente NÃO pode transmitir 1 sequer.
                tx_antes = (await db.execute(text(
                    "SELECT count(*) FROM sst_afastamentos WHERE recibo_s2230 IS NOT NULL"))).scalar()

                ref = "__TESTE_5.4__ESOC-0001"
                re_ = await _propor_esocial(db, _U_, _S(),
                    tipo_evento="S-2230", referencia=ref, empresa_id=emp_id,
                    employee_id=None, payload={"marca": "__TESTE_5.4__"})
                assert re_["status"] == "pendente", re_
                esoc_id = re_["entity_id"]
                esoc_ids.append(esoc_id)

                # a proposta nasce 'proposto' (NUNCA transmitida)
                st = (await db.execute(text(
                    "SELECT status FROM esocial_transmissao_propostas WHERE id = cast(:i as uuid)"),
                    {"i": esoc_id})).scalar()
                assert st == "proposto", f"status inesperado: {st!r}"

                # PROVA 🔴: nenhum evento foi transmitido ao gov por causa da proposta
                tx_depois = (await db.execute(text(
                    "SELECT count(*) FROM sst_afastamentos WHERE recibo_s2230 IS NOT NULL"))).scalar()
                assert tx_depois == tx_antes, "evento transmitido ao gov sem humano (VIOLAÇÃO 🔴)"

                # gate 🔴 (diretoria só) + 3 papéis: propositor EXCLUÍDO; aprovadores == admins
                aps_e = re_.get("aprovadores") or []
                assert ESOCIAL_TOOL is not None and ROLES_MONEY == ("admin",), ROLES_MONEY
                assert prop_id not in aps_e, f"propositor não pode aprovar a si mesmo: {aps_e}"
                assert set(aps_e) == set(admins), \
                    f"eSocial deve ir só p/ diretoria (admins), veio {aps_e}"

                # RBAC de módulo: a tool só existe no belt de quem tem 'dp' (eSocial
                # SST é DP-preparado; execução segue admin+humano). NÃO vaza p/ fiscal.
                assert ESOCIAL_TOOL.module == "dp", ESOCIAL_TOOL.module
                assert "propor_esocial" in {t.name for t in tools_for_modules({"dp"})}
                assert "propor_esocial" not in {t.name for t in tools_for_modules({"fiscal"})}, \
                    "propor_esocial vazou p/ módulo 'fiscal' (RBAC quebrado)"

                # S-1200 (folha, via Portte) é RECUSADO — fora de escopo, agente não toca
                r_folha = await _propor_esocial(db, _U_, _S(),
                    tipo_evento="S-1200", referencia=ref, empresa_id=emp_id)
                assert "erro" in r_folha and "escopo" in r_folha["erro"], r_folha

                # idempotência SINO: mesma (tipo,ref) → duplicado, inserir não roda
                re2 = await _propor_esocial(db, _U_, _S(),
                    tipo_evento="S-2230", referencia=ref, empresa_id=emp_id)
                assert re2.get("duplicado") is True, re2

                # idempotência NATIVA ("não confie só no sino"): desativa a notificação
                # e propõe de novo — quem barra a 2ª proposta é o SELECT-existing.
                await db.execute(text(
                    "UPDATE communication_notifications SET is_active = false "
                    "WHERE extra_data->>'idempotency_key' = :k"),
                    {"k": f"esocial:{ref}:S-2230"})
                await db.commit()
                re3 = await _propor_esocial(db, _U_, _S(),
                    tipo_evento="S-2230", referencia=ref, empresa_id=emp_id)
                if re3.get("entity_id") and re3["entity_id"] not in esoc_ids:
                    esoc_ids.append(re3["entity_id"])
                assert re3["status"] == "pendente", re3
                assert re3["entity_id"] == esoc_id, \
                    f"idempotência NATIVA falhou: criou 2ª proposta ({re3['entity_id']} != {esoc_id})"
                n_prop = (await db.execute(text(
                    "SELECT count(*) FROM esocial_transmissao_propostas "
                    "WHERE tipo_evento = 'S-2230' AND referencia = :r AND status = 'proposto'"),
                    {"r": ref})).scalar()
                assert n_prop == 1, f"idempotência NATIVA falhou: {n_prop} propostas 'proposto' (esperado 1)"

                # PROVA 🔴 (reforço): ainda 0 transmitido após todas as (re)propostas
                tx_fim = (await db.execute(text(
                    "SELECT count(*) FROM sst_afastamentos WHERE recibo_s2230 IS NOT NULL"))).scalar()
                assert tx_fim == tx_antes, "evento transmitido ao gov sem humano (VIOLAÇÃO 🔴)"
                print("SUBTESTE eSocial PASS (proposto criado, 0 transmitido ao gov, "
                      "S-1200/Portte recusado, idempotência [sino+NATIVA], gate 🔴 diretoria, "
                      "RBAC fiscal, propositor excluído)")

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
                # rede de segurança: apaga QUALQUER proposta marcada de teste, mesmo
                # que o teste tenha falhado antes de capturar o id em esoc_ids.
                await db.execute(text(
                    "DELETE FROM esocial_transmissao_propostas WHERE referencia LIKE '__TESTE_5.4__%'"))
                # audit_logs da proposta eSocial (append-only p/ real; aqui é resíduo).
                if esoc_ids:
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'tool' = 'propor_esocial' "
                        "AND details->>'entity_id' = ANY(:i)"), {"i": esoc_ids})
                await db.commit()
                # 0 remanescentes: tabela de PAGAMENTO + eSocial + notif + audit (confirmado 2x)
                rem = (await db.execute(text(
                    "SELECT count(*) FROM inter_payments WHERE observacoes LIKE '%__TESTE_5.4__POSTO%'"))).scalar()
                rem_n = (await db.execute(text(
                    "SELECT count(*) FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' LIKE 'lote:__TESTE_5.4__%'"))).scalar()
                rem_a = (await db.execute(text(
                    "SELECT count(*) FROM audit_logs WHERE details->>'tool' = 'propor_lote_pagamento' "
                    "AND details->>'entity_id' = ANY(:i)"), {"i": lote_ids or ['-']})).scalar()
                rem_e = (await db.execute(text(
                    "SELECT count(*) FROM esocial_transmissao_propostas WHERE referencia LIKE '__TESTE_5.4__%'"))).scalar()
                rem_en = (await db.execute(text(
                    "SELECT count(*) FROM communication_notifications "
                    "WHERE extra_data->>'idempotency_key' LIKE 'esocial:__TESTE_5.4__%'"))).scalar()
                rem_ea = (await db.execute(text(
                    "SELECT count(*) FROM audit_logs WHERE details->>'tool' = 'propor_esocial' "
                    "AND details->>'entity_id' = ANY(:i)"), {"i": esoc_ids or ['-']})).scalar()
                assert rem == 0, f"remanescentes lote (inter_payments)={rem}"
                assert rem_n == 0, f"remanescentes notif={rem_n}"
                assert rem_a == 0, f"remanescentes audit={rem_a}"
                assert rem_e == 0, f"remanescentes eSocial (propostas)={rem_e}"
                assert rem_en == 0, f"remanescentes notif eSocial={rem_en}"
                assert rem_ea == 0, f"remanescentes audit eSocial={rem_ea}"
                print(f"LIMPEZA OK — 0 remanescentes (inter_payments={rem}, notif={rem_n}, audit={rem_a}, "
                      f"esocial={rem_e}, notif_esoc={rem_en}, audit_esoc={rem_ea})")
        await eng.dispose()

    asyncio.run(main())
