"""Redesign builder — Suprimentos (DGX F9, 24/09/2026).

O monólito (`redesign_data_controller._build_suprimentos`) entrega `visao` e `almoxarifado` lendo
`nfe_compras_estoque`. Este builder chama esse mesmo corpo e estende com a cadeia de compras,
materiais/estoque, fornecedores, comunicações móveis/rastreadores e kits (`_dgx_f9_suprimentos`).
`requisicoes` (item do JSON do módulo, nunca ligado) passa a ser a tela de solicitações de compra.
A AA1 acrescenta o catálogo que nasce da nota de compra (`_dgx_aa1_catalogo`), com aprovação humana.
"""

from fastapi import APIRouter

from ._dgx_aa1_catalogo import MENU as _menu_aa1  # noqa: N811  # dgx aa1
from ._dgx_aa1_catalogo import router as _router_aa1  # dgx aa1
from ._dgx_f9_suprimentos import MENU as _menu_f9  # noqa: N811  # dgx f9
from ._dgx_f9_suprimentos import router as _router_f9  # dgx f9
from ._dgx_t5_suprimentos_frotas_sesmt_config import MENU_SUP as _menu_t5  # noqa: N811  # dgx t5
from ._dgx_t5_suprimentos_frotas_sesmt_config import router as _router_t5  # dgx t5
from ._dgx_v3_frota_app import (
    MENU_SUP as _menu_v3,  # noqa: N811  # dgx v3 — grupos (router incluído em equipamentos.py)
)

SLUG = "suprimentos"
# dgx t5 — solicitações de material; dgx v3 — grupos; dgx aa1 — compra → catálogo
EXTRA_MENU: list[dict] = [*_menu_f9, *_menu_t5, *_menu_v3, *_menu_aa1]

router = APIRouter()
router.include_router(_router_f9)  # dgx f9
router.include_router(_router_aa1)  # dgx aa1 — compra → catálogo (aprovar/descartar/reclassificar)
router.include_router(_router_t5)  # dgx t5 — ações de material, exame do ASO, acesso temporário e log (um só router)


async def build(db) -> dict:
    from modules.operacional.controllers.redesign_data_controller import _build_suprimentos

    # tardio de propósito: no boot este arquivo é importado pelo discovery enquanto `_dgx_f9` ainda
    # está pela metade (ciclo data_controller → discovery → aqui → _dgx_f9 → data_controller)
    from ._dgx_f9_suprimentos import telas as _telas_f9  # dgx f9

    out = await _build_suprimentos(db)
    await _telas_f9(db, out)  # dgx f9
    if "solicitacoes-compra" in out:
        out["requisicoes"] = out["solicitacoes-compra"]  # porta que já existia no JSON do módulo
    from ._dgx_t5_suprimentos_frotas_sesmt_config import telas_sup as _telas_t5  # dgx t5

    await _telas_t5(db, out)  # dgx t5 — solicitação de material por posto (atender baixa o estoque)
    from ._dgx_v3_frota_app import telas_sup as _telas_v3  # dgx v3

    await _telas_v3(db, out)  # dgx v3 — grupos hierárquicos de materiais/uniformes
    from ._dgx_aa1_catalogo import telas as _telas_aa1  # dgx aa1

    await _telas_aa1(db, out)  # dgx aa1 — nota de compra vira produto no catálogo, com aprovação humana
    return out
