"""DGX T5 — o que faltava depois das frentes F4/F9/F10/F12, medido no trial em 24/09/2026
(lista em docs/dgx/lacunas/suprimentos_frotas_sesmt_config.md):

  1. LOG DO SISTEMA como tela. `crm_audit_log` (36.228 linhas: quem, quando, método, caminho,
     status, IP, tela aberta) só tinha porta pelo tool `consultar_auditoria`; a tela
     `seguranca?t=auditoria` lia `turnover_audit_logs` (5 linhas). Aqui ela passa a ler a trilha
     viva, com filtros por método e usuário, e ganha «Telas abertas» (quem abriu o quê, 7 dias).
  2. SOLICITAÇÃO DE MATERIAIS por posto (DGX: `/SolicitacoesMaterial`). Pede → aprova/rejeita →
     atende. Atender baixa o estoque pelo MESMO caminho da F9 (`EstoqueRealService.registrar_saida`,
     COGS no razão) — nada de segundo jeito de mexer em saldo. Parcial quando entrega < pedido.
  3. EXAMES POR ASO com data e validade (DGX: ASO → Exames → «Válido até»). A F12 guardou só os
     ids (`gp_asos.tipos_exame_ids`); sem data não há «exame vencido» — audiometria de 6 meses
     vencia escondida atrás do ASO anual. `valido_ate` = data + `periodicidade_meses` do tipo.
  4. ACESSOS TEMPORÁRIOS (DGX: `/view/acessosTemporarios`). Usuário com validade: papel leitura
     ou operacional, módulos (nunca financeiro — mesma regra de users.py), expira sozinho. A
     varredura roda no gate do redesign (`redesign_data`) e aqui; o oráculo acusa expirado ativo.

Nada em core/auth foi tocado: o acesso temporário é um `users` comum (role viewer/operator +
module:X) — as travas existentes (`require_permission`, `_slug_allowed`, `is_active`) valem
inteiras. Prefixo `_` = o discovery pula. DDL idempotente em `_ensure`.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db

#: ANTES do import do data_controller (o ciclo de import fecha com o router pronto).
router = APIRouter()

_TZ = ZoneInfo("America/Manaus")
_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_ICO = "M3 3v18h18"

MENU_SEG = [{"id": "auditoria-telas", "label": "Auditoria — telas abertas", "icon": "M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"}]
MENU_SUP = [
    {"id": "solicitacoes-material", "label": "Solicitações de material", "icon": _ICO, "grupo": "Materiais & estoque"},
    {"id": "solicitacao-material-nova", "label": "Nova solicitação de material", "icon": "M12 5v14M5 12h14", "grupo": "Materiais & estoque"},
]
MENU_SST = [
    {"id": "aso-exames-vencendo", "label": "Exames por colaborador", "icon": _ICO},
    {"id": "aso-exame-novo", "label": "Registrar exame", "icon": "M12 5v14M5 12h14"},
]
MENU_CFG = [
    {"id": "acessos-temporarios", "label": "Acessos temporários", "icon": "M5 11h14v10H5zM8 11V7a4 4 0 0 1 8 0v4", "grupo": "Acessos"},
    {"id": "acesso-temporario-novo", "label": "Novo acesso temporário", "icon": "M12 5v14M5 12h14", "grupo": "Acessos"},
]

from modules.operacional.controllers.redesign_data_controller import _helpers, b, brl, t  # noqa: E402

from . import _frente_10 as f10  # noqa: E402  # _dec/_quem — módulo inteiro para não fechar ciclo

#: papéis do acesso temporário → role de `users`. Módulos vêm de `core.auth.module_scope`.
PAPEIS = {"leitura": "viewer", "operacional": "operator"}
MODULO_PROIBIDO = {"financeiro"}  # users.py: financeiro é exclusivo do CEO — a regra é a mesma aqui

_DDL = [
    """CREATE TABLE IF NOT EXISTS sup_solicitacoes_material (
        id serial PRIMARY KEY,
        numero varchar(20) NOT NULL UNIQUE,
        post_id uuid,
        solicitante varchar(120) NOT NULL,
        tipo varchar(10) NOT NULL DEFAULT 'normal' CHECK (tipo IN ('normal','mensal','urgente')),
        data_necessidade date,
        observacao text,
        status varchar(10) NOT NULL DEFAULT 'aberta' CHECK (status IN ('aberta','aprovada','rejeitada','parcial','atendida')),
        motivo_rejeicao text,
        decidido_por varchar(120), decidido_em timestamptz,
        created_at timestamptz NOT NULL DEFAULT now())""",
    """CREATE TABLE IF NOT EXISTS sup_solicitacao_material_itens (
        id serial PRIMARY KEY,
        solicitacao_id int NOT NULL REFERENCES sup_solicitacoes_material(id) ON DELETE CASCADE,
        item_code varchar(60) NOT NULL,
        descricao text,
        quantidade numeric(12,3) NOT NULL CHECK (quantidade > 0),
        entregue numeric(12,3) NOT NULL DEFAULT 0 CHECK (entregue >= 0 AND entregue <= quantidade),
        observacao text)""",
    "CREATE INDEX IF NOT EXISTS ix_sup_sol_mat_status ON sup_solicitacoes_material (status, created_at DESC)",
    """CREATE TABLE IF NOT EXISTS sst_aso_exames (
        id serial PRIMARY KEY,
        employee_id uuid NOT NULL,
        aso_id varchar(60),
        tipo_exame_id int NOT NULL REFERENCES sst_tipos_exame(id),
        data date NOT NULL,
        valido_ate date NOT NULL,
        resultado varchar(20) NOT NULL DEFAULT 'normal' CHECK (resultado IN ('normal','alterado','pendente')),
        observacao text,
        created_by varchar(120), created_at timestamptz NOT NULL DEFAULT now(),
        CHECK (valido_ate >= data))""",
    "CREATE INDEX IF NOT EXISTS ix_sst_aso_exames_emp ON sst_aso_exames (employee_id, tipo_exame_id, valido_ate DESC)",
    """CREATE TABLE IF NOT EXISTS acessos_temporarios (
        id serial PRIMARY KEY,
        user_id uuid NOT NULL UNIQUE,
        papel varchar(20) NOT NULL CHECK (papel IN ('leitura','operacional')),
        modulos text[] NOT NULL,
        motivo text NOT NULL,
        expira_em timestamptz NOT NULL,
        criado_por varchar(120) NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
        revogado_em timestamptz, revogado_por varchar(120))""",
]


async def _ensure(db) -> None:
    for ddl in _DDL:
        await db.execute(text(ddl))


async def _um(db, sql: str, **p):
    return (await db.execute(text(sql), p)).first()


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:  # noqa: BLE001
        return str(v or "—")


def _dth(v):
    try:
        return v.astimezone(_TZ).strftime("%d/%m/%Y %H:%M:%S") if v else "—"
    except Exception:  # noqa: BLE001
        return str(v or "—")


def _data(v, campo, obrigatorio=False):
    s = (v or "").strip()
    if not s:
        if obrigatorio:
            raise HTTPException(status_code=400, detail=f"{campo} é obrigatório.")
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            pass
    raise HTTPException(status_code=400, detail=f"{campo}: use DD/MM/AAAA.")


def _uuid(v):
    s = (v or "").strip()
    return s or None


def _id(v) -> int:
    """id de linha vem como int do JSON da tela ou como texto de um form — o banco quer int."""
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="Registro não informado.") from None


def _acao(titulo, endpoint, btn, fields, ok="Feito. Recarregue.", style="outline", confirm=None, fixed=None, sub=None):
    a = {"title": titulo, "endpoint": _ACT + endpoint, "method": "POST", "btnLabel": btn, "btnStyle": style,
         "submitLabel": btn, "okMsg": ok, "fields": fields}
    if sub:
        a["sub"] = sub
    if confirm:
        a["confirm"] = confirm
    if fixed:
        a["fixed"] = fixed
    return a


def _sel(key, label, options, span="span 1", value=""):
    return {"key": key, "label": label, "type": "select", "options": options, "span": span, "value": value}


# =============================================================================
# 1) LOG DO SISTEMA — módulo seguranca
# =============================================================================
async def telas_seguranca(db, out: dict) -> dict:
    """`auditoria` (sobrescreve a lista de turnover_audit_logs) + `auditoria-telas`."""
    mine, safe, tbl = _helpers(db)
    n_total = (await _um(db, "SELECT count(*) FROM crm_audit_log"))[0]
    n24 = (await _um(db, "SELECT count(*) FROM crm_audit_log WHERE ts > now() - interval '24 hours'"))[0]
    n7 = (await _um(db, "SELECT count(*), count(DISTINCT user_id) FROM crm_audit_log WHERE ts > now() - interval '7 days'"))

    def _tone(st):
        try:
            st = int(st)
        except (TypeError, ValueError):
            return "mut"
        return "ok" if st < 300 else ("warn" if st < 500 else "bad")

    def _o_que(m, p):
        p = p or ""
        if p.startswith("/api/v1/redesign/data/"):
            return "abriu a tela " + p.rsplit("/", 1)[-1]
        if p.startswith("/api/v1/redesign/action/"):
            return "ação " + p.rsplit("/", 1)[-1]
        return {"POST": "criou/enviou", "PUT": "alterou", "PATCH": "alterou", "DELETE": "apagou"}.get(m, m) + " " + p.replace("/api/v1/", "")

    await safe("auditoria", tbl(
        "Auditoria — log do sistema",
        f"{n_total} registros · {n24} nas últimas 24 h · {n7[0]} em 7 dias por {n7[1]} usuários · o middleware grava toda "
        "escrita (POST/PUT/PATCH/DELETE) e cada tela do redesign aberta: quem, quando, o quê, resultado, IP · fonte: crm_audit_log",
        "—",
        ["Quando", "Quem", "O quê", "Método", "Caminho", "HTTP", "IP"], "1.2fr 1.4fr 2fr 0.6fr 2fr 0.5fr 0.9fr",
        "SELECT a.ts, coalesce(u.name, u.email, '— sem login —'), a.method, a.path, a.status, a.ip, coalesce(u.email,'—') "
        "FROM crm_audit_log a LEFT JOIN users u ON u.id = a.user_id "
        "WHERE a.path NOT LIKE '%/log-acesso-sensivel%' ORDER BY a.ts DESC LIMIT 400",
        lambda r: [t(_dth(r[0]), 500, _ND), t(r[1], 600, _ND), t(_o_que(r[2], r[3])[:70]), b(r[2], "info" if r[2] == "GET" else "warn"),
                   t((r[3] or "")[:70]), b(str(r[4] or "—"), _tone(r[4])), t(r[5] or "—")],
        hint="Buscar por caminho, usuário…",
        filtrofn=lambda r: {"Método": r[2], "Usuário": (r[1] or "—")[:40]},
    ))
    await safe("auditoria-telas", tbl(
        "Auditoria — telas abertas (7 dias)",
        "Quem abriu qual tela e quantas vezes · GET /api/v1/redesign/data/<módulo> · fonte: crm_audit_log", "—",
        ["Usuário", "Módulo (tela)", "Aberturas", "Última vez"], "1.6fr 1.4fr 0.7fr 1.2fr",
        "SELECT coalesce(u.name, u.email, '— sem login —'), split_part(a.path, '/api/v1/redesign/data/', 2), count(*), max(a.ts) "
        "FROM crm_audit_log a LEFT JOIN users u ON u.id = a.user_id "
        "WHERE a.method = 'GET' AND a.path LIKE '/api/v1/redesign/data/%' AND a.ts > now() - interval '7 days' "
        "GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 300",
        lambda r: [t(r[0], 600, _ND), t(r[1]), b(str(r[2]), "info"), t(_dth(r[3]))],
        filtrofn=lambda r: {"Usuário": (r[0] or "—")[:40]},
    ))
    out.update(mine)
    return out


# =============================================================================
# 2) SOLICITAÇÃO DE MATERIAIS — módulo suprimentos
# =============================================================================
_STATUS_SM = {"aberta": ("Aberta", "warn"), "aprovada": ("Aprovada", "info"), "rejeitada": ("Rejeitada", "bad"),
              "parcial": ("Parcial", "warn"), "atendida": ("Atendida", "ok")}


async def _itens_sm(db, sid: int):
    return (await db.execute(text(
        "SELECT item_code, coalesce(descricao, item_code), quantidade, entregue FROM sup_solicitacao_material_itens WHERE solicitacao_id = :s ORDER BY id"
    ), {"s": sid})).fetchall()


async def telas_sup(db, out: dict) -> dict:
    await _ensure(db)
    mine, safe, tbl = _helpers(db)
    cont = dict((await db.execute(text("SELECT status, count(*) FROM sup_solicitacoes_material GROUP BY 1"))).fetchall())
    itens_por = {}
    for r in (await db.execute(text(
        "SELECT solicitacao_id, string_agg(item_code || ' × ' || trim(to_char(quantidade,'FM999999990.###')) || "
        "CASE WHEN entregue > 0 THEN ' (entregue ' || trim(to_char(entregue,'FM999999990.###')) || ')' ELSE '' END, ' · ' ORDER BY id), "
        "string_agg(item_code || '|' || trim(to_char(quantidade - entregue,'FM999999990.###')), E'\\n' ORDER BY id) FILTER (WHERE entregue < quantidade) "
        "FROM sup_solicitacao_material_itens GROUP BY 1"
    ))).fetchall():
        itens_por[r[0]] = (r[1], r[2] or "")

    def _acoes(r):
        sid, st = r[0], r[6]
        acts = []
        if st == "aberta":
            acts.append(_acao(f"Aprovar {r[1]}", "sup-solicitacao-material-status", "Aprovar", [], style="primary",
                              fixed={"id": sid, "status": "aprovada"}, ok="Aprovada. Recarregue."))
            acts.append(_acao(f"Rejeitar {r[1]}", "sup-solicitacao-material-status", "Rejeitar",
                              [{"key": "motivo", "label": "Motivo*", "type": "textarea", "span": "span 2"}],
                              style="danger", fixed={"id": sid, "status": "rejeitada"}, ok="Rejeitada. Recarregue."))
        if st in ("aprovada", "parcial"):
            acts.append(_acao(f"Atender {r[1]}", "sup-solicitacao-material-atender", "Atender",
                              [{"key": "entregas", "label": "Entregas (código|quantidade, uma por linha; vem preenchido com o que falta)",
                                "type": "textarea", "span": "span 2", "value": itens_por.get(sid, ("", ""))[1]}],
                              style="primary", fixed={"id": sid}, confirm="Baixa o estoque e lança o custo no razão. Confirma?",
                              ok="Atendida — estoque baixado. Recarregue.",
                              sub="Mesmo caminho da baixa por serviço (F9): reduz saldo, registra movimento de saída e posta o COGS."))
        return acts

    await safe("solicitacoes-material", tbl(
        "Solicitações de material",
        f"Abertas {cont.get('aberta', 0)} · Aprovadas {cont.get('aprovada', 0)} · Parciais {cont.get('parcial', 0)} · "
        f"Atendidas {cont.get('atendida', 0)} · Rejeitadas {cont.get('rejeitada', 0)} · posto pede, almoxarifado aprova e atende baixando o estoque",
        "—",
        ["Nº", "Posto", "Solicitante", "Tipo", "Necessidade", "Itens", "Situação", "Decisão"],
        "0.9fr 1.4fr 1.2fr 0.6fr 0.8fr 2.2fr 0.8fr 1.1fr",
        "SELECT s.id, s.numero, coalesce(p.name, '— sem posto —'), s.solicitante, s.tipo, s.data_necessidade, s.status, "
        "s.decidido_por, s.decidido_em, s.motivo_rejeicao FROM sup_solicitacoes_material s LEFT JOIN posts p ON p.id = s.post_id "
        "ORDER BY (s.status IN ('aberta','aprovada','parcial')) DESC, s.created_at DESC LIMIT 300",
        lambda r: [t(r[1], 600, _ND), t(r[2]), t(r[3]), b(r[4].capitalize(), "bad" if r[4] == "urgente" else "mut"),
                   t(_d(r[5])), t(itens_por.get(r[0], ("—", ""))[0][:90]), b(*_STATUS_SM.get(r[6], (r[6], "mut"))),
                   t((f"{r[7]} · {_d(r[8])}" if r[7] else "—") + (f" · {r[9]}" if r[9] else ""))],
        actionsfn=_acoes,
        filtrofn=lambda r: {"Situação": _STATUS_SM.get(r[6], (r[6],))[0], "Posto": r[2]},
    ))
    postos = [{"value": str(r[0]), "label": r[1]} for r in (await db.execute(text(
        "SELECT id, name FROM posts WHERE coalesce(is_active, true) AND coalesce(status,'active') = 'active' ORDER BY name"))).fetchall()]
    out["solicitacao-material-nova"] = {
        "title": "Nova solicitação de material", "cta": "Solicitar", "type": "form",
        "sub": "O posto pede ao almoxarifado. Itens: código do material (tela Materiais) | quantidade | observação, um por linha. "
               "Nasce «Aberta»; o almoxarifado aprova e atende — só atender mexe no estoque.",
        "submit": {"endpoint": _ACT + "sup-solicitacao-material", "okMsg": "Solicitação aberta. Veja em Solicitações de material."},
        "fields": [
            _sel("post_id", "Posto", [{"value": "", "label": "— sem posto —"}, *postos]),
            _sel("tipo", "Tipo*", [{"value": "normal", "label": "Normal"}, {"value": "mensal", "label": "Mensal"}, {"value": "urgente", "label": "Urgente"}], value="normal"),
            {"key": "data_necessidade", "label": "Necessário até", "type": "date", "span": "span 1"},
            {"key": "itens", "label": "Itens* (código | quantidade | observação)", "type": "textarea", "span": "span 2", "ph": "1254 | 10 | saco de lixo 100L\nEPI-001 | 2"},
            {"key": "observacao", "label": "Observação", "type": "textarea", "span": "span 2"},
        ],
    }
    out.update(mine)
    return out


async def _material(db, ref: str):
    r = await _um(db, "SELECT item_code, descricao FROM nfe_compras_estoque WHERE coalesce(ativo,true) AND item_code = :r", r=ref)
    if r:
        return r
    rs = (await db.execute(text(
        "SELECT item_code, descricao FROM nfe_compras_estoque WHERE coalesce(ativo,true) AND descricao ILIKE :r LIMIT 2"), {"r": f"%{ref}%"})).fetchall()
    if len(rs) == 1:
        return rs[0]
    raise HTTPException(status_code=404, detail=f"Material «{ref}» não encontrado (ou ambíguo) — use o código da tela Materiais.")


def _linhas(txt: str):
    for ln in (txt or "").splitlines():
        if ln.strip():
            yield [x.strip() for x in ln.split("|")]


@router.post("/action/sup-solicitacao-material")
async def sup_solicitacao_material(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    itens = []
    for p in _linhas(payload.get("itens")):
        if len(p) < 2:
            raise HTTPException(status_code=400, detail=f"Item «{' | '.join(p)}»: informe código | quantidade.")
        code, desc = await _material(db, p[0])
        qtd = f10._dec(p[1], "Quantidade")
        if not qtd or qtd <= 0:
            raise HTTPException(status_code=400, detail=f"Item {code}: quantidade deve ser maior que zero.")
        itens.append((code, desc, qtd, p[2] if len(p) > 2 else None))
    if not itens:
        raise HTTPException(status_code=400, detail="Informe ao menos um item.")
    tipo = payload.get("tipo") or "normal"
    if tipo not in ("normal", "mensal", "urgente"):
        raise HTTPException(status_code=400, detail="Tipo inválido.")
    quem = f10._quem(current_user)
    n = (await _um(db, "SELECT count(*) + 1 FROM sup_solicitacoes_material"))[0]
    numero = f"SM-{datetime.now(_TZ):%Y%m}-{n:04d}"
    sid = (await _um(db,
        "INSERT INTO sup_solicitacoes_material (numero, post_id, solicitante, tipo, data_necessidade, observacao) "
        "VALUES (:n, CAST(:p AS uuid), :s, :t, :d, :o) RETURNING id",
        n=numero, p=_uuid(payload.get("post_id")), s=quem, t=tipo,
        d=_data(payload.get("data_necessidade"), "Necessário até"), o=(payload.get("observacao") or "").strip() or None))[0]
    for code, desc, qtd, obs in itens:
        await db.execute(text(
            "INSERT INTO sup_solicitacao_material_itens (solicitacao_id, item_code, descricao, quantidade, observacao) VALUES (:s, :c, :d, :q, :o)"),
            {"s": sid, "c": code, "d": desc, "q": qtd, "o": obs})
    await db.commit()
    return {"ok": True, "id": sid, "numero": numero, "message": f"Solicitação {numero} aberta com {len(itens)} item(ns)."}


@router.post("/action/sup-solicitacao-material-status")
async def sup_solicitacao_material_status(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    sid, novo = _id(payload.get("id")), payload.get("status")
    if novo not in ("aprovada", "rejeitada"):
        raise HTTPException(status_code=400, detail="Status inválido.")
    motivo = (payload.get("motivo") or "").strip()
    if novo == "rejeitada" and not motivo:
        raise HTTPException(status_code=400, detail="Informe o motivo da rejeição.")
    r = await _um(db,
        "UPDATE sup_solicitacoes_material SET status = :n, motivo_rejeicao = :m, decidido_por = :q, decidido_em = now() "
        "WHERE id = :id AND status = 'aberta' RETURNING numero", n=novo, m=motivo or None, q=f10._quem(current_user), id=sid)
    if not r:
        raise HTTPException(status_code=409, detail="Solicitação não está «Aberta» (ou não existe).")
    await db.commit()
    return {"ok": True, "message": f"{r[0]} {novo}."}


@router.post("/action/sup-solicitacao-material-atender")
async def sup_solicitacao_material_atender(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    """Entrega parcial ou total. Cada linha código|qtd baixa o estoque pelo caminho provado da F9
    (`EstoqueRealService.registrar_saida`: saldo, movimento de saída, COGS). Saldo insuficiente → 409,
    nada gravado (a baixa é a primeira coisa a falhar, antes do UPDATE dos itens)."""
    await _ensure(db)
    sid = _id(payload.get("id"))
    s = await _um(db, "SELECT id, numero, status, post_id FROM sup_solicitacoes_material WHERE id = :id", id=sid)
    if not s or s[2] not in ("aprovada", "parcial"):
        raise HTTPException(status_code=409, detail="Só se atende solicitação «Aprovada» ou «Parcial».")
    pedidos = {r[0]: (float(r[2]), float(r[3])) for r in await _itens_sm(db, s[0])}
    entregas = []
    for p in _linhas(payload.get("entregas")):
        if len(p) < 2 or p[0] not in pedidos:
            raise HTTPException(status_code=400, detail=f"Linha «{' | '.join(p)}»: código não está na solicitação.")
        q = f10._dec(p[1], "Quantidade") or 0
        if q <= 0:
            continue
        falta = pedidos[p[0]][0] - pedidos[p[0]][1]
        if q > falta + 1e-9:
            raise HTTPException(status_code=400, detail=f"{p[0]}: entrega {q:g} maior que o que falta ({falta:g}).")
        entregas.append((p[0], q))
    if not entregas:
        raise HTTPException(status_code=400, detail="Nenhuma quantidade a entregar.")
    from modules.financial.services.estoque_real_service import EstoqueRealService

    quem = f10._quem(current_user)
    posto = (await _um(db, "SELECT name FROM posts WHERE id = :p", p=s[3]))[0] if s[3] else None
    custo = 0.0
    for code, q in entregas:
        try:
            r = await asyncio.to_thread(EstoqueRealService().registrar_saida, code, q, posto, f"Solicitação {s[1]} · {quem}")
        except ValueError as e:
            raise HTTPException(status_code=409, detail=f"{code}: {e}") from None
        custo += float(r.get("custo_total") or 0)
        await db.execute(text(
            "UPDATE sup_solicitacao_material_itens SET entregue = entregue + :q WHERE solicitacao_id = :s AND item_code = :c"),
            {"q": q, "s": s[0], "c": code})
    completo = (await _um(db,
        "SELECT bool_and(entregue >= quantidade) FROM sup_solicitacao_material_itens WHERE solicitacao_id = :s", s=s[0]))[0]
    novo = "atendida" if completo else "parcial"
    await db.execute(text(
        "UPDATE sup_solicitacoes_material SET status = :n, decidido_por = :q, decidido_em = now() WHERE id = :id"),
        {"n": novo, "q": quem, "id": s[0]})
    await db.commit()
    return {"ok": True, "status": novo, "custo_total": custo,
            "message": f"{s[1]}: {len(entregas)} item(ns) baixado(s), custo {brl(custo)} lançado — situação «{_STATUS_SM[novo][0]}»."}


# =============================================================================
# 3) EXAMES POR ASO — módulo saude-ocupacional
# =============================================================================
async def telas_sst(db, out: dict) -> dict:
    await _ensure(db)
    mine, safe, tbl = _helpers(db)
    hoje = datetime.now(_TZ).date()
    tot = await _um(db,
        "WITH u AS (SELECT DISTINCT ON (employee_id, tipo_exame_id) valido_ate FROM sst_aso_exames ORDER BY employee_id, tipo_exame_id, valido_ate DESC) "
        "SELECT count(*), count(*) FILTER (WHERE valido_ate < :h), count(*) FILTER (WHERE valido_ate >= :h AND valido_ate < :h + 30) FROM u", h=hoje)

    def _sit(v):
        if v < hoje:
            return b(f"vencido há {(hoje - v).days} d", "bad")
        if (v - hoje).days <= 30:
            return b(f"vence em {(v - hoje).days} d", "warn")
        return b("em dia", "ok")

    await safe("aso-exames-vencendo", tbl(
        "Exames por colaborador",
        f"{tot[0]} exames (último por colaborador × tipo) · {tot[1]} vencidos · {tot[2]} vencem em 30 dias · «Válido até» = data + "
        "periodicidade do tipo (tela Tipos de exame) · o ASO anual não esconde mais a audiometria de 6 meses · fonte: sst_aso_exames",
        "—",
        ["Colaborador", "Cargo", "Exame", "Data", "Válido até", "Resultado", "Situação"], "1.8fr 1.1fr 1.4fr 0.8fr 0.8fr 0.8fr 1.1fr",
        "SELECT DISTINCT ON (x.employee_id, x.tipo_exame_id) coalesce(e.nome,'—'), coalesce(e.cargo,'—'), te.nome, x.data, x.valido_ate, x.resultado, "
        "coalesce(e.status,'—') FROM sst_aso_exames x JOIN sst_tipos_exame te ON te.id = x.tipo_exame_id LEFT JOIN employees e ON e.id = x.employee_id "
        "ORDER BY x.employee_id, x.tipo_exame_id, x.valido_ate DESC, x.id DESC",
        lambda r: [t(r[0], 600, _ND), t(r[1]), t(r[2]), t(_d(r[3])), t(_d(r[4]), 600, _ND),
                   b(r[5].capitalize(), "bad" if r[5] == "alterado" else ("warn" if r[5] == "pendente" else "ok")), _sit(r[4])],
        filtrofn=lambda r: {"Situação": "vencido" if r[4] < hoje else ("vence em 30 d" if (r[4] - hoje).days <= 30 else "em dia"),
                            "Exame": r[2]},
    ))
    emps = [{"value": str(r[0]), "label": f"{r[1]} · {r[2] or '—'}"} for r in (await db.execute(text(
        "SELECT id, nome, cargo FROM employees WHERE status = 'ativo' ORDER BY nome LIMIT 400"))).fetchall()]
    tipos = [{"value": str(r[0]), "label": f"{r[1]} ({r[2] or 12} meses)"} for r in (await db.execute(text(
        "SELECT id, nome, periodicidade_meses FROM sst_tipos_exame WHERE coalesce(ativo,true) ORDER BY nome"))).fetchall()]
    out["aso-exame-novo"] = {
        "title": "Registrar exame realizado", "cta": "Registrar", "type": "form",
        "sub": "Um exame, uma data. «Válido até» sai da periodicidade do tipo (Tipos de exame). Se houver ASO agendado/realizado "
               "do colaborador, o exame fica ligado a ele.",
        "submit": {"endpoint": _ACT + "aso-exame-registrar", "okMsg": "Exame registrado. Veja em Exames por colaborador."},
        "fields": [
            _sel("employee_id", "Colaborador*", emps, "span 2"),
            _sel("tipo_exame_id", "Exame*", tipos),
            {"key": "data", "label": "Data do exame*", "type": "date", "span": "span 1"},
            _sel("resultado", "Resultado", [{"value": "normal", "label": "Normal"}, {"value": "alterado", "label": "Alterado"}, {"value": "pendente", "label": "Pendente (laudo)"}], value="normal"),
            {"key": "observacao", "label": "Observação", "type": "text", "span": "span 1"},
        ],
    }
    out.update(mine)
    return out


def _mais_meses(d: date, meses: int) -> date:
    m = d.month - 1 + meses
    y, m = d.year + m // 12, m % 12 + 1
    dia = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 != 0 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, dia)


@router.post("/action/aso-exame-registrar")
async def aso_exame_registrar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    emp, tid = _uuid(payload.get("employee_id")), payload.get("tipo_exame_id")
    if not emp or not str(tid or "").isdigit():
        raise HTTPException(status_code=400, detail="Colaborador e exame são obrigatórios.")
    tipo = await _um(db, "SELECT nome, coalesce(periodicidade_meses, 12) FROM sst_tipos_exame WHERE id = :t", t=int(tid))
    if not tipo:
        raise HTTPException(status_code=404, detail="Tipo de exame não encontrado.")
    d = _data(payload.get("data"), "Data do exame", obrigatorio=True)
    if d > datetime.now(_TZ).date():
        raise HTTPException(status_code=400, detail="Data do exame no futuro.")
    res = payload.get("resultado") or "normal"
    if res not in ("normal", "alterado", "pendente"):
        raise HTTPException(status_code=400, detail="Resultado inválido.")
    valido = _mais_meses(d, int(tipo[1]))
    aso = await _um(db,
        "SELECT aso_id FROM gp_asos WHERE employee_id = CAST(:e AS uuid) AND status IN ('agendado','realizado') ORDER BY coalesce(data_realizacao, data_agendamento) DESC NULLS LAST LIMIT 1", e=emp)
    r = await _um(db,
        "INSERT INTO sst_aso_exames (employee_id, aso_id, tipo_exame_id, data, valido_ate, resultado, observacao, created_by) "
        "VALUES (CAST(:e AS uuid), :a, :t, :d, :v, :r, :o, :q) RETURNING id",
        e=emp, a=(aso[0] if aso else None), t=int(tid), d=d, v=valido, r=res, o=(payload.get("observacao") or "").strip() or None,
        q=f10._quem(current_user))
    await db.commit()
    return {"ok": True, "id": r[0], "valido_ate": valido.isoformat(),
            "message": f"{tipo[0]} em {d:%d/%m/%Y} — válido até {valido:%d/%m/%Y}" + (" (ligado ao ASO)" if aso else " (sem ASO em aberto)") + "."}


# =============================================================================
# 4) ACESSOS TEMPORÁRIOS — módulo configuracoes
# =============================================================================
async def expirar_acessos(db) -> int:
    """Desativa o `users` de todo acesso vencido e ainda ativo. Chamada no gate do redesign e nas telas;
    idempotente e barata (um UPDATE). Devolve quantos desativou."""
    await _ensure(db)
    n = (await db.execute(text(
        "UPDATE users u SET is_active = false, updated_at = now() FROM acessos_temporarios a "
        "WHERE a.user_id = u.id AND u.is_active AND (a.expira_em < now() OR a.revogado_em IS NOT NULL)"))).rowcount
    if n:
        await db.commit()
    return n


def _modulos_permitidos() -> list[str]:
    from core.auth.module_scope import CANONICAL_MODULES

    return sorted(m for m in CANONICAL_MODULES if m not in MODULO_PROIBIDO)


async def telas_config(db, out: dict) -> dict:
    await expirar_acessos(db)
    mine, safe, tbl = _helpers(db)
    tot = await _um(db,
        "SELECT count(*), count(*) FILTER (WHERE revogado_em IS NULL AND expira_em >= now()), "
        "count(*) FILTER (WHERE revogado_em IS NULL AND expira_em < now()), count(*) FILTER (WHERE revogado_em IS NOT NULL) FROM acessos_temporarios")

    def _sit(r):
        if r[8]:
            return b("Revogado", "mut")
        return b("Vigente", "ok") if r[6] >= datetime.now(r[6].tzinfo) else b("Expirado", "bad")

    await safe("acessos-temporarios", tbl(
        "Acessos temporários",
        f"{tot[0]} acessos · {tot[1]} vigentes · {tot[2]} expirados · {tot[3]} revogados · usuário comum de `users` com validade: "
        "as travas de sempre valem (módulo, admin-only, ativo) e a expiração desativa o login sozinha · fonte: acessos_temporarios",
        "—",
        ["Nome", "E-mail", "Papel", "Módulos", "Motivo", "Expira em", "Situação", "Criado por"],
        "1.3fr 1.6fr 0.8fr 1.3fr 1.6fr 1fr 0.8fr 1.2fr",
        "SELECT a.id, u.name, u.email, a.papel, array_to_string(a.modulos, ', '), a.motivo, a.expira_em, a.criado_por, a.revogado_em, u.is_active "
        "FROM acessos_temporarios a JOIN users u ON u.id = a.user_id ORDER BY (a.revogado_em IS NULL AND a.expira_em >= now()) DESC, a.expira_em DESC LIMIT 200",
        lambda r: [t(r[1], 600, _ND), t(r[2]), b(r[3].capitalize(), "info" if r[3] == "leitura" else "warn"), t(r[4]), t((r[5] or "")[:60]),
                   t(_dth(r[6])), _sit(r), t(f"{r[7]} · login {'ativo' if r[9] else 'inativo'}")],
        actionsfn=lambda r: [] if (r[8] or r[6] < datetime.now(r[6].tzinfo)) else [
            _acao(f"Revogar acesso de {r[1]}", "acesso-temporario-revogar", "Revogar", [], style="danger", fixed={"id": r[0]},
                  confirm="Desativa o login agora. Confirma?", ok="Acesso revogado. Recarregue.")],
        filtrofn=lambda r: {"Situação": "revogado" if r[8] else ("vigente" if r[6] >= datetime.now(r[6].tzinfo) else "expirado")},
    ))
    out["acesso-temporario-novo"] = {
        "title": "Novo acesso temporário", "cta": "Criar acesso", "type": "form",
        "sub": "Para contador, auditor ou consultor: cria um usuário com validade. Leitura = perfil viewer; operacional = operator. "
               "Financeiro nunca entra (mesma regra da tela Usuários). A senha inicial aparece UMA vez na resposta.",
        "submit": {"endpoint": _ACT + "acesso-temporario-criar", "okMsg": "Acesso criado — copie a senha da resposta.", "showResult": True,
                   "confirm": "Cria um login novo com validade. Confirma?"},
        "fields": [
            {"key": "nome", "label": "Nome*", "type": "text", "span": "span 1"},
            {"key": "email", "label": "E-mail (login)*", "type": "text", "span": "span 1"},
            _sel("papel", "Papel*", [{"value": "leitura", "label": "Leitura"}, {"value": "operacional", "label": "Operacional"}], value="leitura"),
            {"key": "dias", "label": "Validade (dias)*", "type": "number", "span": "span 1", "value": "7"},
            {"key": "modulos", "label": "Módulos*", "type": "multiselect", "span": "span 2",
             "options": [{"value": m, "label": m.upper()} for m in _modulos_permitidos()], "value": "[]"},
            {"key": "motivo", "label": "Motivo*", "type": "textarea", "span": "span 2", "ph": "Ex.: auditoria do contador sobre setembro/2026"},
        ],
    }
    out.update(mine)
    return out


def _lista(v) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    s = (v or "").strip()
    if s.startswith("["):
        try:
            return [str(x).strip() for x in json.loads(s) if str(x).strip()]
        except ValueError:
            pass
    return [x.strip() for x in s.split(",") if x.strip()]


@router.post("/action/acesso-temporario-criar")
async def acesso_temporario_criar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    from core.auth.security import hash_password

    await _ensure(db)
    nome, email = (payload.get("nome") or "").strip(), (payload.get("email") or "").strip().lower()
    papel, motivo = payload.get("papel") or "leitura", (payload.get("motivo") or "").strip()
    if not nome or "@" not in email or not motivo:
        raise HTTPException(status_code=400, detail="Nome, e-mail e motivo são obrigatórios.")
    if papel not in PAPEIS:
        raise HTTPException(status_code=400, detail="Papel inválido.")
    dias = f10._int(payload.get("dias"), "Validade", 1)
    if not dias or dias > 90:
        raise HTTPException(status_code=400, detail="Validade: entre 1 e 90 dias.")
    permitidos = set(_modulos_permitidos())
    mods = [m.replace("module:", "") for m in _lista(payload.get("modulos"))]
    if not mods or any(m not in permitidos for m in mods):
        raise HTTPException(status_code=400, detail=f"Módulos: escolha entre {', '.join(sorted(permitidos))} (financeiro nunca).")
    if await _um(db, "SELECT 1 FROM users WHERE lower(email) = :e", e=email):
        raise HTTPException(status_code=409, detail="Já existe usuário com esse e-mail.")
    senha = secrets.token_urlsafe(9)
    expira = datetime.now(_TZ) + timedelta(days=dias)
    quem = f10._quem(current_user)
    uid = (await _um(db,
        "INSERT INTO users (id, email, password_hash, name, role, permissions, is_active, notes) "
        "VALUES (gen_random_uuid(), :e, :h, :n, :r, CAST(:p AS varchar[]), true, :o) RETURNING id",
        e=email, h=hash_password(senha), n=nome, r=PAPEIS[papel], p=[f"module:{m}" for m in mods],
        o=f"Acesso temporário até {expira:%d/%m/%Y %H:%M} · {motivo} · criado por {quem}"))[0]
    await db.execute(text(
        "INSERT INTO acessos_temporarios (user_id, papel, modulos, motivo, expira_em, criado_por) VALUES (:u, :p, CAST(:m AS text[]), :mo, :x, :q)"),
        {"u": uid, "p": papel, "m": mods, "mo": motivo, "x": expira, "q": quem})
    await db.commit()
    return {"ok": True, "user_id": str(uid), "email": email, "senha_inicial": senha, "expira_em": expira.isoformat(),
            "message": f"Acesso de {nome} ({email}) até {expira:%d/%m/%Y %H:%M} · módulos {', '.join(mods)} · senha inicial: {senha}"}


@router.post("/action/acesso-temporario-revogar")
async def acesso_temporario_revogar(current_user: CurrentActiveUser, payload: dict = Body(...), db=Depends(get_db)) -> dict:
    await _ensure(db)
    r = await _um(db,
        "UPDATE acessos_temporarios SET revogado_em = now(), revogado_por = :q WHERE id = :id AND revogado_em IS NULL RETURNING user_id",
        q=f10._quem(current_user), id=_id(payload.get("id")))
    if not r:
        raise HTTPException(status_code=404, detail="Acesso não encontrado ou já revogado.")
    await db.execute(text("UPDATE users SET is_active = false, updated_at = now() WHERE id = :u"), {"u": r[0]})
    await db.commit()
    return {"ok": True, "message": "Acesso revogado — login desativado."}
