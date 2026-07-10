"""
Assinatura QUALIFICADA ICP-Brasil (certificado A1) — camada criptográfica pura.

Isola a mecânica PAdES (assinatura digital embutida no PDF) do motor de
persistência (`UniversalSignatureService`). Aqui NÃO há banco: só bytes de PDF
entram e bytes de PDF assinado (PAdES) saem, mais os metadados do certificado.

Certificado: A1 (.p12/.pfx) da empresa — titular CNPJ 35.710.481/0001-03
(CONECTAMAIS ELETRONICA LTDA), emitido por AC SOLUTI Multipla v5 (ICP-Brasil).
O .p12 já embute a cadeia completa (AC intermediária → AC → Raiz Brasileira v5),
portanto a assinatura resultante carrega a cadeia ICP-Brasil e valida em qualquer
verificador com a âncora do ITI (Adobe Reader BR, validador ITI, gov.br).

SEGURANÇA:
- A senha do .p12 vem SOMENTE da env `CERT_A1_PASSWORD`. Nunca é hardcoded,
  nunca é logada, e o conteúdo do .p12 nunca é logado.
- O certificado é validado (não expirado) ANTES de assinar; se vencido, levanta
  `CertificadoExpiradoError` com mensagem honesta.

Lib: pyhanko (PAdES). Escolhida sobre `endesive` porque endesive arrasta
`pykcs11` (token A3/hardware) que exige toolchain de build (SWIG) e falha no bake;
pyhanko instala com dependências puras-Python (asn1crypto, oscrypto, pyyaml,
uritools, pyhanko-certvalidator) e é a lib PAdES mais mantida do ecossistema.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Caminho do .p12 da empresa. Env override, com fallback documentado para o
# caminho montado no container (bind mount de /opt/conecta-pro/credentials).
DEFAULT_CERT_PATH = "/app/credentials/certificates/certificado.pfx"


class QualifiedSignatureError(RuntimeError):
    """Erro genérico na assinatura qualificada ICP-Brasil."""


class CertificadoExpiradoError(QualifiedSignatureError):
    """O certificado A1 está fora do período de validade."""


class CertificadoIndisponivelError(QualifiedSignatureError):
    """O .p12 não foi encontrado ou a senha (env) não está configurada."""


@dataclass
class QualifiedSignatureResult:
    """Resultado da assinatura PAdES ICP-Brasil."""

    signed_pdf: bytes
    certificate_subject_cn: str
    certificate_issuer_cn: str
    certificate_serial: str
    certificate_valid_from: datetime
    certificate_valid_to: datetime


def _cert_path() -> str:
    """Caminho do .p12 — env `CERT_A1_PATH`, senão `CERTIFICATE_PATH`, senão default."""
    return (
        os.getenv("CERT_A1_PATH")
        or os.getenv("CERTIFICATE_PATH")
        or DEFAULT_CERT_PATH
    )


def _cert_password() -> bytes:
    """Senha do .p12 — SOMENTE via env `CERT_A1_PASSWORD`. Nunca hardcoded/logada."""
    pwd = os.getenv("CERT_A1_PASSWORD")
    if not pwd:
        raise CertificadoIndisponivelError(
            "Variável de ambiente CERT_A1_PASSWORD não definida. Configure-a no "
            ".env (senha do certificado A1) antes de assinar contratos com "
            "assinatura qualificada ICP-Brasil. A senha nunca é embutida no código."
        )
    return pwd.encode("utf-8")


def _cn(name) -> str:
    """Extrai o Common Name legível de um x509 Name (asn1crypto)."""
    try:
        return name.native.get("common_name", name.human_friendly)
    except Exception:  # noqa: BLE001
        return str(name.human_friendly)


def assinar_pdf_icp_brasil(
    pdf_bytes: bytes,
    *,
    reason: str = "Assinatura qualificada ICP-Brasil — Contrato",
    location: str = "Manaus/AM",
    field_name: str = "AssinaturaEmpresaICPBrasil",
    contact_info: str | None = None,
) -> QualifiedSignatureResult:
    """Assina um PDF com o certificado A1 da empresa (PAdES, ICP-Brasil).

    Args:
        pdf_bytes: Conteúdo do PDF do contrato a assinar.
        reason: Motivo da assinatura (gravado no dicionário de assinatura PDF).
        location: Local da assinatura.
        field_name: Nome do campo de assinatura embutido.
        contact_info: Contato do signatário (opcional).

    Returns:
        QualifiedSignatureResult com o PDF assinado e os metadados do certificado.

    Raises:
        CertificadoIndisponivelError: .p12 ausente ou CERT_A1_PASSWORD não setada.
        CertificadoExpiradoError: certificado fora da validade.
        QualifiedSignatureError: falha ao assinar.
    """
    if not pdf_bytes:
        raise QualifiedSignatureError("PDF vazio: nada a assinar.")

    # Import tardio: a lib só é exigida quando de fato se assina em nível QUALIFIED,
    # para não quebrar o boot em ambientes onde a lib ainda não foi bakeada.
    try:
        from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
        from pyhanko.sign import signers
        from pyhanko.sign.signers.pdf_signer import PdfSignatureMetadata
    except ImportError as exc:  # pragma: no cover
        raise QualifiedSignatureError(
            "Biblioteca de assinatura PAdES (pyhanko) não instalada. "
            "Adicione 'pyhanko' ao requirements e refaça o bake da imagem."
        ) from exc

    cert_path = _cert_path()
    if not os.path.exists(cert_path):
        raise CertificadoIndisponivelError(
            f"Certificado A1 não encontrado em '{cert_path}'. Ajuste CERT_A1_PATH "
            f"ou CERTIFICATE_PATH."
        )

    passphrase = _cert_password()  # levanta se env ausente

    try:
        signer = signers.SimpleSigner.load_pkcs12(
            pfx_file=cert_path,
            passphrase=passphrase,
        )
    except Exception as exc:  # noqa: BLE001
        # NUNCA logar exc com o conteúdo do .p12 nem a senha.
        raise QualifiedSignatureError(
            "Falha ao abrir o certificado A1 (verifique CERT_A1_PASSWORD). "
            "Detalhe técnico omitido por segurança."
        ) from exc

    cert = signer.signing_cert

    # Validação de validade (não expirado) ANTES de assinar — erro honesto.
    now = datetime.now(timezone.utc)
    not_before = cert.not_valid_before
    not_after = cert.not_valid_after
    if now < not_before:
        raise CertificadoExpiradoError(
            f"Certificado A1 ainda não é válido (início em {not_before.isoformat()})."
        )
    if now > not_after:
        raise CertificadoExpiradoError(
            f"Certificado A1 VENCIDO em {not_after.isoformat()}. "
            f"Renove o certificado ICP-Brasil antes de assinar contratos."
        )

    meta = PdfSignatureMetadata(
        field_name=field_name,
        reason=reason,
        location=location,
        contact_info=contact_info,
    )
    pdf_signer = signers.PdfSigner(meta, signer=signer)

    out = io.BytesIO()
    try:
        writer = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))
        # pyhanko.sign_pdf() usa asyncio.run() internamente, o que estoura se já
        # houver um event loop (rotas async do FastAPI). Detectamos o loop e, se
        # existir, usamos a API async em um loop dedicado numa thread separada.
        import asyncio

        async def _run_async_sign() -> None:
            await pdf_signer.async_sign_pdf(writer, output=out)

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            # sem loop rodando: caminho síncrono normal
            pdf_signer.sign_pdf(writer, output=out)
        else:
            # já dentro de um event loop: roda o sign async numa thread própria
            import concurrent.futures

            def _thread_target() -> None:
                asyncio.run(_run_async_sign())

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pool.submit(_thread_target).result()
    except QualifiedSignatureError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise QualifiedSignatureError(f"Falha ao assinar o PDF (PAdES): {exc}") from exc

    logger.info(
        "PDF assinado com A1 ICP-Brasil: subject_cn=%s issuer_cn=%s serial=%s "
        "valido_ate=%s bytes=%d",
        _cn(cert.subject),
        _cn(cert.issuer),
        hex(cert.serial_number),
        not_after.isoformat(),
        out.getbuffer().nbytes,
    )

    return QualifiedSignatureResult(
        signed_pdf=out.getvalue(),
        certificate_subject_cn=_cn(cert.subject),
        certificate_issuer_cn=_cn(cert.issuer),
        certificate_serial=hex(cert.serial_number),
        certificate_valid_from=not_before.replace(tzinfo=None),
        certificate_valid_to=not_after.replace(tzinfo=None),
    )


def certificado_status() -> dict:
    """Diagnóstico do certificado A1 (para health/painel). Nunca expõe a senha.

    Returns:
        Dict com disponibilidade, validade e titular. Se algo falhar, devolve
        `available=False` com o motivo — sem vazar segredo.
    """
    try:
        from pyhanko.sign import signers
    except ImportError:
        return {"available": False, "reason": "pyhanko não instalado (falta bake)."}

    cert_path = _cert_path()
    if not os.path.exists(cert_path):
        return {"available": False, "reason": f"Certificado não encontrado em {cert_path}."}
    if not os.getenv("CERT_A1_PASSWORD"):
        return {"available": False, "reason": "CERT_A1_PASSWORD não configurada."}

    try:
        signer = signers.SimpleSigner.load_pkcs12(
            pfx_file=cert_path, passphrase=_cert_password()
        )
    except Exception:  # noqa: BLE001
        return {"available": False, "reason": "Falha ao abrir o certificado (senha?)."}

    cert = signer.signing_cert
    now = datetime.now(timezone.utc)
    return {
        "available": True,
        "subject_cn": _cn(cert.subject),
        "issuer_cn": _cn(cert.issuer),
        "serial": hex(cert.serial_number),
        "valid_from": cert.not_valid_before.isoformat(),
        "valid_to": cert.not_valid_after.isoformat(),
        "expired": now > cert.not_valid_after,
        "days_to_expire": (cert.not_valid_after - now).days,
    }
