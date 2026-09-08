"""
Controller para integracao SEFAZ-AM (Amazonas).

Endpoints especificos para NF-e no estado do Amazonas:
- GET /sefaz-am/status - Status do servico
- GET /sefaz-am/nfe/{chave} - Consulta NF-e por chave
- GET /sefaz-am/cadastro/ie/{ie} - Consulta cadastro por IE
- GET /sefaz-am/cadastro/cnpj/{cnpj} - Consulta cadastro por CNPJ
- GET /sefaz-am/dfe - Consulta DF-e (notas destinadas)
- POST /sefaz-am/cancelar - Cancela NF-e
- POST /sefaz-am/carta-correcao - Registra carta de correcao
- POST /sefaz-am/inutilizar - Inutiliza numeracao
"""

import logging
import os

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


def get_sefaz_service(db: Session = None):
    """
    Helper para inicializar SefazAMService com certificado.

    Args:
        db: Sessão do banco de dados (opcional)

    Returns:
        Tuple[SefazAMService, CertificateManager]: Service e gerenciador de certificado
    """
    from modules.government_integrations.core.certificate_manager import CertificateManager
    from modules.government_integrations.core.sefaz_am import SefazAMService

    cert_path = os.getenv("CERTIFICATE_PATH", "/opt/conecta-pro/credentials/certificates/certificado.pfx")
    cert_password = os.getenv("CERTIFICATE_PASSWORD", "")

    cert_manager = CertificateManager(pfx_path=cert_path, password=cert_password)
    service = SefazAMService(db_session=db, certificate_manager=cert_manager)

    return service, cert_manager


router = APIRouter(prefix="/sefaz-am", tags=["SEFAZ-AM (Amazonas)"])


# =========================================================================
# SCHEMAS
# =========================================================================


class StatusServicoResponse(BaseModel):
    """Resposta de status do servico."""

    disponivel: bool
    codigo: str
    mensagem: str
    tempo_resposta_ms: float
    ambiente: str
    data_consulta: str


class ConsultaNFeResponse(BaseModel):
    """Resposta de consulta NF-e."""

    sucesso: bool
    codigo: str
    mensagem: str
    chave_acesso: str | None = None
    protocolo: str | None = None
    data_autorizacao: str | None = None
    status_nota: str | None = None
    eventos: list[dict] = []


class CadastroContribuinteResponse(BaseModel):
    """Resposta de consulta cadastral."""

    sucesso: bool
    codigo: str
    mensagem: str
    contribuintes: list[dict] = []


class DFeResponse(BaseModel):
    """Resposta de consulta DF-e."""

    sucesso: bool
    codigo: str
    mensagem: str
    ultimo_nsu: str | None = None
    quantidade_documentos: int = 0
    documentos: list[dict] = []


class CancelamentoRequest(BaseModel):
    """Requisicao de cancelamento."""

    chave_acesso: str = Field(..., min_length=44, max_length=44)
    cnpj: str = Field(..., min_length=14, max_length=14)
    justificativa: str = Field(..., min_length=15, max_length=255)


class CartaCorrecaoRequest(BaseModel):
    """Requisicao de carta de correcao."""

    chave_acesso: str = Field(..., min_length=44, max_length=44)
    cnpj: str = Field(..., min_length=14, max_length=14)
    correcao: str = Field(..., min_length=15, max_length=1000)
    sequencia: int = Field(default=1, ge=1, le=20)


class InutilizacaoRequest(BaseModel):
    """Requisicao de inutilizacao."""

    cnpj: str = Field(..., min_length=14, max_length=14)
    serie: int = Field(..., ge=0, le=999)
    numero_inicial: int = Field(..., ge=1)
    numero_final: int = Field(..., ge=1)
    justificativa: str = Field(..., min_length=15, max_length=255)
    ano: int | None = None


class EventoResponse(BaseModel):
    """Resposta de evento."""

    sucesso: bool
    codigo: str
    mensagem: str
    protocolo: str | None = None
    data_registro: str | None = None


# =========================================================================
# ENDPOINTS
# =========================================================================


