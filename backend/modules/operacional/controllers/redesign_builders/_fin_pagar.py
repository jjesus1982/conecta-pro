"""F3 — Pagar: aging com KPIs (espelho do endpoint /payables/aging: sum(net_value),
status NOT IN ('pago','cancelado')), fila de aprovação (LEITURA — aprovar segue ação
humana gated fora desta tela) e AUDIT LOG dos pagamentos Inter (trilha real da tabela:
prepared_by/approved_by/otp/executed_at). Nenhum pagamento é disparado por estas telas."""

from sqlalchemy import text

from modules.operacional.controllers.redesign_data_controller import (
    S,
    _fmtdate,
    _helpers,
    _scalar,
    b,
    brl,
    t,
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
        _lotes = (
            await db.execute(
                text("""
            SELECT l.id::text, l.referencia, l.competencia, l.banco, l.status,
                   l.total_centavos, l.qtd_itens, coalesce(l.aprovado_por,'—') AS quem,
                   (SELECT count(*) FROM payroll_payments p
                     WHERE p.lote_ordem_id = l.id AND p.status = 'aguardando_app') AS falta,
                   (SELECT count(*) FROM payroll_payments p
                     WHERE p.lote_ordem_id = l.id AND p.status = 'pago') AS ok
            FROM folha_lote_ordem l ORDER BY l.created_at DESC LIMIT 40
        """)
            )
        ).fetchall()
        _TONE = {
            "RASCUNHO": "warn",
            "APROVADO": "info",
            "EXECUTANDO": "info",
            "CONCLUIDO": "ok",
            "CONCLUIDO_PARCIAL": "warn",
            "CANCELADO": "bad",
        }
        out["ordens-pagamento"] = {
            "title": "Ordens de pagamento",
            "sub": (
                f"Lote aprovado AQUI (teto {brl(_teto_ordem)} + OTP), executado no app do "
                f"banco, e o extrato de amanhã fecha cada item sozinho pelo CPF. "
                f"Aprovar NÃO paga ninguém — libera a ordem."
            ),
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar competência…",
            "cols": ["Referência", "Competência", "Status", "Itens", "Total", "Pagos", "Aprovado por"],
            "grid": "1.6fr 1fr 1.1fr 0.7fr 1.1fr 0.9fr 1.4fr",
            "rows": [
                {
                    "cells": [
                        t(r[1], 600, "#0F1B3A"),
                        t(r[2]),
                        b(r[4].replace("_", " ").capitalize(), _TONE.get(r[4], "info")),
                        t(str(r[6])),
                        t(brl(r[5] / 100), 600),
                        t(f"{r[9]}/{r[6]}" + (f" · faltam {r[8]}" if r[8] else "")),
                        t(str(r[7])[:26]),
                    ]
                }
                for r in _lotes
            ],
        }

        # Itens liberados para executar no app — a "lista de compras" do Jordan.
        # ── EXECUTAR PELO INTER, por API ─────────────────────────────────────────────
        # 22/09/2026. O Jordan aprovou o lote de R$ 33.137,71, abriu o app e não havia
        # nada para aprovar — o app nunca recebeu nada, ele esperava 49 PIX digitados à
        # mão. O fluxo terminava em «execute no app» porque nasceu para a CORA, que não
        # envia PIX por chave via API. A regra do banco dela virou regra de todos, e o
        # Inter — que paga por API, provado nas 49 transferências de R$ 0,01 desta noite —
        # ficou de fora sem motivo.
        _lotes_inter = [x for x in _lotes if str(x[3]).lower() == "inter" and str(x[4]).upper() == "APROVADO"]
        out["executar-inter"] = {
            "title": "Executar o lote pelo Inter (paga de verdade)",
            "sub": (
                "Envia os PIX do lote APROVADO, um a um, e pergunta ao banco QUEM RECEBEU "
                "depois de cada um. Não pede código de novo: o OTP já foi consumido ao "
                "aprovar, e é esse o gate. Repetir não duplica — só paga o que ainda não saiu. "
                "Lote da CORA não aparece aqui: aquele banco não envia PIX por chave via API."
            ),
            "cta": "PAGAR agora",
            "type": "form",
            "submit": {
                "endpoint": "/api/v1/redesign/action/executar-lote-inter",
                "gated": True,
                "confirm": "Isto ENVIA os PIX do lote AGORA, de verdade. Confirma?",
                "okMsg": "Lote executado.",
            },
            "fields": [
                {
                    "key": "lote_id",
                    "label": "Qual lote APROVADO*",
                    "type": "select",
                    "span": "span 2",
                    "options": [{"value": "", "label": "— escolha o lote —"}]
                    + [
                        {"value": str(x[0]), "label": f"{x[1]} — {x[6]} item(ns), {brl(x[5] / 100)}"}
                        for x in _lotes_inter
                    ],
                },
            ],
        }

        out["executar-no-app"] = await tbl(
            "Executar no app do banco",
            "Pagamentos já aprovados com OTP. Pague no app e NÃO precisa voltar aqui: "
            "o extrato de amanhã reconhece cada um pelo CPF e valor (beat 08:40).",
            "—",
            ["Funcionário", "CPF", "Chave PIX", "Competência", "Valor"],
            "1.8fr 1.1fr 1.4fr 0.9fr 1fr",
            """SELECT e.nome, coalesce(e.cpf,'—'), coalesce(p.pix_key, e.pix_key, '— sem chave —'),
                      lpad(p.mes::text,2,'0') || '/' || p.ano, p.valor_liquido
                 FROM payroll_payments p JOIN employees e ON e.id = p.employee_id
                WHERE p.status = 'aguardando_app' ORDER BY p.valor_liquido DESC""",
            lambda r: [t(r[0][:32], 600, "#0F1B3A"), t(str(r[1])), t(str(r[2])[:26]), t(str(r[3])), t(brl(r[4]), 600)],
        )

        # Montar: só isso não aprova nada.
        out["montar-ordem"] = {
            "title": "Montar ordem de pagamento",
            "sub": (
                "Junta os pagamentos pendentes da competência num lote. NÃO aprova e NÃO "
                f"paga — só reserva. Recusa se passar do teto de {brl(_teto_ordem)}."
            ),
            "cta": "Montar lote",
            "type": "form",
            "submit": {
                "endpoint": "/api/v1/redesign/action/montar-ordem-pagamento",
                "okMsg": "Lote montado. Gere o OTP para aprovar.",
            },
            "fields": [
                {
                    "key": "competencia",
                    "label": "Competência* (MM/AAAA)",
                    "type": "text",
                    "span": "span 1",
                    "ph": "Ex.: 09/2026",
                },
                {
                    "key": "banco",
                    "label": "Banco onde vai pagar*",
                    "type": "select",
                    "span": "span 1",
                    "value": "cora",
                    "options": [
                        {"value": "cora", "label": "Cora (Patrimonial)"},
                        {"value": "inter", "label": "Inter (Eletrônica)"},
                    ],
                },
                {
                    "key": "parcela",
                    "label": "Parcela",
                    "type": "select",
                    "span": "span 1",
                    "value": "1",
                    "options": [
                        {"value": "1", "label": "1ª — adiantamento (40%)"},
                        {"value": "2", "label": "2ª — saldo (60%)"},
                    ],
                },
                {
                    "key": "agrupador",
                    "label": "Posto (vazio = todos num lote só)",
                    "type": "text",
                    "span": "span 1",
                    "ph": "Ex.: VILLA DOS PASSAROS",
                },
            ],
        }
        # Gerar as parcelas ANTES de montar lote: sem linha de pagamento não há o que
        # reservar. Simula por padrão — a tela chama com dry_run e só grava quando o
        # Jordan marca 'nao'. Criar linha de pagamento é criar dinheiro a pagar.
        # ⭐ 22/09/2026 — DUAS ETAPAS, não uma. Regra do Jordan: «a folha tem que rodar
        # tanto o 40% quanto o 60% com as informações do DIA que foi pedido para gerar».
        # Gerar as duas de uma vez congelava em 22/09 uma folha que ainda muda: entre o
        # adiantamento (dia 20/21) e o saldo (5º dia útil) entram contratações e saídas.
        # Por isso a tela pergunta QUAL etapa, e o percentual da outra sai do formulário.
        out["gerar-parcelas"] = {
            "title": "Gerar parcelas da folha (adiantamento ou saldo)",
            "sub": (
                "Lê os holerites da competência e cria as linhas de pagamento. Rode "
                "DUAS vezes: o ADIANTAMENTO por volta do dia 20/21, e o SALDO no 5º dia "
                "útil do mês seguinte — cada um com a folha do dia, para pegar quem "
                "entrou ou saiu no meio. No saldo o sistema confere, pessoa a pessoa, se "
                "o que a folha abateu bate com o que realmente saiu no adiantamento. "
                "Simula por padrão."
            ),
            "cta": "Gerar",
            "type": "form",
            "submit": {"endpoint": "/api/v1/redesign/action/gerar-parcelas-folha", "okMsg": "Parcelas processadas."},
            "fields": [
                {
                    "key": "competencia",
                    "label": "Competência* (MM/AAAA)",
                    "type": "text",
                    "span": "span 1",
                    "ph": "Ex.: 09/2026",
                },
                {
                    "key": "etapa",
                    "label": "Qual etapa*",
                    "type": "select",
                    "span": "span 1",
                    "value": "adiantamento",
                    "options": [
                        {"value": "adiantamento", "label": "1. Adiantamento (40%) — dia 20/21"},
                        {"value": "saldo", "label": "2. Saldo (60%) — 5º dia útil do mês seguinte"},
                    ],
                },
                {
                    "key": "dry_run",
                    "label": "Só simular?",
                    "type": "select",
                    "span": "span 1",
                    "value": "sim",
                    "options": [
                        {"value": "sim", "label": "Sim — só mostrar"},
                        {"value": "nao", "label": "NÃO — gravar de verdade"},
                    ],
                },
                {
                    "key": "pct1",
                    "label": "% do adiantamento (só na etapa 1)",
                    "type": "text",
                    "span": "span 1",
                    "value": "40",
                },
                {
                    "key": "data1",
                    "label": "Quando o dinheiro sai* (DD/MM/AAAA)",
                    "type": "text",
                    "span": "span 1",
                    "ph": "Ex.: 22/09/2026",
                },
            ],
        }
        # ── PARCELAS DA FOLHA: conferir, editar, segurar, excluir, incluir ────────────
        # 22/09/2026 — pedido do Jordan, depois de eu ter feito por terminal o que é dele:
        # «constrói os botões, eu quero conferir, editar, excluir, incluir se for o caso».
        # Até aqui a única forma de segurar UMA pessoa do lote (o caso do Geilson) era um
        # UPDATE no banco. Capacidade que só existe no terminal não existe para o dono.
        #
        # O que NÃO se mexe, e a tela mostra isso em vez de esconder: linha já paga, ou
        # reservada em lote aberto. Editar a base de um pagamento em curso é trocar o chão
        # sob os pés de quem está aprovando.
        _parc = (
            await db.execute(
                text("""
            SELECT p.id::text, e.nome, coalesce(e.pix_key,'(sem chave)'), p.parcela,
                   p.valor_liquido, p.data_prevista, coalesce(p.status,'pendente_pagamento'),
                   p.lote_ordem_id IS NOT NULL AS em_lote, p.data_pagamento IS NOT NULL AS pago,
                   to_char(make_date(p.ano, p.mes, 1),'MM/YYYY') AS comp
              FROM payroll_payments p JOIN employees e ON e.id = p.employee_id
             WHERE make_date(p.ano, p.mes, 1) >= (CURRENT_DATE - INTERVAL '4 months')
             ORDER BY p.ano DESC, p.mes DESC, p.parcela, e.nome
             LIMIT 400
        """)
            )
        ).fetchall()

        def _linha_parcela(r):
            pid, nome, chave, parcela, valor, dt, status, em_lote, pago, comp = r
            travada = bool(pago) or status == "pago" or bool(em_lote)
            _tone = {"pago": "ok", "retido": "warn", "aguardando_app": "info"}.get(status, "info")
            cells = [
                t(nome, 600, "#0F1B3A"),
                t(str(chave)),
                t(f"{parcela}ª"),
                t(brl(float(valor or 0)), 600),
                t(_fmtdate(dt) if dt else "—"),
                b(status.replace("_", " "), _tone),
                t(comp),
            ]
            if travada:
                # Sem ações: a linha existe, o motivo aparece, e não há botão que engane.
                return {"cells": cells, "actions": []}
            acoes = [
                {
                    "title": f"Editar parcela de {nome}",
                    "endpoint": f"/api/v1/redesign/action/parcela-editar?parcela_id={pid}",
                    "method": "POST",
                    "btnLabel": "Editar",
                    "submitLabel": "Salvar",
                    "btnStyle": "outline",
                    "okMsg": "Parcela atualizada. Recarregue a tela.",
                    "fields": [
                        {
                            "key": "valor",
                            "label": "Valor (R$)",
                            "type": "text",
                            "value": f"{float(valor or 0):.2f}".replace(".", ","),
                        },
                        {
                            "key": "data",
                            "label": "Quando sai (DD/MM/AAAA)",
                            "type": "text",
                            "value": _fmtdate(dt) if dt else "",
                        },
                    ],
                },
                {
                    "title": (
                        f"LIBERAR {nome} para pagamento" if status == "retido" else f"SEGURAR {nome} fora do lote"
                    ),
                    "endpoint": f"/api/v1/redesign/action/parcela-segurar?parcela_id={pid}",
                    "method": "POST",
                    "btnLabel": "Liberar" if status == "retido" else "Segurar",
                    "submitLabel": "Confirmar",
                    "btnStyle": "primary" if status == "retido" else "outline",
                    "okMsg": "Estado alterado. Recarregue a tela.",
                    "fields": [{"key": "motivo", "label": "Por quê? (fica registrado)", "type": "text"}],
                },
                {
                    "title": f"EXCLUIR a parcela de {nome}",
                    "endpoint": f"/api/v1/redesign/action/parcela-excluir?parcela_id={pid}",
                    "method": "POST",
                    "btnLabel": "Excluir",
                    "submitLabel": "Excluir",
                    "btnStyle": "danger",
                    "okMsg": "Parcela excluída. Recarregue a tela.",
                    "fields": [{"key": "motivo", "label": "Por quê? (fica registrado)", "type": "text"}],
                },
            ]
            return {"cells": cells, "actions": acoes}

        _retidos = sum(1 for r in _parc if r[6] == "retido")
        _a_pagar = sum(float(r[4] or 0) for r in _parc if r[6] == "pendente_pagamento")
        out["parcelas-folha"] = {
            "title": "Parcelas da folha — conferir e ajustar",
            "sub": (
                f"Cada linha é dinheiro a pagar. {len(_parc)} linha(s); "
                f"{brl(_a_pagar)} aguardando pagamento; {_retidos} segurada(s). "
                "Linha já PAGA ou reservada em lote ABERTO não tem botão — de propósito: "
                "mexer na base de um pagamento em curso é pior que não poder mexer."
            ),
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar pessoa…",
            "cols": ["Pessoa", "Chave PIX", "Parcela", "Valor", "Quando sai", "Estado", "Competência"],
            "grid": "1.8fr 1.6fr 0.6fr 1fr 1fr 1.1fr 0.9fr",
            "rows": [_linha_parcela(r) for r in _parc],
        }

        # INCLUIR quem ficou de fora: admitido depois da geração, ou linha excluída por engano.
        _cands = (
            await db.execute(
                text("""
            SELECT e.id::text, e.nome, coalesce(e.salario_base,0)
              FROM employees e
             WHERE e.status='ativo' AND coalesce(e.is_homologacao,false)=false
             ORDER BY e.nome
        """)
            )
        ).fetchall()
        out["parcela-incluir"] = {
            "title": "Incluir pessoa numa parcela",
            "sub": (
                "Para quem ficou de fora: admitido depois da geração, ou linha excluída "
                "por engano. Cria UMA linha de pagamento — não mexe na folha."
            ),
            "cta": "Incluir",
            "type": "form",
            "submit": {
                "endpoint": "/api/v1/redesign/action/parcela-incluir",
                "gated": True,
                "confirm": "Isto CRIA uma linha de dinheiro a pagar. Confirma?",
                "okMsg": "Linha criada.",
            },
            "fields": [
                {
                    "key": "employee_id",
                    "label": "Quem*",
                    "type": "select",
                    "span": "span 2",
                    "options": [{"value": "", "label": "— escolha a pessoa —"}]
                    + [{"value": c[0], "label": f"{c[1]} — base {brl(float(c[2] or 0))}"} for c in _cands],
                },
                {
                    "key": "competencia",
                    "label": "Competência* (MM/AAAA)",
                    "type": "text",
                    "span": "span 1",
                    "ph": "Ex.: 09/2026",
                },
                {
                    "key": "parcela",
                    "label": "Qual parcela*",
                    "type": "select",
                    "span": "span 1",
                    "value": "1",
                    "options": [
                        {"value": "1", "label": "1ª — adiantamento (40%)"},
                        {"value": "2", "label": "2ª — saldo (60%)"},
                    ],
                },
                {"key": "valor", "label": "Valor (R$)*", "type": "text", "span": "span 1", "ph": "Ex.: 668,00"},
                {
                    "key": "data",
                    "label": "Quando sai* (DD/MM/AAAA)",
                    "type": "text",
                    "span": "span 1",
                    "ph": "Ex.: 22/09/2026",
                },
            ],
        }

        out["aprovar-ordem"] = {
            "title": "Aprovar ordem de pagamento (OTP)",
            "sub": (
                "Gere o código, receba por e-mail e confirme. O código é conferido AQUI "
                "DENTRO e consumido na mesma operação — não vale duas vezes. "
                "Aprovar libera a ordem; quem paga é você, no app do banco."
            ),
            "cta": "Aprovar lote",
            "type": "form",
            "submit": {
                "endpoint": "/api/v1/redesign/action/aprovar-ordem-pagamento",
                "confirm": "Confirmar a aprovação deste lote? Isto NÃO paga ninguém — "
                "libera a ordem para você executar no app.",
                "okMsg": "Ordem liberada.",
            },
            "fields": [
                # ⭐ 22/09/2026 — era campo de TEXTO pedindo «copie o ID da aba Ordens de
                # pagamento», e aquela aba NÃO mostra o ID (Referência, Competência,
                # Status, Itens, Total, Pagos, Aprovado por). O formulário pedia uma coisa
                # que o sistema não mostrava em lugar nenhum. O Jordan montou a ordem de
                # R$ 33.137,71, foi aprovar e o OTP «não chegou» — nunca chegou a ser
                # gerado, porque a chamada não tinha como sair com o campo vazio.
                # Vira LISTA dos lotes abertos, pelo nome. UUID não é coisa que se digita.
                {
                    "key": "lote_id",
                    "label": "Qual lote*",
                    "type": "select",
                    "span": "span 2",
                    "options": [{"value": "", "label": "— escolha o lote —"}]
                    + [
                        {
                            "value": str(_l[0]),
                            "label": f"{_l[1]} — {_l[6]} item(ns), {brl(_l[5] / 100)} · {_l[4].capitalize()}",
                        }
                        for _l in _lotes
                        if str(_l[4]).upper() in ("RASCUNHO", "APROVADO")
                    ],
                },
                {
                    "key": "acao",
                    "label": "O que fazer*",
                    "type": "select",
                    "span": "span 1",
                    "value": "otp",
                    "options": [
                        {"value": "otp", "label": "1) Gerar e enviar o OTP"},
                        {"value": "aprovar", "label": "2) Aprovar com o código"},
                    ],
                },
                {
                    "key": "codigo",
                    "label": "Código OTP (só no passo 2)",
                    "type": "text",
                    "span": "span 1",
                    "ph": "6 dígitos",
                },
            ],
        }
    except Exception as _e:  # noqa: BLE001 — tela nunca derruba o módulo
        import logging

        logging.getLogger(__name__).warning("[ordens-pagamento] %s", _e)

    # ── Aging na tela (espelho EXATO do endpoint /financial/payables/aging) ─────────────
    try:
        faixas = (
            await db.execute(
                text(
                    "SELECT CASE WHEN due_date >= CURRENT_DATE THEN '1. A vencer' "
                    "WHEN due_date >= CURRENT_DATE-30 THEN '2. Vencidas até 30d' "
                    "WHEN due_date >= CURRENT_DATE-60 THEN '3. Vencidas 31-60d' "
                    "WHEN due_date >= CURRENT_DATE-90 THEN '4. Vencidas 61-90d' "
                    "ELSE '5. Acima de 90d' END AS faixa, count(*), coalesce(sum(net_value),0) "
                    "FROM payable_accounts WHERE status::text NOT IN ('pago','cancelado') "
                    "GROUP BY 1 ORDER BY 1"
                )
            )
        ).fetchall()
        if isinstance(out.get("contas-pagar"), dict):
            out["contas-pagar"]["panelGrid"] = "1fr"
            out["contas-pagar"]["panels"] = [
                {
                    "title": "Aging — contas em aberto",
                    "rows": [
                        {
                            "left": f[3:],
                            "right": f"{n} · {brl(v)}",
                            **(S["ok"] if f.startswith("1.") else S["warn"] if f.startswith("2.") else S["bad"]),
                        }
                        for f, n, v in faixas
                    ]
                    or [{"left": "Sem contas em aberto", "right": "0", **S["ok"]}],
                }
            ]
    except Exception:  # noqa: BLE001
        pass

    # ── Fila de aprovação (LEITURA) — inter_payments preparados + payables requires_approval.
    # Aprovar/agendar = ação humana no fluxo gated (OTP); esta tela SÓ mostra a fila. ──
    try:
        n_prep = await _scalar(db, "SELECT count(*) FROM inter_payments WHERE lower(status)='preparado'")
        n_req = await _scalar(
            db,
            "SELECT count(*) FROM payable_accounts WHERE requires_approval=true AND coalesce(approval_status::text,'') NOT IN ('approved','aprovado')",
        )
        scr = await tbl(
            "Fila de aprovação (D7)",
            f"{(n_prep or 0)} pagamento(s) Inter preparado(s) · {(n_req or 0)} conta(s) exigindo aprovação — aprovar é ação humana gated (fora desta tela)",
            "—",
            ["Origem", "Descrição", "Valor", "Preparado em", "Status"],
            "1fr 1.8fr 1fr 1fr 0.9fr",
            "SELECT 'Inter', coalesce(destinatario->>'nome_recebedor', destinatario->>'chave', left(destinatario->>'codigo_barras',22), payment_type), "
            "valor, created_at, coalesce(status,'—') FROM inter_payments WHERE lower(status)='preparado' "
            "UNION ALL "
            "SELECT 'Contas a pagar', coalesce(description,'—'), net_value, created_at, coalesce(approval_status::text,'aguardando') "
            "FROM payable_accounts WHERE requires_approval=true AND coalesce(approval_status::text,'') NOT IN ('approved','aprovado') "
            "ORDER BY 4 DESC LIMIT 100",
            lambda r: [
                b(r[0], "info"),
                t((r[1] or "—")[:44], 600, "#0F1B3A"),
                t(brl(r[2]) if r[2] is not None else "—", 600),
                t(_fmtdate(r[3])),
                b((r[4] or "—").capitalize(), "warn"),
            ],
        )
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
            "—",
            ["Destinatário", "Valor", "Preparado por", "Aprovado por", "OTP", "Executado", "Status"],
            "1.6fr 0.9fr 1.1fr 1.1fr 0.6fr 1fr 0.9fr",
            "SELECT coalesce(p.destinatario->>'nome_recebedor', p.destinatario->>'chave', left(p.destinatario->>'codigo_barras',18), p.payment_type), "
            "p.valor, coalesce(u1.email, left(p.prepared_by::text,8), '—'), coalesce(u2.email, left(p.approved_by::text,8), '—'), "
            "(p.approval_otp_used IS NOT NULL AND p.approval_otp_used<>''), "
            "coalesce(p.executed_at, p.confirmed_at, p.cancelled_at), coalesce(p.status,'—') "
            "FROM inter_payments p LEFT JOIN users u1 ON u1.id=p.prepared_by LEFT JOIN users u2 ON u2.id=p.approved_by "
            "ORDER BY p.created_at DESC LIMIT 200",
            lambda r: [
                t((r[0] or "—")[:34], 600, "#0F1B3A"),
                t(brl(r[1]) if r[1] is not None else "—", 600),
                t((r[2] or "—")[:18]),
                t((r[3] or "—")[:18]),
                b("✓", "ok") if r[4] else t("—"),
                t(_fmtdate(r[5], "%d/%m %H:%M") if r[5] else "—"),
                b((r[6] or "—").capitalize(), _atone.get((r[6] or "").lower(), "info")),
            ],
        )
    except Exception:  # noqa: BLE001
        pass
