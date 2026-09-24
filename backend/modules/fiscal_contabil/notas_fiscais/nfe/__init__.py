"""
NF-e Produto — Módulo de emissão de Nota Fiscal Eletrônica (modelo 55)
via SEFAZ-AM com certificado A1.

Exports:
    router — FastAPI router com prefix /nfe, registrado em /fiscal/nfe
"""

from .emissor import router

__all__ = ["router"]
