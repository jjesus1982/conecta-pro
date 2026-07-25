"""
redesign_builders/financeiro.py — T4 (cluster financeiro/comercial).
Sobrescreve o _build_financeiro do monólito: reusa a base (dashboard, contas a
pagar/receber, clientes, fornecedores, diaristas, Inter, formulários) e ADICIONA
as ~21 telas que faltavam, todas lendo o DADO REAL do clássico.

Regra de ouro: dinheiro que SAI e transmissão legal = GATED (só visibilidade).
Nunca fabricar dado — vazio real = tabela honesta "aguardando dado".
Ver auditoria/parity/DIVISAO_3T.md + BRIEFING_T4.md.
"""
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

SLUG = "financeiro"

# F0: menu extra ZERADO — as antigas entradas viram ABAS dos 7 grupos (_fin_grupos.py).
# As telas continuam montadas no build; só saem da navegação de topo.
EXTRA_MENU: list[dict] = []


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
    return {"title": "Saldos por conta",
            "sub": "Inter e Cora — saldo do último sync (a cada 15 min); a data mostra o quão fresco está",
            "cta": "—", "type": "table", "searchHint": "Buscar…",
            "grid": "1.6fr 1.2fr 1.1fr 1.1fr 0.9fr",
            "cols": ["Conta", "Banco", "Saldo", "Atualizado", "Status"], "rows": cells}


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
    #      Médio (NFS-e 12m). Trago como painel ADITIVO — mantém os KPIs de caixa do redesign. ----
    try:
        _fat = (await db.execute(text(
            "SELECT coalesce(sum(valor_servicos),0), coalesce(sum(valor_liquido),0), coalesce(sum(iss_valor),0), count(*) "
            "FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false "
            "AND data_emissao >= (SELECT max(data_emissao) FROM nfse_emitidas_nacional) - interval '12 months'"))).fetchone()
        _bruto, _liq, _iss, _n = float(_fat[0] or 0), float(_fat[1] or 0), float(_fat[2] or 0), (_fat[3] or 0)
        # Faturamento por Cliente (12m) — o clássico exibe; dado real de nfse
        _porcli = (await db.execute(text(
            "SELECT coalesce(tomador_nome,'—'), sum(valor_servicos) FROM nfse_emitidas_nacional "
            "WHERE coalesce(cancelada,false)=false AND data_emissao >= (SELECT max(data_emissao) FROM nfse_emitidas_nacional) - interval '12 months' "
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
        "SELECT coalesce(competencia,'—'), coalesce(beneficiario,'—'), coalesce(empresa_slug,'—'), valor, coalesce(status,'—'), nf_exigida, nf_ok "
        "FROM financial_pagamentos_pj ORDER BY competencia DESC NULLS LAST, valor DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1], 600, "#0F1B3A", initials(r[1])),
                   t((r[2] or '—').replace('_', ' ').title()), t(brl(r[3]), 600),
                   _nf(r[5], r[6]), b((r[4] or '—').replace('_', ' ').capitalize(), _pj_tone.get((r[4] or '').lower(), "info"))]))

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
    await safe("banking", tbl(
        "Banking", "Extrato bancário consolidado (todas as contas)",
        "—", ["Data", "Banco", "Contraparte", "Descrição", "Valor", "Saldo"], "1fr 1fr 1.4fr 1.8fr 1fr 1fr",
        "SELECT bt.transaction_date, coalesce(ba.bank_name,'—'), coalesce(bt.counterparty_name,bt.contraparte_nome,'—'), "
        "coalesce(bt.description,bt.memo,'—'), bt.amount, bt.balance_after "
        "FROM bank_transactions bt LEFT JOIN bank_accounts ba ON ba.id=bt.bank_account_id "
        "ORDER BY bt.transaction_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0])), b(r[1] or '—', "info"), t(r[2], 600, "#0F1B3A"), t(r[3]), t(brl(r[4]), 600),
                   t(brl(r[5]) if r[5] is not None else '—')]))

    # ---- Banco Inter (extrato Inter real) ----
    await safe("inter", tbl(
        "Banco Inter", f"{await _scalar(db, 'SELECT count(*) FROM inter_transactions')} lançamentos no extrato Inter",
        "—", ["Data", "Operação", "Descrição", "Valor", "Tipo"], "1fr 0.9fr 2fr 1fr 1.1fr",
        "SELECT data_lancamento, coalesce(tipo_operacao,'—'), coalesce(titulo,descricao,'—'), valor, coalesce(tipo_transacao,'—') "
        "FROM inter_transactions ORDER BY data_lancamento DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0])), b("Crédito" if r[1] == 'C' else ("Débito" if r[1] == 'D' else (r[1] or '—')),
                                        "ok" if r[1] == 'C' else "mut"),
                   t(r[2]), t(brl(r[3]), 600, "#0F1B3A"), t(r[4])]))

    # ---- Banco Cora (extrato Cora real — bank_transactions da conta Cora, bank_code 403) ----
    _cora_n = await _scalar(db, "SELECT count(*) FROM bank_transactions bt JOIN bank_accounts ba ON ba.id=bt.bank_account_id WHERE ba.bank_code='403'")
    await safe("cora", tbl(
        "Banco Cora", f"{_cora_n} lançamentos no extrato Cora",
        "—", ["Data", "Contraparte", "Descrição", "Valor", "Tipo"], "1fr 1.5fr 2fr 1fr 1.1fr",
        "SELECT bt.transaction_date, coalesce(bt.counterparty_name,bt.contraparte_nome,'—'), coalesce(bt.description,bt.memo,'—'), "
        "bt.amount, coalesce(bt.transaction_type,'—') "
        "FROM bank_transactions bt JOIN bank_accounts ba ON ba.id=bt.bank_account_id "
        "WHERE ba.bank_code='403' ORDER BY bt.transaction_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0])), t(r[1], 600, "#0F1B3A"), t(r[2]), t(brl(r[3]), 600),
                   b("Crédito" if (r[4] or '').lower() in ('credit', 'credito', 'c') else "Débito",
                     "ok" if (r[4] or '').lower() in ('credit', 'credito', 'c') else "mut")]))

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
        "SELECT coalesce(numero,'—'), coalesce(competencia,'—'), coalesce(tomador_nome,'—'), valor_servicos, valor_liquido "
        "FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false ORDER BY data_emissao DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]), t(brl(r[3]), 600), t(brl(r[4]))]))

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
        ],
    }
    out["pagar-diaristas"] = {
        "title": "Pagar diaristas (Inter)",
        "sub": "Dinheiro que SAI — 2 etapas: gera o código OTP (e-mail ao Jordan) e só paga ao confirmar. Nunca dispara sozinho. Paga o lote 'a_revisar' do dia.",
        "cta": "Gerar código de pagamento", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/pagar-diaristas", "gated": True,
                   "confirm": "Isto vai PAGAR o lote de diaristas (Inter) do dia via PIX. Gerar o código OTP para o Jordan confirmar?",
                   "okMsg": "Lote processado."},
        "fields": [
            {"key": "data", "label": "Data* (AAAA-MM-DD)", "type": "date", "span": "span 2"},
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
                   "confirm": "Isto vai PAGAR um boleto via Inter. Gerar o código OTP para o Jordan confirmar?",
                   "okMsg": "Boleto pago."},
        "fields": [
            {"key": "codigo_barras", "label": "Código de barras / linha digitável*", "type": "text", "span": "span 2", "ph": "34191... (47-48 dígitos)"},
            {"key": "valor", "label": "Valor* (R$)", "type": "text", "span": "span 1", "ph": "1.234,56"},
            {"key": "data", "label": "Data do pagamento (AAAA-MM-DD)", "type": "date", "span": "span 1"},
            {"key": "descricao", "label": "Descrição", "type": "text", "span": "span 2", "ph": "Ex.: Energia, ISS, fornecedor X"},
        ],
    }

    # ---- Enviar PIX / Transferência — money-out via InterPaymentService + OTP ----
    out["enviar-pix"] = {
        "title": "Enviar PIX / Transferência (Inter)",
        "sub": "Dinheiro que SAI — 2 etapas + OTP. Por chave PIX ou colando um PIX copia-e-cola.",
        "cta": "Preparar e gerar OTP", "type": "form",
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
    montar_grupos(out)

    return out


# ── ESCRITA (router incluído pelo registry). Dinheiro que SAI = SEMPRE gate humano.
router = APIRouter()


@router.post("/action/pagar-folha-pj")
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
    return {"ok": True, "message": f"Lote pago: {r.get('pagos', 0)} pago(s), {r.get('falhas', 0)} falha(s)."}


@router.post("/action/pagar-diaristas")
async def _rd_pagar_diaristas(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Pagar lote de diaristas (Inter) — DELEGA ao serviço provado (OTP próprio). Mesmo
    padrão do pagar-folha-pj: sem otp_code → gera código; com otp_code → paga real.
    Sem OTP válido, nada é pago."""
    import modules.financial.pagamentos_diaristas_service as svc
    data = (payload.get("data") or "").strip()
    if not data or len(data) < 8:
        raise HTTPException(status_code=400, detail="Informe a data (AAAA-MM-DD) do lote.")
    otp_code = (payload.get("otp_code") or "").strip()
    lote_id = (payload.get("_gate_ref") or "").strip()
    if not otp_code:
        r = await svc.gerar_otp_lote(db, data=data)
        if not r.get("ok"):
            raise HTTPException(status_code=400, detail=r.get("mensagem") or "Nenhum item elegível.")
        return {"otp_required": True, "ref": r.get("lote_id", ""),
                "message": f"{r.get('quantidade')} diarista(s) · R$ {float(r.get('total') or 0):.2f}. Confirme com o código OTP."}
    r = await svc.executar_lote(db, data=data, confirmar=True, otp_code=otp_code,
                                lote_id=lote_id or None, user_id=str(getattr(current_user, "id", "")))
    if r.get("otp_invalido") or r.get("otp_requerido"):
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "OTP inválido ou obrigatório.")
    if not r.get("ok"):
        raise HTTPException(status_code=400, detail=r.get("mensagem") or "Não foi possível executar o lote.")
    return {"ok": True, "message": f"Lote pago: {r.get('pagos', 0)} pago(s), {r.get('falhas', 0)} falha(s)."}


# ── Money-out genérico (boleto/PIX/TED/DARF) via InterPaymentService — 2 fases + OTP ──
def _rd_parse_valor(s):
    s = str(s or "").strip().replace("R$", "").replace(" ", "")
    if not s:
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
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
    origem = (payload.get("origem") or "inter").strip().lower()
    if origem not in ("inter", "cora"):
        origem = "inter"
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


@router.post("/action/pagar-boleto")
async def _rd_pagar_boleto(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    return await _rd_inter_pay(db, current_user, payload, payment_type="boleto",
                               categoria="fornecedor", dest_fn=_dest_boleto, label="Pagamento de boleto")


@router.post("/action/enviar-pix")
async def _rd_enviar_pix(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    return await _rd_inter_pay(db, current_user, payload, payment_type="pix",
                               categoria="transferencia", dest_fn=_dest_pix, label="PIX")


@router.post("/action/transferir-ted")
async def _rd_transferir_ted(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    return await _rd_inter_pay(db, current_user, payload, payment_type="ted_interno",
                               categoria="transferencia", dest_fn=_dest_ted, label="Transferência TED")


@router.post("/action/pagar-darf")
async def _rd_pagar_darf(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    return await _rd_inter_pay(db, current_user, payload, payment_type="darf",
                               categoria="imposto", dest_fn=_dest_darf, label="Pagamento de DARF")


@router.post("/action/pagar-gps")
async def _rd_pagar_gps(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    return await _rd_inter_pay(db, current_user, payload, payment_type="gps",
                               categoria="imposto", dest_fn=_dest_gps, label="Pagamento de GPS")


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
    from modules.financial.services.recurring_billing_service import gerar_cobrancas_mensais
    r = await run_in_threadpool(gerar_cobrancas_mensais, mes, ano, False)
    if isinstance(r, dict) and r.get("success") is False:
        raise HTTPException(status_code=400, detail=str(r.get("error") or "Falha ao gerar cobranças."))
    tc = (r or {}).get("total_clientes", 0); tv = (r or {}).get("total_cobrado", 0); er = (r or {}).get("erros", 0)
    return {"ok": True, "message": f"Cobranças {mes:02d}/{ano}: {tc} cliente(s) processado(s), "
            f"{brl(tv)} cobrado, {er} erro(s)."}


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
