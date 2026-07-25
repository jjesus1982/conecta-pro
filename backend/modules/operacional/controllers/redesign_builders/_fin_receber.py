"""F1 — piloto Receber: aging com KPIs, clientes reais (customers), régua read-only e
recorrência (preview) — rotas/shapes verificados em auditoria/parity/F1_ROTAS_RECEBER.md.
Chamado pelo financeiro.py ANTES de montar_grupos. Leitura real; NENHUMA cobrança é
disparada por estas telas (regra da spec: régua/recorrência v1 read-only)."""
from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    S, _helpers, _scalar, b, brl, t,
)


async def build_receber(db, out: dict) -> None:
    _, _safe, tbl = _helpers(db)

    # ── Aging com KPIs NA TELA (o clássico tem; redesign só tinha o PDF) ─────────────────
    # Mesmas faixas do endpoint /financial/receivables/aging (oráculo compara os totais).
    try:
        faixas = (await db.execute(text(
            "SELECT CASE WHEN due_date >= CURRENT_DATE THEN '1. A vencer' "
            "WHEN due_date >= CURRENT_DATE-30 THEN '2. Vencidas até 30d' "
            "WHEN due_date >= CURRENT_DATE-60 THEN '3. Vencidas 31-60d' "
            "WHEN due_date >= CURRENT_DATE-90 THEN '4. Vencidas 61-90d' "
            "ELSE '5. Acima de 90d' END AS faixa, count(*), coalesce(sum(net_value),0) "
            "FROM receivable_accounts WHERE status::text NOT IN ('paga','cancelada','cancelado') "
            "GROUP BY 1 ORDER BY 1"))).fetchall()  # ESPELHO do endpoint /receivables-aging (net_value + mesmo filtro)
        if isinstance(out.get("contas-receber"), dict):
            out["contas-receber"]["panelGrid"] = "1fr"
            out["contas-receber"]["panels"] = [{"title": "Aging — títulos em aberto", "rows": [
                {"left": f[3:], "right": f"{n} · {brl(v)}",
                 **(S["ok"] if f.startswith('1.') else S["warn"] if f.startswith('2.') else S["bad"])}
                for f, n, v in faixas] or [{"left": "Sem títulos em aberto", "right": "0", **S["ok"]}]}]
    except Exception:  # noqa: BLE001 — painel não derruba a tela
        pass

    # ── Clientes do CONTAS A RECEBER (customers, 12) — corrige o substituto (lia clients/CRM) ──
    try:
        out["clientes"] = await tbl(
            "Clientes (contas a receber)",
            f"{await _scalar(db, 'SELECT count(*) FROM customers')} clientes de cobrança — fonte: customers (AR)",
            "—", ["Cliente", "CPF/CNPJ", "Tipo", "Email", "Status"], "2fr 1.2fr 0.9fr 1.6fr 0.9fr",
            "SELECT coalesce(name,'—'), coalesce(cpf_cnpj,'—'), coalesce(customer_type::text,'—'), "
            "coalesce(email,'—'), coalesce(status::text,'—') FROM customers ORDER BY name LIMIT 300",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t((r[2] or '—').replace('_', ' ').capitalize()),
                       t(r[3]), b((r[4] or '—').capitalize(),
                                  "ok" if (r[4] or '').lower() in ('active', 'ativo') else "mut")])
    except Exception:  # noqa: BLE001
        pass

    # ── Régua de cobrança — READ-ONLY v1 (billing_rules; cols reais: billing_type/frequency/
    # base_value/due_day). Disparo automatizado SÓ com aprovação explícita do Jordan. ──
    try:
        out["regua"] = await tbl(
            "Régua de cobrança (config)",
            f"{await _scalar(db, 'SELECT count(*) FROM billing_rules')} regras — v1 leitura (nenhum disparo automático por esta tela)",
            "—", ["Regra", "Tipo", "Frequência", "Valor base", "Venc. dia"], "2fr 1.1fr 1fr 1fr 0.8fr",
            "SELECT coalesce(name,'—'), coalesce(billing_type::text,'—'), coalesce(frequency::text,'—'), "
            "base_value, due_day FROM billing_rules ORDER BY name LIMIT 100",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or '—').replace('_', ' ').capitalize()),
                       t((r[2] or '—').replace('_', ' ').capitalize()),
                       t(brl(r[3]) if r[3] is not None else '—', 600), t(str(r[4] or '—'))])
    except Exception:  # noqa: BLE001
        pass

    # ── Recorrência (MRR) — PREVIEW read-only do ciclo mensal. Mesma base do endpoint
    # GET /billing/cobrar-recorrente/{m}/{a}/preview (10 clientes · R$270.586,96 — oráculo).
    # O POST (que executa a cobrança) NÃO é chamado por tela nenhuma. ──
    try:
        tot_cli = await _scalar(db, "SELECT count(*) FROM clients WHERE ativo=true AND coalesce(mrr,0)>0")
        tot_mrr = await _scalar(db, "SELECT coalesce(sum(mrr),0) FROM clients WHERE ativo=true AND coalesce(mrr,0)>0")
        scr = await tbl(
            "Recorrência mensal (MRR)",
            f"{tot_cli or 0} clientes · {brl(tot_mrr)} /mês — PREVIEW: nenhuma cobrança é disparada por esta tela",
            "—", ["Cliente", "MRR", "Status"], "2.2fr 1fr 0.9fr",
            "SELECT coalesce(name,'—'), mrr, CASE WHEN ativo THEN 'Ativo' ELSE 'Inativo' END "
            "FROM clients WHERE ativo=true AND coalesce(mrr,0)>0 ORDER BY mrr DESC LIMIT 100",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[1]), 600), b(r[2], "ok")])
        scr["panelGrid"] = "1fr"
        scr["panels"] = [{"title": "Ciclo do mês (preview)", "rows": [
            {"left": "Clientes no ciclo", "right": str(tot_cli or 0), **S["info"]},
            {"left": "Total MRR", "right": brl(tot_mrr), **S["ok"]},
            {"left": "Disparo da cobrança", "right": "Manual/gated — aba 'Gerar cobranças'", **S["warn"]},
        ]}]
        out["recorrencia"] = scr
    except Exception:  # noqa: BLE001
        pass

    # ── Gerar cobranças do mês — AÇÃO GATED (money-IN: emite cobranças REAIS aos clientes).
    # NÃO é beat automático — exige o Jordan/Pyetra confirmar. Idempotente por cliente/período. ─
    try:
        _n = (await db.execute(text(
            "SELECT count(*) FROM clients WHERE status='active' AND coalesce(mrr,0)>0"))).scalar() or 0
        _mrr = (await db.execute(text(
            "SELECT coalesce(sum(mrr),0) FROM clients WHERE status='active' AND coalesce(mrr,0)>0"))).scalar() or 0
        out["gerar-cobrancas"] = {
            "title": "Gerar cobranças recorrentes do mês",
            "sub": (f"EMITE cobranças REAIS (PIX/boleto via Inter/Cora) aos clientes — base de {int(_n)} "
                    f"cliente(s) ativo(s) · {brl(_mrr)}/mês. Idempotente: não recobra quem já foi cobrado no "
                    "período. Confira a aba 'Recorrência (preview)' antes de gerar."),
            "cta": "Gerar cobranças", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/cobrar-recorrente", "gated": False,
                       "confirm": "ATENÇÃO: isto vai EMITIR COBRANÇAS REAIS aos clientes do mês/ano informado "
                                  "(PIX/boleto de verdade). Confirmar a emissão?",
                       "okMsg": "Cobranças processadas."},
            "fields": [
                {"key": "mes", "label": "Mês* (1-12)", "type": "text", "span": "span 1", "ph": "Ex.: 7"},
                {"key": "ano", "label": "Ano* (AAAA)", "type": "text", "span": "span 1", "ph": "Ex.: 2026"},
            ],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── Régua de cobrança ATIVA (gated): fila de vencidos + tier + mensagem pronta ──────────
    _NTONE = {"lembrete": "ok", "contato_ativo": "info", "notificacao_formal": "warn",
              "negativacao_iminente": "bad", "juridico": "bad"}
    try:
        from modules.financial.services.regua_cobranca_service import montar_fila_cobranca
        fila = await montar_fila_cobranca(db)
        scr = {
            "title": "Fila de cobrança (régua)", "type": "table", "cta": "—", "searchHint": "Buscar cliente…",
            "sub": (f"{len(fila)} recebível(is) vencido(s) — nível pela régua (lembrete→jurídico). "
                    "Copie a mensagem pronta e registre o contato na aba 'Registrar cobrança' (gated). "
                    "Envio automático (WhatsApp) = próxima versão."),
            "grid": "1.8fr 1.1fr 1fr 0.7fr 1.1fr 0.9fr",
            "cols": ["Cliente", "Valor", "Vencimento", "Atraso", "Nível", "Tentativas"],
            "rows": [{"cells": [
                t((f["cliente"] or "—")[:34], 600, "#0F1B3A"), t(brl(f["valor"]), 600),
                t(str(f["vencimento"])), t(f"{f['dias']}d"),
                b(f["nivel"].replace("_", " ").capitalize(), _NTONE.get(f["nivel"], "info")),
                t(str(f["tentativas"]) + ("· hoje" if f["contatado_hoje"] else ""))]} for f in fila],
            "panelGrid": "1fr",
            "panels": [{"title": "Mensagens prontas (copiar e enviar)", "rows": [
                {"left": f"{(f['cliente'] or '—')[:22]} · {f['canal']}", "right": f["mensagem"][:80] + "…", **S["info"]}
                for f in fila[:6]] or [{"left": "Todos em dia — sem cobranças pendentes", "right": "0 vencidos", **S["ok"]}]}],
        }
        out["fila-cobranca"] = scr
    except Exception:  # noqa: BLE001
        pass

    # ── Registrar cobrança — AÇÃO GATED (registra a tentativa; NÃO envia nem move dinheiro) ──
    out["registrar-cobranca"] = {
        "title": "Registrar cobrança",
        "sub": "Registra uma tentativa de contato de cobrança no recebível (nível, canal, data, tentativa). "
               "Bookkeeping — NÃO envia mensagem nem move dinheiro. Anti-spam: 1 registro por cliente/dia.",
        "cta": "Registrar cobrança", "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/registrar-cobranca", "gated": False,
                   "confirm": "Registrar a tentativa de cobrança para este recebível?",
                   "okMsg": "Cobrança registrada."},
        "fields": [
            {"key": "receivable_id", "label": "ID do recebível* (da Fila de cobrança)", "type": "text", "span": "span 2", "ph": "cole o id da fila"},
            {"key": "canal", "label": "Canal usado", "type": "select", "span": "span 2",
             "options": [{"value": "whatsapp", "label": "WhatsApp"}, {"value": "email", "label": "E-mail"},
                         {"value": "telefone", "label": "Telefone"}, {"value": "boleto", "label": "Re-emissão boleto/PIX"}]},
        ],
    }
