"""DGX F11 — Financeiro/Faturamento: os cadastros pequenos do DGX que aqui viviam soltos (24/09/2026).

O que foi cavado antes de construir (sandbox = cópia de produção de 23/09):
  · `financial_custos_recorrentes` (3 linhas de teste, inativas) era só projeção do CFO — não gerava
    título. `payable_accounts.is_recurring` + `process_recurring_accounts` gera o PRÓXIMO só de conta
    já PAGA (1 linha). Nenhum dos dois é a «Conta Fixa» do DGX (recorrência que gera o título do mês).
  · `fin_cost_centers` vazia e `payable_accounts.cost_center` NULL em 369/369. O centro de custo que
    a casa usa DE FATO é a categoria do extrato (`bank_transactions.category`, 100% das saídas
    classificadas desde 04/2026: Folha, Fornecedor, Impostos, Diaristas…). É por ela que o orçado ×
    realizado deste arquivo fala.
  · `cfops` vazia; as NFS-e daqui NÃO usam CFOP — usam cTribNac (LC 116): 110201 (50 notas), 140601
    (32), 071002 (16), 140101 (9), 071001 (7). O emissor Manaus ainda manda `ItemListaServico`
    fixo 17.19 (nfse_multi_empresa_service.py:387) — apontado no relatório, não mexido.
  · `build_recibo_pdf` (crm/services/doc_pdf.py) já é o recibo timbrado «Recebemos de…», mas era
    sem número e sem registro. Aqui ganha `fin_recibos` com número sequencial sem buraco.
  · `commissions` 15 pendentes / `commission_payments` 0. Fechar = criar o pagamento (não confirmado)
    e marcar `approved`; confirmar/pagar continua no CRM e no caminho do dinheiro.
  · `employee_deductions.tipo='pensao_alimenticia'` existe no DP (0 linhas hoje); pensionista vira
    `financial_beneficiarios.tipo='pensionista'` + `employee_id` (de quem é descontado).

Prefixo `_` = o discovery pula; `financeiro.py` inclui `router` e chama `telas(db, out)` antes de
`montar_grupos` (abas em `_fin_grupos.GRUPOS`). DDL idempotente em `_ensure`.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, require_permission
from core.database import get_db

#: ANTES do import do data_controller (mesmo motivo do F1: o ciclo de import fecha com o router pronto).
router = APIRouter()

from modules.operacional.controllers.redesign_data_controller import (  # noqa: E402
    S,
    _helpers,
    b,
    brl,
    doc,
    t,
)

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_GATE = [Depends(require_permission("module:financeiro"))]

#: ids de tela que este arquivo entrega — o oráculo confere que cada um tem aba em `_fin_grupos`.
IDS = (
    "condicoes-pagamento",
    "condicao-pagamento-nova",
    "contas-fixas",
    "conta-fixa-nova",
    "contas-fixas-gerar",
    "codigos-servico",
    "codigo-servico-novo",
    "cfop-natureza",
    "cfop-novo",
    "recibos",
    "recibo-novo",
    "comissoes-fechamento",
    "comissoes-fechar",
    "orcamento-vs-realizado",
    "orcamento-centro-novo",
    "pensionistas",
    "pensionista-novo",
)

TIPOS_BENEFICIARIO = ("fornecedor", "prestador", "pensionista", "advogado", "representante")

# ── DDL ─────────────────────────────────────────────────────────────────────────────────────
_DDL = [
    """CREATE TABLE IF NOT EXISTS fin_condicoes_pagamento (
        id serial PRIMARY KEY, nome text NOT NULL UNIQUE, parcelas int NOT NULL DEFAULT 1,
        dias jsonb NOT NULL DEFAULT '[0]', entrada_percentual numeric(5,2) NOT NULL DEFAULT 0,
        ativo boolean NOT NULL DEFAULT true, created_at timestamptz DEFAULT now())""",
    "ALTER TABLE financial_custos_recorrentes ADD COLUMN IF NOT EXISTS favorecido text",
    "ALTER TABLE financial_custos_recorrentes ADD COLUMN IF NOT EXISTS encerrado_em date",
    """CREATE TABLE IF NOT EXISTS fin_contas_fixas_geradas (
        custo_id bigint NOT NULL, competencia char(7) NOT NULL, payable_id uuid,
        created_at timestamptz DEFAULT now(), PRIMARY KEY (custo_id, competencia))""",
    """CREATE TABLE IF NOT EXISTS fin_codigos_servico (
        id serial PRIMARY KEY, item_lc116 text NOT NULL UNIQUE, ctribnac text, descricao text,
        aliquota_iss numeric(5,2), codigo_municipal text, cnae text, ativo boolean NOT NULL DEFAULT true,
        created_at timestamptz DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS fin_recibos (
        id serial PRIMARY KEY, numero int NOT NULL UNIQUE, cliente_id uuid, cliente_nome text NOT NULL,
        cliente_documento text, valor numeric(14,2) NOT NULL, referente_a text, data date NOT NULL DEFAULT CURRENT_DATE,
        forma_pagamento text, emitido_por text, pdf_path text, created_at timestamptz DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS fin_comissoes_fechamentos (
        id serial PRIMARY KEY, competencia char(7) NOT NULL, seller_id uuid NOT NULL, qtd int NOT NULL,
        total numeric(14,2) NOT NULL, fechado_por text, fechado_em timestamptz DEFAULT now(),
        UNIQUE (competencia, seller_id))""",
    "ALTER TABLE financial_beneficiarios ADD COLUMN IF NOT EXISTS tipo varchar(30)",
    "ALTER TABLE financial_beneficiarios ADD COLUMN IF NOT EXISTS employee_id uuid",
    "CREATE INDEX IF NOT EXISTS ix_benef_employee ON financial_beneficiarios (employee_id) WHERE employee_id IS NOT NULL",
]

_SEED_CONDICOES = [
    ("À vista", 1, [0], 0),
    ("30 dias", 1, [30], 0),
    ("30/60", 2, [30, 60], 0),
    ("30/60/90", 3, [30, 60, 90], 0),
]

#: LC 116 → cTribNac que as NFS-e da casa já emitiram (contagem no sandbox 24/09) + os do mapa de vigilância.
_SEED_SERVICOS = [
    ("11.02", "110201", "Vigilância, segurança ou monitoramento de bens, pessoas e semoventes"),
    ("11.03", "110301", "Escolta, inclusive de veículos e cargas"),
    ("11.04", "110401", "Armazenamento, depósito, carga, descarga, arrumação e guarda de bens"),
    ("11.05", "110501", "Transporte de valores"),
    ("7.10", "071001", "Limpeza, manutenção e conservação de vias, imóveis, chaminés, piscinas, parques, jardins"),
    ("7.10.02", "071002", "Limpeza, conservação, zeladoria e portaria (desdobro 02)"),
    (
        "14.01",
        "140101",
        "Lubrificação, limpeza, lustração, revisão, carga e recarga, conserto, restauração, manutenção",
    ),
    ("14.06", "140601", "Instalação e montagem de aparelhos, máquinas e equipamentos"),
]

#: (codigo, natureza da operação, tipo, grupo=1º dígito) — enums de financial/models/cfop_ncm.py
_SEED_CFOP = [
    ("5933", "Prestação de serviço tributado pelo ISSQN — dentro do estado", "saida", "5"),
    ("6933", "Prestação de serviço tributado pelo ISSQN — fora do estado", "saida", "6"),
]


async def _ensure(db: AsyncSession) -> None:
    for sql in _DDL:
        await db.execute(text(sql))
    for nome, n, dias, ent in _SEED_CONDICOES:
        await db.execute(
            text(
                "INSERT INTO fin_condicoes_pagamento (nome, parcelas, dias, entrada_percentual) "
                "VALUES (:n, :p, CAST(:d AS jsonb), :e) ON CONFLICT (nome) DO NOTHING"
            ),
            {"n": nome, "p": n, "d": json.dumps(dias), "e": ent},
        )
    for item, ctrib, desc in _SEED_SERVICOS:
        await db.execute(
            text(
                "INSERT INTO fin_codigos_servico (item_lc116, ctribnac, descricao) VALUES (:i, :c, :d) "
                "ON CONFLICT (item_lc116) DO NOTHING"
            ),
            {"i": item, "c": ctrib, "d": desc},
        )
    # alíquota: a da ÚLTIMA NFS-e emitida com o código — nunca inventada; fica NULL se nunca emitiu.
    await db.execute(
        text(
            "UPDATE fin_codigos_servico s SET aliquota_iss = (SELECT n.iss_aliquota FROM nfse_emitidas_nacional n "
            " WHERE n.codigo_servico = s.ctribnac AND coalesce(n.cancelada,false)=false AND n.iss_aliquota IS NOT NULL "
            " ORDER BY n.data_emissao DESC LIMIT 1) WHERE s.aliquota_iss IS NULL"
        )
    )
    for cod, desc, tipo, grupo in _SEED_CFOP:
        await db.execute(
            text(
                "INSERT INTO cfops (id, codigo, descricao, descricao_resumida, tipo, grupo, natureza, active, created_at, updated_at) "
                "SELECT gen_random_uuid(), CAST(:c AS varchar), CAST(:d AS text), CAST(:d AS varchar), CAST(:t AS varchar), CAST(:g AS varchar), "
                "'outras', true, now(), now() WHERE NOT EXISTS (SELECT 1 FROM cfops WHERE codigo = CAST(:c AS varchar))"
            ),
            {"c": cod, "d": desc, "t": tipo, "g": grupo},
        )
    await db.commit()


# ── regras puras (o oráculo importa estas) ──────────────────────────────────────────────────
def vencimentos(dias: list[int], data_base: date) -> list[date]:
    """Datas de vencimento = data-base + cada prazo da condição."""
    return [data_base + timedelta(days=int(d)) for d in dias]


def parcelas(valor: Decimal, n: int, entrada_pct: Decimal) -> list[Decimal]:
    """Divide `valor` em `n` parcelas fechando ao centavo; a 1ª leva a entrada (%) se houver."""
    valor = Decimal(valor).quantize(Decimal("0.01"))
    n = max(1, int(n))
    if n == 1:
        return [valor]
    out: list[Decimal] = []
    resto = valor
    if entrada_pct and entrada_pct > 0:
        ent = (valor * Decimal(entrada_pct) / 100).quantize(Decimal("0.01"), ROUND_HALF_UP)
        out.append(ent)
        resto -= ent
        n -= 1
    base = (resto / n).quantize(Decimal("0.01"), ROUND_HALF_UP)
    out += [base] * (n - 1)
    out.append(resto - base * (n - 1))
    return out


_UNID = [
    "",
    "um",
    "dois",
    "três",
    "quatro",
    "cinco",
    "seis",
    "sete",
    "oito",
    "nove",
    "dez",
    "onze",
    "doze",
    "treze",
    "quatorze",
    "quinze",
    "dezesseis",
    "dezessete",
    "dezoito",
    "dezenove",
]
_DEZ = ["", "", "vinte", "trinta", "quarenta", "cinquenta", "sessenta", "setenta", "oitenta", "noventa"]
_CEN = [
    "",
    "cento",
    "duzentos",
    "trezentos",
    "quatrocentos",
    "quinhentos",
    "seiscentos",
    "setecentos",
    "oitocentos",
    "novecentos",
]


def _ate_999(n: int) -> str:
    if n == 0:
        return ""
    if n == 100:
        return "cem"
    c, r = divmod(n, 100)
    d, u = divmod(r, 10)
    partes = [_CEN[c]] if c else []
    if r < 20:
        if r:
            partes.append(_UNID[r])
    else:
        partes.append(_DEZ[d] + (f" e {_UNID[u]}" if u else ""))
    return " e ".join(partes)


def por_extenso(v: Decimal) -> str:
    """Reais por extenso (até 999 milhões) — o recibo exige; errar o extenso invalida o papel."""
    v = Decimal(v).quantize(Decimal("0.01"))
    inteiro, cent = int(v), int((v - int(v)) * 100)
    if inteiro == 0 and cent == 0:
        return "zero reais"
    partes = []
    mi, r = divmod(inteiro, 1_000_000)
    mil, uni = divmod(r, 1_000)
    if mi:
        partes.append(f"{_ate_999(mi)} {'milhão' if mi == 1 else 'milhões'}")
    if mil:
        partes.append("mil" if mil == 1 else f"{_ate_999(mil)} mil")
    if uni:
        partes.append(_ate_999(uni))
    txt = ", ".join(partes[:-1]) + (" e " if len(partes) > 1 else "") + partes[-1] if partes else ""
    if inteiro:
        txt += " real" if inteiro == 1 else " reais"
    if cent:
        txt += (" e " if inteiro else "") + _ate_999(cent) + (" centavo" if cent == 1 else " centavos")
    return txt


def _dec(v, rotulo: str, minimo: Decimal | None = Decimal("0.01")) -> Decimal:
    s = str(v or "").strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail=f"{rotulo}: valor inválido.")
    if minimo is not None and d < minimo:
        raise HTTPException(status_code=400, detail=f"{rotulo}: deve ser maior que zero.")
    return d.quantize(Decimal("0.01"))


def _comp(v) -> str:
    """'MM/AAAA' ou 'AAAA-MM' → 'AAAA-MM'."""
    s = str(v or "").strip()
    m = re.fullmatch(r"(\d{2})/(\d{4})", s)
    if m:
        return f"{m.group(2)}-{m.group(1)}"
    if re.fullmatch(r"\d{4}-\d{2}", s) and 1 <= int(s[5:]) <= 12:
        return s
    raise HTTPException(status_code=400, detail="Competência no formato MM/AAAA.")


def _br(c: str) -> str:
    return f"{c[5:7]}/{c[:4]}" if c and len(c) == 7 else (c or "—")


def _date(v, rotulo="Data") -> date:
    try:
        return date.fromisoformat(str(v or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{rotulo} inválida.")


# ── serviços que o oráculo chama direto ─────────────────────────────────────────────────────
async def emitir_recibo(db: AsyncSession, p: dict, emitido_por: str) -> int:
    """Grava o recibo com o PRÓXIMO número. Lock de aplicação para dois cliques não pegarem o mesmo."""
    nome = str(p.get("cliente_nome") or "").strip()
    if len(nome) < 2:
        raise HTTPException(status_code=400, detail="Cliente obrigatório.")
    valor = _dec(p.get("valor"), "Valor")
    cid = str(p.get("cliente_id") or "").strip() or None
    docn = str(p.get("cliente_documento") or "").strip() or None
    if cid and not docn:
        r = (
            await db.execute(text("SELECT name, document_number FROM clients WHERE id = CAST(:i AS uuid)"), {"i": cid})
        ).first()
        if r:
            nome, docn = r[0] or nome, r[1]
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext('fin_recibos'))"))
    numero = (
        await db.execute(
            text(
                "INSERT INTO fin_recibos (numero, cliente_id, cliente_nome, cliente_documento, valor, referente_a, data, forma_pagamento, emitido_por) "
                "SELECT coalesce(max(numero),0)+1, CAST(:cid AS uuid), :n, :d, :v, :ref, :dt, :fp, :por FROM fin_recibos RETURNING numero"
            ),
            {
                "cid": cid,
                "n": nome,
                "d": docn,
                "v": valor,
                "ref": str(p.get("referente_a") or "serviços prestados").strip(),
                "dt": _date(p.get("data")) if p.get("data") else date.today(),
                "fp": str(p.get("forma_pagamento") or "").strip() or None,
                "por": emitido_por,
            },
        )
    ).scalar()
    await db.execute(
        text("UPDATE fin_recibos SET pdf_path = :u WHERE numero = :n"),
        {"u": f"/api/v1/redesign/recibo/{numero}/pdf", "n": numero},
    )
    await db.commit()
    return int(numero)


_SQL_ABERTAS = (
    "SELECT c.id::text, c.final_commission, c.reference_number, c.description, c.sale_value "
    "  FROM commissions c "
    " WHERE c.seller_id = CAST(:s AS uuid) AND coalesce(c.is_active,true) AND c.status IN ('pending','approved') "
    "   AND to_char(coalesce(c.period_start, c.trigger_date, c.due_date, c.created_at::date),'YYYY-MM') = :m "
    "   AND NOT EXISTS (SELECT 1 FROM commission_payments p WHERE p.commission_id = c.id)"
)


async def fechar_comissoes(db: AsyncSession, competencia: str, seller_id: str, por: str) -> dict:
    """Fecha o período de UM vendedor: cria `commission_payments` (não confirmado) por comissão aberta,
    marca `approved` e registra o fechamento. Segunda chamada no mesmo par → ValueError."""
    ja = (
        await db.execute(
            text("SELECT id FROM fin_comissoes_fechamentos WHERE competencia=:m AND seller_id=CAST(:s AS uuid)"),
            {"m": competencia, "s": seller_id},
        )
    ).scalar()
    if ja:
        raise ValueError(f"Período {_br(competencia)} deste vendedor já fechado (#{ja}).")
    abertas = (await db.execute(text(_SQL_ABERTAS), {"s": seller_id, "m": competencia})).fetchall()
    if not abertas:
        raise ValueError(f"Nenhuma comissão aberta em {_br(competencia)} para este vendedor.")
    total = Decimal("0")
    for cid, valor, _ref, _d, _sv in abertas:
        total += Decimal(str(valor or 0))
        await db.execute(
            text(
                "INSERT INTO commission_payments (id, commission_id, amount, payment_method, payment_date, payment_reference, is_confirmed, notes, created_at) "
                "VALUES (gen_random_uuid(), CAST(:c AS uuid), :v, 'pix', CURRENT_DATE, :ref, false, :n, now())"
            ),
            {
                "c": cid,
                "v": float(valor or 0),
                "ref": f"FECH-{competencia}",
                "n": f"Fechamento de comissões {_br(competencia)} por {por}",
            },
        )
        await db.execute(
            text("UPDATE commissions SET status='approved', updated_at=now() WHERE id = CAST(:c AS uuid)"), {"c": cid}
        )
    fid = (
        await db.execute(
            text(
                "INSERT INTO fin_comissoes_fechamentos (competencia, seller_id, qtd, total, fechado_por) "
                "VALUES (:m, CAST(:s AS uuid), :q, :t, :p) RETURNING id"
            ),
            {"m": competencia, "s": seller_id, "q": len(abertas), "t": total, "p": por},
        )
    ).scalar()
    await db.commit()
    return {"id": int(fid), "qtd": len(abertas), "total": float(total)}


_SQL_REALIZADO = (
    "SELECT category, to_char(transaction_date,'YYYY-MM') AS mes, round(sum(-amount)::numeric,2) "
    "  FROM bank_transactions WHERE amount < 0 AND category IS NOT NULL AND category <> '' "
    "   AND transaction_date >= date_trunc('month', CURRENT_DATE) - interval '11 months' "
    " GROUP BY 1, 2"
)


async def orcado_realizado(db: AsyncSession) -> list[dict]:
    """(centro, mês) dos últimos 12 meses: orçado (`financial_orcamentos` chave `cc:<centro>:<AAAA-MM>`) ×
    realizado (saídas classificadas do extrato). Linha existe se houver orçado OU realizado."""
    real = {(r[0], r[1]): Decimal(str(r[2])) for r in (await db.execute(text(_SQL_REALIZADO))).fetchall()}
    orc: dict[tuple[str, str], Decimal] = {}
    for k, v in (
        await db.execute(text("SELECT chave, valor FROM financial_orcamentos WHERE chave LIKE 'cc:%'"))
    ).fetchall():
        partes = k.split(":")
        if len(partes) == 3:
            orc[(partes[1], partes[2])] = Decimal(str(v))
    out = []
    for centro, mes in sorted(set(real) | set(orc), key=lambda x: (x[1], x[0]), reverse=True):
        o, r = orc.get((centro, mes)), real.get((centro, mes), Decimal("0"))
        out.append(
            {
                "centro": centro,
                "mes": mes,
                "orcado": o,
                "realizado": r,
                "desvio": (o - r) if o is not None else None,
                "desvio_pct": (float((o - r) / o * 100) if o else None) if o is not None else None,
            }
        )
    return out


_SQL_PENSOES = (
    "SELECT d.id::text, e.id::text, e.nome, coalesce(d.descricao,'Pensão alimentícia'), d.valor, d.percentual, d.data_inicio, "
    "       bf.id, bf.nome, bf.chave_pix, bf.tipo_chave "
    "  FROM employee_deductions d JOIN employees e ON e.id = d.employee_id "
    "  LEFT JOIN LATERAL (SELECT b.id, b.nome, b.chave_pix, b.tipo_chave FROM financial_beneficiarios b "
    "         WHERE b.employee_id = e.id AND b.tipo = 'pensionista' AND coalesce(b.ativo,true) ORDER BY b.id DESC LIMIT 1) bf ON true "
    " WHERE d.tipo = 'pensao_alimenticia' AND coalesce(d.ativo,true) ORDER BY e.nome"
)


async def pensoes_sem_beneficiario(db: AsyncSession) -> int:
    return sum(1 for r in (await db.execute(text(_SQL_PENSOES))).fetchall() if r[7] is None)


# ── telas ───────────────────────────────────────────────────────────────────────────────────
async def telas(db, out: dict | None = None) -> dict:
    await _ensure(db)
    mine, safe, tbl = _helpers(db)
    out = out if out is not None else {}
    hoje = date.today()
    comp_atual = f"{hoje.month:02d}/{hoje.year}"

    # 1) Condições de pagamento ───────────────────────────────────────────────────────────
    conds = (
        await db.execute(
            text(
                "SELECT id, nome, parcelas, dias, entrada_percentual, ativo FROM fin_condicoes_pagamento ORDER BY ativo DESC, id"
            )
        )
    ).fetchall()
    _campos_cond = lambda r=None: [  # noqa: E731
        {
            "key": "nome",
            "label": "Nome*",
            "type": "text",
            "span": "span 1",
            "ph": "Ex.: 30/60/90",
            **({"value": r[1]} if r else {}),
        },
        {
            "key": "dias",
            "label": "Dias após a data-base (separados por vírgula)*",
            "type": "text",
            "span": "span 1",
            "ph": "0 · 30 · 30,60",
            **({"value": ",".join(str(x) for x in (r[3] or []))} if r else {}),
        },
        {
            "key": "entrada_percentual",
            "label": "Entrada (%)",
            "type": "number",
            "span": "span 1",
            **({"value": str(r[4] or 0)} if r else {}),
        },
    ]
    mine["condicoes-pagamento"] = {
        "title": "Condições de pagamento",
        "sub": "À vista, 30, 30/60, 30/60/90… O número de parcelas é o número de prazos. Usada em «Registrar conta» (pagar e receber) para gerar as parcelas com os vencimentos certos.",
        "cta": "Nova condição",
        "ctaTo": "condicao-pagamento-nova",
        "type": "table",
        "searchHint": "Buscar condição…",
        "grid": "1.4fr 0.6fr 1.4fr 0.7fr 0.7fr",
        "cols": ["Nome", "Parcelas", "Dias", "Entrada", "Ativa"],
        "rows": [
            {
                "cells": [
                    t(r[1], 600, _ND),
                    t(str(r[2])),
                    t(" / ".join(str(x) for x in (r[3] or [])) + " dias"),
                    t(f"{float(r[4] or 0):.0f}%"),
                    b("Ativa", "ok") if r[5] else b("Inativa", "mut"),
                ],
                "edit": {
                    "endpoint": f"{_ACT}condicao-pagamento-salvar",
                    "method": "POST",
                    "btnLabel": "Editar",
                    "submitLabel": "Salvar",
                    "okMsg": "Condição salva. Recarregue.",
                    "fields": [
                        {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                        *_campos_cond(r),
                    ],
                },
                "actions": [
                    {
                        "title": f"{'Inativar' if r[5] else 'Reativar'} «{r[1]}»",
                        "endpoint": f"{_ACT}condicao-pagamento-salvar",
                        "method": "POST",
                        "btnLabel": "Inativar" if r[5] else "Reativar",
                        "btnStyle": "outline",
                        "submitLabel": "Confirmar",
                        "okMsg": "Feito. Recarregue.",
                        "fields": [
                            {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                            {
                                "key": "ativo",
                                "label": "ativo",
                                "type": "text",
                                "value": "0" if r[5] else "1",
                                "span": "span 1",
                            },
                        ],
                    }
                ],
            }
            for r in conds
        ],
    }
    mine["condicao-pagamento-nova"] = {
        "title": "Nova condição de pagamento",
        "sub": "Ex.: «Entrada + 30/60» = dias 0,30,60 com entrada 40%.",
        "cta": "Salvar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}condicao-pagamento-salvar", "okMsg": "Condição criada."},
        "fields": _campos_cond(),
    }
    # o select entra nos forms existentes de «Registrar conta» — e o envio passa a criar as parcelas.
    _opt_cond = [{"value": "", "label": "— sem condição (um vencimento só) —"}] + [
        {"value": str(r[0]), "label": f"{r[1]} ({r[2]}x)"} for r in conds if r[5]
    ]
    for fid, novo in (
        ("registrar-conta-pagar", "payable-condicao"),
        ("registrar-conta-receber", "receivable-condicao"),
    ):
        scr = out.get(fid)
        if (
            isinstance(scr, dict)
            and scr.get("type") == "form"
            and not any(f.get("key") == "condicao_id" for f in scr.get("fields", []))
        ):
            scr["submit"]["endpoint"] = f"{_ACT}{novo}"
            for f in scr["fields"]:
                if f.get("key") == "due_date":
                    f["label"] = "Vencimento (ou data-base da condição)*"
            scr["fields"].append(
                {
                    "key": "condicao_id",
                    "label": "Condição de pagamento",
                    "type": "select",
                    "span": "span 1",
                    "options": _opt_cond,
                }
            )

    # 2) Contas fixas ─────────────────────────────────────────────────────────────────────
    await safe(
        "contas-fixas",
        tbl(
            "Contas fixas",
            "Recorrência que GERA o título do mês em Contas a Pagar (um por conta por competência — nunca duplica). Encerrar não apaga o que já foi gerado.",
            "Nova conta fixa",
            ["Descrição", "Categoria", "Favorecido", "Valor", "Vence dia", "Gerado até", "Estado"],
            "2fr 0.9fr 1.3fr 0.9fr 0.6fr 0.8fr 0.8fr",
            "SELECT c.id, coalesce(c.descricao,'—'), coalesce(c.categoria,'—'), coalesce(c.favorecido,'—'), coalesce(c.valor,0), c.dia_vencimento, "
            "       (SELECT max(competencia) FROM fin_contas_fixas_geradas g WHERE g.custo_id=c.id), coalesce(c.ativo,true) AND c.encerrado_em IS NULL, c.encerrado_em, "
            "       c.parcelas_total, coalesce(c.parcelas_pagas,0) + (SELECT count(*) FROM fin_contas_fixas_geradas g WHERE g.custo_id=c.id) "
            "  FROM financial_custos_recorrentes c ORDER BY (coalesce(c.ativo,true) AND c.encerrado_em IS NULL) DESC, c.valor DESC NULLS LAST LIMIT 300",
            lambda r: [
                t((r[1] or "—")[:56], 600, _ND),
                b((r[2] or "—").capitalize(), "info"),
                t((r[3] or "—")[:30]),
                t(brl(r[4]), 600),
                t(f"dia {int(r[5])}" if r[5] else "—"),
                t(_br(r[6]) if r[6] else "nunca", 500, "#94A3B8" if not r[6] else "#334155"),
                b("Ativa" + (f" · {r[10]}/{r[9]}" if r[9] else ""), "ok")
                if r[7]
                else b(f"Encerrada {r[8].strftime('%d/%m/%Y') if r[8] else ''}".strip(), "mut"),
            ],
            actionsfn=lambda r: (
                [
                    {
                        "title": f"Encerrar «{r[1]}»",
                        "sub": "Para de gerar título a partir de agora. O que já foi gerado fica.",
                        "endpoint": f"{_ACT}conta-fixa-encerrar",
                        "method": "POST",
                        "btnLabel": "Encerrar",
                        "btnStyle": "outline",
                        "submitLabel": "Encerrar",
                        "okMsg": "Conta fixa encerrada. Recarregue.",
                        "fields": [{"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"}],
                    }
                ]
                if r[7]
                else None
            ),
        ),
    )
    if isinstance(mine.get("contas-fixas"), dict):
        mine["contas-fixas"]["ctaTo"] = "conta-fixa-nova"
    mine["conta-fixa-nova"] = {
        "title": "Nova conta fixa",
        "sub": "Aluguel, contador, software, seguro, parcelamento. O título do mês nasce em «Gerar títulos do mês».",
        "cta": "Cadastrar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}conta-fixa-salvar", "okMsg": "Conta fixa cadastrada."},
        "fields": [
            {"key": "descricao", "label": "Descrição*", "type": "text", "span": "span 2", "ph": "Ex.: Aluguel — sede"},
            {
                "key": "categoria",
                "label": "Categoria*",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": v, "label": l}
                    for v, l in (
                        ("fixo", "Fixo"),
                        ("parcelamento", "Parcelamento"),
                        ("software", "Software"),
                        ("seguro", "Seguro"),
                        ("impostos", "Impostos"),
                        ("outros", "Outros"),
                    )
                ],
            },
            {"key": "valor", "label": "Valor (R$)*", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "dia_vencimento", "label": "Dia do vencimento*", "type": "number", "span": "span 1", "ph": "10"},
            {
                "key": "parcelas_total",
                "label": "Total de parcelas (vazio = sem fim)",
                "type": "number",
                "span": "span 1",
            },
            {"key": "favorecido", "label": "Favorecido", "type": "text", "span": "span 2", "ph": "Quem recebe"},
        ],
    }
    n_ativas = (
        await db.execute(
            text(
                "SELECT count(*) FROM financial_custos_recorrentes WHERE coalesce(ativo,true) AND encerrado_em IS NULL AND coalesce(valor,0)>0"
            )
        )
    ).scalar() or 0
    mine["contas-fixas-gerar"] = {
        "title": "Gerar títulos do mês",
        "sub": f"{n_ativas} conta(s) fixa(s) ativa(s). Cria em Contas a Pagar o título de cada uma na competência — rodar de novo não duplica. Não paga nada.",
        "cta": "Gerar",
        "type": "form",
        "submit": {
            "endpoint": f"{_ACT}contas-fixas-gerar",
            "okMsg": "Títulos gerados.",
            "showResult": True,
            "confirm": "Vai criar um título em Contas a Pagar para cada conta fixa ativa nesta competência (sem duplicar).",
        },
        "fields": [
            {
                "key": "competencia",
                "label": "Competência (MM/AAAA)*",
                "type": "text",
                "span": "span 1",
                "value": comp_atual,
            }
        ],
    }

    # 3) Códigos de serviço + CFOP ────────────────────────────────────────────────────────
    _campos_serv = lambda r=None: [  # noqa: E731
        {
            "key": "item_lc116",
            "label": "Item LC 116*",
            "type": "text",
            "span": "span 1",
            "ph": "11.02",
            **({"value": r[1]} if r else {}),
        },
        {
            "key": "descricao",
            "label": "Descrição*",
            "type": "text",
            "span": "span 2",
            **({"value": r[3] or ""} if r else {}),
        },
        {
            "key": "aliquota_iss",
            "label": "Alíquota ISS (%)",
            "type": "number",
            "span": "span 1",
            **({"value": str(r[4]) if r and r[4] is not None else ""} if r else {}),
        },
        {
            "key": "codigo_municipal",
            "label": "Código municipal (Manaus)",
            "type": "text",
            "span": "span 1",
            **({"value": r[5] or ""} if r else {}),
        },
        {"key": "cnae", "label": "CNAE", "type": "text", "span": "span 1", **({"value": r[6] or ""} if r else {})},
    ]
    await safe(
        "codigos-servico",
        tbl(
            "Códigos de serviço (LC 116 / cTribNac)",
            "As NFS-e daqui não usam CFOP: usam o código de tributação nacional (LC 116). A alíquota vem da última NFS-e emitida com o código — vazia = nunca emitida. «Notas» = quantas saíram com ele.",
            "Novo código",
            ["Item LC 116", "cTribNac", "Descrição", "ISS", "Cód. municipal", "CNAE", "Notas"],
            "0.7fr 0.7fr 2.4fr 0.5fr 0.9fr 0.7fr 0.5fr",
            "SELECT s.id, s.item_lc116, s.ctribnac, s.descricao, s.aliquota_iss, s.codigo_municipal, s.cnae, s.ativo, "
            "       (SELECT count(*) FROM nfse_emitidas_nacional n WHERE n.codigo_servico = s.ctribnac AND coalesce(n.cancelada,false)=false) "
            "  FROM fin_codigos_servico s ORDER BY s.ativo DESC, 9 DESC, s.item_lc116",
            lambda r: [
                t(r[1], 600, _ND),
                t(r[2] or "—"),
                t((r[3] or "—")[:70]),
                t(f"{float(r[4]):.2f}%" if r[4] is not None else "—"),
                t(r[5] or "—"),
                t(r[6] or "—"),
                b(str(r[8]), "ok" if r[8] else "mut"),
            ],
            editfn=lambda r: {
                "endpoint": f"{_ACT}codigo-servico-salvar",
                "method": "POST",
                "btnLabel": "Editar",
                "submitLabel": "Salvar",
                "okMsg": "Código salvo. Recarregue.",
                "fields": [
                    {"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"},
                    *_campos_serv(r),
                ],
            },
        ),
    )
    if isinstance(mine.get("codigos-servico"), dict):
        mine["codigos-servico"]["ctaTo"] = "codigo-servico-novo"
    mine["codigo-servico-novo"] = {
        "title": "Novo código de serviço",
        "sub": "O cTribNac é derivado do item (11.02 → 110201).",
        "cta": "Salvar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}codigo-servico-salvar", "okMsg": "Código criado."},
        "fields": _campos_serv(),
    }
    await safe(
        "cfop-natureza",
        tbl(
            "CFOP / Natureza da operação",
            "Cadastro do DGX. Aqui só vale para NF-e de mercadoria (compras/estoque) — a NFS-e usa código de serviço (aba ao lado). 5933/6933 semeados.",
            "Novo CFOP",
            ["Código", "Descrição", "Tipo", "Grupo", "Ativo"],
            "0.6fr 3fr 0.7fr 0.7fr 0.6fr",
            "SELECT id::text, codigo, coalesce(descricao,'—'), coalesce(tipo,'—'), coalesce(grupo,'—'), coalesce(active,true) FROM cfops ORDER BY codigo",
            lambda r: [
                t(r[1], 600, _ND),
                t(r[2][:90]),
                t(r[3]),
                t(r[4]),
                b("Ativo", "ok") if r[5] else b("Inativo", "mut"),
            ],
        ),
    )
    if isinstance(mine.get("cfop-natureza"), dict):
        mine["cfop-natureza"]["ctaTo"] = "cfop-novo"
    mine["cfop-novo"] = {
        "title": "Novo CFOP",
        "sub": "Código de 4 dígitos + natureza da operação.",
        "cta": "Salvar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}cfop-salvar", "okMsg": "CFOP criado."},
        "fields": [
            {"key": "codigo", "label": "Código*", "type": "text", "span": "span 1", "ph": "5933"},
            {"key": "descricao", "label": "Natureza da operação*", "type": "text", "span": "span 2"},
            {
                "key": "tipo",
                "label": "Tipo",
                "type": "select",
                "span": "span 1",
                "options": [{"value": "saida", "label": "Saída"}, {"value": "entrada", "label": "Entrada"}],
            },
        ],
    }

    # 4) Recibos de venda ─────────────────────────────────────────────────────────────────
    await safe(
        "recibos",
        tbl(
            "Recibos de venda",
            "Numeração sequencial sem buraco. Cada linha abre o PDF timbrado (padrão-ouro, valor por extenso).",
            "Novo recibo",
            ["Nº", "Data", "Cliente", "Valor", "Referente a", "Forma", "Emitido por"],
            "0.4fr 0.7fr 1.8fr 0.9fr 2fr 0.8fr 1fr",
            "SELECT numero, data, cliente_nome, valor, coalesce(referente_a,'—'), coalesce(forma_pagamento,'—'), coalesce(emitido_por,'—') FROM fin_recibos ORDER BY numero DESC LIMIT 300",
            lambda r: [
                t(f"{r[0]:05d}", 600, _ND),
                t(r[1].strftime("%d/%m/%Y")),
                t(r[2][:40], 600),
                t(brl(r[3]), 600),
                t(r[4][:60]),
                t(r[5]),
                t(r[6][:24]),
            ],
            docsfn=lambda r: [doc(f"Recibo {r[0]:05d}", f"/api/v1/redesign/recibo/{r[0]}/pdf", fmt="pdf")],
        ),
    )
    if isinstance(mine.get("recibos"), dict):
        mine["recibos"]["ctaTo"] = "recibo-novo"
    clientes = (
        await db.execute(
            text(
                "SELECT id::text, name, coalesce(document_number,'') FROM clients WHERE coalesce(ativo,true) ORDER BY name LIMIT 400"
            )
        )
    ).fetchall()
    mine["recibo-novo"] = {
        "title": "Emitir recibo de venda",
        "sub": "Documento com fé — sai numerado, timbrado e com o valor por extenso. Escolha o cliente cadastrado OU digite o nome.",
        "cta": "Emitir recibo",
        "type": "form",
        "submit": {
            "endpoint": f"{_ACT}recibo-pdf",
            "okMsg": "Recibo emitido — abrindo o PDF.",
            "gated": True,
            "confirm": "Vai emitir um recibo NUMERADO em nome da empresa. Confira cliente e valor.",
        },
        "fields": [
            {
                "key": "cliente_id",
                "label": "Cliente cadastrado",
                "type": "select",
                "span": "span 2",
                "options": [{"value": "", "label": "— digitar o nome abaixo —"}]
                + [{"value": c[0], "label": f"{c[1]}" + (f" · {c[2]}" if c[2] else "")} for c in clientes],
            },
            {"key": "cliente_nome", "label": "Ou nome do cliente", "type": "text", "span": "span 1"},
            {"key": "cliente_documento", "label": "CNPJ/CPF", "type": "text", "span": "span 1"},
            {"key": "valor", "label": "Valor (R$)*", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "data", "label": "Data", "type": "date", "span": "span 1"},
            {
                "key": "forma_pagamento",
                "label": "Forma de pagamento",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": v, "label": v} for v in ("", "PIX", "Transferência", "Boleto", "Dinheiro", "Cartão")
                ],
            },
            {
                "key": "referente_a",
                "label": "Referente a*",
                "type": "textarea",
                "span": "span 2",
                "ph": "Ex.: serviços de portaria — competência 08/2026",
            },
        ],
    }

    # 5) Fechamento de comissões ──────────────────────────────────────────────────────────
    grupos = (
        await db.execute(
            text(
                "SELECT x.seller, x.nome, x.m, x.n, x.tot, (SELECT f.id FROM fin_comissoes_fechamentos f WHERE f.seller_id = CAST(x.seller AS uuid) AND f.competencia = x.m) AS fech "
                "  FROM (SELECT c.seller_id::text AS seller, coalesce(u.name, u.email, c.seller_id::text) AS nome, "
                "               to_char(coalesce(c.period_start, c.trigger_date, c.due_date, c.created_at::date),'YYYY-MM') AS m, "
                "               count(*) AS n, round(sum(c.final_commission)::numeric,2) AS tot "
                "          FROM commissions c LEFT JOIN users u ON u.id = c.seller_id "
                "         WHERE coalesce(c.is_active,true) AND c.status IN ('pending','approved') "
                "           AND NOT EXISTS (SELECT 1 FROM commission_payments p WHERE p.commission_id = c.id) "
                "         GROUP BY 1, 2, 3) x ORDER BY x.m DESC, x.nome"
            )
        )
    ).fetchall()
    fechados = (
        await db.execute(
            text(
                "SELECT f.id, f.competencia, coalesce(u.name, u.email, f.seller_id::text), f.qtd, f.total, f.fechado_por, f.fechado_em, "
                "       (SELECT count(*) FROM commission_payments p JOIN commissions c ON c.id=p.commission_id WHERE c.seller_id=f.seller_id AND p.payment_reference='FECH-'||f.competencia AND p.is_confirmed) "
                "  FROM fin_comissoes_fechamentos f LEFT JOIN users u ON u.id = f.seller_id ORDER BY f.fechado_em DESC LIMIT 60"
            )
        )
    ).fetchall()
    regra = (
        await db.execute(
            text(
                "SELECT name, commission_type, base_value FROM commission_rules WHERE coalesce(is_active,true) ORDER BY priority DESC NULLS LAST LIMIT 1"
            )
        )
    ).first()
    mine["comissoes-fechamento"] = {
        "title": "Fechamento de comissões",
        "sub": (
            f"Régua vigente: {regra[0]} ({regra[2]:g}{'%' if regra[1] == 'percentage' else ' R$'}) · "
            if regra
            else "Sem régua ativa em commission_rules · "
        )
        + "Em aberto = comissão sem pagamento lançado. Fechar cria o pagamento (a confirmar) e marca «aprovada». Confirmar/pagar segue no CRM e no caminho do dinheiro.",
        "cta": "Fechar período",
        "ctaTo": "comissoes-fechar",
        "type": "table",
        "searchHint": "Buscar vendedor…",
        "filterCol": 1,
        "filterLabel": "Competência",
        "grid": "1.6fr 0.8fr 0.6fr 1fr 1fr",
        "cols": ["Vendedor", "Competência", "Qtd", "Total aberto", "Situação"],
        "rows": [
            {
                "cells": [
                    t(g[1][:40], 600, _ND),
                    t(_br(g[2])),
                    t(str(g[3])),
                    t(brl(g[4]), 600),
                    b(f"fechado #{g[5]}", "ok") if g[5] else b("aberto", "warn"),
                ]
            }
            for g in grupos
        ]
        or [{"cells": [t("Nenhuma comissão em aberto", 500, "#94A3B8"), t("—"), t("—"), t("—"), b("—", "mut")]}],
        "panelGrid": "1fr",
        "panels": [
            {
                "title": "Fechamentos feitos (demonstrativo em PDF na aba «Fechar período»)",
                "rows": [
                    {
                        "left": f"#{f[0]} · {_br(f[1])} · {f[2][:30]} · {f[3]} comissão(ões) · por {f[5] or '—'} em {f[6].strftime('%d/%m/%Y') if f[6] else '—'}",
                        "right": f"{brl(f[4])} · {f[7]}/{f[3]} confirmadas",
                        **S["ok" if f[7] == f[3] else "info"],
                    }
                    for f in fechados
                ]
                or [{"left": "Nenhum fechamento ainda", "right": "0", **S["mut"]}],
            }
        ],
    }
    mine["comissoes-fechar"] = {
        "title": "Fechar período de comissões",
        "sub": "Escolha vendedor + competência com comissões em aberto. Cria um pagamento por comissão (não confirmado) e o demonstrativo em PDF. Não paga ninguém.",
        "cta": "Fechar período",
        "type": "form",
        "submit": {
            "endpoint": f"{_ACT}comissoes-fechar",
            "okMsg": "Período fechado — abrindo o demonstrativo.",
            "gated": True,
            "showResult": True,
            "confirm": "Fechar marca as comissões como aprovadas e lança o pagamento a confirmar. Não dá para fechar duas vezes o mesmo período.",
        },
        "fields": [
            {
                "key": "alvo",
                "label": "Vendedor · competência*",
                "type": "select",
                "span": "span 2",
                "options": [{"value": "", "label": "— escolha —"}]
                + [
                    {
                        "value": f"{g[0]}|{g[2]}",
                        "label": f"{g[1][:36]} · {_br(g[2])} · {g[3]} comissão(ões) · {brl(g[4])}",
                    }
                    for g in grupos
                    if not g[5]
                ],
            }
        ],
        "docs": [
            doc(
                f"Demonstrativo #{f[0]} — {_br(f[1])} · {f[2][:24]}",
                f"/api/v1/redesign/comissoes-fechamento/{f[0]}/pdf",
                fmt="pdf",
            )
            for f in fechados[:12]
        ],
    }

    # 6) Orçado × realizado por centro (categoria do extrato) ──────────────────────────────
    linhas = await orcado_realizado(db)
    centros = sorted({x["centro"] for x in linhas})
    n_orc = sum(1 for x in linhas if x["orcado"] is not None)
    mine["orcamento-vs-realizado"] = {
        "title": "Análise orçamentária — orçado × realizado por centro",
        "sub": f"Centro = categoria das saídas classificadas no extrato (a que a casa usa de fato; fin_cost_centers está vazia). {len(linhas)} linhas · {n_orc} com orçamento. "
        "Lance o orçado em «Lançar orçamento» para a comparação acender.",
        "cta": "Lançar orçamento",
        "ctaTo": "orcamento-centro-novo",
        "type": "table",
        "searchHint": "Buscar centro…",
        "filterCol": 1,
        "filterLabel": "Mês",
        "grid": "1.4fr 0.7fr 1fr 1fr 1fr 0.7fr 0.8fr",
        "cols": ["Centro", "Mês", "Orçado", "Realizado", "Desvio", "Desvio %", "Situação"],
        "rows": [
            {
                "cells": [
                    t(x["centro"][:36], 600, _ND),
                    t(_br(x["mes"])),
                    t(
                        brl(x["orcado"]) if x["orcado"] is not None else "—",
                        600,
                        "#334155" if x["orcado"] is not None else "#94A3B8",
                    ),
                    t(brl(x["realizado"]), 600),
                    t(brl(x["desvio"]) if x["desvio"] is not None else "—"),
                    t(f"{x['desvio_pct']:+.1f}%" if x["desvio_pct"] is not None else "—"),
                    b("sem orçamento", "mut")
                    if x["orcado"] is None
                    else (b("dentro", "ok") if x["desvio"] >= 0 else b("estourou", "bad")),
                ]
            }
            for x in linhas
        ]
        or [
            {
                "cells": [
                    t("Sem saídas classificadas nem orçamento", 500, "#94A3B8"),
                    t("—"),
                    t("—"),
                    t("—"),
                    t("—"),
                    t("—"),
                    b("—", "mut"),
                ]
            }
        ],
    }
    mine["orcamento-centro-novo"] = {
        "title": "Lançar orçamento por centro e mês",
        "sub": "Grava em financial_orcamentos (chave cc:<centro>:<AAAA-MM>). Lançar de novo substitui.",
        "cta": "Salvar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}orcamento-centro-salvar", "okMsg": "Orçamento salvo."},
        "fields": [
            {
                "key": "centro",
                "label": "Centro (categoria)*",
                "type": "select",
                "span": "span 1",
                "options": [{"value": c, "label": c} for c in centros]
                or [{"value": "", "label": "— sem categorias no extrato —"}],
            },
            {
                "key": "competencia",
                "label": "Competência (MM/AAAA)*",
                "type": "text",
                "span": "span 1",
                "value": comp_atual,
            },
            {"key": "valor", "label": "Orçado (R$)*", "type": "text", "span": "span 1", "ph": "0,00"},
        ],
    }

    # 7) Pensionistas ─────────────────────────────────────────────────────────────────────
    pens = (await db.execute(text(_SQL_PENSOES))).fetchall()
    sem = [r for r in pens if r[7] is None]
    mine["pensionistas"] = {
        "title": "Pensionistas — desconto em folha × quem recebe",
        "sub": f"{len(pens)} desconto(s) de pensão ativo(s) no DP · {len(sem)} SEM beneficiário cadastrado (não dá para pagar). Cadastre o pensionista aqui; o desconto nasce em DP › Descontos.",
        "cta": "Cadastrar pensionista",
        "ctaTo": "pensionista-novo",
        "type": "table",
        "searchHint": "Buscar colaborador ou pensionista…",
        "grid": "1.6fr 1.2fr 0.8fr 1.4fr 1.4fr 1fr",
        "cols": ["Colaborador (descontado)", "Desconto", "Valor", "Pensionista", "Chave PIX", "Situação"],
        "rows": [
            {
                "cells": [
                    t(r[2][:36], 600, _ND),
                    t(r[3][:30]),
                    t(brl(r[4]) if r[4] else (f"{float(r[5]):.1f}%" if r[5] else "—"), 600),
                    t((r[8] or "—")[:30]),
                    t((r[9] or "—")[:28]),
                    b("sem beneficiário — não paga", "bad") if r[7] is None else b("pronto para pagar", "ok"),
                ]
            }
            for r in pens
        ]
        or [
            {
                "cells": [
                    t("Nenhum desconto de pensão ativo no DP", 500, "#94A3B8"),
                    t("—"),
                    t("—"),
                    t("—"),
                    t("—"),
                    b("—", "mut"),
                ]
            }
        ],
        "panelGrid": "1fr",
        "panels": [
            {
                "title": "Pendências",
                "rows": [
                    {"left": f"{r[2]} — desconto sem pensionista cadastrado", "right": "cadastrar", **S["bad"]}
                    for r in sem
                ]
                or [{"left": "Todo desconto de pensão tem beneficiário", "right": "0", **S["ok"]}],
            }
        ],
    }
    emps = (
        await db.execute(text("SELECT id::text, nome FROM employees WHERE status='ativo' ORDER BY nome"))
    ).fetchall()
    mine["pensionista-novo"] = {
        "title": "Cadastrar pensionista",
        "sub": "Beneficiário de pagamento (tipo pensionista) vinculado ao colaborador de quem a pensão é descontada.",
        "cta": "Cadastrar",
        "type": "form",
        "submit": {"endpoint": f"{_ACT}pensionista-salvar", "okMsg": "Pensionista cadastrado."},
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador (de quem é descontado)*",
                "type": "select",
                "span": "span 2",
                "options": [{"value": "", "label": "— escolha —"}] + [{"value": e[0], "label": e[1]} for e in emps],
            },
            {"key": "nome", "label": "Nome do pensionista*", "type": "text", "span": "span 1"},
            {"key": "cpf", "label": "CPF*", "type": "text", "span": "span 1"},
            {"key": "chave_pix", "label": "Chave PIX*", "type": "text", "span": "span 1"},
            {
                "key": "tipo_chave",
                "label": "Tipo da chave*",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": v, "label": l}
                    for v, l in (
                        ("cpf", "CPF"),
                        ("email", "E-mail"),
                        ("telefone", "Telefone"),
                        ("aleatoria", "Aleatória"),
                    )
                ],
            },
        ],
    }
    out.update(mine)
    return mine


# ── ações ───────────────────────────────────────────────────────────────────────────────────
@router.post("/action/condicao-pagamento-salvar", dependencies=_GATE)
async def rd_condicao_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    cid = str(payload.get("id") or "").strip()
    if cid and "ativo" in payload and "nome" not in payload:  # inativar/reativar
        await db.execute(
            text("UPDATE fin_condicoes_pagamento SET ativo = :a WHERE id = :i"),
            {"a": str(payload["ativo"]) == "1", "i": int(cid)},
        )
        await db.commit()
        return {"ok": True, "message": "Condição atualizada."}
    nome = str(payload.get("nome") or "").strip()
    if len(nome) < 2:
        raise HTTPException(status_code=400, detail="Nome obrigatório.")
    try:
        dias = sorted({int(x) for x in re.split(r"[,\s/;]+", str(payload.get("dias") or "").strip()) if x != ""})
    except ValueError:
        raise HTTPException(status_code=400, detail="Dias: números separados por vírgula (ex.: 30,60).")
    if not dias or any(d < 0 or d > 730 for d in dias):
        raise HTTPException(status_code=400, detail="Dias: ao menos um prazo entre 0 e 730.")
    ent = _dec(payload.get("entrada_percentual") or "0", "Entrada", minimo=None)
    if ent < 0 or ent >= 100:
        raise HTTPException(status_code=400, detail="Entrada: 0 a 99%.")
    p = {"n": nome, "p": len(dias), "d": json.dumps(dias), "e": ent}
    if cid:
        await db.execute(
            text(
                "UPDATE fin_condicoes_pagamento SET nome=:n, parcelas=:p, dias=CAST(:d AS jsonb), entrada_percentual=:e WHERE id=:i"
            ),
            {**p, "i": int(cid)},
        )
    else:
        await db.execute(
            text(
                "INSERT INTO fin_condicoes_pagamento (nome, parcelas, dias, entrada_percentual) VALUES (:n, :p, CAST(:d AS jsonb), :e) ON CONFLICT (nome) DO UPDATE SET parcelas=EXCLUDED.parcelas, dias=EXCLUDED.dias, entrada_percentual=EXCLUDED.entrada_percentual, ativo=true"
            ),
            p,
        )
    await db.commit()
    return {
        "ok": True,
        "message": f"Condição «{nome}» salva ({len(dias)} parcela(s): {'/'.join(map(str, dias))} dias).",
    }


async def _conta_com_condicao(db, current_user, payload: dict, tipo: str) -> dict:
    """Registrar conta a pagar/receber com condição: N parcelas pelos MESMOS serviços da tela original."""
    await _ensure(db)
    desc = str(payload.get("description") or "").strip()
    if len(desc) < 3:
        raise HTTPException(status_code=400, detail="Descrição (mínimo 3 caracteres).")
    valor = _dec(payload.get("valor"), "Valor")
    base = _date(payload.get("due_date"), "Vencimento")
    cond = None
    if str(payload.get("condicao_id") or "").strip():
        cond = (
            await db.execute(
                text("SELECT nome, dias, entrada_percentual FROM fin_condicoes_pagamento WHERE id=:i AND ativo"),
                {"i": int(payload["condicao_id"])},
            )
        ).first()
        if not cond:
            raise HTTPException(status_code=400, detail="Condição de pagamento inexistente ou inativa.")
    dias = list(cond[1]) if cond else [0]
    vencs = vencimentos(dias, base)
    vals = parcelas(valor, len(dias), Decimal(str(cond[2] or 0)) if cond else Decimal("0"))
    notas = str(payload.get("notes") or "").strip() or None
    cond_emp = UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    ids = []
    if tipo == "pagar":
        from modules.financial.schemas.payable import PayableAccountCreate
        from modules.financial.services.payable_service import PayableService

        svc = PayableService(db)
        for i, (v, d) in enumerate(zip(vals, vencs, strict=True), start=1):
            c = await svc.create_account(
                PayableAccountCreate(
                    condominio_id=cond_emp,
                    description=desc if len(vals) == 1 else f"{desc} ({i}/{len(vals)})",
                    gross_value=v,
                    due_date=d,
                    supplier_name=(str(payload.get("supplier_name") or "").strip() or None),
                    notes=notas,
                    total_installments=len(vals),
                ),
                current_user.id,
            )
            ids.append(str(c.id))
    else:
        from modules.financial.schemas.receivable import ReceivableAccountCreate
        from modules.financial.services.receivable_service import ReceivableService

        svc = ReceivableService(db)
        for i, (v, d) in enumerate(zip(vals, vencs, strict=True), start=1):
            c = await svc.create_account(
                ReceivableAccountCreate(
                    condominio_id=cond_emp,
                    description=desc if len(vals) == 1 else f"{desc} ({i}/{len(vals)})",
                    gross_value=v,
                    due_date=d,
                    customer_name=(str(payload.get("customer_name") or "").strip() or None),
                    notes=notas,
                    total_installments=len(vals),
                ),
                current_user.id,
            )
            ids.append(str(c.id))
    det = " · ".join(f"{d.strftime('%d/%m')} {brl(v)}" for v, d in zip(vals, vencs, strict=True))
    return {
        "ok": True,
        "ids": ids,
        "message": f"{len(ids)} título(s) registrado(s)"
        + (f" pela condição «{cond[0]}»" if cond else "")
        + f": {det}."
        + (" Não paga — pagamento é com OTP." if tipo == "pagar" else ""),
    }


@router.post("/action/payable-condicao", dependencies=_GATE)
async def rd_payable_condicao(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    return await _conta_com_condicao(db, current_user, payload, "pagar")


@router.post("/action/receivable-condicao", dependencies=_GATE)
async def rd_receivable_condicao(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    return await _conta_com_condicao(db, current_user, payload, "receber")


@router.post("/action/conta-fixa-salvar", dependencies=_GATE)
async def rd_conta_fixa_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    desc = str(payload.get("descricao") or "").strip()
    if len(desc) < 3:
        raise HTTPException(status_code=400, detail="Descrição obrigatória.")
    valor = _dec(payload.get("valor"), "Valor")
    try:
        dia = int(payload.get("dia_vencimento") or 0)
        pt = int(payload["parcelas_total"]) if str(payload.get("parcelas_total") or "").strip() else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Dia e parcelas devem ser números.")
    if not 1 <= dia <= 31:
        raise HTTPException(status_code=400, detail="Dia do vencimento: 1 a 31.")
    await db.execute(
        text(
            "INSERT INTO financial_custos_recorrentes (categoria, descricao, valor, dia_vencimento, parcelas_total, parcelas_pagas, ativo, favorecido, created_by) "
            "VALUES (:c, :d, :v, :dia, :pt, 0, true, :f, :u)"
        ),
        {
            "c": str(payload.get("categoria") or "fixo").strip()[:40],
            "d": desc,
            "v": valor,
            "dia": dia,
            "pt": pt,
            "f": str(payload.get("favorecido") or "").strip() or None,
            "u": getattr(current_user, "email", None) or str(current_user.id),
        },
    )
    await db.commit()
    return {
        "ok": True,
        "message": f"Conta fixa «{desc}» cadastrada — {brl(valor)} todo dia {dia}. Gere o título do mês em «Gerar títulos do mês».",
    }


@router.post("/action/conta-fixa-encerrar", dependencies=_GATE)
async def rd_conta_fixa_encerrar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    try:
        cid = int(payload.get("id") or 0)
    except ValueError:
        raise HTTPException(status_code=400, detail="id inválido.")
    n = (
        await db.execute(
            text(
                "UPDATE financial_custos_recorrentes SET encerrado_em = CURRENT_DATE, ativo = false WHERE id=:i AND encerrado_em IS NULL RETURNING id"
            ),
            {"i": cid},
        )
    ).scalar()
    await db.commit()
    if not n:
        raise HTTPException(status_code=404, detail="Conta fixa não encontrada ou já encerrada.")
    return {"ok": True, "message": "Conta fixa encerrada. Títulos já gerados continuam em Contas a Pagar."}


@router.post("/action/contas-fixas-gerar", dependencies=_GATE)
async def rd_contas_fixas_gerar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    from modules.financial.services.contas_fixas import gerar_titulos_do_mes

    await _ensure(db)
    comp = _comp(payload.get("competencia"))
    r = await gerar_titulos_do_mes(db, comp, current_user.id)
    return {
        "ok": True,
        **r,
        "message": f"{_br(comp)}: {r['criados']} título(s) criado(s), {r['pulados']} já existia(m) ou completo(s). Nada foi pago.",
    }


@router.post("/action/codigo-servico-salvar", dependencies=_GATE)
async def rd_codigo_servico_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    from modules.government_integrations.core.nfse_nacional import ctribnac_de_lc116

    await _ensure(db)
    item = str(payload.get("item_lc116") or "").strip()
    try:
        ctrib = ctribnac_de_lc116(item)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    desc = str(payload.get("descricao") or "").strip()
    if len(desc) < 3:
        raise HTTPException(status_code=400, detail="Descrição obrigatória.")
    aliq = (
        _dec(payload.get("aliquota_iss"), "Alíquota", minimo=None)
        if str(payload.get("aliquota_iss") or "").strip()
        else None
    )
    if aliq is not None and not 0 <= aliq <= 10:
        raise HTTPException(status_code=400, detail="Alíquota ISS: 0 a 10%.")
    p = {
        "i": item,
        "c": ctrib,
        "d": desc,
        "a": aliq,
        "m": str(payload.get("codigo_municipal") or "").strip() or None,
        "n": str(payload.get("cnae") or "").strip() or None,
    }
    if str(payload.get("id") or "").strip():
        await db.execute(
            text(
                "UPDATE fin_codigos_servico SET item_lc116=:i, ctribnac=:c, descricao=:d, aliquota_iss=:a, codigo_municipal=:m, cnae=:n WHERE id=:id"
            ),
            {**p, "id": int(payload["id"])},
        )
    else:
        await db.execute(
            text(
                "INSERT INTO fin_codigos_servico (item_lc116, ctribnac, descricao, aliquota_iss, codigo_municipal, cnae) VALUES (:i, :c, :d, :a, :m, :n) "
                "ON CONFLICT (item_lc116) DO UPDATE SET descricao=EXCLUDED.descricao, aliquota_iss=EXCLUDED.aliquota_iss, codigo_municipal=EXCLUDED.codigo_municipal, cnae=EXCLUDED.cnae, ativo=true"
            ),
            p,
        )
    await db.commit()
    return {"ok": True, "message": f"Código {item} (cTribNac {ctrib}) salvo."}


@router.post("/action/cfop-salvar", dependencies=_GATE)
async def rd_cfop_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    cod = str(payload.get("codigo") or "").strip()
    if not re.fullmatch(r"[1-7]\d{3}", cod):
        raise HTTPException(status_code=400, detail="CFOP: 4 dígitos começando por 1–7.")
    desc = str(payload.get("descricao") or "").strip()
    if len(desc) < 3:
        raise HTTPException(status_code=400, detail="Natureza da operação obrigatória.")
    tipo = "entrada" if cod[0] in "123" else "saida"
    n = (
        await db.execute(
            text(
                "INSERT INTO cfops (id, codigo, descricao, descricao_resumida, tipo, grupo, natureza, active, created_at, updated_at) "
                "SELECT gen_random_uuid(), CAST(:c AS varchar), CAST(:d AS text), left(CAST(:d AS varchar), 100), CAST(:t AS varchar), CAST(:g AS varchar), 'outras', true, now(), now() "
                "WHERE NOT EXISTS (SELECT 1 FROM cfops WHERE codigo=CAST(:c AS varchar)) RETURNING id"
            ),
            {"c": cod, "d": desc, "t": tipo, "g": cod[0]},
        )
    ).scalar()
    await db.commit()
    if not n:
        raise HTTPException(status_code=400, detail=f"CFOP {cod} já existe.")
    return {"ok": True, "message": f"CFOP {cod} criado."}


@router.post("/action/recibo-pdf", dependencies=_GATE)
async def rd_recibo_pdf(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Emite o recibo (número sequencial) atrás do gate OTP humano — documento com fé em nome da empresa."""
    from modules.operacional.controllers.redesign_write_gate import GateError, OTPRequired, money_gov

    await _ensure(db)
    valor = _dec(payload.get("valor"), "Valor")
    if not (str(payload.get("cliente_id") or "").strip() or len(str(payload.get("cliente_nome") or "").strip()) >= 2):
        raise HTTPException(status_code=400, detail="Escolha o cliente ou digite o nome.")
    if len(str(payload.get("referente_a") or "").strip()) < 3:
        raise HTTPException(status_code=400, detail="«Referente a» obrigatório.")
    ref = (
        str(payload.get("_gate_ref") or "").strip()
        or f"recibo:{current_user.id}:{datetime.now().strftime('%Y%m%d%H%M%S')}"
    )
    por = getattr(current_user, "email", None) or str(current_user.id)

    async def _emitir():
        n = await emitir_recibo(db, payload, por)
        return {
            "ok": True,
            "numero": n,
            "message": f"Recibo nº {n:05d} emitido — {brl(valor)}.",
            "doc": {
                "label": f"Recibo {n:05d}",
                "url": f"/api/v1/redesign/recibo/{n}/pdf",
                "fmt": "pdf",
                "mode": "blob",
            },
        }

    try:
        return await money_gov(
            db,
            ref=ref,
            amount=None,
            otp_code=(payload.get("otp_code") or "").strip() or None,
            real_dispatch=_emitir,
            label="recibo de venda",
            dest=str(payload.get("cliente_nome") or payload.get("cliente_id") or ""),
        )
    except OTPRequired as e:
        return {"otp_required": True, "ref": e.ref, "message": f"Recibo de {brl(valor)} preparado. {e.message}"}
    except GateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/recibo/{numero}/pdf", summary="Recibo de venda (PDF padrão-ouro)")
async def rd_recibo_pdf_get(numero: int, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import Response

    from modules.crm.services.doc_pdf import build_recibo_pdf
    from modules.crm.services.pdf_branding import EMPRESA_PATRIMONIAL

    r = (
        await db.execute(
            text(
                "SELECT numero, cliente_nome, cliente_documento, valor, referente_a, data, forma_pagamento FROM fin_recibos WHERE numero=:n"
            ),
            {"n": numero},
        )
    ).first()
    if not r:
        raise HTTPException(status_code=404, detail="Recibo não encontrado.")
    pdf = build_recibo_pdf(
        {
            "numero": f"{r[0]:05d}",
            "pagador": r[1],
            "documento": r[2],
            "valor": float(r[3]),
            "referente": f"{r[4]} ({por_extenso(Decimal(str(r[3])))})",
            "data": r[5],
            "forma_pagamento": r[6],
            "empresa": EMPRESA_PATRIMONIAL,
        }
    )
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="recibo-{r[0]:05d}.pdf"'},
    )


@router.post("/action/comissoes-fechar", dependencies=_GATE)
async def rd_comissoes_fechar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    from modules.operacional.controllers.redesign_write_gate import GateError, OTPRequired, money_gov

    await _ensure(db)
    alvo = str(payload.get("alvo") or "").strip()
    if "|" not in alvo:
        raise HTTPException(status_code=400, detail="Escolha vendedor · competência.")
    seller, comp = alvo.split("|", 1)
    try:
        UUID(seller)
    except ValueError:
        raise HTTPException(status_code=400, detail="Vendedor inválido.")
    comp = _comp(comp)
    total = (
        await db.execute(
            text("SELECT coalesce(sum(final_commission),0) FROM (" + _SQL_ABERTAS + ") x"), {"s": seller, "m": comp}
        )
    ).scalar() or 0
    ref = str(payload.get("_gate_ref") or "").strip() or f"comissoes:{seller}:{comp}"
    por = getattr(current_user, "email", None) or str(current_user.id)

    async def _fechar():
        try:
            r = await fechar_comissoes(db, comp, seller, por)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        return {
            "ok": True,
            **r,
            "message": f"Fechamento #{r['id']}: {r['qtd']} comissão(ões), {brl(r['total'])} — aprovadas, pagamento a confirmar.",
            "doc": {
                "label": f"Demonstrativo #{r['id']}",
                "url": f"/api/v1/redesign/comissoes-fechamento/{r['id']}/pdf",
                "fmt": "pdf",
                "mode": "blob",
            },
        }

    try:
        return await money_gov(
            db,
            ref=ref,
            amount=float(total),
            otp_code=(payload.get("otp_code") or "").strip() or None,
            real_dispatch=_fechar,
            label="fechamento de comissões",
            dest=seller,
        )
    except OTPRequired as e:
        return {
            "otp_required": True,
            "ref": e.ref,
            "message": f"Fechamento de {_br(comp)} ({brl(total)}) preparado. {e.message}",
        }
    except GateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/comissoes-fechamento/{fid}/pdf", summary="Demonstrativo de comissões do período (PDF padrão-ouro)")
async def rd_comissoes_pdf_get(fid: int, db: AsyncSession = Depends(get_db)):
    import io

    from fastapi.responses import Response
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from modules.crm.services.pdf_branding import (
        AZUL_ESCURO,
        FONTE,
        FONTE_B,
        FUNDO_CLARO,
        TEXTO,
        header_footer,
        secao,
        styles,
    )

    f = (
        await db.execute(
            text(
                "SELECT f.competencia, coalesce(u.name, u.email, f.seller_id::text), f.qtd, f.total, f.fechado_por, f.fechado_em, f.seller_id::text "
                "  FROM fin_comissoes_fechamentos f LEFT JOIN users u ON u.id=f.seller_id WHERE f.id=:i"
            ),
            {"i": fid},
        )
    ).first()
    if not f:
        raise HTTPException(status_code=404, detail="Fechamento não encontrado.")
    itens = (
        await db.execute(
            text(
                "SELECT c.reference_number, coalesce(c.description,'—'), c.sale_value, c.commission_rate, c.final_commission, p.is_confirmed "
                "  FROM commission_payments p JOIN commissions c ON c.id=p.commission_id "
                " WHERE c.seller_id = CAST(:s AS uuid) AND p.payment_reference = :ref ORDER BY c.reference_number"
            ),
            {"s": f[6], "ref": f"FECH-{f[0]}"},
        )
    ).fetchall()
    st = styles()
    buf = io.BytesIO()
    docp = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=40 * mm,
        bottomMargin=20 * mm,
        title=f"Demonstrativo de comissoes {f[0]}",
    )
    story = [
        Paragraph(
            f"<b>Vendedor:</b> {f[1]} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Competência:</b> {_br(f[0])} &nbsp;&nbsp;|&nbsp;&nbsp; <b>Fechamento nº</b> {fid}",
            st["small"],
        ),
        Paragraph(
            f"Fechado por {f[4] or '—'} em {f[5].strftime('%d/%m/%Y %H:%M') if f[5] else '—'} · emitido em {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            st["small"],
        ),
        Spacer(1, 5 * mm),
    ]
    story += secao("Comissões do período", st)
    linhas = [["#", "Referência", "Descrição", "Venda", "Taxa", "Comissão", "Situação"]]
    for n, i in enumerate(itens, start=1):
        linhas.append(
            [
                str(n),
                i[0] or "—",
                (i[1] or "—")[:44],
                brl(i[2] or 0),
                f"{float(i[3] or 0):g}%",
                brl(i[4] or 0),
                "confirmada" if i[5] else "a confirmar",
            ]
        )
    linhas.append(["", "TOTAL", "", "", "", brl(f[3]), f"{f[2]} comissão(ões)"])
    tb = Table(linhas, colWidths=[8 * mm, 30 * mm, 62 * mm, 24 * mm, 14 * mm, 24 * mm, 22 * mm], repeatRows=1)
    tb.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, 0), FONTE_B),
                ("FONTNAME", (0, 1), (-1, -1), FONTE),
                ("FONTNAME", (0, -1), (-1, -1), FONTE_B),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("BACKGROUND", (0, 0), (-1, 0), AZUL_ESCURO),
                ("TEXTCOLOR", (0, 0), (-1, 0), FUNDO_CLARO),
                ("TEXTCOLOR", (0, 1), (-1, -1), TEXTO),
                ("GRID", (0, 0), (-1, -1), 0.3, AZUL_ESCURO),
                ("ALIGN", (3, 1), (5, -1), "RIGHT"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -2), [None, FUNDO_CLARO]),
                ("BACKGROUND", (0, -1), (-1, -1), FUNDO_CLARO),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story += [
        tb,
        Spacer(1, 6 * mm),
        Paragraph(f"Valor total por extenso: <b>{por_extenso(Decimal(str(f[3])))}</b>.", st["corpo"]),
        Spacer(1, 3 * mm),
        Paragraph(
            "Documento gerado pelo Conecta PRO. «A confirmar» = pagamento lançado no fechamento e ainda não confirmado no caminho do dinheiro. Confidencial.",
            st["small"],
        ),
    ]
    docp.build(
        story,
        onFirstPage=lambda c, d: header_footer(c, d, titulo="DEMONSTRATIVO DE COMISSÕES"),
        onLaterPages=lambda c, d: header_footer(c, d, titulo="DEMONSTRATIVO DE COMISSÕES"),
    )
    return Response(
        content=buf.getvalue(),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="comissoes-{f[0]}-{fid}.pdf"'},
    )


@router.post("/action/orcamento-centro-salvar", dependencies=_GATE)
async def rd_orcamento_centro_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    centro = str(payload.get("centro") or "").strip()
    if not centro or ":" in centro:
        raise HTTPException(status_code=400, detail="Centro obrigatório (sem ':').")
    comp = _comp(payload.get("competencia"))
    valor = _dec(payload.get("valor"), "Orçado", minimo=Decimal("0"))
    await db.execute(
        text(
            "INSERT INTO financial_orcamentos (chave, valor, updated_by, updated_at) VALUES (:k, :v, :u, now()) "
            "ON CONFLICT (chave) DO UPDATE SET valor=EXCLUDED.valor, updated_by=EXCLUDED.updated_by, updated_at=now()"
        ),
        {"k": f"cc:{centro}:{comp}", "v": valor, "u": getattr(current_user, "email", None) or str(current_user.id)},
    )
    await db.commit()
    return {"ok": True, "message": f"Orçado de «{centro}» em {_br(comp)}: {brl(valor)}."}


@router.post("/action/pensionista-salvar", dependencies=_GATE)
async def rd_pensionista_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await _ensure(db)
    try:
        emp = UUID(str(payload.get("employee_id") or ""))
    except ValueError:
        raise HTTPException(status_code=400, detail="Escolha o colaborador.")
    nome = str(payload.get("nome") or "").strip()
    cpf = re.sub(r"\D", "", str(payload.get("cpf") or ""))
    chave = str(payload.get("chave_pix") or "").strip()
    tipo_chave = str(payload.get("tipo_chave") or "").strip()
    if len(nome) < 3 or len(cpf) != 11 or not chave or tipo_chave not in ("cpf", "email", "telefone", "aleatoria"):
        raise HTTPException(
            status_code=400, detail="Nome, CPF (11 dígitos), chave PIX e tipo da chave são obrigatórios."
        )
    try:
        await db.execute(
            text(
                "INSERT INTO financial_beneficiarios (nome, chave_pix, tipo_chave, cpf_cnpj, categoria, origem, tipo, employee_id, ativo) "
                "VALUES (:n, :k, :tk, :c, 'pessoa', 'manual', 'pensionista', :e, true)"
            ),
            {"n": nome, "k": chave, "tk": tipo_chave, "c": cpf, "e": str(emp)},
        )
        await db.commit()
    except Exception as e:  # noqa: BLE001 — chave PIX é única (uq_benef_chave)
        await db.rollback()
        if "uq_benef_chave" in str(e):
            raise HTTPException(status_code=400, detail="Esta chave PIX já está cadastrada em outro beneficiário.")
        raise
    return {"ok": True, "message": f"Pensionista «{nome}» cadastrado e vinculado ao colaborador."}
