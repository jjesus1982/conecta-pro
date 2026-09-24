"""DGX T1 — DP/RH, passagem de teste (24/09/2026): foto do colaborador (individual e em lote), ficha
única da pessoa, certificados vencendo, turnover mensal, cargo com CBO/exigências, termo
disciplinar em PDF. Prefixo `_` = o discovery pula; `departamento_pessoal.py` chama `telas(db, out)`
ANTES de `montar_grupos` (as abas estão em `_dp_grupos.GRUPOS`) e inclui `router`.

Onde cada coisa mora (cavado, não suposto — `docs/dgx/lacunas/dp_rh.md`):
- Foto: `employees.foto_url` (0/63 preenchidos; só o sync Sólides escrevia). Serviço
  `hr/services/foto_colaborador.py` grava em `UPLOADS_DIR/employees/<id>.<ext>` e a url RELATIVA
  que `cracha_pdf.foto_path` já resolve — o crachá da F6 passa a sair com foto sem mudar.
- Ficha: NÃO cria tabela. Lê as 14 fontes que já existem (employees, employee_dp, alocações da F5,
  benefícios da F3, descontos/vales da F6, ASO, cursos RH + vigilante, disciplina, afastamentos,
  férias, uniforme/EPI, equipamentos) e devolve seções no painel de resultado do form.
- Certificados: `training_certificates.expires_at` (nunca lido por tela) ∪ `vigilante_cursos.
  vence_em` (frente 05) ∪ validades da própria ficha (CNV, curso de vigilante, CNH, porte).
- Turnover: fórmula do DGX, ((admitidos + desligados) / 2) / headcount do período, por mês e
  por gênero — `turnover_service` só tinha a taxa trimestral global.
- Cargo: `cct_cargos` (o cadastro real, F2) ganha `cbo`, `tipo_servico`, `exige_cnh`, `exige_cnv`,
  `exige_porte_arma` — o DGX exige CBO/CBO-RAIS e tipo de serviço no cargo e flags na função.
- Termo disciplinar: `hr/services/termo_disciplinar_pdf.py` veste `document_text` (já hasheado e
  assinado) com a marca; o botão vive na linha de `disc-medidas` (rh.py).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from modules.operacional.controllers.redesign_data_controller import S, _fmtdate, b, brl, doc, initials, t

_ND = "#0F1B3A"
_ACT = "/api/v1/redesign/action/"
_CLT = "coalesce(status,'') NOT IN ('candidato','pj_ativo','pj_inativo') AND coalesce(is_homologacao,false)=false"

DDL = (
    "ALTER TABLE cct_cargos ADD COLUMN IF NOT EXISTS cbo varchar(10)",
    "ALTER TABLE cct_cargos ADD COLUMN IF NOT EXISTS tipo_servico varchar(20)",
    "ALTER TABLE cct_cargos ADD COLUMN IF NOT EXISTS exige_cnh boolean NOT NULL DEFAULT false",
    "ALTER TABLE cct_cargos ADD COLUMN IF NOT EXISTS exige_cnv boolean NOT NULL DEFAULT false",
    "ALTER TABLE cct_cargos ADD COLUMN IF NOT EXISTS exige_porte_arma boolean NOT NULL DEFAULT false",
)
_ensured = False  # ponytail: DDL idempotente uma vez por processo — ALTER TABLE pega lock mesmo sem mudar nada
TIPOS_SERVICO = ["Patrimonial", "Administrativo", "Limpeza", "Escolta", "Outros"]

router = APIRouter()


async def _ensure(db: AsyncSession) -> None:
    global _ensured
    if _ensured:
        return
    for s in DDL:
        await db.execute(text(s))
    await db.commit()
    _ensured = True


def _gate_dp(current_user: CurrentActiveUser) -> None:
    from .departamento_pessoal import _require_modulo_dp  # lazy: departamento_pessoal importa este módulo

    _require_modulo_dp(current_user)


def _uuid(v) -> str:
    try:
        return str(UUID(str(v or "").strip()))
    except ValueError:
        raise HTTPException(status_code=422, detail="Selecione o colaborador.")


def _fmt(v):
    if v is None or v == "":
        return "—"
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, date):
        return _fmtdate(v)
    if isinstance(v, Decimal):
        return brl(v)
    return str(v)


# ----------------------------------------------------------------------------- régua de validade
def situacao_validade(vence_em: date | None, hoje: date | None = None) -> tuple[str, str]:
    """(rótulo, tom) — Não expira · Vencido · Vence em ≤30/≤60/≤90 · Ativo. Régua única para
    certificado do RH, curso do vigilante e validades da ficha (CNV/CNH/porte)."""
    hoje = hoje or date.today()
    if vence_em is None:
        return "Não expira", "mut"
    d = (vence_em - hoje).days
    if d < 0:
        return f"Vencido há {-d} d", "bad"
    if d <= 30:
        return f"Vence em {d} d", "bad"
    if d <= 60:
        return f"Vence em {d} d", "warn"
    if d <= 90:
        return f"Vence em {d} d", "info"
    return "Ativo", "ok"


def turnover(admitidos: int, desligados: int, headcount: int) -> float:
    """Fórmula do DGX (medida em 24/09: 1 admitido, 0 desligados, 1 no quadro → 0,50)."""
    return round(((admitidos + desligados) / 2) / headcount, 2) if headcount else 0.0


# ----------------------------------------------------------------------------- telas
async def _opt_pessoas(db: AsyncSession, so_ativos: bool = False) -> list[dict]:
    where = "status = 'ativo'" if so_ativos else "data_demissao IS NULL"
    rows = (
        await db.execute(
            text(f"SELECT id::text, nome, coalesce(matricula,''), coalesce(status,'') FROM employees WHERE {where} AND {_CLT} ORDER BY nome")
        )
    ).fetchall()
    return [{"value": r[0], "label": f"{r[1]}" + (f" · {r[2]}" if r[2] else "") + ("" if r[3] == "ativo" else f" ({r[3]})")} for r in rows]


async def _tela_fotos(db: AsyncSession, out: dict) -> None:
    from modules.people_management.hr.services.cracha_pdf import foto_path

    rows = (
        await db.execute(
            text(
                f"SELECT id::text, nome, coalesce(matricula,'—'), coalesce(cargo,'—'), foto_url, updated_at "
                f"FROM employees WHERE status = 'ativo' AND {_CLT} ORDER BY nome"
            )
        )
    ).fetchall()
    com = [r for r in rows if foto_path(r[4])]
    linhas = []
    for r in rows:
        tem = foto_path(r[4]) is not None
        linhas.append(
            {
                "cells": [t(r[1], 600, _ND, initials(r[1])), t(r[2]), t(r[3]), b("com foto", "ok") if tem else b("sem foto", "bad"), t(r[4] if tem else "—")],
                "filtro": "com foto" if tem else "sem foto",
                "docs": [doc("Foto", f"/api/v1/redesign/colaboradores/{r[0]}/foto", fmt="jpg", filename=f"foto-{r[2]}.jpg")] if tem else [],
            }
        )
    out["colaboradores-fotos"] = {
        "title": "Fotos dos colaboradores",
        "sub": f"{len(com)} de {len(rows)} ativos com foto · a foto alimenta o crachá (Admissão & Cadastro → Crachás em lote) e a ficha",
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar colaborador…",
        "grid": "2fr 0.8fr 1.4fr 0.9fr 1.6fr",
        "cols": ["Colaborador", "Matrícula", "Cargo", "Foto", "Arquivo"],
        "rows": linhas,
        "ctaTo": "colaborador-foto",
    }
    out["colaborador-foto"] = {
        "title": "Enviar foto do colaborador",
        "sub": "JPEG, PNG ou WebP até 5 MB — rosto de frente, fundo claro (é a foto do crachá). Substitui a anterior.",
        "cta": "Enviar foto",
        "type": "form",
        "submit": {"endpoint": _ACT + "colaborador-foto", "okMsg": "Foto gravada.", "multipart": True, "showResult": True},
        "fields": [
            {"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2", "ph": "Selecione", "options": await _opt_pessoas(db)},
            {"key": "foto", "label": "Foto*", "type": "file", "accept": "image/jpeg,image/png,image/webp", "span": "span 2"},
        ],
    }
    out["colaboradores-fotos-lote"] = {
        "title": "Fotos em lote (ZIP)",
        "sub": "Um ZIP com uma imagem por pessoa, batizada pela MATRÍCULA (ex.: 85.jpg), pelo CPF só com dígitos "
        "(03527554238.jpg) ou pelo id. Quem não casar aparece no resultado — nada é inventado.",
        "cta": "Importar fotos",
        "type": "form",
        "submit": {"endpoint": _ACT + "colaboradores-fotos-lote", "okMsg": "Lote processado.", "multipart": True, "showResult": True},
        "fields": [{"key": "arquivo", "label": "ZIP*", "type": "file", "accept": ".zip,application/zip", "span": "span 2"}],
    }


async def _tela_ficha(db: AsyncSession, out: dict) -> None:
    out["ficha-colaborador"] = {
        "title": "Ficha do colaborador",
        "sub": "A pessoa inteira numa tela: dados, contrato, documentos, endereço, banco, alocação, dependentes, "
        "benefícios, descontos, ASO, cursos, disciplina, afastamentos, férias, uniforme/EPI e equipamentos — "
        "lidos das fontes que a folha e o eSocial já usam. Só leitura; para editar, cada aba do grupo.",
        "cta": "Abrir ficha",
        "type": "form",
        "submit": {"endpoint": _ACT + "ficha-colaborador", "okMsg": "Ficha aberta.", "showResult": True},
        "fields": [{"key": "employee_id", "label": "Colaborador*", "type": "select", "span": "span 2", "ph": "Selecione", "options": await _opt_pessoas(db)}],
    }


async def certificados(db: AsyncSession, hoje: date | None = None) -> list[dict]:
    """União das três fontes de validade. Cada item: nome, employee_id, item, origem, conclusao, vence_em."""
    hoje = hoje or date.today()
    itens: list[dict] = []
    for r in (
        await db.execute(
            text(
                "SELECT e.id::text, e.nome, coalesce(c.name,'curso'), tc.issued_at::date, tc.expires_at::date, tc.status::text "
                "FROM training_certificates tc JOIN employees e ON e.id = tc.employee_id "
                "LEFT JOIN training_courses c ON c.id = tc.course_id WHERE coalesce(tc.status::text,'') <> 'revoked'"
            )
        )
    ).fetchall():
        itens.append({"employee_id": r[0], "nome": r[1], "item": r[2], "origem": "RH · certificado", "conclusao": r[3], "vence_em": r[4]})
    for r in (
        await db.execute(
            text(
                "SELECT e.id::text, e.nome, v.tipo, v.data_conclusao, v.vence_em FROM vigilante_cursos v JOIN employees e ON e.id = v.employee_id"
            )
        )
    ).fetchall():
        itens.append({"employee_id": r[0], "nome": r[1], "item": (r[2] or "curso").replace("_", " "), "origem": "vigilante", "conclusao": r[3], "vence_em": r[4]})
    for r in (
        await db.execute(
            text(
                f"SELECT id::text, nome, cnv_validade, curso_vigilante_validade, cnh_validade, porte_arma_validade "
                f"FROM employees WHERE status='ativo' AND {_CLT}"
            )
        )
    ).fetchall():
        for col, rotulo in ((2, "CNV"), (3, "curso de vigilante"), (4, "CNH"), (5, "porte de arma")):
            if r[col]:
                itens.append({"employee_id": r[0], "nome": r[1], "item": rotulo, "origem": "ficha", "conclusao": None, "vence_em": r[col]})
    for it in itens:
        it["situacao"], it["tom"] = situacao_validade(it["vence_em"], hoje)
    itens.sort(key=lambda x: (x["vence_em"] or date.max, x["nome"]))
    return itens


async def _tela_certificados(db: AsyncSession, out: dict) -> None:
    itens = await certificados(db)
    venc = sum(1 for i in itens if i["tom"] == "bad" and i["situacao"].startswith("Vencido"))
    v30 = sum(1 for i in itens if i["situacao"].startswith("Vence") and i["tom"] == "bad")
    out["certificados-vencimento"] = {
        "title": "Cursos e certificados — validade",
        "sub": f"{len(itens)} item(ns) · {venc} vencido(s) · {v30} vencem em ≤ 30 dias · régua: vencido / ≤30 / ≤60 / ≤90 / ativo / não expira "
        "· fontes: certificados do RH, cursos do vigilante e validades da ficha (CNV, CNH, porte)"
        + (" · aguardando dado: nenhum certificado emitido pelo RH ainda" if not any(i["origem"].startswith("RH") for i in itens) else ""),
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar pessoa ou curso…",
        "grid": "2fr 1.4fr 1fr 0.9fr 0.9fr 1.1fr",
        "cols": ["Colaborador", "Curso / certificado", "Origem", "Conclusão", "Vence em", "Situação"],
        "rows": [
            {
                "cells": [t(i["nome"], 600, _ND, initials(i["nome"])), t(i["item"]), t(i["origem"]), t(_fmtdate(i["conclusao"])), t(_fmtdate(i["vence_em"])), b(i["situacao"], i["tom"])],
                "filtro": "vencido" if i["situacao"].startswith("Vencido") else ("vence em 90 d" if i["situacao"].startswith("Vence") else i["situacao"].lower()),
            }
            for i in itens
        ]
        or [],
    }


async def serie_turnover(db: AsyncSession, meses: int = 12, hoje: date | None = None) -> list[dict]:
    """Por mês (mais antigo → mais novo): admitidos, desligados, quadro no fim do mês, turnover DGX."""
    hoje = hoje or date.today()
    out = []
    ini = date(hoje.year, hoje.month, 1)
    for k in range(meses - 1, -1, -1):
        m = ini
        for _ in range(k):
            m = (m - timedelta(days=1)).replace(day=1)
        fim = (m.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        r = (
            await db.execute(
                text(
                    f"SELECT count(*) FILTER (WHERE data_admissao BETWEEN :i AND :f), "
                    f"count(*) FILTER (WHERE coalesce(data_demissao, data_desligamento) BETWEEN :i AND :f), "
                    # quadro no fim do mês: admitido até lá e (desligado depois OU ainda no quadro hoje).
                    # 15 inativos/demitidos SEM data de demissão (medido 24/09) não entram — sem data
                    # não há como colocá-los no tempo; o subtítulo conta.
                    f"count(*) FILTER (WHERE data_admissao <= :f AND (coalesce(data_demissao, data_desligamento) > :f "
                    f"OR (coalesce(data_demissao, data_desligamento) IS NULL AND status IN ('ativo','afastado_inss','suspenso','ferias')))) "
                    f"FROM employees WHERE {_CLT} AND data_admissao IS NOT NULL"
                ),
                {"i": m, "f": fim},
            )
        ).first()
        adm, desl, quadro = int(r[0] or 0), int(r[1] or 0), int(r[2] or 0)
        out.append({"mes": m, "admitidos": adm, "desligados": desl, "quadro": quadro, "turnover": turnover(adm, desl, quadro + desl)})
    return out


async def _tela_turnover(db: AsyncSession, out: dict) -> None:
    serie = await serie_turnover(db, 12)
    ult6 = serie[-6:]
    adm12, desl12 = sum(x["admitidos"] for x in serie), sum(x["desligados"] for x in serie)
    quadro = serie[-1]["quadro"]
    g = (
        await db.execute(
            text(
                f"SELECT coalesce(sexo,'—'), count(*) FILTER (WHERE status='ativo'), "
                f"count(*) FILTER (WHERE coalesce(data_demissao, data_desligamento) >= CURRENT_DATE - INTERVAL '12 months') "
                f"FROM employees WHERE {_CLT} GROUP BY 1 ORDER BY 1"
            )
        )
    ).fetchall()
    sem_motivo = (
        await db.execute(
            text(
                f"SELECT count(*) FROM employees WHERE {_CLT} AND coalesce(data_demissao, data_desligamento) >= CURRENT_DATE - INTERVAL '12 months' "
                "AND coalesce(motivo_desligamento,'') = ''"
            )
        )
    ).scalar() or 0
    sem_data = (
        await db.execute(
            text(f"SELECT count(*) FROM employees WHERE {_CLT} AND status IN ('demitido','inativo') AND coalesce(data_demissao, data_desligamento) IS NULL")
        )
    ).scalar() or 0
    rot = {"M": "Masculino", "F": "Feminino"}
    out["turnover-dashboard"] = {
        "title": "Turnover",
        "sub": f"12 meses até {_fmtdate(date.today())} · fórmula (DGX): (admitidos + desligados) ÷ 2 ÷ quadro do período · "
        f"quadro = CLT no quadro ao fim do mês (PJ, candidatos e homologação fora) · {sem_motivo} desligado(s) sem motivo registrado"
        + (f" · {sem_data} desligado(s)/inativo(s) SEM data de demissão (fora da série — cadastrar a data)" if sem_data else ""),
        "cta": "—",
        "type": "dash",
        "panelGrid": "1fr 1fr",
        "kpis": [
            {"v": str(quadro), "l": "Ativos (CLT)", "icon": "M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2M9 3a4 4 0 1 1 0 8 4 4 0 0 1 0-8", "color": _ND},
            {"v": str(adm12), "l": "Admitidos · 12 m", "icon": "M12 5v14M5 12h14", "color": "#16A34A"},
            {"v": str(desl12), "l": "Desligados · 12 m", "icon": "M5 12h14", "color": "#B91C1C"},
            {"v": f"{turnover(adm12, desl12, quadro + desl12):.2f}".replace(".", ","), "l": "Turnover · 12 m", "icon": "M3 3v18h18", "color": "#B45309"},
        ],
        "panels": [
            {
                "title": "Mensal (últimos 6 meses) — admitidos · desligados · quadro · turnover",
                "rows": [
                    {"left": x["mes"].strftime("%m/%Y"), "right": f"+{x['admitidos']} · −{x['desligados']} · {x['quadro']} · {x['turnover']:.2f}".replace(".", ","), **S["bad" if x["desligados"] > x["admitidos"] else ("ok" if x["admitidos"] else "mut")]}
                    for x in ult6
                ],
            },
            {
                "title": "Gênero — ativos · desligados 12 m",
                "rows": [{"left": rot.get(r[0], r[0]), "right": f"{int(r[1] or 0)} ativos · {int(r[2] or 0)} desligados", **S["info"]} for r in g]
                or [{"left": "aguardando dado", "right": "—", **S["mut"]}],
            },
        ],
    }


async def _tela_cargos(db: AsyncSession, out: dict) -> None:
    rows = (
        await db.execute(
            text(
                "SELECT c.id::text, c.cargo_nome, c.piso_salarial, c.cbo, c.tipo_servico, c.exige_cnh, c.exige_cnv, c.exige_porte_arma, "
                "(SELECT count(*) FROM employees e WHERE e.cct_cargo_id = c.id AND e.status='ativo') "
                "FROM cct_cargos c WHERE c.is_active ORDER BY 9 DESC, c.cargo_nome"
            )
        )
    ).fetchall()
    out["cargos-atributos"] = {
        "title": "Cargos — CBO e exigências",
        "sub": f"{len(rows)} cargos da CCT · {sum(1 for r in rows if r[3])} com CBO · o DGX exige CBO e tipo de serviço no cargo e "
        "CNH/CNV na função; aqui tudo vive em cct_cargos (F2). Aba «Editar cargo» grava.",
        "cta": "—",
        "type": "table",
        "searchHint": "Buscar cargo…",
        "grid": "2fr 1fr 0.9fr 1fr 0.6fr 0.6fr 0.7fr 0.6fr",
        "cols": ["Cargo", "Piso", "CBO", "Tipo de serviço", "CNH", "CNV", "Porte", "Ativos"],
        "rows": [
            {
                "cells": [t(r[1], 600, _ND), t(brl(r[2]) if r[2] is not None else "—"), t(r[3] or "—"), t(r[4] or "—"), b("exige", "warn") if r[5] else t("—"), b("exige", "warn") if r[6] else t("—"), b("exige", "warn") if r[7] else t("—"), t(str(int(r[8] or 0)))],
                "filtro": r[4] or "sem tipo",
            }
            for r in rows
        ],
        "ctaTo": "cargo-atributos-form",
    }
    out["cargo-atributos-form"] = {
        "title": "Editar cargo — CBO e exigências",
        "sub": "CBO com 6 dígitos (ex.: 5174-20 → 517420). Só preenche o que você informar; campo vazio não apaga.",
        "cta": "Gravar",
        "type": "form",
        "submit": {"endpoint": _ACT + "cargo-atributos-salvar", "okMsg": "Cargo atualizado."},
        "fields": [
            {"key": "cargo_id", "label": "Cargo*", "type": "select", "span": "span 2", "ph": "Selecione", "options": [{"value": r[0], "label": f"{r[1]}" + (f" · CBO {r[3]}" if r[3] else "")} for r in rows]},
            {"key": "cbo", "label": "CBO", "type": "text", "span": "span 1", "ph": "517420"},
            {"key": "tipo_servico", "label": "Tipo de serviço", "type": "select", "span": "span 1", "options": [{"value": x, "label": x} for x in TIPOS_SERVICO]},
            {"key": "exige_cnh", "label": "Exige CNH", "type": "select", "span": "span 1", "options": [{"value": "nao", "label": "Não"}, {"value": "sim", "label": "Sim"}]},
            {"key": "exige_cnv", "label": "Exige CNV", "type": "select", "span": "span 1", "options": [{"value": "nao", "label": "Não"}, {"value": "sim", "label": "Sim"}]},
            {"key": "exige_porte_arma", "label": "Exige porte de arma", "type": "select", "span": "span 1", "options": [{"value": "nao", "label": "Não"}, {"value": "sim", "label": "Sim"}]},
        ],
    }


async def telas(db: AsyncSession, out: dict) -> None:
    await _ensure(db)
    for fn in (_tela_fotos, _tela_ficha, _tela_certificados, _tela_turnover, _tela_cargos):
        try:
            await fn(db, out)
        except Exception as exc:  # noqa: BLE001 — uma tela quebrada não derruba o módulo
            await db.rollback()
            import logging

            logging.getLogger(__name__).warning("dgx t1 %s: %s", fn.__name__, exc)


# ----------------------------------------------------------------------------- ficha
async def ficha(db: AsyncSession, employee_id: str) -> dict:
    """Seções da ficha (dict de dicts/listas) — o painel de resultado do redesign renderiza
    `{secao: {campo: valor}}` e `[{nome, valor}]`. Só leitura."""
    e = (await db.execute(text("SELECT * FROM employees WHERE id::text = :e"), {"e": employee_id})).mappings().first()
    if not e:
        raise HTTPException(status_code=404, detail="Colaborador não encontrado.")
    dp = (await db.execute(text("SELECT * FROM employee_dp WHERE employee_id::text = :e LIMIT 1"), {"e": employee_id})).mappings().first() or {}
    cct = (await db.execute(text("SELECT cargo_nome, piso_salarial, cbo FROM cct_cargos WHERE id = :c"), {"c": e.get("cct_cargo_id")})).first() if e.get("cct_cargo_id") else None
    from modules.people_management.hr.services.cracha_pdf import foto_path

    def kv(pairs) -> dict:
        return {k: _fmt(v) for k, v in pairs if v not in (None, "", [], {})} or {"—": "aguardando dado"}

    deps = e.get("dependentes") or []
    if isinstance(deps, str):
        import json

        deps = json.loads(deps or "[]")
    sec: dict = {
        "dados_gerais": kv(
            [("nome", e["nome"]), ("matricula", e.get("matricula")), ("cpf", e.get("cpf")), ("nascimento", e.get("data_nascimento")), ("sexo", e.get("sexo")),
             ("estado_civil", e.get("estado_civil")), ("nacionalidade", e.get("nacionalidade")), ("naturalidade", e.get("naturalidade")),
             ("nome_da_mae", e.get("nome_mae")), ("nome_do_pai", e.get("nome_pai")), ("grau_de_instrucao", dp.get("grau_instrucao")), ("raca_cor", dp.get("raca_cor")),
             ("pcd", dp.get("deficiencia")), ("tipo_de_deficiencia", dp.get("tipo_deficiencia")), ("status", e.get("status")), ("foto", "sim" if foto_path(e.get("foto_url")) else "sem foto"),
             ("cracha", e.get("cracha_numero"))]
        ),
        "contrato": kv(
            [("cargo", e.get("cargo")), ("funcao_cct", cct[0] if cct else None), ("piso_cct", cct[1] if cct else None), ("cbo", cct[2] if cct else None),
             ("departamento", e.get("departamento")), ("setor", e.get("setor")), ("centro_de_custo", e.get("centro_custo")), ("gestor", e.get("gestor_nome")),
             ("admissao", e.get("data_admissao")), ("tipo_de_contrato", e.get("tipo_contrato")), ("regime", e.get("regime_trabalho")), ("jornada", e.get("jornada_trabalho")),
             ("carga_semanal", e.get("carga_horaria_semanal")), ("escala", e.get("escala_padrao")), ("turno", e.get("turno_padrao")), ("salario_base", e.get("salario_base")),
             ("insalubridade_pct", e.get("insalubridade_percentual")), ("periculosidade_pct", e.get("periculosidade_percentual")), ("adicional_ronda_pct", e.get("adicional_ronda_percentual")),
             ("demissao", e.get("data_demissao") or e.get("data_desligamento")), ("motivo_desligamento", e.get("motivo_desligamento"))]
        ),
        "documentos": kv(
            [("rg", e.get("rg")), ("orgao_uf", f"{e.get('rg_orgao') or ''} {e.get('rg_uf') or ''}".strip()), ("ctps", e.get("ctps_numero") or dp.get("ctps_numero")),
             ("ctps_serie_uf", f"{e.get('ctps_serie') or dp.get('ctps_serie') or ''} {e.get('ctps_uf') or dp.get('ctps_uf') or ''}".strip()), ("pis", e.get("pis") or dp.get("pis_pasep")),
             ("titulo_de_eleitor", e.get("titulo_eleitor")), ("zona_secao", f"{e.get('zona_eleitoral') or ''}/{e.get('secao_eleitoral') or ''}".strip("/")),
             ("reservista", e.get("certificado_reservista")), ("cnh", e.get("cnh_numero")), ("cnh_categoria", e.get("cnh_categoria")), ("cnh_validade", e.get("cnh_validade")),
             ("cnv", e.get("cnv")), ("cnv_validade", e.get("cnv_validade")), ("curso_de_vigilante_validade", e.get("curso_vigilante_validade")),
             ("porte_de_arma", e.get("porte_arma")), ("porte_numero", e.get("porte_arma_numero")), ("porte_validade", e.get("porte_arma_validade"))]
        ),
        "endereco_e_contato": kv(
            [("endereco", " ".join(str(x) for x in (e.get("logradouro"), e.get("numero"), e.get("complemento")) if x)), ("bairro", e.get("bairro")),
             ("cidade_uf", f"{e.get('cidade') or ''}/{e.get('uf') or ''}".strip("/")), ("cep", e.get("cep")), ("email", e.get("email")), ("telefone", e.get("telefone")),
             ("celular", e.get("celular")), ("contato_de_emergencia", e.get("contato_emergencia")), ("telefone_de_emergencia", e.get("telefone_emergencia"))]
        ),
        "banco_e_pix": kv(
            [("pix", e.get("pix_key") or e.get("pix")), ("tipo_da_chave", e.get("pix_key_type")), ("pix_confirmada", e.get("pix_confirmada")),
             ("banco", e.get("banco_codigo") or e.get("banco")), ("agencia", e.get("banco_agencia") or e.get("agencia")), ("conta", e.get("banco_conta") or e.get("conta")),
             ("tipo_de_conta", e.get("banco_tipo") or e.get("tipo_conta")), ("forma_de_pagamento", e.get("tipo_pagamento"))]
        ),
    }
    aloc = (
        await db.execute(
            text(
                "SELECT c.nome, a.funcao, a.data_inicio, a.tipo, a.motivo FROM employee_alocacoes a LEFT JOIN condominios c ON c.id = a.condominio_id "
                "WHERE a.employee_id::text = :e AND a.ativo ORDER BY a.data_inicio DESC LIMIT 3"
            ),
            {"e": employee_id},
        )
    ).fetchall()
    sec["alocacao"] = kv([("posto_atual", e.get("posto_atual_nome")), ("cliente", e.get("cliente_nome")), ("no_posto_desde", e.get("data_inicio_posto"))]) | {
        f"alocacao_{i + 1}": f"{r[0] or '—'} · {r[1] or '—'} · desde {_fmtdate(r[2])}" + (f" · {r[4]}" if r[4] else "") for i, r in enumerate(aloc)
    }
    sec["dependentes"] = [
        {"nome": d.get("nome") or "(sem nome — herdado da Portte)", "valor": f"{d.get('grau') or d.get('tipo') or '—'} · nasc. {d.get('nascimento') or d.get('data_nascimento') or '—'}" + (" · salário-família" if d.get("menor_14") else "")}
        for d in deps
        if isinstance(d, dict)
    ]
    sec["beneficios"] = [
        {"nome": f"{r[0] or '—'}" + (f" · {r[1]}" if r[1] else "") + (f" · {r[4]}" if r[4] else ""), "valor": (f"{brl(r[2])}" if r[2] is not None else "—") + (f" · qtd {r[3]}" if r[3] else "")}
        for r in (
            await db.execute(
                text(
                    "SELECT b.type, coalesce(bt.nome, b.plan_name), coalesce(b.company_contribution, b.valor_unitario), b.quantidade, l.nome "
                    "FROM employee_benefits b LEFT JOIN beneficio_tipos bt ON bt.id = b.beneficio_tipo_id LEFT JOIN beneficio_linhas l ON l.id = b.linha_id "
                    "WHERE b.employee_id::text = :e AND coalesce(b.status,'active') = 'active' ORDER BY b.type"
                ),
                {"e": employee_id},
            )
        ).fetchall()
    ]
    sec["descontos_e_vales"] = [
        {"nome": f"{r[0]} · {r[1] or r[2] or '—'}", "valor": f"{brl(r[3])}" + (f" · parcela {r[4]}/{r[5]}" if r[5] else "")}
        for r in (
            await db.execute(
                text("SELECT tipo, descricao, motivo, valor, parcela_atual, total_parcelas FROM employee_deductions WHERE employee_id::text = :e AND ativo ORDER BY data_inicio DESC"),
                {"e": employee_id},
            )
        ).fetchall()
    ]
    sec["aso"] = [
        {"nome": f"{r[0] or '—'} · {_fmtdate(r[1])}", "valor": f"válido até {_fmtdate(r[2])} · " + ("apto" if r[3] else ("inapto" if r[3] is False else r[4] or "—"))}
        for r in (
            await db.execute(
                text("SELECT tipo, data_realizacao, data_validade, apto, status FROM gp_asos WHERE employee_id::text = :e ORDER BY coalesce(data_realizacao, data_agendamento) DESC NULLS LAST LIMIT 4"),
                {"e": employee_id},
            )
        ).fetchall()
    ]
    sec["cursos_e_certificados"] = [{"nome": f"{i['item']} ({i['origem']})", "valor": f"{_fmtdate(i['vence_em'])} · {i['situacao']}"} for i in await certificados(db) if i["employee_id"] == employee_id]
    sec["disciplina"] = [
        {"nome": f"{(r[0] or '—').replace('_', ' ')} · {_fmtdate(r[1])}", "valor": f"{r[2] or '—'} · {(r[3] or '—').replace('_', ' ')}"}
        for r in (
            await db.execute(
                text("SELECT action_type, incident_date, code, status FROM disciplinary_actions WHERE employee_id::text = :e ORDER BY incident_date DESC NULLS LAST LIMIT 10"),
                {"e": employee_id},
            )
        ).fetchall()
    ]
    sec["afastamentos"] = [
        {"nome": f"{(r[0] or '—').replace('_', ' ')} · {_fmtdate(r[1])}", "valor": (f"retorno {_fmtdate(r[2])}" if r[2] else f"previsto {_fmtdate(r[3])}") + f" · {r[4] or '—'}" + (f" · CID {r[5]}" if r[5] else "")}
        for r in (
            await db.execute(
                text("SELECT tipo, data_inicio, data_retorno, data_fim_prevista, status, cid FROM sst_afastamentos WHERE employee_id::text = :e ORDER BY data_inicio DESC LIMIT 10"),
                {"e": employee_id},
            )
        ).fetchall()
    ]
    sec["ferias"] = [
        {"nome": f"{_fmtdate(r[0])} a {_fmtdate(r[1])}", "valor": f"{r[2] or 0} dias · {r[3] or '—'}"}
        for r in (
            await db.execute(
                text("SELECT start_date, end_date, days_requested, status FROM hr_vacation_requests WHERE employee_id::text = :e ORDER BY start_date DESC LIMIT 6"),
                {"e": employee_id},
            )
        ).fetchall()
    ]
    uni = (
        await db.execute(
            text(
                "SELECT count(*) FILTER (WHERE entregue_em IS NOT NULL AND devolvido_em IS NULL), count(*) FILTER (WHERE entregue_em IS NULL AND status <> 'cancelado') "
                "FROM sst_uniforme_entregas WHERE employee_id::text = :e"
            ),
            {"e": employee_id},
        )
    ).first()
    eq = (
        await db.execute(
            text("SELECT count(*) FROM equipamentos_controlados_alocacoes WHERE employee_id::text = :e AND devolvido_em IS NULL"),
            {"e": employee_id},
        )
    ).scalar()
    sec["uniforme_epi_e_equipamentos"] = {"uniformes_epi_em_posse": int(uni[0] or 0), "uniformes_epi_pendentes": int(uni[1] or 0), "armamento_colete_em_posse": int(eq or 0)}
    return sec


# ----------------------------------------------------------------------------- ações
@router.post("/action/colaborador-foto", dependencies=[Depends(_gate_dp)])
async def rd_colaborador_foto(request: Request, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> dict:
    from modules.people_management.hr.services.foto_colaborador import salvar_foto

    form = await request.form()
    eid = _uuid(form.get("employee_id"))
    f = form.get("foto")
    if f is None or not hasattr(f, "read"):
        raise HTTPException(status_code=422, detail="Escolha o arquivo da foto.")
    try:
        url = await salvar_foto(db, eid, await f.read(), f.content_type, getattr(f, "filename", "") or "")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    nome = (await db.execute(text("SELECT nome FROM employees WHERE id::text = :e"), {"e": eid})).scalar()
    return {"ok": True, "message": f"Foto de {nome} gravada ({url}). O crachá já sai com ela.", "arquivo": url}


@router.post("/action/colaboradores-fotos-lote", dependencies=[Depends(_gate_dp)])
async def rd_fotos_lote(request: Request, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> dict:
    from modules.people_management.hr.services.foto_colaborador import importar_zip

    form = await request.form()
    f = form.get("arquivo")
    if f is None or not hasattr(f, "read"):
        raise HTTPException(status_code=422, detail="Escolha o ZIP.")
    conteudo = await f.read()
    if len(conteudo) > 200 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="ZIP acima de 200 MB.")
    try:
        r = await importar_zip(db, conteudo)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {
        "ok": True,
        "message": f"{len(r['ok'])} foto(s) gravada(s) · {len(r['nao_encontrados'])} sem colaborador correspondente · {len(r['ignorados'])} ignorado(s).",
        "gravadas": r["ok"],
        "nao_encontrados": r["nao_encontrados"],
        "ignorados": r["ignorados"],
    }


@router.get("/colaboradores/{employee_id}/foto", summary="Foto do colaborador (arquivo)")
async def rd_colaborador_foto_get(employee_id: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)) -> FileResponse:
    from modules.people_management.hr.services.cracha_pdf import foto_path

    url = (await db.execute(text("SELECT foto_url FROM employees WHERE id::text = :e"), {"e": _uuid(employee_id)})).scalar()
    p = foto_path(url)
    if not p:
        raise HTTPException(status_code=404, detail="Colaborador sem foto.")
    return FileResponse(p)


@router.post("/action/ficha-colaborador", dependencies=[Depends(_gate_dp)])
async def rd_ficha(current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)) -> dict:
    sec = await ficha(db, _uuid(payload.get("employee_id")))
    return {"ok": True, "message": f"Ficha de {sec['dados_gerais'].get('nome', '—')}.", **sec}


@router.get("/disciplina/{action_id}/pdf", summary="Termo de advertência/suspensão (PDF padrão-ouro)")
async def rd_termo_pdf(action_id: str, current_user: CurrentActiveUser, db: AsyncSession = Depends(get_db)):
    from modules.people_management.hr.services.termo_disciplinar_pdf import montar_termo

    a = (await db.execute(text("SELECT * FROM disciplinary_actions WHERE id::text = :i"), {"i": _uuid(action_id)})).mappings().first()
    if not a:
        raise HTTPException(status_code=404, detail="Medida não encontrada.")
    if not a.get("document_text"):
        raise HTTPException(status_code=409, detail="Medida ainda sem texto gerado — submeta/aprove primeiro.")
    # chaves que `pdf_branding.bloco_autenticidade_assinaturas` lê: signer_name, signer_type, signed_at, signature_hash
    assin = (
        await db.execute(
            text(
                "SELECT signer_name, lower(coalesce(signer_type,'')) AS signer_type, created_at AS signed_at, signature_hash FROM digital_signatures "
                "WHERE document_type = 'disciplinary_action' AND document_id = :i AND coalesce(is_valid, true) ORDER BY created_at"
            ),
            {"i": a["id"]},
        )
    ).mappings().all()
    pdf = montar_termo(dict(a), [dict(s) for s in assin])
    return Response(content=pdf, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="termo-{a.get("code") or action_id[:8]}.pdf"'})


@router.post("/action/cargo-atributos-salvar", dependencies=[Depends(_gate_dp)])
async def rd_cargo_atributos(current_user: CurrentActiveUser, payload: dict = Body(...), db: AsyncSession = Depends(get_db)) -> dict:
    await _ensure(db)
    cid = _uuid(payload.get("cargo_id"))
    cbo = "".join(ch for ch in str(payload.get("cbo") or "") if ch.isdigit())
    if cbo and len(cbo) != 6:
        raise HTTPException(status_code=422, detail="CBO tem 6 dígitos (ex.: 517420).")
    ts = (payload.get("tipo_servico") or "").strip()
    if ts and ts not in TIPOS_SERVICO:
        raise HTTPException(status_code=422, detail="Tipo de serviço inválido.")
    sets, params = [], {"c": cid}
    if cbo:
        sets.append("cbo = :cbo")
        params["cbo"] = cbo
    if ts:
        sets.append("tipo_servico = :ts")
        params["ts"] = ts
    for k in ("exige_cnh", "exige_cnv", "exige_porte_arma"):
        v = (payload.get(k) or "").strip().lower()
        if v in ("sim", "nao", "não", "true", "false"):
            sets.append(f"{k} = :{k}")
            params[k] = v in ("sim", "true")
    if not sets:
        raise HTTPException(status_code=422, detail="Nada para gravar.")
    r = await db.execute(text(f"UPDATE cct_cargos SET {', '.join(sets)}, updated_at = now() WHERE id::text = :c RETURNING cargo_nome"), params)
    nome = r.scalar()
    if not nome:
        raise HTTPException(status_code=404, detail="Cargo não encontrado.")
    await db.commit()
    return {"ok": True, "message": f"{nome}: {len(sets)} atributo(s) gravado(s)."}
