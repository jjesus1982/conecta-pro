"""Frente 10 (12/09/2026) — uniforme/EPI com grade de tamanho e mínimo/máximo, frota com `Restam` e
vistoria chegada×saída, avaliação por ambiente (link público por token).

Telas entram nos builders `gestao_de_pessoas` (uniforme) e `equipamentos` (frota + avaliação) por
`telas(db, slug)`; ações em `router` (incluído por `equipamentos.py`, uma vez só). Decisões do
pré-mortem, em código:
  · SKU normalizado NA ESCRITA (`sku_norm`, régua do `_normalize` do Hermes) e UNIQUE no banco;
  · `Restam` só com KM lido dentro de `PERIODO_KM_DIAS`; fora disso "sem dado", nunca vencido;
  · saída só compara com a chegada do MESMO veículo/OS/condutor dentro de `JANELA_VISTORIA_HORAS`;
    sem par → "aguardando checklist";
  · avaliação sempre com contrato + ambiente + turno; anônima quanto à pessoa (nada de IP/usuário);
  · multa: sem tabela de posse datada não se aponta condutor — gestão de multas fora do escopo.

DDL (staging aplicado com IF NOT EXISTS; produção pelo integrador): ver `DDL` no fim do arquivo.
"""

from __future__ import annotations

import html
import json
import logging
import re
import secrets
import unicodedata
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from sqlalchemy import text

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter()

PERIODO_KM_DIAS = 30  # leitura de KM mais velha que isso → `Restam` vira "sem dado"
JANELA_VISTORIA_HORAS = 24 * 7  # chegada mais velha que isso não é par da saída
_TZ = ZoneInfo("America/Manaus")
_ND = "#0F1B3A"
_TAM_RE = re.compile(r"^(PP|P|M|G|GG|XG|EXG|XGG|\d{2})$")
_STATUS_ENTREGA = ["solicitado", "separado", "entregue", "devolvido"]
_MOTIVOS = [("admissao", "Admissão"), ("troca", "Troca"), ("reposicao", "Reposição"), ("perda", "Perda/extravio")]
_AREAS = [
    ("dianteira", "Dianteira"),
    ("traseira", "Traseira"),
    ("lateral_direita", "Lateral direita"),
    ("lateral_esquerda", "Lateral esquerda"),
    ("interior", "Interior"),
]
_NOTAS = [
    ("na", "N/A", "➖"),
    ("otimo", "Ótimo", "😄"),
    ("bom", "Bom", "🙂"),
    ("regular", "Regular", "😐"),
    ("ruim", "Ruim", "🙁"),
]
_TURNOS = [("manha", "Manhã"), ("tarde", "Tarde"), ("noite", "Noite")]
# mesmo destino das fotos de ronda (inspection_round_controller.FOTOS_DIR é /app/uploads/rondas)
_FOTOS_DIR = Path("/app/uploads/frota")
_MIME_EXT = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_MAX_FOTO = 10 * 1024 * 1024

MENU_GESTAO = [
    {"id": "uniforme-grade", "label": "Uniforme/EPI · Grade", "icon": "M21 8 12 3 3 8v8l9 5 9-5zM3 8l9 5 9-5M12 13v8"},
    {"id": "uniforme-grade-novo", "label": "Uniforme/EPI · Novo SKU", "icon": "M12 5v14M5 12h14"},
    {"id": "uniforme-entregas", "label": "Uniforme/EPI · Entregas", "icon": "M22 2 11 13M22 2l-7 20-4-9-9-4z"},
    {
        "id": "uniforme-entrega-lote",
        "label": "Uniforme/EPI · Entrega em lote",
        "icon": "M22 2 11 13M22 2l-7 20-4-9-9-4z",
    },
]
MENU_EQUIPAMENTOS = [
    {"id": "frota-painel", "label": "Frota · Painel", "icon": "M3 3v18h18"},
    {"id": "frota-veiculo-novo", "label": "Frota · Novo veículo", "icon": "M12 5v14M5 12h14"},
    {"id": "frota-leitura", "label": "Frota · KM / Abastecimento", "icon": "M12 5v14M5 12h14"},
    {"id": "frota-abastecimentos", "label": "Frota · Abastecimentos", "icon": "M3 3v18h18"},
    {
        "id": "frota-vistorias",
        "label": "Frota · Vistorias",
        "icon": "M9 11l3 3L22 4M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11",
    },
    {"id": "frota-vistoria-nova", "label": "Frota · Nova vistoria", "icon": "M12 5v14M5 12h14"},
    {"id": "avaliacao-dashboard", "label": "Avaliação · Painel", "icon": "M3 3v18h18"},
    {
        "id": "avaliacao-ambientes",
        "label": "Avaliação · Ambientes",
        "icon": "M3 3h7v7H3zM14 3h7v5h-7zM14 12h7v9h-7zM3 16h7v5H3z",
    },
    {"id": "avaliacao-ambiente-novo", "label": "Avaliação · Novo ambiente", "icon": "M12 5v14M5 12h14"},
    {"id": "avaliacao-links", "label": "Avaliação · Links", "icon": "M22 2 11 13M22 2l-7 20-4-9-9-4z"},
    {"id": "avaliacao-link-novo", "label": "Avaliação · Novo link", "icon": "M12 5v14M5 12h14"},
]


# ----------------------------------------------------------------------------- régua
def _normalize(s: str) -> str:
    """Réplica de `HermesAgent._normalize` (modules/gedeon/agents/hermes.py:408) — é método de
    instância num módulo pesado; a régua é esta: NFKD, maiúsculas, sem marca de acento."""
    nfkd = unicodedata.normalize("NFKD", (s or "").upper())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def sku_norm(item: str, tamanho: str = "") -> str:
    """'Blazer Feminino M' e 'BLAZER FEMININO - M' → 'BLAZER FEMININO M'. Separadores colapsam."""
    return " ".join(re.sub(r"[^A-Z0-9]+", " ", _normalize(f"{item} {tamanho}")).split())


# Importado DEPOIS das constantes e do `sku_norm`: os oráculos importam este módulo primeiro, e o
# redesign_data_controller, ao carregar, importa os builders — que leem MENU_*/router daqui.
from modules.operacional.controllers.redesign_data_controller import S, _helpers, b, brl, doc, t  # noqa: E402


def _int(v, campo: str, minimo: int = 0):
    if v is None or str(v).strip() == "":
        return None
    try:
        n = int(str(v).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{campo}: informe um número inteiro.") from None
    if n < minimo:
        raise HTTPException(status_code=400, detail=f"{campo}: não pode ser menor que {minimo}.")
    return n


def _dec(v, campo: str):
    if v is None or str(v).strip() == "":
        return None
    try:
        n = float(str(v).replace(",", "."))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"{campo}: informe um número.") from None
    if n < 0:
        raise HTTPException(status_code=400, detail=f"{campo}: não pode ser negativo.")
    return n


def _quem(u) -> str:
    return getattr(u, "email", None) or str(getattr(u, "id", "") or "")


def _dt(v, fmt="%d/%m/%Y %H:%M"):
    try:
        return v.astimezone(_TZ).strftime(fmt) if v else "—"
    except Exception:  # noqa: BLE001
        return "—"


async def _opts(db, sql: str) -> list[dict]:
    return [{"value": str(r[0]), "label": str(r[1])} for r in (await db.execute(text(sql))).fetchall()]


async def _form(db, key: str, title: str, sub: str, cta: str, endpoint: str, fields, **submit):
    return {
        "title": title,
        "sub": sub,
        "cta": cta,
        "type": "form",
        "submit": {"endpoint": endpoint, "okMsg": "Registrado.", **submit},
        "fields": fields,
    }


_SQL_EMPREGADOS = "SELECT id, nome FROM employees WHERE data_demissao IS NULL ORDER BY nome"
_SQL_CONTRATOS = (
    "SELECT c.id, coalesce(c.contract_number,'') || ' · ' || coalesce(cl.name, c.name, '—') "
    "FROM contracts c LEFT JOIN clients cl ON cl.id = c.client_id "
    "WHERE lower(c.status::text) IN ('active','ativo','vigente') ORDER BY 2"
)
_SQL_VEICULOS = "SELECT id, placa || ' · ' || coalesce(modelo,'—') FROM frota_veiculos WHERE ativo ORDER BY placa"


# ----------------------------------------------------------------------------- telas
async def telas(db, slug: str | None = None) -> dict:
    out, safe, tbl = _helpers(db)
    if slug in (None, "gestao-de-pessoas"):
        await _telas_uniforme(db, out, safe, tbl)
    if slug in (None, "equipamentos"):
        await _telas_frota(db, out, safe, tbl)
        await _telas_avaliacao(db, out, safe, tbl)
    return out


async def _telas_uniforme(db, out, safe, tbl):
    def _situacao(atual, mi, ma):
        if atual is None:
            return b("sem contagem", "mut")
        if atual < mi:
            return b(f"abaixo do mínimo ({atual}/{mi})", "bad")
        if atual > ma:
            return b(f"acima do máximo ({atual}/{ma})", "warn")
        return b("ok", "ok")

    await safe(
        "uniforme-grade",
        tbl(
            "Uniforme/EPI — grade de tamanho",
            "Mínimo · Máximo · Pendente · Atual por SKU (SKU normalizado na escrita)",
            "—",
            ["SKU", "Tamanho", "Mínimo", "Máximo", "Pendente", "Atual", "Valor", "Situação"],
            "1.8fr 0.7fr 0.7fr 0.7fr 0.8fr 0.7fr 0.8fr 1.3fr",
            "SELECT g.id, g.item, g.tamanho, g.minimo, g.maximo, g.atual, g.valor_unitario, "
            "(SELECT coalesce(sum(e.quantidade),0) FROM sst_uniforme_entregas e WHERE e.grade_id = g.id "
            " AND e.status IN ('solicitado','separado')) "
            "FROM sst_uniforme_grade g WHERE g.ativo ORDER BY g.item, g.tamanho",
            lambda r: [
                t(r[1], 600, _ND),
                t(r[2]),
                t(str(r[3])),
                t(str(r[4])),
                b(str(r[7]), "warn" if r[7] else "mut"),
                t(str(r[5]) if r[5] is not None else "sem dado"),
                t(brl(float(r[6])) if r[6] is not None else "—"),
                _situacao(r[5], r[3], r[4]),
            ],
            actionsfn=lambda r: [
                {
                    "title": f"Contagem de estoque — {r[1]} {r[2]}",
                    "sub": "Quantidade física contada agora.",
                    "endpoint": "/api/v1/redesign/action/uniforme-estoque",
                    "method": "POST",
                    "btnLabel": "Contar",
                    "submitLabel": "Registrar contagem",
                    "okMsg": "Contagem registrada. Recarregue a tela.",
                    "fixed": {"id": r[0]},
                    "fields": [
                        {
                            "key": "atual",
                            "label": "Quantidade atual",
                            "type": "text",
                            "value": "" if r[5] is None else str(r[5]),
                        }
                    ],
                }
            ],
        ),
    )

    async def _f_grade():
        return await _form(
            db,
            "uniforme-grade-novo",
            "Novo SKU de uniforme/EPI",
            "Um item por tamanho. 'Blazer Feminino M' e 'BLAZER FEMININO - M' são o MESMO SKU — o segundo é recusado.",
            "Cadastrar",
            "/api/v1/redesign/action/uniforme-grade",
            [
                {"key": "item", "label": "Item*", "type": "text", "span": "span 2", "ph": "Ex.: Blazer Feminino"},
                {
                    "key": "tamanho",
                    "label": "Tamanho*",
                    "type": "text",
                    "ph": "PP, P, M, G, GG, EXG ou número (38, 40…)",
                },
                {"key": "minimo", "label": "Mínimo*", "type": "text"},
                {"key": "maximo", "label": "Máximo*", "type": "text"},
                {"key": "atual", "label": "Atual (contagem; vazio = sem contagem)", "type": "text"},
                {"key": "valor_unitario", "label": "Valor unitário (R$)", "type": "text"},
                {
                    "key": "catalog_id",
                    "label": "Item do catálogo de EPI (em branco = casa pelo nome)",
                    "type": "select",
                    "span": "span 2",
                    "options": await _opts(
                        db, "SELECT id, nome FROM health_epi_catalog WHERE coalesce(ativo,true) ORDER BY nome"
                    ),
                },
            ],
            okMsg="SKU cadastrado.",
        )

    await safe("uniforme-grade-novo", _f_grade())

    def _acoes_entrega(r):
        st = r[7]
        prox = {
            "solicitado": ("separado", "Separar"),
            "separado": ("entregue", "Entregar"),
            "entregue": ("devolvido", "Devolver"),
        }.get(st)
        if not prox:
            return []
        return [
            {
                "title": f"{prox[1]} — {r[2]} · {r[3]} {r[4]}",
                "sub": f"Lote {r[1]}. Estado atual: {st}.",
                "endpoint": "/api/v1/redesign/action/uniforme-entrega-status",
                "method": "POST",
                "btnLabel": prox[1],
                "submitLabel": prox[1],
                "btnStyle": "primary" if st == "separado" else "outline",
                "okMsg": "Estado atualizado. Recarregue a tela.",
                "fixed": {"id": r[0], "status": prox[0]},
                "fields": [],
            }
        ]

    await safe(
        "uniforme-entregas",
        tbl(
            "Uniforme/EPI — entregas",
            "Solicitação → separação → entrega → devolução",
            "—",
            ["Lote", "Colaborador", "Item", "Tam.", "Qtd", "Motivo", "Prazo", "Status", "Última etapa"],
            "1fr 1.8fr 1.4fr 0.5fr 0.5fr 0.9fr 0.9fr 1fr 1.1fr",
            "SELECT e.id, e.lote, coalesce(emp.nome,'—'), g.item, g.tamanho, e.quantidade, e.motivo, e.prazo, e.status, "
            "coalesce(e.devolvido_em, e.entregue_em, e.separado_em, e.solicitado_em) "
            "FROM sst_uniforme_entregas e JOIN sst_uniforme_grade g ON g.id = e.grade_id "
            "LEFT JOIN employees emp ON emp.id = e.employee_id ORDER BY e.solicitado_em DESC LIMIT 300",
            lambda r: [
                t(r[1], 600, _ND),
                t(r[2]),
                t(r[3]),
                t(r[4]),
                t(str(r[5])),
                t(dict(_MOTIVOS).get(r[6], r[6])),
                t(r[7].strftime("%d/%m/%Y") if r[7] else "—"),
                b(
                    r[8],
                    {"solicitado": "warn", "separado": "info", "entregue": "ok", "devolvido": "mut"}.get(r[8], "mut"),
                ),
                t(_dt(r[9])),
            ],
            actionsfn=lambda r: _acoes_entrega((r[0], r[1], r[2], r[3], r[4], r[5], r[6], r[8])),
        ),
    )

    async def _f_lote():
        return await _form(
            db,
            "uniforme-entrega-lote",
            "Entrega em lote (ou individual)",
            "Escolha um posto (todos os alocados) e/ou liste CPFs, um por linha. Nasce como 'solicitado'.",
            "Solicitar",
            "/api/v1/redesign/action/uniforme-entrega-lote",
            [
                {
                    "key": "grade_id",
                    "label": "SKU*",
                    "type": "select",
                    "span": "span 2",
                    "options": await _opts(
                        db,
                        "SELECT id, item || ' · ' || tamanho FROM sst_uniforme_grade WHERE ativo ORDER BY item, tamanho",
                    ),
                },
                {"key": "quantidade", "label": "Quantidade por pessoa*", "type": "text", "value": "1"},
                {
                    "key": "motivo",
                    "label": "Motivo*",
                    "type": "select",
                    "options": [{"value": k, "label": v} for k, v in _MOTIVOS],
                },
                {"key": "prazo", "label": "Prazo de entrega", "type": "date"},
                {
                    "key": "post_id",
                    "label": "Posto (todos os alocados ativos)",
                    "type": "select",
                    "options": await _opts(
                        db, "SELECT id, coalesce(name, code) FROM posts WHERE coalesce(is_active,true) ORDER BY name"
                    ),
                },
                {"key": "cpfs", "label": "CPFs (um por linha)", "type": "textarea", "span": "span 2"},
            ],
            okMsg="Solicitação criada.",
            showResult=True,
        )

    await safe("uniforme-entrega-lote", _f_lote())


async def _telas_frota(db, out, safe, tbl):
    def _restam(km_atual, troca):
        if km_atual is None:
            return t("sem dado", "#64748B")
        if troca is None:
            return t("—")
        rest = troca - km_atual
        return b(f"{rest:,} km".replace(",", "."), "bad" if rest < 0 else ("warn" if rest < 500 else "ok"))

    await safe(
        "frota-painel",
        tbl(
            "Frota — painel",
            f"KM atual e `Restam` até a próxima troca (só com leitura nos últimos {PERIODO_KM_DIAS} dias)",
            "—",
            ["Placa", "Modelo", "KM atual", "Última leitura", "Óleo · restam", "Pneu · restam", "Correia · restam"],
            "0.9fr 1.3fr 0.9fr 1fr 1fr 1fr 1fr",
            "SELECT v.id, v.placa, coalesce(v.modelo,'—'), "
            f"(SELECT max(km) FROM frota_leituras l WHERE l.veiculo_id = v.id AND l.lida_em > now() - interval '{PERIODO_KM_DIAS} days'), "
            "(SELECT max(lida_em) FROM frota_leituras l WHERE l.veiculo_id = v.id), "
            "v.km_proxima_troca_oleo, v.km_proxima_troca_pneu, v.km_proxima_troca_correia "
            "FROM frota_veiculos v WHERE v.ativo ORDER BY v.placa",
            lambda r: [
                t(r[1], 600, _ND),
                t(r[2]),
                t(f"{r[3]:,}".replace(",", ".") if r[3] is not None else "sem dado"),
                t(_dt(r[4])),
                _restam(r[3], r[5]),
                _restam(r[3], r[6]),
                _restam(r[3], r[7]),
            ],
        ),
    )

    await safe(
        "frota-veiculo-novo",
        _form(
            db,
            "frota-veiculo-novo",
            "Novo veículo",
            "Placa única. Trocas em KM absoluto do hodômetro.",
            "Cadastrar",
            "/api/v1/redesign/action/frota-veiculo",
            [
                {"key": "placa", "label": "Placa*", "type": "text", "ph": "ABC1D23"},
                {"key": "modelo", "label": "Modelo", "type": "text"},
                {"key": "km_proxima_troca_oleo", "label": "Próx. troca de óleo (KM)", "type": "text"},
                {"key": "km_proxima_troca_pneu", "label": "Próx. troca de pneu (KM)", "type": "text"},
                {"key": "km_proxima_troca_correia", "label": "Próx. troca de correia (KM)", "type": "text"},
            ],
            okMsg="Veículo cadastrado.",
        ),
    )

    async def _f_leitura():
        return await _form(
            db,
            "frota-leitura",
            "KM / abastecimento",
            "KM do hodômetro. Abastecimento pede litros e valor.",
            "Registrar",
            "/api/v1/redesign/action/frota-leitura",
            [
                {"key": "veiculo_id", "label": "Veículo*", "type": "select", "options": await _opts(db, _SQL_VEICULOS)},
                {
                    "key": "tipo",
                    "label": "Tipo*",
                    "type": "select",
                    "options": [
                        {"value": "km", "label": "Leitura de KM"},
                        {"value": "abastecimento", "label": "Abastecimento"},
                    ],
                },
                {"key": "km", "label": "KM do hodômetro*", "type": "text"},
                {"key": "litros", "label": "Litros", "type": "text"},
                {"key": "valor", "label": "Valor total (R$)", "type": "text"},
                {
                    "key": "condutor_id",
                    "label": "Condutor",
                    "type": "select",
                    "options": await _opts(db, _SQL_EMPREGADOS),
                },
            ],
        )

    await safe("frota-leitura", _f_leitura())

    await safe(
        "frota-abastecimentos",
        tbl(
            "Frota — abastecimentos",
            "R$/litro e média km/l (KM rodado desde o abastecimento anterior ÷ litros)",
            "—",
            ["Placa", "Data", "KM", "Litros", "Valor", "R$/L", "Média km/l", "Condutor"],
            "0.9fr 1.1fr 0.8fr 0.7fr 0.9fr 0.7fr 0.9fr 1.5fr",
            "SELECT v.placa, l.lida_em, l.km, l.litros, l.valor, "
            "l.km - lag(l.km) OVER (PARTITION BY l.veiculo_id ORDER BY l.lida_em), coalesce(e.nome,'—') "
            "FROM frota_leituras l JOIN frota_veiculos v ON v.id = l.veiculo_id LEFT JOIN employees e ON e.id = l.condutor_id "
            "WHERE l.tipo = 'abastecimento' ORDER BY l.lida_em DESC LIMIT 300",
            lambda r: [
                t(r[0], 600, _ND),
                t(_dt(r[1])),
                t(f"{r[2]:,}".replace(",", ".")),
                t(f"{float(r[3]):.1f}"),
                t(brl(float(r[4]))),
                t(f"{float(r[4]) / float(r[3]):.2f}" if r[3] else "—"),
                t(f"{float(r[5]) / float(r[3]):.1f}" if r[5] is not None and r[3] else "sem dado"),
                t(r[6]),
            ],
        ),
    )

    def _st_saida(v):
        return {
            "sem_diferencas": b("Sem diferenças", "ok"),
            "houve_diferencas": b("Houve diferenças", "bad"),
            "aguardando_checklist": b("Aguardando checklist", "warn"),
        }.get(v, t("—"))

    def _fotos(r):
        areas = r[9] if isinstance(r[9], dict) else (json.loads(r[9]) if r[9] else {})
        return [
            doc(f"Foto {dict(_AREAS).get(a, a)}", f"/api/v1/redesign/frota/vistorias/{r[0]}/fotos/{a}", fmt="jpg")
            for a, d in areas.items()
            if isinstance(d, dict) and d.get("foto")
        ]

    await safe(
        "frota-vistorias",
        tbl(
            "Frota — vistorias chegada × saída",
            "Saída compara com a chegada do mesmo veículo, OS e condutor; sem par, aguarda checklist",
            "—",
            ["#", "Placa", "Tipo", "OS", "Condutor", "KM", "Quando", "Checklist", "Status de saída", "Par"],
            "0.4fr 0.8fr 0.7fr 0.8fr 1.5fr 0.7fr 1fr 0.8fr 1.2fr 0.5fr",
            "SELECT s.id, v.placa, s.tipo, s.os_ref, coalesce(e.nome,'—'), s.km, s.criado_em, s.checklist, s.status_saida, s.areas, s.par_id "
            "FROM frota_vistorias s JOIN frota_veiculos v ON v.id = s.veiculo_id LEFT JOIN employees e ON e.id = s.condutor_id "
            "ORDER BY s.criado_em DESC LIMIT 300",
            lambda r: [
                t(str(r[0]), 600, _ND),
                t(r[1], 600),
                t(r[2].capitalize()),
                t(r[3]),
                t(r[4]),
                t(f"{r[5]:,}".replace(",", ".") if r[5] is not None else "—"),
                t(_dt(r[6])),
                b("Ok", "ok") if r[7] == "ok" else b("Avariado", "bad"),
                _st_saida(r[8]) if r[2] == "saida" else t("—"),
                t(f"#{r[10]}" if r[10] else "—"),
            ],
            docsfn=_fotos,
        ),
    )

    async def _f_vistoria():
        campos = [
            {"key": "veiculo_id", "label": "Veículo*", "type": "select", "options": await _opts(db, _SQL_VEICULOS)},
            {
                "key": "tipo",
                "label": "Tipo*",
                "type": "select",
                "options": [{"value": "chegada", "label": "Chegada"}, {"value": "saida", "label": "Saída"}],
            },
            {"key": "os_ref", "label": "OS / referência*", "type": "text", "ph": "Ex.: OS-2026-0912"},
            {"key": "condutor_id", "label": "Condutor*", "type": "select", "options": await _opts(db, _SQL_EMPREGADOS)},
            {"key": "km", "label": "KM do hodômetro", "type": "text"},
            {
                "key": "checklist",
                "label": "Checklist*",
                "type": "select",
                "options": [{"value": "ok", "label": "Ok"}, {"value": "avariado", "label": "Avariado"}],
            },
        ]
        for a, lbl in _AREAS:
            campos.append(
                {
                    "key": f"aval_{a}",
                    "label": f"{lbl} — avaliação",
                    "type": "select",
                    "options": [{"value": "bom", "label": "Bom"}, {"value": "ruim", "label": "Ruim"}],
                }
            )
            campos.append({"key": f"foto_{a}", "label": f"{lbl} — foto", "type": "file", "accept": "image/*"})
        return await _form(
            db,
            "frota-vistoria-nova",
            "Nova vistoria",
            "Chegada primeiro; a saída da mesma OS/condutor compara com ela.",
            "Registrar vistoria",
            "/api/v1/redesign/action/frota-vistoria",
            campos,
            multipart=True,
            showResult=True,
        )

    await safe("frota-vistoria-nova", _f_vistoria())


async def _telas_avaliacao(db, out, safe, tbl):
    async def _dash():
        tot = (
            await db.execute(
                text(
                    "SELECT count(*), count(DISTINCT ambiente_id), count(DISTINCT token) FROM aval_respostas WHERE criado_em > now() - interval '30 days'"
                )
            )
        ).first()
        por = (
            await db.execute(
                text(
                    "SELECT coalesce(c.contract_number, '—'), a.nome, r.turno, kv.value, count(*) "
                    "FROM aval_respostas r JOIN aval_ambientes a ON a.id = r.ambiente_id "
                    "LEFT JOIN contracts c ON c.id = a.contract_id, jsonb_each_text(r.notas) kv "
                    "WHERE r.criado_em > now() - interval '30 days' AND kv.value <> 'na' GROUP BY 1,2,3,4 ORDER BY 1,2,3"
                )
            )
        ).fetchall()
        agg: dict[tuple, dict] = {}
        for ctr, amb, turno, nota, n in por:
            agg.setdefault((ctr, amb, turno), {})[nota] = n
        rows = []
        for (ctr, amb, turno), notas in agg.items():
            n = sum(notas.values())
            pos = notas.get("otimo", 0) + notas.get("bom", 0)
            pct = round(100 * pos / n) if n else None
            tone = "ok" if pct is not None and pct >= 80 else ("warn" if pct is not None and pct >= 60 else "bad")
            rows.append(
                {
                    "left": f"{ctr} · {amb} · {dict(_TURNOS).get(turno, turno)}",
                    "right": f"{pct}% ótimo/bom · {n} item(ns) · ruim {notas.get('ruim', 0)}" if n else "sem dado",
                    **S[tone],
                }
            )
        pos_tot = sum(v for (_c, _a, _t), d in agg.items() for k, v in d.items() if k in ("otimo", "bom"))
        all_tot = sum(v for d in agg.values() for v in d.values())
        return {
            "title": "Avaliação por ambiente — 30 dias",
            "sub": "Contrato · ambiente · turno. Anônima quanto à pessoa, nunca quanto ao posto.",
            "type": "dash",
            "panelGrid": "1fr",
            "kpis": [
                {"v": str(tot[0] or 0), "l": "Respostas (30d)", "icon": "M3 3v18h18", "color": _ND},
                {
                    "v": f"{round(100 * pos_tot / all_tot)}%" if all_tot else "sem dado",
                    "l": "Ótimo + bom",
                    "icon": "M3 3v18h18",
                    "color": "#16A34A",
                },
                {"v": str(tot[1] or 0), "l": "Ambientes avaliados", "icon": "M3 3v18h18", "color": _ND},
                {"v": str(tot[2] or 0), "l": "Links usados", "icon": "M3 3v18h18", "color": _ND},
            ],
            "panels": [
                {"title": "Por ambiente e turno", "rows": rows or [{"left": "—", "right": "sem dado", **S["mut"]}]}
            ],
        }

    await safe("avaliacao-dashboard", _dash())

    await safe(
        "avaliacao-ambientes",
        tbl(
            "Avaliação — ambientes por contrato",
            "Itens avaliados com carinha em cada ambiente",
            "—",
            ["Contrato", "Ambiente", "Itens", "Respostas (30d)"],
            "1.6fr 1.2fr 2fr 0.8fr",
            "SELECT a.id, coalesce(c.contract_number,'') || ' · ' || coalesce(cl.name, c.name, '—'), a.nome, a.itens, "
            "(SELECT count(*) FROM aval_respostas r WHERE r.ambiente_id = a.id AND r.criado_em > now() - interval '30 days') "
            "FROM aval_ambientes a LEFT JOIN contracts c ON c.id = a.contract_id LEFT JOIN clients cl ON cl.id = c.client_id "
            "WHERE a.ativo ORDER BY 2, a.nome",
            lambda r: [
                t(r[1], 600, _ND),
                t(r[2]),
                t(", ".join(r[3] if isinstance(r[3], list) else json.loads(r[3] or "[]"))),
                t(str(r[4])),
            ],
        ),
    )

    async def _f_amb():
        return await _form(
            db,
            "avaliacao-ambiente-novo",
            "Novo ambiente",
            "Ex.: Portaria — itens: assento, mesa, piso, portas.",
            "Cadastrar",
            "/api/v1/redesign/action/avaliacao-ambiente",
            [
                {
                    "key": "contract_id",
                    "label": "Contrato*",
                    "type": "select",
                    "span": "span 2",
                    "options": await _opts(db, _SQL_CONTRATOS),
                },
                {
                    "key": "nome",
                    "label": "Ambiente*",
                    "type": "text",
                    "span": "span 2",
                    "ph": "Portaria, Banheiro térreo, Recepção…",
                },
                {"key": "itens", "label": "Itens (um por linha)*", "type": "textarea", "span": "span 2"},
            ],
            okMsg="Ambiente cadastrado.",
        )

    await safe("avaliacao-ambiente-novo", _f_amb())

    await safe(
        "avaliacao-links",
        tbl(
            "Avaliação — links compartilháveis",
            "Página pública por token (QR/totem/celular). Sem login; o token é o acesso.",
            "—",
            ["Contrato", "Link", "Identificação", "Ativo", "Respostas", "Criado"],
            "1.5fr 2.4fr 0.9fr 0.6fr 0.7fr 1fr",
            "SELECT l.token, coalesce(c.contract_number,'') || ' · ' || coalesce(cl.name, c.name, '—'), l.exige_identificacao, l.ativo, "
            "(SELECT count(*) FROM aval_respostas r WHERE r.token = l.token), l.criado_em "
            "FROM aval_links l LEFT JOIN contracts c ON c.id = l.contract_id LEFT JOIN clients cl ON cl.id = c.client_id ORDER BY l.criado_em DESC",
            lambda r: [
                t(r[1], 600, _ND),
                t(f"/api/v1/redesign/publico/avaliacao/{r[0]}"),
                b("obrigatória", "info") if r[2] else b("anônima", "mut"),
                b("sim", "ok") if r[3] else b("não", "bad"),
                t(str(r[4])),
                t(_dt(r[5])),
            ],
            actionsfn=lambda r: [
                {
                    "title": "Desativar link",
                    "sub": "Quem abrir o link depois disso vê 'link encerrado'.",
                    "endpoint": "/api/v1/redesign/action/avaliacao-link-desativar",
                    "method": "POST",
                    "btnLabel": "Desativar",
                    "submitLabel": "Desativar",
                    "okMsg": "Link desativado.",
                    "fixed": {"token": r[0]},
                    "fields": [],
                }
            ]
            if r[3]
            else [],
        ),
    )

    async def _f_link():
        return await _form(
            db,
            "avaliacao-link-novo",
            "Novo link de avaliação",
            "Um link por contrato; com ou sem identificação obrigatória.",
            "Gerar link",
            "/api/v1/redesign/action/avaliacao-link",
            [
                {
                    "key": "contract_id",
                    "label": "Contrato*",
                    "type": "select",
                    "span": "span 2",
                    "options": await _opts(db, _SQL_CONTRATOS),
                },
                {
                    "key": "exige_identificacao",
                    "label": "Identificação*",
                    "type": "select",
                    "options": [
                        {"value": "nao", "label": "Anônima (sem identificação)"},
                        {"value": "sim", "label": "Identificação obrigatória"},
                    ],
                },
            ],
            okMsg="Link gerado.",
            showResult=True,
        )

    await safe("avaliacao-link-novo", _f_link())


# ----------------------------------------------------------------------------- ações: uniforme
@router.post("/action/uniforme-grade")
async def uniforme_grade(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    item = (payload.get("item") or "").strip()
    tam = (payload.get("tamanho") or "").strip().upper()
    if len(item) < 3:
        raise HTTPException(status_code=400, detail="Informe o item (mínimo 3 letras).")
    if not _TAM_RE.match(tam):
        raise HTTPException(status_code=400, detail="Tamanho: PP, P, M, G, GG, EXG ou número de 2 dígitos.")
    mi, ma = _int(payload.get("minimo"), "Mínimo"), _int(payload.get("maximo"), "Máximo")
    if mi is None or ma is None:
        raise HTTPException(
            status_code=400, detail="Mínimo e máximo são obrigatórios — sem eles o estoque não é conferido."
        )
    if mi > ma:
        raise HTTPException(status_code=400, detail="Mínimo maior que máximo.")
    norm = sku_norm(item, tam)
    # ⭐ 18/09/2026 — o vínculo com o catálogo de EPI se resolve SOZINHO pelo nome quando
    # quem cadastra não escolhe no select (o campo é opcional, e uniforme que não é EPI de
    # fato não tem par no catálogo). Sem isto, a grade podia existir inteira e o item do
    # catálogo continuar "sem ninguém conferindo o mínimo" — que é o que o oráculo
    # `test_oraculo_sku_unico` vigia. Casa pela MESMA régua de normalização do SKU, sem
    # tamanho: "Botina de Segurança Marluvas 40" encontra "Botina de Seguranca Marluvas".
    cat_id = payload.get("catalog_id") or None
    if not cat_id:
        for cid, nome in (
            await db.execute(text("SELECT id::text, nome FROM health_epi_catalog WHERE coalesce(ativo, true)"))
        ).all():
            if sku_norm(nome) == sku_norm(item):
                cat_id = cid
                break
    row = (
        await db.execute(
            text(
                "INSERT INTO sst_uniforme_grade (item, tamanho, sku_norm, minimo, maximo, atual, valor_unitario, catalog_id) "
                "VALUES (:item, :tam, :norm, :mi, :ma, :atual, :valor, CAST(:cat AS uuid)) "
                "ON CONFLICT (sku_norm) DO NOTHING RETURNING id"
            ),
            {
                "item": item,
                "tam": tam,
                "norm": norm,
                "mi": mi,
                "ma": ma,
                "atual": _int(payload.get("atual"), "Atual"),
                "valor": _dec(payload.get("valor_unitario"), "Valor"),
                "cat": cat_id,
            },
        )
    ).first()
    if not row:
        raise HTTPException(status_code=409, detail=f"Este SKU já existe: '{norm}'. Não vai duplicar.")
    await db.commit()
    return {"ok": True, "id": row[0], "sku": norm, "message": f"SKU '{norm}' cadastrado."}


@router.post("/action/uniforme-estoque")
async def uniforme_estoque(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    atual = _int(payload.get("atual"), "Quantidade atual")
    if atual is None:
        raise HTTPException(status_code=400, detail="Informe a quantidade contada.")
    n = (
        await db.execute(
            text("UPDATE sst_uniforme_grade SET atual = :a, updated_at = now() WHERE id = :id AND ativo"),
            {"a": atual, "id": _int(payload.get("id"), "id")},
        )
    ).rowcount
    if not n:
        raise HTTPException(status_code=404, detail="SKU não encontrado.")
    await db.commit()
    return {"ok": True, "message": f"Contagem registrada: {atual}."}


@router.post("/action/uniforme-entrega-lote")
async def uniforme_entrega_lote(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    gid = _int(payload.get("grade_id"), "SKU")
    qtd = _int(payload.get("quantidade"), "Quantidade", 1)
    motivo = payload.get("motivo") or ""
    if not gid or not qtd:
        raise HTTPException(status_code=400, detail="SKU e quantidade são obrigatórios.")
    if motivo not in dict(_MOTIVOS):
        raise HTTPException(status_code=400, detail="Motivo inválido.")
    # asyncpg infere o tipo pelo CAST: com `CAST(:p AS date)` ele EXIGE um date, não a string
    # do <input type=date> ("invalid input for query argument ... 'str' object has no attribute").
    prazo = (payload.get("prazo") or "").strip()
    try:
        prazo = date.fromisoformat(prazo) if prazo else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Prazo: use uma data válida.") from None
    ids: dict[str, str] = {}
    post_id = (payload.get("post_id") or "").strip()
    if post_id:
        for eid, nome in (
            await db.execute(
                text(
                    "SELECT DISTINCT e.id::text, e.nome FROM allocations a JOIN employees e ON e.id = a.employee_id "
                    "WHERE a.post_id::text = :p AND coalesce(a.is_active,true) AND e.data_demissao IS NULL"
                ),
                {"p": post_id},
            )
        ).fetchall():
            ids[eid] = nome
    cpfs = [re.sub(r"\D", "", c) for c in (payload.get("cpfs") or "").splitlines() if re.sub(r"\D", "", c)]
    nao_achados = []
    for cpf in cpfs:
        r = (
            await db.execute(
                text(
                    "SELECT id::text, nome FROM employees WHERE regexp_replace(coalesce(cpf,''),'\\D','','g') = :c "
                    "AND data_demissao IS NULL"
                ),
                {"c": cpf},
            )
        ).fetchall()
        if len(r) != 1:
            nao_achados.append(cpf)
        else:
            ids[r[0][0]] = r[0][1]
    if nao_achados:
        raise HTTPException(status_code=400, detail=f"CPF sem colaborador ativo único: {', '.join(nao_achados)}.")
    if not ids:
        raise HTTPException(status_code=400, detail="Nenhum colaborador: escolha um posto com alocados ou liste CPFs.")
    if not (await db.execute(text("SELECT 1 FROM sst_uniforme_grade WHERE id = :g AND ativo"), {"g": gid})).first():
        raise HTTPException(status_code=404, detail="SKU não encontrado.")
    lote = f"L{datetime.now(_TZ).strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}"
    for eid in ids:
        await db.execute(
            text(
                "INSERT INTO sst_uniforme_entregas (lote, grade_id, employee_id, quantidade, motivo, prazo, created_by) "
                "VALUES (:l, :g, CAST(:e AS uuid), :q, :m, CAST(:p AS date), :u)"
            ),
            {"l": lote, "g": gid, "e": eid, "q": qtd, "m": motivo, "p": prazo, "u": _quem(current_user)},
        )
    await db.commit()
    return {
        "ok": True,
        "lote": lote,
        "colaboradores": len(ids),
        "message": f"Lote {lote}: {len(ids)} solicitação(ões) criada(s).",
    }


@router.post("/action/uniforme-entrega-status")
async def uniforme_entrega_status(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    eid = _int(payload.get("id"), "id")
    novo = payload.get("status") or ""
    row = (
        await db.execute(
            text(
                "SELECT e.status, e.quantidade, g.id, g.atual, g.item, g.tamanho FROM sst_uniforme_entregas e "
                "JOIN sst_uniforme_grade g ON g.id = e.grade_id WHERE e.id = :id"
            ),
            {"id": eid},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Entrega não encontrada.")
    atual_st = row[0]
    if novo not in _STATUS_ENTREGA or _STATUS_ENTREGA.index(novo) != _STATUS_ENTREGA.index(atual_st) + 1:
        raise HTTPException(
            status_code=409,
            detail=f"De '{atual_st}' só se vai para "
            f"'{_STATUS_ENTREGA[_STATUS_ENTREGA.index(atual_st) + 1] if atual_st != 'devolvido' else '—'}'.",
        )
    if novo == "entregue":
        # sensível é o default: sem contagem ou estoque insuficiente → bloqueia, não entrega no negativo
        if row[3] is None:
            raise HTTPException(
                status_code=409, detail=f"'{row[4]} {row[5]}' está sem contagem de estoque. Conte antes de entregar."
            )
        if row[3] < row[1]:
            raise HTTPException(
                status_code=409, detail=f"Estoque de '{row[4]} {row[5]}' não cobre: atual {row[3]} < {row[1]}."
            )
        await db.execute(
            text("UPDATE sst_uniforme_grade SET atual = atual - :q, updated_at = now() WHERE id = :g"),
            {"q": row[1], "g": row[2]},
        )
    await db.execute(
        text(f"UPDATE sst_uniforme_entregas SET status = :s, {novo}_em = now() WHERE id = :id"), {"s": novo, "id": eid}
    )
    await db.commit()
    return {"ok": True, "message": f"Entrega #{eid}: {atual_st} → {novo}."}


# ----------------------------------------------------------------------------- ações: frota
@router.post("/action/frota-veiculo")
async def frota_veiculo(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    placa = re.sub(r"[^A-Z0-9]", "", (payload.get("placa") or "").upper())
    if not re.match(r"^[A-Z]{3}\d[A-Z0-9]\d{2}$", placa):
        raise HTTPException(status_code=400, detail="Placa inválida (padrão ABC1D23 ou ABC1234).")
    row = (
        await db.execute(
            text(
                "INSERT INTO frota_veiculos (placa, modelo, km_proxima_troca_oleo, km_proxima_troca_pneu, km_proxima_troca_correia) "
                "VALUES (:p, :m, :o, :pn, :c) ON CONFLICT (placa) DO NOTHING RETURNING id"
            ),
            {
                "p": placa,
                "m": (payload.get("modelo") or "").strip() or None,
                "o": _int(payload.get("km_proxima_troca_oleo"), "Óleo"),
                "pn": _int(payload.get("km_proxima_troca_pneu"), "Pneu"),
                "c": _int(payload.get("km_proxima_troca_correia"), "Correia"),
            },
        )
    ).first()
    if not row:
        raise HTTPException(status_code=409, detail=f"Placa {placa} já cadastrada.")
    await db.commit()
    return {"ok": True, "id": row[0], "message": f"Veículo {placa} cadastrado."}


@router.post("/action/frota-leitura")
async def frota_leitura(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    vid = _int(payload.get("veiculo_id"), "Veículo")
    tipo = payload.get("tipo") or "km"
    km = _int(payload.get("km"), "KM")
    if not vid or km is None or tipo not in ("km", "abastecimento"):
        raise HTTPException(status_code=400, detail="Veículo, tipo e KM são obrigatórios.")
    litros, valor = _dec(payload.get("litros"), "Litros"), _dec(payload.get("valor"), "Valor")
    if tipo == "abastecimento" and not (litros and valor):
        raise HTTPException(status_code=400, detail="Abastecimento pede litros e valor maiores que zero.")
    ultimo = (await db.execute(text("SELECT max(km) FROM frota_leituras WHERE veiculo_id = :v"), {"v": vid})).scalar()
    if ultimo is not None and km < ultimo:
        raise HTTPException(
            status_code=409, detail=f"KM {km} menor que a última leitura ({ultimo}). Hodômetro não anda para trás."
        )
    if not (await db.execute(text("SELECT 1 FROM frota_veiculos WHERE id = :v AND ativo"), {"v": vid})).first():
        raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    await db.execute(
        text(
            "INSERT INTO frota_leituras (veiculo_id, tipo, km, litros, valor, condutor_id, created_by) "
            "VALUES (:v, :t, :k, :l, :va, CAST(:c AS uuid), :u)"
        ),
        {
            "v": vid,
            "t": tipo,
            "k": km,
            "l": litros,
            "va": valor,
            "c": (payload.get("condutor_id") or None),
            "u": _quem(current_user),
        },
    )
    await db.commit()
    return {"ok": True, "message": f"{'Abastecimento' if tipo == 'abastecimento' else 'KM'} registrado: {km} km."}


def _comparar(chegada_areas: dict, chegada_check: str, saida_areas: dict, saida_check: str) -> str:
    if chegada_check == "ok" and saida_check == "avariado":
        return "houve_diferencas"
    for a, d in saida_areas.items():
        if isinstance(d, dict) and d.get("aval") == "ruim" and (chegada_areas.get(a) or {}).get("aval") == "bom":
            return "houve_diferencas"
    return "sem_diferencas"


@router.post("/action/frota-vistoria")
async def frota_vistoria(request: Request, current_user: CurrentActiveUser, db=Depends(get_db)) -> dict:
    form = await request.form()
    vid = _int(form.get("veiculo_id"), "Veículo")
    tipo = form.get("tipo") or ""
    os_ref = (form.get("os_ref") or "").strip()
    cond = (form.get("condutor_id") or "").strip()
    check = form.get("checklist") or ""
    if not vid or tipo not in ("chegada", "saida") or len(os_ref) < 3 or not cond or check not in ("ok", "avariado"):
        raise HTTPException(status_code=400, detail="Veículo, tipo, OS, condutor e checklist são obrigatórios.")
    km = _int(form.get("km"), "KM")
    if not (await db.execute(text("SELECT 1 FROM employees WHERE id::text = :c"), {"c": cond})).first():
        raise HTTPException(status_code=404, detail="Condutor não encontrado.")
    areas: dict = {}
    fotos: dict[str, tuple[str, bytes]] = {}
    for a, _lbl in _AREAS:
        aval = form.get(f"aval_{a}") or ""
        f = form.get(f"foto_{a}")
        if aval in ("bom", "ruim"):
            areas[a] = {"aval": aval}
        if f is not None and hasattr(f, "read"):
            ext = _MIME_EXT.get((f.content_type or "").lower())
            if not ext:
                raise HTTPException(status_code=422, detail=f"Foto '{a}': envie JPEG, PNG ou WebP.")
            conteudo = await f.read()
            if len(conteudo) > _MAX_FOTO:
                raise HTTPException(status_code=422, detail=f"Foto '{a}' acima de 10MB.")
            if conteudo:
                fotos[a] = (ext, conteudo)
                areas.setdefault(a, {})["foto"] = True
    par_id, status = None, None
    if tipo == "saida":
        par = (
            await db.execute(
                text(
                    "SELECT id, areas, checklist, km FROM frota_vistorias c WHERE c.tipo = 'chegada' AND c.veiculo_id = :v "
                    "AND c.os_ref = :os AND c.condutor_id::text = :c AND c.criado_em > now() - make_interval(hours => :h) "
                    "AND NOT EXISTS (SELECT 1 FROM frota_vistorias s WHERE s.par_id = c.id) ORDER BY c.criado_em DESC LIMIT 1"
                ),
                {"v": vid, "os": os_ref, "c": cond, "h": JANELA_VISTORIA_HORAS},
            )
        ).first()
        if par:
            if km is not None and par[3] is not None and km < par[3]:
                raise HTTPException(status_code=409, detail=f"KM {km} menor que o da chegada ({par[3]}).")
            par_id = par[0]
            c_areas = par[1] if isinstance(par[1], dict) else json.loads(par[1] or "{}")
            status = _comparar(c_areas, par[2], areas, check)
        else:
            status = "aguardando_checklist"
    row = (
        await db.execute(
            text(
                "INSERT INTO frota_vistorias (veiculo_id, tipo, os_ref, condutor_id, km, checklist, areas, par_id, status_saida, created_by) "
                "VALUES (:v, :t, :os, CAST(:c AS uuid), :km, :ck, CAST(:ar AS jsonb), :par, :st, :u) RETURNING id"
            ),
            {
                "v": vid,
                "t": tipo,
                "os": os_ref,
                "c": cond,
                "km": km,
                "ck": check,
                "ar": json.dumps(areas),
                "par": par_id,
                "st": status,
                "u": _quem(current_user),
            },
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Veículo não encontrado.")
    vid_row = row[0]
    dest = _FOTOS_DIR / str(vid_row)
    for a, (ext, conteudo) in fotos.items():
        dest.mkdir(parents=True, exist_ok=True)
        (dest / f"{a}{ext}").write_bytes(conteudo)
        areas[a]["foto"] = f"{a}{ext}"
    if fotos:
        await db.execute(
            text("UPDATE frota_vistorias SET areas = CAST(:ar AS jsonb) WHERE id = :id"),
            {"ar": json.dumps(areas), "id": vid_row},
        )
    await db.commit()
    rotulo = {
        "sem_diferencas": "Sem diferenças",
        "houve_diferencas": "Houve diferenças",
        "aguardando_checklist": "Aguardando checklist (sem chegada da mesma OS/condutor)",
    }.get(status, "Chegada registrada")
    return {
        "ok": True,
        "id": vid_row,
        "par_id": par_id,
        "status_saida": status,
        "fotos": len(fotos),
        "message": f"Vistoria #{vid_row}: {rotulo}.",
    }


@router.get("/frota/vistorias/{vistoria_id}/fotos/{area}")
async def frota_vistoria_foto(
    vistoria_id: int, area: str, current_user: CurrentActiveUser, db=Depends(get_db)
) -> FileResponse:
    areas = (await db.execute(text("SELECT areas FROM frota_vistorias WHERE id = :id"), {"id": vistoria_id})).scalar()
    areas = areas if isinstance(areas, dict) else json.loads(areas or "{}")
    nome = (areas.get(area) or {}).get("foto")
    base = (_FOTOS_DIR / str(vistoria_id)).resolve()
    alvo = (base / str(nome)).resolve() if nome else None
    if not alvo or not str(alvo).startswith(str(base)) or not alvo.is_file():
        raise HTTPException(status_code=404, detail="Foto não encontrada.")
    return FileResponse(alvo)


# ----------------------------------------------------------------------------- ações: avaliação
@router.post("/action/avaliacao-ambiente")
async def avaliacao_ambiente(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    cid = (payload.get("contract_id") or "").strip()
    nome = (payload.get("nome") or "").strip()
    itens = [i.strip() for i in (payload.get("itens") or "").splitlines() if i.strip()]
    if not cid or len(nome) < 3 or not itens:
        raise HTTPException(status_code=400, detail="Contrato, ambiente e ao menos um item são obrigatórios.")
    row = (
        await db.execute(
            text(
                "INSERT INTO aval_ambientes (contract_id, nome, itens) VALUES (CAST(:c AS uuid), :n, CAST(:i AS jsonb)) "
                "ON CONFLICT (contract_id, nome) DO NOTHING RETURNING id"
            ),
            {"c": cid, "n": nome, "i": json.dumps(itens)},
        )
    ).first()
    if not row:
        raise HTTPException(status_code=409, detail=f"Ambiente '{nome}' já existe neste contrato.")
    await db.commit()
    return {"ok": True, "id": row[0], "message": f"Ambiente '{nome}' com {len(itens)} item(ns)."}


@router.post("/action/avaliacao-link")
async def avaliacao_link(
    request: Request, current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    cid = (payload.get("contract_id") or "").strip()
    if not cid:
        raise HTTPException(status_code=400, detail="Escolha o contrato.")
    if not (
        await db.execute(text("SELECT 1 FROM aval_ambientes WHERE contract_id::text = :c AND ativo"), {"c": cid})
    ).first():
        raise HTTPException(
            status_code=409, detail="Este contrato não tem ambiente cadastrado — cadastre antes de gerar o link."
        )
    token = secrets.token_urlsafe(24)
    await db.execute(
        text("INSERT INTO aval_links (token, contract_id, exige_identificacao) VALUES (:t, CAST(:c AS uuid), :e)"),
        {"t": token, "c": cid, "e": (payload.get("exige_identificacao") == "sim")},
    )
    await db.commit()
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    path = f"/api/v1/redesign/publico/avaliacao/{token}"
    return {
        "ok": True,
        "url": f"https://{host}{path}" if host else path,
        "message": "Link gerado — copie a URL abaixo.",
    }


@router.post("/action/avaliacao-link-desativar")
async def avaliacao_link_desativar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)
) -> dict:
    n = (
        await db.execute(
            text("UPDATE aval_links SET ativo = false WHERE token = :t AND ativo"), {"t": payload.get("token") or ""}
        )
    ).rowcount
    if not n:
        raise HTTPException(status_code=404, detail="Link não encontrado ou já inativo.")
    await db.commit()
    return {"ok": True, "message": "Link desativado."}


_CSS = (
    "body{font-family:system-ui,sans-serif;background:#F1F4FA;margin:0;padding:16px;color:#0F1B3A}"
    ".c{max-width:520px;margin:0 auto;background:#fff;border-radius:12px;padding:20px;box-shadow:0 2px 12px rgba(15,27,58,.08)}"
    "h1{font-size:20px;margin:0 0 4px}p.s{color:#64748B;margin:0 0 16px;font-size:14px}label{display:block;font-weight:600;margin:14px 0 6px}"
    "select,input[type=text],textarea{width:100%;padding:10px;border:1px solid #CBD5E1;border-radius:8px;font-size:15px;box-sizing:border-box}"
    ".it{border-top:1px solid #E2E8F0;padding:10px 0}.it b{display:block;margin-bottom:6px}.n{display:flex;gap:6px;flex-wrap:wrap}"
    ".n label{margin:0;flex:1;text-align:center;border:1px solid #CBD5E1;border-radius:8px;padding:8px 4px;font-weight:500;font-size:13px;cursor:pointer}"
    ".n input{display:none}.n input:checked+span{font-weight:700}.n label:has(input:checked){background:#EAF0FF;border-color:#2563EB}"
    "button{width:100%;margin-top:18px;padding:12px;background:#F26522;color:#fff;border:0;border-radius:8px;font-size:16px;font-weight:600}"
    ".ok{text-align:center;font-size:18px;padding:30px 0}"
)


async def _link_ativo(db, token: str):
    return (
        await db.execute(
            text(
                "SELECT l.contract_id::text, l.exige_identificacao, coalesce(cl.name, c.name, c.contract_number, '—') "
                "FROM aval_links l LEFT JOIN contracts c ON c.id = l.contract_id LEFT JOIN clients cl ON cl.id = c.client_id "
                "WHERE l.token = :t AND l.ativo"
            ),
            {"t": token},
        )
    ).first()


def _pagina(titulo: str, corpo: str) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(titulo)}</title><style>{_CSS}</style></head><body><div class='c'>{corpo}</div></body></html>"
    )


@router.get("/publico/avaliacao/{token}", response_class=HTMLResponse)
async def avaliacao_publica(token: str, db=Depends(get_db)):
    """Página pública (totem/QR/celular). Sem login: o token do link é o acesso. Não grava IP nem
    usuário — anônima quanto à pessoa; contrato + ambiente + turno são obrigatórios."""
    link = await _link_ativo(db, token)
    if not link:
        return _pagina(
            "Avaliação", "<h1>Link encerrado</h1><p class='s'>Este link de avaliação não está mais ativo.</p>"
        )
    ambs = (
        await db.execute(
            text("SELECT id, nome, itens FROM aval_ambientes WHERE contract_id::text = :c AND ativo ORDER BY nome"),
            {"c": link[0]},
        )
    ).fetchall()
    itens_js = {str(a[0]): (a[2] if isinstance(a[2], list) else json.loads(a[2] or "[]")) for a in ambs}
    opts = "".join(f"<option value='{a[0]}'>{html.escape(a[1])}</option>" for a in ambs)
    turnos = "".join(f"<option value='{k}'>{v}</option>" for k, v in _TURNOS)
    notas = "".join(
        f"<label><input type='radio' name='__N__' value='{k}' required><span>{e}<br>{v}</span></label>"
        for k, v, e in _NOTAS
    )
    ident = (
        "<label>Seu nome*</label><input type='text' name='identificacao' required maxlength='120'>"
        if link[1]
        else "<label>Seu nome (opcional)</label><input type='text' name='identificacao' maxlength='120'>"
    )
    corpo = (
        f"<h1>Como está o serviço?</h1><p class='s'>{html.escape(link[2])} · marque uma carinha por item</p>"
        f"<form method='post'><label>Ambiente*</label><select name='ambiente_id' id='amb' required><option value=''>Selecione…</option>{opts}</select>"
        f"<label>Turno*</label><select name='turno' required><option value=''>Selecione…</option>{turnos}</select>"
        f"<div id='itens'></div>{ident}<label>Comentário (opcional)</label><textarea name='comentario' rows='3' maxlength='500'></textarea>"
        f"<button type='submit'>Enviar avaliação</button></form>"
        f"<script>var I={json.dumps(itens_js, ensure_ascii=False)};var T={json.dumps(notas)};"
        "function esc(s){return s.replace(/[&<>\"']/g,function(c){return '&#'+c.charCodeAt(0)+';'})}"
        "document.getElementById('amb').onchange=function(){var h='';(I[this.value]||[]).forEach(function(it,i){"
        "h+='<div class=it><b>'+esc(it)+'</b><div class=n>'+T.split('__N__').join('nota_'+i)+'</div></div>'});"
        "document.getElementById('itens').innerHTML=h};</script>"
    )
    return _pagina("Avaliação", corpo)


@router.post("/publico/avaliacao/{token}", response_class=HTMLResponse)
async def avaliacao_publica_responder(token: str, request: Request, db=Depends(get_db)):
    link = await _link_ativo(db, token)
    if not link:
        return _pagina("Avaliação", "<h1>Link encerrado</h1>")
    form = await request.form()
    amb = (
        await db.execute(
            text("SELECT id, itens FROM aval_ambientes WHERE id::text = :a AND contract_id::text = :c AND ativo"),
            {"a": str(form.get("ambiente_id") or ""), "c": link[0]},
        )
    ).first()
    turno = form.get("turno") or ""
    if not amb or turno not in dict(_TURNOS):
        return _pagina("Avaliação", "<h1>Faltou ambiente ou turno</h1><p class='s'>Volte e escolha os dois.</p>")
    itens = amb[1] if isinstance(amb[1], list) else json.loads(amb[1] or "[]")
    validas = {k for k, _v, _e in _NOTAS}
    notas = {}
    for i, it in enumerate(itens):
        v = form.get(f"nota_{i}") or ""
        if v not in validas:
            return _pagina(
                "Avaliação",
                f"<h1>Faltou avaliar '{html.escape(it)}'</h1><p class='s'>Marque uma carinha em cada item (ou N/A).</p>",
            )
        notas[it] = v
    ident = (form.get("identificacao") or "").strip()[:120] or None
    if link[1] and not ident:
        return _pagina("Avaliação", "<h1>Este link pede identificação</h1><p class='s'>Informe seu nome.</p>")
    await db.execute(
        text(
            "INSERT INTO aval_respostas (token, ambiente_id, turno, identificacao, notas, comentario) "
            "VALUES (:t, :a, :tu, :i, CAST(:n AS jsonb), :c)"
        ),
        {
            "t": token,
            "a": amb[0],
            "tu": turno,
            "i": ident,
            "n": json.dumps(notas, ensure_ascii=False),
            "c": (form.get("comentario") or "").strip()[:500] or None,
        },
    )
    await db.commit()
    return _pagina(
        "Obrigado",
        "<div class='ok'>🙂 Obrigado! Sua avaliação foi registrada.</div>"
        f"<p class='s' style='text-align:center'><a href='/api/v1/redesign/publico/avaliacao/{html.escape(token)}'>Avaliar outro ambiente</a></p>",
    )


# ----------------------------------------------------------------------------- DDL (referência)
DDL = """
CREATE TABLE IF NOT EXISTS sst_uniforme_grade (
  id serial PRIMARY KEY, item varchar(120) NOT NULL, tamanho varchar(10) NOT NULL,
  sku_norm varchar(140) NOT NULL UNIQUE, minimo integer NOT NULL CHECK (minimo >= 0),
  maximo integer NOT NULL CHECK (maximo >= minimo), atual integer CHECK (atual >= 0),
  valor_unitario numeric(12,2), catalog_id uuid, ativo boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS sst_uniforme_entregas (
  id serial PRIMARY KEY, lote varchar(40) NOT NULL, grade_id integer NOT NULL REFERENCES sst_uniforme_grade(id),
  employee_id uuid NOT NULL, quantidade integer NOT NULL CHECK (quantidade > 0), motivo varchar(30) NOT NULL, prazo date,
  status varchar(20) NOT NULL DEFAULT 'solicitado' CHECK (status IN ('solicitado','separado','entregue','devolvido')),
  solicitado_em timestamptz NOT NULL DEFAULT now(), separado_em timestamptz, entregue_em timestamptz, devolvido_em timestamptz,
  created_by varchar(120));
CREATE INDEX IF NOT EXISTS ix_sst_uniforme_entregas_grade ON sst_uniforme_entregas (grade_id, status);
CREATE TABLE IF NOT EXISTS frota_veiculos (
  id serial PRIMARY KEY, placa varchar(10) NOT NULL UNIQUE, modelo varchar(80),
  km_proxima_troca_oleo integer, km_proxima_troca_pneu integer, km_proxima_troca_correia integer,
  ativo boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS frota_leituras (
  id serial PRIMARY KEY, veiculo_id integer NOT NULL REFERENCES frota_veiculos(id),
  tipo varchar(15) NOT NULL CHECK (tipo IN ('km','abastecimento')), km integer NOT NULL CHECK (km >= 0),
  litros numeric(8,2), valor numeric(10,2), condutor_id uuid, lida_em timestamptz NOT NULL DEFAULT now(), created_by varchar(120));
CREATE INDEX IF NOT EXISTS ix_frota_leituras_veiculo ON frota_leituras (veiculo_id, lida_em);
CREATE TABLE IF NOT EXISTS frota_vistorias (
  id serial PRIMARY KEY, veiculo_id integer NOT NULL REFERENCES frota_veiculos(id),
  tipo varchar(10) NOT NULL CHECK (tipo IN ('chegada','saida')), os_ref varchar(40) NOT NULL, condutor_id uuid NOT NULL,
  km integer, checklist varchar(10) NOT NULL CHECK (checklist IN ('ok','avariado')), areas jsonb NOT NULL DEFAULT '{}'::jsonb,
  par_id integer REFERENCES frota_vistorias(id),
  status_saida varchar(25) CHECK (status_saida IN ('sem_diferencas','houve_diferencas','aguardando_checklist')),
  criado_em timestamptz NOT NULL DEFAULT now(), created_by varchar(120));
CREATE TABLE IF NOT EXISTS aval_ambientes (
  id serial PRIMARY KEY, contract_id uuid NOT NULL, nome varchar(80) NOT NULL, itens jsonb NOT NULL DEFAULT '[]'::jsonb,
  ativo boolean NOT NULL DEFAULT true, criado_em timestamptz NOT NULL DEFAULT now(), UNIQUE (contract_id, nome));
CREATE TABLE IF NOT EXISTS aval_links (
  token varchar(48) PRIMARY KEY, contract_id uuid NOT NULL, exige_identificacao boolean NOT NULL DEFAULT false,
  ativo boolean NOT NULL DEFAULT true, criado_em timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS aval_respostas (
  id serial PRIMARY KEY, token varchar(48) NOT NULL REFERENCES aval_links(token),
  ambiente_id integer NOT NULL REFERENCES aval_ambientes(id), turno varchar(10) NOT NULL CHECK (turno IN ('manha','tarde','noite')),
  identificacao varchar(120), notas jsonb NOT NULL, comentario text, criado_em timestamptz NOT NULL DEFAULT now());
CREATE INDEX IF NOT EXISTS ix_aval_respostas_amb ON aval_respostas (ambiente_id, criado_em);
"""
