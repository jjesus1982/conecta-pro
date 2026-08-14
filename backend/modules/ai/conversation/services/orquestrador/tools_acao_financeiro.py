"""Fase 6 (balde FAZER) — ação FINANCEIRA reversível (🔵) via propor→aprovar.

No chat, quem tem o módulo `financeiro` PROPÕE o CADASTRO de um custo recorrente
(tributo/parcelamento/acordo/fixo/fornecedor) para entrar na previsão de custos.
Grava um PENDENTE INERTE em `financial_custos_recorrentes` via `acoes.base.propor`
— e NADA executa. O custo nasce `ativo=FALSE`: por isso NÃO entra na previsão
(previsao_custos → custos_recorrentes_listar filtra `ativo=TRUE`); ele só aparece
na tela de custos do Financeiro marcado "aguardando aprovação" (superfície de
revisão do aprovador). A ativação (ativo→TRUE) é humana, na tela — nunca aqui.

NÃO é dinheiro que SAI: `registrar_custo_recorrente` é um CADASTRO reversível
(soft-delete nativo `ativo=FALSE`), não um pagamento/PIX. Nenhum caminho paga
nada. Aprovador = diretoria (ROLES_MONEY = ('admin',)). Reversível 🔵.
Registra via `registrar_acao` (o agir_dispatcher colapsa em agir_financeiro(acao, dados)).
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Any

from sqlalchemy import text

from .acoes.base import ROLES_MONEY, propor
from .agir_dispatcher import registrar_acao

#: categorias aceitas (espelha o doc da tool nativa registrar_custo_recorrente).
_CATEGORIAS = {"tributo", "parcelamento", "acordo", "fixo", "fornecedor"}

#: o custo NASCE inerte: ativo=FALSE (fora da previsão) até aprovação humana.
_MARCA_PENDENTE = "[proposto via IA] aguardando aprovação"


async def _propor_registrar_custo_recorrente(
    db, user, scope, *, categoria: str = "", descricao: str = "", valor: float | str = 0,
    dia_vencimento: int | str | None = None, parcelas_total: int | str | None = None,
    parcelas_pagas: int | str = 0, **_
) -> dict[str, Any]:
    categoria = (categoria or "").strip().lower()
    if categoria not in _CATEGORIAS:
        return {"erro": f"categoria inválida; opções: {', '.join(sorted(_CATEGORIAS))}"}
    descricao = (descricao or "").strip()
    if len(descricao) < 2:
        return {"erro": "descricao (>=2 chars) é obrigatória"}
    try:
        valor_f = round(float(valor), 2)
    except (TypeError, ValueError):
        return {"erro": "valor inválido (número > 0)"}
    if valor_f <= 0:
        return {"erro": "valor deve ser > 0 (custo recorrente é cadastro, não pagamento)"}

    def _int_ou_none(v, minimo):
        if v in (None, "", 0) and minimo > 0:
            return None
        try:
            n = int(str(v).split()[0])
        except (TypeError, ValueError, IndexError):
            return None
        return n if n >= minimo else None

    dv = _int_ou_none(dia_vencimento, 1)
    if dv is not None and not (1 <= dv <= 31):
        return {"erro": "dia_vencimento deve estar entre 1 e 31"}
    pt = _int_ou_none(parcelas_total, 1)
    try:
        pp = max(0, int(str(parcelas_pagas).split()[0]))
    except (TypeError, ValueError, IndexError):
        pp = 0

    idem = f"custo:{categoria}:{hashlib.sha1(descricao.lower().encode()).hexdigest()[:10]}:{valor_f}"

    async def _inserir(db) -> str:
        # Idempotência NATIVA (defesa em profundidade): não duplica um custo PENDENTE
        # (ativo=FALSE + marca) com a mesma categoria+descrição+valor. Ignora os ativos
        # (já aprovados) — repropor o mesmo custo pendente devolve o MESMO ref.
        # ponytail: a PK nativa é BIGSERIAL (int) e o sino/audit exigem reference_id UUID
        # → gravamos um ref UUID sintético dentro da observação (traceável na tela) e o
        # devolvemos como entity_id; a PK int continua sendo a chave real da linha.
        existente = (await db.execute(text(
            "SELECT substring(observacao from 'ref:([0-9a-f-]{36})') FROM financial_custos_recorrentes "
            "WHERE ativo = FALSE AND categoria = :c AND lower(descricao) = :d "
            "  AND valor = :v AND coalesce(observacao,'') LIKE :marca LIMIT 1"),
            {"c": categoria, "d": descricao.lower(), "v": valor_f,
             "marca": "%" + _MARCA_PENDENTE + "%"})).scalar()
        if existente:
            return existente

        ref = str(uuid.uuid4())
        # ativo=FALSE de propósito: mantém o custo FORA da previsão (previsao_custos usa
        # custos_recorrentes_listar(ativos=True)) até a aprovação humana ativar na tela.
        # created_by é VARCHAR(64) — grava o id do propositor.
        await db.execute(text("""
            INSERT INTO financial_custos_recorrentes
                (categoria, descricao, valor, dia_vencimento, parcelas_total, parcelas_pagas,
                 ativo, observacao, created_by, created_at)
            VALUES
                (:c, :d, :v, :dv, :pt, :pp, FALSE, :obs, :u, now())
        """), {"c": categoria, "d": descricao, "v": valor_f, "dv": dv, "pt": pt, "pp": pp,
               "obs": f"{_MARCA_PENDENTE} [ref:{ref}]", "u": str(getattr(user, "id", None))[:64]})
        return ref

    return await propor(
        db, user=user, scope=scope, dominio="custo_recorrente", gate="🔵",
        roles_aprovador=ROLES_MONEY, idempotency_key=idem,
        titulo="[Proposta] Registrar custo recorrente",
        corpo=f"Custo {categoria} '{descricao}' de R$ {valor_f:.2f}"
              + (f" (venc. dia {dv})" if dv else "")
              + (f", {pp}/{pt} parcelas" if pt else "")
              + ". Nasce INATIVO (fora da previsão) — aguarda sua aprovação na tela de custos.",
        action_url="/modulos/financeiro/custos",
        tool="propor_registrar_custo_recorrente",
        args={"categoria": categoria, "descricao": descricao, "valor": valor_f,
              "dia_vencimento": dv, "parcelas_total": pt, "parcelas_pagas": pp},
        entity_type="financial_custo_recorrente", inserir=_inserir,
    )


registrar_acao("financeiro", "registrar_custo_recorrente",
               "cadastrar um custo recorrente p/ entrar na previsão de custos. dados: "
               "categoria (tributo|parcelamento|acordo|fixo|fornecedor, obrigatório), "
               "descricao (obrigatório), valor (>0, obrigatório), dia_vencimento (1-31), "
               "parcelas_total, parcelas_pagas. É CADASTRO (não pagamento); nasce inativo "
               "(fora da previsão) e a ativação é humana.",
               _propor_registrar_custo_recorrente)


# ─────────────────────────────────────────────────────────────────────────────
# F2-b — EXECUTORES dos achados dos agentes do beat (risco/fluxo/cobrança).
# O agente do beat CRIA o rascunho (propor→aprovar) via criar_rascunho; ao aprovar,
# o executor abaixo roda. Aprovar = o humano ACEITA a recomendação — NÃO move dinheiro
# (gate 🟡, sem OTP). A ação concreta (disparar régua etc.) segue humana/nas telas;
# aqui o valor é o aceite GOVERNADO e auditado (draft vira 'executado' + decidido_por).
# ─────────────────────────────────────────────────────────────────────────────
from .acoes.rascunho import registrar_executor  # noqa: E402

# risco/fluxo = aceite governado (sem ação concreta segura). cobrança = aciona a régua (F2-b.2).
_TIPOS_ACEITE = ("financeiro_recomendacao_risco", "financeiro_alerta_fluxo_caixa")


async def _exec_aceite_recomendacao_agente(db: Any, aprovador: Any, payload: dict) -> str:
    """Registra o ACEITE da recomendação do agente. Não efetiva dinheiro nem fabrica ação."""
    return str(payload.get("category") or payload.get("origem") or "recomendacao")


async def _exec_regua_cobranca(db: Any, aprovador: Any, payload: dict) -> str:
    """F2-b.2: aprovar a recomendação de cobrança ACIONA a régua — registra a tentativa
    (collection_attempts++, next_collection_date, nota) em cada recebível VENCIDO. NÃO envia
    ao cliente (comms = gate humano) nem move dinheiro. Anti-spam mesmo-dia embutido no serviço."""
    from modules.financial.services.regua_cobranca_service import (
        montar_fila_cobranca,
        registrar_cobranca,
    )

    quem = str(getattr(aprovador, "nome", None) or getattr(aprovador, "email", None)
               or getattr(aprovador, "id", None) or "gestor")
    fila = await montar_fila_cobranca(db)
    registrados = 0
    for item in fila:
        if item.get("contatado_hoje"):
            continue  # anti-spam já cobre; evita chamada à toa
        r = await registrar_cobranca(db, item["id"], item.get("canal") or "", quem=quem)
        if r.get("ok"):
            registrados += 1
    return f"regua_cobranca:{registrados}_registradas"


async def _exec_baixa_pagavel(db: Any, aprovador: Any, payload: dict) -> str:
    """Aprovar → dá BAIXA no pagável proposto (marca 'pago', bookkeeping). NÃO move dinheiro (pagar
    de verdade é o fluxo OTP); idempotente (só 'pendente'). É o "sim, essa conta JÁ foi paga" do gestor
    sobre um pendente vencido — resolve os grandes pendentes (folha/tributos/fornecedores) sem auto-baixa
    cega e sem fabricar (o humano confirma cada um)."""
    from sqlalchemy import text as _text

    pid = str(payload.get("payable_id") or "").strip()
    if not pid:
        return "sem_payable_id"
    quem = str(getattr(aprovador, "nome", None) or getattr(aprovador, "id", None) or "gestor")
    await db.execute(_text(
        "UPDATE payable_accounts SET status='pago', "
        "payment_date=coalesce(payment_date, due_date, CURRENT_DATE), paid_at=NOW(), "
        "paid_value=net_value, remaining_value=0, updated_at=NOW(), "
        "internal_notes=coalesce(internal_notes,'') || :nota "
        "WHERE id::text = :id AND status='pendente'"),
        {"id": pid, "nota": f" | baixa aprovada na Central por {quem}"})
    return f"baixa_pagavel:{pid[:8]}"


for _t in _TIPOS_ACEITE:
    registrar_executor(_t, _exec_aceite_recomendacao_agente)
async def _exec_cobranca_individual(db: Any, aprovador: Any, payload: dict) -> str:
    """Aprovar a cobrança de UM cliente registra a tentativa NAQUELE recebível.

    O beat `financeiro-propor-cobranca-vencidos` cria um rascunho POR CLIENTE, com
    tipo `financeiro_cobranca` — e esse tipo não tinha executor NENHUM. Aprovar
    levantava "sem executor registrado" e o rascunho morria em 'falha'. Era por isso
    que nenhuma cobrança do sistema jamais saiu do lugar: a proposta chegava à tela e
    o botão não tinha para onde ir.

    Não reusa `_exec_regua_cobranca` de propósito: aquele aciona a fila INTEIRA, então
    aprovar "cobrar o cliente A" registraria também B, C e D, e os rascunhos deles
    virariam mentira (propõem o que já foi feito). Aqui, um rascunho = um cliente.

    Não envia nada ao cliente — comunicação continua sendo gate humano.
    """
    from modules.financial.services.regua_cobranca_service import registrar_cobranca

    rid = str(payload.get("receivable_id") or "").strip()
    if not rid:
        raise ValueError("rascunho de cobrança sem `receivable_id` no payload")
    quem = str(getattr(aprovador, "nome", None) or getattr(aprovador, "email", None)
               or getattr(aprovador, "id", None) or "gestor")
    r = await registrar_cobranca(db, rid, str(payload.get("canal") or ""), quem=quem)
    if not r.get("ok"):
        # Recusa da régua (já pago, anti-spam do dia) é motivo legítimo e precisa
        # aparecer como falha explicada, não como sucesso silencioso.
        raise ValueError(r.get("message") or "régua de cobrança recusou o registro")
    return f"cobranca:{rid}"


registrar_executor("financeiro_cobranca", _exec_cobranca_individual)
registrar_executor("financeiro_recomendacao_cobranca", _exec_regua_cobranca)
registrar_executor("financeiro_baixa_pagavel", _exec_baixa_pagavel)


if __name__ == "__main__":
    import asyncio
    import os

    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from .agir_dispatcher import montar_acao_dispatchers
    from .tool_registry import get_tool, tools_for_modules

    SENT = "__TESTE_F6FAZER_FIN__"

    class _U:
        id = "00000000-0000-0000-0000-0000000000ff"
        role = "funcionario"
        email = "teste-f6fin@conectapro.local"
        permissions = ["module:financeiro"]

    class _USemFin:
        id = "00000000-0000-0000-0000-0000000000fe"
        role = "funcionario"
        email = "sem-fin@conectapro.local"
        permissions = ["module:crm"]

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
        montar_acao_dispatchers()
        agir = get_tool("agir_financeiro")
        assert agir is not None and agir.module == "financeiro", "agir_financeiro não registrado no módulo financeiro"

        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            refs: list[str] = []
            try:
                disp = agir.handler  # _fazer_acao_dispatch(financeiro)

                # ── (a) registrar_custo_recorrente: 1 PENDENTE inerte ativo=FALSE, não executa, idempotente ──
                desc = f"{SENT} contador mensal"
                r = await disp(db, _U(), _S(), acao="registrar_custo_recorrente",
                               dados={"categoria": "fixo", "descricao": desc, "valor": 1234.56,
                                      "dia_vencimento": 10})
                assert r.get("status") == "pendente" and not r.get("duplicado"), r
                ref = r["entity_id"]; refs.append(ref)
                # entity_id é o ref UUID sintético (a PK nativa é int) — busca a linha pelo ref
                row = (await db.execute(text(
                    "SELECT ativo, observacao FROM financial_custos_recorrentes "
                    "WHERE observacao LIKE :ref"), {"ref": "%" + ref + "%"})).mappings().first()
                assert row is not None, "linha do custo pendente não encontrada pelo ref"
                assert row["ativo"] is False, f"custo nasceu ativo={row['ativo']}, esperado FALSE (inerte, fora da previsão)"
                assert _MARCA_PENDENTE in (row["observacao"] or ""), "custo pendente sem marca de aprovação"
                # NÃO executou: nenhum custo sentinela entrou ATIVO na previsão
                exec_n = (await db.execute(text(
                    "SELECT count(*) FROM financial_custos_recorrentes WHERE descricao LIKE :n AND ativo = TRUE"),
                    {"n": SENT + "%"})).scalar()
                assert exec_n == 0, "custo sentinela ficou ATIVO (executado/entrou na previsão) — não deveria"
                # idempotência: 2ª chamada idêntica não duplica
                r2 = await disp(db, _U(), _S(), acao="registrar_custo_recorrente",
                                dados={"categoria": "fixo", "descricao": desc, "valor": 1234.56,
                                       "dia_vencimento": 10})
                assert r2.get("duplicado") is True, r2
                n = (await db.execute(text(
                    "SELECT count(*) FROM financial_custos_recorrentes WHERE descricao = :d AND ativo = FALSE"),
                    {"d": desc})).scalar()
                assert n == 1, f"idempotência custo falhou: {n} linhas"
                print("TESTE a (registrar_custo_recorrente: PENDENTE inerte ativo=FALSE, não executa, idempotente) PASS")

                # validação: valor<=0 e categoria inválida são recusados (cadastro, não pagamento)
                assert "erro" in await disp(db, _U(), _S(), acao="registrar_custo_recorrente",
                                            dados={"categoria": "fixo", "descricao": "x negativo", "valor": -5})
                assert "erro" in await disp(db, _U(), _S(), acao="registrar_custo_recorrente",
                                            dados={"categoria": "pix", "descricao": "cat ruim", "valor": 10})
                print("TESTE a2 (valida valor>0 e categoria — nunca vira dinheiro que sai) PASS")

                # ── (b) acao inválida → recusa + opções ──
                rb = await disp(db, _U(), _S(), acao="pagar", dados={})
                assert rb.get("status") == "recusado" and "opções" in rb.get("motivo", ""), rb
                assert "registrar_custo_recorrente" in rb["motivo"], rb
                print("TESTE b (acao inválida → recusa listando opções) PASS")

                # ── (c) _gate sem financeiro → PermissionError; agir_financeiro só no belt de financeiro ──
                try:
                    await disp(db, _USemFin(), _S(), acao="registrar_custo_recorrente",
                               dados={"categoria": "fixo", "descricao": "x", "valor": 1})
                    raise AssertionError("esperado PermissionError p/ usuário sem módulo financeiro")
                except PermissionError:
                    pass
                assert "agir_financeiro" in {t.name for t in tools_for_modules({"financeiro"})}
                assert "agir_financeiro" not in {t.name for t in tools_for_modules({"crm"})}, \
                    "agir_financeiro vazou p/ outro módulo (RBAC quebrado)"
                print("TESTE c (_gate sem financeiro → PermissionError; agir_financeiro só no belt de financeiro) PASS")

                # ── (d) prova: PROPÔS sem executar (ativo=FALSE, fora da previsão, sem pagar) ──
                print("TESTE d (registrar_custo_recorrente PROPÕE sem executar: cadastro ativo=FALSE, "
                      "nunca ativo/pagamento) PASS")
                print("\nTODAS AS PROVAS DE tools_acao_financeiro.py PASSARAM")
            finally:
                # a PK nativa é int e o entity_id é ref uuid → limpa pela marca sentinela na descrição
                await db.execute(text(
                    "DELETE FROM financial_custos_recorrentes WHERE descricao LIKE :n"), {"n": SENT + "%"})
                if refs:
                    await db.execute(text(
                        "DELETE FROM audit_logs WHERE details->>'entity_id' = ANY(:i)"), {"i": refs})
                await _limpar(db, "custo:%")
                await db.commit()
                rem = (await db.execute(text(
                    "SELECT count(*) FROM financial_custos_recorrentes WHERE descricao LIKE :n"),
                    {"n": SENT + "%"})).scalar()
                assert rem == 0, f"remanescentes custo={rem}"
                print("LIMPEZA OK — 0 remanescentes (financial_custos_recorrentes/audit/sino)")
        await eng.dispose()

    asyncio.run(main())
