"""Fatura como DOCUMENTO — o que o DGX chama de `/Faturas` e aqui não existia (W2, 24/09/2026).

A diferença que esta frente fecha, medida no sandbox (cópia de produção de 23/09):

    RECEBÍVEL (o que já tínhamos)          FATURA (o que faltava)
    `receivable_accounts`, 52 linhas       documento comercial que ANTECEDE a NFS-e
    nasce de `gerar_recebiveis`            nasce a mão OU do contrato, e pode nascer rascunho
    (contrato × competência, valor cheio)  com PERÍODO de prestação e ITENS discriminados
    um valor só, sem itens                 Σ de itens (posto, adicional, avulso)
    sem número próprio (`code` interno)    NÚMERO sequencial sem buraco, como o recibo (F11)
    sem papel: não imprime                 PDF timbrado, um por página, imprimível em LOTE
    quem paga = quem contrata              sai no nome da FONTE PAGADORA quando há (F12)

O recebível continua sendo o registro contábil do que é devido — nada nele muda. A fatura é o
papel que o cliente confere item a item, e de onde o recebível PASSA A NASCER quando se clica
«Gerar conta» (`gerar_conta`, idempotente por `receivable_id` — nunca cobra duas vezes).

Paredes desta camada:
  · número só existe depois de `emitir`; rascunho não consome número (e não deixa buraco);
  · `pg_advisory_xact_lock` na emissão: dois cliques simultâneos não pegam o mesmo número;
  · itens travam na emissão — fatura emitida é documento, não rascunho;
  · `valor_total` é sempre recontado de `Σ quantidade × valor_unitario` (nunca digitado);
  · `gerar_conta` REGISTRA o devido e não recebe (status `pendente`), igual a `gerar_recebiveis`;
  · uma fatura por (contrato, competência) enquanto não cancelada — índice único parcial, que é
    o que faz «copiar em lote» rodado duas vezes não duplicar o mês;
  · `cancelar` recusa (409) fatura cujo recebível já foi pago.

Quem chama: `redesign_builders/_dgx_w2_fatura.py` (telas e rotas). O oráculo
`scripts/orq/test_oraculo_w2_fatura.py` chama ESTE módulo direto e reconta por SQL próprio.
"""

from __future__ import annotations

import logging
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

#: mesma empresa-guarda-chuva que os demais títulos do redesign usam (F11 `_conta_com_condicao`).
_CONDOMINIO = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

STATUS = ("rascunho", "emitida", "enviada", "paga", "cancelada")

#: status do recebível que impedem cancelar a fatura — o dinheiro já entrou (ou parte dele).
_RECEBIDO = ("paga", "parcial")

#: `enviada` e `paga` estão no CHECK porque são o ciclo do DGX, mas hoje NINGUÉM as escreve:
#: não há envio ao cliente nem baixa que reflita na fatura. Declarado aqui para não virar
#: promessa de tela — o que a fatura mostra de dinheiro recebido é o status do RECEBÍVEL.

DDL = (
    """CREATE TABLE IF NOT EXISTS fin_faturas (
        id serial PRIMARY KEY,
        numero int,
        cliente_id uuid,
        fonte_pagadora_id int,
        contrato_id uuid,
        competencia char(7) NOT NULL,
        periodo_inicio date,
        periodo_fim date,
        vencimento date NOT NULL,
        condicao_pagamento_id int,
        descricao_padrao text,
        valor_total numeric(14,2) NOT NULL DEFAULT 0,
        status text NOT NULL DEFAULT 'rascunho',
        receivable_id uuid,
        nfse_id uuid,
        observacao text,
        criado_por text,
        emitida_em timestamptz,
        created_at timestamptz DEFAULT now(),
        CONSTRAINT fin_fatura_status CHECK (status IN ('rascunho','emitida','enviada','paga','cancelada')),
        CONSTRAINT fin_fatura_periodo CHECK (periodo_fim IS NULL OR periodo_inicio IS NULL OR periodo_fim >= periodo_inicio),
        CONSTRAINT fin_fatura_emitida_tem_numero CHECK (status = 'rascunho' OR status = 'cancelada' OR numero IS NOT NULL))""",
    # número só é único entre os que EXISTEM: rascunho não consome série.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_fin_faturas_numero ON fin_faturas (numero) WHERE numero IS NOT NULL",
    # a parede do «copiar em lote»: uma fatura viva por contrato/competência.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_fin_faturas_contrato_comp ON fin_faturas (contrato_id, competencia) "
    "  WHERE contrato_id IS NOT NULL AND status <> 'cancelada'",
    "ALTER TABLE fin_faturas ADD COLUMN IF NOT EXISTS origem_fatura_id int",
    # a outra metade da parede do «copiar em lote»: a MESMA fatura não vira duas cópias no MESMO
    # mês. O índice de contrato acima não cobre a fatura avulsa (sem contrato) — esta cobre.
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_fin_faturas_origem_comp ON fin_faturas (origem_fatura_id, competencia) "
    "  WHERE origem_fatura_id IS NOT NULL AND status <> 'cancelada'",
    "CREATE INDEX IF NOT EXISTS ix_fin_faturas_comp ON fin_faturas (competencia, status)",
    """CREATE TABLE IF NOT EXISTS fin_fatura_itens (
        id serial PRIMARY KEY,
        fatura_id int NOT NULL REFERENCES fin_faturas(id) ON DELETE CASCADE,
        descricao text NOT NULL,
        quantidade numeric(12,3) NOT NULL DEFAULT 1,
        valor_unitario numeric(14,2) NOT NULL,
        valor_total numeric(14,2) NOT NULL DEFAULT 0,
        codigo_servico_id int,
        posto_id uuid,
        created_at timestamptz DEFAULT now(),
        CONSTRAINT fin_fatura_item_qtd CHECK (quantidade > 0))""",
    "CREATE INDEX IF NOT EXISTS ix_fin_fatura_itens_fat ON fin_fatura_itens (fatura_id)",
)


#: o que prova que o DDL já rodou — barato e por SQL, não por variável de processo.
_SQL_PRONTO = (
    "SELECT to_regclass('fin_faturas') IS NOT NULL AND to_regclass('fin_fatura_itens') IS NOT NULL "
    "   AND EXISTS (SELECT 1 FROM information_schema.columns "
    "               WHERE table_name = 'fin_faturas' AND column_name = 'origem_fatura_id')"
)


async def ensure(db: AsyncSession) -> None:
    """DDL idempotente. Chamada por `telas()` e por cada ação — nunca por alembic.

    O guard não é elegância: `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` pega ACCESS EXCLUSIVE
    na tabela MESMO quando a coluna já existe. Sem ele, duas ações simultâneas sobre a mesma
    fatura dão **deadlock** (medido no oráculo em 24/09: duas emissões concorrentes, uma
    esperando RowExclusive e a outra AccessExclusive na mesma relação).
    """
    if (await db.execute(text(_SQL_PRONTO))).scalar():
        return
    for sql in DDL:
        await db.execute(text(sql))
    await db.commit()


# ── helpers de valor/data ───────────────────────────────────────────────────────────────────
def _q(v) -> Decimal:
    return Decimal(str(v or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _mes_mais(d: date | None, n: int) -> date | None:
    """Mesma data N meses adiante, encurtando o dia quando o mês é curto (31/01 +1 → 28/02)."""
    if d is None:
        return None
    import calendar

    m = d.month - 1 + n
    ano, mes = d.year + m // 12, m % 12 + 1
    return date(ano, mes, min(d.day, calendar.monthrange(ano, mes)[1]))


def _delta_meses(a: str, b: str) -> int:
    """Quantos meses de 'AAAA-MM' a até 'AAAA-MM' b."""
    return (int(b[:4]) - int(a[:4])) * 12 + (int(b[5:7]) - int(a[5:7]))


def _fim_do_mes(comp: str) -> date:
    import calendar

    ano, mes = int(comp[:4]), int(comp[5:7])
    return date(ano, mes, calendar.monthrange(ano, mes)[1])


async def _recalc(db: AsyncSession, fid: int) -> Decimal:
    """`valor_total` NUNCA é digitado: é sempre Σ (quantidade × valor_unitario) dos itens."""
    await db.execute(
        text("UPDATE fin_fatura_itens SET valor_total = round(quantidade * valor_unitario, 2) WHERE fatura_id = :i"),
        {"i": fid},
    )
    v = (
        await db.execute(
            text(
                "UPDATE fin_faturas SET valor_total = coalesce("
                "  (SELECT round(sum(quantidade * valor_unitario), 2) FROM fin_fatura_itens WHERE fatura_id = :i), 0) "
                "WHERE id = :i RETURNING valor_total"
            ),
            {"i": fid},
        )
    ).scalar()
    return _q(v)


async def _fatura(db: AsyncSession, fid: int):
    r = (
        await db.execute(
            text(
                "SELECT id, numero, status, receivable_id::text, valor_total, competencia, cliente_id::text, "
                "       contrato_id::text, fonte_pagadora_id, descricao_padrao, vencimento "
                "  FROM fin_faturas WHERE id = :i"
            ),
            {"i": fid},
        )
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Fatura não encontrada.")
    return r


# ── criar ───────────────────────────────────────────────────────────────────────────────────
async def itens_do_contrato(db: AsyncSession, contrato_id: str, competencia: str) -> list[dict]:
    """Itens da fatura a partir do CONTRATO.

    Medido no sandbox 24/09: `contract_items` tem 16 linhas, mas só 2 contratos ativos as têm — e
    `posts.salario_base` (a vaga da T3) está NULL em 17/17, então o caminho «Σ vagas × salário»
    não produziria número nenhum hoje. Então: itens do contrato quando existirem com valor; senão
    UMA linha com o `monthly_value`, que é o que o contrato de fato cobra no mês. Nunca inventado.
    """
    itens = (
        await db.execute(
            text(
                "SELECT service_name, coalesce(quantity,1), unit_price "
                "  FROM contract_items WHERE contract_id = CAST(:c AS uuid) AND coalesce(is_active,true) "
                "   AND coalesce(unit_price,0) > 0 ORDER BY service_name"
            ),
            {"c": contrato_id},
        )
    ).fetchall()
    if itens:
        return [
            {"descricao": r[0] or "Serviço", "quantidade": Decimal(str(r[1] or 1)), "valor_unitario": _q(r[2])}
            for r in itens
        ]
    r = (
        await db.execute(
            text("SELECT monthly_value, contract_number FROM contracts WHERE id = CAST(:c AS uuid)"),
            {"c": contrato_id},
        )
    ).first()
    if not r or not r[0] or Decimal(str(r[0])) <= 0:
        raise HTTPException(
            status_code=400,
            detail="Contrato sem itens e sem valor mensal — informe os itens a mão.",
        )
    ref = f"{competencia[5:7]}/{competencia[:4]}"
    return [
        {
            "descricao": f"Prestação de serviços {ref}" + (f" — contrato {r[1]}" if r[1] else ""),
            "quantidade": Decimal("1"),
            "valor_unitario": _q(r[0]),
        }
    ]


async def criar(db: AsyncSession, p: dict, criado_por: str) -> int:
    """Cria a fatura em RASCUNHO (sem número). Itens vêm em `p['itens']` ou do contrato.

    `p`: cliente_id, contrato_id, fonte_pagadora_id, competencia ('AAAA-MM'), periodo_inicio/fim,
    vencimento (date), condicao_pagamento_id, descricao_padrao, observacao, itens (list de dicts
    com descricao/quantidade/valor_unitario/codigo_servico_id/posto_id).
    """
    await ensure(db)
    comp = str(p.get("competencia") or "").strip()
    if len(comp) != 7 or comp[4] != "-":
        raise HTTPException(status_code=400, detail="Competência no formato MM/AAAA.")
    contrato = str(p.get("contrato_id") or "").strip() or None
    cliente = str(p.get("cliente_id") or "").strip() or None
    if not (cliente or contrato):
        raise HTTPException(status_code=400, detail="Escolha o cliente ou o contrato.")
    if contrato and not cliente:
        cliente = (
            await db.execute(text("SELECT client_id::text FROM contracts WHERE id = CAST(:c AS uuid)"), {"c": contrato})
        ).scalar()
    itens = list(p.get("itens") or [])
    if not itens:
        if not contrato:
            raise HTTPException(status_code=400, detail="Informe ao menos um item (ou escolha um contrato).")
        itens = await itens_do_contrato(db, contrato, comp)
    venc = p.get("vencimento")
    if not isinstance(venc, date):
        raise HTTPException(status_code=400, detail="Vencimento obrigatório.")

    if contrato:
        ja = (
            await db.execute(
                text(
                    "SELECT id, numero FROM fin_faturas WHERE contrato_id = CAST(:c AS uuid) "
                    "   AND competencia = :m AND status <> 'cancelada'"
                ),
                {"c": contrato, "m": comp},
            )
        ).first()
        if ja:
            raise HTTPException(
                status_code=409,
                detail=f"Este contrato já tem fatura em {comp[5:7]}/{comp[:4]} (#{ja[1] or 'rascunho ' + str(ja[0])}).",
            )
    fid = (
        await db.execute(
            text(
                "INSERT INTO fin_faturas (cliente_id, fonte_pagadora_id, contrato_id, competencia, periodo_inicio, "
                "  periodo_fim, vencimento, condicao_pagamento_id, descricao_padrao, observacao, criado_por) "
                "VALUES (CAST(:cli AS uuid), :fp, CAST(:ctr AS uuid), :m, :pi, :pf, :v, :cond, :desc, :obs, :por) "
                "RETURNING id"
            ),
            {
                "cli": cliente,
                "fp": int(p["fonte_pagadora_id"]) if str(p.get("fonte_pagadora_id") or "").strip() else None,
                "ctr": contrato,
                "m": comp,
                "pi": p.get("periodo_inicio") or date(int(comp[:4]), int(comp[5:7]), 1),
                "pf": p.get("periodo_fim") or _fim_do_mes(comp),
                "v": venc,
                "cond": int(p["condicao_pagamento_id"]) if str(p.get("condicao_pagamento_id") or "").strip() else None,
                "desc": str(p.get("descricao_padrao") or "").strip() or None,
                "obs": str(p.get("observacao") or "").strip() or None,
                "por": criado_por,
            },
        )
    ).scalar()
    for it in itens:
        await _inserir_item(db, int(fid), it)
    await _recalc(db, int(fid))
    await db.commit()
    return int(fid)


async def _inserir_item(db: AsyncSession, fid: int, it: dict) -> None:
    desc = str(it.get("descricao") or "").strip()
    if len(desc) < 2:
        raise HTTPException(status_code=400, detail="Item sem descrição.")
    qtd = Decimal(str(it.get("quantidade") or 1))
    if qtd <= 0:
        raise HTTPException(status_code=400, detail=f"Item «{desc[:40]}»: quantidade deve ser maior que zero.")
    unit = _q(it.get("valor_unitario"))
    if unit <= 0:
        raise HTTPException(status_code=400, detail=f"Item «{desc[:40]}»: valor unitário deve ser maior que zero.")
    await db.execute(
        text(
            "INSERT INTO fin_fatura_itens (fatura_id, descricao, quantidade, valor_unitario, valor_total, "
            "  codigo_servico_id, posto_id) VALUES (:f, :d, CAST(:q AS numeric), CAST(:u AS numeric), "
            "  round(CAST(:q AS numeric) * CAST(:u AS numeric), 2), :cs, CAST(:p AS uuid))"
        ),
        {
            "f": fid,
            "d": desc[:500],
            "q": qtd,
            "u": unit,
            "cs": int(it["codigo_servico_id"]) if str(it.get("codigo_servico_id") or "").strip() else None,
            "p": str(it.get("posto_id") or "").strip() or None,
        },
    )


async def item_incluir(db: AsyncSession, fid: int, it: dict) -> Decimal:
    """Inclui item — só em RASCUNHO: fatura emitida é documento, não rascunho."""
    f = await _fatura(db, fid)
    if f[2] != "rascunho":
        raise HTTPException(status_code=409, detail=f"Fatura {f[2]} — itens travados na emissão.")
    await _inserir_item(db, fid, it)
    v = await _recalc(db, fid)
    await db.commit()
    return v


async def item_excluir(db: AsyncSession, fid: int, item_id: int) -> Decimal:
    f = await _fatura(db, fid)
    if f[2] != "rascunho":
        raise HTTPException(status_code=409, detail=f"Fatura {f[2]} — itens travados na emissão.")
    await db.execute(text("DELETE FROM fin_fatura_itens WHERE id = :i AND fatura_id = :f"), {"i": item_id, "f": fid})
    v = await _recalc(db, fid)
    await db.commit()
    return v


# ── emitir ──────────────────────────────────────────────────────────────────────────────────
async def emitir(db: AsyncSession, fid: int, por: str) -> int:
    """Dá o PRÓXIMO número à fatura e trava os itens.

    O lock de aplicação é o que faz dois cliques simultâneos não pegarem o mesmo número — mesma
    receita do recibo (F11). Rascunho não consome número, então a série não tem buraco.
    """
    await ensure(db)
    f = await _fatura(db, fid)
    if f[2] != "rascunho":
        raise HTTPException(status_code=409, detail=f"Fatura já {f[2]} (nº {f[1] or '—'}).")
    if _q(f[4]) <= 0:
        raise HTTPException(status_code=400, detail="Fatura sem valor — inclua ao menos um item.")
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('fin_faturas'))"))
    numero = (
        await db.execute(
            text(
                "UPDATE fin_faturas SET numero = (SELECT coalesce(max(numero),0)+1 FROM fin_faturas), "
                "  status = 'emitida', emitida_em = now(), criado_por = coalesce(criado_por, :por) "
                "WHERE id = :i AND status = 'rascunho' RETURNING numero"
            ),
            {"i": fid, "por": por},
        )
    ).scalar()
    if numero is None:  # outra sessão emitiu no meio — não há número a devolver
        await db.rollback()
        raise HTTPException(status_code=409, detail="Fatura emitida por outra sessão.")
    await db.commit()
    return int(numero)


# ── gerar conta (o «GerarConta» do DGX) ─────────────────────────────────────────────────────
async def gerar_conta(db: AsyncSession, fid: int, user_id) -> dict:
    """Cria o RECEBÍVEL da fatura pelo caminho existente (`ReceivableService`). NÃO recebe.

    Idempotente por `fin_faturas.receivable_id`: segunda chamada devolve o mesmo id e `criado=False`.
    """
    await ensure(db)
    f = await _fatura(db, fid)
    if f[2] == "cancelada":
        raise HTTPException(status_code=409, detail="Fatura cancelada.")
    if f[2] == "rascunho":
        raise HTTPException(status_code=409, detail="Emita a fatura antes de gerar a conta a receber.")
    if f[3]:
        existe = (
            await db.execute(text("SELECT 1 FROM receivable_accounts WHERE id = CAST(:r AS uuid)"), {"r": f[3]})
        ).scalar()
        if existe:
            return {"ok": True, "criado": False, "receivable_id": f[3], "message": "Conta a receber já existe."}

    d = await dados_documento(db, fid)
    from modules.financial.schemas.receivable import ReceivableAccountCreate
    from modules.financial.services.receivable_service import ReceivableService

    numero, comp = f[1], f[5]
    desc = (f[9] or f"Fatura {numero:05d} — serviços {comp[5:7]}/{comp[:4]}")[:500]
    conta = await ReceivableService(db).create_account(
        ReceivableAccountCreate(
            condominio_id=_CONDOMINIO,
            description=desc,
            document_number=f"FAT-{numero:05d}",
            gross_value=_q(f[4]),
            due_date=f[10],
            competence_date=date(int(comp[:4]), int(comp[5:7]), 1),
            customer_name=(d["sacado"] or None),
            notes=f"Gerada da fatura nº {numero:05d}.",
        ),
        user_id,
    )
    # colunas que o schema não carrega — a identidade do título (mesmo padrão do F11 com a forma
    # de pagamento). `customer_id` fica NULO de propósito: a FK aponta para `customers`, e a
    # fatura referencia `clients` (ver receivable_contract_service.py).
    await db.execute(
        text(
            "UPDATE receivable_accounts SET code = :code, reference_month = :ref, competencia_mes = :m, "
            "  competencia_ano = :a, origem = 'fatura', customer_document = :docn, fonte_pagadora_id = :fp "
            "WHERE id = :i"
        ),
        {
            "code": f"FAT-{numero:05d}",
            "ref": f"{comp[5:7]}/{comp[:4]}",
            "m": int(comp[5:7]),
            "a": int(comp[:4]),
            "docn": (d["sacado_documento"] or "")[:20] or None,
            "fp": f[8],
            "i": conta.id,
        },
    )
    # o status NÃO anda aqui. «Gerar conta» cria o título; não envia nada a ninguém — e marcar
    # «enviada» sem ninguém ter enviado travava o cancelamento de uma fatura ainda NÃO PAGA
    # (visto na prova HTTP de 24/09). Quem barra o cancelamento é o recebível pago, não o status.
    await db.execute(
        text("UPDATE fin_faturas SET receivable_id = :r WHERE id = :i"),
        {"r": str(conta.id), "i": fid},
    )
    await db.commit()
    # AVISO, não trava: `gerar_recebiveis` (Receber › Gerar do mês) cria um título do MESMO
    # contrato/competência com outro `code` (REC-… × FAT-…) — daria para cobrar duas vezes. Qual
    # dos dois caminhos é o oficial é decisão do dono (§7.2 do relatório), então aqui só se diz.
    aviso = ""
    if f[7]:
        outro = (
            await db.execute(
                text(
                    "SELECT code, net_value FROM receivable_accounts "
                    " WHERE origem = 'contrato' AND competencia_mes = :m AND competencia_ano = :a "
                    "   AND metadata->>'contract_id' = :c AND status NOT IN ('cancelada','baixada') LIMIT 1"
                ),
                {"m": int(comp[5:7]), "a": int(comp[:4]), "c": f[7]},
            )
        ).first()
        if outro:
            aviso = (
                f" ATENÇÃO: este contrato já tem o título {outro[0]} de {_brl(outro[1])} na mesma "
                "competência, criado por «Gerar do mês». Confira se não está cobrando duas vezes."
            )
    return {
        "ok": True,
        "criado": True,
        "receivable_id": str(conta.id),
        "message": f"Conta a receber criada de {_brl(f[4])} para {f[10].strftime('%d/%m/%Y')}. "
        f"Não recebeu — a baixa é outro ato.{aviso}",
    }


def _brl(v) -> str:
    s = f"{float(v or 0):,.2f}"
    return "R$ " + s.replace(",", "§").replace(".", ",").replace("§", ".")


# ── copiar (o «copiar em lote» do DGX) ──────────────────────────────────────────────────────
async def copiar(db: AsyncSession, fid: int, comp_destino: str, por: str) -> int | None:
    """Duplica a fatura (com itens) para outra competência, em RASCUNHO. Datas andam N meses.

    Devolve o id novo, ou None se o contrato já tem fatura viva no destino.
    """
    r = (
        await db.execute(
            text(
                "SELECT competencia, cliente_id::text, fonte_pagadora_id, contrato_id::text, periodo_inicio, "
                "       periodo_fim, vencimento, condicao_pagamento_id, descricao_padrao, observacao "
                "  FROM fin_faturas WHERE id = :i"
            ),
            {"i": fid},
        )
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Fatura não encontrada.")
    n = _delta_meses(r[0], comp_destino)
    if n == 0:
        raise HTTPException(status_code=400, detail="Competência de destino igual à de origem.")
    # já copiada para lá? (a fatura avulsa não tem contrato: a guarda é pela ORIGEM)
    ja = (
        await db.execute(
            text(
                "SELECT 1 FROM fin_faturas WHERE competencia = :m AND status <> 'cancelada' "
                "   AND (origem_fatura_id = :i OR contrato_id = CAST(:ctr AS uuid))"
            ),
            {"m": comp_destino, "i": fid, "ctr": r[3]},
        )
    ).scalar()
    if ja:
        return None
    novo = (
        await db.execute(
            text(
                "INSERT INTO fin_faturas (cliente_id, fonte_pagadora_id, contrato_id, competencia, periodo_inicio, "
                "  periodo_fim, vencimento, condicao_pagamento_id, descricao_padrao, observacao, criado_por, "
                "  origem_fatura_id) "
                "VALUES (CAST(:cli AS uuid), :fp, CAST(:ctr AS uuid), :m, :pi, :pf, :v, :cond, :desc, :obs, :por, :orig) "
                "RETURNING id"
            ),
            {
                "cli": r[1],
                "fp": r[2],
                "ctr": r[3],
                "m": comp_destino,
                "pi": _mes_mais(r[4], n),
                "pf": _mes_mais(r[5], n),
                "v": _mes_mais(r[6], n),
                "cond": r[7],
                "desc": (r[8] or "").replace(f"{r[0][5:7]}/{r[0][:4]}", f"{comp_destino[5:7]}/{comp_destino[:4]}")
                or None,
                "obs": r[9],
                "por": por,
                "orig": fid,
            },
        )
    ).scalar()
    await db.execute(
        text(
            "INSERT INTO fin_fatura_itens (fatura_id, descricao, quantidade, valor_unitario, valor_total, "
            "  codigo_servico_id, posto_id) "
            "SELECT :novo, descricao, quantidade, valor_unitario, valor_total, codigo_servico_id, posto_id "
            "  FROM fin_fatura_itens WHERE fatura_id = :velho ORDER BY id"
        ),
        {"novo": int(novo), "velho": fid},
    )
    await _recalc(db, int(novo))
    return int(novo)


async def copiar_lote(
    db: AsyncSession, comp_origem: str, comp_destino: str, contratos: list[str] | None, por: str
) -> dict:
    """Copia TODAS as faturas vivas da competência de origem para a de destino (N de uma vez).

    Rodar duas vezes não duplica: o índice único parcial (contrato, competência) é a parede, e
    `copiar` devolve None para quem já tem fatura viva no destino.
    """
    await ensure(db)
    if comp_origem == comp_destino:
        raise HTTPException(status_code=400, detail="Competência de destino igual à de origem.")
    sql = "SELECT id, contrato_id::text FROM fin_faturas WHERE competencia = :m AND status <> 'cancelada' ORDER BY id"
    linhas = (await db.execute(text(sql), {"m": comp_origem})).fetchall()
    alvos = set(contratos or [])
    copiadas, puladas = 0, 0
    for fid, ctr in linhas:
        if alvos and (ctr or "") not in alvos:
            continue
        if await copiar(db, int(fid), comp_destino, por) is None:
            puladas += 1
        else:
            copiadas += 1
    await db.commit()
    return {
        "ok": True,
        "copiadas": copiadas,
        "puladas": puladas,
        "message": (
            f"{copiadas} fatura(s) copiada(s) para {comp_destino[5:7]}/{comp_destino[:4]} em rascunho"
            + (f"; {puladas} já existiam" if puladas else "")
            + ". Confira e emita."
        ),
    }


# ── cancelar ────────────────────────────────────────────────────────────────────────────────
async def cancelar(db: AsyncSession, fid: int, por: str) -> dict:
    """Só rascunho/emitida, e nunca com recebível pago — o dinheiro entrou, o papel fica."""
    await ensure(db)
    f = await _fatura(db, fid)
    if f[2] == "cancelada":
        return {"ok": True, "message": "Fatura já cancelada."}
    if f[3]:
        st = (
            await db.execute(
                text("SELECT status, coalesce(paid_value,0) FROM receivable_accounts WHERE id = CAST(:r AS uuid)"),
                {"r": f[3]},
            )
        ).first()
        if st and (st[0] in _RECEBIDO or Decimal(str(st[1])) > 0):
            raise HTTPException(
                status_code=409,
                detail=(
                    f"Fatura nº {f[1]:05d} tem conta a receber {st[0]} ({_brl(st[1])} recebido). "
                    "Cancele pela baixa/estorno do recebível, não pela fatura."
                ),
            )
    if f[2] not in ("rascunho", "emitida"):
        raise HTTPException(status_code=409, detail=f"Fatura {f[2]} — só rascunho ou emitida se cancela.")
    await db.execute(
        text("UPDATE fin_faturas SET status = 'cancelada', observacao = coalesce(observacao,'') || :s WHERE id = :i"),
        {"i": fid, "s": f"\nCancelada por {por} em {date.today().strftime('%d/%m/%Y')}."},
    )
    await db.commit()
    return {"ok": True, "message": f"Fatura {'nº ' + format(f[1], '05d') if f[1] else 'rascunho'} cancelada."}


# ── documento ───────────────────────────────────────────────────────────────────────────────
async def dados_documento(db: AsyncSession, fid: int) -> dict:
    """Os dados do PDF. O SACADO é a FONTE PAGADORA quando há — quem paga pode não ser quem contrata."""
    f = (
        await db.execute(
            text(
                "SELECT f.id, f.numero, f.competencia, f.periodo_inicio, f.periodo_fim, f.vencimento, "
                "       f.descricao_padrao, f.valor_total, f.status, f.observacao, "
                "       c.name, c.document_number, fp.razao_social, fp.cnpj, fp.endereco_cobranca, "
                "       ct.contract_number, cond.nome, e.slug "
                "  FROM fin_faturas f "
                "  LEFT JOIN clients c ON c.id = f.cliente_id "
                "  LEFT JOIN crm_fontes_pagadoras fp ON fp.id = f.fonte_pagadora_id "
                "  LEFT JOIN contracts ct ON ct.id = f.contrato_id "
                "  LEFT JOIN empresas e ON e.id = ct.empresa_id "
                "  LEFT JOIN fin_condicoes_pagamento cond ON cond.id = f.condicao_pagamento_id "
                " WHERE f.id = :i"
            ),
            {"i": fid},
        )
    ).first()
    if not f:
        raise HTTPException(status_code=404, detail="Fatura não encontrada.")
    itens = (
        await db.execute(
            text(
                "SELECT i.descricao, i.quantidade, i.valor_unitario, i.valor_total, s.item_lc116 "
                "  FROM fin_fatura_itens i LEFT JOIN fin_codigos_servico s ON s.id = i.codigo_servico_id "
                " WHERE i.fatura_id = :i ORDER BY i.id"
            ),
            {"i": fid},
        )
    ).fetchall()
    return {
        "id": f[0],
        "numero": f"{f[1]:05d}" if f[1] else "RASCUNHO",
        "competencia": f"{f[2][5:7]}/{f[2][:4]}",
        "periodo_inicio": f[3],
        "periodo_fim": f[4],
        "vencimento": f[5],
        "descricao": f[6],
        "valor": _q(f[7]),
        "status": f[8],
        "observacao": f[9],
        # a troca que a F12 pediu: com fonte pagadora, o papel sai no nome de quem PAGA.
        "sacado": f[12] or f[10] or "—",
        "sacado_documento": f[13] or f[11] or "",
        "endereco": f[14],
        "cliente": f[10] or "—",
        "contrato": f[15],
        "condicao": f[16],
        # quem EMITE é a empresa dona do contrato (`empresas.slug` → timbrado). Fatura avulsa,
        # sem contrato, sai pela Patrimonial — é quem fatura serviço (mesma decisão do recibo, F11).
        "empresa_slug": f[17] or "conecta_patrimonial",
        "itens": [
            {"descricao": i[0], "quantidade": i[1], "unitario": i[2], "total": i[3], "servico": i[4]} for i in itens
        ],
    }


async def pdf_lote(db: AsyncSession, ids: list[int]) -> bytes:
    """PDF timbrado com UMA fatura por página (o «imprimir lote» do DGX)."""
    if not ids:
        raise HTTPException(status_code=404, detail="Nenhuma fatura para imprimir.")
    return build_faturas_pdf([await dados_documento(db, int(i)) for i in ids])


# ── PDF (padrão-ouro Conecta Mais) ──────────────────────────────────────────────────────────
# Mora aqui, e não em `crm/services/doc_pdf.py`, por um motivo prático: aquele arquivo está fora
# do formato do `ruff format` desde antes desta frente, e encostar nele faria o hook de
# pre-commit reescrever 5 mil linhas de código de outras frentes no meio da onda. A marca
# continua vindo de `pdf_branding` (é lá que ela é centralizada), que é o que a regra da casa pede.
import io  # noqa: E402

from reportlab.lib import colors  # noqa: E402
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle  # noqa: E402

from modules.crm.services import pdf_branding as B  # noqa: E402, N812


def _doc(titulo: str) -> tuple:
    """Mesma moldura A4 dos demais documentos da casa (`doc_pdf._doc`)."""
    buf = io.BytesIO()
    return buf, SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=40 * mm,
        bottomMargin=16 * mm,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        title=titulo,
    )


def _meta(st, numero: str, periodo: str) -> list:
    partes = [x for x in (f"<b>Nº {numero}</b>" if numero else "", periodo) if x]
    if not partes:
        return []
    return [Paragraph("&nbsp;&nbsp;•&nbsp;&nbsp;".join(partes), st["capa_meta"]), Spacer(1, 6 * mm)]


def build_faturas_pdf(faturas: list[dict]) -> bytes:
    """Fatura(s) no padrão-ouro — UMA por página (é assim que o «imprimir lote» do DGX serve).

    Recebe uma LISTA de propósito: o lote da competência sai num PDF só, e a fatura avulsa é
    a lista de um. Cada dict vem de `financial/services/fin_faturas.dados_documento`.
    O «sacado» já chega resolvido (fonte pagadora quando há) — este arquivo não decide quem paga.
    """
    buf, doc = _doc("Fatura")
    st = B.styles()
    el: list = []
    for n, d in enumerate(faturas):
        if n:
            el.append(PageBreak())
        el += _fatura_corpo(st, d)
    # o timbrado é o da empresa DONA do contrato (Eletrônica × Patrimonial), por página.
    # ponytail: casa página N com a fatura N-1; uma fatura que passe de uma página levaria o
    # timbrado da seguinte na folha de transbordo. Se algum dia houver fatura de 2 páginas,
    # o conserto é marcar a página inicial de cada fatura num Flowable e ler daí.
    marcas = [B.empresa_branding(d.get("empresa_slug")) for d in faturas]

    def _hf(c, dc):
        B.header_footer(
            c, dc, titulo="FATURA DE SERVIÇOS", empresa=marcas[min(max(c.getPageNumber() - 1, 0), len(marcas) - 1)]
        )

    doc.build(el, onFirstPage=_hf, onLaterPages=_hf)
    return buf.getvalue()


def _fatura_corpo(st: dict, d: dict) -> list:
    periodo = ""
    if d.get("periodo_inicio") and d.get("periodo_fim"):
        periodo = f"Período {B.br_date(d['periodo_inicio'])} a {B.br_date(d['periodo_fim'])}"
    el: list = _meta(st, d.get("numero", ""), periodo or f"Competência {d.get('competencia', '')}")
    if d.get("status") == "cancelada":
        el.append(Paragraph("<b>FATURA CANCELADA</b>", st["destaque"]))
        el.append(Spacer(1, 3 * mm))

    info = [
        ("Sacado", d.get("sacado") or "—"),
        ("CNPJ/CPF", d.get("sacado_documento") or "—"),
        ("Competência", d.get("competencia") or "—"),
        ("Vencimento", B.br_date(d["vencimento"]) if d.get("vencimento") else "—"),
    ]
    if d.get("endereco"):
        info.insert(2, ("Endereço de cobrança", d["endereco"]))
    if d.get("contrato"):
        info.append(("Contrato", d["contrato"]))
    if d.get("condicao"):
        info.append(("Condição de pagamento", d["condicao"]))
    if d.get("sacado") != d.get("cliente"):
        info.append(("Serviços prestados a", d.get("cliente") or "—"))
    el.append(
        Table(
            [[Paragraph(f"<b>{k}</b>", st["cell"]), Paragraph(str(v), st["cell"])] for k, v in info],
            colWidths=[42 * mm, 132 * mm],
            style=TableStyle(
                [
                    ("BOX", (0, 0), (-1, -1), 0.5, B.AZUL_MEDIO),
                    ("INNERGRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#E5E7EB")),
                    ("BACKGROUND", (0, 0), (0, -1), B.FUNDO_CLARO),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ]
            ),
        )
    )
    el.append(Spacer(1, 5 * mm))

    el += B.secao("Discriminação dos serviços", st)
    linhas = [
        [
            Paragraph("<b>Descrição</b>", st["cellh"]),
            Paragraph("<b>LC 116</b>", st["cellh"]),
            Paragraph("<b>Qtd.</b>", st["cellh"]),
            Paragraph("<b>Valor unit.</b>", st["cellh"]),
            Paragraph("<b>Total</b>", st["cellh"]),
        ]
    ]
    for it in d.get("itens") or []:
        q = float(it.get("quantidade") or 0)
        linhas.append(
            [
                Paragraph(str(it.get("descricao") or ""), st["cell"]),
                Paragraph(str(it.get("servico") or "—"), st["cell"]),
                Paragraph(f"{q:.0f}" if q == int(q) else f"{q:.3f}", st["cellr"]),
                Paragraph(B.brl(it.get("unitario")), st["cellr"]),
                Paragraph(B.brl(it.get("total")), st["cellr"]),
            ]
        )
    linhas.append(
        [
            Paragraph("", st["cell"]),
            Paragraph("", st["cell"]),
            Paragraph("", st["cell"]),
            Paragraph("<b>TOTAL</b>", st["cell"]),
            Paragraph(f"<b>{B.brl(d.get('valor'))}</b>", st["cellr"]),
        ]
    )
    tb = Table(linhas, colWidths=[78 * mm, 18 * mm, 16 * mm, 32 * mm, 30 * mm], hAlign="LEFT")
    tb.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), B.AZUL_ESCURO),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, B.FUNDO_CLARO]),
                ("LINEABOVE", (0, -1), (-1, -1), 0.8, B.AZUL_MEDIO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    el.append(tb)
    el.append(Spacer(1, 5 * mm))
    if d.get("descricao"):
        el.append(Paragraph(str(d["descricao"]).replace("\n", "<br/>"), st["corpo"]))
    el.append(
        Paragraph(
            "<font size=8 color='#6B7280'>Fatura é documento de cobrança: não substitui a Nota Fiscal "
            "de Serviços (NFS-e), emitida à parte. Divergência nos itens acima, procure o setor "
            "financeiro antes do vencimento.</font>",
            st["corpo"],
        )
    )
    el.append(Spacer(1, 3 * mm))
    el.append(Paragraph(B.data_extenso(date.today()), st["corpo"]))
    return el
