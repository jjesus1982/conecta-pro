"""
Middleware de AUDITORIA — registra toda escrita (POST/PUT/PATCH/DELETE) da API — e, desde
06/09/2026, cada TELA do redesign aberta (GET /api/v1/redesign/data/<slug>) — em crm_audit_log:
quem (user_id do JWT), quando (ts), o quê (method+path), resultado (status), de onde (ip/user-agent).

Best-effort e fire-and-forget: a gravação roda em background (asyncio.create_task) e NUNCA bloqueia ou
quebra a requisição. Não audita leituras (GET) nem rotas ruidosas (login/health/docs).
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

_WRITE = {"POST", "PUT", "PATCH", "DELETE"}
_SKIP = ("/auth/login", "/auth/refresh", "/auth/logout", "/health", "/docs", "/openapi", "/metrics")
#: Leitura de TELA do redesign também entra (06/09/2026): é a única forma de saber QUEM abriu
#: o quê — o nginx não tem usuário. Só este prefixo: um GET por tela aberta, não por lista.
_READ_TELAS = "/api/v1/redesign/data/"


#: ⭐ BUG-09 (30/09/2026) — O `request_id` NÃO SERVIA PARA NADA, e isso era demonstrável.
#: O conector MCP manda `X-Request-ID` em toda chamada, com um comentário no código dizendo
#: que é "para `consultar_auditoria(request_id=...)` ter o que achar". Deste lado, ninguém
#: lia o cabeçalho, a tabela não tinha a coluna, e a rota `/crm/audit` ACEITAVA o parâmetro
#: e não o usava no WHERE — devolvia a trilha inteira com HTTP 200.
#:
#: Resultado prático: o Jordan recebia «{"codigo":"ERRO_INTERNO","mensagem":"Internal Server
#: Error"}` com um `req_28235eb2338d9573`, e do lado do servidor não havia NADA com esse
#: número. Seis 500 do `criar_proposta` em 30/09 ficaram assim, sem uma linha correlata.
_DDL_REQ_ID = (
    "ALTER TABLE crm_audit_log ADD COLUMN IF NOT EXISTS request_id varchar(64)",
    "ALTER TABLE crm_audit_log ADD COLUMN IF NOT EXISTS erro text",
    "CREATE INDEX IF NOT EXISTS ix_crm_audit_log_request_id ON crm_audit_log (request_id)",
    "COMMENT ON COLUMN crm_audit_log.erro IS "
    "'Classe e mensagem da exceção NÃO TRATADA que virou 500, quando houve. "
    "NULO = a requisição não estourou.'",
)
_ddl_feito = False


async def _garantir_colunas(s) -> None:
    global _ddl_feito  # noqa: PLW0603 — uma vez por processo; o custo é um SELECT a menos
    if _ddl_feito:
        return
    from sqlalchemy import text

    for ddl in _DDL_REQ_ID:
        await s.execute(text(ddl))
    await s.commit()
    _ddl_feito = True


async def _gravar(user_id, method, path, status, ip, ua, request_id=None, erro=None):
    try:
        from sqlalchemy import text

        from core.database import async_session_factory

        async with async_session_factory() as s:
            await _garantir_colunas(s)
            await s.execute(
                text("""
                INSERT INTO crm_audit_log (id, ts, user_id, method, path, status, ip, user_agent,
                                           request_id, erro)
                VALUES (gen_random_uuid(), now(), :u, :m, :p, :st, :ip, :ua, :rid, :err)
            """),
                {
                    "u": user_id,
                    "m": method,
                    "p": path[:500],
                    "st": status,
                    "ip": ip,
                    "ua": (ua or "")[:255],
                    "rid": (request_id or None),
                    "err": (erro or None),
                },
            )
            await s.commit()
    except Exception as exc:  # noqa: BLE001 — auditoria nunca quebra nada
        logger.debug("audit log ignorado: %s", exc)


def _quem(request) -> str | None:
    auth = request.headers.get("authorization", "")
    if not auth.startswith("Bearer "):
        return None
    try:
        from core.auth.jwt import decode_token

        return decode_token(auth[7:]).get("sub")
    except Exception:  # noqa: BLE001
        return None


def _de_onde(request) -> str | None:
    xff = request.headers.get("x-forwarded-for")
    return xff.split(",")[0].strip() if xff else (request.client.host if request.client else None)


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        # O id vem do chamador (o conector manda) ou nasce aqui. Nascer aqui importa: o
        # mesmo número volta no corpo do erro, e é por ele que se acha a linha na trilha.
        rid = request.headers.get("x-request-id") or f"srv_{uuid.uuid4().hex[:16]}"
        erro = None
        try:
            response = await call_next(request)
        except Exception as exc:
            # ClientDisconnect NÃO é defeito nosso: o navegador fechou a aba no meio da
            # resposta. Apareceu 2× no `/whatsapp/webhook` na primeira hora desta trava.
            # Gravar isso como 500 encheria a trilha de ruído e faria o dono caçar um bug
            # que não existe — e responder JSON a quem já foi embora não chega a ninguém.
            if type(exc).__name__ == "ClientDisconnect":
                raise

            # ⭐ 30/09/2026 — ANTES, A EXCEÇÃO PASSAVA POR AQUI SEM DEIXAR RASTRO.
            # `call_next` estava fora do try: o handler padrão do Starlette devolvia
            # «Internal Server Error» em texto puro e a auditoria nem chegava a rodar.
            # Agora a classe e a mensagem ficam gravadas, e o `request_id` viaja nas duas
            # pontas — resposta e trilha. `raise` no fim: o erro continua sendo erro.
            erro = f"{type(exc).__name__}: {exc}"[:2000]
            logger.exception("500 nao tratado [request_id=%s] %s %s", rid, request.method, request.url.path)
            asyncio.create_task(
                _gravar(
                    _quem(request),
                    request.method,
                    request.url.path,
                    500,
                    _de_onde(request),
                    request.headers.get("user-agent", ""),
                    request_id=rid,
                    erro=erro,
                )
            )
            from fastapi.responses import JSONResponse

            return JSONResponse(
                status_code=500,
                headers={"X-Request-ID": rid},
                content={
                    "ok": False,
                    "codigo": "ERRO_INTERNO",
                    "request_id": rid,
                    "excecao": type(exc).__name__,
                    "mensagem": f"{type(exc).__name__} em {request.method} {request.url.path}",
                    "dica": f"A trilha tem a linha: consultar_auditoria(request_id='{rid}') "
                    f"traz caminho, quem chamou e a exceção completa.",
                },
            )
        try:
            method = request.method
            path = request.url.path
            e_tela = method == "GET" and path.startswith(_READ_TELAS)
            if (method in _WRITE or e_tela) and "/api/" in path and not any(s in path for s in _SKIP):
                asyncio.create_task(
                    _gravar(
                        _quem(request),
                        method,
                        path,
                        response.status_code,
                        _de_onde(request),
                        request.headers.get("user-agent", ""),
                        request_id=rid,
                    )
                )
        except Exception as exc:  # noqa: BLE001
            logger.debug("audit middleware ignorado: %s", exc)
        response.headers["X-Request-ID"] = rid
        return response
