"""
Redesign — dados reais por módulo (READ-ONLY).

Devolve patches de tela na MESMA forma que os *.dc.html (kpis/panels/cols/rows/items),
para o renderizador genérico do /redesign trocar os exemplos do pacote por dado real.

Oráculo: todo valor exibido == fato no banco. Vazio-real = 0/"aguardando dado".
NUNCA fabricar. Este controller é somente leitura.
"""

import logging
import re
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser, require_permission
from core.database import get_db
from modules.operacional.scope import OperationalScope, get_operational_scope

logger = logging.getLogger(__name__)

router = APIRouter()


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


# Paleta de status (idêntica ao pacote)
S = {
    "ok": {"color": "#16A34A", "bg": "#E7F7ED"},
    "warn": {"color": "#B45309", "bg": "#FFFBEB"},
    "bad": {"color": "#B91C1C", "bg": "#FEF2F2"},
    "info": {"color": "#2563EB", "bg": "#EAF0FF"},
    "mut": {"color": "#64748B", "bg": "#F1F4FA"},
}
IC = {
    "shield": "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
    "users": "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8",
    "cal": "M3 4h18v18H3zM16 2v4M8 2v4M3 10h18",
    "alert": "M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h16.9a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01",
}


def _acao_pagar_boleto(r) -> dict | None:
    """Botão "Pagar" na linha, quando o título tem código de barras e está em aberto.

    Sem isto, pagar exigia ler o código numa tela e colar noutra — e é aí que o erro
    acontece. Em 14/08/2026 o Jordan tentou pagar VT da Patrimonial e as duas ordens
    nasceram na Eletrônica, porque a tela nem tinha campo de conta.

    ⚠️ A conta de origem NÃO vem pré-escolhida, de propósito. Valor e código de barras
    vêm prontos porque são FATOS do documento; de qual banco o dinheiro sai não é fato,
    é decisão — e preencher por padrão foi exatamente o defeito que custou caro antes.

    ⚠️ Clicar NÃO paga. Abre a mesma ação `pagar-boleto`, que é gated e exige OTP.
    """
    codigo = "".join(c for c in (r[5] or "") if c.isdigit())
    if len(codigo) not in (44, 47, 48):
        return None  # sem código de barras não há o que pagar por aqui
    if (r[4] or "").lower() not in ("pendente", "parcial"):
        return None  # já pago/cancelado: o botão convidaria a pagar de novo
    return {
        "actions": [
            {
                "title": f"Pagar boleto — {r[0]}",
                "sub": (
                    "Dinheiro que SAI: 2 etapas + OTP. Confira a conta — Cora é a Patrimonial, "
                    "Inter é a Eletrônica, são CNPJs diferentes. Boleto vencido costuma ser "
                    "recusado no valor de face: nesse caso peça a segunda via com juros."
                ),
                "endpoint": "/api/v1/redesign/action/pagar-boleto",
                "method": "POST",
                "btnLabel": "Pagar",
                "submitLabel": "Preparar e gerar OTP",
                "btnStyle": "primary",
                "gated": True,
                "okMsg": "Ordem preparada. Confira o OTP no e-mail para liberar.",
                "fields": [
                    {"key": "codigo_barras", "label": "Código de barras", "type": "text", "value": codigo},
                    {
                        "key": "valor",
                        "label": "Valor (R$)",
                        "type": "text",
                        "value": f"{float(r[2] or 0):.2f}".replace(".", ","),
                    },
                    {
                        "key": "origem",
                        "label": "Pagar pela conta*",
                        "type": "select",
                        "value": "",
                        "options": [
                            {"value": "", "label": "— escolha —"},
                            {"value": "cora", "label": "Cora (Patrimonial)"},
                            {"value": "inter", "label": "Inter (Eletrônica)"},
                        ],
                    },
                    {"key": "data", "label": "Data do pagamento", "type": "date", "value": ""},
                    {"key": "descricao", "label": "Descrição", "type": "text", "value": str(r[1] or "")[:120]},
                ],
            }
        ]
    }


def t(v: Any, w: int = 500, tc: str = "#334155", ini: str = "") -> dict:
    """Célula de texto. `al` diz o alinhamento: dinheiro à direita, o resto à esquerda.

    Sem isto o CSS alinhava à direita TODA célula de texto único — e aí o nome do
    diarista flutuava para a direita enquanto o cabeçalho "DIARISTA" ficava à esquerda.
    Visto na tela em 23/08/2026, não no builder: coluna de nome esfarrapada, difícil de
    correr o olho. Número em coluna alinha à direita porque as casas decimais batem;
    nome alinha à esquerda porque é assim que se lê.
    """
    txt = str(v) if v is not None else "—"
    dinheiro = txt.startswith("R$") or txt.startswith("-R$")
    return {"isText": True, "v": txt, "w": w, "tc": tc, "ini": ini, "al": "r" if dinheiro else "l"}


def b(v: str, s: str) -> dict:
    p = S.get(s, S["mut"])
    return {"isBadge": True, "v": v, "color": p["color"], "bg": p["bg"]}


def initials(nome: str) -> str:
    parts = [p for p in (nome or "").split() if p]
    if not parts:
        return "--"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


async def _scalar(db: AsyncSession, sql: str) -> Any:
    r = await db.execute(text(sql))
    return r.scalar()


#: Fragmento SQL: quem é funcionário DE VERDADE. Usar em toda contagem de gente.
#:
#: ⭐ 21/09/2026 — o painel do hub dizia «64 colaboradores» e a folha da Portte tem 51. Os 13
#: de diferença são o conjunto de HOMOLOGAÇÃO do app de ponto: 12 pessoas criadas no mesmo
#: segundo (09/09 12:33:26), com 416 batidas criadas no segundo seguinte, holerites sem fonte
#: e contas `@homologacao.conectamais.pro`, mais o `COLABORADOR TESTE HOMOLOGACAO`.
#:
#: Eles JÁ estavam marcados `is_homologacao = true`, e OITO scripts e oráculos já respeitavam
#: a marca (`checar_telefone_funcionario`, `test_oraculo_todos_batem_ponto`, o lembrete de
#: ponto…). Quem não respeitava era a tela. Não se apaga o conjunto — ele serve para testar o
#: app sem tocar em gente real; o que se conserta é quem conta.
#:
#: ⚠️ Medido no mesmo dia: 47 lugares no backend contam `employees WHERE status='ativo'` sem
#: este filtro. Os KPIs de headcount foram corrigidos; o resto é varredura a fazer.
SQL_FUNCIONARIO_REAL = "coalesce(is_homologacao, false) = false"


async def _build_operacional(db: AsyncSession) -> dict:
    postos_ativos = await _scalar(db, "SELECT count(*) FROM posts WHERE status='active'")
    colaboradores = await _scalar(db, f"SELECT count(*) FROM employees WHERE status='ativo' AND {SQL_FUNCIONARIO_REAL}")
    aloc_ativas = await _scalar(db, "SELECT count(*) FROM employee_alocacoes WHERE ativo=true")
    occ_7d = await _scalar(db, "SELECT count(*) FROM occurrences WHERE occurred_at >= now()-interval '7 days'")

    # Cobertura: postos ativos + headcount
    cov = (
        await db.execute(
            text(
                "SELECT p.name, p.current_headcount, p.required_headcount "
                "FROM posts p WHERE p.status='active' ORDER BY p.name LIMIT 8"
            )
        )
    ).fetchall()
    cov_rows = []
    for name, hc, req in cov:
        hc = hc or 0
        req = req or 0
        if req and hc >= req:
            cov_rows.append({"left": name, "right": "100% coberto", **S["ok"]})
        elif hc > 0:
            cov_rows.append({"left": name, "right": f"{hc} em campo", **S["warn"]})
        else:
            cov_rows.append({"left": name, "right": "sem headcount", **S["mut"]})
    if not cov_rows:
        cov_rows = [{"left": "Nenhum posto ativo", "right": "aguardando dado", **S["mut"]}]

    # Últimas ocorrências
    occ = (
        await db.execute(
            text(
                "SELECT o.title, p.name, o.severity, o.occurred_at "
                "FROM occurrences o LEFT JOIN posts p ON p.id=o.post_id "
                "ORDER BY o.occurred_at DESC NULLS LAST LIMIT 5"
            )
        )
    ).fetchall()

    def sev_tone(sev: str) -> tuple:
        s = (sev or "").lower()
        if s in ("critical", "high", "grave", "alta", "critica"):
            return ("Grave", "bad")
        if s in ("medium", "media", "moderada"):
            return ("Média", "warn")
        if s in ("low", "baixa"):
            return ("Baixa", "info")
        return (sev or "Info", "info")

    occ_rows = []
    for title, pname, sev, _ in occ:
        lbl, tone = sev_tone(sev)
        occ_rows.append({"left": f"{title} · {pname or 's/ posto'}", "right": lbl, **S[tone]})
    if not occ_rows:
        occ_rows = [{"left": "Sem ocorrências nos últimos 7 dias", "right": "0", **S["ok"]}]

    visao = {
        "title": "Visão geral",
        "sub": f"{postos_ativos} postos ativos · {colaboradores} colaboradores",
        "cta": "Nova ação",
        "type": "dash",
        "panelGrid": "1.6fr 1fr",
        "kpis": [
            {"v": str(postos_ativos), "l": "Postos ativos", "icon": IC["shield"], "color": "#0F1B3A"},
            {"v": str(colaboradores), "l": "Colaboradores", "icon": IC["users"], "color": "#0F1B3A"},
            {"v": str(aloc_ativas), "l": "Alocações ativas", "icon": IC["cal"], "color": "#0F1B3A"},
            {
                "v": str(occ_7d),
                "l": "Ocorrências (7d)",
                "icon": IC["alert"],
                "color": "#C2410C" if occ_7d else "#0F1B3A",
            },
        ],
        "panels": [
            {"title": "Cobertura dos postos hoje", "rows": cov_rows},
            {"title": "Últimas ocorrências", "rows": occ_rows},
        ],
    }

    # Postos (tabela)
    prows = (
        await db.execute(
            text(
                "SELECT p.name, c.name, p.shift_type, p.current_headcount, p.status, "
                "coalesce(p.address,'—'), coalesce(p.supervisor_name,'—'), coalesce(p.supervisor_phone,'—'), "
                "p.geofence_raio_metros, p.latitude, p.longitude "
                "FROM posts p LEFT JOIN clients c ON c.id=p.client_id "
                "ORDER BY (p.status='active') DESC, p.name"
            )
        )
    ).fetchall()
    postos = {
        "title": "Postos",
        "sub": f"{postos_ativos} postos ativos",
        "cta": "Novo posto",
        "type": "table",
        "searchHint": "Buscar posto ou cliente…",
        "grid": "2fr 1.6fr 1fr 1fr 0.9fr",
        "cols": ["Posto", "Cliente", "Turno", "Vigilantes", "Status"],
        "rows": [
            {
                "cells": [
                    t(name, 600, "#0F1B3A"),
                    t(cli or "—"),
                    t(shift or "—"),
                    t(hc if hc is not None else 0),
                    b("Ativo", "ok") if st == "active" else b("Inativo", "mut"),
                ],
                "edit": {
                    "btnLabel": "Ver posto",
                    "readOnly": True,
                    "title": f"Posto — {name}",
                    "fields": [
                        {"label": "Posto", "value": name, "span": "span 2"},
                        {"label": "Cliente", "value": cli or "—", "span": "span 2"},
                        {"label": "Turno", "value": shift or "—"},
                        {"label": "Vigilantes", "value": str(hc if hc is not None else 0)},
                        {"label": "Status", "value": "Ativo" if st == "active" else "Inativo"},
                        {"label": "Supervisor", "value": sup},
                        {"label": "Telefone supervisor", "value": supf},
                        {"label": "Endereço", "value": addr, "span": "span 2"},
                        {
                            "label": "Coordenadas",
                            "value": (f"{lat}, {lng}" if (lat is not None and lng is not None) else "—"),
                        },
                        {"label": "Raio geofence (m)", "value": (str(geo) if geo is not None else "—")},
                    ],
                },
            }
            for name, cli, shift, hc, st, addr, sup, supf, geo, lat, lng in prows
        ],
    }

    # Colaboradores (tabela)
    erows = (
        await db.execute(
            text(
                "SELECT nome, cargo, posto_atual_nome, status FROM employees "
                "WHERE status='ativo' ORDER BY nome LIMIT 300"
            )
        )
    ).fetchall()
    st_tone = {
        "ativo": ("Ativo", "ok"),
        "afastado_inss": ("Afastado", "warn"),
        "suspenso": ("Suspenso", "warn"),
        "inativo": ("Inativo", "mut"),
        "demitido": ("Demitido", "bad"),
    }
    colaboradores_scr = {
        "title": "Colaboradores",
        "sub": f"{len(erows)} colaboradores ativos",
        "cta": "Novo colaborador",
        "type": "table",
        "searchHint": "Buscar colaborador…",
        "grid": "2fr 1.4fr 1.6fr 0.9fr",
        "cols": ["Colaborador", "Cargo", "Posto", "Status"],
        "rows": [
            {
                "cells": [
                    t(nome, 600, "#0F1B3A", initials(nome)),
                    t(cargo or "—"),
                    t(posto or "—"),
                    b(*st_tone.get(status, (status or "—", "mut"))),
                ]
            }
            for nome, cargo, posto, status in erows
        ],
    }

    # Alocações (tabela)
    arows = (
        await db.execute(
            text(
                # employee_alocacoes.condominio_id aponta para `condominios`, NÃO para `clients`.
                # O join antigo era em clients: 0 das 73 linhas casavam e a coluna
                # "Cliente / Posto" saía "—" para todo mundo — a única informação que
                # uma alocação precisa dar. Medido em 13/09/2026 no banco de produção.
                "SELECT e.nome, cond.nome, al.funcao, al.ativo, al.data_inicio, al.data_fim, al.created_at "
                "FROM employee_alocacoes al LEFT JOIN employees e ON e.id=al.employee_id "
                "LEFT JOIN condominios cond ON cond.id=al.condominio_id "
                "ORDER BY al.ativo DESC, e.nome LIMIT 300"
            )
        )
    ).fetchall()
    alocacoes = {
        "title": "Alocações",
        "sub": f"{aloc_ativas} alocações ativas",
        "cta": "Nova alocação",
        "type": "table",
        "searchHint": "Buscar alocação…",
        "grid": "2fr 1.6fr 1.2fr 0.9fr",
        "cols": ["Colaborador", "Cliente / Posto", "Função", "Status"],
        "rows": [
            {
                "cells": [
                    t(nome or "—", 600, "#0F1B3A", initials(nome or "")),
                    t(cli or "—"),
                    t(funcao or "—"),
                    b("Ativa", "ok") if ativo else b("Encerrada", "mut"),
                ],
                "edit": {
                    "btnLabel": "Ver alocação",
                    "readOnly": True,
                    "title": f"Alocação — {nome or '—'}",
                    "fields": [
                        {"label": "Colaborador", "value": nome or "—", "span": "span 2"},
                        {"label": "Cliente / Posto", "value": cli or "—", "span": "span 2"},
                        {"label": "Função", "value": funcao or "—"},
                        {"label": "Status", "value": "Ativa" if ativo else "Encerrada"},
                        {"label": "Início", "value": _fmtdate(ini)},
                        {"label": "Fim", "value": _fmtdate(fim)},
                        {"label": "Registrada em", "value": _fmtdate(criada)},
                    ],
                },
            }
            for nome, cli, funcao, ativo, ini, fim, criada in arows
        ],
    }

    # Ocorrências (lista)
    olist = (
        await db.execute(
            text(
                "SELECT o.title, p.name, o.severity, o.occurred_at "
                "FROM occurrences o LEFT JOIN posts p ON p.id=o.post_id "
                "ORDER BY o.occurred_at DESC NULLS LAST LIMIT 30"
            )
        )
    ).fetchall()
    dotmap = {"bad": "#EF4444", "warn": "#F5A524", "info": "#2563EB", "ok": "#16A34A"}
    ocorrencias = {
        "title": "Ocorrências",
        "sub": "Registro de eventos nos postos",
        "cta": "Registrar ocorrência",
        "type": "list",
        "items": [
            (
                lambda lbl, tone: {
                    "title": title,  # noqa: B023  # pré-existente: closure em laço, avaliada na hora
                    "meta": f"{pname or 's/ posto'} · {occ_at.strftime('%d/%m %H:%M') if occ_at else 's/ data'}",  # noqa: B023  # pré-existente: closure em laço, avaliada na hora
                    "dot": dotmap.get(tone, "#64748B"),
                    "badge": lbl,
                    **S[tone],
                }
            )(*sev_tone(sev))
            for title, pname, sev, occ_at in olist
        ],
    }
    if not ocorrencias["items"]:
        ocorrencias["items"] = [
            {
                "title": "Sem ocorrências registradas",
                "meta": "aguardando dado",
                "dot": "#16A34A",
                "badge": "OK",
                **S["ok"],
            }
        ]

    # Ocorrência rápida (FORM com ESCRITA real → POST /redesign/action/occurrence)
    post_opts = (await db.execute(text("SELECT id, name FROM posts WHERE status='active' ORDER BY name"))).fetchall()
    ocorrencia_rapida = {
        "title": "Ocorrência rápida",
        "sub": "Registro ágil de evento em campo",
        "cta": "Registrar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/occurrence", "okMsg": "Ocorrência registrada com sucesso"},
        "fields": [
            {
                "key": "post_id",
                "label": "Posto",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione o posto",
                "options": [{"value": str(i), "label": n} for i, n in post_opts],
            },
            {
                "key": "occurrence_type",
                "label": "Tipo",
                "type": "select",
                "span": "span 1",
                "ph": "Tipo",
                "options": [
                    {"value": v, "label": l}
                    for v, l in [
                        ("incidente", "Incidente"),
                        ("nao_conformidade_documental", "Não conformidade"),
                        ("abandono_posto", "Abandono de posto"),
                        ("atraso", "Atraso"),
                        ("falta_epi", "Falta de EPI"),
                        ("uso_celular", "Uso de celular"),
                        ("elogio", "Elogio"),
                        ("outros", "Outros"),
                    ]
                ],
            },
            {
                "key": "severity",
                "label": "Gravidade",
                "type": "select",
                "span": "span 1",
                "ph": "Gravidade",
                "options": [
                    {"value": v, "label": l}
                    for v, l in [
                        ("leve", "Leve"),
                        ("moderada", "Moderada"),
                        ("grave", "Grave"),
                        ("gravissima", "Gravíssima"),
                    ]
                ],
            },
            {"key": "title", "label": "Título", "type": "text", "span": "span 1", "ph": "Resumo curto"},
            {
                "key": "description",
                "label": "Descrição",
                "type": "textarea",
                "span": "span 2",
                "ph": "Descreva o ocorrido…",
            },
        ],
    }

    # Resolver ocorrência (FORM com ESCRITA real → POST /redesign/action/occurrence-resolve)
    open_occ = (
        await db.execute(
            text(
                "SELECT id, code, title FROM occurrences WHERE status='aberta' ORDER BY occurred_at DESC NULLS LAST LIMIT 50"
            )
        )
    ).fetchall()
    resolver_ocorrencia = {
        "title": "Resolver ocorrência",
        "sub": "Encerrar uma ocorrência aberta com a ação tomada",
        "cta": "Resolver",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/occurrence-resolve", "okMsg": "Ocorrência resolvida"},
        "fields": [
            {
                "key": "occurrence_id",
                "label": "Ocorrência aberta*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione a ocorrência",
                "options": [{"value": str(i), "label": f"{c or '—'} · {(ti or '')[:50]}"} for i, c, ti in open_occ],
            },
            {
                "key": "corrective_action",
                "label": "Ação corretiva*",
                "type": "textarea",
                "span": "span 2",
                "ph": "O que foi feito para resolver…",
            },
            {
                "key": "resolution_notes",
                "label": "Observações",
                "type": "textarea",
                "span": "span 2",
                "ph": "Notas adicionais (opcional)…",
            },
        ],
    }

    # Comentar ocorrência (FORM com ESCRITA real → POST /redesign/action/occurrence-comment)
    recent_occ = (
        await db.execute(text("SELECT id, code, title FROM occurrences ORDER BY occurred_at DESC NULLS LAST LIMIT 50"))
    ).fetchall()
    comentar_ocorrencia = {
        "title": "Comentar ocorrência",
        "sub": "Adicionar um comentário a uma ocorrência",
        "cta": "Comentar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/occurrence-comment", "okMsg": "Comentário adicionado"},
        "fields": [
            {
                "key": "occurrence_id",
                "label": "Ocorrência*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione a ocorrência",
                "options": [{"value": str(i), "label": f"{c or '—'} · {(ti or '')[:50]}"} for i, c, ti in recent_occ],
            },
            {
                "key": "content",
                "label": "Comentário*",
                "type": "textarea",
                "span": "span 2",
                "ph": "Escreva o comentário…",
            },
        ],
    }

    # Diaristas — opções (referência) + LEITURA + FORM Lançar diária
    d_diaristas = (await db.execute(text("SELECT id, nome FROM diaria_diaristas WHERE ativo ORDER BY nome"))).fetchall()
    d_postos = (await db.execute(text("SELECT nome FROM diaria_postos WHERE ativo ORDER BY nome"))).fetchall()
    d_funcoes = (await db.execute(text("SELECT nome FROM diaria_funcoes WHERE ativo ORDER BY nome"))).fetchall()
    d_turnos = (await db.execute(text("SELECT nome FROM diaria_turnos WHERE ativo ORDER BY nome"))).fetchall()
    lancar_diaria = {
        "title": "Lançar diária",
        "sub": "Registrar a diária de um diarista (o valor é automático pela função/turno)",
        "cta": "Lançar diária",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/diaria", "okMsg": "Diária lançada"},
        "fields": [
            {
                "key": "diarista_id",
                "label": "Diarista*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione o diarista",
                "options": [{"value": str(i), "label": n} for i, n in d_diaristas],
            },
            {"key": "data", "label": "Data*", "type": "date", "span": "span 1"},
            {
                "key": "posto",
                "label": "Posto*",
                "type": "select",
                "span": "span 1",
                "ph": "Posto",
                "options": [{"value": n, "label": n} for (n,) in d_postos],
            },
            {
                "key": "funcao",
                "label": "Função*",
                "type": "select",
                "span": "span 1",
                "ph": "Função",
                "options": [{"value": n, "label": n} for (n,) in d_funcoes],
            },
            {
                "key": "turno",
                "label": "Turno",
                "type": "select",
                "span": "span 1",
                "ph": "Turno (só p/ Agente de Portaria)",
                "options": [{"value": n, "label": n} for (n,) in d_turnos],
            },
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }
    # Leitura: Diaristas
    drows = (
        await db.execute(
            text(
                "SELECT nome, cpf, coalesce(pix,'—'), coalesce(telefone,'—'), coalesce(email,'—'), coalesce(funcoes::text,'—') FROM diaria_diaristas WHERE ativo ORDER BY nome LIMIT 200"
            )
        )
    ).fetchall()
    # ctaTo: sem ele a ModuleView NÃO desenha o botão da tabela (ModuleView.tsx:706) — o gerente
    # abria a tela, não achava o botão e concluía que a opção não existia no redesign.
    diaristas_scr = {
        "title": "Diaristas",
        "sub": f"{len(drows)} diaristas ativos",
        "cta": "Novo diarista",
        "ctaTo": "cadastrar-diarista",
        "type": "table",
        "searchHint": "Buscar diarista…",
        "grid": "2fr 1.2fr 1.6fr",
        "cols": ["Diarista", "CPF", "PIX"],
        "rows": [
            {
                "cells": [t(n, 600, "#0F1B3A", initials(n)), t(c or "—"), t(px)],
                "edit": {
                    "btnLabel": "Ver diarista",
                    "readOnly": True,
                    "title": f"Diarista — {n}",
                    "fields": [
                        {"label": "Nome", "value": n, "span": "span 2"},
                        {"label": "CPF", "value": c or "—"},
                        {"label": "Chave PIX", "value": px},
                        {"label": "Telefone", "value": tel},
                        {"label": "E-mail", "value": em},
                        {"label": "Funções", "value": fu, "span": "span 2"},
                    ],
                },
            }
            for n, c, px, tel, em, fu in drows
        ],
    }
    # Leitura: Diárias (lançamentos recentes)
    lrows = (
        await db.execute(
            text(
                "SELECT l.data, coalesce(d.nome,'—'), l.funcao, l.posto, l.valor, l.status, "
                "coalesce(l.turno,'—'), coalesce(l.observacao,'—'), l.created_at "
                "FROM diaria_lancamentos l LEFT JOIN diaria_diaristas d ON d.id=l.diarista_id "
                "ORDER BY l.data DESC, l.id DESC LIMIT 200"
            )
        )
    ).fetchall()
    diarias_scr = {
        "title": "Lançamento de diárias",
        "sub": f"{len(lrows)} lançamentos",
        "cta": "Lançar diária",
        "ctaTo": "lancar-diaria",
        "type": "table",
        "searchHint": "Buscar…",
        "grid": "1fr 1.8fr 1.4fr 1.2fr 1fr 0.9fr",
        "cols": ["Data", "Diarista", "Função", "Posto", "Valor", "Status"],
        "rows": [
            {
                "cells": [
                    t(dt.strftime("%d/%m/%Y") if dt else "—"),
                    t(nm, 600, "#0F1B3A"),
                    t(fu or "—"),
                    t(po or "—"),
                    t(brl(vl), 600),
                    b("Lançado", "info") if (stt or "").lower() == "lancado" else b(stt or "—", "mut"),
                ],
                "edit": {
                    "btnLabel": "Ver diária",
                    "readOnly": True,
                    "title": f"Diária — {nm}",
                    "fields": [
                        {"label": "Diarista", "value": nm, "span": "span 2"},
                        {"label": "Data", "value": dt.strftime("%d/%m/%Y") if dt else "—"},
                        {"label": "Status", "value": (stt or "—").capitalize()},
                        {"label": "Função", "value": fu or "—"},
                        {"label": "Posto", "value": po or "—"},
                        {"label": "Turno", "value": tur},
                        {"label": "Valor", "value": brl(vl)},
                        {"label": "Registrada em", "value": _fmtdate(cr)},
                        {"label": "Observação", "value": obs, "span": "span 2"},
                    ],
                },
            }
            for dt, nm, fu, po, vl, stt, tur, obs, cr in lrows
        ],
    }

    cadastrar_diarista = {
        "title": "Cadastrar diarista",
        "sub": "Adicionar um diarista à lista (CPF e PIX obrigatórios — nunca inventar)",
        "cta": "Cadastrar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/diarista", "okMsg": "Diarista cadastrado"},
        "fields": [
            {"key": "nome", "label": "Nome completo*", "type": "text", "span": "span 2", "ph": "Nome do diarista"},
            {"key": "cpf", "label": "CPF*", "type": "text", "span": "span 1", "ph": "000.000.000-00"},
            {
                "key": "pix",
                "label": "Chave PIX*",
                "type": "text",
                "span": "span 1",
                "ph": "CPF, telefone, e-mail ou aleatória",
            },
            {"key": "telefone", "label": "Telefone", "type": "text", "span": "span 1", "ph": "(92) 90000-0000"},
            {"key": "email", "label": "E-mail", "type": "text", "span": "span 1", "ph": "email@exemplo.com"},
        ],
    }

    # Falta → substituto (fluxo ativo, curado). Registrar falta:
    turnos_hoje = (
        await db.execute(
            text(
                "SELECT s.id, coalesce(e.nome,'—'), coalesce(p.name,'—'), s.planned_start_time "
                "FROM shifts s LEFT JOIN employees e ON e.id=s.employee_id LEFT JOIN posts p ON p.id=s.post_id "
                "WHERE s.employee_id IS NOT NULL AND s.is_active "
                "AND s.shift_date BETWEEN (now() AT TIME ZONE 'America/Manaus')::date - 1 AND (now() AT TIME ZONE 'America/Manaus')::date "
                "AND s.status IN ('scheduled','in_progress') ORDER BY p.name, e.nome LIMIT 300"
            )
        )
    ).fetchall()

    def _tno(hhmm):
        try:
            return "Noturno" if hhmm and hhmm.hour >= 15 else "Diurno"
        except Exception:
            return ""

    registrar_falta_scr = {
        "title": "Registrar falta",
        "sub": "Marcar a falta de um turno de hoje/ontem (abre a substituição)",
        "cta": "Registrar falta",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/falta", "okMsg": "Falta registrada"},
        "fields": [
            {
                "key": "shift_id",
                "label": "Turno faltoso*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione o turno de hoje/ontem",
                "options": [{"value": str(i), "label": f"{n} · {po} ({_tno(hh)})"} for i, n, po, hh in turnos_hoje],
            },
            {
                "key": "motivo",
                "label": "Motivo",
                "type": "select",
                "span": "span 1",
                "ph": "Motivo",
                "options": [
                    {"value": v, "label": l}
                    for v, l in [
                        ("falta", "Falta (sem aviso)"),
                        ("atestado", "Atestado"),
                        ("emergencia", "Emergência"),
                        ("pessoal", "Pessoal"),
                        ("outro", "Outro"),
                    ]
                ],
            },
            {"key": "detalhes", "label": "Detalhes", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }
    # Escalar substituto (diarista) numa substituição aberta:
    subs_abertas = (
        await db.execute(
            text(
                "SELECT sub.id, coalesce(e.nome,'—'), coalesce(p.name,'—'), sub.substitution_date "
                "FROM substitutions sub LEFT JOIN employees e ON e.id=sub.original_employee_id LEFT JOIN posts p ON p.id=sub.post_id "
                "WHERE sub.is_active AND sub.status='pending' ORDER BY sub.substitution_date DESC LIMIT 100"
            )
        )
    ).fetchall()
    escalar_substituto_scr = {
        "title": "Escalar substituto (diarista)",
        "sub": "Cobrir uma falta aberta com um diarista (gera a diária automática)",
        "cta": "Escalar diarista",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/substituir-diarista", "okMsg": "Diarista escalado"},
        "fields": [
            {
                "key": "substitution_id",
                "label": "Falta aberta*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione a substituição aberta",
                "options": [
                    {"value": str(i), "label": f"{n} · {po} · {dt.strftime('%d/%m') if dt else '—'}"}
                    for i, n, po, dt in subs_abertas
                ],
            },
            {
                "key": "diarista_id",
                "label": "Diarista*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione o diarista",
                "options": [{"value": str(i), "label": n} for i, n in d_diaristas],
            },
            {
                "key": "funcao",
                "label": "Função",
                "type": "select",
                "span": "span 1",
                "ph": "Auto pelo cargo do faltoso",
                "options": [{"value": n, "label": n} for (n,) in d_funcoes],
            },
            {
                "key": "turno",
                "label": "Turno",
                "type": "select",
                "span": "span 1",
                "ph": "Auto pelo horário",
                "options": [{"value": n, "label": n} for (n,) in d_turnos],
            },
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }

    # Comunicados — leitura real de communication_announcements (menu já existia vazio)
    crows = (
        await db.execute(
            text(
                "SELECT titulo, coalesce(tipo::text,'—'), coalesce(prioridade::text,'—'), data_publicacao, "
                "coalesce(total_destinatarios,0), coalesce(total_visualizacoes,0), coalesce(status::text,'—') "
                "FROM communication_announcements WHERE coalesce(is_active,true)=true ORDER BY data_publicacao DESC NULLS LAST LIMIT 200"
            )
        )
    ).fetchall()
    _prio_tone = {"alta": "bad", "urgente": "bad", "media": "warn", "normal": "info", "baixa": "mut"}
    comunicados_scr = {
        "title": "Comunicados",
        "sub": f"{len(crows)} comunicados",
        "cta": "Novo comunicado",
        "type": "table",
        "searchHint": "Buscar comunicado…",
        "grid": "2.2fr 1fr 0.9fr 1fr 0.9fr 0.7fr 0.9fr",
        "cols": ["Título", "Tipo", "Prioridade", "Publicação", "Destinatários", "Views", "Status"],
        "rows": [
            {
                "cells": [
                    t(ti, 600, "#0F1B3A"),
                    t((tp or "—").replace("_", " ")),
                    b((pr or "—").capitalize(), _prio_tone.get((pr or "").lower(), "info")),
                    t(dp.strftime("%d/%m/%Y") if dp else "—"),
                    t(str(dest)),
                    t(str(views)),
                    # A MESMA coluna guarda 'publicado' (10 linhas antigas) e 'published'
                    # (o que a ação de publicar grava hoje). Medido em 14/09/2026.
                    # Comparar só com 'publicado' pintava de cinza um comunicado publicado.
                    b((st or "—").capitalize(), "ok" if (st or "").lower() in ("publicado", "published") else "mut"),
                ]
            }
            for ti, tp, pr, dp, dest, views, st in crows
        ],
    }

    return {
        "visao": visao,
        "postos": postos,
        "colaboradores": colaboradores_scr,
        "alocacoes": alocacoes,
        "ocorrencias": ocorrencias,
        "ocorrencia-rapida": ocorrencia_rapida,
        "resolver-ocorrencia": resolver_ocorrencia,
        "comentar-ocorrencia": comentar_ocorrencia,
        "lancar-diaria": lancar_diaria,
        "cadastrar-diarista": cadastrar_diarista,
        "registrar-falta": registrar_falta_scr,
        "escalar-substituto": escalar_substituto_scr,
        "diaristas": diaristas_scr,
        "diarias": diarias_scr,
        "comunicados": comunicados_scr,
    }


def brl(v: Any) -> str:
    try:
        v = float(v or 0)
    except Exception:
        v = 0.0
    s = f"{v:,.2f}"
    return "R$ " + s.replace(",", "§").replace(".", ",").replace("§", ".")


_ICF = {
    "money": "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
    "chart": "M3 3v18h18M7 14l3-3 3 3 5-6",
    "users": "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8",
    "hand": "M8 13V5a2 2 0 1 1 4 0v6M12 11V4a2 2 0 1 1 4 0v7M16 11V6a2 2 0 1 1 4 0v8a7 7 0 0 1-7 7h-2a7 7 0 0 1-5-2l-3-3",
}

_PAY_TONE = {
    "pendente": ("Pendente", "warn"),
    "pago": ("Pago", "ok"),
    "paga": ("Paga", "ok"),
    "parcial": ("Parcial", "info"),
    "cancelada": ("Cancelada", "mut"),
    "agendada": ("Agendada", "info"),
}


async def _build_financeiro(db: AsyncSession) -> dict:
    out: dict = {}

    async def safe(key: str, coro):
        try:
            out[key] = await coro
        except Exception:
            await db.rollback()

    async def _dashboard():
        # 12 meses a partir de HOJE e nas DUAS tabelas: o histórico Manaus é ARQUIVO
        # (parou em 29/12/2025) e ancorar nele congelava o faturamento em
        # R$ 3.005.979,80 enquanto a empresa faturava. Real hoje: R$ 3.140.234,54.
        fat = await _scalar(
            db,
            "SELECT coalesce((SELECT sum(valor_servicos) FROM nfse_manaus_historico "
            "                 WHERE data_emissao >= CURRENT_DATE - interval '12 months'), 0) "
            "     + coalesce((SELECT sum(valor_servicos) FROM nfse_emitidas_nacional "
            "                 WHERE data_emissao >= CURRENT_DATE - interval '12 months'), 0)",
        )
        receber = await _scalar(
            db, "SELECT coalesce(sum(net_value),0) FROM receivable_accounts WHERE status IN ('pendente','parcial')"
        )
        pagar = await _scalar(
            db, "SELECT coalesce(sum(net_value),0) FROM payable_accounts WHERE status IN ('pendente','parcial')"
        )
        clientes = await _scalar(db, "SELECT count(*) FROM clients WHERE status='active'")
        pay_top = (
            await db.execute(
                text(
                    "SELECT coalesce(nullif(supplier_name,''), fornecedor_nome, '—'), net_value FROM payable_accounts "
                    "WHERE status IN ('pendente','parcial') ORDER BY net_value DESC LIMIT 6"
                )
            )
        ).fetchall()
        nfse_recent = (
            await db.execute(
                text(
                    "SELECT tomador_nome, valor_servicos FROM nfse_manaus_historico ORDER BY data_emissao DESC LIMIT 6"
                )
            )
        ).fetchall()
        return {
            "title": "Dashboard",
            "sub": "Financeiro — dados reais",
            "cta": "Atualizar",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": brl(fat), "l": "Faturamento (12m NFS-e)", "icon": _ICF["money"], "color": "#0F1B3A"},
                {"v": brl(receber), "l": "A receber (aberto)", "icon": _ICF["chart"], "color": "#16A34A"},
                {"v": brl(pagar), "l": "A pagar (aberto)", "icon": _ICF["money"], "color": "#C2410C"},
                {"v": str(clientes), "l": "Clientes ativos", "icon": _ICF["users"], "color": "#0F1B3A"},
            ],
            "panels": [
                {
                    "title": "Contas a pagar em aberto",
                    "rows": [{"left": n, "right": brl(v), **S["warn"]} for n, v in pay_top]
                    or [{"left": "Nada em aberto", "right": brl(0), **S["ok"]}],
                },
                {
                    "title": "Últimas NFS-e emitidas",
                    "rows": [{"left": nm or "—", "right": brl(v), **S["info"]} for nm, v in nfse_recent]
                    or [{"left": "Sem NFS-e", "right": "—", **S["mut"]}],
                },
            ],
        }

    async def _tbl(title, sub, cta, cols, grid, sql, rowfn, hint="Buscar…", extra=None):
        rows = (await db.execute(text(sql))).fetchall()
        return {
            "title": title,
            "sub": sub,
            "cta": cta,
            "type": "table",
            "searchHint": hint,
            "grid": grid,
            "cols": cols,
            # `extra` acrescenta chaves à LINHA (não à célula) — é assim que a
            # tabela ganha botão de ação sem virar outra tabela. A ModuleView já
            # renderiza `row.actions`; nada muda no frontend.
            "rows": [{"cells": rowfn(r), **((extra(r) if extra else None) or {})} for r in rows],  # nosec B610 - pré-existente: não é Django ORM
        }

    def paytone(st):
        return _PAY_TONE.get((st or "").lower(), ((st or "—"), "mut"))

    await safe("dashboard", _dashboard())
    await safe(
        "contas-pagar",
        _tbl(
            # ⚠️ A PLACA vai aqui, no sub da PRIMEIRA ABA — não no `sub` do grupo. O cabeçalho
            # da tela mostra o título do GRUPO + o sub da ABA ATIVA; pus no grupo primeiro e
            # não apareceu. Quem tem o link antigo (?t=g-pagar) cai aqui e não acha mais os
            # diaristas, que mudaram de grupo — foi o que aconteceu com o Jordan: "não vi
            # porra nenhuma, acho que ficou pior". Mudar o mapa sem deixar placa é pior que
            # não mudar.
            "Contas a pagar",
            "A pagar em aberto e recentes.  ·  Diaristas, VT/VR e folha → menu «Pessoas & Folha»"
            "  ·  Boleto, PIX e impostos → «Contas & Impostos»  ·  Lotes e o que já saiu → "
            "«Ordens & Histórico»",
            "Nova conta",
            ["Fornecedor", "Descrição", "Valor", "Vencimento", "Status"],
            "1.5fr 2fr 1fr 1fr 0.9fr",
            "SELECT coalesce(nullif(supplier_name,''),fornecedor_nome,'—'), coalesce(description,'—'), net_value, due_date, status, "
            "       coalesce(document_number,'') "
            "FROM payable_accounts ORDER BY (status IN ('pendente','parcial')) DESC, due_date NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(r[1]),
                t(brl(r[2]), 600),
                t(r[3].strftime("%d/%m/%Y") if r[3] else "—"),
                b(*paytone(r[4])),
            ],
            extra=_acao_pagar_boleto,
        ),
    )
    await safe(
        "contas-receber",
        _tbl(
            "Contas a receber",
            "A receber em aberto e recentes",
            "Nova cobrança",
            ["Cliente", "Descrição", "Valor", "Vencimento", "Status"],
            "1.5fr 2fr 1fr 1fr 0.9fr",
            "SELECT coalesce(customer_name,'—'), coalesce(description,'—'), net_value, due_date, status "
            "FROM receivable_accounts ORDER BY (status IN ('pendente','parcial')) DESC, due_date NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(r[1]),
                t(brl(r[2]), 600),
                t(r[3].strftime("%d/%m/%Y") if r[3] else "—"),
                b(*paytone(r[4])),
            ],
        ),
    )
    await safe(
        "clientes",
        _tbl(
            "Clientes",
            f"{await _scalar(db, 'SELECT count(*) FROM clients')} clientes",
            "Novo cliente",
            ["Cliente", "Segmento", "MRR", "Status"],
            "2fr 1.4fr 1fr 0.9fr",
            "SELECT name, coalesce(segment::text,'—'), coalesce(mrr,0), status::text FROM clients ORDER BY name LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0])),
                t(r[1]),
                t(brl(r[2]), 600),
                b("Ativo", "ok") if r[3] == "active" else b(r[3] or "—", "mut"),
            ],
        ),
    )
    await safe(
        "fornecedores",
        _tbl(
            "Fornecedores",
            f"{await _scalar(db, 'SELECT count(*) FROM suppliers')} fornecedores",
            "Novo fornecedor",
            ["Fornecedor", "Categoria", "Cidade", "Status"],
            "2fr 1.4fr 1.2fr 0.9fr",
            "SELECT name, coalesce(category,'—'), coalesce(address_city,'—'), status FROM suppliers ORDER BY name LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(r[1]),
                t(r[2]),
                b("Ativo", "ok") if (r[3] or "").lower() in ("active", "ativo") else b(r[3] or "—", "mut"),
            ],
        ),
    )
    await safe(
        "pagamentos-diaristas",
        _tbl(
            "Pagamentos diaristas",
            f"{await _scalar(db, 'SELECT count(*) FROM financial_pagamentos_diaristas')} lançamentos",
            "Novo pagamento",
            ["Beneficiário", "Valor", "Competência", "Status"],
            "2fr 1fr 1.2fr 0.9fr",
            "SELECT coalesce(beneficiario,'—'), valor, coalesce(competencia, to_char(data_referencia,'MM/YYYY')), status "
            "FROM financial_pagamentos_diaristas ORDER BY data_referencia DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(brl(r[1]), 600), t(r[2]), b(*paytone(r[3]))],
        ),
    )
    # Pagamentos Inter — VISIBILIDADE da fila (dinheiro que SAI = SEMPRE gate OTP humano; esta tela NÃO paga).
    _pay_tone = {
        "confirmado": "ok",
        "executado": "ok",
        "preparado": "warn",
        "aguardando_otp": "warn",
        "erro": "bad",
        "cancelado": "mut",
    }
    await safe(
        "inter-pagamentos",
        _tbl(
            "Pagamentos Inter",
            f"{await _scalar(db, 'SELECT count(*) FROM inter_payments')} pagamentos — dinheiro que sai é SEMPRE com gate OTP humano (esta tela só mostra)",
            "—",
            ["Tipo", "Destinatário", "Valor", "Data", "Status", "OTP"],
            "1fr 2fr 1fr 1fr 1fr 0.7fr",
            "SELECT coalesce(payment_type,'—'), "
            "coalesce(destinatario->>'nome_recebedor', destinatario->>'condominio', destinatario->>'chave', left(destinatario->>'codigo_barras',18), '—'), "
            "valor, data_pagamento, coalesce(status::text,'—'), coalesce(approval_otp_used::text,'') "
            "FROM inter_payments ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t((r[0] or "—").upper()),
                t(r[1], 600, "#0F1B3A"),
                t(brl(r[2]) if r[2] is not None else "—", 600),
                t(_fmtdate(r[3])),
                b((r[4] or "—").capitalize(), _pay_tone.get((r[4] or "").lower(), "info")),
                b("OTP ✓", "ok")
                if (r[5] and str(r[5]).lower() not in ("", "false", "nao", "no", "0", "none"))
                else b("—", "mut"),
            ],
        ),
    )
    # Registrar conta a pagar (FORM com ESCRITA real → POST /redesign/action/payable-condicao, F11) — REGISTRO, não pagamento
    out["registrar-conta-pagar"] = {
        "title": "Registrar conta a pagar",
        "sub": "Lançar uma conta a pagar (registro — o pagamento é sempre com OTP)",
        "cta": "Registrar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/payable-condicao", "okMsg": "Conta a pagar registrada"},  # dgx u3
        "fields": [
            {
                "key": "description",
                "label": "Descrição*",
                "type": "text",
                "span": "span 2",
                "ph": "Ex.: Energia — Posto Centro",
            },
            {
                "key": "supplier_name",
                "label": "Fornecedor",
                "type": "text",
                "span": "span 1",
                "ph": "Nome do fornecedor",
            },
            {"key": "valor", "label": "Valor (R$)*", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "due_date", "label": "Vencimento*", "type": "date", "span": "span 1"},
            {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }
    # Registrar conta a receber (ESCRITA real → POST /redesign/action/receivable-condicao, F11) — REGISTRO, não recebimento
    out["registrar-conta-receber"] = {
        "title": "Registrar conta a receber",
        "sub": "Lançar uma conta a receber (registro — não gera boleto/PIX)",
        "cta": "Registrar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/receivable-condicao", "okMsg": "Conta a receber registrada"},  # dgx u3
        "fields": [
            {
                "key": "description",
                "label": "Descrição*",
                "type": "text",
                "span": "span 2",
                "ph": "Ex.: Vigilância — Condomínio Green",
            },
            {
                "key": "customer_name",
                "label": "Cliente/Sacado",
                "type": "text",
                "span": "span 1",
                "ph": "Nome do cliente",
            },
            {"key": "valor", "label": "Valor (R$)*", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "due_date", "label": "Vencimento*", "type": "date", "span": "span 1"},
            {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }
    # Custeio CCT — simulador de encargos (cálculo PURO reusando PricingEngine; nada é gravado)
    out["custeio-cct"] = {
        "title": "Custeio CCT (encargos)",
        "sub": "Provisões e encargos CCT sobre a folha — cálculo, nada é gravado",
        "cta": "Calcular",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/custeio-cct", "okMsg": "Custeio calculado"},
        "fields": [
            {
                "key": "salario_base",
                "label": "Salário base (R$)*",
                "type": "text",
                "span": "span 1",
                "ph": "1.670,00 (piso CCT)",
            },
            {"key": "headcount", "label": "Nº de colaboradores*", "type": "text", "span": "span 1", "ph": "1"},
            {"key": "meses", "label": "Meses do contrato", "type": "text", "span": "span 1", "ph": "12"},
        ],
    }

    return out


async def _build_dp(db: AsyncSession) -> dict:
    out: dict = {}

    async def safe(key: str, coro):
        try:
            out[key] = await coro
        except Exception:
            await db.rollback()

    async def _tbl(title, sub, cta, cols, grid, sql, rowfn, hint="Buscar…"):
        rows = (await db.execute(text(sql))).fetchall()
        return {
            "title": title,
            "sub": sub,
            "cta": cta,
            "type": "table",
            "searchHint": hint,
            "grid": grid,
            "cols": cols,
            "rows": [{"cells": rowfn(r)} for r in rows],
        }

    ic_users = IC["users"]
    ic_money = _ICF["money"]
    ic_cal = IC["cal"]

    async def _visao():
        ativos = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
        # Competência FUTURA fica de fora, mesma regra da tela de Folha. Sem isso o KPI de
        # destaque do módulo pegava 12/2026 (47 holerites de teste, R$ 30.410,64) em vez da
        # folha real fechada — 07/2026, 102 holerites, R$ 165.612,95. Primeiro número que o
        # DP vê ao abrir o módulo; errado por um fator de cinco.
        _ULT_COMP = (
            # sem 13º (payslip_code '13O-…' mora em 11/12 desde 03/08) e sem competência futura
            "SELECT reference_year, reference_month FROM hr_payslips "
            "WHERE payslip_code NOT LIKE '13O-%' AND make_date(reference_year, reference_month, 1) <= date_trunc('month', current_date) "
            "ORDER BY reference_year DESC, reference_month DESC LIMIT 1"
        )
        comp = (await db.execute(text(_ULT_COMP))).fetchone()
        liq = await _scalar(
            db,
            f"SELECT coalesce(sum(net_salary),0) FROM hr_payslips WHERE (reference_year,reference_month)=({_ULT_COMP})",
        )
        # `hr_vacation_requests`, a AUTORITATIVA — as 7 leituras de férias deste arquivo
        # liam `employee_vacation_requests` até 13/08/2026, e ela é CÓPIA, não fila.
        # Medido: os 15 pedidos dela já existem na autoritativa, com o MESMO funcionário, o
        # MESMO período e a MESMA data de criação — foram gravados nos dois lados em
        # paralelo. Ler a cópia mostrava 15 onde há 19, e mostrava ANDREW COSTA VASCONCELOS
        # como `SUBMITTED` quando a decisão registrada na autoritativa foi `REJECTED`.
        # KPI que discorda da decisão do RH é pior que KPI faltando.
        ferias_req = await _scalar(db, "SELECT count(*) FROM hr_vacation_requests")
        admissoes = await _scalar(db, "SELECT count(*) FROM admission_processes")
        comp_lbl = f"{comp[1]:02d}/{comp[0]}" if comp else "—"
        # quadro por status
        st_rows = (
            await db.execute(text("SELECT status, count(*) FROM employees GROUP BY status ORDER BY count(*) DESC"))
        ).fetchall()
        st_tone = {"ativo": "ok", "afastado_inss": "warn", "suspenso": "warn", "inativo": "mut", "demitido": "bad"}
        quadro = [
            {"left": (s or "—").replace("_", " ").capitalize(), "right": str(c), **S[st_tone.get(s, "mut")]}
            for s, c in st_rows
        ]
        # férias por status
        fr_rows = (
            await db.execute(
                text("SELECT status, count(*) FROM hr_vacation_requests GROUP BY status ORDER BY count(*) DESC")
            )
        ).fetchall()
        fer = [
            {"left": (s or "—").replace("_", " ").capitalize(), "right": str(c), **S["info"]} for s, c in fr_rows
        ] or [{"left": "Sem solicitações", "right": "0", **S["mut"]}]
        return {
            "title": "Visão geral",
            "sub": f"{ativos} colaboradores ativos · folha {comp_lbl}",
            "cta": "Nova admissão",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(ativos), "l": "Colaboradores ativos", "icon": ic_users, "color": "#0F1B3A"},
                {"v": brl(liq), "l": f"Folha líquida ({comp_lbl})", "icon": ic_money, "color": "#0F1B3A"},
                {"v": str(ferias_req), "l": "Solicitações de férias", "icon": ic_cal, "color": "#0F1B3A"},
                {"v": str(admissoes), "l": "Admissões em processo", "icon": ic_users, "color": "#0F1B3A"},
            ],
            "panels": [
                {"title": "Quadro por situação", "rows": quadro},
                {"title": "Férias por status", "rows": fer},
            ],
        }

    st_emp = {
        "ativo": ("Ativo", "ok"),
        "afastado_inss": ("Afastado", "warn"),
        "suspenso": ("Suspenso", "warn"),
        "inativo": ("Inativo", "mut"),
        "demitido": ("Demitido", "bad"),
    }
    n_ativos = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
    n_demit = await _scalar(db, "SELECT count(*) FROM employees WHERE status='demitido'")
    n_ferias = await _scalar(db, "SELECT count(*) FROM hr_vacation_requests")
    n_benef = await _scalar(db, "SELECT count(*) FROM employee_benefits")

    await safe("visao", _visao())
    await safe(
        "funcionarios",
        _tbl(
            "Funcionários",
            f"{n_ativos} ativos",
            "Nova admissão",
            ["Colaborador", "Cargo", "Admissão", "Status"],
            "2fr 1.5fr 1fr 0.9fr",
            "SELECT nome, coalesce(cargo,'—'), data_admissao, status::text FROM employees WHERE status='ativo' ORDER BY nome LIMIT 300",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0])),
                t(r[1]),
                t(r[2].strftime("%d/%m/%Y") if r[2] else "—"),
                b(*st_emp.get(r[3], (r[3] or "—", "mut"))),
            ],
        ),
    )
    await safe(
        "folha",
        _tbl(
            "Folha de pagamento",
            "Última competência",
            "Fechar folha",
            ["Colaborador", "Competência", "Salário base", "Líquido", "Status"],
            "2fr 1fr 1fr 1fr 0.9fr",
            "SELECT e.nome, p.reference_month, p.reference_year, p.base_salary, p.net_salary, p.status::text "
            "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id "
            "WHERE (p.reference_year,p.reference_month)=(SELECT reference_year,reference_month FROM hr_payslips WHERE payslip_code NOT LIKE '13O-%' AND make_date(reference_year, reference_month, 1) <= date_trunc('month', current_date) ORDER BY reference_year DESC, reference_month DESC LIMIT 1) "
            "ORDER BY e.nome LIMIT 300",
            lambda r: [
                t(r[0] or "—", 600, "#0F1B3A", initials(r[0] or "")),
                t(f"{(r[1] or 0):02d}/{r[2] or ''}"),
                t(brl(r[3])),
                t(brl(r[4]), 600),
                b("Processada", "ok")
                if (r[5] or "").lower() in ("processed", "processada", "fechada", "paga")
                else b(r[5] or "—", "info"),
            ],
        ),
    )
    # Folha · Rubricas — breakdown de proventos/descontos por rubrica (unnest do JSON earnings/deductions da última competência)
    await safe(
        "folha-rubricas",
        _tbl(
            "Folha · Rubricas",
            "Proventos e descontos linha-a-linha (última competência)",
            "—",
            ["Colaborador", "Competência", "Rubrica", "Tipo", "Valor"],
            "1.8fr 1fr 2fr 0.9fr 1fr",
            "SELECT e.nome, p.reference_month, p.reference_year, elem->>'description', 'Provento', (elem->>'value')::numeric "
            "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id "
            "CROSS JOIN LATERAL jsonb_array_elements(p.earnings::jsonb) elem "
            "WHERE p.earnings IS NOT NULL AND (p.reference_year,p.reference_month)=(SELECT reference_year,reference_month FROM hr_payslips WHERE payslip_code NOT LIKE '13O-%' AND make_date(reference_year, reference_month, 1) <= date_trunc('month', current_date) ORDER BY reference_year DESC, reference_month DESC LIMIT 1) "
            "UNION ALL "
            "SELECT e.nome, p.reference_month, p.reference_year, elem->>'description', 'Desconto', (elem->>'value')::numeric "
            "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id "
            "CROSS JOIN LATERAL jsonb_array_elements(p.deductions::jsonb) elem "
            "WHERE p.deductions IS NOT NULL AND (p.reference_year,p.reference_month)=(SELECT reference_year,reference_month FROM hr_payslips WHERE payslip_code NOT LIKE '13O-%' AND make_date(reference_year, reference_month, 1) <= date_trunc('month', current_date) ORDER BY reference_year DESC, reference_month DESC LIMIT 1) "
            "ORDER BY 1, 5 DESC LIMIT 400",
            lambda r: [
                t(r[0] or "—", 600, "#0F1B3A", initials(r[0] or "")),
                t(f"{(r[1] or 0):02d}/{r[2] or ''}"),
                t(r[3] or "—"),
                b(r[4], "ok" if r[4] == "Provento" else "bad"),
                t(brl(r[5]) if r[5] is not None else "—", 600),
            ],
        ),
    )
    # Benefícios CCT — configuração legal dos benefícios obrigatórios/opcionais (cct_beneficios)
    await safe(
        "beneficios-cct",
        _tbl(
            "Benefícios CCT",
            "Benefícios da convenção — valores e obrigatoriedade (CCT SINDECOMPRESTS)",
            "—",
            ["Benefício", "Valor mínimo", "Valor empresa", "Desconto máx.", "Obrigatoriedade"],
            "2fr 1.1fr 1.1fr 1.1fr 1.1fr",
            "SELECT tipo_beneficio, valor_minimo, valor_empresa, desconto_maximo_percentual, coalesce(obrigatorio,false) "
            "FROM cct_beneficios WHERE coalesce(is_active,true)=true ORDER BY obrigatorio DESC NULLS LAST, tipo_beneficio LIMIT 60",
            lambda r: [
                t((r[0] or "—").replace("_", " ").capitalize(), 600, "#0F1B3A"),
                t(brl(r[1]) if r[1] is not None else "—"),
                t(brl(r[2]) if r[2] is not None else "—"),
                t(f"{float(r[3]):.0f}%" if r[3] is not None else "—"),
                b("Obrigatório", "bad") if r[4] else b("Opcional", "mut"),
            ],
        ),
    )
    await safe(
        "ferias",
        _tbl(
            "Férias",
            f"{n_ferias} solicitações",
            "Solicitar férias",
            ["Colaborador", "Início", "Fim", "Dias", "Status"],
            "2fr 1fr 1fr 0.7fr 0.9fr",
            "SELECT e.nome, v.start_date, v.end_date, v.days_requested, v.status::text "
            "FROM hr_vacation_requests v LEFT JOIN employees e ON e.id=v.employee_id ORDER BY v.start_date DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0] or "—", 600, "#0F1B3A", initials(r[0] or "")),
                t(r[1].strftime("%d/%m/%Y") if r[1] else "—"),
                t(r[2].strftime("%d/%m/%Y") if r[2] else "—"),
                t(r[3] if r[3] is not None else "—"),
                b(r[4] or "—", "info"),
            ],
        ),
    )
    await safe(
        "beneficios",
        _tbl(
            "Benefícios",
            f"{n_benef} benefícios",
            "Novo benefício",
            ["Colaborador", "Tipo", "Fornecedor", "Status"],
            "2fr 1.2fr 1.4fr 0.9fr",
            "SELECT e.nome, coalesce(b.type::text,'—'), coalesce(b.provider,'—'), b.status::text "
            "FROM employee_benefits b LEFT JOIN employees e ON e.id=b.employee_id ORDER BY e.nome LIMIT 200",
            lambda r: [
                t(r[0] or "—", 600, "#0F1B3A", initials(r[0] or "")),
                t(r[1]),
                t(r[2]),
                b("Ativo", "ok") if (r[3] or "").lower() in ("active", "ativo") else b(r[3] or "—", "mut"),
            ],
        ),
    )
    await safe(
        "rescisao",
        _tbl(
            "Rescisão",
            f"{n_demit} desligados",
            "Nova rescisão",
            ["Colaborador", "Cargo", "Desligamento", "Motivo"],
            "2fr 1.4fr 1fr 1.4fr",
            "SELECT nome, coalesce(cargo,'—'), coalesce(data_demissao,data_desligamento), coalesce(motivo_desligamento,motivo_inatividade,'—') "
            "FROM employees WHERE status='demitido' ORDER BY coalesce(data_demissao,data_desligamento) DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0])),
                t(r[1]),
                t(r[2].strftime("%d/%m/%Y") if r[2] else "—"),
                t(r[3]),
            ],
        ),
    )
    # Registrar reembolso (ESCRITA real → POST /redesign/action/reembolso) — nasce em RASCUNHO, sem mover dinheiro
    _cat_lbl = {
        "transporte": "Transporte",
        "alimentacao": "Alimentação",
        "hospedagem": "Hospedagem",
        "material": "Material",
        "comunicacao": "Comunicação",
        "viagem": "Viagem",
        "estacionamento": "Estacionamento",
        "pedagio": "Pedágio",
        "saude": "Saúde",
        "cursos": "Cursos",
        "outros": "Outros",
    }
    out["registrar-reembolso"] = {
        "title": "Registrar reembolso",
        "sub": "Solicitar reembolso de despesa (rascunho — aprovação e pagamento seguem o fluxo)",
        "cta": "Registrar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/reembolso", "okMsg": "Reembolso registrado"},
        "fields": [
            {
                "key": "title",
                "label": "Título/motivo*",
                "type": "text",
                "span": "span 2",
                "ph": "Ex.: Táxi para visita ao posto Centro",
            },
            {
                "key": "category_type",
                "label": "Categoria*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione a categoria",
                "options": [{"value": k, "label": v} for k, v in _cat_lbl.items()],
            },
            {"key": "valor", "label": "Valor (R$)*", "type": "text", "span": "span 1", "ph": "0,00"},
            {
                "key": "merchant",
                "label": "Estabelecimento",
                "type": "text",
                "span": "span 1",
                "ph": "Onde foi a despesa",
            },
            {"key": "expense_date", "label": "Data da despesa*", "type": "date", "span": "span 1"},
            {
                "key": "description",
                "label": "Detalhe da despesa",
                "type": "textarea",
                "span": "span 2",
                "ph": "Opcional…",
            },
        ],
    }
    # Solicitar férias (ESCRITA real → POST /redesign/action/vacation-request) — sobre SALDO REAL, nasce RASCUNHO
    try:
        fer_rows = (
            await db.execute(
                text(
                    "SELECT p.employee_id, e.nome, sum(p.days_remaining) d FROM employee_vacation_periods p "
                    "JOIN employees e ON e.id=p.employee_id "
                    "WHERE p.is_expired=false AND p.is_fully_used=false "
                    "GROUP BY 1,2 HAVING sum(p.days_remaining)>=5 ORDER BY e.nome LIMIT 400"
                )
            )
        ).fetchall()
        fer_opts = [{"value": str(eid), "label": f"{nm} · saldo {int(d)}d"} for eid, nm, d in fer_rows]
    except Exception:
        await db.rollback()
        fer_opts = []
    out["solicitar-ferias"] = {
        "title": "Solicitar férias",
        "sub": "Pedir férias sobre o saldo disponível (rascunho — segue para aprovação)",
        "cta": "Solicitar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/vacation-request", "okMsg": "Férias solicitadas"},
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador (com saldo)*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione o colaborador",
                "options": fer_opts,
            },
            {
                "key": "vacation_type",
                "label": "Tipo",
                "type": "select",
                "span": "span 1",
                "ph": "Tipo",
                "options": [
                    {"value": v, "label": l}
                    for v, l in [
                        ("full", "Integral"),
                        ("split", "Fracionada"),
                        ("sell", "Com venda (abono)"),
                        ("collective", "Coletiva"),
                    ]
                ],
            },
            {"key": "start_date", "label": "Início*", "type": "date", "span": "span 1"},
            {"key": "end_date", "label": "Fim*", "type": "date", "span": "span 1"},
            {
                "key": "employee_notes",
                "label": "Observações",
                "type": "textarea",
                "span": "span 2",
                "ph": "Opcional… (5 a 30 dias corridos)",
            },
        ],
    }
    # Calcular rescisão (calculadora CLT — cálculo PURO; não gera rescisão nem transmite/paga)
    try:
        _resc_rows = (
            await db.execute(
                text(
                    "SELECT id, nome FROM employees WHERE status='ativo' AND salario_base IS NOT NULL AND data_admissao IS NOT NULL ORDER BY nome LIMIT 400"
                )
            )
        ).fetchall()
        _resc_opts = [{"value": str(eid), "label": nm} for eid, nm in _resc_rows]
    except Exception:
        await db.rollback()
        _resc_opts = []
    out["calcular-rescisao"] = {
        "title": "Calcular rescisão (CLT)",
        "sub": "Calculadora de verbas rescisórias — cálculo, NÃO gera rescisão nem transmite/paga",
        "cta": "Calcular",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/rescisao-calc", "okMsg": "Rescisão calculada"},
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione o colaborador",
                "options": _resc_opts,
            },
            {
                "key": "tipo_rescisao",
                "label": "Motivo*",
                "type": "select",
                "span": "span 1",
                "ph": "Motivo",
                "options": [
                    {"value": v, "label": l}
                    for v, l in [
                        ("sem_justa_causa", "Sem justa causa"),
                        ("pedido_demissao", "Pedido de demissão"),
                        ("acordo", "Acordo (art. 484-A)"),
                        ("justa_causa", "Justa causa"),
                    ]
                ],
            },
            {"key": "data_desligamento", "label": "Data de desligamento*", "type": "date", "span": "span 1"},
            {
                "key": "dias_trabalhados_mes",
                "label": "Dias trabalhados no mês",
                "type": "text",
                "span": "span 1",
                "ph": "0",
            },
            {
                "key": "ferias_vencidas_dias",
                "label": "Dias de férias vencidas",
                "type": "text",
                "span": "span 1",
                "ph": "0",
            },
            {
                "key": "saldo_fgts",
                "label": "Saldo FGTS (R$)",
                "type": "text",
                "span": "span 1",
                "ph": "0,00 (p/ multa 40%)",
            },
        ],
    }
    # Calcular férias (calculadora CLT — cálculo PURO; não solicita/agenda/paga férias)
    out["calcular-ferias"] = {
        "title": "Calcular férias (CLT)",
        "sub": "Calculadora de férias + 1/3 + abono — cálculo, NÃO solicita/paga férias",
        "cta": "Calcular",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/ferias-calc", "okMsg": "Férias calculadas"},
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione o colaborador",
                "options": _resc_opts,
            },
            {"key": "dias_gozo", "label": "Dias de gozo", "type": "text", "span": "span 1", "ph": "30"},
            {
                "key": "dias_abono",
                "label": "Dias de abono (venda, máx 10)",
                "type": "text",
                "span": "span 1",
                "ph": "0",
            },
        ],
    }

    # Saldo de férias — leitura real dos períodos aquisitivos (employee_vacation_periods)
    def _ferstatus(r):
        if r[8]:  # is_expired
            return b("Vencido", "bad")
        if r[9]:  # is_fully_used
            return b("Gozado", "ok")
        if (r[6] or 0) > 0:
            return b(f"{int(r[6])}d disponíveis", "warn")
        return b("Em curso", "info")

    await safe(
        "saldo-ferias",
        _tbl(
            "Saldo de férias",
            f"{await _scalar(db, 'SELECT count(*) FROM employee_vacation_periods')} períodos aquisitivos",
            "—",
            ["Colaborador", "Período aquisitivo", "Direito", "Gozados", "Vendidos", "Saldo", "Vence em", "Status"],
            "1.6fr 1.4fr 0.7fr 0.7fr 0.7fr 0.7fr 0.9fr 1fr",
            "SELECT e.nome, p.start_date, p.end_date, p.total_days_entitled, p.days_used, p.days_sold, "
            "p.days_remaining, p.expires_at, p.is_expired, p.is_fully_used "
            "FROM employee_vacation_periods p JOIN employees e ON e.id = p.employee_id "
            "ORDER BY p.expires_at ASC NULLS LAST, e.nome LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(f"{_fmtdate(r[1])} – {_fmtdate(r[2])}"),
                t(f"{int(r[3] or 0)}d"),
                t(f"{int(r[4] or 0)}d"),
                t(f"{int(r[5] or 0)}d"),
                t(f"{int(r[6] or 0)}d", 600, "#0F1B3A"),
                t(_fmtdate(r[7])),
                _ferstatus(r),
            ],
        ),
    )

    return out


def _helpers(db: AsyncSession):
    out: dict = {}

    async def safe(key: str, coro):
        try:
            out[key] = await coro
        except Exception:
            await db.rollback()

    async def tbl(
        title, sub, cta, cols, grid, sql, rowfn, hint="Buscar…", docsfn=None, editfn=None, actionsfn=None, filtrofn=None
    ):
        # docsfn(r) → docs por-LINHA. editfn(r) → dict de EDIÇÃO por-linha ({endpoint, method,
        # fields:[{key,label,type,value,options}]}) → o FormScreen inline pré-preenche e faz PATCH.
        # Ambos opcionais e retrocompatíveis (telas sem eles não mudam).
        rows = (await db.execute(text(sql))).fetchall()

        def _mkrow(r):
            row = {"cells": rowfn(r)}
            # `filtro` = valor do seletor do topo SEM precisar ser coluna visível. Antes o
            # filtro lia uma célula (filterCol), o que obrigava a Competência a ocupar uma
            # coluna repetindo o mesmo valor em todas as linhas — medido: 1 valor distinto em
            # 102 linhas, espremendo as colunas que de fato variam.
            if filtrofn:
                _f = filtrofn(r)
                # DICT = vários filtros na mesma tela (14/09/2026): cada chave vira um
                # dropdown próprio e eles combinam com E — "setembro E Ideal Flores", que é
                # como se trabalha ponto. Valor simples segue no seletor único de sempre;
                # telas antigas não mudam.
                if isinstance(_f, dict):
                    row["filtros"] = _f
                else:
                    row["filtro"] = _f
            if docsfn:
                ds = docsfn(r)
                if ds:
                    row["docs"] = ds
            if editfn:
                e = editfn(r)
                if e:
                    row["edit"] = e
            if actionsfn:
                acts = [a for a in (actionsfn(r) or []) if a]
                if acts:
                    row["actions"] = acts
            return row

        _linhas = [_mkrow(r) for r in rows]
        _tela = {
            "title": title,
            "sub": sub,
            "cta": cta,
            "type": "table",
            "searchHint": hint,
            "grid": grid,
            "cols": cols,
            "rows": _linhas,
        }
        _dedup_campos(_tela)
        return _tela

    return out, safe, tbl


def _dedup_recursivo(screens: dict) -> None:
    """Passa o dedup por TODA tela do módulo, inclusive as que viraram aba de grupo."""

    def _andar(no):
        if isinstance(no, dict):
            if no.get("type") == "table" and isinstance(no.get("rows"), list):
                _dedup_campos(no)
            for v in no.values():
                _andar(v)
        elif isinstance(no, list):
            for v in no:
                _andar(v)

    _andar(screens)


def _dedup_campos(tela: dict) -> None:
    """Manda o FORMULÁRIO uma vez por tela, não uma vez por linha.

    Medido em 15/09/2026, quando o Jordan disse que o sistema estava pesado. O módulo DP
    entregava 7,8 MB por carregamento — e 2,6 MB (33%) eram a lista de `fields` dos
    formulários de linha, REPETIDA. O formulário de «Ajustar ponto», com as mesmas quatro
    opções de tipo de batida, vinha 2.000 vezes na mesma resposta; o segundo mais repetido,
    1.466 vezes. Uma tela só (o Ponto) era metade do módulo.

    Nada muda para quem monta a tela: `editfn`/`actionsfn` continuam devolvendo `fields`
    normalmente. Aqui, no fim, blocos com a MESMA lista passam a apontar para uma cópia
    única em `tela["campos"]` via `fieldsRef`. O front resolve a referência; bloco sem
    referência (tela antiga, campo com valor por linha) segue como está.

    Só deduplica o que REPETE: lista que aparece uma vez fica onde está, porque trocá-la
    por referência gastaria mais bytes do que economiza.
    """
    import hashlib
    import json as _json

    linhas = tela.get("rows") or []
    if len(linhas) < 3:  # tela pequena não paga o custo da indireção
        return

    def _blocos(linha: dict):
        if isinstance(linha.get("edit"), dict):
            yield linha["edit"]
        for a in linha.get("actions") or []:
            if isinstance(a, dict):
                yield a

    contagem: dict[str, int] = {}
    chaves: dict[int, str] = {}
    for linha in linhas:
        for bloco in _blocos(linha):
            campos = bloco.get("fields")
            if not campos:
                continue
            bruto = _json.dumps(campos, sort_keys=True, ensure_ascii=False)
            h = hashlib.md5(bruto.encode()).hexdigest()[:12]  # noqa: S324  # nosec B324 - md5 de CACHE, não de segurança
            contagem[h] = contagem.get(h, 0) + 1
            chaves[id(bloco)] = h

    repetidos = {h for h, n in contagem.items() if n >= 3}
    if not repetidos:
        return

    catalogo: dict[str, list] = {}
    for linha in linhas:
        for bloco in _blocos(linha):
            h = chaves.get(id(bloco))
            if h in repetidos:
                catalogo.setdefault(h, bloco["fields"])
                bloco["fieldsRef"] = h
                bloco.pop("fields", None)
    if catalogo:
        tela["campos"] = catalogo


def doc(label, url=None, fmt="pdf", mode="blob", filename=None, gate=None, disabled=False, motivo=None):
    """Fundação de documentos do REDESIGN — monta o dict de um documento clicável (abrir HTML +
    baixar PDF/formato) que o frontend (DocButtons) renderiza. Usar em scr["docs"] (nível tela)
    e em docsfn de tbl (nível linha).

    - label: texto do botão · url: rota EXATA do backend (copiar, não adivinhar) · fmt: pdf/html/
      xml/txt/xlsx/csv/zip · mode: 'blob' (arquivo direto, default) ou 'json' ({content,filename}).
    - disabled=True + motivo: para stub/placeholder/documento-sem-transmissão-real (botão honesto
      desabilitado, NUNCA um botão que abre lixo). gate: informativo (o gate REAL é no endpoint).
    """
    d = {"label": label, "fmt": fmt, "mode": mode}
    if url:
        d["url"] = url
    if filename:
        d["filename"] = filename
    if gate:
        d["gate"] = gate
    if disabled:
        d["disabled"] = True
        d["motivo"] = motivo or "Documento indisponível"
    return d


def grp(title, sub, tabs):
    """Tela-GRUPO (type=tabs) da fundação de navegação (F0 financeiro). tabs=[(id, label,
    screen_dict)]; telas None (não montadas nesta base) são omitidas — nunca aba vazia fabricada."""
    return {
        "title": title,
        "sub": sub,
        "type": "tabs",
        "tabs": [{"id": i, "label": l, "screen": s} for i, l, s in tabs if s],
    }


def moved(group_id, tab_id):
    """Stub de redirecionamento p/ deep-link antigo (?t=<id-antigo>). O ModuleView resolve
    para o grupo+aba novos. Mantém zero-regressão de links SEM duplicar payload."""
    return {"type": "redirect", "groupRef": {"t": group_id, "tab": tab_id}}


def _ver_todas_rec(screens: dict) -> None:
    """Clique-na-linha 'Ver' (modal read-only com os campos da linha) em TODA tabela do
    redesign onde ainda NÃO há ver/editar/ação. Recorre nos grupos (type=tabs). Universal e
    sem escrita — aplicado no dispatcher a TODOS os módulos (mata o 'clico e não abre nada').
    Ficha rica/edição por tabela continua sendo feita por cima disto (aquelas já têm edit → puladas)."""

    def _apply(scr):
        if not isinstance(scr, dict):
            return
        ty = scr.get("type")
        if ty == "tabs":
            for tab in scr.get("tabs") or []:
                _apply((tab or {}).get("screen"))
            return
        if ty != "table":
            return
        cols = scr.get("cols", []) or []
        titulo = scr.get("title", "Detalhe")
        for row in scr.get("rows") or []:
            if not isinstance(row, dict):
                continue
            # Pular quando a linha JÁ tem como ser vista: uma ação "Ver", ou um `edit` que é
            # de fato ver/editar o registro (ficha rica). Um `edit` cujo rótulo é AÇÃO DE
            # DOMÍNIO ("Concluir", "Regenerar link", "Aprovar") não mostra a linha — ele faz
            # outra coisa — e tratá-lo como visualização deixava a linha sem nenhum "Ver".
            # Foi o que aconteceu na Admissão: a linha viva tinha Concluir/Editar/Excluir e
            # nenhum Ver, enquanto as canceladas (sem ação) tinham.
            # o default "Editar" só vale quando EXISTE um edit — sem esta guarda, linha
            # nenhuma (que é a maioria) caía no default e era pulada, e as tabelas perdiam
            # o "Ver" que já tinham. Pego ao conferir Prestadores PJ, não pela Admissão.
            _e = row.get("edit")
            if _e and (_e.get("btnLabel") or "Editar").strip().lower() in (
                "ver",
                "editar",
                "detalhe",
                "detalhes",
                "abrir",
            ):
                continue
            # startswith e não igualdade: linhas com "Ver reembolso"/"Ver turno"/"Ver ronda" já
            # abrem o registro — somar um "Ver" genérico ao lado seria só ruído.
            if any(
                ((a or {}).get("btnLabel") or "").strip().lower().startswith("ver") for a in (row.get("actions") or [])
            ):
                continue
            # O "Ver" mostra A PRÓPRIA LINHA: rótulo = cabeçalho da coluna, valor = célula.
            # Materializar isso em `fields` DUPLICAVA a linha inteira dentro dela mesma —
            # medido em 15/09/2026: 434 bytes por linha, 2.000 linhas, ~870 KB só nessa tela,
            # e o mesmo em toda tabela do sistema. Agora vai um MARCADOR e o front monta o
            # detalhe a partir de `cols` + `cells`, que já estão na resposta.
            if cols and (row.get("cells") or []):
                row.setdefault("actions", []).insert(
                    0, {"btnLabel": "Ver", "readOnly": True, "title": f"{titulo} — detalhe", "verDaLinha": True}
                )

    for scr in list(screens.values()):
        _apply(scr)


# Drill dos dashboards por MÓDULO (KPI → tela). Match por startswith (robusto a rótulos com
# data dinâmica, ex.: "Folha líquida (12/2026)"). Financeiro (50 KPIs, muito editado) fica
# p/ a sessão dele. Só drilla p/ tela que EXISTE no módulo (honesto).
_MOD_KPI_DRILL = {
    "departamento-pessoal": {
        "Colaboradores ativos": "funcionarios",
        "Admissões": "admissao",
        "Solicitações de férias": "ferias",
        "Folha líquida": "folha",
    },
    "fiscal": {"Certidões": "certidoes", "NFS-e Emitidas": "nfse", "Faturamento": "nfse"},
    "crm": {"Leads": "leads", "Propostas": "propostas", "Contratos": "contratos", "Comissões": "comissoes"},
}


def _aplicar_drill_mod(screens: dict, slug: str) -> None:
    """Torna clicável os KPIs dos dashboards do módulo `slug` (seta `to` por startswith).
    Universal via dispatcher; só p/ telas que existem. Recorre em grupos."""
    mp = _MOD_KPI_DRILL.get(slug)
    if not mp:
        return
    ids = set()

    def _collect(sc):
        if not isinstance(sc, dict):
            return
        if sc.get("type") == "tabs":
            for tb in sc.get("tabs") or []:
                if (tb or {}).get("id"):
                    ids.add(tb["id"])
                _collect((tb or {}).get("screen"))

    for k, sc in screens.items():
        ids.add(k)
        _collect(sc)

    def _apply(sc):
        if not isinstance(sc, dict):
            return
        if sc.get("type") == "tabs":
            for tb in sc.get("tabs") or []:
                _apply((tb or {}).get("screen"))
        elif sc.get("type") == "dash":
            for kpi in sc.get("kpis") or []:
                lbl = kpi.get("l") or ""
                if kpi.get("to"):
                    continue
                for key, tgt in mp.items():
                    if lbl.startswith(key) and tgt in ids:
                        kpi["to"] = tgt
                        break

    for sc in screens.values():
        _apply(sc)


def _fmtdate(d, fmt="%d/%m/%Y"):
    return d.strftime(fmt) if d else "—"


async def _build_crm(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    # ⚠️ 18/09/2026 — O KPI TEM DE CONTAR O QUE A TELA QUE ELE ABRE MOSTRA.
    # O de Leads dizia **304** e a tela de leads listava **13**: ele somava os apagados
    # (`is_active = false`) e ela não. Clicar no número levava a outro mundo, e ninguém
    # denunciava — o oráculo de KPIs usava `count(*)` e CONCORDAVA com o 304, enquanto
    # acusava o de Propostas, que era o único certo (12 ativas de 37).
    # Medido no dia: leads 304 → 13 · propostas 37 → 12 · contratos 20 = 20.
    n_leads = await _scalar(db, "SELECT count(*) FROM leads WHERE coalesce(is_active,true)")
    n_prop = await _scalar(db, "SELECT count(*) FROM proposals WHERE coalesce(is_active,true)")
    n_contr = await _scalar(db, "SELECT count(*) FROM contracts WHERE coalesce(is_active,true)")
    com_pend = await _scalar(
        db,
        "SELECT coalesce(sum(final_commission),0) FROM commissions WHERE status::text NOT IN ('paid','pago','cancelled','cancelada')",
    )

    async def _dash():
        lead_st = (
            await db.execute(
                text(
                    "SELECT status::text, count(*) FROM leads WHERE coalesce(is_active,true) "
                    "GROUP BY status ORDER BY count(*) DESC"
                )
            )
        ).fetchall()
        prop_st = (
            await db.execute(
                text(
                    "SELECT status::text, count(*) FROM proposals WHERE coalesce(is_active,true) GROUP BY status ORDER BY count(*) DESC"
                )
            )
        ).fetchall()
        return {
            "title": "Dashboard",
            "sub": "Comercial — dados reais",
            "cta": "Novo lead",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_leads), "l": "Leads", "icon": _ICF["users"], "color": "#0F1B3A"},
                {"v": str(n_prop), "l": "Propostas", "icon": _ICF["hand"], "color": "#0F1B3A"},
                {"v": str(n_contr), "l": "Contratos", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": brl(com_pend), "l": "Comissões a pagar", "icon": _ICF["money"], "color": "#C2410C"},
            ],
            "panels": [
                {
                    "title": "Leads por status",
                    "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in lead_st]
                    or [{"left": "Sem leads", "right": "0", **S["mut"]}],
                },
                {
                    "title": "Propostas por status",
                    "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["warn"]} for s, c in prop_st]
                    or [{"left": "Sem propostas", "right": "0", **S["mut"]}],
                },
            ],
        }

    await safe("dashboard", _dash())
    await safe(
        "leads",
        tbl(
            "Leads",
            f"{n_leads} leads",
            "Novo lead",
            ["Lead", "Empresa", "Valor estimado", "Status"],
            "2fr 1.6fr 1fr 0.9fr",
            "SELECT name, coalesce(company,'—'), coalesce(expected_value,0), status::text FROM leads ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0])),
                t(r[1]),
                t(brl(r[2])),
                b("Qualificado", "ok")
                if r[3] == "qualified"
                else b("Novo" if r[3] == "new" else (r[3] or "—"), "info"),
            ],
        ),
    )
    await safe(
        "propostas",
        tbl(
            "Propostas",
            f"{n_prop} propostas",
            "Nova proposta",
            ["Número", "Cliente", "Título", "Valor", "Status"],
            "1fr 1.6fr 1.6fr 1fr 0.9fr",
            "SELECT coalesce(number,'—'), coalesce(client_name,'—'), coalesce(title,'—'), coalesce(total,subtotal,0), status::text FROM proposals WHERE coalesce(is_active,true) ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1]), t(r[2]), t(brl(r[3]), 600), b(r[4] or "—", "info")],
        ),
    )
    # Contratos: além do cadastro, o INSTRUMENTO e o estado da assinatura. Até 23/08 esta
    # tela mostrava só Contrato/Cliente/Mensal/Total/Status — para baixar o PDF ou abrir
    # assinatura era preciso trocar de módulo (jurídico) ou pedir para o agente.
    # A coluna Assinatura lê sig_signature_requests: é o banco dizendo quem já firmou,
    # nunca uma suposição a partir do status do contrato.
    await safe(
        "contratos",
        tbl(
            "Contratos",
            f"{n_contr} contratos · baixe o instrumento pelo modelo e acompanhe a assinatura",
            "Novo contrato",
            ["Contrato", "Cliente", "Serviço", "Mensal", "Status", "Assinatura"],
            "1.1fr 1.5fr 1fr 0.9fr 0.8fr 1.1fr",
            "SELECT coalesce(ct.contract_number,'—'), coalesce(cl.name, ct.name, '—'), "
            "coalesce(ct.tipo_servico::text,'—'), coalesce(ct.monthly_value,0), ct.status::text, "
            "(SELECT count(*) FROM sig_signature_requests s WHERE s.reference_code = ct.contract_number), "
            "(SELECT count(*) FROM sig_signature_requests s WHERE s.reference_code = ct.contract_number AND s.signed_at IS NOT NULL), "
            "ct.template_id::text "
            "FROM contracts ct LEFT JOIN clients cl ON cl.id=ct.client_id ORDER BY ct.start_date DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—")[:32]),
                t((r[2] or "—").replace("_", " ")),
                t(brl(r[3])),
                b("Ativo", "ok") if (r[4] or "").lower() in ("active", "ativo", "vigente") else b(r[4] or "—", "mut"),
                (
                    b("Não aberta", "mut")
                    if not r[5]
                    else b(f"{r[6]}/{r[5]} assinada(s)", "ok" if r[6] and r[6] == r[5] else "warn")
                ),
            ],
            # botão só em quem TEM modelo: oferecer download que devolve 422 é pior que não oferecer
            docsfn=lambda r: (
                [doc("Contrato completo (PDF)", f"/api/v1/crm/contracts/{r[0]}/pdf-modelo", fmt="pdf")] if r[7] else []
            ),
        ),
    )
    await safe(
        "comissoes",
        tbl(
            "Comissões",
            f"{await _scalar(db, 'SELECT count(*) FROM commissions')} comissões",
            "Nova comissão",
            ["Referência", "Venda", "Comissão", "Status"],
            "1.4fr 1fr 1fr 0.9fr",
            "SELECT coalesce(reference_number,'—'), coalesce(sale_value,0), coalesce(final_commission,0), status::text FROM commissions ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(brl(r[1])),
                t(brl(r[2]), 600),
                b("Paga", "ok") if (r[3] or "").lower() in ("paid", "pago") else b(r[3] or "—", "warn"),
            ],
        ),
    )
    await safe(
        "contatos",
        tbl(
            "Contatos",
            f"{await _scalar(db, 'SELECT count(*) FROM crm_contacts')} contatos",
            "Novo contato",
            ["Contato", "Cliente", "Cargo", "Telefone"],
            "1.6fr 1.6fr 1.2fr 1fr",
            "SELECT ct.name, coalesce(cl.name,'—'), coalesce(ct.role,'—'), coalesce(ct.phone, ct.whatsapp, '—') FROM crm_contacts ct LEFT JOIN clients cl ON cl.id=ct.client_id ORDER BY ct.name LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(r[2]), t(r[3])],
        ),
    )
    # Precificação — Tabela de referência CCT 2026 por função (base legal da folha; era P0 no audit)
    await safe(
        "precificacao",
        tbl(
            "Precificação — Tabela CCT 2026",
            f"{await _scalar(db, 'SELECT count(*) FROM crm_pricing_funcoes')} funções (piso + adicionais CCT SINDECOMPRESTS)",
            "—",
            ["Função", "Salário base", "Jornada", "Noturno", "Ronda", "Periculosidade", "Insalubridade"],
            "2fr 1.1fr 0.9fr 0.9fr 0.9fr 1fr 1fr",
            "SELECT nome, coalesce(salario_base,0), coalesce(jornada_dias::text,'—'), coalesce(noturno::text,'—'), "
            "coalesce(ronda::text,'—'), coalesce(periculosidade::text,'—'), coalesce(insalubridade::text,'—') "
            "FROM crm_pricing_funcoes WHERE coalesce(ativo,true)=true ORDER BY ordem NULLS LAST LIMIT 60",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(brl(r[1]), 600),
                t(f"{r[2]} dias" if r[2] not in (None, "—") else "—"),
                *[
                    b("Sim", "ok") if str(v).lower() in ("true", "t", "1", "sim") else t("—")
                    for v in (r[3], r[4], r[5], r[6])
                ],
            ],
        ),
    )
    # Atividades — timeline real do CRM (crm_activities; menu já existia)
    await safe(
        "atividades",
        tbl(
            "Atividades",
            f"{await _scalar(db, 'SELECT count(*) FROM crm_activities')} atividades",
            "Nova atividade",
            ["Assunto", "Tipo", "Cliente", "Agendada", "Concluída", "Resultado"],
            "2fr 1fr 1.6fr 1fr 1fr 1.2fr",
            "SELECT coalesce(a.subject,'—'), coalesce(a.type::text,'—'), coalesce(cl.name,'—'), a.scheduled_at, a.completed_at, coalesce(a.outcome,'—') "
            "FROM crm_activities a LEFT JOIN clients cl ON cl.id=a.client_id ORDER BY coalesce(a.scheduled_at, a.created_at) DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                b((r[1] or "—").replace("_", " ").capitalize(), "info"),
                t(r[2]),
                t(_fmtdate(r[3], "%d/%m/%Y %H:%M") if r[3] else "—"),
                b("Concluída", "ok") if r[4] else b("Aberta", "warn"),
                t(r[5]),
            ],
        ),
    )
    # Simular preço (calculadora de precificação — cálculo puro, não gera proposta/contrato)
    out["simular-preco"] = {
        "title": "Simular preço",
        "sub": "Calculadora de precificação (CCT + custos + margem) — simulação, não gera proposta",
        "cta": "Simular",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/simular-preco", "okMsg": "Preço simulado"},
        "fields": [
            {
                "key": "service_type",
                "label": "Serviço*",
                "type": "select",
                "span": "span 1",
                "ph": "Tipo",
                "options": [
                    {"value": v, "label": l}
                    for v, l in [
                        ("portaria", "Portaria"),
                        ("vigilancia", "Vigilância"),
                        ("limpeza", "Limpeza"),
                        ("seguranca_eletronica", "Segurança eletrônica"),
                        ("portaria_remota", "Portaria remota"),
                    ]
                ],
            },
            {
                "key": "base_salary",
                "label": "Salário base (R$)",
                "type": "text",
                "span": "span 1",
                "ph": "1670,00 (piso CCT)",
            },
            {"key": "headcount", "label": "Nº de postos", "type": "text", "span": "span 1", "ph": "1"},
            {"key": "contract_months", "label": "Meses de contrato", "type": "text", "span": "span 1", "ph": "12"},
            {"key": "margin_target", "label": "Margem alvo (%)", "type": "text", "span": "span 1", "ph": "35"},
            {"key": "client_state", "label": "UF do cliente", "type": "text", "span": "span 1", "ph": "AM"},
            {"key": "benefits_value", "label": "Benefícios/posto (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "equipment_value", "label": "Equipamentos (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
        ],
    }
    # Novo lead (FORM com ESCRITA real → POST /redesign/action/lead)
    out["novo-lead"] = {
        "title": "Novo lead",
        "sub": "Cadastrar um novo lead comercial",
        "cta": "Cadastrar lead",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/lead", "okMsg": "Lead criado com sucesso"},
        "fields": [
            {"key": "name", "label": "Nome*", "type": "text", "span": "span 1", "ph": "Nome do contato"},
            {"key": "company", "label": "Empresa", "type": "text", "span": "span 1", "ph": "Empresa / condomínio"},
            {"key": "email", "label": "E-mail", "type": "text", "span": "span 1", "ph": "email@empresa.com"},
            {"key": "phone", "label": "Telefone", "type": "text", "span": "span 1", "ph": "(92) 90000-0000"},
            {
                "key": "source",
                "label": "Origem",
                "type": "select",
                "span": "span 1",
                "ph": "Origem",
                "options": [
                    {"value": v, "label": l}
                    for v, l in [
                        ("whatsapp", "WhatsApp"),
                        ("referral", "Indicação"),
                        ("website", "Site"),
                        ("social_media", "Redes sociais"),
                        ("cold_call", "Prospecção ativa"),
                        ("event", "Evento"),
                        ("partner", "Parceiro"),
                        ("email_campaign", "E-mail mkt"),
                        ("other", "Outro"),
                    ]
                ],
            },
            {"key": "expected_value", "label": "Valor estimado (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "notes", "label": "Observações", "type": "textarea", "span": "span 2", "ph": "Notas sobre o lead…"},
        ],
    }
    # Nova tarefa (FORM com ESCRITA real → POST /redesign/action/task)
    cli_opts = (
        await db.execute(text("SELECT id, name FROM clients WHERE status='active' ORDER BY name LIMIT 100"))
    ).fetchall()
    out["nova-tarefa"] = {
        "title": "Nova tarefa",
        "sub": "Criar um follow-up / lembrete comercial",
        "cta": "Criar tarefa",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/task", "okMsg": "Tarefa criada com sucesso"},
        "fields": [
            {
                "key": "title",
                "label": "Título*",
                "type": "text",
                "span": "span 2",
                "ph": "Ex.: Ligar para o cliente sobre proposta",
            },
            {
                "key": "priority",
                "label": "Prioridade",
                "type": "select",
                "span": "span 1",
                "ph": "Prioridade",
                "options": [
                    {"value": v, "label": l} for v, l in [("low", "Baixa"), ("medium", "Média"), ("high", "Alta")]
                ],
            },
            {"key": "due_date", "label": "Vencimento", "type": "date", "span": "span 1"},
            {
                "key": "client_id",
                "label": "Cliente (opcional)",
                "type": "select",
                "span": "span 2",
                "ph": "Vincular a um cliente",
                "options": [{"value": str(i), "label": n} for i, n in cli_opts],
            },
            {
                "key": "description",
                "label": "Descrição",
                "type": "textarea",
                "span": "span 2",
                "ph": "Detalhes da tarefa…",
            },
        ],
    }
    # Oportunidades (LEITURA real) + Mover no funil (ESCRITA)
    _STG = {
        "qualification": ("Qualificação", "mut"),
        "needs_analysis": ("Análise", "info"),
        "proposal": ("Proposta", "info"),
        "negotiation": ("Negociação", "warn"),
        "closed_won": ("Ganho", "ok"),
        "closed_lost": ("Perdido", "bad"),
    }
    opp_rows = (
        await db.execute(
            text(
                "SELECT id, title, coalesce(company_name, contact_name, '—'), coalesce(value,0), stage::text "
                "FROM opportunities WHERE coalesce(is_active,true) ORDER BY updated_at DESC NULLS LAST LIMIT 200"
            )
        )
    ).fetchall()
    await safe(
        "oportunidades",
        tbl(
            "Oportunidades",
            f"{len(opp_rows)} no funil",
            "Mover no funil",
            ["Oportunidade", "Cliente", "Valor", "Estágio"],
            "2.4fr 1.4fr 1fr 1fr",
            "SELECT id, title, coalesce(company_name, contact_name, '—'), coalesce(value,0), stage::text "
            "FROM opportunities WHERE coalesce(is_active,true) ORDER BY updated_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t((r[1] or "—")[:70], 600, "#0F1B3A"),
                t(r[2]),
                t(brl(r[3]), 600),
                b(*_STG.get(r[4], (r[4] or "—", "mut"))),
            ],
            # Mover na PRÓPRIA linha. A tela tinha 104 linhas e só "Ver": para mudar o estágio
            # era preciso abrir outro formulário e caçar a oportunidade num menu de 104 itens.
            # Jordan, 10/09/2026, indo higienizar o funil: 70 delas estão em "proposta" SEM
            # proposta nenhuma, e fechar uma a uma por menu é uma hora de trabalho.
            actionsfn=lambda r: [
                {
                    "title": f"Mover “{(r[1] or '—')[:48]}” no funil",
                    "endpoint": "/api/v1/redesign/action/opportunity-stage",
                    "method": "POST",
                    "btnLabel": "Mover",
                    "submitLabel": "Mover",
                    "btnStyle": "outline",
                    "okMsg": "Oportunidade movida. Recarregue.",
                    "fields": [
                        {"key": "opportunity_id", "type": "hidden", "value": str(r[0])},
                        {
                            "key": "stage",
                            "label": "Novo estágio*",
                            "type": "select",
                            "span": "span 1",
                            "value": r[4] or "",
                            "options": [{"value": v, "label": lab} for v, (lab, _x) in _STG.items()],
                        },
                        {
                            "key": "notes",
                            "label": "Motivo (fica no histórico)",
                            "type": "text",
                            "span": "span 2",
                            "value": "",
                        },
                    ],
                },
                # Confirmação por DIÁLOGO, não por digitação. Nasceu pedindo "digite
                # EXCLUIR" e o Jordan tentou tirar 7 linhas do GRUPO PARVI sem conseguir:
                # sete digitações num trabalho de faxina. O botão do LEAD já usava
                # `confirm` e funcionou na mão dele no mesmo dia — a diferença era minha,
                # não do produto. É soft delete e a lista filtra `is_active`, então o custo
                # de um clique errado é um UPDATE de volta, não perda de dado.
                {
                    "title": f"Excluir “{(r[1] or '—')[:44]}” do funil",
                    "sub": "Some da lista. Para 'não fechou', use Mover → Perdida.",
                    "endpoint": "/api/v1/redesign/action/oportunidade-excluir",
                    "method": "POST",
                    "btnLabel": "Excluir",
                    "submitLabel": "Excluir",
                    "btnStyle": "outline",
                    "confirm": f"Excluir “{(r[1] or '—')[:40]}” da lista?",
                    "okMsg": "Oportunidade excluída. Recarregue.",
                    "fields": [
                        {"key": "opportunity_id", "type": "hidden", "value": str(r[0])},
                        {"key": "confirmar", "type": "hidden", "value": "EXCLUIR"},
                    ],
                },
            ],
        ),
    )
    out["mover-oportunidade"] = {
        "title": "Mover no funil",
        "sub": "Atualizar o estágio de uma oportunidade",
        "cta": "Mover",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/opportunity-stage", "okMsg": "Oportunidade movida"},
        "fields": [
            {
                "key": "opportunity_id",
                "label": "Oportunidade*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione a oportunidade",
                "options": [
                    {"value": str(i), "label": f"{(ti or '—')[:55]} · {_STG.get(st, (st, ''))[0]}"}
                    for i, ti, _cn, _v, st in opp_rows
                ],
            },
            {
                "key": "stage",
                "label": "Novo estágio*",
                "type": "select",
                "span": "span 1",
                "ph": "Estágio",
                "options": [{"value": v, "label": l} for v, (l, _tone) in _STG.items()],
            },
            {
                "key": "notes",
                "label": "Observação",
                "type": "textarea",
                "span": "span 2",
                "ph": "Motivo/nota da mudança (opcional)…",
            },
        ],
    }
    # Consumo de IA — a linha de base que não existia. Sem ela, "a troca de provedor
    # economizou" é opinião. `custo_usd` nulo = modelo fora da tabela de preço: melhor
    # célula vazia que número inventado numa planilha de custo.
    try:
        await safe(
            "consumo-ia",
            tbl(
                "Consumo de IA (30 dias)",
                "Tokens e custo estimado por origem — a fatura do provedor é a verdade final",
                "—",
                ["Origem", "Modelo", "Chamadas", "Falhas", "Tokens", "Custo est. (US$)"],
                "1.3fr 1.2fr 0.8fr 0.7fr 1fr 1fr",
                "SELECT origem, modelo, count(*), count(*) FILTER (WHERE NOT ok), "
                "coalesce(sum(tokens_total),0), sum(custo_usd) "
                "FROM llm_usage WHERE criado_em > now() - interval '30 days' "
                "GROUP BY origem, modelo ORDER BY coalesce(sum(custo_usd),0) DESC, count(*) DESC "
                "LIMIT 100",
                lambda r: [
                    t(r[0], 600, "#0F1B3A"),
                    t(r[1]),
                    t(str(r[2])),
                    (b(str(r[3]), "warn") if r[3] else t("0")),
                    t(f"{int(r[4]):,}".replace(",", ".")),
                    t(f"US$ {float(r[5]):.4f}" if r[5] is not None else "—", 600),
                ],
            ),
        )
    except Exception:  # noqa: BLE001 — tabela recém-criada; ausência não derruba a tela
        await db.rollback()

    # Proposta -> contrato: o elo que faltava. Só propostas que AINDA não viraram contrato
    # aparecem; oferecer as que já viraram só produziria 409 na cara do usuário.
    _prop_rows = (
        await db.execute(
            text(
                "SELECT p.id::text, p.number, coalesce(p.client_company, p.title, '') AS quem, "
                "coalesce(p.total,0) AS total "
                "FROM proposals p "
                "WHERE coalesce(p.is_active, true) AND coalesce(p.client_document,'') <> '' "
                # Proposta RECUSADA não vira contrato. Não havia filtro de status: o seletor
                # oferecia PROP-2026-00114 e PROP-2026-00093, as duas `rejected` — propostas que
                # o cliente já disse não. Medido em 14/09/2026.
                "  AND coalesce(p.status::text,'') NOT IN ('rejected','recusada','lost','perdida','cancelled','cancelada') "
                "  AND NOT EXISTS (SELECT 1 FROM contracts c WHERE c.proposal_id = p.id) "
                "ORDER BY p.created_at DESC LIMIT 120"
            )
        )
    ).fetchall()
    out["contrato-da-proposta"] = {
        "title": "Gerar contrato a partir da proposta",
        "sub": f"{len(_prop_rows)} proposta(s) sem contrato. Cliente e valor vêm da "
        "proposta; a modalidade define o modelo e o CNPJ que emite.",
        "cta": "Gerar contrato",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/contrato-da-proposta",
            "confirm": "Criar o contrato a partir desta proposta?",
            "okMsg": "Contrato criado",
        },
        "fields": [
            {
                "key": "proposal_id",
                "label": "Proposta*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione a proposta",
                "options": [{"value": i, "label": f"{n} · {q[:34]} · {brl(v)}"} for i, n, q, v in _prop_rows],
            },
            {
                "key": "modalidade",
                "label": "Modalidade*",
                "type": "select",
                "span": "span 1",
                "ph": "Define o modelo e o CNPJ emitente",
                "options": [
                    {"value": "portaria", "label": "Portaria / Controle de acesso"},
                    {"value": "servicos_gerais", "label": "Serviços gerais / Limpeza (ASG)"},
                    {"value": "jardinagem", "label": "Jardinagem"},
                    {"value": "piscina", "label": "Piscina"},
                    {"value": "zeladoria", "label": "Zeladoria"},
                    {"value": "eletronica", "label": "Segurança eletrônica / CFTV"},
                ],
            },
            {"key": "vigencia_inicio", "label": "Início da vigência*", "type": "date", "span": "span 1"},
            {
                "key": "valor_mensal",
                "label": "Valor mensal (R$)",
                "type": "text",
                "span": "span 1",
                "ph": "Vazio usa o valor da proposta",
            },
            {"key": "vigencia_meses", "label": "Vigência (meses)", "type": "text", "span": "span 1", "ph": "12"},
            {"key": "dia_vencimento", "label": "Dia do vencimento", "type": "text", "span": "span 1", "ph": "Ex.: 10"},
            {
                "key": "renovacao_aviso_dias",
                "label": "Aviso de não renovação (dias)",
                "type": "text",
                "span": "span 1",
                "ph": "30",
            },
        ],
    }
    # Assinatura do contrato, dentro do CRM (antes só existia via agente/Cowork).
    # As duas ações chamam as MESMAS rotas de /crm/contracts já provadas — nada de motor
    # novo, e o portão de emitente continua sendo o do serviço.
    _ctr_rows = (
        await db.execute(
            text(
                "SELECT ct.contract_number, coalesce(cl.name, ct.name, ''), "
                "(SELECT count(*) FROM sig_signature_requests s "
                " WHERE s.reference_code = ct.contract_number) AS aberta "
                "FROM contracts ct LEFT JOIN clients cl ON cl.id = ct.client_id "
                "WHERE coalesce(ct.is_active, true) AND ct.template_id IS NOT NULL "
                "ORDER BY ct.start_date DESC NULLS LAST LIMIT 120"
            )
        )
    ).fetchall()
    out["abrir-assinatura"] = {
        "title": "Abrir assinatura do contrato",
        "sub": "Registra a solicitação das duas partes e gera os links. A CONTRATADA "
        "assina primeiro; só depois o link do cliente funciona.",
        "cta": "Abrir assinatura",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/contrato-abrir-assinatura",
            "confirm": "Abrir a assinatura eletrônica deste contrato?",
            "okMsg": "Assinatura aberta",
        },
        "fields": [
            {
                "key": "contrato",
                "label": "Contrato*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione o contrato",
                "options": [
                    {"value": n, "label": f"{n} · {c[:34]}" + (" · já aberta" if a else "")} for n, c, a in _ctr_rows
                ],
            },
            {
                "key": "email_cliente",
                "label": "E-mail do cliente (opcional)",
                "type": "text",
                "span": "span 2",
                "ph": "Para notificar o link — o código vai depois, no e-mail que ele informar",
            },
        ],
    }
    out["enviar-link-assinatura"] = {
        "title": "Enviar link de assinatura",
        "sub": "Manda o convite ao signatário — ou devolve o link para você mandar por "
        "WhatsApp. Recusa mandar ao cliente antes de a Conecta Mais assinar.",
        "cta": "Enviar link",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/contrato-enviar-link", "okMsg": "Link enviado"},
        "fields": [
            {
                "key": "contrato",
                "label": "Contrato*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione o contrato",
                "options": [{"value": n, "label": f"{n} · {c[:34]}"} for n, c, a in _ctr_rows if a],
            },
            {
                "key": "parte",
                "label": "Para quem*",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": "cliente", "label": "Cliente (CONTRATANTE)"},
                    {"value": "empresa", "label": "Conecta Mais (CONTRATADA)"},
                ],
            },
            {
                "key": "email",
                "label": "E-mail",
                "type": "text",
                "span": "span 1",
                "ph": "Vazio devolve o link para envio manual",
            },
        ],
    }
    # Definir lead (FORM → POST /redesign/action/lead-definir)
    # 29 dos 32 leads estavam parados em `new` sem NENHUMA ação na tela para tirá-los de
    # lá: o CRM cadastrava lead e não sabia o que fazer com ele. `mover-oportunidade` só
    # serve para quem já virou oportunidade.
    _lead_rows = (
        await db.execute(
            text(
                "SELECT id::text, name, coalesce(company,''), coalesce(status::text,''), "
                "coalesce(qualificacao->>'temperatura','') "
                "FROM leads WHERE coalesce(is_active, true) "
                "ORDER BY (status::text = 'new') DESC, created_at DESC LIMIT 300"
            )
        )
    ).fetchall()
    _n_novos = sum(1 for r in _lead_rows if r[3] == "new")
    out["definir-lead"] = {
        "title": "Definir lead",
        "sub": f"{_n_novos} lead(s) ainda sem destino. Qualifique, descarte ou abra a "
        "oportunidade — descartar exige motivo.",
        "cta": "Definir",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/lead-definir", "okMsg": "Lead definido"},
        "fields": [
            {
                "key": "lead_id",
                "label": "Lead*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione o lead",
                "options": [
                    {
                        "value": i,
                        "label": (
                            f"{(n or '—')[:40]}"
                            + (f" · {c[:24]}" if c else "")
                            + f" · {st}"
                            + (f" · {tp}" if tp else "")
                        ),
                    }
                    for i, n, c, st, tp in _lead_rows
                ],
            },
            {
                "key": "destino",
                "label": "Destino*",
                "type": "select",
                "span": "span 1",
                "ph": "O que fazer com ele",
                "options": [
                    {"value": "contacted", "label": "Contatado"},
                    {"value": "qualified", "label": "Qualificado"},
                    {"value": "proposal", "label": "Proposta enviada"},
                    {"value": "negotiation", "label": "Em negociação"},
                    {"value": "won", "label": "Ganho (virou cliente)"},
                    {"value": "lost", "label": "Descartado"},
                ],
            },
            {"key": "abrir_oportunidade", "label": "Abrir oportunidade no funil", "type": "checkbox", "span": "span 1"},
            {
                "key": "motivo",
                "label": "Motivo / observação",
                "type": "textarea",
                "span": "span 2",
                "ph": "Obrigatório ao descartar. Ex.: sem verba, escolheu concorrente…",
            },
        ],
    }
    # Nova proposta (FORM com ESCRITA real → POST /redesign/action/proposal)
    try:
        _emp_rows = (
            await db.execute(
                text(
                    # `empresas` não tem coluna `ativo` — tem `status`. Conferido no banco em 14/09.
                    "SELECT id::text, coalesce(razao_social, slug) FROM empresas "
                    "WHERE coalesce(status::text,'ativo') NOT IN ('inativo','inativa') "
                    "ORDER BY is_principal DESC NULLS LAST, razao_social"
                )
            )
        ).fetchall()
    except Exception:  # noqa: BLE001
        await db.rollback()
        _emp_rows = []
    _emp_opts = [{"value": i, "label": n} for i, n in _emp_rows]
    out["nova-proposta"] = {
        "title": "Nova proposta",
        "sub": "Criar uma proposta comercial",
        "cta": "Criar proposta",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/proposal", "okMsg": "Proposta criada com sucesso"},
        "fields": [
            {
                "key": "client_id",
                "label": "Cliente*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione o cliente",
                "options": [{"value": str(i), "label": n} for i, n in cli_opts],
            },
            {
                "key": "title",
                "label": "Título*",
                "type": "text",
                "span": "span 2",
                "ph": "Ex.: Proposta de portaria — Cond. X",
            },
            # Empresa emissora: `proposal_items.empresa_id` é NOT NULL e não havia campo nenhum
            # para informá-la. Resultado medido em 14/09/2026: criar proposta pela tela devolvia
            # HTTP 500 (NotNullViolationError) — o CRM não conseguia emitir proposta.
            # A tabela `proposals` não tem empresa_id; quem carrega a empresa é o ITEM.
            {
                "key": "empresa_id",
                "label": "Empresa emissora*",
                "type": "select",
                "span": "span 2",
                "ph": "De qual CNPJ sai a proposta",
                "options": _emp_opts,
            },
            {"key": "item_name", "label": "Serviço/Item", "type": "text", "span": "span 1", "ph": "Ex.: Portaria 24h"},
            {"key": "valor", "label": "Valor (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {
                "key": "description",
                "label": "Descrição",
                "type": "textarea",
                "span": "span 2",
                "ph": "Detalhes da proposta…",
            },
        ],
    }
    # Anotar cliente (FORM com ESCRITA real → POST /redesign/action/client-note)
    out["anotar-cliente"] = {
        "title": "Anotar cliente",
        "sub": "Registrar uma anotação na ficha do cliente",
        "cta": "Salvar anotação",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/client-note", "okMsg": "Anotação salva"},
        "fields": [
            {
                "key": "client_id",
                "label": "Cliente*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione o cliente",
                "options": [{"value": str(i), "label": n} for i, n in cli_opts],
            },
            {
                "key": "nota",
                "label": "Anotação*",
                "type": "textarea",
                "span": "span 2",
                "ph": "Escreva a anotação sobre o cliente…",
            },
        ],
    }
    # Aditivos contratuais (reajustes/alterações) — contract_addendums
    await safe(
        "aditivos",
        tbl(
            "Aditivos contratuais",
            f"{await _scalar(db, 'SELECT count(*) FROM contract_addendums')} aditivos",
            "—",
            ["Contrato", "Aditivo", "Tipo", "Valor anterior", "Novo valor", "Reajuste", "Vigência", "Assinado"],
            "1.2fr 0.7fr 1fr 1fr 1fr 0.8fr 0.9fr 0.8fr",
            "SELECT coalesce(ct.contract_number, ct.name, '—'), coalesce(a.addendum_number::text,'—'), coalesce(a.addendum_type::text,'—'), "
            "a.previous_value, a.new_value, a.adjustment_percent, a.effective_date, a.signed "
            "FROM contract_addendums a LEFT JOIN contracts ct ON ct.id = a.contract_id "
            "ORDER BY a.effective_date DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(r[1]),
                t((r[2] or "—").replace("_", " ").capitalize()),
                t(brl(r[3]) if r[3] is not None else "—"),
                t(brl(r[4]) if r[4] is not None else "—", 600),
                t(f"{r[5]}%" if r[5] is not None else "—"),
                t(_fmtdate(r[6])),
                b("Assinado", "ok") if r[7] else b("Pendente", "warn"),
            ],
        ),
    )
    return out


async def _build_fiscal(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_nfse = await _scalar(db, "SELECT count(*) FROM nfse_manaus_historico")
    fat12 = await _scalar(
        db,
        "SELECT coalesce((SELECT sum(valor_servicos) FROM nfse_manaus_historico "
        "                 WHERE data_emissao >= CURRENT_DATE - interval '12 months'), 0) "
        "     + coalesce((SELECT sum(valor_servicos) FROM nfse_emitidas_nacional "
        "                 WHERE data_emissao >= CURRENT_DATE - interval '12 months'), 0)",
    )
    obr_pend = await _scalar(
        db,
        "SELECT count(*) FROM fiscal_obligations WHERE lower(coalesce(status::text,'')) NOT IN ('cumprida','cumprido','pago','paga','concluido','concluida')",
    )
    obr_val = await _scalar(
        db,
        "SELECT coalesce(sum(valor_devido),0) FROM fiscal_obligations WHERE lower(coalesce(status::text,'')) NOT IN ('cumprida','cumprido','pago','paga','concluido','concluida')",
    )

    async def _painel():
        obr = (
            await db.execute(
                text(
                    "SELECT nome, valor_devido, data_vencimento, status::text FROM fiscal_obligations ORDER BY data_vencimento NULLS LAST LIMIT 6"
                )
            )
        ).fetchall()
        nf = (
            await db.execute(
                text(
                    "SELECT tomador_nome, valor_servicos FROM nfse_manaus_historico ORDER BY data_emissao DESC LIMIT 6"
                )
            )
        ).fetchall()
        return {
            "title": "Painel fiscal",
            "sub": "Fiscal & Contábil — dados reais",
            "cta": "Atualizar",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_nfse), "l": "NFS-e (histórico)", "icon": _ICF["chart"], "color": "#0F1B3A"},
                {"v": brl(fat12), "l": "Faturamento (12m)", "icon": _ICF["money"], "color": "#0F1B3A"},
                {
                    "v": str(obr_pend),
                    "l": "Obrigações em aberto",
                    "icon": IC["alert"],
                    "color": "#C2410C" if obr_pend else "#0F1B3A",
                },
                {"v": brl(obr_val), "l": "Valor em aberto", "icon": _ICF["money"], "color": "#0F1B3A"},
            ],
            "panels": [
                {
                    "title": "Obrigações",
                    "rows": [
                        {"left": f"{n or '—'}", "right": brl(v), **(S["bad"] if False else S["warn"])}
                        for n, v, dv, st in obr
                    ]
                    or [{"left": "Sem obrigações", "right": brl(0), **S["ok"]}],
                },
                {
                    "title": "Últimas NFS-e",
                    "rows": [{"left": nm or "—", "right": brl(v), **S["info"]} for nm, v in nf]
                    or [{"left": "Sem NFS-e", "right": "—", **S["mut"]}],
                },
            ],
        }

    await safe("painel", _painel())
    await safe(
        "nfse",
        tbl(
            "NFS-e",
            f"{n_nfse} notas (histórico)",
            "Emitir NFS-e",
            ["Número", "Tomador", "Valor", "Emissão", "Status"],
            "1fr 2fr 1fr 1fr 0.9fr",
            "SELECT coalesce(numero::text,'—'), coalesce(tomador_nome,'—'), coalesce(valor_servicos,0), data_emissao, coalesce(status::text,'—') FROM nfse_manaus_historico ORDER BY data_emissao DESC LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(r[1]),
                t(brl(r[2]), 600),
                t(_fmtdate(r[3])),
                b("Autorizada", "ok")
                if "autoriz" in (r[4] or "").lower() or (r[4] or "").lower() in ("normal", "emitida")
                else b(r[4] or "—", "info"),
            ],
        ),
    )
    await safe(
        "guias",
        tbl(
            "Guias / Obrigações",
            f"{await _scalar(db, 'SELECT count(*) FROM fiscal_obligations')} obrigações",
            "Nova guia",
            ["Obrigação", "Competência", "Valor", "Vencimento", "Status"],
            "1.8fr 1fr 1fr 1fr 0.9fr",
            "SELECT coalesce(nome,'—'), coalesce(to_char(make_date(competencia_ano, greatest(competencia_mes,1), 1),'MM/YYYY'),'—'), coalesce(valor_devido,0), data_vencimento, status::text "
            "FROM fiscal_obligations ORDER BY data_vencimento DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(r[1]),
                t(brl(r[2]), 600),
                t(_fmtdate(r[3])),
                b("Pago", "ok") if (r[4] or "").lower() in ("pago", "paga") else b(r[4] or "Pendente", "warn"),
            ],
        ),
    )

    # DCTFWeb / EFD-Reinf — status de obrigação (compliance legal, leitura de fiscal_obligations por tipo)
    def _obrig(tipo, label):
        return tbl(
            label,
            f"{label} — obrigações, prazos e status (fiscal_obligations)",
            "—",
            ["Obrigação", "Competência", "Valor devido", "Valor pago", "Vencimento", "Status"],
            "1.6fr 1fr 1fr 1fr 1fr 0.9fr",
            "SELECT coalesce(nome, tipo, '—'), coalesce(to_char(make_date(competencia_ano, greatest(competencia_mes,1), 1),'MM/YYYY'),'—'), "
            "coalesce(valor_devido,0), coalesce(valor_pago,0), data_vencimento, coalesce(status::text,'—') "
            f"FROM fiscal_obligations WHERE tipo='{tipo}' ORDER BY data_vencimento DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(r[1]),
                t(brl(r[2]), 600),
                t(brl(r[3])),
                t(_fmtdate(r[4])),
                b("Cumprida", "ok")
                if (r[5] or "").lower() in ("cumprida", "pago", "paga")
                else b((r[5] or "Pendente").capitalize(), "warn"),
            ],
        )

    await safe("dctfweb", _obrig("DCTFWEB", "DCTFWeb"))
    await safe("reinf", _obrig("EFD_REINF", "EFD-Reinf"))
    # Guias FGTS / INSS — leitura real das guias puxadas do Onvio (fgts_guias / inss_guias).
    # Colunas espelham só o dado real: competência/tipo/status + documento PDF (valor/vencimento
    # ainda não são extraídos → omitidos p/ não exibir colunas 100% vazias).
    _gtone = {"pago": "ok", "paga": "ok", "conciliado": "ok", "pendente": "warn", "vencido": "bad", "vencida": "bad"}
    await safe(
        "guias-fgts",
        tbl(
            "Guias FGTS",
            f"{await _scalar(db, 'SELECT count(*) FROM fgts_guias')} guias (Onvio)",
            "—",
            ["Competência", "Tipo", "Documento", "Status"],
            "1fr 1.4fr 0.9fr 0.9fr",
            "SELECT coalesce(mes_ref,'—'), coalesce(tipo,'—'), (arquivo_pdf IS NOT NULL AND arquivo_pdf<>''), coalesce(status,'—') "
            "FROM fgts_guias ORDER BY mes_ref DESC NULLS LAST, tipo LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—").replace("_", " ").capitalize()),
                b("PDF", "ok") if r[2] else t("—"),
                b((r[3] or "—").capitalize(), _gtone.get((r[3] or "").lower(), "info")),
            ],
        ),
    )
    await safe(
        "guias-inss",
        tbl(
            "Guias INSS",
            f"{await _scalar(db, 'SELECT count(*) FROM inss_guias')} guias (Onvio)",
            "—",
            ["Competência", "Documento", "Status"],
            "1.2fr 0.9fr 0.9fr",
            "SELECT coalesce(competencia, mes_ref, '—'), (arquivo_pdf IS NOT NULL AND arquivo_pdf<>''), coalesce(status,'—') "
            "FROM inss_guias ORDER BY mes_ref DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                b("PDF", "ok") if r[1] else t("—"),
                b((r[2] or "—").capitalize(), _gtone.get((r[2] or "").lower(), "info")),
            ],
        ),
    )
    # Certidões CND (compliance fiscal) — ged_certidoes (federal/estadual/municipal/FGTS/trabalhista)
    from datetime import date as _dtoday

    _hoje_cnd = _dtoday.today()

    def _cnd_sit(exp):
        if exp is None:
            return b("—", "info")
        d = exp.date() if hasattr(exp, "date") else exp
        try:
            dias = (d - _hoje_cnd).days
        except TypeError:
            return b("—", "info")
        if dias < 0:
            return b("Vencida", "bad")
        if dias <= 30:
            return b(f"Vence em {dias}d", "warn")
        return b("Válida", "ok")

    await safe(
        "certidoes-cnd",
        tbl(
            "Certidões (CND)",
            f"{await _scalar(db, 'SELECT count(*) FROM ged_certidoes')} certidões",
            "—",
            ["Certidão", "Tipo", "Órgão emissor", "Emissão", "Validade", "Situação"],
            "1.8fr 1.1fr 1.3fr 0.9fr 0.9fr 1fr",
            "SELECT coalesce(name,'—'), coalesce(document_type,'—'), coalesce(issuing_body,'—'), issue_date, expiry_date "
            "FROM ged_certidoes ORDER BY expiry_date ASC NULLS LAST LIMIT 200",
            lambda r: [
                t((r[0] or "—")[:48], 600, "#0F1B3A"),
                t(r[1]),
                t((r[2] or "—")[:32]),
                t(_fmtdate(r[3])),
                t(_fmtdate(r[4])),
                _cnd_sit(r[4]),
            ],
        ),
    )
    # NFS-e tomadas (notas de serviço recebidas) — nfse_tomadas_nacional
    await safe(
        "nfse-tomadas",
        tbl(
            "NFS-e tomadas",
            f"{await _scalar(db, 'SELECT count(*) FROM nfse_tomadas_nacional')} notas recebidas",
            "—",
            ["Número", "Prestador", "CNPJ", "Competência", "Valor", "ISS", "Emissão"],
            "0.8fr 1.8fr 1.1fr 0.9fr 1fr 0.9fr 0.9fr",
            "SELECT coalesce(numero::text,'—'), coalesce(prestador_nome,'—'), coalesce(prestador_cnpj,'—'), coalesce(competencia,'—'), valor_servicos, iss_valor, data_emissao "
            "FROM nfse_tomadas_nacional ORDER BY data_emissao DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0]),
                t((r[1] or "—")[:42], 600, "#0F1B3A"),
                t(r[2]),
                t(r[3]),
                t(brl(r[4]) if r[4] is not None else "—", 600),
                t(brl(r[5]) if r[5] is not None else "—"),
                t(_fmtdate(r[6])),
            ],
        ),
    )
    return out


async def _build_gp(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_ged = await _scalar(db, "SELECT count(*) FROM ged_kit_documents")
    n_aso = await _scalar(db, "SELECT count(*) FROM gp_asos")
    n_epi = await _scalar(db, "SELECT count(*) FROM gp_epi_deliveries")
    n_punch = await _scalar(db, "SELECT count(*) FROM gp_clock_punches")

    async def _visao():
        aso_st = (
            await db.execute(
                text("SELECT status::text, count(*) FROM gp_asos GROUP BY status ORDER BY count(*) DESC LIMIT 6")
            )
        ).fetchall()
        ged_ty = (
            await db.execute(
                text(
                    "SELECT document_type::text, count(*) FROM ged_kit_documents GROUP BY document_type ORDER BY count(*) DESC LIMIT 6"
                )
            )
        ).fetchall()
        return {
            "title": "Visão geral",
            "sub": "Gestão de Pessoas — dados reais",
            "cta": "Nova ação",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": f"{n_ged:,}".replace(",", "."), "l": "Documentos GED", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": str(n_aso), "l": "ASOs", "icon": _ICF["hand"], "color": "#0F1B3A"},
                {"v": str(n_epi), "l": "EPIs entregues", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": f"{n_punch:,}".replace(",", "."), "l": "Batidas de ponto", "icon": IC["cal"], "color": "#0F1B3A"},
            ],
            "panels": [
                {
                    "title": "ASO por status",
                    "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in aso_st]
                    or [{"left": "Sem ASO", "right": "0", **S["mut"]}],
                },
                {
                    "title": "GED por tipo",
                    "rows": [
                        {"left": (s or "—").replace("_", " ").capitalize(), "right": str(c), **S["ok"]}
                        for s, c in ged_ty
                    ]
                    or [{"left": "Sem documentos", "right": "0", **S["mut"]}],
                },
            ],
        }

    await safe("visao", _visao())
    await safe(
        "ged",
        tbl(
            "GED — Documentos",
            f"{n_ged} documentos",
            "Enviar documento",
            ["Documento", "Tipo", "Colaborador", "Assinado"],
            "2fr 1.4fr 1.6fr 0.9fr",
            "SELECT coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), coalesce(e.nome,'—'), g.is_signed, CAST(g.id AS TEXT), coalesce(g.notes,'') "
            "FROM ged_kit_documents g LEFT JOIN employees e ON e.id=g.employee_id ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—").replace("_", " ")),
                t(r[2]),
                b("Assinado", "ok") if r[3] else b("Pendente", "warn"),
            ],
            # LIGAR (revisão 08/09/2026): renomear/anotar e remover documento errado do kit
            actionsfn=lambda r: [
                {
                    "title": f"Editar documento — {r[0]}",
                    "endpoint": f"/api/v1/people-management/ged/documents/{r[4]}",
                    "method": "PUT",
                    "btnLabel": "Editar",
                    "btnStyle": "outline",
                    "submitLabel": "Salvar",
                    "okMsg": "Documento atualizado. Recarregue.",
                    "fields": [
                        {"key": "document_name", "label": "Nome", "type": "text", "value": r[0] or ""},
                        {"key": "notes", "label": "Observações", "type": "textarea", "value": r[5] or ""},
                    ],
                },
                {
                    "title": f"Remover do kit — {r[0]}",
                    "endpoint": f"/api/v1/people-management/ged/documents/{r[4]}",
                    "method": "DELETE",
                    "btnLabel": "Remover",
                    "btnStyle": "outline",
                    "submitLabel": "Remover documento",
                    "confirm": "Remove o documento do kit (o arquivo original não é apagado do Drive). Confirma?",
                    "okMsg": "Documento removido. Recarregue.",
                    "fields": [],
                },
            ],
        ),
    )
    await safe(
        "ponto",
        tbl(
            "Ponto eletrônico",
            f"{n_punch} batidas",
            "Registrar",
            ["Colaborador", "Data/Hora", "Tipo", "Status"],
            "2fr 1.2fr 1fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), to_char(p.punch_timestamp,'DD/MM HH24:MI'), coalesce(p.punch_type::text,'—'), coalesce(p.status::text,'—') "
            "FROM gp_clock_punches p LEFT JOIN employees e ON e.id=p.employee_id ORDER BY p.punch_timestamp DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0])),
                t(r[1]),
                t((r[2] or "—").replace("_", " ")),
                b("OK", "ok")
                if (r[3] or "").lower() in ("valid", "aprovado", "ok", "approved")
                else b(r[3] or "—", "info"),
            ],
        ),
    )
    # Fechamento de ponto / espelho (Portaria 671) — leitura real de gp_monthly_closings (controle legal)
    await safe(
        "ponto-espelho",
        tbl(
            "Fechamento de ponto (Portaria 671)",
            f"{await _scalar(db, 'SELECT count(*) FROM gp_monthly_closings')} fechamentos",
            "Fechar mês",
            ["Colaborador", "Competência", "Dias", "Horas trab.", "HE 50%", "Faltas", "Atraso (min)", "Status"],
            "1.8fr 1fr 0.6fr 1fr 0.8fr 0.7fr 0.9fr 0.9fr",
            "SELECT coalesce(e.nome, m.employee_id, '—'), m.month, m.year, coalesce(m.total_dias_trabalhados,0), "
            "coalesce(m.total_horas_trabalhadas,0), coalesce(m.total_horas_extras_50,0), coalesce(m.total_faltas,0), "
            "coalesce(m.total_atrasos_minutos,0), coalesce(m.fechado,false) "
            "FROM gp_monthly_closings m LEFT JOIN employees e ON e.id::text=m.employee_id::text "
            "ORDER BY m.year DESC NULLS LAST, m.month DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0])),
                t(f"{r[1]:02d}/{r[2]}" if r[1] else "—"),
                t(str(r[3])),
                t(f"{float(r[4]):.0f}h" if r[4] is not None else "—"),
                t(f"{float(r[5]):.0f}h" if r[5] else "—"),
                b(str(r[6]), "bad" if (r[6] or 0) > 0 else "ok"),
                t(str(r[7])),
                b("Fechado", "ok") if r[8] else b("Aberto", "warn"),
            ],
        ),
    )
    await safe(
        "saude-exames",
        tbl(
            "Saúde · Exames (ASO)",
            f"{n_aso} ASOs",
            "Agendar exame",
            ["Colaborador", "Tipo", "Validade", "Situação"],
            "2fr 1.2fr 1fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), coalesce(a.tipo::text,'—'), a.data_validade, a.apto "
            "FROM gp_asos a LEFT JOIN employees e ON e.id=a.employee_id ORDER BY a.data_validade DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0])),
                t((r[1] or "—").replace("_", " ")),
                t(_fmtdate(r[2])),
                b("Apto", "ok") if r[3] else b("Inapto/Pendente", "warn"),
            ],
        ),
    )
    await safe(
        "sst",
        tbl(
            "SST — Entrega de EPI",
            f"{n_epi} entregas",
            "Registrar entrega",
            ["Colaborador", "EPI", "CA", "Entrega"],
            "2fr 1.4fr 0.9fr 1fr",
            "SELECT coalesce(e.nome,'—'), coalesce(d.epi_nome,'—'), coalesce(d.epi_ca,'—'), d.data_entrega "
            "FROM gp_epi_deliveries d LEFT JOIN employees e ON e.id=d.employee_id ORDER BY d.data_entrega DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(r[2]), t(_fmtdate(r[3]))],
        ),
    )
    # Registrar entrega de EPI (ESCRITA real → POST /redesign/action/epi-delivery) — log operacional NR-6
    try:
        emp_rows = (
            await db.execute(text("SELECT id, nome FROM employees WHERE status='ativo' ORDER BY nome LIMIT 400"))
        ).fetchall()
        emp_opts = [{"value": str(eid), "label": nm} for eid, nm in emp_rows]
    except Exception:
        await db.rollback()
        emp_opts = []
    out["registrar-entrega-epi"] = {
        "title": "Registrar entrega de EPI",
        "sub": "Registrar a entrega de um EPI ao colaborador (NR-6)",
        "cta": "Registrar entrega",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/epi-delivery", "okMsg": "Entrega de EPI registrada"},
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione o colaborador",
                "options": emp_opts,
            },
            {"key": "epi_nome", "label": "EPI*", "type": "text", "span": "span 1", "ph": "Ex.: Colete Refletivo"},
            {"key": "epi_ca", "label": "CA", "type": "text", "span": "span 1", "ph": "Ex.: CA-40123"},
            {"key": "quantidade", "label": "Quantidade", "type": "text", "span": "span 1", "ph": "1"},
            {"key": "nr", "label": "Norma (NR)", "type": "text", "span": "span 1", "ph": "NR-6"},
            {"key": "data_entrega", "label": "Data de entrega*", "type": "date", "span": "span 1"},
            {"key": "data_validade", "label": "Validade", "type": "date", "span": "span 1"},
        ],
    }
    # Registrar justificativa de ponto (ESCRITA real → POST /redesign/action/justificativa-ponto) — nasce PENDENTE
    out["registrar-justificativa-ponto"] = {
        "title": "Registrar justificativa de ponto",
        "sub": "Justificar atraso/falta (pendente — o gestor revisa depois)",
        "cta": "Registrar",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/justificativa-ponto", "okMsg": "Justificativa registrada"},
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione o colaborador",
                "options": emp_opts,
            },
            {
                "key": "justification_type",
                "label": "Tipo*",
                "type": "select",
                "span": "span 1",
                "ph": "Atraso ou falta",
                "options": [{"value": "atraso", "label": "Atraso"}, {"value": "falta", "label": "Falta"}],
            },
            {
                "key": "category",
                "label": "Motivo*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione o motivo",
                "options": [
                    {"value": v, "label": l}
                    for v, l in [
                        ("transito", "Trânsito"),
                        ("saude", "Saúde"),
                        ("familiar", "Familiar"),
                        ("transporte_publico", "Transporte público"),
                        ("acidente", "Acidente"),
                        ("outro", "Outro"),
                    ]
                ],
            },
            {
                "key": "reason",
                "label": "Justificativa*",
                "type": "textarea",
                "span": "span 2",
                "ph": "Descreva o ocorrido (mínimo 5 caracteres)",
            },
        ],
    }
    return out


async def _candidatos_screen(db, tbl):
    n = await _scalar(db, "SELECT count(*) FROM candidates")
    return await tbl(
        "Candidatos",
        f"{n} candidatos",
        "Novo candidato",
        ["Candidato", "Cargo pretendido", "Cidade", "Empresa atual"],
        "1.8fr 1.4fr 1fr 1.4fr",
        "SELECT name, coalesce(current_position,'—'), coalesce(nullif(concat_ws('/', city, state),''),'—'), coalesce(current_company,'—') FROM candidates ORDER BY name LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(r[2]), t(r[3])],
    )


async def _entrevistas_screen(db):
    rows = (
        await db.execute(
            text(
                "SELECT interview_type::text, format::text, scheduled_at, status::text FROM interviews ORDER BY scheduled_at DESC NULLS LAST LIMIT 100"
            )
        )
    ).fetchall()
    tone = {"scheduled": "info", "completed": "ok", "cancelled": "mut", "agendada": "info", "realizada": "ok"}
    items = [
        {
            "title": (it or "Entrevista").replace("_", " ").capitalize(),
            "meta": f"{(fmt or '—')} · {_fmtdate(sa, '%d/%m/%Y %H:%M')}",
            "dot": "#2563EB",
            "badge": (st or "—").capitalize(),
            **S[tone.get((st or "").lower(), "info")],
        }
        for it, fmt, sa, st in rows
    ]
    if not items:
        items = [{"title": "Sem entrevistas", "meta": "aguardando dado", "dot": "#16A34A", "badge": "OK", **S["ok"]}]
    return {"title": "Entrevistas", "sub": "Agenda de entrevistas", "cta": "Agendar", "type": "list", "items": items}


async def _build_recrutamento(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_cand = await _scalar(db, "SELECT count(*) FROM candidates")
    n_int = await _scalar(db, "SELECT count(*) FROM interviews")
    n_adm = await _scalar(db, "SELECT count(*) FROM admission_processes")
    n_vagas = await _scalar(db, "SELECT count(*) FROM job_positions")
    n_vagas_abertas = await _scalar(db, "SELECT count(*) FROM job_positions WHERE status='aberta'")

    async def _visao():
        return {
            "title": "Visão geral",
            "sub": "Recrutamento & Seleção — dados reais",
            "cta": "Nova vaga",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_cand), "l": "Candidatos", "icon": IC["users"], "color": "#0F1B3A"},
                {"v": str(n_int), "l": "Entrevistas", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": str(n_adm), "l": "Admissões em processo", "icon": _ICF["hand"], "color": "#0F1B3A"},
                {"v": str(n_vagas_abertas), "l": "Vagas abertas", "icon": IC["shield"], "color": "#0F1B3A"},
            ],
            "panels": [
                {
                    "title": "Candidatos por cidade",
                    "rows": [
                        {"left": (c or "—"), "right": str(n), **S["info"]}
                        for c, n in (
                            await db.execute(
                                text(
                                    "SELECT coalesce(city,'—'), count(*) FROM candidates GROUP BY city ORDER BY count(*) DESC LIMIT 6"
                                )
                            )
                        ).fetchall()
                    ]
                    or [{"left": "Sem candidatos", "right": "0", **S["mut"]}],
                },
                {
                    "title": "Entrevistas por status",
                    "rows": [
                        {"left": (s or "—").capitalize(), "right": str(n), **S["warn"]}
                        for s, n in (
                            await db.execute(
                                text(
                                    "SELECT status::text, count(*) FROM interviews GROUP BY status ORDER BY count(*) DESC"
                                )
                            )
                        ).fetchall()
                    ]
                    or [{"left": "Sem entrevistas", "right": "0", **S["mut"]}],
                },
            ],
        }

    _vaga_tone = {"aberta": "ok", "rascunho": "mut", "pausada": "warn", "encerrada": "bad", "preenchida": "info"}
    await safe("visao", _visao())
    # dgx v2 — as colunas post_id/contract_id nascem aqui se o operacional ainda não foi aberto
    try:
        from modules.operacional.controllers.redesign_builders._dgx_v2_recrutamento_qr import _ensure as _ensure_v2

        await _ensure_v2(db)
    except Exception:  # noqa: BLE001
        await db.rollback()
    await safe(
        "vagas",
        tbl(
            "Vagas",
            f"{n_vagas} vagas · Posto/Contrato preenchidos quando a vaga nasceu de «Recrutar» na vaga do contrato (DGX V2)",
            "Abrir vaga",
            ["Vaga", "Departamento", "Posto", "Contrato", "Preench.", "Nº", "Status"],
            "1.8fr 1.1fr 1.3fr 1.1fr 0.7fr 0.5fr 0.9fr",
            "SELECT v.title, coalesce(v.department,'—'), coalesce(p.name,'—'), "
            "coalesce(k.contract_number, c.name, '—'), coalesce(v.filled_count,0), coalesce(v.vacancies,1), coalesce(v.status,'—') "
            "FROM job_positions v LEFT JOIN posts p ON p.id = v.post_id LEFT JOIN contracts k ON k.id = v.contract_id "
            "LEFT JOIN clients c ON c.id = k.client_id ORDER BY v.created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(r[1]),
                t(r[2], 600 if r[2] != "—" else 400),
                t(r[3]),
                t(f"{r[4]}/{r[5]}"),
                t(str(r[5])),
                b(*(((r[6] or "—").capitalize()), _vaga_tone.get((r[6] or "").lower(), "mut"))),
            ],
        ),
    )
    await safe("candidatos", _candidatos_screen(db, tbl))
    await safe("entrevistas", _entrevistas_screen(db))
    # Abrir vaga (ESCRITA real → POST /redesign/action/job-position) — nasce em RASCUNHO
    out["abrir-vaga"] = {
        "title": "Abrir vaga",
        "sub": "Cadastrar uma nova vaga (rascunho — publique quando quiser divulgar)",
        "cta": "Abrir vaga",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/job-position", "okMsg": "Vaga aberta"},
        "fields": [
            {
                "key": "title",
                "label": "Título da vaga*",
                "type": "text",
                "span": "span 2",
                "ph": "Ex.: Agente de Portaria 12x36",
            },
            {"key": "department", "label": "Departamento", "type": "text", "span": "span 1", "ph": "Ex.: Operacional"},
            {
                "key": "position_type",
                "label": "Contratação",
                "type": "select",
                "span": "span 1",
                "ph": "Tipo",
                "options": [
                    {"value": v, "label": l}
                    for v, l in [
                        ("clt", "CLT"),
                        ("pj", "PJ"),
                        ("temporario", "Temporário"),
                        ("estagio", "Estágio"),
                        ("aprendiz", "Aprendiz"),
                    ]
                ],
            },
            {
                "key": "work_model",
                "label": "Modelo",
                "type": "select",
                "span": "span 1",
                "ph": "Modelo",
                "options": [
                    {"value": v, "label": l}
                    for v, l in [("presencial", "Presencial"), ("hibrido", "Híbrido"), ("remoto", "Remoto")]
                ],
            },
            {"key": "vacancies", "label": "Nº de vagas", "type": "text", "span": "span 1", "ph": "1"},
            {"key": "city", "label": "Cidade", "type": "text", "span": "span 1", "ph": "Ex.: Manaus"},
            {"key": "state", "label": "UF", "type": "text", "span": "span 1", "ph": "AM"},
            {"key": "salary_min", "label": "Salário mín. (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "salary_max", "label": "Salário máx. (R$)", "type": "text", "span": "span 1", "ph": "0,00"},
            {"key": "requirements", "label": "Requisitos", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
            {"key": "description", "label": "Descrição", "type": "textarea", "span": "span 2", "ph": "Opcional…"},
        ],
    }
    return out


async def _build_rh(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    ativos = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
    n_cand = await _scalar(db, "SELECT count(*) FROM candidates")
    n_int = await _scalar(db, "SELECT count(*) FROM interviews")
    n_cert = await _scalar(db, "SELECT count(*) FROM hr_certifications")

    async def _dash():
        st_rows = (
            await db.execute(
                text("SELECT status::text, count(*) FROM employees GROUP BY status ORDER BY count(*) DESC")
            )
        ).fetchall()
        st_tone = {"ativo": "ok", "afastado_inss": "warn", "suspenso": "warn", "inativo": "mut", "demitido": "bad"}
        return {
            "title": "RH",
            "sub": "Recursos Humanos — dados reais",
            "cta": "Nova ação",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(ativos), "l": "Colaboradores ativos", "icon": IC["users"], "color": "#0F1B3A"},
                {"v": str(n_cand), "l": "Candidatos", "icon": _ICF["hand"], "color": "#0F1B3A"},
                {"v": str(n_int), "l": "Entrevistas", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": str(n_cert), "l": "Certificações", "icon": IC["shield"], "color": "#0F1B3A"},
            ],
            "panels": [
                {
                    "title": "Quadro por situação",
                    "rows": [
                        {"left": (s or "—").replace("_", " ").capitalize(), "right": str(c), **S[st_tone.get(s, "mut")]}
                        for s, c in st_rows
                    ],
                },
                {
                    "title": "Certificações (competência)",
                    "rows": [
                        {"left": (c or "—"), "right": str(n), **S["info"]}
                        for c, n in (
                            await db.execute(
                                text(
                                    "SELECT competencia::text, count(*) FROM hr_certifications GROUP BY competencia ORDER BY competencia DESC LIMIT 6"
                                )
                            )
                        ).fetchall()
                    ]
                    or [{"left": "Sem certificações", "right": "0", **S["mut"]}],
                },
            ],
        }

    await safe("dashboard", _dash())
    await safe("candidatos", _candidatos_screen(db, tbl))
    await safe("entrevistas", _entrevistas_screen(db))
    await safe(
        "certificados",
        tbl(
            "Certificados",
            f"{n_cert} certificações",
            "Nova certificação",
            ["Colaborador", "Competência", "Tipo", "Status"],
            "1.8fr 1fr 1.2fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), coalesce(c.competencia::text,'—'), coalesce(c.tipo_calculo::text,'—'), c.status::text "
            "FROM hr_certifications c LEFT JOIN employees e ON e.id=c.employee_id ORDER BY c.competencia DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0] or "")),
                t(r[1]),
                t((r[2] or "—").replace("_", " ")),
                b("OK", "ok") if (r[3] or "").lower() in ("ok", "certificado", "valido") else b(r[3] or "—", "info"),
            ],
        ),
    )
    return out


async def _build_juridico(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_proc = await _scalar(db, "SELECT count(*) FROM juridico_processos")

    async def _visao():
        st = (
            await db.execute(
                text("SELECT status::text, count(*) FROM juridico_processos GROUP BY status ORDER BY count(*) DESC")
            )
        ).fetchall()
        tp = (
            await db.execute(
                text("SELECT tipo::text, count(*) FROM juridico_processos GROUP BY tipo ORDER BY count(*) DESC LIMIT 6")
            )
        ).fetchall()
        return {
            "title": "Visão geral",
            "sub": "Jurídico — dados reais",
            "cta": "Novo processo",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_proc), "l": "Processos", "icon": _ICF["chart"], "color": "#0F1B3A"},
                {
                    "v": str(await _scalar(db, "SELECT count(*) FROM juridico_processos WHERE escalonar=true") or 0),
                    "l": "Escalonados",
                    "icon": IC["alert"],
                    "color": "#C2410C",
                },
                {"v": "—", "l": "Pareceres", "icon": IC["cal"], "color": "#64748B"},
                {"v": "—", "l": "Contratos", "icon": _ICF["hand"], "color": "#64748B"},
            ],
            "panels": [
                {
                    "title": "Processos por status",
                    "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in st]
                    or [{"left": "Sem processos", "right": "0", **S["mut"]}],
                },
                {
                    "title": "Processos por tipo",
                    "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["warn"]} for s, c in tp]
                    or [{"left": "—", "right": "0", **S["mut"]}],
                },
            ],
        }

    await safe("visao", _visao())
    await safe(
        "processos",
        tbl(
            "Processos",
            f"{n_proc} processos",
            "Novo processo",
            ["Número", "Tipo", "Reclamante", "Status"],
            "1.4fr 1.2fr 1.8fr 0.9fr",
            "SELECT coalesce(numero,'—'), coalesce(tipo::text,'—'), coalesce(reclamante,'—'), status::text FROM juridico_processos ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or "—").replace("_", " ")), t(r[2]), b(r[3] or "—", "info")],
        ),
    )
    # DET — Comunicações (Domicílio Eletrônico Trabalhista) — juridico_det_comunicacoes
    _det_tone = {
        "nova": "warn",
        "aberta": "warn",
        "pendente": "warn",
        "respondida": "ok",
        "encerrada": "ok",
        "ciente": "ok",
        "arquivada": "mut",
    }
    await safe(
        "det-comunicacoes",
        tbl(
            "DET — Comunicações",
            f"{await _scalar(db, 'SELECT count(*) FROM juridico_det_comunicacoes')} comunicações",
            "—",
            ["Título", "Tipo", "Órgão", "Número", "Prazo", "Status"],
            "1.9fr 1fr 1.3fr 0.9fr 0.9fr 0.9fr",
            "SELECT coalesce(titulo,'—'), coalesce(tipo,'—'), coalesce(orgao,'—'), coalesce(numero,'—'), coalesce(prazo,'—'), coalesce(status,'—') "
            "FROM juridico_det_comunicacoes ORDER BY created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t((r[0] or "—")[:52], 600, "#0F1B3A"),
                t(r[1]),
                t((r[2] or "—")[:30]),
                t(r[3]),
                t(r[4]),
                b((r[5] or "—").capitalize(), _det_tone.get((r[5] or "").lower(), "info")),
            ],
        ),
    )
    return out


async def _build_empresas(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_emp = await _scalar(db, "SELECT count(*) FROM empresas")
    obr_pend = await _scalar(
        db,
        "SELECT count(*) FROM fiscal_obligations WHERE lower(coalesce(status::text,'')) NOT IN ('cumprida','cumprido','pago','paga','concluido','concluida')",
    )

    async def _visao():
        emps = (
            await db.execute(
                text(
                    "SELECT razao_social, coalesce(regime_tributario::text,'—') FROM empresas ORDER BY razao_social LIMIT 10"
                )
            )
        ).fetchall()
        return {
            "title": "Visão geral",
            "sub": "Empresas — dados reais",
            "cta": "Nova empresa",
            "type": "dash",
            "panelGrid": "1.4fr 1fr",
            "kpis": [
                {"v": str(n_emp), "l": "Empresas", "icon": IC["shield"], "color": "#0F1B3A"},
                {
                    "v": str(obr_pend),
                    "l": "Obrigações em aberto",
                    "icon": IC["alert"],
                    "color": "#C2410C" if obr_pend else "#0F1B3A",
                },
                {
                    "v": str(await _scalar(db, "SELECT count(*) FROM clients WHERE status='active'") or 0),
                    "l": "Clientes",
                    "icon": IC["users"],
                    "color": "#0F1B3A",
                },
                {
                    "v": str(await _scalar(db, "SELECT count(*) FROM nfse_manaus_historico") or 0),
                    "l": "NFS-e (histórico)",
                    "icon": _ICF["chart"],
                    "color": "#0F1B3A",
                },
            ],
            "panels": [
                {
                    "title": "Empresas do grupo",
                    "rows": [{"left": rs, "right": (rg or "—"), **S["info"]} for rs, rg in emps]
                    or [{"left": "Sem empresas", "right": "—", **S["mut"]}],
                },
                {
                    "title": "Obrigações",
                    "rows": [
                        {"left": (n or "—"), "right": brl(v), **S["warn"]}
                        for n, v in (
                            await db.execute(
                                text(
                                    "SELECT nome, valor_devido FROM fiscal_obligations ORDER BY data_vencimento NULLS LAST LIMIT 6"
                                )
                            )
                        ).fetchall()
                    ]
                    or [{"left": "Sem obrigações", "right": brl(0), **S["ok"]}],
                },
            ],
        }

    await safe("visao", _visao())
    await safe("dashboard", _visao())
    await safe(
        "obrigacoes",
        tbl(
            "Obrigações",
            f"{await _scalar(db, 'SELECT count(*) FROM fiscal_obligations')} obrigações",
            "Nova obrigação",
            ["Obrigação", "Competência", "Valor", "Vencimento", "Status"],
            "1.8fr 1fr 1fr 1fr 0.9fr",
            "SELECT coalesce(nome,'—'), coalesce(to_char(make_date(competencia_ano, greatest(competencia_mes,1), 1),'MM/YYYY'),'—'), coalesce(valor_devido,0), data_vencimento, status::text "
            "FROM fiscal_obligations ORDER BY data_vencimento DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t(r[1]),
                t(brl(r[2]), 600),
                t(_fmtdate(r[3])),
                b("Pago", "ok") if (r[4] or "").lower() in ("pago", "paga") else b(r[4] or "Pendente", "warn"),
            ],
        ),
    )
    return out


async def _asos_screen(db, tbl):
    n = await _scalar(db, "SELECT count(*) FROM gp_asos")
    return await tbl(
        "Exames (ASO)",
        f"{n} ASOs",
        "Agendar exame",
        ["Colaborador", "Tipo", "Validade", "Situação"],
        "2fr 1.2fr 1fr 0.9fr",
        "SELECT coalesce(e.nome,'—'), coalesce(a.tipo::text,'—'), a.data_validade, a.apto FROM gp_asos a LEFT JOIN employees e ON e.id=a.employee_id ORDER BY a.data_validade DESC NULLS LAST LIMIT 200",
        lambda r: [
            t(r[0], 600, "#0F1B3A", initials(r[0] or "")),
            t((r[1] or "—").replace("_", " ")),
            t(_fmtdate(r[2])),
            b("Apto", "ok") if r[3] else b("Inapto/Pendente", "warn"),
        ],
    )


async def _epi_screen(db, tbl):
    n = await _scalar(db, "SELECT count(*) FROM gp_epi_deliveries")
    return await tbl(
        "EPI — Entregas",
        f"{n} entregas",
        "Registrar entrega",
        ["Colaborador", "EPI", "CA", "Entrega"],
        "2fr 1.4fr 0.9fr 1fr",
        "SELECT coalesce(e.nome,'—'), coalesce(d.epi_nome,'—'), coalesce(d.epi_ca,'—'), d.data_entrega FROM gp_epi_deliveries d LEFT JOIN employees e ON e.id=d.employee_id ORDER BY d.data_entrega DESC NULLS LAST LIMIT 200",
        lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0] or "")), t(r[1]), t(r[2]), t(_fmtdate(r[3]))],
    )


async def _ged_screen(db, tbl):
    n = await _scalar(db, "SELECT count(*) FROM ged_kit_documents")
    return await tbl(
        "Arquivos",
        f"{n} documentos",
        "Enviar documento",
        ["Documento", "Tipo", "Colaborador", "Assinado"],
        "2fr 1.4fr 1.6fr 0.9fr",
        "SELECT coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), coalesce(e.nome,'—'), g.is_signed FROM ged_kit_documents g LEFT JOIN employees e ON e.id=g.employee_id ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
        lambda r: [
            t(r[0], 600, "#0F1B3A"),
            t((r[1] or "—").replace("_", " ")),
            t(r[2]),
            b("Assinado", "ok") if r[3] else b("Pendente", "warn"),
        ],
    )


async def _build_saude(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_aso = await _scalar(db, "SELECT count(*) FROM gp_asos")
    n_risk = await _scalar(db, "SELECT count(*) FROM gp_risks")
    n_epi = await _scalar(db, "SELECT count(*) FROM gp_epi_deliveries")
    aptos = await _scalar(db, "SELECT count(*) FROM gp_asos WHERE apto=true")

    async def _visao():
        aso_st = (
            await db.execute(
                text("SELECT status::text, count(*) FROM gp_asos GROUP BY status ORDER BY count(*) DESC LIMIT 6")
            )
        ).fetchall()
        risk_lv = (
            await db.execute(
                text("SELECT nivel::text, count(*) FROM gp_risks GROUP BY nivel ORDER BY count(*) DESC LIMIT 6")
            )
        ).fetchall()
        return {
            "title": "Visão geral",
            "sub": "Saúde Ocupacional — dados reais",
            "cta": "Nova ação",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_aso), "l": "ASOs", "icon": _ICF["hand"], "color": "#0F1B3A"},
                {"v": str(aptos), "l": "Aptos", "icon": IC["shield"], "color": "#16A34A"},
                {"v": str(n_risk), "l": "Riscos mapeados", "icon": IC["alert"], "color": "#0F1B3A"},
                {"v": str(n_epi), "l": "EPIs entregues", "icon": IC["shield"], "color": "#0F1B3A"},
            ],
            "panels": [
                {
                    "title": "ASO por status",
                    "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in aso_st]
                    or [{"left": "Sem ASO", "right": "0", **S["mut"]}],
                },
                {
                    "title": "Riscos por nível",
                    "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["warn"]} for s, c in risk_lv]
                    or [{"left": "Sem riscos", "right": "0", **S["mut"]}],
                },
            ],
        }

    risk_tone = {
        "alto": "bad",
        "high": "bad",
        "critico": "bad",
        "medio": "warn",
        "moderado": "warn",
        "baixo": "info",
        "low": "info",
    }
    await safe("visao", _visao())
    await safe("exames", _asos_screen(db, tbl))
    await safe("epi", _epi_screen(db, tbl))
    await safe(
        "riscos",
        tbl(
            "Riscos ocupacionais",
            f"{n_risk} riscos",
            "Novo risco",
            ["Categoria", "Descrição", "Nível", "Status"],
            "1.2fr 2.2fr 0.9fr 0.9fr",
            "SELECT coalesce(categoria::text,'—'), coalesce(descricao,'—'), coalesce(nivel::text,'—'), status::text FROM gp_risks ORDER BY nivel DESC NULLS LAST LIMIT 200",
            lambda r: [
                t((r[0] or "—").replace("_", " "), 600, "#0F1B3A"),
                t(r[1]),
                b((r[2] or "—").capitalize(), risk_tone.get((r[2] or "").lower(), "mut")),
                b(r[3] or "—", "info"),
            ],
        ),
    )

    # eSocial · Transmissão (VISIBILIDADE real, READ-ONLY) — reusa o acompanhamento do clássico.
    # Protocolo/recibo SEMPRE do governo; transmitir em lote continua no fluxo gated (não aqui).
    async def _esocial_screen():
        from modules.people_management.sst.services.transmissao_central_service import acompanhamento

        ac = await acompanhamento(db, 200)
        cont = ac.get("contagem", {})
        st_tone = {"recibo_casado": "ok", "aguardando_recibo": "warn", "rejeitado_ou_erro": "bad"}
        rows = [
            {
                "cells": [
                    t(ev.get("tipo", "—"), 600, "#0F1B3A"),
                    t(ev.get("funcionario") or "—"),
                    b((ev.get("esocial_status") or "—").capitalize(), st_tone.get(ev.get("grupo"), "info")),
                    t(ev.get("esocial_protocolo") or "—"),
                    t(ev.get("recibo") or "—"),
                ]
            }
            for ev in ac.get("eventos", [])
        ]
        sub = (
            f"Aguardando recibo {cont.get('aguardando_recibo', 0)} · Casados {cont.get('recibo_casado', 0)} · "
            f"Rejeitados {cont.get('rejeitado_ou_erro', 0)} — protocolo/recibo SEMPRE do governo (nada fabricado)"
        )
        return {
            "title": "eSocial · Transmissão",
            "sub": sub,
            "type": "table",
            "searchHint": "Buscar evento…",
            "grid": "0.8fr 2fr 1fr 1.4fr 1.4fr",
            "cols": ["Evento", "Funcionário", "Status", "Protocolo", "Recibo"],
            "rows": rows or [{"cells": [t("—"), t("Sem eventos transmitidos"), b("—", "mut"), t("—"), t("—")]}],
        }

    await safe("esocial", _esocial_screen())
    # CAT (S-2210) — leitura real de gp_cats
    _cat_tone = {"grave": "bad", "fatal": "bad", "moderada": "warn", "leve": "info", "tipica": "info"}
    await safe(
        "cat",
        tbl(
            "CAT — Comunicação de Acidente",
            f"{await _scalar(db, 'SELECT count(*) FROM gp_cats')} CATs (S-2210)",
            "Nova CAT",
            ["Colaborador", "Tipo", "Data", "Gravidade", "Nº CAT INSS", "eSocial"],
            "1.8fr 1.2fr 1fr 0.9fr 1.1fr 0.9fr",
            "SELECT coalesce(e.nome, c.employee_id::text, '—'), coalesce(c.tipo_acidente,'—'), c.data_acidente, "
            "coalesce(c.gravidade,'—'), coalesce(c.numero_cat_inss,'—'), coalesce(c.esocial_status::text,'nao_transmitida') "
            "FROM gp_cats c LEFT JOIN employees e ON e.id::text=c.employee_id::text ORDER BY c.data_acidente DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0])),
                t((r[1] or "—").replace("_", " ")),
                t(_fmtdate(r[2])),
                b((r[3] or "—").capitalize(), _cat_tone.get((r[3] or "").lower(), "info")),
                t(r[4]),
                b((r[5] or "—").replace("_", " ").capitalize(), "ok" if (r[5] or "").startswith("aceit") else "warn"),
            ],
        ),
    )
    # Afastamentos (S-2230) — leitura real de sst_afastamentos
    await safe(
        "afastamentos",
        tbl(
            "Afastamentos",
            f"{await _scalar(db, 'SELECT count(*) FROM sst_afastamentos')} afastamentos (S-2230)",
            "Novo afastamento",
            ["Colaborador", "Tipo", "Início", "Fim previsto", "Retorno", "CID", "Estabilidade", "Status"],
            "1.6fr 1fr 0.9fr 1fr 0.9fr 0.7fr 1fr 0.9fr",
            "SELECT coalesce(employee_nome,'—'), coalesce(tipo::text,'—'), data_inicio, data_fim_prevista, data_retorno, "
            "coalesce(cid,'—'), gera_estabilidade, estabilidade_ate, coalesce(status::text,'—') FROM sst_afastamentos ORDER BY data_inicio DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0])),
                t((r[1] or "—").replace("_", " ")),
                t(_fmtdate(r[2])),
                t(_fmtdate(r[3])),
                t(_fmtdate(r[4]) if r[4] else "em curso"),
                t(r[5]),
                b(f"até {_fmtdate(r[7])}", "warn") if r[6] else b("não", "mut"),
                b((r[8] or "—").capitalize(), "info"),
            ],
        ),
    )
    return out


async def _build_documentos(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_ged = await _scalar(db, "SELECT count(*) FROM ged_kit_documents")
    n_signed = await _scalar(db, "SELECT count(*) FROM ged_kit_documents WHERE is_signed=true")

    async def _visao():
        ty = (
            await db.execute(
                text(
                    "SELECT document_type::text, count(*) FROM ged_kit_documents GROUP BY document_type ORDER BY count(*) DESC LIMIT 8"
                )
            )
        ).fetchall()
        return {
            "title": "Visão geral",
            "sub": "Documentos (GED) — dados reais",
            "cta": "Enviar documento",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": f"{n_ged:,}".replace(",", "."), "l": "Documentos", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": f"{n_signed:,}".replace(",", "."), "l": "Assinados", "icon": IC["shield"], "color": "#16A34A"},
                {
                    "v": str(await _scalar(db, "SELECT count(DISTINCT employee_id) FROM ged_kit_documents") or 0),
                    "l": "Colaboradores",
                    "icon": IC["users"],
                    "color": "#0F1B3A",
                },
                {
                    "v": str(await _scalar(db, "SELECT count(DISTINCT document_type) FROM ged_kit_documents") or 0),
                    "l": "Tipos",
                    "icon": IC["cal"],
                    "color": "#0F1B3A",
                },
            ],
            "panels": [
                {
                    "title": "Documentos por tipo",
                    "rows": [
                        {"left": (s or "—").replace("_", " ").capitalize(), "right": str(c), **S["ok"]} for s, c in ty
                    ]
                    or [{"left": "Sem documentos", "right": "0", **S["mut"]}],
                },
                {
                    "title": "Assinatura",
                    "rows": [
                        {"left": "Assinados", "right": str(n_signed), **S["ok"]},
                        {"left": "Pendentes", "right": str((n_ged or 0) - (n_signed or 0)), **S["warn"]},
                    ],
                },
            ],
        }

    await safe("visao", _visao())
    await safe("arquivos", _ged_screen(db, tbl))
    return out


async def _build_campo(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_vis = await _scalar(db, "SELECT count(*) FROM visitas")
    n_os = await _scalar(db, "SELECT count(*) FROM ordens_servico")

    async def _visao():
        return {
            "title": "Visão geral",
            "sub": "Campo — dados reais",
            "cta": "Nova visita",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_vis), "l": "Visitas", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": str(n_os), "l": "Ordens de serviço", "icon": _ICF["hand"], "color": "#0F1B3A"},
                {
                    "v": str(await _scalar(db, "SELECT count(*) FROM posts WHERE status='active'") or 0),
                    "l": "Postos ativos",
                    "icon": IC["shield"],
                    "color": "#0F1B3A",
                },
                {
                    "v": str(await _scalar(db, "SELECT count(*) FROM occurrences") or 0),
                    "l": "Ocorrências",
                    "icon": IC["alert"],
                    "color": "#0F1B3A",
                },
            ],
            "panels": [
                {
                    "title": "Visitas por status",
                    "rows": [
                        {"left": (s or "—").capitalize(), "right": str(c), **S["info"]}
                        for s, c in (
                            await db.execute(
                                text(
                                    "SELECT status::text, count(*) FROM visitas GROUP BY status ORDER BY count(*) DESC"
                                )
                            )
                        ).fetchall()
                    ]
                    or [{"left": "Sem visitas", "right": "0", **S["mut"]}],
                },
                {
                    "title": "OS por status",
                    "rows": [
                        {"left": (s or "—").capitalize(), "right": str(c), **S["warn"]}
                        for s, c in (
                            await db.execute(
                                text(
                                    "SELECT status::text, count(*) FROM ordens_servico GROUP BY status ORDER BY count(*) DESC"
                                )
                            )
                        ).fetchall()
                    ]
                    or [{"left": "Sem OS", "right": "0", **S["mut"]}],
                },
            ],
        }

    await safe("visao", _visao())
    await safe(
        "checkin",
        tbl(
            "Visitas de campo",
            f"{n_vis} visitas",
            "Nova visita",
            ["Número", "Tipo", "Responsável", "Status"],
            "1fr 1.2fr 1.8fr 0.9fr",
            "SELECT coalesce(numero,'—'), coalesce(tipo::text,'—'), coalesce(responsavel_nome, prospect_nome, '—'), status::text FROM visitas ORDER BY id DESC LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or "—").replace("_", " ")), t(r[2]), b(r[3] or "—", "info")],
        ),
    )
    await safe(
        "ordens-servico",
        tbl(
            "Ordens de serviço",
            f"{n_os} OS",
            "Nova OS",
            ["Número", "Tipo", "Cliente", "Prioridade", "Status"],
            "1fr 1.2fr 1.6fr 0.9fr 0.9fr",
            "SELECT coalesce(numero,'—'), coalesce(tipo::text,'—'), coalesce(cliente_nome,'—'), coalesce(prioridade::text,'—'), status::text FROM ordens_servico ORDER BY id DESC LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—").replace("_", " ")),
                t(r[2]),
                b(
                    (r[3] or "—").capitalize(),
                    "warn" if (r[3] or "").lower() in ("alta", "urgente", "high") else "info",
                ),
                b(r[4] or "—", "info"),
            ],
        ),
    )
    return out


async def _build_servicos(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_os = await _scalar(db, "SELECT count(*) FROM ordens_servico")

    async def _visao():
        return {
            "title": "Visão geral",
            "sub": "Serviços — dados reais",
            "cta": "Nova OS",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_os), "l": "Ordens de serviço", "icon": _ICF["hand"], "color": "#0F1B3A"},
                {
                    "v": str(await _scalar(db, "SELECT count(*) FROM service_catalog") or 0),
                    "l": "Catálogo",
                    "icon": IC["cal"],
                    "color": "#0F1B3A",
                },
                {
                    "v": str(await _scalar(db, "SELECT count(*) FROM clients WHERE status='active'") or 0),
                    "l": "Clientes",
                    "icon": IC["users"],
                    "color": "#0F1B3A",
                },
                {
                    "v": str(
                        await _scalar(
                            db,
                            "SELECT count(*) FROM ordens_servico WHERE status::text NOT IN ('concluida','concluido','cancelada')",
                        )
                        or 0
                    ),
                    "l": "Em aberto",
                    "icon": IC["alert"],
                    "color": "#0F1B3A",
                },
            ],
            "panels": [
                {
                    "title": "OS por status",
                    "rows": [
                        {"left": (s or "—").capitalize(), "right": str(c), **S["info"]}
                        for s, c in (
                            await db.execute(
                                text(
                                    "SELECT status::text, count(*) FROM ordens_servico GROUP BY status ORDER BY count(*) DESC"
                                )
                            )
                        ).fetchall()
                    ]
                    or [{"left": "Sem OS", "right": "0", **S["mut"]}],
                },
                {
                    "title": "OS por tipo",
                    "rows": [
                        {"left": (s or "—").capitalize(), "right": str(c), **S["warn"]}
                        for s, c in (
                            await db.execute(
                                text(
                                    "SELECT tipo::text, count(*) FROM ordens_servico GROUP BY tipo ORDER BY count(*) DESC LIMIT 6"
                                )
                            )
                        ).fetchall()
                    ]
                    or [{"left": "—", "right": "0", **S["mut"]}],
                },
            ],
        }

    await safe("visao", _visao())
    await safe(
        "ordens",
        tbl(
            "Ordens",
            f"{n_os} OS",
            "Nova OS",
            ["Número", "Tipo", "Cliente", "Status"],
            "1fr 1.2fr 1.8fr 0.9fr",
            "SELECT coalesce(numero,'—'), coalesce(tipo::text,'—'), coalesce(cliente_nome,'—'), status::text FROM ordens_servico ORDER BY id DESC LIMIT 200",
            lambda r: [t(r[0], 600, "#0F1B3A"), t((r[1] or "—").replace("_", " ")), t(r[2]), b(r[3] or "—", "info")],
        ),
    )
    return out


def _kv(val, unit):
    v = float(val or 0)
    if unit == "BRL":
        return brl(v)
    if unit == "%":
        return f"{v:.1f}".replace(".", ",") + "%"
    return str(int(v)) if v == int(v) else f"{v:.1f}".replace(".", ",")


async def _build_bi(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)

    async def _dash():
        rows = (
            await db.execute(
                text(
                    "SELECT name, current_value, unit, category::text, direction::text FROM executive_kpis WHERE status::text!='inactive' ORDER BY category"
                )
            )
        ).fetchall()
        by_name = {r[0]: r for r in rows}

        def kpi(nm, label, icon, color="#0F1B3A"):
            r = by_name.get(nm)
            return {"v": _kv(r[1], r[2]) if r else "—", "l": label, "icon": icon, "color": color}

        cats: dict = {}
        for nm, val, unit, cat, direc in rows:  # noqa: B007  # pré-existente: variável de laço não usada
            cats.setdefault(cat or "—", []).append((nm, _kv(val, unit)))

        # dois painéis: FINANCIAL e COMMERCIAL/OPERATIONAL
        def panel(title, catkey):
            return {
                "title": title,
                "rows": [{"left": nm, "right": v, **S["info"]} for nm, v in cats.get(catkey, [])]
                or [{"left": "—", "right": "—", **S["mut"]}],
            }

        return {
            "title": "Dashboard",
            "sub": "Business Intelligence — KPIs reais",
            "cta": "Atualizar",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                kpi("Funcionarios Ativos", "Funcionários ativos", IC["users"]),
                kpi("Clientes Ativos", "Clientes ativos", _ICF["hand"]),
                kpi("Receita Recorrente Mensal", "MRR", _ICF["money"], "#16A34A"),
                kpi("Margem Bruta", "Margem bruta", _ICF["chart"]),
            ],
            "panels": [panel("Financeiro", "FINANCIAL"), panel("Comercial", "COMMERCIAL")],
        }

    await safe("dashboard", _dash())
    return out


async def _build_analytics(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)

    async def _visao():
        async def sc(sql):
            return await _scalar(db, sql) or 0

        punches = await sc("SELECT count(*) FROM gp_clock_punches")
        ged = await sc("SELECT count(*) FROM ged_kit_documents")
        nfse = await sc("SELECT count(*) FROM nfse_manaus_historico") + await sc(
            "SELECT count(*) FROM nfse_emitidas_nacional"
        )
        prop = await sc("SELECT count(*) FROM proposals WHERE coalesce(is_active,true)")
        emp = await sc("SELECT count(*) FROM employees")
        inter = await sc("SELECT count(*) FROM inter_transactions")
        return {
            "title": "Visão geral",
            "sub": "Analytics — métricas de uso reais",
            "cta": "Exportar",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": f"{punches:,}".replace(",", "."), "l": "Batidas de ponto", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": f"{ged:,}".replace(",", "."), "l": "Documentos GED", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": f"{nfse:,}".replace(",", "."), "l": "NFS-e", "icon": _ICF["chart"], "color": "#0F1B3A"},
                {
                    "v": f"{inter:,}".replace(",", "."),
                    "l": "Transações bancárias",
                    "icon": _ICF["money"],
                    "color": "#0F1B3A",
                },
            ],
            "panels": [
                {
                    "title": "Volume por módulo",
                    "rows": [
                        {"left": "Colaboradores", "right": str(emp), **S["info"]},
                        {"left": "Propostas comerciais", "right": str(prop), **S["info"]},
                        {"left": "Documentos GED", "right": f"{ged:,}".replace(",", "."), **S["info"]},
                        {"left": "Batidas de ponto", "right": f"{punches:,}".replace(",", "."), **S["info"]},
                    ],
                },
                {
                    "title": "Fiscal",
                    "rows": [
                        {
                            "left": "NFS-e (histórico)",
                            "right": str(await sc("SELECT count(*) FROM nfse_manaus_historico")),
                            **S["ok"],
                        },
                        {
                            "left": "NFS-e nacional",
                            "right": str(await sc("SELECT count(*) FROM nfse_emitidas_nacional")),
                            **S["ok"],
                        },
                        {
                            "left": "NFS-e tomadas",
                            "right": str(await sc("SELECT count(*) FROM nfse_tomadas_nacional")),
                            **S["ok"],
                        },
                    ],
                },
            ],
        }

    await safe("visao", _visao())
    return out


async def _build_relatorios(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)

    async def sc(sql):
        return await _scalar(db, sql) or 0

    async def _central():
        postos = await sc("SELECT count(*) FROM posts WHERE status='active'")
        colab = await sc("SELECT count(*) FROM employees WHERE status='ativo'")
        pagar = await sc(
            "SELECT coalesce(sum(net_value),0) FROM payable_accounts WHERE status IN ('pendente','parcial')"
        )
        receber = await sc(
            "SELECT coalesce(sum(net_value),0) FROM receivable_accounts WHERE status IN ('pendente','parcial')"
        )
        leads = await sc("SELECT count(*) FROM leads")
        prop = await sc("SELECT count(*) FROM proposals")
        contr = await sc("SELECT count(*) FROM contracts")
        holerites = await sc("SELECT count(*) FROM hr_payslips")
        return {
            "title": "Central de relatórios",
            "sub": "Indicadores reais por área",
            "cta": "Novo relatório",
            "type": "cards",
            "cards": [
                {
                    "title": "Operacional",
                    "sub": "Postos e escalas",
                    "badge": "Ativo",
                    **S["ok"],
                    "hasStats": True,
                    "stats": [
                        {"v": str(postos), "l": "Postos"},
                        {"v": str(colab), "l": "Colab."},
                        {"v": str(await sc("SELECT count(*) FROM occurrences")), "l": "Ocorr."},
                    ],
                },
                {
                    "title": "Financeiro",
                    "sub": "Contas e caixa",
                    "badge": "Ativo",
                    **S["info"],
                    "hasStats": True,
                    "stats": [
                        {"v": brl(pagar), "l": "A pagar", "color": "#C2410C"},
                        {"v": brl(receber), "l": "A receber", "color": "#16A34A"},
                    ],
                },
                {
                    "title": "Comercial",
                    "sub": "Funil e vendas",
                    "badge": "Ativo",
                    **S["info"],
                    "hasStats": True,
                    "stats": [
                        {"v": str(leads), "l": "Leads"},
                        {"v": str(prop), "l": "Propostas"},
                        {"v": str(contr), "l": "Contratos"},
                    ],
                },
                {
                    "title": "Departamento Pessoal",
                    "sub": "Folha e benefícios",
                    "badge": "Ativo",
                    **S["ok"],
                    "hasStats": True,
                    "stats": [
                        {"v": str(holerites), "l": "Holerites"},
                        {
                            "v": brl(
                                await sc(
                                    "SELECT coalesce(sum(net_salary),0) FROM hr_payslips WHERE (reference_year,reference_month)=(SELECT reference_year,reference_month FROM hr_payslips WHERE payslip_code NOT LIKE '13O-%' AND make_date(reference_year, reference_month, 1) <= date_trunc('month', current_date) ORDER BY reference_year DESC, reference_month DESC LIMIT 1)"
                                )
                            ),
                            "l": "Folha líq.",
                        },
                    ],
                },
            ],
        }

    await safe("central", _central())
    await safe(
        "operacional",
        tbl(
            "Relatório operacional",
            "Indicadores reais",
            "Exportar",
            ["Indicador", "Valor"],
            "2fr 1fr",
            "SELECT * FROM (VALUES "
            "('Postos ativos', (SELECT count(*)::text FROM posts WHERE status='active')), "
            "('Postos inativos', (SELECT count(*)::text FROM posts WHERE status='inactive')), "
            "('Colaboradores ativos', (SELECT count(*)::text FROM employees WHERE status='ativo')), "
            "('Alocações ativas', (SELECT count(*)::text FROM employee_alocacoes WHERE ativo=true)), "
            "('Ocorrências (total)', (SELECT count(*)::text FROM occurrences))) v(k,val)",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1], 700)],
        ),
    )
    await safe(
        "financeiro",
        tbl(
            "Relatório financeiro",
            "Indicadores reais",
            "Exportar",
            ["Indicador", "Valor"],
            "2fr 1fr",
            "SELECT * FROM (VALUES "
            "('Contas a pagar (aberto)','money', (SELECT coalesce(sum(net_value),0) FROM payable_accounts WHERE status IN ('pendente','parcial'))::text), "
            "('Contas a receber (aberto)','money', (SELECT coalesce(sum(net_value),0) FROM receivable_accounts WHERE status IN ('pendente','parcial'))::text), "
            "('Diaristas pagos (total)','money', (SELECT coalesce(sum(valor),0) FROM financial_pagamentos_diaristas)::text), "
            "('Clientes ativos','int', (SELECT count(*) FROM clients WHERE status='active')::text)) v(k,kind,val)",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(brl(r[2]) if r[1] == "money" else r[2], 700)],
        ),
    )
    await safe(
        "comercial",
        tbl(
            "Relatório comercial",
            "Indicadores reais",
            "Exportar",
            ["Indicador", "Valor"],
            "2fr 1fr",
            "SELECT * FROM (VALUES "
            "('Leads', (SELECT count(*)::text FROM leads)), "
            "('Propostas', (SELECT count(*)::text FROM proposals)), "
            "('Contratos', (SELECT count(*)::text FROM contracts)), "
            "('Comissões (registros)', (SELECT count(*)::text FROM commissions))) v(k,val)",
            lambda r: [t(r[0], 600, "#0F1B3A"), t(r[1], 700)],
        ),
    )
    return out


async def _build_configuracoes(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_users = await _scalar(db, "SELECT count(*) FROM users")
    n_active = await _scalar(db, "SELECT count(*) FROM users WHERE is_active=true")

    async def _visao():
        by_role = (
            await db.execute(
                text(
                    "SELECT coalesce(role::text,'—'), count(*) FROM users GROUP BY role ORDER BY count(*) DESC LIMIT 6"
                )
            )
        ).fetchall()
        return {
            "title": "Visão geral",
            "sub": "Configurações — dados reais",
            "cta": "Novo usuário",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_users), "l": "Usuários", "icon": IC["users"], "color": "#0F1B3A"},
                {"v": str(n_active), "l": "Ativos", "icon": IC["shield"], "color": "#16A34A"},
                {
                    "v": str(await _scalar(db, "SELECT count(DISTINCT role) FROM users") or 0),
                    "l": "Perfis",
                    "icon": IC["cal"],
                    "color": "#0F1B3A",
                },
                {"v": str((n_users or 0) - (n_active or 0)), "l": "Inativos", "icon": IC["alert"], "color": "#0F1B3A"},
            ],
            "panels": [
                {
                    "title": "Usuários por perfil",
                    "rows": [{"left": (r or "—"), "right": str(c), **S["info"]} for r, c in by_role]
                    or [{"left": "Sem usuários", "right": "0", **S["mut"]}],
                },
                {
                    "title": "Situação",
                    "rows": [
                        {"left": "Ativos", "right": str(n_active), **S["ok"]},
                        {"left": "Inativos", "right": str((n_users or 0) - (n_active or 0)), **S["mut"]},
                    ],
                },
            ],
        }

    await safe("visao", _visao())
    await safe(
        "usuarios",
        tbl(
            "Usuários",
            f"{n_users} usuários · {n_active} ativos",
            "Novo usuário",
            ["Usuário", "E-mail", "Perfil", "Status"],
            "1.6fr 1.8fr 1fr 0.9fr",
            "SELECT coalesce(name,'—'), coalesce(email,'—'), coalesce(role::text,'—'), is_active FROM users ORDER BY name LIMIT 300",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0] or "")),
                t(r[1]),
                t(r[2]),
                b("Ativo", "ok") if r[3] else b("Inativo", "mut"),
            ],
        ),
    )
    return out


async def _build_seguranca(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_audit = await _scalar(db, "SELECT count(*) FROM turnover_audit_logs")

    async def _visao():
        return {
            "title": "Visão geral",
            "sub": "Segurança & LGPD — dados reais",
            "cta": "Ver auditoria",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_audit), "l": "Eventos de auditoria", "icon": IC["shield"], "color": "#0F1B3A"},
                {
                    "v": str(await _scalar(db, "SELECT count(*) FROM users WHERE is_active=true") or 0),
                    "l": "Usuários ativos",
                    "icon": IC["users"],
                    "color": "#0F1B3A",
                },
                {
                    "v": str(
                        await _scalar(db, "SELECT count(*) FROM employees WHERE face_enrolled_at IS NOT NULL") or 0
                    ),
                    "l": "Biometria facial",
                    "icon": IC["shield"],
                    "color": "#0F1B3A",
                },
                {"v": "—", "l": "Solicitações LGPD", "icon": IC["alert"], "color": "#64748B"},
            ],
            "panels": [
                {
                    "title": "Auditoria por ação",
                    "rows": [
                        {"left": (a or "—").replace("_", " ").capitalize(), "right": str(c), **S["info"]}
                        for a, c in (
                            await db.execute(
                                text(
                                    "SELECT acao::text, count(*) FROM turnover_audit_logs GROUP BY acao ORDER BY count(*) DESC LIMIT 6"
                                )
                            )
                        ).fetchall()
                    ]
                    or [{"left": "Sem eventos", "right": "0", **S["mut"]}],
                },
                {
                    "title": "Recursos auditados",
                    "rows": [
                        {"left": (r or "—"), "right": str(c), **S["warn"]}
                        for r, c in (
                            await db.execute(
                                text(
                                    "SELECT recurso::text, count(*) FROM turnover_audit_logs GROUP BY recurso ORDER BY count(*) DESC LIMIT 6"
                                )
                            )
                        ).fetchall()
                    ]
                    or [{"left": "—", "right": "0", **S["mut"]}],
                },
            ],
        }

    await safe("visao", _visao())
    audit = (
        await db.execute(
            text(
                "SELECT a.acao::text, a.recurso::text, u.name, a.created_at FROM turnover_audit_logs a LEFT JOIN users u ON u.id=a.usuario_id ORDER BY a.created_at DESC NULLS LAST LIMIT 100"
            )
        )
    ).fetchall()
    out["auditoria"] = {
        "title": "Auditoria",
        "sub": f"{n_audit} eventos",
        "cta": "Exportar",
        "type": "list",
        "items": [
            {
                "title": f"{(ac or '—').replace('_', ' ').capitalize()} · {rec or '—'}",
                "meta": f"{nm or 'sistema'} · {_fmtdate(dt, '%d/%m/%Y %H:%M')}",
                "dot": "#2563EB",
                "badge": "Auditoria",
                **S["info"],
            }
            for ac, rec, nm, dt in audit
        ]
        or [
            {"title": "Sem eventos de auditoria", "meta": "aguardando dado", "dot": "#16A34A", "badge": "OK", **S["ok"]}
        ],
    }
    return out


async def _build_licitacoes(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_opp = await _scalar(db, "SELECT count(*) FROM bidding_opportunities")
    n_ten = await _scalar(db, "SELECT count(*) FROM bidding_tenders")
    n_part = await _scalar(db, "SELECT count(*) FROM bidding_tenders WHERE participando=true")
    n_prop = await _scalar(db, "SELECT count(*) FROM bidding_proposals")

    async def _visao():
        opp_st = (
            await db.execute(
                text(
                    "SELECT coalesce(status,'—'), count(*) FROM bidding_opportunities GROUP BY 1 ORDER BY 2 DESC LIMIT 6"
                )
            )
        ).fetchall()
        mod = (
            await db.execute(
                text(
                    "SELECT coalesce(modalidade,'—'), count(*) FROM bidding_tenders GROUP BY 1 ORDER BY 2 DESC LIMIT 6"
                )
            )
        ).fetchall()
        val_ctr = await _scalar(
            db, "SELECT coalesce(sum(valor_contrato),0) FROM bidding_public_contracts WHERE coalesce(ativo,true)=true"
        )
        return {
            "title": "Visão geral",
            "sub": "Licitações — dados reais",
            "cta": "Atualizar",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_opp), "l": "Oportunidades", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": f"{n_part}/{n_ten}", "l": "Editais (participando)", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": str(n_prop), "l": "Propostas", "icon": _ICF["hand"], "color": "#0F1B3A"},
                {"v": brl(val_ctr), "l": "Contratos públicos", "icon": _ICF["money"], "color": "#16A34A"},
            ],
            "panels": [
                {
                    "title": "Oportunidades por status",
                    "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in opp_st]
                    or [{"left": "Sem oportunidades", "right": "0", **S["mut"]}],
                },
                {
                    "title": "Editais por modalidade",
                    "rows": [{"left": (m or "—"), "right": str(c), **S["ok"]} for m, c in mod]
                    or [{"left": "Sem editais", "right": "0", **S["mut"]}],
                },
            ],
        }

    await safe("visao", _visao())
    await safe(
        "oportunidades",
        tbl(
            "Oportunidades",
            f"{n_opp} captadas",
            "Atualizar",
            ["Objeto", "Órgão", "UF", "Valor estimado", "Encerra", "Status"],
            "2.2fr 1.6fr 0.5fr 1fr 1fr 0.9fr",
            "SELECT objeto, coalesce(orgao_nome,'—'), coalesce(uf,'—'), valor_estimado, data_encerramento, coalesce(status,'—') "
            "FROM bidding_opportunities ORDER BY data_encerramento DESC NULLS LAST LIMIT 200",
            lambda r: [
                t((r[0] or "—")[:80], 600, "#0F1B3A"),
                t((r[1] or "—")[:40]),
                t(r[2]),
                t(brl(r[3]) if r[3] is not None else "—"),
                t(_fmtdate(r[4])),
                b((r[5] or "—").capitalize(), "info"),
            ],
        ),
    )
    await safe(
        "editais",
        tbl(
            "Editais",
            f"{n_ten} editais ({n_part} participando)",
            "Novo edital",
            ["Nº / Objeto", "Órgão", "Modalidade", "Valor estimado", "Status", "Participa"],
            "2fr 1.6fr 1.1fr 1fr 0.9fr 0.8fr",
            "SELECT coalesce(objeto_resumido, objeto, numero, '—'), coalesce(orgao_nome,'—'), coalesce(modalidade,'—'), valor_estimado, coalesce(status,'—'), coalesce(participando,false) "
            "FROM bidding_tenders ORDER BY data_abertura DESC NULLS LAST LIMIT 200",
            lambda r: [
                t((r[0] or "—")[:70], 600, "#0F1B3A"),
                t((r[1] or "—")[:40]),
                t(r[2]),
                t(brl(r[3]) if r[3] is not None else "—"),
                b((r[4] or "—").capitalize(), "info"),
                b("Sim", "ok") if r[5] else b("Não", "mut"),
            ],
        ),
    )
    await safe(
        "propostas",
        tbl(
            "Propostas",
            f"{n_prop} propostas",
            "Nova proposta",
            ["Nº", "Edital", "Valor total", "Classificação", "Status"],
            "0.8fr 2.2fr 1fr 1fr 0.9fr",
            "SELECT coalesce(p.numero,'—'), coalesce(t.objeto_resumido, t.objeto, '—'), p.valor_total, p.posicao_classificacao, coalesce(p.status,'—') "
            "FROM bidding_proposals p LEFT JOIN bidding_tenders t ON t.id=p.tender_id ORDER BY p.created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—")[:70]),
                t(brl(r[2]) if r[2] is not None else "—"),
                t(f"{r[3]}º" if r[3] else "—"),
                b((r[4] or "—").capitalize(), "info"),
            ],
        ),
    )
    await safe(
        "contratos",
        tbl(
            "Contratos públicos",
            f"{await _scalar(db, 'SELECT count(*) FROM bidding_public_contracts')} contratos",
            "Novo contrato",
            ["Contrato", "Objeto", "Órgão", "Valor", "Vigência", "Status"],
            "1fr 1.8fr 1.4fr 1fr 1.1fr 0.9fr",
            "SELECT coalesce(numero_contrato,'—'), coalesce(objeto_resumido, objeto, '—'), coalesce(orgao_nome,'—'), valor_contrato, data_vigencia_fim, coalesce(status,'—') "
            "FROM bidding_public_contracts ORDER BY data_assinatura DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—")[:55]),
                t((r[2] or "—")[:35]),
                t(brl(r[3]) if r[3] is not None else "—"),
                t(_fmtdate(r[4])),
                b((r[5] or "—").capitalize(), "ok"),
            ],
        ),
    )
    await safe(
        "certidoes",
        tbl(
            "Certidões",
            f"{await _scalar(db, 'SELECT count(*) FROM ged_certidoes')} certidões (ged_certidoes — a fonte viva; bidding_certificates era seed)",
            "—",
            ["Certidão", "Tipo", "Órgão", "Validade", "Situação"],
            "1.8fr 1.2fr 1.4fr 1fr 0.9fr",
            "SELECT coalesce(name,'—'), coalesce(document_type,'—'), coalesce(issuing_body,'—'), expiry_date, "
            "CASE WHEN expiry_date IS NULL THEN '—' WHEN expiry_date >= (now() AT TIME ZONE 'America/Manaus')::date THEN 'válida' ELSE 'vencida' END "
            "FROM ged_certidoes ORDER BY expiry_date ASC NULLS LAST LIMIT 200",
            lambda r: [
                t((r[0] or "—")[:45], 600, "#0F1B3A"),
                t(r[1]),
                t((r[2] or "—")[:35]),
                t(_fmtdate(r[3])),
                b((r[4] or "—").capitalize(), "info"),
            ],
        ),
    )
    # disputas (list)
    drows = (
        await db.execute(
            text(
                "SELECT coalesce(d.status,'—'), coalesce(d.resultado,'—'), d.posicao_final, coalesce(t.objeto_resumido, t.objeto, '—'), d.finished_at "
                "FROM bidding_disputes d LEFT JOIN bidding_tenders t ON t.id=d.tender_id ORDER BY d.started_at DESC NULLS LAST LIMIT 100"
            )
        )
    ).fetchall()
    res_tone = {"vencedor": "ok", "ganhou": "ok", "perdedor": "bad", "perdeu": "bad", "desclassificado": "bad"}
    ditems = [
        {
            "title": (obj or "Disputa")[:70],
            "meta": f"Resultado: {(resu or '—')} · {(f'{pos}º' if pos else '—')} · {_fmtdate(fin, '%d/%m/%Y %H:%M')}",
            "dot": "#2563EB",
            "badge": (st or "—").capitalize(),
            **S[res_tone.get((resu or "").lower(), "info")],
        }
        for st, resu, pos, obj, fin in drows
    ]
    if not ditems:
        ditems = [{"title": "Sem disputas", "meta": "aguardando dado", "dot": "#16A34A", "badge": "OK", **S["ok"]}]
    out["disputas"] = {
        "title": "Disputas",
        "sub": f"{len(drows)} disputas",
        "cta": "Ver",
        "type": "list",
        "items": ditems,
    }
    return out


async def _build_portal_funcionario(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    ativos = await _scalar(db, "SELECT count(*) FROM employees WHERE status='ativo'")
    n_pay = await _scalar(db, "SELECT count(*) FROM hr_payslips")
    n_fer = await _scalar(db, "SELECT count(*) FROM hr_vacation_requests")
    n_reemb = await _scalar(db, "SELECT count(*) FROM reimbursement_requests")

    async def _dash():
        comp = (
            await db.execute(
                text(
                    "SELECT reference_year, reference_month FROM hr_payslips WHERE payslip_code NOT LIKE '13O-%' AND make_date(reference_year, reference_month, 1) <= date_trunc('month', current_date) ORDER BY reference_year DESC, reference_month DESC LIMIT 1"
                )
            )
        ).fetchone()
        comp_lbl = f"{comp[1]:02d}/{comp[0]}" if comp else "—"
        liq = await _scalar(
            db,
            "SELECT coalesce(sum(net_salary),0) FROM hr_payslips WHERE (reference_year,reference_month)=(SELECT reference_year,reference_month FROM hr_payslips WHERE payslip_code NOT LIKE '13O-%' AND make_date(reference_year, reference_month, 1) <= date_trunc('month', current_date) ORDER BY reference_year DESC, reference_month DESC LIMIT 1)",
        )
        fr = (
            await db.execute(
                text(
                    "SELECT coalesce(status::text,'—'), count(*) FROM hr_vacation_requests GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
                )
            )
        ).fetchall()
        return {
            "title": "Início",
            "sub": "Portal do Funcionário — dados reais",
            "cta": "Atualizar",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(ativos), "l": "Colaboradores", "icon": IC["users"], "color": "#0F1B3A"},
                {"v": str(n_pay), "l": "Holerites", "icon": _ICF["money"], "color": "#0F1B3A"},
                {"v": str(n_fer), "l": "Férias solicitadas", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": str(n_reemb), "l": "Reembolsos", "icon": _ICF["hand"], "color": "#0F1B3A"},
            ],
            "panels": [
                {
                    "title": f"Folha — competência {comp_lbl}",
                    "rows": [{"left": "Líquido total", "right": brl(liq), **S["ok"]}],
                },
                {
                    "title": "Férias por status",
                    "rows": [{"left": (s or "—").capitalize(), "right": str(c), **S["info"]} for s, c in fr]
                    or [{"left": "Sem férias", "right": "0", **S["mut"]}],
                },
            ],
        }

    await safe("dashboard", _dash())
    await safe(
        "contracheque",
        tbl(
            "Contracheque",
            f"{n_pay} holerites",
            "Ver",
            ["Colaborador", "Competência", "Líquido", "Status"],
            "2fr 1fr 1fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), p.reference_month, p.reference_year, p.net_salary, coalesce(p.status::text,'—') "
            "FROM hr_payslips p LEFT JOIN employees e ON e.id=p.employee_id ORDER BY p.reference_year DESC, p.reference_month DESC LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0])),
                t(f"{r[1]:02d}/{r[2]}" if r[1] else "—"),
                t(brl(r[3]) if r[3] is not None else "—"),
                b((r[4] or "—").capitalize(), "info"),
            ],
        ),
    )
    await safe(
        "ferias",
        tbl(
            "Minhas férias",
            f"{n_fer} solicitações",
            "Solicitar",
            ["Colaborador", "Início", "Fim", "Dias", "Status"],
            "2fr 1fr 1fr 0.7fr 0.9fr",
            "SELECT coalesce(e.nome,'—'), v.start_date, v.end_date, v.days_requested, coalesce(v.status::text,'—') "
            "FROM hr_vacation_requests v LEFT JOIN employees e ON e.id=v.employee_id ORDER BY v.start_date DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A", initials(r[0])),
                t(_fmtdate(r[1])),
                t(_fmtdate(r[2])),
                t(str(r[3]) if r[3] is not None else "—"),
                b((r[4] or "—").capitalize(), "info"),
            ],
        ),
    )
    await safe(
        "documentos",
        tbl(
            "Meus documentos",
            f"{await _scalar(db, 'SELECT count(*) FROM ged_kit_documents')} documentos",
            "Enviar",
            ["Documento", "Tipo", "Colaborador", "Assinado"],
            "2fr 1.4fr 1.6fr 0.9fr",
            "SELECT coalesce(g.document_name,'—'), coalesce(g.document_type::text,'—'), coalesce(e.nome,'—'), g.is_signed, CAST(g.id AS TEXT), coalesce(g.notes,'') "
            "FROM ged_kit_documents g LEFT JOIN employees e ON e.id=g.employee_id ORDER BY g.created_at DESC NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—").replace("_", " ")),
                t(r[2]),
                b("Assinado", "ok") if r[3] else b("Pendente", "warn"),
            ],
            # LIGAR (revisão 08/09/2026): renomear/anotar e remover documento errado do kit
            actionsfn=lambda r: [
                {
                    "title": f"Editar documento — {r[0]}",
                    "endpoint": f"/api/v1/people-management/ged/documents/{r[4]}",
                    "method": "PUT",
                    "btnLabel": "Editar",
                    "btnStyle": "outline",
                    "submitLabel": "Salvar",
                    "okMsg": "Documento atualizado. Recarregue.",
                    "fields": [
                        {"key": "document_name", "label": "Nome", "type": "text", "value": r[0] or ""},
                        {"key": "notes", "label": "Observações", "type": "textarea", "value": r[5] or ""},
                    ],
                },
                {
                    "title": f"Remover do kit — {r[0]}",
                    "endpoint": f"/api/v1/people-management/ged/documents/{r[4]}",
                    "method": "DELETE",
                    "btnLabel": "Remover",
                    "btnStyle": "outline",
                    "submitLabel": "Remover documento",
                    "confirm": "Remove o documento do kit (o arquivo original não é apagado do Drive). Confirma?",
                    "okMsg": "Documento removido. Recarregue.",
                    "fields": [],
                },
            ],
        ),
    )
    return out


async def _build_meu_espaco(db: AsyncSession, current_user=None) -> dict:
    """Área PESSOAL — escopada ao usuário logado (parede self-only / LGPD). Notificações por
    employee_id do usuário; tarefas por assigned_to/created_by; reembolsos por requester.
    Sem vínculo → vazio (nunca notificação/PII de terceiro). Literais UUID validados."""
    import uuid as _uuid

    out, safe, tbl = _helpers(db)
    uid = getattr(current_user, "id", None) if current_user is not None else None
    me = None
    if uid is not None:
        _r = (
            await db.execute(text("SELECT CAST(employee_id AS TEXT) FROM users WHERE id::text=:i"), {"i": str(uid)})
        ).first()
        if _r and _r[0]:
            me = _r[0]
    _ZERO = "'00000000-0000-0000-0000-000000000000'"
    try:
        me_lit = f"'{me}'" if me and _uuid.UUID(str(me)) else _ZERO
    except Exception:
        me_lit = _ZERO
    try:
        uid_lit = f"'{uid}'" if uid and _uuid.UUID(str(uid)) else _ZERO
    except Exception:
        uid_lit = _ZERO
    _wt = f"(assigned_to_id::text={uid_lit} OR created_by_id::text={uid_lit})"
    # Notificações = as do colaborador (portal) + as do USUÁRIO no sino (communication_notifications,
    # a fonte de /operacional/comunicacao/notificacoes que o cabeçalho lê). Só a primeira deixava o
    # "Meu espaço" do Jordan em 0 com o sino marcando centenas (medido 07/09/2026 pelo navegador).
    _q_sino = (
        f"SELECT count(*) FROM communication_notifications WHERE user_id::text={uid_lit} AND coalesce(is_active,true)"
    )
    n_not = (await _scalar(db, f"SELECT count(*) FROM portal_notifications WHERE employee_id={me_lit}")) + (
        await _scalar(db, _q_sino)
    )
    n_task = await _scalar(db, f"SELECT count(*) FROM crm_tasks WHERE {_wt}")

    async def _visao():
        nlidas = (
            await _scalar(
                db,
                f"SELECT count(*) FROM portal_notifications WHERE employee_id={me_lit} AND coalesce(is_read,false)=false",
            )
        ) + (await _scalar(db, _q_sino + " AND read_at IS NULL"))
        n_reemb = await _scalar(db, f"SELECT count(*) FROM reimbursement_requests WHERE requester_id::text={uid_lit}")
        ty = (
            await db.execute(
                text(
                    f"SELECT coalesce(notification_type::text,'—'), count(*) FROM portal_notifications WHERE employee_id={me_lit} GROUP BY 1 ORDER BY 2 DESC LIMIT 6"
                )
            )
        ).fetchall()
        return {
            "title": "Meu espaço",
            "sub": "Área pessoal — dados reais",
            "cta": "Atualizar",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_not), "l": "Notificações", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": str(nlidas), "l": "Não lidas", "icon": IC["shield"], "color": "#C2410C"},
                {"v": str(n_task), "l": "Tarefas", "icon": _ICF["hand"], "color": "#0F1B3A"},
                {"v": str(n_reemb), "l": "Reembolsos", "icon": _ICF["money"], "color": "#0F1B3A"},
            ],
            "panels": [
                {
                    "title": "Notificações por tipo",
                    "rows": [
                        {"left": (x or "—").replace("_", " ").capitalize(), "right": str(c), **S["info"]} for x, c in ty
                    ]
                    or [{"left": "Sem notificações", "right": "0", **S["mut"]}],
                },
                {
                    "title": "Tarefas",
                    "rows": [
                        {"left": "Tarefas abertas", "right": str(n_task), **(S["ok"] if n_task == 0 else S["warn"])}
                    ],
                },
            ],
        }

    await safe("visao", _visao())
    await safe(
        "tarefas",
        tbl(
            "Minhas tarefas",
            f"{n_task} tarefas",
            "Nova tarefa",
            ["Tarefa", "Prioridade", "Vencimento", "Status"],
            "2fr 1fr 1fr 0.9fr",
            f"SELECT coalesce(title,'—'), coalesce(priority::text,'—'), due_date, coalesce(status::text,'—') FROM crm_tasks WHERE {_wt} ORDER BY due_date NULLS LAST LIMIT 200",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                b((r[1] or "—").capitalize(), "info"),
                t(_fmtdate(r[2])),
                b((r[3] or "—").capitalize(), "info"),
            ],
        ),
    )
    nrows = (
        await db.execute(
            text(
                # QA E2E 08/09: o KPI "Não lidas" soma portal_notifications (por colaborador) + communication_notifications
                # (sino, por usuário), mas a lista só lia a primeira → 941 não lidas e lista vazia. Agora lista as duas.
                f"SELECT coalesce(n.title,'—'), coalesce(n.message,''), coalesce(n.is_read,false), n.created_at, coalesce(e.nome,'—') "
                f"FROM portal_notifications n LEFT JOIN employees e ON e.id=n.employee_id WHERE n.employee_id={me_lit} "
                f"UNION ALL SELECT coalesce(c.title,'—'), coalesce(c.body,''), (c.read_at IS NOT NULL), c.created_at, 'Sino' "
                f"FROM communication_notifications c WHERE c.user_id::text={uid_lit} AND coalesce(c.is_active,true) "
                f"ORDER BY 4 DESC NULLS LAST LIMIT 100"
            )
        )
    ).fetchall()
    nitems = [
        {
            "title": (ti or "—"),
            "meta": f"{(msg or '')[:70]} · {nm} · {_fmtdate(dt, '%d/%m/%Y %H:%M')}",
            "dot": "#16A34A" if rd else "#C2410C",
            "badge": "Lida" if rd else "Nova",
            **(S["ok"] if rd else S["warn"]),
        }
        for ti, msg, rd, dt, nm in nrows
    ]
    if not nitems:
        nitems = [{"title": "Sem notificações", "meta": "aguardando dado", "dot": "#16A34A", "badge": "OK", **S["ok"]}]
    out["notificacoes"] = {
        "title": "Notificações",
        "sub": f"{len(nrows)} notificações",
        "cta": "Marcar lidas",
        "ctaTo": "notificacoes-marcar-todas",  # dgx u3 — o botão existia e não levava a nada
        "type": "list",
        "items": nitems,
    }
    # dgx u3: veio do operacional (lá era tela sem porta e as notificações não vivem lá).
    # A rota é a mesma de sempre (operacional.py: rd_action_notif_marcar_todas) — marca as do usuário logado.
    out["notificacoes-marcar-todas"] = {
        "title": "Marcar notificações como lidas",
        "sub": f"Marca TODAS as suas {len(nrows)} notificações como lidas",
        "cta": "Marcar todas",
        "type": "form",
        "submit": {"endpoint": "/api/v1/redesign/action/notificacoes-marcar-todas", "okMsg": "Notificações marcadas como lidas"},
        "fields": [],
    }
    # ── LIGAR (revisão 08/09/2026): ouvidoria, meus dados e assinaturas pendentes existiam só por API ──
    _SS = "/api/v1/people-management/portal/self-service"
    out["ouvidoria-abrir"] = {
        "title": "Ouvidoria — abrir manifestação",
        "sub": "Denúncia, reclamação, sugestão ou elogio. Anônima por padrão: a empresa responde sem saber quem escreveu.",
        "cta": "Enviar",
        "type": "form",
        "submit": {
            "endpoint": f"{_SS}/ouvidoria",
            "okMsg": "Manifestação registrada — guarde o protocolo.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "categoria",
                "label": "Categoria",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": v, "label": l}
                    for v, l in (
                        ("denuncia", "Denúncia"),
                        ("reclamacao", "Reclamação"),
                        ("sugestao", "Sugestão"),
                        ("elogio", "Elogio"),
                        ("outro", "Outro"),
                    )
                ],
            },
            {
                "key": "anonimo",
                "label": "Anônima?",
                "type": "select",
                "span": "span 1",
                "options": [
                    {"value": "true", "label": "Sim (padrão)"},
                    {"value": "false", "label": "Não — quero ser identificado"},
                ],
            },
            {"key": "mensagem", "label": "Mensagem*", "type": "textarea", "span": "span 2"},
        ],
    }
    try:
        out["minhas-manifestacoes"] = await tbl(
            "Ouvidoria — minhas manifestações",
            "Só as identificadas aparecem aqui (as anônimas não guardam quem enviou)",
            "—",
            ["Protocolo", "Categoria", "Mensagem", "Status", "Resposta"],
            "1fr 1fr 2fr 0.8fr 2fr",
            f"SELECT coalesce(protocolo,'—'), coalesce(categoria::text,'—'), coalesce(mensagem,''), coalesce(status::text,'aberta'), "
            f"coalesce(resposta,'') FROM ouvidoria_manifestacoes WHERE employee_id={me_lit} ORDER BY created_at DESC LIMIT 100",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—").capitalize()),
                t(r[2][:80]),
                b((r[3] or "—").capitalize(), "ok" if (r[3] or "").lower() in ("respondida", "encerrada") else "warn"),
                t(r[4][:80] or "—"),
            ],
        )
        out["assinaturas-pendentes"] = await tbl(
            "Documentos aguardando minha assinatura",
            "Holerites, espelhos, contratos e comunicados que precisam do seu 'de acordo'",
            "—",
            ["Documento", "Tipo", "Solicitado em", "Vence", "Status"],
            "2fr 1fr 1fr 1fr 0.8fr",
            f"SELECT coalesce(title,'—'), coalesce(document_type,'—'), created_at, due_date, coalesce(status::text,'—') "
            f"FROM sig_signature_requests WHERE signer_type='employee' AND CAST(signer_id AS TEXT)={me_lit} "
            f"AND coalesce(status::text,'') NOT IN ('signed','assinado','cancelled','cancelado','expired') ORDER BY created_at DESC LIMIT 100",
            lambda r: [
                t(r[0], 600, "#0F1B3A"),
                t((r[1] or "—").replace("_", " ")),
                t(_fmtdate(r[2])),
                t(_fmtdate(r[3])),
                b((r[4] or "—").capitalize(), "warn"),
            ],
        )
    except Exception as _exc:  # noqa: BLE001
        await db.rollback()
        logger.warning("meu-espaco: ouvidoria/assinaturas não montadas: %s", _exc)
    # ── MEUS PAGAMENTOS ──────────────────────────────────────────────────────────────
    # 22/09/2026 — pedido do Jordan depois de pagar o adiantamento: «disparar pro José Luís
    # informar que já está no portal do funcionário - meu espaço, cada um com o SEU».
    # Escopada por `me` (o employee_id de quem logou): cada um vê só o seu. Mostra o
    # COMPROVANTE do banco (e2e), que é o que transforma «o sistema diz que pagou» em algo
    # que a pessoa pode conferir no extrato dela.
    await safe(
        "meus-pagamentos",
        tbl(
            "Meus pagamentos",
            "Adiantamento e saldo da sua folha, com a data em que o dinheiro saiu e o "
            "comprovante do banco. Se algo não bater com o seu extrato, fale com o DP.",
            "—",
            ["Competência", "Parcela", "Valor", "Quando saiu", "Situação", "Comprovante"],
            "1fr 0.9fr 1fr 1.2fr 1fr 1.6fr",
            f"""SELECT lpad(p.mes::text,2,'0') || '/' || p.ano,
                       CASE p.parcela WHEN 1 THEN 'Adiantamento (40%)'
                                      WHEN 2 THEN 'Saldo (60%)' ELSE p.parcela::text END,
                       p.valor_liquido, p.data_pagamento, coalesce(p.status,'—'),
                       coalesce(p.pix_e2e_id,'—')
                  FROM payroll_payments p
                 WHERE p.employee_id = {me_lit}
                 ORDER BY p.ano DESC, p.mes DESC, p.parcela""",
            lambda r: [
                t(str(r[0]), 600, "#0F1B3A"),
                t(str(r[1])),
                t(brl(float(r[2] or 0)), 600),
                t(_fmtdate(r[3], "%d/%m/%Y %H:%M") if r[3] else "ainda não saiu"),
                b(
                    "pago" if str(r[4]) == "pago" else str(r[4]).replace("_", " "),
                    "ok" if str(r[4]) == "pago" else "warn",
                ),
                t(str(r[5])[:34]),
            ],
        ),
    )

    out["meus-dados"] = {
        "title": "Meus dados",
        "sub": "Contato e endereço — o DP vê a alteração na ficha. Nome, CPF e cargo só o DP altera.",
        "cta": "Salvar",
        "type": "form",
        "submit": {"endpoint": f"{_SS}/meus-dados", "method": "PUT", "okMsg": "Dados atualizados"},
        "fields": [
            {"key": "celular", "label": "Celular (WhatsApp)", "type": "text", "span": "span 1"},
            {"key": "telefone", "label": "Telefone", "type": "text", "span": "span 1"},
            {"key": "email", "label": "E-mail", "type": "text", "span": "span 2"},
            {"key": "cep", "label": "CEP", "type": "text", "span": "span 1"},
            {"key": "logradouro", "label": "Rua/Av.", "type": "text", "span": "span 1"},
            {"key": "numero", "label": "Número", "type": "text", "span": "span 1"},
            {"key": "complemento", "label": "Complemento", "type": "text", "span": "span 1"},
            {"key": "bairro", "label": "Bairro", "type": "text", "span": "span 1"},
            {"key": "cidade", "label": "Cidade", "type": "text", "span": "span 1"},
            {"key": "uf", "label": "UF", "type": "text", "span": "span 1"},
        ],
    }

    return out


async def _build_suprimentos(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_est = await _scalar(db, "SELECT count(*) FROM nfe_compras_estoque")
    n_req = await _scalar(db, "SELECT count(*) FROM purchase_requisitions")

    async def _visao():
        val = await _scalar(
            db, "SELECT coalesce(sum(qty_on_hand*coalesce(avg_cost,unit_cost,0)),0) FROM nfe_compras_estoque"
        )
        n_fin = await _scalar(db, "SELECT count(*) FROM fin_stock_items")
        top = (
            await db.execute(
                text(
                    "SELECT descricao, qty_on_hand, coalesce(avg_cost,unit_cost,0) FROM nfe_compras_estoque ORDER BY qty_on_hand*coalesce(avg_cost,unit_cost,0) DESC NULLS LAST LIMIT 6"
                )
            )
        ).fetchall()
        return {
            "title": "Visão geral",
            "sub": "Suprimentos — dados reais",
            "cta": "Atualizar",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_est), "l": "Itens no estoque (NF-e)", "icon": IC["shield"], "color": "#0F1B3A"},
                {"v": brl(val), "l": "Valor em estoque", "icon": _ICF["money"], "color": "#16A34A"},
                {"v": str(n_req), "l": "Requisições", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": str(n_fin), "l": "Itens financeiros", "icon": _ICF["hand"], "color": "#0F1B3A"},
            ],
            "panels": [
                {
                    "title": "Itens de maior valor",
                    "rows": [
                        {"left": (d or "—")[:40], "right": brl((q or 0) * (cst or 0)), **S["info"]} for d, q, cst in top
                    ]
                    or [{"left": "Sem estoque", "right": brl(0), **S["mut"]}],
                },
                {
                    "title": "Requisições",
                    "rows": [
                        {"left": "Requisições de compra", "right": str(n_req), **(S["ok"] if n_req == 0 else S["warn"])}
                    ],
                },
            ],
        }

    await safe("visao", _visao())
    await safe(
        "almoxarifado",
        tbl(
            "Almoxarifado",
            f"{n_est} itens (NF-e)",
            "Atualizar",
            ["Item", "NCM", "Un", "Qtd", "Custo médio", "Última compra"],
            "2.4fr 1fr 0.5fr 0.7fr 1fr 1fr",
            "SELECT coalesce(descricao, item_code, '—'), coalesce(ncm,'—'), coalesce(unidade,'—'), qty_on_hand, coalesce(avg_cost,unit_cost,0), last_purchase_date "
            "FROM nfe_compras_estoque ORDER BY last_purchase_date DESC NULLS LAST LIMIT 200",
            lambda r: [
                t((r[0] or "—")[:55], 600, "#0F1B3A"),
                t(r[1]),
                t(r[2]),
                t(str(r[3]) if r[3] is not None else "—"),
                t(brl(r[4]) if r[4] is not None else "—"),
                t(_fmtdate(r[5])),
            ],
        ),
    )
    return out


async def _build_integracoes(db: AsyncSession) -> dict:
    out, safe, tbl = _helpers(db)
    n_sol = await _scalar(db, "SELECT count(*) FROM solides_employees")
    n_esc = await _scalar(db, "SELECT count(*) FROM solides_work_schedules")

    async def _visao():
        n_cpf = await _scalar(db, "SELECT count(DISTINCT cpf) FROM solides_employees WHERE cpf IS NOT NULL")
        return {
            "title": "Visão geral",
            "sub": "Integrações — dados reais",
            "cta": "Atualizar",
            "type": "dash",
            "panelGrid": "1fr 1fr",
            "kpis": [
                {"v": str(n_sol), "l": "Colaboradores Sólides", "icon": IC["users"], "color": "#0F1B3A"},
                {"v": str(n_esc), "l": "Escalas Sólides", "icon": IC["cal"], "color": "#0F1B3A"},
                {"v": str(n_cpf), "l": "CPFs sincronizados", "icon": IC["shield"], "color": "#16A34A"},
                {"v": "Ativo", "l": "Conector Sólides", "icon": _ICF["hand"], "color": "#16A34A"},
            ],
            "panels": [
                {
                    "title": "Conectores ativos",
                    "rows": [
                        {"left": "Sólides (RH/ponto)", "right": "Ativo", **S["ok"]},
                        {"left": "Banco Inter (financeiro)", "right": "Ativo", **S["ok"]},
                    ],
                },
                {
                    "title": "Sólides — escopo do sync",
                    "rows": [
                        {"left": "Identidade (nome/email/CPF)", "right": f"{n_sol}", **S["ok"]},
                        {"left": "Escalas de trabalho", "right": f"{n_esc}", **S["info"]},
                    ],
                },
            ],
        }

    await safe("visao", _visao())
    await safe(
        "solides",
        tbl(
            "Sólides · Colaboradores sincronizados",
            f"{n_sol} colaboradores · {n_esc} escalas (sync RH/ponto)",
            "Sincronizar",
            ["Colaborador", "Email", "CPF"],
            "1.8fr 2fr 1.2fr",
            "SELECT coalesce(nome,'—'), coalesce(email,'—'), coalesce(cpf,'—') FROM solides_employees ORDER BY nome LIMIT 300",
            lambda r: [t(r[0], 600, "#0F1B3A", initials(r[0])), t(r[1]), t(r[2])],
        ),
    )
    return out


BUILDERS = {
    "operacional": _build_operacional,
    "financeiro": _build_financeiro,
    "departamento-pessoal": _build_dp,
    "crm": _build_crm,
    "fiscal": _build_fiscal,
    "gestao-de-pessoas": _build_gp,
    "recrutamento": _build_recrutamento,
    "rh": _build_rh,
    "juridico": _build_juridico,
    "empresas": _build_empresas,
    "saude-ocupacional": _build_saude,
    "documentos": _build_documentos,
    "campo": _build_campo,
    "servicos": _build_servicos,
    "bi": _build_bi,
    "analytics": _build_analytics,
    "relatorios": _build_relatorios,
    "configuracoes": _build_configuracoes,
    "seguranca": _build_seguranca,
    "licitacoes": _build_licitacoes,
    "portal-do-funcionario": _build_portal_funcionario,
    "meu-espaco": _build_meu_espaco,
    "suprimentos": _build_suprimentos,
    "integracoes": _build_integracoes,
}


# =============================================================================
# ESCRITA (mutações) — Onda 1: ocorrência (baixo risco, sem dinheiro/legal).
# Import LAZY dentro da função: não arrisca o boot do backend; no pior caso
# só este endpoint falha, nunca derruba o app. Dinheiro/folha/fiscal NÃO
# passam por aqui — esses seguem o fluxo comprovado com gate OTP.
# =============================================================================
@router.post("/action/occurrence")
async def rd_action_occurrence(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import uuid as _uuid

    import modules.operacional.occurrences.controllers.occurrence_controller as _OC  # noqa: N812  # pré-existente: alias curto de import
    from modules.operacional.occurrences.repositories.occurrence_repository import OccurrenceRepository

    desc = (payload.get("description") or "").strip()
    post_id = payload.get("post_id")
    if not post_id:
        raise HTTPException(status_code=400, detail="Selecione o posto da ocorrência.")
    if len(desc) < 10:
        raise HTTPException(status_code=400, detail="A descrição precisa de ao menos 10 caracteres.")
    title = (payload.get("title") or desc).strip()[:120]
    if len(title) < 5:
        title = (title + " · ocorrência")[:120]
    try:
        data = _OC.OccurrenceCreate(
            tenant_id=getattr(current_user, "condominio_id", None) or _uuid.uuid4(),
            reported_by_id=current_user.id,
            post_id=str(post_id),
            title=title,
            description=desc,
            occurrence_type=payload.get("occurrence_type") or "incidente",
            severity=payload.get("severity") or "moderada",
            category=payload.get("category") or "operacional",
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    occ = await OccurrenceRepository(db).create(data, inspector_id=str(current_user.id))
    return {"ok": True, "id": str(occ.id), "code": getattr(occ, "code", None), "message": "Ocorrência registrada"}


@router.post("/action/aviso-ferias")
async def rd_action_aviso_ferias(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Gera o Aviso Prévio de Férias (HTML) de uma férias REAL e devolve o doc p/ o front abrir.
    payload.ferias = 'employee_id|YYYY-MM-DD|dias' (do select de férias aprovadas). Sem digitação
    livre — os dados vêm de hr_vacation_requests. Retorna {ok, message, doc:{url, fmt}} → o
    FormScreen abre o documento gerado (gancho d.doc)."""
    import uuid as _uuid

    raw = (payload.get("ferias") or "").strip()
    parts = raw.split("|")
    if len(parts) != 3 or not parts[0]:
        raise HTTPException(status_code=400, detail="Selecione uma férias válida.")
    employee_id, data_inicio, dias_s = parts[0].strip(), parts[1].strip(), parts[2].strip()
    try:
        _uuid.UUID(employee_id)
    except (ValueError, AttributeError):
        raise HTTPException(status_code=400, detail="Colaborador inválido.")
    try:
        dias = max(1, min(30, int(dias_s)))
    except ValueError:
        dias = 30

    from modules.people_management.hr.services.contract_generator_service import (
        ContractGeneratorService,
    )

    try:
        result = await ContractGeneratorService(db).gerar_aviso_previo_ferias_html(
            employee_id=employee_id,
            data_inicio_ferias=data_inicio,
            dias=dias,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Erro ao gerar aviso: {exc}") from exc

    url = getattr(result, "file_url", None)
    nome = getattr(result, "employee_name", "") or ""
    if not url:
        raise HTTPException(status_code=500, detail="Aviso gerado sem URL de download.")
    return {
        "ok": True,
        "message": f"Aviso prévio de férias gerado — {nome}.",
        "doc": {"label": "Aviso prévio de férias", "url": url, "fmt": "html", "mode": "blob"},
    }


@router.post("/action/contracheques-batch")
async def rd_action_contracheques_batch(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Gera contracheques em LOTE de todos os ativos da competência (PDF + arquiva no GED + publica
    eventos). AÇÃO de efeito em massa → o front exige confirmação humana antes (scr.submit.confirm).
    Reusa a lógica provada de gerar_contracheques_batch. payload.competencia = 'AAAA-MM'."""
    import re as _re

    comp = (payload.get("competencia") or "").strip()
    if not _re.match(r"^\d{4}-(0[1-9]|1[0-2])$", comp):
        raise HTTPException(status_code=400, detail="Competência inválida. Use AAAA-MM.")

    from modules.people_management.hr.controllers.payroll_export_controller import (
        gerar_contracheques_batch,
    )

    try:
        res = await gerar_contracheques_batch(comp, current_user, db)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"Erro ao gerar contracheques: {exc}") from exc

    ger = res.get("contracheques_gerados", 0)
    tot = res.get("total_funcionarios", 0)
    arq = res.get("arquivados_ged", 0)
    return {"ok": True, "message": f"Contracheques {comp}: {ger}/{tot} gerados, {arq} arquivados no GED."}


@router.post("/action/kpis-recalcular")
async def rd_action_kpis_recalcular(current_user: CurrentActiveUser) -> dict:
    """Dispara a task `analytics.recalcular_kpis` (a mesma do beat das 06:15). A tela
    Relatórios apontava para /analytics/executive/kpis/recalcular, que nunca existiu (404
    medido em 07/09/2026). Só recalcula — não altera lançamento."""
    from modules.analytics.tasks import recalcular_kpis_task

    r = recalcular_kpis_task.delay()
    return {"ok": True, "message": "Recálculo dos KPIs enfileirado.", "task_id": str(r.id)}


@router.post("/action/desconto-criar")
async def rd_action_desconto_criar(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Cria um desconto recorrente (consignado, pensão, empréstimo) para um colaborador.

    LIGAR 14/09/2026. `POST /hr/employees/{employee_id}/deductions` existe e leva o
    colaborador no CAMINHO da URL — e o formulário do redesign manda os campos no corpo,
    nunca no path. Sem esta ponte, os 97 descontos ativos que a folha desconta todo mês
    só podiam ser criados pelo banco.

    Chama o MESMO service do endpoint real: a regra de negócio não é duplicada aqui.
    """
    from modules.people_management.hr.controllers.employee_controller import (  # noqa: PLC0415
        DeductionCreate,
        create_deduction,
    )

    eid = str(payload.get("employee_id") or "").strip()
    if not eid:
        return {"ok": False, "message": "Escolha o colaborador."}
    dados = {k: v for k, v in payload.items() if k != "employee_id" and v not in ("", None)}
    # O form manda tudo como texto; os numéricos precisam chegar como número.
    for campo in ("valor", "percentual"):
        if campo in dados:
            try:
                dados[campo] = (
                    float(str(dados[campo]).replace(".", "").replace(",", "."))
                    if "," in str(dados[campo])
                    else float(dados[campo])
                )
            except (TypeError, ValueError):
                return {"ok": False, "message": f"{campo}: informe um número."}
    if "total_parcelas" in dados:
        try:
            dados["total_parcelas"] = int(dados["total_parcelas"])
        except (TypeError, ValueError):
            return {"ok": False, "message": "Parcelas: informe um número inteiro."}
    try:
        r = await create_deduction(eid, DeductionCreate(**dados), current_user, db)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "message": f"Não criei o desconto: {e}"}
    return {"ok": True, "message": "Desconto criado.", "detalhe": r if isinstance(r, dict) else None}


@router.post("/action/cert-gerar-folha")
async def rd_action_cert_gerar_folha(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Gera a fila de certificações (hr_certifications) de TODOS os holerites de uma competência —
    AÇÃO de efeito em massa → o front exige confirmação humana antes (scr.submit.confirm). O endpoint
    real (certification_controller) recebe a competência como PATH param; aqui ela chega no body do
    form redesign, então chamamos o serviço direto (mesma lógica de gerar_da_folha, idempotente)."""
    competencia = (payload.get("competencia") or "").strip()
    if not competencia:
        # Guard probe-safe: sem competência não chama o serviço (nada é gerado).
        return {"ok": False, "message": "Competência obrigatória."}

    from modules.people_management.certification.services.certification_service import (
        CertificationService,
    )

    res = await CertificationService(db).gerar_da_folha(competencia)
    await db.commit()
    return {"ok": True, "message": "Certificações geradas.", "detalhe": res if isinstance(res, dict) else None}


@router.post("/action/lead")
async def rd_action_lead(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.crm.repositories.lead_repository import LeadRepository
    from modules.crm.schemas.lead import LeadCreate

    name = (payload.get("name") or "").strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Informe o nome do lead (mínimo 2 caracteres).")
    kwargs: dict = {"name": name, "source": payload.get("source") or "other"}
    for k in ("email", "company", "position", "notes"):
        v = (payload.get(k) or "").strip()
        if v:
            kwargs[k] = v
    phone = "".join(c for c in (payload.get("phone") or "") if c.isdigit())
    if 10 <= len(phone) <= 15:
        kwargs["phone"] = phone
    ev = payload.get("expected_value")
    if ev not in (None, ""):
        try:
            kwargs["expected_value"] = float(_brl_norm(str(ev)))
        except (ValueError, TypeError):
            pass
    try:
        data = LeadCreate(**kwargs)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    repo = LeadRepository(db)
    # Guard de e-mail PRESERVADO (contrato atual do endpoint: e-mail repetido = 400).
    if data.email and await repo.get_by_email(data.email):
        raise HTTPException(status_code=400, detail="Já existe um lead com este e-mail.")
    # create_or_get acrescenta o dedup por TELEFONE (mesmo telefone = mesmo lead).
    # Quando reaproveita, a resposta DIZ isso — devolver "criado com sucesso" sem ter
    # criado nada é o falso positivo que confunde quem está na tela.
    lead, criado = await repo.create_or_get(data)
    if criado:
        return {"ok": True, "id": str(lead.id), "message": "Lead criado com sucesso"}
    return {
        "ok": True,
        "id": str(lead.id),
        "message": (
            f"Este telefone já é do lead “{lead.name}” — reaproveitado em vez de "
            f"duplicar (origem {lead.source} preservada)."
        ),
    }


@router.post("/action/task")
async def rd_action_task(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from datetime import date as _date

    from modules.crm.models.activity_task import CrmTask

    title = (payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Informe o título da tarefa.")
    due = None
    dd = (payload.get("due_date") or "").strip()
    if dd:
        try:
            due = _date.fromisoformat(dd)
        except ValueError:
            raise HTTPException(status_code=400, detail="Data de vencimento inválida.")
    task = CrmTask(
        title=title[:255],
        description=(payload.get("description") or "").strip() or None,
        due_date=due,
        priority=payload.get("priority") or "medium",
        assigned_to_id=str(current_user.id),
        created_by_id=str(current_user.id),
        client_id=payload.get("client_id") or None,
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)
    return {"ok": True, "id": str(task.id), "message": "Tarefa criada com sucesso"}


@router.post("/action/occurrence-resolve")
async def rd_action_occ_resolve(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import modules.operacional.occurrences.controllers.occurrence_controller as _OC  # noqa: N812  # pré-existente: alias curto de import
    from modules.operacional.occurrences.repositories.occurrence_repository import OccurrenceRepository

    occ_id = payload.get("occurrence_id")
    if not occ_id:
        raise HTTPException(status_code=400, detail="Selecione a ocorrência.")
    action = (payload.get("corrective_action") or "").strip()
    if len(action) < 5:
        raise HTTPException(status_code=400, detail="Descreva a ação corretiva (mínimo 5 caracteres).")
    data = _OC.OccurrenceResolve(
        corrective_action=action,
        resolution_notes=(payload.get("resolution_notes") or "").strip() or None,
    )
    occ = await OccurrenceRepository(db).resolve(str(occ_id), data, resolved_by_id=current_user.id)
    if not occ:
        raise HTTPException(status_code=404, detail="Ocorrência não encontrada ou já resolvida.")
    return {"ok": True, "id": str(occ.id), "message": "Ocorrência resolvida com sucesso"}


@router.post("/action/occurrence-comment")
async def rd_action_occ_comment(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import uuid as _uuid
    from datetime import datetime as _dt

    occ_id = payload.get("occurrence_id")
    content = (payload.get("content") or "").strip()
    if not occ_id:
        raise HTTPException(status_code=400, detail="Selecione a ocorrência.")
    if len(content) < 2:
        raise HTTPException(status_code=400, detail="Escreva o comentário.")
    await db.execute(
        text(
            "INSERT INTO occurrence_comments (id, occurrence_id, author_id, author_name, content, is_internal, created_at, is_active) "
            "VALUES (:id, :oid, :aid, :an, :c, FALSE, :ts, TRUE)"
        ),
        {
            "id": str(_uuid.uuid4()),
            "oid": str(occ_id),
            "aid": str(current_user.id),
            "an": getattr(current_user, "name", None),
            "c": content,
            "ts": _dt.utcnow(),
        },
    )
    await db.commit()
    return {"ok": True, "message": "Comentário adicionado"}


@router.post("/action/client-note")
async def rd_action_client_note(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    import uuid as _uuid
    from datetime import datetime as _dt

    cid = payload.get("client_id")
    nota = (payload.get("nota") or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="Selecione o cliente.")
    if len(nota) < 3:
        raise HTTPException(status_code=400, detail="Escreva a anotação (mínimo 3 caracteres).")
    row = (await db.execute(text("SELECT name FROM clients WHERE id=:i"), {"i": cid})).first()
    cliente_nome = row[0] if row else None
    await db.execute(
        text(
            "INSERT INTO crm_client_notes (id, cliente_id, cliente_nome, nota, autor, created_at) "
            "VALUES (:id, :cid, :nome, :nota, :autor, :ts)"
        ),
        {
            "id": str(_uuid.uuid4()),
            "cid": str(cid),
            "nome": cliente_nome,
            "nota": nota,
            "autor": getattr(current_user, "email", None),
            "ts": _dt.utcnow(),
        },
    )
    await db.commit()
    return {"ok": True, "message": "Anotação salva"}


@router.post("/action/proposal")
async def rd_action_proposal(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.crm.repositories.proposal_repository import ProposalRepository
    from modules.crm.schemas.proposal import ProposalCreate, ProposalItemCreate

    title = (payload.get("title") or "").strip()
    if len(title) < 2:
        raise HTTPException(status_code=400, detail="Informe o título da proposta.")
    client_name = (payload.get("client_name") or "").strip()
    client_document = (payload.get("client_document") or "").strip()
    client_id = payload.get("client_id")
    if client_id:
        # Busca nome E documento. Antes só o nome era buscado, e a proposta nascia com
        # `client_document` vazio — o que a tornava INVISÍVEL em «Gerar contrato a partir da
        # proposta», cujo filtro é `coalesce(client_document,'') <> ''`. Ou seja: proposta
        # criada por esta tela nunca virava contrato. Medido em 14/09/2026: das 5 propostas
        # mais recentes, 3 (todas as criadas pela tela) estavam sem documento.
        row = (
            await db.execute(
                text("SELECT name, coalesce(document_number,'') FROM clients WHERE id=:i"),
                {"i": client_id},
            )
        ).first()
        if row:
            client_name = client_name or row[0]
            client_document = client_document or row[1]
    if not client_name:
        raise HTTPException(status_code=400, detail="Selecione o cliente da proposta.")
    try:
        valor = float(_brl_norm(str(payload.get("valor") or "0")))
    except (ValueError, TypeError):
        valor = 0.0
    item_name = (payload.get("item_name") or title).strip()[:255]
    # `proposal_items.empresa_id` é NOT NULL. O repositório já avisava no comentário que
    # "quem chega aqui sem empresa já foi recusado antes" — só que esta ação não recusava:
    # mandava None e o banco devolvia NotNullViolationError, que virava 500 sem explicação.
    # Agora a empresa é exigida aqui, com mensagem, antes de chegar no banco.
    empresa_id = (payload.get("empresa_id") or "").strip()
    tem_item = valor > 0 or payload.get("item_name")
    if tem_item and not empresa_id:
        raise HTTPException(status_code=400, detail="Selecione a empresa emissora da proposta.")
    items = (
        [ProposalItemCreate(name=item_name, quantity=1, unit_price=valor, empresa_id=empresa_id)] if tem_item else []
    )
    try:
        data = ProposalCreate(
            title=title[:255],
            client_name=client_name[:255],
            client_document=(client_document or None),
            description=(payload.get("description") or "").strip() or None,
            items=items,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    proposal = await ProposalRepository(db).create(data, created_by_id=str(current_user.id))
    return {
        "ok": True,
        "id": str(proposal.id),
        "number": getattr(proposal, "number", None),
        "message": "Proposta criada com sucesso",
    }


@router.post("/action/contrato-da-proposta")
async def rd_action_contrato_da_proposta(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Transforma uma proposta em contrato, já ligado ao modelo e ao CNPJ emitente.

    Era o elo que faltava no funil: o CRM ia de lead a proposta e parava ali — para virar
    contrato era preciso trocar de módulo. O cliente e o valor vêm da PROPOSTA, não digitados
    de novo; a modalidade é escolhida porque a proposta não a declara de forma confiável.
    """
    from modules.crm.services import contract_wizard as W  # noqa: N812  # pré-existente: alias curto de import

    pid = (payload.get("proposal_id") or "").strip()
    modalidade = (payload.get("modalidade") or "").strip()
    inicio = (payload.get("vigencia_inicio") or "").strip()
    if not pid or not modalidade or not inicio:
        raise HTTPException(status_code=400, detail="Informe a proposta, a modalidade e o início da vigência.")
    try:
        W.exigir_emitente(current_user)
    except W.NaoAutorizado as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    pr = (
        (
            await db.execute(
                text(
                    "SELECT p.id::text, p.number, coalesce(p.total,0) AS total, "
                    "coalesce(p.client_document,'') AS doc, coalesce(p.client_company,'') AS empresa, "
                    "(SELECT count(*) FROM contracts c WHERE c.proposal_id = p.id) AS ja "
                    ", (SELECT string_agg(DISTINCT coalesce(c.empresa_id::text,'?'), ',') "
                    "     FROM contracts c WHERE c.proposal_id = p.id) AS emitentes "
                    "FROM proposals p WHERE p.id::text = :i"
                ),
                {"i": pid},
            )
        )
        .mappings()
        .first()
    )
    if not pr:
        raise HTTPException(status_code=404, detail="Proposta não encontrada.")
    # UMA PROPOSTA = UM CONTRATO **POR EMITENTE**, não um contrato e ponto.
    #
    # A trava original supunha que toda proposta vira um único instrumento. O negócio do
    # Jordan não é assim, e a regra é dele, antiga e explícita: a proposta PODE misturar, o
    # contrato e a nota fiscal NUNCA. Agente de portaria é CLT no posto e sai pela
    # Patrimonial; portaria remota é eletrônica e sai pela Eletrônica — duas naturezas
    # fiscais, dois CNPJs, dois instrumentos, duas notas.
    #
    # Caso real que trouxe isto (10/09/2026): Kopenhagen, PROP-2026-00096, R$ 45.312/mês =
    # R$ 40.612 de agentes (Patrimonial) + R$ 4.700 de portaria remota (Eletrônica). Gerar
    # o segundo contrato batia em 409, e o dono ficava sem caminho pela tela.
    #
    # O que a trava protege continua protegido: clique repetido na MESMA modalidade segue
    # barrado, porque a comparação passou a ser por empresa emitente.
    if pr["ja"]:
        # `.get` nos DOIS níveis: modalidade fora do catálogo chega aqui antes de
        # `criar_contrato` validá-la, e um KeyError viraria 500 em vez da mensagem em
        # português que o wizard já sabe dar.
        _cat = W.CATALOGO.get(modalidade) or {}
        _emit_novo = W.EMPRESA_POR_TIPO.get(_cat.get("modelo_service_type") or "")
        _ja_emitentes = {e for e in (pr["emitentes"] or "").split(",") if e}
        if _emit_novo and _emit_novo in _ja_emitentes:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"A proposta {pr['number']} já gerou contrato para este emitente. "
                    "Para a outra parte do serviço, escolha a modalidade do outro CNPJ."
                ),
            )
    if not pr["doc"]:
        raise HTTPException(
            status_code=422,
            detail=f"A proposta {pr['number']} não tem o CNPJ do cliente — sem ele não dá "
            "para saber para quem é o contrato.",
        )
    # valor do formulário só quando informado; o padrão é o VALOR DA PROPOSTA
    valor = payload.get("valor_mensal")
    valor = float(str(valor).replace(",", ".")) if str(valor or "").strip() else float(pr["total"])
    if valor <= 0:
        raise HTTPException(status_code=422, detail="A proposta está com valor zerado — informe o valor mensal.")

    r = await W.criar_contrato(
        db,
        cliente_documento=pr["doc"],
        modalidade=modalidade,
        valor_mensal=valor,
        vigencia_inicio=inicio[:10],
        vigencia_meses=int(payload.get("vigencia_meses") or 12),
        dia_vencimento=int(payload["dia_vencimento"]) if payload.get("dia_vencimento") else None,
        renovacao_aviso_dias=int(payload.get("renovacao_aviso_dias") or 30),
        proposal_id=pid,
    )
    if r.get("status") != "criado":
        raise HTTPException(status_code=400, detail=r.get("resumo") or r.get("status"))
    pend = r.get("perguntas") or []
    return {
        "ok": True,
        "message": (
            f"{r['contrato']} criado a partir da proposta {pr['number']} para {r['cliente']} "
            f"({r['vigencia']}). "
            + (
                "Pronto para baixar o PDF em Contratos."
                if r.get("pronto_para_emitir")
                else "Faltam: " + "; ".join(x["pergunta"] for x in pend[:4])
            )
        ),
    }


@router.post("/action/contrato-abrir-assinatura")
async def rd_action_contrato_abrir_assinatura(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Abre a assinatura eletrônica do contrato pelo CRM.

    Chama a MESMA rota de negócio de /crm/contracts — o portão de emitente e a ordem dos
    signatários vivem lá, para as superfícies não divergirem.
    """
    from modules.crm.services import contract_signature as CS  # noqa: N812  # pré-existente: alias curto de import
    from modules.crm.services import contract_wizard as W  # noqa: N812  # pré-existente: alias curto de import
    from modules.crm.services.contract_render import RenderError, renderizar_contrato

    num = (payload.get("contrato") or "").strip()
    if not num:
        raise HTTPException(status_code=400, detail="Selecione o contrato.")
    try:
        W.exigir_emitente(current_user)
    except W.NaoAutorizado as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    # "Já tem assinatura aberta" tem de significar ABERTA — cancelada e expirada não são.
    # A contagem era de TODAS as solicitações, então um contrato com assinatura cancelada
    # ficava preso: não dava para reabrir ("já tem") e não dava para enviar (o link estava
    # morto). Foi o caso do CTR-2026-00019, travado desde 23/08, e o botão "Reabrir
    # assinatura" que a Central oferece batia exatamente nesta linha.
    ja = (
        await db.execute(
            text(
                "SELECT count(*) FROM sig_signature_requests WHERE reference_code = :k "
                "  AND upper(coalesce(status::text,'')) NOT IN "
                "      ('CANCELLED','CANCELED','CANCELADA','EXPIRED','EXPIRADA')"
            ),
            {"k": num},
        )
    ).scalar()
    if ja:
        raise HTTPException(status_code=409, detail=f"{num} já tem assinatura aberta. Use “Enviar link de assinatura”.")
    try:
        res = await renderizar_contrato(db, num)
    except RenderError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    d = (
        (
            await db.execute(
                text("""
        SELECT cl.name AS cliente,
          (SELECT k.name FROM crm_contacts k WHERE k.client_id = c.client_id
            AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%' OR k.role ILIKE '%presidente%' OR k.role ILIKE '%diretor%' OR k.role ILIKE '%s%cio%' OR k.role ILIKE '%administrador%' OR k.role ILIKE '%procurador%' OR k.role ILIKE '%titular%') LIMIT 1) AS rep,
          (SELECT k.notes FROM crm_contacts k WHERE k.client_id = c.client_id
            AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%' OR k.role ILIKE '%presidente%' OR k.role ILIKE '%diretor%' OR k.role ILIKE '%s%cio%' OR k.role ILIKE '%administrador%' OR k.role ILIKE '%procurador%' OR k.role ILIKE '%titular%') LIMIT 1) AS cpf,
          (SELECT k.email FROM crm_contacts k WHERE k.client_id = c.client_id
            AND (k.role ILIKE '%representante%' OR k.role ILIKE '%s%ndic%' OR k.role ILIKE '%legal%' OR k.role ILIKE '%presidente%' OR k.role ILIKE '%diretor%' OR k.role ILIKE '%s%cio%' OR k.role ILIKE '%administrador%' OR k.role ILIKE '%procurador%' OR k.role ILIKE '%titular%') LIMIT 1) AS mail
        FROM contracts c LEFT JOIN clients cl ON cl.id = c.client_id
        WHERE c.contract_number = :n"""),
                {"n": num},
            )
        )
        .mappings()
        .first()
    )
    if not d or not d["rep"]:
        raise HTTPException(
            status_code=422,
            detail="O cliente não tem representante legal/síndico cadastrado em Contatos — "
            "é quem assina pelo condomínio. Cadastre antes de abrir a assinatura.",
        )

    sol = await CS.abrir_assinatura(
        db,
        num,
        res.pdf,
        contratante_nome=d["cliente"] or "",
        representante=d["rep"],
        representante_cpf=(d["cpf"] or ""),
        representante_email=(payload.get("email_cliente") or "").strip() or d["mail"],
        contratada_nome=res.contratada.razao_social,
        assinante_empresa=getattr(current_user, "full_name", None) or "Conecta Mais",
        assinante_empresa_id=getattr(current_user, "id", None),
        solicitado_por=getattr(current_user, "id", None),
    )
    await db.commit()

    # Manda o link da CONTRATADA para quem ABRIU, no ato. Pedido do Jordan em 09/09/2026,
    # depois de clicar "Abrir assinatura" às 23:56 e esperar um e-mail que não vinha: abrir
    # só criava as solicitações e devolvia os links num texto na tela. Quem abre a
    # assinatura quer assinar — o segundo botão era cerimônia.
    #
    # ⚠️ Só o link da CONTRATADA, e só para o próprio operador. O do CLIENTE continua
    # exigindo clique separado: mandar contrato ao cliente é ação para fora e irreversível,
    # e o cliente nem deveria receber antes de a Conecta Mais assinar.
    aviso = ""
    destino = (getattr(current_user, "email", "") or "").strip()
    if destino:
        try:
            enviado = await CS.convidar_para_assinar(
                db,
                num,
                para=destino,
                link=sol.link_empresa,
                nome=getattr(current_user, "full_name", "") or "",
                papel="CONTRATADA",
            )
            await db.commit()
            aviso = f" O link para VOCÊ assinar foi enviado para {destino}." if enviado else ""
        except Exception as e:  # noqa: BLE001 — e-mail que falha não derruba a abertura
            logger.warning(f"abrir-assinatura {num}: convite à contratada falhou: {e}")

    return {
        "ok": True,
        "message": (
            f"Assinatura de {num} aberta.{aviso} Link da CONTRATADA: {sol.link_empresa} · "
            f"link do cliente: {sol.link_cliente} (só funciona depois que a Conecta Mais assinar)."
        ),
    }


@router.post("/action/contrato-enviar-link")
async def rd_action_contrato_enviar_link(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Manda o link ao signatário, ou devolve para envio manual por WhatsApp."""
    from modules.crm.services import contract_signature as CS  # noqa: N812  # pré-existente: alias curto de import
    from modules.crm.services import contract_wizard as W  # noqa: N812  # pré-existente: alias curto de import

    num = (payload.get("contrato") or "").strip()
    if not num:
        raise HTTPException(status_code=400, detail="Selecione o contrato.")
    try:
        W.exigir_emitente(current_user)
    except W.NaoAutorizado as e:
        raise HTTPException(status_code=403, detail=str(e)) from e

    parte = (payload.get("parte") or "cliente").lower()
    papel = "customer" if parte.startswith(("cli", "contratante")) else "company"
    linha = (
        (
            await db.execute(
                text(
                    "SELECT access_token, signer_name, signer_email, signed_at IS NOT NULL AS assinou, "
                    "       upper(coalesce(status::text,'')) AS situacao "
                    "FROM sig_signature_requests WHERE reference_code = :k AND signer_type = :p "
                    "ORDER BY created_at DESC"
                ),
                {"k": num, "p": papel},
            )
        )
        .mappings()
        .first()
    )
    # PAREDE contra solicitação CANCELADA. Eu tinha posto esta guarda no caminho do CHAT
    # (`_enviar_link_assinatura`) e NÃO aqui — e é este o código que o botão da tela usa.
    # Em 10/09/2026 o Jordan clicou "Enviar link" no CTR-2026-00019, cujas duas solicitações
    # estavam CANCELLED desde 23/08, e o sistema mandou ao cliente um convite com link
    # morto. A regra da casa é literal: quando a ação nasce num lugar e é executada em
    # outro, PROVE OS DOIS. Eu provei um.
    if linha and str(linha.get("situacao") or "") in (
        "CANCELLED",
        "CANCELED",
        "CANCELADA",
        "EXPIRED",
        "EXPIRADA",
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                f"A assinatura de {num} para esta parte está "
                f"{str(linha['situacao']).lower()} — o link não funcionaria. "
                "Reabra a assinatura antes de enviar."
            ),
        )
    if not linha or not linha["access_token"]:
        raise HTTPException(
            status_code=404, detail=f"{num} não tem link em aberto para esta parte. Abra a assinatura primeiro."
        )
    if linha["assinou"]:
        raise HTTPException(status_code=409, detail=f"{linha['signer_name']} já assinou.")
    if papel == "customer":
        pend = (
            await db.execute(
                text(
                    "SELECT signer_name FROM sig_signature_requests WHERE reference_code = :k "
                    "AND signer_type = 'company' AND signed_at IS NULL"
                ),
                {"k": num},
            )
        ).scalar()
        if pend:
            raise HTTPException(
                status_code=409,
                detail="A Conecta Mais ainda não assinou — o link do cliente seria recusado. Assine primeiro.",
            )

    link = f"{CS.BASE_PUBLICA}/assinar/contrato/{linha['access_token']}"
    # Mais de um destinatário, separados por vírgula ou ponto-e-vírgula. Pedido do Jordan em
    # 09/09/2026: no Maiápolis quem assina é a presidente e a VICE também precisa receber.
    # É lista explícita, digitada e visível na tela — não varredura automática dos contatos
    # do cliente, que mandaria o contrato para quem ninguém escolheu.
    bruto = (payload.get("email") or "").strip() or (linha["signer_email"] or "")
    destinos = [e.strip() for e in re.split(r"[;,]", bruto) if e.strip()]
    enviados: list[str] = []
    for destino in destinos:
        try:
            await CS.convidar_para_assinar(
                db,
                num,
                para=destino,
                link=link,
                nome=linha["signer_name"] or "",
                papel="CONTRATANTE" if papel == "customer" else "CONTRATADA",
            )
            enviados.append(destino)
        except Exception as e:  # noqa: BLE001 — um endereço ruim não pode matar os outros
            logger.warning(f"contrato-enviar-link {num}: falhou para {destino}: {e}")
    if enviados:
        # CÓPIA DE ARQUIVO para quem enviou. Pedido do Jordan em 10/09/2026, com o motivo
        # dele: a síndica do Maiápolis disse que não recebeu o convite, e não havia como
        # provar o contrário — log de servidor não é prova que se mostre a um cliente.
        # Agora cada envio deixa um comprovante impresso na caixa dele, com a lista de
        # destinatários e a hora. A cópia NÃO leva o link (é pessoal do signatário).
        # Manaus é UTC-4 e o container roda em UTC: sem o fuso, o comprovante que o dono
        # vai imprimir carimbaria uma hora que não foi a dele. `ZoneInfo` é stdlib e não
        # depende de helper interno — a primeira versão importava `core.timezone`, que NÃO
        # EXISTE, e derrubou o envio com 500 depois de o e-mail já ter saído.
        from datetime import datetime  # noqa: PLC0415
        from zoneinfo import ZoneInfo  # noqa: PLC0415

        quando = datetime.now(ZoneInfo("America/Manaus")).strftime("%d/%m/%Y às %H:%M")
        await CS.copia_de_envio(
            db, num, destinatarios=enviados, papel="CONTRATANTE" if papel == "customer" else "CONTRATADA", quando=quando
        )
        await db.commit()
        return {
            "ok": True,
            "message": (
                f"Convite enviado para {', '.join(enviados)}. Cópia do comprovante em {CS.COPIA_PARA}. Link: {link}"
            ),
        }
    return {"ok": True, "message": f"Sem e-mail informado — mande este link: {link}"}


@router.post("/action/lead-definir")
async def rd_action_lead_definir(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Dá destino a um lead parado: qualifica, descarta ou abre oportunidade.

    Em 23/08 havia 29 leads em `new` sem nenhuma ação na tela para tirá-los de lá — o CRM
    cadastrava lead e não sabia o que fazer com ele depois. `mover-oportunidade` só serve
    para quem JÁ virou oportunidade.

    Abrir oportunidade é opcional e explícito: qualificar não cria funil sozinho. Lead
    descartado exige motivo — "lost" sem porquê não ensina nada a quem for revisar.
    """
    from datetime import date as _date

    from modules.crm.models.lead import LeadStatus

    lead_id = (payload.get("lead_id") or "").strip()
    destino = (payload.get("destino") or "").strip()
    motivo = (payload.get("motivo") or "").strip()
    if not lead_id:
        raise HTTPException(status_code=400, detail="Selecione o lead.")
    try:
        novo = LeadStatus(destino)
    except ValueError:
        raise HTTPException(status_code=400, detail="Destino inválido. Use: " + ", ".join(x.value for x in LeadStatus))
    if novo == LeadStatus.LOST and not motivo:
        raise HTTPException(status_code=400, detail="Para descartar o lead, informe o motivo.")

    row = (
        (
            await db.execute(
                text(
                    "SELECT id::text, name, coalesce(company,'') AS company, coalesce(email,'') AS email, "
                    "coalesce(phone,'') AS phone, coalesce(expected_value,0) AS valor, "
                    "coalesce(status::text,'') AS status "
                    "FROM leads WHERE id::text = :i"
                ),
                {"i": lead_id},
            )
        )
        .mappings()
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Lead não encontrado.")

    nota = f"[{_date.today().isoformat()}] {novo.value}" + (f" — {motivo}" if motivo else "")
    await db.execute(
        text(
            # CAST explícito: dentro de concat_ws o Postgres não infere o tipo do parâmetro
            # e devolve IndeterminateDatatypeError
            "UPDATE leads SET status = :s, notes = trim(both E'\n' FROM "
            "concat_ws(E'\n', notes, CAST(:n AS text))), last_contact_at = now(), "
            "updated_at = now() WHERE id::text = :i"
        ),
        {"s": novo.value, "n": nota, "i": lead_id},
    )

    criou_opp = None
    if payload.get("abrir_oportunidade"):
        ja = (
            await db.execute(
                text("SELECT id::text FROM opportunities WHERE lead_id::text = :i AND coalesce(is_active,true)"),
                {"i": lead_id},
            )
        ).scalar()
        if ja:
            criou_opp = ja  # idempotente: não abre duas para o mesmo lead
        else:
            # contact_email é NOT NULL e muitos leads vêm de WhatsApp sem e-mail; string
            # vazia registra a ausência sem inventar endereço
            criou_opp = (
                await db.execute(
                    text("""
                INSERT INTO opportunities
                    (id, title, contact_name, contact_email, stage, priority, value,
                     probability, lead_id, is_active, created_at, updated_at, custom_fields)
                VALUES (gen_random_uuid(), :t, :cn, :ce, 'qualification', 'medium', :v, 20,
                        CAST(:l AS uuid), true, now(), now(), '{}'::jsonb)
                RETURNING id::text"""),
                    {
                        "t": (row["company"] or row["name"])[:120],
                        "cn": row["name"][:120],
                        "ce": row["email"],
                        "v": row["valor"],
                        "l": lead_id,
                    },
                )
            ).scalar()
    await db.commit()

    msg = f"Lead “{row['name']}” → {novo.value}"
    if motivo:
        msg += f" ({motivo})"
    if criou_opp:
        msg += " · oportunidade aberta em qualificação"
    return {"ok": True, "id": lead_id, "opportunity_id": criou_opp, "message": msg}


@router.post("/action/opportunity-stage")
async def rd_action_opp_stage(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.crm.models.opportunity import OpportunityStage
    from modules.crm.repositories.opportunity_repository import OpportunityRepository

    opp_id = payload.get("opportunity_id")
    stage = payload.get("stage")
    if not opp_id:
        raise HTTPException(status_code=400, detail="Selecione a oportunidade.")
    if not stage:
        raise HTTPException(status_code=400, detail="Selecione o estágio.")
    try:
        st = OpportunityStage(stage)
    except ValueError:
        raise HTTPException(status_code=400, detail="Estágio inválido.")
    opp = await OpportunityRepository(db).update_stage(str(opp_id), st, (payload.get("notes") or "").strip() or None)
    if not opp:
        raise HTTPException(status_code=404, detail="Oportunidade não encontrada.")
    # 08/09/2026: a rota do CRM cria o contrato no ganho e registra na timeline; a tela nova não fazia nenhum dos dois
    from modules.crm.services.pipeline_sync import ensure_contract_for_won_opportunity
    from modules.crm.services.timeline import log_activity

    try:
        await ensure_contract_for_won_opportunity(db, opp)
        await log_activity(db, "deal_stage", f"Deal movido para {st.value}", opportunity_id=str(opp.id))
    except TypeError:
        await log_activity(db, "deal_stage", f"Deal movido para {st.value}")
    except Exception as exc:  # noqa: BLE001
        logger.warning("pós-processamento do estágio falhou: %s", exc)
    return {"ok": True, "id": str(opp.id), "message": f"Oportunidade movida para “{st.value}”"}


@router.post("/action/diaria")
async def rd_action_diaria(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.operacional.diaristas import diarias_service as _ds

    diarista_id = payload.get("diarista_id")
    data_str = (payload.get("data") or "").strip()
    posto = (payload.get("posto") or "").strip()
    funcao = (payload.get("funcao") or "").strip()
    turno = (payload.get("turno") or "").strip() or None
    if not diarista_id:
        raise HTTPException(status_code=400, detail="Selecione o diarista.")
    if not data_str:
        raise HTTPException(status_code=400, detail="Informe a data.")
    if not posto:
        raise HTTPException(status_code=400, detail="Selecione o posto.")
    if not funcao:
        raise HTTPException(status_code=400, detail="Selecione a função.")
    try:
        did = int(diarista_id)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Diarista inválido.")
    res = await _ds.lancar(
        db,
        data=data_str,
        diarista_id=did,
        funcao=funcao,
        posto=posto,
        turno=turno,
        observacao=(payload.get("observacao") or "").strip() or None,
        user_id=str(current_user.id),
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("mensagem") or "Não foi possível lançar a diária.")
    vtvr = " · VT+VR no Financeiro" if res.get("vt_vr_enviado_financeiro") else ""
    return {"ok": True, "id": res.get("id"), "message": f"Diária lançada — R$ {float(res.get('valor', 0)):.2f}{vtvr}"}


@router.post("/action/diarista")
async def rd_action_diarista(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.operacional.diaristas import diarias_service as _ds

    res = await _ds.criar_diarista(
        db,
        nome=(payload.get("nome") or "").strip(),
        cpf=(payload.get("cpf") or "").strip() or None,
        pix=(payload.get("pix") or "").strip() or None,
        telefone=(payload.get("telefone") or "").strip() or None,
        email=(payload.get("email") or "").strip() or None,
    )
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("mensagem") or "Não foi possível cadastrar.")
    return {
        "ok": True,
        "id": res.get("id"),
        "message": "Diarista já estava cadastrado." if res.get("ja_existia") else "Diarista cadastrado com sucesso.",
    }


@router.post("/action/falta")
async def rd_action_falta(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # REUSA o endpoint comprovado (toda validação: hoje/ontem, sem presença/batida, escopo por posto)
    from modules.operacional.controllers.falta_substituto_controller import FaltaBody, registrar_falta

    shift_id = payload.get("shift_id")
    if not shift_id:
        raise HTTPException(status_code=400, detail="Selecione o turno faltoso.")
    body = FaltaBody(motivo=payload.get("motivo") or "falta", detalhes=(payload.get("detalhes") or "").strip() or None)
    res = await registrar_falta(shift_id, body, scope, db)
    return {
        "ok": True,
        "substitution_id": res.get("substitution_id"),
        "message": f"Falta de {res.get('faltoso')} registrada em {res.get('posto')} — substituição aberta",
    }


@router.post("/action/substituir-diarista")
async def rd_action_substituir(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    scope: OperationalScope = Depends(get_operational_scope),
    db: AsyncSession = Depends(get_db),
) -> dict:
    from modules.operacional.controllers.falta_substituto_controller import SubstituirBody, escalar_substituto

    sub_id = payload.get("substitution_id")
    if not sub_id:
        raise HTTPException(status_code=400, detail="Selecione a substituição aberta.")
    if not payload.get("diarista_id"):
        raise HTTPException(status_code=400, detail="Selecione o diarista.")
    try:
        did = int(payload.get("diarista_id"))
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Diarista inválido.")
    body = SubstituirBody(
        tipo="diarista",
        diarista_id=did,
        funcao=(payload.get("funcao") or "").strip() or None,
        turno=(payload.get("turno") or "").strip() or None,
        observacao=(payload.get("observacao") or "").strip() or None,
    )
    res = await escalar_substituto(sub_id, body, scope, db)
    return {
        "ok": True,
        "lancamento_id": res.get("lancamento_id"),
        "message": f"Diarista {res.get('substituto')} escalado — diária R$ {float(res.get('valor_diaria', 0)):.2f}",
    }


# dgx u3 (24/09/2026): a rota HTTP /action/payable saiu — desde a F11 os forms postam em
# /action/payable-condicao (`_dgx_f11_financeiro._conta_com_condicao`, que sem condição faz
# exatamente isto: 1 título). Nenhuma tela, MCP ou teste chamava a rota (grep 24/09). A FUNÇÃO
# fica porque `_dgx_f10_frotas` a chama por import (locação → título em contas a pagar).
async def rd_action_payable(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # REGISTRO de conta a pagar (NÃO paga — dinheiro que sai só via fluxo OTP). Gate financeiro.
    from datetime import date as _date
    from decimal import Decimal, InvalidOperation

    from modules.financial.schemas.payable import PayableAccountCreate
    from modules.financial.services.payable_service import PayableService

    desc = (payload.get("description") or "").strip()
    if len(desc) < 3:
        raise HTTPException(status_code=400, detail="Descrição (mínimo 3 caracteres).")
    try:
        valor = Decimal(_brl_norm(str(payload.get("valor") or "0")))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Valor inválido.")
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser maior que zero.")
    dd = (payload.get("due_date") or "").strip()
    try:
        due = _date.fromisoformat(dd)
    except ValueError:
        raise HTTPException(status_code=400, detail="Vencimento inválido.")
    import uuid as _uuid

    # condominio_id "empresa" (todas as 71 contas existentes usam este mesmo tenant default)
    _COND_EMPRESA = _uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")
    try:
        data = PayableAccountCreate(
            condominio_id=_COND_EMPRESA,
            description=desc,
            gross_value=valor,
            due_date=due,
            supplier_name=(payload.get("supplier_name") or "").strip() or None,
            notes=(payload.get("notes") or "").strip() or None,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    account = await PayableService(db).create_account(data, current_user.id)
    return {"ok": True, "id": str(account.id), "message": "Conta a pagar registrada (não paga — pagamento é com OTP)"}


# dgx u3 (24/09/2026): /action/receivable e rd_action_receivable removidos — mesmo motivo do payable
# acima; o caminho vivo é /action/receivable-condicao (F11). Sem chamador em front, MCP ou testes.


@router.post("/action/epi-delivery")
async def rd_action_epi_delivery(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Registro de entrega de EPI (log operacional NR-6). Alimenta a ficha (ficha_epi_id NULL = pendente).
    # INSERT cru: a coluna employee_id é uuid no banco (o modelo ORM está como String → asyncpg recusa).
    import uuid as _uuid
    from datetime import date as _date

    try:
        emp_uuid = _uuid.UUID((payload.get("employee_id") or "").strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    row = (await db.execute(text("SELECT nome FROM employees WHERE id=:i"), {"i": emp_uuid})).first()
    if not row:
        raise HTTPException(status_code=400, detail="Colaborador não encontrado.")
    nome = (payload.get("epi_nome") or "").strip()
    if len(nome) < 2:
        raise HTTPException(status_code=400, detail="Informe o nome do EPI.")
    try:
        d_ent = _date.fromisoformat((payload.get("data_entrega") or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Data de entrega inválida.")
    d_val = None
    dv = (payload.get("data_validade") or "").strip()
    if dv:
        try:
            d_val = _date.fromisoformat(dv)
        except ValueError:
            raise HTTPException(status_code=400, detail="Data de validade inválida.")
    try:
        qtd = int(payload.get("quantidade") or 1)
    except (ValueError, TypeError):
        qtd = 1
    qtd = max(qtd, 1)
    nr = (payload.get("nr") or "").strip() or "NR-6"
    ca = (payload.get("epi_ca") or "").strip() or None
    delivery_id = str(_uuid.uuid4())
    await db.execute(
        text(
            "INSERT INTO gp_epi_deliveries "
            "(delivery_id, employee_id, epi_nome, epi_ca, quantidade, nr, data_entrega, data_validade, created_at) "
            "VALUES (:did, :eid, :nome, :ca, :qtd, :nr, :de, :dv, now())"
        ),
        {"did": delivery_id, "eid": emp_uuid, "nome": nome, "ca": ca, "qtd": qtd, "nr": nr, "de": d_ent, "dv": d_val},
    )
    await db.commit()
    return {"ok": True, "id": delivery_id, "message": f"Entrega de EPI registrada para {row[0]}"}


_REEMBOLSO_CATS = {
    "transporte",
    "alimentacao",
    "hospedagem",
    "material",
    "comunicacao",
    "viagem",
    "estacionamento",
    "pedagio",
    "saude",
    "cursos",
    "outros",
}


@router.post("/action/reembolso")
async def rd_action_reembolso(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Solicitação de reembolso → nasce em RASCUNHO (aprovação e pagamento seguem o fluxo, sem mover dinheiro aqui).
    from datetime import date as _date
    from decimal import Decimal, InvalidOperation

    from modules.reimbursement.repositories import CondominioRepository
    from modules.reimbursement.schemas.reimbursement_item import ReimbursementItemCreate
    from modules.reimbursement.schemas.reimbursement_request import ReimbursementRequestCreate
    from modules.reimbursement.services.reimbursement_service import ReimbursementService

    title = (payload.get("title") or "").strip()
    if len(title) < 3:
        raise HTTPException(status_code=400, detail="Título (mínimo 3 caracteres).")
    cat = (payload.get("category_type") or "").strip()
    if cat not in _REEMBOLSO_CATS:
        raise HTTPException(status_code=400, detail="Selecione a categoria da despesa.")
    try:
        valor = Decimal(_brl_norm(str(payload.get("valor") or "0")))
    except (InvalidOperation, ValueError):
        raise HTTPException(status_code=400, detail="Valor inválido.")
    if valor <= 0:
        raise HTTPException(status_code=400, detail="O valor deve ser maior que zero.")
    try:
        exp = _date.fromisoformat((payload.get("expense_date") or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Data da despesa inválida.")
    desc = (payload.get("description") or "").strip()
    if len(desc) < 3:
        desc = title
    merchant = (payload.get("merchant") or "").strip() or None
    notes = (payload.get("notes") or "").strip() or None

    cond_id = await CondominioRepository(db).get_first_active_condominio()
    if not cond_id:
        raise HTTPException(status_code=400, detail="Nenhum condomínio disponível para o reembolso.")
    try:
        data = ReimbursementRequestCreate(
            title=title,
            expense_date_start=exp,
            expense_date_end=exp,
            notes=notes,
            items=[
                ReimbursementItemCreate(
                    category_type=cat, description=desc, merchant=merchant, expense_date=exp, amount=valor
                )
            ],
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    req = await ReimbursementService(db).create_request(cond_id, current_user.id, data)
    return {
        "ok": True,
        "id": str(req.id),
        "code": req.code,
        "message": f"Reembolso {req.code} criado (rascunho — aprovação e pagamento seguem o fluxo)",
    }


_JUSTIF_TYPES = {"atraso", "falta"}
_JUSTIF_CATS = {"transito", "saude", "familiar", "transporte_publico", "acidente", "outro"}


@router.post("/action/justificativa-ponto")
async def rd_action_justificativa_ponto(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Justificativa de atraso/falta → nasce PENDENTE (gestor revisa depois). Sem efeito na folha aqui.
    import uuid as _uuid

    from modules.people_management.ponto.schemas.punch_schemas import JustificationCreate
    from modules.people_management.ponto.services.punch_service import PunchService

    try:
        emp_uuid = _uuid.UUID((payload.get("employee_id") or "").strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    row = (await db.execute(text("SELECT nome FROM employees WHERE id=:i"), {"i": emp_uuid})).first()
    if not row:
        raise HTTPException(status_code=400, detail="Colaborador não encontrado.")
    jtype = (payload.get("justification_type") or "").strip()
    if jtype not in _JUSTIF_TYPES:
        raise HTTPException(status_code=400, detail="Selecione o tipo (atraso ou falta).")
    cat = (payload.get("category") or "").strip()
    if cat not in _JUSTIF_CATS:
        raise HTTPException(status_code=400, detail="Selecione o motivo.")
    reason = (payload.get("reason") or "").strip()
    if len(reason) < 5:
        raise HTTPException(status_code=400, detail="Descreva a justificativa (mínimo 5 caracteres).")
    data = JustificationCreate(employee_id=str(emp_uuid), justification_type=jtype, reason=reason, category=cat)
    result = await PunchService(db).criar_justificativa(data)
    await db.commit()
    return {
        "ok": True,
        "id": result.get("justification_id"),
        "message": f"Justificativa de {jtype} registrada para {row[0]} (pendente de revisão)",
    }


@router.post("/action/job-position")
async def rd_action_job_position(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Abrir vaga → nasce em RASCUNHO (o recrutador publica depois). Sem impacto em folha/operacional.
    from decimal import Decimal, InvalidOperation

    from modules.recruitment.schemas.job_position import JobPositionCreate
    from modules.recruitment.services.job_position_service import JobPositionService

    title = (payload.get("title") or "").strip()
    if len(title) < 3:
        raise HTTPException(status_code=400, detail="Título da vaga (mínimo 3 caracteres).")

    def _money(key):
        raw = (payload.get(key) or "").strip()
        if not raw:
            return None
        try:
            return Decimal(_brl_norm(raw))
        except (InvalidOperation, ValueError):
            raise HTTPException(status_code=400, detail=f"Valor de salário inválido ({key}).")

    try:
        vagas = int(payload.get("vacancies") or 1)
    except (ValueError, TypeError):
        vagas = 1
    vagas = max(vagas, 1)
    sal_min, sal_max = _money("salary_min"), _money("salary_max")
    try:
        data = JobPositionCreate(
            title=title,
            department=(payload.get("department") or "").strip() or None,
            position_type=(payload.get("position_type") or "").strip() or "clt",
            work_model=(payload.get("work_model") or "").strip() or None,
            city=(payload.get("city") or "").strip() or None,
            state=((payload.get("state") or "").strip()[:2].upper() or None),
            vacancies=vagas,
            salary_min=sal_min,
            salary_max=sal_max,
            show_salary=bool(sal_min or sal_max),
            description=(payload.get("description") or "").strip() or None,
            requirements=(payload.get("requirements") or "").strip() or None,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Dados inválidos: {e}")
    position = await JobPositionService(db).create(data)
    return {
        "ok": True,
        "id": str(position.id),
        "code": getattr(position, "code", None),
        "message": f"Vaga '{title}' aberta (rascunho — publique quando quiser divulgar)",
    }


@router.post("/action/vacation-request")
async def rd_action_vacation_request(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Solicitação de férias (auto-serviço) → nasce SUBMITTED sobre SALDO REAL. Sem mover
    # folha/dinheiro.
    #
    # Esta ação gravava em `employee_vacation_requests` (via
    # `hr/employee_portal/services/vacation_service`) enquanto a aprovação — o
    # `/action/ferias-aprovar`, logo ali — trabalha em `hr_vacation_requests`. **O pedido
    # que esta tela criava nunca podia ser aprovado por ela.** Não é hipótese: em 13/08/2026
    # havia 14 pedidos parados em SUBMITTED desde 01/04 de um lado, enquanto o outro seguia
    # até 16/07.
    #
    # `hr_vacation_requests` é a autoritativa (19 linhas, a mais recente, a única com ciclo
    # completo). Agora criar e aprovar passam pelo MESMO controller, que é o que fecha o
    # ciclo — e `criar_vacation` já traz as travas da CLT (art. 130, teto de 30 dias
    # corridos) que este caminho não tinha.
    import uuid as _uuid
    from datetime import date as _date

    from modules.hr.employee_portal.schemas.vacation import VacationType
    from modules.people_management.hr.controllers.vacation_controller import criar_vacation

    try:
        emp_uuid = _uuid.UUID((payload.get("employee_id") or "").strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    row = (await db.execute(text("SELECT nome FROM employees WHERE id=:i"), {"i": emp_uuid})).first()
    if not row:
        raise HTTPException(status_code=400, detail="Colaborador não encontrado.")
    vtype = (payload.get("vacation_type") or "full").strip()
    if vtype not in {v.value for v in VacationType}:
        vtype = "full"
    try:
        sd = _date.fromisoformat((payload.get("start_date") or "").strip())
        ed = _date.fromisoformat((payload.get("end_date") or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Datas de início/fim inválidas.")
    if sd < _date.today():
        raise HTTPException(status_code=400, detail="A data de início não pode ser no passado.")
    dias = (ed - sd).days + 1
    if dias < 5 or dias > 30:
        raise HTTPException(status_code=400, detail="O período deve ter de 5 a 30 dias corridos.")
    # O condomínio NÃO é escolhido aqui: `criar_vacation` usa o canônico
    # (`_HVR_DEFAULT_CONDOMINIO_ID`), que é o mesmo das 19 solicitações existentes. Escolher
    # um por fora faria o pedido nascer num condomínio que a aprovação não procura.
    try:
        req = await criar_vacation(
            data={
                "employee_id": str(emp_uuid),
                "start_date": sd.isoformat(),
                "end_date": ed.isoformat(),
                "days": dias,
                "vacation_type": vtype,
                "reason": (payload.get("employee_notes") or "").strip() or None,
            },
            current_user=current_user,
            db=db,
        )
    except HTTPException:
        raise  # 422 da CLT e 400 de validação sobem como estão — são a resposta certa
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "ok": True,
        "id": req.get("id"),
        "code": req.get("request_code"),
        "message": f"Férias solicitadas para {row[0]} — {dias} dias (pendente de aprovação)",
    }


@router.post("/action/vacation-reject")
async def rd_action_vacation_reject(
    current_user: CurrentActiveUser,
    vid: str,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Rejeita férias (fonte canônica hr_vacation_requests). O endpoint real (/vacations/{id}/reject)
    # espera reason como QUERY param, não body — por isso este handler fino: vacation id chega na
    # query string do próprio endpoint da ação (?vid=), reason chega no body {reason} do modal.
    from modules.people_management.hr.services.vacation_service import VacationService

    reason = (payload.get("reason") or "").strip()
    if not reason:
        return {"ok": False, "message": "Motivo é obrigatório para rejeitar as férias."}
    # Parede de EQUIPE (simétrico ao aprovar): supervisor/gerente só rejeita férias de colaborador
    # operacional (alocado a posto ativo); admin age sobre todos.
    from modules.operacional.controllers.redesign_builders.operacional import _exige_escopo_operacional

    _v = (
        await db.execute(
            text("SELECT CAST(employee_id AS TEXT) FROM hr_vacation_requests WHERE id::text=:i"), {"i": vid}
        )
    ).first()
    if not _v or not _v[0]:
        raise HTTPException(status_code=404, detail="Solicitação de férias não encontrada.")
    await _exige_escopo_operacional(db, current_user, _v[0], "rejeitar férias de colaborador da sua equipe operacional")
    try:
        await VacationService(db).reject_vacation(vid, rejected_by_id=current_user.id, reason=reason)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    await db.commit()
    return {"ok": True, "message": "Férias rejeitada"}


@router.post("/action/rescisao-calc")
async def rd_action_rescisao_calc(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Calculadora de rescisão (CLT) — cálculo PURO, sem gravar/transmitir/pagar. Reusa clt_calculator.
    import uuid as _uuid
    from datetime import date as _date
    from decimal import Decimal, InvalidOperation

    from modules.people_management.common.utils.clt_calculator import calcular_rescisao

    try:
        emp_uuid = _uuid.UUID((payload.get("employee_id") or "").strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    row = (
        await db.execute(text("SELECT nome, salario_base, data_admissao FROM employees WHERE id=:i"), {"i": emp_uuid})
    ).first()
    if not row:
        raise HTTPException(status_code=400, detail="Colaborador não encontrado.")
    nome, sal, adm = row
    if not sal or not adm:
        raise HTTPException(status_code=400, detail="Colaborador sem salário base ou data de admissão cadastrados.")
    tipo = (payload.get("tipo_rescisao") or "sem_justa_causa").strip()
    try:
        demissao = _date.fromisoformat((payload.get("data_desligamento") or "").strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="Data de desligamento inválida.")
    if demissao < adm:
        raise HTTPException(status_code=400, detail="Desligamento não pode ser antes da admissão.")

    def _int(k):
        try:
            return max(int(payload.get(k) or 0), 0)
        except (ValueError, TypeError):
            return 0

    def _money(k):
        raw = (payload.get(k) or "").strip()
        if not raw:
            return Decimal("0")
        try:
            return Decimal(_brl_norm(raw))
        except (InvalidOperation, ValueError):
            return Decimal("0")

    try:
        r = calcular_rescisao(
            Decimal(str(sal)),
            tipo,
            adm,
            demissao,
            _money("saldo_fgts"),
            _int("ferias_vencidas_dias"),
            _int("dias_trabalhados_mes"),
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Não foi possível calcular: {e}")
    ferias_tot = (
        r["ferias_proporcionais"] + r["terco_ferias_proporcionais"] + r["ferias_vencidas"] + r["terco_ferias_vencidas"]
    )
    msg = (
        f"Rescisão de {nome} ({tipo.replace('_', ' ')}) — LÍQUIDO {brl(r['total_liquido'])} | "
        f"Saldo salário {brl(r['saldo_salario'])} · Aviso {brl(r['aviso_previo_indenizado'])} ({r['aviso_previo_dias']}d) · "
        f"Férias+1/3 {brl(ferias_tot)} · 13º {brl(r['decimo_terceiro_proporcional'])} · "
        f"Multa FGTS {brl(r['multa_fgts'])} · INSS −{brl(r['inss'])} · IRRF −{brl(r['irrf'])} "
        f"({r['anos_servico']} anos de serviço). Cálculo — não gera rescisão."
    )
    return {"ok": True, "message": msg}


@router.post("/action/simular-preco")
async def rd_action_simular_preco(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Simulador de preço (precificação) — cálculo PURO via PricingEngine. Não grava proposta/contrato.
    from decimal import Decimal, InvalidOperation

    from modules.crm.services.pricing_engine import PricingEngine, PricingInput

    def _money(k, default):
        raw = (payload.get(k) or "").strip()
        if not raw:
            return Decimal(default)
        try:
            return Decimal(_brl_norm(raw))
        except (InvalidOperation, ValueError):
            raise HTTPException(status_code=400, detail=f"Valor inválido em '{k}'.")

    def _int(k, default):
        try:
            return int(payload.get(k) or default)
        except (ValueError, TypeError):
            return default

    stype = (payload.get("service_type") or "portaria").strip()
    hc = max(_int("headcount", 1), 1)
    months = _int("contract_months", 12) or 12
    state = (payload.get("client_state") or "AM").strip()[:2].upper() or "AM"
    try:
        inp = PricingInput(
            base_salary=_money("base_salary", "1670"),
            headcount=hc,
            contract_months=months,
            service_type=stype,
            client_state=state,
            margin_target=_money("margin_target", "35"),
            benefits_value=_money("benefits_value", "0"),
            equipment_value=_money("equipment_value", "0"),
        )
        res = PricingEngine().calculate(inp)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Não foi possível simular: {e}")
    msg = (
        f"Preço simulado ({stype.replace('_', ' ')}, {hc} posto(s), {months}m) — "
        f"PREÇO/POSTO {brl(res.unit_price)} · MENSAL {brl(res.total_monthly)} · CONTRATO {brl(res.total_contract)} | "
        f"Custo total {brl(res.total_cost)} · CCT {res.cct_percent}% · Margem {res.margin_percent}% ({brl(res.margin_value)}) · "
        f"Impostos {brl(res.tax_amount)}. Simulação — não gera proposta."
    )
    return {"ok": True, "message": msg}


@router.post("/action/ferias-calc")
async def rd_action_ferias_calc(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Calculadora de férias (CLT) — cálculo PURO. Não solicita/agenda/paga férias.
    import uuid as _uuid
    from decimal import Decimal

    from modules.people_management.common.utils.clt_calculator import calcular_ferias, calcular_inss, calcular_irrf

    try:
        emp_uuid = _uuid.UUID((payload.get("employee_id") or "").strip())
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Selecione o colaborador.")
    row = (await db.execute(text("SELECT nome, salario_base FROM employees WHERE id=:i"), {"i": emp_uuid})).first()
    if not row:
        raise HTTPException(status_code=400, detail="Colaborador não encontrado.")
    nome, sal = row
    if not sal:
        raise HTTPException(status_code=400, detail="Colaborador sem salário base cadastrado.")

    def _int(k, default):
        try:
            return max(int(payload.get(k) or default), 0)
        except (ValueError, TypeError):
            return default

    dias_gozo = min(_int("dias_gozo", 30), 30)
    dias_abono = min(_int("dias_abono", 0), 10)
    try:
        r = calcular_ferias(Decimal(str(sal)), dias_gozo, dias_abono)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Não foi possível calcular: {e}")
    # INSS/IRRF incidem sobre férias + 1/3 (abono pecuniário é isento).
    base = r["valor_ferias"] + r["terco_constitucional"]
    inss = calcular_inss(base)
    irrf = calcular_irrf(base - inss)
    liquido = r["total_bruto"] - inss - irrf
    msg = (
        f"Férias de {nome} — {dias_gozo}d gozo + {dias_abono}d abono — LÍQUIDO {brl(liquido)} | "
        f"Férias {brl(r['valor_ferias'])} + 1/3 {brl(r['terco_constitucional'])}"
        f"{f' + abono {brl(r["abono_pecuniario"])}+1/3 {brl(r["terco_abono"])}' if dias_abono else ''} · "
        f"INSS −{brl(inss)} · IRRF −{brl(irrf)}. Cálculo — não solicita/paga férias."
    )
    return {"ok": True, "message": msg}


@router.post("/action/custeio-cct")
async def rd_action_custeio_cct(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Custeio CCT — encargos/provisões sobre a folha (cálculo PURO via PricingEngine). Nada é gravado.
    from decimal import Decimal, InvalidOperation

    from modules.crm.services.pricing_engine import PricingEngine

    def _money(k, default):
        raw = (payload.get(k) or "").strip()
        if not raw:
            return Decimal(default)
        try:
            return Decimal(_brl_norm(raw))
        except (InvalidOperation, ValueError):
            raise HTTPException(status_code=400, detail=f"Valor inválido em '{k}'.")

    def _int(k, default):
        try:
            return int(payload.get(k) or default)
        except (ValueError, TypeError):
            return default

    sal = _money("salario_base", "1670")
    if sal <= 0:
        raise HTTPException(status_code=400, detail="Informe o salário base.")
    headcount = max(_int("headcount", 1), 1)
    meses = _int("meses", 12) or 12
    try:
        r = PricingEngine().calculate_cct_breakdown(sal, headcount, meses)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Não foi possível calcular: {e}")
    total = sum(Decimal(str(v)) for v in r.values())
    por_col_mes = total / Decimal(headcount) / Decimal(meses) if headcount and meses else Decimal(0)
    _lbls = {
        "inss_empresa": "INSS patronal",
        "fgts": "FGTS",
        "sat_rat": "SAT/RAT",
        "terceiros": "Terceiros",
        "ferias": "Férias",
        "ferias_terco": "1/3 férias",
        "decimo_terceiro": "13º",
        "aviso_previo": "Aviso prévio",
        "multa_fgts": "Multa FGTS 40%",
        "provisao_rescisao": "Provisão rescisão",
    }
    partes = " · ".join(f"{_lbls.get(k, k)} {brl(v)}" for k, v in r.items())
    msg = (
        f"Custeio CCT ({headcount} colaborador(es), sal. base {brl(sal)}, {meses}m) — "
        f"ENCARGOS TOTAIS {brl(total)} · {brl(por_col_mes)}/colab./mês | {partes}. "
        f"Cálculo — nada é gravado."
    )
    return {"ok": True, "message": msg}


# Itens de menu extras (telas de ação/escrita) que o ModuleView anexa à nav.
EXTRA_MENU = {
    # F0: itens do financeiro removidos — registrar-conta-* e custeio-cct agora são ABAS
    # dos grupos (g-pagar/g-receber/g-custos em _fin_grupos.py). Menu = só os 7 grupos.
    "financeiro": [],
    # F0: itens do operacional removidos — lancar-diaria/cadastrar-diarista/registrar-falta/
    # escalar-substituto/resolver-ocorrencia/comentar-ocorrencia agora são ABAS dos grupos
    # (g-diaristas/g-escalas/g-rondas em _op_grupos.py). Menu = só os 8 grupos.
    "operacional": [],
    "crm": [
        {"id": "novo-lead", "label": "Novo lead", "icon": "M12 5v14M5 12h14", "grupo": "Leads & funil"},
        {
            "id": "nova-proposta",
            "label": "Nova proposta",
            "icon": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M9 13h6M9 17h3",
        },
        {"id": "definir-lead", "label": "Definir lead", "icon": "M20 6L9 17l-5-5", "grupo": "Leads & funil"},
        {
            "id": "consumo-ia",
            "label": "Consumo de IA",
            "icon": "M3 3v18h18M7 15l3-4 3 3 4-6",
            "grupo": "José Luís (IA)",
        },
        {
            "id": "contrato-da-proposta",
            "label": "Contrato da proposta",
            "icon": "M9 12h6M9 16h6M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z",
        },
        {
            "id": "abrir-assinatura",
            "label": "Abrir assinatura",
            "icon": "M12 20h9M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z",
        },
        {
            "id": "enviar-link-assinatura",
            "label": "Enviar link de assinatura",
            "icon": "M22 2L11 13M22 2l-7 20-4-9-9-4z",
        },
        {
            "id": "mover-oportunidade",
            "label": "Mover no funil",
            "icon": "M3 3v18h18M7 14l3-3 3 3 5-6",
            "grupo": "Leads & funil",
        },
        {
            "id": "nova-tarefa",
            "label": "Nova tarefa",
            "icon": "M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18M12 7v5l3 2",
            "grupo": "Tarefas",
        },
        {
            "id": "anotar-cliente",
            "label": "Anotar cliente",
            "icon": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h5",
        },
        {
            "id": "simular-preco",
            "label": "Simular preço",
            "icon": "M9 7h6M9 11h6M9 15h4M5 3h14a1 1 0 0 1 1 1v16H4V4a1 1 0 0 1 1-1z",
        },
        {
            "id": "aditivos",
            "label": "Aditivos contratuais",
            "icon": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M12 11v6M9 14h6",
        },
    ],
    "gestao-de-pessoas": [
        {
            "id": "registrar-entrega-epi",
            "label": "Registrar entrega de EPI",
            "icon": "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z",
        },
        {
            "id": "registrar-justificativa-ponto",
            "label": "Justificar ponto",
            "icon": "M12 8v4l3 2M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18z",
        },
    ],
    # F0 — zerado: os 6 itens que estavam aqui (calcular-rescisao, calcular-ferias,
    # beneficios-cct, saldo-ferias, registrar-reembolso, solicitar-ferias) viraram ABAS dos 8
    # grupos do DP (_dp_grupos.py). Este dict é SOMADO ao menu do pacote e ao EXTRA_MENU do
    # builder — deixá-los aqui os fazia reaparecer soltos no topo, ao lado do grupo que já os
    # continha. Terceira fonte de menu do mesmo módulo: quem for reagrupar outro módulo tem
    # que zerar as TRÊS (pacote JSON, EXTRA_MENU do builder, e este).
    "departamento-pessoal": [],
    "recrutamento": [
        {
            "id": "abrir-vaga",
            "label": "Abrir vaga",
            "icon": "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8M19 8v6M22 11h-6",
        },
    ],
    "saude-ocupacional": [
        {"id": "esocial", "label": "eSocial · Transmissão", "icon": "M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"},
        {"id": "asos-vencendo", "label": "ASOs vencendo (30 dias)", "icon": "M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"},
        {"id": "cipa-membros", "label": "CIPA · Membros", "icon": "M22 2 11 13M22 2l-7 20-4-9-9-4 20-7z"},
    ],
    "fiscal": [
        {
            "id": "guias-fgts",
            "label": "Guias FGTS",
            "icon": "M3 10h18M7 15h4M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
        },
        {
            "id": "guias-inss",
            "label": "Guias INSS",
            "icon": "M3 10h18M7 15h4M5 4h14a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2z",
        },
        {
            "id": "certidoes-cnd",
            "label": "Certidões (CND)",
            "icon": "M9 12l2 2 4-4M12 3l7 3v6c0 5-3.5 8-7 9-3.5-1-7-4-7-9V6l7-3z",
        },
        {
            "id": "nfse-tomadas",
            "label": "NFS-e tomadas",
            "icon": "M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zM14 2v6h6M8 13h8M8 17h6",
        },
    ],
    "juridico": [
        {
            "id": "det-comunicacoes",
            "label": "DET · Comunicações",
            "icon": "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z",
        },
    ],
}


@router.get("/home")
async def redesign_home(current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> dict:
    """KPIs e pendências REAIS da Home (launcher). Substitui os exemplos chumbados."""
    from datetime import date as _date

    async def _sc(q: str):
        try:
            return await _scalar(db, q)
        except Exception:  # noqa: BLE001
            await db.rollback()
            return 0

    # ⭐ 21/09/2026 — CLT e PJ SEPARADOS. Pedido do Jordan: «na dashboard tem que informar
    # quantos são clt e quantos são pj», porque os números têm de conferir com a folha e o
    # recibo da Portte. Antes havia UM número, «Colaboradores», que era
    # `count(*) WHERE status='ativo'` — e isso conta só CLT, porque PJ tem status `pj_ativo`
    # e ficava simplesmente FORA da tela. Ninguém sabia disso olhando o painel.
    #
    # ⚠️ O corte é por STATUS e não por `tipo_contrato`, que seria o campo semanticamente
    # certo: medido hoje, `tipo_contrato` está NULO em 51 dos 64 ativos, então ele não separa
    # nada. Enquanto o cadastro não for preenchido, status é o único critério que funciona.
    clt = await _sc(
        f"SELECT count(*) FROM employees WHERE lower(coalesce(status,''))='ativo' AND {SQL_FUNCIONARIO_REAL}"
    )
    pj = await _sc(
        f"SELECT count(*) FROM employees WHERE lower(coalesce(status,''))='pj_ativo' AND {SQL_FUNCIONARIO_REAL}"
    )
    # ⚠️ 25/09 — ASSIMETRIA CORRIGIDA. A pessoa de teste já era excluída (`SQL_FUNCIONARIO_REAL`
    # no CLT e no PJ), mas o POSTO e o CLIENTE de teste não: "15 Postos ativos" somava os 6 do
    # Conecta Village + Conecta Base, que o Jordan confirmou serem o condomínio de HOMOLOGAÇÃO do
    # Conecta Plus, e "29 Clientes" incluía HOMOLOGACAO (CONECTA BASE). Duas verdades sobre a
    # mesma pergunta, dependendo de qual contador se olhava.
    #
    # `posts.is_homologacao` / `clients.is_homologacao` são marcador na ORIGEM. Filtrar por
    # `name ~* 'CONECTA'` quebraria no dia em que um condomínio real se chamasse assim — e a
    # marcação por NOME já falhou uma vez aqui (casou 0 linhas por causa de caixa e travessão);
    # foi feita por id.
    #
    # Confirmado pelo dono: Condomínio Gelain é REAL (está nos 9) e as duas empresas do grupo SÃO
    # clientes — faturam entre si —, então continuam contando.
    postos = await _sc(
        "SELECT count(*) FROM posts WHERE coalesce(is_active,true)=true "
        "AND coalesce(is_homologacao,false)=false"
    )
    clientes = await _sc(
        "SELECT count(*) FROM clients WHERE status='active' AND coalesce(is_homologacao,false)=false"
    )

    kpis = [
        {"v": str(clt), "l": "CLT ativos"},
        {"v": str(pj), "l": "PJ ativos"},
        {"v": str(postos), "l": "Postos ativos"},
        {"v": str(clientes), "l": "Clientes"},
    ]

    # Pendências REAIS: certidões com vencimento (vencidas ou vencendo em ≤45 dias)
    alerts: list[dict] = []
    try:
        hoje = _date.today()
        rows = (
            await db.execute(
                text(
                    "SELECT name, expiry_date FROM ged_certidoes "
                    "WHERE expiry_date IS NOT NULL ORDER BY expiry_date ASC LIMIT 20"
                )
            )
        ).fetchall()
        for name, exp in rows:
            dias = (exp - hoje).days
            if dias < 0:
                meta, level, action = f"Vencido há {abs(dias)} dias", "var(--error)", "Regularizar"
            elif dias <= 45:
                meta, level, action = f"Vence em {dias} dias", "var(--warning)", "Ver"
            else:
                continue
            alerts.append({"title": name, "meta": meta, "action": action, "dot": level})
        alerts = alerts[:4]
    except Exception:  # noqa: BLE001
        await db.rollback()
        alerts = []

    # Identidade REAL + RBAC do launcher (fecha o "Jordan/admin + 31 módulos" chumbado).
    # `denied` = slugs GATEADOS que ESTE usuário não pode abrir → o front oculta o tile.
    # Só gateados entram no universo; slugs abertos/pessoais nunca são negados.
    _gated = set(_SLUG_MODULO_CANONICO) | _SLUG_ADMIN_ONLY
    denied = sorted(s for s in _gated if not _slug_allowed(current_user, s))
    _nome = getattr(current_user, "name", None) or (getattr(current_user, "email", "") or "").split("@")[0] or "Usuário"
    user = {
        "name": _nome,
        "role": getattr(current_user, "role", "") or "",
        "email": getattr(current_user, "email", "") or "",
        "isAdmin": _is_admin_user(current_user),
    }
    return {"kpis": kpis, "alerts": alerts, "user": user, "denied": denied}


# slug do redesign → módulo canônico (gate de permissão). Só back-office; slugs pessoais/
# cliente/admin (portal, meu-espaco, area-do-cliente, empresas, bi, relatorios, configuracoes…)
# NÃO entram aqui — têm escopo próprio; gatear por perm de gestor os quebraria.
_SLUG_MODULO_CANONICO = {
    "operacional": "operacional",
    "campo": "operacional",
    "financeiro": "financeiro",
    "fiscal": "fiscal",
    "juridico": "juridico",
    "crm": "crm",
    "marketing": "crm",
    "licitacoes": "crm",
    "servicos": "crm",
    "area-do-cliente": "crm",  # visão 360 de TODOS os clientes (MRR/faturas/contratos) → domínio comercial
    "departamento-pessoal": "dp",
    "rh": "dp",
    "gestao-de-pessoas": "dp",
    "recrutamento": "dp",
    "homologacao": "dp",
    "saude-ocupacional": "sst",
    "documentos": "ged",
    "bi": "financeiro",  # bank_transactions / DRE / receita×despesa → domínio financeiro
    "automacoes": "crm",  # crm_workflows / workflow_runs → domínio comercial
    "equipamentos": "operacional",  # patrimônio/comodatos/manutenções → gestão de ativos de campo
    "suprimentos": "financeiro",  # nfe_compras_estoque / requisições / stock_items → compras/custo
    "agendador": "dev",  # scheduler_tasks/executions → infra/dev
    "integracoes": "dev",  # integration_logs / solides_sync → infra/dev
}

# Slugs restritos à ADMINISTRAÇÃO/DIRETORIA (não é módulo — admin/all/* passam, resto 403):
# configuracoes=usuários/tenants/feature-flags/config-sistema; empresas=estrutura CNPJ+
# demonstrativos+liminares+migrador; relatorios=KPIs executivos consolidados (folha líq/AR/AP/MRR).
_SLUG_ADMIN_ONLY = {"configuracoes", "empresas", "relatorios", "analytics", "seguranca"}


def _is_admin_user(user) -> bool:
    role = (getattr(user, "role", "") or "").lower()
    perms = getattr(user, "permissions", None) or []
    return role in ("admin", "super_admin", "administrador") or "*" in perms or "all" in perms


def _slug_allowed(user, slug: str) -> bool:
    """Decisão ÚNICA de acesso a um slug do /redesign/data — usada pelo dispatcher E pelo
    launcher (evita drift do RBAC entre back e front). admin-only → só admin/all; módulo-
    gated → precisa do módulo; sem gate → aberto (self/pessoal)."""
    from core.auth.module_scope import user_has_module

    if slug in _SLUG_ADMIN_ONLY:
        return _is_admin_user(user)
    mod = _SLUG_MODULO_CANONICO.get(slug)
    if mod:
        return user_has_module(user, mod)
    return True


@router.get("/indice")
async def redesign_indice(current_user: CurrentActiveUser) -> dict:
    """Índice de TODAS as abas que ESTE usuário pode abrir. Alimenta a busca do topo.

    Origem: 17/09/2026. O Jordan: «to super perdido no sistema, tudo muito confuso, difícil de
    achar as coisas». Medido: 289 itens de menu e 587 telas, com a barra «Buscar…» do shell
    sendo um `<input>` sem uma linha de código — não havia como achar nada senão clicando.

    Barato de propósito: `EXTRA_MENU` é um dict em memória, montado no import. Aqui não roda
    NENHUM builder e não se toca no banco — buscar não pode custar o que custa abrir um módulo
    (o de financeiro devolve 8,95 MB).

    O filtro por `_slug_allowed` é a mesma porta do `/data/{slug}`: a busca não pode revelar a
    existência de uma tela que a pessoa levaria 403 ao abrir.
    """
    itens: list[dict] = []
    for slug, menu in EXTRA_MENU.items():
        if not _slug_allowed(current_user, slug):
            continue
        vistos: set[str] = set()
        for it in menu or []:
            ident, label = it.get("id"), it.get("label")
            # id repetido no mesmo menu existe (integracoes tinha um bloco colado 3x até hoje):
            # na busca, item duplicado é ruído puro.
            if not ident or not label or ident in vistos:
                continue
            vistos.add(ident)
            itens.append({"slug": slug, "id": ident, "label": label})
    return {"itens": itens, "total": len(itens)}


@router.get("/data/{slug}")
async def redesign_data(slug: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> dict:
    """Patches de tela com dado real para o módulo <slug>. Telas não cobertas ficam de fora.
    RBAC: se o slug mapeia a um módulo canônico, exige module:<mod> (admin/all passam)."""
    if not _slug_allowed(current_user, slug):
        if slug in _SLUG_ADMIN_ONLY:
            raise HTTPException(status_code=403, detail="Acesso restrito à administração/diretoria.")
        raise HTTPException(status_code=403, detail=f"Sem acesso ao módulo '{_SLUG_MODULO_CANONICO.get(slug)}'.")
    # dgx t5 — acesso temporário vencido é desativado aqui, na porta por onde todo mundo passa
    # (um UPDATE; `is_active=false` derruba o login nas travas que já existem). Nunca derruba a tela.
    try:
        from modules.operacional.controllers.redesign_builders._dgx_t5_suprimentos_frotas_sesmt_config import expirar_acessos

        await expirar_acessos(db)
    except Exception:  # noqa: BLE001
        await db.rollback()
    builder = BUILDERS.get(slug)
    if not builder:
        return {"slug": slug, "screens": {}, "wired": [], "extraMenu": []}
    # Builders self-scoped (ex.: portal do funcionário) declaram `current_user` na assinatura
    # → passamos o usuário logado p/ escoparem o dado ao próprio requisitante (parede LGPD).
    # Retrocompatível: builders com só (db) seguem recebendo só db.
    import inspect

    if "current_user" in inspect.signature(builder).parameters:
        screens = await builder(db, current_user=current_user)
    else:
        screens = await builder(db)
    try:
        _ver_todas_rec(screens)  # clique-na-linha 'Ver' universal (todos os módulos)
        _aplicar_drill_mod(screens, slug)  # KPIs de dashboard clicáveis (DP/fiscal/crm)
    except Exception:  # noqa: BLE001 — navegação nunca derruba o dado
        pass
    # Dedup dos formulários DEPOIS da navegação: `_ver_todas_rec` acrescenta uma ação
    # "Ver" em CADA linha, e sem passar aqui o DP voltava de 4,87 MB para 6,79 MB —
    # 2.000 blocos novos, iguais entre si. Deduplicar no fim pega tudo que foi montado,
    # não só o que o `tbl()` produziu.
    try:
        _dedup_recursivo(screens)
    except Exception:  # noqa: BLE001 — otimização nunca derruba o dado
        pass
    return {"slug": slug, "screens": screens, "wired": list(screens.keys()), "extraMenu": EXTRA_MENU.get(slug, [])}


# =============================================================================
# FANOUT 3 TERMINAIS — descoberta de builders por módulo (override + merge).
# Cada redesign_builders/<mod>.py define SLUG, build(db), EXTRA_MENU e (opcional) router.
# O build() do arquivo SOBRESCREVE o _build_<mod> do monólito (fallback); EXTRA_MENU e
# routers são SOMADOS. Assim T1/T2/T3 adicionam telas SEM tocar este arquivo.
# Um módulo quebrado é logado e ignorado — nunca derruba o boot. Ver DIVISAO_3T.md.
# =============================================================================
def _discover_module_builders() -> list[str]:
    import importlib
    import logging
    import pkgutil

    loaded: list[str] = []
    try:
        from . import redesign_builders as _pkg
    except Exception:  # noqa: BLE001 — pacote ausente → no-op
        return loaded
    for _mi in pkgutil.iter_modules(_pkg.__path__):
        if _mi.name.startswith("_"):
            continue
        try:
            _m = importlib.import_module(f"{_pkg.__name__}.{_mi.name}")
        except Exception as _e:  # noqa: BLE001 — módulo WIP não derruba o app
            logging.getLogger(__name__).error("redesign_builders/%s falhou: %s", _mi.name, _e)
            continue
        slug = getattr(_m, "SLUG", _mi.name)
        if hasattr(_m, "build"):
            BUILDERS[slug] = _m.build
        if hasattr(_m, "EXTRA_MENU"):
            # os builders declaram EXTRA_MENU como DICT {slug: [itens]} (é o formato de
            # todos eles). `extend(dict)` adicionava as CHAVES, então o menu do módulo
            # saía como ['aprovacoes'] — uma aba com o nome do slug e nenhuma das reais.
            # Aceita as duas formas: dict {slug: [...]} ou lista solta.
            _em = _m.EXTRA_MENU
            _itens = _em.get(slug, []) if isinstance(_em, dict) else list(_em)
            if _itens:
                EXTRA_MENU.setdefault(slug, [])
                # idempotente: recarregar o módulo não duplica a aba
                _ids = {i.get("id") for i in EXTRA_MENU[slug] if isinstance(i, dict)}
                EXTRA_MENU[slug].extend(i for i in _itens if isinstance(i, dict) and i.get("id") not in _ids)
        if hasattr(_m, "router"):
            router.include_router(_m.router)
        loaded.append(slug)

    # O menu de um módulo vem de até TRÊS arquivos (este dict, o EXTRA_MENU do builder e as
    # frentes que ele importa). A sidebar agrupa itens CONSECUTIVOS do mesmo grupo, então um
    # assunto espalhado entre fontes viraria dois blocos com o mesmo nome — ou, pior, grupos de
    # um item só. Agrupar aqui, DEPOIS da junção, é o único lugar que enxerga todas as fontes.
    #
    # Ordenação estável: soltos primeiro (na ordem em que chegaram), depois cada grupo inteiro
    # na ordem em que apareceu pela primeira vez. Ninguém muda de posição sem motivo.
    for _slug, _itens in EXTRA_MENU.items():
        _soltos = [i for i in _itens if isinstance(i, dict) and not i.get("grupo")]
        _grupos: dict[str, list] = {}
        for i in _itens:
            if isinstance(i, dict) and i.get("grupo"):
                _grupos.setdefault(i["grupo"], []).append(i)
        if _grupos:
            EXTRA_MENU[_slug] = _soltos + [i for g in _grupos.values() for i in g]

    return loaded


_LOADED_MODULE_BUILDERS = _discover_module_builders()
