"""
Controllers para integrações governamentais.

Sprint 33: Adicionado suporte a certificados digitais A1.
Sprint 34: Adicionado NFS-e Manaus (Prefeitura de Manaus - ABRASF 2.04)
Sprint 34: Adicionado EFD-Reinf (Eventos R-1000, R-2010, R-4010, R-4020, R-2099)
Sprint 34: Adicionado DCTFWeb (Declaração, DARFs, Transmissão)
Sprint 34: Adicionado Simples Nacional (PGDAS-D, DAS, Fator R)
Sprint 34: Adicionado FGTS Digital (Guias PIX, Rescisões, Relatórios)
Sprint 34: Adicionado SPED Fiscal (EFD ICMS/IPI, Apuração, Arquivo)
Sprint 34: Adicionado SPED Contabil (ECD, Lancamentos, Demonstracoes)
Sprint 35: Adicionado e-CAC (Situacao Fiscal, Certidoes, Debitos, Parcelamentos)
Sprint 35: Adicionado CT-e (Conhecimento de Transporte Eletronico)
Sprint 35: Adicionado MDF-e (Manifesto Eletronico de Documentos Fiscais)
Sprint 36: Adicionado NFS-e Padrao Nacional (preparacao para migracao 2026)
Sprint 36: Adicionado SEFAZ-AM (Endpoints especificos Amazonas)
Sprint 36: Adicionado Sync Controller (Sincronizacao automatica)
Sprint 36: Adicionado Jobs Controller (Agendamento de sincronizacoes)
Sprint 37: Adicionado Dashboard Controller (Monitoramento de extracoes)
Sprint 37: Adicionado Extraction Controller (Orquestracao de extracoes)
"""

from fastapi import APIRouter

from .certificate_controller import router as certificate_router
from .cte_controller import router as cte_router
from .dashboard_controller import router as dashboard_router
from .dctfweb_controller import router as dctfweb_router
from .ecac_controller import router as ecac_router
from .efd_reinf_controller import router as efd_reinf_router
from .esocial_controller import router as esocial_router
from .esocial_espelho_controller import router as esocial_espelho_router
from .extraction_controller import router as extraction_router
from .fgts_digital_controller import router as fgts_digital_router
from .fgts_inss_controller import router as fgts_inss_router
from .govbr_controller import router as govbr_router
from .jobs_controller import router as jobs_router
from .mdfe_controller import router as mdfe_router
from .nfce_controller import router as nfce_router
from .nfse_manaus_controller import router as nfse_manaus_router
from .nfse_nacional_controller import router as nfse_nacional_router
from .receita_federal_controller import router as receita_federal_router
from .sefaz_am_controller import router as sefaz_am_router
from .sefaz_controller import router as sefaz_router
from .simples_nacional_controller import router as simples_nacional_router
from .sped_contabil_controller import router as sped_contabil_router
from .sped_fiscal_controller import router as sped_fiscal_router
from .status_controller import router as status_router
from .sync_controller import router as sync_router

# Router principal que agrega todos os sub-routers
router = APIRouter(prefix="/government", tags=["Government - Integracoes Governamentais"])

# Inclui sub-routers
router.include_router(receita_federal_router)
router.include_router(fgts_inss_router)
router.include_router(esocial_router)
router.include_router(esocial_espelho_router)
router.include_router(sefaz_router)
router.include_router(status_router)
router.include_router(certificate_router)
router.include_router(nfse_manaus_router)
router.include_router(efd_reinf_router)
router.include_router(dctfweb_router)
router.include_router(simples_nacional_router)
router.include_router(fgts_digital_router)
router.include_router(sped_fiscal_router)
router.include_router(sped_contabil_router)
router.include_router(ecac_router)
router.include_router(cte_router)
router.include_router(mdfe_router)
router.include_router(govbr_router)
router.include_router(nfse_nacional_router)
router.include_router(sync_router)
router.include_router(sefaz_am_router)
router.include_router(jobs_router)
router.include_router(dashboard_router)
router.include_router(extraction_router)
router.include_router(nfce_router)

__all__ = [
    "router",
    "receita_federal_router",
    "fgts_inss_router",
    "esocial_router",
    "sefaz_router",
    "status_router",
    "certificate_router",
    "nfse_manaus_router",
    "efd_reinf_router",
    "dctfweb_router",
    "simples_nacional_router",
    "fgts_digital_router",
    "sped_fiscal_router",
    "sped_contabil_router",
    "ecac_router",
    "cte_router",
    "mdfe_router",
    "govbr_router",
    "nfse_nacional_router",
    "sync_router",
    "sefaz_am_router",
    "jobs_router",
    "dashboard_router",
    "extraction_router",
    "nfce_router",
]
