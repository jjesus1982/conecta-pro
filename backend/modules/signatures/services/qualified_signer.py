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
from datetime import UTC, datetime

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


# Certificado A1 por EMPRESA (multi-CNPJ). Cada empresa tem seu .p12 e sua senha,
# ambos vindos SÓ de env (nunca hardcoded/logados). empresa_slug None => Eletrônica
# (CNPJ1): comportamento histórico byte-idêntico.
_CERT_POR_EMPRESA: dict[str, dict] = {
    "conecta_eletronica": {
        "path_envs": ("CERT_A1_PATH", "CERTIFICATE_PATH"),
        "path_default": DEFAULT_CERT_PATH,
        "password_env": "CERT_A1_PASSWORD",  # pragma: allowlist secret — NOME da env, não a senha
    },
    "conecta_patrimonial": {
        "path_envs": ("CERT_A1_PATH_PATRIMONIAL",),
        "path_default": "/app/credentials/certificates/patrimonial.pfx",
        "password_env": "CERT_A1_PASSWORD_PATRIMONIAL",  # pragma: allowlist secret — NOME da env
    },
}
_EMPRESA_DEFAULT = "conecta_eletronica"


def _cfg_empresa(empresa_slug: str | None) -> dict:
    """Config de certificado da empresa (slug em empresas.slug). Slug desconhecido/None
    cai na Eletrônica (CNPJ1) — nunca assume a empresa nova por acidente."""
    return _CERT_POR_EMPRESA.get(empresa_slug or _EMPRESA_DEFAULT, _CERT_POR_EMPRESA[_EMPRESA_DEFAULT])


def _cert_path(empresa_slug: str | None = None) -> str:
    """Caminho do .p12 da empresa — env específica da empresa, senão default documentado."""
    cfg = _cfg_empresa(empresa_slug)
    for env in cfg["path_envs"]:
        val = os.getenv(env)
        if val:
            return val
    return cfg["path_default"]


def _cert_password(empresa_slug: str | None = None) -> bytes:
    """Senha do .p12 da empresa — SOMENTE via env específica. Nunca hardcoded/logada."""
    cfg = _cfg_empresa(empresa_slug)
    env = cfg["password_env"]
    pwd = os.getenv(env)
    if not pwd:
        raise CertificadoIndisponivelError(
            f"Variável de ambiente {env} não definida. Configure-a no .env (senha do "
            f"certificado A1 desta empresa) antes de assinar com assinatura qualificada "
            f"ICP-Brasil. A senha nunca é embutida no código."
        )
    return pwd.encode("utf-8")


def _cn(name) -> str:
    """Extrai o Common Name legível de um x509 Name (asn1crypto)."""
    try:
        return name.native.get("common_name", name.human_friendly)
    except Exception:  # noqa: BLE001
        return str(name.human_friendly)


_SELO_SEAL_CANDS = (
    "/app/uploads/assets/pdf/seal.png",
    "/app/uploads/assets/conecta-mais/lototipo-conecta.png",
    "/app/uploads/assets/conecta-mais/conecta-mais.png",
    "/app/uploads/assets/pdf/cover.png",
)

# Razão social de EXIBIÇÃO por CNPJ (marca atual). Usado no selo visível, pois o
# certificado A1 da Eletrônica traz a razão antiga ("JORDAN SANTOS DE JESUS LTDA").
_RAZAO_POR_CNPJ = {
    "35710481000103": "CONECTA MAIS ELETRÔNICA LTDA",
    "66014833000110": "CONECTA MAIS PATRIMONIAL LTDA",
}


def _estampar_selo_eletronico(pdf_bytes: bytes, nome, cpf, sha256, quando=None, slot: int = 0) -> bytes:
    """SELO VISÍVEL da assinatura ELETRÔNICA SIMPLES (funcionário/cliente) — MP 2.200-2.
    Distinto do ICP-Brasil da empresa (acento VERDE + selo de check), CENTRALIZADO no rodapé
    da última página. É a camada visual; a prova é o hash SHA-256 + evidências. Best-effort."""
    import re as _re
    from datetime import timedelta

    import fitz  # PyMuPDF

    if quando is not None and hasattr(quando, "strftime"):
        when = quando.strftime("%d/%m/%Y %H:%M:%S")
    else:
        when = (datetime.now(UTC) - timedelta(hours=4)).strftime("%d/%m/%Y %H:%M:%S")  # Manaus
    dig = _re.sub(r"\D", "", str(cpf or ""))
    cpf_f = f"{dig[:3]}.{dig[3:6]}.{dig[6:9]}-{dig[9:11]}" if len(dig) == 11 else (str(cpf or "").strip())
    h = (str(sha256 or ""))[:24]

    navy = (0.086, 0.153, 0.290)
    green = (0.086, 0.53, 0.30)
    greend = (0.055, 0.40, 0.23)
    gray = (0.42, 0.47, 0.55)
    light = (0.949, 0.980, 0.960)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pg = doc[-1]
        w, h_pg = pg.rect.width, pg.rect.height
        bw, bh = 316, 76
        x0 = (w - bw) / 2
        y0 = h_pg - bh - 44 - slot * (bh + 8)  # slot 0 = rodapé; 1 = acima (empilha sem sobrepor)
        x1, y1 = x0 + bw, y0 + bh
        # 🔴 `k` e `compacto` eram usados abaixo e NUNCA definidos AQUI. Entraram em
        # ef63c0dfe (17/08/2026), que os criou na função irmã `_estampar_icp` — onde a
        # caixa é variável — e deixou esta usando nomes que não existem no escopo dela.
        # Resultado: `NameError: name 'k' is not defined` em TODA assinatura eletrônica, e
        # o `except` que engolia o erro escondeu isso por 4 dias. O selo nunca era gerado.
        # Aqui a caixa é fixa em 316x76, que é o denominador de k — logo k = 1.0 e
        # compacto = False; mantidos como variáveis para as duas funções continuarem
        # legíveis lado a lado.
        k = min(1.0, bw / 316.0, bh / 76.0)
        compacto = bw < 260
        sh = pg.new_shape()
        sh.draw_rect(fitz.Rect(x0, y0, x1, y1))
        sh.finish(color=greend, fill=light, width=1.1)
        sh.draw_rect(fitz.Rect(x0, y0, x0 + 5 * k, y1))
        sh.finish(color=green, fill=green, width=0)
        sh.commit()
        # selo de CHECK verde (distingue da assinatura ICP-Brasil da empresa)
        cx, cy, rr = x0 + 34, y0 + 38, 16
        s2 = pg.new_shape()
        s2.draw_circle(fitz.Point(cx, cy), rr)
        s2.finish(color=green, fill=None, width=1.5)
        s2.draw_polyline([fitz.Point(cx - 7, cy + 1), fitz.Point(cx - 2, cy + 7), fitz.Point(cx + 8, cy - 7)])
        s2.finish(color=green, width=2.2)
        s2.commit()
        tx = x0 + (12 if compacto else 66 * k)
        pg.insert_text((tx, y0 + 19), "ASSINADO ELETRONICAMENTE", fontsize=9, color=greend, fontname="hebo")
        pg.insert_text(
            (tx, y0 + 33),
            f"{(str(nome or 'Funcionário'))[:40]}  ·  CPF {cpf_f}",
            fontsize=8,
            color=navy,
            fontname="hebo",
        )
        pg.insert_text(
            (tx, y0 + 45),
            f"{when} (Manaus)  ·  via Conecta PRO (MP 2.200-2)",
            fontsize=7.2,
            color=gray,
            fontname="helv",
        )
        pg.insert_text(
            (tx, y0 + 59), f"SHA-256: {h}…  ·  conectamais.pro/verificar", fontsize=6.6, color=green, fontname="helv"
        )
        return doc.tobytes(deflate=True)
    finally:
        doc.close()


def _estampar_selo_branded(
    pdf_bytes: bytes, subject_cn: str, slot: int = 0, rect: tuple[float, float, float, float] | None = None
) -> bytes:
    """Desenha um SELO VISÍVEL branded (marca Conecta Mais) CENTRALIZADO no rodapé da
    última página — como Sólides/DocuSign. É a camada VISUAL; a validade jurídica vem da
    assinatura PAdES (que cobre este selo). Best-effort: erro aqui não bloqueia a assinatura.

    Cores da marca: navy #16277D / #2D5F8B, laranja #F26522. Mostra titular, CNPJ formatado,
    AC emissora e data/hora de Manaus (UTC-4)."""
    import re as _re
    from datetime import timedelta

    import fitz  # PyMuPDF

    m = _re.match(r"(.*?):(\d{6,14})\s*$", (subject_cn or "").strip())
    dig = m.group(2) if m else ""
    cnpj = f"{dig[:2]}.{dig[2:5]}.{dig[5:8]}/{dig[8:12]}-{dig[12:14]}" if len(dig) == 14 else dig
    # Razão de EXIBIÇÃO por CNPJ (marca atual). O certificado pode trazer razão ANTIGA
    # (o cert da Eletrônica tem "JORDAN SANTOS DE JESUS LTDA"); o CNPJ é o identificador.
    razao = _RAZAO_POR_CNPJ.get(dig)
    if not razao:  # fallback: razão do próprio cert, com a marca separada
        razao = _re.sub(
            r"CONECTAMAIS", "CONECTA MAIS", (m.group(1) if m else (subject_cn or "")).strip(), flags=_re.IGNORECASE
        )
    when = (datetime.now(UTC) - timedelta(hours=4)).strftime("%d/%m/%Y %H:%M:%S")  # Manaus (com segundos)

    seal = next((c for c in _SELO_SEAL_CANDS if os.path.exists(c)), None)
    navy = (0.086, 0.153, 0.290)
    navy2 = (0.176, 0.365, 0.545)
    orange = (0.949, 0.396, 0.133)
    gray = (0.42, 0.47, 0.55)
    light = (0.969, 0.980, 0.992)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    try:
        pg = doc[-1]
        w, h = pg.rect.width, pg.rect.height
        if rect:
            # Posição EXPLÍCITA: o chamador sabe onde fica a linha de assinatura do
            # documento. No rodapé fixo, o selo caía por cima do nome e do cargo de quem
            # assina — o campo de assinatura existe justamente para receber a assinatura.
            x0, y0, x1, y1 = rect
            bw, bh = x1 - x0, y1 - y0
        else:
            bw, bh = 316, 76
            x0 = (w - bw) / 2
            y0 = h - bh - 44 - slot * (bh + 8)  # slot 0 = rodapé; 1 = acima
            x1, y1 = x0 + bw, y0 + bh
        # Tipografia proporcional à caixa: fixa em caixa menor estoura o texto para fora.
        k = min(1.0, bw / 316.0, bh / 76.0)
        # Caixa ESTREITA (encaixe na linha de assinatura, ~210pt): o logo comeria 1/5 da
        # largura e sobraria pouco para o texto. Sem ele, a fonte cabe maior e fica
        # legível — que é o ponto de um selo que a pessoa precisa ler.
        compacto = bw < 260
        sh = pg.new_shape()
        sh.draw_rect(fitz.Rect(x0, y0, x1, y1))
        sh.finish(color=navy2, fill=light, width=1.1)
        sh.draw_rect(fitz.Rect(x0, y0, x0 + 5, y1))
        sh.finish(color=orange, fill=orange, width=0)
        sh.commit()
        if seal and not compacto:
            try:
                pg.insert_image(
                    fitz.Rect(x0 + 13 * k, y0 + 17 * k, x0 + 55 * k, y0 + 59 * k),
                    filename=seal,
                    keep_proportion=True,
                    overlay=True,
                )
            except Exception:  # noqa: BLE001
                pass
        # Linhas do selo: (texto, tamanho compacto, tamanho normal, cor, fonte)
        _linhas = [
            ("ASSINADO DIGITALMENTE  ·  ICP-Brasil", 7.4, 9 * k, navy, "hebo"),
            (razao[: (30 if compacto else 44)], 7.0, 8 * k, navy2, "hebo"),
            (f"CNPJ {cnpj}  ·  AC SOLUTI (fé pública)", 6.0, 7.2 * k, gray, "helv"),
            (f"{when}  ·  PAdES  ·  conectamais.pro/verificar", 5.4, 6.6 * k, orange, "helv"),
        ]
        if compacto:
            # CENTRALIZADO de verdade: cada linha medida e posta no meio do espaço útil
            # (a caixa menos a barra laranja). Alinhar tudo à esquerda com uma margem
            # fixa deixava 54pt de vazio à direita — o selo parecia empurrado para o
            # canto. Verticalmente, o bloco inteiro é centrado na altura da caixa.
            barra = 5 * k
            util_x0, util_larg = x0 + barra, bw - barra
            alt_linha = 11.5
            bloco = alt_linha * len(_linhas)
            base = y0 + (bh - bloco) / 2 + 8.5
            for i, (txt, fs_c, _fs_n, cor, fn) in enumerate(_linhas):
                larg = fitz.get_text_length(txt, fontname=fn, fontsize=fs_c)
                px = util_x0 + max(0.0, (util_larg - larg) / 2)
                pg.insert_text((px, base + i * alt_linha), txt, fontsize=fs_c, color=cor, fontname=fn)
        else:
            tx = x0 + 66 * k
            for i, (txt, _fs_c, fs_n, cor, fn) in enumerate(_linhas):
                pg.insert_text((tx, y0 + (19, 33, 45, 59)[i] * k), txt, fontsize=fs_n, color=cor, fontname=fn)
        return doc.tobytes(deflate=True)
    finally:
        doc.close()


def assinar_pdf_icp_brasil(
    pdf_bytes: bytes,
    *,
    reason: str = "Assinatura qualificada ICP-Brasil — Contrato",
    location: str = "Manaus/AM",
    field_name: str = "AssinaturaEmpresaICPBrasil",
    contact_info: str | None = None,
    empresa_slug: str | None = None,
    visivel: bool = True,
    slot: int = 0,
    rect: tuple[float, float, float, float] | None = None,
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

    cert_path = _cert_path(empresa_slug)
    if not os.path.exists(cert_path):
        raise CertificadoIndisponivelError(
            f"Certificado A1 não encontrado em '{cert_path}' (empresa "
            f"'{empresa_slug or _EMPRESA_DEFAULT}'). Ajuste a env de caminho do cert."
        )

    passphrase = _cert_password(empresa_slug)  # levanta se env ausente

    try:
        signer = signers.SimpleSigner.load_pkcs12(
            pfx_file=cert_path,
            passphrase=passphrase,
        )
    except Exception as exc:  # noqa: BLE001
        # NUNCA logar exc com o conteúdo do .p12 nem a senha.
        raise QualifiedSignatureError(
            "Falha ao abrir o certificado A1 (verifique CERT_A1_PASSWORD). Detalhe técnico omitido por segurança."
        ) from exc

    cert = signer.signing_cert

    # Validação de validade (não expirado) ANTES de assinar — erro honesto.
    now = datetime.now(UTC)
    not_before = cert.not_valid_before
    not_after = cert.not_valid_after
    if now < not_before:
        raise CertificadoExpiradoError(f"Certificado A1 ainda não é válido (início em {not_before.isoformat()}).")
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

    # SELO VISÍVEL branded (marca Conecta Mais) desenhado ANTES de assinar — centralizado no
    # rodapé da última página, como Sólides/DocuSign. A assinatura PAdES cobre o selo.
    # Best-effort: se o desenho falhar, assina o PDF original (sem selo), nunca bloqueia.
    pdf_para_assinar = pdf_bytes
    if visivel:
        try:
            pdf_para_assinar = _estampar_selo_branded(pdf_bytes, _cn(cert.subject), slot=slot, rect=rect)
        except Exception:  # noqa: BLE001
            pdf_para_assinar = pdf_bytes

    pdf_signer = signers.PdfSigner(meta, signer=signer)

    out = io.BytesIO()
    try:
        writer = IncrementalPdfFileWriter(io.BytesIO(pdf_para_assinar))
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
        "PDF assinado com A1 ICP-Brasil: subject_cn=%s issuer_cn=%s serial=%s valido_ate=%s bytes=%d",
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


def certificado_status(empresa_slug: str | None = None) -> dict:
    """Diagnóstico do certificado A1 da empresa (para health/painel). Nunca expõe a senha.

    Returns:
        Dict com disponibilidade, validade e titular. Se algo falhar, devolve
        `available=False` com o motivo — sem vazar segredo.
    """
    try:
        from pyhanko.sign import signers
    except ImportError:
        return {"available": False, "reason": "pyhanko não instalado (falta bake)."}

    cfg = _cfg_empresa(empresa_slug)
    cert_path = _cert_path(empresa_slug)
    if not os.path.exists(cert_path):
        return {"available": False, "reason": f"Certificado não encontrado em {cert_path}."}
    if not os.getenv(cfg["password_env"]):
        return {"available": False, "reason": f"{cfg['password_env']} não configurada."}

    try:
        signer = signers.SimpleSigner.load_pkcs12(pfx_file=cert_path, passphrase=_cert_password(empresa_slug))
    except Exception:  # noqa: BLE001
        return {"available": False, "reason": "Falha ao abrir o certificado (senha?)."}

    cert = signer.signing_cert
    now = datetime.now(UTC)
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
