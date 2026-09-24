"""DGX V4 — DP: fila de falhas de importação, exportar/imprimir colaboradores com contadores
por status, e importar apontamentos da folha em CSV (24/09/2026).

Prefixo `_` = o discovery pula; `departamento_pessoal.py` importa `router` e chama
`telas(db, out)` no FIM do build() (2 + 1 linhas, `# dgx v4`). Abas no FIM dos grupos
`g-visao` (falhas) e `g-folha` (importar apontamentos), em `_dp_grupos.py`.

Regra mora fora daqui:
  · `people_management/hr/services/importacao_falhas.py`     — a fila (DDL, idempotência, ações);
  · `people_management/hr/services/colaboradores_export.py`  — contadores e export (réguas importadas);
  · `people_management/folha/services/apontamentos_csv.py`   — o CSV de apontamentos (paralelo cego).

Esta frente NÃO cria tela de export: o botão nasce na tela que já existe (`funcionarios`), como
`doc`, que é onde a Pyetra já está quando precisa da lista. Tela nova para baixar um arquivo é
uma porta a mais para a mesma sala.
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Response, UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.database.session import get_sync_db_dependency
from modules.operacional.controllers.redesign_data_controller import b, doc, t
from modules.people_management.hr.services import colaboradores_export as expo
from modules.people_management.hr.services import importacao_falhas as falhas

from ._dgx_f7_ponto import _falhou, _fd, _require_dp

logger = logging.getLogger(__name__)
_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"

ABAS_VISAO = [("importacao-falhas", "Falhas de importação")]
ABAS_FOLHA = [("folha-apontamentos-importar", "Importar apontamentos (CSV)")]

_ROTULO_ORIGEM = {
    "solides": "Sólides",
    "portte": "Portte (folha analítica)",
    "planilha": "Planilha / CSV",
    "afd": "Relógio (AFD)",
    "outro": "Outro",
}
_ROTULO_STATUS = {"nao_resolvido": "Não resolvido", "resolvido_manual": "Resolvido (manual)", "ignorado": "Ignorado"}


def _e_admin(user) -> bool:
    """CPF completo no Excel só para admin (LGPD). Mesma régua de `module_scope.user_modules`."""
    role = (getattr(user, "role", None) or "").lower()
    perms = getattr(user, "permissions", None) or []
    return role == "admin" or "*" in perms or "all" in perms


# ───────────────────────── 1. fila de falhas de importação ─────────────────────────
async def _tela_falhas(db: AsyncSession) -> dict:
    await falhas._ensure(db)
    rows = (
        await db.execute(
            text(
                "SELECT f.id, f.origem, f.executada_em AT TIME ZONE 'America/Manaus', f.identificador_origem, "
                "coalesce(f.nome,'—'), coalesce(f.matricula,'—'), coalesce(f.cpf,'—'), f.motivo, f.status, "
                "coalesce(f.resolvido_por,'—'), coalesce(e.nome,'') "
                "FROM dp_importacao_falhas f LEFT JOIN employees e ON e.id = f.employee_id "
                "ORDER BY (f.status = 'nao_resolvido') DESC, f.executada_em DESC, f.id DESC LIMIT 400"
            )
        )
    ).fetchall()
    por_status = {}
    for r in rows:
        por_status[r[8]] = por_status.get(r[8], 0) + 1
    abertas = por_status.get("nao_resolvido", 0)
    pessoas = (
        await db.execute(
            text(
                "SELECT CAST(id AS text), nome || ' — ' || coalesce(matricula,'sem matrícula') FROM employees "
                "WHERE lower(coalesce(status,'')) <> 'demitido' ORDER BY nome LIMIT 500"
            )
        )
    ).fetchall()
    opts_pessoa = [{"value": "", "label": "— resolver sem ligar (incluí manualmente) —"}] + [
        {"value": r[0], "label": r[1]} for r in pessoas
    ]

    def linha(r) -> dict:
        fid, origem, quando, ident, nome, mat, cpf, motivo, status, quem, lig = r
        acoes = []
        if status == "nao_resolvido":
            acoes = [
                {
                    "title": f"Resolver — {nome if nome != '—' else ident}",
                    "endpoint": _ACT + "importacao-falha-resolver",
                    "method": "POST",
                    "btnLabel": "Resolver",
                    "submitLabel": "Confirmar",
                    "btnStyle": "primary",
                    "okMsg": "Falha resolvida. Recarregue a tela.",
                    "fields": [
                        {"key": "id", "type": "hidden", "label": "id", "value": str(fid)},
                        {
                            "key": "employee_id",
                            "label": "Ligar a qual colaborador?",
                            "type": "select",
                            "span": "span 2",
                            "options": opts_pessoa,
                        },
                    ],
                },
                {
                    "title": f"Ignorar — {nome if nome != '—' else ident}",
                    "endpoint": _ACT + "importacao-falha-ignorar",
                    "method": "POST",
                    "btnLabel": "Ignorar",
                    "submitLabel": "Ignorar",
                    "btnStyle": "outline",
                    "okMsg": "Falha ignorada. Recarregue a tela.",
                    "fields": [
                        {"key": "id", "type": "hidden", "label": "id", "value": str(fid)},
                        {
                            "key": "motivo",
                            "label": "Por que ignorar?* (mín. 5 caracteres)",
                            "type": "textarea",
                            "span": "span 2",
                            "ph": "ex.: linha de teste do contador; pessoa nunca foi contratada",
                        },
                    ],
                },
            ]
        return {
            "cells": [
                t(_fd(quando, "%d/%m/%Y %H:%M")),
                t(_ROTULO_ORIGEM.get(origem, origem), 600, _ND),
                t(ident[:60] or "—"),
                t(nome, 600, _ND),
                t(mat),
                t(cpf),
                t(motivo[:160]),
                b(
                    _ROTULO_STATUS.get(status, status),
                    {"nao_resolvido": "bad", "resolvido_manual": "ok", "ignorado": "mut"}.get(status, "mut"),
                ),
                t(f"{quem}{' → ' + lig if lig else ''}"),
            ],
            "actions": acoes,
            "filtros": {"Origem": _ROTULO_ORIGEM.get(origem, origem), "Situação": _ROTULO_STATUS.get(status, status)},
        }

    sub = (
        "Toda linha que um importador do DP recusou vira uma pendência COM DONO aqui — antes o erro "
        "morria no JSON da resposta e sumia quando alguém fechava a aba. Origens: Sólides (férias), "
        "Portte (folha analítica), planilha (cadastro e apontamentos) e relógio (AFD). "
        "Rerodar a mesma importação não duplica a fila (chave origem + identificador + motivo). "
        + (
            f"⚠ {abertas} pendência(s) não resolvida(s)."
            if abertas
            else "Nenhuma pendência aberta (recontado agora, não vazio por falta de tabela)."
        )
    )
    return {
        "title": "Falhas de importação",
        "sub": sub,
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar nome, matrícula, motivo…",
        "cols": [
            "Quando",
            "Origem",
            "Identificador",
            "Nome",
            "Matrícula",
            "CPF",
            "Motivo",
            "Situação",
            "Quem resolveu",
        ],
        "grid": "1.1fr 1.2fr 1.3fr 1.6fr 0.8fr 1fr 2.6fr 1fr 1.4fr",
        "rows": [linha(r) for r in rows],
    }


# ───────────────────────── 2. exportar / imprimir colaboradores ─────────────────────────
def _tela_funcionarios(out: dict) -> dict | None:
    """A tela real, onde quer que ela esteja. Depois de `montar_grupos`, `out["funcionarios"]`
    é o STUB `moved()` (deep-link antigo) e a tela de verdade vive na aba do `g-visao` — decorar
    o stub não muda nada na tela e não avisa ninguém (medido em 24/09, primeiro tiro desta frente)."""
    for tb in (out.get("g-visao") or {}).get("tabs") or []:
        if tb.get("id") == "funcionarios" and isinstance(tb.get("screen"), dict):
            return tb["screen"]
    tela = out.get("funcionarios")
    return tela if isinstance(tela, dict) and tela.get("type") != "redirect" else None


async def _enfeitar_funcionarios(db: AsyncSession, out: dict) -> None:
    """Acrescenta contadores no cabeçalho e os botões Exportar/Imprimir na tela `funcionarios`
    que JÁ existe (aditivo: se ela não estiver montada nesta base, não faz nada)."""
    tela = _tela_funcionarios(out)
    if tela is None:
        logger.warning("dgx v4: tela `funcionarios` não encontrada — export e contadores não foram acoplados")
        return
    cont = await expo.contadores(db)
    faixa = " · ".join(f"{c['label']}: {c['valor']}" + ("*" if c["subconjunto_de_ativo"] else "") for c in cont)
    # Por que «Ativo» difere do «N ativos» que esta tela já mostrava: aquele conta `status='ativo'`
    # e inclui os cadastros de HOMOLOGAÇÃO. Dois números com a mesma palavra, sem explicação, é
    # como se repete em reunião um número que ninguém reconferiu.
    homolog = (
        await db.execute(text("SELECT count(*) FROM employees WHERE coalesce(is_homologacao,false)"))
    ).scalar() or 0
    tela["sub"] = (
        f"{faixa}  (* subconjunto de Ativo) — régua única: `identidade.SEM_VINCULO`, `sst_afastamentos`, "
        "férias aprovadas de hoje e a ausência do mapa de ponto. «Ativo» = vínculo vivo"
        + (f", fora os {homolog} cadastros de homologação. " if homolog else ". ")
        + str(tela.get("sub") or "")
    ).strip()
    tela["docs"] = [
        doc("Exportar (Excel)", "/api/v1/redesign/colaboradores/export?formato=xlsx", fmt="xlsx"),
        doc("Exportar (CSV)", "/api/v1/redesign/colaboradores/export?formato=csv", fmt="csv"),
        doc("Imprimir (PDF)", "/api/v1/redesign/colaboradores/lista/pdf", fmt="pdf"),
        doc("Excel — quadro inteiro", "/api/v1/redesign/colaboradores/export?formato=xlsx&status=todos", fmt="xlsx"),
    ] + list(tela.get("docs") or [])


# ───────────────────────── 3. importar apontamentos (CSV) ─────────────────────────
async def _tela_apontamentos_csv(db: AsyncSession) -> dict:
    comp = (
        await db.execute(
            text(
                "SELECT reference_year, reference_month, count(*) FROM hr_payslips WHERE status::text = 'draft' "
                "GROUP BY 1,2 ORDER BY 1 DESC, 2 DESC LIMIT 6"
            )
        )
    ).fetchall()
    n_rub = (await db.execute(text("SELECT count(*) FROM rubricas_folha WHERE ativo"))).scalar() or 0
    abertas = "; ".join(f"{m:02d}/{a} = {n} rascunho(s)" for a, m, n in comp) or "nenhuma"
    return {
        "title": "Importar apontamentos da folha (CSV)",
        "sub": (
            "CSV com uma linha por lançamento: `matricula;rubrica;referencia;valor;competencia` "
            "(cabeçalho opcional; aceita `,` e decimal com vírgula). Valida matrícula com vínculo ativo, "
            f"rubrica ATIVA ({n_rub} hoje em `rubricas_folha`) e competência SEM folha publicada. "
            "Cada linha válida vira um APONTAMENTO no holerite rascunho — pelo mesmo caminho de «Apontar» e "
            "dos eventos coletivos. NÃO muda valor calculado: quem fecha a folha lê o apontamento e decide. "
            "Linha recusada vai para «Falhas de importação» (origem planilha). "
            f"Competências com rascunho: {abertas}."
        ),
        "cta": "Importar",
        "type": "form",
        "submit": {
            "endpoint": _ACT + "folha-apontamentos-importar",
            "method": "POST",
            "multipart": True,
            "showResult": True,
            "okMsg": "Planilha processada — veja o resultado.",
            "confirm": "As linhas válidas viram apontamento no holerite rascunho (salvo em «Só validar»). Confirma?",
        },
        "fields": [
            {
                "key": "simular",
                "label": "Modo",
                "type": "select",
                "span": "span 2",
                "options": [
                    {"value": "true", "label": "Só validar (prévia — não grava nem na fila de falhas)"},
                    {"value": "false", "label": "Importar (grava o apontamento)"},
                ],
            },
            {
                "key": "arquivo",
                "label": "Planilha CSV*",
                "type": "file",
                "accept": ".csv,.txt,text/csv",
                "span": "span 2",
            },
        ],
    }


# ───────────────────────── montagem ─────────────────────────
async def telas(db: AsyncSession, out: dict | None = None) -> dict:
    mine: dict = {}
    montagens = [
        ("importacao-falhas", "Falhas de importação", lambda: _tela_falhas(db)),
        ("folha-apontamentos-importar", "Importar apontamentos (CSV)", lambda: _tela_apontamentos_csv(db)),
    ]
    for tid, titulo, fn in montagens:
        try:
            r = fn()
            mine[tid] = await r if hasattr(r, "__await__") else r
        except Exception as exc:  # noqa: BLE001 — visível na tela, nunca calado
            await db.rollback()
            mine[tid] = _falhou(titulo, exc)
    try:
        await _enfeitar_funcionarios(db, out or {})
    except Exception as exc:  # noqa: BLE001 — export é acréscimo; não pode derrubar a tela base
        await db.rollback()
        logger.error("dgx v4: contadores/export em funcionarios falharam: %s", exc, exc_info=True)

    from modules.operacional.controllers.redesign_data_controller import moved

    for gid, abas in (("g-visao", ABAS_VISAO), ("g-folha", ABAS_FOLHA)):
        grupo = (out or {}).get(gid)
        if not (isinstance(grupo, dict) and isinstance(grupo.get("tabs"), list)):
            continue
        ja = {tb.get("id") for tb in grupo["tabs"]}
        for tid, lbl in abas:
            if tid in mine and tid not in ja:
                grupo["tabs"].append({"id": tid, "label": lbl, "screen": mine[tid]})
                mine[tid] = moved(gid, tid)
    return mine


# ───────────────────────── ações e documentos ─────────────────────────
router = APIRouter()


def _quem(current_user) -> str:
    return str(
        getattr(current_user, "name", None) or getattr(current_user, "email", None) or getattr(current_user, "id", "")
    )[:120]


@router.post("/action/importacao-falha-resolver", dependencies=[Depends(_require_dp)])
async def rd_falha_resolver(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        r = await falhas.resolver(
            db, int(payload.get("id") or 0), _quem(current_user), str(payload.get("employee_id") or "").strip() or None
        )
    except (ValueError, TypeError) as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ligado = " e ligada ao colaborador escolhido" if r["employee_id"] else " (incluído manualmente)"
    return {"ok": True, "message": f"Falha #{r['id']} ({r['origem']}) resolvida{ligado}.", "resultado": r}


@router.post("/action/importacao-falha-ignorar", dependencies=[Depends(_require_dp)])
async def rd_falha_ignorar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    try:
        r = await falhas.ignorar(db, int(payload.get("id") or 0), str(payload.get("motivo") or ""), _quem(current_user))
    except (ValueError, TypeError) as exc:
        await db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "message": f"Falha #{r['id']} ignorada: {r['motivo'][:80]}", "resultado": r}


@router.get("/colaboradores/export", summary="Colaboradores em Excel/CSV (DGX V4)")
async def rd_colaboradores_export(
    current_user: CurrentActiveUser,
    formato: str = Query("xlsx", pattern="^(xlsx|csv)$"),
    status: str | None = Query(None),
    condominio: str | None = Query(None),
    funcao: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    _require_dp(current_user)
    admin = _e_admin(current_user)
    dados = await expo.linhas(db, status=status, condominio=condominio, funcao=funcao, admin=admin)
    hoje = date.today().isoformat()
    if formato == "csv":
        return Response(
            content=expo.para_csv(dados),
            media_type="text/csv; charset=iso-8859-1",
            headers={"Content-Disposition": f'attachment; filename="colaboradores-{hoje}.csv"'},
        )
    return Response(
        content=expo.para_xlsx(dados),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="colaboradores-{hoje}.xlsx"'},
    )


@router.get("/colaboradores/lista/pdf", summary="Relação de colaboradores (PDF timbrado, DGX V4)")
async def rd_colaboradores_pdf(
    current_user: CurrentActiveUser,
    status: str | None = Query(None),
    condominio: str | None = Query(None),
    funcao: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    _require_dp(current_user)
    dados = await expo.linhas(db, status=status, condominio=condominio, funcao=funcao, admin=False)
    filtros = " · ".join(
        x
        for x in (
            f"status: {status or 'com vínculo'}",
            condominio and f"cliente: {condominio}",
            funcao and f"função: {funcao}",
        )
        if x
    )
    pdf = expo.para_pdf(dados, subtitulo=f"{len(dados)} colaborador(es) — {filtros}", resumo=await expo.contadores(db))
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="colaboradores-{date.today().isoformat()}.pdf"'},
    )


@router.post("/action/folha-apontamentos-importar", dependencies=[Depends(_require_dp)])
async def rd_apontamentos_importar(
    current_user: CurrentActiveUser,
    arquivo: UploadFile = File(...),
    simular: str = Form("true"),
    sdb=Depends(get_sync_db_dependency),
) -> dict:
    from modules.people_management.folha.services import apontamentos_csv

    raw = await arquivo.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Arquivo vazio.")
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo maior que 5 MB.")
    try:
        conteudo = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        conteudo = raw.decode("latin-1")
    r = await apontamentos_csv.importar(
        sdb,
        conteudo,
        _quem(current_user),
        arquivo=arquivo.filename or "",
        simular=str(simular).lower() == "true",
        current_user=current_user,
    )
    modo = "SIMULAÇÃO — nada gravado" if r["simulacao"] else "gravado"
    return {
        "ok": True,
        "message": f"{modo}: {r['linhas']} linha(s) — {r['validas']} válida(s), {r['recusadas']} recusada(s) "
        f"(na fila de falhas), {r['apontamentos']} apontamento(s) em {r['holerites_alvo']} holerite(s).",
        "resultado": r,
    }
