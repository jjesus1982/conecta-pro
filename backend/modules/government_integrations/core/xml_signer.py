"""
Assinador XML Digital (XMLDSig)
Sprint 33: Integrações Governamentais

Implementa assinatura digital XML conforme padrão XMLDSig para:
- eSocial
- SEFAZ (NF-e, NFC-e, CT-e, MDF-e)
- Outros sistemas governamentais

Referências:
- W3C XML Signature: https://www.w3.org/TR/xmldsig-core/
- Manual eSocial: https://www.gov.br/esocial/
- Manual NF-e: https://www.nfe.fazenda.gov.br/
"""

import base64
import hashlib
import logging
from dataclasses import dataclass
from enum import StrEnum

from lxml import etree

from modules.government_integrations.core.certificate_manager import CertificateManager

logger = logging.getLogger(__name__)


# Namespaces XML
NAMESPACES = {
    "ds": "http://www.w3.org/2000/09/xmldsig#",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "esocial": "http://www.esocial.gov.br/schema/evt/",
    "nfe": "http://www.portalfiscal.inf.br/nfe",
    "cte": "http://www.portalfiscal.inf.br/cte",
    "mdfe": "http://www.portalfiscal.inf.br/mdfe",
}


class SignatureType(StrEnum):
    """Tipos de assinatura suportados."""

    ESOCIAL = "esocial"
    NFE = "nfe"
    NFCE = "nfce"
    CTE = "cte"
    MDFE = "mdfe"
    GENERIC = "generic"


class DigestMethod(StrEnum):
    """Métodos de digest suportados."""

    SHA1 = "http://www.w3.org/2000/09/xmldsig#sha1"
    SHA256 = "http://www.w3.org/2001/04/xmlenc#sha256"


class SignatureMethod(StrEnum):
    """Métodos de assinatura suportados."""

    RSA_SHA1 = "http://www.w3.org/2000/09/xmldsig#rsa-sha1"
    RSA_SHA256 = "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256"


class CanonicalizationMethod(StrEnum):
    """Métodos de canonicalização."""

    C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
    C14N_EXCLUSIVE = "http://www.w3.org/2001/10/xml-exc-c14n#"


class TransformMethod(StrEnum):
    """Métodos de transformação."""

    ENVELOPED = "http://www.w3.org/2000/09/xmldsig#enveloped-signature"
    C14N = "http://www.w3.org/TR/2001/REC-xml-c14n-20010315"
    C14N_EXCLUSIVE = "http://www.w3.org/2001/10/xml-exc-c14n#"


@dataclass
class SignatureConfig:
    """Configuração de assinatura."""

    signature_type: SignatureType
    digest_method: DigestMethod = DigestMethod.SHA1
    signature_method: SignatureMethod = SignatureMethod.RSA_SHA1
    canonicalization: CanonicalizationMethod = CanonicalizationMethod.C14N
    transforms: list = None
    reference_uri: str = ""  # URI do elemento a assinar

    def __post_init__(self):
        if self.transforms is None:
            self.transforms = [
                TransformMethod.ENVELOPED,
                TransformMethod.C14N,
            ]


# Configurações padrão por tipo
DEFAULT_CONFIGS = {
    SignatureType.ESOCIAL: SignatureConfig(
        signature_type=SignatureType.ESOCIAL,
        digest_method=DigestMethod.SHA256,
        signature_method=SignatureMethod.RSA_SHA256,
        canonicalization=CanonicalizationMethod.C14N,  # Governo exige C14N não-exclusiva
        transforms=[TransformMethod.ENVELOPED, TransformMethod.C14N],
    ),
    SignatureType.NFE: SignatureConfig(
        signature_type=SignatureType.NFE,
        digest_method=DigestMethod.SHA1,
        signature_method=SignatureMethod.RSA_SHA1,
        canonicalization=CanonicalizationMethod.C14N,
        transforms=[TransformMethod.ENVELOPED, TransformMethod.C14N],
    ),
    SignatureType.NFCE: SignatureConfig(
        signature_type=SignatureType.NFCE,
        digest_method=DigestMethod.SHA1,
        signature_method=SignatureMethod.RSA_SHA1,
        canonicalization=CanonicalizationMethod.C14N,
        transforms=[TransformMethod.ENVELOPED, TransformMethod.C14N],
    ),
    SignatureType.CTE: SignatureConfig(
        signature_type=SignatureType.CTE,
        digest_method=DigestMethod.SHA1,
        signature_method=SignatureMethod.RSA_SHA1,
        canonicalization=CanonicalizationMethod.C14N,
        transforms=[TransformMethod.ENVELOPED, TransformMethod.C14N],
    ),
    SignatureType.MDFE: SignatureConfig(
        signature_type=SignatureType.MDFE,
        digest_method=DigestMethod.SHA1,
        signature_method=SignatureMethod.RSA_SHA1,
        canonicalization=CanonicalizationMethod.C14N,
        transforms=[TransformMethod.ENVELOPED, TransformMethod.C14N],
    ),
}


class XMLSigner:
    """
    Assinador de documentos XML conforme padrão XMLDSig.

    Implementa assinatura envelopada (enveloped signature) usada
    por eSocial, SEFAZ e outros sistemas governamentais.
    """

    def __init__(self, certificate_manager: CertificateManager):
        """
        Inicializa o assinador.

        Args:
            certificate_manager: Gerenciador de certificado carregado
        """
        self.cert_manager = certificate_manager

        # Garantir que certificado está carregado
        if not certificate_manager._loaded:
            certificate_manager.load()

    def sign(
        self,
        xml_content: str,
        signature_type: SignatureType = SignatureType.GENERIC,
        reference_uri: str | None = None,
        config: SignatureConfig | None = None,
    ) -> str:
        """
        Assina documento XML.

        Args:
            xml_content: XML a ser assinado
            signature_type: Tipo de assinatura (define configurações padrão)
            reference_uri: URI do elemento a assinar (ex: "#ID123")
            config: Configuração customizada (sobrescreve padrão)

        Returns:
            XML assinado

        Raises:
            ValueError: Se XML inválido ou erro na assinatura
        """
        # Obter configuração
        if config is None:
            config = DEFAULT_CONFIGS.get(signature_type, SignatureConfig(signature_type=SignatureType.GENERIC))

        if reference_uri:
            config.reference_uri = reference_uri

        try:
            # Parse XML
            xml_doc = etree.fromstring(xml_content.encode("utf-8"))  # noqa: S320 - Necessário para assinatura XML NF-e

            # Encontrar elemento a assinar
            element_to_sign = self._find_element_to_sign(xml_doc, config.reference_uri)

            # Calcular digest do elemento
            digest_value = self._calculate_digest(element_to_sign, config)

            # Criar elemento Signature
            signature_element = self._create_signature_element(digest_value, config)

            # Inserir Signature no documento
            self._insert_signature(xml_doc, signature_element, config.signature_type)

            # Calcular SignatureValue
            signed_info = signature_element.find(".//ds:SignedInfo", NAMESPACES)
            signature_value = self._calculate_signature(signed_info, config)

            # Atualizar SignatureValue no documento
            sig_value_elem = signature_element.find(".//ds:SignatureValue", NAMESPACES)
            sig_value_elem.text = signature_value

            # Serializar XML assinado
            signed_xml = etree.tostring(xml_doc, encoding="unicode", xml_declaration=False)

            # Adicionar declaração XML se necessário
            if not signed_xml.startswith("<?xml"):
                signed_xml = '<?xml version="1.0" encoding="UTF-8"?>' + signed_xml

            logger.debug(f"XML assinado com sucesso ({config.signature_type.value})")
            return signed_xml

        except Exception as e:
            logger.error(f"Erro ao assinar XML: {e}")
            raise ValueError(f"Erro ao assinar XML: {e}")

    def _find_element_to_sign(self, xml_doc: etree._Element, reference_uri: str) -> etree._Element:
        """Encontra elemento a ser assinado."""
        if not reference_uri or reference_uri == "":
            # Assinar documento inteiro
            return xml_doc

        # Remover # do início
        element_id = reference_uri.lstrip("#")

        # Buscar por Id ou id
        element = xml_doc.find(f'.//*[@Id="{element_id}"]')
        if element is None:
            element = xml_doc.find(f'.//*[@id="{element_id}"]')

        if element is None:
            # Tentar busca mais ampla
            for elem in xml_doc.iter():
                if elem.get("Id") == element_id or elem.get("id") == element_id:
                    element = elem
                    break

        if element is None:
            raise ValueError(f"Elemento com Id '{element_id}' não encontrado")

        return element

    def _calculate_digest(self, element: etree._Element, config: SignatureConfig) -> str:
        """Calcula digest do elemento."""
        # Canonicalizar elemento
        canonicalized = self._canonicalize(element, config)

        # Calcular hash
        if config.digest_method == DigestMethod.SHA256:
            hash_obj = hashlib.sha256(canonicalized)
        else:
            hash_obj = hashlib.sha1(canonicalized, usedforsecurity=False)  # noqa: S324 - SEFAZ exige SHA1 para assinatura XML

        digest = base64.b64encode(hash_obj.digest()).decode("ascii")
        return digest

    def _canonicalize(self, element: etree._Element, config: SignatureConfig) -> bytes:
        """Canonicaliza elemento XML."""
        exclusive = config.canonicalization == CanonicalizationMethod.C14N_EXCLUSIVE

        # Se o elemento tem Signature embutida (transform enveloped), remove numa cópia.
        # Caso contrário, canonicaliza IN-PLACE — preserva o contexto de namespace dos
        # ancestrais (essencial p/ o digest bater com o que o SEFIN recalcula).
        if element.find(".//ds:Signature", NAMESPACES) is not None:
            element_copy = etree.fromstring(etree.tostring(element))  # noqa: S320
            for sig in element_copy.findall(".//ds:Signature", NAMESPACES):
                sig.getparent().remove(sig)
            return etree.tostring(element_copy, method="c14n", exclusive=exclusive, with_comments=False)
        return etree.tostring(element, method="c14n", exclusive=exclusive, with_comments=False)

    def _create_signature_element(self, digest_value: str, config: SignatureConfig) -> etree._Element:
        """Cria elemento Signature."""
        ds_ns = NAMESPACES["ds"]

        # Criar elemento Signature
        signature = etree.Element(f"{{{ds_ns}}}Signature", nsmap={"ds": ds_ns})

        # SignedInfo
        signed_info = etree.SubElement(signature, f"{{{ds_ns}}}SignedInfo")

        # CanonicalizationMethod
        c14n_method = etree.SubElement(signed_info, f"{{{ds_ns}}}CanonicalizationMethod")
        c14n_method.set("Algorithm", config.canonicalization.value)

        # SignatureMethod
        sig_method = etree.SubElement(signed_info, f"{{{ds_ns}}}SignatureMethod")
        sig_method.set("Algorithm", config.signature_method.value)

        # Reference
        reference = etree.SubElement(signed_info, f"{{{ds_ns}}}Reference")
        reference.set("URI", config.reference_uri)

        # Transforms
        transforms = etree.SubElement(reference, f"{{{ds_ns}}}Transforms")
        for transform in config.transforms:
            transform_elem = etree.SubElement(transforms, f"{{{ds_ns}}}Transform")
            transform_elem.set("Algorithm", transform.value)

        # DigestMethod
        digest_method = etree.SubElement(reference, f"{{{ds_ns}}}DigestMethod")
        digest_method.set("Algorithm", config.digest_method.value)

        # DigestValue
        digest_value_elem = etree.SubElement(reference, f"{{{ds_ns}}}DigestValue")
        digest_value_elem.text = digest_value

        # SignatureValue (vazio, será preenchido depois)
        sig_value = etree.SubElement(signature, f"{{{ds_ns}}}SignatureValue")
        sig_value.text = ""

        # KeyInfo
        key_info = etree.SubElement(signature, f"{{{ds_ns}}}KeyInfo")
        x509_data = etree.SubElement(key_info, f"{{{ds_ns}}}X509Data")
        x509_cert = etree.SubElement(x509_data, f"{{{ds_ns}}}X509Certificate")
        x509_cert.text = self.cert_manager.get_certificate_base64()

        return signature

    def _insert_signature(self, xml_doc: etree._Element, signature: etree._Element, signature_type: SignatureType):
        """Insere Signature no documento."""
        # Para eSocial: inserir como último child do <eSocial> (sibling do evtXXX)
        # XSD exige: <eSocial><evtXXX Id="...">...</evtXXX><Signature>...</Signature></eSocial>
        if signature_type == SignatureType.ESOCIAL:
            xml_doc.append(signature)
            return

        # Para NFe: inserir após infNFe
        if signature_type in [SignatureType.NFE, SignatureType.NFCE]:
            inf_nfe = xml_doc.find(".//{http://www.portalfiscal.inf.br/nfe}infNFe")
            if inf_nfe is not None:
                inf_nfe.addnext(signature)
                return

        # Para CTe: inserir após infCte
        if signature_type == SignatureType.CTE:
            inf_cte = xml_doc.find(".//{http://www.portalfiscal.inf.br/cte}infCte")
            if inf_cte is not None:
                inf_cte.addnext(signature)
                return

        # Fallback: inserir no final do documento
        xml_doc.append(signature)

    def _calculate_signature(self, signed_info: etree._Element, config: SignatureConfig) -> str:
        """Calcula valor da assinatura."""
        # Canonicalizar SignedInfo
        exclusive = config.canonicalization == CanonicalizationMethod.C14N_EXCLUSIVE
        signed_info_c14n = etree.tostring(signed_info, method="c14n", exclusive=exclusive, with_comments=False)

        # Assinar com chave privada
        if config.signature_method == SignatureMethod.RSA_SHA256:
            algorithm = "sha256"
        else:
            algorithm = "sha1"

        signature_bytes = self.cert_manager.sign_data(signed_info_c14n, algorithm)
        signature_b64 = base64.b64encode(signature_bytes).decode("ascii")

        return signature_b64

    def verify(self, signed_xml: str) -> tuple[bool, str]:
        """
        Verifica assinatura de XML.

        Args:
            signed_xml: XML assinado

        Returns:
            Tupla (válido, mensagem)
        """
        try:
            xml_doc = etree.fromstring(signed_xml.encode("utf-8"))  # noqa: S320 - Validação de assinatura

            # Encontrar Signature
            signature = xml_doc.find(".//ds:Signature", NAMESPACES)
            if signature is None:
                return False, "Assinatura não encontrada"

            # Obter valores
            signed_info = signature.find(".//ds:SignedInfo", NAMESPACES)
            sig_value = signature.find(".//ds:SignatureValue", NAMESPACES)
            digest_value = signature.find(".//ds:DigestValue", NAMESPACES)

            if signed_info is None or sig_value is None or digest_value is None:
                return False, "Estrutura de assinatura incompleta"

            # Verificar digest
            reference = signed_info.find(".//ds:Reference", NAMESPACES)
            uri = reference.get("URI", "")

            element = self._find_element_to_sign(xml_doc, uri)

            # Determinar método de digest
            digest_method = reference.find(".//ds:DigestMethod", NAMESPACES)
            method_uri = digest_method.get("Algorithm", "")

            if "sha256" in method_uri.lower():
                config = SignatureConfig(signature_type=SignatureType.GENERIC, digest_method=DigestMethod.SHA256)
            else:
                config = SignatureConfig(signature_type=SignatureType.GENERIC, digest_method=DigestMethod.SHA1)

            calculated_digest = self._calculate_digest(element, config)

            if calculated_digest != digest_value.text:
                return False, "Digest não confere"

            # Verificar assinatura
            sig_method = signed_info.find(".//ds:SignatureMethod", NAMESPACES)
            method_uri = sig_method.get("Algorithm", "")

            if "sha256" in method_uri.lower():
                algorithm = "sha256"
            else:
                algorithm = "sha1"

            # Canonicalizar SignedInfo
            c14n_method = signed_info.find(".//ds:CanonicalizationMethod", NAMESPACES)
            exclusive = "exc" in c14n_method.get("Algorithm", "").lower()

            signed_info_c14n = etree.tostring(signed_info, method="c14n", exclusive=exclusive, with_comments=False)

            # Decodificar assinatura
            sig_bytes = base64.b64decode(sig_value.text)

            # Verificar
            if self.cert_manager.verify_signature(signed_info_c14n, sig_bytes, algorithm):
                return True, "Assinatura válida"
            else:
                return False, "Assinatura inválida"

        except Exception as e:
            return False, f"Erro ao verificar assinatura: {e}"


class ESocialXMLSigner(XMLSigner):
    """Assinador especializado para eSocial."""

    def sign_event(self, xml_content: str, event_id: str) -> str:
        """
        Assina evento eSocial.

        Args:
            xml_content: XML do evento
            event_id: ID do evento (ex: "ID1234567890123...")

        Returns:
            XML assinado
        """
        # Governo exige URI vazia — assinatura sobre documento inteiro
        return self.sign(xml_content, signature_type=SignatureType.ESOCIAL, reference_uri="")


class NFSeNacionalXMLSigner(XMLSigner):
    """Assinador para NFS-e Nacional — SEM prefixo ds: na Signature (resolve E6155)."""

    def _create_signature_element(self, digest_value: str, config: SignatureConfig) -> etree._Element:
        """Cria Signature SEM prefixo de namespace (NFS-e Nacional exige)."""
        ds_ns = NAMESPACES["ds"]

        # nsmap={None: ds_ns} gera <Signature xmlns="..."> sem prefixo "ds:"
        signature = etree.Element(f"{{{ds_ns}}}Signature", nsmap={None: ds_ns})

        signed_info = etree.SubElement(signature, f"{{{ds_ns}}}SignedInfo")

        c14n_method = etree.SubElement(signed_info, f"{{{ds_ns}}}CanonicalizationMethod")
        c14n_method.set("Algorithm", config.canonicalization.value)

        sig_method = etree.SubElement(signed_info, f"{{{ds_ns}}}SignatureMethod")
        sig_method.set("Algorithm", config.signature_method.value)

        reference = etree.SubElement(signed_info, f"{{{ds_ns}}}Reference")
        reference.set("URI", config.reference_uri)

        transforms = etree.SubElement(reference, f"{{{ds_ns}}}Transforms")
        for transform in config.transforms:
            transform_elem = etree.SubElement(transforms, f"{{{ds_ns}}}Transform")
            transform_elem.set("Algorithm", transform.value)

        digest_method = etree.SubElement(reference, f"{{{ds_ns}}}DigestMethod")
        digest_method.set("Algorithm", config.digest_method.value)

        digest_value_elem = etree.SubElement(reference, f"{{{ds_ns}}}DigestValue")
        digest_value_elem.text = digest_value

        sig_value = etree.SubElement(signature, f"{{{ds_ns}}}SignatureValue")
        sig_value.text = ""

        key_info = etree.SubElement(signature, f"{{{ds_ns}}}KeyInfo")
        x509_data = etree.SubElement(key_info, f"{{{ds_ns}}}X509Data")
        x509_cert = etree.SubElement(x509_data, f"{{{ds_ns}}}X509Certificate")
        x509_cert.text = self.cert_manager.get_certificate_base64()

        return signature

    def sign_nfse(self, xml_content: str) -> str:
        """Assina o DPS da NFS-e Nacional com signxml, Signature SEM prefixo ds: (padrão SEFIN).
        C14N robusta (signxml) + namespaces={None: ds} → assinatura válida e sem prefixo."""
        import re as _re

        from cryptography.hazmat.primitives.serialization import (
            Encoding as _Enc,
        )
        from cryptography.hazmat.primitives.serialization import (
            NoEncryption as _NE,
        )
        from cryptography.hazmat.primitives.serialization import (
            PrivateFormat as _PF,
        )
        from lxml import etree as _etree
        from signxml import XMLSigner as _SX
        from signxml import methods as _methods
        from signxml import namespaces as _ns

        m = _re.search(r'<infDPS Id="([^"]+)"', xml_content)
        ref = m.group(1) if m else None
        root = _etree.fromstring(xml_content.encode("utf-8"))
        key_pem = self.cert_manager.private_key.private_bytes(_Enc.PEM, _PF.TraditionalOpenSSL, _NE())
        cert_pem = self.cert_manager.get_certificate_pem()
        signer = _SX(
            method=_methods.enveloped,
            signature_algorithm="rsa-sha256",
            digest_algorithm="sha256",
            c14n_algorithm="http://www.w3.org/TR/2001/REC-xml-c14n-20010315",
        )
        signer.namespaces = {None: _ns.ds}  # Signature sem prefixo ds:
        signed = signer.sign(root, key=key_pem, cert=cert_pem, reference_uri=ref, id_attribute="Id")
        return '<?xml version="1.0" encoding="UTF-8"?>' + _etree.tostring(signed, encoding="unicode")


class NFEXMLSigner(XMLSigner):
    """Assinador especializado para NF-e/NFC-e."""

    def sign_nfe(self, xml_content: str, inf_nfe_id: str) -> str:
        """
        Assina NF-e.

        Args:
            xml_content: XML da NF-e
            inf_nfe_id: ID do infNFe (ex: "NFe35...")

        Returns:
            XML assinado
        """
        return self.sign(xml_content, signature_type=SignatureType.NFE, reference_uri=f"#{inf_nfe_id}")

    def sign_nfce(self, xml_content: str, inf_nfe_id: str) -> str:
        """Assina NFC-e."""
        return self.sign(xml_content, signature_type=SignatureType.NFCE, reference_uri=f"#{inf_nfe_id}")

    def sign_cancellation(self, xml_content: str, inf_evento_id: str) -> str:
        """Assina evento de cancelamento."""
        return self.sign(xml_content, signature_type=SignatureType.NFE, reference_uri=f"#{inf_evento_id}")


class CTEXMLSigner(XMLSigner):
    """Assinador especializado para CT-e."""

    def sign_cte(self, xml_content: str, inf_cte_id: str) -> str:
        """Assina CT-e."""
        return self.sign(xml_content, signature_type=SignatureType.CTE, reference_uri=f"#{inf_cte_id}")


class MDFEXMLSigner(XMLSigner):
    """Assinador especializado para MDF-e."""

    def sign_mdfe(self, xml_content: str, inf_mdfe_id: str) -> str:
        """Assina MDF-e."""
        return self.sign(xml_content, signature_type=SignatureType.MDFE, reference_uri=f"#{inf_mdfe_id}")
