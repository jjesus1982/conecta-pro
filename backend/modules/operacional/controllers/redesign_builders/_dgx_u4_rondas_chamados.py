"""DGX U4 — Rondas do APP Vigilância (modelos com pontos, alertas, pânico) e chamados com setor
(24/09/2026). Regra em `operacional/services/ronda_alertas.py`; aqui só se pinta e se despacha.
Prefixo `_` = o discovery pula; `operacional.py` importa `router` no topo e chama `telas(db, out)`
antes de `montar_grupos` (abas no FIM de g-rondas e g-comunicacao em `_op_grupos`).

Telas (deep-link `/redesign/operacional?t=<id>`):
  g-rondas      · ronda-modelos · ronda-modelo-novo · ronda-alertas · ronda-alerta-novo · ronda-mapa · panicos
  g-comunicacao · setores · setor-novo  (+ `chamado-novo` da F8 ganha setor e contato do solicitante)
Pânico do celular: `POST /api/v1/operacional/rondas/panico` (controller da frente 06).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.services import ronda_alertas as ra

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_END = "/api/v1/redesign/action/"

SQL_MODELOS = """
SELECT m.id::text, m.nome, coalesce(p.name, '—'), coalesce(c.name, '—'), m.pontos, m.intervalo_min, m.tolerancia_min, m.ativo,
       (SELECT count(*) FROM ronda_alertas a WHERE a.modelo_id = m.id AND a.ativo),
       (SELECT count(*) FROM inspection_rounds r WHERE r.modelo_id = m.id AND r.is_active)
FROM ronda_modelos m LEFT JOIN posts p ON p.id = m.post_id LEFT JOIN clients c ON c.id = m.client_id
ORDER BY m.ativo DESC, m.nome
"""
SQL_ALERTAS = """
SELECT a.id::text, m.nome, a.tipo, a.minutos, a.destinatarios, a.ativo,
       (SELECT count(*) FROM ronda_alertas_disparados d WHERE d.alerta_id = a.id),
       (SELECT count(*) FROM ronda_alertas_disparados d WHERE d.alerta_id = a.id AND d.status = 'aberto')
FROM ronda_alertas a JOIN ronda_modelos m ON m.id = a.modelo_id ORDER BY a.ativo DESC, m.nome, a.tipo
"""
SQL_RONDAS_DIA = """
SELECT r.id::text, r.code, m.nome, m.pontos, m.intervalo_min, m.tolerancia_min, r.inspector_name, r.status,
       r.scheduled_date, r.started_at, r.completed_at
FROM inspection_rounds r JOIN ronda_modelos m ON m.id = r.modelo_id
WHERE r.is_active AND coalesce(r.completed_at, r.started_at, r.scheduled_date + interval '4 hours', r.created_at) >= :desde
ORDER BY coalesce(r.started_at, r.scheduled_date + interval '4 hours') DESC LIMIT 200
"""
SQL_DISPAROS = """
SELECT d.id::text, d.tipo, d.disparado_em, coalesce(r.code, '—'), coalesce(m.nome, '—'), d.detalhe, d.notificado, d.status
FROM ronda_alertas_disparados d LEFT JOIN inspection_rounds r ON r.id = d.ronda_id LEFT JOIN ronda_modelos m ON m.id = d.modelo_id
WHERE d.tipo <> 'panico' ORDER BY d.disparado_em DESC LIMIT 100
"""
SQL_PANICOS = """
SELECT d.id::text, d.disparado_em, coalesce(d.employee_nome, '—'), coalesce(p.name, '—'), d.latitude, d.longitude, d.mensagem,
       o.code, o.status, d.notificado, d.status, d.reconhecido_em, d.encerrado_em, d.foto_url
FROM ronda_alertas_disparados d LEFT JOIN posts p ON p.id = d.post_id LEFT JOIN occurrences o ON o.id = d.occurrence_id
WHERE d.tipo = 'panico' ORDER BY (d.status = 'aberto') DESC, d.disparado_em DESC LIMIT 200
"""
SQL_SETORES = """
SELECT s.id::text, s.nome, coalesce(c.name, '—'), coalesce(k.contract_number, '—'), coalesce(s.responsavel, '—'),
       coalesce(s.email, '—'), coalesce(s.whatsapp, '—'), s.ativo,
       (SELECT count(*) FROM op_chamados ch WHERE ch.setor_id = s.id),
       (SELECT count(*) FROM op_chamados ch WHERE ch.setor_id = s.id AND ch.status IN ('aberto','em_atendimento'))
FROM op_setores s LEFT JOIN clients c ON c.id = s.client_id LEFT JOIN contracts k ON k.id = s.contract_id
ORDER BY s.ativo DESC, c.name NULLS LAST, s.nome
"""
SQL_POSTOS = "SELECT id::text, name FROM posts WHERE is_active ORDER BY name"
SQL_CLIENTES = "SELECT id::text, name FROM clients WHERE ativo ORDER BY name"
SQL_CONTRATOS = "SELECT k.id::text, coalesce(k.contract_number, '') || ' · ' || coalesce(c.name, k.name, '') FROM contracts k LEFT JOIN clients c ON c.id = k.client_id WHERE k.is_active ORDER BY 2"
SQL_EMPS = "SELECT id::text, nome FROM employees WHERE status = 'ativo' AND coalesce(is_homologacao,false) = false ORDER BY nome"


def _dh(v) -> str:
    return v.strftime("%d/%m %H:%M") if v else "—"


def _dh_utc(v) -> str:  # UTC naive → Manaus
    return (v - ra._MANAUS_UTC).strftime("%d/%m %H:%M") if v else "—"


def _opts(rows, vazio="— escolha —") -> list[dict]:
    return [{"value": "", "label": vazio}] + [{"value": r[0], "label": r[1]} for r in rows]


def _kv(d: dict, vazio: str | None = None) -> list[dict]:
    base = [{"value": "", "label": vazio}] if vazio else []
    return base + [{"value": k, "label": v} for k, v in d.items()]


def _js(v) -> list | dict:
    return v if isinstance(v, (list, dict)) else json.loads(v or "null") or ([] if v is None else v)


def _notif_txt(n) -> str:
    n = _js(n) or []
    return ", ".join(f"{x.get('canal')} {x.get('para')} · {x.get('status')}" for x in n) or "ninguém avisado"


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


def _botao(
    titulo: str, endpoint: str, rotulo: str, estilo: str = "outline", ok: str = "Feito. Recarregue a tela."
) -> dict:
    return {
        "title": titulo,
        "endpoint": endpoint,
        "method": "POST",
        "btnLabel": rotulo,
        "submitLabel": rotulo,
        "btnStyle": estilo,
        "okMsg": ok,
        "fields": [],
    }


async def telas(db, out: dict) -> None:
    from modules.operacional.controllers.redesign_data_controller import S, b, t

    try:
        await ra._ensure(db)
        postos = (await db.execute(text(SQL_POSTOS))).fetchall()
        clientes = (await db.execute(text(SQL_CLIENTES))).fetchall()
        contratos = (await db.execute(text(SQL_CONTRATOS))).fetchall()
        emps = (await db.execute(text(SQL_EMPS))).fetchall()
        modelos = (await db.execute(text(SQL_MODELOS))).fetchall()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx u4: fontes: %s", exc, exc_info=True)
        for tid in ("ronda-modelos", "ronda-alertas", "ronda-mapa", "panicos", "setores"):
            _falhou(out, tid, tid, exc)
        return
    agora = ra.agora_utc()

    # ───────── 1. Modelos de ronda ─────────
    try:
        linhas = []
        for mid, nome, posto, cli, pontos, inter, tol, ativo, n_al, n_ro in modelos:
            pontos = _js(pontos) or []
            acoes = []
            if ativo:
                acoes.append(
                    {
                        "title": f"Agendar ronda do modelo «{nome}»",
                        "endpoint": f"{_END}ronda-modelo-agendar?modelo_id={mid}",
                        "method": "POST",
                        "btnLabel": "Agendar ronda",
                        "submitLabel": "Agendar",
                        "btnStyle": "primary",
                        "okMsg": "Ronda agendada — aparece em Rondas e no Mapa da ronda.",
                        "fields": [
                            {
                                "key": "quando",
                                "label": "Quando (vazio = agora)",
                                "type": "text",
                                "ph": "DD/MM/AAAA HH:MM",
                            }
                        ],
                    }
                )
                acoes.append(
                    _botao(f"Desativar o modelo «{nome}»", f"{_END}ronda-modelo-desativar?modelo_id={mid}", "Desativar")
                )
            linhas.append(
                {
                    "cells": [
                        t(nome, 600, _ND),
                        t(posto),
                        t(cli),
                        t(" → ".join(str(p.get("nome")) for p in pontos) or "—"),
                        t(f"{len(pontos)}", 600),
                        t(f"{inter} min"),
                        t(f"{tol} min"),
                        t(str(n_al)),
                        t(str(n_ro)),
                        b("ativo" if ativo else "inativo", "ok" if ativo else "mut"),
                    ],
                    "filtros": {"status": "ativo" if ativo else "inativo", "posto": posto},
                    "actions": acoes,
                }
            )
        out["ronda-modelos"] = {
            "title": "Modelos de ronda",
            "sub": f"{sum(1 for m in modelos if m[7])} ativo(s) · pontos ordenados por modelo (nome, GPS + raio, foto) · "
            "«Agendar ronda» cria uma ronda do modelo que o motor de alertas passa a vigiar",
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar modelo, posto, cliente…",
            "grid": "1.4fr 1.2fr 1.2fr 2.2fr 0.5fr 0.7fr 0.7fr 0.6fr 0.6fr 0.7fr",
            "cols": [
                "Modelo",
                "Posto",
                "Cliente",
                "Pontos (ordem)",
                "Nº",
                "Intervalo",
                "Tolerância",
                "Alertas",
                "Rondas",
                "Situação",
            ],
            "filtros": [{"key": "status", "label": "Situação"}, {"key": "posto", "label": "Posto"}],
            "rows": linhas or [{"cells": [t("Nenhum modelo — crie em «Novo modelo»", 500)] + [t("—")] * 9}],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx u4: ronda-modelos: %s", exc, exc_info=True)
        _falhou(out, "ronda-modelos", "Modelos de ronda", exc)

    out["ronda-modelo-novo"] = {
        "title": "Novo modelo de ronda",
        "cta": "Salvar modelo",
        "sub": "Como no DGX (ModelosRondas + locais): nome, posto/cliente e os pontos em ordem. Um ponto por linha: "
        "`nome; lat; lng; raio_m; foto` — lat/lng/raio/foto opcionais (raio padrão 50 m; foto = sim exige foto no ponto).",
        "type": "form",
        "submit": {"endpoint": _END + "ronda-modelo-novo", "okMsg": "Modelo criado.", "showResult": True},
        "fields": [
            {"key": "nome", "label": "Nome*", "type": "text", "span": "span 2", "ph": "Ronda noturna — perímetro"},
            {"key": "post_id", "label": "Posto", "type": "select", "options": _opts(postos)},
            {"key": "client_id", "label": "Cliente (se sem posto)", "type": "select", "options": _opts(clientes)},
            {
                "key": "intervalo_min",
                "label": "Intervalo (min) — duração esperada da ronda",
                "type": "number",
                "ph": "60",
            },
            {"key": "tolerancia_min", "label": "Tolerância (min)", "type": "number", "ph": "15"},
            {
                "key": "pontos",
                "label": "Pontos* (um por linha)",
                "type": "textarea",
                "span": "span 2",
                "ph": "Portaria; -3.1019; -60.0250; 40; sim\nGaragem; -3.1021; -60.0248\nPiscina",
            },
        ],
    }

    # ───────── 2. Alertas ─────────
    try:
        rows = (await db.execute(text(SQL_ALERTAS))).fetchall()
        linhas = []
        for aid, mnome, tipo, minutos, dest, ativo, n_disp, n_ab in rows:
            d = _js(dest) or {}
            resumo = (
                ", ".join((d.get("emails") or []) + [f"wa:{len(d.get('whatsapp_employee_ids') or [])} colab."]) or "—"
            )
            linhas.append(
                {
                    "cells": [
                        t(mnome, 600, _ND),
                        b(ra.TIPOS_ALERTA.get(tipo, tipo), "bad" if tipo == "panico" else "info"),
                        t(f"{minutos} min" if minutos is not None else "padrão do modelo"),
                        t(resumo),
                        t(str(n_disp)),
                        b(str(n_ab), "bad" if n_ab else "mut"),
                        b("ativo" if ativo else "inativo", "ok" if ativo else "mut"),
                    ],
                    "filtros": {"tipo": ra.TIPOS_ALERTA.get(tipo, tipo), "modelo": mnome},
                    "actions": [
                        _botao(
                            f"Desativar alerta {tipo} de «{mnome}»",
                            f"{_END}ronda-alerta-desativar?alerta_id={aid}",
                            "Desativar",
                        )
                    ]
                    if ativo
                    else [],
                }
            )
        disparos = (await db.execute(text(SQL_DISPAROS))).fetchall()
        painel = [
            {
                "left": f"{_dh_utc(dt)} · {ra.TIPOS_ALERTA.get(tp, tp)} · {code} ({mn}) — {json.dumps(_js(det), ensure_ascii=False)[:120]}",
                "right": _notif_txt(nt)[:80],
                **S["bad" if st == "aberto" else "mut"],
            }
            for _i, tp, dt, code, mn, det, nt, st in disparos[:30]
        ]
        out["ronda-alertas"] = {
            "title": "Alertas de ronda",
            "sub": f"{len(rows)} alerta(s) · {len(disparos)} disparo(s) recentes · tipos: ronda atrasada · ponto pulado · fora de sequência · "
            "sem movimento · pânico · um disparo por (alerta, ronda) — avaliar de novo NÃO duplica",
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar modelo ou tipo…",
            "grid": "1.4fr 1fr 1fr 2fr 0.6fr 0.6fr 0.7fr",
            "cols": ["Modelo", "Tipo", "Limite", "Destinatários", "Disparos", "Abertos", "Situação"],
            "filtros": [{"key": "tipo", "label": "Tipo"}, {"key": "modelo", "label": "Modelo"}],
            "rows": linhas or [{"cells": [t("Nenhum alerta — crie em «Novo alerta»", 500)] + [t("—")] * 6}],
            "panelGrid": "1fr",
            "panels": [
                {
                    "title": "Últimos disparos (motor) — «Avaliar agora» está no Mapa da ronda",
                    "rows": painel or [{"left": "Nenhum disparo", "right": "0", **S["ok"]}],
                }
            ],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx u4: ronda-alertas: %s", exc, exc_info=True)
        _falhou(out, "ronda-alertas", "Alertas de ronda", exc)

    out["ronda-alerta-novo"] = {
        "title": "Novo alerta de ronda",
        "cta": "Salvar alerta",
        "sub": "Quem é avisado quando a ronda do modelo atrasa, pula ponto, sai da ordem, para de se mover ou quando o botão de "
        "pânico é acionado. E-mail real só em produção; no sandbox fica registrado como «simulado».",
        "type": "form",
        "submit": {"endpoint": _END + "ronda-alerta-novo", "okMsg": "Alerta criado.", "showResult": True},
        "fields": [
            {
                "key": "modelo_id",
                "label": "Modelo*",
                "type": "select",
                "span": "span 2",
                "options": _opts([(m[0], m[1]) for m in modelos if m[7]]),
            },
            {"key": "tipo", "label": "Tipo*", "type": "select", "options": _kv(ra.TIPOS_ALERTA)},
            {"key": "minutos", "label": "Minutos (vazio = tolerância/intervalo do modelo)", "type": "number"},
            {
                "key": "emails",
                "label": "E-mails (vírgula)",
                "type": "text",
                "span": "span 2",
                "ph": "gerente@conectamais.pro, sindico@…",
            },
            {
                "key": "whatsapp_employee_id",
                "label": "Colaborador para WhatsApp",
                "type": "select",
                "options": _opts(emps, "— nenhum —"),
            },
        ],
    }

    # ───────── 3. Mapa da ronda (previsto × batido) ─────────
    try:
        rondas = (await db.execute(text(SQL_RONDAS_DIA), {"desde": agora - timedelta(hours=24)})).fetchall()
        linhas = []
        tot_pul = tot_atr = 0
        for rid, code, mnome, pontos, inter, tol, insp, st, sched, started, completed in rondas:
            pontos = _js(pontos) or []
            cps = await ra._checkpoints(db, rid)
            ronda = {"status": st, "scheduled_date": sched, "started_at": started, "completed_at": completed}
            seq = [ra.ponto_do_checkpoint(pontos, c) for c in cps]
            batidos = sorted({i for i in seq if i is not None})
            pul = ra.avaliar_ronda("ponto_pulado", ronda, pontos, cps, agora, None, inter, tol)
            atr = ra.avaliar_ronda("ronda_atrasada", ronda, pontos, cps, agora, None, inter, tol)
            seqx = ra.avaliar_ronda("fora_de_sequencia", ronda, pontos, cps, agora, None, inter, tol)
            tot_pul += bool(pul)
            tot_atr += bool(atr)
            marca = " · ".join(("✓ " if i in batidos else "✗ ") + str(p.get("nome")) for i, p in enumerate(pontos))
            linhas.append(
                {
                    "cells": [
                        t(code, 600, _ND),
                        t(mnome),
                        t(insp or "—"),
                        b(st, "ok" if st == "concluida" else ("warn" if st == "em_andamento" else "mut")),
                        t(_dh(sched)),
                        t(_dh_utc(started)),
                        t(_dh_utc(completed)),
                        t(f"{len(batidos)} / {len(pontos)}", 600),
                        t(marca),
                        b(", ".join(pul["pulados"]), "bad") if pul else t("—"),
                        b(f"{atr['atraso_min']} min ({atr['motivo']})", "bad") if atr else t("—"),
                        b("fora da ordem", "warn") if seqx else t("—"),
                    ],
                    "filtros": {"status": st, "modelo": mnome},
                }
            )
        out["ronda-mapa"] = {
            "title": "Mapa da ronda — previsto × batido (24 h)",
            "sub": f"{len(rondas)} ronda(s) de modelo nas últimas 24 h · {tot_pul} com ponto pulado · {tot_atr} atrasada(s) · "
            "ponto é «batido» por nome (extra_data.ponto), por posto ou por GPS dentro do raio · sem mapa gráfico (tabela)",
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar ronda, modelo, inspetor…",
            "grid": "0.9fr 1.2fr 1.1fr 0.8fr 0.8fr 0.8fr 0.8fr 0.5fr 2fr 1fr 1fr 0.8fr",
            "cols": [
                "Ronda",
                "Modelo",
                "Inspetor",
                "Situação",
                "Agendada",
                "Início",
                "Fim",
                "Batidos",
                "Pontos",
                "Pulados",
                "Atraso",
                "Ordem",
            ],
            "filtros": [{"key": "status", "label": "Situação"}, {"key": "modelo", "label": "Modelo"}],
            "rows": linhas
            or [
                {
                    "cells": [t("Nenhuma ronda de modelo nas últimas 24 h — agende uma em «Modelos de ronda»", 500)]
                    + [t("—")] * 11
                }
            ],
            "panelGrid": "1fr",
            "panels": [
                {
                    "title": "Motor de alertas",
                    "rows": [
                        {
                            "left": "Avaliar agora (idempotente — só o que nasce agora notifica). Em produção o orquestrador agenda a cada 5 min.",
                            "right": "POST /api/v1/redesign/action/ronda-avaliar",
                            **S["info"],
                        }
                    ],
                }
            ],
            "actions": [
                _botao(
                    "Rodar o motor de alertas agora",
                    f"{_END}ronda-avaliar",
                    "Avaliar agora",
                    "primary",
                    "Motor rodou. Veja os disparos em «Alertas de ronda».",
                )
            ],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx u4: ronda-mapa: %s", exc, exc_info=True)
        _falhou(out, "ronda-mapa", "Mapa da ronda", exc)

    # ───────── 4. Pânicos ─────────
    try:
        rows = (await db.execute(text(SQL_PANICOS))).fetchall()
        linhas = []
        for did, dt, quem, posto, lat, lng, msg, occ_code, occ_st, notif, st, rec, enc, foto in rows:
            acoes = []
            if st == "aberto":
                acoes.append(
                    _botao(
                        f"Reconhecer o pânico de {quem}",
                        f"{_END}panico-reconhecer?disparo_id={did}",
                        "Reconhecer",
                        "primary",
                    )
                )
            if st != "encerrado":
                acoes.append(
                    _botao(f"Encerrar o pânico de {quem}", f"{_END}panico-encerrar?disparo_id={did}", "Encerrar")
                )
            linhas.append(
                {
                    "cells": [
                        t(_dh_utc(dt), 600),
                        t(quem, 600, _ND),
                        t(posto),
                        t(f"{lat:.5f}, {lng:.5f}" if lat is not None and lng is not None else "—"),
                        t((msg or "—")[:120] + (" 📷" if foto else "")),
                        t(f"{occ_code or '—'} ({occ_st or '—'})"),
                        t(_notif_txt(notif)[:160]),
                        b(
                            ra.STATUS_DISPARO.get(st, st),
                            "bad" if st == "aberto" else ("warn" if st == "reconhecido" else "ok"),
                        ),
                        t(_dh_utc(rec)),
                        t(_dh_utc(enc)),
                    ],
                    "filtros": {"status": ra.STATUS_DISPARO.get(st, st), "posto": posto},
                    "actions": acoes,
                }
            )
        n_ab = sum(1 for r in rows if r[10] == "aberto")
        out["panicos"] = {
            "title": "Pânicos",
            "sub": f"{n_ab} aberto(s) · cada acionamento gera ocorrência GRAVE (livro do posto) e avisa os destinatários dos alertas "
            "tipo «pânico» do posto/cliente · rota do celular: POST /api/v1/operacional/rondas/panico",
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar colaborador, posto…",
            "grid": "0.8fr 1.3fr 1.2fr 1.1fr 1.6fr 1fr 1.8fr 0.8fr 0.8fr 0.8fr",
            "cols": [
                "Quando",
                "Quem",
                "Posto",
                "GPS",
                "Mensagem",
                "Ocorrência",
                "Avisados",
                "Situação",
                "Reconhecido",
                "Encerrado",
            ],
            "filtros": [{"key": "status", "label": "Situação"}, {"key": "posto", "label": "Posto"}],
            "rows": linhas or [{"cells": [t("Nenhum pânico acionado", 500)] + [t("—")] * 9}],
        }
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx u4: panicos: %s", exc, exc_info=True)
        _falhou(out, "panicos", "Pânicos", exc)

    # ───────── 5. Setores de chamado (g-comunicacao) ─────────
    try:
        rows = (await db.execute(text(SQL_SETORES))).fetchall()
        linhas = [
            {
                "cells": [
                    t(nome, 600, _ND),
                    t(cli),
                    t(ctr),
                    t(resp),
                    t(email),
                    t(wa),
                    t(str(n_ch)),
                    b(str(n_ab), "bad" if n_ab else "mut"),
                    b("ativo" if ativo else "inativo", "ok" if ativo else "mut"),
                ],
                "filtros": {"cliente": cli, "status": "ativo" if ativo else "inativo"},
                "actions": [_botao(f"Desativar o setor «{nome}»", f"{_END}setor-desativar?setor_id={sid}", "Desativar")]
                if ativo
                else [],
            }
            for sid, nome, cli, ctr, resp, email, wa, ativo, n_ch, n_ab in rows
        ]
        out["setores"] = {
            "title": "Setores de chamado",
            "sub": f"{sum(1 for r in rows if r[7])} ativo(s) · como o ContratoSetores do DGX: setor por cliente/contrato com responsável; "
            "abrir chamado no setor avisa o responsável (e-mail/WhatsApp) e resolver avisa quem pediu",
            "cta": "—",
            "type": "table",
            "searchHint": "Buscar setor, cliente, responsável…",
            "grid": "1.3fr 1.4fr 1fr 1.2fr 1.4fr 1fr 0.6fr 0.6fr 0.7fr",
            "cols": [
                "Setor",
                "Cliente",
                "Contrato",
                "Responsável",
                "E-mail",
                "WhatsApp",
                "Chamados",
                "Vivos",
                "Situação",
            ],
            "filtros": [{"key": "cliente", "label": "Cliente"}, {"key": "status", "label": "Situação"}],
            "rows": linhas or [{"cells": [t("Nenhum setor — crie em «Novo setor»", 500)] + [t("—")] * 8}],
        }
        setor_opts = _opts([(r[0], f"{r[1]} · {r[2]}") for r in rows if r[7]], "— sem setor —")
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx u4: setores: %s", exc, exc_info=True)
        _falhou(out, "setores", "Setores de chamado", exc)
        setor_opts = _opts([], "— sem setor —")

    out["setor-novo"] = {
        "title": "Novo setor de chamado",
        "cta": "Salvar setor",
        "sub": "Setor do cliente/contrato (portaria, manutenção, limpeza, elevadores…) com o responsável a avisar.",
        "type": "form",
        "submit": {"endpoint": _END + "setor-novo", "okMsg": "Setor criado.", "showResult": True},
        "fields": [
            {"key": "nome", "label": "Nome*", "type": "text", "span": "span 2", "ph": "Manutenção predial"},
            {"key": "client_id", "label": "Cliente", "type": "select", "options": _opts(clientes)},
            {"key": "contract_id", "label": "Contrato", "type": "select", "options": _opts(contratos)},
            {"key": "responsavel", "label": "Responsável", "type": "text", "ph": "Nome"},
            {"key": "email", "label": "E-mail do responsável", "type": "text", "ph": "zelador@condominio.com"},
            {"key": "whatsapp", "label": "WhatsApp do responsável", "type": "text", "ph": "92 9xxxx-xxxx"},
        ],
    }

    # chamado-novo (F8) ganha o setor e o contato de quem pediu — o action da F8 já repassa os dois
    form = out.get("chamado-novo")
    if (
        isinstance(form, dict)
        and isinstance(form.get("fields"), list)
        and not any(f.get("key") == "setor_id" for f in form["fields"])
    ):
        form["fields"].insert(
            1,
            {
                "key": "setor_id",
                "label": "Setor (avisa o responsável)",
                "type": "select",
                "span": "span 2",
                "options": setor_opts,
            },
        )
        form["fields"].append(
            {
                "key": "solicitante_contato",
                "label": "Contato de quem pediu (e-mail ou WhatsApp) — avisado ao resolver",
                "type": "text",
                "span": "span 2",
                "ph": "sindico@… ou 92 9xxxx-xxxx",
            }
        )


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


def _int(v, default):
    try:
        return int(float(str(v).replace(",", "."))) if str(v or "").strip() else default
    except ValueError:
        return default


@router.post("/action/ronda-modelo-novo")
async def rd_modelo_novo(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    try:
        r = await ra.criar_modelo(
            db,
            nome=p.get("nome", ""),
            post_id=p.get("post_id") or None,
            client_id=p.get("client_id") or None,
            pontos=ra.parse_pontos(str(payload.get("pontos") or "")),
            intervalo_min=_int(p.get("intervalo_min"), 60),
            tolerancia_min=_int(p.get("tolerancia_min"), 15),
            user_id=_uid(current_user),
        )
    except ra.RondaErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": f"Modelo criado com {r['pontos']} ponto(s).", **r}


@router.post("/action/ronda-modelo-desativar")
async def rd_modelo_desativar(
    current_user: CurrentActiveUser,
    modelo_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await ra.desativar(db, "ronda_modelos", modelo_id)
    except ra.RondaErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": "Modelo desativado."}


@router.post("/action/ronda-modelo-agendar")
async def rd_modelo_agendar(
    current_user: CurrentActiveUser,
    modelo_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    q = str(payload.get("quando") or "").strip()
    quando = None
    if q:
        try:
            quando = datetime.strptime(q, "%d/%m/%Y %H:%M")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Data no formato DD/MM/AAAA HH:MM.") from exc
    try:
        r = await ra.agendar_ronda_do_modelo(
            db,
            modelo_id=modelo_id,
            user_id=_uid(current_user) or "",
            user_nome=_unome(current_user),
            quando_manaus=quando,
        )
    except ra.RondaErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": f"Ronda {r['code']} agendada.", **r}


@router.post("/action/ronda-alerta-novo")
async def rd_alerta_novo(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    if not p.get("modelo_id"):
        raise HTTPException(status_code=400, detail="Escolha o modelo.")
    try:
        r = await ra.criar_alerta(
            db,
            modelo_id=p["modelo_id"],
            tipo=p.get("tipo") or "",
            minutos=_int(p.get("minutos"), None),
            emails=p.get("emails", "").replace(";", ",").split(","),
            whatsapp_employee_ids=[p["whatsapp_employee_id"]] if p.get("whatsapp_employee_id") else [],
        )
    except ra.RondaErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": "Alerta criado.", **r}


@router.post("/action/ronda-alerta-desativar")
async def rd_alerta_desativar(
    current_user: CurrentActiveUser,
    alerta_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        await ra.desativar(db, "ronda_alertas", alerta_id)
    except ra.RondaErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": "Alerta desativado."}


@router.post("/action/ronda-avaliar")
async def rd_ronda_avaliar(
    current_user: CurrentActiveUser, payload: dict = Body(default={}), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        novos = await ra.avaliar_rondas(db)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Motor falhou: {exc}") from exc
    return {"ok": True, "message": f"{len(novos)} disparo(s) novo(s).", "disparos": novos}


@router.post("/action/panico-reconhecer")
async def rd_panico_reconhecer(
    current_user: CurrentActiveUser,
    disparo_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        r = await ra.mudar_status_disparo(db, disparo_id=disparo_id, novo="reconhecido", user_id=_uid(current_user))
    except ra.RondaErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": "Pânico reconhecido.", **r}


@router.post("/action/panico-encerrar")
async def rd_panico_encerrar(
    current_user: CurrentActiveUser,
    disparo_id: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        r = await ra.mudar_status_disparo(db, disparo_id=disparo_id, novo="encerrado", user_id=_uid(current_user))
    except ra.RondaErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": "Pânico encerrado.", **r}


@router.post("/action/setor-novo")
async def rd_setor_novo(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    p = _p(payload)
    try:
        r = await ra.criar_setor(
            db,
            nome=p.get("nome", ""),
            client_id=p.get("client_id") or None,
            contract_id=p.get("contract_id") or None,
            responsavel=p.get("responsavel"),
            email=p.get("email"),
            whatsapp=p.get("whatsapp"),
        )
    except ra.RondaErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": "Setor criado.", **r}


@router.post("/action/setor-desativar")
async def rd_setor_desativar(
    current_user: CurrentActiveUser, setor_id: str, payload: dict = Body(default={}), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        await ra.desativar(db, "op_setores", setor_id)
    except ra.RondaErro as exc:
        await db.rollback()
        raise _erro(exc) from exc
    return {"ok": True, "message": "Setor desativado."}
