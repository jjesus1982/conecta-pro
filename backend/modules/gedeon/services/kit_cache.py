"""GEDEON — Cache compartilhado dos dois hotspots de leitura do Drive.

Vários endpoints (ficha, conferir/ATLAS, assinaturas, DP, visão funcionário, entrega)
precisam das MESMAS leituras caras do Google Drive:
  - `_ler_kit`        → lista todas as subpastas/arquivos do kit (várias chamadas à API);
  - `_nomes_da_folha` → baixa e parseia o PDF da Folha de Pagamento.

Sem cache, cada endpoint refazia essas leituras (lentas, ainda mais sob steal de CPU),
podendo saturar o threadpool do FastAPI e até derrubar o worker. Aqui centralizamos com
um TTL curto e invalidação explícita nas mutações (upload/delete/montagem).
"""

from __future__ import annotations

import threading
import time

# 5 min: mutações via API invalidam explicitamente (invalidar()); leitura fria do
# Drive é cara (~1-3s por kit) e o TTL curto fazia as telas re-lerem o Drive toda hora.
_TTL = 300  # segundos
_lock = threading.Lock()
_kit: dict = {}    # (cond, comp) -> (ts, kit_dict)
_folha: dict = {}  # (cond, comp) -> (ts, [nomes])


def _get(store: dict, key, ttl: float):
    hit = store.get(key)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]
    return None


def ler_kit(svc, cond: str, competencia: str, ttl: float = _TTL) -> dict:
    """`_ler_kit` cacheado por (condomínio, competência)."""
    from modules.gedeon.services.kit_completude_service import _ler_kit

    key = (cond, competencia)
    cached = _get(_kit, key, ttl)
    if cached is not None:
        return cached
    val = _ler_kit(svc, cond, competencia)
    with _lock:
        _kit[key] = (time.time(), val)
    return val


def nomes_folha(svc, cond: str, competencia: str, ttl: float = _TTL) -> list[str]:
    """`_nomes_da_folha` cacheado por (condomínio, competência)."""
    from modules.gedeon.services.kit_ficha_service import _nomes_da_folha

    key = (cond, competencia)
    cached = _get(_folha, key, ttl)
    if cached is not None:
        return cached
    val = _nomes_da_folha(svc, cond, competencia) if svc else []
    with _lock:
        _folha[key] = (time.time(), val)
    return val


def invalidar(cond: str | None = None, competencia: str | None = None) -> None:
    """Limpa o cache após uma mutação. Sem args = limpa tudo; com (cond,comp) = só aquele kit."""
    with _lock:
        if cond is None and competencia is None:
            _kit.clear()
            _folha.clear()
            return
        for store in (_kit, _folha):
            for k in [k for k in store if (cond is None or k[0] == cond) and (competencia is None or k[1] == competencia)]:
                store.pop(k, None)
