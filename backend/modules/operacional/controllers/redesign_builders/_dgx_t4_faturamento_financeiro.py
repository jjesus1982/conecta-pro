"""DGX T4 — Faturamento/Financeiro: o que o DGX faz e aqui faltava (passagem de 24/09/2026).

Cavado antes de construir (sandbox = cópia de produção de 23/09; lista em
`docs/dgx/lacunas/faturamento_financeiro.md`):
  · Cobrança por e-mail a vencer/vencidos: o DGX manda sozinho pelos parâmetros `CRDiasAVencerEmailAuto`
    e `CRDiasVencidosEmailAuto`. Aqui a régua (`regua_cobranca_service`) entrega texto pronto para o
    humano, o beat cria rascunho na Central, `core.mailer.send_email` existe — e os parâmetros
    `financeiro.cobranca_dias_a_vencer_email` / `_vencidos_email` (F4) estavam semeados sem leitor.
    Esta tela LÊ os dois, lista quem está na janela e manda o e-mail **por clique** (regra da casa:
    comunicação a cliente real é gate humano; o clique é o gate). Automático fica para o dono (§7).
  · OFX: `_parse_ofx` vivia em `bank_transaction_controller.py` (90 linhas, 0 rotas) e o card da
    conciliação dizia «backend pronto (via API) — UI próxima». Aqui ganha rota + tela; a linha entra em
    `bank_transactions` com `external_id = ofx:banco:conta:fitid` (índice único parcial já existente
    — o mesmo que protege o Inter) e depois passa pelo `conciliar_todas` de sempre.
  · Fluxo de caixa por DIA: o DGX tem calendário; o front daqui não tem tipo calendário → tabela por
    dia com saldo projetado (bancos + recebíveis − pagáveis em aberto até o dia).
  · Comissões → conta a pagar: a F11 fecha o período (`commission_payments` + `approved`) e parou aí.
    «Conta gerada» do DGX = registrar o pagável (registrar a obrigação ≠ pagar — mesmo princípio do
    beat `registrar_obrigacoes`), pelo `PayableService.create_account` da tela «Registrar conta».
  · Recebível proporcional por dias vive em `receivable_contract_service.valor_proporcional` (paralelo
    cego: parâmetro vazio = valor cheio).

Prefixo `_` = o discovery pula; `financeiro.py` inclui `router` e chama `telas(db, out)` antes de
`montar_grupos` (abas em `_fin_grupos.GRUPOS`). DDL idempotente em `_ensure`.
"""

from __future__ import annotations

import calendar
import json
import re
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, require_permission
from core.database import get_db

#: ANTES do import do data_controller (o ciclo de import fecha com o router pronto — como F1/F11).
router = APIRouter()

from modules.operacional.controllers.redesign_data_controller import (  # noqa: E402
    S,
    _helpers,
    b,
    brl,
    t,
)

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_GATE = [Depends(require_permission("module:financeiro"))]
P_AV, P_VE = "financeiro.cobranca_dias_a_vencer_email", "financeiro.cobranca_dias_vencidos_email"
_ABERTO_REC = "('paga','cancelada','recebida')"
_ABERTO_PAG = "('pago','cancelado','cancelled','cancelada','baixada')"

IDS = ("cobranca-email", "importar-ofx", "fluxo-caixa-agenda", "comissoes-conta-gerada")

_DDL = [
    "ALTER TABLE fin_comissoes_fechamentos ADD COLUMN IF NOT EXISTS payable_id uuid",
]


async def _ensure(db: AsyncSession) -> None:
    for sql in _DDL:
        try:
            await db.execute(text(sql))
        except Exception:  # noqa: BLE001 — a tabela da F11 nasce no 1º acesso dela; aqui só a coluna
            await db.rollback()
    await db.commit()


def _br(d) -> str:
    return d.strftime("%d/%m/%Y") if d else "—"


# ── 1) Cobrança por e-mail ─────────────────────────────────────────────────────────────────


async def candidatos_cobranca(db: AsyncSession, hoje: date | None = None) -> list[dict]:
    """Recebíveis em aberto na janela dos parâmetros: vence em até N dias (a vencer) ou venceu há M+ dias.
    Parâmetro vazio = aquele estágio desligado. E-mail vem de `clients` pelo CNPJ (só dígitos)."""
    from core.parametros import param

    hoje = hoje or date.today()
    n_av = await param(db, P_AV, default=None)
    n_ve = await param(db, P_VE, default=None)
    n_av = int(n_av) if n_av not in (None, "") else None
    n_ve = int(n_ve) if n_ve not in (None, "") else None
    if n_av is None and n_ve is None:
        return []
    rows = (
        await db.execute(
            text(
                "WITH p AS (SELECT CAST(:h AS date) h, CAST(:av AS int) av, CAST(:ve AS int) ve) "
                "SELECT r.id::text, coalesce(r.customer_name,'—'), r.net_value, r.due_date, r.due_date - p.h AS delta, "
                "       c.email, coalesce(r.collection_attempts,0), r.last_collection_date, r.boleto_digitable_line, r.pix_copy_paste, "
                "       coalesce(r.description,'') "
                "  FROM receivable_accounts r CROSS JOIN p "
                "  LEFT JOIN clients c ON regexp_replace(coalesce(c.document_number,''),'\\D','','g') = regexp_replace(coalesce(r.customer_document,''),'\\D','','g') "
                "   AND coalesce(r.customer_document,'') <> '' "
                f" WHERE r.status NOT IN {_ABERTO_REC} AND r.due_date IS NOT NULL "
                "   AND ((p.av IS NOT NULL AND r.due_date > p.h AND r.due_date - p.h <= p.av) "
                "     OR (p.ve IS NOT NULL AND p.h - r.due_date >= p.ve)) "
                " ORDER BY r.due_date"
            ),
            {"h": hoje, "av": n_av, "ve": n_ve},
        )
    ).fetchall()
    out = []
    for rid, nome, valor, due, delta, email, tent, ultimo, boleto, pix, desc in rows:
        ultimo_d = ultimo.date() if hasattr(ultimo, "date") and ultimo else ultimo
        out.append(
            {
                "id": rid,
                "cliente": nome,
                "valor": float(valor or 0),
                "vencimento": due,
                "dias": int(delta),
                "estagio": "a_vencer" if delta > 0 else "vencido",
                "email": (email or "").strip() or None,
                "tentativas": int(tent),
                "ultimo": ultimo_d,
                "enviado_hoje": ultimo_d == hoje,
                "boleto": boleto,
                "pix": pix,
                "descricao": desc,
            }
        )
    return out


def montar_email(item: dict) -> tuple[str, str]:
    """Assunto + HTML do lembrete. Texto sóbrio, em PT-BR, com valor, vencimento e o que já existe
    para pagar (linha digitável / PIX copia-e-cola), sem prometer o que não há."""
    valor, venc = brl(item["valor"]), _br(item["vencimento"])
    if item["estagio"] == "a_vencer":
        assunto = f"Conecta Mais — lembrete: fatura de {valor} vence em {venc}"
        abertura = f"Lembramos que a fatura de <b>{valor}</b> vence em <b>{venc}</b>."
    else:
        assunto = f"Conecta Mais — fatura de {valor} vencida em {venc}"
        abertura = f"Identificamos que a fatura de <b>{valor}</b>, vencida em <b>{venc}</b>, ainda consta em aberto."
    pagar = ""
    if item.get("boleto"):
        pagar += f"<p>Linha digitável do boleto:<br><code>{item['boleto']}</code></p>"
    if item.get("pix"):
        pagar += f"<p>PIX copia-e-cola:<br><code>{item['pix']}</code></p>"
    if not pagar:
        pagar = "<p>Se precisar da segunda via ou de outra forma de pagamento, responda este e-mail.</p>"
    html = (
        f"<p>Prezados, {item['cliente']}.</p><p>{abertura}</p>"
        + (f"<p>Referente a: {item['descricao']}</p>" if item.get("descricao") else "")
        + pagar
        + "<p>Se o pagamento já foi feito, desconsidere esta mensagem.</p>"
        "<p>Conecta Mais — Segurança e Tecnologia<br>financeiro@conectamais.pro</p>"
    )
    return assunto, html


async def enviar_cobranca_email(db: AsyncSession, receivable_id: str, quem: str) -> dict:
    """Manda UM lembrete e registra no recebível (tentativa, data, nota). Anti-spam: 1 por dia."""
    from core.mailer import send_email

    item = next((c for c in await candidatos_cobranca(db) if c["id"] == receivable_id), None)
    if not item:
        raise ValueError("Recebível fora da janela de cobrança (ou já pago).")
    if not item["email"]:
        raise ValueError(f"{item['cliente']}: cliente sem e-mail cadastrado.")
    if item["enviado_hoje"]:
        raise ValueError(f"{item['cliente']}: já houve cobrança HOJE (anti-spam).")
    assunto, html = montar_email(item)
    ok = await send_email(item["email"], assunto, html)
    if not ok:
        raise ValueError("SMTP não entregou o e-mail — nada foi registrado.")
    nota = f"[{date.today()}] E-mail de cobrança ({item['estagio'].replace('_', ' ')}, {abs(item['dias'])}d) para {item['email']} por {quem}."
    await db.execute(
        text(
            "UPDATE receivable_accounts SET collection_attempts = coalesce(collection_attempts,0) + 1, last_collection_date = now(), "
            "collection_notes = coalesce(collection_notes,'') || ' | ' || :n, updated_at = now() WHERE id::text = :id"
        ),
        {"n": nota, "id": receivable_id},
    )
    await db.commit()
    return {"ok": True, "cliente": item["cliente"], "email": item["email"], "assunto": assunto}


# ── 2) OFX ─────────────────────────────────────────────────────────────────────────────────


def _cabecalho_ofx(conteudo: str) -> tuple[str, str]:
    bank = re.search(r"<BANKID>\s*([^<\s]+)", conteudo)
    acct = re.search(r"<ACCTID>\s*([^<\s]+)", conteudo)
    return (bank.group(1).strip() if bank else ""), (acct.group(1).strip() if acct else "")


async def importar_ofx(db: AsyncSession, conteudo: str, bank_account_id: str | None, conciliar: bool = True) -> dict:
    """OFX → `bank_transactions`. Idempotente por `external_id` (ofx:banco:conta:fitid — o índice único
    parcial `idx_bank_tx_external_id`). Conta: a informada, senão a que casa BANKID/ACCTID."""
    from modules.financial.controllers.bank_transaction_controller import _parse_ofx

    txs = _parse_ofx(conteudo)
    if not txs:
        raise ValueError("Nenhuma transação encontrada — o arquivo é um OFX válido?")
    bankid, acctid = _cabecalho_ofx(conteudo)
    acc = None
    if bank_account_id:
        acc = (
            await db.execute(
                text("SELECT id::text, name FROM bank_accounts WHERE id::text = :i"), {"i": str(bank_account_id)}
            )
        ).fetchone()
    elif bankid and acctid:
        acc = (
            await db.execute(
                text(
                    "SELECT id::text, name FROM bank_accounts WHERE ativo AND ltrim(coalesce(bank_code,''),'0') = ltrim(:b,'0') "
                    "  AND regexp_replace(coalesce(account_number,'')||coalesce(account_digit,''),'\\D','','g') LIKE regexp_replace(:a,'\\D','','g') || '%' "
                    " ORDER BY is_main_account DESC LIMIT 1"
                ),
                {"b": bankid, "a": acctid},
            )
        ).fetchone()
    if not acc:
        raise ValueError(
            f"Conta bancária não reconhecida (OFX: banco {bankid or '?'} / conta {acctid or '?'}). Escolha a conta no formulário."
        )
    inseridas = 0
    for tx in txs:
        ext = f"ofx:{bankid or 'x'}:{acctid or 'x'}:{tx['fitid']}"
        credito = str(tx["type"]).endswith("credito")
        amt = Decimal(str(tx["amount"]))
        r = await db.execute(
            text(
                "INSERT INTO bank_transactions (id, bank_account_id, transaction_type, category, amount, description, transaction_date, "
                " status, reconciliation_status, imported_from, raw_data, created_at, updated_at, ativo, external_id) "
                "VALUES (gen_random_uuid(), CAST(:acc AS uuid), :tp, 'OFX', :amt, :desc, :dt, 'confirmado', 'pendente', 'ofx', "
                " CAST(:raw AS jsonb), now(), now(), true, :ext) "
                "ON CONFLICT (external_id) WHERE external_id IS NOT NULL DO NOTHING"
            ),
            {
                "acc": acc[0],
                "tp": "credit" if credito else "debit",
                "amt": amt if credito else -amt,
                "desc": (tx.get("description") or "Transação OFX")[:500],
                "dt": tx["date"],
                "raw": json.dumps({"fitid": tx["fitid"], "bankid": bankid, "acctid": acctid, "tipo": str(tx["type"])}),
                "ext": ext,
            },
        )
        inseridas += int(r.rowcount or 0)
    await db.commit()
    concil = None
    if conciliar and inseridas:
        try:
            from starlette.concurrency import run_in_threadpool

            from modules.financial.services.reconciliation_service import conciliar_todas

            concil = await run_in_threadpool(conciliar_todas)
        except Exception as exc:  # noqa: BLE001 — importar entrou; conciliar pode rodar de novo pela aba
            concil = {"erro": str(exc)[:200]}
    return {
        "conta": acc[1],
        "lidas": len(txs),
        "inseridas": inseridas,
        "ja_existiam": len(txs) - inseridas,
        "conciliacao": concil,
    }


# ── 3) Agenda de caixa ─────────────────────────────────────────────────────────────────────


async def agenda_fluxo(db: AsyncSession, ano: int, mes: int) -> list[dict]:
    """Um item por dia do mês com vencimento: entradas (recebíveis), saídas (pagáveis) e saldo projetado
    = saldo dos bancos + Σ recebíveis em aberto até o dia − Σ pagáveis em aberto até o dia (inclui o
    que venceu antes do mês — está em aberto, então pesa no caixa)."""
    primeiro, ultimo = date(ano, mes, 1), date(ano, mes, calendar.monthrange(ano, mes)[1])
    saldo0 = (
        await db.execute(text("SELECT coalesce(sum(current_balance),0) FROM bank_accounts WHERE ativo"))
    ).scalar() or 0
    antes = (
        await db.execute(
            text(
                f"SELECT coalesce((SELECT sum(net_value) FROM receivable_accounts WHERE due_date < :p AND status NOT IN {_ABERTO_REC}),0), "
                f"       coalesce((SELECT sum(net_value) FROM payable_accounts WHERE due_date < :p AND status NOT IN {_ABERTO_PAG}),0), "
                f"       (SELECT count(*) FROM receivable_accounts WHERE due_date < :p AND status NOT IN {_ABERTO_REC}), "
                f"       (SELECT count(*) FROM payable_accounts WHERE due_date < :p AND status NOT IN {_ABERTO_PAG})"
            ),
            {"p": primeiro},
        )
    ).fetchone()
    rows = (
        await db.execute(
            text(
                "SELECT d, sum(e), sum(s), sum(ne), sum(ns), string_agg(quem, ' · ') FROM ("
                f"  SELECT due_date d, net_value e, 0 s, 1 ne, 0 ns, left(coalesce(customer_name,description),28) quem FROM receivable_accounts WHERE due_date BETWEEN :p AND :u AND status NOT IN {_ABERTO_REC}"
                "  UNION ALL "
                f"  SELECT due_date, 0, net_value, 0, 1, left(coalesce(description,''),28) FROM payable_accounts WHERE due_date BETWEEN :p AND :u AND status NOT IN {_ABERTO_PAG}"
                ") x GROUP BY d ORDER BY d"
            ),
            {"p": primeiro, "u": ultimo},
        )
    ).fetchall()
    saldo = Decimal(str(saldo0)) + Decimal(str(antes[0])) - Decimal(str(antes[1]))
    out = [
        {
            "dia": None,
            "rotulo": f"Em aberto antes de {primeiro.strftime('%m/%Y')} (atrasados)",
            "entradas": float(antes[0]),
            "saidas": float(antes[1]),
            "n_rec": int(antes[2]),
            "n_pag": int(antes[3]),
            "saldo": float(saldo),
            "quem": "",
        }
    ]
    for d, e, s, ne, ns, quem in rows:
        saldo += Decimal(str(e or 0)) - Decimal(str(s or 0))
        out.append(
            {
                "dia": d,
                "rotulo": _br(d),
                "entradas": float(e or 0),
                "saidas": float(s or 0),
                "n_rec": int(ne or 0),
                "n_pag": int(ns or 0),
                "saldo": float(saldo),
                "quem": quem or "",
            }
        )
    return out


# ── 4) Comissões → conta a pagar ───────────────────────────────────────────────────────────


async def gerar_conta_comissoes(db: AsyncSession, fechamento_id: int, user_id) -> dict:
    """«Conta gerada» do DGX: o fechamento aprovado (F11) vira UM pagável, pelo mesmo serviço da tela
    «Registrar conta». Idempotente por `fin_comissoes_fechamentos.payable_id`."""
    from modules.financial.schemas.payable import PayableAccountCreate
    from modules.financial.services.contas_fixas import COND_EMPRESA
    from modules.financial.services.payable_service import PayableService

    await _ensure(db)
    f = (
        await db.execute(
            text(
                "SELECT f.competencia, f.total, f.qtd, f.payable_id::text, coalesce(u.name, u.email, f.seller_id::text) "
                "  FROM fin_comissoes_fechamentos f LEFT JOIN users u ON u.id = f.seller_id WHERE f.id = :i"
            ),
            {"i": fechamento_id},
        )
    ).fetchone()
    if not f:
        raise ValueError(f"Fechamento #{fechamento_id} não existe.")
    comp, total, qtd, payable_id, vendedor = f
    if payable_id:
        raise ValueError(f"Fechamento #{fechamento_id} já gerou a conta a pagar ({payable_id[:8]}…).")
    if not total or Decimal(str(total)) <= 0:
        raise ValueError("Fechamento sem valor — nada a registrar.")
    ano, mes = int(comp[:4]), int(comp[5:7])
    venc = date(ano, mes, calendar.monthrange(ano, mes)[1])
    if venc < date.today():
        venc = date.today()
    conta = await PayableService(db).create_account(
        PayableAccountCreate(
            condominio_id=COND_EMPRESA,
            description=f"Comissões {mes:02d}/{ano} — {vendedor}"[:500],
            gross_value=Decimal(str(total)),
            due_date=venc,
            competence_date=date(ano, mes, 1),
            supplier_name=str(vendedor)[:200],
            notes=f"Fechamento de comissões #{fechamento_id} ({qtd} comissão(ões)) — gerado pela tela «Comissões → conta a pagar». Não pago.",
        ),
        user_id,
    )
    pid = str(getattr(conta, "id", None) or (conta.get("id") if isinstance(conta, dict) else ""))
    await db.execute(
        text("UPDATE fin_comissoes_fechamentos SET payable_id = CAST(:p AS uuid) WHERE id = :i"),
        {"p": pid, "i": fechamento_id},
    )
    await db.commit()
    return {"payable_id": pid, "valor": float(total), "vencimento": venc.isoformat(), "vendedor": vendedor}


# ── telas ──────────────────────────────────────────────────────────────────────────────────


async def telas(db, out: dict | None = None) -> dict:
    await _ensure(db)
    mine, safe, tbl = _helpers(db)
    out = out if out is not None else {}
    hoje = date.today()

    # 1) Cobrança por e-mail
    from core.parametros import param

    n_av = await param(db, P_AV, default=None)
    n_ve = await param(db, P_VE, default=None)
    try:
        cands = await candidatos_cobranca(db, hoje)
    except Exception:  # noqa: BLE001
        await db.rollback()
        cands = []
    sem_email = sum(1 for c in cands if not c["email"])
    rows = []
    for c in cands:
        sit = (
            b(f"vence em {c['dias']}d", "warn") if c["estagio"] == "a_vencer" else b(f"vencido há {-c['dias']}d", "bad")
        )
        row = {
            "cells": [
                t(c["cliente"][:40], 600, _ND),
                t(brl(c["valor"]), 600),
                t(_br(c["vencimento"])),
                sit,
                t(c["email"] or "sem e-mail", 500, "#B91C1C" if not c["email"] else "#334155"),
                t(f"{c['tentativas']}× · {_br(c['ultimo'])}" + (" · hoje" if c["enviado_hoje"] else "")),
            ]
        }
        if c["email"] and not c["enviado_hoje"]:
            row["actions"] = [
                {
                    "title": f"Enviar lembrete a {c['cliente'][:30]}",
                    "sub": f"E-mail para {c['email']} · {brl(c['valor'])} · venc. {_br(c['vencimento'])}. Registra a tentativa no recebível.",
                    "endpoint": f"{_ACT}cobranca-email-enviar",
                    "method": "POST",
                    "btnLabel": "Enviar e-mail",
                    "btnStyle": "outline",
                    "submitLabel": "Enviar agora",
                    "confirm": f"Enviar o e-mail de cobrança para {c['email']}? Vai chegar no cliente.",
                    "okMsg": "E-mail enviado e registrado. Recarregue.",
                    "fields": [{"key": "id", "label": "id", "type": "text", "value": c["id"], "span": "span 1"}],
                }
            ]
        rows.append(row)
    ligado = n_av not in (None, "") or n_ve not in (None, "")
    mine["cobranca-email"] = {
        "title": "Cobrança por e-mail (a vencer / vencidos)",
        "sub": (
            f"{len(cands)} recebível(is) na janela — a vencer até {n_av or '—'} dia(s), vencidos há {n_ve or '—'}+ dia(s) "
            "(Configurações › Parâmetros). O envio é por clique, um por cliente por dia; nada sai sozinho."
            if ligado
            else "Parâmetros vazios: defina «Cobrança: dias antes do vencimento» e «dias após vencido» em Configurações › Parâmetros para esta tela listar alguém."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar cliente…",
        "grid": "1.8fr 1fr 0.9fr 1fr 1.6fr 1.2fr",
        "cols": ["Cliente", "Valor", "Vencimento", "Situação", "E-mail", "Tentativas · último"],
        "rows": rows
        or [{"cells": [t("Ninguém na janela de cobrança hoje", 500), t("—"), t("—"), t("—"), t("—"), t("—")]}],
        "panelGrid": "1fr 1fr",
        "panels": [
            {
                "title": "Parâmetros lidos (F4)",
                "rows": [
                    {
                        "left": "Dias antes do vencimento",
                        "right": str(n_av) if n_av not in (None, "") else "vazio",
                        **(S["ok"] if n_av not in (None, "") else S["mut"]),
                    },
                    {
                        "left": "Dias após vencido",
                        "right": str(n_ve) if n_ve not in (None, "") else "vazio",
                        **(S["ok"] if n_ve not in (None, "") else S["mut"]),
                    },
                    {"left": "Envio automático", "right": "Desligado — decisão do dono", **S["info"]},
                ],
            },
            {
                "title": "Hoje",
                "rows": [
                    {
                        "left": "A vencer",
                        "right": str(sum(1 for c in cands if c["estagio"] == "a_vencer")),
                        **S["warn"],
                    },
                    {"left": "Vencidos", "right": str(sum(1 for c in cands if c["estagio"] == "vencido")), **S["bad"]},
                    {"left": "Sem e-mail no cadastro", "right": str(sem_email), **(S["bad"] if sem_email else S["ok"])},
                ],
            },
        ],
    }

    # 2) Importar OFX
    contas = (
        await db.execute(
            text(
                "SELECT id::text, coalesce(name,bank_name,'—'), coalesce(bank_code,''), coalesce(account_number,'') FROM bank_accounts WHERE ativo ORDER BY is_main_account DESC, name"
            )
        )
    ).fetchall()
    n_ofx = (await db.execute(text("SELECT count(*) FROM bank_transactions WHERE imported_from='ofx'"))).scalar() or 0
    mine["importar-ofx"] = {
        "title": "Importar extrato OFX",
        "sub": (
            f"Banco sem API (Asaas, ou qualquer outro): baixe o OFX no internet banking e suba aqui. A linha entra no extrato uma vez só "
            f"(mesmo arquivo duas vezes não duplica) e passa pela conciliação automática. {n_ofx} linha(s) já vieram de OFX."
        ),
        "cta": "Importar",
        "type": "form",
        "submit": {
            "endpoint": f"{_ACT}importar-ofx",
            "multipart": True,
            "confirm": "Importar as transações deste OFX para o extrato? Não move dinheiro — só registra.",
            "okMsg": "OFX importado.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "arquivo",
                "label": "Arquivo OFX*",
                "type": "file",
                "accept": ".ofx,.OFX,.qfx,text/plain",
                "span": "span 2",
            },
            {
                "key": "bank_account_id",
                "label": "Conta bancária",
                "type": "select",
                "span": "span 2",
                "options": [{"value": "", "label": "— reconhecer pelo BANKID/ACCTID do arquivo —"}]
                + [{"value": c[0], "label": f"{c[1]} · {c[2]}/{c[3]}".strip(" ·/")} for c in contas],
            },
        ],
    }

    # 3) Agenda de caixa (mês atual + próximo; seletor do topo filtra por mês)
    rows = []
    for ano, mes in ((hoje.year, hoje.month), (hoje.year + (hoje.month == 12), hoje.month % 12 + 1)):
        try:
            ag = await agenda_fluxo(db, ano, mes)
        except Exception:  # noqa: BLE001
            await db.rollback()
            ag = []
        for a in ag:
            tone = "bad" if a["saldo"] < 0 else ("warn" if a["dia"] is None and (a["n_rec"] or a["n_pag"]) else "ok")
            rows.append(
                {
                    "cells": [
                        t(a["rotulo"], 600, _ND),
                        t(brl(a["entradas"]) if a["entradas"] else "—", 500, "#16A34A") if True else t("—"),
                        t(brl(a["saidas"]) if a["saidas"] else "—", 500, "#B91C1C"),
                        b(brl(a["saldo"]), tone),
                        t(f"{a['n_rec']} rec · {a['n_pag']} pag" + (f" · {a['quem'][:60]}" if a["quem"] else "")),
                    ],
                    "filtro": f"{mes:02d}/{ano}",
                }
            )
    saldo0 = (
        await db.execute(text("SELECT coalesce(sum(current_balance),0) FROM bank_accounts WHERE ativo"))
    ).scalar() or 0
    mine["fluxo-caixa-agenda"] = {
        "title": "Agenda de caixa — vencimentos por dia",
        "sub": (
            f"Saldo projetado dia a dia: bancos hoje ({brl(saldo0)}) + o que há a receber − o que há a pagar, em aberto, até cada data. "
            "Primeira linha = o que já venceu e está em aberto. Escolha o mês no seletor."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar dia ou cliente…",
        "grid": "1.4fr 1fr 1fr 1.1fr 2fr",
        "cols": ["Dia", "Entradas", "Saídas", "Saldo projetado", "Títulos"],
        "rows": rows or [{"cells": [t("Nenhum vencimento em aberto", 500), t("—"), t("—"), t("—"), t("—")]}],
    }

    # 4) Comissões → conta a pagar
    await safe(
        "comissoes-conta-gerada",
        tbl(
            "Comissões — fechamentos e a conta a pagar",
            "Cada período fechado (aba «Fechamento de comissões») vira UMA conta a pagar aqui. Registrar ≠ pagar: o pagamento segue pela fila de aprovação e ordens.",
            "—",
            ["Competência", "Vendedor", "Comissões", "Total", "Fechado em", "Conta a pagar"],
            "0.9fr 1.6fr 0.8fr 1fr 1fr 1.3fr",
            "SELECT f.id, f.competencia, coalesce(u.name,u.email,f.seller_id::text), f.qtd, f.total, f.fechado_em, f.payable_id::text, "
            "       (SELECT status FROM payable_accounts p WHERE p.id = f.payable_id) "
            "  FROM fin_comissoes_fechamentos f LEFT JOIN users u ON u.id = f.seller_id ORDER BY f.competencia DESC, f.id DESC LIMIT 200",
            lambda r: [
                t(f"{r[1][5:7]}/{r[1][:4]}", 600, _ND),
                t((r[2] or "—")[:40]),
                t(str(r[3])),
                t(brl(r[4]), 600),
                t(_br(r[5])),
                b(f"gerada · {(r[7] or '—')}", "ok") if r[6] else b("não gerada", "warn"),
            ],
            actionsfn=lambda r: (
                [
                    {
                        "title": f"Gerar conta a pagar — {r[1][5:7]}/{r[1][:4]} · {(r[2] or '')[:30]}",
                        "sub": f"Registra um pagável de {brl(r[4])} ({r[3]} comissão(ões)). Não paga ninguém.",
                        "endpoint": f"{_ACT}comissoes-gerar-conta",
                        "method": "POST",
                        "btnLabel": "Gerar conta",
                        "btnStyle": "outline",
                        "submitLabel": "Gerar",
                        "confirm": f"Registrar a conta a pagar de {brl(r[4])} para este fechamento?",
                        "okMsg": "Conta a pagar registrada. Recarregue.",
                        "fields": [{"key": "id", "label": "id", "type": "text", "value": str(r[0]), "span": "span 1"}],
                    }
                ]
                if not r[6]
                else None
            ),
        ),
    )
    if "comissoes-conta-gerada" not in mine:
        mine["comissoes-conta-gerada"] = {
            "title": "Comissões — fechamentos e a conta a pagar",
            "sub": "Nenhum período fechado ainda (aba «Fechamento de comissões»).",
            "cta": "—",
            "type": "table",
            "grid": "1fr",
            "cols": ["—"],
            "rows": [{"cells": [t("Sem fechamentos", 500)]}],
        }

    for k in IDS:
        if k in mine:
            out[k] = mine[k]
    return out


# ── ações ──────────────────────────────────────────────────────────────────────────────────


@router.post("/action/cobranca-email-enviar", dependencies=_GATE)
async def rd_cobranca_email_enviar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    rid = str(payload.get("id") or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="id do recebível obrigatório.")
    quem = getattr(current_user, "email", None) or str(current_user.id)
    try:
        r = await enviar_cobranca_email(db, rid, quem)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"ok": True, **r, "message": f"E-mail «{r['assunto']}» enviado para {r['email']} e registrado no recebível."}


@router.post("/action/importar-ofx", dependencies=_GATE)
async def rd_importar_ofx(
    current_user: CurrentActiveUser,
    arquivo: UploadFile = File(...),
    bank_account_id: str | None = Form(None),
    db: AsyncSession = Depends(get_db),
) -> dict:
    raw = await arquivo.read()
    if len(raw) > 5_000_000:
        raise HTTPException(status_code=400, detail="OFX acima de 5 MB.")
    conteudo = (
        raw.decode("utf-8", errors="ignore")
        if b"<OFX>" in raw or b"OFXHEADER" in raw
        else raw.decode("latin-1", errors="ignore")
    )
    try:
        r = await importar_ofx(db, conteudo, (bank_account_id or "").strip() or None)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    c = r.get("conciliacao") or {}
    msg = f"{r['conta']}: {r['lidas']} lida(s), {r['inseridas']} nova(s), {r['ja_existiam']} já existia(m)."
    if isinstance(c, dict) and c and "erro" not in c:
        msg += f" Conciliação automática rodou ({c.get('conciliadas', c.get('total', '—'))})."
    return {"ok": True, **r, "message": msg}


@router.post("/action/comissoes-gerar-conta", dependencies=_GATE)
async def rd_comissoes_gerar_conta(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        fid = int(str(payload.get("id") or "0"))
    except ValueError as e:
        raise HTTPException(status_code=400, detail="id inválido.") from e
    uid = current_user.id if isinstance(current_user.id, UUID) else UUID(str(current_user.id))
    try:
        r = await gerar_conta_comissoes(db, fid, uid)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {
        "ok": True,
        **r,
        "message": f"Conta a pagar de {brl(r['valor'])} registrada para {r['vendedor']} (venc. {_br(datetime.fromisoformat(r['vencimento']))}). Nada foi pago.",
    }
