"""Fase 2.B — interface do backend ao sidecar de embedding LOCAL (soberano).

`embed_local(textos)` chama o container `conecta-pro-embedding` (ONNX, multilíngue,
384d), sem OpenAI. Retorna list[list[float]] ou [] se o sidecar não responder
(o chamador decide o fallback). Dimensão real exposta em `dim_local()`.
"""
import json
import os
import urllib.error
import urllib.request

EMBED_URL = os.getenv("EMBED_LOCAL_URL", "http://conecta-pro-embedding:8900")
_DIM = None


def dim_local() -> int | None:
    global _DIM
    if _DIM is None:
        try:
            with urllib.request.urlopen(f"{EMBED_URL}/health", timeout=30) as r:
                _DIM = int(json.load(r).get("dim") or 0) or None
        except Exception:  # noqa: BLE001
            return None
    return _DIM


def embed_local(textos: list[str]) -> list[list[float]]:
    if not textos:
        return []
    try:
        data = json.dumps({"texts": [t[:8000] for t in textos]}).encode()
        req = urllib.request.Request(
            f"{EMBED_URL}/embed", data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=60) as r:
            out = json.load(r)
        global _DIM
        _DIM = int(out.get("dim") or 0) or _DIM
        return out.get("vectors") or []
    except (urllib.error.URLError, TimeoutError, ValueError):
        return []
