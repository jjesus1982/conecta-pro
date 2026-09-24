"""Frente 03 — Benefício ligado ao ponto no DP (12/09/2026): três telas de LEITURA + os forms que
rodam o motor, geram o arquivo do operador e ABREM PEDIDO de reajuste. Nada aqui escreve em
folha, holerite, pagamento ou contrato — é o paralelo cego do pré-mortem.

Prefixo `_` = o discovery de builders pula este arquivo; `departamento_pessoal.py` importa
`telas(db, out)` no fim do build() e `router` no nível do módulo (2 + 1 linhas, `# frente 03`).
As telas entram como abas do grupo "Benefícios & Reembolsos" (g-beneficios) quando ele existe."""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, t

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
#: onde os relatórios dos portais são procurados pelo form "calcular" (produção monta uploads/ em /app/uploads)
PDF_DIRS = ("/app/uploads/referencia_kits", "/app/uploads/kits", "/pdfs")

_TONE = {
    "ok": "ok",
    "sem_anterior": "info",
    "anterior_sem_ponto": "warn",
    "anterior_nao_integral": "warn",
    "so_portal": "bad",
    "sem_parametro": "bad",
    "sem_modalidade": "warn",
    "sem_escala": "bad",
    "sem_regra": "bad",
    "cortado_faltas": "warn",
}  # dgx f3: regra lida de beneficio_tipos


def _delta(v):
    if v is None:
        return t("—")
    v = Decimal(v)
    return b(("+" if v > 0 else "") + brl(float(v)), "ok" if v == 0 else ("warn" if abs(v) <= 30 else "bad"))


def _n(v):
    return t("—" if v is None else str(v))


async def telas(db, out: dict | None = None) -> dict:
    mine, safe, tbl = _helpers(db)
    await safe(
        "beneficio-conferencia",
        tbl(
            "Benefício calculado × folha × portal",
            "Paralelo cego (frente 03): o que o motor calculou pela escala e pelo ponto, o que a folha concede hoje e o que "
            "o portal pagou. Nada daqui vai para a folha — a Pyetra confere no olho até fechar dois meses.",
            "—",
            [
                "Colaborador",
                "Comp.",
                "Benef.",
                "Estado",
                "Plan.ant",
                "Trab.ant",
                "Receb.ant",
                "Prev.",
                "+Pt",
                "−Pt",
                "Qtd",
                "Unit.",
                "Calculado",
                "Folha",
                "Portal",
                "Δ calc−portal",
            ],
            "1.8fr 0.6fr 0.5fr 1fr 0.5fr 0.5fr 0.7fr 0.5fr 0.4fr 0.4fr 0.4fr 0.6fr 0.8fr 0.8fr 0.8fr 0.9fr",
            "SELECT e.nome, to_char(c.competencia,'MM/YYYY'), c.beneficio, c.estado, c.planejado_anterior, c.trabalhado_anterior, "
            " c.recebido_anterior, c.previsao, c.mais_ponto, c.menos_ponto, c.quantidade, c.unitario, c.total, c.concedido_folha, "
            " c.portal_valor, CASE WHEN c.total IS NOT NULL AND c.portal_valor IS NOT NULL THEN c.total - c.portal_valor END, c.operadora "
            "FROM folha_beneficio_conferencia c JOIN employees e ON e.id = c.employee_id "
            "WHERE c.competencia >= (date_trunc('month', now() AT TIME ZONE 'America/Manaus') - interval '3 months')::date "
            "ORDER BY c.competencia DESC, e.nome, c.beneficio LIMIT 600",
            lambda r: [
                t(r[0], 600, _ND),
                t(r[1]),
                b(f"{r[2]}{(' ' + r[16][:3]) if r[16] else ''}", "info"),
                b((r[3] or "—").replace("_", " "), _TONE.get(r[3], "mut")),
                _n(r[4]),
                _n(r[5]),
                t(brl(float(r[6])) if r[6] is not None else "—"),
                _n(r[7]),
                _n(r[8]),
                _n(r[9]),
                _n(r[10]),
                t(brl(float(r[11])) if r[11] is not None else "—"),
                t(brl(float(r[12])) if r[12] is not None else "—", 600),
                t(brl(float(r[13])) if r[13] is not None else "—"),
                t(brl(float(r[14])) if r[14] is not None else "—"),
                _delta(r[15]),
            ],
        ),
    )

    await safe(
        "beneficio-frequencia",
        tbl(
            "Mapa de frequência (dia a dia)",
            "Um caractere por dia: T trabalhou · E trabalhou fora da escala · F falta · I ponto < horas mínimas · S sem ponto no mês · "
            "O folga · V férias · A afastado · X fora do vínculo · ? escala não cadastrada. Fonte da escala: shifts (lançada) ou escala_padrao.",
            "—",
            ["Colaborador", "Comp.", "Escala", "Fonte", "T", "E", "F", "I", "S", "V", "A", "Mapa"],
            "1.8fr 0.6fr 0.5fr 0.9fr 0.3fr 0.3fr 0.3fr 0.3fr 0.3fr 0.3fr 0.3fr 3fr",
            "SELECT e.nome, to_char(c.competencia,'MM/YYYY'), coalesce(c.mapa->>'escala','—'), coalesce(c.fonte_escala,'—'), "
            " c.mapa->'contagem'->>'T', c.mapa->'contagem'->>'E', c.mapa->'contagem'->>'F', c.mapa->'contagem'->>'I', "
            " c.mapa->'contagem'->>'S', c.mapa->'contagem'->>'V', c.mapa->'contagem'->>'A', "
            " (SELECT string_agg(value, '' ORDER BY key) FROM jsonb_each_text(c.mapa->'dias')) "
            "FROM folha_beneficio_conferencia c JOIN employees e ON e.id = c.employee_id "
            "WHERE c.beneficio = 'VR' AND c.mapa IS NOT NULL "
            "AND c.competencia >= (date_trunc('month', now() AT TIME ZONE 'America/Manaus') - interval '3 months')::date "
            "ORDER BY c.competencia DESC, e.nome LIMIT 400",
            lambda r: [
                t(r[0], 600, _ND),
                t(r[1]),
                t(r[2]),
                b(r[3], "ok" if r[3] == "shifts" else "warn"),
                b(r[4] or "0", "ok"),
                t(r[5] or "0"),
                b(r[6] or "0", "bad" if (r[6] or "0") != "0" else "mut"),
                t(r[7] or "0"),
                t(r[8] or "0"),
                t(r[9] or "0"),
                t(r[10] or "0"),
                t(r[11] or "—"),
            ],
        ),
    )

    mine["beneficio-calcular"] = {
        "title": "Calcular benefício da competência (paralelo cego)",
        "sub": "Roda o motor pela escala + ponto e importa os relatórios de portal que estiverem em uploads/referencia_kits e "
        "uploads/kits. Grava SÓ na tabela de conferência — não toca folha nem pagamento.",
        "cta": "Calcular",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/beneficio-calcular",
            "okMsg": "Calculado — veja o resultado e a aba de conferência.",
            "showResult": True,
        },
        "fields": [
            {"key": "competencia", "label": "Competência (AAAA-MM)*", "type": "text", "span": "span 1", "ph": "2026-09"}
        ],
    }
    mine["beneficio-arquivo"] = {
        "title": "Arquivo do operador (Sólides / SINETRAM)",
        "sub": "Gera o pedido com as colunas do relatório do portal a partir do que o motor calculou. ⚠️ Layout oficial de importação "
        "ainda não confirmado com o portal — o arquivo é relido pelo nosso parser (oráculo de ida e volta), não pelo deles.",
        "cta": "Gerar",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/beneficio-arquivo-operador",
            "okMsg": "Arquivo gerado — o conteúdo está no resultado.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "competencia",
                "label": "Competência (AAAA-MM)*",
                "type": "text",
                "span": "span 1",
                "ph": "2026-09",
            },
            {
                "key": "operadora",
                "label": "Operadora*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [
                    {"value": "solides", "label": "Sólides (VA + mobilidade)"},
                    {"value": "sinetram", "label": "SINETRAM (VT)"},
                ],
            },
        ],
    }
    mine["beneficio-reajuste"] = {
        "title": "Reajuste de benefício com repasse — abrir PEDIDO",
        "sub": "Simula R$ Contrato / R$ Unitário / R$ Repasse por contrato × função e abre um pedido 🔴 na Central de Aprovações. "
        "Aprovar NÃO muda preço nem unitário: o preço muda por aditivo assinado, contrato a contrato.",
        "cta": "Simular e abrir pedido",
        "type": "form",
        "submit": {
            "endpoint": "/api/v1/redesign/action/beneficio-reajuste-pedido",
            "okMsg": "Pedido aberto na Central de Aprovações.",
            "showResult": True,
        },
        "fields": [
            {
                "key": "beneficio",
                "label": "Benefício*",
                "type": "select",
                "span": "span 1",
                "ph": "Selecione",
                "options": [{"value": "VR", "label": "Vale-refeição"}, {"value": "VT", "label": "Vale-transporte"}],
            },
            {
                "key": "novo_unitario",
                "label": "Novo valor por dia (R$)*",
                "type": "text",
                "span": "span 1",
                "ph": "24.00",
            },
            {
                "key": "competencia",
                "label": "Competência base (AAAA-MM)*",
                "type": "text",
                "span": "span 1",
                "ph": "2026-09",
            },
            {
                "key": "justificativa",
                "label": "Justificativa",
                "type": "textarea",
                "span": "span 2",
                "ph": "CCT 2027, reajuste da tarifa…",
            },
        ],
    }

    ids = [
        ("beneficio-conferencia", "Benefício × ponto × portal"),
        ("beneficio-frequencia", "Mapa de frequência"),
        ("beneficio-calcular", "Calcular competência"),
        ("beneficio-arquivo", "Arquivo do operador"),
        ("beneficio-reajuste", "Reajuste com repasse (pedido)"),
    ]
    grupo = (out or {}).get("g-beneficios")
    if isinstance(grupo, dict) and isinstance(grupo.get("tabs"), list):
        from modules.operacional.controllers.redesign_data_controller import moved

        for tid, lbl in ids:
            if tid in mine:
                grupo["tabs"].append({"id": tid, "label": lbl, "screen": mine[tid]})
                mine[tid] = moved("g-beneficios", tid)
    return mine


# ───────────────────────── ações (POST /api/v1/redesign/action/…) ─────────────────────────
router = APIRouter()


def _comp(payload: dict) -> tuple[int, int]:
    c = str(payload.get("competencia") or "").strip()
    try:
        ano, mes = int(c[:4]), int(c[5:7])
        assert c[4] == "-" and 1 <= mes <= 12 and 2020 <= ano <= 2100
    except Exception:
        raise HTTPException(status_code=400, detail="Competência no formato AAAA-MM (ex.: 2026-09).")
    return ano, mes


@router.post("/action/beneficio-calcular")
async def rd_beneficio_calcular(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    import glob

    from modules.people_management.folha.services import beneficio_ponto as bp

    ano, mes = _comp(payload)
    pdfs = sorted({p for d in PDF_DIRS for p in glob.glob(f"{d}/**/*.pdf", recursive=True)})
    portal = await bp.importar_portal(db, pdfs) if pdfs else {"pedidos": [], "gravados": 0}
    res = await bp.calcular_competencia(db, ano, mes)
    return {
        "ok": True,
        "message": f"{res['pessoas']} pessoa(s), {res['linhas']} linha(s) calculadas em {res['competencia']}",
        "competencia": res["competencia"],
        "pessoas": res["pessoas"],
        "linhas": res["linhas"],
        "estados": res["estados"],
        "portal_pedidos_lidos": len(portal["pedidos"]),
        "portal_valores_gravados": portal["gravados"],
        "sem_parametro": len(res["sem_parametro"]),
    }


@router.post("/action/beneficio-arquivo-operador")
async def rd_beneficio_arquivo(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    from modules.people_management.folha.services import beneficio_ponto as bp

    ano, mes = _comp(payload)
    op = str(payload.get("operadora") or "").lower()
    if op not in ("solides", "sinetram"):
        raise HTTPException(status_code=400, detail="Operadora: solides ou sinetram.")
    quem = getattr(current_user, "full_name", None) or getattr(current_user, "email", "") or "Conecta PRO"
    try:
        nome, texto, avisos = await bp.gerar_arquivo_operador(db, ano, mes, op, str(quem))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    n = max(0, len(texto.splitlines()) - (9 if op == "solides" else 6))
    return {
        "ok": True,
        "message": f"{nome}: {n} linha(s). Layout oficial do portal a confirmar antes de subir.",
        "arquivo": nome,
        "linhas": n,
        "avisos": len(avisos),
        "avisos_detalhe": {f"aviso {i + 1}": a for i, a in enumerate(avisos[:20])},
        "conteudo": texto,
    }


@router.post("/action/beneficio-reajuste-pedido")
async def rd_beneficio_reajuste(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    from modules.people_management.folha.services import beneficio_ponto as bp

    ano, mes = _comp(payload)
    ben = str(payload.get("beneficio") or "").upper()
    try:
        novo = Decimal(str(payload.get("novo_unitario") or "").replace(",", "."))
        assert novo > 0
    except (InvalidOperation, AssertionError):
        raise HTTPException(status_code=400, detail="Novo valor por dia inválido (ex.: 24.00).")
    if ben not in ("VR", "VT"):
        raise HTTPException(status_code=400, detail="Benefício: VR ou VT.")
    r = await bp.abrir_pedido_reajuste(db, current_user, ben, novo, ano, mes, str(payload.get("justificativa") or ""))
    sim = r["simulacao"]
    if not r["ok"]:
        raise HTTPException(
            status_code=422,
            detail=(r.get("erro") or (r.get("rascunho") or {}).get("erro") or "não abriu")
            + " · "
            + "; ".join(sim["avisos"][:5]),
        )
    rasc = r["rascunho"] or {}
    return {
        "ok": True,
        "message": ("Pedido já existia (não duplicado)" if rasc.get("duplicado") else "Pedido aberto")
        + f" — rascunho {str(rasc.get('draft_id') or '')[:8]}",
        "beneficio": ben,
        "competencia": sim["competencia"],
        "novo_unitario_valor": float(novo),
        "beneficiarios": sim["beneficiarios"],
        "contratos": len({x["contrato"] for x in sim["linhas"]}),
        "repasse_total_mes_valor": float(sim["repasse_total_mes"]),
        "avisos": len(sim["avisos"]),
        "por_contrato_e_funcao": {
            f"{x['contrato']} · {x['funcao']} ({x['operadora']})": f"{x['beneficiarios']} × {x['dias']} dias · {brl(float(x['unitario_atual']))} → {brl(float(x['unitario_novo']))} · "
            f"contrato {brl(float(x['valor_contrato'])) if x['valor_contrato'] is not None else 'sem dado'} · repasse {brl(float(x['repasse_mes']))}/mês"
            for x in sim["linhas"]
        },
        "rascunho_id": rasc.get("draft_id"),
    }
