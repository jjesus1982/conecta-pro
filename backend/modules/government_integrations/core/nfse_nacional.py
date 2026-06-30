"""
Module: NFSeNacional
Description: Integração com o Sistema Nacional NFS-e (Padrão Nacional)
             Obrigatório para todos municípios a partir de 01/01/2026
             Lei Complementar 214/2025
Author: Conecta PRO
Date: 2026-01-17

Portal: https://www.nfse.gov.br
Documentação: https://www.gov.br/nfse/pt-br/biblioteca/documentacao-tecnica
Swagger: https://www.nfse.gov.br/swagger/contribuintesissqn/

Características:
- API REST (não mais SOAP)
- Autenticação mTLS com certificado ICP-Brasil
- XML assinado, compactado (GZip) e codificado (Base64)
- Respostas em JSON
- Número único nacional da NFS-e
"""

import base64
import gzip
import logging
import re
import ssl
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

try:
    import httpx

    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False

logger = logging.getLogger(__name__)


# Endpoints do Sistema Nacional NFS-e
# URL REAL validada: sefin.nfse.gov.br/sefinnacional/ (versão SefinNacional_1.6.0)
# Auth: mTLS com certificado A1 ICP-Brasil
# Formato: XML DPS assinado → GZip → Base64 → POST /nfse
NFSE_NACIONAL_ENDPOINTS = {
    "producao": {
        "base_url": "https://sefin.nfse.gov.br",
        "api_url": "https://sefin.nfse.gov.br/sefinnacional",
        "portal": "https://www.nfse.gov.br/EmissorNacional",
        "swagger": "https://www.nfse.gov.br/swagger/contribuintesissqn/",
    },
    "homologacao": {
        "base_url": "https://sefin.nfse.gov.br",
        "api_url": "https://sefin.nfse.gov.br/sefinnacional",
        "portal": "https://www.nfse.gov.br/EmissorNacional",
        "swagger": "https://www.nfse.gov.br/swagger/contribuintesissqn/",
    },
}


class AmbienteNacional(StrEnum):
    """Ambientes do Padrão Nacional."""

    PRODUCAO = "producao"
    HOMOLOGACAO = "homologacao"


class TipoTributacao(StrEnum):
    """Tipos de tributação no Padrão Nacional."""

    TRIBUTACAO_MUNICIPIO = "1"
    TRIBUTACAO_FORA_MUNICIPIO = "2"
    ISENCAO = "3"
    IMUNE = "4"
    EXIGIBILIDADE_SUSPENSA_JUDICIAL = "5"
    EXIGIBILIDADE_SUSPENSA_ADM = "6"
    EXPORTACAO_SERVICO = "7"


class RegimeEspecial(StrEnum):
    """Regimes especiais de tributação."""

    SEM_REGIME = "0"
    MICROEMPRESA = "1"
    ESTIMATIVA = "2"
    SOCIEDADE_PROFISSIONAIS = "3"
    COOPERATIVA = "4"
    MEI = "5"
    ME_EPP_SIMPLES = "6"


@dataclass
class PrestadorNacional:
    """Dados do prestador no Padrão Nacional."""

    cnpj: str
    inscricao_municipal: str
    codigo_municipio: str  # Código IBGE
    razao_social: str
    nome_fantasia: str | None = None
    regime_especial: RegimeEspecial = RegimeEspecial.ME_EPP_SIMPLES
    optante_simples: bool = True


@dataclass
class TomadorNacional:
    """Dados do tomador no Padrão Nacional."""

    cpf_cnpj: str
    razao_social: str
    endereco: dict[str, str] = field(default_factory=dict)
    email: str | None = None
    telefone: str | None = None
    inscricao_municipal: str | None = None
    tipo_documento: str = "CNPJ"  # CPF ou CNPJ


@dataclass
class ServicoNacional:
    """Dados do serviço no Padrão Nacional."""

    codigo_tributacao_nacional: str  # Código do item da NBS ou LC 116
    descricao: str
    valor_servico: Decimal
    valor_deducao: Decimal = Decimal("0")
    valor_desconto_incondicionado: Decimal = Decimal("0")
    valor_desconto_condicionado: Decimal = Decimal("0")
    codigo_cnae: str | None = None
    aliquota_iss: Decimal = Decimal("0.05")
    iss_retido: bool = False


@dataclass
class DPSNacional:
    """
    Declaração de Prestação de Serviços (DPS).

    No Padrão Nacional, o RPS foi substituído pela DPS.
    """

    # Identificação
    id_dps: str | None = None
    numero: str | None = None

    # Prestador
    prestador: PrestadorNacional | None = None

    # Tomador
    tomador: TomadorNacional | None = None

    # Serviço
    servico: ServicoNacional | None = None

    # Datas
    data_competencia: datetime = field(default_factory=datetime.now)

    # Tributação
    tipo_tributacao: TipoTributacao = TipoTributacao.TRIBUTACAO_MUNICIPIO

    # Valores calculados
    valor_liquido: Decimal | None = None
    valor_iss: Decimal | None = None

    def calcular_valores(self):
        """Calcula valores derivados."""
        if self.servico:
            base_calculo = (
                self.servico.valor_servico - self.servico.valor_deducao - self.servico.valor_desconto_incondicionado
            )
            self.valor_iss = base_calculo * self.servico.aliquota_iss

            self.valor_liquido = (
                self.servico.valor_servico
                - self.servico.valor_deducao
                - self.servico.valor_desconto_incondicionado
                - (self.valor_iss if self.servico.iss_retido else Decimal("0"))
            )


class NFSeNacionalManager:
    """
    Gerenciador de NFS-e Padrão Nacional (Preparação).

    IMPORTANTE: Esta classe está em preparação para a migração.
    O Padrão Nacional ainda não está disponível em Manaus.

    Quando a migração for realizada, este manager substituirá
    o NFSeManausManager para novas emissões.

    URLs previstas:
    - Produção: https://nfse.fazenda.gov.br/api/
    - Homologação: https://nfse-homolog.fazenda.gov.br/api/
    """

    # URL REAL validada em 2026-03-24 (SefinNacional_1.6.0)
    URL_API = "https://sefin.nfse.gov.br/sefinnacional"

    ENDPOINTS = {
        "emitir_dps": "/nfse",
        "consultar_nfse": "/nfse/{chave}",
        "consultar_dps": "/nfse/DPS/{chave}",
        "danfse": "/nfse/DANFSe/{chave}",
        "eventos": "/nfse/{chave}/eventos",
    }

    def __init__(
        self,
        ambiente: AmbienteNacional = AmbienteNacional.HOMOLOGACAO,
        cnpj: str = "",
        certificado_path: str | None = None,
        certificado_senha: str | None = None,
    ):
        """
        Inicializa o manager.

        Args:
            ambiente: Ambiente (produção ou homologação)
            cnpj: CNPJ do prestador
            certificado_path: Caminho para certificado A1
            certificado_senha: Senha do certificado
        """
        self.ambiente = ambiente
        self.cnpj = cnpj
        self.certificado_path = certificado_path
        self.certificado_senha = certificado_senha

        # Homologação nacional = "produção restrita" (URL distinta da produção)
        self.url_base = (
            "https://sefin.producaorestrita.nfse.gov.br/sefinnacional"
            if ambiente == AmbienteNacional.HOMOLOGACAO
            else self.URL_API
        )

        logger.info(f"NFSe Nacional Manager inicializado - Ambiente: {ambiente.value}, URL: {self.url_base}")

    def _build_dps_xml(self, dps: DPSNacional) -> str:
        """Constrói XML DPS conforme schema nacional."""
        import re as _re
        from datetime import datetime as _dt

        dps.calcular_valores()
        tp_amb = "1" if getattr(self, "ambiente", None) == AmbienteNacional.PRODUCAO else "2"
        cnpj_clean = _re.sub(r"\D", "", self.cnpj)
        tomador_doc = _re.sub(r"\D", "", dps.tomador.cpf_cnpj) if dps.tomador else ""
        im = dps.prestador.inscricao_municipal if dps.prestador and dps.prestador.inscricao_municipal else "45177801"
        # cTribNac: 6 dígitos (2 Item + 2 Subitem + 2 Desdobro LC 116/2003)
        raw_trib = _re.sub(r"\D", "", dps.servico.codigo_tributacao_nacional) if dps.servico else "140601"
        cod_trib = raw_trib[:6] if len(raw_trib) >= 6 else raw_trib.ljust(6, "0")
        valor = f"{dps.servico.valor_servico:.2f}" if dps.servico else "0.00"
        _aliquota = f"{dps.servico.aliquota_iss * 100:.2f}" if dps.servico else "5.00"  # noqa: F841
        _valor_iss = f"{dps.valor_iss:.2f}" if dps.valor_iss else "0.00"  # noqa: F841
        descricao = dps.servico.descricao if dps.servico else "Prestação de serviços"
        competencia = (
            dps.data_competencia.strftime("%Y-%m-%d") if dps.data_competencia else _dt.now().strftime("%Y-%m-%d")
        )

        # Id do infDPS: cMun(7) + tpInsc(1) + nrInsc(14) + serie(5) + nDPS(15) = 42 chars
        # tpInsc: 1=CPF, 2=CNPJ (prestador é CNPJ → 2)
        serie_pad = "00900"  # série 900 com 5 dígitos
        ndps_pad = f"{int(dps.numero or '1'):015d}"  # nDPS com 15 dígitos
        dps_id = f"DPS13026032{cnpj_clean}{serie_pad}{ndps_pad}"

        # opSimpNac: 1=Não optante (Lucro Real/Presumido), 2=MEI, 3=ME/EPP Simples
        _optante = bool(dps.prestador and dps.prestador.optante_simples)
        op_simp = "3" if _optante else "1"
        # totTrib: optante usa pTotTribSN (% Simples); não optante usa vTotTrib (valores R$,
        # Lei 12.741 transparência fiscal) — indTotTrib/pTotTribSN proibidos p/ não optante (E0713)
        tot_trib = (
            "<pTotTribSN>0.00</pTotTribSN>"
            if _optante
            else "<vTotTrib><vTotTribFed>0.00</vTotTribFed>"
            "<vTotTribEst>0.00</vTotTribEst><vTotTribMun>0.00</vTotTribMun></vTotTrib>"
        )

        # Ordem EXATA do XSD TCInfDPS (tiposComplexos_v1.00.xsd):
        # tpAmb → dhEmi → verAplic → serie → nDPS → dCompet → tpEmit → cLocEmi →
        # [subst] → prest → [toma] → [interm] → serv → valores
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<DPS xmlns="http://www.sped.fazenda.gov.br/nfse" versao="1.00">
  <infDPS Id="{dps_id}">
    <tpAmb>{tp_amb}</tpAmb>
    <dhEmi>{(_dt.now() - __import__("datetime").timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M:%S")}-03:00</dhEmi>
    <verAplic>ConectaPRO-2.0</verAplic>
    <serie>900</serie>
    <nDPS>{dps.numero or "1"}</nDPS>
    <dCompet>{competencia}</dCompet>
    <tpEmit>1</tpEmit>
    <cLocEmi>1302603</cLocEmi>
    <prest>
      <CNPJ>{cnpj_clean}</CNPJ>
      <IM>{im}</IM>
      <regTrib>
        <opSimpNac>{op_simp}</opSimpNac>
        <regEspTrib>0</regEspTrib>
      </regTrib>
    </prest>
    <toma>
      <CNPJ>{tomador_doc}</CNPJ>
      <xNome>{dps.tomador.razao_social if dps.tomador else "TOMADOR"}</xNome>
    </toma>
    <serv>
      <locPrest>
        <cLocPrestacao>1302603</cLocPrestacao>
      </locPrest>
      <cServ>
        <cTribNac>{cod_trib}</cTribNac>
        <cTribMun>100</cTribMun>
        <xDescServ>{descricao}</xDescServ>
        <cNBS>120032900</cNBS>
      </cServ>
    </serv>
    <valores>
      <vServPrest>
        <vServ>{valor}</vServ>
      </vServPrest>
      <trib>
        <tribMun>
          <tribISSQN>1</tribISSQN>
          <tpRetISSQN>1</tpRetISSQN>
        </tribMun>
        <totTrib>
          {tot_trib}
        </totTrib>
      </trib>
    </valores>
  </infDPS>
</DPS>"""
        return xml

    def emitir_dps(self, dps: DPSNacional, dry_run: bool = False) -> dict[str, Any]:
        """
        Emite DPS (Declaração de Prestação de Serviços) via API Nacional.

        Fluxo: XML DPS → Assinar XMLDSig → GZip → Base64 → POST mTLS

        Args:
            dps: Dados da DPS
            dry_run: Se True, gera XML sem transmitir

        Returns:
            Dict com resultado da emissão
        """
        import base64
        import gzip

        import requests

        # 1. Construir XML
        xml_dps = self._build_dps_xml(dps)

        result = {
            "xml_gerado": True,
            "xml_tamanho": len(xml_dps),
            "ambiente": self.ambiente.value,
        }

        if dry_run:
            result["xml_preview"] = xml_dps[:800]
            result["status"] = "dry_run"
            result["fonte"] = "xml_gerado_localmente"
            return result

        # 2. Assinar XML com certificado A1
        try:
            from .certificate_manager import CertificateManager
            from .xml_signer import NFSeNacionalXMLSigner

            cert_mgr = CertificateManager(
                pfx_path=self.certificado_path,
                password=self.certificado_senha,
            )
            cert_mgr.load()
            # NFSeNacionalXMLSigner gera <Signature> sem prefixo ds: (resolve E6155)
            signer = NFSeNacionalXMLSigner(cert_mgr)
            xml_assinado = signer.sign_nfse(xml_dps)
            result["xml_assinado"] = True
        except Exception as e:
            logger.error(f"Erro assinando DPS: {e}")
            result["status"] = "erro_assinatura"
            result["erro"] = str(e)
            return result

        # 3. GZip + Base64
        xml_gzipped = gzip.compress(xml_assinado.encode("utf-8"))
        xml_b64 = base64.b64encode(xml_gzipped).decode("ascii")

        # 4. POST para API Nacional com mTLS
        url = f"{self.url_base}/nfse"

        # Exportar certificado .pfx para PEM temporários (mTLS)
        from .certificate_manager import CertificateManager

        tmp_cert_path = None
        tmp_key_path = None
        try:
            cert_mgr = CertificateManager(pfx_path=self.certificado_path, password=self.certificado_senha)
            cert_mgr.load()

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb") as tmp_cert:
                tmp_cert.write(cert_mgr.get_certificate_pem())
                tmp_cert_path = tmp_cert.name

            with tempfile.NamedTemporaryFile(delete=False, suffix=".pem", mode="wb") as tmp_key:
                tmp_key.write(cert_mgr.get_private_key_pem())
                tmp_key_path = tmp_key.name

            resp = requests.post(
                url,
                json={"dpsXmlGZipB64": xml_b64},
                cert=(tmp_cert_path, tmp_key_path),
                timeout=30,
                verify=True,
            )

            result["http_status"] = resp.status_code
            result["response"] = resp.text[:1000]

            if resp.status_code in (200, 201):
                result["status"] = "aceita"
            elif resp.status_code == 400:
                result["status"] = "rejeitada"
            else:
                result["status"] = f"http_{resp.status_code}"

            logger.info(f"NFS-e Nacional: HTTP {resp.status_code} — {resp.text[:200]}")

        except Exception as e:
            logger.error(f"Erro transmitindo DPS: {e}")
            result["status"] = "erro_transmissao"
            result["erro"] = str(e)
        finally:
            import os as _os

            for _p in (tmp_cert_path, tmp_key_path):
                if _p:
                    try:
                        _os.unlink(_p)
                    except Exception:
                        pass

        return result

    def consultar_status_migracao(self) -> dict[str, Any]:
        """
        Consulta status da migração para o Padrão Nacional.

        Returns:
            Dict com informações sobre a migração
        """
        return {
            "municipio": "Manaus",
            "codigo_ibge": "1302603",
            "padrao_atual": "ABRASF 2.04",
            "provedor_atual": "Abaco/GIF",
            "migracao_prevista": "2026",
            "status": "aguardando",
            "notas": [
                "O Padrão Nacional está sendo implementado gradualmente",
                "Manaus ainda utiliza o padrão ABRASF via Abaco/GIF",
                "A migração trará benefícios como número único nacional",
                "Recomenda-se acompanhar comunicados da SEMEF Manaus",
            ],
            "links_uteis": {
                "portal_nacional": "https://www.gov.br/nfse",
                "documentacao": "https://www.gov.br/nfse/pt-br/acesso-a-informacao/manuais",
                "semef_manaus": "https://semef.manaus.am.gov.br",
            },
        }

    def comparar_padroes(self) -> dict[str, Any]:
        """
        Compara características entre padrão atual e Padrão Nacional.

        Returns:
            Dict com comparação entre padrões
        """
        return {
            "abrasf_204": {
                "nome": "ABRASF 2.04 (Atual em Manaus)",
                "protocolo": "SOAP/XML",
                "autenticacao": "Certificado Digital A1/A3",
                "documento": "RPS (Recibo Provisório de Serviço)",
                "numeracao": "Municipal (cada município)",
                "cancelamento": "Até 90 dias",
                "vantagens": [
                    "Sistema estável e consolidado",
                    "Integração conhecida",
                ],
                "desvantagens": [
                    "Sem padronização nacional",
                    "Cada município tem suas regras",
                    "Dificuldade em operações intermunicipais",
                ],
            },
            "padrao_nacional": {
                "nome": "Padrão Nacional NFS-e",
                "protocolo": "REST/JSON",
                "autenticacao": "Certificado Digital + Gov.br",
                "documento": "DPS (Declaração de Prestação de Serviços)",
                "numeracao": "Nacional (único em todo Brasil)",
                "cancelamento": "Seguirá regras nacionais",
                "vantagens": [
                    "Número único nacional",
                    "Integração com eSocial/DCTFWeb",
                    "API moderna (REST/JSON)",
                    "Ambiente único de dados",
                    "Simplificação de obrigações",
                ],
                "desvantagens": [
                    "Período de transição",
                    "Necessidade de adaptação de sistemas",
                ],
            },
            "recomendacao": (
                "Mantenha o sistema atual funcionando com NFSeManausManager. "
                "Quando a migração for anunciada, ative NFSeNacionalManager "
                "e migre gradualmente as emissões."
            ),
        }


# Mapeamento de códigos de serviço ABRASF para NBS (Nomenclatura Brasileira de Serviços)
# Este mapeamento será necessário na migração
MAPEAMENTO_SERVICOS_VIGILANCIA = {
    # Código ABRASF -> Código NBS + descrição
    "11.02": {
        "nbs": "1.1701.10.00",
        "descricao": "Serviços de vigilância e segurança privada",
    },
    "11.03": {
        "nbs": "1.1701.20.00",
        "descricao": "Serviços de escolta armada",
    },
    "11.04": {
        "nbs": "1.1702.10.00",
        "descricao": "Serviços de armazenamento e guarda de bens",
    },
    "11.05": {
        "nbs": "1.1701.30.00",
        "descricao": "Serviços de transporte de valores",
    },
}


@dataclass
class NFSeNacionalResult:
    """Resultado de operação com NFS-e Nacional."""

    sucesso: bool
    mensagem: str
    codigo: str | None = None
    chave_acesso: str | None = None
    numero_nfse: int | None = None
    codigo_verificacao: str | None = None
    link_nfse: str | None = None
    xml_nfse: str | None = None
    pdf_danfse: bytes | None = None
    dados_retorno: dict[str, Any] | None = None
    tempo_resposta: float = 0.0


class NFSeNacionalClient:
    """
    Cliente para integração com o Sistema Nacional NFS-e.

    Utiliza API REST com autenticação mTLS (certificado digital).

    Endpoints:
    - Produção: https://www.nfse.gov.br/api
    - Homologação: https://www.producaorestrita.nfse.gov.br/api

    Rotas principais:
    - POST /dps - Enviar DPS (gera NFS-e)
    - GET /dps/{id} - Consultar DPS
    - GET /nfse/{chaveAcesso} - Consultar NFS-e
    - GET /danfse/{chaveAcesso} - Baixar DANFSE (PDF)
    - POST /nfse/{chaveAcesso}/eventos - Registrar eventos (cancelamento, etc)
    """

    def __init__(
        self,
        ambiente: str = "2",
        cert_path: str | None = None,
        cert_password: str | None = None,
    ):
        """
        Inicializa o cliente NFS-e Nacional.

        Args:
            ambiente: 1=Produção, 2=Homologação
            cert_path: Caminho do certificado PFX/P12
            cert_password: Senha do certificado
        """
        if not HTTPX_AVAILABLE:
            raise ImportError("httpx é necessário para NFSeNacionalClient. Instale com: pip install httpx")

        self.ambiente = ambiente
        env_key = "producao" if ambiente == "1" else "homologacao"
        self.endpoints = NFSE_NACIONAL_ENDPOINTS[env_key]
        self.api_url = self.endpoints["api_url"]

        self.cert_path = cert_path
        self.cert_password = cert_password

        self._client: httpx.AsyncClient | None = None
        self._cert_pem_path: str | None = None
        self._key_pem_path: str | None = None

        logger.info(f"NFSeNacionalClient inicializado: Ambiente={'Produção' if ambiente == '1' else 'Homologação'}")

    async def _get_client(self) -> httpx.AsyncClient:
        """Obtém cliente HTTP com certificado mTLS."""
        if self._client is None:
            ssl_context = ssl.create_default_context()

            if self.cert_path:
                from .certificate_manager import CertificateManager

                cert_manager = CertificateManager(pfx_path=self.cert_path, password=self.cert_password)
                cert_manager.load()

                # Exportar para arquivos temporários PEM
                with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as cert_file:
                    cert_file.write(cert_manager.get_certificate_pem())
                    self._cert_pem_path = cert_file.name

                with tempfile.NamedTemporaryFile(mode="wb", suffix=".pem", delete=False) as key_file:
                    key_file.write(cert_manager.get_private_key_pem())
                    self._key_pem_path = key_file.name

                ssl_context.load_cert_chain(self._cert_pem_path, self._key_pem_path)

            self._client = httpx.AsyncClient(
                base_url=self.api_url,
                verify=ssl_context,
                timeout=60.0,
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
            )

        return self._client

    async def close(self):
        """Fecha o cliente HTTP e limpa arquivos temporários."""
        if self._client:
            await self._client.aclose()
            self._client = None

        # Limpar arquivos temporários
        import os

        if self._cert_pem_path and os.path.exists(self._cert_pem_path):
            os.unlink(self._cert_pem_path)
        if self._key_pem_path and os.path.exists(self._key_pem_path):
            os.unlink(self._key_pem_path)

    def _compress_and_encode_xml(self, xml: str) -> str:
        """Compacta (GZip) e codifica (Base64) o XML."""
        xml_bytes = xml.encode("utf-8")
        compressed = gzip.compress(xml_bytes)
        return base64.b64encode(compressed).decode("ascii")

    def _decode_and_decompress_xml(self, encoded: str) -> str:
        """Decodifica (Base64) e descompacta (GZip) o XML."""
        compressed = base64.b64decode(encoded)
        xml_bytes = gzip.decompress(compressed)
        return xml_bytes.decode("utf-8")

    async def enviar_dps(self, dps: DPSNacional) -> NFSeNacionalResult:
        """
        Envia um DPS para gerar NFS-e.

        Args:
            dps: Declaração de Prestação de Serviços

        Returns:
            Resultado da operação
        """
        import time

        start_time = time.time()

        try:
            client = await self._get_client()

            # Montar payload JSON (formato da API Nacional)
            dps.calcular_valores()

            payload = {
                "infDPS": {
                    "tpAmb": int(self.ambiente),
                    "dhEmi": datetime.now(UTC).isoformat(),
                    "verAplic": "CONECTA_PRO_1.0",
                    "dCompet": dps.data_competencia.strftime("%Y-%m"),
                    "prest": dps.prestador.to_dict()
                    if hasattr(dps.prestador, "to_dict")
                    else {
                        "CNPJ": re.sub(r"[^\d]", "", dps.prestador.cnpj),
                        "IM": dps.prestador.inscricao_municipal,
                    },
                    "serv": {
                        "cServ": dps.servico.codigo_tributacao_nacional,
                        "xDescServ": dps.servico.descricao,
                    },
                    "valores": {
                        "vServPrest": float(dps.servico.valor_servico),
                        "vISS": float(dps.valor_iss or 0),
                    },
                }
            }

            if dps.tomador:
                payload["infDPS"]["toma"] = {
                    "CPF" if len(re.sub(r"[^\d]", "", dps.tomador.cpf_cnpj)) == 11 else "CNPJ": re.sub(
                        r"[^\d]", "", dps.tomador.cpf_cnpj
                    ),
                    "xNome": dps.tomador.razao_social,
                }

            response = await client.post("/dps", json=payload)
            tempo_resposta = time.time() - start_time

            if response.status_code in [200, 201]:
                data = response.json()
                return NFSeNacionalResult(
                    sucesso=True,
                    mensagem="DPS enviado com sucesso",
                    chave_acesso=data.get("chaveAcesso"),
                    numero_nfse=data.get("numero"),
                    codigo_verificacao=data.get("codigoVerificacao"),
                    link_nfse=data.get("link"),
                    dados_retorno=data,
                    tempo_resposta=tempo_resposta,
                )
            else:
                data = response.json() if "application/json" in response.headers.get("content-type", "") else {}
                return NFSeNacionalResult(
                    sucesso=False,
                    mensagem=data.get("message", f"Erro HTTP {response.status_code}"),
                    codigo=str(response.status_code),
                    dados_retorno=data,
                    tempo_resposta=tempo_resposta,
                )

        except Exception as e:
            logger.error(f"Erro ao enviar DPS: {e}")
            return NFSeNacionalResult(sucesso=False, mensagem=str(e), tempo_resposta=time.time() - start_time)

    async def consultar_nfse(self, chave_acesso: str) -> NFSeNacionalResult:
        """Consulta uma NFS-e pela chave de acesso."""
        import time

        start_time = time.time()

        try:
            client = await self._get_client()
            response = await client.get(f"/nfse/{chave_acesso}")
            tempo_resposta = time.time() - start_time

            if response.status_code == 200:
                data = response.json()
                xml_nfse = None
                if "xmlNFSe" in data:
                    xml_nfse = self._decode_and_decompress_xml(data["xmlNFSe"])

                return NFSeNacionalResult(
                    sucesso=True,
                    mensagem="NFS-e encontrada",
                    chave_acesso=chave_acesso,
                    numero_nfse=data.get("numero"),
                    xml_nfse=xml_nfse,
                    dados_retorno=data,
                    tempo_resposta=tempo_resposta,
                )
            else:
                return NFSeNacionalResult(
                    sucesso=False,
                    mensagem=f"Erro HTTP {response.status_code}",
                    codigo=str(response.status_code),
                    tempo_resposta=tempo_resposta,
                )

        except Exception as e:
            logger.error(f"Erro ao consultar NFS-e: {e}")
            return NFSeNacionalResult(sucesso=False, mensagem=str(e), tempo_resposta=time.time() - start_time)

    async def baixar_danfse(self, chave_acesso: str) -> NFSeNacionalResult:
        """Baixa o DANFSE (PDF) de uma NFS-e."""
        import time

        start_time = time.time()

        try:
            client = await self._get_client()
            response = await client.get(f"/danfse/{chave_acesso}")
            tempo_resposta = time.time() - start_time

            if response.status_code == 200:
                return NFSeNacionalResult(
                    sucesso=True,
                    mensagem="DANFSE baixado",
                    chave_acesso=chave_acesso,
                    pdf_danfse=response.content,
                    tempo_resposta=tempo_resposta,
                )
            else:
                return NFSeNacionalResult(
                    sucesso=False, mensagem=f"Erro HTTP {response.status_code}", tempo_resposta=tempo_resposta
                )

        except Exception as e:
            return NFSeNacionalResult(sucesso=False, mensagem=str(e), tempo_resposta=time.time() - start_time)

    async def cancelar_nfse(self, chave_acesso: str, codigo: str, motivo: str) -> NFSeNacionalResult:
        """Registra evento de cancelamento de NFS-e."""
        import time

        start_time = time.time()

        try:
            client = await self._get_client()
            payload = {"tipoEvento": "cancelamento", "codigoCancelamento": codigo, "motivo": motivo}
            response = await client.post(f"/nfse/{chave_acesso}/eventos", json=payload)
            tempo_resposta = time.time() - start_time

            if response.status_code in [200, 201]:
                return NFSeNacionalResult(
                    sucesso=True,
                    mensagem="NFS-e cancelada",
                    chave_acesso=chave_acesso,
                    dados_retorno=response.json(),
                    tempo_resposta=tempo_resposta,
                )
            else:
                return NFSeNacionalResult(
                    sucesso=False, mensagem=f"Erro HTTP {response.status_code}", tempo_resposta=tempo_resposta
                )

        except Exception as e:
            return NFSeNacionalResult(sucesso=False, mensagem=str(e), tempo_resposta=time.time() - start_time)


logger.info("Módulo NFSeNacional carregado")
