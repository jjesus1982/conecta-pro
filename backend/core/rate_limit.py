"""
Rate Limiting - Proteção contra abuso da API.

Implementa rate limiting usando slowapi + Redis para limitar
requisições por IP, usuário ou endpoint.
"""

from collections.abc import Callable

from fastapi import Request, Response
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from core.config import settings
from core.logging import logger


def get_user_identifier(request: Request) -> str:
    """
    Identifica o usuário para rate limiting.

    Prioridade:
    1. user_id do token JWT (se autenticado)
    2. IP address (fallback)

    Args:
        request: Request do FastAPI

    Returns:
        String identificadora única para o usuário
    """
    # Tentar obter user_id do state (definido pelo middleware de auth)
    user_id = getattr(request.state, "user_id", None)
    if user_id:
        return f"user:{user_id}"

    # Fallback para IP — atrás do nginx, request.client.host é o gateway Docker (todos
    # compartilhariam o mesmo balde). Preferir o 1º hop do X-Forwarded-For (IP real).
    return f"ip:{_real_ip(request)}"


def _real_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return get_remote_address(request)


def get_api_key_identifier(request: Request) -> str:
    """
    Identifica requisições por API key.

    Args:
        request: Request do FastAPI

    Returns:
        String identificadora para API key ou IP
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        # Hash da API key para não expor no Redis
        import hashlib

        hashed = hashlib.sha256(api_key.encode()).hexdigest()[:16]
        return f"apikey:{hashed}"

    return get_user_identifier(request)


# Configurar storage do Redis se disponível
storage_uri = None
if settings.redis_url:
    storage_uri = settings.redis_url
    logger.info(
        "Rate limiting configurado com Redis",
        action="init_rate_limiter",
        storage="redis",
        redis_url=settings.redis_url,
    )
else:
    logger.warning(
        "Rate limiting usando memória (não recomendado para produção)",
        action="init_rate_limiter",
        storage="memory",
    )


# Criar instância do limiter
limiter = Limiter(
    key_func=get_user_identifier,
    storage_uri=storage_uri,
    default_limits=["1000/hour"],  # Limite padrão global
    swallow_errors=False,  # Levantar erro se Redis falhar
    headers_enabled=True,  # Adicionar headers X-RateLimit-*
)


# Criar limiter alternativo por API key
api_key_limiter = Limiter(
    key_func=get_api_key_identifier,
    storage_uri=storage_uri,
    default_limits=["5000/hour"],  # API keys têm limite maior
    headers_enabled=True,
)


def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """
    Handler customizado para erros de rate limit.

    Args:
        request: Request que excedeu o limite
        exc: Exception de rate limit

    Returns:
        Response 429 com detalhes
    """
    logger.warning(
        "Rate limit excedido",
        action="rate_limit_exceeded",
        path=request.url.path,
        identifier=get_user_identifier(request),
        limit=str(exc.detail),
    )

    return Response(
        content={
            "error": "rate_limit_exceeded",
            "message": "Limite de requisições excedido. Tente novamente mais tarde.",
            "detail": str(exc.detail),
            "retry_after": request.headers.get("Retry-After", "unknown"),
        },
        status_code=HTTP_429_TOO_MANY_REQUESTS,
        headers={
            "Retry-After": request.headers.get("Retry-After", "60"),
            "X-RateLimit-Limit": request.headers.get("X-RateLimit-Limit", "unknown"),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": request.headers.get("X-RateLimit-Reset", "unknown"),
        },
    )


# Limites pré-configurados por tipo de endpoint

# Endpoints públicos (sem autenticação)
PUBLIC_LIMIT = "10/minute"

# Endpoints de autenticação (login, registro)
AUTH_LIMIT = getattr(settings, "auth_rate_limit", "20/minute")

# Endpoints de leitura (GET)
READ_LIMIT = "100/minute"

# Endpoints de escrita (POST, PUT, PATCH, DELETE)
WRITE_LIMIT = "30/minute"

# Endpoints críticos (operações sensíveis)
CRITICAL_LIMIT = "10/minute"

# Endpoints de bulk operations
BULK_LIMIT = "5/minute"

# Endpoints de export/report
EXPORT_LIMIT = "3/minute"


def get_rate_limit_dependency(limit: str) -> Callable:
    """
    Cria uma dependency do FastAPI para rate limiting.

    Args:
        limit: String de limite (ex: "10/minute", "100/hour")

    Returns:
        Função dependency para usar com Depends()

    Example:
        ```python
        @router.get("/", dependencies=[Depends(get_rate_limit_dependency("10/minute"))])
        async def endpoint():
            pass
        ```
    """

    async def rate_limit_dependency(request: Request):
        # A verificação real é feita pelo decorator @limiter.limit()
        # Esta função serve apenas como marcador para documentação
        pass

    rate_limit_dependency.__name__ = f"rate_limit_{limit.replace('/', '_per_')}"
    return rate_limit_dependency
