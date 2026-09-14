"""
redesign_builders/financeiro.py — T4 (cluster financeiro/comercial).
Sobrescreve o _build_financeiro do monólito: reusa a base (dashboard, contas a
pagar/receber, clientes, fornecedores, diaristas, Inter, formulários) e ADICIONA
as ~21 telas que faltavam, todas lendo o DADO REAL do clássico.

Regra de ouro: dinheiro que SAI e transmissão legal = GATED (só visibilidade).
Nunca fabricar dado — vazio real = tabela honesta "aguardando dado".
Ver auditoria/parity/DIVISAO_3T.md + BRIEFING_T4.md.
"""
from datetime import date as _date, timedelta as _timedelta
import re
from fastapi import APIRouter, Body, Depends, HTTPException  # noqa: F401
from sqlalchemy import text  # noqa: F401

from core.auth.dependencies import CurrentActiveUser  # noqa: F401
from core.database import get_db  # noqa: F401
from modules.operacional.controllers.redesign_data_controller import (  # noqa: F401
    S,
    _build_financeiro as _base,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    doc,
    initials,
    t,
)


def _brl_norm(s) -> str:
    """Normaliza dinheiro DIGITADO em formulário para string numérica ("1920.50").
    Aceita "1.920,50", "1920,50", "1920.50", "R$ 1.920,50" e "1920". O antigo
    `.replace(".", "").replace(",", ".")` tratava TODO ponto como milhar: "1920.50"
    virava 192050 — o simulador de preço do CRM devolveu R$ 476 mil por posto
    (medido 07/09/2026 pelo navegador)."""
    s = str(s or "").replace("R$", "").replace(" ", "").strip()
    if "," in s:
        return s.replace(".", "").replace(",", ".")
    if s.count(".") == 1 and 1 <= len(s.split(".")[1]) <= 2:
        return s
    return s.replace(".", "")

SLUG = "financeiro"

# F0: menu extra ZERADO — as antigas entradas viram ABAS dos 7 grupos (_fin_grupos.py).
# As telas continuam montadas no build; só saem da navegação de topo.
EXTRA_MENU: list[dict] = [
    # VAZIO de propósito. Estes 18 itens ficavam SOLTOS na barra lateral, abaixo dos
    # grupos, com os rótulos cortados pela largura ("Consultor CFO — com an…",
    # "Registrar saída de esto…"). Somados aos 10 grupos davam 28 entradas, e foi
    # exatamente disso que o Jordan reclamou: "tem tantos botões que confunde".
    # Cada um virou ABA do grupo a que pertence, em `_fin_grupos.py` — perguntar ao CFO
    # é Visão Geral, justificar transação é Bancos, calcular preço é Custos.
    # ⚠️ Há TRÊS fontes de menu por módulo (o JSON do frontend, o EXTRA_MENU do
    # redesign_data_controller e este). Zerar uma só deixa o item reaparecendo.
]


async def _fetch_live_balance(bank_code, bank_name):
    """Saldo REAL do banco ao vivo (READ-only=visibilidade, NÃO move dinheiro).
    Timeout curto + tudo em try/except → nunca trava/derruba a tela; falhou → None
    (a tela cai pro cache com a data). Inter=OAuth2+mTLS; Cora=mTLS."""
    import asyncio
    nome = (bank_name or "").lower()
    try:
        if bank_code == "077" or "inter" in nome:
            from modules.integrations.inter.client import InterClient
            async with InterClient() as cli:
                s = await asyncio.wait_for(cli.consultar_saldo(), timeout=5)
            return float(getattr(s, "total", None) or getattr(s, "available", 0) or 0)
        if bank_code == "403" or "cora" in nome:
            from modules.integrations.banking.adapters.cora import CoraAdapter
            ad = CoraAdapter()
            if not await asyncio.wait_for(ad.authenticate(), timeout=5):
                return None
            s = await asyncio.wait_for(ad.get_balance(), timeout=5)
            return float(getattr(s, "total", None) or getattr(s, "available", 0) or 0)
    except Exception:  # noqa: BLE001 — qualquer falha → cai pro cache
        return None
    return None



def _acao_pagar_dia(r, resumo: dict | None = None, ja_vistos: set | None = None) -> dict:
    """Botão de pagar o LOTE do dia — UMA vez por data, não em toda linha.

    O clássico resolvia isto numa tela só: o Jordan via quem o Gonzaga lançou, o valor, e
    pagava ali mesmo. No redesign virou SETE abas, e esta lista mandava "abra 'Pagar
    diaristas' e informe a DATA da linha" — ou seja, ler a data, trocar de aba e digitar.
    É onde ele se perdeu, e com razão: informação numa tela e ação noutra é o operador
    fazendo de ponte.

    ⚠️ UMA vez por data, e o rótulo carrega a CONTAGEM e o TOTAL. Na primeira versão o
    botão saía em TODAS as 44 linhas: 44 botões idênticos se leem como "pagar esta
    pessoa", e o Jordan disse exatamente isso — "quero pagar em lote, não individualmente
    cada um". A ação sempre foi em lote; a aparência é que mentia. Botão que promete pagar
    um e paga dezesseis é pior que botão nenhum — mesmo avisando no modal.

    ⚠️ Sem PIX não paga. Linha `sem_pix` não ganha botão: o lote a ignoraria de qualquer
    forma, e oferecer a ação prometeria o que não acontece.

    ⚠️ O banco NÃO vem escolhido — mesma regra do boleto: de onde o dinheiro sai é
    decisão, não preenchimento automático. Clicar não paga: abre o gate com OTP.
    """
    if r[4] == "sem_pix" or not r[0]:
        return {}
    dia = r[0].isoformat() if hasattr(r[0], "isoformat") else str(r[0])
    if ja_vistos is not None:
        if dia in ja_vistos:
            return {}                    # o dia já tem seu botão, na primeira linha dele
        ja_vistos.add(dia)
    ag = (resumo or {}).get(dia) or {}
    n, tot = ag.get("n", 0), ag.get("total", 0.0)
    rotulo = ("Pagar este dia" if not n
              else f"Pagar 1 do dia · {brl(tot)}" if n == 1
              else f"Pagar os {n} do dia · {brl(tot)}")
    return {"actions": [{
        "title": (f"Pagar EM LOTE {n} lançamento(s) de {_fmtdate(r[0])} — {brl(tot)}"),
        "sub": ("Dinheiro que SAI, com OTP. Paga TODO o lote desta data — VT/VR e diária "
                "da mesma data saem juntos, não só esta linha. Confira a conta: Cora é a "
                "Patrimonial, Inter é a Eletrônica."),
        "endpoint": "/api/v1/redesign/action/pagar-diaristas",
        "method": "POST", "btnLabel": rotulo, "submitLabel": "Preparar e gerar OTP",
        "btnStyle": "primary", "gated": True,
        "okMsg": "Lote preparado. Confira o OTP no e-mail para liberar.",
        "fields": [
            {"key": "data", "label": "Data do lote", "type": "date", "value": dia},
            {"key": "origem", "label": "Pagar pela conta*", "type": "select", "value": "",
             "options": [{"value": "", "label": "— escolha —"},
                         {"value": "cora", "label": "Cora (Patrimonial)"},
                         {"value": "inter", "label": "Inter (Eletrônica)"}]},
        ]}]}



async def _build_saldos(db):
    """Saldos por conta — lê SÓ o cache (bank_accounts): rápido e seguro. NÃO faz
    chamada ao banco aqui: I/O externo no render bloqueava/derrubava o worker
    (502 no módulo inteiro, aprendido 21/07). A frescura vem do sync agendado
    (celery `financial.sync_bank_balances`, a cada 15 min); a coluna 'Atualizado'
    mostra o quão fresco está — sem carimbo recente, o saldo é sinalizado."""
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    rows = (await db.execute(text(
        "SELECT name, bank_name, current_balance, last_balance_update "
        "FROM bank_accounts WHERE ativo IS NOT FALSE "
        "AND (bank_code IN ('077','403') OR bank_name ILIKE '%inter%' OR bank_name ILIKE '%cora%') "
        "ORDER BY is_main_account DESC NULLS LAST, name"))).fetchall()
    cells = []
    for name, bank_name, bal, upd in rows:
        upd_utc = upd.replace(tzinfo=timezone.utc) if (upd and upd.tzinfo is None) else upd
        if upd_utc is None:
            status, tone = "Nunca sincronizado", "bad"
        else:
            age_min = (now - upd_utc).total_seconds() / 60
            if age_min < 90:
                status, tone = "Atualizado", "ok"
            elif age_min < 60 * 26:
                status, tone = "Recente", "info"
            else:
                status, tone = "Desatualizado", "warn"
        cells.append({"cells": [
            t(name or "—", 600, "#0F1B3A"), t(bank_name or "—"),
            t(brl(bal) if bal is not None else "aguardando dado", 600, "#0F1B3A" if bal is not None else "#64748B"),
            t(_fmtdate(upd, "%d/%m %H:%M") if upd else "nunca"),
            b(status, tone),
        ]})
    # Teto do dia (o que o app do banco mostra como limite): consumido vem da MESMA
    # função que o InterPaymentService usa p/ barrar pagamento (get_limite_diario_consumido),
    # teto do MESMO env do serviço. Só banco/env — sem I/O externo aqui (regra acima).
    import os as _os
    try:
        _teto = float(_os.getenv("CONECTA_LIMITE_DIARIO_PAGAMENTOS", "5000.00"))
        _consumido = float(await _scalar(db, "SELECT get_limite_diario_consumido()") or 0)
    except Exception:  # noqa: BLE001 — sem a função/env, a tela não quebra
        _teto, _consumido = None, None
    _painel_limite = []
    if _teto is not None:
        _disp = max(_teto - _consumido, 0)
        _painel_limite = [{"title": "Limite de pagamento de hoje", "rows": [
            {"left": "Teto diário", "right": brl(_teto), **S["mut"]},
            {"left": "Já usado hoje", "right": brl(_consumido), **S["warn" if _consumido else "mut"]},
            {"left": "Ainda disponível hoje", "right": brl(_disp), **S["ok" if _disp > 0 else "bad"]}]}]
    return {"title": "Saldos por conta",
            "sub": "Inter e Cora — saldo do último sync (a cada 15 min); a data mostra o quão fresco está",
            "cta": "—", "type": "table", "searchHint": "Buscar…",
            "grid": "1.6fr 1.2fr 1.1fr 1.1fr 0.9fr",
            "cols": ["Conta", "Banco", "Saldo", "Atualizado", "Status"], "rows": cells,
            **({"panels": _painel_limite} if _painel_limite else {})}


def _mes_br(comp) -> str:
    """'2026-07' -> '07/2026' (o filtro de mês da tabela usa este texto)."""
    s = str(comp or "")
    return f"{s[5:7]}/{s[0:4]}" if len(s) >= 7 and "-" in s else (s or "—")


def _simnao(v) -> dict:
    return b("Sim", "info") if v else b("—", "mut")


def _cnpj(v) -> str:
    d = "".join(ch for ch in (v or "") if ch.isdigit())
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return v or "—"


def _kpi_valor(nome, valor, unidade, atualizado) -> dict:
    """KPI sem timestamp de cálculo = nunca recalculado → mostra 'não calculado'
    em vez de deixar um placeholder velho se passar por métrica real. Só honra o
    valor quando há prova de que foi computado/sincronizado (atualizado != NULL)."""
    if atualizado is None:
        return b("não calculado", "mut")
    if (unidade or "") == "R$":
        return t(brl(valor), 600)
    return t(f"{float(valor):g}" if valor is not None else "—", 600)


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)
    # Base do monólito (10 telas já provadas) — reusa sem duplicar.
    out.update(await _base(db))

    # cta → formulário-alvo: o botão do topo abre o form de criação (antes era decorativo).
    # A ModuleView navega para scr.ctaTo; onde não há form, o botão some (honesto).
    for _tbl_id, _form_id in [("contas-pagar", "registrar-conta-pagar"),
                              ("contas-receber", "registrar-conta-receber")]:
        if isinstance(out.get(_tbl_id), dict) and _form_id in out:
            out[_tbl_id]["ctaTo"] = _form_id

    # ---- Fidelidade dashboard: o clássico exibe Faturamento Bruto/Líquido/ISS Retido/Ticket
    # Janela a partir de HOJE, não do max() da tabela: ancorar na última nota faz o KPI
    # congelar no dia em que a emissão parar, com o rótulo ainda dizendo '12 meses'.
    #      Médio (NFS-e 12m). Trago como painel ADITIVO — mantém os KPIs de caixa do redesign. ----
    try:
        _fat = (await db.execute(text(
            "SELECT coalesce(sum(valor_servicos),0), coalesce(sum(valor_liquido),0), coalesce(sum(iss_valor),0), count(*) "
            "FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false "
            "AND data_emissao >= CURRENT_DATE - interval '12 months'"))).fetchone()
        _bruto, _liq, _iss, _n = float(_fat[0] or 0), float(_fat[1] or 0), float(_fat[2] or 0), (_fat[3] or 0)
        # Faturamento por Cliente (12m) — o clássico exibe; dado real de nfse
        _porcli = (await db.execute(text(
            "SELECT coalesce(tomador_nome,'—'), sum(valor_servicos) FROM nfse_emitidas_nacional "
            "WHERE coalesce(cancelada,false)=false AND data_emissao >= CURRENT_DATE - interval '12 months' "
            "GROUP BY tomador_nome ORDER BY sum(valor_servicos) DESC LIMIT 6"))).fetchall()
        _dash = out.get("dashboard")
        if isinstance(_dash, dict) and _dash.get("type") == "dash":
            _dash["panelGrid"] = "1fr 1fr"
            _dash.setdefault("panels", []).append({
                "title": "Faturamento NFS-e (12m)", "rows": [
                    {"left": "Faturamento Bruto", "right": brl(_bruto), **S["info"]},
                    {"left": "Faturamento Líquido", "right": brl(_liq), **S["ok"]},
                    {"left": "ISS Retido", "right": brl(_iss), **S["warn"]},
                    {"left": "Ticket Médio", "right": brl(_bruto / _n if _n else 0), **S["mut"]},
                ]})
            _dash["panels"].append({
                "title": "Faturamento por Cliente (12m)",
                "rows": [{"left": (nm or "—")[:32], "right": brl(v), **S["info"]} for nm, v in _porcli]
                or [{"left": "Sem NFS-e", "right": "—", **S["mut"]}]})
    except Exception:  # noqa: BLE001 — enriquecimento nunca quebra o dashboard
        await db.rollback()

    # ---- Clientes / Fornecedores (override: + CNPJ, que o clássico mostra) ----
    await safe("clientes", tbl(
        "Clientes", f"{await _scalar(db, 'SELECT count(*) FROM clients')} clientes", "Novo cliente",
        ["Cliente", "CNPJ", "Segmento", "MRR", "Status"], "2fr 1.3fr 1.2fr 1fr 0.9fr",
        "SELECT name, coalesce(document_number,'—'), coalesce(segment::text,'—'), coalesce(mrr,0), status::text "
        "FROM clients ORDER BY mrr DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(_cnpj(r[1])), t((r[2] or '—').capitalize()),
                   t(brl(r[3]), 600), b("Ativo", "ok") if r[4] == "active" else b((r[4] or '—').capitalize(), "mut")]))
    await safe("fornecedores", tbl(
        "Fornecedores", f"{await _scalar(db, 'SELECT count(*) FROM suppliers')} fornecedores", "Novo fornecedor",
        ["Fornecedor", "CNPJ", "Categoria", "Cidade", "Status"], "2fr 1.3fr 1.2fr 1fr 0.9fr",
        "SELECT name, coalesce(cpf_cnpj,'—'), coalesce(category,'—'), coalesce(address_city,'—'), status "
        "FROM suppliers ORDER BY name LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(_cnpj(r[1])), t(r[2]), t(r[3]),
                   b("Ativo", "ok") if (r[4] or '').lower() in ("active", "ativo") else b(r[4] or '—', "mut")]))

    # ---- Saldos por conta (Inter + Cora ao vivo, com fonte/data) ----
    await safe("saldos", _build_saldos(db))

    # ---- Pagamentos PJ (folha PJ — VISIBILIDADE; o pagar money-out fica no fluxo gated do clássico) ----
    def _nf(exig, ok):
        if not exig:
            return b("—", "mut")
        return b("NF OK", "ok") if ok else b("NF pendente", "warn")
    _pj_tone = {"pago": "ok", "pendente": "warn", "programado": "info", "sem_pix": "bad", "erro": "bad", "cancelado": "mut"}
    await safe("pagamentos-pj", tbl(
        "Pagamentos PJ", f"{await _scalar(db, 'SELECT count(*) FROM financial_pagamentos_pj')} pagamentos (folha PJ) — visibilidade; o pagamento é sempre com gate OTP humano",
        "—", ["Competência", "Beneficiário", "Empresa", "Valor", "NF", "Status"], "1fr 2fr 1.3fr 1fr 1fr 1fr",
        "SELECT coalesce(competencia,'—'), coalesce(beneficiario,'—'), coalesce(empresa_slug,'—'), valor, coalesce(status,'—'), nf_exigida, nf_ok, id "
        "FROM financial_pagamentos_pj ORDER BY competencia DESC NULLS LAST, valor DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1], 600, "#0F1B3A", initials(r[1])),
                   t((r[2] or '—').replace('_', ' ').title()), t(brl(r[3]), 600),
                   _nf(r[5], r[6]), b((r[4] or '—').replace('_', ' ').capitalize(), _pj_tone.get((r[4] or '').lower(), "info"))],
        actionsfn=lambda r: [{"title": f"Nota fiscal do PJ — {r[1]} {r[0]}", "endpoint": f"/api/v1/financial/pagamentos-pj/item/{r[7]}/nota-fiscal", "method": "POST",
                              "btnLabel": "NF recebida?", "btnStyle": "outline", "submitLabel": "Registrar", "okMsg": "Situação da NF registrada. Recarregue.",
                              "fields": [{"key": "ok", "label": "Nota fiscal recebida e conferida?", "type": "select", "span": "span 2", "value": "true" if r[6] else "false",
                                          "options": [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]}]}] if r[5] else []))

    # ---- Fluxo de caixa (bank_transactions — entradas/saídas reais) ----
    await safe("fluxo-caixa", tbl(
        "Fluxo de caixa", f"{await _scalar(db, 'SELECT count(*) FROM bank_transactions')} lançamentos bancários",
        "—", ["Data", "Tipo", "Descrição", "Valor", "Status"], "1fr 1.1fr 2fr 1fr 1fr",
        "SELECT transaction_date, coalesce(transaction_type,'—'), coalesce(description,memo,'—'), amount, coalesce(status,'—') "
        "FROM bank_transactions ORDER BY transaction_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0])), b((r[1] or '—').replace('_', ' ').capitalize(), "info"),
                   t(r[2]), t(brl(r[3]), 600, "#0F1B3A"), t((r[4] or '—').capitalize())]))

    # ---- Conciliação bancária (inter_conciliacao_folha — folha x extrato Inter) ----
    await safe("conciliacao", tbl(
        "Conciliação bancária", f"{await _scalar(db, 'SELECT count(*) FROM inter_conciliacao_folha')} itens conciliados (folha × Inter)",
        "—", ["Competência", "Líquido", "Prevista", "Paga", "Status"], "1fr 1fr 1fr 1fr 0.9fr",
        "SELECT coalesce(competencia,'—'), valor_liquido, data_prevista, data_paga, coalesce(status,'—') "
        "FROM inter_conciliacao_folha ORDER BY data_prevista DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[1]), 600), t(_fmtdate(r[2])), t(_fmtdate(r[3])),
                   b((r[4] or '—').capitalize(), "ok" if (r[3] is not None) else "warn")]))

    # ---- Boletos (inter_cobrancas — cobranças emitidas via Inter) ----
    await safe("boletos", tbl(
        "Boletos", f"{await _scalar(db, 'SELECT count(*) FROM inter_cobrancas')} cobranças Inter",
        "—", ["Número", "Valor", "Vencimento", "Status", "Descrição"], "1fr 1fr 1fr 0.9fr 2fr",
        "SELECT coalesce(seu_numero,'—'), valor, vencimento, coalesce(status,'—'), coalesce(descricao,'—') "
        "FROM inter_cobrancas ORDER BY vencimento DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[1]), 600), t(_fmtdate(r[2])),
                   b((r[3] or '—').capitalize(), "ok" if (r[3] or '').upper() in ("RECEBIDO", "PAGO") else "warn"), t(r[4])]))

    # ---- Cobranças (receivable_accounts em aberto) ----
    await safe("cobrancas", tbl(
        "Cobranças", "Recebíveis em aberto (pendente/parcial)",
        "—", ["Cliente", "Descrição", "Valor", "Vencimento", "Status"], "1.5fr 2fr 1fr 1fr 0.9fr",
        "SELECT coalesce(customer_name,'—'), coalesce(description,'—'), net_value, due_date, coalesce(status,'—') "
        "FROM receivable_accounts WHERE status IN ('pendente','parcial') ORDER BY due_date NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]), 600), t(_fmtdate(r[3])),
                   b((r[4] or '—').capitalize(), "warn")]))

    # ---- Banking (extrato bancário consolidado com BANCO/contraparte/saldo) ----
    # Mês como 1ª coluna + filterCol → seletor de mês (mesmo mecanismo de Orçamentos).
    # Janela de 12 meses (antes: 200 mais recentes = poucas semanas com 5k+ lançamentos).
    await safe("banking", tbl(
        "Banking", "Extrato bancário consolidado (todas as contas) — 12 meses, filtre por mês",
        "—", ["Mês", "Data", "Banco", "Contraparte", "Descrição", "Valor", "Saldo"], "0.8fr 1fr 1fr 1.4fr 1.8fr 1fr 1fr",
        "SELECT to_char(bt.transaction_date,'MM/YYYY'), bt.transaction_date, coalesce(ba.bank_name,'—'), "
        "coalesce(bt.counterparty_name,bt.contraparte_nome,'—'), "
        "coalesce(bt.description,bt.memo,'—'), bt.amount, bt.balance_after "
        "FROM bank_transactions bt LEFT JOIN bank_accounts ba ON ba.id=bt.bank_account_id "
        "WHERE bt.transaction_date >= date_trunc('month', CURRENT_DATE - interval '11 months') "
        # ponytail: teto alto p/ os 12 meses caberem inteiros (5,2k hoje); truncar
        # silenciosamente sumiria com os meses mais antigos e a tela mentiria.
        "ORDER BY bt.transaction_date DESC NULLS LAST LIMIT 8000",
        lambda r: [t(r[0], 600), t(_fmtdate(r[1])), b(r[2] or '—', "info"), t(r[3], 600, "#0F1B3A"), t(r[4]),
                   t(brl(r[5]), 600), t(brl(r[6]) if r[6] is not None else '—')]))
    if isinstance(out.get("banking"), dict):
        out["banking"]["filterCol"] = 0
        out["banking"]["filterLabel"] = "Mês"
        # Resumo do período (o que o app do banco mostra no topo do extrato).
        _res = (await db.execute(text(
            "SELECT coalesce(sum(amount) FILTER (WHERE amount > 0),0), "
            "coalesce(sum(-amount) FILTER (WHERE amount < 0),0), count(*) "
            "FROM bank_transactions "
            "WHERE transaction_date >= date_trunc('month', CURRENT_DATE - interval '11 months')"))).fetchone()
        _mes = (await db.execute(text(
            "SELECT coalesce(sum(amount) FILTER (WHERE amount > 0),0), "
            "coalesce(sum(-amount) FILTER (WHERE amount < 0),0) FROM bank_transactions "
            "WHERE date_trunc('month', transaction_date) = date_trunc('month', CURRENT_DATE)"))).fetchone()
        if _res:
            _e, _s, _n = float(_res[0] or 0), float(_res[1] or 0), int(_res[2] or 0)
            _me, _ms = (float(_mes[0] or 0), float(_mes[1] or 0)) if _mes else (0.0, 0.0)
            out["banking"]["panelGrid"] = "1fr 1fr"
            out["banking"]["panels"] = [
                {"title": f"Movimento dos 12 meses ({_n} lançamentos)", "rows": [
                    {"left": "Entradas", "right": brl(_e), **S["ok"]},
                    {"left": "Saídas", "right": brl(_s), **S["bad"]},
                    {"left": "Líquido", "right": brl(_e - _s), **S["info" if _e >= _s else "warn"]}]},
                {"title": "Mês corrente", "rows": [
                    {"left": "Entradas", "right": brl(_me), **S["ok"]},
                    {"left": "Saídas", "right": brl(_ms), **S["bad"]},
                    {"left": "Líquido", "right": brl(_me - _ms), **S["info" if _me >= _ms else "warn"]}]},
            ]

    # ---- PIX recebidos (inter_pix_recebidos — entradas PIX, como no app do banco) ----
    _pix_n = await _scalar(db, "SELECT count(*) FROM inter_pix_recebidos") or 0
    await safe("pix-recebidos", tbl(
        "PIX recebidos",
        (f"{_pix_n} PIX recebido(s) sincronizado(s) do Inter" if _pix_n
         else "Nenhum PIX sincronizado ainda — a carga vem do sync do Inter (aguardando dado)"),
        "—", ["Data", "Pagador", "Valor", "txid", "E2E"], "1.1fr 1.8fr 1fr 1.3fr 1.6fr",
        # pagador é jsonb ({} quando o Inter não manda o dador) → extrai nome/CPF, senão '—'.
        "SELECT data_horario, "
        "coalesce(nullif(pagador->>'nome',''), nullif(pagador->>'nomePagador',''), "
        "         nullif(pagador->>'cpf',''), nullif(pagador->>'cnpj',''), '—'), "
        "valor, coalesce(txid,'—'), coalesce(end_to_end_id,'—') "
        "FROM inter_pix_recebidos ORDER BY data_horario DESC NULLS LAST LIMIT 500",
        lambda r: [t(_fmtdate(r[0], "%d/%m/%Y %H:%M") if r[0] else '—'), t(r[1], 600, "#0F1B3A"),
                   t(brl(r[2]), 600, "#16A34A"), t(str(r[3])[:24]), t(str(r[4])[:32])]))
    if isinstance(out.get("pix-recebidos"), dict):
        out["pix-recebidos"]["ctaTo"] = "sincronizar-pix"
        out["pix-recebidos"]["cta"] = "Sincronizar PIX"

    # ---- RENTABILIDADE POR CONTRATO (margem) + RESULTADO POR CNPJ ------------------
    # Receita = NFS-e emitida (bruto = valor do contrato; líquido = o que o condomínio paga
    # após retenções). Custo DIRETO = folha CLT das pessoas alocadas no condomínio (vigência
    # respeitada) + diaristas do posto. Estrutura (PJ do escritório) e fornecedores NÃO entram
    # no contrato — são indiretos, aparecem no resultado do CNPJ (rateio seria arbitrário).
    _DEPARA = (
        "(VALUES ('IDEAL FLORES','CONDOMINIO IDEAL FLORES DA CIDADE'),"
        "('MIRANTE','CONDOMINIO MIRANTE DAS FLORES'),"
        "('LARANJEIRAS','RESIDENCIAL LARANJEIRAS VILLAGE'),('LARANJEIRAS VILLAGE','RESIDENCIAL LARANJEIRAS VILLAGE'),"
        "('VILLA DEI FIORI','CONDOMINIO VILLA DEI FIORI'),('VILA DEI FIORI','CONDOMINIO VILLA DEI FIORI'),"
        "('PRIME ARENA','CONDOMINIO PRIME ARENA'),('PRIME','CONDOMINIO PRIME ARENA'),('PISCINAS','CONDOMINIO PRIME ARENA'),"
        "('VILLA PÁSSAROS','CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS'),"
        "('VILLA DOS PASSAROS','CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS'),"
        "('MICHELANGELO','CONDOMINIO DO EDIFICIO MICHELANGELO'),"
        "('PARISE','CONDOMINIO RESIDENCIAL PARISE VILLAGE'),('PARISE VILLAGE','CONDOMINIO RESIDENCIAL PARISE VILLAGE'),"
        "('GREEN HILLS','CONDOMINIO RESIDENCIAL GREEN HILLS'),"
        "('P. GELAIN','CONDOMINIO PARQUE RESIDENCIAL GELAIN')) AS d(apelido, cliente)"
    )
    _SQL_RENT = """WITH depara(apelido, cliente) AS (VALUES
  ('IDEAL FLORES','CONDOMINIO IDEAL FLORES DA CIDADE'),('MIRANTE','CONDOMINIO MIRANTE DAS FLORES'),
  ('LARANJEIRAS','RESIDENCIAL LARANJEIRAS VILLAGE'),('VILLA DEI FIORI','CONDOMINIO VILLA DEI FIORI'),
  ('PRIME ARENA','CONDOMINIO PRIME ARENA'),('VILLA PÁSSAROS','CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS'),
  ('MICHELANGELO','CONDOMINIO DO EDIFICIO MICHELANGELO'),('PARISE','CONDOMINIO RESIDENCIAL PARISE VILLAGE'),
  ('GREEN HILLS','CONDOMINIO RESIDENCIAL GREEN HILLS'),('P. GELAIN','CONDOMINIO PARQUE RESIDENCIAL GELAIN')),
dep2(apelido, cliente) AS (VALUES
  ('IDEAL FLORES','CONDOMINIO IDEAL FLORES DA CIDADE'),('MIRANTE','CONDOMINIO MIRANTE DAS FLORES'),
  ('LARANJEIRAS','RESIDENCIAL LARANJEIRAS VILLAGE'),('LARANJEIRAS VILLAGE','RESIDENCIAL LARANJEIRAS VILLAGE'),
  ('VILA DEI FIORI','CONDOMINIO VILLA DEI FIORI'),('VILLA DEI FIORI','CONDOMINIO VILLA DEI FIORI'),
  ('PRIME ARENA','CONDOMINIO PRIME ARENA'),('PRIME','CONDOMINIO PRIME ARENA'),('PISCINAS','CONDOMINIO PRIME ARENA'),
  ('VILLA DOS PASSAROS','CONDOMINIO RESIDENCIAL VILLA DOS PASSAROS'),
  ('PARISE VILLAGE','CONDOMINIO RESIDENCIAL PARISE VILLAGE')),
rec AS (SELECT n.competencia AS comp, e.razao_social AS cnpj, n.tomador_nome AS cli,
        sum(n.valor_servicos) AS bruto, sum(n.valor_liquido) AS liq, sum(coalesce(n.inss_retido,0)) AS inss
        FROM nfse_emitidas_nacional n JOIN empresas e ON e.id=n.empresa_id
        WHERE coalesce(n.cancelada,false)=false AND n.competencia>='2026-06' GROUP BY 1,2,3),
clt AS (SELECT to_char(p.competence_start,'YYYY-MM') AS comp, d.cliente AS cli,
        sum(p.total_earnings) AS folha, count(DISTINCT p.employee_id) AS pess
        FROM hr_payslips p JOIN employee_alocacoes a ON a.employee_id=p.employee_id
          AND a.data_inicio <= (date_trunc('month',p.competence_start)+interval '1 month -1 day')::date
          AND (a.data_fim IS NULL OR a.data_fim >= date_trunc('month',p.competence_start)::date)
        JOIN condominios co ON co.id=a.condominio_id JOIN depara d ON d.apelido=upper(co.nome)
        JOIN employees e2 ON e2.id=p.employee_id AND coalesce(e2.is_homologacao,false)=false
        WHERE p.competence_start IS NOT NULL GROUP BY 1,2),
dia AS (SELECT to_char(l.data,'YYYY-MM') AS comp, d.cliente AS cli, sum(l.valor) AS diaristas
        FROM diaria_lancamentos l JOIN dep2 d ON d.apelido=upper(l.posto) GROUP BY 1,2),
vt AS (SELECT competencia AS comp, sum(valor_servicos) AS total FROM nfse_tomadas_nacional
       WHERE prestador_nome ILIKE '%SOLIDES%' AND descricao ILIKE '%Administra%' GROUP BY 1),
hc AS (SELECT comp, sum(pess) AS total_pess FROM clt GROUP BY 1)
SELECT coalesce(r.comp,c.comp,dd.comp) AS comp,
  CASE WHEN r.cnpj ILIKE '%PATRIMONIAL%' THEN 'Patrimonial' WHEN r.cnpj ILIKE '%ELETRONICA%' THEN 'Eletrônica' ELSE '—' END AS cnpj,
  coalesce(r.cli,c.cli,dd.cli) AS contrato,
  round(coalesce(r.liq,0)::numeric,2) AS recebe,
  round((coalesce(c.folha,0)*1.274 + coalesce(c.pess,0)*coalesce(vt.total/nullif(hc.total_pess,0),0) + coalesce(dd.diaristas,0))::numeric,2) AS custo_total,
  round((coalesce(r.liq,0) - coalesce(c.folha,0)*1.274 - coalesce(c.pess,0)*coalesce(vt.total/nullif(hc.total_pess,0),0) - coalesce(dd.diaristas,0))::numeric,2) AS margem_hoje,
  round((coalesce(r.liq,0)+coalesce(r.inss,0) - coalesce(c.folha,0)*1.274 - coalesce(c.pess,0)*coalesce(vt.total/nullif(hc.total_pess,0),0) - coalesce(dd.diaristas,0))::numeric,2) AS margem_liminar
FROM rec r
FULL OUTER JOIN clt c ON c.cli=r.cli AND c.comp=r.comp
FULL OUTER JOIN dia dd ON dd.cli=coalesce(r.cli,c.cli) AND dd.comp=coalesce(r.comp,c.comp)
LEFT JOIN vt ON vt.comp=coalesce(r.comp,c.comp,dd.comp)
LEFT JOIN hc ON hc.comp=coalesce(r.comp,c.comp,dd.comp)
WHERE coalesce(r.comp,c.comp,dd.comp)>='2026-06' ORDER BY 1 DESC, 7 DESC"""

    def _rent_row(r):
        rec = float(r[3] or 0)
        m_hoje = float(r[5] or 0)
        m_lim = float(r[6] or 0)
        pct = (m_hoje / rec * 100) if rec else 0.0
        return [t(_mes_br(r[0]), 600), b(r[1], "info" if r[1] == 'Patrimonial' else "mut"),
                t((r[2] or '—').replace('CONDOMINIO ', '').replace('RESIDENCIAL ', '')[:28], 600, "#0F1B3A"),
                t(brl(rec), 600),
                t(brl(float(r[4] or 0)), 600, "#C2410C"),
                t(brl(m_hoje), 700, "#16A34A" if m_hoje >= 0 else "#DC2626"),
                t(f"{pct:.0f}%" if rec else "—", 600, "#16A34A" if m_hoje >= 0 else "#DC2626"),
                t(brl(m_lim), 700, "#16A34A" if m_lim >= 0 else "#DC2626")]

    await safe("rentabilidade", tbl(
        "Rentabilidade por contrato",
        "Custo TOTAL de pessoal: folha + FGTS 8% + provisão férias+1/3+13º (19,4%) + VT/VR + diaristas. "
        "NÃO inclui DAS (você ainda não tem o 1º mês) nem estrutura/fornecedores (indiretos, ficam no CNPJ). "
        "'Com liminar' = recupera o INSS retido REAL de cada nota. Patrimonial é Simples Anexo III: NÃO paga patronal. "
        "Julho é mês de TRANSIÇÃO e a folha de julho fecha em agosto — até lá julho sai só com diaristas.",
        "—", ["Mês", "CNPJ", "Contrato", "Recebe", "Custo total", "Margem hoje", "%", "Com liminar"],
        "0.8fr 1fr 1.7fr 1.1fr 1.1fr 1.1fr 0.6fr 1.1fr",
        _SQL_RENT, _rent_row))
    if isinstance(out.get("rentabilidade"), dict):
        out["rentabilidade"]["filterCol"] = 0
        out["rentabilidade"]["filterLabel"] = "Mês"

    _SQL_CNPJ = """
WITH meses(comp) AS (SELECT DISTINCT competencia FROM nfse_emitidas_nacional WHERE competencia>='2026-06'),
emp(cnpj) AS (VALUES ('Patrimonial'),('Eletrônica')),
base AS (SELECT m.comp, e.cnpj FROM meses m CROSS JOIN emp e),
rec AS (SELECT n.competencia AS comp,
        CASE WHEN em.razao_social ILIKE '%PATRIMONIAL%' THEN 'Patrimonial' ELSE 'Eletrônica' END AS cnpj,
        sum(n.valor_liquido) AS receita
        FROM nfse_emitidas_nacional n JOIN empresas em ON em.id=n.empresa_id
        WHERE coalesce(n.cancelada,false)=false AND n.competencia>='2026-06' GROUP BY 1,2),
folha AS (SELECT to_char(p.competence_start,'YYYY-MM') AS comp,
        CASE WHEN em.razao_social ILIKE '%PATRIMONIAL%' THEN 'Patrimonial' ELSE 'Eletrônica' END AS cnpj,
        sum(p.total_earnings)*1.274 AS custo
        FROM hr_payslips p LEFT JOIN empresas em ON em.id=p.empresa_id
        JOIN employees e2 ON e2.id=p.employee_id AND coalesce(e2.is_homologacao,false)=false
        WHERE p.competence_start IS NOT NULL GROUP BY 1,2),
vtvr AS (SELECT competencia AS comp, sum(valor_servicos) AS total FROM nfse_tomadas_nacional
        WHERE prestador_nome ILIKE '%SOLIDES%' AND descricao ILIKE '%Administra%' GROUP BY 1),
diar AS (SELECT to_char(data,'YYYY-MM') AS comp, sum(valor) AS total FROM diaria_lancamentos GROUP BY 1),
pj AS (SELECT competencia AS comp,
        CASE WHEN beneficiario ILIKE ANY(ARRAY['%Pyetra%','%Eliziel%','%ORLAILSON%','%Diego%'])
             THEN 'Patrimonial' ELSE 'Eletrônica' END AS cnpj, sum(valor) AS estrutura
        FROM financial_pagamentos_pj GROUP BY 1,2),
forn AS (SELECT nt.competencia AS comp,
        CASE WHEN em.razao_social ILIKE '%PATRIMONIAL%' THEN 'Patrimonial' ELSE 'Eletrônica' END AS cnpj,
        sum(nt.valor_servicos) AS fornecedores
        FROM nfse_tomadas_nacional nt LEFT JOIN empresas em ON em.id=nt.empresa_id
        WHERE nt.competencia>='2026-06' AND NOT (nt.prestador_nome ILIKE '%SOLIDES%' AND nt.descricao ILIKE '%Administra%')
        GROUP BY 1,2)
SELECT b.comp, b.cnpj, coalesce(r.receita,0),
  coalesce(f.custo,0)+CASE WHEN b.cnpj='Patrimonial' THEN coalesce(v.total,0)+coalesce(d.total,0) ELSE 0 END,
  coalesce(pj.estrutura,0), coalesce(fo.fornecedores,0),
  coalesce(r.receita,0)-coalesce(f.custo,0)
    -CASE WHEN b.cnpj='Patrimonial' THEN coalesce(v.total,0)+coalesce(d.total,0) ELSE 0 END
    -coalesce(pj.estrutura,0)-coalesce(fo.fornecedores,0)
FROM base b
LEFT JOIN rec r ON r.comp=b.comp AND r.cnpj=b.cnpj
LEFT JOIN folha f ON f.comp=b.comp AND f.cnpj=b.cnpj
LEFT JOIN vtvr v ON v.comp=b.comp
LEFT JOIN diar d ON d.comp=b.comp
LEFT JOIN pj ON pj.comp=b.comp AND pj.cnpj=b.cnpj
LEFT JOIN forn fo ON fo.comp=b.comp AND fo.cnpj=b.cnpj
ORDER BY b.comp DESC, b.cnpj"""

    def _cnpj_row(r):
        res = float(r[6] or 0)
        return [t(_mes_br(r[0]), 600), b(r[1], "info" if r[1] == 'Patrimonial' else "mut"),
                t(brl(float(r[2] or 0)), 600, "#16A34A"),
                t(brl(float(r[3] or 0)), 600, "#C2410C"),
                t(brl(float(r[4] or 0)), 600, "#C2410C"),
                t(brl(float(r[5] or 0)), 600, "#C2410C"),
                t(brl(res), 700, "#16A34A" if res >= 0 else "#DC2626")]

    await safe("resultado-cnpj", tbl(
        "Resultado por CNPJ",
        "Receita (NFS-e líquida) − custo direto (folha×1,274 + VT/VR + diaristas) − estrutura (PJ do "
        "escritório) − fornecedores. NÃO inclui DAS (1º mês em agosto) nem a receita do Hawk Eye "
        "(entra por depósito no Inter, sem nota nossa). Junho/julho são meses de TRANSIÇÃO: a folha "
        "migrou p/ a Patrimonial em junho mas o faturamento ainda saía pela Eletrônica — por isso o "
        "descasamento. Agosto é o 1º mês limpo.",
        "—", ["Mês", "CNPJ", "Receita", "Custo direto", "Estrutura", "Fornecedores", "Resultado"],
        "0.8fr 1fr 1.2fr 1.2fr 1.1fr 1.2fr 1.2fr",
        _SQL_CNPJ, _cnpj_row))
    if isinstance(out.get("resultado-cnpj"), dict):
        out["resultado-cnpj"]["filterCol"] = 0
        out["resultado-cnpj"]["filterLabel"] = "Mês"

    # ---- Programar VT+VR dos lançados no dia (o rito DIÁRIO do Jordan) --------------------
    # O Eliziel lança as diárias no Operacional; aqui o Jordan escolhe o dia e programa o
    # VT+VR (R$32) de cada diarista lançado. Só existia no clássico. Reusa o serviço provado
    # (idempotente por data+beneficiário; sem PIX vira 'sem_pix', nunca fabrica chave).
    out["programar-vtvr-dia"] = {
        "title": "Programar VT+VR do dia",
        "sub": "O Eliziel lança as diárias no Operacional; aqui você programa o VT+VR (R$ 32 = R$10 VT + "
               "R$22 VR) de cada diarista lançado no dia. Idempotente: rodar de novo não duplica. "
               "Quem não tem chave PIX no cadastro entra como 'sem PIX' e não é pago até completar.",
        "cta": "Programar VT+VR", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/programar-vtvr-dia",
                   "okMsg": "VT+VR programado — veja na aba Diaristas."},
        "fields": [{"key": "data", "label": "Dia* (AAAA-MM-DD)", "type": "date", "span": "span 2"}],
    }

    # ---- Adicionar pagamento avulso (cobertura CLT / líder com ajudantes) -----------------
    out["adicionar-vtvr-avulso"] = {
        "title": "Adicionar VT+VR avulso",
        "sub": "Cobertura de falta por CLT, ou líder que leva ajudantes (ex.: líder com 2 ajudantes "
               "recebe o VT+VR dos dois num PIX só → quantidade 2 = R$ 64). Entra no lote do dia.",
        "cta": "Adicionar ao lote", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/vtvr-avulso", "okMsg": "Adicionado ao lote."},
        "fields": [
            {"key": "data", "label": "Dia*", "type": "date", "span": "span 1"},
            {"key": "beneficiario", "label": "Beneficiário*", "type": "text", "span": "span 1", "ph": "Nome de quem recebe"},
            {"key": "pix_key", "label": "Chave PIX*", "type": "text", "span": "span 1", "ph": "CPF ou chave"},
            {"key": "quantidade", "label": "Qtd de pessoas", "type": "text", "span": "span 1", "ph": "1"},
        ],
    }

    # ---- Lote MENSAL de diárias (dia 15) — FLUXO 2, so existia no classico -----------------
    out["programar-diarias-mes"] = {
        "title": "Programar diárias do mês (lote dia 15)",
        "sub": "Soma os dias trabalhados × valor da diária de cada diarista no mês e monta o lote "
               "para o dia 15. NÃO paga — só programa. Idempotente por competência.",
        "cta": "Programar lote do mês", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/programar-diarias-mes",
                   "okMsg": "Lote do mês programado — veja na aba Diaristas."},
        "fields": [
            {"key": "mes", "label": "Mês* (1-12)", "type": "text", "span": "span 1", "ph": "8"},
            {"key": "ano", "label": "Ano*", "type": "text", "span": "span 1", "ph": "2026"},
        ],
    }

    # ---- Marcar pago por fora (dinheiro/outro banco) — evita pagar 2x --------------------
    out["marcar-pago-externo"] = {
        "title": "Marcar pago por fora",
        "sub": "Quando o VT/VR foi pago em dinheiro ou por outro banco. NÃO move dinheiro — só "
               "registra que já foi pago, para o item sair do lote e você não pagar duas vezes. "
               "O ID está na aba Diaristas.",
        "cta": "Marcar como pago", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/marcar-pago-externo",
                   "confirm": "Confirma que este pagamento JÁ foi feito por fora? Ele sai do lote.",
                   "okMsg": "Marcado como pago por fora."},
        "fields": [
            {"key": "pagamento_id", "label": "ID do pagamento*", "type": "text", "span": "span 1", "ph": "ex.: 1234"},
            {"key": "observacao", "label": "Como foi pago", "type": "text", "span": "span 1", "ph": "dinheiro / outro banco"},
        ],
    }

    # ---- Dar baixa em conta a pagar (bookkeeping — marca pago, NÃO move dinheiro) ---------
    out["baixar-pagavel"] = {
        "title": "Dar baixa em conta a pagar",
        "sub": "Quando a conta JÁ foi paga (PIX/boleto/dinheiro). NÃO move dinheiro — só registra "
               "que foi paga, com a data, p/ sair do 'a pagar' e entrar no fluxo de caixa real. "
               "Pagar de verdade é o fluxo com OTP. O ID está na tabela Contas a Pagar.",
        "cta": "Registrar baixa", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/baixar-pagavel",
                   "confirm": "Confirma que esta conta JÁ foi paga? Ela é MARCADA como paga (não paga de novo).",
                   "okMsg": "Baixa registrada."},
        "fields": [
            {"key": "payable_id", "label": "ID da conta a pagar*", "type": "text", "span": "span 1", "ph": "cole o ID da tabela"},
            {"key": "data_pagamento", "label": "Data do pagamento", "type": "text", "span": "span 1", "ph": "AAAA-MM-DD (vazio=hoje)"},
            {"key": "valor", "label": "Valor pago (vazio = total)", "type": "text", "span": "span 1", "ph": "ex.: 1500.00"},
        ],
    }

    out["baixar-recebivel"] = {
        "title": "Dar baixa em conta a receber",
        "sub": "Quando o cliente JÁ pagou. O valor que cai na conta costuma ser MENOR que a nota "
               "por causa da retenção na fonte (INSS 11%, IR 1%…) — informe o valor que entrou "
               "de verdade e diga se a diferença é retenção (quita a nota) ou pagamento parcial "
               "(fica saldo em aberto). NÃO move dinheiro: só registra o recebimento.",
        "cta": "Registrar recebimento", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/baixar-recebivel",
                   "okMsg": "Recebimento registrado.", "showResult": True},
        "fields": [
            {"key": "receivable_id", "label": "ID da conta a receber*", "type": "text", "span": "span 1",
             "ph": "cole o ID da tabela Contas a Receber"},
            {"key": "valor_recebido", "label": "Valor que entrou (vazio = total da nota)", "type": "text",
             "span": "span 1", "ph": "ex.: 36932.63"},
            {"key": "data_recebimento", "label": "Data do crédito", "type": "text", "span": "span 1",
             "ph": "AAAA-MM-DD (vazio = hoje)"},
            {"key": "tratamento", "label": "Diferença (se houver)*", "type": "select", "span": "span 1",
             "options": [{"value": "retencao", "label": "Retenção na fonte — quita a nota"},
                         {"value": "parcial", "label": "Pagamento parcial — deixa saldo em aberto"}]},
        ],
    }

    out["registrar-obrigacoes"] = {
        "title": "Registrar obrigações como conta a pagar",
        "sub": "Varre as fontes REAIS do que a empresa deve — NFS-e tomadas (serviço com nota), "
               "folha por competência e guias FGTS/INSS — e registra o que ainda não está no "
               "contas a pagar. Idempotente: rodar de novo não duplica. NÃO move dinheiro. "
               "Comece por PREVISUALIZAR: mostra o que faria sem gravar nada.",
        "cta": "Executar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/registrar-obrigacoes",
                   "okMsg": "Concluído.", "showResult": True},
        "fields": [
            {"key": "modo", "label": "Modo*", "type": "select", "span": "span 1",
             "options": [{"value": "preview", "label": "Previsualizar (não grava)"},
                         {"value": "aplicar", "label": "Aplicar (grava no contas a pagar)"}]},
        ],
    }

    out["gerar-recebiveis"] = {
        "title": "Gerar contas a receber do mês",
        "sub": "Um recebível por CONTRATO ativo na competência, com o CNPJ credor correto. "
               "É o que faz aging, inadimplência e régua de cobrança terem substrato. "
               "NÃO emite cobrança ao cliente: boleto/PIX é outro ato, com decisão sua. "
               "Idempotente por contrato/competência.",
        "cta": "Executar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/gerar-recebiveis",
                   "okMsg": "Concluído.", "showResult": True},
        "fields": [
            {"key": "mes", "label": "Mês", "type": "text", "span": "span 1", "ph": "1-12 (vazio = mês atual)"},
            {"key": "ano", "label": "Ano", "type": "text", "span": "span 1", "ph": "vazio = ano atual"},
            {"key": "modo", "label": "Modo*", "type": "select", "span": "span 1",
             "options": [{"value": "preview", "label": "Previsualizar (não grava)"},
                         {"value": "aplicar", "label": "Aplicar (grava no contas a receber)"}]},
        ],
    }

    # ---- Diaristas a cadastrar (do histórico de PIX R$32) ---------------------------------
    try:
        import modules.financial.pagamentos_diaristas_service as _sd
        _sug = await _sd.sugestoes_cadastro_historico(db, dias=60)
        _sug_itens = _sug.get("itens") or _sug.get("sugestoes") or []
    except Exception:  # noqa: BLE001 — tela nunca derruba o módulo
        _sug_itens = []
    out["diaristas-a-cadastrar"] = {
        "title": "Diaristas a cadastrar",
        "sub": (f"{len(_sug_itens)} pessoa(s) que já receberam VT/VR por PIX mas NÃO estão no cadastro "
                "de diaristas do Operacional. Cadastre lá para o lote sair completo."
                if _sug_itens else "Ninguém pendente de cadastro (aguardando dado)."),
        "cta": "—", "type": "table", "searchHint": "Buscar…",
        "grid": "2fr 1.6fr 1fr 1fr", "cols": ["Beneficiário", "Chave PIX", "Pagamentos", "Total"],
        "rows": [{"cells": [t(str(i.get("beneficiario") or "—"), 600, "#0F1B3A"),
                            t(str(i.get("pix_key") or i.get("pix") or "—")),
                            t(str(i.get("qtd") or i.get("pagamentos") or "—")),
                            t(brl(float(i.get("total") or 0)), 600)]} for i in _sug_itens]
                or [{"cells": [t("Ninguém pendente"), t("—"), t("—"), t("—")]}],
    }

    # ---- Sincronizar PIX recebidos — puxa do Inter p/ inter_pix_recebidos ----
    # Aponta DIRETO no endpoint que já existe (nada de wrapper novo). NÃO é money-out:
    # só LÊ do Inter e grava na nossa tabela → sem gate OTP (mesma classe do "Rodar
    # conciliação"). Roda em background no backend, por isso a mensagem não finge que
    # já acabou. ponytail: `dias` fixo em 30 na query; se precisar escolher, virar campo.
    # ---- Devolver PIX (MONEY-OUT, gate OTP) ----
    _pix_opts = [{"value": r[0], "label": f"{r[1]} · {brl(float(r[2] or 0))} · {_fmtdate(r[3]) if r[3] else '—'}"}
                 for r in (await db.execute(text(
                     "SELECT end_to_end_id, coalesce(nullif(pagador->>'nome',''),'(sem pagador)'), valor, data_horario "
                     "FROM inter_pix_recebidos WHERE end_to_end_id IS NOT NULL "
                     "ORDER BY data_horario DESC LIMIT 100"))).fetchall()]
    out["devolver-pix"] = {
        "title": "Devolver PIX recebido (Inter)",
        "sub": "Dinheiro que SAI — devolve ao pagador um PIX que entrou. 2 etapas: gera o código OTP "
               "(e-mail ao Jordan) e só devolve ao confirmar. Nunca dispara sozinho. "
               "Não deixa devolver mais do que entrou." if _pix_opts else
               "Nenhum PIX recebido sincronizado — use 'Sincronizar PIX' antes (aguardando dado).",
        "cta": "Gerar código de devolução", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/devolver-pix", "gated": True,
                   "confirm": "Isto vai DEVOLVER dinheiro ao pagador via Inter. Gerar o código OTP para o Jordan confirmar?",
                   "okMsg": "Devolução enviada."},
        "fields": [
            {"key": "e2e_id", "label": "PIX recebido*", "type": "select", "span": "span 2",
             "ph": "Selecione o PIX a devolver", "options": _pix_opts},
            {"key": "valor", "label": "Valor a devolver* (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "motivo", "label": "Motivo", "type": "text", "span": "span 1", "ph": "Devolucao solicitada"},
        ],
    }

    # ---- Ajustar saldo (override contábil, gate OTP) ----
    _conta_opts = [{"value": str(r[0]), "label": f"{r[1]} · {r[2]} · saldo {brl(float(r[3] or 0))}"}
                   for r in (await db.execute(text(
                       "SELECT id, coalesce(name,'—'), coalesce(bank_name,'—'), current_balance "
                       "FROM bank_accounts WHERE ativo IS NOT FALSE ORDER BY name"))).fetchall()]
    out["ajustar-saldo"] = {
        "title": "Ajustar saldo da conta",
        "sub": "NÃO move dinheiro no banco — sobrescreve o saldo NO SISTEMA e grava um lançamento "
               "de ajuste no extrato (afeta conciliação e DRE). Por isso exige OTP, como dinheiro. "
               "Use só quando o extrato real divergir e você souber o motivo.",
        "cta": "Gerar código de ajuste", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/ajustar-saldo", "gated": True,
                   "confirm": "Isto vai SOBRESCREVER o saldo da conta no sistema e lançar um ajuste no extrato. Gerar o código OTP?",
                   "okMsg": "Saldo ajustado."},
        "fields": [
            {"key": "conta", "label": "Conta*", "type": "select", "span": "span 2",
             "ph": "Selecione a conta", "options": _conta_opts},
            {"key": "novo_saldo", "label": "Novo saldo* (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "motivo", "label": "Motivo* (fica no extrato)", "type": "text", "span": "span 1",
             "ph": "ex.: divergência de sync do dia 30"},
        ],
    }

    out["sincronizar-pix"] = {
        "title": "Sincronizar PIX recebidos (Inter)",
        "sub": "Puxa os PIX recebidos dos últimos 30 dias do Inter para o Conecta PRO. "
               "Só leitura do banco — não move dinheiro. Roda em segundo plano: a aba "
               "'PIX recebidos' preenche em instantes (recarregue para ver).",
        "cta": "Sincronizar agora", "type": "form",
        "submit": {"endpoint": "/api/v1/financeiro/inter/pix/sync-recebidos?dias=30",
                   "okMsg": "Sincronização iniciada — a lista atualiza em instantes."},
        "fields": [],
    }

    # ---- Banco Inter (extrato Inter real) ----
    await safe("inter", tbl(
        "Banco Inter", f"{await _scalar(db, 'SELECT count(*) FROM inter_transactions')} lançamentos no extrato Inter — 12 meses, filtre por mês",
        "—", ["Mês", "Data", "Operação", "Descrição", "Valor", "Tipo"], "0.8fr 1fr 0.9fr 2fr 1fr 1.1fr",
        "SELECT to_char(data_lancamento,'MM/YYYY'), data_lancamento, coalesce(tipo_operacao,'—'), "
        "coalesce(titulo,descricao,'—'), valor, coalesce(tipo_transacao,'—') "
        "FROM inter_transactions "
        "WHERE data_lancamento >= date_trunc('month', CURRENT_DATE - interval '11 months') "
        "ORDER BY data_lancamento DESC NULLS LAST LIMIT 3000",
        lambda r: [t(r[0], 600), t(_fmtdate(r[1])),
                   b("Crédito" if r[2] == 'C' else ("Débito" if r[2] == 'D' else (r[2] or '—')),
                     "ok" if r[2] == 'C' else "mut"),
                   t(r[3]), t(brl(r[4]), 600, "#0F1B3A"), t(r[5])]))
    if isinstance(out.get("inter"), dict):
        out["inter"]["filterCol"] = 0
        out["inter"]["filterLabel"] = "Mês"

    # ---- Banco Cora (extrato Cora real — bank_transactions da conta Cora, bank_code 403) ----
    _cora_n = await _scalar(db, "SELECT count(*) FROM bank_transactions bt JOIN bank_accounts ba ON ba.id=bt.bank_account_id WHERE ba.bank_code='403'")
    await safe("cora", tbl(
        "Banco Cora", f"{_cora_n} lançamentos no extrato Cora — 12 meses, filtre por mês",
        "—", ["Mês", "Data", "Contraparte", "Descrição", "Valor", "Tipo"], "0.8fr 1fr 1.5fr 2fr 1fr 1.1fr",
        "SELECT to_char(bt.transaction_date,'MM/YYYY'), bt.transaction_date, "
        "coalesce(bt.counterparty_name,bt.contraparte_nome,'—'), coalesce(bt.description,bt.memo,'—'), "
        "bt.amount, coalesce(bt.transaction_type,'—') "
        "FROM bank_transactions bt JOIN bank_accounts ba ON ba.id=bt.bank_account_id "
        "WHERE ba.bank_code='403' "
        "AND bt.transaction_date >= date_trunc('month', CURRENT_DATE - interval '11 months') "
        "ORDER BY bt.transaction_date DESC NULLS LAST LIMIT 3000",
        lambda r: [t(r[0], 600), t(_fmtdate(r[1])), t(r[2], 600, "#0F1B3A"), t(r[3]), t(brl(r[4]), 600),
                   b("Crédito" if (r[5] or '').lower() in ('credit', 'credito', 'c') else "Débito",
                     "ok" if (r[5] or '').lower() in ('credit', 'credito', 'c') else "mut")]))
    if isinstance(out.get("cora"), dict):
        out["cora"]["filterCol"] = 0
        out["cora"]["filterLabel"] = "Mês"

    # ---- Compras (nfe_compras_estoque — itens comprados por NF-e) ----
    await safe("compras", tbl(
        "Compras", f"{await _scalar(db, 'SELECT count(*) FROM nfe_compras_estoque')} itens de compra (NF-e)",
        "—", ["Código", "Item", "Qtd", "Custo unit.", "Última compra"], "1fr 2fr 0.8fr 1fr 1fr",
        "SELECT coalesce(item_code,'—'), coalesce(descricao,'—'), qty_on_hand, unit_cost, last_purchase_date "
        "FROM nfe_compras_estoque ORDER BY last_purchase_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(str(r[2]) if r[2] is not None else '—'),
                   t(brl(r[3]) if r[3] is not None else '—', 600), t(_fmtdate(r[4]))]))

    # ---- Estoque (saldo atual + custo médio) ----
    await safe("estoque", tbl(
        "Estoque", "Saldo de estoque (a partir das NF-e de compra)",
        "—", ["Código", "Item", "Unid.", "Saldo", "Custo médio"], "1fr 2fr 0.8fr 0.9fr 1fr",
        "SELECT coalesce(item_code,'—'), coalesce(descricao,'—'), coalesce(unidade,'—'), qty_on_hand, avg_cost "
        "FROM nfe_compras_estoque ORDER BY descricao LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]),
                   t(str(r[3]) if r[3] is not None else '—', 600), t(brl(r[4]) if r[4] is not None else '—')]))

    # ---- Faturamento (NFS-e emitidas — receita) ----
    await safe("faturamento", tbl(
        "Faturamento", f"{await _scalar(db, 'SELECT count(*) FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false')} NFS-e emitidas",
        "—", ["Número", "Competência", "Tomador", "Serviços", "Líquido"], "1fr 1fr 2fr 1fr 1fr",
        "SELECT chave_acesso, coalesce(numero,'—'), coalesce(competencia,'—'), coalesce(tomador_nome,'—'), valor_servicos, valor_liquido "
        "FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false ORDER BY data_emissao DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, "#0F1B3A"), t(r[2]), t(r[3]), t(brl(r[4]), 600), t(brl(r[5]))],
        docsfn=lambda r: [doc("DANFSe", f"/api/v1/financial/fiscal/nfse-emitida/{r[0]}/danfse", fmt="pdf")] if r[0] else []))

    # ---- Fiscal (tributos sobre NFS-e emitidas — ISS/INSS retido) ----
    await safe("fiscal", tbl(
        "Fiscal", "Tributos sobre NFS-e emitidas (ISS / INSS retido)",
        "—", ["Competência", "NFS-e", "Base", "ISS", "INSS ret."], "1fr 1fr 1fr 1fr 1fr",
        "SELECT coalesce(competencia,'—'), coalesce(numero,'—'), valor_servicos, iss_valor, inss_retido "
        "FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false ORDER BY data_emissao DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2])), t(brl(r[3])),
                   t(brl(r[4]) if r[4] is not None else brl(0))]))

    # ---- NFS-e entrada (notas tomadas + CNPJ prestador e Empresa, que o clássico mostra) ----
    # NFS-e entrada (Notas Recebidas) — DANFSe por-linha (download/ver nota), paridade com o clássico.
    # Rota curl-provada 200 application/pdf: /api/v1/financial/nfse-entrada/{chave}/pdf (gera do
    # xml_raw fiel ou dos campos como fallback). Só liga onde há chave_acesso.
    await safe("nfse-entrada", tbl(
        "NFS-e entrada", f"{await _scalar(db, 'SELECT count(*) FROM nfse_tomadas_nacional')} notas tomadas",
        "—", ["Prestador", "CNPJ", "Empresa", "Competência", "Serviços", "ISS"], "1.8fr 1.3fr 1.6fr 1fr 1fr 1fr",
        "SELECT nt.chave_acesso, coalesce(nt.prestador_nome,'—'), coalesce(nt.prestador_cnpj,'—'), "
        "coalesce(e.razao_social, e.nome_fantasia, e.slug, '—'), coalesce(nt.competencia,'—'), nt.valor_servicos, nt.iss_valor "
        "FROM nfse_tomadas_nacional nt LEFT JOIN empresas e ON e.id=nt.empresa_id ORDER BY nt.data_emissao DESC NULLS LAST LIMIT 500",
        lambda r: [t(r[1], 600, "#0F1B3A"), t(_cnpj(r[2])), t(r[3]), t(r[4]), t(brl(r[5]), 600),
                   t(brl(r[6]) if r[6] is not None else brl(0))],
        docsfn=lambda r: [doc("DANFSe", f"/api/v1/financial/nfse-entrada/{r[0]}/pdf", fmt="pdf")] if r[0] else []))

    # ---- Orçamentos (financial_orcamentos — chaves orçamentárias) ----
    # Orçado × Realizado mensal — orçado = MRR real (baseline, não projeção fabricada);
    # realizado = receita real do extrato no mês. Estrutura do clássico, sem inventar crescimento.
    _mrr_base = float(await _scalar(db, "SELECT coalesce(sum(mrr),0) FROM clients WHERE ativo=true AND coalesce(mrr,0)>0") or 0)
    await safe("orcamentos", tbl(
        "Orçamentos", f"Orçado × Realizado mensal — orçado = MRR ({brl(_mrr_base)}, baseline real); realizado = receita do extrato",
        "—", ["Mês", "Orçado (MRR)", "Realizado", "Diferença", "%"], "1fr 1.3fr 1.3fr 1.3fr 0.9fr",
        "SELECT to_char(date_trunc('month', transaction_date), 'MM/YYYY'), "
        "ROUND(SUM(CASE WHEN amount>0 THEN amount ELSE 0 END)::numeric,2) "
        "FROM bank_transactions WHERE transaction_date >= date_trunc('month', CURRENT_DATE - interval '11 months') "
        "GROUP BY 1, date_trunc('month', transaction_date) ORDER BY date_trunc('month', transaction_date) DESC",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(_mrr_base), 600),
                   t(brl(r[1]), 600, "#16A34A"),
                   b(f"{'+' if (float(r[1] or 0) - _mrr_base) >= 0 else ''}{brl(float(r[1] or 0) - _mrr_base)}",
                     "ok" if (float(r[1] or 0) - _mrr_base) >= 0 else "bad"),
                   t(f"{((float(r[1] or 0) - _mrr_base) / _mrr_base * 100):+.1f}%" if _mrr_base else "—")]))
    if isinstance(out.get("orcamentos"), dict):  # A3: filtro de Mês (filterCol já existe no renderer)
        out["orcamentos"]["filterCol"] = 0
        out["orcamentos"]["filterLabel"] = "Mês"

    # ---- Precificação (crm_pricing_funcoes — tabela CCT de funções) ----
    # Precificação — custo/preço/margem por função (mesma tabela do clássico, reusa calcular_funcao)
    try:
        from modules.operacional.controllers.redesign_builders.crm import _build_precificacao as _bp
        out["precificacao"] = await _bp(db, t, b, brl)
    except Exception:  # noqa: BLE001 — fallback: mantém o config CCT
        await db.rollback()
        await safe("precificacao", tbl(
            "Precificação", f"{await _scalar(db, 'SELECT count(*) FROM crm_pricing_funcoes WHERE ativo=true')} funções (base CCT)",
            "—", ["Função", "Piso", "Noturno", "Periculosidade", "Insalubridade"], "2fr 1fr 1fr 1fr 1fr",
            "SELECT nome, salario_base, noturno, periculosidade, insalubridade "
            "FROM crm_pricing_funcoes WHERE ativo=true ORDER BY ordem NULLS LAST LIMIT 50",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[1]), 600), _simnao(r[2]), _simnao(r[3]), _simnao(r[4])]))

    # ---- Custos (financial_custos_recorrentes) ----
    await safe("custos", tbl(
        "Custos", f"{await _scalar(db, 'SELECT count(*) FROM financial_custos_recorrentes')} custos recorrentes",
        "—", ["Categoria", "Descrição", "Valor", "Dia venc.", "Ativo"], "1.2fr 2fr 1fr 0.8fr 0.7fr",
        "SELECT coalesce(categoria,'—'), coalesce(descricao,'—'), valor, dia_vencimento, ativo "
        "FROM financial_custos_recorrentes ORDER BY valor DESC LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(brl(r[2]), 600),
                   t(str(r[3]) if r[3] is not None else '—'), b("Ativo", "ok") if r[4] else b("Inativo", "mut")]))

    # ---- Contabilidade (razão — extrato bancário categorizado) ----
    await safe("contabilidade", tbl(
        "Contabilidade", "Lançamentos categorizados (razão a partir do extrato)",
        "—", ["Data", "Conta/Categoria", "Histórico", "D/C", "Valor"], "1fr 1.3fr 2fr 0.9fr 1fr",
        "SELECT transaction_date, coalesce(category,'—'), coalesce(description,memo,'—'), coalesce(transaction_type,'—'), amount "
        "FROM bank_transactions WHERE category IS NOT NULL ORDER BY transaction_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0])), t((r[1] or '—').replace('_', ' ').capitalize(), 600, "#0F1B3A"),
                   t(r[2]), b((r[3] or '—').replace('_', ' ').capitalize(), "info"), t(brl(r[4]), 600)]))

    # ---- Contratos (contracts + Cliente/CNPJ e Retenções, que o clássico mostra) ----
    def _reten(iss, inss, csll):
        tags = [x for x, on in (("ISS", iss), ("INSS", inss), ("CSLL", csll)) if on]
        return b(" ".join(tags), "warn") if tags else b("Nenhuma", "mut")
    await safe("contratos", tbl(
        "Contratos", f"{await _scalar(db, 'SELECT count(*) FROM contracts')} contratos",
        "—", ["Nº", "Cliente", "Contrato", "Mensal", "Retenções", "Status"], "1fr 1.8fr 1.8fr 1fr 1fr 0.9fr",
        "SELECT coalesce(ct.contract_number,'—'), coalesce(cl.name,'—'), coalesce(ct.name,'—'), ct.monthly_value, "
        "ct.retencao_iss, ct.retencao_inss, ct.retencao_csll, coalesce(ct.status::text,'—') "
        "FROM contracts ct LEFT JOIN clients cl ON cl.id=ct.client_id ORDER BY ct.monthly_value DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1], 600, "#0F1B3A"), t(r[2]),
                   t(brl(r[3]) if r[3] is not None else '—', 600), _reten(r[4], r[5], r[6]),
                   b((r[7] or '—').capitalize(), "ok" if (r[7] or '').lower() in ("active", "ativo", "assinado", "signed") else "info")]))

    # ---- Raio-X (KPIs financeiros — só honra valor com prova de cálculo/sync) ----
    await safe("raio-x", tbl(
        "Raio-X financeiro", "Indicadores-chave — 'não calculado' = KPI sem cálculo/sync (não é métrica real ainda)",
        "—", ["Indicador", "Valor", "Unidade", "Atualizado", "Status"], "2fr 1fr 0.8fr 1.1fr 0.9fr",
        "SELECT coalesce(nome,'—'), valor_atual, coalesce(unidade,'—'), coalesce(status::text,'—'), "
        "coalesce(ultima_atualizacao, ultimo_calculo_at) "
        'FROM financial_kpis WHERE ativo=true ORDER BY "order" NULLS LAST LIMIT 50',
        lambda r: [t(r[0], 600, "#0F1B3A"), _kpi_valor(r[0], r[1], r[2], r[4]), t(r[2]),
                   t(_fmtdate(r[4], '%d/%m %H:%M') if r[4] else '—'),
                   b((r[3] or '—').capitalize(), "ok" if (r[3] or '').upper() == "ACTIVE" else "mut")]))

    # ---- CFO IA (histórico de consultas — READ) ----
    await safe("cfo", tbl(
        "CFO IA", f"{await _scalar(db, 'SELECT count(*) FROM financial_cfo_consultas')} consultas (histórico)",
        "—", ["Área", "Pergunta", "Autor", "Data"], "1fr 2.5fr 1fr 1fr",
        "SELECT coalesce(area,'—'), left(coalesce(pergunta,'—'),90), coalesce(created_by,'—'), created_at "
        "FROM financial_cfo_consultas ORDER BY created_at DESC NULLS LAST LIMIT 200",
        lambda r: [b((r[0] or '—').capitalize(), "info"), t(r[1], 600, "#0F1B3A"), t(r[2]), t(_fmtdate(r[3]))]))

    # ---- Agentes (áreas ativas do CFO IA, agregadas — real) ----
    await safe("agentes", tbl(
        "Agentes IA", "Áreas de consultoria ativas (CFO IA)",
        "—", ["Agente / Área", "Consultas", "Última consulta"], "2fr 1fr 1.2fr",
        "SELECT coalesce(area,'—'), count(*), max(created_at) FROM financial_cfo_consultas GROUP BY area ORDER BY count(*) DESC",
        lambda r: [t((r[0] or '—').capitalize(), 600, "#0F1B3A"), b(f"{r[1]} consultas", "info"), t(_fmtdate(r[2]))]))

    # ---- Relatórios (indicadores para relatórios — marca não calculados) ----
    await safe("relatorios", tbl(
        "Relatórios", "Indicadores para relatórios — 'não calculado' = sem cálculo/sync ainda",
        "—", ["Indicador", "Categoria", "Valor atual", "Atualizado", "Frequência"], "2fr 1.1fr 1fr 1.1fr 0.9fr",
        "SELECT coalesce(nome,'—'), coalesce(categoria::text,'—'), valor_atual, coalesce(frequencia::text,'—'), "
        "coalesce(ultima_atualizacao, ultimo_calculo_at) "
        'FROM financial_kpis WHERE ativo=true ORDER BY "order" NULLS LAST LIMIT 50',
        lambda r: [t(r[0], 600, "#0F1B3A"), b((r[1] or '—').capitalize(), "mut"),
                   _kpi_valor(r[0], r[2], None, r[4]),
                   t(_fmtdate(r[4], '%d/%m %H:%M') if r[4] else '—'), t((r[3] or '—').capitalize())]))

    # ---- Custeio CCT — o form de compute já existe no monólito sob 'custeio-cct';
    #      o menu-id real é 'custeio' → aponta a mesma ferramenta (compute puro, nada é gravado).
    if "custeio-cct" in out:
        out["custeio"] = out["custeio-cct"]

    # ---- ESCRITA GATED: Pagar folha PJ (money-out). Delega ao serviço PROVADO
    #      pagamento_pj (que tem OTP próprio: gerar código → executar). NUNCA dispara
    #      sozinho — 2 etapas + confirmação humana + OTP do Jordan. ----
    out["pagar-folha-pj"] = {
        "title": "Pagar folha PJ (Inter)",
        "sub": "Dinheiro que SAI — 2 etapas: gera o código OTP (e-mail ao Jordan) e só paga ao confirmar com o código. Nunca dispara sozinho.",
        "cta": "Gerar código de pagamento", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/pagar-folha-pj", "gated": True,
                   "confirm": "Isto vai PAGAR a folha PJ (Inter) do mês via PIX. Gerar o código OTP para o Jordan confirmar?",
                   "okMsg": "Lote processado."},
        "fields": [
            {"key": "mes", "label": "Mês* (1-12)", "type": "text", "span": "span 1", "ph": "7"},
            {"key": "ano", "label": "Ano*", "type": "text", "span": "span 1", "ph": "2026"},
            # A folha CLT é da PATRIMONIAL desde 06/2026 → Cora é o padrão.
            {"key": "origem", "label": "Banco", "type": "select", "span": "span 2",
             "ph": "Cora — Patrimonial (padrão da folha CLT)",
             "options": [{"value": "cora", "label": "Cora — Patrimonial (padrão: a folha CLT é da Patrimonial)"},
                         {"value": "inter", "label": "Inter — Eletrônica (só se for exceção)"}]},
        ],
    }
    # Lote de diaristas a pagar (VT/VR + diária) — a aba "Diaristas" estava vazia (sem builder),
    # então não dava p/ ver/pagar o VT/VR no redesign. Visibilidade do que pagar-diaristas processa.
    _dia = (await db.execute(text(
        "SELECT data_referencia, beneficiario, tipo, valor, status, coalesce(pix_key,'') FROM financial_pagamentos_diaristas "
        "WHERE status IN ('a_revisar','sem_pix') "
        "ORDER BY (data_referencia = CURRENT_DATE) DESC, data_referencia DESC, beneficiario LIMIT 300"))).fetchall()
    # Quantos e quanto por DIA — o botão precisa dizer isso, senão "Pagar este dia" numa
    # linha se lê como "pagar esta pessoa".
    _resumo_dia: dict = {}
    for _r in _dia:
        if _r[4] != "a_revisar" or not _r[0]:
            continue
        _k = _r[0].isoformat() if hasattr(_r[0], "isoformat") else str(_r[0])
        _a = _resumo_dia.setdefault(_k, {"n": 0, "total": 0.0})
        _a["n"] += 1
        _a["total"] += float(_r[3] or 0)
    _ja_teve_botao: set = set()
    _dcells = [{"cells": [
        t(_fmtdate(r[0]) if r[0] else "—", 600, "#0F1B3A"), t(r[1] or "—"),
        b("VT/VR" if r[2] == "vt_vr" else "Diária" if r[2] == "diaria_mensal" else (r[2] or "—"),
          "info" if r[2] == "vt_vr" else "mut"),
        t(brl(r[3]) if r[3] is not None else "—", 600),
        t(r[5] or "—"),
        b("sem PIX" if r[4] == "sem_pix" else "a revisar", "bad" if r[4] == "sem_pix" else "warn"),
    ], **_acao_pagar_dia(r, _resumo_dia, _ja_teve_botao)} for r in _dia]
    _n_pessoas = len({(r[1] or "").strip().upper() for r in _dia if r[1]})
    # Total POR DIA de pagamento — o Jordan paga o VT/VR no dia e as diárias no dia 15,
    # entao ele precisa ver "quanto sai no dia X", nao so o total geral.
    _por_dia: dict = {}
    for r in _dia:
        if r[4] != "a_revisar":
            continue
        k = r[0]
        d = _por_dia.setdefault(k, {"vt": 0.0, "di": 0.0, "n": 0})
        d["n"] += 1
        d["vt" if r[2] == "vt_vr" else "di"] += float(r[3] or 0)
    _linhas_dia = [{"left": f"{_fmtdate(k)} — {v['n']} item(ns)",
                    "right": brl(v["vt"] + v["di"]),
                    **S["ok" if v["di"] else "info"]}
                   for k, v in sorted(_por_dia.items(), key=lambda x: str(x[0]), reverse=True)][:8]
    _tot_vt = sum(float(r[3] or 0) for r in _dia if r[2] == "vt_vr" and r[4] == "a_revisar")
    _tot_di = sum(float(r[3] or 0) for r in _dia if r[2] == "diaria_mensal" and r[4] == "a_revisar")
    # Documentos de diarista: lista geral + extrato e recibo POR LINHA. O periodo sai
    # do mes corrente por padrao (regra da rota); para outra competencia, os botoes
    # levam o intervalo na URL — foi o que o Jordan pediu ao querer julho fechado.
    _p_ini = (_date.today().replace(day=1) - _timedelta(days=1)).replace(day=1)
    _p_fim = _date.today().replace(day=1) - _timedelta(days=1)
    _qs = f"?inicio={_p_ini.isoformat()}&fim={_p_fim.isoformat()}"
    # Junta o LANÇADO (dias trabalhados) com o PAGO (valor, data e comprovante do banco).
    # Conferir recibo exige as duas pontas: quantos dias geraram o valor, e a prova de que
    # o valor saiu. Só o lançado não diz se foi pago; só o pago não diz de onde veio.
    _comp_ref = f"{_p_ini:%m/%Y}"
    _dl = (await db.execute(text(
        "SELECT d.id, d.nome, coalesce(d.cpf,'') AS cpf, "
        "       coalesce(nullif(d.pix,''),'(SEM CHAVE PIX)') AS pix, "
        "       count(*) AS dias, sum(l.valor)::numeric(12,2) AS total, "
        "       coalesce(p.status,'nao lancado') AS pstatus, "
        "       p.updated_at::date AS pago_em, "
        "       CASE WHEN position('| e2e:' in coalesce(p.descricao,'')) > 0 "
        "            THEN right(p.descricao, 36) ELSE '' END AS comprovante "
        "  FROM diaria_lancamentos l "
        "  JOIN diaria_diaristas d ON d.id = l.diarista_id "
        "  LEFT JOIN financial_pagamentos_diaristas p "
        "         ON upper(btrim(p.beneficiario)) = upper(btrim(d.nome)) "
        "        AND p.competencia = :comp AND p.tipo = 'diaria_mensal' "
        " WHERE l.status = 'lancado' AND l.data BETWEEN :a AND :b "
        " GROUP BY d.id, d.nome, d.cpf, d.pix, p.status, p.updated_at, p.descricao "
        " ORDER BY d.nome"),
        {"a": _p_ini, "b": _p_fim, "comp": _comp_ref})).fetchall()
    _pagos = [r for r in _dl if str(r[6]) == "pago"]
    out["documentos-diaristas"] = {
        "title": f"Diaristas — documentos ({_p_ini:%m/%Y})",
        "sub": ("Lista de pagamento do mês fechado, extrato individual e recibo para assinatura. "
                "O extrato mostra dia a dia com posto, turno e valor; o recibo traz o valor por "
                "extenso e a linha de assinatura. Nenhum deles paga nada."),
        "cta": "—", "type": "table", "searchHint": "Buscar diarista…",
        "grid": "1.8fr 1.4fr 0.4fr 0.9fr 0.8fr 0.8fr 1.4fr",
        "cols": ["Diarista", "Chave PIX", "Dias", "Total", "Situação", "Pago em", "Comprovante do banco"],
        "rows": [{"cells": [t(r[1]), t(r[3]), t(str(r[4])), t(brl(r[5])),
                            b("PAGO", "ok") if str(r[6]) == "pago" else b(str(r[6]).upper(), "warn"),
                            t(_fmtdate(r[7]) if r[7] else "—"),
                            t((r[8] or "—")[-36:])],
                  "docs": [doc("Extrato (PDF)", f"/api/v1/financial/diaristas/{r[0]}/extrato/pdf{_qs}", fmt="pdf"),
                           doc("Recibo (PDF)", f"/api/v1/financial/diaristas/{r[0]}/recibo/pdf{_qs}", fmt="pdf")]}
                 for r in _dl] or [{"cells": [t("—"), t("Nenhuma diária no mês fechado"), t("—"), t("—"), t("—"), t("—")]}],
        "docs": [doc(f"Lista de pagamento {_p_ini:%m/%Y} (PDF)",
                     f"/api/v1/financial/diaristas/relatorio/pdf{_qs}", fmt="pdf"),
                 doc(f"Recibos ASSINADOS {_p_ini:%m/%Y} — todos em ZIP",
                     f"/api/v1/financial/diaristas/recibos/{_p_ini:%Y-%m}/zip", fmt="zip", mode="blob")],
        "panelGrid": "1fr 1fr",
        "panels": [
            {"title": f"Conferência — {_comp_ref}", "rows": [
                {"left": "Diaristas com diária lançada", "right": str(len(_dl)), **S["info"]},
                {"left": "Dias trabalhados", "right": str(sum(r[4] for r in _dl)), **S["info"]},
                {"left": "Valor lançado", "right": brl(sum(float(r[5]) for r in _dl)), **S["info"]},
                {"left": "PAGOS (com prova no banco)", "right": f"{len(_pagos)} · {brl(sum(float(r[5]) for r in _pagos))}",
                 **(S["ok"] if len(_pagos) == len(_dl) else S["warn"])},
                {"left": "Ainda não pagos", "right": str(len(_dl) - len(_pagos)),
                 **(S["ok"] if len(_pagos) == len(_dl) else S["bad"])}]},
            {"title": "Como usar", "rows": [
                {"left": "1. Confira a coluna Comprovante contra o extrato", "right": "conferência", **S["mut"]},
                {"left": "2. Baixe os recibos em lote — já vêm assinados", "right": "ICP-Brasil", **S["ok"]},
                {"left": "3. Ou baixe o recibo de uma pessoa só, na linha", "right": "por linha", **S["mut"]},
                {"left": "Recibo sai só para quem foi PAGO", "right": "regra", **S["warn"]}]},
        ],
    }
    out["pagamentos-diaristas"] = {
        "title": "A pagar — VT+VR e diárias",
        # O texto mandava "abra outra aba e informe a DATA" — agora o botão está na linha.
        # O sub diz o TOTAL primeiro: a pergunta do dono é "quantas pessoas e quanto sai",
        # e ela não pode exigir somar 45 linhas de cabeça.
        "sub": (f"{_n_pessoas} pessoa(s) · {len(_dia)} lançamento(s) · {brl(_tot_vt + _tot_di)} a pagar. "
                "Clique em 'Pagar este dia' na linha — paga o lote inteiro da data (VT/VR e "
                "diária saem juntos), com OTP. 'sem PIX' = falta a chave no cadastro do Operacional."),
        "cta": "—", "type": "table", "searchHint": "Buscar diarista…",
        "grid": "1fr 1.8fr 0.8fr 1fr 1.4fr 0.9fr",
        "cols": ["Data", "Diarista", "Tipo", "Valor", "Chave PIX", "Status"],
        "rows": _dcells or [{"cells": [t("Nada pendente"), t("—"), t("—"), t("—"), t("—")]}],
        "filterCol": 0, "filterLabel": "Dia", "filterUnit": "lançamento(s)",
        "panelGrid": "1fr 1fr 1fr",
        "panels": [
            {"title": "A pagar POR DIA (o que sai em cada data)",
             "rows": _linhas_dia or [{"left": "Nada pendente", "right": brl(0), **S["mut"]}]},
            {"title": "Total pendente (a_revisar)", "rows": [
                {"left": "VT/VR", "right": brl(_tot_vt), **S["info"]},
                {"left": "Diária mensal", "right": brl(_tot_di), **S["ok"]}]},
            {"title": "Como pagar", "rows": [
                {"left": "Botão 'Pagar este dia' na linha — já leva a data", "right": "OTP", **S["ok"]},
                {"left": "Paga o lote da DATA inteira, não só a linha", "right": "atenção", **S["warn"]},
                {"left": "Escolha a conta: Cora=Patrimonial, Inter=Eletrônica", "right": "2 CNPJs", **S["warn"]},
                {"left": "Mês inteiro de uma vez: aba 'Pagar diaristas'", "right": "lote", **S["mut"]}]},
        ],
    }
    # Opções vindas do banco: só competência que TEM item a pagar. Lista fixa de meses
    # ofereceria escolha que resulta em "nenhum item elegível" — botão que não faz nada.
    _cl = (await db.execute(text(
        "SELECT competencia, count(*) n, sum(valor) v FROM financial_pagamentos_diaristas "
        "WHERE status='a_revisar' AND pix_key IS NOT NULL AND competencia IS NOT NULL "
        "GROUP BY 1 ORDER BY substring(competencia,4,4) DESC, substring(competencia,1,2) DESC"))).fetchall()
    _comp_opts = [{"value": "", "label": "— escolha a competência —"}] + [
        {"value": f"{r[0][3:]}-{r[0][:2]}", "label": f"{r[0]} — {r[1]} diarista(s), {brl(r[2])}"}
        for r in _cl]

    out["pagar-diaristas"] = {
        # O título repete o que o rótulo da aba diz, porque é o cabeçalho que o operador
        # lê antes de clicar em "gerar OTP" — e aqui sai dinheiro.
        "title": "Pagar VT+VR ou diárias (em lote)",
        "sub": "Dinheiro que SAI. DEIXE A DATA VAZIA para pagar o lote inteiro de uma vez (o mês "
               "fechado); informe um dia só se quiser pagar apenas aquele dia. Pelo INTER o sistema paga "
               "direto (2 etapas com OTP); pela CORA a API não envia PIX por chave — devolve a lista para "
               "você concluir no app e depois marcar em 'Pago por fora'.",
        "cta": "Gerar código de pagamento", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/pagar-diaristas", "gated": True,
                   "confirm": "Isto vai PAGAR o lote de diaristas (Inter) do dia via PIX. Gerar o código OTP para o Jordan confirmar?",
                   "okMsg": "Lote processado."},
        "fields": [
            {"key": "competencia", "label": "Competência — paga o mês inteiro", "type": "select",
             "span": "span 1", "options": _comp_opts},
            {"key": "data", "label": "OU um dia só (AAAA-MM-DD)", "type": "date", "span": "span 1"},
            # Sem escolha = tudo, como sempre foi. O seletor existe porque VT/VR e diária
            # caem na mesma data e o lote levava os dois: quem quer soltar só a passagem
            # do dia acabava soltando o mês inteiro de alguém.
            {"key": "tipo", "label": "O que pagar", "type": "select", "span": "span 1",
             "options": [{"value": "", "label": "Tudo (VT/VR + diária)"},
                         {"value": "vt_vr", "label": "Só VT+VR do dia"},
                         {"value": "diaria_mensal", "label": "Só a diária"}]},
            # Diarista é prestador da PATRIMONIAL → Cora é o padrão (regra do Jordan:
            # Eletrônica paga pelo Inter, Patrimonial paga pela Cora).
            {"key": "origem", "label": "Banco", "type": "select", "span": "span 1",
             "ph": "Cora — Patrimonial (padrão dos diaristas)",
             "options": [{"value": "cora", "label": "Cora — Patrimonial (padrão: diaristas são da Patrimonial)"},
                         {"value": "inter", "label": "Inter — Eletrônica (só se for exceção)"}]},
        ],
    }
    out["pagar-folha-clt"] = {
        "title": "Pagar folha CLT",
        "sub": "Dinheiro que SAI — paga o LÍQUIDO dos funcionários CLT via PIX (chave PIX cadastrada). "
               "2 etapas: gera o código OTP (e-mail ao Jordan) e só paga ao confirmar. Nunca dispara sozinho. Teto R$100k.",
        "cta": "Gerar código de pagamento", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/pagar-folha-clt", "gated": True,
                   "confirm": "Isto vai PAGAR a folha CLT (líquido dos funcionários) do mês. Pela Cora, devolve a lista p/ o app; pelo Inter, gera o código OTP para o Jordan confirmar?",
                   "okMsg": "Folha CLT processada."},
        "fields": [
            {"key": "mes", "label": "Mês* (1-12)", "type": "text", "span": "span 1", "ph": "7"},
            {"key": "ano", "label": "Ano*", "type": "text", "span": "span 1", "ph": "2026"},
            # A folha CLT e da PATRIMONIAL desde 06/2026 -> Cora e o padrao (regra do Jordan).
            {"key": "origem", "label": "Banco", "type": "select", "span": "span 2",
             "ph": "Cora — Patrimonial (padrão da folha CLT)",
             "options": [{"value": "cora", "label": "Cora — Patrimonial (padrão: a folha CLT é da Patrimonial)"},
                         {"value": "inter", "label": "Inter — Eletrônica (só se for exceção)"}]},
        ],
    }

    # ---- Pagar boleto (código de barras) — money-out via InterPaymentService + OTP ----
    out["pagar-boleto"] = {
        "title": "Pagar boleto (Inter)",
        "sub": "Dinheiro que SAI — 2 etapas + OTP. Boleto, convênio ou tributo por código de barras/linha digitável. Trava de saldo e limite diário no serviço.",
        "cta": "Preparar e gerar OTP", "type": "form",
        "originField": True,
        # Anexar o PDF do boleto → o backend extrai linha digitável + valor (endpoint read-only,
        # NÃO paga — rota provada: 422 sem arquivo). Preenche codigo_barras/valor no form.
        "attach": {"label": "Anexar boleto (PDF) — lê a linha digitável",
                   "endpoint": "/api/v1/financeiro/inter/payments/extrair-boleto-pdf",
                   "accept": "application/pdf,image/*", "okFlag": "encontrado",
                   "fills": {"codigo_barras": "linha_digitavel", "valor": "valor"}},
        # Câmera: lê o código de barras do boleto (Interleaved 2of5) e preenche o campo. NÃO paga.
        "scan": {"label": "Escanear código de barras (câmera)", "barcodeField": "codigo_barras"},
        "submit": {"endpoint": "/api/v1/redesign/action/pagar-boleto", "gated": True,
                   "confirm": "Isto vai PAGAR um boleto. Confira a conta escolhida — Cora é "
                              "a Patrimonial, Inter é a Eletrônica, são CNPJs diferentes. "
                              "Gerar o código OTP?",
                   "okMsg": "Boleto encaminhado."},
        "fields": [
            {"key": "codigo_barras", "label": "Código de barras / linha digitável*", "type": "text", "span": "span 2", "ph": "34191... (47-48 dígitos)"},
            {"key": "valor", "label": "Valor* (R$)", "type": "text", "span": "span 1", "ph": "1.234,56"},
            # SEM esse campo, todo boleto ia calado para o Inter — e o texto de
            # confirmação dizia "via Inter" como se fosse a única opção. Em 14/08/2026
            # o Jordan tentou duas vezes pagar VT da Patrimonial e as duas ordens
            # nasceram na Eletrônica. Sem valor pré-escolhido de propósito: a conta de
            # onde sai o dinheiro é escolha dele, não default do sistema.
            # ⚠️ NÃO repetir o seletor de conta aqui: `originField: True` já o desenha no
            # topo do formulário, e os DOIS escreviam no mesmo `origem`. A tela ficava com
            # duas perguntas idênticas — uma mostrando "Inter" e a outra "Selecione..." —
            # e o operador não tinha como saber qual valia. Visto na tela em 23/08/2026.
            {"key": "data", "label": "Data do pagamento (AAAA-MM-DD)", "type": "date", "span": "span 1"},
            {"key": "descricao", "label": "Descrição", "type": "text", "span": "span 2", "ph": "Ex.: Energia, ISS, fornecedor X"},
        ],
    }

    # ---- Enviar PIX / Transferência — money-out via InterPaymentService + OTP ----
    out["enviar-pix"] = {
        "title": "Enviar PIX / Transferência (Inter)",
        "sub": "Dinheiro que SAI — 2 etapas + OTP. Por chave PIX ou colando um PIX copia-e-cola.",
        "cta": "Preparar e gerar OTP", "type": "form",
        # A ação /action/enviar-pix EXIGE a conta de origem e recusa com 400:
        # «Escolha de qual conta sai o pagamento: Cora (Patrimonial) ou Inter (Eletrônica).»
        # Sem esta flag o renderizador não desenhava o seletor — a tela era impossível de
        # enviar: toda tentativa batia no 400 e não havia onde escolher a conta.
        # Medido em 14/09/2026. Boleto, DARF, GPS e TED já tinham a flag; o PIX era o único fora.
        "originField": True,
        "submit": {"endpoint": "/api/v1/redesign/action/enviar-pix", "gated": True,
                   "confirm": "Isto vai ENVIAR um PIX via Inter. Gerar o código OTP para o Jordan confirmar?",
                   "okMsg": "PIX enviado."},
        # Captura tipo banco: câmera (QR PIX) e colar copia-e-cola → decodifica (read-only, NÃO paga) e preenche.
        "scan": {"label": "Escanear QR PIX (câmera)", "pix": {
            "endpoint": "/api/v1/financeiro/inter/payments/decodificar-pix", "field": "brcode", "okFlag": "valido",
            "dynamicField": "pix_copia_e_cola", "fills": {"chave": "chave", "valor": "valor", "descricao": "nome"}}},
        "decode": {"endpoint": "/api/v1/financeiro/inter/payments/decodificar-pix", "field": "brcode", "okFlag": "valido",
                   "dynamicField": "pix_copia_e_cola", "fills": {"chave": "chave", "valor": "valor", "descricao": "nome"},
                   "ph": "Cole o PIX copia-e-cola (EMV)", "cta": "Ler PIX"},
        "fields": [
            {"key": "chave", "label": "Chave PIX", "type": "text", "span": "span 1", "ph": "CPF/CNPJ, e-mail, telefone, aleatória"},
            {"key": "pix_copia_e_cola", "label": "…ou PIX copia-e-cola", "type": "text", "span": "span 1", "ph": "cole o código EMV (opcional)"},
            {"key": "valor", "label": "Valor* (R$)", "type": "text", "span": "span 1", "ph": "1.234,56"},
            {"key": "data", "label": "Data (AAAA-MM-DD)", "type": "date", "span": "span 1"},
            {"key": "descricao", "label": "Descrição / favorecido", "type": "text", "span": "span 2", "ph": "Ex.: Fornecedor X, reembolso"},
        ],
    }

    # ---- Transferência TED — money-out via InterPaymentService + OTP ----
    out["transferir-ted"] = {
        "title": "Transferência TED (Inter ou Cora)",
        "sub": "Dinheiro que SAI — 2 etapas + OTP. Transferência por dados bancários. Pela Patrimonial (Cora) "
               "é a forma de pagar pessoas (o Cora não envia PIX).",
        "cta": "Preparar e gerar OTP", "type": "form",
        "originField": True,
        "submit": {"endpoint": "/api/v1/redesign/action/transferir-ted", "gated": True,
                   "confirm": "Isto vai TRANSFERIR (TED). Gerar o código OTP para o Jordan confirmar?",
                   "okMsg": "TED preparada."},
        "fields": [
            {"key": "nome", "label": "Favorecido (nome)", "type": "text", "span": "span 1", "ph": "Nome do titular"},
            {"key": "documento", "label": "CPF/CNPJ do favorecido", "type": "text", "span": "span 1", "ph": "só dígitos"},
            {"key": "banco", "label": "Banco (código)*", "type": "text", "span": "span 1", "ph": "Ex.: 001, 341, 077"},
            {"key": "agencia", "label": "Agência*", "type": "text", "span": "span 1", "ph": "0001"},
            {"key": "conta", "label": "Conta*", "type": "text", "span": "span 1", "ph": "12345-6"},
            {"key": "valor", "label": "Valor* (R$)", "type": "text", "span": "span 1", "ph": "1.234,56"},
            {"key": "data", "label": "Data (AAAA-MM-DD)", "type": "date", "span": "span 2"},
        ],
    }

    # ---- Pagar DARF / tributo — money-out via InterPaymentService + OTP ----
    out["pagar-darf"] = {
        "title": "Pagar DARF / tributo (Inter ou Cora)",
        "sub": "Dinheiro que SAI — 2 etapas + OTP. DARF (IRPJ, CSLL, COFINS, PIS, INSS). Pela Cora, "
               "informe o contribuinte e o vencimento (o Cora exige) e aprove no app.",
        "cta": "Preparar e gerar OTP", "type": "form",
        "originField": True,
        "submit": {"endpoint": "/api/v1/redesign/action/pagar-darf", "gated": True,
                   "confirm": "Isto vai PAGAR um DARF. Gerar o código OTP para o Jordan confirmar?",
                   "okMsg": "DARF preparado."},
        "fields": [
            {"key": "periodo_apuracao", "label": "Período de apuração* (AAAA-MM-DD)", "type": "date", "span": "span 1"},
            {"key": "codigo_receita", "label": "Código da receita*", "type": "text", "span": "span 1", "ph": "Ex.: 2100"},
            {"key": "numero_referencia", "label": "Número de referência", "type": "text", "span": "span 1", "ph": "opcional"},
            {"key": "valor", "label": "Valor* (R$)", "type": "text", "span": "span 1", "ph": "1.234,56"},
            {"key": "payer_name", "label": "Contribuinte (nome) — só Cora", "type": "text", "span": "span 1", "ph": "Razão social / nome"},
            {"key": "payer_document", "label": "CPF/CNPJ do contribuinte — só Cora", "type": "text", "span": "span 1", "ph": "só dígitos"},
            {"key": "vencimento", "label": "Vencimento (AAAA-MM-DD) — só Cora", "type": "date", "span": "span 1"},
            {"key": "data", "label": "Data do pagamento (AAAA-MM-DD)", "type": "date", "span": "span 1"},
        ],
    }

    # ---- Pagar GPS / INSS — money-out via Inter ou Cora + OTP ----
    out["pagar-gps"] = {
        "title": "Pagar GPS / INSS (Inter ou Cora)",
        "sub": "Dinheiro que SAI — 2 etapas + OTP. Guia da Previdência (INSS). Pela Cora, informe o "
               "contribuinte e o tipo de identificação (NIT/PIS/PASEP) e aprove no app.",
        "cta": "Preparar e gerar OTP", "type": "form",
        "originField": True,
        "submit": {"endpoint": "/api/v1/redesign/action/pagar-gps", "gated": True,
                   "confirm": "Isto vai PAGAR uma GPS (INSS). Gerar o código OTP para o Jordan confirmar?",
                   "okMsg": "GPS preparada."},
        "fields": [
            {"key": "competencia", "label": "Competência* (AAAA-MM)", "type": "text", "span": "span 1", "ph": "Ex.: 2026-06"},
            {"key": "codigo_pagamento", "label": "Código de pagamento*", "type": "text", "span": "span 1", "ph": "Ex.: 2100"},
            {"key": "valor", "label": "Valor* (R$)", "type": "text", "span": "span 1", "ph": "1.234,56"},
            {"key": "data", "label": "Data do pagamento (AAAA-MM-DD)", "type": "date", "span": "span 1"},
            {"key": "payer_name", "label": "Contribuinte (nome) — só Cora", "type": "text", "span": "span 1", "ph": "Razão social / nome"},
            {"key": "payer_document", "label": "Identidade (NIT/PIS/PASEP) — só Cora", "type": "text", "span": "span 1", "ph": "só dígitos"},
            {"key": "identification_type", "label": "Tipo de identificação — só Cora", "type": "select", "span": "span 2",
             "options": [{"value": "NIT", "label": "NIT"}, {"value": "PIS", "label": "PIS"}, {"value": "PASEP", "label": "PASEP"}]},
        ],
    }

    # ---- Emitir boleto (cobrança — dinheiro que ENTRA, sem OTP) ----
    out["emitir-boleto"] = {
        "title": "Emitir boleto (Inter)",
        "sub": "Cobrança que ENTRA — gera um boleto no Inter. Não move dinheiro seu; cria a cobrança.",
        "cta": "Emitir boleto", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/emitir-boleto",
                   "confirm": "Emitir um boleto de cobrança no Inter?", "okMsg": "Boleto emitido."},
        "fields": [
            {"key": "valor", "label": "Valor* (R$)", "type": "text", "span": "span 1", "ph": "1.234,56"},
            {"key": "vencimento", "label": "Vencimento* (AAAA-MM-DD)", "type": "date", "span": "span 1"},
            {"key": "payer_name", "label": "Pagador — nome*", "type": "text", "span": "span 1", "ph": "Nome/razão social"},
            {"key": "payer_document", "label": "Pagador — CPF/CNPJ*", "type": "text", "span": "span 1", "ph": "só dígitos"},
            {"key": "descricao", "label": "Descrição", "type": "text", "span": "span 2", "ph": "Ex.: Serviço de segurança — jul/2026"},
        ],
    }

    # ---- Cobrar PIX (cobrança — dinheiro que ENTRA, sem OTP) ----
    out["cobrar-pix"] = {
        "title": "Cobrar PIX (Inter)",
        "sub": "Cobrança que ENTRA — gera um PIX copia-e-cola/QR no Inter. Não move dinheiro seu.",
        "cta": "Gerar cobrança PIX", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/cobrar-pix",
                   "confirm": "Gerar uma cobrança PIX no Inter?", "okMsg": "Cobrança PIX gerada."},
        "fields": [
            {"key": "valor", "label": "Valor* (R$)", "type": "text", "span": "span 1", "ph": "1.234,56"},
            {"key": "expiracao_horas", "label": "Validade (horas)", "type": "text", "span": "span 1", "ph": "24"},
            {"key": "payer_name", "label": "Pagador — nome", "type": "text", "span": "span 1", "ph": "opcional"},
            {"key": "payer_document", "label": "Pagador — CPF/CNPJ", "type": "text", "span": "span 1", "ph": "opcional"},
            {"key": "descricao", "label": "Descrição", "type": "text", "span": "span 2", "ph": "Ex.: Mensalidade jul/2026"},
        ],
    }

    # ---- Cancelar boleto emitido (sem saída de dinheiro) ----
    out["cancelar-boleto"] = {
        "title": "Cancelar boleto (Inter)",
        "sub": "Cancela um boleto de cobrança já emitido. Motivo: ACERTOS / APEDIDODOCLIENTE / PAGODIRETOAOCLIENTE.",
        "cta": "Cancelar boleto", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/cancelar-boleto",
                   "confirm": "Cancelar este boleto no Inter?", "okMsg": "Boleto cancelado."},
        "fields": [
            {"key": "boleto_id", "label": "ID / nosso número do boleto*", "type": "text", "span": "span 2", "ph": "identificador do boleto"},
            {"key": "motivo", "label": "Motivo", "type": "text", "span": "span 2", "ph": "ACERTOS (padrão)"},
        ],
    }

    # ---- Cancelar pagamento agendado (antes de executar; sem saída de dinheiro) ----
    out["cancelar-pagamento"] = {
        "title": "Cancelar pagamento agendado (Inter)",
        "sub": "Cancela um pagamento que foi agendado e ainda não foi executado.",
        "cta": "Cancelar pagamento", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/cancelar-pagamento",
                   "confirm": "Cancelar este pagamento agendado?", "okMsg": "Pagamento cancelado."},
        "fields": [
            {"key": "payment_id", "label": "ID do pagamento*", "type": "text", "span": "span 2", "ph": "identificador do pagamento"},
        ],
    }

    # ---- Pagamentos Inter (D7) — tela NOVA (paridade com o clássico "Pagamentos Inter D7").
    # Leitura de inter_payments; COMPROVANTE (PDF) por-linha SÓ nos confirmados (rota curl-provada
    # 200: /api/v1/financeiro/inter/payments/{id}/comprovante; 409 se não confirmado). Ação de PAGAR
    # segue no fluxo gated (enviar-pix etc.) — aqui é leitura + comprovante.
    _ip_tone = {"confirmado": "ok", "executado": "ok", "preparado": "warn", "cancelado": "mut", "erro": "bad"}
    await safe("pagamentos-inter", tbl(
        "Pagamentos Inter", f"{await _scalar(db, 'SELECT count(*) FROM inter_payments')} pagamentos (Banco Inter)", "—",
        ["Tipo", "Destinatário", "Valor", "Data", "Status"], "1fr 1.8fr 1fr 1fr 0.9fr",
        "SELECT id, coalesce(payment_type,'—'), "
        "coalesce(destinatario->>'nome_recebedor', destinatario->>'chave', left(destinatario->>'codigo_barras',22), '—'), "
        "valor, data_pagamento, coalesce(status,'—') "
        "FROM inter_payments ORDER BY created_at DESC NULLS LAST LIMIT 300",
        lambda r: [t((r[1] or '—').replace('_', ' ').capitalize()), t((r[2] or '—')[:40], 600, "#0F1B3A"),
                   t(brl(r[3]) if r[3] is not None else '—', 600), t(_fmtdate(r[4])),
                   b((r[5] or '—').capitalize(), _ip_tone.get((r[5] or '').lower(), "info"))],
        docsfn=lambda r: [doc("Comprovante", f"/api/v1/financeiro/inter/payments/{r[0]}/comprovante", fmt="pdf")]
        if (r[5] or '').lower() in ("confirmado", "executado") else []))

    # ---- DOCUMENTOS (botões abrir HTML + baixar PDF) — paridade com o clássico. Rotas curl-provadas
    # 200 application/pdf. Nível-tela (sem id) nas telas de relatório/aging; conciliação = modo json.
    from datetime import date as _dt
    _ano = _dt.today().year
    try:
        if isinstance(out.get("relatorios"), dict):
            out["relatorios"]["docs"] = [
                doc("DRE (PDF)", f"/api/v1/financial/relatorios/dre/pdf?ano={_ano}", fmt="pdf", gate="financeiro"),
                doc("Balancete (PDF)", f"/api/v1/financial/relatorios/balancete/pdf?ano={_ano}", fmt="pdf", gate="financeiro"),
                doc("Fluxo de Caixa (PDF)", f"/api/v1/financial/relatorios/fluxo-caixa/pdf?ano={_ano}", fmt="pdf", gate="financeiro"),
            ]
        if isinstance(out.get("contas-pagar"), dict):
            out["contas-pagar"]["docs"] = [doc("Aging Contas a Pagar (PDF)", "/api/v1/financial/payables/aging/pdf", fmt="pdf", gate="financeiro")]
        if isinstance(out.get("contas-receber"), dict):
            out["contas-receber"]["docs"] = [doc("Aging Contas a Receber (PDF)", "/api/v1/financial/receivables/aging/pdf", fmt="pdf", gate="financeiro")]
    except Exception:  # noqa: BLE001 — documentos não derrubam o módulo
        pass

    # F1 — piloto Receber: aging KPIs, clientes reais (customers), régua e recorrência read-only.
    from modules.operacional.controllers.redesign_builders._fin_receber import build_receber
    await build_receber(db, out)

    # F2 — Bancos & Conciliação: contas reais + conciliação bancária de extrato.
    from modules.operacional.controllers.redesign_builders._fin_bancos import build_bancos
    await build_bancos(db, out)

    # F3 — Pagar: aging KPIs, fila de aprovação (leitura) e audit log Inter.
    from modules.operacional.controllers.redesign_builders._fin_pagar import build_pagar
    await build_pagar(db, out)

    # F4 — Visão Geral: projeção 30/60/90d, insights IA e DRE inline (reuso exato dos endpoints).
    from modules.operacional.controllers.redesign_builders._fin_visao import build_visao
    await build_visao(db, out)

    # F5 — Contabilidade real: plano de contas, lançamentos D/C e balancete.
    from modules.operacional.controllers.redesign_builders._fin_contabil import build_contabil
    await build_contabil(db, out)

    # F6 — Custeio ABC real (reuso exato do custeio_controller).
    from modules.operacional.controllers.redesign_builders._fin_custos import build_custos
    await build_custos(db, out)

    # F7 — Compras & Estoque reais (fontes purchase_*/fin_stock_*).
    from modules.operacional.controllers.redesign_builders._fin_cadastros import build_cadastros
    await build_cadastros(db, out)

    # F0 — fundação: compõe os 7 grupos (tabs) e stub-a as telas antigas (deep-link preservado).
    from modules.operacional.controllers.redesign_builders._fin_grupos import montar_grupos
    # ---- NFS-e x CONTA A RECEBER (o furo: receita emitida sem titulo) ------------------
    out["gerar-contas-de-nfse"] = {
        "title": "Gerar contas a receber das NFS-e",
        "sub": "Cria uma conta a receber por NFS-e emitida não cancelada. Idempotente: rodar de "
               "novo não duplica. Comece em Simular para ver os números antes de gravar.",
        "cta": "Executar", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/gerar-contas-de-nfse", "okMsg": "Processado",
                   "confirm": "Gravar cria contas a receber de verdade e muda inadimplência e DSO. Confirmar?"},
        "fields": [
            {"key": "competencia", "label": "Competência", "type": "text", "span": "span 1",
             "ph": "Ex.: 2026-07 · em branco = todas"},
            {"key": "dry_run", "label": "Modo*", "type": "select", "span": "span 1",
             "ph": "Simular primeiro", "options": [
                 {"value": "sim", "label": "Simular (não grava)"},
                 {"value": "nao", "label": "Gravar de verdade"}]},
        ],
    }
    await safe("nfse-a-receber", tbl(
        "NFS-e × conta a receber",
        "Cada nota emitida e se ela já virou título. Sem conta = receita reconhecida sem "
        "título, logo fora do aging, da inadimplência e do DSO.",
        "—", ["Competência", "Nº", "Tomador", "Bruto", "Líquido", "Conta a receber"],
        "0.9fr 0.7fr 1.9fr 1fr 1fr 1.2fr",
        """
        SELECT coalesce(n.competencia,'—'), coalesce(n.numero,'—'), coalesce(n.tomador_nome,'—'),
               n.valor_servicos, n.valor_liquido,
               CASE WHEN r.id IS NULL THEN 'SEM CONTA' ELSE coalesce(r.status,'criada') END
        FROM nfse_emitidas_nacional n
        LEFT JOIN receivable_accounts r ON r.document_number = n.chave_acesso
        WHERE coalesce(n.cancelada,false) = false
        ORDER BY (r.id IS NULL) DESC, n.data_emissao DESC
        LIMIT 400
        """,
        lambda r: [t(r[0], 600), t(r[1]), t(r[2], 600, "#0F1B3A"),
                   t(brl(float(r[3] or 0))), t(brl(float(r[4] or 0)), 600),
                   b("SEM CONTA", "bad") if r[5] == "SEM CONTA" else b(r[5], "ok")]))
    if isinstance(out.get("nfse-a-receber"), dict):
        out["nfse-a-receber"]["filterCol"] = 0
        out["nfse-a-receber"]["filterLabel"] = "Competência"
        out["nfse-a-receber"]["cta"] = "Gerar contas a receber"
        out["nfse-a-receber"]["ctaTo"] = "gerar-contas-de-nfse"

    # ---- DIÁRIAS SOBREPOSTAS À FOLHA CLT (controle contínuo, era levantamento avulso) ----
    # Diarista que virou CLT e continuou recebendo diária. Nem toda sobreposição é erro:
    # CLT cobrindo posto na FOLGA é legítimo. O que denuncia duplicidade é ter BATIDO PONTO
    # como CLT no MESMO dia. Ordem: a_revisar primeiro (ainda dá p/ barrar antes de pagar),
    # depois quem bateu ponto. O lote do dia 15 cobre a competência do mês ANTERIOR — é assim
    # que o dia se liga ao pagamento (programar_diarias_mensais: dia 15 do mês seguinte).
    await safe("diarias-sobrepostas", tbl(
        "Diárias e VT/VR — divergências",
        "Três divergências num lugar só. SOBREPOSTO = lançado depois da admissão CLT ('Ponto "
        "CLT = SIM' é o caso grave: trabalhou como CLT e recebeu como diarista no mesmo dia; o "
        "CLT já recebe VT pela folha). ÓRFÃO = VT/VR cujo dia não tem mais diária lançada — "
        "excluir a diária não apaga o VT/VR do dia. 'a revisar' ainda não foi pago: dá para barrar.",
        "—", ["Competência", "Colaborador", "Tipo", "Dia", "Posto", "Valor", "Ponto CLT", "Pagamento"],
        "0.8fr 1.7fr 0.8fr 0.7fr 1.3fr 0.8fr 0.8fr 0.9fr",
        """
        SELECT comp, nome, tipo, dia, posto, valor, ponto, pagamento, ref, kind FROM (
            -- DIÁRIA: o dia vem de diaria_lancamentos; o status, do lote do dia 15 da
            -- competência SEGUINTE (programar_diarias_mensais).
            SELECT to_char(l.data,'MM/YYYY') AS comp, e.nome AS nome, 'Diária' AS tipo,
                   to_char(l.data,'DD/MM') AS dia, l.posto AS posto, l.valor AS valor,
                   CASE WHEN pt.n > 0 THEN 'SIM' ELSE 'não' END AS ponto,
                   coalesce(pg.status, 'não programado') AS pagamento,
                   l.id AS ref, 'diaria' AS kind, l.data AS ord
            FROM diaria_lancamentos l
            JOIN diaria_diaristas d ON d.id = l.diarista_id
            JOIN employees e
              ON replace(replace(coalesce(e.cpf,''),'.',''),'-','')
               = replace(replace(coalesce(d.cpf,''),'.',''),'-','')
            LEFT JOIN LATERAL (
                SELECT count(*) AS n FROM gp_clock_punches c
                WHERE c.employee_id = e.id AND c.punch_timestamp::date = l.data) pt ON true
            LEFT JOIN LATERAL (
                SELECT p.status FROM financial_pagamentos_diaristas p
                WHERE upper(btrim(p.beneficiario)) = upper(btrim(e.nome)) AND p.tipo = 'diaria_mensal'
                  AND p.data_referencia = ((date_trunc('month', l.data) + interval '1 month')::date + 14)
                LIMIT 1) pg ON true
            WHERE e.status = 'ativo' AND coalesce(e.is_homologacao,false) = false
              AND e.data_admissao IS NOT NULL AND l.data >= e.data_admissao
            UNION ALL
            -- VT/VR: a linha JÁ é o pagamento (status próprio, um por dia). Posto sai da
            -- diária do mesmo dia, quando houver.
            SELECT to_char(v.data_referencia,'MM/YYYY'), e.nome, 'VT+VR',
                   to_char(v.data_referencia,'DD/MM'), coalesce(lp.posto,'—'), v.valor,
                   CASE WHEN pt.n > 0 THEN 'SIM' ELSE 'não' END, v.status,
                   v.id, 'vtvr', v.data_referencia
            FROM financial_pagamentos_diaristas v
            JOIN employees e ON upper(btrim(e.nome)) = upper(btrim(v.beneficiario))
            LEFT JOIN LATERAL (
                SELECT count(*) AS n FROM gp_clock_punches c
                WHERE c.employee_id = e.id AND c.punch_timestamp::date = v.data_referencia) pt ON true
            LEFT JOIN LATERAL (
                SELECT l2.posto FROM diaria_lancamentos l2
                JOIN diaria_diaristas d2 ON d2.id = l2.diarista_id
                WHERE l2.data = v.data_referencia
                  AND replace(replace(coalesce(d2.cpf,''),'.',''),'-','')
                    = replace(replace(coalesce(e.cpf,''),'.',''),'-','') LIMIT 1) lp ON true
            WHERE v.tipo = 'vt_vr' AND v.status <> 'cancelado'
              AND e.status = 'ativo' AND coalesce(e.is_homologacao,false) = false
              AND e.data_admissao IS NOT NULL AND v.data_referencia >= e.data_admissao
            UNION ALL
            -- VT/VR ÓRFÃO: não existe mais diária daquela pessoa naquele dia. Independe de ser
            -- CLT — é a sobra da exclusão do lançamento, que não propaga ao VT/VR.
            SELECT to_char(v.data_referencia,'MM/YYYY'), v.beneficiario, 'VT+VR órfão',
                   to_char(v.data_referencia,'DD/MM'), '—', v.valor, '—', v.status,
                   v.id, 'vtvr', v.data_referencia
            FROM financial_pagamentos_diaristas v
            WHERE v.tipo = 'vt_vr' AND v.status <> 'cancelado'
              AND NOT EXISTS (
                SELECT 1 FROM diaria_lancamentos l JOIN diaria_diaristas d ON d.id = l.diarista_id
                WHERE l.data = v.data_referencia
                  AND upper(btrim(d.nome)) = upper(btrim(v.beneficiario)))
        ) u
        ORDER BY (pagamento IN ('a_revisar','sem_pix')) DESC, (ponto = 'SIM') DESC, ord DESC
        LIMIT 800
        """,
        lambda r: [t(r[0], 600), t(r[1], 600, "#0F1B3A", initials(r[1] or "")),
                   b(r[2], {"Diária": "info", "VT+VR": "mut"}.get(r[2], "warn")),
                   t(r[3], 600), t(r[4]), t(brl(float(r[5] or 0)), 600),
                   b("SIM", "bad") if r[6] == "SIM" else t("não", 500, "#64748B"),
                   b({"a_revisar": "a revisar", "sem_pix": "sem PIX", "pago": "PAGO"}.get(r[7], r[7]),
                     "warn" if r[7] in ("a_revisar", "sem_pix") else ("bad" if r[7] == "pago" else "mut"))],
        actionsfn=lambda r: ([] if r[7] == "pago" else [{
            "title": f"Cancelar {r[2]} — {r[1]} em {r[3]}",
            "endpoint": "/api/v1/redesign/action/cancelar-diaria-sobreposta",
            "method": "POST", "btnLabel": f"Cancelar {r[2]}", "btnStyle": "outline",
            "submitLabel": "Cancelar", "okMsg": "Cancelado. Recarregue a tela.",
            "fixed": {"ref": r[8],
                      "kind": "vtvr_orfao" if r[2] == "VT+VR órfão" else r[9]},
            "fields": [
                {"key": "motivo", "label": "Motivo do cancelamento*", "type": "textarea",
                 "span": "span 2",
                 "ph": "Ex.: já pago pela folha CLT do mesmo dia (bateu ponto)."},
            ]}])))
    if isinstance(out.get("diarias-sobrepostas"), dict):
        # 7 = índice da CÉLULA renderizada (Pagamento); ref/kind vêm no SELECT mas não viram célula.
        out["diarias-sobrepostas"]["filterCol"] = 7
        out["diarias-sobrepostas"]["filterLabel"] = "Pagamento"

    # montar_grupos(out) fica no FIM do build (antes do return): as 16 telas definidas abaixo
    # ("fios soltos", CFO, justificativas…) são abas de grupo e ficavam VAZIAS porque os grupos
    # eram montados antes de elas existirem (medido 07/09/2026 pelo navegador: aba em branco).

    # ── Fios soltos do financeiro (2026-08-10) ─────────────────────────────────────
    # DE FORA de proposito: conciliar/auto e bank-reconciliations/auto JA tem botao pela
    # acao /redesign/action/conciliar-auto (nao duplicar); auto-criar-payables e
    # ai/billing/contrato-ativado sao gatilhos de integracao, nao fluxo de tela; e o que
    # move DINHEIRO segue no fluxo com OTP, fora daqui.
    out["cfo-perguntar"] = {
        "title": "Consultor CFO",
        "sub": "Pergunta ancorada no razao, no fluxo e nos contratos reais. E consulta - "
               "não lança, não paga, não baixa nada.",
        "cta": "Perguntar", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/cfo/perguntar", "okMsg": "Consulta respondida",
                   "showResult": True},
        "fields": [
            {"key": "area", "label": "Area*", "type": "text", "span": "span 2",
             "ph": "Ex.: margem, inadimplencia, fluxo de caixa"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["cfo-perguntar-arquivo"] = {
        "title": "Consultor CFO - analisando um anexo",
        "sub": "Anexe extrato, boleto ou planilha e pergunte sobre o documento.",
        "cta": "Analisar", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/cfo/perguntar-arquivo",
                   "multipart": True, "query": True,
                   "okMsg": "Análise concluida", "showResult": True},
        "fields": [
            {"key": "arquivo", "label": "Arquivo*", "type": "file", "span": "span 2"},
            {"key": "area", "label": "Area", "type": "text", "span": "span 2"},
            {"key": "pergunta", "label": "Pergunta*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["pricing-calcular"] = {
        "title": "Calcular preço de serviço",
        "sub": "Preço sugerido a partir do custo real (CCT, escala, localização). Cálculo - "
               "não grava proposta.",
        "cta": "Calcular", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/ai/pricing/calculate",
                   "okMsg": "Preço calculado", "showResult": True},
        "fields": [
            {"key": "tipo", "label": "Tipo de serviço", "type": "text", "span": "span 1",
             "ph": "Ex.: portaria"},
            {"key": "quantidade", "label": "Quantidade de postos", "type": "number",
             "span": "span 1", "ph": "1"},
            {"key": "escala", "label": "Escala", "type": "text", "span": "span 1", "ph": "12x36"},
            {"key": "localizacao", "label": "Localizacao", "type": "text", "span": "span 1",
             "ph": "Manaus"},
        ],
    }
    out["custo-registrar"] = {
        "title": "Registrar custo de contrato",
        "sub": "Lança o custo real do contrato na competência - e o que alimenta a margem.",
        "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/ai/costing/registrar", "okMsg": "Custo registrado"},
        "fields": [
            {"key": "tipo", "label": "Tipo*", "type": "text", "span": "span 1",
             "ph": "Ex.: folha, material"},
            {"key": "mes", "label": "Competencia*", "type": "text", "span": "span 1",
             "ph": "AAAA-MM"},
            {"key": "custo_total", "label": "Custo total (R$)*", "type": "number", "span": "span 1"},
            {"key": "margem_contratual", "label": "Margem contratual (%)", "type": "number",
             "span": "span 1"},
            {"key": "contrato_id", "label": "Contrato (id)", "type": "text", "span": "span 2"},
        ],
    }
    out["custo-recorrente-novo"] = {
        "title": "Novo custo recorrente",
        "sub": "Despesa que se repete todo mes (aluguel, software, seguro). Entra no fluxo "
               "projetado.",
        "cta": "Cadastrar", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/cfo/custos-recorrentes",
                   "okMsg": "Custo recorrente cadastrado"},
        "fields": [
            {"key": "categoria", "label": "Categoria*", "type": "text", "span": "span 1",
             "ph": "Ex.: software"},
            {"key": "valor", "label": "Valor mensal (R$)*", "type": "number", "span": "span 1"},
            {"key": "dia_vencimento", "label": "Dia do vencimento", "type": "number",
             "span": "span 1", "ph": "10"},
            {"key": "parcelas_total", "label": "Total de parcelas", "type": "number",
             "span": "span 1", "ph": "vazio = sem fim"},
            {"key": "descricao", "label": "Descricao*", "type": "text", "span": "span 2"},
            {"key": "observacao", "label": "Observacao", "type": "textarea", "span": "span 2"},
        ],
    }
    out["cashflow-sync"] = {
        "title": "Sincronizar fluxo de caixa",
        "sub": "Recalcula o fluxo a partir de recebiveis e pagáveis. So recalcula - não "
               "cria nem baixa lançamento.",
        "cta": "Sincronizar", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/cashflow/sync", "okMsg": "Fluxo sincronizado",
                   "showResult": True},
        "fields": [],
    }
    out["beneficiarios-seed"] = {
        "title": "Semear beneficiários",
        "sub": "Carrega a base de beneficiários de pagamento. Idempotente. NAO paga ninguem.",
        "cta": "Semear", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/beneficiarios/seed",
                   "okMsg": "Beneficiários semeados", "showResult": True},
        "fields": [],
    }
    out["estoque-saida"] = {
        "title": "Registrar saída de estoque",
        "sub": "Baixa material do estoque real, com o serviço que consumiu.",
        "cta": "Registrar saída", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/inventory/real/saida", "okMsg": "Saída registrada"},
        "fields": [
            {"key": "item_code", "label": "Código do item*", "type": "text", "span": "span 1"},
            {"key": "quantidade", "label": "Quantidade*", "type": "number", "span": "span 1"},
            {"key": "servico_ref", "label": "Serviço / OS", "type": "text", "span": "span 1"},
            {"key": "nfse_id", "label": "NFS-e (id)", "type": "text", "span": "span 1"},
            {"key": "motivo", "label": "Motivo", "type": "textarea", "span": "span 2"},
        ],
    }
    
    # Custos recorrentes (2026-08-10): o DELETE leva {custo_id} no CAMINHO -> acao por LINHA.
    # A tela de criar ja existe acima; faltava ver e remover.
    await safe("custos-recorrentes-lista", tbl(
        "Custos recorrentes", "Despesas que se repetem todo mes", "Novo custo",
        ["Categoria", "Descricao", "Valor", "Vencimento", "Estado"],
        "1.2fr 2fr 1fr 0.9fr 0.9fr",
        "SELECT id, coalesce(categoria,'—'), coalesce(descricao,'—'), coalesce(valor,0), "
        "dia_vencimento, parcelas_pagas, parcelas_total, coalesce(ativo,true) "
        # SEM filtro por ativo: os 3 registros de hoje estao inativos, e esconde-los deixaria
        # a aba vazia mentindo que nao existe custo recorrente nenhum. Melhor mostrar com o
        # estado a vista; remover so aparece no que esta ativo.
        "FROM financial_custos_recorrentes ORDER BY coalesce(ativo,true) DESC, valor DESC "
        "NULLS LAST LIMIT 200",
        lambda r: [b((r[1] or '—').capitalize(), "info"), t((r[2] or '—')[:60], 600, "#0F1B3A"),
                   t(brl(r[3]), 600),
                   t(f"dia {int(r[4])}" if r[4] else "—"),
                   b("Ativo", "ok") if r[7] else b("Inativo", "mut")],
        actionsfn=lambda r: None if not r[7] else [
            {"title": f"Remover o custo recorrente: {r[2]}",
             "sub": "Para de projetar esta despesa no fluxo. Não apaga lançamento ja feito.",
             "endpoint": f"/api/v1/financial/cfo/custos-recorrentes/{r[0]}",
             "method": "DELETE", "btnLabel": "Remover", "submitLabel": "Remover custo",
             "btnStyle": "outline", "okMsg": "Custo removido. Recarregue.", "fields": []},
        ]))
    if isinstance(out.get("custos-recorrentes-lista"), dict):
        out["custos-recorrentes-lista"]["ctaTo"] = "custo-recorrente-novo"

    # ── Ultimo lote de fios soltos do financeiro (2026-08-10) ───────────────────────
    # payable/auto-criar e payables/auto-criar (singular e plural) fazem a MESMA coisa —
    # ligo UMA. Duas telas identicas seria a duplicacao que o Jordan proibiu.
    out["orcamento-kv"] = {
        "title": "Orçado do mes",
        "sub": "Define o valor orçado por chave. E o que a comparacao orçado x realizado "
               "usa — sem isto ela cai no valor fixo antigo.",
        "cta": "Salvar", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/relatorios/orcamentos-kv", "method": "PUT",
                   "okMsg": "Orçado salvo", "showResult": True},
        "fields": [
            {"key": "chave", "label": "Chave*", "type": "text", "span": "span 1",
             "ph": "ex.: 2026-08 ou folha:2026-08"},
            {"key": "valor", "label": "Valor orçado (R$)*", "type": "number", "span": "span 1"},
        ],
    }
    out["billing-contrato-ativado"] = {
        "title": "Registrar faturamento de contrato ativado",
        "sub": "Abre o faturamento de um contrato que entrou em vigencia. Use quando a "
               "ativacao aconteceu por fora e o financeiro não acompanhou.",
        "cta": "Registrar", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/ai/billing/contrato-ativado",
                   "okMsg": "Faturamento registrado", "showResult": True},
        "fields": [
            {"key": "contrato_id", "label": "Contrato (id)*", "type": "text", "span": "span 2"},
            {"key": "cliente_nome", "label": "Cliente", "type": "text", "span": "span 1"},
            {"key": "valor_mensal", "label": "Valor mensal (R$)*", "type": "number", "span": "span 1"},
            {"key": "tipo_servico", "label": "Tipo de serviço*", "type": "text", "span": "span 2",
             "ph": "ex.: portaria, seguranca eletrônica"},
        ],
    }
    out["payables-auto-criar"] = {
        "title": "Criar contas a pagar das NFS-e recebidas",
        "sub": "Varre as NFS-e de entrada sem pagável vinculado e cria o pagável de cada uma. "
               "So LANÇA a conta — não paga nada.",
        "cta": "Criar pagáveis", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/payables/auto-criar",
                   "okMsg": "Pagáveis criados", "showResult": True,
                   "confirm": "Cria conta a pagar para TODA NFS-e de entrada sem pagável. Confirma?"},
        "fields": [],
    }
    out["just-registrar"] = {
        "title": "Justificar uma transação",
        "sub": "Explica a que se refere um lançamento do extrato. E o que tira a transação "
               "da lista de pendentes.",
        "cta": "Justificar", "type": "form",
        "submit": {"endpoint": "/api/v1/justificativa/registrar", "okMsg": "Justificativa registrada"},
        "fields": [
            {"key": "transacao_id", "label": "Transação (id)*", "type": "text", "span": "span 2"},
            {"key": "categoria", "label": "Categoria*", "type": "text", "span": "span 1",
             "ph": "ex.: folha, tributo, fornecedor"},
            {"key": "responsavel", "label": "Responsavel", "type": "text", "span": "span 1"},
            {"key": "descricao", "label": "Descricao*", "type": "textarea", "span": "span 2"},
        ],
    }
    out["just-classificar"] = {
        "title": "Classificar transações automaticamente",
        "sub": "Sugere categoria para as transações sem justificativa. Deixe APLICAR em não "
               "para so ver a sugestão antes de gravar.",
        "cta": "Classificar", "type": "form",
        "submit": {"endpoint": "/api/v1/justificativa/classificar-auto", "query": True,
                   "okMsg": "Classificacao processada", "showResult": True,
                   "confirm": "Se você marcou APLICAR, as categorias são gravadas agora. Confirma?"},
        "fields": [
            {"key": "aplicar", "label": "Aplicar de verdade?", "type": "select", "span": "span 2",
             "ph": "Não — so sugerir (padrão)",
             "options": [{"value": "false", "label": "Não — so mostrar a sugestão"},
                         {"value": "true", "label": "SIM — gravar as categorias"}]},
            {"key": "apenas_sem_categoria", "label": "So as sem categoria?", "type": "select",
             "span": "span 1", "ph": "Sim",
             "options": [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Nao"}]},
            {"key": "responsavel", "label": "Responsavel", "type": "text", "span": "span 1"},
        ],
    }
    out["just-alertar"] = {
        "title": "Alertar pendências de justificativa",
        "sub": "Avisa quem precisa justificar transação parada. Notificação interna — vai "
               "para o sino, não para fora.",
        "cta": "Alertar", "type": "form",
        "submit": {"endpoint": "/api/v1/justificativa/alertar", "okMsg": "Alertas enviados",
                   "showResult": True},
        "fields": [],
    }

    # nfse-entrada-payaveis / auto-payaveis / sync-prestador APOSENTADAS 08/09/2026: liam a tabela
    # legada nfse_entrada (10 notas, todas com pagavel). O caminho real e registrar-obrigacoes
    # (payable_sources_service sobre nfse_tomadas_nacional) e o sync e o beat sincronizar_nfse_nacional.

    from modules.operacional.controllers.redesign_builders._fin_ligar4 import build_ligar4
    await build_ligar4(db, out)  # lote 4 LIGAR (08/09) — antes de montar_grupos
    montar_grupos(out)   # SEMPRE por último — ver comentário acima
    return out


# ── ESCRITA (router incluído pelo registry). Dinheiro que SAI = SEMPRE gate humano.
router = APIRouter()


def _require_financeiro_dep(current_user: CurrentActiveUser) -> None:
    """Trava de CARGO p/ dinheiro que SAI: só quem tem module:financeiro (ou admin/all).
    Roda ANTES do corpo (dependency), então bloqueia não-financeiro antes de qualquer OTP.
    O OTP continua sendo a 2ª parede (pagamento real); esta é a 1ª (quem pode iniciar)."""
    from core.auth.module_scope import user_has_module
    if not user_has_module(current_user, "financeiro"):
        raise HTTPException(status_code=403, detail="Ação financeira (dinheiro que sai) restrita ao módulo Financeiro.")


@router.post("/action/cancelar-diaria-sobreposta", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_cancelar_diaria_sobreposta(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db),
) -> dict:
    """Cancela UMA diária OU UM VT/VR que se sobrepõe à folha CLT da mesma pessoa.

    NÃO é um "apagar qualquer coisa": o servidor RE-VERIFICA a sobreposição (a pessoa tem
    de ser CLT ativo e o lançamento posterior à admissão) antes de agir. Sem isso o botão
    viraria delete genérico — o id vem do front e id se falsifica.

    Diária → `diarias_service.excluir_lancamento` (só status='lancado').
    VT/VR  → `pagamentos_diaristas_service.cancelar` (só a_revisar/sem_pix). Esse devolve
    ok:True mesmo sem alterar linha, então conferimos o status DEPOIS — não mentir é a regra.

    Não move dinheiro: IMPEDE uma saída futura. Registra em audit_logs com identidade real.
    """
    from sqlalchemy import text as _sql

    kind = (payload.get("kind") or "diaria").strip().lower()
    try:
        ref = int(str(payload.get("ref") or payload.get("lancamento_id") or "").strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="Lançamento inválido.")
    motivo = (payload.get("motivo") or "").strip()
    if len(motivo) < 5:
        raise HTTPException(status_code=422, detail="Descreva o motivo do cancelamento (mín. 5 caracteres).")
    if kind not in ("diaria", "vtvr", "vtvr_orfao"):
        raise HTTPException(status_code=422, detail="Tipo inválido.")

    recusa = ("Este lançamento não é uma sobreposição à folha CLT — cancelamento recusado. "
              "Para excluir um lançamento comum use o Operacional.")

    if kind == "diaria":
        row = (await db.execute(_sql(
            "SELECT l.data, l.posto, l.valor, e.nome, e.data_admissao, e.id, "
            "       (SELECT count(*) FROM gp_clock_punches c "
            "          WHERE c.employee_id = e.id AND c.punch_timestamp::date = l.data) "
            "FROM diaria_lancamentos l "
            "JOIN diaria_diaristas d ON d.id = l.diarista_id "
            "JOIN employees e ON replace(replace(coalesce(e.cpf,''),'.',''),'-','') "
            "                  = replace(replace(coalesce(d.cpf,''),'.',''),'-','') "
            "WHERE l.id = :i AND e.status = 'ativo' AND coalesce(e.is_homologacao,false) = false "
            "  AND e.data_admissao IS NOT NULL AND l.data >= e.data_admissao"), {"i": ref})).first()
        if not row:
            raise HTTPException(status_code=422, detail=recusa)
        dia, posto, valor, nome_e, adm, _eid, n_ponto = row

        from modules.operacional.diaristas import diarias_service as _dsvc

        res = await _dsvc.excluir_lancamento(db, ref)
        if not res.get("ok"):
            raise HTTPException(status_code=int(res.get("http_status", 422)),
                                detail=res.get("mensagem", "Não foi possível cancelar a diária."))
        rotulo = "Diária"
        cascata = int(res.get("vt_vr_cancelado", 0) or 0)
    elif kind == "vtvr_orfao":
        # ÓRFÃO é outra verificação: NÃO exige vínculo CLT (o beneficiário pode ser diarista
        # puro, e o nome do cadastro nem sempre casa com o do funcionário — 'ADAILSON SERRA'
        # x 'ADAILSON SERRA ALVES'). O que se prova aqui é a ORFANDADE: não existe diária
        # daquela pessoa naquele dia. Sem este caminho o botão da linha de órfão era
        # recusado pela trava de sobreposição.
        row = (await db.execute(_sql(
            "SELECT v.data_referencia, v.valor, v.beneficiario, v.status "
            "FROM financial_pagamentos_diaristas v "
            "WHERE v.id = :i AND v.tipo = 'vt_vr' "
            "  AND NOT EXISTS (SELECT 1 FROM diaria_lancamentos l "
            "                  JOIN diaria_diaristas d ON d.id = l.diarista_id "
            "                  WHERE l.data = v.data_referencia "
            "                    AND upper(btrim(d.nome)) = upper(btrim(v.beneficiario)))"),
            {"i": ref})).first()
        if not row:
            raise HTTPException(
                status_code=422,
                detail="Este VT/VR não está órfão (existe diária lançada nesse dia) — "
                       "cancelamento recusado.")
        dia, valor, nome_e, st_antes = row
        posto, adm, n_ponto, cascata = "—", None, 0, 0
        if st_antes == "pago":
            raise HTTPException(status_code=422, detail="VT/VR já PAGO não pode ser cancelado.")

        from modules.financial import pagamentos_diaristas_service as _psvc

        await _psvc.cancelar(db, ref)
        st_depois = (await db.execute(_sql(
            "SELECT status FROM financial_pagamentos_diaristas WHERE id = :i"), {"i": ref})).scalar()
        if st_depois != "cancelado":
            raise HTTPException(status_code=422,
                                detail=f"VT/VR não pôde ser cancelado (status '{st_depois}').")
        rotulo = "VT+VR órfão"
    else:
        row = (await db.execute(_sql(
            "SELECT v.data_referencia, v.valor, e.nome, e.data_admissao, e.id, v.status, "
            "       (SELECT count(*) FROM gp_clock_punches c "
            "          WHERE c.employee_id = e.id AND c.punch_timestamp::date = v.data_referencia) "
            "FROM financial_pagamentos_diaristas v "
            "JOIN employees e ON upper(btrim(e.nome)) = upper(btrim(v.beneficiario)) "
            "WHERE v.id = :i AND v.tipo = 'vt_vr' AND e.status = 'ativo' "
            "  AND coalesce(e.is_homologacao,false) = false "
            "  AND e.data_admissao IS NOT NULL AND v.data_referencia >= e.data_admissao"),
            {"i": ref})).first()
        if not row:
            raise HTTPException(status_code=422, detail=recusa)
        dia, valor, nome_e, adm, _eid, st_antes, n_ponto = row
        posto = "—"
        cascata = 0
        if st_antes == "pago":
            raise HTTPException(status_code=422, detail="VT/VR já PAGO não pode ser cancelado.")

        from modules.financial import pagamentos_diaristas_service as _psvc

        await _psvc.cancelar(db, ref)
        # o service devolve ok:True mesmo sem alterar linha — confere o efeito REAL
        st_depois = (await db.execute(_sql(
            "SELECT status FROM financial_pagamentos_diaristas WHERE id = :i"), {"i": ref})).scalar()
        if st_depois != "cancelado":
            raise HTTPException(status_code=422,
                                detail=f"VT/VR não pôde ser cancelado (status '{st_depois}').")
        rotulo = "VT+VR"

    try:
        # is_sensitive/is_pii/requires_review/archived são NOT NULL SEM default: omitir
        # derrubava o INSERT inteiro e, como ele vive num try/except, o log sumia em
        # silêncio — 5 cancelamentos reais ficaram sem trilha antes disso ser visto.
        await db.execute(_sql(
            "INSERT INTO audit_logs (id, event_id, action, category, severity, result, description, "
            " details, user_id, user_email, is_sensitive, is_pii, requires_review, archived, created_at) "
            "VALUES (gen_random_uuid(), :ev, 'cancelar_sobreposto_clt', 'financeiro', 'warning', "
            " 'success', :desc, CAST(:det AS jsonb), CAST(:uid AS uuid), :mail, "
            " true, false, false, false, now())"),
            {"ev": f"{kind}-{ref}", "desc": f"{rotulo} sobreposto cancelado: {nome_e} em {dia}",
             "det": __import__("json").dumps({
                 "kind": kind, "ref": ref, "data": str(dia), "posto": posto,
                 "valor": float(valor or 0), "admissao_clt": str(adm),
                 "bateu_ponto_no_dia": bool(n_ponto), "motivo": motivo}),
             "uid": str(current_user.id), "mail": getattr(current_user, "email", None)})
        await db.commit()
    except Exception:  # noqa: BLE001 — já foi cancelado; o log não pode desfazer isso
        await db.rollback()

    return {"ok": True, "message": (
        f"{rotulo} de {nome_e} em {dia.strftime('%d/%m/%Y')} ({brl(float(valor or 0))}) CANCELADO."
        + (f" CLT desde {adm.strftime('%d/%m/%Y')}" if adm else " Sem diária lançada nesse dia.")
        + (("; bateu ponto nesse dia." if n_ponto else "; sem ponto nesse dia.") if adm else "")
        + (f" O VT/VR do mesmo dia foi cancelado junto ({cascata})." if cascata else "")
        + " Nenhum dinheiro foi movido — a saída futura foi impedida. Recarregue a tela.")}


@router.post("/action/gerar-contas-de-nfse", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_gerar_contas_de_nfse(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Gera conta a receber a partir das NFS-e emitidas. NÃO move dinheiro.

    dry_run=sim (padrão) só relata. Idempotente: nota já convertida é pulada.
    """
    from modules.financial.services.nfse_receivable_service import gerar_contas_de_nfse

    comp = (payload.get("competencia") or "").strip() or None
    dry = (payload.get("dry_run") or "sim").strip().lower() != "nao"
    r = await gerar_contas_de_nfse(db, competencia=comp, dry_run=dry)
    prefixo = "SIMULAÇÃO (nada gravado)" if dry else "GRAVADO"
    return {"ok": True, "message": (
        f"{prefixo} — {r['analisadas']} NFS-e analisada(s): {r['criadas']} conta(s) criada(s), "
        f"{r['ja_existiam']} já existia(m), {r['canceladas_ignoradas']} cancelada(s) ignorada(s). "
        f"{r['sem_cliente']} sem cliente casado por CNPJ (entram com o nome do tomador). "
        f"Total {brl(r['total_valor'])}.")}


@router.post("/action/pagar-folha-pj", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_pagar_folha_pj(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Pagar folha PJ (Inter) — DELEGA ao serviço provado (OTP próprio). 1ª chamada sem
    otp_code → gera o código (e-mail Jordan) e devolve otp_required; 2ª com otp_code →
    executa o pagamento REAL. Sem OTP válido, nada é pago (o serviço garante)."""
    from modules.financial.services import pagamento_pj_service as svc
    try:
        mes = int(payload.get("mes") or 0)
        ano = int(payload.get("ano") or 0)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Mês e ano devem ser números.")
    if not (1 <= mes <= 12) or ano < 2025:
        raise HTTPException(status_code=400, detail="Informe mês (1-12) e ano (>=2025) válidos.")
    otp_code = (payload.get("otp_code") or "").strip()
    lote_id = (payload.get("_gate_ref") or "").strip()
    if not otp_code:
        r = await svc.gerar_otp_lote(db, mes, ano)
        if not r.get("ok"):
            raise HTTPException(status_code=400, detail=r.get("mensagem") or "Nenhum item Inter elegível.")
        return {"otp_required": True, "ref": r.get("lote_id", ""),
                "message": f"{r.get('quantidade')} prestador(es) · R$ {float(r.get('total') or 0):.2f}. "
                           f"{r.get('message', '')}. Confirme com o código OTP."}
    r = await svc.executar_lote(db, mes, ano, confirmar=True, otp_code=otp_code, lote_id=lote_id or None)
    if r.get("otp_invalido") or r.get("otp_requerido"):
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "OTP inválido ou obrigatório.")
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "Não foi possível executar o lote.")
    # Link pagamento→baixa (PJ): folha PJ paga de verdade (Inter, OTP) → baixa o pagável PJ da competência.
    await _baixar_pagavel_folha(db, mes, ano,
                                quem=str(getattr(current_user, "nome", None) or getattr(current_user, "id", "")),
                                pj=True)
    return {"ok": True, "message": f"Lote pago: {r.get('pagos', 0)} pago(s), {r.get('falhas', 0)} falha(s)."}


def _conta_que_paga(payload: dict) -> str:
    """De qual conta sai o dinheiro. Vazio é RECUSA, nunca um padrão.

    ⚠️ Os dois pontos de saída assumiam 'cora' quando o campo — obrigatório na tela,
    mas enviável em branco — vinha vazio. Um padrão silencioso aqui escolhe DE QUAL
    CNPJ o dinheiro sai (Cora=Patrimonial, Inter=Eletrônica), e a escolha errada já
    fez VT da Patrimonial sair pela Eletrônica.

    O efeito visível era pior que um erro: como a Cora não envia PIX por chave, o
    pedido morria em "vá pagar no app do Cora", o modal fechava e parecia tela
    quebrada. Medido em 23/08 clicando na tela: sem escolher a conta, nenhum OTP era
    emitido e nada indicava por quê.
    """
    v = str(payload.get("origem") or "").strip().lower()
    if v not in ("cora", "inter"):
        raise HTTPException(
            status_code=400,
            detail="Escolha a conta que vai pagar: Cora (Patrimonial) ou Inter (Eletrônica).",
        )
    return v


@router.post("/action/pagar-diaristas", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_pagar_diaristas(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Pagar lote de diaristas (Inter) — DELEGA ao serviço provado (OTP próprio). Mesmo
    padrão do pagar-folha-pj: sem otp_code → gera código; com otp_code → paga real.
    Sem OTP válido, nada é pago."""
    import modules.financial.pagamentos_diaristas_service as svc
    # Data OPCIONAL: vazia = LOTE INTEIRO (todo item elegivel, o mes fechado de uma vez).
    # Antes era obrigatoria e o Jordan tinha que pagar dia a dia — 31 operacoes para uma
    # competencia. O servico ja aceitava `data=None` e montava o lote completo; quem
    # obrigava era esta tela.
    # Vazio = tudo do recorte (VT/VR + diária), que é o comportamento de sempre.
    # `vt_vr` = só a passagem/alimentação do dia: soltar o que o Eliziel lançou sem levar
    # junto a diária mensal de alguém que caia na mesma data.
    # ⚠️ Definido AQUI, dentro desta função. Estava numa âncora curta que também casava
    # em `_rd_pagar_folha_pj`, e o replace acertou a vizinha: a variável nascia lá e a
    # chamada daqui estourava `NameError` na hora de gerar o OTP — com o Jordan na tela.
    _tipo_lote = (payload.get("tipo") or "").strip() or None
    if _tipo_lote not in (None, "vt_vr", "diaria_mensal"):
        raise HTTPException(status_code=400, detail="Tipo inválido.")
    data = (payload.get("data") or "").strip()
    if data and len(data) < 8:
        raise HTTPException(status_code=400, detail="Data no formato AAAA-MM-DD (ou vazia).")
    _d_sql = _rd_parse_data(data) or data if data else None
    # COMPETÊNCIA é o recorte natural: paga-se "julho", não "o dia 15/08". Aceita
    # AAAA-MM (o que se digita) e converte para MM/AAAA (como a tabela guarda).
    _comp_in = (payload.get("competencia") or "").strip()
    competencia = None
    if _comp_in:
        m = re.match(r"^(\d{4})-(\d{1,2})$", _comp_in) or re.match(r"^(\d{1,2})/(\d{4})$", _comp_in)
        if not m:
            raise HTTPException(status_code=400, detail="Competência no formato AAAA-MM (ex.: 2026-07).")
        ano, mes = (m.group(1), m.group(2)) if "-" in _comp_in else (m.group(2), m.group(1))
        competencia = f"{int(mes):02d}/{ano}"
    # ── TRAVA ANTI-LOTE-VELHO ────────────────────────────────────────────────────────
    # O lote envelhece: o Eliziel segue lançando enquanto ele espera o dia 15. Medido em
    # 03/08 — lote R$8.670 contra R$8.730 já lançados; pagar ali pagaria A MENOS.
    # Compara PESSOA A PESSOA e só o que ainda dá para mudar (a_revisar/sem_pix): comparar
    # totais daria falso alarme, porque quem já está 'pago'/'cancelado' legitimamente não
    # bate com o lançado (ex.: R$640 pagos sem lançamento + R$850 cancelados).
    # Roda ANTES de Cora e de Inter: vale para gerar lista e para gerar OTP.
    _d_ref = _d_sql
    # Sem data, a trava vale para TODA competencia com item ainda mudavel — nao pular a
    # verificacao e o ponto: pagar o lote inteiro sem conferir seria pagar a menos em
    # escala, em vez de num dia so.
    if _d_ref:
        _comp = (await db.execute(text(
            "SELECT DISTINCT competencia FROM financial_pagamentos_diaristas "
            "WHERE data_referencia = CAST(:d AS date) AND tipo = 'diaria_mensal'"),
            {"d": _d_ref})).scalars().all()
    elif competencia:
        _comp = [competencia]
    else:
        _comp = (await db.execute(text(
            "SELECT DISTINCT competencia FROM financial_pagamentos_diaristas "
            "WHERE tipo = 'diaria_mensal' AND status IN ('a_revisar','sem_pix') "
            "  AND competencia IS NOT NULL"))).scalars().all()
    for _c in _comp:
        try:
            _mm, _aa = str(_c).split("/")
            _mm, _aa = int(_mm), int(_aa)
        except (ValueError, AttributeError):
            continue
        _div = (await db.execute(text(
            "WITH lanc AS ("
            "  SELECT d.nome AS nome, sum(l.valor) AS v"
            "  FROM diaria_lancamentos l JOIN diaria_diaristas d ON d.id = l.diarista_id"
            "  WHERE EXTRACT(MONTH FROM l.data) = :m AND EXTRACT(YEAR FROM l.data) = :a"
            "  GROUP BY d.nome),"
            "lote AS ("
            "  SELECT beneficiario AS nome, valor AS v, status"
            "  FROM financial_pagamentos_diaristas"
            "  WHERE competencia = :c AND tipo = 'diaria_mensal')"
            "SELECT coalesce(lanc.nome, lote.nome), coalesce(lanc.v,0), coalesce(lote.v,0),"
            "       coalesce(lote.status,'(fora do lote)')"
            "FROM lanc FULL OUTER JOIN lote"
            "  ON upper(btrim(lanc.nome)) = upper(btrim(lote.nome))"
            "WHERE coalesce(lote.status,'a_revisar') IN ('a_revisar','sem_pix')"
            "  AND abs(coalesce(lanc.v,0) - coalesce(lote.v,0)) > 0.005 "
            "ORDER BY abs(coalesce(lanc.v,0) - coalesce(lote.v,0)) DESC"),
            {"m": _mm, "a": _aa, "c": _c})).fetchall()
        if _div:
            _delta = sum(float(r[1] or 0) - float(r[2] or 0) for r in _div)
            _quem = "; ".join(
                f"{r[0]}: lançado {brl(float(r[1] or 0))} × lote {brl(float(r[2] or 0))}"
                for r in _div[:6]) + ("…" if len(_div) > 6 else "")
            raise HTTPException(status_code=409, detail=(
                f"LOTE DESATUALIZADO — pagamento bloqueado. A competência {_c} tem "
                f"{len(_div)} divergência(s) entre o lançado e o lote "
                f"({'faltam ' if _delta > 0 else 'sobram '}{brl(abs(_delta))}). "
                f"{_quem}. Regere o lote em 'Lote mensal (dia 15)' e tente de novo."))

    # padrão CORA: diarista é prestador da Patrimonial, e a Patrimonial paga pela Cora.
    origem = _conta_que_paga(payload)
    if origem == "cora":
        # O Cora NAO envia PIX por chave (limitacao da API do proprio banco). Em vez de fingir que
        # pagou, devolve a LISTA pro Jordan concluir no app — e depois marcar em 'Pago por fora'.
        _filtro = ("data_referencia = CAST(:d AS date) AND " if _d_sql else
                   ("competencia = :comp AND " if competencia else ""))
        itens = (await db.execute(text(
            "SELECT beneficiario, coalesce(pix_key,'(sem PIX)'), valor FROM financial_pagamentos_diaristas "
            f"WHERE {_filtro}status='a_revisar' ORDER BY beneficiario"),
            ({"d": _d_sql} if _d_sql else ({"comp": competencia} if competencia else {})))).fetchall()
        if not itens:
            _onde = f"em {data}" if data else "no lote"
            return {"ok": True, "message": f"Nada a pagar {_onde} (nenhum item 'a revisar')."}
        total = sum(float(i[2] or 0) for i in itens)
        linhas = " · ".join(f"{i[0]}: {i[1]} = {brl(float(i[2] or 0))}" for i in itens[:12])
        # Lista curta cabe na mensagem; lista longa vira "vá na aba Diaristas e exporte" —
        # truncar uma lista de pagamento seria pior que não mostrar (risco de pagar só parte).
        if len(itens) <= 12:
            return {"ok": True, "message": (
                f"CORA — {len(itens)} pagamento(s), total {brl(total)}. O Cora não envia PIX por chave: "
                f"conclua no app do Cora e depois registre em 'Pago por fora'. Lista: {linhas}")}
        return {"ok": True, "message": (
            f"CORA — {len(itens)} pagamento(s), total {brl(total)}. O Cora não envia PIX por chave. "
            f"A lista completa (nome + chave PIX + valor) está na aba 'Diaristas': filtre o Dia "
            f"{_fmtdate(_rd_parse_data(data)) if _rd_parse_data(data) else data} e use o botão Exportar. Depois registre cada um em 'Pago por fora'.")}
    otp_code = (payload.get("otp_code") or "").strip()
    lote_id = (payload.get("_gate_ref") or "").strip()
    if not otp_code:
        r = await svc.gerar_otp_lote(db, data=(data or None), competencia=competencia,
                                     tipo=_tipo_lote)
        if not r.get("ok"):
            raise HTTPException(status_code=400, detail=r.get("mensagem") or "Nenhum item elegível.")
        return {"otp_required": True, "ref": r.get("lote_id", ""),
                "message": f"{r.get('quantidade')} diarista(s) · R$ {float(r.get('total') or 0):.2f}. Confirme com o código OTP."}
    r = await svc.executar_lote(db, data=(data or None), competencia=competencia, confirmar=True, otp_code=otp_code,
                                lote_id=lote_id or None, user_id=str(getattr(current_user, "id", "")),
                                tipo=_tipo_lote)
    if r.get("otp_invalido") or r.get("otp_requerido"):
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "OTP inválido ou obrigatório.")
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "Não foi possível executar o lote.")
    return {"ok": True, "message": f"Lote pago: {r.get('pagos', 0)} pago(s), {r.get('falhas', 0)} falha(s)."}


async def _rd_folha_clt_cora(db, payload: dict) -> dict:
    """Folha CLT pela CORA: a API do Cora NÃO envia PIX por chave, então em vez de fingir
    pagamento devolve o RESUMO real (quantos, total, quantos sem PIX). Nunca simula liquidação."""
    try:
        mes = int(str(payload.get("mes") or "").strip()); ano = int(str(payload.get("ano") or "").strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Informe mês (1-12) e ano.")
    comp = f"{ano:04d}-{mes:02d}"
    row = (await db.execute(text(
        "SELECT count(*) FILTER (WHERE coalesce(e.pix_key,'') <> ''), "
        "       coalesce(round(sum(CASE WHEN coalesce(e.pix_key,'') <> '' "
        "               THEN p.total_earnings - p.total_deductions ELSE 0 END)::numeric,2),0), "
        "       count(*) FILTER (WHERE coalesce(e.pix_key,'') = ''), "
        "       coalesce(round(sum(p.total_earnings - p.total_deductions)::numeric,2),0) "
        "FROM hr_payslips p JOIN employees e ON e.id = p.employee_id "
        "WHERE to_char(p.competence_start,'YYYY-MM') = :c "
        "  AND coalesce(e.is_homologacao,false) = false"), {"c": comp})).first()
    if not row or not row[3]:
        return {"ok": True, "message": f"Folha {mes:02d}/{ano} não encontrada (nenhum holerite na competência)."}
    com_pix, tot_pix, sem_pix, tot_geral = int(row[0] or 0), float(row[1] or 0), int(row[2] or 0), float(row[3] or 0)
    aviso = (f" ATENÇÃO: {sem_pix} funcionário(s) SEM chave PIX — some(m) {brl(tot_geral - tot_pix)} "
             "e não entram na lista até cadastrar a chave.") if sem_pix else ""
    return {"ok": True, "message": (
        f"CORA — folha {mes:02d}/{ano}: {com_pix} pagamento(s), total {brl(tot_pix)}. "
        f"O Cora não envia PIX por chave: conclua no app do Cora. A lista (nome + chave + líquido) "
        f"está em DP → Holerites.{aviso}")}


async def _baixar_pagavel_folha(db, mes: int, ano: int, quem: str = "", pj: bool = False) -> None:
    """Link pagamento→baixa: depois que a folha foi PAGA de verdade (money-out já OTP-gated via Inter),
    dá baixa no pagável da folha daquela competência (se existir e pendente). Bookkeeping best-effort:
    NUNCA derruba o pagamento, idempotente (só 'pendente'), NÃO move dinheiro. `pj`=folha de prestadores
    (casa 'folha/pagamento/prestador' COM 'pj'); CLT casa 'folha' SEM 'pj' — pra um pagamento não baixar
    o pagável do outro. Assim a folha não fica 'pendente' no livro depois de paga (caso do velho Março)."""
    import logging as _logging
    # cond é LITERAL escolhida por flag interna (não é input do usuário) — sem risco de injeção.
    cond = ("description ~* 'pj' AND description ~* 'folha|pagamento|prestador'" if pj
            else "description ~* 'folha' AND description !~* 'pj|prestador'")
    origem = "PJ" if pj else "CLT"
    try:
        await db.execute(text(
            "UPDATE payable_accounts SET status='pago', payment_date=CURRENT_DATE, paid_at=NOW(), "
            "paid_value=net_value, remaining_value=0, updated_at=NOW(), "
            "internal_notes = coalesce(internal_notes,'') || :nota "
            f"WHERE status='pendente' AND {cond} "
            "AND date_trunc('month', due_date) BETWEEN make_date(:ano,:mes,1) "
            "    AND make_date(:ano,:mes,1) + interval '1 month'"),
            {"ano": ano, "mes": mes,
             "nota": f" | baixa auto: folha {origem} {mes:02d}/{ano} paga via sistema por {quem or 'gestor'}"})
        await db.commit()
    except Exception as e:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001, S110
            pass
        _logging.getLogger("financeiro.redesign").warning("[folha] baixa do pagável falhou (segue): %s", e)


@router.post("/action/pagar-folha-clt", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_pagar_folha_clt(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Pagar a FOLHA CLT (líquido dos funcionários) via PIX Inter — DINHEIRO QUE SAI.
    2 fases + OTP humano (mesmo gate do lote de diaristas): sem otp_code → gera o código
    (e-mail ao Jordan); com otp_code → paga real. Reusa os endpoints provados
    /folha/pagar-via-pix (gerar-otp + pagar). Sem OTP válido, nada é pago. Teto R$100k aplicado."""
    origem = _conta_que_paga(payload)
    if origem == "cora":
        return await _rd_folha_clt_cora(db, payload)
    from modules.people_management.employee_portal.controllers.dp_payslips_controller import (
        gerar_otp_pagamento_folha, pagar_folha_via_pix,
    )
    try:
        mes = int(str(payload.get("mes") or "").strip()); ano = int(str(payload.get("ano") or "").strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Informe o mês (1-12) e o ano (AAAA).")
    if not (1 <= mes <= 12) or not (2020 <= ano <= 2100):
        raise HTTPException(status_code=400, detail="Mês (1-12) ou ano (AAAA) fora do intervalo.")
    otp_code = (payload.get("otp_code") or "").strip()
    lote_id = (payload.get("_gate_ref") or "").strip()
    if not otp_code:
        r = await gerar_otp_pagamento_folha(mes, ano, db=db, _user=current_user)
        if not r.get("ok"):
            raise HTTPException(status_code=400, detail=r.get("mensagem") or "Nada a pagar no período.")
        return {"otp_required": True, "ref": r.get("lote_id", ""),
                "message": f"Folha CLT {mes:02d}/{ano} · R$ {float(r.get('total') or 0):.2f}. "
                           "Confirme com o código OTP enviado ao Jordan."}
    r = await pagar_folha_via_pix(mes, ano, otp_code=otp_code, lote_id=lote_id or None, db=db, _user=current_user)
    if r.get("otp_invalido") or r.get("otp_requerido"):
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "OTP inválido ou obrigatório.")
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "Não foi possível pagar a folha.")
    # Link pagamento→baixa: folha paga de verdade (Inter, OTP) → baixa o pagável da competência.
    await _baixar_pagavel_folha(db, mes, ano,
                                quem=str(getattr(current_user, "nome", None) or getattr(current_user, "id", "")))
    return {"ok": True, "message": f"Folha CLT paga: {r.get('pagos', r.get('sucesso', 0))} funcionário(s), "
            f"{r.get('falhas', 0)} falha(s)."}


# ── Money-out genérico (boleto/PIX/TED/DARF) via InterPaymentService — 2 fases + OTP ──
def _rd_parse_valor(s):
    s = str(s or "").strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = _brl_norm(s)
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _rd_parse_data(s):
    from datetime import date as _date
    s = str(s or "").strip()
    if not s:
        return _date.today()
    try:
        y, m, d = s.split("-")
        return _date(int(y), int(m), int(d))
    except Exception:  # noqa: BLE001
        return None


def _dest_boleto(p):
    cb = (p.get("codigo_barras") or "").strip().replace(" ", "")
    if not cb:
        raise HTTPException(status_code=400, detail="Informe o código de barras / linha digitável.")
    return {"codigo_barras": cb}


def _dest_pix(p):
    chave = (p.get("chave") or "").strip()
    cec = (p.get("pix_copia_e_cola") or "").strip()
    if not chave and not cec:
        raise HTTPException(status_code=400, detail="Informe a chave PIX ou o PIX copia-e-cola.")
    d: dict = {}
    if cec:
        d["pix_copia_e_cola"] = cec
    if chave:
        d["chave"] = chave
    return d


def _dest_ted(p):
    banco = (p.get("banco") or "").strip()
    agencia = (p.get("agencia") or "").strip()
    conta = (p.get("conta") or "").strip()
    if not (banco and agencia and conta):
        raise HTTPException(status_code=400, detail="Informe banco, agência e conta.")
    d = {"banco": banco, "agencia": agencia, "conta": conta}
    if (p.get("nome") or "").strip():
        d["nome"] = p["nome"].strip()
    if (p.get("documento") or "").strip():
        d["documento"] = p["documento"].strip()
    return d


def _dest_darf(p):
    pa = (p.get("periodo_apuracao") or "").strip()
    cr = (p.get("codigo_receita") or "").strip()
    if not (pa and cr):
        raise HTTPException(status_code=400, detail="Informe período de apuração e código da receita.")
    d = {"periodo_apuracao": pa, "codigo_receita": cr}
    if (p.get("numero_referencia") or "").strip():
        d["numero_referencia"] = p["numero_referencia"].strip()
    # Cora exige dados do contribuinte + vencimento (Inter ignora esses campos).
    for k in ("payer_name", "payer_document", "vencimento"):
        if (p.get(k) or "").strip():
            d[k] = p[k].strip()
    return d


def _dest_gps(p):
    comp = (p.get("competencia") or "").strip()
    cod = (p.get("codigo_pagamento") or "").strip()
    if not (comp and cod):
        raise HTTPException(status_code=400, detail="Informe a competência (AAAA-MM) e o código de pagamento GPS.")
    d = {"competencia": comp, "codigo_pagamento": cod}
    doc = (p.get("payer_document") or "").strip()
    if doc:
        d["payer_document"] = doc
        d["identificador"] = doc  # o Inter usa 'identificador'
    for k in ("payer_name", "identification_type"):
        if (p.get(k) or "").strip():
            d[k] = p[k].strip()
    return d


async def _rd_inter_pay(db, current_user, payload, *, payment_type, categoria, dest_fn, label):
    """Money-out via serviço PROVADO InterPaymentService. Fase 1 (sem otp_code):
    preparar (trava saldo/limite diário) + gerar_otp (e-mail ao Jordan) → otp_required.
    Fase 2 (otp_code + _gate_ref): aprovar (valida OTP) + executar (chama o Inter).
    Sem OTP válido, NADA é pago — o serviço garante. Espelha o console clássico."""
    from modules.integrations.inter.services.payment_service import InterPaymentService, PaymentError
    svc = InterPaymentService(db)
    uid = str(getattr(current_user, "id", ""))
    otp_code = (payload.get("otp_code") or "").strip()
    ref = (payload.get("_gate_ref") or "").strip()
    # De qual EMPRESA sai o dinheiro. Não tem default: em 14/08/2026 o campo não chegou
    # no payload e o código assumiu 'inter' calado — o vale-transporte da Patrimonial
    # virou ordem de saída da Eletrônica, duas vezes, sem ninguém escolher isso. Banco
    # aqui é CNPJ; adivinhar CNPJ é adivinhar de quem é o dinheiro.
    origem = (payload.get("origem") or payload.get("banco") or "").strip().lower()
    if origem not in ("inter", "cora"):
        raise HTTPException(status_code=400, detail=(
            "Escolha de qual conta sai o pagamento: Cora (Patrimonial) ou Inter "
            "(Eletrônica). São CNPJs diferentes e o sistema não escolhe por você."))
    # Boleto pelo Cora via API não se confirma. Medido em 13 e 14/08/2026: a ordem é
    # aceita (pay_6uNouTktocNnlKiq5ikdbp), o Jordan aprova no app, o dinheiro NÃO sai —
    # o saldo ficou parado em R$51.832,90 — e ao consultar, o Cora responde 404: a ordem
    # sumiu. E não existe endpoint para listar pendências, então depois de criar ficamos
    # CEGOS. Money-out que a gente inicia e não consegue observar não é caminho: ou paga
    # duas vezes, ou some. Enquanto a Efí não abre, boleto da Patrimonial é no app.
    if origem == "cora" and payment_type == "boleto":
        raise HTTPException(status_code=400, detail=(
            "Boleto pelo Cora não completa por API — medido em 13 e 14/08/2026: a ordem "
            "é aceita, você aprova no app, o dinheiro não sai e depois o Cora responde "
            "404. Pague este boleto direto no app do Cora; o extrato de amanhã registra "
            "e concilia sozinho. (Some quando a conta Efí entrar.)"))
    # O Cora não envia PIX de saída (API do próprio banco) — bloqueia cedo, com mensagem honesta.
    if origem == "cora" and payment_type == "pix":
        raise HTTPException(status_code=400, detail=(
            "O Cora (Patrimonial) não envia PIX de saída — é regra da API do próprio Cora. "
            "Use 'TED' por dados bancários para pagar da Patrimonial, ou selecione o Inter."))
    try:
        if not otp_code:
            valor = _rd_parse_valor(payload.get("valor"))
            if valor is None or valor <= 0:
                raise HTTPException(status_code=400, detail="Informe um valor válido (R$).")
            dp = _rd_parse_data(payload.get("data"))
            if dp is None:
                raise HTTPException(status_code=400, detail="Data inválida (use AAAA-MM-DD).")
            dest = dest_fn(payload)
            prep = await svc.preparar(payment_type=payment_type, destinatario=dest, valor=valor,
                                      data_pagamento=dp, prepared_by=uid,
                                      observacoes=(payload.get("descricao") or "").strip(),
                                      categoria=categoria, origem=origem)
            await svc.gerar_otp(prep["id"], uid)
            return {"otp_required": True, "ref": prep["id"],
                    "message": f"{label} de {brl(valor)} preparado. Confirme com o código OTP enviado ao e-mail do Jordan."}
        if not ref:
            raise HTTPException(status_code=400, detail="Referência do pagamento ausente. Refaça a operação.")
        await svc.aprovar(ref, otp_code, uid)
        res = await svc.executar(ref, uid)
        st = res.get("status") if isinstance(res, dict) else None
        # Honesto: se o banco devolveu "aguardando_aprovacao" (Cora sempre; Inter quando a conta
        # exige), NÃO diz "executado" — usa a mensagem real do serviço (aprovar no app).
        if isinstance(res, dict) and (res.get("aguardando_aprovacao") or st == "aguardando_aprovacao"):
            return {"ok": True, "message": res.get("mensagem")
                    or f"{label}: iniciado — aprove no app do banco para concluir."}
        return {"ok": True, "message": f"{label} executado com sucesso." + (f" Status: {st}." if st else "")}
    except HTTPException:
        raise
    except PaymentError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=400, detail=f"Falha no pagamento: {str(e)[:200]}")


@router.post("/action/pagar-boleto", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_pagar_boleto(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    return await _rd_inter_pay(db, current_user, payload, payment_type="boleto",
                               categoria="fornecedor", dest_fn=_dest_boleto, label="Pagamento de boleto")


@router.post("/action/enviar-pix", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_enviar_pix(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    return await _rd_inter_pay(db, current_user, payload, payment_type="pix",
                               categoria="transferencia", dest_fn=_dest_pix, label="PIX")


@router.post("/action/transferir-ted", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_transferir_ted(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    return await _rd_inter_pay(db, current_user, payload, payment_type="ted_interno",
                               categoria="transferencia", dest_fn=_dest_ted, label="Transferência TED")


@router.post("/action/pagar-darf", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_pagar_darf(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    return await _rd_inter_pay(db, current_user, payload, payment_type="darf",
                               categoria="imposto", dest_fn=_dest_darf, label="Pagamento de DARF")


@router.post("/action/pagar-gps", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_pagar_gps(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    return await _rd_inter_pay(db, current_user, payload, payment_type="gps",
                               categoria="imposto", dest_fn=_dest_gps, label="Pagamento de GPS")


@router.post("/action/programar-diarias-mes")
async def _rd_programar_diarias_mes(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """FLUXO 2: monta o lote do dia 15 somando os dias trabalhados do mês. NÃO paga."""
    import modules.financial.pagamentos_diaristas_service as _svc
    try:
        mes = int(str(payload.get("mes") or "").strip())
        ano = int(str(payload.get("ano") or "").strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Informe mês (1-12) e ano.")
    if not 1 <= mes <= 12:
        raise HTTPException(status_code=400, detail="Mês deve estar entre 1 e 12.")
    r = await _svc.programar_diarias_mensais(db, mes=mes, ano=ano, user_id=str(getattr(current_user, "id", "")))
    # A mensagem antiga decidia por 'ja_programados', chave que o service NÃO devolve: com
    # tudo já programado ele dizia "nenhuma diária lançada" MESMO tendo recalculado o lote
    # (medido: 28 diaristas processados, lote 10.870 -> 10.160, mensagem "nada a programar").
    # Agora o que manda é quantos diaristas o service realmente processou.
    pessoas = int(r.get("diaristas", 0) or 0)
    if not pessoas:
        return {"ok": True, "message": f"Nenhuma diária lançada em {mes:02d}/{ano} — nada a programar."}
    novos = int(r.get("programados_novos", 0) or 0)
    upd = int(r.get("atualizados", 0) or 0)
    canc = r.get("cancelados_sem_lancamento") or []
    tot = r.get("total_a_pagar", 0)
    extra = ""
    if canc:
        extra = (f" {len(canc)} cancelada(s) por não ter mais diária lançada "
                 f"({brl(sum(c['valor'] for c in canc))}): "
                 + ", ".join(c["beneficiario"] for c in canc[:5])
                 + ("…" if len(canc) > 5 else "") + ".")
    return {"ok": True, "message": (
        f"{mes:02d}/{ano}: {pessoas} diarista(s) com diária lançada — {novos} nova(s), "
        f"{upd} atualizada(s).{extra} Total a pagar no lote: {brl(float(tot or 0))}.")}


@router.post("/action/marcar-pago-externo")
async def _rd_marcar_pago_externo(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Marca um item do lote como pago FORA do sistema (dinheiro, outro banco). NÃO move dinheiro —
    só registra que já foi pago, p/ não pagar duas vezes."""
    import modules.financial.pagamentos_diaristas_service as _svc
    try:
        pid = int(str(payload.get("pagamento_id") or "").strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Informe o ID do pagamento (da aba Diaristas).")
    obs = (payload.get("observacao") or "").strip()
    r = await _svc.marcar_pago_externo(db, pagamento_id=pid,
                                       user_nome=(obs or "pago por fora")[:120])
    if isinstance(r, dict) and r.get("ok") is False:
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "Não foi possível marcar.")
    return {"ok": True, "message": f"Pagamento {pid} marcado como pago por fora — não entra mais no lote."}


@router.post("/action/baixar-recebivel")
async def _rd_baixar_recebivel(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Registra o RECEBIMENTO de uma conta a receber (bookkeeping — não move dinheiro).

    O crédito que cai na conta é quase sempre MENOR que a nota por retenção na fonte
    (INSS 11%, IRRF 1%…). A diferença NÃO é inadimplência: é imposto retido pelo
    tomador. Quem decide o tratamento é o humano — o sistema não adivinha."""
    import uuid as _uuid
    from datetime import date as _date
    from decimal import Decimal as _Dec

    from sqlalchemy import text as _text

    raw = str(payload.get("receivable_id") or payload.get("id") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Informe o ID da conta a receber.")
    try:
        rid = _uuid.UUID(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="ID inválido.")

    row = (await db.execute(_text(
        "SELECT description, net_value, status, customer_name FROM receivable_accounts WHERE id = :i"
    ), {"i": str(rid)})).first()
    if not row:
        raise HTTPException(status_code=404, detail="Conta a receber não encontrada.")
    if str(row[2]) in ("paga", "cancelada"):
        raise HTTPException(status_code=400, detail=f"Conta já está '{row[2]}'. Nada a fazer.")

    nota = _Dec(str(row[1] or 0))
    bruto = _brl_norm(str(payload.get("valor_recebido") or "").strip())
    try:
        recebido = _Dec(bruto) if bruto else nota
    except Exception:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="Valor inválido.")
    if recebido <= 0:
        raise HTTPException(status_code=400, detail="Valor recebido deve ser maior que zero.")

    dt = str(payload.get("data_recebimento") or "").strip()
    try:
        quando = _date.fromisoformat(dt) if dt else _date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Data inválida (use AAAA-MM-DD).")

    diferenca = nota - recebido
    parcial = diferenca > 0 and str(payload.get("tratamento") or "retencao").strip().lower() == "parcial"
    novo_status = "parcial" if parcial else "paga"

    await db.execute(_text(
        """
        UPDATE receivable_accounts
           SET status = :st, paid_value = :pv, remaining_value = :rv,
               payment_date = :dt, data_recebimento = :dt, updated_at = NOW()
         WHERE id = :i
        """
    ), {"st": novo_status, "pv": float(recebido),
        "rv": float(diferenca if parcial else 0), "dt": quando, "i": str(rid)})
    await db.commit()

    msg = f"{row[0]}: recebido R$ {float(recebido):,.2f}"
    if diferenca > 0:
        msg += (f" — saldo em aberto R$ {float(diferenca):,.2f}" if parcial
                else f" (retenção na fonte R$ {float(diferenca):,.2f} — nota quitada)")
    return {
        "ok": True, "message": msg, "conta": row[0], "cliente": row[3],
        "valor_da_nota": float(nota), "valor_recebido": float(recebido),
        "diferenca": float(diferenca),
        "tratamento": "pagamento parcial" if parcial else "retencao na fonte",
        "status": novo_status, "data": quando.isoformat(),
    }


@router.post("/action/registrar-obrigacoes")
async def _rd_registrar_obrigacoes(current_user: CurrentActiveUser, payload: dict = Body(...)) -> dict:
    """Registra como pagável o que a empresa deve (NFS-e tomadas, folha, guias).
    `modo=preview` (padrão) não grava nada. NÃO move dinheiro."""
    from starlette.concurrency import run_in_threadpool

    from modules.financial.services.payable_sources_service import gerar_pagaveis

    aplicar = str(payload.get("modo") or "preview").strip().lower() == "aplicar"
    r = await run_in_threadpool(gerar_pagaveis, preview=not aplicar)
    fontes = {f["fonte"]: f["criados"] for f in r.get("fontes", [])}
    ignorados = {
        k: v
        for f in r.get("fontes", [])
        for k, v in f.items()
        if k.endswith("ignorados") and v
    }
    verbo = "Registradas" if aplicar else "Seriam registradas"
    return {
        "ok": True,
        "message": f"{verbo} {r['total_criados']} obrigações — R$ {r['total_valor']:,.2f}"
                   + ("" if aplicar else " (nada gravado: previsualização)"),
        "modo": r["modo"],
        "total": r["total_criados"],
        "valor_total": r["total_valor"],
        "por_fonte": fontes,
        **({"ignorados_por_regra": ignorados} if ignorados else {}),
    }


@router.post("/action/gerar-recebiveis")
async def _rd_gerar_recebiveis(current_user: CurrentActiveUser, payload: dict = Body(...)) -> dict:
    """Recebível por contrato/competência. NÃO emite cobrança ao cliente."""
    from datetime import date as _date

    from starlette.concurrency import run_in_threadpool

    from modules.financial.services.receivable_contract_service import gerar_recebiveis

    hoje = _date.today()
    try:
        mes = int(str(payload.get("mes") or hoje.month).strip())
        ano = int(str(payload.get("ano") or hoje.year).strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Mês/ano inválidos.")
    aplicar = str(payload.get("modo") or "preview").strip().lower() == "aplicar"
    r = await run_in_threadpool(gerar_recebiveis, mes, ano, preview=not aplicar)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("erro") or "Não foi possível gerar.")
    verbo = "Gerados" if aplicar else "Seriam gerados"
    return {
        "ok": True,
        "message": f"{verbo} {r['criados']} recebíveis de {r['competência']} — "
                   f"R$ {r['valor_total']:,.2f}"
                   + (f" ({r['ja_existiam']} já existiam)" if r.get("ja_existiam") else "")
                   + ("" if aplicar else " — nada gravado: previsualização"),
        "modo": r["modo"],
        "competencia": r["competencia"],
        "criados": r["criados"],
        "ja_existiam": r.get("ja_existiam", 0),
        "valor_total": r["valor_total"],
        "aviso": r.get("aviso"),
    }


@router.post("/action/baixar-pagavel")
async def _rd_baixar_pagavel(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Dá BAIXA numa conta a pagar já quitada — marca 'pago' + data (bookkeeping). NÃO move dinheiro
    (pagar de verdade = fluxo gated com OTP). Idempotente: bloqueia conta já paga/cancelada."""
    import uuid as _uuid
    from datetime import date as _date
    from decimal import Decimal as _Dec

    from sqlalchemy import select as _select

    from modules.financial.models.payable_account import PayableAccount, PayableStatus

    raw = str(payload.get("payable_id") or payload.get("id") or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="Informe o ID da conta a pagar (está na tabela Contas a Pagar).")
    try:
        pid = _uuid.UUID(raw)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="ID inválido.")
    pa = (await db.execute(_select(PayableAccount).where(PayableAccount.id == pid))).scalar_one_or_none()
    if not pa:
        raise HTTPException(status_code=404, detail="Conta a pagar não encontrada.")
    if pa.status in (PayableStatus.PAGA.value, "paga", PayableStatus.CANCELADA.value):
        raise HTTPException(status_code=400, detail=f"Conta já está '{pa.status}' — nada a baixar.")

    ds = str(payload.get("data_pagamento") or "").strip()
    try:
        pay_date = _date.fromisoformat(ds) if ds else _date.today()
    except ValueError:
        raise HTTPException(status_code=400, detail="Data inválida (use AAAA-MM-DD).")

    if pa.paid_value is None:
        pa.paid_value = _Dec("0")
    restante = _Dec(str(pa.net_value)) - _Dec(str(pa.paid_value))
    vs = str(payload.get("valor") or "").strip().replace(",", ".")
    try:
        val = _Dec(vs) if vs else restante
    except Exception:
        raise HTTPException(status_code=400, detail="Valor inválido.")
    if val <= 0:
        raise HTTPException(status_code=400, detail="Valor deve ser maior que zero.")

    pa.register_payment(val, pay_date)  # paid_value += val; payment_date; update_status → 'pago' se quitado
    await db.commit()
    return {"ok": True, "message": f"Baixa registrada: {pa.description} — R$ {float(val):,.2f} em "
            f"{pay_date.isoformat()} (status {pa.status})."}


@router.post("/action/programar-vtvr-dia")
async def _rd_programar_vtvr_dia(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Programa o VT+VR dos diaristas LANÇADOS no dia (rito diário). NÃO paga — só cria o lote.
    Reusa programar_vt_vr_dos_lancados (idempotente, nunca fabrica chave PIX)."""
    import modules.financial.pagamentos_diaristas_service as _svc
    data = (payload.get("data") or "").strip()
    if not data or len(data) < 8:
        raise HTTPException(status_code=400, detail="Informe o dia (AAAA-MM-DD).")
    r = await _svc.programar_vt_vr_dos_lancados(db, data, created_by=str(getattr(current_user, "id", "")))
    novos = r.get("programados_novos", 0); ja = r.get("ja_programados", 0); sem = r.get("sem_pix", 0)
    if not novos and not ja:
        return {"ok": True, "message": f"Nenhuma diária lançada em {data} — nada a programar."}
    return {"ok": True, "message": f"{data}: {novos} VT+VR programado(s), {ja} já estava(m)."
            + (f" {sem} sem chave PIX (complete o cadastro no Operacional)." if sem else "")}


@router.post("/action/vtvr-avulso")
async def _rd_vtvr_avulso(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """VT+VR avulso: cobertura de falta por CLT ou líder que leva ajudantes (quantidade N = N x R$32)."""
    import modules.financial.pagamentos_diaristas_service as _svc
    data = (payload.get("data") or "").strip()
    ben = (payload.get("beneficiario") or "").strip()
    pix = (payload.get("pix_key") or "").strip()
    try:
        qtd = max(1, int(str(payload.get("quantidade") or "1").strip() or 1))
    except (TypeError, ValueError):
        qtd = 1
    if not data or not ben:
        raise HTTPException(status_code=400, detail="Informe o dia e o beneficiário.")
    r = await _svc.adicionar_manual(db, data=data, beneficiario=ben, pix_key=pix, quantidade=qtd,
                                   user_id=str(getattr(current_user, "id", "")))
    if not r.get("ok", True):
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "Não foi possível adicionar.")
    return {"ok": True, "message": f"{ben}: {qtd} x R$ 32,00 adicionado ao lote de {data}."
            + ("" if pix else " SEM chave PIX — não será pago até completar o cadastro.")}


@router.post("/action/devolver-pix")
async def _rd_devolver_pix(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Devolução de PIX recebido — DINHEIRO QUE SAI. Gate OTP obrigatório (money_gov):
    sem OTP válido consumido nesta request, a API do Inter NÃO é chamada. O disparo real
    é o adapter provado (PUT /pix/v2/pix/{e2e}/devolucao/{id}); devolvemos o retorno REAL
    do banco, nunca sucesso inventado."""
    import uuid as _uuid

    from modules.operacional.controllers.redesign_write_gate import GateError, OTPRequired, money_gov

    e2e = (payload.get("e2e_id") or "").strip()
    motivo = (payload.get("motivo") or "").strip() or "Devolucao solicitada"
    valor = _rd_parse_valor(payload.get("valor"))
    if not e2e:
        raise HTTPException(status_code=400, detail="Selecione o PIX recebido (E2E) a devolver.")
    if valor is None or valor <= 0:
        raise HTTPException(status_code=400, detail="Informe um valor válido (R$) para a devolução.")
    # Confere contra o PIX recebido real: não deixa devolver mais do que entrou.
    orig = (await db.execute(text(
        "SELECT valor FROM inter_pix_recebidos WHERE end_to_end_id = :e LIMIT 1"), {"e": e2e})).scalar()
    if orig is None:
        raise HTTPException(status_code=400, detail="PIX não encontrado na base (sincronize os PIX recebidos).")
    if valor > float(orig):
        raise HTTPException(status_code=400,
                            detail=f"Valor maior que o PIX recebido ({brl(float(orig))}). Devolva até esse valor.")
    otp_code = (payload.get("otp_code") or "").strip()
    ref = (payload.get("_gate_ref") or "").strip() or f"pixrefund:{e2e}:{valor:.2f}"

    async def _dispatch():
        from modules.integrations.banking.controllers.banking_controller import _get_banking_service
        adapter = _get_banking_service()._adapters.get("077")
        if adapter is None:
            raise GateError("Banco Inter não configurado — devolução não disparada.")
        # id da devolução (BACEN: alfanumérico, até 35) — gerado aqui, único por tentativa.
        return await adapter.request_pix_refund(e2e, _uuid.uuid4().hex[:32], valor, motivo)

    try:
        res = await money_gov(db, ref=ref, amount=valor, otp_code=otp_code, real_dispatch=_dispatch,
                              label="devolucao_pix", dest=f"PIX {e2e[:18]}")
    except OTPRequired as e:
        return {"otp_required": True, "ref": e.ref,
                "message": f"Devolução de {brl(valor)} preparada. {e.message}"}
    except GateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if isinstance(res, dict) and res.get("success") is False:
        raise HTTPException(status_code=400, detail=str(res.get("error") or "O Inter recusou a devolução."))
    st = (res or {}).get("status") if isinstance(res, dict) else None
    return {"ok": True, "message": f"Devolução de {brl(valor)} enviada ao Inter."
            + (f" Status: {st}." if st else "")}


@router.post("/action/ajustar-saldo")
async def _rd_ajustar_saldo(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Ajuste manual de saldo de conta — NÃO move dinheiro no banco, mas SOBRESCREVE o
    saldo do sistema e grava uma transação de ajuste no extrato (afeta conciliação e DRE).
    Por isso vai gated por OTP igual a money-out. Reusa a função provada do controller."""
    from decimal import Decimal as _Dec
    from uuid import UUID as _UUID

    from modules.operacional.controllers.redesign_write_gate import GateError, OTPRequired, money_gov

    conta = (payload.get("conta") or "").strip()
    motivo = (payload.get("motivo") or "").strip()
    novo = _rd_parse_valor(payload.get("novo_saldo"))
    if not conta:
        raise HTTPException(status_code=400, detail="Selecione a conta bancária.")
    if novo is None:
        raise HTTPException(status_code=400, detail="Informe o novo saldo (R$).")
    if len(motivo) < 5:
        raise HTTPException(status_code=400, detail="Descreva o motivo do ajuste (mín. 5 caracteres) — fica no extrato.")
    atual = (await db.execute(text(
        "SELECT current_balance FROM bank_accounts WHERE id::text = :i"), {"i": conta})).scalar()
    if atual is None:
        raise HTTPException(status_code=400, detail="Conta bancária não encontrada.")
    otp_code = (payload.get("otp_code") or "").strip()
    ref = (payload.get("_gate_ref") or "").strip() or f"adjbal:{conta}:{novo:.2f}"

    async def _dispatch():
        from modules.financial.controllers.bank_account_controller import adjust_balance as _adj
        from modules.financial.repositories import BankAccountRepository
        await _adj(account_id=_UUID(conta), new_balance=_Dec(str(novo)), reason=motivo,
                   repo=BankAccountRepository(db), session=db, current_user=current_user)
        return {"ok": True, "anterior": float(atual), "novo": float(novo)}

    try:
        # amount=None: não é dinheiro saindo do banco → não consome o teto diário de pagamento.
        res = await money_gov(db, ref=ref, amount=None, otp_code=otp_code, real_dispatch=_dispatch,
                              label="ajuste_saldo", dest=f"conta {conta[:8]} → {brl(novo)}")
    except OTPRequired as e:
        return {"otp_required": True, "ref": e.ref,
                "message": f"Ajuste de {brl(float(atual))} → {brl(novo)} preparado. {e.message}"}
    except GateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        raise HTTPException(status_code=400, detail=f"Falha no ajuste: {str(e)[:200]}") from e
    return {"ok": True, "message": f"Saldo ajustado: {brl(float(atual))} → {brl(novo)}. "
            f"Lançamento de ajuste gravado no extrato (motivo: {motivo[:60]})."}


@router.post("/action/classificar-saidas")
async def _rd_classificar_saidas(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Aplica uma categoria a TODAS as saídas sem classificação de uma contraparte.

    O razão só conhece 6% do extrato porque as saídas não dizem o que são. Isto é o
    mutirão: o sistema sugere por regra, o humano confirma o GRUPO. Só toca saída
    (amount<0) ainda SEM categoria — nunca reclassifica o que já foi decidido.
    NÃO move dinheiro: é rótulo, não pagamento."""
    from modules.financial.services.classificacao_saidas_service import classificar_grupo

    contraparte = str(payload.get("contraparte") or "").strip()
    categoria = str(payload.get("categoria") or "").strip()
    if not categoria:
        raise HTTPException(status_code=400, detail="Escolha a categoria.")
    quem = getattr(current_user, "email", None) or getattr(current_user, "name", None) or "sistema"
    r = await classificar_grupo(db, contraparte=contraparte, categoria=categoria, responsavel=str(quem))
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("erro") or "Não foi possível classificar.")
    return {
        "ok": True,
        "message": f"{r['classificadas']} movimentação(ões) de {r['contraparte'][:34]} "
                   f"classificadas como {r['categoria_label']} — R$ {r['valor']:,.2f}",
        "classificadas": r["classificadas"], "valor": r["valor"],
        "categoria": r["categoria_label"],
    }


@router.post("/action/corrigir-classificacao")
async def _rd_corrigir_classificacao(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Troca a categoria de um grupo JÁ classificado — exige motivo, guarda a anterior.

    `classificar-saidas` só toca no que ainda não tem categoria (protege decisão humana
    de ser sobrescrita). Faltava o caminho inverso: consertar o que foi classificado
    ERRADO. Repõe o lançamento no razão, mas só em competência ABERTA — o passado fica
    como foi fechado. NÃO move dinheiro: é rótulo, não pagamento."""
    from modules.financial.services.classificacao_saidas_service import corrigir_classificacao_grupo

    contraparte = str(payload.get("contraparte") or "").strip()
    categoria = str(payload.get("categoria") or "").strip()
    motivo = str(payload.get("motivo") or "").strip()
    if not categoria:
        raise HTTPException(status_code=400, detail="Escolha a categoria correta.")
    quem = getattr(current_user, "email", None) or getattr(current_user, "name", None) or "sistema"
    r = await corrigir_classificacao_grupo(db, contraparte=contraparte, categoria=categoria,
                                           motivo=motivo, responsavel=str(quem))
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("erro") or "Não foi possível corrigir.")
    _fechado = (f" {r['lancamentos_em_periodo_fechado']} lançamento(s) em competência FECHADA "
                f"não foram tocados." if r["lancamentos_em_periodo_fechado"] else "")
    return {
        "ok": True,
        "message": (f"{r['corrigidas']} movimentação(ões) de {r['contraparte'][:30]} "
                    f"corrigidas de '{', '.join(r['anteriores'])}' para {r['categoria_label']} "
                    f"— R$ {r['valor']:,.2f}. {r['lancamentos_repostos']} lançamento(s) "
                    f"repostos no razão.{_fechado}"),
        "corrigidas": r["corrigidas"], "valor": r["valor"],
    }


@router.post("/action/gerar-parcelas-folha", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_gerar_parcelas_folha(current_user: CurrentActiveUser, payload: dict = Body(...),
                                   db=Depends(get_db)) -> dict:
    """Cria as linhas de pagamento da competência, partidas em parcelas.

    Simula por padrão: `dry_run` só é desligado quando o Jordan escolhe explicitamente
    "NÃO — gravar de verdade". Criar linha de pagamento é criar dinheiro a pagar, e o
    caminho fácil tem que ser o que não grava.
    """
    from modules.financial.services.ordem_pagamento_service import gerar_parcelas

    comp = str(payload.get("competencia") or "").strip()
    if not re.match(r"^\d{4}-\d{2}$", comp):
        raise HTTPException(status_code=400, detail="Competência no formato AAAA-MM (ex.: 2026-08).")
    dry = (str(payload.get("dry_run") or "sim").strip().lower() != "nao")
    try:
        pcts = [int(payload.get("pct1") or 40), int(payload.get("pct2") or 60)]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Percentuais devem ser números.")
    datas = [str(payload.get("data1") or "").strip(), str(payload.get("data2") or "").strip()]
    for d in datas:
        if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
            raise HTTPException(status_code=400,
                                detail="Informe as duas datas no formato AAAA-MM-DD.")
    r = await gerar_parcelas(db, competencia=comp,
                             parcelas=list(zip(pcts, datas)), dry_run=dry)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("erro") or "Não foi possível gerar.")
    linhas = " · ".join(f"{p['percentual']}% em {p['data_prevista']} = {brl(p['total'])}"
                        for p in r["por_parcela"])
    _sc = (f" ⚠️ {len(r['sem_chave'])} sem chave PIX." if r.get("sem_chave") else "")
    prefixo = "SIMULAÇÃO (nada gravado)" if r["dry_run"] else "GRAVADO"
    return {"ok": True, "message": (
        f"{prefixo} — {r['pessoas']} pessoa(s), líquido {brl(r['liquido_total'])} (fonte "
        f"{r['fonte']}). {linhas}. Postos: {', '.join(r['agrupadores'])}.{_sc}")}


@router.post("/action/montar-ordem-pagamento", dependencies=[Depends(_require_financeiro_dep)])
async def _rd_montar_ordem(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Monta o lote da competência. NÃO aprova e NÃO paga — só reserva os itens.

    O teto (CONECTA_LIMITE_DIARIO_PAGAMENTOS) é conferido no serviço, não aqui: guard
    de dinheiro mora junto da regra, não da tela — tela se contorna."""
    from modules.financial.services.ordem_pagamento_service import montar_lote

    comp = str(payload.get("competencia") or "").strip()
    banco = str(payload.get("banco") or "cora").strip().lower()
    if not re.match(r"^\d{4}-\d{2}$", comp):
        raise HTTPException(status_code=400, detail="Competência no formato AAAA-MM (ex.: 2026-08).")
    try:
        parcela = int(payload.get("parcela") or 1)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Parcela deve ser um número (1 ou 2).")
    agrupador = (str(payload.get("agrupador") or "").strip() or None)
    quem = getattr(current_user, "email", None) or getattr(current_user, "name", None) or "sistema"
    r = await montar_lote(db, competencia=comp, banco=banco, criado_por=str(quem),
                          parcela=parcela, agrupador=agrupador)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("erro") or "Não foi possível montar.")
    _sc = (f" ⚠️ {len(r['sem_chave'])} sem chave PIX: {', '.join(r['sem_chave'][:3])}"
           if r.get("sem_chave") else "")
    return {"ok": True, "lote_id": r["lote_id"],
            "message": (f"Lote {r['referencia']}: {r['itens']} pagamentos, {brl(r['total'])}. "
                        f"Folga no teto: {brl(r['folga'])}. ID {r['lote_id']} — use na aba "
                        f"'Aprovar ordem' para gerar o OTP.{_sc}")}


@router.post("/action/aprovar-ordem-pagamento")
async def _rd_aprovar_ordem(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Gera o OTP (passo 1) ou aprova com o código (passo 2). NÃO paga ninguém.

    O código é conferido DENTRO do serviço, contra inter_lote_otp, e consumido no mesmo
    commit que aprova. Nunca chega aqui como booleano: quem chama não pode decidir se o
    OTP passou — isso juntaria propor, aprovar e executar num ator só."""
    from modules.financial.services.ordem_pagamento_service import aprovar_lote, gerar_otp

    lote_id = str(payload.get("lote_id") or "").strip()
    acao = str(payload.get("acao") or "otp").strip().lower()
    if not lote_id:
        raise HTTPException(status_code=400, detail="Informe o ID do lote.")
    if acao == "otp":
        r = await gerar_otp(db, lote_id=lote_id)
        if not r.get("ok"):
            raise HTTPException(status_code=400, detail=r.get("erro") or "Falha ao gerar OTP.")
        return {"ok": True, "message": r.get("mensagem") or r.get("aviso") or
                f"OTP enviado. Válido por {r.get('expira_em_s', 600) // 60} minutos."}
    codigo = str(payload.get("codigo") or "").strip()
    if not codigo:
        raise HTTPException(status_code=400, detail="Informe o código OTP recebido por e-mail.")
    quem = getattr(current_user, "email", None) or getattr(current_user, "name", None) or "sistema"
    r = await aprovar_lote(db, lote_id=lote_id, codigo=codigo, aprovado_por=str(quem))
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("erro") or "Não foi possível aprovar.")
    return {"ok": True, "message": (f"{r['referencia']} liberado: {r['itens']} pagamentos, "
                                    f"{brl(r['total'])}. {r['mensagem']}")}


@router.post("/action/conciliar-classificados")
async def _rd_conciliar_classificados(current_user: CurrentActiveUser, payload: dict = Body(default={})) -> dict:
    """Segunda passada sobre os débitos JÁ CLASSIFICADOS ('justificado').

    Enquanto o contas-a-pagar era casca, um débito de fornecedor não tinha nota
    pra casar e classificar era o fim da linha. Com as NFS-e tomadas registradas
    como pagável, esses débitos podem virar baixa PROVADA — sobem de "explicado
    por uma pessoa" para "ligado ao documento". Mesmo match forte de sempre
    (nome + valor exato + candidato único): não afrouxa nada, não move dinheiro.
    Vale rodar depois de registrar obrigações novas."""
    from starlette.concurrency import run_in_threadpool

    from modules.financial.services.reconciliation_service import conciliar_justificados
    r = await run_in_threadpool(conciliar_justificados)
    ok = r.get("baixados_auto", 0)
    return {
        "ok": True,
        "message": f"{ok} pagável(is) ganharam baixa PROVADA pelo extrato "
                   f"(de {r.get('total_avaliados', 0)} débitos já classificados). "
                   f"{r.get('sem_match', 0)} seguem sem documento que case.",
        "baixados": ok,
        "avaliados": r.get("total_avaliados", 0),
        "sem_match": r.get("sem_match", 0),
        "erros": r.get("erros", 0),
    }


@router.post("/action/conciliar-auto")
async def _rd_conciliar_auto(current_user: CurrentActiveUser, payload: dict = Body(default={}), db=Depends(get_db)) -> dict:
    """Roda o matching automático (extrato × contas a pagar/receber). Bookkeeping — só marca
    reconciliation_status, NÃO move dinheiro. Reusa a função provada conciliar_todas()."""
    from starlette.concurrency import run_in_threadpool

    from modules.financial.services.reconciliation_service import conciliar_todas
    r = await run_in_threadpool(conciliar_todas)
    tot = r.get("total", 0); ok = r.get("conciliados", 0); sm = r.get("sem_match", 0); er = r.get("erros", 0)
    return {"ok": True, "message": f"Conciliação rodada: {ok} conciliada(s), {sm} sem match, "
            f"{er} erro(s) — de {tot} pendente(s) processada(s)."}


@router.post("/action/registrar-cobranca")
async def _rd_registrar_cobranca(current_user: CurrentActiveUser, payload: dict = Body(default={}), db=Depends(get_db)) -> dict:
    """Régua ativa: registra uma tentativa de cobrança no recebível (bookkeeping — NÃO envia
    mensagem nem move dinheiro). Anti-spam por dia no serviço."""
    from modules.financial.services.regua_cobranca_service import registrar_cobranca
    rid = (payload.get("receivable_id") or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="Informe o ID do recebível (da Fila de cobrança).")
    quem = getattr(current_user, "email", "") or str(getattr(current_user, "id", ""))
    r = await registrar_cobranca(db, rid, (payload.get("canal") or "").strip(), quem)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("message") or "Não foi possível registrar.")
    return {"ok": True, "message": r["message"]}


@router.post("/action/conciliar-liquido")
async def _rd_conciliar_liquido(current_user: CurrentActiveUser, payload: dict = Body(default={}), db=Depends(get_db)) -> dict:
    """Conciliação por LÍQUIDO: marca conciliados os créditos do banco que casaram EXATO com o
    líquido das NFS-e (bookkeeping — NÃO move dinheiro). Só os exatos; sugestões ficam de fora."""
    from modules.financial.services.conciliacao_liquido_service import casar_notas_banco
    ini = (payload.get("inicio") or "2026-01-01").strip()
    fim = (payload.get("fim") or "2026-12-31").strip()
    r = await casar_notas_banco(db, ini, fim, persistir=True)
    return {"ok": True, "message": f"Conciliação por líquido: {r['aplicados']} crédito(s) marcados conciliados "
            f"(de {r['n_casados']} casados exatos, {r['pct_casado']}% do faturado). "
            f"{r['n_sugestoes']} sugestão(ões) e {r['n_sem']} sem crédito ficaram para revisão."}


@router.post("/action/postar-provisoes")
async def _rd_postar_provisoes(current_user: CurrentActiveUser, payload: dict = Body(default={}), db=Depends(get_db)) -> dict:
    """Posta no razão as provisões de férias (1/9) e 13º (1/12) sobre a folha REAL, por
    competência. Bookkeeping — NÃO move dinheiro. Gate humano (confirm na tela). Idempotente
    (ref PROVFER-/PROV13- por mês): re-acionar não duplica. Reversível apagando esses refs."""
    from starlette.concurrency import run_in_threadpool

    from modules.financial.services.ledger_auto_service import LedgerAutoService
    r = await run_in_threadpool(LedgerAutoService().lancar_provisoes_trabalhistas)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("erro") or "Falha ao postar provisões."))
    novos = r["provisoes_ferias"] + r["provisoes_13"]
    return {"ok": True, "message": (
        f"Provisões postadas no razão: {r['provisoes_ferias']} de férias + {r['provisoes_13']} de 13º "
        f"({novos} lançamento(s) novo(s); {brl(r['total_provisionado'])} provisionado). "
        "Idempotente — meses já postados não duplicam." if novos else
        f"Nada novo — as provisões ({brl(r['total_provisionado'])}) já estavam postadas. Idempotente.")}


@router.post("/action/postar-inss")
async def _rd_postar_inss(current_user: CurrentActiveUser, payload: dict = Body(default={}), db=Depends(get_db)) -> dict:
    """Posta no razão o INSS retido do empregado (verdade Portte = hr_payslips.inss_value), por
    competência. Reclassificação da folha (D 2.1.2.01 / C 2.1.3.01) — NÃO move dinheiro nem adiciona
    despesa. Gate humano (confirm). Idempotente (ref INSSEMP- por mês). Converge o razão à Portte."""
    from starlette.concurrency import run_in_threadpool

    from modules.financial.services.ledger_auto_service import LedgerAutoService
    r = await run_in_threadpool(LedgerAutoService().lancar_inss_empregado)
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=str(r.get("erro") or "Falha ao postar INSS."))
    n = r.get("lancamentos", 0)
    return {"ok": True, "message": (
        f"INSS-empregado postado no razão: {n} lançamento(s) novo(s), {brl(r.get('total_inss', 0))} "
        "(verdade Portte, hr_payslips). Idempotente." if n else
        f"Nada novo — INSS ({brl(r.get('total_inss', 0))}) já estava postado. Idempotente.")}


@router.post("/action/cobrar-recorrente")
async def _rd_cobrar_recorrente(current_user: CurrentActiveUser, payload: dict = Body(default={}), db=Depends(get_db)) -> dict:
    """Money-IN: EMITE cobranças recorrentes REAIS (PIX/boleto Inter/Cora) do mês/ano aos clientes.
    Gate humano (confirm na tela). Idempotente por cliente/período (não recobra). Reusa a função
    provada gerar_cobrancas_mensais — NÃO é disparo automático (sem beat)."""
    from starlette.concurrency import run_in_threadpool

    try:
        mes = int(str(payload.get("mes") or "").strip()); ano = int(str(payload.get("ano") or "").strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Informe o mês (1-12) e o ano (AAAA).")
    if not (1 <= mes <= 12) or not (2020 <= ano <= 2100):
        raise HTTPException(status_code=400, detail="Mês (1-12) ou ano (AAAA) fora do intervalo.")
    # 07/09/2026: mesma porta, fluxo novo — emite NA conta a receber que o gerador do dia 1 já
    # criou (Eletrônica → Inter, Patrimonial → Cora). O serviço antigo criava contas paralelas.
    from modules.financial.services.cobranca_recebivel_service import emitir_pendentes_mes
    r = await run_in_threadpool(emitir_pendentes_mes, ano, mes, False)
    tv = sum(float(i.get("valor") or 0) for i in r.get("itens", []) if i.get("situacao") == "emitida")
    return {"ok": True, "message": f"Cobranças {mes:02d}/{ano}: {r.get('total', 0)} conta(s), "
            f"{r.get('emitidas', 0)} emitida(s), {brl(tv)}, {len(r.get('erros', []))} pendência(s).",
            "detalhe": r}


# ── Money-IN (cobrança) e gestão — delega às funções do console clássico ──
@router.post("/action/emitir-boleto")
async def _rd_emitir_boleto(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Emite boleto de cobrança (Inter) — delega a generate_boleto do console clássico. Não move dinheiro que sai."""
    from modules.integrations.banking.controllers.banking_controller import BoletoGenerateRequest, generate_boleto
    valor = _rd_parse_valor(payload.get("valor"))
    if valor is None or valor <= 0:
        raise HTTPException(status_code=400, detail="Informe um valor válido (R$).")
    due = (payload.get("vencimento") or "").strip()
    pn = (payload.get("payer_name") or "").strip()
    pd = (payload.get("payer_document") or "").strip()
    if not due:
        raise HTTPException(status_code=400, detail="Informe o vencimento (AAAA-MM-DD).")
    if not pn or not pd:
        raise HTTPException(status_code=400, detail="Informe nome e CPF/CNPJ do pagador.")
    try:
        req = BoletoGenerateRequest(bank_code="077", amount=valor, due_date=due, payer_name=pn,
                                    payer_document=pd, description=(payload.get("descricao") or "Cobrança").strip())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {str(e)[:150]}")
    res = await generate_boleto(req, current_user)
    if not getattr(res, "success", False):
        raise HTTPException(status_code=400, detail=getattr(res, "error", None) or "Falha ao emitir boleto.")
    linha = getattr(res, "digitable_line", None) or getattr(res, "barcode", None) or "—"
    pdf = getattr(res, "pdf_url", None)
    return {"ok": True, "message": f"Boleto emitido. Linha digitável: {linha}." + (f" PDF: {pdf}" if pdf else "")}


@router.post("/action/cobrar-pix")
async def _rd_cobrar_pix(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Gera cobrança PIX (Inter) — delega a generate_pix_charge. Não move dinheiro que sai."""
    from modules.integrations.banking.controllers.banking_controller import PixChargeRequest, generate_pix_charge
    valor = _rd_parse_valor(payload.get("valor"))
    if valor is None or valor <= 0:
        raise HTTPException(status_code=400, detail="Informe um valor válido (R$).")
    try:
        exp = int(str(payload.get("expiracao_horas") or 24).strip() or 24)
    except (ValueError, TypeError):
        exp = 24
    try:
        req = PixChargeRequest(bank_code="077", amount=valor,
                               description=(payload.get("descricao") or "Cobrança Grupo Conecta Mais").strip(),
                               payer_name=(payload.get("payer_name") or "").strip() or None,
                               payer_document=(payload.get("payer_document") or "").strip() or None,
                               expiracao_horas=exp)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {str(e)[:150]}")
    res = await generate_pix_charge(req, current_user)
    if not getattr(res, "success", False):
        raise HTTPException(status_code=400, detail=getattr(res, "error", None) or "Falha ao gerar cobrança PIX.")
    copia = getattr(res, "pix_copy_paste", None) or "—"
    return {"ok": True, "message": f"Cobrança PIX gerada. Copia-e-cola: {copia}"}


@router.post("/action/cancelar-boleto")
async def _rd_cancelar_boleto(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Cancela boleto emitido — delega a cancel_boleto. Sem saída de dinheiro."""
    from modules.integrations.banking.controllers.banking_controller import cancel_boleto
    bid = (payload.get("boleto_id") or "").strip()
    if not bid:
        raise HTTPException(status_code=400, detail="Informe o ID / nosso número do boleto.")
    motivo = (payload.get("motivo") or "ACERTOS").strip().upper()
    if motivo not in ("ACERTOS", "APEDIDODOCLIENTE", "PAGODIRETOAOCLIENTE"):
        motivo = "ACERTOS"
    res = await cancel_boleto(bid, motivo, current_user)
    if isinstance(res, dict) and (res.get("error") or res.get("success") is False):
        raise HTTPException(status_code=400, detail=res.get("error") or "Não foi possível cancelar o boleto.")
    return {"ok": True, "message": "Boleto cancelado."}


@router.post("/action/cancelar-pagamento")
async def _rd_cancelar_pagamento(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Cancela pagamento agendado (antes de executar) — delega a cancel_payment. Sem saída de dinheiro."""
    from modules.integrations.banking.controllers.payment_controller import cancel_payment
    pid = (payload.get("payment_id") or "").strip()
    if not pid:
        raise HTTPException(status_code=400, detail="Informe o ID do pagamento.")
    res = await cancel_payment(pid, current_user)
    if not (isinstance(res, dict) and res.get("success")):
        raise HTTPException(status_code=400, detail=(res or {}).get("mensagem") or "Não foi possível cancelar o pagamento.")
    return {"ok": True, "message": res.get("mensagem") or "Pagamento cancelado."}

# _ligar_lote4_20260908: ver _fin_ligar4.py
