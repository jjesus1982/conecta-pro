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
    initials,
    t,
)

SLUG = "financeiro"

# Menu extra do módulo (mesclado pelo registry) — telas que o clássico tem e o menu do redesign não.
EXTRA_MENU: list[dict] = [
    {"id": "saldos", "label": "Saldos por conta",
     "icon": "M3 21h18M4 10h16M5 10 12 4l7 6M6 10v11M18 10v11M10 10v11M14 10v11"},
    {"id": "pagamentos-pj", "label": "Pagamentos PJ",
     "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"},
    {"id": "pagar-folha-pj", "label": "Pagar folha PJ",
     "icon": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"},
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

    # ---- Fidelidade dashboard: o clássico exibe Faturamento Bruto/Líquido/ISS Retido/Ticket
    #      Médio (NFS-e 12m). Trago como painel ADITIVO — mantém os KPIs de caixa do redesign. ----
    try:
        _fat = (await db.execute(text(
            "SELECT coalesce(sum(valor_servicos),0), coalesce(sum(valor_liquido),0), coalesce(sum(iss_valor),0), count(*) "
            "FROM nfse_emitidas_nacional WHERE coalesce(cancelada,false)=false "
            "AND data_emissao >= (SELECT max(data_emissao) FROM nfse_emitidas_nacional) - interval '12 months'"))).fetchone()
        _bruto, _liq, _iss, _n = float(_fat[0] or 0), float(_fat[1] or 0), float(_fat[2] or 0), (_fat[3] or 0)
        _dash = out.get("dashboard")
        if isinstance(_dash, dict) and _dash.get("type") == "dash":
            _dash["panelGrid"] = "1fr 1fr 1fr"
            _dash.setdefault("panels", []).append({
                "title": "Faturamento NFS-e (12m)", "rows": [
                    {"left": "Faturamento Bruto", "right": brl(_bruto), **S["info"]},
                    {"left": "Faturamento Líquido", "right": brl(_liq), **S["ok"]},
                    {"left": "ISS Retido", "right": brl(_iss), **S["warn"]},
                    {"left": "Ticket Médio", "right": brl(_bruto / _n if _n else 0), **S["mut"]},
                ]})
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

    # ---- Banking (extrato bancário consolidado com contraparte/saldo) ----
    await safe("banking", tbl(
        "Banking", "Extrato bancário consolidado",
        "—", ["Data", "Contraparte", "Descrição", "Valor", "Saldo"], "1fr 1.5fr 2fr 1fr 1fr",
        "SELECT transaction_date, coalesce(counterparty_name,contraparte_nome,'—'), coalesce(description,memo,'—'), amount, balance_after "
        "FROM bank_transactions ORDER BY transaction_date DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0])), t(r[1], 600, "#0F1B3A"), t(r[2]), t(brl(r[3]), 600),
                   t(brl(r[4]) if r[4] is not None else '—')]))

    # ---- Banco Inter (extrato Inter real) ----
    await safe("inter", tbl(
        "Banco Inter", f"{await _scalar(db, 'SELECT count(*) FROM inter_transactions')} lançamentos no extrato Inter",
        "—", ["Data", "Operação", "Descrição", "Valor", "Tipo"], "1fr 0.9fr 2fr 1fr 1.1fr",
        "SELECT data_lancamento, coalesce(tipo_operacao,'—'), coalesce(titulo,descricao,'—'), valor, coalesce(tipo_transacao,'—') "
        "FROM inter_transactions ORDER BY data_lancamento DESC NULLS LAST LIMIT 200",
        lambda r: [t(_fmtdate(r[0])), b("Crédito" if r[1] == 'C' else ("Débito" if r[1] == 'D' else (r[1] or '—')),
                                        "ok" if r[1] == 'C' else "mut"),
                   t(r[2]), t(brl(r[3]), 600, "#0F1B3A"), t(r[4])]))

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
    await safe("nfse-entrada", tbl(
        "NFS-e entrada", f"{await _scalar(db, 'SELECT count(*) FROM nfse_tomadas_nacional')} notas tomadas",
        "—", ["Prestador", "CNPJ", "Empresa", "Competência", "Serviços", "ISS"], "1.8fr 1.3fr 1.6fr 1fr 1fr 1fr",
        "SELECT coalesce(nt.prestador_nome,'—'), coalesce(nt.prestador_cnpj,'—'), "
        "coalesce(e.razao_social, e.nome_fantasia, e.slug, '—'), coalesce(nt.competencia,'—'), nt.valor_servicos, nt.iss_valor "
        "FROM nfse_tomadas_nacional nt LEFT JOIN empresas e ON e.id=nt.empresa_id ORDER BY nt.data_emissao DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A"), t(_cnpj(r[1])), t(r[2]), t(r[3]), t(brl(r[4]), 600),
                   t(brl(r[5]) if r[5] is not None else brl(0))]))

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
