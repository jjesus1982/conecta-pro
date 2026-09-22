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

import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as _date

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

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


async def gerar_parcelas(
    db: AsyncSession,
    *,
    competencia: str,
    parcelas: list[tuple[int, str]],
    dry_run: bool = True,
    etapa: str = "ambas",
) -> dict:
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

    ── ETAPAS SEPARADAS (regra do Jordan, 22/09/2026) ────────────────────────────────
    «a folha tem que rodar tanto o 40% quanto o 60% com as informações do DIA que foi
    pedido para gerar» — o adiantamento por volta do dia 20/21, o saldo no 5º dia útil
    do mês seguinte. Entre as duas datas entram contratações e saídas, e o eSocial muda.

    Gerar as duas de uma vez (o que esta função fazia) CONGELA em 22/09 uma folha que
    ainda vai mudar: quem for admitido dia 25 não teria linha de saldo, e quem sair não
    teria o valor corrigido. Por isso `etapa`:

      · "adiantamento" — cria só a parcela 1, com a folha de HOJE;
      · "saldo"        — cria só a parcela 2, com a folha do DIA em que for chamada, e
                         confere pessoa a pessoa se o que a folha abateu bate com o que
                         foi REALMENTE pago no adiantamento;
      · "ambas"        — comportamento antigo, exige somar 100%. Só para competência
                         fechada, em que nada mais vai mudar.
    """
    etapa = (etapa or "ambas").strip().lower()
    if etapa not in ("adiantamento", "saldo", "ambas"):
        return {"ok": False, "erro": "etapa deve ser 'adiantamento', 'saldo' ou 'ambas'"}
    if etapa == "ambas":
        soma = sum(p for p, _ in parcelas)
        if soma != 100:
            return {"ok": False, "erro": f"as parcelas somam {soma}%, precisam somar 100%"}
    elif len(parcelas) != 1:
        return {"ok": False, "erro": f"a etapa '{etapa}' gera UMA parcela; recebi {len(parcelas)}"}
    mes, ano = int(competencia[5:7]), int(competencia[:4])

    # ── FONTE POR COMPETÊNCIA, não global ────────────────────────────────────────────
    # 22/09/2026: o Jordan pediu os 40% de setembro «saindo do DP» e a geração recusou —
    # «nenhum holerite portte mensal em 2026-09». A constante fixava a Portte como fonte
    # única, e a Portte parou de mandar folha em julho. Resultado: o DP gerava 51
    # holerites e o Financeiro não os enxergava. A cadeia não existia para nenhum mês
    # que a Portte ainda não tivesse transmitido — ou seja, para o mês corrente, sempre.
    #
    # A regra original continua valendo e é a parte importante: a Portte é a verdade
    # fiscal ENQUANTO ela transmitir, e as duas fontes NUNCA se somam (misturar deu 112
    # holerites e R$160.811,99 numa competência de 56 pessoas). O que muda é só o
    # «enquanto»: se a Portte não mandou o mês, a folha do mês é a do nosso motor.
    fonte = FONTE_FOLHA
    _tem_portte = (
        await db.execute(
            text(
                "SELECT count(*) FROM hr_payslips WHERE reference_month = :m AND reference_year = :a "
                "AND source_system = :f AND payslip_type = ANY(:t)"
            ),
            {"m": mes, "a": ano, "f": FONTE_FOLHA, "t": list(TIPOS_MENSAIS)},
        )
    ).scalar() or 0
    if not _tem_portte:
        fonte = "conecta"

    holerites = (
        (
            await db.execute(
                text("""
        SELECT h.employee_id::text AS eid, h.id::text AS payslip_id, e.nome,
               h.net_salary AS liquido, coalesce(h.base_salary, 0) AS base,
               -- a folha do mês JÁ abate o adiantamento? Se abater, o líquido é o saldo e
               -- não se desconta de novo. Medido em 21/09/2026: nenhuma folha Portte de 2026
               -- traz rubrica de adiantamento SALARIAL (só 937, de FÉRIAS) — o vocabulário
               -- dela é VA, INSS, VT, taxa negocial, odontológico e faltas. Mas isso pode
               -- mudar no mês em que eles passarem a lançar, e aí a conta tem de mudar sozinha.
               -- ⚠️ `%ADIANT%`, não `%ADIANTAMENTO%`. Escrevi ADIANTAMENTO primeiro e o
               -- padrão NÃO pegava: na folha real da Portte a rubrica é «981
               -- DESC.ADIANT.SALARIAL», abreviada. O erro só apareceu porque o Jordan
               -- subiu a folha de agosto DELA — a de julho, a única no banco, não tinha a
               -- rubrica, então o banco não podia me desmentir. Sem esta correção o saldo
               -- sairia descontado DUAS vezes: uma pelo abatimento dela, outra pela minha.
               EXISTS (SELECT 1 FROM jsonb_array_elements(coalesce(h.deductions,'[]'::jsonb)) d
                        WHERE upper(d->>'descricao') LIKE '%ADIANT%'
                          AND upper(d->>'descricao') NOT LIKE '%FERIAS%'
                          AND upper(d->>'descricao') NOT LIKE '%FÉRIAS%') AS ja_abate,
               -- O VALOR do adiantamento que a FOLHA abateu. O Financeiro não recalcula:
               -- lê o que o DP decidiu. Enquanto os dois faziam a mesma conta em paralelo,
               -- bastava uma regra mudar de um lado (base cheia × base proporcional, 22/09)
               -- para a 1ª parcela e o abatimento do holerite discordarem — e a diferença
               -- some no saldo, sem ninguém ver.
               coalesce((SELECT (d->>'valor')::numeric
                           FROM jsonb_array_elements(coalesce(h.deductions,'[]'::jsonb)) d
                          WHERE upper(d->>'descricao') LIKE '%ADIANT%'
                            AND upper(d->>'descricao') NOT LIKE '%FERIAS%'
                            AND upper(d->>'descricao') NOT LIKE '%FÉRIAS%'
                          LIMIT 1), 0) AS adiant_folha,
               coalesce(e.pix_key,'') AS chave,
               regexp_replace(coalesce(e.cpf,''),'[^0-9]','','g') AS cpf,
               coalesce(e.posto_atual_nome,'(sem posto)') AS agrupador
        FROM hr_payslips h JOIN employees e ON e.id = h.employee_id
        WHERE h.reference_month = :m AND h.reference_year = :a
          AND h.source_system = :f AND h.payslip_type = ANY(:t)
          AND lower(coalesce(e.status,'')) = 'ativo'
          AND coalesce(h.net_salary, 0) > 0
    """),
                {"m": mes, "a": ano, "f": fonte, "t": list(TIPOS_MENSAIS)},
            )
        )
        .mappings()
        .all()
    )

    if not holerites:
        return {
            "ok": False,
            "erro": (
                f"nenhum holerite mensal em {competencia} para funcionário ativo "
                f"(procurei em '{fonte}'; a folha precisa estar gerada no DP antes de virar pagamento)"
            ),
        }

    # O QUE JÁ SAIU no adiantamento, por pessoa — a verdade do saldo não é a folha de
    # hoje, é o dinheiro que efetivamente saiu. Lido de payroll_payments (parcela 1),
    # que é onde o pagamento é registrado e conciliado.
    pago_adiant: dict[str, float] = {}
    if etapa == "saldo":
        pago_adiant = {
            str(r["eid"]): float(r["v"] or 0)
            for r in (
                await db.execute(
                    text(
                        # PAGO de verdade, não "tem linha". Medido em 22/09: o Geilson está
                        # `retido` (decisão do Jordan) e com o filtro largo o desacerto NÃO
                        # acusava — o saldo dele sairia abatido de um adiantamento que ele
                        # nunca recebeu. Vale o mesmo para quem ficar `pendente` ou
                        # `aguardando_app`: aprovado no sistema não é dinheiro na conta.
                        "SELECT employee_id::text AS eid, sum(valor_liquido) AS v "
                        "FROM payroll_payments WHERE mes = :m AND ano = :a AND parcela = 1 "
                        "  AND (data_pagamento IS NOT NULL OR lower(coalesce(status,'')) = 'pago') "
                        "GROUP BY 1"
                    ),
                    {"m": mes, "a": ano},
                )
            )
            .mappings()
            .all()
        }

    criadas, sem_chave, previsto, sem_base, estoura, desacerto = [], [], [], [], [], []
    for h in holerites:
        liquido = round(float(h["liquido"]), 2)
        base = round(float(h["base"] or 0), 2)
        if not h["chave"] and not h["cpf"]:
            sem_chave.append(h["nome"])

        # ⭐ 21/09/2026 — ADIANTAMENTO É % DO SALÁRIO BASE, não do líquido.
        # Jordan, no dia de pagar: «o nosso sistema tem que gerar idêntico ao da portte».
        # Medido nos PDFs que ele subiu (48 recibos da Portte × nossa folha de 51): a rubrica
        # 980 ADIANTAMENTO SALARIAL é exatamente 40% do salário BASE em 44 de 47 pessoas em
        # comum — e as 3 fora do padrão são base diferente da nossa, não regra diferente
        # (ele confirmou: «o salario de nailson é diferente»).
        #
        # A conta antiga dividia o LÍQUIDO, e o desvio não era de centavos: nos 47, a Portte
        # manda R$ 31.754,70 e a nossa mandaria R$ 19.069,38 — R$ 12.685,32 A MENOS, para 47
        # pessoas, cada uma com um recibo na mão dizendo outro valor.
        #
        # A ÚLTIMA parcela leva o saldo (líquido − o que já foi adiantado), e não um
        # percentual: adiantar 40% da base e depois pagar 60% do líquido não fecha com nada.
        # Se a folha já abate o adiantamento (`ja_abate`), o líquido JÁ é o saldo e não se
        # desconta duas vezes.
        if base <= 0 and len(parcelas) > 1:
            sem_base.append(h["nome"])
            continue
        acumulado, valores = 0.0, []
        adiant_folha = round(float(h["adiant_folha"] or 0), 2)
        if etapa == "adiantamento":
            # Parcela 1, sozinha. O valor é o que a FOLHA abateu (fonte única: quem decide
            # o adiantamento é o DP). Sem rubrica na folha, cai no percentual pedido.
            valores = [adiant_folha if adiant_folha > 0 else round(base * parcelas[0][0] / 100, 2)]
        elif etapa == "saldo":
            # Parcela 2, sozinha, com a folha do DIA de hoje. O líquido da folha já vem
            # abatido do adiantamento (`ja_abate`), então ELE é o saldo.
            ja_pago = round(pago_adiant.get(str(h["eid"]), 0.0), 2)
            valores = [liquido if h["ja_abate"] else round(liquido - ja_pago, 2)]
            # ⚠️ A folha abateu X e saiu Y: o saldo estaria errado nos dois sentidos, e
            # ninguém veria — a diferença some dentro de um número plausível. Casos reais
            # que isto pega: quem foi admitido DEPOIS do adiantamento (a folha desconta um
            # adiantamento que ele nunca recebeu) e quem ficou retido no lote.
            if abs(adiant_folha - ja_pago) > 0.005:
                desacerto.append(
                    {
                        "nome": h["nome"],
                        "abatido_na_folha": adiant_folha,
                        "pago_no_adiantamento": ja_pago,
                        "diferenca": round(adiant_folha - ja_pago, 2),
                    }
                )
        else:
            for i, (pct, _dt) in enumerate(parcelas, start=1):
                if i == 1 and adiant_folha > 0:
                    v = adiant_folha  # o que a folha abateu é o que se adianta — fonte única
                elif i < len(parcelas):
                    v = round(base * pct / 100, 2)
                else:
                    v = liquido if h["ja_abate"] else round(liquido - acumulado, 2)
                acumulado = round(acumulado + v, 2)
                valores.append(v)

        # 40% da base pode passar do líquido do mês inteiro (quem tem muito desconto). Um
        # saldo negativo não é pagamento: é cobrança. Fica de fora e aparece nomeado.
        if any(v < 0 for v in valores):
            estoura.append(
                {"nome": h["nome"], "base": base, "liquido": liquido, "adiantamento": valores[0], "saldo": valores[-1]}
            )
            continue
        # Numeração da parcela: na etapa avulsa o índice NÃO é a posição na lista — o
        # saldo é sempre a parcela 2 de 2, mesmo sendo a única gerada nesta chamada.
        _base_idx = {"adiantamento": 1, "saldo": 2}.get(etapa, 0)
        _tot = 2 if etapa in ("adiantamento", "saldo") else len(parcelas)
        for i, ((_pct, dt), v) in enumerate(zip(parcelas, valores, strict=True), start=1):
            criadas.append(
                {
                    "eid": h["eid"],
                    "payslip_id": h["payslip_id"],
                    "nome": h["nome"],
                    "parcela": _base_idx or i,
                    "total": _tot,
                    "valor": v,
                    "data_prevista": dt,
                    "chave": h["chave"],
                    "agrupador": h["agrupador"],
                    "liquido": liquido,
                }
            )
        previsto.append(liquido)

    resumo = {
        "ok": True,
        "dry_run": dry_run,
        "competencia": competencia,
        "fonte": fonte,
        "pessoas": len(holerites),
        "linhas": len(criadas),
        "liquido_total": round(sum(previsto), 2),
        "etapa": etapa,
        "por_parcela": [
            {
                "parcela": ({"adiantamento": 1, "saldo": 2}.get(etapa) or i),
                "percentual": p,
                "data_prevista": d,
                "total": round(
                    sum(
                        c["valor"] for c in criadas if c["parcela"] == ({"adiantamento": 1, "saldo": 2}.get(etapa) or i)
                    ),
                    2,
                ),
            }
            for i, (p, d) in enumerate(parcelas, start=1)
        ],
        # Quem a folha abateu diferente do que recebeu. Vazio é a única forma de dizer
        # "ninguém"; contar só quem entrou esconderia justamente o caso perigoso.
        "desacerto_adiantamento": desacerto,
        "sem_chave": sem_chave,
        # quem FICOU DE FORA, nomeado. Lista vazia é a única forma de dizer "ninguém
        # ficou" — contar só quem entrou esconde quem o filtro descartou calado.
        "sem_base": sem_base,
        "adiantamento_maior_que_liquido": estoura,
        "agrupadores": sorted({c["agrupador"] for c in criadas}),
    }
    if dry_run:
        resumo["mensagem"] = "SIMULAÇÃO — nada gravado. Chame com dry_run=False para valer."
        return resumo

    for c in criadas:
        await db.execute(
            text("""
            INSERT INTO payroll_payments
                (id, employee_id, payslip_id, mes, ano, valor_liquido, metodo, pix_key,
                 status, parcela, parcelas_total, data_prevista, created_at, updated_at)
            VALUES (gen_random_uuid(), CAST(:e AS uuid), :ps, :m, :a, :v, 'PIX', :k,
                 'pendente_pagamento', :par, :tot, :dt, now(), now())
            ON CONFLICT (employee_id, mes, ano, parcela) DO NOTHING
        """),
            {
                "e": c["eid"],
                "ps": c["payslip_id"],
                "m": mes,
                "a": ano,
                "v": c["valor"],
                "k": c["chave"] or None,
                "par": c["parcela"],
                "tot": c["total"],
                # `date`, não texto: com asyncpg o CAST(:dt AS date) do SQL é tarde demais —
                # o driver infere o tipo do parâmetro ANTES de mandar e estoura
                # «'str' object has no attribute 'toordinal'». O dry_run nunca tocava neste
                # INSERT, então a simulação passava e o GRAVAR nunca tinha funcionado
                # (medido em 22/09/2026, na primeira vez que se tentou gravar de verdade).
                "dt": _date.fromisoformat(str(c["data_prevista"])[:10]),
            },
        )
    await db.commit()
    resumo["mensagem"] = (
        f"{len(criadas)} linha(s) criada(s) para {len(holerites)} pessoa(s). Monte os lotes por agrupador e parcela."
    )
    return resumo


async def montar_lote(
    db: AsyncSession, *, competencia: str, banco: str, criado_por: str, parcela: int = 1, agrupador: str | None = None
) -> dict:
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
    itens = (
        (
            await db.execute(
                text(f"""
        SELECT p.id::text AS id, 'clt' AS tipo, e.nome, p.valor_liquido AS valor,
               regexp_replace(coalesce(e.cpf,''),'[^0-9]','','g') AS cpf,
               coalesce(p.pix_key,'') AS chave
        FROM payroll_payments p JOIN employees e ON e.id = p.employee_id
        WHERE p.status = 'pendente_pagamento' AND p.mes = :m AND p.ano = :a
          AND p.parcela = :p AND p.lote_ordem_id IS NULL {filtro_ag}
    """),
                par,
            )
        )
        .mappings()
        .all()
    )

    if not itens:
        alvo = f"{competencia} parcela {parcela}" + (f" · {agrupador}" if agrupador else "")
        return {"ok": False, "erro": f"nenhum pagamento pendente em {alvo} sem lote"}

    total = round(sum(float(i["valor"]) for i in itens), 2)
    if total > TETO_DIARIO:
        return {
            "ok": False,
            "erro": (
                f"lote de R$ {total:,.2f} passa do teto diário de R$ {TETO_DIARIO:,.2f}. "
                f"Divida a competência em dois lotes — o teto existe para que um erro "
                f"não drene a conta de uma vez."
            ),
        }

    sem_chave = [i["nome"] for i in itens if not i["chave"] and not i["cpf"]]
    lote_id = str(uuid.uuid4())
    slug = "".join(ch if ch.isalnum() else "_" for ch in (agrupador or "TODOS").upper())[:28]
    ref = f"ORDEM-{banco.upper()}-{competencia}-P{parcela}-{slug}"
    await db.execute(
        text("""
        INSERT INTO folha_lote_ordem
            (id, referencia, competencia, banco, total_centavos, qtd_itens, status,
             criado_por, parcela, agrupador)
        VALUES (CAST(:i AS uuid), :r, :c, :b, :t, :q, 'RASCUNHO', :u, :p, :ag)
    """),
        {
            "i": lote_id,
            "r": ref,
            "c": competencia,
            "b": banco,
            "t": int(round(total * 100)),
            "q": len(itens),
            "u": criado_por,
            "p": parcela,
            "ag": agrupador,
        },
    )
    await db.execute(
        text(
            "UPDATE payroll_payments SET lote_ordem_id = CAST(:l AS uuid), updated_at = now() "
            "WHERE id::text = ANY(CAST(:ids AS text[]))"
        ),
        {"l": lote_id, "ids": [str(i["id"]) for i in itens]},
    )
    await db.commit()
    return {
        "ok": True,
        "lote_id": lote_id,
        "referencia": ref,
        "itens": len(itens),
        "total": total,
        "sem_chave": sem_chave,
        "teto": TETO_DIARIO,
        "folga": round(TETO_DIARIO - total, 2),
    }


async def gerar_otp(db: AsyncSession, *, lote_id: str, email: str | None = None) -> dict:
    """Gera o OTP do lote e manda por e-mail. Invalida os anteriores não usados."""
    lote = (
        (
            await db.execute(
                text(
                    "SELECT referencia, total_centavos, qtd_itens, status FROM folha_lote_ordem "
                    "WHERE id = CAST(:i AS uuid)"
                ),
                {"i": lote_id},
            )
        )
        .mappings()
        .first()
    )
    if not lote:
        return {"ok": False, "erro": "lote inexistente"}
    if lote["status"] != "RASCUNHO":
        return {"ok": False, "erro": f"lote não está em RASCUNHO (está {lote['status']})"}

    await db.execute(
        text("UPDATE inter_lote_otp SET used = true WHERE lote_id = CAST(:l AS uuid) AND used = false"), {"l": lote_id}
    )
    code = f"{secrets.randbelow(900000) + 100000}"
    await db.execute(
        text("""
        INSERT INTO inter_lote_otp (id, lote_id, code, expires_at, used, created_at)
        VALUES (gen_random_uuid(), CAST(:l AS uuid), :c, :e, false, now())
    """),
        {"l": lote_id, "c": code, "e": datetime.now(UTC) + timedelta(seconds=OTP_TTL_S)},
    )
    await db.commit()

    total = lote["total_centavos"] / 100
    destino = email or os.getenv("JORDAN_EMAIL", "jjesus@conectamais.pro")
    # ⚠️ DOIS defeitos moravam aqui, e o primeiro anulava o segundo:
    # 1. `send_email` é ASSÍNCRONA e era chamada SEM await — a corrotina era criada e
    #    descartada, então o e-mail NUNCA saía. Sem exceção, sem log, e a função ainda
    #    respondia "OTP enviado para X". Mentira completa, silenciosa.
    # 2. No except, devolvia `ok: True` com um aviso. Num gate de dinheiro, "ok" com a
    #    pessoa sem o código é sucesso que engana (achado do T4, F6).
    # Agora o retorno reflete o fato: entregue = ok; não entregue = ok False com o caminho.
    saiu_daqui = False
    try:
        from core.mailer import send_email

        saiu_daqui = await send_email(
            destino,
            f"[Conecta PRO] OTP ordem de pagamento R$ {total:,.2f}",
            f"Código: {code}<br><br>Lote {lote['referencia']} — {lote['qtd_itens']} "
            f"pagamentos, R$ {total:,.2f}.<br>Válido por {OTP_TTL_S // 60} minutos.<br><br>"
            f"Aprovar NÃO paga ninguém: libera a ordem para você executar no app do banco.",
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("OTP ordem de pagamento: falha ao enviar para %s: %s", destino, exc)
    if not saiu_daqui:
        return {
            "ok": False,
            "saiu_daqui": False,
            "destino": destino,
            "expira_em_s": OTP_TTL_S,
            "erro": (
                f"O código foi gravado mas NÃO SAIU para {destino} — o servidor recusou. Você não vai "
                f"recebê-lo por e-mail. Confira o endereço configurado (JORDAN_EMAIL) "
                f"antes de tentar de novo."
            ),
        }
    return {
        "ok": True,
        "saiu_daqui": True,
        "destino": destino,
        "mensagem": f"OTP enviado para {destino}",
        "expira_em_s": OTP_TTL_S,
    }


async def aprovar_lote(db: AsyncSession, *, lote_id: str, codigo: str, aprovado_por: str) -> dict:
    """Valida o OTP AQUI DENTRO e libera a ordem. NÃO paga ninguém.

    O código é consumido (`used = true`) no MESMO commit que aprova — não existe
    janela em que um OTP aprovado siga válido para um segundo lote.
    """
    lote = (
        (
            await db.execute(
                text(
                    "SELECT referencia, total_centavos, qtd_itens, status FROM folha_lote_ordem "
                    "WHERE id = CAST(:i AS uuid) FOR UPDATE"
                ),
                {"i": lote_id},
            )
        )
        .mappings()
        .first()
    )
    if not lote:
        return {"ok": False, "erro": "lote inexistente"}
    if lote["status"] != "RASCUNHO":
        return {"ok": False, "erro": f"lote já saiu de RASCUNHO (está {lote['status']})"}

    otp = (
        await db.execute(
            text("""
        SELECT id::text FROM inter_lote_otp
        WHERE lote_id = CAST(:l AS uuid) AND code = :c AND used = false AND expires_at > now()
        ORDER BY created_at DESC LIMIT 1
    """),
            {"l": lote_id, "c": (codigo or "").strip()},
        )
    ).scalar()
    if not otp:
        return {"ok": False, "erro": "código inválido, já usado ou expirado"}

    # A soma dos itens tem que bater com o total gravado. Se alguém mexeu num valor
    # entre montar e aprovar, o lote aprovado seria outro — aborta.
    soma = float(
        (
            await db.execute(
                text(
                    "SELECT coalesce(sum(valor_liquido),0) FROM payroll_payments WHERE lote_ordem_id = CAST(:l AS uuid)"
                ),
                {"l": lote_id},
            )
        ).scalar()
        or 0
    )
    if abs(round(soma * 100) - lote["total_centavos"]) > 1:
        return {
            "ok": False,
            "erro": (
                f"soma dos itens (R$ {soma:,.2f}) não bate com o total do lote "
                f"(R$ {lote['total_centavos'] / 100:,.2f}) — algum valor mudou depois de montar"
            ),
        }

    await db.execute(text("UPDATE inter_lote_otp SET used = true WHERE id = CAST(:i AS uuid)"), {"i": otp})
    await db.execute(
        text(
            "UPDATE folha_lote_ordem SET status='APROVADO', aprovado_por=:u, aprovado_em=now(), "
            "updated_at=now() WHERE id = CAST(:i AS uuid)"
        ),
        {"u": aprovado_por, "i": lote_id},
    )
    await db.execute(
        text(
            "UPDATE payroll_payments SET status='aguardando_app', updated_at=now() "
            "WHERE lote_ordem_id = CAST(:l AS uuid) AND status='pendente_pagamento'"
        ),
        {"l": lote_id},
    )
    await db.commit()
    return {
        "ok": True,
        "referencia": lote["referencia"],
        "itens": lote["qtd_itens"],
        "total": lote["total_centavos"] / 100,
        "mensagem": "Ordem liberada. Execute os pagamentos no app do banco — "
        "o extrato de amanhã fecha cada um sozinho.",
    }


async def executar_lote_inter(db: AsyncSession, *, lote_id: str, user_id: str = "") -> dict:
    """PAGA o lote APROVADO enviando PIX pelo Inter — o mesmo motor do lote de diaristas.

    Por que isto não existia (22/09/2026): o fluxo de ordem de pagamento nasceu para a
    CORA, que não envia PIX por chave via API — então terminava em «execute no app do
    banco», e o extrato do dia seguinte reconhecia cada item. A regra da Cora acabou
    valendo para TODO lote, inclusive os do Inter, que paga por API. O Jordan aprovou um
    lote Inter de R$ 33.137,71, abriu o app e não havia nada para aprovar: o app nunca
    tinha recebido nada — ele esperava 49 PIX digitados à mão.

    Lote da CORA continua sem execução aqui, porque ali a limitação é do banco, não nossa.

    Igual ao lote de diaristas, e pelos mesmos motivos medidos:
      · commit POR ITEM — PIX que saiu fica registrado mesmo se o próximo falhar;
      · pergunta ao banco QUEM RECEBEU depois de cada um e grava o veredito na linha;
      · idempotente: só paga o que ainda está `aguardando_app`, então repetir não duplica.
    """
    import os as _os
    from decimal import Decimal

    lote = (
        (
            await db.execute(
                text(
                    "SELECT referencia, banco, status, total_centavos FROM folha_lote_ordem WHERE id = CAST(:i AS uuid)"
                ),
                {"i": lote_id},
            )
        )
        .mappings()
        .first()
    )
    if not lote:
        return {"ok": False, "erro": "lote inexistente"}
    if str(lote["banco"]).lower() != "inter":
        return {
            "ok": False,
            "erro": (
                f"lote do {lote['banco']}: este banco não envia PIX por chave via API. "
                "Pague no app e o extrato reconhece cada item pelo CPF + valor."
            ),
        }
    if str(lote["status"]).upper() != "APROVADO":
        return {"ok": False, "erro": (f"lote está {lote['status']} — só se executa o que foi APROVADO com OTP.")}

    itens = [
        dict(r)
        for r in (
            await db.execute(
                text(
                    "SELECT p.id::text AS id, e.nome, coalesce(p.pix_key, e.pix_key, '') AS chave, "
                    "       regexp_replace(coalesce(e.cpf,''),'\\D','','g') AS cpf, p.valor_liquido AS valor "
                    "  FROM payroll_payments p JOIN employees e ON e.id = p.employee_id "
                    " WHERE p.lote_ordem_id = CAST(:l AS uuid) AND p.status = 'aguardando_app' "
                    " ORDER BY e.nome"
                ),
                {"l": lote_id},
            )
        )
        .mappings()
        .all()
    ]
    if not itens:
        return {
            "ok": True,
            "pagos": 0,
            "falhas": 0,
            "mensagem": "Nada a executar: nenhum item aguardando pagamento neste lote.",
        }
    sem_chave = [i["nome"] for i in itens if not i["chave"]]
    if sem_chave:
        return {
            "ok": False,
            "erro": (
                f"{len(sem_chave)} pessoa(s) sem chave PIX no lote — o pagamento sairia pela "
                f"metade: {', '.join(sem_chave[:6])}. Cadastre a chave e monte o lote de novo."
            ),
        }

    from modules.financial.pagamentos_diaristas_service import _tipo_pix
    from modules.integrations.banking.adapters.base import BankCredentials
    from modules.integrations.banking.adapters.inter import InterAdapter

    adapter = InterAdapter(
        BankCredentials(
            client_id=_os.getenv("INTER_CLIENT_ID", ""),
            client_secret=_os.getenv("INTER_CLIENT_SECRET", ""),
            certificate_path=_os.getenv("INTER_CERT_PATH"),
            private_key_path=_os.getenv("INTER_KEY_PATH"),
            agency=_os.getenv("INTER_AGENCY"),
            account=_os.getenv("INTER_ACCOUNT"),
            environment=_os.getenv("INTER_ENVIRONMENT", "production"),
        )
    )
    pagos, falhas, diverge = [], [], []
    try:
        for i in itens:
            try:
                resp = await adapter.enviar_pix(
                    chave=i["chave"],
                    tipo_chave=_tipo_pix(i["chave"]),
                    valor=Decimal(str(i["valor"])),
                    nome_recebedor=i["nome"],
                    descricao=f"Folha {lote['referencia']} (Conecta PRO)",
                )
                if isinstance(resp, dict) and resp.get("success") is False:
                    falhas.append({"nome": i["nome"], "erro": str(resp.get("detail") or resp.get("error"))[:140]})
                    continue
                ref = (resp or {}).get("codigoSolicitacao") or (resp or {}).get("endToEndId") or "ok"
                # QUEM RECEBEU, segundo o banco — só vem depois de pago. Não impede o erro;
                # denuncia em segundos o que só apareceria pela reclamação de quem não recebeu.
                conf = {"veredito": "nao_confirmado"}
                try:
                    import asyncio as _aio  # noqa: PLC0415

                    from modules.financial.pagamentos_diaristas_service import (  # noqa: PLC0415
                        _ESPERA_CONFERENCIA_S,
                    )
                    from modules.financial.services.conferencia_pix import conferir  # noqa: PLC0415

                    await _aio.sleep(_ESPERA_CONFERENCIA_S)
                    c = await adapter.consultar_pix_pagamento(str(ref))
                    conf = conferir(
                        nome_banco=c.get("recebedor_nome", ""),
                        documento_banco=c.get("recebedor_documento", ""),
                        nome_nosso=i["nome"],
                        documento_nosso=i["cpf"],
                    )
                except Exception as ce:  # noqa: BLE001
                    conf = {"veredito": "nao_confirmado", "detalhe": f"consulta falhou: {str(ce)[:120]}"}
                if conf.get("veredito") == "DIVERGE":
                    diverge.append({"nome": i["nome"], "detalhe": str(conf.get("detalhe"))[:160]})
                    logger.error("FOLHA: PIX FOI PARA OUTRA PESSOA — %s: %s", i["nome"], conf.get("detalhe"))
                await db.execute(
                    text(
                        "UPDATE payroll_payments SET status='pago', data_pagamento=now(), "
                        "  pix_e2e_id=:ref, updated_at=now() WHERE id = CAST(:i AS uuid)"
                    ),
                    {"ref": str(ref)[:60], "i": i["id"]},
                )
                await db.commit()  # por item: PIX que saiu fica 'pago' mesmo se o próximo falhar
                pagos.append(
                    {
                        "nome": i["nome"],
                        "valor": float(i["valor"]),
                        "ref": str(ref)[:60],
                        "conferencia": conf.get("veredito"),
                    }
                )
            except Exception as e:  # noqa: BLE001
                logger.error("folha lote %s: falha ao pagar %s: %s", lote_id, i["nome"], e)
                falhas.append({"nome": i["nome"], "erro": str(e)[:140]})
    finally:
        await adapter.close()

    restam = (
        await db.execute(
            text(
                "SELECT count(*) FROM payroll_payments WHERE lote_ordem_id = CAST(:l AS uuid) "
                "  AND status = 'aguardando_app'"
            ),
            {"l": lote_id},
        )
    ).scalar() or 0
    await db.execute(
        text(
            "UPDATE folha_lote_ordem SET status = :s, concluido_em = CASE WHEN :s = 'CONCLUIDO' "
            "  THEN now() ELSE concluido_em END, updated_at = now() WHERE id = CAST(:i AS uuid)"
        ),
        {"s": "CONCLUIDO" if not restam else "CONCLUIDO_PARCIAL", "i": lote_id},
    )
    await db.commit()
    logger.warning(
        "folha lote %s executado por %s: %s pagos, %s falhas, %s divergem",
        lote_id,
        user_id,
        len(pagos),
        len(falhas),
        len(diverge),
    )
    return {
        "ok": True,
        "pagos": len(pagos),
        "falhas": falhas,
        "divergem": diverge,
        "total_pago": round(sum(p["valor"] for p in pagos), 2),
        "restam": restam,
    }


async def fechar_pelo_extrato(db: AsyncSession, *, lote_id: str | None = None) -> dict:
    """Fecha os itens que já apareceram no extrato. Roda no beat, sozinho.

    Regra provada em 14/08/2026 (84 de 96, zero ambíguo): existe UMA saída para
    aquele CPF, entre o dia 1 e o 20 do mês seguinte à competência, com valor igual
    ao líquido? Somar tudo que a pessoa recebeu erra — VT/VR e adiantamento não
    estão no líquido. Mais de uma candidata idêntica = não escolhe.
    """
    where = "AND p.lote_ordem_id = CAST(:l AS uuid)" if lote_id else ""
    itens = (
        (
            await db.execute(
                text(f"""
        SELECT p.id, p.mes, p.ano, p.valor_liquido AS valor, p.lote_ordem_id::text AS lote,
               p.data_prevista, p.parcela,
               regexp_replace(coalesce(e.cpf,''),'[^0-9]','','g') AS cpf
        FROM payroll_payments p JOIN employees e ON e.id = p.employee_id
        WHERE p.status = 'aguardando_app' {where}
    """),
                ({"l": lote_id} if lote_id else {}),
            )
        )
        .mappings()
        .all()
    )

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
        cand = (
            (
                await db.execute(
                    text("""
            SELECT id::text, coalesce(pix_end_to_end,'') AS e2e, transaction_date::text AS d
            FROM bank_transactions
            WHERE amount < 0 AND transaction_date BETWEEN :a AND :b
              AND regexp_replace(coalesce(counterparty_document,''),'[^0-9]','','g') = :c
              AND abs(abs(amount) - :v) <= :tol
        """),
                    {"a": ini, "b": fim, "c": it["cpf"], "v": float(it["valor"]), "tol": TOLERANCIA},
                )
            )
            .mappings()
            .all()
        )
        if len(cand) == 1:
            await db.execute(
                text("""
                UPDATE payroll_payments SET status='pago', data_pagamento=CAST(:d AS date),
                    pix_e2e_id=coalesce(nullif(pix_e2e_id,''), :e2e), updated_at=now()
                WHERE id::text = :i
            """),
                {"d": cand[0]["d"], "e2e": cand[0]["e2e"] or None, "i": str(it["id"])},
            )
            fechados += 1
        elif len(cand) > 1:
            ambiguos += 1
        else:
            sem_par += 1
    if fechados:
        await db.execute(
            text("""
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
        """)
        )
    await db.commit()
    return {"fechados": fechados, "ambiguos": ambiguos, "sem_par": sem_par, "avaliados": len(itens)}
