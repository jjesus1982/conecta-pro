"""Ordem de pagamento: aprovado no sistema, executado no app do banco.

O Cora não envia PIX por API — 99,8% do que sai da Patrimonial é PIX. Então o
pagamento continua no celular, mas a DECISÃO passa a ser aqui: lote com teto e OTP,
aprovado por gente, e o extrato do dia seguinte fechando cada item.

Inverte a ordem: de "executado no app, descoberto depois" para "aprovado no sistema,
executado no app".

Três travas, e nenhuma é opcional:

1. **Teto** (`CONECTA_LIMITE_DIARIO_PAGAMENTOS`, R$100.000). A folha de agosto foi
   R$94.394,91 — 94% do teto num lote só. Não é hipótese distante.
2. **OTP verificado AQUI DENTRO**, contra `inter_lote_otp`, consumido no mesmo commit
   que aprova. Nunca como parâmetro booleano: quem chama não pode decidir se o OTP
   passou — isso junta propor, aprovar e executar num ator só.
3. **Soma dos itens = total do lote**. Divergência de um centavo aborta.

O fechamento usa a regra provada em 14/08/2026: existe UMA saída para aquele CPF, na
janela do pagamento, com valor igual ao líquido? Somar tudo que a pessoa recebeu erra
— VT/VR (R$32) e adiantamentos não estão no líquido da folha.
"""
from __future__ import annotations

import os
import secrets
import uuid
from datetime import UTC, date as _date, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

TETO_DIARIO = float(os.getenv("CONECTA_LIMITE_DIARIO_PAGAMENTOS", "100000.00"))
OTP_TTL_S = 600
TOLERANCIA = 0.50


async def montar_lote(db: AsyncSession, *, competencia: str, banco: str,
                      criado_por: str) -> dict:
    """Junta os pagamentos pendentes da competência num lote RASCUNHO.

    Não aprova nada e não muda o status dos itens — só os reserva ao lote. Um item
    já vinculado a outro lote não entra: sem isso, dois lotes abertos pagariam a
    mesma pessoa duas vezes e a descoberta viria pelo extrato, tarde.
    """
    mes, ano = int(competencia[5:7]), int(competencia[:4])
    itens = (await db.execute(text("""
        SELECT p.id::text AS id, 'clt' AS tipo, e.nome, p.valor_liquido AS valor,
               regexp_replace(coalesce(e.cpf,''),'[^0-9]','','g') AS cpf,
               coalesce(p.pix_key,'') AS chave
        FROM payroll_payments p JOIN employees e ON e.id = p.employee_id
        WHERE p.status = 'pendente_pagamento' AND p.mes = :m AND p.ano = :a
          AND p.lote_ordem_id IS NULL
    """), {"m": mes, "a": ano})).mappings().all()

    if not itens:
        return {"ok": False, "erro": f"nenhum pagamento pendente em {competencia} sem lote"}

    total = round(sum(float(i["valor"]) for i in itens), 2)
    if total > TETO_DIARIO:
        return {"ok": False, "erro": (
            f"lote de R$ {total:,.2f} passa do teto diário de R$ {TETO_DIARIO:,.2f}. "
            f"Divida a competência em dois lotes — o teto existe para que um erro "
            f"não drene a conta de uma vez.")}

    sem_chave = [i["nome"] for i in itens if not i["chave"] and not i["cpf"]]
    lote_id = str(uuid.uuid4())
    ref = f"ORDEM-{banco.upper()}-{competencia}"
    await db.execute(text("""
        INSERT INTO folha_lote_ordem
            (id, referencia, competencia, banco, total_centavos, qtd_itens, status, criado_por)
        VALUES (CAST(:i AS uuid), :r, :c, :b, :t, :q, 'RASCUNHO', :u)
    """), {"i": lote_id, "r": ref, "c": competencia, "b": banco,
           "t": int(round(total * 100)), "q": len(itens), "u": criado_por})
    await db.execute(text(
        "UPDATE payroll_payments SET lote_ordem_id = CAST(:l AS uuid), updated_at = now() "
        "WHERE id::text = ANY(CAST(:ids AS text[]))"),
        {"l": lote_id, "ids": [str(i["id"]) for i in itens]})
    await db.commit()
    return {"ok": True, "lote_id": lote_id, "referencia": ref, "itens": len(itens),
            "total": total, "sem_chave": sem_chave,
            "teto": TETO_DIARIO, "folga": round(TETO_DIARIO - total, 2)}


async def gerar_otp(db: AsyncSession, *, lote_id: str, email: str | None = None) -> dict:
    """Gera o OTP do lote e manda por e-mail. Invalida os anteriores não usados."""
    lote = (await db.execute(text(
        "SELECT referencia, total_centavos, qtd_itens, status FROM folha_lote_ordem "
        "WHERE id = CAST(:i AS uuid)"), {"i": lote_id})).mappings().first()
    if not lote:
        return {"ok": False, "erro": "lote inexistente"}
    if lote["status"] != "RASCUNHO":
        return {"ok": False, "erro": f"lote não está em RASCUNHO (está {lote['status']})"}

    await db.execute(text(
        "UPDATE inter_lote_otp SET used = true WHERE lote_id = CAST(:l AS uuid) AND used = false"),
        {"l": lote_id})
    code = f"{secrets.randbelow(900000) + 100000}"
    await db.execute(text("""
        INSERT INTO inter_lote_otp (id, lote_id, code, expires_at, used, created_at)
        VALUES (gen_random_uuid(), CAST(:l AS uuid), :c, :e, false, now())
    """), {"l": lote_id, "c": code, "e": datetime.now(UTC) + timedelta(seconds=OTP_TTL_S)})
    await db.commit()

    total = lote["total_centavos"] / 100
    destino = email or os.getenv("JORDAN_EMAIL", "jjesus@conectamais.pro")
    try:
        from core.mailer import send_email
        send_email(destino, f"[Conecta PRO] OTP ordem de pagamento R$ {total:,.2f}",
                   f"Código: {code}\n\nLote {lote['referencia']} — {lote['qtd_itens']} "
                   f"pagamentos, R$ {total:,.2f}.\nVálido por {OTP_TTL_S // 60} minutos.\n\n"
                   f"Aprovar NÃO paga ninguém: libera a ordem para você executar no app do banco.")
    except Exception as exc:  # noqa: BLE001 — o OTP existe mesmo se o e-mail falhar
        return {"ok": True, "aviso": f"OTP gravado, e-mail falhou: {str(exc)[:120]}",
                "expira_em_s": OTP_TTL_S}
    return {"ok": True, "mensagem": f"OTP enviado para {destino}", "expira_em_s": OTP_TTL_S}


async def aprovar_lote(db: AsyncSession, *, lote_id: str, codigo: str,
                       aprovado_por: str) -> dict:
    """Valida o OTP AQUI DENTRO e libera a ordem. NÃO paga ninguém.

    O código é consumido (`used = true`) no MESMO commit que aprova — não existe
    janela em que um OTP aprovado siga válido para um segundo lote.
    """
    lote = (await db.execute(text(
        "SELECT referencia, total_centavos, qtd_itens, status FROM folha_lote_ordem "
        "WHERE id = CAST(:i AS uuid) FOR UPDATE"), {"i": lote_id})).mappings().first()
    if not lote:
        return {"ok": False, "erro": "lote inexistente"}
    if lote["status"] != "RASCUNHO":
        return {"ok": False, "erro": f"lote já saiu de RASCUNHO (está {lote['status']})"}

    otp = (await db.execute(text("""
        SELECT id::text FROM inter_lote_otp
        WHERE lote_id = CAST(:l AS uuid) AND code = :c AND used = false AND expires_at > now()
        ORDER BY created_at DESC LIMIT 1
    """), {"l": lote_id, "c": (codigo or "").strip()})).scalar()
    if not otp:
        return {"ok": False, "erro": "código inválido, já usado ou expirado"}

    # A soma dos itens tem que bater com o total gravado. Se alguém mexeu num valor
    # entre montar e aprovar, o lote aprovado seria outro — aborta.
    soma = float((await db.execute(text(
        "SELECT coalesce(sum(valor_liquido),0) FROM payroll_payments "
        "WHERE lote_ordem_id = CAST(:l AS uuid)"), {"l": lote_id})).scalar() or 0)
    if abs(round(soma * 100) - lote["total_centavos"]) > 1:
        return {"ok": False, "erro": (
            f"soma dos itens (R$ {soma:,.2f}) não bate com o total do lote "
            f"(R$ {lote['total_centavos'] / 100:,.2f}) — algum valor mudou depois de montar")}

    await db.execute(text("UPDATE inter_lote_otp SET used = true WHERE id = CAST(:i AS uuid)"),
                     {"i": otp})
    await db.execute(text(
        "UPDATE folha_lote_ordem SET status='APROVADO', aprovado_por=:u, aprovado_em=now(), "
        "updated_at=now() WHERE id = CAST(:i AS uuid)"), {"u": aprovado_por, "i": lote_id})
    await db.execute(text(
        "UPDATE payroll_payments SET status='aguardando_app', updated_at=now() "
        "WHERE lote_ordem_id = CAST(:l AS uuid) AND status='pendente_pagamento'"),
        {"l": lote_id})
    await db.commit()
    return {"ok": True, "referencia": lote["referencia"], "itens": lote["qtd_itens"],
            "total": lote["total_centavos"] / 100,
            "mensagem": "Ordem liberada. Execute os pagamentos no app do banco — "
                        "o extrato de amanhã fecha cada um sozinho."}


async def fechar_pelo_extrato(db: AsyncSession, *, lote_id: str | None = None) -> dict:
    """Fecha os itens que já apareceram no extrato. Roda no beat, sozinho.

    Regra provada em 14/08/2026 (84 de 96, zero ambíguo): existe UMA saída para
    aquele CPF, entre o dia 1 e o 20 do mês seguinte à competência, com valor igual
    ao líquido? Somar tudo que a pessoa recebeu erra — VT/VR e adiantamento não
    estão no líquido. Mais de uma candidata idêntica = não escolhe.
    """
    where = "AND p.lote_ordem_id = CAST(:l AS uuid)" if lote_id else ""
    itens = (await db.execute(text(f"""
        SELECT p.id, p.mes, p.ano, p.valor_liquido AS valor, p.lote_ordem_id::text AS lote,
               regexp_replace(coalesce(e.cpf,''),'[^0-9]','','g') AS cpf
        FROM payroll_payments p JOIN employees e ON e.id = p.employee_id
        WHERE p.status = 'aguardando_app' {where}
    """), ({"l": lote_id} if lote_id else {}))).mappings().all()

    fechados, ambiguos, sem_par = 0, 0, 0
    for it in itens:
        pm, pa = (it["mes"] + 1, it["ano"]) if it["mes"] < 12 else (1, it["ano"] + 1)
        cand = (await db.execute(text("""
            SELECT id::text, coalesce(pix_end_to_end,'') AS e2e, transaction_date::text AS d
            FROM bank_transactions
            WHERE amount < 0 AND transaction_date BETWEEN :a AND :b
              AND regexp_replace(coalesce(counterparty_document,''),'[^0-9]','','g') = :c
              AND abs(abs(amount) - :v) <= :tol
        """), {"a": _date(pa, pm, 1), "b": _date(pa, pm, 20), "c": it["cpf"],
               "v": float(it["valor"]), "tol": TOLERANCIA})).mappings().all()
        if len(cand) == 1:
            await db.execute(text("""
                UPDATE payroll_payments SET status='pago', data_pagamento=CAST(:d AS date),
                    pix_e2e_id=coalesce(nullif(pix_e2e_id,''), :e2e), updated_at=now()
                WHERE id::text = :i
            """), {"d": cand[0]["d"], "e2e": cand[0]["e2e"] or None, "i": str(it["id"])})
            fechados += 1
        elif len(cand) > 1:
            ambiguos += 1
        else:
            sem_par += 1
    if fechados:
        await db.execute(text("""
            UPDATE folha_lote_ordem l SET
                status = CASE WHEN NOT EXISTS (
                    SELECT 1 FROM payroll_payments p WHERE p.lote_ordem_id = l.id
                      AND p.status = 'aguardando_app')
                    THEN 'CONCLUIDO' ELSE 'EXECUTANDO' END,
                concluido_em = CASE WHEN NOT EXISTS (
                    SELECT 1 FROM payroll_payments p WHERE p.lote_ordem_id = l.id
                      AND p.status = 'aguardando_app')
                    THEN now() ELSE concluido_em END,
                updated_at = now()
            WHERE l.status IN ('APROVADO','EXECUTANDO')
        """))
    await db.commit()
    return {"fechados": fechados, "ambiguos": ambiguos, "sem_par": sem_par,
            "avaliados": len(itens)}
