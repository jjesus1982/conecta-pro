"""Fase 5.3 — Registry de regras proativas (SQL determinístico, read-only).

Cada Regra re-deriva sua condição direto da FONTE (idempotente por natureza).
A Regra DECIDE se dispara, para quem e a severidade — o LLM (redator) só escreve
o texto depois. Fail-closed: regra sem destinatário não é registrada.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

FALLBACK_CAIXA_SEM_FOLHA = 10000.0  # spec: CNPJ sem folha própria → R$ 10k fixo


@dataclass(frozen=True)
class Achado:
    """Uma ocorrência concreta de uma condição. `dados` carrega os números EXATOS
    da query (groundedness do redator/template)."""
    correlation_id: str
    dados: dict


@dataclass(frozen=True)
class Regra:
    nome: str
    familia: str
    severidade: str  # info | atencao | critico
    roles_destino: tuple[str, ...]
    action_url: str
    detectar: Callable[[AsyncSession], Awaitable[list[Achado]]]
    template: Callable[[dict], tuple[str, str]]  # dados -> (title, body) determinístico


REGISTRY: dict[str, Regra] = {}


def register(regra: Regra) -> None:
    """Registra a regra. Fail-closed: sem roles_destino não entra (nunca dispara órfão)."""
    if not regra.roles_destino:
        logger.warning("[proativo] regra %r sem roles_destino — NÃO registrada", regra.nome)
        return
    REGISTRY[regra.nome] = regra


# ─────────────────────────── posto_descoberto ───────────────────────────
async def _detectar_posto_descoberto(db: AsyncSession) -> list[Achado]:
    rows = (await db.execute(text(
        "SELECT id::text AS id, coalesce(name,'') AS name, "
        "       required_headcount AS req, current_headcount AS cur "
        "FROM posts "
        "WHERE is_active AND current_headcount < required_headcount"
    ))).mappings().all()
    out = []
    for r in rows:
        faltam = int(r["req"]) - int(r["cur"])
        out.append(Achado(
            correlation_id=f"posto_descoberto:{r['id']}",
            dados={"post_id": r["id"], "posto": r["name"], "faltam": faltam,
                   "req": int(r["req"]), "cur": int(r["cur"])},
        ))
    return out


def _tpl_posto(d: dict) -> tuple[str, str]:
    return (
        f"Posto descoberto: {d['posto']}",
        f"O posto {d['posto']} está com {d['faltam']} vaga(s) descoberta(s) "
        f"({d['cur']}/{d['req']}). Verificar cobertura.",
    )


register(Regra(
    nome="posto_descoberto", familia="operacional", severidade="critico",
    roles_destino=("admin", "gerente_operacional", "supervisor"),
    action_url="/modulos/operacional/postos",
    detectar=_detectar_posto_descoberto, template=_tpl_posto,
))


# ─────────────────────────── certidao_vencendo ───────────────────────────
async def _detectar_certidao_vencendo(db: AsyncSession) -> list[Achado]:
    # TZ canônico: dia-de-negócio = Manaus, NUNCA current_date (sessão Postgres em UTC) —
    # janela diária 20h-23h59 Manaus cairia no dia UTC seguinte e erraria o corte.
    rows = (await db.execute(text(
        "SELECT id::text AS id, coalesce(name,'certidão') AS name, "
        "       expiry_date, "
        "       (expiry_date - (now() AT TIME ZONE 'America/Manaus')::date) AS dias "
        "FROM ged_certidoes "
        "WHERE expiry_date <= (now() AT TIME ZONE 'America/Manaus')::date + 30"
    ))).mappings().all()
    out = []
    for r in rows:
        dias = int(r["dias"])
        vencida = dias < 0
        out.append(Achado(
            correlation_id=f"certidao:{r['id']}:{r['expiry_date']}",
            dados={"cert_id": r["id"], "nome": r["name"], "dias": dias,
                   "expiry": str(r["expiry_date"]), "vencida": vencida,
                   # per-achado: vencida é sempre crítico; a vencer (<=30d) mantém atencao
                   "severidade": "critico" if vencida else "atencao"},
        ))
    return out


def _tpl_certidao(d: dict) -> tuple[str, str]:
    if d["vencida"]:
        return (f"Certidão VENCIDA: {d['nome']}",
                f"A certidão {d['nome']} venceu em {d['expiry']} "
                f"(há {abs(d['dias'])} dia(s)). Regularizar.")
    return (f"Certidão vencendo: {d['nome']}",
            f"A certidão {d['nome']} vence em {d['dias']} dia(s) ({d['expiry']}).")


register(Regra(
    nome="certidao_vencendo", familia="documentos", severidade="atencao",
    roles_destino=("admin",),
    action_url="/modulos/juridico/certidoes",
    detectar=_detectar_certidao_vencendo, template=_tpl_certidao,
))


# ─────────────────────────── caixa_baixo_cnpj ───────────────────────────
async def _detectar_caixa_baixo(db: AsyncSession) -> list[Achado]:
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from modules.financial.services.caixa_service import caixa_por_cnpj

    caixa = await caixa_por_cnpj(db)
    competencia = datetime.now(ZoneInfo("America/Manaus")).strftime("%Y-%m")
    out = []
    for natureza in ("eletronica", "patrimonial"):
        bloco = caixa.get(natureza) or {}
        saldo = bloco.get("saldo")
        if saldo is None:  # sem saldo disponível → silêncio honesto (não fabricar)
            continue
        folha = bloco.get("folha")
        limiar = float(folha) if folha not in (None, 0) else FALLBACK_CAIXA_SEM_FOLHA
        if float(saldo) < limiar:
            slug = bloco.get("slug") or natureza
            out.append(Achado(
                correlation_id=f"caixa_baixo:{slug}:{competencia}",
                dados={"cnpj": bloco.get("nome") or natureza, "slug": slug,
                       "saldo": float(saldo), "limiar": limiar,
                       "banco": bloco.get("banco"),
                       "usou_fallback": folha in (None, 0)},
            ))
    return out


def _tpl_caixa(d: dict) -> tuple[str, str]:
    from modules.notifications.proativo.redator import _brl

    base = ("folha do CNPJ" if not d["usou_fallback"] else "piso R$ 10.000")
    return (
        f"Caixa baixo: {d['cnpj']}",
        f"O caixa de {d['cnpj']} ({d['banco']}) está em R$ {_brl(d['saldo'])}, "
        f"abaixo do limiar de R$ {_brl(d['limiar'])} ({base}).",
    )


register(Regra(
    nome="caixa_baixo_cnpj", familia="financeiro", severidade="critico",
    roles_destino=("admin",),  # LGPD: financeiro SÓ diretoria
    action_url="/modulos/financeiro/caixa",
    detectar=_detectar_caixa_baixo, template=_tpl_caixa,
))


# ─────────────────────────── aging_reforcado ───────────────────────────
async def _detectar_aging(db: AsyncSession) -> list[Achado]:
    # MESMA fonte/filtro de notifications.reconciliar_alertas (não duplica).
    row = (await db.execute(text(
        "SELECT count(*), coalesce(sum(net_value),0) FROM receivable_accounts "
        "WHERE due_date < current_date "
        "AND coalesce(status::text,'') NOT ILIKE '%pag%' "
        "AND coalesce(status::text,'') NOT ILIKE '%cancel%'"))).fetchone()
    n, total = int(row[0] or 0), float(row[1] or 0)
    if n == 0:
        return []
    return [Achado(
        correlation_id="financeiro_aging:portfolio:None",  # namespace do enqueue_alert
        # espelha notifications.tasks.py:61 (mesmo corte do reconciliador)
        dados={"n": n, "total": total,
               "severidade": "critico" if total >= 50000 else "atencao"},
    )]


def _tpl_aging(d: dict) -> tuple[str, str]:
    from modules.notifications.proativo.redator import _brl

    return (
        f"{d['n']} recebível(is) vencido(s)",
        f"Há {d['n']} título(s) vencido(s) em aberto, total R$ {_brl(d['total'])}.",
    )


register(Regra(
    nome="aging_reforcado", familia="financeiro", severidade="atencao",
    roles_destino=("admin",),  # LGPD: financeiro SÓ diretoria
    action_url="/modulos/financeiro/recebiveis",
    detectar=_detectar_aging, template=_tpl_aging,
))


# ─────────────────────────── tributo_a_vencer (B3) ───────────────────────────
async def _detectar_tributo_vencer(db: AsyncSession) -> list[Achado]:
    row = (await db.execute(text(
        "SELECT count(*), coalesce(sum(valor_devido),0) FROM fiscal_obligations "
        "WHERE status='pendente' AND data_vencimento BETWEEN current_date AND current_date + 7"))).fetchone()
    n, total = int(row[0] or 0), float(row[1] or 0)
    if n == 0:
        return []
    return [Achado(correlation_id="financeiro_tributo_vencer:portfolio:None",
                   dados={"n": n, "total": total, "severidade": "atencao"})]


def _tpl_tributo_vencer(d: dict) -> tuple[str, str]:
    from modules.notifications.proativo.redator import _brl
    return (f"{d['n']} tributo(s)/guia(s) a vencer em 7 dias",
            f"{d['n']} obrigação(ões) fiscal(is) pendente(s) vence(m) nos próximos 7 dias, total R$ {_brl(d['total'])}.")


register(Regra(
    nome="tributo_a_vencer", familia="financeiro", severidade="atencao",
    roles_destino=("admin",), action_url="/modulos/financeiro/fiscal",
    detectar=_detectar_tributo_vencer, template=_tpl_tributo_vencer,
))


# ─────────────────────────── concentracao_pagaveis (B3) ───────────────────────────
async def _detectar_pagaveis_7d(db: AsyncSession) -> list[Achado]:
    row = (await db.execute(text(
        "SELECT count(*), coalesce(sum(net_value),0) FROM payable_accounts "
        "WHERE due_date BETWEEN current_date AND current_date + 7 "
        "AND coalesce(status::text,'') NOT ILIKE '%pag%' "
        "AND coalesce(status::text,'') NOT ILIKE '%cancel%'"))).fetchone()
    n, total = int(row[0] or 0), float(row[1] or 0)
    if total < 10000:  # só alerta concentração relevante
        return []
    return [Achado(correlation_id="financeiro_pagaveis_7d:portfolio:None",
                   dados={"n": n, "total": total, "severidade": "critico" if total >= 50000 else "atencao"})]


def _tpl_pagaveis_7d(d: dict) -> tuple[str, str]:
    from modules.notifications.proativo.redator import _brl
    return (f"{d['n']} conta(s) a pagar vencendo em 7 dias",
            f"R$ {_brl(d['total'])} em {d['n']} conta(s) a pagar vence(m) nos próximos 7 dias — planeje o caixa.")


register(Regra(
    nome="concentracao_pagaveis", familia="financeiro", severidade="atencao",
    roles_destino=("admin",), action_url="/modulos/financeiro/pagar",
    detectar=_detectar_pagaveis_7d, template=_tpl_pagaveis_7d,
))


# ─────────────────────────── justificativa_parada ───────────────────────────
async def _detectar_justificativa(db: AsyncSession) -> list[Achado]:
    rows = (await db.execute(text(
        "SELECT id, coalesce(employee_id,'') AS emp, "
        "       EXTRACT(EPOCH FROM (now() - created_at))/3600 AS horas "
        "FROM gp_justifications "
        "WHERE lower(coalesce(status,'')) IN ('pending','pendente') "
        "AND created_at < now() - interval '48 hours'"))).mappings().all()
    out = []
    for r in rows:
        out.append(Achado(
            correlation_id=f"justificativa_parada:{r['id']}",
            dados={"just_id": int(r["id"]), "horas": int(r["horas"] or 0)},
        ))
    return out


def _tpl_justificativa(d: dict) -> tuple[str, str]:
    return (
        "Justificativa de ponto parada",
        f"Uma justificativa de ponto está pendente de análise há {d['horas']}h "
        f"(id {d['just_id']}). Revisar.",
    )


register(Regra(
    nome="justificativa_parada", familia="ponto", severidade="atencao",
    roles_destino=("admin", "gerente_operacional"),
    action_url="/modulos/operacional/ponto/justificativas",
    detectar=_detectar_justificativa, template=_tpl_justificativa,
))


# ─────────────────────────── juridico_prazo (silenciosa até ter dado) ────────
async def _detectar_juridico(db: AsyncSession) -> list[Achado]:
    # TZ canônico: dia-de-negócio = Manaus, NUNCA a data crua da sessão Postgres (UTC).
    # Vocabulário real da tabela é {aberto, cumprido, atrasado} (prazos_service._STATUS_VALIDOS);
    # os dois valores excluídos antes (ver git blame) nunca existem na tabela — exclusão
    # morta que fazia prazos já resolvidos alertarem pra sempre. Só 'cumprido' sai do radar.
    rows = (await db.execute(text(
        "SELECT id::text AS id, coalesce(titulo,'prazo') AS titulo, data_limite, "
        "       (data_limite - (now() AT TIME ZONE 'America/Manaus')::date) AS dias "
        "FROM juridico_prazos "
        "WHERE data_limite <= (now() AT TIME ZONE 'America/Manaus')::date + 7 "
        "AND lower(coalesce(status,'')) NOT IN ('cumprido')"))).mappings().all()
    out = []
    for r in rows:
        out.append(Achado(
            correlation_id=f"juridico_prazo:{r['id']}:{r['data_limite']}",
            dados={"prazo_id": r["id"], "titulo": r["titulo"], "dias": int(r["dias"]),
                   # per-achado: prazo já vencido é sempre crítico; a vencer mantém atencao
                   "severidade": "critico" if int(r["dias"]) < 0 else "atencao"},
        ))
    return out


def _tpl_juridico(d: dict) -> tuple[str, str]:
    return (
        f"Prazo jurídico: {d['titulo']}",
        f"O prazo '{d['titulo']}' vence em {d['dias']} dia(s).",
    )


register(Regra(
    nome="juridico_prazo", familia="juridico", severidade="critico",
    roles_destino=("admin",),
    action_url="/modulos/juridico/prazos",
    detectar=_detectar_juridico, template=_tpl_juridico,
))


# ─────────────────────────── recrutamento_parado (silenciosa até funil) ──────
async def _detectar_recrutamento(db: AsyncSession) -> list[Achado]:
    # Hoje candidates.status só tem 'ativo' (sem estágio de funil). A regra existe e
    # acorda quando houver funil: candidato parado num estágio 'em_analise'/'triagem'
    # há >7d. Enquanto só houver 'ativo', é silenciosa (não fabricar movimento).
    rows = (await db.execute(text(
        "SELECT id::text AS id, coalesce(name,'candidato') AS name "
        "FROM candidates "
        "WHERE coalesce(is_active,true) AND coalesce(is_deleted,false)=false "
        "AND lower(coalesce(status,'')) IN ('em_analise','em_análise','triagem','entrevista') "
        "AND updated_at < now() - interval '7 days'"))).mappings().all()
    out = []
    for r in rows:
        out.append(Achado(
            correlation_id=f"recrutamento_parado:{r['id']}",
            dados={"candidate_id": r["id"], "nome": r["name"]},
        ))
    return out


def _tpl_recrutamento(d: dict) -> tuple[str, str]:
    return (
        f"Candidato parado: {d['nome']}",
        f"O candidato {d['nome']} está há mais de 7 dias sem movimento no funil.",
    )


register(Regra(
    nome="recrutamento_parado", familia="recrutamento", severidade="info",
    roles_destino=("admin", "gerente_operacional"),
    action_url="/modulos/rh/recrutamento",
    detectar=_detectar_recrutamento, template=_tpl_recrutamento,
))


if __name__ == "__main__":
    import asyncio
    import inspect
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    async def main() -> None:
        eng = create_async_engine(os.environ["DATABASE_URL"])
        Session = async_sessionmaker(eng, expire_on_commit=False)
        async with Session() as db:
            # ---- posto_descoberto: Achados == oráculo vivo ----
            oráculo_postos = (await db.execute(text(
                "SELECT count(*) FROM posts WHERE is_active "
                "AND current_headcount < required_headcount"))).scalar()
            achados_postos = await REGISTRY["posto_descoberto"].detectar(db)
            assert len(achados_postos) == oráculo_postos, (len(achados_postos), oráculo_postos)
            if achados_postos:
                a = achados_postos[0]
                assert a.correlation_id.startswith("posto_descoberto:")
                t, b = REGISTRY["posto_descoberto"].template(a.dados)
                assert str(a.dados["faltam"]) in b  # groundedness do template

            # ---- certidao_vencendo: Achados == oráculo (<=30d OU vencida), dia de Manaus ----
            oráculo_cert = (await db.execute(text(
                "SELECT count(*) FROM ged_certidoes "
                "WHERE expiry_date <= (now() AT TIME ZONE 'America/Manaus')::date + 30"
            ))).scalar()
            achados_cert = await REGISTRY["certidao_vencendo"].detectar(db)
            assert len(achados_cert) == oráculo_cert, (len(achados_cert), oráculo_cert)
            for a in achados_cert:
                esperado = "critico" if a.dados["vencida"] else "atencao"
                assert a.dados["severidade"] == esperado, (a.dados["severidade"], esperado)

            # ---- caixa_baixo_cnpj: cada Achado tem saldo < limiar; limiar>0 ----
            achados_caixa = await REGISTRY["caixa_baixo_cnpj"].detectar(db)
            for a in achados_caixa:
                assert a.dados["saldo"] < a.dados["limiar"]
                assert a.dados["limiar"] > 0
                assert a.correlation_id.startswith("caixa_baixo:")

            # ---- aging_reforcado: Achado agregado == existe vencido? (mesma fonte do reconciliador) ----
            venc = (await db.execute(text(
                "SELECT count(*), coalesce(sum(net_value),0) FROM receivable_accounts "
                "WHERE due_date < current_date "
                "AND coalesce(status::text,'') NOT ILIKE '%pag%' "
                "AND coalesce(status::text,'') NOT ILIKE '%cancel%'"))).fetchone()
            achados_aging = await REGISTRY["aging_reforcado"].detectar(db)
            assert len(achados_aging) == (1 if int(venc[0]) > 0 else 0)
            if achados_aging:
                assert achados_aging[0].dados["n"] == int(venc[0])
                assert achados_aging[0].correlation_id == "financeiro_aging:portfolio:None"
                # fix pós-review (4): severidade dinâmica espelha notifications/tasks.py:61
                esperado_sev = "critico" if achados_aging[0].dados["total"] >= 50000 else "atencao"
                assert achados_aging[0].dados["severidade"] == esperado_sev, (
                    achados_aging[0].dados["severidade"], achados_aging[0].dados["total"])

            # ---- justificativa_parada: == pending/pendente há >48h (fix pós-review 3) ----
            j = (await db.execute(text(
                "SELECT count(*) FROM gp_justifications "
                "WHERE lower(coalesce(status,'')) IN ('pending','pendente') "
                "AND created_at < now() - interval '48 hours'"))).scalar()
            achados_just = await REGISTRY["justificativa_parada"].detectar(db)
            assert len(achados_just) == int(j)
            src_just = inspect.getsource(_detectar_justificativa)
            assert "'pending','pendente'" in src_just, "SQL de justificativa deve cobrir os dois vocabulários"

            # ---- mudas honestas: hoje 0, mas registradas (acordam sozinhas) ----
            assert "juridico_prazo" in REGISTRY and "recrutamento_parado" in REGISTRY
            achados_jur = await REGISTRY["juridico_prazo"].detectar(db)
            assert len(achados_jur) == (await db.execute(text(
                "SELECT count(*) FROM juridico_prazos "
                "WHERE data_limite <= (now() AT TIME ZONE 'America/Manaus')::date + 7 "
                "AND lower(coalesce(status,'')) NOT IN ('cumprido')"))).scalar()
            for a in achados_jur:
                esperado = "critico" if a.dados["dias"] < 0 else "atencao"
                assert a.dados["severidade"] == esperado, (a.dados["severidade"], esperado)

            # ---- fix pós-review (1)+(2): SQL do juridico sem current_date cru; usa Manaus; vocabulário real ----
            src_jur = inspect.getsource(_detectar_juridico)
            assert "current_date" not in src_jur, "juridico_prazo não pode usar current_date cru (TZ UTC)"
            assert "America/Manaus" in src_jur
            assert "NOT IN ('cumprido')" in src_jur
            assert "concluido" not in src_jur and "cancelado" not in src_jur

            achados_rec = await REGISTRY["recrutamento_parado"].detectar(db)
            assert len(achados_rec) == (await db.execute(text(
                "SELECT count(*) FROM candidates "
                "WHERE coalesce(is_active,true) AND coalesce(is_deleted,false)=false "
                "AND lower(coalesce(status,'')) IN ('em_analise','em_análise','triagem','entrevista') "
                "AND updated_at < now() - interval '7 days'"))).scalar()

            # ---- fail-closed: regra sem roles não entra ----
            n0 = len(REGISTRY)
            register(Regra(nome="__x__", familia="x", severidade="info",
                           roles_destino=(), action_url="/",
                           detectar=achados_postos.__class__,  # dummy, não usado
                           template=lambda d: ("", "")))
            assert "__x__" not in REGISTRY and len(REGISTRY) == n0

            print(f"OK regras — postos={len(achados_postos)} cert={len(achados_cert)} "
                  f"caixa={len(achados_caixa)} aging={len(achados_aging)} "
                  f"just={len(achados_just)} jur={len(achados_jur)} rec={len(achados_rec)}")
        await eng.dispose()

    asyncio.run(main())
