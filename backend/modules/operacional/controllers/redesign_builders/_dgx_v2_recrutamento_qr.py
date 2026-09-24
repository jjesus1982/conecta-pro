"""DGX V2 — Vaga do contrato → Recrutamento, e QR de abertura de chamado por setor (24/09/2026).

Duas lacunas da onda 4 (`docs/dgx/lacunas/operacional_comercial.md`):

  #12 **Vaga → Recrutamento** — no DGX o supervisor vê o buraco no grid e clica «Recrutamento»:
      abre a vaga no RH já preenchida pela vaga do contrato. Aqui a vaga do contrato é o `posts`
      (T3 deu a ele `contract_id` e `salario_base`) e a vaga do RH é `job_positions` — as duas não
      se conheciam. Agora `job_positions.post_id/contract_id` fecham o elo, a ação `vaga-recrutar`
      abre a vaga pré-preenchida (função, escala, salário base ou piso da CCT, condomínio,
      quantidade = o descoberto de HOJE) e a esteira de candidatos, ao aprovar alguém vindo dessa
      vaga, registra a MOVIMENTAÇÃO (F5, motivo `alocacao_de_vaga`) e baixa a vaga.
      Idempotente por índice único: **uma vaga ABERTA por posto** — recrutar de novo aponta a que
      já existe em vez de criar a segunda.

  #10 **QR de chamado por setor** — no DGX a etiqueta do setor tem um QR que abre chamado sem
      login. Aqui `op_setores` (U4) ganha `token` (gerado uma vez, nunca reemitido), a página
      pública copia o padrão da avaliação por token (frente 10: sem login, o token É o acesso) e o
      POST cai no `supervisao_service.abrir_chamado` — o MESMO serviço da F8, que já valida setor
      e já avisa o responsável. Canal novo: `qr`. A etiqueta sai em PDF timbrado (padrão-ouro).

Prefixo `_` = o discovery pula; `operacional.py` importa `router` no topo e chama `telas(db, out)`
antes de `montar_grupos` (aba `setor-etiqueta` no FIM de g-comunicacao em `_op_grupos`).

Telas/portas (deep-link `/redesign/operacional?t=<id>`):
  g-postos      · `vagas-do-contrato` e `grid-real-contratual` ganham a ação **Recrutar** por linha
  g-comunicacao · `setores` ganha o documento **Etiqueta QR** por linha · `setor-etiqueta` (aba nova)
Rotas: POST /api/v1/redesign/action/vaga-recrutar · GET /api/v1/redesign/setores/{id}/etiqueta/pdf
       GET|POST /api/v1/redesign/publico/chamado/{token}  (sem login, rate limit)
"""

from __future__ import annotations

import html
import logging
import os

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.rate_limit import limiter

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_END = "/api/v1/redesign/action/"
BASE_URL = os.getenv("PUBLIC_BASE_URL", "https://erp.conectamais.pro").rstrip("/")
PUBLICO = "/api/v1/redesign/publico/chamado"

_DDL = (
    # elo vaga do RH → vaga do contrato (posto) e contrato
    "ALTER TABLE job_positions ADD COLUMN IF NOT EXISTS post_id uuid",
    "ALTER TABLE job_positions ADD COLUMN IF NOT EXISTS contract_id uuid",
    # a idempotência do "recrutar" é uma REGRA DO BANCO, não um if: uma vaga aberta por posto
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_job_positions_post_aberta ON job_positions (post_id) "
    "WHERE post_id IS NOT NULL AND status = 'aberta' AND coalesce(is_deleted, false) = false",
    # token do QR do setor — gerado UMA vez (etiqueta já impressa não pode virar lixo)
    "ALTER TABLE op_setores ADD COLUMN IF NOT EXISTS token varchar(48)",
    "UPDATE op_setores SET token = replace(gen_random_uuid()::text, '-', '') WHERE token IS NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_op_setores_token ON op_setores (token) WHERE token IS NOT NULL",
)

SQL_SETOR_POR_TOKEN = """
SELECT s.id::text, s.nome, coalesce(cl.name, '—'), coalesce(k.contract_number, '—')
FROM op_setores s LEFT JOIN clients cl ON cl.id = s.client_id LEFT JOIN contracts k ON k.id = s.contract_id
WHERE s.token = :t AND s.ativo
"""
SQL_POSTO_DA_VAGA = """
SELECT p.id::text, p.name, coalesce(p.post_type, ''), coalesce(p.shift_type, ''),
       coalesce(p.required_headcount, 0), p.salario_base, p.contract_id::text, p.client_id::text,
       coalesce(cl.name, ''), coalesce(nullif(concat_ws('/', p.city, p.state), ''), ''),
       (SELECT count(*) FROM allocations a WHERE a.post_id = p.id AND a.status = 'active' AND a.is_active),
       (SELECT c.id::text FROM condominios c WHERE c.client_id = p.client_id AND c.ativo ORDER BY c.nome LIMIT 1)
FROM posts p LEFT JOIN clients cl ON cl.id = p.client_id
WHERE p.id = CAST(:p AS uuid) AND coalesce(p.is_active, true)
"""
SQL_SETORES_QR = """
SELECT s.id::text, s.nome, s.token, coalesce(cl.name, '—'), s.ativo,
       (SELECT count(*) FROM op_chamados ch WHERE ch.setor_id = s.id AND ch.canal = 'qr')
FROM op_setores s LEFT JOIN clients cl ON cl.id = s.client_id
ORDER BY s.ativo DESC, cl.name NULLS LAST, s.nome
"""


async def _ensure(db) -> None:
    for sql in _DDL:
        await db.execute(text(sql))
    await db.commit()


async def piso_cct(db, funcao: str) -> float | None:
    """Piso da CCT para a função. MESMA escada da esteira de candidatos
    (`candidatos_esteira_controller.aprovar_e_ativar`): o vínculo verdadeiro é `cct_cargo_id` do
    quadro real — o nome da nossa função não casa com o da CCT. Só se ninguém usa a função é que
    se tenta o nome direto em `cct_cargos`."""
    if not (funcao or "").strip():
        return None
    v = (
        await db.execute(
            text(
                "SELECT cc.piso_salarial FROM employees e JOIN cct_cargos cc ON cc.id = e.cct_cargo_id "
                "WHERE e.status = 'ativo' AND coalesce(e.is_homologacao, false) = false AND upper(e.cargo) = upper(:c) "
                "GROUP BY cc.id, cc.piso_salarial ORDER BY count(*) DESC LIMIT 1"
            ),
            {"c": funcao},
        )
    ).scalar()
    if v is None:
        v = (
            await db.execute(
                text(
                    "SELECT piso_salarial FROM cct_cargos WHERE upper(cargo_nome) = upper(:c) "
                    "AND coalesce(is_active, true) ORDER BY created_at LIMIT 1"
                ),
                {"c": funcao},
            )
        ).scalar()
    return float(v) if v is not None else None


# ───────────────────────────────── telas ─────────────────────────────────
def _acao_recrutar(post_id: str, posto: str) -> dict:
    return {
        "title": f"Abrir vaga de recrutamento — {posto}",
        "endpoint": f"{_END}vaga-recrutar?post_id={post_id}",
        "method": "POST",
        "btnLabel": "Recrutar",
        "submitLabel": "Abrir vaga",
        "btnStyle": "outline",
        "okMsg": "Vaga aberta no recrutamento.",
        "showResult": True,
        "fields": [
            {
                "key": "quantidade",
                "label": "Quantidade (vazio = o descoberto de hoje)",
                "type": "number",
                "span": "span 2",
            },
            {"key": "salario_base", "label": "Salário base (vazio = da vaga ou piso da CCT)", "type": "number"},
            {"key": "deadline", "label": "Prazo para preencher (opcional)", "type": "date"},
            {
                "key": "motivo",
                "label": "Motivo",
                "type": "select",
                "options": [
                    {"value": "aumento", "label": "Aumento de quadro"},
                    {"value": "substituicao", "label": "Substituição"},
                ],
            },
        ],
    }


def _doc_etiqueta(sid: str, nome: str):
    from modules.operacional.controllers.redesign_data_controller import doc

    return doc(
        "Etiqueta QR",
        f"/api/v1/redesign/setores/{sid}/etiqueta/pdf",
        fmt="pdf",
        filename=f"etiqueta-qr-{(nome or 'setor')[:24].strip().replace(' ', '-').lower()}.pdf",
    )


async def telas(db, out: dict) -> None:
    """Pendura a ação «Recrutar» nas linhas que já existem (T3 e frente 04 montaram), o documento
    «Etiqueta QR» nas linhas de setores (U4) e monta `setor-etiqueta`. Nenhuma tabela nova."""
    from modules.operacional.controllers.redesign_data_controller import t

    try:
        await _ensure(db)
    except Exception as exc:  # noqa: BLE001 — visível, nunca calado
        await db.rollback()
        logger.error("dgx v2: _ensure falhou: %s", exc, exc_info=True)
        return

    # ── 1. «Recrutar» em Vagas do contrato (T3) e no grid (frente 04) ──
    for tid, chave in (("vagas-do-contrato", "vagas"), ("grid-real-contratual", "postos")):
        try:
            scr = out.get(tid) or {}
            itens = (scr.get("_meta") or {}).get(chave) or []
            linhas = scr.get("rows") or []
            if not itens or len(linhas) != len(itens):
                continue
            for linha, item in zip(linhas, itens, strict=True):
                pid = item.get("post_id")
                if not pid:
                    continue
                linha.setdefault("actions", []).append(_acao_recrutar(pid, item.get("posto") or "posto"))
            scr["sub"] = (scr.get("sub") or "") + " · Recrutar abre a vaga no RH (V2)"
        except Exception as exc:  # noqa: BLE001
            logger.warning("dgx v2: ação Recrutar não pendurada em %s: %s", tid, exc)

    # ── 2. Etiqueta QR por linha em Setores (U4) + tela com o endereço público ──
    try:
        setores = (await db.execute(text(SQL_SETORES_QR))).fetchall()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("dgx v2: setores não lidos: %s", exc, exc_info=True)
        return

    scr = out.get("setores") or {}
    linhas = scr.get("rows") or []
    if linhas and len(linhas) == len(setores):  # mesma ordem do SQL_SETORES do U4
        for linha, s in zip(linhas, setores, strict=True):
            linha["docs"] = [_doc_etiqueta(s[0], s[1])]
        scr["sub"] = (scr.get("sub") or "") + " · Etiqueta QR por linha: cola no setor e quem está lá abre chamado sem login (V2)"

    ativos = [s for s in setores if s[4]]
    out["setor-etiqueta"] = {
        "title": "Etiquetas QR dos setores",
        "cta": "—",
        "type": "table",
        "sub": (
            f"{len(ativos)} setor(es) ativo(s) · cada etiqueta leva ao endereço público do setor, sem login "
            f"({PUBLICO}/<token>) · quem abrir informa nome, telefone e o que houve; o chamado nasce com canal «qr» "
            "e o responsável do setor é avisado na hora (mesmo serviço da F8) · o token é gerado UMA vez, "
            "nunca reemitido: etiqueta impressa não vira lixo"
        ),
        "searchHint": "Buscar setor, cliente…",
        "grid": "1.4fr 1.4fr 2.6fr 0.9fr 0.8fr",
        "cols": ["Setor", "Cliente", "Endereço do QR", "Chamados por QR", "Situação"],
        "rows": [
            {
                "cells": [
                    t(s[1], 600, _ND),
                    t(s[3]),
                    t(f"{BASE_URL}{PUBLICO}/{s[2]}" if s[2] else "sem token"),
                    t(str(s[5]), 600),
                    t("ativo" if s[4] else "inativo"),
                ],
                "docs": [_doc_etiqueta(s[0], s[1])],
            }
            for s in setores
        ]
        or [{"cells": [t("Nenhum setor cadastrado — crie em «Novo setor»", 500)] + [t("—")] * 4}],
    }


# ───────────────────────────────── rotas ─────────────────────────────────
router = APIRouter()


def _p(payload: dict) -> dict:
    return {k: (str(v).strip() if v is not None else "") for k, v in payload.items()}


def _num(v, default=None):
    try:
        return float(str(v).replace(".", "").replace(",", ".")) if ("," in str(v)) else float(v)
    except (TypeError, ValueError):
        return default


def _uuid(v: str, rotulo: str) -> str:
    v = (v or "").strip()
    if len(v) != 36:
        raise HTTPException(status_code=400, detail=f"{rotulo} inválido — recarregue a tela e tente de novo.")
    return v


def _brl(v) -> str:
    return f"R$ {float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


@router.post("/action/vaga-recrutar")
async def rd_vaga_recrutar(
    current_user: CurrentActiveUser, post_id: str, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    """Abre a vaga do RH a partir da vaga do contrato (posto). Idempotente: se já existe vaga
    ABERTA para o posto, aponta a que existe e NÃO cria a segunda."""
    p = _p(payload)
    post_id = _uuid(post_id, "Posto")
    await _ensure(db)
    r = (await db.execute(text(SQL_POSTO_DA_VAGA), {"p": post_id})).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Posto não encontrado ou inativo.")
    (pid, nome, funcao, escala, contratado, salario, contract_id, _cli, cliente, local, alocado, condominio) = r

    ja = (
        await db.execute(
            text(
                "SELECT id::text, coalesce(code, ''), title, coalesce(vacancies, 1) FROM job_positions "
                "WHERE post_id = CAST(:p AS uuid) AND status = 'aberta' AND coalesce(is_deleted, false) = false LIMIT 1"
            ),
            {"p": post_id},
        )
    ).fetchone()
    if ja:
        return {
            "ok": True,
            "ja_existia": True,
            "vaga_id": ja[0],
            "post_id": pid,
            "message": f"Já existe vaga ABERTA para o posto {nome}: «{ja[2]}» ({ja[3]} posição(ões)). "
            "Nada foi criado — acompanhe essa em Recrutamento › Vagas.",
        }

    descoberto = max(int(contratado or 0) - int(alocado or 0), 0)
    qtd = int(_num(p.get("quantidade"), 0) or 0) or descoberto
    if qtd < 1:
        raise HTTPException(
            status_code=422,
            detail=f"O posto {nome} está com o efetivo completo ({alocado}/{contratado}) — "
            "informe a quantidade se for aumento de quadro.",
        )
    sal = _num(p.get("salario_base")) if p.get("salario_base") else None
    if sal is None:
        sal = float(salario) if salario is not None else await piso_cct(db, funcao)
    if sal is not None and sal < 0:
        raise HTTPException(status_code=400, detail="Salário base não pode ser negativo.")
    motivo = "substituicao" if p.get("motivo") == "substituicao" else "aumento"
    titulo = (" ".join(x for x in (funcao or nome, escala) if x).strip() or nome)[:200]
    cidade, uf = ((local.split("/") + [""])[:2]) if local else ("", "")

    vaga = (
        await db.execute(
            text(
                "INSERT INTO job_positions (title, description, department, position_type, status, vacancies, "
                " salary_min, salary_max, show_salary, city, state, condominio_id, post_id, contract_id, deadline, "
                " is_active, is_deleted, published_at, created_at) "
                "VALUES (:t, :d, 'Operacional', 'clt', 'aberta', :q, :s, :s, false, nullif(:city, ''), nullif(:uf, ''), "
                " CAST(:cond AS uuid), CAST(:p AS uuid), CAST(:ct AS uuid), CAST(nullif(:dl, '') AS date), "
                " true, false, now(), now()) RETURNING id::text"
            ),
            {
                "t": titulo,
                "d": f"Vaga do posto {nome}"
                + (f" — {cliente}" if cliente else "")
                + f". Escala {escala or '—'}. "
                + f"Motivo: {'substituição' if motivo == 'substituicao' else 'aumento de quadro'}. "
                + f"Efetivo do posto na abertura: {alocado}/{contratado} (descoberto {descoberto}).",
                "q": qtd,
                "s": sal,
                "city": cidade,
                "uf": uf[:2],
                "cond": condominio,
                "p": post_id,
                "ct": contract_id,
                "dl": p.get("deadline", ""),
            },
        )
    ).scalar()
    await db.commit()
    return {
        "ok": True,
        "ja_existia": False,
        "vaga_id": vaga,
        "post_id": pid,
        "message": f"Vaga «{titulo}» aberta com {qtd} posição(ões) para o posto {nome}"
        + (f" ({cliente})" if cliente else "")
        + (f", salário base {_brl(sal)}" if sal else ", SEM salário base (nem na vaga, nem na CCT)")
        + ". Está em Recrutamento › Vagas; o candidato aprovado na esteira cai alocado neste posto.",
    }


# ───────────────────────────── etiqueta QR (PDF) ─────────────────────────────
@router.get("/setores/{setor_id}/etiqueta/pdf", summary="Etiqueta QR do setor — abre chamado sem login")
async def rd_setor_etiqueta_pdf(
    setor_id: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)
) -> Response:
    await _ensure(db)
    r = (
        await db.execute(
            text(
                "SELECT s.nome, s.token, coalesce(cl.name, ''), coalesce(s.responsavel, ''), coalesce(k.contract_number, '') "
                "FROM op_setores s LEFT JOIN clients cl ON cl.id = s.client_id LEFT JOIN contracts k ON k.id = s.contract_id "
                "WHERE s.id = CAST(:i AS uuid)"
            ),
            {"i": _uuid(setor_id, "Setor")},
        )
    ).fetchone()
    if not r or not r[1]:
        raise HTTPException(status_code=404, detail="Setor não encontrado.")
    pdf = montar_etiqueta_pdf(r[0], f"{BASE_URL}{PUBLICO}/{r[1]}", cliente=r[2], responsavel=r[3], contrato=r[4])
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="etiqueta-qr-{setor_id[:8]}.pdf"'},
    )


def montar_etiqueta_pdf(setor: str, url: str, cliente: str = "", responsavel: str = "", contrato: str = "") -> bytes:
    """Etiqueta A4 no timbrado padrão-ouro (`pdf_branding`), com o QR do endereço público.
    QR pelo `reportlab.graphics.barcode.qr` — a imagem já traz o gerador; nenhuma dependência nova
    (o pacote `qrcode` NÃO está instalado, conferido no container em 24/09/2026)."""
    import io

    from reportlab.graphics import renderPDF
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.pdfgen import canvas as _canvas

    from modules.crm.services.pdf_branding import AZUL_ESCURO, AZUL_MEDIO, FONTE, FONTE_B, marca_canvas, rodape_canvas

    buf = io.BytesIO()
    c = _canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Etiqueta QR — {setor}")
    w, _h = A4
    y = marca_canvas(c, titulo="Abertura de chamado", pagesize=A4, subtitulo=cliente or None)

    c.setFillColor(AZUL_ESCURO)
    c.setFont(FONTE_B, 24)
    c.drawCentredString(w / 2, y - 6 * mm, setor[:44])
    c.setFillColor(AZUL_MEDIO)
    c.setFont(FONTE, 11)
    c.drawCentredString(w / 2, y - 14 * mm, "Aponte a câmera do celular para o código e descreva o problema.")
    c.drawCentredString(w / 2, y - 20 * mm, "Não precisa de login nem de aplicativo.")

    lado = 82 * mm
    topo = y - 30 * mm
    wid = qr.QrCodeWidget(url, barLevel="M")
    x1, y1, x2, y2 = wid.getBounds()
    d = Drawing(lado, lado, transform=[lado / (x2 - x1), 0, 0, lado / (y2 - y1), 0, 0])
    d.add(wid)
    renderPDF.draw(d, c, (w - lado) / 2, topo - lado)

    c.setFillColor(AZUL_MEDIO)
    c.setFont(FONTE, 8)
    c.drawCentredString(w / 2, topo - lado - 8 * mm, url)
    rodape = " · ".join(
        x for x in (cliente, f"Contrato {contrato}" if contrato else "", f"Responsável: {responsavel}" if responsavel else "") if x
    )
    if rodape:
        c.setFont(FONTE, 9)
        c.drawCentredString(w / 2, topo - lado - 16 * mm, rodape[:120])
    rodape_canvas(c, pagesize=A4)
    c.showPage()
    c.save()
    return buf.getvalue()


# ───────────────────────── página pública por token ─────────────────────────
async def _setor_por_token(db, token: str):
    return (await db.execute(text(SQL_SETOR_POR_TOKEN), {"t": (token or "")[:48]})).first()


def _pagina(titulo: str, corpo: str, status: int = 200) -> HTMLResponse:
    from ._frente_10 import _CSS  # mesma folha da avaliação pública (frente 10) — não se copia CSS

    return HTMLResponse(
        f"<!doctype html><html lang='pt-BR'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{html.escape(titulo)}</title><style>{_CSS}</style></head>"
        f"<body><div class='c'>{corpo}</div></body></html>",
        status_code=status,
    )


@router.get("/publico/chamado/{token}", response_class=HTMLResponse)
@limiter.limit("30/minute")
async def chamado_publico(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    """Página pública do QR do setor (celular, sem login: o token É o acesso). Token inválido ou
    setor inativo = 404 — nunca um formulário que grava em lugar nenhum."""
    s = await _setor_por_token(db, token)
    if not s:
        return _pagina(
            "Chamado",
            "<h1>Etiqueta inválida</h1><p class='s'>Este código não corresponde a nenhum setor ativo. "
            "Procure a administração.</p>",
            status=404,
        )
    tk = html.escape(token)
    corpo = (
        f"<h1>Abrir chamado</h1><p class='s'>{html.escape(s[1])} · {html.escape(s[2])}</p>"
        f"<form method='post' action='{PUBLICO}/{tk}'>"
        "<label>O que está acontecendo?*</label>"
        "<textarea name='descricao' rows='5' maxlength='1000' minlength='10' required "
        "placeholder='Descreva o problema com pelo menos 10 caracteres'></textarea>"
        "<label>Seu nome*</label><input type='text' name='nome' required maxlength='120'>"
        # type=text (não tel): a folha da frente 10 só estiliza text/select/textarea
        "<label>Telefone para retorno*</label>"
        "<input type='text' inputmode='tel' name='telefone' required maxlength='30'>"
        "<label>Urgência</label><select name='prioridade'>"
        "<option value='normal'>Normal</option><option value='alta'>Alta</option>"
        "<option value='urgente'>Urgente</option><option value='baixa'>Baixa</option></select>"
        "<button type='submit'>Abrir chamado</button></form>"
    )
    return _pagina("Abrir chamado", corpo)


@router.post("/publico/chamado/{token}", response_class=HTMLResponse)
@limiter.limit("10/minute")
async def chamado_publico_abrir(request: Request, token: str, db: AsyncSession = Depends(get_db)):
    """Abre o chamado pelo MESMO serviço da F8 (`abrir_chamado`) — que valida o setor e avisa o
    responsável. Canal `qr`, aberto por `cliente`."""
    from modules.operacional.services import supervisao_service as sv

    s = await _setor_por_token(db, token)
    if not s:
        return _pagina("Chamado", "<h1>Etiqueta inválida</h1>", status=404)
    form = await request.form()
    descricao = str(form.get("descricao") or "").strip()
    nome = str(form.get("nome") or "").strip()[:120]
    telefone = str(form.get("telefone") or "").strip()[:30]
    if len(descricao) < 10 or not nome or not telefone:
        return _pagina(
            "Chamado",
            "<h1>Faltou informação</h1><p class='s'>Descreva o problema (mín. 10 caracteres) e informe "
            f"nome e telefone.</p><p class='s'><a href='{PUBLICO}/{html.escape(token)}'>Voltar</a></p>",
            status=422,
        )
    prioridade = str(form.get("prioridade") or "normal")
    if prioridade not in sv.PRIORIDADES:
        prioridade = "normal"
    try:
        r = await sv.abrir_chamado(
            db,
            descricao=descricao,
            aberto_por="cliente",
            solicitante_nome=nome,
            solicitante_contato=telefone,
            canal="qr",
            categoria="equipamento",
            prioridade=prioridade,
            setor_id=s[0],
        )
    except sv.SupervisaoErro as exc:
        await db.rollback()
        return _pagina("Chamado", f"<h1>Não deu para abrir</h1><p class='s'>{html.escape(str(exc))}</p>", status=422)
    return _pagina(
        "Chamado aberto",
        f"<div class='ok'>✅ Chamado #{r['numero']} aberto.</div>"
        f"<p class='s' style='text-align:center'>Setor {html.escape(s[1])} · prazo de atendimento "
        f"{r['sla_min'] // 60} h. O responsável do setor foi avisado.</p>",
    )
