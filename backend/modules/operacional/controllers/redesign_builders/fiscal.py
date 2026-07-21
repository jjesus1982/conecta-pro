"""Fiscal (T1) — delega ao _build_fiscal e liga o menu json 'certidoes' às CNDs reais
(ged_certidoes) que já são montadas como 'certidoes-cnd'. Ação fiscal (transmitir) segue GATED.
nfse-multi/sped/ecac/consultor = capacidade sem tabela → honesto vazio."""
from modules.operacional.controllers.redesign_data_controller import _build_fiscal

SLUG = "fiscal"
EXTRA_MENU: list[dict] = []


async def build(db) -> dict:
    out = await _build_fiscal(db)
    # O item de menu json 'certidoes' estava vazio; aponta pras mesmas CNDs reais.
    if "certidoes-cnd" in out:
        out["certidoes"] = out["certidoes-cnd"]
    return out
