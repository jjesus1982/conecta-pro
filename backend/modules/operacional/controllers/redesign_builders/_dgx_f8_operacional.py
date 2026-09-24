"""DGX F8 — Operacional (24/09/2026): coberturas (folga trabalhada), livro de ocorrências do
posto, checklist de supervisão, chamados e painel de avisos. Regra em
`operacional/services/cobertura_service.py` e `supervisao_service.py`; aqui só se pinta e se
despacha. Prefixo `_` = o discovery pula; `operacional.py` importa `router` no topo e chama
`telas(db, out)` antes de `montar_grupos` (abas em `_op_grupos`).

Telas (deep-link `/redesign/operacional?t=<id>`):
  g-escalas    · coberturas · cobertura-nova
  g-postos     · livro-ocorrencias · livro-ocorrencia-nova · livro-ocorrencias-pdf
               · checklist-modelos · checklist-modelo-novo · checklist-executar · checklist-execucoes
  g-comunicacao· chamados · chamado-novo · avisos-painel · aviso-novo
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.services import cobertura_service as cs
from modules.operacional.services import supervisao_service as ss

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_END = "/api/v1/redesign/action/"

SQL_COBERTURAS = """
SELECT coalesce(s.cobertura_id, s.id)::text, min(s.substitution_date), max(s.substitution_date), count(*),
       count(*) FILTER (WHERE s.folga_trabalhada), coalesce(sum(s.horas), 0), max(eo.nome), max(es.nome), max(p.name),
       max(s.reason), string_agg(DISTINCT s.status, '/'), max(coalesce(u.name, u.email)), bool_or(s.alocacao_id IS NOT NULL),
       max(s.reason_details), max(s.post_id::text)
FROM substitutions s
LEFT JOIN employees eo ON eo.id = s.original_employee_id
LEFT JOIN employees es ON es.id = s.substitute_employee_id
LEFT JOIN posts p ON p.id = s.post_id
LEFT JOIN users u ON u.id = coalesce(s.approved_by, s.requested_by)
WHERE s.is_active
GROUP BY 1 ORDER BY 2 DESC, 7 LIMIT 400
"""
SQL_RESUMO_MES = """
SELECT to_char(s.substitution_date, 'MM/YYYY'), es.nome, count(*), count(*) FILTER (WHERE s.folga_trabalhada), coalesce(sum(s.horas), 0)
FROM substitutions s JOIN employees es ON es.id = s.substitute_employee_id
WHERE s.is_active AND s.status IN ('confirmed', 'in_progress', 'completed')
  AND s.substitution_date >= (date_trunc('month', (now() AT TIME ZONE 'America/Manaus')::date) - interval '1 month')::date
GROUP BY 1, 2 ORDER BY 1 DESC, 3 DESC, 2
"""
SQL_EMPS = (
    "SELECT id::text, nome, coalesce(cargo,'') FROM employees WHERE status = 'ativo' "
    "AND coalesce(is_homologacao,false) = false ORDER BY nome"
)
SQL_POSTOS = "SELECT id::text, name FROM posts WHERE is_active ORDER BY name"
SQL_CARGOS = (
    "SELECT DISTINCT upper(cargo) FROM employees WHERE status = 'ativo' AND coalesce(cargo,'') <> '' ORDER BY 1"
)
SQL_EXECUCOES = """
SELECT c.id::text, c.finalizado_at, t.nome, p.name, coalesce(c.executado_por_nome, '—'), c.total_itens, c.itens_conformes,
       c.itens_nao_conformes, c.percentual_conformidade, o.code, o.id::text,
       (SELECT string_agg(i.pergunta, '; ' ORDER BY i.ordem) FROM checklist_respostas r JOIN checklist_itens i ON i.id = r.item_id
         WHERE r.checklist_preenchido_id = c.id AND r.is_conforme = false)
FROM checklist_preenchido c
JOIN checklist_templates t ON t.id = c.template_id
LEFT JOIN posts p ON p.id = c.post_id
LEFT JOIN occurrences o ON o.id = c.ocorrencia_id
WHERE c.post_id IS NOT NULL
ORDER BY c.finalizado_at DESC NULLS LAST LIMIT 300
"""
SQL_CHAMADOS = """
SELECT * FROM (
  SELECT 'op' AS origem, c.id::text, c.numero::text, coalesce(p.name, '—') AS posto, c.aberto_por, coalesce(c.solicitante_nome, '—'),
         coalesce(c.canal, '—'), coalesce(c.categoria, '—'), c.prioridade, c.descricao, c.status, e.nome AS atribuido,
         c.aberto_em, c.atendido_em, c.resolvido_em, c.sla_min, c.resolucao
  FROM op_chamados c LEFT JOIN posts p ON p.id = c.post_id LEFT JOIN employees e ON e.id = c.atribuido_a
  UNION ALL
  SELECT 'portal', t.id::text, 'P-' || left(t.id::text, 6), coalesce(g.name, '—'), 'cliente', coalesce(g.name, '—'), 'portal',
         'portal', lower(coalesce(t.priority, 'NORMAL')), t.subject || coalesce(' — ' || t.description, ''),
         CASE upper(t.status) WHEN 'ABERTO' THEN 'aberto' WHEN 'FECHADO' THEN 'resolvido' ELSE 'em_atendimento' END,
         NULL, t.created_at AT TIME ZONE 'America/Manaus', NULL, t.closed_at AT TIME ZONE 'America/Manaus', 1440, NULL
  FROM client_portal_tickets t LEFT JOIN ged_clients g ON g.id = t.client_id
) x ORDER BY (status = 'aberto') DESC, (status = 'em_atendimento') DESC, aberto_em DESC LIMIT 300
"""


def _d(v) -> str:
    return v.strftime("%d/%m/%Y") if v else "—"


def _dh(v) -> str:
    return v.strftime("%d/%m %H:%M") if v else "—"


def _opts(rows, label, vazio="— escolha —") -> list[dict]:
    return [{"value": "", "label": vazio}] + [{"value": r[0], "label": label(r)} for r in rows]


def _kv(d: dict, vazio: str | None = None) -> list[dict]:
    base = [{"value": "", "label": vazio}] if vazio else []
    return base + [{"value": k, "label": v} for k, v in d.items()]


def _falhou(out: dict, tid: str, titulo: str, exc: Exception) -> None:
    from modules.operacional.controllers.redesign_data_controller import t

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


async def telas(db, out: dict) -> None:
    from modules.operacional.controllers.redesign_data_controller import b, initials, t

    try:
        await cs._ensure(db)
        await ss._ensure(db)
        emps = (await db.execute(text(SQL_EMPS))).fetchall()
        postos = (await db.execute(text(SQL_POSTOS))).fetchall()
        cargos = [r[0] for r in (await db.execute(text(SQL_CARGOS))).fetchall()]
    except Exception as exc:  # noqa: BLE001 — visível, nunca calado
        await db.rollback()
        logger.error("dgx f8: _ensure/listas falharam: %s", exc, exc_info=True)
        _falhou(out, "coberturas", "Coberturas", exc)
        return
    hoje = cs.hoje_manaus()
    hoje_s = hoje.isoformat()
    emp_opts = _opts(emps, lambda r: f"{r[1]} — {r[2]}" if r[2] else r[1], "— colaborador (ativos) —")
    posto_opts = _opts(postos, lambda r: r[1], "— posto —")
    posto_nome = {r[0]: r[1] for r in postos}

    # ───────── 1. Coberturas (g-escalas) ─────────
    try:
        rows = (await db.execute(text(SQL_COBERTURAS))).fetchall()
        resumo = (await db.execute(text(SQL_RESUMO_MES))).fetchall()
        linhas = []
        for r in rows:
            gid, ini, fim, dias, folgas, horas, coberto, cobertura, posto, reason, status, quem, f5, obs, pid = r
            tone = (
                "ok"
                if "confirmed" in (status or "") or "completed" in (status or "")
                else ("warn" if "pending" in (status or "") else "mut")
            )
            linhas.append(
                {
                    "cells": [
                        t(_d(ini) if ini == fim else f"{_d(ini)} → {_d(fim)}", 600),
                        t(coberto or "—", 600, _ND, initials(coberto or "")),
                        t(cobertura or "— (sem substituto)", 600, _ND, initials(cobertura or "")),
                        t(posto or "—"),
                        t(cs.ROTULO.get(reason or "", reason or "—")),
                        t(str(dias)),
                        b(f"{folgas} de {dias}", "warn" if folgas else "mut"),
                        t(f"{float(horas):.1f} h"),
                        b("F5 ✓", "info") if f5 else t("—"),
                        t(quem or "—"),
                        b((status or "—").replace("_", " "), tone),
                    ],
                    "filtros": {"mes": f"{ini:%m/%Y}" if ini else "—", "posto": posto or "—"},
                }
            )
        paineis: dict[str, list] = {}
        for mes, nome, n, nf, h in resumo:
            paineis.setdefault(mes, []).append(
                {"left": nome, "right": f"{n} cob. · {nf} em folga · {float(h):.0f} h", "tone": "warn" if nf else "mut"}
            )
        n_folga = sum(r[4] for r in rows)
        out["coberturas"] = {
            "title": "Coberturas — quem cobriu quem",
            "sub": (
                f"{len(rows)} cobertura(s) · {n_folga} dia(s) em folga trabalhada · fonte: substitutions (a mesma do quadro "
                "falta → substituto) · folga = o cobertura não tinha turno no dia mas tem escala na quinzena (derivado de shifts) · "
                "resumo por pessoa no mês abaixo é a base para HE / folga compensatória"
            ),
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar coberto, cobertura, posto…",
            "grid": "1.2fr 1.5fr 1.5fr 1.3fr 0.9fr 0.5fr 0.8fr 0.6fr 0.5fr 1fr 0.9fr",
            "cols": [
                "Período",
                "Coberto",
                "Cobertura",
                "Posto",
                "Motivo",
                "Dias",
                "Folga trab.",
                "Horas",
                "Mov.",
                "Registrou",
                "Situação",
            ],
            "filtros": [{"key": "mes", "label": "Mês"}, {"key": "posto", "label": "Posto"}],
            "rows": linhas or [{"cells": [t("Nenhuma cobertura registrada", 500)] + [t("—")] * 10}],
            "panelGrid": "1fr 1fr",
            "panels": [
                {"title": f"Resumo por pessoa — {mes}", "rows": [{"left": p["left"], "right": p["right"]} for p in ps]}
                for mes, ps in paineis.items()
            ]
            or [
                {
                    "title": "Resumo por pessoa",
                    "rows": [{"left": "Sem coberturas neste mês e no anterior", "right": "—"}],
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx f8: coberturas: %s", exc, exc_info=True)
        _falhou(out, "coberturas", "Coberturas", exc)

    out["cobertura-nova"] = {
        "title": "Nova cobertura",
        "cta": "Registrar cobertura",
        "sub": (
            "Uma linha por dia do período, com turno espelho para o cobertura no posto (o mesmo do quadro falta → substituto). "
            "Folga trabalhada é derivada da escala do cobertura em cada dia. Férias/afastamento também criam a movimentação "
            "(F5) — o coberto precisa ter férias aprovadas / afastamento ativo na data. Nunca dois postos no mesmo dia."
        ),
        "type": "form",
        "submit": {
            "endpoint": _END + "cobertura-registrar",
            "okMsg": "Cobertura registrada.",
            "showResult": True,
            "confirm": "Isto cria turnos reais para o cobertura e, em férias/afastamento, muda a alocação dele. Confirma?",
        },
        "fields": [
            {
                "key": "coberto_id",
                "label": "Colaborador coberto*",
                "type": "select",
                "span": "span 2",
                "options": emp_opts,
            },
            {
                "key": "cobertura_id",
                "label": "Colaborador cobertura*",
                "type": "select",
                "span": "span 2",
                "options": emp_opts,
            },
            {"key": "post_id", "label": "Posto*", "type": "select", "span": "span 2", "options": posto_opts},
            {
                "key": "motivo",
                "label": "Motivo*",
                "type": "select",
                "options": _kv({k: cs.ROTULO[v] for k, v in cs.MOTIVOS.items()}, "— motivo —"),
            },
            {"key": "inicio", "label": "Data início*", "type": "date", "value": hoje_s},
            {"key": "fim", "label": "Data término (vazio = só o dia)", "type": "date"},
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
        ],
    }

    # ───────── 2. Livro de ocorrências (g-postos) ─────────
    try:
        lv = await ss.livro(db)
        tipo_tone = {"ocorrencia": "bad", "passagem": "info", "checkin": "ok", "instrucao": "mut"}
        tipo_rotulo = {
            "ocorrencia": "Ocorrência",
            "passagem": "Passagem",
            "checkin": "Check-in",
            "instrucao": "Instrução",
        }
        grau_tone = {"leve": "mut", "moderada": "warn", "grave": "bad", "gravissima": "bad"}
        linhas = []
        for r in lv:
            tipo, pid, quando, quem, titulo, detalhe, grau, situacao, ref, _rid = r
            dia = quando.date() if quando else None
            docs = (
                [
                    {
                        "label": f"Livro {posto_nome.get(pid, '')} {dia:%d/%m}",
                        "url": f"/api/v1/redesign/livro-ocorrencias/{pid}/{dia.isoformat()}/pdf",
                        "fmt": "pdf",
                        "mode": "blob",
                    }
                ]
                if (pid and dia)
                else []
            )
            linhas.append(
                {
                    "cells": [
                        t(_dh(quando), 600),
                        t(posto_nome.get(pid, "—"), 600, _ND),
                        b(tipo_rotulo.get(tipo, tipo), tipo_tone.get(tipo, "info")),
                        t(f"{titulo or '—'}" + (f" — {str(detalhe)[:140]}" if detalhe else "")),
                        t(quem or "—"),
                        b(f"{grau} · {situacao}", grau_tone.get(grau or "", "mut")) if grau else t(ref or "—"),
                    ],
                    "filtros": {"posto": posto_nome.get(pid, "—"), "dia": _d(dia)},
                    "docs": docs,
                }
            )
        out["livro-ocorrencias"] = {
            "title": "Livro de ocorrências do posto",
            "sub": (
                f"{len(lv)} registro(s) nos últimos 30 dias · união de ocorrências + passagens de turno + check-ins do gerente + "
                "instruções de posto, em ordem cronológica (hora de Manaus) · filtre por posto e dia · PDF timbrado do dia por linha"
            ),
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar registro, posto, quem…",
            "grid": "0.9fr 1.4fr 0.8fr 3fr 1.1fr 1fr",
            "cols": ["Quando", "Posto", "Tipo", "Registro", "Quem registrou", "Grau / ref."],
            "filtros": [{"key": "posto", "label": "Posto"}, {"key": "dia", "label": "Dia"}],
            "rows": linhas or [{"cells": [t("Nenhum registro nos últimos 30 dias", 500)] + [t("—")] * 5}],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx f8: livro: %s", exc, exc_info=True)
        _falhou(out, "livro-ocorrencias", "Livro de ocorrências", exc)

    tipos_oc = [
        ("incidente", "Incidente"),
        ("nao_conformidade_documental", "Não conformidade"),
        ("abandono_posto", "Abandono de posto"),
        ("atraso", "Atraso"),
        ("falta_injustificada", "Falta injustificada"),
        ("falta_uniforme", "Falta de uniforme"),
        ("falta_epi", "Falta de EPI"),
        ("uso_celular", "Uso de celular"),
        ("dormindo_servico", "Dormindo em serviço"),
        ("postura_inadequada", "Postura inadequada"),
        ("manutencao", "Manutenção"),
        ("conflito", "Conflito"),
        ("elogio", "Elogio"),
        ("outros", "Outros"),
    ]
    out["livro-ocorrencia-nova"] = {
        "title": "Registrar no livro",
        "cta": "Registrar",
        "sub": "Grava em `occurrences` pelo mesmo caminho da ocorrência rápida (código OCO-AAAA-NNNNN). Aparece no livro do posto e no PDF do dia.",
        "type": "form",
        "submit": {"endpoint": _END + "livro-ocorrencia-nova", "okMsg": "Registrado no livro.", "showResult": True},
        "fields": [
            {"key": "post_id", "label": "Posto*", "type": "select", "span": "span 2", "options": posto_opts},
            {
                "key": "occurrence_type",
                "label": "Tipo*",
                "type": "select",
                "options": [{"value": v, "label": l} for v, l in tipos_oc],
            },
            {
                "key": "severity",
                "label": "Gravidade*",
                "type": "select",
                "options": [
                    {"value": v, "label": l}
                    for v, l in (
                        ("leve", "Leve"),
                        ("moderada", "Moderada"),
                        ("grave", "Grave"),
                        ("gravissima", "Gravíssima"),
                    )
                ],
            },
            {"key": "dia", "label": "Dia", "type": "date", "value": hoje_s},
            {"key": "hora", "label": "Hora (HH:MM)", "type": "text", "ph": "vazio = agora"},
            {"key": "title", "label": "Título", "type": "text", "span": "span 2", "ph": "vazio = início da descrição"},
            {"key": "description", "label": "Descrição* (mín. 10)", "type": "textarea", "span": "span 2"},
            {
                "key": "employee_id",
                "label": "Colaborador envolvido",
                "type": "select",
                "span": "span 2",
                "options": _opts(emps, lambda r: r[1], "— ninguém em específico —"),
            },
            {"key": "witnesses", "label": "Envolvidos / testemunhas", "type": "text", "span": "span 2"},
            {
                "key": "foto_url",
                "label": "Foto (URL, opcional)",
                "type": "text",
                "span": "span 2",
                "ph": "cole o link da foto",
            },
        ],
    }
    out["livro-ocorrencias-pdf"] = {
        "title": "Livro do dia em PDF",
        "cta": "Gerar PDF",
        "sub": "PDF timbrado (padrão-ouro) com todos os registros do posto no dia — ocorrências, passagens, check-ins e instruções.",
        "type": "form",
        "submit": {"endpoint": _END + "livro-ocorrencias-pdf", "okMsg": "PDF gerado.", "showResult": True},
        "fields": [
            {"key": "post_id", "label": "Posto*", "type": "select", "span": "span 2", "options": posto_opts},
            {"key": "dia", "label": "Dia*", "type": "date", "value": hoje_s},
        ],
    }

    # ───────── 3. Checklist de supervisão (g-postos) ─────────
    try:
        modelos = (await db.execute(text(ss.SQL_MODELOS))).fetchall()
        itens = (await db.execute(text(ss.SQL_ITENS))).fetchall()
        execs = (await db.execute(text(SQL_EXECUCOES))).fetchall()
        out["checklist-modelos"] = {
            "title": "Checklist — modelos",
            "sub": f"{len(modelos)} modelo(s) · fonte: checklist_templates/checklist_itens (as mesmas do Campo, tipo em categoria_equipamento)",
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar modelo…",
            "grid": "0.9fr 2fr 0.9fr 0.6fr 0.8fr 0.7fr 0.7fr",
            "cols": ["Código", "Modelo", "Tipo", "Itens", "Obrigatórios", "Execuções", "Ativo"],
            "rows": [
                {
                    "cells": [
                        t(m[1], 600),
                        t(m[2] + (" (padrão)" if m[5] else ""), 600, _ND),
                        t(ss.TIPOS_CHECKLIST.get(m[3], m[3])),
                        t(str(m[6])),
                        t(str(m[7])),
                        t(str(m[8])),
                        b("sim", "ok") if m[4] else b("não", "mut"),
                    ]
                }
                for m in modelos
            ]
            or [{"cells": [t("Nenhum modelo", 500)] + [t("—")] * 6}],
        }
        out["checklist-modelo-novo"] = {
            "title": "Novo modelo de checklist",
            "cta": "Criar modelo",
            "sub": (
                "Itens: UMA LINHA POR ITEM no formato  pergunta | tipo | obrigatório  — tipo: sim_nao, nota, texto ou foto; "
                "obrigatório: s ou n (padrão s). Ex.:  Extintor na validade | sim_nao | s"
            ),
            "type": "form",
            "submit": {"endpoint": _END + "checklist-modelo-criar", "okMsg": "Modelo criado.", "showResult": True},
            "fields": [
                {"key": "nome", "label": "Nome*", "type": "text", "span": "span 2"},
                {"key": "tipo", "label": "Tipo*", "type": "select", "options": _kv(ss.TIPOS_CHECKLIST)},
                {
                    "key": "itens",
                    "label": "Itens* (uma linha por item)",
                    "type": "textarea",
                    "span": "span 2",
                    "ph": "Uniforme completo | sim_nao | s\nNota do atendimento | nota | n",
                },
            ],
        }
        campos = [
            {
                "key": "template_id",
                "label": "Modelo*",
                "type": "select",
                "span": "span 2",
                "options": [{"value": m[0], "label": m[2] + (" (padrão)" if m[5] else "")} for m in modelos if m[4]],
            },
            {"key": "post_id", "label": "Posto*", "type": "select", "span": "span 2", "options": posto_opts},
        ]
        nome_modelo = {m[0]: m[2] for m in modelos}
        varios = len({i[1] for i in itens}) > 1
        for it in itens:
            iid, tid, ordem, pergunta, tipo_resp, obrig = it
            rot = f"{ordem}. {pergunta}" + (" *" if obrig else "")
            if varios:
                rot = f"[{nome_modelo.get(tid, '?')[:28]}] " + rot
            k = ss.tipo_item(tipo_resp)
            if k == "sim_nao":
                campos.append(
                    {
                        "key": f"r_{iid}",
                        "label": rot,
                        "type": "select",
                        "span": "span 2",
                        "options": [
                            {"value": "", "label": "— não avaliado —"},
                            {"value": "sim", "label": "Conforme"},
                            {"value": "nao", "label": "NÃO conforme"},
                        ],
                    }
                )
            elif k == "nota":
                campos.append(
                    {"key": f"r_{iid}", "label": rot + " (0–10; ≥ 7 conforme)", "type": "number", "span": "span 2"}
                )
            elif k == "foto":
                campos.append({"key": f"r_{iid}", "label": rot + " (URL da foto)", "type": "text", "span": "span 2"})
            else:
                campos.append({"key": f"r_{iid}", "label": rot, "type": "text", "span": "span 2"})
        campos.append({"key": "observacoes", "label": "Observações gerais", "type": "textarea", "span": "span 2"})
        out["checklist-executar"] = {
            "title": "Executar checklist",
            "cta": "Concluir checklist",
            "sub": (
                "Escolha o modelo e o posto e responda os itens (* = obrigatório). Só os itens do modelo escolhido contam. "
                "Item obrigatório NÃO conforme (ou sem resposta) gera UMA ocorrência no posto automaticamente."
            ),
            "type": "form",
            "submit": {"endpoint": _END + "checklist-executar", "okMsg": "Checklist gravado.", "showResult": True},
            "fields": campos,
        }
        out["checklist-execucoes"] = {
            "title": "Checklist — execuções",
            "sub": f"{len(execs)} execução(ões) · fonte: checklist_preenchido/checklist_respostas · ocorrência gerada quando item obrigatório reprova",
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar modelo, posto, quem…",
            "grid": "0.9fr 1.4fr 1.4fr 1.1fr 0.5fr 0.7fr 0.7fr 2fr 0.9fr",
            "cols": ["Quando", "Modelo", "Posto", "Quem", "Itens", "Conf.", "% conf.", "Não conformes", "Ocorrência"],
            "rows": [
                {
                    "cells": [
                        t(_dh(e[1]), 600),
                        t(e[2], 600, _ND),
                        t(e[3] or "—"),
                        t(e[4]),
                        t(str(e[5] or 0)),
                        t(f"{e[6] or 0}/{(e[6] or 0) + (e[7] or 0)}"),
                        b(
                            f"{float(e[8] or 0):.0f}%",
                            "ok" if float(e[8] or 0) >= 90 else ("warn" if float(e[8] or 0) >= 70 else "bad"),
                        ),
                        t((e[11] or "—")[:160]),
                        b(e[9], "bad") if e[9] else t("—"),
                    ],
                    "filtros": {"posto": e[3] or "—", "modelo": e[2]},
                }
                for e in execs
            ]
            or [{"cells": [t("Nenhuma execução ainda", 500)] + [t("—")] * 8}],
            "filtros": [{"key": "posto", "label": "Posto"}, {"key": "modelo", "label": "Modelo"}],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx f8: checklist: %s", exc, exc_info=True)
        _falhou(out, "checklist-modelos", "Checklist", exc)

    # ───────── 4. Chamados (g-comunicacao) ─────────
    try:
        ch = (await db.execute(text(SQL_CHAMADOS))).fetchall()
        agora = ss.agora_manaus()
        linhas = []
        n_abertos = n_vencidos = 0
        for r in ch:
            (
                origem,
                cid,
                numero,
                posto,
                ab,
                sol,
                canal,
                cat,
                prio,
                desc,
                status,
                atrib,
                aberto_em,
                atendido_em,
                resolvido_em,
                sla,
                resol,
            ) = r
            prazo = (aberto_em + timedelta(minutes=int(sla or 0))) if aberto_em else None
            vivo = status in ("aberto", "em_atendimento")
            vencido = bool(vivo and prazo and agora > prazo)
            if status == "aberto":
                n_abertos += 1
            if vencido:
                n_vencidos += 1
            if vivo:
                sla_txt = b("SLA VENCIDO", "bad") if vencido else b(f"até {_dh(prazo)}", "ok" if prazo else "mut")
            else:
                cumpriu = bool(prazo and resolvido_em and resolvido_em <= prazo)
                sla_txt = b("no prazo", "ok") if cumpriu else b("fora do prazo", "warn")
            acoes = []
            if origem == "op" and status == "aberto":
                acoes.append(
                    {
                        "title": f"Assumir o chamado #{numero}",
                        "endpoint": f"{_END}chamado-assumir?chamado_id={cid}",
                        "method": "POST",
                        "btnLabel": "Assumir",
                        "submitLabel": "Assumir",
                        "btnStyle": "outline",
                        "okMsg": "Chamado assumido. Recarregue a tela.",
                        "fields": [
                            {
                                "key": "employee_id",
                                "label": "Atribuir a (vazio = eu)",
                                "type": "select",
                                "options": _opts(emps, lambda r: r[1], "— eu mesmo —"),
                            }
                        ],
                    }
                )
            if origem == "op" and vivo:
                acoes.append(
                    {
                        "title": f"Resolver o chamado #{numero}",
                        "endpoint": f"{_END}chamado-resolver?chamado_id={cid}",
                        "method": "POST",
                        "btnLabel": "Resolver",
                        "submitLabel": "Resolver",
                        "btnStyle": "primary",
                        "okMsg": "Chamado resolvido. Recarregue a tela.",
                        "fields": [
                            {"key": "resolucao", "label": "Resolução*", "type": "textarea", "span": "span 2"},
                            {
                                "key": "cancelar",
                                "label": "Cancelar em vez de resolver?",
                                "type": "select",
                                "options": [
                                    {"value": "", "label": "Não — resolvido"},
                                    {"value": "sim", "label": "Sim — cancelar"},
                                ],
                            },
                        ],
                    }
                )
            linhas.append(
                {
                    "cells": [
                        b(f"#{numero}", "bad" if status == "aberto" else "info")
                        if origem == "op"
                        else b(numero, "mut"),
                        t(_dh(aberto_em), 600),
                        t(posto, 600, _ND),
                        t(
                            f"{ss.ABERTO_POR.get(ab, ab)} · {sol}"
                            + (f" · {ss.CANAIS.get(canal, canal)}" if canal and canal != "—" else "")
                        ),
                        t(ss.CATEGORIAS_CHAMADO.get(cat, cat)),
                        b(prio, "bad" if prio in ("urgente", "alta") else "mut"),
                        t((desc or "—")[:160]),
                        t(atrib or "—"),
                        sla_txt,
                        b(
                            ss.STATUS_CHAMADO.get(status, status),
                            "bad" if status == "aberto" else ("warn" if status == "em_atendimento" else "ok"),
                        ),
                    ],
                    "filtros": {"status": ss.STATUS_CHAMADO.get(status, status), "posto": posto},
                    "actions": acoes,
                }
            )
        out["chamados"] = {
            "title": "Chamados",
            "sub": (
                f"{n_abertos} aberto(s) · {n_vencidos} com SLA vencido · fonte: op_chamados ∪ client_portal_tickets (os do portal do cliente "
                "entram só para leitura, com prefixo P-) · SLA por prioridade: urgente 1h · alta 4h · normal 24h · baixa 72h"
            ),
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar chamado, posto, solicitante…",
            "grid": "0.6fr 0.9fr 1.3fr 1.5fr 1fr 0.6fr 2.2fr 1fr 0.9fr 0.9fr",
            "cols": [
                "Nº",
                "Aberto em",
                "Posto",
                "Quem abriu",
                "Categoria",
                "Prior.",
                "Descrição",
                "Atribuído",
                "SLA",
                "Situação",
            ],
            "filtros": [{"key": "status", "label": "Situação"}, {"key": "posto", "label": "Posto"}],
            "rows": linhas or [{"cells": [t("Nenhum chamado", 500)] + [t("—")] * 9}],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx f8: chamados: %s", exc, exc_info=True)
        _falhou(out, "chamados", "Chamados", exc)

    out["chamado-novo"] = {
        "title": "Novo chamado",
        "cta": "Abrir chamado",
        "sub": "Registra o pedido do cliente/supervisor/colaborador com SLA pela prioridade. Assumir e Resolver ficam na linha do chamado.",
        "type": "form",
        "submit": {"endpoint": _END + "chamado-abrir", "okMsg": "Chamado aberto.", "showResult": True},
        "fields": [
            {"key": "post_id", "label": "Posto", "type": "select", "span": "span 2", "options": posto_opts},
            {"key": "aberto_por", "label": "Aberto por*", "type": "select", "options": _kv(ss.ABERTO_POR)},
            {"key": "canal", "label": "Canal", "type": "select", "options": _kv(ss.CANAIS, "— canal —")},
            {
                "key": "solicitante_nome",
                "label": "Nome de quem pediu",
                "type": "text",
                "span": "span 2",
                "ph": "síndico, morador, colaborador…",
            },
            {
                "key": "categoria",
                "label": "Categoria",
                "type": "select",
                "options": _kv(ss.CATEGORIAS_CHAMADO, "— categoria —"),
            },
            {
                "key": "prioridade",
                "label": "Prioridade*",
                "type": "select",
                "options": [
                    {"value": k, "label": f"{k.capitalize()} (SLA {v // 60} h)"} for k, v in ss.PRIORIDADES.items()
                ],
            },
            {"key": "descricao", "label": "Descrição* (mín. 10)", "type": "textarea", "span": "span 2"},
        ],
    }

    # ───────── 5. Avisos / painel (g-comunicacao) ─────────
    try:
        av = await ss.avisos(db)
        linhas = []
        for r in av:
            (
                aid,
                titulo,
                prio,
                tipo,
                dtipo,
                pub,
                exp,
                req,
                status,
                postos_n,
                funcao,
                dest,
                lidos,
                conf,
                sem_user,
                nao_leram,
            ) = r
            if dtipo in ("post", "posto"):
                publico = f"Posto: {postos_n or '—'}"
            elif dtipo in ("employee", "funcionario"):
                publico = f"Função: {funcao}" if funcao else "Pessoas escolhidas"
            else:
                publico = "Todos"
            nao = int(dest or 0) - int(lidos or 0)
            linhas.append(
                {
                    "cells": [
                        t(titulo[:70], 600, _ND),
                        t(publico),
                        t(f"{_d(pub)} → {_d(exp) if exp else 'sem fim'}"),
                        b(prio or "normal", "bad" if prio in ("alta", "urgente") else "mut"),
                        t(str(dest or 0)),
                        b(str(lidos or 0), "ok" if lidos else "mut"),
                        b(str(nao), "warn" if nao else "ok"),
                        t(f"{conf or 0}" + (" (exige)" if req else "")),
                        t((nao_leram or "—")[:120] + (f" · {sem_user} sem usuário" if sem_user else "")),
                        b(
                            "publicado" if (status or "").lower() in ("published", "publicado") else "agendado",
                            "ok" if (status or "").lower() in ("published", "publicado") else "info",
                        ),
                    ],
                    "filtros": {"publico": publico.split(":")[0]},
                }
            )
        out["avisos-painel"] = {
            "title": "Avisos — painel de leitura",
            "sub": (
                f"{len(av)} aviso(s) vigente(s) · destinatários pela régua do serviço de comunicados (todos = ativos; posto = "
                "employees.posto_atual_id; função = lista de pessoas) · lido = communication_announcement_reads via o usuário do "
                "colaborador · 'sem usuário' = colaborador sem login, não tem como ler no app"
            ),
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar aviso…",
            "grid": "2fr 1.2fr 1.2fr 0.6fr 0.6fr 0.5fr 0.6fr 0.7fr 2fr 0.8fr",
            "cols": [
                "Aviso",
                "Público",
                "Vigência",
                "Prior.",
                "Destin.",
                "Lidos",
                "Não lidos",
                "Confirm.",
                "Quem não leu",
                "Status",
            ],
            "filtros": [{"key": "publico", "label": "Público"}],
            "rows": linhas or [{"cells": [t("Nenhum aviso vigente", 500)] + [t("—")] * 9}],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx f8: avisos: %s", exc, exc_info=True)
        _falhou(out, "avisos-painel", "Avisos", exc)

    out["aviso-novo"] = {
        "title": "Novo aviso",
        "cta": "Publicar aviso",
        "sub": (
            "Grava pelo serviço de comunicados e PUBLICA (início hoje) ou agenda (início futuro). Público: todos, um posto "
            "(quem tem o posto como atual) ou uma função (todos os ativos do cargo). Fim da vigência = expiração."
        ),
        "type": "form",
        "submit": {
            "endpoint": _END + "aviso-novo",
            "okMsg": "Aviso publicado.",
            "showResult": True,
            "confirm": "Isto publica o aviso para as pessoas do público escolhido. Confirma?",
        },
        "fields": [
            {"key": "titulo", "label": "Título*", "type": "text", "span": "span 2"},
            {"key": "conteudo", "label": "Conteúdo* (mín. 10)", "type": "textarea", "span": "span 2"},
            {"key": "publico", "label": "Público*", "type": "select", "options": _kv(ss.PUBLICOS)},
            {"key": "post_id", "label": "Posto (se público = posto)", "type": "select", "options": posto_opts},
            {
                "key": "funcao",
                "label": "Função (se público = função)",
                "type": "select",
                "options": [{"value": "", "label": "— função —"}] + [{"value": c, "label": c} for c in cargos],
            },
            {
                "key": "prioridade",
                "label": "Prioridade",
                "type": "select",
                "options": [
                    {"value": v, "label": l}
                    for v, l in (("normal", "Normal"), ("baixa", "Baixa"), ("alta", "Alta"), ("urgente", "Urgente"))
                ],
            },
            {"key": "inicio", "label": "Vigência — início*", "type": "date", "value": hoje_s},
            {"key": "fim", "label": "Vigência — fim (vazio = sem fim)", "type": "date"},
            {
                "key": "categoria",
                "label": "Categoria",
                "type": "select",
                "options": [
                    {"value": v, "label": l}
                    for v, l in (
                        ("informativo", "Informativo"),
                        ("procedimento", "Procedimento"),
                        ("alerta", "Alerta"),
                        ("treinamento", "Treinamento"),
                        ("politica", "Política"),
                    )
                ],
            },
            {
                "key": "requer_confirmacao",
                "label": "Exige confirmação de leitura?",
                "type": "select",
                "options": [{"value": "", "label": "Não"}, {"value": "sim", "label": "Sim"}],
            },
        ],
    }


# ───────────────────────── ações (POST /api/v1/redesign/action/…) ─────────────────────────
router = APIRouter()


def _erro(exc) -> HTTPException:
    return HTTPException(status_code=getattr(exc, "status", 400), detail=str(exc))


def _p(payload: dict) -> dict:
    return {k: (str(v).strip() if v is not None else "") for k, v in payload.items()}


def _uid(current_user) -> str | None:
    return str(getattr(current_user, "id", "") or "") or None


def _unome(current_user) -> str:
    return str(getattr(current_user, "name", "") or getattr(current_user, "email", "") or "redesign")


@router.post("/action/cobertura-registrar")
async def rd_cobertura_registrar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    try:
        r = await cs.registrar(
            db,
            coberto_id=p.get("coberto_id", ""),
            cobertura_id=p.get("cobertura_id", ""),
            post_id=p.get("post_id", ""),
            inicio=p.get("inicio") or cs.hoje_manaus(),
            fim=p.get("fim") or None,
            motivo=p.get("motivo", ""),
            observacao=p.get("observacao"),
            user_id=_uid(current_user),
            user_nome=_unome(current_user),
        )
    except cs.CoberturaErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    msg = f"Cobertura registrada: {r['dias']} dia(s), {r['em_folga']} em folga trabalhada, {r['horas']:.1f} h."
    if r["alocacao_id"]:
        msg += " Movimentação (F5) criada."
    return {"ok": True, "message": msg, **r}


@router.post("/action/livro-ocorrencia-nova")
async def rd_livro_ocorrencia_nova(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    if not p.get("post_id"):
        raise HTTPException(status_code=400, detail="Selecione o posto.")
    quando = None
    if p.get("dia"):
        try:
            hh, mm = (p.get("hora") or ss.agora_manaus().strftime("%H:%M")).split(":")[:2]
            quando = datetime.combine(date.fromisoformat(p["dia"][:10]), datetime.min.time()).replace(
                hour=int(hh), minute=int(mm)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Dia/hora inválidos (use AAAA-MM-DD e HH:MM).") from None
    try:
        occ = await ss.criar_ocorrencia(
            db,
            user_id=_uid(current_user) or "",
            post_id=p["post_id"],
            titulo=p.get("title", ""),
            descricao=p.get("description", ""),
            tipo=p.get("occurrence_type") or "incidente",
            gravidade=p.get("severity") or "moderada",
            categoria="operacional",
            employee_id=p.get("employee_id") or None,
            envolvidos=p.get("witnesses"),
            quando=quando,
            foto_url=p.get("foto_url") or None,
        )
    except ss.SupervisaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "id": str(occ.id), "code": occ.code, "message": f"Registrado no livro: {occ.code}."}


async def _linhas_do_dia(db, post_id: str, dia: date) -> list[dict]:
    ini = datetime.combine(dia, datetime.min.time())
    rows = await ss.livro(db, desde=ini, ate=ini + timedelta(days=1))
    return [
        {
            "tipo": r[0],
            "quando": r[2],
            "quem": r[3],
            "titulo": r[4],
            "detalhe": r[5],
            "grau": r[6],
            "situacao": r[7],
            "ref": r[8],
        }
        for r in sorted(rows, key=lambda r: r[2] or ini)
        if r[1] == post_id
    ]


@router.post("/action/livro-ocorrencias-pdf")
async def rd_livro_pdf_link(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    if not p.get("post_id") or not p.get("dia"):
        raise HTTPException(status_code=400, detail="Posto e dia são obrigatórios.")
    try:
        dia = date.fromisoformat(p["dia"][:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="Dia inválido.") from None
    nome = (await db.execute(text("SELECT name FROM posts WHERE id = CAST(:p AS uuid)"), {"p": p["post_id"]})).scalar()
    if not nome:
        raise HTTPException(status_code=404, detail="Posto não encontrado.")
    n = len(await _linhas_do_dia(db, p["post_id"], dia))
    return {
        "ok": True,
        "message": f"Livro de {nome} em {dia:%d/%m/%Y}: {n} registro(s).",
        "doc": {
            "label": f"Livro {nome} {dia:%d/%m/%Y}",
            "url": f"/api/v1/redesign/livro-ocorrencias/{p['post_id']}/{dia.isoformat()}/pdf",
            "fmt": "pdf",
            "mode": "blob",
        },
    }


@router.get(
    "/livro-ocorrencias/{post_id}/{dia}/pdf", summary="Livro de ocorrências do posto — PDF do dia (padrão-ouro)"
)
async def rd_livro_pdf_get(post_id: str, dia: str, db: AsyncSession = Depends(get_db)):
    from modules.operacional.services.livro_ocorrencias_pdf import montar_livro_pdf

    try:
        d = date.fromisoformat(dia[:10])
    except ValueError:
        raise HTTPException(status_code=400, detail="Dia inválido.") from None
    nome = (await db.execute(text("SELECT name FROM posts WHERE id = CAST(:p AS uuid)"), {"p": post_id})).scalar()
    if not nome:
        raise HTTPException(status_code=404, detail="Posto não encontrado.")
    pdf = montar_livro_pdf(nome, d, await _linhas_do_dia(db, post_id, d))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="livro_{d:%Y%m%d}.pdf"'},
    )


@router.post("/action/checklist-modelo-criar")
async def rd_checklist_modelo_criar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    try:
        r = await ss.criar_modelo(
            db,
            nome=p.get("nome", ""),
            tipo=p.get("tipo", ""),
            itens_texto=payload.get("itens") or "",
            user_id=_uid(current_user),
        )
    except ss.SupervisaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {
        "ok": True,
        "message": f"Modelo {r['codigo']} criado com {r['itens']} item(ns). Recarregue a tela para vê-lo em Executar.",
        **r,
    }


@router.post("/action/checklist-executar")
async def rd_checklist_executar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    try:
        r = await ss.executar(
            db,
            template_id=p.get("template_id", ""),
            post_id=p.get("post_id", ""),
            respostas=p,
            observacoes=p.get("observacoes"),
            user_id=_uid(current_user),
            user_nome=_unome(current_user),
        )
    except ss.SupervisaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    msg = f"Checklist gravado: {r['conformes']} conforme(s), {r['nao_conformes']} não conforme(s) — {r['percentual']:.0f}%."
    if r["ocorrencia_id"]:
        msg += f" Ocorrência gerada ({len(r['reprovados_obrigatorios'])} obrigatório(s) reprovado(s))."
    return {"ok": True, "message": msg, **r}


@router.post("/action/chamado-abrir")
async def rd_chamado_abrir(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    try:
        r = await ss.abrir_chamado(
            db,
            descricao=p.get("descricao", ""),
            post_id=p.get("post_id") or None,
            aberto_por=p.get("aberto_por") or "supervisor",
            solicitante_nome=p.get("solicitante_nome"),
            canal=p.get("canal") or None,
            categoria=p.get("categoria") or None,
            prioridade=p.get("prioridade") or "normal",
            user_id=_uid(current_user),
        )
    except ss.SupervisaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": f"Chamado #{r['numero']} aberto (SLA {r['sla_min'] // 60} h).", **r}


@router.post("/action/chamado-assumir")
async def rd_chamado_assumir(
    current_user: CurrentActiveUser,
    chamado_id: str | None = None,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cid = chamado_id or str(payload.get("chamado_id") or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="Escolha o chamado.")
    try:
        r = await ss.assumir_chamado(
            db,
            chamado_id=cid,
            employee_id=str(payload.get("employee_id") or "").strip() or None,
            user_id=_uid(current_user),
        )
    except ss.SupervisaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": "Chamado em atendimento.", **r}


@router.post("/action/chamado-resolver")
async def rd_chamado_resolver(
    current_user: CurrentActiveUser,
    chamado_id: str | None = None,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cid = chamado_id or str(payload.get("chamado_id") or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="Escolha o chamado.")
    try:
        r = await ss.resolver_chamado(
            db,
            chamado_id=cid,
            resolucao=str(payload.get("resolucao") or ""),
            cancelar=bool(str(payload.get("cancelar") or "").strip()),
        )
    except ss.SupervisaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {
        "ok": True,
        "message": f"Chamado {r['status']}" + (" — dentro do SLA." if r["sla_cumprido"] else " — fora do SLA."),
        **r,
    }


@router.post("/action/aviso-novo")
async def rd_aviso_novo(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    try:
        r = await ss.criar_aviso(
            db,
            current_user=current_user,
            titulo=p.get("titulo", ""),
            conteudo=payload.get("conteudo") or "",
            publico=p.get("publico") or "todos",
            post_id=p.get("post_id") or None,
            funcao=p.get("funcao") or None,
            inicio=p.get("inicio") or None,
            fim=p.get("fim") or None,
            prioridade=p.get("prioridade") or "normal",
            categoria=p.get("categoria") or "informativo",
            requer_confirmacao=bool(p.get("requer_confirmacao")),
        )
    except ss.SupervisaoErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    except ValueError as exc:  # datas do form
        await db.rollback()
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {exc}") from exc
    return {
        "ok": True,
        "message": "Aviso publicado." if r["publicado"] else f"Aviso agendado para {r['agendado_para']}.",
        **r,
    }
