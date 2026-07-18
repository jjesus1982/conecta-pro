"""GEDEON — NFS-e Nacional via ADN (Ambiente de Dados Nacional). Roda no container.

Manaus migrou pro NFS-e Nacional (gov.br/SPED). O ADN distribui os DF-e do CNPJ:
  GET https://adn.nfse.gov.br/contribuintes/DFe/{NSU(15)}  (mTLS cert A1) →
    {StatusProcessamento, LoteDFe:[{NSU, ChaveAcesso, TipoDocumento, ArquivoXml(gzip+b64)}]}
Incremental por NSU. Inclui notas EMITIDAS (emit=prestador) e RECEBIDAS (tomador).

Aqui: pagina o ADN, decodifica os XML, filtra as notas EMITIDAS pelo nosso CNPJ.
"""

from __future__ import annotations

import base64
import gzip
import logging
import os
import re
import tempfile

import httpx
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
    pkcs12,
)

logger = logging.getLogger(__name__)

ADN_BASE = "https://adn.nfse.gov.br/contribuintes/DFe"
CNPJ_PRESTADOR = os.getenv("NFSE_MANAUS_CNPJ", "35710481000103")
CERT_PATH = os.getenv("CERTIFICATE_PATH", "/app/credentials/certificates/certificado.pfx")


def _cert_pem(cert_path: str | None = None, senha: str | None = None) -> tuple[str, str]:
    pfx = open(cert_path or CERT_PATH, "rb").read()
    pwd = (senha if senha is not None else os.getenv("CERTIFICATE_PASSWORD", "")).encode()
    key, cert, _ = pkcs12.load_key_and_certificates(pfx, pwd)
    cf = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
    kf = tempfile.NamedTemporaryFile(suffix=".pem", delete=False)
    cf.write(cert.public_bytes(Encoding.PEM))
    cf.flush()
    kf.write(key.private_bytes(Encoding.PEM, PrivateFormat.TraditionalOpenSSL, NoEncryption()))
    kf.flush()
    return cf.name, kf.name


def _resolver_empresa(empresa_slug: str | None) -> tuple[str, str | None, str | None]:
    """(cnpj_prestador, cert_path, cert_senha) — slug None = env/CNPJ1 (legado)."""
    if not empresa_slug:
        return CNPJ_PRESTADOR, None, None
    from modules.fiscal.services.nfse_multi_empresa_service import (
        EMPRESAS_CONFIG,
        refresh_empresas_config,
    )

    refresh_empresas_config()
    cfg = EMPRESAS_CONFIG.get(empresa_slug) or {}
    if not cfg.get("cnpj") or not cfg.get("certificado_path"):
        raise LookupError(f"ADN: empresa '{empresa_slug}' sem CNPJ/certificado configurado")
    return cfg["cnpj"], cfg["certificado_path"], cfg.get("certificado_senha")


def _decode_xml(arquivo_xml: str) -> str:
    try:
        return gzip.decompress(base64.b64decode(arquivo_xml)).decode("utf-8", "ignore")
    except Exception:
        try:
            return base64.b64decode(arquivo_xml).decode("utf-8", "ignore")
        except Exception:
            return arquivo_xml


def _campo(xml: str, tag: str) -> str:
    m = re.search(rf"<{tag}>([^<]+)</{tag}>", xml)
    return m.group(1).strip() if m else ""


def _emit_cnpj(xml: str) -> str:
    m = re.search(r"<emit>.*?<CNPJ>([^<]+)</CNPJ>", xml, re.S)
    return m.group(1).strip() if m else ""


def _tomador_nome(xml: str) -> str:
    m = re.search(r"<toma>.*?<xNome>([^<]+)</xNome>", xml, re.S)
    return m.group(1).strip() if m else ""


def parse_nota(xml: str) -> dict:
    return {
        "chave": (re.search(r'Id="NFS([0-9]+)"', xml) or [None, ""])[1],
        "numero": _campo(xml, "nNFSe"),
        "emit_cnpj": _emit_cnpj(xml),
        "tomador": _tomador_nome(xml),
        "dhProc": _campo(xml, "dhProc"),
        "competencia": _campo(xml, "dCompet") or _campo(xml, "dhProc")[:7],
    }


_TOMADORES_CACHE: list[dict] | None = None


def _tomador_completo(xml: str) -> dict:
    m = re.search(r"<toma>(.*?)</toma>", xml, re.S)
    bloco = m.group(1) if m else ""

    def g(tag):
        mm = re.search(rf"<{tag}>([^<]+)</{tag}>", bloco)
        return mm.group(1).strip() if mm else ""

    return {
        "cnpj": g("CNPJ") or g("CPF"),
        "razao_social": g("xNome"),
        "logradouro": g("xLgr"),
        "numero": g("nro") or "S/N",
        "bairro": g("xBairro"),
        "cep": g("CEP"),
        "codigo_municipio": g("cMun") or "1302603",
    }


def listar_tomadores(forcar: bool = False) -> list[dict]:
    """Lista distinta de tomadores (condomínios) com endereço completo, das notas emitidas.
    Cacheado em memória (a 1ª chamada pagina o ADN ~15s; as seguintes são instantâneas)."""
    global _TOMADORES_CACHE
    if _TOMADORES_CACHE is not None and not forcar:
        return _TOMADORES_CACHE
    r = distribuir(max_paginas=80)
    por_cnpj: dict[str, dict] = {}
    for n in sorted(r["emitidas"], key=lambda x: x.get("dhProc", "")):  # mais recente sobrescreve
        t = _tomador_completo(n.get("_xml", ""))
        if t["cnpj"] and t["razao_social"]:
            por_cnpj[t["cnpj"]] = t
    _TOMADORES_CACHE = sorted(por_cnpj.values(), key=lambda x: x["razao_social"])
    return _TOMADORES_CACHE


def filtrar_vivas(emitidas: list[dict]) -> tuple[list[dict], int]:
    """Regra de validade das NFS-e (fonte única — provada com as notas reais):

    uma nota é VIVA se a chave dela NÃO é referenciada como <chSubstda> por
    nenhum outro documento do feed (o cStat do XML distribuído marca o DOC
    substituidor, não a validade). Dedupe por chave ficando a de maior NSU.
    Retorna (vivas, qtd_mortas).
    """
    mortas: set[str] = set()
    for n in emitidas:
        m = re.search(r"<chSubstda>([^<]+)</chSubstda>", n.get("_xml", ""))
        if m:
            mortas.add(m.group(1).strip())
    vivas: list[dict] = []
    vistos: set[str] = set()
    descartadas = 0
    for n in sorted(emitidas, key=lambda x: int(x.get("nsu") or 0), reverse=True):
        chave = n.get("chave_acesso") or n.get("chave") or ""
        if not chave or chave in mortas:
            descartadas += 1
            continue
        if chave in vistos:
            continue
        vistos.add(chave)
        vivas.append(n)
    return vivas, descartadas


def distribuir(nsu_inicial: int = 0, max_paginas: int = 80, empresa_slug: str | None = None) -> dict:
    """Pagina o ADN e devolve as notas EMITIDAS pelo CNPJ da empresa + o último NSU.

    Multi-CNPJ E5: `empresa_slug` seleciona identidade/certificado da tabela
    `empresas`; None = comportamento legado (env/CNPJ1). O NSU do ADN é POR
    CNPJ no gov — use fiscal_nsu_checkpoint por empresa para incrementalidade.
    """
    import time

    cnpj_prestador, cert_path, cert_senha = _resolver_empresa(empresa_slug)
    cert = _cert_pem(cert_path, cert_senha)
    emitidas: list[dict] = []
    total = 0
    nsu = nsu_inicial
    with httpx.Client(cert=cert, timeout=40) as cli:
        for _ in range(max_paginas):
            # throttle + retry no 429 (ADN limita req/seg)
            r = None
            for tent in range(6):
                r = cli.get(f"{ADN_BASE}/{str(nsu).zfill(15)}")
                if r.status_code != 429:
                    break
                time.sleep(2 * (tent + 1))
            if r is None or r.status_code == 404:
                break
            if r.status_code != 200:
                break
            d = r.json()
            lote = d.get("LoteDFe") or []
            if not lote:
                break
            for doc in lote:
                total += 1
                xml = _decode_xml(doc.get("ArquivoXml", ""))
                if _emit_cnpj(xml) == cnpj_prestador:
                    n = parse_nota(xml)
                    n["nsu"] = doc.get("NSU")
                    n["chave_acesso"] = doc.get("ChaveAcesso")
                    n["_xml"] = xml
                    emitidas.append(n)
            ultimo = int(lote[-1].get("NSU", nsu))
            nsu = ultimo + 1
            if len(lote) < 50:
                break
            time.sleep(1.3)  # gentil com o rate-limit do ADN
    return {"total_processados": total, "ultimo_nsu": nsu - 1, "emitidas": emitidas}
