"""
Módulo TÉCNICO — Agregador

`equipment_management` (equipamentos, instalações, manutenções, comodatos: 96 rotas, 0
requisições em 15 dias, 4 tabelas com 0 linhas) e `documents` (GED genérico; o GED vivo é
`ged_kit_documents`) foram APAGADOS em 06/09/2026. `document_kits` fica. `main_production.py`
(zona proibida) importa os nomes abaixo — routers VAZIOS até o bloco ser removido de lá.
Ver auditoria/MAPA_CONECTA_PRO_20260906.md.
"""
from fastapi import APIRouter

from modules.document_kits.controllers import router as document_kit_router

equipment_router = APIRouter()
installation_router = APIRouter()
equipment_maintenance_router = APIRouter()
comodato_router = APIRouter()
documents_router = None

__all__ = ["equipment_router", "installation_router", "equipment_maintenance_router",
           "comodato_router", "document_kit_router", "documents_router"]
