"""Fonte única de identidade das empresas do Grupo (Multi-CNPJ).

Este módulo é O caminho canônico para resolver "qual empresa" em qualquer
ponto do sistema — substitui gradualmente os hardcodes de CNPJ/UUID
(EMPRESA_PRINCIPAL_ID triplicado, CNPJs literais em services).

Regras (PRD Multi-CNPJ 2026-07-17):
- `razao_social` = grafia EXATA da Receita → usar APENAS em campos legais
  (qualificação contratual, fiscal). Ex.: "CONECTAMAIS PATRIMONIAL LTDA".
- `nome_fantasia` = nome de EXIBIÇÃO no sistema/documentos.
  Ex.: "Conecta Mais Patrimonial".
- Roteamento serviço→empresa é regra de negócio (tabela canônica), NUNCA
  inferência por CNAE (os CNAEs das duas empresas se sobrepõem).
"""

import logging
import time
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

SLUG_ELETRONICA = "conecta_eletronica"
SLUG_PATRIMONIAL = "conecta_patrimonial"

_COLS = (
    "id, slug, razao_social, nome_fantasia, cnpj, inscricao_municipal, "
    "inscricao_estadual, inscricao_suframa, codigo_municipio_ibge, "
    "regime_tributario, anexo_simples, regime_futuro, "
    "certificado_a1_path, certificado_a1_senha, certificado_validade, "
    "nfse_ambiente, nfse_serie_rps, status, is_principal"
)

# Cache leve por processo: identidade de empresa muda raríssimo; TTL curto
# evita query repetida em loops de emissão/kit sem risco de dado velho.
_CACHE_TTL_S = 60.0
_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row._mapping)
    d["id"] = UUID(str(d["id"]))
    return d


def _cache_get(key: str) -> dict[str, Any] | None:
    hit = _cache.get(key)
    if hit and (time.monotonic() - hit[0]) < _CACHE_TTL_S:
        return hit[1]
    return None


def _cache_put(row: dict[str, Any]) -> None:
    now = time.monotonic()
    for key in (f"slug:{row['slug']}", f"id:{row['id']}"):
        _cache[key] = (now, row)
    if row.get("cnpj"):
        _cache[f"cnpj:{_digits(row['cnpj'])}"] = (now, row)


def _digits(value: str) -> str:
    return "".join(ch for ch in value if ch.isdigit())


async def get_empresa(
    db: AsyncSession,
    *,
    slug: str | None = None,
    cnpj: str | None = None,
    empresa_id: UUID | str | None = None,
) -> dict[str, Any]:
    """Resolve UMA empresa ativa por slug, CNPJ (com ou sem máscara) ou id.

    Levanta LookupError se não encontrar — nunca devolve fallback silencioso
    (princípio: espelhar, não assumir).
    """
    if slug:
        key, where, param = f"slug:{slug}", "slug = :v", slug
    elif cnpj:
        key = f"cnpj:{_digits(cnpj)}"
        where, param = "regexp_replace(cnpj, '\\D', '', 'g') = :v", _digits(cnpj)
    elif empresa_id:
        key, where, param = f"id:{empresa_id}", "id = :v", str(empresa_id)
    else:
        raise ValueError("get_empresa: informe slug, cnpj ou empresa_id")

    cached = _cache_get(key)
    if cached:
        return cached

    result = await db.execute(
        text(f"SELECT {_COLS} FROM empresas WHERE {where} AND status = 'ativa'"),
        {"v": param},
    )
    row = result.fetchone()
    if not row:
        raise LookupError(f"Empresa ativa não encontrada ({key})")
    data = _row_to_dict(row)
    _cache_put(data)
    return data


async def get_empresas_ativas(db: AsyncSession) -> list[dict[str, Any]]:
    """Todas as empresas ativas do Grupo — para loops por-empresa (beats, CNDs, NFS-e)."""
    result = await db.execute(
        text(f"SELECT {_COLS} FROM empresas WHERE status = 'ativa' ORDER BY is_principal DESC")
    )
    rows = [_row_to_dict(r) for r in result.fetchall()]
    for r in rows:
        _cache_put(r)
    return rows


async def get_empresa_principal(db: AsyncSession) -> dict[str, Any]:
    """Empresa principal (CNPJ1). Preferir get_empresa(slug=...) explícito em código novo."""
    result = await db.execute(
        text(f"SELECT {_COLS} FROM empresas WHERE is_principal AND status = 'ativa' LIMIT 1")
    )
    row = result.fetchone()
    if not row:
        raise LookupError("Nenhuma empresa principal ativa cadastrada")
    data = _row_to_dict(row)
    _cache_put(data)
    return data


def invalidate_cache() -> None:
    """Chamar após UPDATE em empresas (admin) para refletir imediatamente."""
    _cache.clear()
