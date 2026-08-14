"""F3 — Pagar: aging com KPIs (espelho do endpoint /payables/aging: sum(net_value),
status NOT IN ('pago','cancelado')), fila de aprovação (LEITURA — aprovar segue ação
humana gated fora desta tela) e AUDIT LOG dos pagamentos Inter (trilha real da tabela:
prepared_by/approved_by/otp/executed_at). Nenhum pagamento é disparado por estas telas."""
from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    S, _fmtdate, _helpers, _scalar, b, brl, t,
)


async def build_pagar(db, out: dict) -> None:
    _, _safe, tbl = _helpers(db)

    # ── ORDEM DE PAGAMENTO: aprovado aqui, executado no app do banco ───────────────────
    # O Cora não envia PIX por API e 99,8% do que sai da Patrimonial é PIX. Então o
    # pagamento continua no celular — mas a DECISÃO vive aqui: lote com teto e OTP.
    # O extrato do dia seguinte fecha cada item pelo CPF + valor (beat 08:40).
    try:
        import os as _os
        _teto_ordem = float(_os.getenv("CONECTA_LIMITE_DIARIO_PAGAMENTOS", "100000.00"))
        _lotes = (await db.execute(text("""
            SELECT l.id::text, l.referencia, l.competencia, l.banco, l.status,
                   l.total_centavos, l.qtd_itens, coalesce(l.aprovado_por,'—') AS quem,
                   (SELECT count(*) FROM payroll_payments p
                     WHERE p.lote_ordem_id = l.id AND p.status = 'aguardando_app') AS falta,
                   (SELECT count(*) FROM payroll_payments p
                     WHERE p.lote_ordem_id = l.id AND p.status = 'pago') AS ok
            FROM folha_lote_ordem l ORDER BY l.created_at DESC LIMIT 40
        """))).fetchall()
        _TONE = {"RASCUNHO": "warn", "APROVADO": "info", "EXECUTANDO": "info",
                 "CONCLUIDO": "ok", "CONCLUIDO_PARCIAL": "warn", "CANCELADO": "bad"}
        out["ordens-pagamento"] = {
            "title": "Ordens de pagamento",
            "sub": (f"Lote aprovado AQUI (teto {brl(_teto_ordem)} + OTP), executado no app do "
                    f"banco, e o extrato de amanhã fecha cada item sozinho pelo CPF. "
                    f"Aprovar NÃO paga ninguém — libera a ordem."),
            "cta": "—", "type": "table", "searchHint": "Buscar competência…",
            "cols": ["Referência", "Competência", "Status", "Itens", "Total", "Pagos", "Aprovado por"],
            "grid": "1.6fr 1fr 1.1fr 0.7fr 1.1fr 0.9fr 1.4fr",
            "rows": [{"cells": [
                t(r[1], 600, "#0F1B3A"), t(r[2]), b(r[4].replace("_", " ").capitalize(), _TONE.get(r[4], "info")),
                t(str(r[6])), t(brl(r[5] / 100), 600),
                t(f"{r[9]}/{r[6]}" + (f" · faltam {r[8]}" if r[8] else "")),
                t(str(r[7])[:26])]} for r in _lotes],
        }

        # Itens liberados para executar no app — a "lista de compras" do Jordan.
        out["executar-no-app"] = await tbl(
            "Executar no app do banco",
            "Pagamentos já aprovados com OTP. Pague no app e NÃO precisa voltar aqui: "
            "o extrato de amanhã reconhece cada um pelo CPF e valor (beat 08:40).",
            "—", ["Funcionário", "CPF", "Chave PIX", "Competência", "Valor"],
            "1.8fr 1.1fr 1.4fr 0.9fr 1fr",
            """SELECT e.nome, coalesce(e.cpf,'—'), coalesce(p.pix_key, e.pix_key, '— sem chave —'),
                      lpad(p.mes::text,2,'0') || '/' || p.ano, p.valor_liquido
                 FROM payroll_payments p JOIN employees e ON e.id = p.employee_id
                WHERE p.status = 'aguardando_app' ORDER BY p.valor_liquido DESC""",
            lambda r: [t(r[0][:32], 600, "#0F1B3A"), t(str(r[1])), t(str(r[2])[:26]),
                       t(str(r[3])), t(brl(r[4]), 600)])

        # Montar: só isso não aprova nada.
        out["montar-ordem"] = {
            "title": "Montar ordem de pagamento",
            "sub": ("Junta os pagamentos pendentes da competência num lote. NÃO aprova e NÃO "
                    f"paga — só reserva. Recusa se passar do teto de {brl(_teto_ordem)}."),
            "cta": "Montar lote", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/montar-ordem-pagamento",
                       "okMsg": "Lote montado. Gere o OTP para aprovar."},
            "fields": [
                {"key": "competencia", "label": "Competência* (AAAA-MM)", "type": "text",
                 "span": "span 1", "ph": "Ex.: 2026-08"},
                {"key": "banco", "label": "Banco onde vai pagar*", "type": "select", "span": "span 1",
                 "value": "cora", "options": [{"value": "cora", "label": "Cora (Patrimonial)"},
                                              {"value": "inter", "label": "Inter (Eletrônica)"}]},
                {"key": "parcela", "label": "Parcela", "type": "select", "span": "span 1",
                 "value": "1", "options": [{"value": "1", "label": "1ª — adiantamento (40%)"},
                                           {"value": "2", "label": "2ª — saldo (60%)"}]},
                {"key": "agrupador", "label": "Posto (vazio = todos num lote só)", "type": "text",
                 "span": "span 1", "ph": "Ex.: VILLA DOS PASSAROS"},
            ],
        }
        # Gerar as parcelas ANTES de montar lote: sem linha de pagamento não há o que
        # reservar. Simula por padrão — a tela chama com dry_run e só grava quando o
        # Jordan marca 'nao'. Criar linha de pagamento é criar dinheiro a pagar.
        out["gerar-parcelas"] = {
            "title": "Gerar parcelas da folha",
            "sub": ("Lê os holerites da competência (fonte Portte, só folha mensal) e cria as "
                    "linhas de pagamento partidas em 40% e 60%. A última parcela leva a sobra "
                    "do arredondamento, então a soma fecha o líquido exato. Simula por padrão."),
            "cta": "Gerar", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/gerar-parcelas-folha",
                       "okMsg": "Parcelas processadas."},
            "fields": [
                {"key": "competencia", "label": "Competência* (AAAA-MM)", "type": "text",
                 "span": "span 1", "ph": "Ex.: 2026-08"},
                {"key": "dry_run", "label": "Só simular?", "type": "select", "span": "span 1",
                 "value": "sim", "options": [{"value": "sim", "label": "Sim — só mostrar"},
                                             {"value": "nao", "label": "NÃO — gravar de verdade"}]},
                {"key": "pct1", "label": "1ª parcela (%)", "type": "text", "span": "span 1",
                 "value": "40"},
                {"key": "data1", "label": "Quando sai a 1ª* (AAAA-MM-DD)", "type": "text",
                 "span": "span 1", "ph": "Ex.: 2026-08-20"},
                {"key": "pct2", "label": "2ª parcela (%)", "type": "text", "span": "span 1",
                 "value": "60"},
                {"key": "data2", "label": "Quando sai a 2ª* (AAAA-MM-DD)", "type": "text",
                 "span": "span 1", "ph": "Ex.: 2026-09-05"},
            ],
        }
        out["aprovar-ordem"] = {
            "title": "Aprovar ordem de pagamento (OTP)",
            "sub": ("Gere o código, receba por e-mail e confirme. O código é conferido AQUI "
                    "DENTRO e consumido na mesma operação — não vale duas vezes. "
                    "Aprovar libera a ordem; quem paga é você, no app do banco."),
            "cta": "Aprovar lote", "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/aprovar-ordem-pagamento",
                       "confirm": "Confirmar a aprovação deste lote? Isto NÃO paga ninguém — "
                                  "libera a ordem para você executar no app.",
                       "okMsg": "Ordem liberada."},
            "fields": [
                {"key": "lote_id", "label": "ID do lote*", "type": "text", "span": "span 2",
                 "ph": "copie da aba 'Ordens de pagamento'"},
                {"key": "acao", "label": "O que fazer*", "type": "select", "span": "span 1",
                 "value": "otp", "options": [{"value": "otp", "label": "1) Gerar e enviar o OTP"},
                                             {"value": "aprovar", "label": "2) Aprovar com o código"}]},
                {"key": "codigo", "label": "Código OTP (só no passo 2)", "type": "text",
                 "span": "span 1", "ph": "6 dígitos"},
            ],
        }
    except Exception as _e:  # noqa: BLE001 — tela nunca derruba o módulo
        import logging
        logging.getLogger(__name__).warning("[ordens-pagamento] %s", _e)

    # ── Aging na tela (espelho EXATO do endpoint /financial/payables/aging) ─────────────
    try:
        faixas = (await db.execute(text(
            "SELECT CASE WHEN due_date >= CURRENT_DATE THEN '1. A vencer' "
            "WHEN due_date >= CURRENT_DATE-30 THEN '2. Vencidas até 30d' "
            "WHEN due_date >= CURRENT_DATE-60 THEN '3. Vencidas 31-60d' "
            "WHEN due_date >= CURRENT_DATE-90 THEN '4. Vencidas 61-90d' "
            "ELSE '5. Acima de 90d' END AS faixa, count(*), coalesce(sum(net_value),0) "
            "FROM payable_accounts WHERE status::text NOT IN ('pago','cancelado') "
            "GROUP BY 1 ORDER BY 1"))).fetchall()
        if isinstance(out.get("contas-pagar"), dict):
            out["contas-pagar"]["panelGrid"] = "1fr"
            out["contas-pagar"]["panels"] = [{"title": "Aging — contas em aberto", "rows": [
                {"left": f[3:], "right": f"{n} · {brl(v)}",
                 **(S["ok"] if f.startswith('1.') else S["warn"] if f.startswith('2.') else S["bad"])}
                for f, n, v in faixas] or [{"left": "Sem contas em aberto", "right": "0", **S["ok"]}]}]
    except Exception:  # noqa: BLE001
        pass

    # ── Fila de aprovação (LEITURA) — inter_payments preparados + payables requires_approval.
    # Aprovar/agendar = ação humana no fluxo gated (OTP); esta tela SÓ mostra a fila. ──
    try:
        n_prep = await _scalar(db, "SELECT count(*) FROM inter_payments WHERE lower(status)='preparado'")
        n_req = await _scalar(db, "SELECT count(*) FROM payable_accounts WHERE requires_approval=true AND coalesce(approval_status::text,'') NOT IN ('approved','aprovado')")
        scr = await tbl(
            "Fila de aprovação (D7)",
            f"{(n_prep or 0)} pagamento(s) Inter preparado(s) · {(n_req or 0)} conta(s) exigindo aprovação — aprovar é ação humana gated (fora desta tela)",
            "—", ["Origem", "Descrição", "Valor", "Preparado em", "Status"], "1fr 1.8fr 1fr 1fr 0.9fr",
            "SELECT 'Inter', coalesce(destinatario->>'nome_recebedor', destinatario->>'chave', left(destinatario->>'codigo_barras',22), payment_type), "
            "valor, created_at, coalesce(status,'—') FROM inter_payments WHERE lower(status)='preparado' "
            "UNION ALL "
            "SELECT 'Contas a pagar', coalesce(description,'—'), net_value, created_at, coalesce(approval_status::text,'aguardando') "
            "FROM payable_accounts WHERE requires_approval=true AND coalesce(approval_status::text,'') NOT IN ('approved','aprovado') "
            "ORDER BY 4 DESC LIMIT 100",
            lambda r: [b(r[0], "info"), t((r[1] or '—')[:44], 600, "#0F1B3A"),
                       t(brl(r[2]) if r[2] is not None else '—', 600), t(_fmtdate(r[3])),
                       b((r[4] or '—').capitalize(), "warn")])
        if not scr.get("rows"):
            scr["sub"] = "Nenhum pagamento aguardando aprovação — fila vazia (dado real)"
        out["fila-aprovacao"] = scr
    except Exception:  # noqa: BLE001
        pass

    # ── AUDIT LOG dos pagamentos Inter — trilha REAL da tabela (quem preparou/aprovou,
    # OTP usado, quando executou/confirmou/cancelou). Era só do clássico; agora exposta. ──
    _atone = {"confirmado": "ok", "executado": "ok", "preparado": "warn", "cancelado": "mut", "erro": "bad"}
    try:
        out["audit-log"] = await tbl(
            "Audit log de pagamentos (Inter)",
            f"{await _scalar(db, 'SELECT count(*) FROM inter_payments')} pagamentos — trilha completa de auditoria",
            "—", ["Destinatário", "Valor", "Preparado por", "Aprovado por", "OTP", "Executado", "Status"],
            "1.6fr 0.9fr 1.1fr 1.1fr 0.6fr 1fr 0.9fr",
            "SELECT coalesce(p.destinatario->>'nome_recebedor', p.destinatario->>'chave', left(p.destinatario->>'codigo_barras',18), p.payment_type), "
            "p.valor, coalesce(u1.email, left(p.prepared_by::text,8), '—'), coalesce(u2.email, left(p.approved_by::text,8), '—'), "
            "(p.approval_otp_used IS NOT NULL AND p.approval_otp_used<>''), "
            "coalesce(p.executed_at, p.confirmed_at, p.cancelled_at), coalesce(p.status,'—') "
            "FROM inter_payments p LEFT JOIN users u1 ON u1.id=p.prepared_by LEFT JOIN users u2 ON u2.id=p.approved_by "
            "ORDER BY p.created_at DESC LIMIT 200",
            lambda r: [t((r[0] or '—')[:34], 600, "#0F1B3A"), t(brl(r[1]) if r[1] is not None else '—', 600),
                       t((r[2] or '—')[:18]), t((r[3] or '—')[:18]),
                       b("✓", "ok") if r[4] else t("—"), t(_fmtdate(r[5], "%d/%m %H:%M") if r[5] else '—'),
                       b((r[6] or '—').capitalize(), _atone.get((r[6] or '').lower(), "info"))])
    except Exception:  # noqa: BLE001
        pass
