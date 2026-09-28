"""DGX F7 — Ponto: configurações por escopo, relógios/aparelhos, feriados com escopo, cartão de
ponto em lote e dashboard de ausências (24/09/2026).

Prefixo `_` = o discovery de builders pula este arquivo; `departamento_pessoal.py` importa
`router` no nível do módulo e chama `telas(db, out)` no fim do build() (2 + 1 linhas, `# dgx f7`).
As telas entram como abas do grupo "Ponto & Jornada" (g-ponto), no FIM da lista.

Regra mora fora daqui: `people_management/ponto/config_ponto.py` (cascata + feriados + DDL),
`ponto/ausencias.py` (mesma régua do mapa de ponto), `ponto/cartao_lote.py` (reúso do espelho).
Falha de uma tela NÃO cala: aparece com o erro no título, como na frente 04.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import b, t
from modules.people_management.ponto import ausencias as aus
from modules.people_management.ponto import cartao_lote
from modules.people_management.ponto import config_ponto as cfg
from modules.people_management.ponto import mapa_de_ponto as regua

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_SN = [{"value": "", "label": "— herda —"}, {"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]
_ESCOPO_LBL = {
    "empresa": "Empresa (toda)",
    "condominio": "Condomínio",
    "posto": "Posto",
    "funcao": "Função",
    "escala": "Escala",
    "colaborador": "Colaborador",
}
_ESCOPO_FERIADO = {
    "nacional": "Nacional",
    "estadual": "Estadual",
    "municipal": "Municipal",
    "cliente": "Cliente (só um condomínio)",
}
_TIPO_APARELHO = {
    "rep_p": "REP-P (programa)",
    "mobile": "celular (app)",
    "contingencia": "contingência (DP)",
    "totem": "totem",
    "web": "web",
}

ABAS = [
    ("ponto-configuracoes", "Configurações de ponto"),
    ("ponto-configuracao-nova", "Nova configuração"),
    ("relogios-ponto", "Relógios/aparelhos"),
    ("feriados", "Feriados"),
    ("feriado-novo", "Novo feriado"),
    ("cartao-ponto-lote", "Cartão de ponto em lote"),
    ("ausencias-dashboard", "Ausências"),
    ("apropriacao-horas", "Apropriação de horas"),
    ("ponto-colaborador", "Ponto do colaborador"),
]


def _fd(v, fmt="%d/%m/%Y") -> str:
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:  # noqa: BLE001
        return str(v or "—")


def _n(v) -> str:
    return "—" if v is None else str(v)


def _sn(v) -> str:
    return "—" if v is None else ("Sim" if v else "Não")


def _data(v, campo: str, obrigatoria: bool = False) -> date | None:
    s = str(v or "").strip()
    if not s:
        if obrigatoria:
            raise HTTPException(status_code=400, detail=f"{campo}: informe a data (DD/MM/AAAA).")
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    raise HTTPException(status_code=400, detail=f"{campo}: data inválida «{s}» (use DD/MM/AAAA).")


def _int(v, campo: str) -> int | None:
    s = str(v if v is not None else "").strip()
    if not s:
        return None
    try:
        n = int(float(s.replace(",", ".")))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{campo}: use um número inteiro (minutos/metros).")
    if n < 0:
        raise HTTPException(status_code=400, detail=f"{campo}: não pode ser negativo.")
    return n


def _bool(v) -> bool | None:
    s = str(v if v is not None else "").strip().lower()
    if s in ("", "—"):
        return None
    return s in ("true", "1", "sim", "s", "yes", "on")


def _competencia(v) -> tuple[int, int]:
    s = str(v or "").strip().replace("-", "/")
    m = re.match(r"^(\d{1,2})/(\d{4})$", s) or None
    m2 = re.match(r"^(\d{4})/(\d{1,2})$", s)
    if m:
        ano, mes = int(m.group(2)), int(m.group(1))
    elif m2:
        ano, mes = int(m2.group(1)), int(m2.group(2))
    else:
        raise HTTPException(status_code=400, detail="Competência no formato MM/AAAA (ex.: 09/2026).")
    if not 1 <= mes <= 12:
        raise HTTPException(status_code=400, detail=f"Mês inválido em «{s}»: use 01 a 12.")
    return ano, mes


def _require_dp(current_user: CurrentActiveUser) -> None:
    from core.auth.module_scope import user_has_module

    if not user_has_module(current_user, "dp"):
        raise HTTPException(status_code=403, detail="Configuração de ponto e feriados são do DP.")


def _falhou(titulo: str, exc: Exception) -> dict:
    logger.error("dgx f7: %s falhou: %s", titulo, exc, exc_info=True)
    return {
        "title": f"{titulo} — FALHOU",
        "sub": f"{type(exc).__name__}: {str(exc)[:300]}",
        "cta": "—",
        "type": "table",
        "searchHint": "",
        "grid": "1fr",
        "cols": ["Erro"],
        "rows": [{"cells": [t("A tela não conseguiu ler as fontes. O erro está no log do backend.", 500, "#B91C1C")]}],
    }


# ───────────────────────────────── opções dos selects ─────────────────────────────────
async def _opcoes(db) -> dict[str, list[dict]]:
    async def q(sql):
        return [{"value": str(r[0]), "label": str(r[1])} for r in (await db.execute(text(sql))).all()]

    return {
        "condominio": await q("SELECT id, nome FROM condominios WHERE ativo ORDER BY nome"),
        "posto": await q("SELECT id, name FROM posts WHERE is_active ORDER BY name"),
        "funcao": await q(
            "SELECT DISTINCT upper(cargo), upper(cargo) FROM employees WHERE lower(status)='ativo' AND cargo IS NOT NULL ORDER BY 1"
        ),
        "escala": await q(
            "SELECT DISTINCT escala_padrao, escala_padrao FROM employees WHERE lower(status)='ativo' AND escala_padrao IS NOT NULL ORDER BY 1"
        ),
        "colaborador": await q(
            "SELECT id, nome FROM employees WHERE lower(status)='ativo' AND coalesce(is_homologacao,false)=false ORDER BY nome"
        ),
    }


def _campos_config(op: dict, r: dict | None = None) -> list[dict]:
    """Campos do form de configuração; `r` pré-preenche (Editar)."""
    r = r or {}
    esc = r.get("escopo") or ""
    eid = str(r.get("escopo_id") or "")

    def val(k, default=""):
        v = r.get(k)
        return default if v is None else (str(v).lower() if isinstance(v, bool) else str(v))

    def sel(key, label, opts, cur):
        return {
            "key": key,
            "label": label,
            "type": "select",
            "span": "span 1",
            "value": cur,
            "options": [{"value": "", "label": "—"}] + opts,
        }

    campos = [
        {
            "key": "escopo",
            "label": "Escopo*",
            "type": "select",
            "span": "span 2",
            "value": esc,
            "options": [{"value": k, "label": v} for k, v in _ESCOPO_LBL.items()],
        },
        sel("condominio", "…se Condomínio", op["condominio"], eid if esc == "condominio" else ""),
        sel("posto", "…se Posto", op["posto"], eid if esc == "posto" else ""),
        sel("funcao", "…se Função", op["funcao"], eid if esc == "funcao" else ""),
        sel("escala", "…se Escala", op["escala"], eid if esc == "escala" else ""),
        sel("colaborador", "…se Colaborador", op["colaborador"], eid if esc == "colaborador" else ""),
        {
            "key": "tolerancia_entrada_min",
            "label": "Tolerância de entrada (min)",
            "type": "number",
            "span": "span 1",
            "value": val("tolerancia_entrada_min"),
            "ph": "vazio = herda",
        },
        {
            "key": "tolerancia_saida_min",
            "label": "Tolerância de saída (min)",
            "type": "number",
            "span": "span 1",
            "value": val("tolerancia_saida_min"),
            "ph": "vazio = herda",
        },
        {
            "key": "raio_metros",
            "label": "Raio do geofence (m)",
            "type": "number",
            "span": "span 1",
            "value": val("raio_metros"),
            "ph": "vazio = herda",
        },
        {
            "key": "arredondamento_min",
            "label": "Arredondamento (min)",
            "type": "number",
            "span": "span 1",
            "value": val("arredondamento_min"),
            "ph": "vazio = herda",
        },
        {
            "key": "intervalo_minimo_min",
            "label": "Intervalo mínimo (min)",
            "type": "number",
            "span": "span 1",
            "value": val("intervalo_minimo_min"),
            "ph": "vazio = herda",
        },
        {
            "key": "facial_obrigatoria",
            "label": "Facial obrigatória",
            "type": "select",
            "span": "span 1",
            "value": val("facial_obrigatoria"),
            "options": _SN,
        },
        {
            "key": "permitir_fora_do_raio",
            "label": "Permitir batida fora do raio",
            "type": "select",
            "span": "span 1",
            "value": val("permitir_fora_do_raio"),
            "options": _SN,
        },
        {
            "key": "vigencia_inicio",
            "label": "Vigência — início",
            "type": "date",
            "span": "span 1",
            "value": _fd(r.get("vigencia_inicio"), "%Y-%m-%d") if r.get("vigencia_inicio") else "",
        },
        {
            "key": "vigencia_fim",
            "label": "Vigência — fim",
            "type": "date",
            "span": "span 1",
            "value": _fd(r.get("vigencia_fim"), "%Y-%m-%d") if r.get("vigencia_fim") else "",
        },
        {
            "key": "origem_regra",
            "label": "Origem da regra (CCT, cliente, decisão)",
            "type": "textarea",
            "span": "span 2",
            "value": val("origem_regra"),
            "ph": "Ex.: contrato do cliente exige 5 min",
        },
    ]
    if r.get("id") is not None:
        campos.insert(
            0, {"key": "id", "label": "ID (não mude)", "type": "text", "span": "span 2", "value": str(r["id"])}
        )
    return campos


# ───────────────────────────────── telas ─────────────────────────────────
async def _tela_configuracoes(db, op: dict) -> dict:
    regras = await cfg.carregar_regras(db)
    nomes = {k: {o["value"]: o["label"] for o in v} for k, v in op.items()}
    rows_db = (
        (
            await db.execute(
                text(
                    "SELECT id, escopo, escopo_id, tolerancia_entrada_min, tolerancia_saida_min, raio_metros, facial_obrigatoria, "
                    "arredondamento_min, intervalo_minimo_min, permitir_fora_do_raio, aplicado, vigencia_inicio, vigencia_fim, "
                    "origem_regra, criado_por, created_at FROM ponto_configuracoes ORDER BY aplicado DESC, "
                    "array_position(ARRAY['empresa','condominio','posto','funcao','escala','colaborador'], escopo), created_at"
                )
            )
        )
        .mappings()
        .all()
    )

    def onde(r):
        if r["escopo"] == "empresa":
            return "toda a empresa"
        return nomes.get(r["escopo"], {}).get(str(r["escopo_id"]), str(r["escopo_id"]))

    def acoes(r):
        ativo = bool(r["aplicado"])
        return [
            {
                "title": f"Editar configuração #{r['id']} — {_ESCOPO_LBL[r['escopo']]}: {onde(r)}",
                "endpoint": "/api/v1/redesign/action/ponto-config-salvar",
                "method": "POST",
                "btnLabel": "Editar",
                "submitLabel": "Salvar",
                "okMsg": "Configuração salva. Recarregue a tela.",
                "confirm": "Isto muda a tolerância/raio que o mapa de ponto e a triagem aplicam. Confirma?",
                "fields": _campos_config(op, dict(r)),
            },
            {
                "title": ("Desativar" if ativo else "Reativar") + f" configuração #{r['id']}",
                "endpoint": "/api/v1/redesign/action/ponto-config-desativar",
                "method": "POST",
                "btnLabel": "Desativar" if ativo else "Reativar",
                "btnStyle": "danger" if ativo else "primary",
                "submitLabel": "Confirmar",
                "okMsg": "Feito. Recarregue a tela.",
                "confirm": (
                    "A regra deixa de valer e o escopo volta a herdar. Confirma?"
                    if ativo
                    else "A regra volta a valer. Confirma?"
                ),
                "fields": [
                    {"key": "id", "label": "ID", "type": "text", "value": str(r["id"])},
                    {"key": "acao", "label": "Ação", "type": "text", "value": "desativar" if ativo else "reativar"},
                ],
            },
        ]

    rows = [
        {
            "cells": [
                b(_ESCOPO_LBL[r["escopo"]], "info" if r["escopo"] == "empresa" else "ok"),
                t(onde(r), 600, _ND),
                t(_n(r["tolerancia_entrada_min"]), 600),
                t(_n(r["tolerancia_saida_min"])),
                t(_n(r["raio_metros"]), 600),
                t(_sn(r["facial_obrigatoria"])),
                t(_n(r["arredondamento_min"])),
                t(_n(r["intervalo_minimo_min"])),
                t(_sn(r["permitir_fora_do_raio"])),
                t(
                    (_fd(r["vigencia_inicio"]) if r["vigencia_inicio"] else "sempre")
                    + (f" → {_fd(r['vigencia_fim'])}" if r["vigencia_fim"] else "")
                ),
                b("aplicado" if r["aplicado"] else "desativado", "ok" if r["aplicado"] else "mut"),
                t((r["origem_regra"] or "—")[:60]),
            ],
            "filtro": _ESCOPO_LBL[r["escopo"]],
            "actions": acoes(r),
        }
        for r in rows_db
    ]

    efetivo = cfg.resolver(regras)
    painel = [
        {
            "left": f"{c.replace('_', ' ')} · origem: {efetivo['origem'][c]}",
            "right": str(efetivo[c]),
            "color": "#16A34A" if efetivo["origem"][c] != "default do código" else "#64748B",
            "bg": "#E7F7ED" if efetivo["origem"][c] != "default do código" else "#F1F4FA",
        }
        for c in cfg.CAMPOS
    ]
    return {
        "title": "Configurações de ponto por escopo",
        "sub": (
            f"{len(rows_db)} regra(s) · {sum(1 for r in rows_db if r['aplicado'])} aplicada(s) · o mais específico vence: "
            "colaborador > escala > função > posto > condomínio > empresa > default do código · campo vazio herda do escopo acima · "
            "`geofence_zones` do posto (dado antigo) continua vencendo a tolerância quando preenchido · "
            "HOJE só tolerância de entrada e raio são lidos pelo mapa de ponto; os demais ficam guardados até o motor os ler"
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar escopo, posto, pessoa…",
        "grid": "1fr 1.6fr 0.5fr 0.5fr 0.5fr 0.5fr 0.5fr 0.5fr 0.6fr 1fr 0.8fr 1.4fr",
        "cols": [
            "Escopo",
            "Onde vale",
            "Entr. min",
            "Saída min",
            "Raio m",
            "Facial",
            "Arred.",
            "Interv.",
            "Fora raio",
            "Vigência",
            "Estado",
            "Origem",
        ],
        "rows": rows,
        "panelGrid": "1fr",
        "panels": [{"title": "Valor efetivo hoje para a EMPRESA (sem escopo mais específico)", "rows": painel}],
    }


def _tela_config_nova(op: dict) -> dict:
    return {
        "title": "Nova configuração de ponto",
        "sub": "Escolha o escopo e preencha SÓ o que muda — o resto herda. Vigência vazia = sempre.",
        "cta": "Salvar configuração",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/ponto-config-salvar",
            "okMsg": "Configuração salva.",
            "confirm": "Isto muda a tolerância/raio que o mapa de ponto e a triagem aplicam a partir de agora. Confirma?",
        },
        "fields": _campos_config(op),
    }


async def _tela_relogios(db) -> dict:
    agora = regua.agora_manaus()
    reps = (
        await db.execute(
            text(
                "SELECT d.id::text, d.device_name, coalesce(d.model,'rep_p'), d.serial_number, coalesce(em.razao_social, '—'), "
                " coalesce(d.last_sync, (SELECT max(a.created_at) FROM afd_records a WHERE a.device_id = d.id)), d.status, d.is_active, "
                " (SELECT max(a.nsr) FROM afd_records a WHERE a.device_id = d.id), "
                " (SELECT count(*) FROM afd_records a WHERE a.device_id = d.id AND a.record_date >= current_date - 7) "
                "FROM rep_devices d LEFT JOIN empresas em ON em.id = d.condominio_id ORDER BY d.device_name"
            )
        )
    ).all()
    moveis = (
        await db.execute(
            text(
                "SELECT m.id::text, coalesce(m.device_name, m.model, m.device_uuid, '—'), coalesce(m.platform,'—'), coalesce(e.nome, '—'), "
                " m.last_seen_at, coalesce(m.checkin_count,0), coalesce(m.status,'—'), m.is_active "
                "FROM mobile_devices m LEFT JOIN employees e ON e.id = m.employee_id ORDER BY m.last_seen_at DESC NULLS LAST"
            )
        )
    ).all()
    origens = (
        await db.execute(
            text(
                "SELECT coalesce(device_type,'?'), coalesce(device_id,'—'), "
                " count(*) FILTER (WHERE punch_timestamp >= :ini7), max(punch_timestamp), "
                " count(DISTINCT employee_id) FILTER (WHERE punch_timestamp >= :ini7) "
                "FROM gp_clock_punches WHERE punch_timestamp >= :ini30 GROUP BY 1,2 ORDER BY 3 DESC"
            ),
            {
                "ini7": agora.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=7),
                "ini30": agora - timedelta(days=30),
            },
        )
    ).all()

    def estado(ultimo):
        if not ultimo:
            return b("nunca", "bad")
        h = (agora - ultimo).total_seconds() / 3600
        return b("ok", "ok") if h <= 24 else b(f"sem sync há {int(h // 24)} d", "warn")

    rows = []
    for r in reps:
        rows.append(
            {
                "cells": [
                    t(r[1] or r[3], 600, _ND),
                    b(_TIPO_APARELHO.get(r[2], r[2]), "info"),
                    t(r[4]),
                    t(_fd(r[5], "%d/%m %H:%M")),
                    t(_n(r[9]), 600),
                    t(_n(r[8])),
                    estado(r[5]),
                ],
                "filtro": "REP-P",
            }
        )
    for r in moveis:
        rows.append(
            {
                "cells": [
                    t(f"{r[1]} ({r[2]})", 600, _ND),
                    b("celular cadastrado", "info"),
                    t(r[3]),
                    t(_fd(r[4], "%d/%m %H:%M")),
                    t(_n(r[5]), 600),
                    t("—"),
                    estado(r[4]),
                ],
                "filtro": "celular",
            }
        )
    for r in origens:
        rows.append(
            {
                "cells": [
                    t(r[1] if r[1] != "—" else f"origem {r[0]}", 600, _ND),
                    b(_TIPO_APARELHO.get(r[0], r[0]), "mut"),
                    t(f"{r[4]} pessoa(s) em 7 d"),
                    t(_fd(r[3], "%d/%m %H:%M")),
                    t(str(r[2]), 600),
                    t("—"),
                    estado(r[3]),
                ],
                "filtro": _TIPO_APARELHO.get(r[0], r[0]),
            }
        )
    return {
        "title": "Relógios e aparelhos de ponto",
        "sub": (
            f"{len(reps)} REP-P · {len(moveis)} celular(es) cadastrado(s) · {len(origens)} origem(ns) de batida em 30 dias · "
            "SÓ LEITURA: o REP-P nasce sozinho na 1ª batida de cada CNPJ (Portaria 671, `rep_p._dispositivo`) e o celular "
            "nasce no app do colaborador — não há cadastro manual porque não há aparelho físico de relógio nesta empresa · "
            "status: ok ≤ 24 h · sem sync > 24 h · nunca"
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar aparelho, empresa, pessoa…",
        "grid": "1.8fr 1.2fr 1.6fr 1fr 0.8fr 0.7fr 1fr",
        "cols": [
            "Identificação",
            "Tipo",
            "Estabelecimento / pessoa",
            "Último sync",
            "Batidas 7 d",
            "NSR último",
            "Status",
        ],
        "rows": rows or [{"cells": [t("Nenhum aparelho ou batida em 30 dias", 500)] + [t("—")] * 6}],
    }


async def _tela_feriados(db, op: dict) -> dict:
    await cfg._ensure(db)
    conds = {o["value"]: o["label"] for o in op["condominio"]}
    # dgx x3 — quem TRABALHOU em cada feriado, na competência corrente (a conferência da X3;
    # `folha_feriado_conferencia`). 0 pessoas não significa «ninguém trabalhou»: significa que a
    # competência ainda não foi apurada — a coluna diz qual dos dois é.
    trabalhado: dict = {}
    comp_x3, janela_x3 = "—", None
    try:
        from modules.people_management.folha.services import feriado_conferencia as _fc

        _c = (await _fc.competencias(db, 1) or [None])[0]
        if _c:
            comp_x3 = f"{_c[5:7]}/{_c[:4]}"
            janela_x3 = _fc._mes_bounds(int(_c[:4]), int(_c[5:7]))
            trabalhado = await _fc.trabalhado_por_feriado(db, *janela_x3)
    except Exception as exc:  # noqa: BLE001 — a tela de feriados não cai por causa da coluna nova
        logger.debug("dgx x3: contagem de feriado trabalhado indisponível: %s", exc)
    rows_db = (
        await db.execute(
            text(
                "SELECT id::text, data_feriado, coalesce(nome,'—'), coalesce(tipo,'—'), coalesce(escopo,'nacional'), uf, municipio, "
                "condominio_id::text, coalesce(recorrente,false), ano, coalesce(is_active,true), observacao "
                "FROM cct_feriados ORDER BY data_feriado DESC, nome LIMIT 300"
            )
        )
    ).all()

    def onde(r):
        return {
            "nacional": "Brasil",
            "estadual": f"UF {r[5] or '?'}",
            "municipal": f"{r[6] or '?'}{(' / ' + r[5]) if r[5] else ''}",
            "cliente": conds.get(r[7] or "", r[7] or "?"),
        }.get(r[4], "—")

    rows = [
        {
            "cells": [
                t(_fd(r[1]), 600, _ND),
                t(r[2][:50]),
                b(r[3], "mut"),
                b(
                    _ESCOPO_FERIADO.get(r[4], r[4]),
                    {"nacional": "info", "estadual": "ok", "municipal": "warn", "cliente": "bad"}.get(r[4], "mut"),
                ),
                t(onde(r)),
                t(str(r[9] or "—")),
                t("todo ano" if r[8] else "só " + str(r[9] or "—")),
                (
                    b(f"{trabalhado[r[1]]} pessoa(s)", "bad")
                    if trabalhado.get(r[1])
                    else t("0" if janela_x3 and janela_x3[0] <= r[1] <= janela_x3[1] else "fora da competência")
                ),
                b("ativo" if r[10] else "removido", "ok" if r[10] else "mut"),
            ],
            "filtros": {"Escopo": _ESCOPO_FERIADO.get(r[4], r[4]), "Ano": str(r[9] or "—")},
            "actions": [
                {
                    "title": f"Remover feriado — {r[2]} ({_fd(r[1])})",
                    "endpoint": "/api/v1/redesign/action/feriado-remover",
                    "method": "POST",
                    "btnLabel": "Remover",
                    "btnStyle": "danger",
                    "submitLabel": "Remover",
                    "confirm": f"Remover o feriado {r[2]}? Ele deixa de contar para HE em feriado e para os modos de precificação.",
                    "okMsg": "Feriado removido. Recarregue.",
                    "fields": [{"key": "id", "label": "ID", "type": "text", "value": r[0]}],
                }
            ]
            if r[10]
            else [],
        }
        for r in rows_db
    ]
    return {
        "title": "Feriados com escopo",
        "sub": (
            f"{len(rows_db)} feriado(s) · nacional vale para todos · estadual/municipal valem para o condomínio da mesma UF/cidade · "
            "CLIENTE vale só para aquele condomínio (não entra no espelho dos outros nem na precificação) · "
            "fonte: cct_feriados · leitura única: config_ponto.feriados_do_dia · "
            f"a coluna «Trabalhado» é a conferência da X3 na competência {comp_x3} "
            "(aba «Feriado trabalhado e HE 100%», em Folha de pagamento)"
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar feriado…",
        "grid": "0.8fr 2fr 0.8fr 1fr 1.2fr 0.5fr 0.8fr 1fr 0.7fr",
        "cols": [
            "Data",
            "Feriado",
            "Tipo",
            "Escopo",
            "Onde vale",
            "Ano",
            "Recorrente",
            f"Trabalhado ({comp_x3})",
            "Estado",
        ],
        "rows": rows,
    }


def _tela_feriado_novo(op: dict) -> dict:
    return {
        "title": "Novo feriado",
        "sub": "Escopo CLIENTE exige o condomínio. Recorrente = mesmo dia/mês todo ano (ex.: 25/12).",
        "cta": "Salvar feriado",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/feriado-salvar",
            "okMsg": "Feriado cadastrado.",
            "confirm": "Feriado novo muda HE em feriado e os modos 5x2/6x1/SDF da precificação. Confirma?",
        },
        "fields": [
            {"key": "data", "label": "Data*", "type": "date", "span": "span 1"},
            {"key": "nome", "label": "Nome*", "type": "text", "span": "span 1", "ph": "Ex.: Aniversário do condomínio"},
            {
                "key": "escopo",
                "label": "Escopo*",
                "type": "select",
                "span": "span 1",
                "value": "nacional",
                "options": [{"value": k, "label": v} for k, v in _ESCOPO_FERIADO.items()],
            },
            {
                "key": "condominio",
                "label": "Condomínio (se escopo = cliente)",
                "type": "select",
                "span": "span 1",
                "options": [{"value": "", "label": "—"}] + op["condominio"],
            },
            {"key": "uf", "label": "UF (estadual/municipal)", "type": "text", "span": "span 1", "value": "AM"},
            {"key": "municipio", "label": "Município (municipal)", "type": "text", "span": "span 1", "value": "Manaus"},
            {
                "key": "recorrente",
                "label": "Recorrente (todo ano)",
                "type": "select",
                "span": "span 1",
                "value": "false",
                "options": [{"value": "false", "label": "Não"}, {"value": "true", "label": "Sim"}],
            },
            {
                "key": "observacao",
                "label": "Observação",
                "type": "textarea",
                "span": "span 2",
                "ph": "Lei, decreto, contrato…",
            },
        ],
    }


def _tela_cartao_lote(op: dict) -> dict:
    hoje = regua.agora_manaus().date()
    return {
        "title": "Cartão de ponto em lote (PDF único)",
        "sub": (
            "Um PDF com o espelho de cada colaborador, no mesmo padrão-ouro do espelho individual. "
            "Quem não tem espelho CALCULADO fica de fora e é listado na resposta — nada é fabricado. "
            "Calcule o mês na aba «Espelho: calcular/fechar» antes. "
            "Escolha os colaboradores (Ctrl/Shift para vários) ou deixe vazio para todos do filtro. "
            "Preencha início e fim para imprimir a folha do PERÍODO (ex.: 26/07 a 25/08); vazio = mês civil inteiro."
        ),
        "cta": "Gerar PDF",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/cartao-ponto-lote-pdf",
            "okMsg": "PDF pronto — abra ou baixe abaixo.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "competencia",
                "label": "Competência (MM/AAAA)*",
                "type": "text",
                "span": "span 1",
                "value": f"{hoje.month:02d}/{hoje.year}",
            },
            # 28/09/2026 (Pyetra: «não consigo colocar data de início e fim das folhas de ponto
            # quando vou verificar os pontos ou emitir elas todas»): o form só tinha competência
            # MM/AAAA e a janela dela é 26/07→25/08 — não é mês civil nenhum, logo não havia como
            # pedir. `date` não é tipo novo: ModuleView.tsx já renderiza <input type="date">.
            {
                "key": "de",
                "label": "Data de início do período (vazio = mês civil inteiro)",
                "type": "date",
                "span": "span 1",
            },
            {
                "key": "ate",
                "label": "Data final do período (define a competência dos totais)",
                "type": "date",
                "span": "span 1",
            },
            # 28/09/2026: o form não tinha como escolher pessoa — o lote saía com TODOS (medido:
            # 53 espelhos, 14.283.110 bytes, 23,0 s). `multiselect` não é tipo novo: ModuleView.tsx
            # (linhas 1013 e 399) já renderiza <select multiple> e manda a seleção como LISTA JSON.
            {
                "key": "colaboradores",
                "label": "Colaboradores (vazio = todos do filtro)",
                "type": "multiselect",
                "span": "span 2",
                "options": op["colaborador"],
            },
            {
                "key": "condominio",
                "label": "Condomínio / contrato",
                "type": "select",
                "span": "span 1",
                "options": [{"value": "", "label": "— todos —"}] + op["condominio"],
            },
            {
                "key": "funcao",
                "label": "Função",
                "type": "select",
                "span": "span 1",
                "options": [{"value": "", "label": "— todas —"}] + op["funcao"],
            },
            {
                "key": "apenas_com_ponto",
                "label": "Apenas com ponto",
                "type": "select",
                "span": "span 1",
                "value": "false",
                "options": [{"value": "false", "label": "Não"}, {"value": "true", "label": "Sim"}],
            },
            {
                "key": "incluir_demitidos",
                "label": "Trazer demitidos",
                "type": "select",
                "span": "span 1",
                "value": "false",
                "options": [{"value": "false", "label": "Não"}, {"value": "true", "label": "Sim"}],
            },
            {
                "key": "detalhes",
                "label": "Exibir detalhes (dia a dia)",
                "type": "select",
                "span": "span 1",
                "value": "true",
                "options": [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não — só totais"}],
            },
        ],
    }


async def _tela_ausencias(db) -> dict:
    agora = regua.agora_manaus()
    meses = [(agora.year, agora.month)]
    meses.append((agora.year - (agora.month == 1), (agora.month - 2) % 12 + 1))
    rows, meta = [], {}
    for ano, mes in meses:
        m = await aus.ausencias_do_mes(db, ano, mes, agora=agora)
        meta[f"{mes:02d}/{ano}"] = m
        for cliente, c in m["por_cliente"].items():
            rows.append(
                {
                    "cells": [
                        t(f"{mes:02d}/{ano}"),
                        t(cliente.title(), 600, _ND),
                        t(str(c["planejados"]), 600),
                        t(str(c["trabalhados"]), 500, "#16A34A"),
                        b(str(c["faltas"]), "bad" if c["faltas"] else "mut"),
                        b(str(c["atrasos"]), "warn" if c["atrasos"] else "mut"),
                        t(str(c["posto_incorreto"])),
                        t(str(c["pendentes"]), 400, "#94A3B8"),
                        t(str(c["justificadas"])),
                        t(str(c["afastados"])),
                        t(str(c["ferias"])),
                    ],
                    "filtros": {"Mês": f"{mes:02d}/{ano}", "Condomínio": cliente.title()},
                }
            )
    atual = meta[f"{agora.month:02d}/{agora.year}"]
    pessoas = [p for p in atual["por_pessoa"] if p["faltas"] or p["atrasos"]][:40]
    painel = [
        {
            "left": f"{p['nome'].title()} — {p['cliente'].title()} · {p['turnos']} turno(s)",
            "right": f"{p['faltas']} falta(s) · {p['atrasos']} atraso(s)",
            "color": "#B91C1C" if p["faltas"] else "#B45309",
            "bg": "#FEF2F2" if p["faltas"] else "#FFFBEB",
        }
        for p in pessoas
    ] or [
        {
            "left": "Ninguém com falta ou atraso no mês (calculado, não vazio)",
            "right": "0",
            "color": "#16A34A",
            "bg": "#E7F7ED",
        }
    ]
    return {
        "title": "Ausências — por mês e condomínio",
        "sub": (
            f"{agora.month:02d}/{agora.year} até {agora:%d/%m %H:%M}: {atual['planejados']} turno(s) cobrados de {atual['lancados']} lançados · "
            "MESMA régua do mapa de ponto (frente 04): falta = turno sem batida após a tolerância; atraso = 1ª batida depois de início+tolerância; "
            "pendente = ainda não venceu · férias/afastado não são cobrados (coorte) e aparecem nas colunas próprias · "
            "justificadas = justificativas abertas no mês (gp_justifications)"
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar condomínio…",
        "grid": "0.6fr 1.6fr 0.6fr 0.7fr 0.5fr 0.5fr 0.6fr 0.6fr 0.6fr 0.6fr 0.5fr",
        "cols": [
            "Mês",
            "Condomínio",
            "Planejados",
            "Trabalhados",
            "Faltas",
            "Atrasos",
            "Posto incorreto",
            "Pendentes",
            "Justificadas",
            "Afastados",
            "Férias",
        ],
        "rows": rows or [{"cells": [t("Nenhum turno na escala dos dois meses", 500)] + [t("—")] * 10}],
        "panelGrid": "1fr",
        "panels": [
            {
                "title": f"Faltas por colaborador — {agora.month:02d}/{agora.year} (do pior para o melhor)",
                "rows": painel,
            }
        ],
        "_meta": atual,
    }


#: Quantas competências a aba de apropriação carrega. 2 = o mês corrente e o que o DP fecha.
_APROP_COMPS = 2


def _apropriacao_linhas(mes_ano: list[tuple[int, int]]) -> tuple[list[dict], list[str], int]:
    """Uma linha por colaborador×dia, vinda do MOTOR — sem SQL de pareamento aqui.

    ⭐ Reúso obrigatório: `ler_espelho` (a mesma fonte do PDF assinado) + `dias_com_segmentos` +
    `_dia_da_tela` (o mesmo formatador da tela de espelho). Esta casa já tem TRÊS réguas de
    pareamento que discordam em 59 pessoa×dia; uma quarta aqui seria o defeito, não a entrega.

    Quem não tem espelho CALCULADO na competência fica de fora e é CONTADO no subtítulo — nada
    é estimado (o mês se calcula na aba «Espelho: calcular/fechar»).
    """
    from core.database.session import SyncSessionLocal
    from modules.people_management.hr.services.espelho_ponto_service import ler_espelho
    from modules.people_management.ponto.controllers.punch_controller import (
        _dia_da_tela,
        dias_com_segmentos,
    )

    linhas: list[dict] = []
    comps: list[str] = []
    sem = 0
    with SyncSessionLocal() as s:
        for ano, mes in mes_ano:
            comp = f"{mes:02d}/{ano}"
            comps.append(comp)
            ids = s.execute(
                text(
                    "SELECT CAST(employee_id AS TEXT), coalesce(employee_name,'—') FROM time_sheets "
                    " WHERE reference_month=:m AND reference_year=:y AND coalesce(is_deleted,false)=false "
                    " ORDER BY 2"
                ),
                {"m": mes, "y": ano},
            ).all()
            # Quem BATEU no mês e não tem espelho calculado não pode sumir sem aviso: a tela
            # não fabrica a jornada dele, mas diz quantos são (o cálculo é na aba
            # «Espelho: calcular/fechar»).
            sem += int(
                s.execute(
                    text(
                        "SELECT count(DISTINCT p.employee_id) FROM gp_clock_punches p "
                        " WHERE date_trunc('month', p.punch_timestamp) = make_date(:y,:m,1) "
                        "   AND NOT EXISTS (SELECT 1 FROM time_sheets ts "
                        "        WHERE CAST(ts.employee_id AS TEXT) = CAST(p.employee_id AS TEXT) "
                        "          AND ts.reference_month=:m AND ts.reference_year=:y "
                        "          AND coalesce(ts.is_deleted,false)=false)"
                    ),
                    {"m": mes, "y": ano},
                ).scalar()
                or 0
            )
            for eid, nome in ids:
                esp = ler_espelho(s, eid, mes, ano)
                if esp is None:
                    continue
                for d in dias_com_segmentos(s, esp, mes, ano):
                    linha = _dia_da_tela(d)
                    linha["_nome"] = (esp.get("employee_name") or nome or "—").title()
                    linha["_comp"] = comp
                    linhas.append(linha)
    linhas.sort(key=lambda r: (r["_nome"], r["data"]))
    return linhas, comps, sem


async def _tela_apropriacao(db) -> dict:
    """Apropriação de horas — o que o Sólides mostra: cada par do dia em sua própria coluna."""
    from starlette.concurrency import run_in_threadpool

    # A competência CORRENTE e a anterior — não «as duas últimas do `time_sheets`»: há espelho
    # gravado de 10/2026 (3 linhas, mês que não chegou), e ele viraria o padrão do filtro,
    # abrindo a tela quase vazia. Manaus, porque o mês do DP é o de Manaus.
    hoje_m = regua.agora_manaus().date()
    comps = [(hoje_m.year, hoje_m.month)]
    for _ in range(_APROP_COMPS - 1):
        ano, mes = comps[-1]
        comps.append((ano - 1, 12) if mes == 1 else (ano, mes - 1))
    linhas, labels, sem = await run_in_threadpool(_apropriacao_linhas, comps)

    def _hora(v: str) -> dict:
        return t(v or "—", 500 if v else 400, _ND if v else "#94A3B8")

    rows = []
    for r in linhas:
        quebrado = "intervalo quebrado" in r["obs"]
        saldo = r.get("saldo_min")
        rows.append(
            {
                "cells": [
                    t(r["_nome"], 600, _ND),
                    t(r["dia"], 500),
                    t(r["dia_semana"]),
                    _hora(r["entrada1"]),
                    _hora(r["saida1"]),
                    _hora(r["entrada2"]),
                    _hora(r["saida2"]),
                    t(r["intervalo"] or "—", 400, "#B45309" if quebrado else None),
                    t(r["total"], 600),
                    t(r["previsto"]),
                    b(r["saldo_dia"], "mut" if saldo in (0, None) else ("ok" if saldo > 0 else "bad")),
                    t(r["obs"] or "", 400, "#B45309" if r["obs"] else None),
                ],
                # os dropdowns do ModuleView (scr.filtros): a Pyetra escolhe UMA pessoa e a
                # competência, como fazia no Sólides.
                "filtros": {"Colaborador": r["_nome"], "Competência": r["_comp"]},
            }
        )
    return {
        "title": "Apropriação de horas (dia a dia, par a par)",
        "sub": (
            "Cada PAR de batidas do dia na sua própria coluna: um plantão 19:00→02:00 + 03:00→07:17 aparece "
            "como as duas linhas que o Sólides mostra, com o intervalo entre elas — e não como «19:00 → 07:17». "
            f"Fonte: `time_sheets` (a MESMA do PDF assinado) + o motor legal de pareamento. Competências: {', '.join(labels) or '—'}. "
            f"{len(rows)} dia(s)"
            + (
                f" · {sem} colaborador(es) bateram ponto e NÃO têm espelho calculado nestas "
                "competências — ficam de fora (calcule na aba «Espelho: calcular/fechar»); nada é estimado"
                if sem
                else ""
            )
            + " · dia com 3+ marcações não cabe em 4 colunas: a coluna Obs diz quantas faltam e o espelho traz todas "
            "· «intervalo quebrado» = falta uma batida do par, e o dia aparece COMO quebrado, nunca como normal."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar colaborador…",
        "grid": "1.6fr 0.5fr 0.4fr 0.5fr 0.5fr 0.5fr 0.5fr 0.6fr 0.6fr 0.6fr 0.6fr 1.2fr",
        "cols": [
            "Colaborador",
            "Data",
            "Dia",
            "Ent.1",
            "Saí.1",
            "Ent.2",
            "Saí.2",
            "Intervalo",
            "Trabalhadas",
            "Previsto",
            "Saldo",
            "Obs",
        ],
        "filtros": [
            {"key": "Colaborador", "label": "Colaborador"},
            # padrão = competência corrente (a 1ª de `comps`); sem isto a tela abriria com dois
            # meses misturados na mesma grade.
            {"key": "Competência", "label": "Competência", "padrao": labels[0] if labels else None},
        ],
        "rows": rows
        or [{"cells": [t("Nenhum espelho calculado nas últimas competências", 500)] + [t("—")] * 11}],
    }


async def telas(db, out: dict | None = None) -> dict:
    mine: dict = {}
    try:
        op = await _opcoes(db)
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        op = {k: [] for k in ("condominio", "posto", "funcao", "escala", "colaborador")}
        logger.error("dgx f7: opções: %s", exc)
    montagens = [
        ("ponto-configuracoes", "Configurações de ponto", lambda: _tela_configuracoes(db, op)),
        ("ponto-configuracao-nova", "Nova configuração", lambda: _tela_config_nova(op)),
        ("relogios-ponto", "Relógios/aparelhos", lambda: _tela_relogios(db)),
        ("feriados", "Feriados", lambda: _tela_feriados(db, op)),
        ("feriado-novo", "Novo feriado", lambda: _tela_feriado_novo(op)),
        ("cartao-ponto-lote", "Cartão de ponto em lote", lambda: _tela_cartao_lote(op)),
        ("ausencias-dashboard", "Ausências", lambda: _tela_ausencias(db)),
        ("apropriacao-horas", "Apropriação de horas", lambda: _tela_apropriacao(db)),
        # 28/09/2026 — a aba única do ponto (pedido da Pyetra). Não carrega grade nenhuma no
        # payload do módulo: é só o filtro, e a grade vem da consulta. Por isso é a aba mais
        # barata do grupo, mesmo sendo a que faz mais.
        ("ponto-colaborador", "Ponto do colaborador", lambda: _tela_ponto_colaborador(op)),
    ]
    for tid, titulo, fn in montagens:
        try:
            r = fn()
            mine[tid] = await r if hasattr(r, "__await__") else r
        except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
            await db.rollback()
            mine[tid] = _falhou(titulo, exc)

    grupo = (out or {}).get("g-ponto")
    if isinstance(grupo, dict) and isinstance(grupo.get("tabs"), list):
        from modules.operacional.controllers.redesign_data_controller import moved

        ja = {tb.get("id") for tb in grupo["tabs"]}
        for tid, lbl in ABAS:
            if tid in mine and tid not in ja:
                grupo["tabs"].append({"id": tid, "label": lbl, "screen": mine[tid]})
                mine[tid] = moved("g-ponto", tid)
    return mine


# ───────────────────────── ações (POST /api/v1/redesign/action/…) ─────────────────────────
router = APIRouter()


@router.post("/action/ponto-config-salvar", dependencies=[Depends(_require_dp)])
async def rd_ponto_config_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await cfg._ensure(db)
    escopo = str(payload.get("escopo") or "").strip().lower()
    if escopo not in cfg.ESCOPOS:
        raise HTTPException(
            status_code=400, detail="Escopo inválido. Use empresa, condomínio, posto, função, escala ou colaborador."
        )
    escopo_id = "" if escopo == "empresa" else str(payload.get(escopo) or "").strip()
    if escopo != "empresa" and not escopo_id:
        raise HTTPException(status_code=400, detail=f"Escolha o {_ESCOPO_LBL[escopo].lower()} a que a regra se aplica.")
    vals = {
        "tolerancia_entrada_min": _int(payload.get("tolerancia_entrada_min"), "Tolerância de entrada"),
        "tolerancia_saida_min": _int(payload.get("tolerancia_saida_min"), "Tolerância de saída"),
        "raio_metros": _int(payload.get("raio_metros"), "Raio"),
        "arredondamento_min": _int(payload.get("arredondamento_min"), "Arredondamento"),
        "intervalo_minimo_min": _int(payload.get("intervalo_minimo_min"), "Intervalo mínimo"),
        "facial_obrigatoria": _bool(payload.get("facial_obrigatoria")),
        "permitir_fora_do_raio": _bool(payload.get("permitir_fora_do_raio")),
    }
    if vals["raio_metros"] == 0:
        raise HTTPException(status_code=400, detail="Raio precisa ser maior que zero (ou vazio para herdar).")
    if all(v is None for v in vals.values()):
        raise HTTPException(status_code=400, detail="Preencha ao menos um valor — uma regra vazia não muda nada.")
    vi, vf = (
        _data(payload.get("vigencia_inicio"), "Vigência início"),
        _data(payload.get("vigencia_fim"), "Vigência fim"),
    )
    if vi and vf and vf < vi:
        raise HTTPException(status_code=400, detail="Vigência: fim antes do início.")
    params = dict(
        vals,
        escopo=escopo,
        escopo_id=escopo_id,
        vi=vi,
        vf=vf,
        origem=(str(payload.get("origem_regra") or "").strip() or None),
        quem=str(getattr(current_user, "email", None) or getattr(current_user, "id", "") or "")[:120],
    )
    rid = str(payload.get("id") or "").strip()
    if rid:
        params["id"] = int(rid) if rid.isdigit() else -1
        n = (
            await db.execute(
                text(
                    "UPDATE ponto_configuracoes SET escopo=:escopo, escopo_id=:escopo_id, tolerancia_entrada_min=:tolerancia_entrada_min, "
                    "tolerancia_saida_min=:tolerancia_saida_min, raio_metros=:raio_metros, arredondamento_min=:arredondamento_min, "
                    "intervalo_minimo_min=:intervalo_minimo_min, facial_obrigatoria=:facial_obrigatoria, permitir_fora_do_raio=:permitir_fora_do_raio, "
                    "vigencia_inicio=:vi, vigencia_fim=:vf, origem_regra=:origem, updated_at=now() WHERE id=:id"
                ),
                params,
            )
        ).rowcount
        if not n:
            raise HTTPException(status_code=404, detail=f"Configuração #{rid} não existe.")
        msg = f"Configuração #{rid} atualizada"
    else:
        rid = (
            await db.execute(
                text(
                    "INSERT INTO ponto_configuracoes (escopo, escopo_id, tolerancia_entrada_min, tolerancia_saida_min, raio_metros, arredondamento_min, "
                    "intervalo_minimo_min, facial_obrigatoria, permitir_fora_do_raio, vigencia_inicio, vigencia_fim, origem_regra, criado_por) "
                    "VALUES (:escopo, :escopo_id, :tolerancia_entrada_min, :tolerancia_saida_min, :raio_metros, :arredondamento_min, "
                    ":intervalo_minimo_min, :facial_obrigatoria, :permitir_fora_do_raio, :vi, :vf, :origem, :quem) RETURNING id"
                ),
                params,
            )
        ).scalar()
        msg = f"Configuração #{rid} criada"
    await db.commit()
    efetivo = cfg.resolver(await cfg.carregar_regras(db), **{escopo: escopo_id} if escopo != "empresa" else {})
    return {
        "ok": True,
        "id": rid,
        "message": f"{msg} ({_ESCOPO_LBL[escopo]}). Efetivo neste escopo agora: entrada {efetivo['tolerancia_entrada_min']} min · raio {efetivo['raio_metros']} m.",
    }


@router.post("/action/ponto-config-desativar", dependencies=[Depends(_require_dp)])
async def rd_ponto_config_desativar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await cfg._ensure(db)
    rid = str(payload.get("id") or "").strip()
    if not rid.isdigit():
        raise HTTPException(status_code=400, detail="Informe o ID da configuração.")
    reativar = str(payload.get("acao") or "desativar").strip().lower() == "reativar"
    n = (
        await db.execute(
            text("UPDATE ponto_configuracoes SET aplicado=:a, updated_at=now() WHERE id=:id"),
            {"a": reativar, "id": int(rid)},
        )
    ).rowcount
    if not n:
        raise HTTPException(status_code=404, detail=f"Configuração #{rid} não existe.")
    await db.commit()
    return {
        "ok": True,
        "message": f"Configuração #{rid} {'reativada' if reativar else 'desativada'} — o escopo {'volta a valer' if reativar else 'volta a herdar'}.",
    }


@router.post("/action/feriado-salvar", dependencies=[Depends(_require_dp)])
async def rd_feriado_salvar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await cfg._ensure(db)
    d = _data(payload.get("data"), "Data", obrigatoria=True)
    nome = str(payload.get("nome") or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Informe o nome do feriado.")
    escopo = str(payload.get("escopo") or "nacional").strip().lower()
    if escopo not in _ESCOPO_FERIADO:
        raise HTTPException(status_code=400, detail="Escopo: nacional, estadual, municipal ou cliente.")
    cond = str(payload.get("condominio") or "").strip() or None
    if escopo == "cliente" and not cond:
        raise HTTPException(status_code=400, detail="Feriado de CLIENTE exige o condomínio.")
    uf = (str(payload.get("uf") or "").strip().upper()[:2] or None) if escopo in ("estadual", "municipal") else None
    mun = (str(payload.get("municipio") or "").strip()[:80] or None) if escopo == "municipal" else None
    conv = (
        await db.execute(
            text(
                "SELECT id FROM cct_convencoes ORDER BY is_vigente DESC NULLS LAST, data_inicio DESC NULLS LAST LIMIT 1"
            )
        )
    ).scalar()
    if conv is None:
        raise HTTPException(
            status_code=400, detail="Não há convenção (cct_convencoes) para ancorar o feriado — cadastre a CCT antes."
        )
    dup = (
        await db.execute(
            text(
                "SELECT 1 FROM cct_feriados WHERE data_feriado=:d AND lower(nome)=lower(:n) AND coalesce(is_active,true) "
                "AND coalesce(escopo,'nacional')=:e AND coalesce(condominio_id::text,'')=coalesce(:c,'')"
            ),
            {"d": d, "n": nome, "e": escopo, "c": cond},
        )
    ).first()
    if dup:
        raise HTTPException(status_code=400, detail=f"«{nome}» em {d:%d/%m/%Y} já existe com este escopo.")
    fid = (
        await db.execute(
            text(
                "INSERT INTO cct_feriados (id, convencao_id, data_feriado, nome, tipo, ano, is_active, escopo, uf, municipio, condominio_id, recorrente, observacao) "
                "VALUES (gen_random_uuid(), :conv, :d, :n, :tipo, :ano, true, :e, :uf, :mun, CAST(:c AS uuid), :rec, :obs) RETURNING id::text"
            ),
            {
                "conv": conv,
                "d": d,
                "n": nome[:100],
                "tipo": escopo,
                "ano": d.year,
                "e": escopo,
                "uf": uf,
                "mun": mun,
                "c": cond,
                "rec": bool(_bool(payload.get("recorrente"))),
                "obs": (
                    str(payload.get("observacao") or "").strip()
                    or f"cadastrado pela tela feriado-novo por {getattr(current_user, 'email', '')}"
                )[:500],
            },
        )
    ).scalar()
    await db.commit()
    return {
        "ok": True,
        "id": fid,
        "message": f"Feriado «{nome}» em {d:%d/%m/%Y} ({_ESCOPO_FERIADO[escopo]}) cadastrado.",
    }


@router.post("/action/feriado-remover", dependencies=[Depends(_require_dp)])
async def rd_feriado_remover(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Remover = `is_active=false` (o espelho e a precificação já filtram por is_active). Nada é apagado."""
    fid = str(payload.get("id") or "").strip()
    if not fid:
        raise HTTPException(status_code=400, detail="Informe o feriado.")
    n = (
        await db.execute(
            text(
                "UPDATE cct_feriados SET is_active=false, updated_at=now() WHERE id::text=:id AND coalesce(is_active,true)"
            ),
            {"id": fid},
        )
    ).rowcount
    if not n:
        raise HTTPException(status_code=404, detail="Feriado não encontrado (ou já removido).")
    await db.commit()
    return {"ok": True, "message": "Feriado removido (inativado). Limpe o cache da CCT se a folha já o tiver lido."}


def _ids_lote(v) -> list[str] | None:
    """Seleção de colaboradores → lista de ids, ou None quando ela não escolheu ninguém.

    28/09/2026: o front `multiselect` manda LISTA (ModuleView.corpoComJson faz JSON.parse); o
    Hermes/curl manda string separada por vírgula. Os dois formatos existem, então conte os dois
    antes de padronizar. `None` = sem seleção = todos do filtro (comportamento de hoje); lista
    vazia NUNCA volta como None, porque devolver as 53 quando ela pediu 2 seria mentir.
    """
    if v is None:
        return None
    itens = v if isinstance(v, (list, tuple, set)) else str(v).split(",")
    ids = [s for s in (str(x).strip() for x in itens) if s]
    return ids or None


def _periodo_lote(payload_de, payload_ate) -> tuple[date, date] | None:
    """(ini, fim) do período livre, ou None quando ela não pediu período.

    28/09/2026 — as DUAS datas ou nenhuma: uma só seria um período com metade inventada pelo
    sistema (fim do mês? hoje?), e a folha sairia com dias que ela não pediu. Falha FECHADO.
    """
    de, ate = str(payload_de or "").strip()[:10], str(payload_ate or "").strip()[:10]
    if not de and not ate:
        return None
    if not (de and ate):
        raise HTTPException(
            status_code=400,
            detail="Informe as DUAS datas do período (início e fim), ou deixe as duas vazias para o mês civil inteiro.",
        )
    try:
        ini, fim = date.fromisoformat(de), date.fromisoformat(ate)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Data inválida em «{de}» / «{ate}»: use AAAA-MM-DD.") from None
    if ini > fim:
        raise HTTPException(status_code=400, detail=f"Período invertido: {ini:%d/%m/%Y} vem depois de {fim:%d/%m/%Y}.")
    return ini, fim


def _filtros_lote(payload: dict) -> dict:
    # Com período, a competência dos TOTAIS é o mês do FIM (25/08 → 08/2026, a convenção de
    # `janela_26a25`) — derivada, nunca lida do campo: competência 07 com período 26/07→25/08
    # imprimiria dias de agosto sob somas de julho, coerente na aparência e errado.
    per = _periodo_lote(payload.get("de"), payload.get("ate"))
    ano, mes = (per[1].year, per[1].month) if per else _competencia(payload.get("competencia"))
    return {
        "ano": ano,
        "mes": mes,
        "de": per[0] if per else None,
        "ate": per[1] if per else None,
        "ids": _ids_lote(payload.get("colaboradores")),
        "cond": str(payload.get("condominio") or "").strip() or None,
        "funcao": str(payload.get("funcao") or "").strip() or None,
        "apenas_com_ponto": bool(_bool(payload.get("apenas_com_ponto"))),
        "demitidos": bool(_bool(payload.get("incluir_demitidos"))),
        "detalhes": _bool(payload.get("detalhes")) is not False,
    }


@router.post("/action/cartao-ponto-lote-pdf", dependencies=[Depends(_require_dp)])
async def rd_cartao_lote(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Devolve o LINK do PDF (padrão `relatorio-pagamento-pdf`): conta quem tem espelho calculado antes de prometer."""
    f = _filtros_lote(payload)
    n_cand, n_com = (
        await db.execute(
            text(
                "SELECT count(*), count(*) FILTER (WHERE EXISTS (SELECT 1 FROM time_sheets ts WHERE ts.employee_id = e.id::text "
                "  AND ts.reference_month=:m AND ts.reference_year=:a AND coalesce(ts.is_deleted,false)=false)) "
                "FROM employees e WHERE coalesce(e.is_homologacao,false)=false "
                "AND (lower(coalesce(e.status,''))='ativo' OR (CAST(:dem AS boolean) AND lower(coalesce(e.status,''))='demitido')) "
                "AND (CAST(:cond AS text) IS NULL OR e.cliente_id = (SELECT c.client_id FROM condominios c WHERE c.id::text=CAST(:cond AS text))) "
                "AND (CAST(:funcao AS text) IS NULL OR upper(coalesce(e.cargo,''))=upper(CAST(:funcao AS text)))"
                # 28/09/2026: a contagem tinha de ganhar o MESMO filtro de seleção que `candidatos()`,
                # senão a mensagem prometia "53 de 53" e o PDF vinha com 2 — as duas pontas medindo
                # coisas diferentes. `string_to_array` porque :ids viaja como texto (a mesma string
                # que vai na query do GET).
                "AND (CAST(:ids AS text) IS NULL OR e.id::text = ANY(string_to_array(CAST(:ids AS text), ',')))"
            ),
            {
                "m": f["mes"],
                "a": f["ano"],
                "dem": f["demitidos"],
                "cond": f["cond"],
                "funcao": f["funcao"],
                "ids": ",".join(f["ids"]) if f["ids"] else None,
            },
        )
    ).one()
    # Seleção que não casa com os outros filtros NÃO pode virar "todos": diz que não casou.
    if f["ids"] and not n_cand:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Nenhum dos {len(f['ids'])} colaborador(es) selecionado(s) passa pelos outros filtros "
                f"(condomínio/função/demitidos) — o lote sairia vazio, não com todos. Revise a seleção."
            ),
        )
    if not n_com:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Nenhum dos {n_cand} colaborador(es) do filtro tem espelho CALCULADO em {f['mes']:02d}/{f['ano']}. "
                "Calcule o mês na aba «Espelho: calcular/fechar» antes."
            ),
        )
    # A competência dos totais vai no rótulo/mensagem junto do período: quem recebe o PDF tem de
    # ler de quais duas coisas ele é feito (dias do período, somas do mês civil).
    per = f"{f['de']:%d/%m/%Y} a {f['ate']:%d/%m/%Y}" if f["de"] else None
    comp = f"{f['mes']:02d}/{f['ano']}"
    qs = (
        f"?condominio={f['cond'] or ''}&funcao={f['funcao'] or ''}&apenas_com_ponto={int(f['apenas_com_ponto'])}"
        f"&incluir_demitidos={int(f['demitidos'])}&detalhes={int(f['detalhes'])}"
        f"&colaboradores={','.join(f['ids']) if f['ids'] else ''}"
        + (f"&de={f['de']:%Y-%m-%d}&ate={f['ate']:%Y-%m-%d}" if f["de"] else "")
    )
    return {
        "ok": True,
        "message": (
            f"{n_com} de {n_cand} colaborador(es) com espelho em {comp} — "
            f"{n_cand - n_com} sem espelho ficam de fora."
            + (
                f" Dias impressos: {per}. Os totais de cada folha são do mês civil "
                f"{comp} e vêm rotulados assim no PDF."
                if per
                else ""
            )
        ),
        "doc": {
            "label": f"Cartão de ponto em lote {per or comp}",
            "url": f"/api/v1/redesign/cartao-ponto-lote/{f['ano']}/{f['mes']}/pdf{qs}",
            "fmt": "pdf",
            "mode": "blob",
            "filename": (
                f"cartao_ponto_lote_{f['de']:%Y%m%d}_{f['ate']:%Y%m%d}.pdf"
                if f["de"]
                else f"cartao_ponto_lote_{f['ano']}_{f['mes']:02d}.pdf"
            ),
            "gate": "dp",
        },
    }


@router.get(
    "/cartao-ponto-lote/{ano}/{mes}/pdf",
    dependencies=[Depends(_require_dp)],
    summary="Cartão de ponto em lote (PDF único, padrão-ouro)",
)
async def rd_cartao_lote_get(
    ano: int,
    mes: int,
    current_user: CurrentActiveUser,
    condominio: str = "",
    funcao: str = "",
    apenas_com_ponto: int = 0,
    incluir_demitidos: int = 0,
    detalhes: int = 1,
    colaboradores: str = "",
    de: str = "",
    ate: str = "",
):
    from fastapi.responses import Response
    from starlette.concurrency import run_in_threadpool

    from core.database.session import SyncSessionLocal

    if not 1 <= mes <= 12:
        raise HTTPException(status_code=400, detail="Mês inválido.")

    # Mesma validação do POST (as duas datas ou nenhuma, na ordem certa): esta rota MONTA o PDF e
    # é chamável direto pelo link/curl, então não pode confiar em quem montou a query string.
    per = _periodo_lote(de, ate)

    # 28/09/2026: esta rota MONTA o PDF e refazia a lista sozinha — filtrar só no POST deixaria
    # o link gerando as 53 de novo (as duas pontas). `colaboradores` vazio = None = todos.
    pedidos = _ids_lote(colaboradores)

    def _montar():
        with SyncSessionLocal() as s:
            ids = [
                i
                for i, _n in cartao_lote.candidatos(
                    s, condominio or None, funcao or None, bool(incluir_demitidos), pedidos
                )
            ]
            return cartao_lote.montar_cartao_lote(
                s,
                mes,
                ano,
                ids,
                apenas_com_ponto=bool(apenas_com_ponto),
                detalhes=bool(detalhes),
                de=per[0] if per else None,
                ate=per[1] if per else None,
            )

    pdf, relato = await run_in_threadpool(_montar)
    # `relato` tem uma entrada por id PEDIDO: vazio com seleção = a seleção não casou com os
    # outros filtros. Dizer isso, nunca devolver o lote inteiro como se fosse o pedido dela.
    if pedidos and not relato:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Nenhum dos {len(pedidos)} colaborador(es) selecionado(s) passa pelos outros filtros "
                "(condomínio/função/demitidos). Nada foi gerado — revise a seleção."
            ),
        )
    if not pdf:
        raise HTTPException(status_code=404, detail=f"Ninguém do filtro tem espelho calculado em {mes:02d}/{ano}.")
    arq = f"cartao_ponto_lote_{per[0]:%Y%m%d}_{per[1]:%Y%m%d}.pdf" if per else f"cartao_ponto_lote_{ano}_{mes:02d}.pdf"
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{arq}"',
            "X-Cartao-Lote": f"{sum(1 for r in relato if 'paginas' in r)} espelho(s); {sum(1 for r in relato if 'motivo' in r)} sem espelho",
            # Header de auditoria: em que janela os DIAS saíram e de que competência são os TOTAIS.
            # Duas coisas, duas janelas — quem baixa por curl precisa ler isso sem abrir o PDF.
            "X-Cartao-Lote-Janela": (
                f"dias {per[0]:%d/%m/%Y} a {per[1]:%d/%m/%Y}; totais do mes civil {mes:02d}/{ano}"
                if per
                else f"dias e totais do mes civil {mes:02d}/{ano}"
            ),
        },
    )


# ═══════════════════════════════════════════════════════════════════════════════════════════
# «Ponto do colaborador» — UMA aba para o trabalho inteiro do ponto (28/09/2026)
# ═══════════════════════════════════════════════════════════════════════════════════════════
#
# POR QUE ESTA ABA EXISTE. A Pyetra (DP/RH) escreveu hoje, sobre o que já estava entregue:
#
#   «Fica muito difícil que sejam tudo e em abas separadas, providenciar que estejam tudo na
#    mesma aba: Pontos, Aprovações, Fotos, Ajustes de ponto e etc. temos que criar o sistema
#    para FACILITAR e não COMPLICAR»
#   «Não consigo colocar data de início e fim das folhas de ponto quando vou verificar os
#    pontos ou emitir elas todas»
#
# CONTADO ANTES DE DESENHAR: para conferir o ponto de UMA pessoa num período ela atravessava
# DOIS módulos e CINCO abas — «Apropriação de horas», «Ajustar batida» e «Cartão de ponto em
# lote» (Departamento Pessoal → Ponto & Jornada), mais «Ponto · Fila de aprovação» e «Ponto
# eletrônico» (Gestão de Pessoas). E nenhuma das cinco aceitava as duas datas dela: a janela do
# DP é 26→25 (26/07 a 25/08), que não é mês civil nenhum.
#
# NADA DE MOTOR NOVO. A grade lê `punch_controller.get_espelho_mensal(de=, ate=)`, que lê
# `time_sheets` — a MESMA fonte do PDF assinado — e já devolve `segmentos` por dia. Esta casa
# tem TRÊS réguas de pareamento que discordam em 59 pessoa×dia; uma quarta seria o defeito, não
# a entrega. O que esta aba acrescenta é a leitura: a foto ao lado da hora, o local de cada
# ponta, o status de aprovação e os botões — tudo sobre o número que o motor já apurou.
#
# POR QUE É UM `form` COM RESULTADO EM TABELA, e não uma tela `table`: a grade depende do que
# ela escolhe (colaborador + as duas datas), então não pode vir pré-carregada no payload do
# módulo, e os filtros da tabela são dropdowns de IGUALDADE sobre linhas já carregadas — não
# sabem pedir período. O ModuleView ganhou por isto UMA linha: um form com `showResult` que
# devolve `tabela` renderiza aquela grade com o TableScreen de sempre (célula de foto, ações
# por linha e `docs` por linha já existiam lá).


def _tela_ponto_colaborador(op: dict) -> dict:
    """Filtro (colaborador + as DUAS datas) e mais nada: a grade nasce da consulta."""
    from modules.people_management.ponto.dias_corridos import janela_26a25

    hoje = regua.agora_manaus().date()
    ini, fim = janela_26a25(hoje.month, hoje.year)
    return {
        "title": "Ponto do colaborador (período, fotos, aprovação e impressão numa tela)",
        "sub": (
            "Escolha a pessoa e as DUAS datas — a janela do DP é 26→25, não o mês civil, e aqui "
            "qualquer recorte é aceito. A grade traz cada TRECHO do dia (um plantão 19:00→02:00 + "
            "03:00→07:17 são duas linhas, como no Sólides), a SELFIE ao lado de cada hora, o local "
            "de cada ponta, o rodapé do dia (trabalhadas · intervalos · previsto · saldo) e os "
            "botões de aprovar/reprovar, registrar batida e imprimir — sem trocar de aba. "
            "Fonte: `time_sheets`, a MESMA do PDF assinado; nenhuma hora é estimada aqui."
        ),
        "cta": "Consultar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/ponto-do-colaborador",
            "okMsg": "Período consultado.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "employee_id",
                "label": "Colaborador*",
                "type": "select",
                "span": "span 2",
                "ph": "Selecione a pessoa",
                "options": op["colaborador"],
            },
            # `value` já preenchido com a janela 26→25 CORRENTE: ela abre a aba e clica Consultar.
            # É a janela dela, não um mês civil — e continua editável, que é o pedido original.
            {"key": "de", "label": "Data de início*", "type": "date", "span": "span 1", "value": ini.isoformat()},
            {"key": "ate", "label": "Data final*", "type": "date", "span": "span 1", "value": fim.isoformat()},
        ],
    }


#: Status de batida → (rótulo, cor). O check verde é SÓ `approved`: `normal`/`pending` é
#: aguardando conferência, e `pendente_de_conferencia` é o SERVIDOR reconferindo o rosto — não
#: é decisão do DP e não pode parecer aprovado.
_ST_BATIDA = {
    "approved": ("✓ Aprovado", "ok"),
    "rejected": ("Reprovado", "bad"),
    "pendente_de_conferencia": ("Rosto em reconferência", "info"),
    "rejeitado": ("Reprovado", "bad"),
}
_FALTA_LBL = {
    "entrada": "Entrada",
    "saida": "Saída",
    "saida_almoco": "Saída para o intervalo",
    "retorno_almoco": "Retorno do intervalo",
}


def _hm(min_: int | float | None) -> str:
    if min_ is None:
        return "—"
    v = int(round(min_))
    s = "-" if v < 0 else ""
    v = abs(v)
    return f"{s}{v // 60:02d}:{v % 60:02d}"


def _dados_das_batidas(s, ids: list[str]) -> dict[str, dict]:
    """`{punch_id: {foto, posto, geo, status, origem, dia_civil}}` para os ids que a grade cita.

    UMA consulta para o período todo, não uma por linha. `string_to_array` porque `punch_id` é
    TEXTO aqui (há ids `tang-4199235-…-entrada` ao lado de UUIDs) e a lista viaja como um
    parâmetro só — nenhum id desta casa tem vírgula.
    """
    if not ids:
        return {}
    rows = s.execute(
        text(
            "SELECT punch_id, coalesce(foto_capturada_url,'') <> '' AS tem_foto, "
            "       coalesce(posto_nome,''), dentro_geofence, coalesce(status::text,''), "
            "       coalesce(device_type,''), to_char(punch_timestamp,'YYYY-MM-DD') "
            "  FROM gp_clock_punches "
            " WHERE punch_id = ANY(string_to_array(CAST(:ids AS text), ','))"
        ),
        {"ids": ",".join(ids)},
    ).all()
    return {
        r[0]: {"foto": bool(r[1]), "posto": r[2], "geo": r[3], "status": r[4], "origem": r[5], "dia_civil": r[6]}
        for r in rows
    }


def _celula_hora(hora: str | None, pid: str | None, info: dict, nome: str, dia: str, lado: str) -> list[dict]:
    """[célula da hora, célula da foto] — a câmera COLADA na hora, como no Sólides.

    A foto só é endereçável por `punch_id` (`/ponto/batida/{punch_id}/foto`), e o segmento não
    devolvia id nenhum: por isso `espelho_service._segmentos` passou a acrescentar
    `entrada_punch_id`/`saida_punch_id`. Casar por HORA seria errado — NAILSON tem 3 batidas
    «entrada» no mesmo segundo (08:01:36,6/,75/,80 em 08/09/2026).

    Sem foto guardada a célula é «—» e NÃO um chip quebrado: a selfie só passou a ser guardada
    em 14/09/2026, então a maior parte do histórico não tem — e um ícone que nunca carrega
    ensina a ignorar o ícone.
    """
    if not hora:
        return [t("—", 400, "#94A3B8"), t("", 400)]
    manual = (info or {}).get("origem") in ("ajuste_dp", "manual", "contingencia")
    cel = t(hora, 600 if not manual else 500, "#0F1B3A" if not manual else "#B45309")
    if not (pid and (info or {}).get("foto")):
        return [cel, t("—", 400, "#CBD5E1")]
    return [
        cel,
        {
            "isFoto": True,
            "v": f"/api/v1/people-management/ponto/batida/{pid}/foto",
            "alt": f"{nome} — {dia} {hora} ({lado})",
        },
    ]


def _local(info: dict | None) -> dict:
    """Local da ponta: o posto que a batida gravou, e se ela caiu FORA do geofence."""
    if not info:
        return t("—", 400, "#94A3B8")
    posto = info.get("posto") or "(sem posto)"
    if info.get("geo") is False:
        return b(f"{posto} · fora do local", "warn")
    return t(posto, 500)


def _status_do_conjunto(infos: list[dict], tem_id: bool = True) -> dict:
    """Badge do trecho/dia a partir do status das batidas que o compõem.

    Verde SÓ quando TODAS estão `approved` — «2 de 4 aprovadas» é meio caminho e tem de aparecer
    como meio caminho. É aqui que mora o turno noturno: o plantão fecha em DOIS dias civis, e
    aprovar só o primeiro deixava o dia metade aprovado com cara de aprovado.

    `tem_id=False` = o segmento gravado não diz de qual batida ele veio (safra de espelho
    anterior ao acréscimo de `entrada_punch_id`). Aí o status é DESCONHECIDO, e dizer «sem
    batida» numa linha que mostra 19:00→02:00 seria afirmar o contrário do que a própria linha
    mostra — converter «não me informa» em «não existe». Declara a ignorância.
    """
    if not tem_id:
        return b("recalcule o espelho", "info")
    if not infos:
        return b("sem batida", "mut")
    st = [(i.get("status") or "").lower() for i in infos]
    if all(x == "approved" for x in st):
        return b("✓ Aprovado", "ok")
    if any(x in ("rejected", "rejeitado") for x in st):
        return b("Reprovado", "bad")
    n_ok = sum(1 for x in st if x == "approved")
    if n_ok:
        return b(f"{n_ok} de {len(st)} aprovadas", "warn")
    if all(x == "pendente_de_conferencia" for x in st):
        return b("Rosto em reconferência", "info")
    return b("Aguardando conferência", "warn")


def _acoes_do_dia(eid: str, nome: str, dia_iso: str, dia_br: str, dias_civis: list[str], pend: int) -> list[dict]:
    """Aprovar/Reprovar o PLANTÃO (todos os dias civis que ele toca) + Registrar batida.

    ⚠️ Aqui está a diferença que justifica a aba: as telas antigas decidem UM dia civil por
    clique (`POST .../time-records/dia/decidir?dia=`). Num 12x36 noturno o plantão de 27/07
    começa 19:00 de 27/07 e termina 07:17 de 28/07 — dois dias civis. Clicar «Aprovar dia 27/07»
    deixava metade das batidas do MESMO plantão pendentes, com a tela dizendo «aprovado».
    `dias_civis` sai dos `punch_timestamp` das batidas DESTE plantão (derivado da fonte, nunca
    do calendário), e a ação percorre os dois chamando a MESMA rota de sempre.
    """
    dias = ",".join(dias_civis)
    quais = " e ".join(f"{d[8:10]}/{d[5:7]}" for d in dias_civis) or dia_br

    def _dec(dec: str, lbl: str, estilo: str, pergunta: str) -> dict:
        return {
            "title": f"{lbl} o plantão de {dia_br} — {nome}",
            "sub": (
                f"{pend} batida(s) aguardando neste plantão. O plantão toca o(s) dia(s) civil(is) "
                f"{quais} e a decisão vale para TODAS as batidas dele — é isto que as telas antigas "
                "não faziam: elas decidiam um dia civil por clique e o turno noturno ficava metade "
                "aprovado. O horário não muda e a folha não muda: aprovação é trilha e estado."
            ),
            "endpoint": (
                f"/api/v1/redesign/action/ponto-plantao-decidir"
                f"?employee_id={eid}&dias={dias}&decisao={dec}"
            ),
            "method": "POST",
            "btnLabel": lbl,
            "submitLabel": f"{lbl} o plantão de {dia_br}",
            "btnStyle": estilo,
            "okMsg": f"Plantão {lbl.lower()}. Clique em Consultar para ver o novo status.",
            "fields": [
                {
                    "key": "observacao",
                    "label": pergunta,
                    "type": "textarea",
                    "span": "span 2",
                    "max": 200,
                    "ph": "Fica no histórico de cada batida, com seu nome e a data.",
                },
            ],
        }

    acoes = []
    if pend:
        acoes.append(_dec("approved", "Aprovar plantão", "primary", "Observação (opcional, máx. 200)"))
    acoes.append(_dec("rejected", "Reprovar plantão", "danger", "Por que está reprovando?* (vai para o histórico)"))
    return acoes


def _acao_registrar(eid: str, nome: str, dia_iso: str, dia_br: str, falta: str | None) -> dict:
    """«Registrar ponto em atraso»: INSERE a batida que não aconteceu, com motivo auditado.

    Reusa `POST /people-management/ponto/ajuste` (a aba «Ajustar batida»), que INSERE uma batida
    `device_type='ajuste_dp'` — não edita a hora de uma batida existente, e é assim de propósito:
    hora é registro de fato da Portaria 671. Por isso o botão aqui diz REGISTRAR, e não «editar».

    A hora vem VAZIA com exemplo no placeholder. É a única coisa que o sistema não sabe: quando
    o segmento está incompleto, o que falta é justamente a marcação — preencher com um palpite
    («00:00»? «a hora do par»?) seria inventar registro de ponto.
    """
    tipos = [
        {"value": v, "label": l}
        for v, l in (
            ("entrada", "Entrada"),
            ("saida_almoco", "Saída para o intervalo"),
            ("retorno_almoco", "Retorno do intervalo"),
            ("saida", "Saída"),
        )
    ]
    if falta in _FALTA_LBL:
        tipos = [o for o in tipos if o["value"] == falta] + [o for o in tipos if o["value"] != falta]
    return {
        "title": f"Registrar batida de {nome} — {dia_br}",
        "sub": (
            (f"O motor diz que falta a marcação «{_FALTA_LBL.get(falta, falta)}» neste plantão. " if falta else "")
            + "Isto INSERE uma batida marcada como ajuste do DP (origem `ajuste_dp`), com o motivo "
            "na auditoria. Não apaga nem reescreve batida nenhuma, e competência FECHADA recusa. "
            "Depois de registrar, recalcule o espelho na aba «Espelho: calcular/fechar» para a "
            "hora entrar na conta."
        ),
        "endpoint": "/api/v1/people-management/ponto/ajuste",
        "method": "POST",
        "btnLabel": "Registrar batida",
        "submitLabel": "Registrar a batida",
        "btnStyle": "outline",
        "okMsg": "Batida registrada. Recalcule o espelho para a hora entrar na conta.",
        # `fixed` e NÃO campo `type:"hidden"`: medido no renderizador em 28/09/2026 — o modal de
        # ação por linha (`ModuleView.tsx`, bloco `editRow`) NÃO filtra `hidden` como o FormScreen
        # filtra. Um campo hidden ali viraria uma caixa de texto SEM rótulo com um UUID dentro,
        # editável — quem fosse registrar a batida veria uma caixa estranha e poderia trocar a
        # pessoa. `editRow.fixed` já é mesclado no corpo do POST e não desenha nada.
        "fixed": {"employee_id": eid, "ajustado_por": "DP"},
        "fields": [
            {"key": "data", "label": "Dia do plantão*", "type": "date", "span": "span 1", "value": dia_iso},
            {"key": "punch_type", "label": "Qual marcação*", "type": "select", "span": "span 1", "options": tipos},
            {
                "key": "timestamp",
                "label": "Hora REAL da batida* (AAAA-MM-DDTHH:MM)",
                "type": "text",
                "span": "span 2",
                "ph": f"{dia_iso}T03:00 — digite a hora real; o sistema não a adivinha",
            },
            {
                "key": "motivo",
                "label": "Por que está registrando?* (mín. 5 caracteres, vai para a auditoria)",
                "type": "textarea",
                "span": "span 2",
            },
        ],
    }


_PC_COLS = [
    "Dia",
    "Trecho",
    "Entrada",
    "📷",
    "Saída",
    "📷",
    "Horas",
    "Local da entrada",
    "Local da saída",
    "Status",
    "Observação",
]
_PC_GRID = "0.8fr 0.85fr 0.55fr 0.35fr 0.55fr 0.35fr 0.55fr 1.2fr 1.2fr 1fr 1.6fr"


def _grade_ponto_colaborador(eid: str, ini: date, fim: date) -> tuple[dict, dict]:
    """(espelho do período, tela `table` da grade). SÍNCRONA: o motor legal é sync.

    Uma linha por TRECHO do dia, o rodapé do dia como linha própria e o total do período no fim.
    Não há agrupamento de linha no renderizador desta casa (medido: `ModuleView.tsx` desenha
    `rows` numa grade CSS chapada, sem subtotal de grupo) — então o «grupo» é a coluna Dia
    repetida e o rodapé é uma linha. Zero tipo de tela novo por causa disto.
    """
    from core.database.session import SyncSessionLocal
    from modules.people_management.ponto.controllers.punch_controller import get_espelho_mensal

    with SyncSessionLocal() as s:
        esp = get_espelho_mensal(eid, de=ini.isoformat(), ate=fim.isoformat(), db=s)
        dias = esp.get("dias") or []
        ids = [
            pid
            for d in dias
            for seg in (d.get("segmentos") or [])
            for pid in (seg.get("entrada_punch_id"), seg.get("saida_punch_id"))
            if pid
        ]
        info = _dados_das_batidas(s, ids)

    nome = esp.get("employee_name") or "colaborador"
    rows: list[dict] = []
    pend_total = sem_foto = com_foto = 0
    for d in dias:
        dia_iso, dia_br = str(d.get("data") or ""), f"{d.get('dia') or '—'} · {d.get('dia_semana') or ''}".strip(" ·")
        segs = [x for x in (d.get("segmentos") or []) if isinstance(x, dict)]
        infos_dia: list[dict] = []
        civis: list[str] = []
        for n, seg in enumerate(segs, 1):
            pe, ps = seg.get("entrada_punch_id"), seg.get("saida_punch_id")
            ie, is_ = info.get(pe or ""), info.get(ps or "")
            for i in (ie, is_):
                if i:
                    infos_dia.append(i)
                    if i.get("dia_civil") and i["dia_civil"] not in civis:
                        civis.append(i["dia_civil"])
                    com_foto += 1 if i.get("foto") else 0
                    sem_foto += 0 if i.get("foto") else 1
            obs = []
            if seg.get("incompleto"):
                falta = seg.get("falta")
                obs.append(
                    f"falta marcar: {_FALTA_LBL.get(falta, falta or 'a outra ponta')}"
                    + (" (turno em andamento)" if seg.get("em_curso") else "")
                )
            if seg.get("entrada_manual") or seg.get("saida_manual"):
                obs.append("hora lançada pelo DP")
            # Sem id de batida não há como buscar a foto, o local nem o status: o espelho gravado
            # é de uma safra anterior ao acréscimo. A linha diz isso em vez de mostrar «—» em três
            # colunas e deixar parecer que a informação não existe no sistema.
            tem_id = bool(pe or ps)
            if not tem_id and not seg.get("incompleto"):
                obs.append("espelho sem id de batida — recalcule para ver foto, local e status")
            rows.append(
                {
                    "cells": [
                        t(dia_br, 600, "#0F1B3A"),
                        t(f"{n}º trecho" if len(segs) > 1 else "Jornada", 500),
                        *_celula_hora(seg.get("entrada"), pe, ie or {}, nome, dia_br, "entrada"),
                        *_celula_hora(seg.get("saida"), ps, is_ or {}, nome, dia_br, "saída"),
                        t(_hm(seg.get("minutos")) if not seg.get("incompleto") else "—", 600),
                        _local(ie),
                        _local(is_),
                        _status_do_conjunto([x for x in (ie, is_) if x], tem_id),
                        t(" · ".join(obs) or "", 400, "#B45309" if obs else "#334155"),
                    ],
                    # Ação na linha do TRECHO: só o que é do trecho — registrar a marca que falta.
                    "actions": (
                        [_acao_registrar(esp["employee_id"], nome, dia_iso, dia_br, seg.get("falta"))]
                        if seg.get("incompleto")
                        else []
                    ),
                }
            )
        if not segs:
            rows.append(
                {
                    "cells": [
                        t(dia_br, 600, "#0F1B3A"),
                        t("Sem batida", 500, "#B45309"),
                        *([t("—", 400, "#94A3B8"), t("", 400)] * 2),
                        t("—"),
                        t("—", 400, "#94A3B8"),
                        t("—", 400, "#94A3B8"),
                        b("sem batida", "mut"),
                        t(d.get("obs") or "nenhuma marcação neste dia", 400, "#B45309"),
                    ],
                    "actions": [_acao_registrar(esp["employee_id"], nome, dia_iso, dia_br, None)],
                }
            )
        pend = sum(1 for i in infos_dia if (i.get("status") or "").lower() not in ("approved", "rejected", "rejeitado"))
        pend_total += pend
        saldo = d.get("saldo_min")
        rows.append(
            {
                "cells": [
                    t(dia_br, 600, "#0F1B3A"),
                    t("Total do dia", 700, "#0F1B3A"),
                    t("", 400),
                    t("", 400),
                    t("", 400),
                    t("", 400),
                    t(d.get("total") or "—", 700, "#0F1B3A"),
                    # Rodapé do dia nas colunas de local, ROTULADO dentro da célula: as quatro
                    # somas do Sólides (trabalhadas · intervalos · previsto · saldo) sem inventar
                    # quatro colunas que ficariam vazias em toda linha de trecho.
                    t(f"Intervalos {d.get('intervalo') or '00:00'}", 600),
                    t(f"Previsto {d.get('previsto') or '—'}", 600),
                    b(
                        f"Saldo {d.get('saldo_dia') or '—'}",
                        "mut" if saldo in (0, None) else ("ok" if saldo > 0 else "bad"),
                    ),
                    t(d.get("obs") or "", 400, "#B45309" if d.get("obs") else "#334155"),
                ],
                "actions": _acoes_do_dia(esp["employee_id"], nome, dia_iso, dia_br, civis or [dia_iso], pend),
            }
        )

    # Total do PERÍODO + o «Imprimir» do Sólides. O PDF é o espelho padrão-ouro com `de`/`ate`
    # (Portaria 671) — a competência da URL é o mês do FIM, a convenção de `janela_26a25`.
    rows.append(
        {
            "cells": [
                t(f"{ini:%d/%m} a {fim:%d/%m}", 700, "#0F1B3A"),
                t("TOTAL DO PERÍODO", 700, "#0F1B3A"),
                t("", 400),
                t("", 400),
                t("", 400),
                t("", 400),
                t(esp.get("total_trabalhado") or "—", 700, "#0F1B3A"),
                t(f"{len(dias)} dia(s) apurado(s)", 600),
                t(f"Previsto {esp.get('horas_esperadas') or '—'}", 600),
                b(
                    f"Saldo {esp.get('saldo') or '—'}",
                    "mut" if not esp.get("saldo_min") else ("ok" if esp["saldo_min"] > 0 else "bad"),
                ),
                t(f"{pend_total} batida(s) aguardando conferência no período", 500),
            ],
            "docs": [
                {
                    "label": f"Folha de ponto {ini:%d/%m/%Y} a {fim:%d/%m/%Y} (PDF)",
                    "url": (
                        f"/api/v1/people-management/hr/ponto/espelho/{esp['employee_id']}"
                        f"/{fim.month}/{fim.year}/pdf?de={ini:%Y-%m-%d}&ate={fim:%Y-%m-%d}"
                    ),
                    "fmt": "pdf",
                    "mode": "blob",
                    "filename": f"folha_ponto_{ini:%Y%m%d}_{fim:%Y%m%d}.pdf",
                    "gate": "dp",
                }
            ],
        }
    )

    sem_esp = esp.get("sem_espelho") or []
    tabela = {
        "title": f"{nome} — {ini:%d/%m/%Y} a {fim:%d/%m/%Y}",
        "sub": (
            f"{len(dias)} dia(s) apurado(s) pelo motor · {esp.get('total_trabalhado')} trabalhadas de "
            f"{esp.get('horas_esperadas')} previstas · saldo {esp.get('saldo')} · "
            f"{pend_total} batida(s) aguardando conferência. "
            f"Selfie: {com_foto} batida(s) com foto guardada, {sem_foto} sem — a selfie só passou a "
            "ser guardada em 14/09/2026, então período anterior mostra «—», não um ícone quebrado. "
            "Posto/escala do operacional são curados à mão e entram aqui só como leitura. "
            + (
                f"⚠️ SEM espelho calculado em {', '.join(sem_esp)}: esses dias NÃO aparecem (nada é "
                "estimado) — calcule na aba «Espelho: calcular/fechar». "
                if sem_esp
                else ""
            )
            + "«Solicitar assinatura» continua na aba própria: a homologação é do MÊS inteiro e de "
            "todos os espelhos fechados, não deste período nem desta pessoa."
        ),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar no período…",
        "grid": _PC_GRID,
        "cols": _PC_COLS,
        "rows": rows,
    }
    return esp, tabela


@router.post("/action/ponto-do-colaborador", dependencies=[Depends(_require_dp)])
async def rd_ponto_do_colaborador(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """A consulta da aba «Ponto do colaborador» — devolve a GRADE em `tabela`. READ-ONLY."""
    from starlette.concurrency import run_in_threadpool

    eid = str(payload.get("employee_id") or "").strip()
    if not eid:
        raise HTTPException(status_code=400, detail="Escolha o colaborador.")
    # As duas datas são OBRIGATÓRIAS aqui (o lote aceita vazio = mês civil; esta tela não tem
    # mês civil nenhum). A checagem de presença vem ANTES de `_periodo_lote` porque a mensagem
    # dele oferece «deixe as duas vazias para o mês civil», que nesta tela não é uma opção — dar
    # instrução que a própria rota recusa manda a pessoa tentar duas vezes.
    if not (str(payload.get("de") or "").strip() and str(payload.get("ate") or "").strip()):
        raise HTTPException(
            status_code=400,
            detail="Informe as DUAS datas do período (início e fim) — a janela do DP é 26→25, não o mês civil.",
        )
    per = _periodo_lote(payload.get("de"), payload.get("ate"))
    assert per is not None  # noqa: S101 — garantido pela guarda acima; só para o type-checker
    esp, tabela = await run_in_threadpool(_grade_ponto_colaborador, eid, per[0], per[1])
    return {
        "ok": True,
        "message": (
            f"{esp.get('employee_name')}: {len(esp.get('dias') or [])} dia(s) apurado(s) de "
            f"{per[0]:%d/%m/%Y} a {per[1]:%d/%m/%Y} — {esp.get('total_trabalhado')} trabalhadas, "
            f"saldo {esp.get('saldo')}."
        ),
        "tabela": tabela,
    }


@router.post("/action/ponto-plantao-decidir", dependencies=[Depends(_require_dp)])
async def rd_ponto_plantao_decidir(
    current_user: CurrentActiveUser,
    employee_id: str,
    dias: str,
    decisao: str,
    payload: dict = Body(default={}),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Aprova/reprova TODOS os dias civis de um plantão, chamando a rota de sempre em cada um.

    POR QUE existe em vez de a tela mandar N POSTs: o modal do ModuleView faz UMA chamada por
    clique. E por que não uma regra nova de aprovação: não há — o corpo abaixo chama
    `decidir_dia_time_records`, a MESMA função que as duas telas antigas usam, uma vez por dia
    civil. Toda validação (observação ≤ 200, reprovação exige motivo, autor real, trilha em
    `gp_audit_logs`) mora lá e continua sendo a única.

    Um plantão noturno toca DOIS dias civis (19:00 de 27/07 → 07:17 de 28/07). A lista vem dos
    `punch_timestamp` das batidas daquele plantão, derivada pelo builder — não do calendário.
    """
    from modules.people_management.hr.controllers.time_record_controller import (
        decidir_dia_time_records,
    )

    alvos = [x for x in (str(dias or "").split(",")) if x.strip()]
    if not alvos:
        raise HTTPException(status_code=400, detail="Nenhum dia civil informado para este plantão.")
    feito = 0
    relato: list[str] = []
    for d in alvos:
        try:
            dia = date.fromisoformat(d.strip()[:10])
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Dia inválido «{d}» — use AAAA-MM-DD.") from None
        r = await decidir_dia_time_records(
            current_user=current_user,
            employee_id=employee_id,
            dia=dia,
            decisao=decisao,
            payload=payload,
            db=db,
        )
        n = int(r.get("batidas") or 0)
        feito += n
        relato.append(f"{dia:%d/%m}: {n} batida(s)")
    return {
        "ok": True,
        "message": (
            f"{feito} batida(s) do plantão — {decisao}. " + " · ".join(relato)
            + ". Clique em Consultar para ver o novo status."
        ),
    }
