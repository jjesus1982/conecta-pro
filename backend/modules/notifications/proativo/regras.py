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
    base = ("folha do CNPJ" if not d["usou_fallback"] else "piso R$ 10.000")
    return (
        f"Caixa baixo: {d['cnpj']}",
        f"O caixa de {d['cnpj']} ({d['banco']}) está em R$ {d['saldo']:,.2f}, "
        f"abaixo do limiar de R$ {d['limiar']:,.2f} ({base}).",
    )


register(Regra(
    nome="caixa_baixo_cnpj", familia="financeiro", severidade="critico",
    roles_destino=("admin",),  # LGPD: financeiro SÓ diretoria
    action_url="/modulos/financeiro/caixa",
    detectar=_detectar_caixa_baixo, template=_tpl_caixa,
))


if __name__ == "__main__":
    import asyncio
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

            # ---- fail-closed: regra sem roles não entra ----
            n0 = len(REGISTRY)
            register(Regra(nome="__x__", familia="x", severidade="info",
                           roles_destino=(), action_url="/",
                           detectar=achados_postos.__class__,  # dummy, não usado
                           template=lambda d: ("", "")))
            assert "__x__" not in REGISTRY and len(REGISTRY) == n0

            print(f"OK regras — postos={len(achados_postos)} cert={len(achados_cert)} "
                  f"caixa={len(achados_caixa)}")
        await eng.dispose()

    asyncio.run(main())
