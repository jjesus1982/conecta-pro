"""DGX T3 — Operacional + Comercial (24/09/2026): o que o trial do DGX faz e a casa não fazia.

  1. VAGA como entidade do contrato — reusa `posts` (1 posto = função × escala × contratado) e
     dá a ele o que faltava: `contract_id` preenchido (só onde o cliente tem UM contrato vivo,
     nunca adivinhado) e `salario_base`. Telas `vagas-do-contrato` (editar por linha) e
     `vaga-nova`; `contratos-custo-por-vaga` = Σ vagas × salário × (1 + encargos da tabela de
     precificação) contra o faturado do contrato — a planilha do DGX na forma mínima.
  2. RESTRIÇÃO de colaborador por cliente (`op_restricoes_cliente`): trava em movimentação (F5),
     cobertura (F8) e substituto de falta. Regra em `services/restricao_cliente.py`.
  3. GRID de planejamento com ação por linha: "Cobrir vaga" e "Alocar pessoa" direto do
     `grid-real-contratual` (frente 04), despachando para os serviços F8/F5 — e as abas que
     faltavam no menu (grid, mapa de ponto).
  4. LIVRO: "Visualizado" (occurrences → em_analise) e "Finalizar" (→ resolvida, pelo mesmo
     repositório do resolver-ocorrencia) por linha do livro (F8).
  5. COPIAR contrato (com itens) — `contrato-copiar` no CRM.
  6. ÚLTIMA VISITA por cliente — `visitas-por-cliente` no CRM.
  7. PAINEL de alertas do sistema — as 32 regras do proativo num painel só (`painel-alertas`).

Prefixo `_` = o discovery pula. `operacional.py` importa `router` e chama `telas(db, out)` antes
de `montar_grupos`; `crm.py` chama `telas_crm(db, out)`. Ações em /api/v1/redesign/action/*.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.services import cobertura_service as cs
from modules.operacional.services import movimentacao_service as ms
from modules.operacional.services import restricao_cliente as rc

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_END = "/api/v1/redesign/action/"

_DDL = (
    "ALTER TABLE posts ADD COLUMN IF NOT EXISTS salario_base numeric(12,2)",
    # elo posto → contrato só onde não há dúvida: cliente com UM contrato vivo. Os outros ficam
    # "sem contrato" na tela, com Editar para o dono escolher (Mirante e Villa dos Pássaros têm 2).
    "UPDATE posts p SET contract_id = x.cid FROM ("
    " SELECT client_id, min(id::text)::uuid AS cid FROM contracts WHERE is_active AND status IN ('active','pending_signature')"
    " GROUP BY client_id HAVING count(*) = 1) x"
    " WHERE p.contract_id IS NULL AND p.client_id = x.client_id AND coalesce(p.is_active, true)",
)

SQL_VAGAS = """
SELECT p.id::text, coalesce(ct.contract_number, '—'), coalesce(ct.name, ''), ct.id::text, coalesce(cl.name, '(sem cliente)'),
       p.name, coalesce(p.post_type, '—'), coalesce(p.shift_type, '—'), coalesce(p.required_headcount, 0),
       (SELECT count(*) FROM allocations a WHERE a.post_id = p.id AND a.status = 'active' AND a.is_active),
       p.salario_base, ct.monthly_value, cl.id::text,
       (SELECT count(*) FROM contracts c2 WHERE c2.client_id = p.client_id AND c2.is_active AND c2.status IN ('active','pending_signature')),
       p.contract_id IS NOT NULL
FROM posts p LEFT JOIN clients cl ON cl.id = p.client_id LEFT JOIN contracts ct ON ct.id = p.contract_id
WHERE coalesce(p.is_active, true) ORDER BY 5, 2, 6
"""
SQL_CONTRATOS = (
    "SELECT ct.id::text, ct.contract_number, coalesce(cl.name,'—'), ct.name, ct.client_id::text FROM contracts ct "
    "LEFT JOIN clients cl ON cl.id = ct.client_id WHERE ct.is_active AND ct.status IN ('active','pending_signature','draft') "
    "ORDER BY 3, 2"
)
SQL_RESTRICOES = """
SELECT r.id::text, e.nome, coalesce(e.cargo,''), c.name, r.motivo, coalesce(r.solicitado_por,'—'), r.criado_em, r.ativo,
       r.encerrado_em, r.encerrado_motivo,
       (SELECT count(*) FROM employee_alocacoes a JOIN condominios cd ON cd.id = a.condominio_id
         WHERE a.ativo AND a.employee_id = r.employee_id AND cd.client_id = r.client_id)
FROM op_restricoes_cliente r JOIN employees e ON e.id = r.employee_id JOIN clients c ON c.id = r.client_id
WHERE r.ativo OR r.encerrado_em >= (now() AT TIME ZONE 'America/Manaus') - interval '90 days'
ORDER BY r.ativo DESC, r.criado_em DESC LIMIT 300
"""
SQL_ALERTAS = """
SELECT regra, severidade, count(*), min(first_seen_at), max(last_seen_at), min(title),
       count(*) FILTER (WHERE first_seen_at >= (now() AT TIME ZONE 'America/Manaus') - interval '1 day')
FROM proativo_alert_state WHERE resolved_at IS NULL GROUP BY 1, 2
ORDER BY CASE severidade WHEN 'critico' THEN 0 WHEN 'atencao' THEN 1 ELSE 2 END, 3 DESC, 1
"""
SQL_VISITAS_CLIENTE = """
WITH v AS (
  SELECT cliente_id AS cid, data_visita::date AS d, coalesce(criado_por, 'Comercial') AS quem, 'relatório comercial' AS tipo
  FROM crm_visit_reports WHERE cliente_id IS NOT NULL AND data_visita IS NOT NULL
  UNION ALL
  SELECT cliente_id, coalesce(((checkin_at AT TIME ZONE 'UTC') AT TIME ZONE 'America/Manaus')::date, data_visita),
         coalesce(responsavel_nome, '—'),
         CASE WHEN tipo::text = 'acompanhamento' THEN 'check-in do gerente' ELSE 'visita ' || tipo::text END
  FROM visitas WHERE cliente_id IS NOT NULL AND coalesce(ativo, true) AND (status::text = 'realizada' OR checkin_at IS NOT NULL)
)
SELECT c.id::text, c.name, x.d, x.quem, x.tipo,
       (SELECT count(*) FROM v WHERE v.cid = c.id AND v.d >= current_date - 90),
       (SELECT count(*) FROM posts p WHERE p.client_id = c.id AND coalesce(p.is_active, true))
FROM clients c LEFT JOIN LATERAL (SELECT * FROM v WHERE v.cid = c.id ORDER BY d DESC LIMIT 1) x ON true
WHERE c.status::text = 'active' ORDER BY x.d NULLS FIRST, c.name
"""
SQL_EMPS = (
    "SELECT id::text, nome, coalesce(cargo,'') FROM employees WHERE status = 'ativo' "
    "AND coalesce(is_homologacao,false) = false ORDER BY nome"
)
SQL_CLIENTES = "SELECT id::text, name FROM clients WHERE status::text = 'active' ORDER BY name"

FUNCOES = [
    "porteiro",
    "portaria",
    "rondante",
    "servicos_gerais",
    "jardinagem",
    "manutencao",
    "monitoramento",
    "limpeza",
    "lider",
    "vigilancia",
]
ESCALAS = ["12x36", "diurno", "noturno", "5x2", "6x1"]
_FAMILIA_ROTULO = {
    "operacional": "Operacional",
    "dp": "DP",
    "financeiro": "Financeiro",
    "documentos": "Documentos",
    "ponto": "Ponto",
    "juridico": "Jurídico",
    "recrutamento": "Recrutamento",
    "comercial": "Comercial",
    "fiscal": "Fiscal",
    "x": "—",
}


def _d(v) -> str:
    return v.strftime("%d/%m/%Y") if v else "—"


def _dh(v) -> str:
    return v.strftime("%d/%m %H:%M") if v else "—"


def _brl(v) -> str:
    try:
        return "R$ " + f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (TypeError, ValueError):
        return "—"


def _opts(rows, label, vazio="— escolha —") -> list[dict]:
    return [{"value": "", "label": vazio}] + [{"value": r[0], "label": label(r)} for r in rows]


def _lst(vals: list[str], vazio: str | None = None) -> list[dict]:
    base = [{"value": "", "label": vazio}] if vazio else []
    return base + [{"value": v, "label": v} for v in vals]


def _falhou(out: dict, tid: str, titulo: str, exc: Exception) -> None:
    from modules.operacional.controllers.redesign_data_controller import t

    logger.error("dgx t3: %s: %s", tid, exc, exc_info=True)
    out[tid] = {
        "title": f"{titulo} — FALHOU",
        "sub": f"{type(exc).__name__}: {str(exc)[:300]}",
        "cta": "—",
        "type": "table",
        "searchHint": "",
        "grid": "1fr",
        "cols": ["Erro"],
        "rows": [{"cells": [t("A tela não conseguiu ler as fontes. O erro está no log do backend.", 500, "#B91C1C")]}],
    }


#: 🔴 DERRUBOU A CASA EM 28/09/2026, 01:30–02:00. Este `_ensure` rodava as DUAS sentenças de
#: `_DDL` **a cada requisição da tela**: um `ALTER TABLE posts ADD COLUMN` e um `UPDATE posts`.
#:
#: `ALTER TABLE` pede ACCESS EXCLUSIVE. Quando uma leitura longa já segura o lock compartilhado de
#: `posts`, o ALTER entra na fila — e a fila de lock do Postgres é **FIFO**, então todo leitor
#: NOVO empilha atrás dele. Medido no incidente: **146 de 150 processos do banco em `waiting`**,
#: `FATAL: sorry, too many clients already`, 230 erros de `QueuePool limit` em 3 minutos, e o
#: Hermes falhando em cadeia porque as ferramentas dele não conseguiam conexão. `posts` é lida
#: por quase todo o operacional, então uma linha de DDL por requisição basta para travar tudo.
#:
#: ⭐ E O PIOR: eu consertei este MESMO defeito hoje à tarde no irmão
#: (`_dgx_f12_sesmt_demandas_comercial`, 13 deadlocks em 6h → 0) e **não procurei a família**.
#: A regra já estava escrita nesta casa: depois de todo conserto, procure a assinatura no
#: repositório inteiro. `grep -rln "ALTER TABLE posts ADD COLUMN"` devolvia os dois arquivos.
#:
#: ⚠️ O defeito nunca foi o DDL — é o DDL ser REEXECUTADO. A checagem de existência é uma leitura
#: em `information_schema` que não pega lock de escrita nenhum.
_PRONTO = False


async def _ensure(db) -> None:
    global _PRONTO  # noqa: PLW0603
    if _PRONTO:
        await rc._ensure(db)
        return

    # Leitura barata primeiro: a coluna já existe? `ADD COLUMN IF NOT EXISTS` é idempotente no
    # RESULTADO, mas não no LOCK — ele pede exclusividade mesmo quando não tem nada a fazer.
    tem_coluna = (await db.execute(text(
        "SELECT count(*) > 0 FROM information_schema.columns "
        " WHERE table_name = 'posts' AND column_name = 'salario_base'"))).scalar()
    if not tem_coluna:
        await db.execute(text(_DDL[0]))

    # O backfill posto→contrato passa a rodar UMA VEZ POR PROCESSO, não por requisição. Ele
    # escreve em `posts`, que é território curado pelo Jordan; manter o comportamento que já
    # existia, mas sem repetir a cada abertura de tela.
    await db.execute(text(_DDL[1]))

    # ⚠️ Só no FIM: marcar pronto antes faria uma falha no meio virar "já fiz".
    _PRONTO = True
    await rc._ensure(db)


async def _encargos_pct(db) -> float:
    """Soma dos encargos da tabela de precificação (a mesma fonte da tela `precificacao`). Sem tabela = 0, e a tela diz."""
    try:
        from modules.crm.services import pricing_cct

        p = await pricing_cct.carregar_params(db)
        # Mesma escolha do motor de preço desde 27/09: o encargo da EMPRESA, e a soma da
        # tabela global (Lucro Real, 0,6124) só como último recurso. A tela mostrava 61,24%
        # para contratos da Patrimonial, que é Anexo IV e paga 55,44%.
        enc = p.get("_encargo_empresa")
        return float(enc if enc is not None else sum(float(p.get(k, 0) or 0) for k in pricing_cct.ENCARGO_KEYS))
    except Exception:  # noqa: BLE001
        await db.rollback()
        return 0.0


def _familia(regra: str) -> str:
    try:
        from modules.notifications.proativo.regras import REGISTRY

        r = REGISTRY.get(regra)
        if r:
            return r.familia
    except Exception:  # noqa: BLE001
        pass
    return regra.split("_")[0]


# ───────────────────────────────── OPERACIONAL ─────────────────────────────────
async def telas(db, out: dict) -> None:
    from modules.operacional.controllers.redesign_data_controller import b, t

    try:
        await _ensure(db)
        await db.commit()
        emps = (await db.execute(text(SQL_EMPS))).fetchall()
        clientes = (await db.execute(text(SQL_CLIENTES))).fetchall()
        contratos = (await db.execute(text(SQL_CONTRATOS))).fetchall()
        enc = await _encargos_pct(db)
    except Exception as exc:  # noqa: BLE001 — visível, nunca calado
        await db.rollback()
        for tid in ("vagas-do-contrato", "contratos-custo-por-vaga", "restricoes-cliente", "painel-alertas"):
            _falhou(out, tid, tid, exc)
        return
    hoje_s = date.today().isoformat()
    emp_opts = _opts(emps, lambda r: f"{r[1]} · {r[2]}" if r[2] else r[1], "— colaborador —")
    cli_opts = _opts(clientes, lambda r: r[1], "— cliente —")
    ctr_opts = _opts(contratos, lambda r: f"{r[1]} · {r[2]} · {r[3][:40]}", "— contrato —")
    ctr_por_cliente: dict[str, list] = {}
    for r in contratos:
        ctr_por_cliente.setdefault(r[4], []).append(r)

    # ── 1. Vagas do contrato ──
    try:
        rows = (await db.execute(text(SQL_VAGAS))).fetchall()
        # A FOLHA REAL de quem está alocado no contrato, no último mês fechado da folha.
        # Os 15 postos ativos têm `salario_base` ZERADO (medido em 27/09/2026), então a coluna
        # planejada mostra R$ 0 para todos os contratos enquanto a folha de agosto é
        # R$ 126.689,72. Esta coluna não substitui a planejada — põe o FATO ao lado do plano.
        # É aproximação declarada: o holerite é da pessoa, não do posto; quem está em dois
        # contratos entra nos dois. Por isso o rótulo diz "dos alocados", não "do contrato".
        folha_real, mes_folha = {}, None
        try:
            ref = (
                await db.execute(
                    text(
                        "SELECT reference_year, reference_month FROM hr_payslips "
                        " WHERE make_date(reference_year, reference_month, 1) < date_trunc('month', current_date) "
                        " GROUP BY 1, 2 ORDER BY 1 DESC, 2 DESC LIMIT 1"
                    )
                )
            ).first()
            if ref:
                mes_folha = f"{int(ref[1]):02d}/{int(ref[0])}"
                for cid_, tot_ in (
                    await db.execute(
                        text(
                            "SELECT x.contract_id::text, coalesce(sum(p.total_earnings), 0) "
                            "  FROM (SELECT DISTINCT po.contract_id, a.employee_id "
                            "          FROM posts po JOIN allocations a ON a.post_id = po.id "
                            "         WHERE coalesce(po.is_active, true) AND coalesce(a.is_active, true) "
                            "           AND po.contract_id IS NOT NULL) x "
                            "  JOIN hr_payslips p ON p.employee_id = x.employee_id "
                            "   AND p.reference_year = :a AND p.reference_month = :m "
                            " GROUP BY 1"
                        ),
                        {"a": int(ref[0]), "m": int(ref[1])},
                    )
                ).all():
                    folha_real[cid_] = float(tot_ or 0)
        except Exception:  # noqa: BLE001 — a coluna nova não pode derrubar a tabela antiga
            await db.rollback()
            folha_real, mes_folha = {}, None

        linhas, por_ctr = [], {}
        for r in rows:
            (
                pid,
                ctr_num,
                ctr_nome,
                ctr_id,
                cliente,
                posto,
                funcao,
                escala,
                contratado,
                alocado,
                sal,
                fat,
                cli_id,
                n_ctr,
                tem_id,
            ) = r
            sal_f = float(sal) if sal is not None else None
            custo = (sal_f or 0) * contratado * (1 + enc) if sal_f else None
            if ctr_id:
                k = por_ctr.setdefault(
                    ctr_id,
                    {
                        "num": ctr_num,
                        "nome": ctr_nome,
                        "cliente": cliente,
                        "vagas": 0,
                        "contratado": 0,
                        "alocado": 0,
                        "salarios": 0.0,
                        "sem_salario": 0,
                        "faturado": float(fat or 0),
                    },
                )
                k["vagas"] += 1
                k["contratado"] += contratado
                k["alocado"] += alocado
                k["salarios"] += (sal_f or 0) * contratado
                k["sem_salario"] += 0 if sal_f else 1
            dif = alocado - contratado
            sit = b("OK", "ok") if dif == 0 else b(f"{dif:+d}", "bad" if dif < 0 else "info")
            ctr_cell = (
                t(ctr_num, 600, _ND)
                if ctr_id
                else b("contrato apagado", "bad")
                if tem_id  # contract_id aponta para contrato que não existe (dado antigo)
                else b("sem contrato" + (f" ({n_ctr} vivos)" if n_ctr > 1 else ""), "warn")
            )
            opcoes_ctr = [{"value": "", "label": "— sem contrato —"}] + [
                {"value": c[0], "label": f"{c[1]} · {c[3][:40]}"} for c in ctr_por_cliente.get(cli_id or "", [])
            ]
            linhas.append(
                {
                    "cells": [
                        ctr_cell,
                        t(cliente, 600, _ND),
                        t(posto),
                        t(funcao),
                        t(escala),
                        t(str(contratado)),
                        t(str(alocado)),
                        t(_brl(sal_f) if sal_f else "—", 500, "#64748B" if not sal_f else "#334155"),
                        t(_brl(custo) if custo else "—", 600),
                        sit,
                    ],
                    "filtros": {"cliente": cliente, "contrato": ctr_num},
                    "actions": [
                        {
                            "title": f"Editar vaga — {posto}",
                            "endpoint": f"{_END}vaga-editar?post_id={pid}",
                            "method": "POST",
                            "btnLabel": "Editar",
                            "submitLabel": "Salvar",
                            "btnStyle": "outline",
                            "okMsg": "Vaga atualizada. Recarregue a tela.",
                            "fields": [
                                {
                                    "key": "contract_id",
                                    "label": "Contrato",
                                    "type": "select",
                                    "options": opcoes_ctr,
                                    "value": ctr_id or "",
                                    "span": "span 2",
                                },
                                {
                                    "key": "post_type",
                                    "label": "Função",
                                    "type": "select",
                                    "options": _lst(sorted(set(FUNCOES + [funcao]))),
                                    "value": funcao,
                                },
                                {
                                    "key": "shift_type",
                                    "label": "Escala",
                                    "type": "select",
                                    "options": _lst(sorted(set(ESCALAS + [escala]))),
                                    "value": escala,
                                },
                                {
                                    "key": "required_headcount",
                                    "label": "Efetivo contratado*",
                                    "type": "number",
                                    "value": str(contratado),
                                },
                                {
                                    "key": "salario_base",
                                    "label": "Salário base (R$)",
                                    "type": "number",
                                    "value": f"{sal_f:.2f}" if sal_f else "",
                                },
                            ],
                        }
                    ],
                }
            )
        n_desc = sum(1 for r in rows if r[9] < r[8])
        n_sem = sum(1 for r in rows if not r[3])
        out["vagas-do-contrato"] = {
            "title": "Vagas do contrato",
            "cta": "—",
            "type": "table",
            "sub": (
                f"{len(rows)} vaga(s) = postos ativos · {n_desc} com efetivo abaixo do contratado · {n_sem} sem contrato ligado · "
                f"custo/mês = salário base × contratado × (1 + {enc * 100:.2f}% de encargos da tabela de precificação) · "
                "fonte: posts × allocations ativas × contracts · Editar liga a vaga ao contrato e grava salário base"
            ),
            "searchHint": "Buscar cliente, posto, contrato…",
            "grid": "1fr 1.6fr 1.6fr 1fr 0.7fr 0.6fr 0.6fr 0.9fr 1fr 0.7fr",
            "cols": [
                "Contrato",
                "Cliente",
                "Posto (vaga)",
                "Função",
                "Escala",
                "Contr.",
                "Aloc.",
                "Salário base",
                "Custo/mês",
                "Situação",
            ],
            "filtros": [{"key": "cliente", "label": "Cliente"}, {"key": "contrato", "label": "Contrato"}],
            "rows": linhas or [{"cells": [t("Nenhum posto ativo", 500)] + [t("—")] * 9}],
            "_meta": {
                "encargos_pct": enc,
                "vagas": [
                    {
                        "post_id": r[0],
                        "posto": r[5],  # dgx v2 — rótulo da ação «Recrutar»
                        "contrato": r[3],
                        "contratado": r[8],
                        "alocado": r[9],
                        "salario_base": float(r[10]) if r[10] is not None else None,
                    }
                    for r in rows
                ],
            },
        }
        # ── 1b. Custo por contrato ──
        linhas = []
        for cid, k in sorted(por_ctr.items(), key=lambda kv: kv[1]["cliente"]):
            com_enc = k["salarios"] * (1 + enc)
            delta = k["faturado"] - com_enc
            real = folha_real.get(cid)
            real_enc = (real * (1 + enc)) if real is not None else None
            delta_real = (k["faturado"] - real_enc) if real_enc is not None else None
            # Sem salário planejado, a situação sai da FOLHA REAL — antes ficava em
            # "sem salário" para sempre e a tabela não dizia se o contrato paga o que custa.
            if k["sem_salario"] and delta_real is not None:
                sit = b("abaixo do custo (pela folha real)", "bad") if delta_real < 0 else b("ok pela folha real", "ok")
            elif k["sem_salario"]:
                sit = b("sem salário em " + str(k["sem_salario"]) + " vaga(s)", "warn")
            else:
                sit = b("abaixo do custo", "bad") if delta < 0 else b("ok", "ok")
            linhas.append(
                {
                    "cells": [
                        t(k["num"], 600, _ND),
                        t(k["cliente"], 600, _ND),
                        t(k["nome"][:50]),
                        t(str(k["vagas"])),
                        t(str(k["contratado"])),
                        t(str(k["alocado"])),
                        t(_brl(k["salarios"])),
                        t(_brl(com_enc), 600),
                        t(_brl(real_enc) if real_enc is not None else "—", 600),
                        t(_brl(k["faturado"])),
                        t(_brl(delta), 600, "#B91C1C" if delta < 0 else "#16A34A"),
                        sit,
                    ],
                    "filtro": k["cliente"],
                    "_meta": {
                        "contract_id": cid,
                        "salarios": k["salarios"],
                        "com_encargos": com_enc,
                        "folha_real": real,
                        "folha_real_com_encargos": real_enc,
                        "faturado": k["faturado"],
                    },
                }
            )
        out["contratos-custo-por-vaga"] = {
            "title": "Custo por contrato (pelas vagas)",
            "cta": "—",
            "type": "table",
            "sub": (
                f"{len(por_ctr)} contrato(s) com vaga ligada · Σ salário base × contratado, com {enc * 100:.2f}% de encargos "
                "da EMPRESA que emprega (encargos.py, pelo anexo do cadastro) × faturado (monthly_value). "
                + (
                    f"«Folha real» = holerites de {mes_folha} de quem está alocado no contrato, com os mesmos encargos "
                    "— o FATO ao lado do plano; aproximação declarada (holerite é da pessoa, não do posto). "
                    if mes_folha
                    else "«Folha real» indisponível: nenhum mês de folha fechado encontrado. "
                )
                + "Sem benefícios, uniforme, tributos nem margem — para isso, `calculado-vs-faturado` (frente 07). "
                "Vaga sem salário base entra com R$ 0 no plano; a situação então sai da folha real."
            ),
            "searchHint": "Buscar contrato ou cliente…",
            "filterLabel": "Cliente",
            "grid": "1fr 1.6fr 2fr 0.5fr 0.6fr 0.6fr 1fr 1.1fr 1.1fr 1fr 1fr 1.1fr",
            "cols": [
                "Contrato",
                "Cliente",
                "Nome",
                "Vagas",
                "Contr.",
                "Aloc.",
                "Σ salários",
                "Com encargos",
                f"Folha real {mes_folha or ''} c/ enc.".strip(),
                "Faturado",
                "Δ",
                "Situação",
            ],
            "rows": linhas
            or [
                {"cells": [t("Nenhuma vaga ligada a contrato — use Editar em Vagas do contrato", 500)] + [t("—")] * 11}
            ],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _falhou(out, "vagas-do-contrato", "Vagas do contrato", exc)
        _falhou(out, "contratos-custo-por-vaga", "Custo por contrato", exc)

    out["vaga-nova"] = {
        "title": "Nova vaga",
        "cta": "Criar vaga",
        "sub": "Cria um posto ligado ao contrato (cliente vem do contrato): função × escala × efetivo × salário base. Aparece em Vagas do contrato, Postos e no grid.",
        "type": "form",
        "submit": {"endpoint": _END + "vaga-nova", "okMsg": "Vaga criada.", "showResult": True},
        "fields": [
            {"key": "contract_id", "label": "Contrato*", "type": "select", "options": ctr_opts, "span": "span 2"},
            {
                "key": "name",
                "label": "Nome do posto/vaga*",
                "type": "text",
                "span": "span 2",
                "ph": "Portaria 24h — Bloco A",
            },
            {"key": "post_type", "label": "Função*", "type": "select", "options": _lst(FUNCOES, "— função —")},
            {"key": "shift_type", "label": "Escala*", "type": "select", "options": _lst(ESCALAS, "— escala —")},
            {"key": "required_headcount", "label": "Efetivo contratado*", "type": "number", "value": "1"},
            {"key": "salario_base", "label": "Salário base (R$)", "type": "number"},
            {"key": "address", "label": "Endereço (opcional)", "type": "text", "span": "span 2"},
        ],
    }

    # ── 2. Restrições por cliente ──
    try:
        rows = (await db.execute(text(SQL_RESTRICOES))).fetchall()
        linhas = []
        for r in rows:
            rid, nome, cargo, cliente, motivo, quem, desde, ativo, enc_em, enc_mot, aloc = r
            acoes = []
            if ativo:
                acoes.append(
                    {
                        "title": f"Encerrar restrição — {nome} em {cliente}",
                        "endpoint": f"{_END}restricao-encerrar?restricao_id={rid}",
                        "method": "POST",
                        "btnLabel": "Encerrar",
                        "submitLabel": "Encerrar",
                        "btnStyle": "outline",
                        "okMsg": "Restrição encerrada. Recarregue a tela.",
                        "fields": [
                            {"key": "motivo", "label": "Por que encerrar", "type": "textarea", "span": "span 2"}
                        ],
                    }
                )
            linhas.append(
                {
                    "cells": [
                        t(nome, 600, _ND),
                        t(cargo or "—"),
                        t(cliente, 600, _ND),
                        t(motivo[:160]),
                        t(quem),
                        t(_d(desde), 500),
                        b(f"ALOCADO lá hoje ({aloc})", "bad") if (ativo and aloc) else t("—"),
                        b("viva", "bad") if ativo else b(f"encerrada {_d(enc_em)}", "mut"),
                    ],
                    "filtros": {"cliente": cliente, "situacao": "viva" if ativo else "encerrada"},
                    "actions": acoes,
                }
            )
        n_viva = sum(1 for r in rows if r[7])
        n_conf = sum(1 for r in rows if r[7] and r[10])
        out["restricoes-cliente"] = {
            "title": "Restrições por cliente",
            "cta": "—",
            "type": "table",
            "sub": (
                f"{n_viva} restrição(ões) viva(s)"
                + (
                    f" · ⚠ {n_conf} com a pessoa ALOCADA hoje nesse cliente (encerre a alocação em Movimentações)"
                    if n_conf
                    else ""
                )
                + " · a parede vale em Nova movimentação, Nova cobertura e Escalar substituto (422) · encerradas nos últimos 90 dias ficam visíveis"
            ),
            "searchHint": "Buscar colaborador, cliente, motivo…",
            "grid": "1.5fr 0.9fr 1.5fr 2.2fr 0.9fr 0.8fr 1fr 0.9fr",
            "cols": ["Colaborador", "Cargo", "Cliente", "Motivo", "Pedido por", "Desde", "Conflito", "Situação"],
            "filtros": [{"key": "cliente", "label": "Cliente"}, {"key": "situacao", "label": "Situação"}],
            "rows": linhas or [{"cells": [t("Nenhuma restrição registrada", 500)] + [t("—")] * 7}],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _falhou(out, "restricoes-cliente", "Restrições por cliente", exc)
    out["restricao-nova"] = {
        "title": "Nova restrição",
        "cta": "Registrar restrição",
        "sub": "«Esta pessoa não pode trabalhar neste cliente.» A partir daqui, alocar, cobrir ou escalar essa pessoa nesse cliente é recusado com o motivo. Não encerra a alocação atual — faça isso em Movimentações.",
        "type": "form",
        "submit": {
            "endpoint": _END + "restricao-nova",
            "okMsg": "Restrição registrada.",
            "showResult": True,
            "confirm": True,
        },
        "fields": [
            {"key": "employee_id", "label": "Colaborador*", "type": "select", "options": emp_opts, "span": "span 2"},
            {"key": "client_id", "label": "Cliente*", "type": "select", "options": cli_opts, "span": "span 2"},
            {"key": "motivo", "label": "Motivo* (o que o cliente pediu, quando)", "type": "textarea", "span": "span 2"},
            {"key": "solicitado_por", "label": "Pedido por (síndico, gerente…)", "type": "text"},
        ],
    }

    # ── 3. Grid com ação por linha (frente 04 já montou; aqui só se pendura a ação) ──
    try:
        g = out.get("grid-real-contratual") or {}
        postos = (g.get("_meta") or {}).get("postos") or []
        rows = g.get("rows") or []
        motivos_cob = [{"value": "", "label": "— motivo —"}] + [
            {"value": k, "label": cs.ROTULO[v]} for k, v in cs.MOTIVOS.items()
        ]
        motivos_mov = [{"value": "", "label": "— motivo —"}] + [{"value": k, "label": v} for k, v in ms.MOTIVOS.items()]
        if postos and len(rows) == len(postos):
            for row, p in zip(rows, postos, strict=True):
                pid = p.get("post_id")
                if not pid:
                    continue
                row["actions"] = [
                    {
                        "title": f"Cobrir vaga — {p['posto']}",
                        "endpoint": f"{_END}grid-cobrir?post_id={pid}",
                        "method": "POST",
                        "btnLabel": "Cobrir",
                        "submitLabel": "Registrar cobertura",
                        "btnStyle": "primary",
                        "okMsg": "Cobertura registrada. Recarregue a tela (o grid atualiza em até 1 min).",
                        "fields": [
                            {
                                "key": "coberto_id",
                                "label": "Quem falta (coberto)*",
                                "type": "select",
                                "options": emp_opts,
                            },
                            {"key": "cobertura_id", "label": "Quem cobre*", "type": "select", "options": emp_opts},
                            {"key": "motivo", "label": "Motivo*", "type": "select", "options": motivos_cob},
                            {"key": "inicio", "label": "Dia*", "type": "date", "value": hoje_s},
                            {"key": "fim", "label": "Até (vazio = só o dia)", "type": "date"},
                            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
                        ],
                    },
                    {
                        "title": f"Alocar pessoa — {p['posto']}",
                        "endpoint": f"{_END}grid-alocar?post_id={pid}",
                        "method": "POST",
                        "btnLabel": "Alocar",
                        "submitLabel": "Alocar",
                        "btnStyle": "outline",
                        "okMsg": "Movimentação registrada. A escala do mês continua sendo gerada pelas alocações ativas.",
                        "fields": [
                            {
                                "key": "employee_id",
                                "label": "Colaborador*",
                                "type": "select",
                                "options": emp_opts,
                                "span": "span 2",
                            },
                            {"key": "funcao", "label": "Função*", "type": "text", "value": "AGENTE DE PORTARIA"},
                            {"key": "data_inicio", "label": "A partir de*", "type": "date", "value": hoje_s},
                            {"key": "motivo", "label": "Motivo*", "type": "select", "options": motivos_mov},
                            {
                                "key": "solicitado_por",
                                "label": "Solicitado por",
                                "type": "select",
                                "options": [{"value": v, "label": v} for v in ms.SOLICITANTES],
                            },
                            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
                        ],
                    },
                ]
            g["sub"] = (g.get("sub") or "") + " · Cobrir/Alocar por linha (T3)"
    except Exception as exc:  # noqa: BLE001
        logger.warning("dgx t3: ações no grid não penduradas: %s", exc)

    # ── 7. Painel de alertas do sistema ──
    try:
        rows = (await db.execute(text(SQL_ALERTAS))).fetchall()
        tone = {"critico": "bad", "atencao": "warn", "info": "info"}
        linhas = []
        for regra, sev, n, desde, visto, exemplo, novos in rows:
            fam = _familia(regra)
            linhas.append(
                {
                    "cells": [
                        t(_FAMILIA_ROTULO.get(fam, fam.title()), 600, _ND),
                        t(regra.replace("_", " "), 600),
                        b(sev, tone.get(sev, "mut")),
                        t(str(n), 600),
                        b(f"+{novos} hoje", "info") if novos else t("—"),
                        t(_dh(desde)),
                        t(_dh(visto)),
                        t((exemplo or "—")[:120]),
                    ],
                    "filtros": {"familia": _FAMILIA_ROTULO.get(fam, fam.title()), "severidade": sev},
                }
            )
        total = sum(r[2] for r in rows)
        crit = sum(r[2] for r in rows if r[1] == "critico")
        out["painel-alertas"] = {
            "title": "Alertas do sistema",
            "cta": "—",
            "type": "table",
            "sub": (
                f"{total} alerta(s) vivo(s) em {len(rows)} regra(s) · {crit} crítico(s) · fonte: proativo_alert_state (o motor de "
                "32 regras do proativo, a cada 15 min) · por regra: quantos, desde quando, último visto e um exemplo · "
                "os limiares moram nas regras (código); a Central de aprovações mostra só os do DP"
            ),
            "searchHint": "Buscar regra, família…",
            "grid": "1fr 1.6fr 0.8fr 0.6fr 0.8fr 0.9fr 0.9fr 2.4fr",
            "cols": ["Família", "Regra", "Severidade", "Vivos", "Novos", "Mais antigo", "Último visto", "Exemplo"],
            "filtros": [{"key": "familia", "label": "Família"}, {"key": "severidade", "label": "Severidade"}],
            "rows": linhas or [{"cells": [t("Nenhum alerta vivo", 500)] + [t("—")] * 7}],
            "_meta": {"total": total, "regras": len(rows)},
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _falhou(out, "painel-alertas", "Alertas do sistema", exc)


# ───────────────────────────────── CRM ─────────────────────────────────
async def telas_crm(db, out: dict) -> None:
    from modules.operacional.controllers.redesign_data_controller import b, t

    try:
        contratos = (
            await db.execute(
                text(
                    "SELECT ct.id::text, ct.contract_number, coalesce(cl.name,'—'), ct.name, ct.status::text FROM contracts ct "
                    "LEFT JOIN clients cl ON cl.id = ct.client_id WHERE ct.is_active ORDER BY 3, 2"
                )
            )
        ).fetchall()
        clientes = (await db.execute(text(SQL_CLIENTES))).fetchall()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _falhou(out, "contrato-copiar", "Copiar contrato", exc)
        _falhou(out, "visitas-por-cliente", "Última visita por cliente", exc)
        return
    out["contrato-copiar"] = {
        "title": "Copiar contrato",
        "cta": "Copiar",
        "sub": "Duplica o contrato (valores, vigência relativa, reajuste, cláusulas) e os itens, como RASCUNHO com número novo. Postos/vagas não são copiados: pertencem ao cliente — ligue-os em Operacional → Vagas do contrato.",
        "type": "form",
        "submit": {
            "endpoint": _END + "contrato-copiar",
            "okMsg": "Contrato copiado.",
            "showResult": True,
            "confirm": True,
        },
        "fields": [
            {
                "key": "contract_id",
                "label": "Contrato de origem*",
                "type": "select",
                "span": "span 2",
                "options": _opts(contratos, lambda r: f"{r[1]} · {r[2]} · {r[3][:40]} ({r[4]})", "— contrato —"),
            },
            {
                "key": "client_id",
                "label": "Novo cliente (vazio = o mesmo)",
                "type": "select",
                "span": "span 2",
                "options": _opts(clientes, lambda r: r[1], "— mesmo cliente —"),
            },
            {"key": "name", "label": "Nome do novo contrato (vazio = «(cópia)»)", "type": "text", "span": "span 2"},
            {"key": "start_date", "label": "Início da vigência*", "type": "date", "value": date.today().isoformat()},
            {
                "key": "copiar_itens",
                "label": "Copiar itens",
                "type": "select",
                "options": [{"value": "sim", "label": "Sim"}, {"value": "nao", "label": "Não"}],
            },
        ],
    }
    try:
        rows = (await db.execute(text(SQL_VISITAS_CLIENTE))).fetchall()
        hoje = date.today()
        linhas = []
        for cid, nome, d, quem, tipo, n90, postos in rows:
            dias = (hoje - d).days if d else None
            ha = (
                b("nunca", "bad")
                if dias is None
                else b(f"{dias} d", "bad" if dias > 60 else ("warn" if dias > 30 else "ok"))
            )
            linhas.append(
                {
                    "cells": [
                        t(nome, 600, _ND),
                        t(_d(d), 600),
                        ha,
                        t(quem or "—"),
                        t(tipo or "—"),
                        t(str(n90)),
                        t(str(postos)),
                    ],
                    "filtros": {
                        "faixa": "nunca"
                        if dias is None
                        else ("> 60 dias" if dias > 60 else ("31–60 dias" if dias > 30 else "≤ 30 dias")),
                        "com_posto": "com posto" if postos else "sem posto",
                    },
                    "_meta": {"client_id": cid, "ultima": d.isoformat() if d else None},
                }
            )
        n_sem = sum(1 for r in rows if r[2] is None or (hoje - r[2]).days > 30)
        out["visitas-por-cliente"] = {
            "title": "Última visita por cliente",
            "cta": "—",
            "type": "table",
            "sub": (
                f"{len(rows)} cliente(s) ativo(s) · {n_sem} sem visita há mais de 30 dias (ou nunca) · fonte: relatórios de visita "
                "comercial (crm_visit_reports) ∪ visitas de campo realizadas ∪ check-ins do gerente (visitas) · ordem: quem está há mais tempo sem ver ninguém"
            ),
            "searchHint": "Buscar cliente…",
            "grid": "2fr 1fr 0.7fr 1.4fr 1.3fr 0.7fr 0.7fr",
            "cols": ["Cliente", "Última visita", "Há", "Quem", "Tipo", "Visitas 90 d", "Postos"],
            "filtros": [{"key": "faixa", "label": "Faixa"}, {"key": "com_posto", "label": "Postos"}],
            "rows": linhas or [{"cells": [t("Nenhum cliente ativo", 500)] + [t("—")] * 6}],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        _falhou(out, "visitas-por-cliente", "Última visita por cliente", exc)


# ───────────────────────────────── AÇÕES ─────────────────────────────────
router = APIRouter()


def _erro(exc) -> HTTPException:
    return HTTPException(status_code=getattr(exc, "status", 400), detail=str(exc))


def _p(payload: dict) -> dict:
    return {k: (str(v).strip() if v is not None else "") for k, v in payload.items()}


def _uid(current_user) -> str | None:
    return str(getattr(current_user, "id", "") or "") or None


def _uuid(v: str, rotulo: str) -> str:
    v = (v or "").strip()
    if len(v) != 36:
        raise HTTPException(status_code=400, detail=f"{rotulo} inválido — recarregue a tela e tente de novo.")
    return v


def _num(v, default=None):
    try:
        return float(str(v).replace(".", "").replace(",", ".")) if ("," in str(v)) else float(v)
    except (TypeError, ValueError):
        return default


async def _condominio_do_posto(db, post_id: str) -> tuple[str, str]:
    r = (
        await db.execute(
            text(
                "SELECT p.name, (SELECT c.id::text FROM condominios c WHERE c.client_id = p.client_id AND c.ativo ORDER BY c.nome LIMIT 1) "
                "FROM posts p WHERE p.id = CAST(:p AS uuid) AND coalesce(p.is_active, true)"
            ),
            {"p": post_id},
        )
    ).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Posto não encontrado.")
    if not r[1]:
        raise HTTPException(
            status_code=422,
            detail=f"O posto {r[0]} não tem condomínio ligado ao cliente — a movimentação (F5) precisa dele.",
        )
    return r[0], r[1]


@router.post("/action/vaga-editar")
async def rd_vaga_editar(
    current_user: CurrentActiveUser, post_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    post_id = _uuid(post_id, "Posto")
    await _ensure(db)
    qtd = int(_num(p.get("required_headcount"), -1) or 0)
    if qtd < 0:
        raise HTTPException(status_code=400, detail="Efetivo contratado precisa ser um número ≥ 0.")
    sal = _num(p.get("salario_base")) if p.get("salario_base") else None
    if sal is not None and sal < 0:
        raise HTTPException(status_code=400, detail="Salário base não pode ser negativo.")
    ctr = p.get("contract_id") or None
    if ctr:
        ok = (
            await db.execute(
                text(
                    "SELECT 1 FROM contracts ct JOIN posts po ON po.client_id = ct.client_id WHERE ct.id = CAST(:c AS uuid) AND po.id = CAST(:p AS uuid)"
                ),
                {"c": ctr, "p": post_id},
            )
        ).scalar()
        if not ok:
            raise HTTPException(status_code=422, detail="Esse contrato não é do cliente do posto.")
    n = (
        await db.execute(
            text(
                "UPDATE posts SET contract_id = CAST(:c AS uuid), post_type = coalesce(nullif(:f,''), post_type), "
                "shift_type = coalesce(nullif(:e,''), shift_type), required_headcount = :q, salario_base = :s, updated_at = now() "
                "WHERE id = CAST(:p AS uuid) RETURNING id"
            ),
            {"c": ctr, "f": p.get("post_type", ""), "e": p.get("shift_type", ""), "q": qtd, "s": sal, "p": post_id},
        )
    ).rowcount
    if not n:
        raise HTTPException(status_code=404, detail="Posto não encontrado.")
    await db.commit()
    return {
        "ok": True,
        "message": f"Vaga atualizada: {qtd} contratado(s)"
        + (f", salário base {_brl(sal)}" if sal else "")
        + (", ligada ao contrato" if ctr else ", sem contrato")
        + ".",
    }


@router.post("/action/vaga-nova")
async def rd_vaga_nova(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    await _ensure(db)
    if not p.get("contract_id") or not p.get("name") or not p.get("post_type") or not p.get("shift_type"):
        raise HTTPException(status_code=400, detail="Contrato, nome, função e escala são obrigatórios.")
    ctr = (
        await db.execute(
            text("SELECT client_id::text, contract_number FROM contracts WHERE id = CAST(:c AS uuid)"),
            {"c": p["contract_id"]},
        )
    ).fetchone()
    if not ctr:
        raise HTTPException(status_code=404, detail="Contrato não encontrado.")
    qtd = int(_num(p.get("required_headcount"), 1) or 1)
    sal = _num(p.get("salario_base")) if p.get("salario_base") else None
    code = "VG-" + datetime.now().strftime("%y%m%d%H%M%S")
    pid = (
        await db.execute(
            text(
                "INSERT INTO posts (id, code, name, post_type, status, shift_type, contract_id, client_id, required_headcount, salario_base, address, "
                " is_active, created_by, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :code, :n, :f, 'active', :e, CAST(:c AS uuid), CAST(:cl AS uuid), :q, :s, nullif(:a,''), true, CAST(:u AS uuid), now(), now()) "
                "RETURNING id::text"
            ),
            {
                "code": code,
                "n": p["name"],
                "f": p["post_type"],
                "e": p["shift_type"],
                "c": p["contract_id"],
                "cl": ctr[0],
                "q": qtd,
                "s": sal,
                "a": p.get("address", ""),
                "u": _uid(current_user),
            },
        )
    ).scalar()
    await db.commit()
    return {"ok": True, "id": pid, "message": f"Vaga {p['name']} criada no contrato {ctr[1]} ({qtd} contratado(s))."}


@router.post("/action/restricao-nova")
async def rd_restricao_nova(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    try:
        r = await rc.incluir(
            db,
            employee_id=p.get("employee_id", ""),
            client_id=p.get("client_id", ""),
            motivo=p.get("motivo", ""),
            solicitado_por=p.get("solicitado_por"),
            user_id=_uid(current_user),
        )
    except rc.RestricaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    msg = "Restrição registrada."
    if r["alocado_hoje_no_cliente"]:
        msg += (
            f" ⚠ A pessoa está ALOCADA nesse cliente hoje ({r['alocado_hoje_no_cliente']}) — encerre em Movimentações."
        )
    return {"ok": True, "message": msg, **r}


@router.post("/action/restricao-encerrar")
async def rd_restricao_encerrar(
    current_user: CurrentActiveUser, restricao_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    restricao_id = _uuid(restricao_id, "Restrição")
    try:
        r = await rc.encerrar(
            db, restricao_id=restricao_id, motivo=_p(payload).get("motivo"), user_id=_uid(current_user)
        )
    except rc.RestricaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": "Restrição encerrada.", **r}


@router.post("/action/grid-cobrir")
async def rd_grid_cobrir(
    current_user: CurrentActiveUser, post_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    post_id = _uuid(post_id, "Posto")
    try:
        r = await cs.registrar(
            db,
            coberto_id=p.get("coberto_id", ""),
            cobertura_id=p.get("cobertura_id", ""),
            post_id=post_id,
            inicio=p.get("inicio") or cs.hoje_manaus(),
            fim=p.get("fim") or None,
            motivo=p.get("motivo", ""),
            observacao=p.get("observacao"),
            user_id=_uid(current_user),
            user_nome=str(getattr(current_user, "name", "") or getattr(current_user, "email", "") or "redesign"),
        )
    except cs.CoberturaErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {
        "ok": True,
        "message": f"Cobertura registrada: {r['dias']} dia(s), {r['em_folga']} em folga trabalhada.",
        **r,
    }


@router.post("/action/grid-alocar")
async def rd_grid_alocar(
    current_user: CurrentActiveUser, post_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    post_id = _uuid(post_id, "Posto")
    nome, cond = await _condominio_do_posto(db, post_id)
    try:
        r = await ms.alocar(
            db,
            employee_id=p.get("employee_id", ""),
            condominio_id=cond,
            funcao=p.get("funcao", ""),
            data_inicio=p.get("data_inicio") or ms.hoje_manaus(),
            motivo=p.get("motivo", ""),
            solicitado_por=p.get("solicitado_por") or "supervisor",
            posto_id=post_id,
            observacao=p.get("observacao"),
            user_id=_uid(current_user),
        )
    except ms.MovimentacaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {
        "ok": True,
        "message": f"Alocado em {nome}."
        + (f" {len(r['encerrou'])} alocação(ões) anterior(es) encerrada(s)." if r["encerrou"] else ""),
        **r,
    }


@router.post("/action/livro-visualizado")
async def rd_livro_visualizado(
    current_user: CurrentActiveUser, occ_id: str, payload: dict = Body(default={}), db: AsyncSession = Depends(get_db)
) -> dict:
    occ_id = _uuid(occ_id, "Ocorrência")
    n = (
        await db.execute(
            text(
                "UPDATE occurrences SET status = 'em_analise', updated_at = now() WHERE id = CAST(:i AS uuid) AND status = 'aberta' RETURNING id"
            ),
            {"i": occ_id},
        )
    ).rowcount
    if not n:
        raise HTTPException(
            status_code=409, detail="Ocorrência não está aberta (já visualizada, resolvida ou cancelada)."
        )
    await db.commit()
    return {"ok": True, "message": "Marcada como visualizada (em análise)."}


@router.post("/action/livro-finalizar")
async def rd_livro_finalizar(
    current_user: CurrentActiveUser, occ_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    from modules.operacional.occurrences.repositories.occurrence_repository import OccurrenceRepository
    from modules.operacional.occurrences.schemas.occurrence import OccurrenceResolve

    p = _p(payload)
    occ_id = _uuid(occ_id, "Ocorrência")
    if len(p.get("corrective_action", "")) < 10:
        raise HTTPException(status_code=400, detail="Descreva o que foi feito (mínimo 10 caracteres).")
    st = (await db.execute(text("SELECT status FROM occurrences WHERE id = CAST(:i AS uuid)"), {"i": occ_id})).scalar()
    if st not in ("aberta", "em_analise"):
        raise HTTPException(
            status_code=409,
            detail=f"Ocorrência está '{st or 'inexistente'}' — só aberta/em análise pode ser finalizada.",
        )
    occ = await OccurrenceRepository(db).resolve(
        occ_id,
        OccurrenceResolve(corrective_action=p["corrective_action"], resolution_notes=p.get("resolution_notes") or None),
        _uid(current_user) or "",
    )
    if not occ:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada.")
    return {"ok": True, "message": f"Ocorrência {occ.code} finalizada."}


@router.post("/action/contrato-copiar")
async def rd_contrato_copiar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    from modules.crm.models.contract import Contract
    from modules.crm.repositories.contract_repository import ContractRepository

    p = _p(payload)
    src = p.get("contract_id", "")
    if len(src) != 36:
        raise HTTPException(status_code=400, detail="Selecione o contrato de origem.")
    orig = (
        await db.execute(
            text(
                "SELECT name, start_date, end_date, client_id::text, contract_number FROM contracts WHERE id = CAST(:i AS uuid) AND is_active"
            ),
            {"i": src},
        )
    ).fetchone()
    if not orig:
        raise HTTPException(status_code=404, detail="Contrato de origem não encontrado.")
    try:
        ini = date.fromisoformat(p.get("start_date") or date.today().isoformat())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Data de início inválida.") from exc
    fim = ini + (orig[2] - orig[1]) if (orig[1] and orig[2]) else None
    novo_cli = p.get("client_id") or orig[3]
    nome = p.get("name") or f"{orig[0]} (cópia)"
    numero = Contract.generate_number(await ContractRepository(db)._get_next_contract_sequence())
    nid = (
        await db.execute(
            text(
                "INSERT INTO contracts (id, contract_number, client_id, opportunity_id, proposal_id, template_id, contract_type, status, name, description, "
                " monthly_value, total_value, setup_fee, start_date, end_date, grace_period_days, notice_period_days, auto_renewal, renewal_period_months, "
                " renewal_notification_days, adjustment_enabled, adjustment_index, adjustment_fixed_percent, adjustment_base_date, has_sla, sla_config, "
                " content, clauses, signature_required, signature_provider, commercial_manager_id, account_manager_id, created_at, updated_at, created_by, "
                " is_active, kit_mensal, tipo_servico, retencao_iss, retencao_inss, retencao_csll, empresa_id, payment_day) "
                "SELECT gen_random_uuid(), :num, CAST(:cli AS uuid), NULL, NULL, template_id, contract_type, 'draft', :nome, description, "
                " monthly_value, total_value, setup_fee, :ini, :fim, grace_period_days, notice_period_days, auto_renewal, renewal_period_months, "
                " renewal_notification_days, adjustment_enabled, adjustment_index, adjustment_fixed_percent, :ini, has_sla, sla_config, "
                " content, clauses, signature_required, signature_provider, commercial_manager_id, account_manager_id, now(), now(), CAST(:u AS uuid), "
                " true, kit_mensal, tipo_servico, retencao_iss, retencao_inss, retencao_csll, empresa_id, payment_day "
                "FROM contracts WHERE id = CAST(:src AS uuid) RETURNING id::text"
            ),
            {"num": numero, "cli": novo_cli, "nome": nome, "ini": ini, "fim": fim, "u": _uid(current_user), "src": src},
        )
    ).scalar()
    n_itens = 0
    if p.get("copiar_itens", "sim") != "nao":
        n_itens = (
            await db.execute(
                text(
                    "INSERT INTO contract_items (id, contract_id, service_type, service_name, description, quantity, unit_price, total_price, notes, created_at, is_active) "
                    "SELECT gen_random_uuid(), CAST(:n AS uuid), service_type, service_name, description, quantity, unit_price, total_price, notes, now(), true "
                    "FROM contract_items WHERE contract_id = CAST(:s AS uuid) AND coalesce(is_active, true)"
                ),
                {"n": nid, "s": src},
            )
        ).rowcount
    await db.commit()
    return {
        "ok": True,
        "id": nid,
        "contract_number": numero,
        "itens": n_itens,
        "message": f"Contrato {numero} criado como rascunho a partir de {orig[4]} ({n_itens} item(ns) copiado(s); vigência {ini:%d/%m/%Y}"
        + (f" a {fim:%d/%m/%Y}" if fim else "")
        + ").",
    }
