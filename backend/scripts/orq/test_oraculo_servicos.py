"""Serviços: a tela bate com o banco E a camada de serviço realmente EXECUTA.

Por que existe. O módulo tem 54 rotas montadas e nunca tinha sido exercitado: 78 chamadas
em 2 arquivos apontavam para métodos que o repositório não tem (`get_service_catalog_stats`
× `get_service_stats`, `list_service_orders` × `list_orders`, …). Não era bug de lógica —
era código que nunca rodou. Consertado em 12/08/2026.

Logo depois, um SEGUNDO defeito da mesma raiz: `get_service_catalog_stats` está anotado
`-> ServiceCatalogStats`, devolvia o **dict cru** do repositório, e o dashboard executivo
estourava em `AttributeError: 'dict' object has no attribute 'total_services'`. A trava
estática dizia verde ("o método existe") — existir e devolver outra forma quebra igual.

Este oráculo vigia as duas coisas que a trava estática não vê: os números da TELA contra o
banco, e a camada de serviço RODANDO de verdade contra o banco.

Regra, não fotografia: nada aqui fixa "1 serviço" ou "14 contratos". Fixa
`exibido == consulta independente`. Catálogo novo entra sozinho; divergência reprova sozinha.
"""
import asyncio
import inspect
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _fixtures import tela  # noqa: E402

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from core.database.session import SyncSessionLocal  # noqa: E402
from modules.operacional.controllers.redesign_builders.servicos import build  # noqa: E402
from modules.services.schemas.service_schemas import (  # noqa: E402
    ServiceCatalogStats,
    ServiceOrderStats,
)
from modules.services.services.service_ai_service import ServiceAIService  # noqa: E402
from modules.services.services.service_management_service import (  # noqa: E402
    ServiceManagementService,
)

#: LIMIT das tabelas do builder — a tela nunca mostra mais que isto
TETO_LINHAS = 200


def _kpi(scr, label):
    for k in scr.get("kpis", []):
        if k.get("l") == label:
            return k.get("v")
    return None


async def _num(db, sql: str) -> int:
    return int((await db.execute(text(sql))).scalar() or 0)


async def _lente_tela(db) -> None:
    """Exibido == banco. Consultas escritas aqui de forma independente, de propósito.

    O QA de 09/08 conferiu KPI do fiscal contra a query do próprio builder e aprovou: os dois
    lados batiam e ambos estavam errados (31 obrigações anunciadas, 5 reais). Copiar a query
    que se audita só prova que se sabe copiar.
    """
    scr = await build(db)
    visao = tela(scr, "visao")
    assert visao and visao.get("type") == "dash", f"visão não é dash: {visao and visao.get('type')}"

    os_total = await _num(db, "SELECT count(*) FROM ordens_servico")
    catalogo = await _num(db, "SELECT count(*) FROM service_catalog")
    clientes = await _num(db, "SELECT count(*) FROM clients WHERE status='active'")
    aberto = await _num(
        db,
        "SELECT count(*) FROM ordens_servico "
        "WHERE lower(coalesce(status,'')) NOT IN ('concluida','concluido','cancelada')",
    )

    for label, esperado in (("Ordens de serviço", os_total), ("Catálogo", catalogo),
                            ("Clientes", clientes), ("Em aberto", aberto)):
        assert _kpi(visao, label) == str(esperado), \
            f"KPI {label}: tela={_kpi(visao, label)} banco={esperado}"

    # Suspenders — o defeito do fiscal (31 anunciadas, 5 reais) foi contar TUDO como aberto.
    # Só dá para acusar quando os dois números divergem de verdade.
    if os_total != aberto:
        assert _kpi(visao, "Em aberto") != str(os_total), \
            "'Em aberto' voltou a contar todas as OS"

    for slug, sql in (("ordens", "SELECT count(*) FROM ordens_servico"),
                      ("agendamentos", "SELECT count(*) FROM diarist_schedules"),
                      ("contratos", "SELECT count(*) FROM contracts")):
        t = tela(scr, slug)
        assert t and t.get("type") == "table", f"{slug} não é tabela"
        n = await _num(db, sql)
        assert len(t.get("rows") or []) == min(n, TETO_LINHAS), \
            f"{slug}: tela={len(t.get('rows') or [])} banco={n} (teto {TETO_LINHAS})"

    print(f"OK tela: OS={os_total} catálogo={catalogo} clientes={clientes} "
          f"aberto={aberto} contratos={await _num(db, 'SELECT count(*) FROM contracts')}")


def _lente_camada_de_servico() -> None:
    """A camada RODA contra o banco — é o que a trava estática não consegue provar.

    Chamada para método inexistente e método que devolve forma errada só aparecem quando o
    código executa. `checar_repositorio.py` pega as duas de forma estática; aqui elas
    encostam no banco de verdade.
    """
    db = SyncSessionLocal()
    try:
        ai = ServiceAIService(db)

        # Os dois que estouravam o dashboard executivo: a anotação promete schema.
        assert isinstance(ai.get_service_catalog_stats(), ServiceCatalogStats), \
            "get_service_catalog_stats voltou a devolver o dict cru do repositório"
        assert isinstance(ai.get_order_stats(), ServiceOrderStats), \
            "get_order_stats voltou a devolver o dict cru do repositório"

        exercitados, quebrados = 0, []
        for obj in (ai, ServiceManagementService(db)):
            for nome in sorted(n for n in dir(obj) if not n.startswith("_")):
                fn = getattr(obj, nome)
                if not callable(fn):
                    continue
                sig = inspect.signature(fn)
                if any(p.default is p.empty and p.kind not in (p.VAR_POSITIONAL, p.VAR_KEYWORD)
                       for p in sig.parameters.values()):
                    continue  # exige argumento: sem dado nas tabelas não há como exercitar
                try:
                    fn()
                    exercitados += 1
                except AttributeError as e:
                    quebrados.append(f"{type(obj).__name__}.{nome}: {e}")
                except Exception:
                    exercitados += 1  # erro de regra de negócio não é o que este oráculo vigia

        assert not quebrados, "camada de serviço chamando o que não existe:\n  " + \
            "\n  ".join(quebrados)
        assert exercitados >= 10, f"só {exercitados} métodos exercitados — o oráculo cegou"
        print(f"OK camada: {exercitados} métodos rodaram contra o banco, 0 AttributeError")
    finally:
        db.close()


async def main() -> None:
    async with async_session_factory() as db:
        await _lente_tela(db)
    _lente_camada_de_servico()
    print("TEST oraculo_servicos PASS")


if __name__ == "__main__":
    asyncio.run(main())
