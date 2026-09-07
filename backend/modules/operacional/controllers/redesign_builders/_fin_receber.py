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

    # ── Contas a receber com a COBRANÇA bancária na linha (07/09/2026) ─────────────────────
    # Sobrescreve a tabela base: id na linha, coluna "Cobrança" (boleto/PIX emitido?) e a ação
    # "Emitir cobrança" — Eletrônica → Inter, Patrimonial → Cora. Regra do dono: boleto nasce aqui.
    def _pt(st):
        s_ = (st or "").lower()
        return ("Pago", "ok") if s_ in ("pago", "paga") else ("Parcial", "warn") if s_ == "parcial" else ("Cancelada", "mut") if "cancel" in s_ else ("Pendente", "info")
    out["contas-receber"] = await tbl(
        "Contas a receber", "A receber em aberto e recentes · cobrança bancária emitida pelo Conecta PRO", "Nova cobrança",
        ["Cliente", "Descrição", "Valor", "Vencimento", "Status", "Cobrança"], "1.5fr 1.8fr 1fr 0.9fr 0.8fr 0.9fr",
        "SELECT r.id::text, coalesce(r.customer_name,'—'), coalesce(r.description,'—'), r.net_value, r.due_date, r.status::text, "
        "  CASE WHEN r.boleto_id IS NOT NULL OR r.pix_txid IS NOT NULL THEN "
        "       CASE WHEN r.empresa_id::text = '7d79ed12-d480-4906-b2e0-2b2c4d299bab' THEN 'Cora' ELSE 'Inter' END ELSE '' END, "
        "  r.status::text IN ('pendente','parcial') AND r.boleto_id IS NULL AND r.pix_txid IS NULL AND r.due_date >= current_date "
        "FROM receivable_accounts r ORDER BY (r.status::text IN ('pendente','parcial')) DESC, r.due_date NULLS LAST LIMIT 200",
        lambda r: [t(r[1], 600, "#0F1B3A"), t(r[2]), t(brl(r[3]), 600), t(r[4].strftime('%d/%m/%Y') if r[4] else '—'),
                   b(*_pt(r[5])), b(f"emitida · {r[6]}", "ok") if r[6] else b("sem cobrança", "warn" if r[7] else "mut")],
        actionsfn=lambda r: ([{
            "title": f"Emitir cobrança: {r[1][:40]}",
            "sub": ("Registra o boleto/PIX no banco da empresa credora e grava na conta. "
                    f"{brl(r[3])} · vence {r[4].strftime('%d/%m/%Y') if r[4] else '—'}. Não envia nada ao cliente."),
            "endpoint": f"/api/v1/financial/receivables/{r[0]}/emitir-cobranca",
            "method": "POST", "btnLabel": "Emitir cobrança", "submitLabel": "Emitir no banco",
            "btnStyle": "primary", "okMsg": "Cobrança emitida. Recarregue.", "fields": []}] if r[7] else []))
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

    # ── Recorrência — PRÉVIA do que "Gerar cobranças" faria neste mês, na MESMA base da ação
    # (contas a receber em aberto do mês, sem cobrança bancária). Antes lia clients.mrr — outra
    # base, outro número; a prévia dizia 10 clientes e a ação emitiria outra coisa. ──
    try:
        import asyncio as _aio
        from modules.financial.services.cobranca_recebivel_service import emitir_pendentes_mes
        _hoje = __import__("datetime").date.today()
        prev = await _aio.to_thread(emitir_pendentes_mes, _hoje.year, _hoje.month, True)
        itens = prev.get("itens") or []
        _tot = sum(float(i.get("valor") or 0) for i in itens if i.get("ok"))
        out["recorrencia"] = {
            "title": f"Cobranças a emitir — {_hoje.month:02d}/{_hoje.year}",
            "sub": (f"{prev.get('total', 0)} conta(s) em aberto do mês sem boleto/PIX · {brl(_tot)} prontas para emitir — "
                    "PRÉVIA: nada é emitido por esta tela"),
            "cta": "—", "type": "table", "cols": ["Cliente", "Valor", "Vencimento", "Banco", "Situação"],
            "grid": "2.2fr 1fr 1fr 0.8fr 1.6fr",
            "rows": [{"cells": [t((i.get("cliente") or "—")[:40], 600, "#0F1B3A"), t(brl(i.get("valor") or 0), 600),
                                t(str(i.get("vencimento") or "—")), b((i.get("banco") or "—").capitalize(), "info"),
                                b("Pronta", "ok") if i.get("ok") else b((i.get("erro") or "—")[:60], "warn")]}
                     for i in itens] or [{"cells": [t("Nenhuma conta em aberto do mês sem cobrança", 500), t("—"), t("—"), t("—"), t("—")]}],
            "panelGrid": "1fr",
            "panels": [{"title": "Ciclo do mês (prévia)", "rows": [
                {"left": "Contas prontas", "right": str(sum(1 for i in itens if i.get("ok"))), **S["ok"]},
                {"left": "Com pendência", "right": str(len(prev.get("erros") or [])), **S["warn"]},
                {"left": "Disparo", "right": "Manual — aba 'Gerar cobranças'", **S["info"]},
            ]}],
        }
    except Exception:  # noqa: BLE001
        pass

    # ── Gerar cobranças do mês — AÇÃO (money-IN): emite boleto/PIX REAIS nas contas a receber em
    # aberto do mês (Eletrônica → Inter, Patrimonial → Cora). Exige confirmação humana; idempotente
    # (conta que já tem boleto/PIX não é reemitida). Não envia nada ao cliente. ─
    _hoje = __import__("datetime").date.today()
    out["gerar-cobrancas"] = {
        "title": "Gerar cobranças do mês",
        "sub": ("Emite boleto/PIX no banco de cada empresa credora para TODAS as contas a receber em aberto do "
                "mês ainda sem cobrança. Marque 'só prever' para ver a lista sem emitir. Confira a aba "
                "'Recorrência' antes."),
        "cta": "Gerar cobranças", "type": "form",
        "submit": {"endpoint": "/api/v1/financial/receivables/emitir-cobrancas-mes", "query": True,
                   "confirm": "ATENÇÃO: com 'só prever' desmarcado isto EMITE boletos/PIX REAIS no Inter e na Cora "
                              "para as contas do mês/ano informado. Confirmar?",
                   "okMsg": "Processado — veja o resultado.", "showResult": True},
        "fields": [
            {"key": "ano", "label": "Ano*", "type": "number", "value": _hoje.year, "span": "span 1"},
            {"key": "mes", "label": "Mês*", "type": "number", "value": _hoje.month, "span": "span 1"},
            {"key": "preview", "label": "Só prever (não emite)", "type": "select", "span": "span 2",
             "value": "true", "options": [{"value": "true", "label": "Sim — só listar"},
                                          {"value": "false", "label": "Não — EMITIR de verdade"}]},
        ],
    }

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
