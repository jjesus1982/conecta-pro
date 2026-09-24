"""Redesign builder — Equipamentos (NOVO módulo; era 100% mock).

Liga visao·patrimonio·comodatos·manutencoes lendo as tabelas reais de patrimônio
(equipments, equipment_comodatos, equipment_maintenances). Módulo ainda não
alimentado no clássico → 0 linhas HONESTAS ("aguardando dado"), nunca mock.
"""

from modules.operacional.controllers.redesign_data_controller import (
    _helpers,
    b,
    t,
)

SLUG = "equipamentos"
EXTRA_MENU: list[dict] = []
_ND = "#0F1B3A"


def _d(v, fmt="%d/%m/%Y"):
    try:
        return v.strftime(fmt) if v else "—"
    except Exception:
        return "—"


def _bs(v):
    s = (v or "").lower()
    if s in ("ativo", "active", "online", "operante", "instalado", "concluido", "concluida", "resolvido"):
        return b(v or "—", "ok")
    if s in ("pendente", "agendado", "scheduled", "manutencao", "em_andamento", "aguardando", "vigente"):
        return b(v or "—", "warn")
    if s in ("inativo", "offline", "avariado", "perdido", "cancelado", "encerrado", "vencido"):
        return b(v or "—", "bad")
    return b(v or "—", "info")


async def build(db) -> dict:
    out, safe, tbl = _helpers(db)

    # 1) Visão — equipments por status (agregado real)
    await safe(
        "visao",
        tbl(
            "Visão geral",
            "Patrimônio por status",
            "—",
            ["Status", "Equipamentos"],
            "2fr 1fr",
            "SELECT coalesce(status::text,'—'), count(*) FROM equipments WHERE coalesce(is_active,true) "
            "GROUP BY status ORDER BY count(*) DESC LIMIT 50",
            lambda r: [_bs(r[0]), t(str(r[1]), 600)],
        ),
    )

    # 2) Patrimônio — equipments
    await safe(
        "patrimonio",
        tbl(
            "Patrimônio",
            "Equipamentos cadastrados",
            "Novo equipamento",
            ["Código", "Equipamento", "Tipo", "Serial", "Status", "Cliente"],
            "1fr 1.6fr 1fr 1.1fr 0.9fr 1.4fr",
            "SELECT coalesce(equipment_code,'—'), coalesce(name,'—'), coalesce(equipment_type::text,'—'), "
            "coalesce(serial_number,'—'), coalesce(status::text,'—'), coalesce(client_name,'—') "
            "FROM equipments WHERE coalesce(is_active,true) ORDER BY created_at DESC LIMIT 300",
            lambda r: [t(r[0], 600, _ND), t(r[1]), t((r[2] or "—").replace("_", " ")), t(r[3]), _bs(r[4]), t(r[5])],
        ),
    )

    # 3) Comodatos — equipment_comodatos
    await safe(
        "comodatos",
        tbl(
            "Comodatos",
            "Equipamentos em comodato",
            "—",
            ["Código", "Equipamento", "Cliente", "Início", "Fim", "Status"],
            "1fr 1.6fr 1.6fr 1fr 1fr 0.9fr",
            "SELECT coalesce(comodato_code,'—'), coalesce(equipment_name,'—'), coalesce(client_name,'—'), "
            "start_date, end_date, coalesce(status::text,'—') FROM equipment_comodatos "
            "WHERE coalesce(is_active,true) ORDER BY created_at DESC LIMIT 200",
            lambda r: [t(r[0], 600, _ND), t(r[1]), t(r[2]), t(_d(r[3])), t(_d(r[4])), _bs(r[5])],
        ),
    )

    # 4) Manutenções — equipment_maintenances
    await safe(
        "manutencoes",
        tbl(
            "Manutenções",
            "Ordens de manutenção",
            "Nova manutenção",
            ["Código", "Equipamento", "Tipo", "Técnico", "Agendada", "Status"],
            "1fr 1.5fr 1fr 1.3fr 1fr 0.9fr",
            "SELECT coalesce(maintenance_code,'—'), coalesce(equipment_name,'—'), "
            "coalesce(maintenance_type::text,'—'), coalesce(technician_name,'—'), scheduled_date, "
            "coalesce(status::text,'—') FROM equipment_maintenances WHERE coalesce(is_active,true) "
            "ORDER BY scheduled_date DESC NULLS LAST LIMIT 200",
            lambda r: [t(r[0], 600, _ND), t(r[1]), t((r[2] or "—").replace("_", " ")), t(r[3]), t(_d(r[4])), _bs(r[5])],
        ),
    )

    from ._frente_10 import telas as _telas_10  # frente 10 — frota + avaliação por ambiente

    out.update(await _telas_10(db, SLUG))
    from ._dgx_f10_frotas import telas as _telas_f10  # dgx f10 — saídas, multas, trocas, locações, requisições

    await _telas_f10(db, out)
    return out


# frente 10 — menu e ações (router incluído UMA vez, aqui; gestao_de_pessoas só anexa telas)
from fastapi import APIRouter  # noqa: E402

from ._dgx_f10_frotas import MENU as _menu_f10  # noqa: E402,N811  # dgx f10
from ._dgx_f10_frotas import router as _router_f10  # noqa: E402
from ._frente_10 import MENU_EQUIPAMENTOS as _menu_10  # noqa: E402,N811
from ._frente_10 import router as _router_10  # noqa: E402

router = APIRouter()
router.include_router(_router_10)
router.include_router(_router_f10)  # dgx f10
EXTRA_MENU.extend(_menu_10)
EXTRA_MENU.extend(_menu_f10)  # dgx f10
