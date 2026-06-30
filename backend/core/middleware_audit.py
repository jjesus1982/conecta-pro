"""
Middleware de AUDITORIA — registra toda escrita (POST/PUT/PATCH/DELETE) da API em crm_audit_log:
quem (user_id do JWT), quando (ts), o quê (method+path), resultado (status), de onde (ip/user-agent).

Best-effort e fire-and-forget: a gravação roda em background (asyncio.create_task) e NUNCA bloqueia ou
quebra a requisição. Não audita leituras (GET) nem rotas ruidosas (login/health/docs).
"""

from __future__ import annotations

import asyncio
import logging

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_WRITE = {"POST", "PUT", "PATCH", "DELETE"}
_SKIP = ("/auth/login", "/auth/refresh", "/auth/logout", "/health", "/docs", "/openapi", "/metrics")


async def _gravar(user_id, method, path, status, ip, ua):
    try:
        from sqlalchemy import text

        from core.database import async_session_factory

        async with async_session_factory() as s:
            await s.execute(
                text("""
                INSERT INTO crm_audit_log (id, ts, user_id, method, path, status, ip, user_agent)
                VALUES (gen_random_uuid(), now(), :u, :m, :p, :st, :ip, :ua)
            """),
                {"u": user_id, "m": method, "p": path[:500], "st": status, "ip": ip, "ua": (ua or "")[:255]},
            )
            await s.commit()
    except Exception as exc:  # noqa: BLE001 — auditoria nunca quebra nada
        logger.debug("audit log ignorado: %s", exc)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        try:
            method = request.method
            path = request.url.path
            if method in _WRITE and "/api/" in path and not any(s in path for s in _SKIP):
                user_id = None
                auth = request.headers.get("authorization", "")
                if auth.startswith("Bearer "):
                    try:
                        from core.auth.jwt import decode_token

                        user_id = decode_token(auth[7:]).get("sub")
                    except Exception:  # noqa: BLE001
                        pass
                xff = request.headers.get("x-forwarded-for")
                ip = xff.split(",")[0].strip() if xff else (request.client.host if request.client else None)
                ua = request.headers.get("user-agent", "")
                asyncio.create_task(_gravar(user_id, method, path, response.status_code, ip, ua))
        except Exception as exc:  # noqa: BLE001
            logger.debug("audit middleware ignorado: %s", exc)
        return response
