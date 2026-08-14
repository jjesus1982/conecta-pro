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

#: Quantos dias em volta da `data_prevista` a conciliação procura a saída. Pagamento
#: de folha escorrega um ou dois dias (feriado, fila do banco, aprovação no app no dia
#: seguinte); janela apertada demais deixa item sem par, larga demais casa o pagamento
#: errado. Cinco antes e quinze depois cobriu 96 de 96 na medição de 14/08/2026.
JANELA_ANTES, JANELA_DEPOIS = 5, 15

#: Fonte autoritativa dos holerites. `hr_payslips` guarda a MESMA competência vinda da
#: Portte e do nosso motor, e os valores divergem (ADAILSON 06/2026: Portte R$643,95 ×
#: nosso R$652,35). Sem escolher, quem vence é a ordem física das linhas — dinheiro
#: saindo por sorteio. A Portte é a verdade fiscal enquanto ela transmitir ao governo.
FONTE_FOLHA = os.getenv("CONECTA_FONTE_FOLHA", "portte")
TIPOS_MENSAIS = ("mensal", "monthly")


async def gerar_parcelas(db: AsyncSession, *, competencia: str,
                         parcelas: list[tuple[int, str]],
                         dry_run: bool = True) -> dict:
    """Cria as linhas de pagamento da competência, partidas em parcelas.

    `parcelas` é [(percentual, data_prevista_iso), ...] — ex.: 40% em 20/08 e 60% em
    05/09. Somar 100 é obrigatório: um lote que soma 95% pagaria a menos e ninguém
    veria, porque cada parcela isolada parece certa.

    Lê `hr_payslips` (domínio do DP) apenas para LER, e filtra fonte e tipo. Sem esse
    filtro a mesma competência traz Portte e nosso motor somados — 112 holerites e
    R$160.811,99 em 06/2026, contra 56 pessoas reais — e em novembro traria os
    holerites de 13º como se fossem folha mensal.

    Centavos: o último a receber leva a sobra do arredondamento, então a soma das
    parcelas fecha o líquido exato. Distribuir por igual deixa resíduo de centavos que
    depois aparece como diferença na conciliação.

    `dry_run=True` por padrão: isto cria dinheiro a pagar: quem chama precisa dizer
    explicitamente que quer gravar.
    """
    soma = sum(p for p, _ in parcelas)
    if soma != 100:
        return {"ok": False, "erro": f"as parcelas somam {soma}%, precisam somar 100%"}
    mes, ano = int(competencia[5:7]), int(competencia[:4])

    holerites = (await db.execute(text("""
        SELECT h.employee_id::text AS eid, h.id::text AS payslip_id, e.nome,
               h.net_salary AS liquido, coalesce(e.pix_key,'') AS chave,
               regexp_replace(coalesce(e.cpf,''),'[^0-9]','','g') AS cpf,
               coalesce(e.posto_atual_nome,'(sem posto)') AS agrupador
        FROM hr_payslips h JOIN employees e ON e.id = h.employee_id
        WHERE h.reference_month = :m AND h.reference_year = :a
          AND h.source_system = :f AND h.payslip_type = ANY(:t)
          AND lower(coalesce(e.status,'')) = 'ativo'
          AND coalesce(h.net_salary, 0) > 0
    """), {"m": mes, "a": ano, "f": FONTE_FOLHA, "t": list(TIPOS_MENSAIS)})).mappings().all()

    if not holerites:
        return {"ok": False, "erro": (
            f"nenhum holerite {FONTE_FOLHA} mensal em {competencia} para funcionário ativo")}

    criadas, sem_chave, previsto = [], [], []
    for h in holerites:
        liquido = round(float(h["liquido"]), 2)
        if not h["chave"] and not h["cpf"]:
            sem_chave.append(h["nome"])
        acumulado, valores = 0.0, []
        for i, (pct, _dt) in enumerate(parcelas, start=1):
            v = round(liquido * pct / 100, 2) if i < len(parcelas) else round(liquido - acumulado, 2)
            acumulado = round(acumulado + v, 2)
            valores.append(v)
        assert abs(acumulado - liquido) < 0.005, f"parcelas não fecham o líquido de {h['nome']}"
        for i, ((_pct, dt), v) in enumerate(zip(parcelas, valores), start=1):
            criadas.append({"eid": h["eid"], "payslip_id": h["payslip_id"], "nome": h["nome"],
                            "parcela": i, "total": len(parcelas), "valor": v,
                            "data_prevista": dt, "chave": h["chave"],
                            "agrupador": h["agrupador"], "liquido": liquido})
        previsto.append(liquido)

    resumo = {"ok": True, "dry_run": dry_run, "competencia": competencia,
              "fonte": FONTE_FOLHA, "pessoas": len(holerites), "linhas": len(criadas),
              "liquido_total": round(sum(previsto), 2),
              "por_parcela": [{"parcela": i, "percentual": p, "data_prevista": d,
                               "total": round(sum(c["valor"] for c in criadas
                                                  if c["parcela"] == i), 2)}
                              for i, (p, d) in enumerate(parcelas, start=1)],
              "sem_chave": sem_chave,
              "agrupadores": sorted({c["agrupador"] for c in criadas})}
    if dry_run:
        resumo["mensagem"] = "SIMULAÇÃO — nada gravado. Chame com dry_run=False para valer."
        return resumo

    for c in criadas:
        await db.execute(text("""
            INSERT INTO payroll_payments
                (id, employee_id, payslip_id, mes, ano, valor_liquido, metodo, pix_key,
                 status, parcela, parcelas_total, data_prevista, created_at, updated_at)
            VALUES (gen_random_uuid(), CAST(:e AS uuid), :ps, :m, :a, :v, 'PIX', :k,
                 'pendente_pagamento', :par, :tot, CAST(:dt AS date), now(), now())
            ON CONFLICT (employee_id, mes, ano, parcela) DO NOTHING
        """), {"e": c["eid"], "ps": c["payslip_id"], "m": mes, "a": ano, "v": c["valor"],
               "k": c["chave"] or None, "par": c["parcela"], "tot": c["total"],
               "dt": c["data_prevista"]})
    await db.commit()
    resumo["mensagem"] = (f"{len(criadas)} linha(s) criada(s) para {len(holerites)} pessoa(s). "
                          f"Monte os lotes por agrupador e parcela.")
    return resumo


async def montar_lote(db: AsyncSession, *, competencia: str, banco: str,
                      criado_por: str, parcela: int = 1,
                      agrupador: str | None = None) -> dict:
    """Junta os pagamentos pendentes da competência num lote RASCUNHO.

    Não aprova nada e não muda o status dos itens — só os reserva ao lote. Um item
    já vinculado a outro lote não entra: sem isso, dois lotes abertos pagariam a
    mesma pessoa duas vezes e a descoberta viria pelo extrato, tarde.

    `agrupador` é o posto (`employees.posto_atual_nome`), que está preenchido nos 52
    ativos. NÃO é o cliente: medido em 14/08/2026, `cliente_nome` falta em 13 dos 52 e
    cruza com o posto (gente com posto PRIME e cliente MIRANTE DAS FLORES). Agrupar
    por cliente hoje montaria lote do condomínio errado — quando o cadastro do
    operacional for corrigido, é só passar o outro campo aqui.
    """
    mes, ano = int(competencia[5:7]), int(competencia[:4])
    filtro_ag = "AND coalesce(e.posto_atual_nome,'(sem posto)') = :ag" if agrupador else ""
    par = {"m": mes, "a": ano, "p": parcela}
    if agrupador:
        par["ag"] = agrupador
    itens = (await db.execute(text(f"""
        SELECT p.id::text AS id, 'clt' AS tipo, e.nome, p.valor_liquido AS valor,
               regexp_replace(coalesce(e.cpf,''),'[^0-9]','','g') AS cpf,
               coalesce(p.pix_key,'') AS chave
        FROM payroll_payments p JOIN employees e ON e.id = p.employee_id
        WHERE p.status = 'pendente_pagamento' AND p.mes = :m AND p.ano = :a
          AND p.parcela = :p AND p.lote_ordem_id IS NULL {filtro_ag}
    """), par)).mappings().all()

    if not itens:
        alvo = f"{competencia} parcela {parcela}" + (f" · {agrupador}" if agrupador else "")
        return {"ok": False, "erro": f"nenhum pagamento pendente em {alvo} sem lote"}

    total = round(sum(float(i["valor"]) for i in itens), 2)
    if total > TETO_DIARIO:
        return {"ok": False, "erro": (
            f"lote de R$ {total:,.2f} passa do teto diário de R$ {TETO_DIARIO:,.2f}. "
            f"Divida a competência em dois lotes — o teto existe para que um erro "
            f"não drene a conta de uma vez.")}

    sem_chave = [i["nome"] for i in itens if not i["chave"] and not i["cpf"]]
    lote_id = str(uuid.uuid4())
    slug = "".join(ch if ch.isalnum() else "_" for ch in (agrupador or "TODOS").upper())[:28]
    ref = f"ORDEM-{banco.upper()}-{competencia}-P{parcela}-{slug}"
    await db.execute(text("""
        INSERT INTO folha_lote_ordem
            (id, referencia, competencia, banco, total_centavos, qtd_itens, status,
             criado_por, parcela, agrupador)
        VALUES (CAST(:i AS uuid), :r, :c, :b, :t, :q, 'RASCUNHO', :u, :p, :ag)
    """), {"i": lote_id, "r": ref, "c": competencia, "b": banco,
           "t": int(round(total * 100)), "q": len(itens), "u": criado_por,
           "p": parcela, "ag": agrupador})
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
               p.data_prevista, p.parcela,
               regexp_replace(coalesce(e.cpf,''),'[^0-9]','','g') AS cpf
        FROM payroll_payments p JOIN employees e ON e.id = p.employee_id
        WHERE p.status = 'aguardando_app' {where}
    """), ({"l": lote_id} if lote_id else {}))).mappings().all()

    fechados, ambiguos, sem_par = 0, 0, 0
    for it in itens:
        # A janela sai da data PREVISTA da parcela. A regra antiga era decorada — "dia
        # 1 a 20 do mês seguinte à competência" — e um adiantamento pago no dia 20 do
        # PRÓPRIO mês cai fora dela: ficaria sem par para sempre, que é exatamente como
        # 12 pagamentos ficaram pendurados por meses. Sem data prevista (linhas
        # antigas, pagamento integral), mantém a regra antiga, que fechou 96 de 96.
        if it["data_prevista"]:
            ini = it["data_prevista"] - timedelta(days=JANELA_ANTES)
            fim = it["data_prevista"] + timedelta(days=JANELA_DEPOIS)
        else:
            pm, pa = (it["mes"] + 1, it["ano"]) if it["mes"] < 12 else (1, it["ano"] + 1)
            ini, fim = _date(pa, pm, 1), _date(pa, pm, 20)
        cand = (await db.execute(text("""
            SELECT id::text, coalesce(pix_end_to_end,'') AS e2e, transaction_date::text AS d
            FROM bank_transactions
            WHERE amount < 0 AND transaction_date BETWEEN :a AND :b
              AND regexp_replace(coalesce(counterparty_document,''),'[^0-9]','','g') = :c
              AND abs(abs(amount) - :v) <= :tol
        """), {"a": ini, "b": fim, "c": it["cpf"],
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
