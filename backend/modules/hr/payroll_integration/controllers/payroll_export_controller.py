"""Controller para exportação de folha de pagamento."""

import logging

from fastapi import APIRouter

from modules.hr.payroll_integration.models import ExportFormat

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/exports", tags=["Payroll Exports"])




def _uget(user, key, default=None):
    """Acessa campo do usuário seja objeto User (get_current_user) ou dict — os endpoints
    usavam current_user['x'], que crashava no User ('User' object is not subscriptable)."""
    if isinstance(user, dict):
        return user.get(key, default)
    return getattr(user, key, default)
def _get_format_description(fmt: ExportFormat) -> str:
    """Retorna descrição do formato."""
    descriptions = {
        ExportFormat.CSV: "Arquivo CSV com separador configurável",
        ExportFormat.JSON: "Arquivo JSON estruturado",
        ExportFormat.TXT: "Arquivo texto posicional",
        ExportFormat.XLSX: "Planilha Excel",
        ExportFormat.XML: "Arquivo XML genérico",
        ExportFormat.CNAB240: "Arquivo bancário CNAB 240",
        ExportFormat.CNAB400: "Arquivo bancário CNAB 400",
        ExportFormat.ESOCIAL_XML: "XML para eSocial",
        ExportFormat.SEFIP: "Arquivo para SEFIP/GFIP",
        ExportFormat.CAGED: "Arquivo para CAGED",
        ExportFormat.RAIS: "Arquivo para RAIS",
        ExportFormat.DIRF: "Arquivo para DIRF",
    }
    return descriptions.get(fmt, "")


def _get_format_extension(fmt: ExportFormat) -> str:
    """Retorna extensão do arquivo."""
    extensions = {
        ExportFormat.CSV: ".csv",
        ExportFormat.JSON: ".json",
        ExportFormat.TXT: ".txt",
        ExportFormat.XLSX: ".xlsx",
        ExportFormat.XML: ".xml",
        ExportFormat.CNAB240: ".rem",
        ExportFormat.CNAB400: ".rem",
        ExportFormat.ESOCIAL_XML: ".xml",
        ExportFormat.SEFIP: ".re",
        ExportFormat.CAGED: ".txt",
        ExportFormat.RAIS: ".txt",
        ExportFormat.DIRF: ".txt",
    }
    return extensions.get(fmt, ".bin")
