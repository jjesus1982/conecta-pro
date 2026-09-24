"""Parâmetros do sistema por CNPJ — leitor único de `system_configs` (DGX F4, 24/09/2026).

Por que existe: o DGX guarda um valor por (parâmetro, empresa). Aqui `system_configs` era
global e cada serviço lia com SQL próprio (vigilante, reconferência facial, GED, oráculos).
Este módulo é o leitor de todos: valor da EMPRESA (`valor_por_empresa` jsonb, {cnpj: valor})
→ valor GLOBAL (`valor`) → `default` do chamador.

Por que jsonb na mesma linha, e não uma linha por CNPJ: `chave` é UNIQUE e oito escritores
fazem `ON CONFLICT (chave)` (oráculos, GED, CRM, financeiro, sino). Trocar a unicidade por
(chave, cnpj) quebraria todos eles no primeiro upsert.

Tipagem por `tipo` (enum setting_type); 'string' cai para o `valor_type` legado (linhas
antigas têm `tipo='string'` e `valor_type='int'`). Default `Decimal` → devolve Decimal.

Cache de 30 s por processo; `invalidar()` ao gravar. Coluna ainda ausente (antes do 1º acesso
à tela, que roda o DDL) ou banco fora → devolve o default SEM envenenar a transação do
chamador: a consulta roda num SAVEPOINT. É o que permite trocar constante por parâmetro no
caminho da folha sem mudar o comportamento de hoje.
"""

from __future__ import annotations

import json
import time
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import text

TTL_S = 30
_cache: dict[tuple[str, str], tuple[float, str | None, str | None]] = {}

_SQL = text(
    "SELECT coalesce(nullif(trim(valor_por_empresa->>:e), ''), nullif(trim(valor), '')), "
    "       coalesce(nullif(tipo::text, 'string'), valor_type, 'string') "
    "  FROM system_configs WHERE chave = :c AND ativo"
)


def so_digitos(cnpj: Any) -> str:
    return "".join(ch for ch in str(cnpj or "") if ch.isdigit())


def tipar(valor: str | None, tipo: str | None, default: Any = None) -> Any:
    """Converte o texto do banco para o tipo declarado; texto inválido devolve o default."""
    if valor is None:
        return default
    t = (tipo or "string").lower()
    try:
        if t in ("integer", "int"):
            return int(Decimal(valor))
        if t in ("float", "decimal", "numeric"):
            return Decimal(valor) if isinstance(default, Decimal) else float(valor)
        if t in ("boolean", "bool"):
            return valor.strip().lower() in ("true", "1", "sim", "yes", "on")
        if t in ("json", "list"):
            return json.loads(valor)
    except (ValueError, InvalidOperation, json.JSONDecodeError):
        return default
    return valor


def invalidar() -> None:
    _cache.clear()


def _lembrar(chave: str, e: str, row) -> tuple[str | None, str | None]:
    bruto, tipo = (row[0], row[1]) if row else (None, None)
    _cache[(chave, e)] = (time.monotonic() + TTL_S, bruto, tipo)
    return bruto, tipo


def _do_cache(chave: str, e: str) -> tuple[str | None, str | None] | None:
    hit = _cache.get((chave, e))
    if hit and hit[0] > time.monotonic():
        return hit[1], hit[2]
    return None


async def param(db, chave: str, empresa_cnpj: Any = None, default: Any = None) -> Any:
    """Valor da empresa → global → default. `db` é AsyncSession."""
    e = so_digitos(empresa_cnpj)
    hit = _do_cache(chave, e)
    if hit is None:
        try:
            async with db.begin_nested():
                row = (await db.execute(_SQL, {"c": chave, "e": e})).first()
        except Exception:  # noqa: BLE001 — coluna ausente/banco fora: vale o default
            return default
        hit = _lembrar(chave, e, row)
    return tipar(hit[0], hit[1], default)


def param_sync(db, chave: str, empresa_cnpj: Any = None, default: Any = None) -> Any:
    """Mesma régua para `Session` síncrona (folha, painéis por token, celery)."""
    e = so_digitos(empresa_cnpj)
    hit = _do_cache(chave, e)
    if hit is None:
        try:
            with db.begin_nested():
                row = db.execute(_SQL, {"c": chave, "e": e}).first()
        except Exception:  # noqa: BLE001
            return default
        hit = _lembrar(chave, e, row)
    return tipar(hit[0], hit[1], default)


def demo() -> None:
    assert tipar("40", "float", Decimal("0")) == Decimal("40")
    assert tipar("15", "integer") == 15 and tipar("abc", "integer", 7) == 7
    assert tipar("Sim", "boolean") is True and tipar("false", "boolean") is False
    assert tipar('["a"]', "json") == ["a"] and tipar(None, "json", default=[]) == []
    assert tipar("x", "string") == "x" and so_digitos("35.710.481/0001-03") == "35710481000103"
    print("ok parametros.demo")


if __name__ == "__main__":
    demo()
