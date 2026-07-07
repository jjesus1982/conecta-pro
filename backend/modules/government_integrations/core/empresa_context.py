"""
EmpresaContext — fonte única da verdade da IDENTIFICAÇÃO da empresa para os
serviços fiscais (SPED Fiscal, SPED Contábil, DCTFWeb, EFD-Reinf, etc.).

Antes, cada serviço tinha seu próprio fallback de env var com defaults DIVERGENTES
e ERRADOS ('Empresa', 'Conecta Seguranca LTDA', UF 'SP', município 3550308 = São
Paulo). Isto gerava arquivos fiscais com identificação de outra empresa/estado.

Este módulo lê os dados REAIS da tabela `empresas` (a empresa principal / Lucro Real)
uma única vez, e todos os serviços consomem o mesmo dado. Nunca fabrica: se o banco
não responder, cai para o CNPJ/dados conhecidos da empresa principal (Manaus/AM),
NUNCA para São Paulo.

Empresa principal (Lucro Real): CONECTAMAIS ELETRONICA LTDA,
CNPJ 35.710.481/0001-03, Manaus/AM (IBGE 1302603).
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from functools import lru_cache

import psycopg2

logger = logging.getLogger(__name__)

# UF por prefixo do código IBGE (2 primeiros dígitos). Só o que precisamos aqui;
# 13 = Amazonas. Usado quando a tabela empresas não tem coluna UF explícita.
_UF_POR_IBGE = {
    "13": "AM",
    "35": "SP",
    "33": "RJ",
    "31": "MG",
    "29": "BA",
    "23": "CE",
    "43": "RS",
    "41": "PR",
    "42": "SC",
    "26": "PE",
    "52": "GO",
    "53": "DF",
}

# Fallback HONESTO (dados reais da empresa principal) caso o banco não responda.
# NUNCA usar São Paulo/SP aqui.
_FALLBACK = {
    "cnpj": "35710481000103",
    "razao_social": "CONECTAMAIS ELETRONICA LTDA",
    "inscricao_estadual": "",
    "inscricao_municipal": "45177801",
    "uf": "AM",
    "codigo_municipio": "1302603",
}


@dataclass(frozen=True)
class EmpresaFiscal:
    """Identificação fiscal da empresa (somente leitura)."""

    cnpj: str  # só dígitos, 14 posições
    razao_social: str
    inscricao_estadual: str
    inscricao_municipal: str
    uf: str
    codigo_municipio: str  # IBGE 7 dígitos


def _db_url() -> str:
    return re.sub(r"\+asyncpg|\+psycopg2?", "", os.getenv("DATABASE_URL", ""))


def _so_digitos(v: str | None) -> str:
    return re.sub(r"\D", "", v or "")


@lru_cache(maxsize=1)
def get_empresa_fiscal() -> EmpresaFiscal:
    """
    Retorna a identificação fiscal da empresa PRINCIPAL (Lucro Real) lida da
    tabela `empresas`. Resultado cacheado. Nunca lança: em erro, usa o fallback
    honesto (empresa principal em Manaus/AM).
    """
    dados = dict(_FALLBACK)
    url = _db_url()
    if url:
        try:
            conn = psycopg2.connect(url)
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT razao_social, cnpj, inscricao_estadual,
                               inscricao_municipal, codigo_municipio_ibge
                        FROM empresas
                        WHERE status = 'ativa'
                        ORDER BY (regime_tributario = 'lucro_real') DESC,
                                 is_principal DESC
                        LIMIT 1
                        """
                    )
                    row = cur.fetchone()
            finally:
                conn.close()

            if row:
                razao, cnpj, ie, im, cod_mun = row
                cod_mun = (cod_mun or _FALLBACK["codigo_municipio"]).strip()
                dados = {
                    "cnpj": _so_digitos(cnpj) or _FALLBACK["cnpj"],
                    "razao_social": (razao or _FALLBACK["razao_social"]).strip(),
                    "inscricao_estadual": _so_digitos(ie),
                    "inscricao_municipal": _so_digitos(im),
                    "uf": _UF_POR_IBGE.get(cod_mun[:2], _FALLBACK["uf"]),
                    "codigo_municipio": cod_mun,
                }
        except Exception as e:  # noqa: BLE001
            logger.warning("EmpresaContext: falha ao ler tabela empresas (%s); usando fallback Manaus/AM", e)

    return EmpresaFiscal(
        cnpj=dados["cnpj"],
        razao_social=dados["razao_social"],
        inscricao_estadual=dados["inscricao_estadual"],
        inscricao_municipal=dados["inscricao_municipal"],
        uf=dados["uf"],
        codigo_municipio=dados["codigo_municipio"],
    )
