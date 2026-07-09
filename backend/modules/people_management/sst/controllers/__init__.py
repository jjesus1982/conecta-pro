"""Controllers SST."""

from .sst_controller import router

# Rollout de assinaturas das fichas de EPI (arquivo separado para não tocar a
# região de transmissão do sst_controller) — herda o prefixo /sst.
try:
    from .rollout_assinaturas_controller import router as rollout_assinaturas_router

    router.include_router(rollout_assinaturas_router)
except Exception:  # pragma: no cover — nunca derrubar o módulo SST inteiro
    import logging

    logging.getLogger(__name__).exception("Rollout assinaturas router não carregou")

__all__ = ["router"]
