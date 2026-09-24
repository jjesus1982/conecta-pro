"""DGX F2 — CCT como DADO no DP (24/09/2026): Sindicato → Funções → Eventos/Benefícios por função →
Municípios. Cinco telas + forms, grupo «Sindicato & CCT» (g-cct) em `_dp_grupos.GRUPOS`.

Regra e DDL moram em `people_management/folha/services/cct_como_dado.py` (`ensure(db)` roda no
1º acesso e em cada ação). Nada aqui toca holerite, `calculo_service` ou `employees` — paralelo
cego; o oráculo `test_oraculo_cct_como_dado.py` é quem compara a régua com a folha.

Prefixo `_` = o discovery de builders pula este arquivo; `departamento_pessoal.py` importa
`router` no nível do módulo e chama `telas(db, out)` ANTES de `montar_grupos` (as abas do g-cct
nascem lá). Alcance: /redesign/departamento-pessoal?t=g-cct (menu via EXTRA_MENU do builder).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import S, _helpers, b, brl, t
from modules.people_management.folha.services import cct_como_dado as cd

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_SIM_NAO = [{"value": "true", "label": "Sim"}, {"value": "false", "label": "Não"}]
_ADIC = {
    "periculosidade_30": "Periculosidade 30%",
    "insalubridade_10": "Insalubridade 10%",
    "adicional_10": "Adicional 10% (sem rubrica)",
}


def _pct(v) -> str:
    return "—" if v is None else f"{float(v):g}%"


def _sn(v) -> dict:
    return b("Obrigatório", "bad") if v else b("Opcional", "mut")


def _quem(u) -> str:
    return getattr(u, "email", None) or str(getattr(u, "id", "") or "")


def _origem_tela(u) -> str:
    return f"tela DP · {_quem(u)} · {datetime.now(ZoneInfo('America/Manaus')).strftime('%d/%m/%Y %H:%M')}"


def _num(v, campo: str):
    s = str(v if v is not None else "").strip().replace("%", "").replace(",", ".")
    if not s:
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail=f"{campo}: número inválido «{v}»")


def _bool(v) -> bool:
    return str(v).strip().lower() in ("true", "1", "sim", "s", "on")


_COL_SIND = {
    "nome": 1,
    "sigla": 2,
    "cnpj": 3,
    "uf": 4,
    "data_base": 5,
    "categoria": 6,
    "tipo": 7,
    "contato": 8,
    "site": 9,
}


def _val_sind(r, k: str) -> str:
    return r[_COL_SIND[k]] or ""


async def telas(db, out: dict | None = None) -> dict:  # noqa: C901
    await cd.ensure(db)
    mine, safe, tbl = _helpers(db)

    conv = (
        await db.execute(
            text(
                "SELECT c.id::text, c.registro_mte, c.data_inicio, c.data_fim, c.data_base, c.sindicato_patronal, c.sindicato_patronal_cnpj, "
                " s.nome FROM cct_convencoes c LEFT JOIN cct_sindicatos s ON s.id=c.sindicato_id "
                "WHERE c.is_vigente AND c.is_active ORDER BY c.data_inicio DESC LIMIT 1"
            )
        )
    ).first()
    conv_id = conv[0] if conv else None
    rubricas = (
        await db.execute(
            text("SELECT codigo, descricao FROM rubricas_folha WHERE coalesce(ativo,true) ORDER BY codigo")
        )
    ).all()
    benef = (
        await db.execute(
            text(
                "SELECT id::text, tipo_beneficio FROM cct_beneficios WHERE is_active AND convencao_id::text = coalesce(:c, convencao_id::text) ORDER BY tipo_beneficio"
            ),
            {"c": conv_id},
        )
    ).all()
    opt_rub = [{"value": r[0], "label": f"{r[0]} — {r[1]}"} for r in rubricas]
    opt_ben = [{"value": r[0], "label": r[1]} for r in benef]

    # ── cct-sindicato: ficha + editar ────────────────────────────────────────────────────────
    campos_sind = [
        ("nome", "Nome*"),
        ("sigla", "Sigla"),
        ("cnpj", "CNPJ"),
        ("uf", "UF"),
        ("data_base", "Data-base (DD/MM)"),
        ("categoria", "Categoria"),
        ("site", "Site"),
        ("contato", "Contato"),
    ]
    await safe(
        "cct-sindicato",
        tbl(
            "Sindicato",
            "Entidade da convenção vigente (DGX: Sindicatos). Editar não muda folha — a folha lê o piso em Funções.",
            "—",
            ["Sindicato", "Sigla", "CNPJ", "UF", "Data-base", "Categoria", "Tipo", "Contato"],
            "1.8fr 0.8fr 1.1fr 0.4fr 0.7fr 1.8fr 0.6fr 1.2fr",
            "SELECT id::text, nome, sigla, cnpj, uf, data_base, categoria, tipo, contato, site FROM cct_sindicatos WHERE ativo ORDER BY tipo, nome",
            lambda r: [
                t(r[1], 600, _ND),
                t(r[2] or "—"),
                t(r[3] or "—"),
                t(r[4] or "—"),
                t(r[5] or "—"),
                t(r[6] or "—"),
                b(r[7], "info"),
                t(r[8] or "—"),
            ],
            editfn=lambda r: {
                "endpoint": _ACT + "cct-sindicato-editar",
                "method": "POST",
                "btnLabel": "Editar",
                "fixed": {"id": r[0]},
                "fields": [{"key": k, "label": l, "type": "text", "value": _val_sind(r, k)} for k, l in campos_sind],
            },
        ),
    )
    if "cct-sindicato" in mine and conv:
        mine["cct-sindicato"]["panelGrid"] = "1fr"
        mine["cct-sindicato"]["panels"] = [
            {
                "title": "Convenção vigente",
                "rows": [
                    {"left": "Registro MTE", "right": conv[1] or "—", **S["info"]},
                    {"left": "Vigência", "right": f"{conv[2]:%d/%m/%Y} a {conv[3]:%d/%m/%Y}", **S["ok"]},
                    {"left": "Data-base", "right": conv[4] or "—", **S["mut"]},
                    {
                        "left": "Sindicato laboral (sindicato_id)",
                        "right": conv[7] or "SEM VÍNCULO",
                        **S["ok" if conv[7] else "bad"],
                    },
                    {"left": "Sindicato patronal", "right": f"{conv[5]} · {conv[6] or ''}", **S["mut"]},
                ],
            }
        ]

    # ── cct-funcoes: função, piso, adicionais, nº eventos, nº benefícios, municípios ─────────
    def _acoes_funcao(r):
        return [
            {
                "title": f"Incluir evento em {r[1]}",
                "endpoint": _ACT + "cct-funcao-evento",
                "method": "POST",
                "btnLabel": "Eventos",
                "submitLabel": "Incluir",
                "btnStyle": "outline",
                "okMsg": "Evento incluído na função. Recarregue a tela.",
                "fixed": {"cct_cargo_id": r[0]},
                "fields": [
                    {
                        "key": "rubrica_codigo",
                        "label": "Rubrica*",
                        "type": "select",
                        "options": opt_rub,
                        "ph": "Selecione",
                    },
                    {"key": "razao", "label": "Razão (%)", "type": "text", "ph": "30"},
                    {"key": "razao_noturna", "label": "Razão noturna (%)", "type": "text", "ph": ""},
                    {"key": "obrigatorio", "label": "Obrigatório", "type": "select", "options": _SIM_NAO},
                    {"key": "observacao", "label": "Observação", "type": "text"},
                ],
            },
            {
                "title": f"Incluir benefício em {r[1]}",
                "endpoint": _ACT + "cct-funcao-beneficio",
                "method": "POST",
                "btnLabel": "Benefícios",
                "submitLabel": "Incluir",
                "btnStyle": "outline",
                "okMsg": "Benefício incluído na função. Recarregue a tela.",
                "fixed": {"cct_cargo_id": r[0]},
                "fields": [
                    {
                        "key": "cct_beneficio_id",
                        "label": "Benefício*",
                        "type": "select",
                        "options": opt_ben,
                        "ph": "Selecione",
                    },
                    {"key": "valor", "label": "Valor (R$)", "type": "text", "ph": "22.00"},
                    {"key": "desconto_percentual", "label": "Desconto (%)", "type": "text", "ph": "1"},
                    {"key": "obrigatorio", "label": "Obrigatório", "type": "select", "options": _SIM_NAO},
                    {"key": "observacao", "label": "Observação", "type": "text"},
                ],
            },
        ]

    await safe(
        "cct-funcoes",
        tbl(
            "Funções da CCT",
            "Uma linha por função (cct_cargos): piso, adicional do cargo, quantos eventos e benefícios estão declarados "
            "e em quantos municípios a convenção vale. «Eventos»/«Benefícios» incluem na função; remover é na aba própria.",
            "—",
            ["Função", "Piso", "Adicional do cargo", "Eventos", "Benefícios", "Ativos", "Municípios"],
            "2.4fr 0.8fr 1.1fr 0.6fr 0.7fr 0.5fr 0.7fr",
            "SELECT c.id::text, c.cargo_nome, c.piso_salarial, c.adicional_tipo, "
            " (SELECT count(*) FROM cct_funcao_eventos x WHERE x.cct_cargo_id=c.id AND x.ativo), "
            " (SELECT count(*) FILTER (WHERE x.obrigatorio) || '/' || count(*) FROM cct_funcao_beneficios x WHERE x.cct_cargo_id=c.id AND x.ativo), "
            " (SELECT count(*) FROM employees e WHERE e.cct_cargo_id=c.id AND lower(coalesce(e.status,''))='ativo' AND coalesce(e.is_homologacao,false)=false), "
            " (SELECT count(*) FROM cct_municipios m WHERE m.convencao_id=c.convencao_id) "
            "FROM cct_cargos c WHERE c.is_active ORDER BY 7 DESC, c.cargo_nome",
            lambda r: [
                t(r[1], 600, _ND),
                t(brl(r[2]), 600),
                b(_ADIC.get(r[3], r[3] or "—"), "warn" if r[3] else "mut"),
                b(str(r[4]), "ok" if r[4] else "bad"),
                t(f"{r[5]} obrig."),
                b(str(r[6]), "info" if r[6] else "mut"),
                t(str(r[7])),
            ],
            actionsfn=_acoes_funcao,
            filtrofn=lambda r: "com ativos" if r[6] else "sem ativos",
        ),
    )

    # ── cct-funcao-eventos ────────────────────────────────────────────────────────────────────
    rem = lambda acao, rid, rotulo: {  # noqa: E731
        "title": f"Remover {rotulo}",
        "endpoint": _ACT + acao,
        "method": "POST",
        "btnLabel": "Remover",
        "submitLabel": "Remover",
        "btnStyle": "danger",
        "okMsg": "Removido. Recarregue a tela.",
        "fixed": {"id": rid},
        "fields": [{"key": "motivo", "label": "Por quê? (fica no log)", "type": "text"}],
    }
    await safe(
        "cct-funcao-eventos",
        tbl(
            "Eventos por função",
            "Quais rubricas cada função pode/deve receber e com que razão (DGX: SindicatoFuncaoEventos). "
            "Obrigatório = o oráculo cobra no holerite. Origem diz de onde a regra veio.",
            "—",
            ["Função", "Rubrica", "Razão", "Razão not.", "Tipo", "Origem"],
            "2fr 1.8fr 0.6fr 0.7fr 0.8fr 3fr",
            "SELECT x.id::text, c.cargo_nome, x.rubrica_codigo, coalesce(r.descricao,'(rubrica fora de rubricas_folha)'), x.razao, x.razao_noturna, "
            " x.obrigatorio, coalesce(x.observacao,''), coalesce(x.origem_regra,'') "
            "FROM cct_funcao_eventos x JOIN cct_cargos c ON c.id=x.cct_cargo_id LEFT JOIN rubricas_folha r ON r.codigo=x.rubrica_codigo "
            "WHERE x.ativo ORDER BY c.cargo_nome, x.obrigatorio DESC, x.rubrica_codigo",
            lambda r: [
                t(r[1], 600, _ND),
                t(f"{r[2]} — {r[3]}"),
                t(_pct(r[4]), 600),
                t(_pct(r[5])),
                _sn(r[6]),
                t((r[7] + " · " if r[7] else "") + r[8][:160]),
            ],
            actionsfn=lambda r: [rem("cct-funcao-evento-remover", r[0], f"{r[2]} de {r[1]}")],
            filtrofn=lambda r: r[1],
            hint="Buscar função ou rubrica…",
        ),
    )

    # ── cct-funcao-beneficios ─────────────────────────────────────────────────────────────────
    await safe(
        "cct-funcao-beneficios",
        tbl(
            "Benefícios por função",
            "Quais benefícios da CCT cada função tem, com valor e desconto (DGX: SindicatoFuncaoBeneficios).",
            "—",
            ["Função", "Benefício", "Valor", "Desconto", "Tipo", "Origem"],
            "2fr 1.4fr 0.7fr 0.7fr 0.8fr 3fr",
            "SELECT x.id::text, c.cargo_nome, bf.tipo_beneficio, x.valor, x.desconto_percentual, x.obrigatorio, coalesce(x.observacao,''), coalesce(x.origem_regra,'') "
            "FROM cct_funcao_beneficios x JOIN cct_cargos c ON c.id=x.cct_cargo_id JOIN cct_beneficios bf ON bf.id=x.cct_beneficio_id "
            "WHERE x.ativo ORDER BY c.cargo_nome, x.obrigatorio DESC, bf.tipo_beneficio",
            lambda r: [
                t(r[1], 600, _ND),
                b(r[2].replace("_", " "), "info"),
                t(brl(r[3]) if r[3] is not None else "—"),
                t(_pct(r[4])),
                _sn(r[5]),
                t((r[6] + " · " if r[6] else "") + r[7][:160]),
            ],
            actionsfn=lambda r: [rem("cct-funcao-beneficio-remover", r[0], f"{r[2]} de {r[1]}")],
            filtrofn=lambda r: r[1],
            hint="Buscar função ou benefício…",
        ),
    )

    # ── cct-municipios (+ form novo) ─────────────────────────────────────────────────────────
    await safe(
        "cct-municipios",
        tbl(
            "Municípios da convenção",
            "Onde a CCT vigente vale (DGX: SindicatoMunicipios).",
            "Adicionar município",
            ["Município", "UF", "IBGE", "Origem"],
            "1.6fr 0.4fr 0.8fr 3fr",
            "SELECT m.id::text, m.municipio, m.uf, coalesce(m.ibge,''), coalesce(m.origem_regra,'') FROM cct_municipios m "
            "WHERE m.convencao_id::text = coalesce(:c, m.convencao_id::text) ORDER BY m.uf, m.municipio".replace(
                ":c", f"'{conv_id}'" if conv_id else "NULL"
            ),
            lambda r: [t(r[1], 600, _ND), t(r[2]), t(r[3] or "—"), t(r[4][:160])],
            actionsfn=lambda r: [rem("cct-municipio-remover", r[0], f"{r[1]}/{r[2]}")],
        ),
    )
    if "cct-municipios" in mine:
        mine["cct-municipios"]["ctaTo"] = "cct-municipio-novo"
    mine["cct-municipio-novo"] = {
        "title": "Adicionar município à convenção",
        "type": "form",
        "cta": "Adicionar",
        "sub": "Abrangência da CCT vigente. Não muda folha nem escala — é declaração para conferência.",
        "submit": {"endpoint": _ACT + "cct-municipio", "okMsg": "Município adicionado."},
        "fields": [
            {"key": "municipio", "label": "Município*", "type": "text", "span": "span 2", "ph": "Manaus"},
            {"key": "uf", "label": "UF*", "type": "text", "span": "span 1", "ph": "AM"},
            {"key": "ibge", "label": "Código IBGE", "type": "text", "span": "span 1", "ph": "1302603"},
        ],
    }

    # ── cct-conformidade (tela existente) ganha o aviso: função sem evento / ativo sem função ─
    tela = (out or {}).get("cct-conformidade")
    if isinstance(tela, dict) and tela.get("type") == "table":
        sem_ev, sem_cct = await cd.funcoes_sem_evento(db)
        tela["sub"] = (
            tela.get("sub") or ""
        ) + f" · Função sem evento configurado: {len(sem_ev)} · Ativos sem função da CCT: {len(sem_cct)}"
        tela["panelGrid"] = "1fr 1fr"
        tela["panels"] = [
            {
                "title": "Ativos cuja função NÃO tem nenhum evento configurado (aba Eventos por função)",
                "rows": [{"left": n, "right": "sem evento", **S["bad"]} for n in sem_ev]
                or [{"left": "Toda função com ativo tem evento", "right": "0", **S["ok"]}],
            },
            {
                "title": "Ativos sem função da CCT (cct_cargo_id) — fora de toda conferência",
                "rows": [{"left": n, "right": "sem função", **S["warn"]} for n in sem_cct]
                or [{"left": "Todos os ativos têm função da CCT", "right": "0", **S["ok"]}],
            },
        ]
    return mine


# ───────────────────────── ações (POST /api/v1/redesign/action/cct-…) ─────────────────────────
router = APIRouter()


async def _log(db, quem: str, acao: str, alvo: str, motivo: str | None = None) -> None:
    import logging

    logging.getLogger(__name__).info("dgx f2 cct: %s %s %s %s", quem, acao, alvo, motivo or "")


@router.post("/action/cct-sindicato-editar")
async def rd_cct_sindicato_editar(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await cd.ensure(db)
    sid = str(payload.get("id") or "").strip()
    nome = str(payload.get("nome") or "").strip()
    if not sid or not nome:
        raise HTTPException(status_code=400, detail="id e nome são obrigatórios.")
    campos = {
        k: (str(payload.get(k) or "").strip() or None)
        for k in ("sigla", "cnpj", "uf", "data_base", "categoria", "site", "contato")
    }
    if campos["uf"] and len(campos["uf"]) != 2:
        raise HTTPException(status_code=400, detail="UF com 2 letras.")
    n = (
        await db.execute(
            text(
                "UPDATE cct_sindicatos SET nome=:nome, sigla=:sigla, cnpj=:cnpj, uf=upper(:uf), data_base=:data_base, categoria=:categoria, "
                "site=:site, contato=:contato, updated_at=now() WHERE id::text=:id"
            ),
            {"id": sid, "nome": nome, **campos},
        )
    ).rowcount
    if not n:
        raise HTTPException(status_code=404, detail="Sindicato não encontrado.")
    await db.commit()
    await _log(db, _quem(current_user), "sindicato-editar", sid)
    return {"ok": True, "message": f"Sindicato «{nome}» atualizado."}


@router.post("/action/cct-funcao-evento")
async def rd_cct_funcao_evento(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await cd.ensure(db)
    cargo = str(payload.get("cct_cargo_id") or "").strip()
    rub = str(payload.get("rubrica_codigo") or "").strip()
    if not cargo or not rub:
        raise HTTPException(status_code=400, detail="Função e rubrica são obrigatórias.")
    if not (await db.execute(text("SELECT 1 FROM rubricas_folha WHERE codigo=:c"), {"c": rub})).first():
        raise HTTPException(
            status_code=400, detail=f"Rubrica {rub} não existe em rubricas_folha — cadastre na aba Rubricas antes."
        )
    if not (await db.execute(text("SELECT 1 FROM cct_cargos WHERE id::text=:c"), {"c": cargo})).first():
        raise HTTPException(status_code=404, detail="Função não encontrada.")
    p = {
        "cargo": cargo,
        "rub": rub,
        "razao": _num(payload.get("razao"), "Razão"),
        "rn": _num(payload.get("razao_noturna"), "Razão noturna"),
        "obrig": _bool(payload.get("obrigatorio")),
        "obs": str(payload.get("observacao") or "").strip() or None,
        "orig": _origem_tela(current_user),
    }
    await db.execute(
        text(
            "INSERT INTO cct_funcao_eventos (cct_cargo_id, rubrica_codigo, razao, razao_noturna, obrigatorio, observacao, origem_regra) "
            "VALUES (:cargo, :rub, :razao, :rn, :obrig, :obs, :orig) "
            "ON CONFLICT (cct_cargo_id, rubrica_codigo) DO UPDATE SET razao=EXCLUDED.razao, razao_noturna=EXCLUDED.razao_noturna, "
            " obrigatorio=EXCLUDED.obrigatorio, observacao=EXCLUDED.observacao, origem_regra=EXCLUDED.origem_regra, ativo=true, updated_at=now()"
        ),
        p,
    )
    await db.commit()
    await _log(db, _quem(current_user), "funcao-evento", f"{cargo}/{rub}")
    return {
        "ok": True,
        "message": f"Rubrica {rub} declarada na função ({'obrigatória' if p['obrig'] else 'opcional'}).",
    }


@router.post("/action/cct-funcao-beneficio")
async def rd_cct_funcao_beneficio(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await cd.ensure(db)
    cargo = str(payload.get("cct_cargo_id") or "").strip()
    ben = str(payload.get("cct_beneficio_id") or "").strip()
    if not cargo or not ben:
        raise HTTPException(status_code=400, detail="Função e benefício são obrigatórios.")
    if not (await db.execute(text("SELECT 1 FROM cct_beneficios WHERE id::text=:b"), {"b": ben})).first():
        raise HTTPException(status_code=404, detail="Benefício não encontrado em cct_beneficios.")
    p = {
        "cargo": cargo,
        "ben": ben,
        "valor": _num(payload.get("valor"), "Valor"),
        "desc": _num(payload.get("desconto_percentual"), "Desconto"),
        "obrig": _bool(payload.get("obrigatorio")),
        "obs": str(payload.get("observacao") or "").strip() or None,
        "orig": _origem_tela(current_user),
    }
    await db.execute(
        text(
            "INSERT INTO cct_funcao_beneficios (cct_cargo_id, cct_beneficio_id, valor, desconto_percentual, obrigatorio, observacao, origem_regra) "
            "VALUES (:cargo, :ben, :valor, :desc, :obrig, :obs, :orig) "
            "ON CONFLICT (cct_cargo_id, cct_beneficio_id) DO UPDATE SET valor=EXCLUDED.valor, desconto_percentual=EXCLUDED.desconto_percentual, "
            " obrigatorio=EXCLUDED.obrigatorio, observacao=EXCLUDED.observacao, origem_regra=EXCLUDED.origem_regra, ativo=true, updated_at=now()"
        ),
        p,
    )
    await db.commit()
    await _log(db, _quem(current_user), "funcao-beneficio", f"{cargo}/{ben}")
    return {"ok": True, "message": "Benefício declarado na função."}


async def _remover(db, tabela: str, rid: str, quem: str, motivo: str | None) -> dict:
    await cd.ensure(db)
    if not rid:
        raise HTTPException(status_code=400, detail="id obrigatório.")
    n = (await db.execute(text(f"DELETE FROM {tabela} WHERE id::text=:id"), {"id": rid})).rowcount  # noqa: S608 — tabela é literal interno
    if not n:
        raise HTTPException(status_code=404, detail="Linha não encontrada.")
    await db.commit()
    await _log(db, quem, f"remover {tabela}", rid, motivo)
    return {"ok": True, "message": "Removido."}


@router.post("/action/cct-funcao-evento-remover")
async def rd_cct_funcao_evento_remover(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    return await _remover(
        db, "cct_funcao_eventos", str(payload.get("id") or ""), _quem(current_user), payload.get("motivo")
    )


@router.post("/action/cct-funcao-beneficio-remover")
async def rd_cct_funcao_beneficio_remover(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    return await _remover(
        db, "cct_funcao_beneficios", str(payload.get("id") or ""), _quem(current_user), payload.get("motivo")
    )


@router.post("/action/cct-municipio")
async def rd_cct_municipio(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    await cd.ensure(db)
    mun = str(payload.get("municipio") or "").strip()
    uf = str(payload.get("uf") or "").strip().upper()
    ibge = str(payload.get("ibge") or "").strip() or None
    if not mun or len(uf) != 2:
        raise HTTPException(status_code=400, detail="Município e UF (2 letras) são obrigatórios.")
    conv = (
        await db.execute(
            text("SELECT id::text FROM cct_convencoes WHERE is_vigente AND is_active ORDER BY data_inicio DESC LIMIT 1")
        )
    ).scalar()
    if not conv:
        raise HTTPException(status_code=400, detail="Não há convenção vigente.")
    await db.execute(
        text(
            "INSERT INTO cct_municipios (convencao_id, municipio, uf, ibge, origem_regra) VALUES (:c, :m, :uf, :ibge, :orig) "
            "ON CONFLICT (convencao_id, municipio, uf) DO UPDATE SET ibge=EXCLUDED.ibge, origem_regra=EXCLUDED.origem_regra"
        ),
        {"c": conv, "m": mun, "uf": uf, "ibge": ibge, "orig": _origem_tela(current_user)},
    )
    await db.commit()
    await _log(db, _quem(current_user), "municipio", f"{mun}/{uf}")
    return {"ok": True, "message": f"{mun}/{uf} incluído na convenção vigente."}


@router.post("/action/cct-municipio-remover")
async def rd_cct_municipio_remover(
    current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)
) -> dict:
    return await _remover(
        db, "cct_municipios", str(payload.get("id") or ""), _quem(current_user), payload.get("motivo")
    )
