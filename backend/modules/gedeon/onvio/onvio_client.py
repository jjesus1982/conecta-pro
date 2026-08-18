"""
GEDEON Fase 3 — Onvio HTTP Client (versão consolidada pós-auditoria T7)
Autenticação: cookies + Authorization: UDSLongToken <long_token>
API correta: onvio.com.br/api/storage/v1/* (clientcenter)
"""

import json
import os

import redis
import requests

ONVIO_BASE = "https://onvio.com.br"
CLIENT_ID = "92A4D531C6314E309B62FDF3D9F1359C"  # Eletrônica — padrão histórico
# O clientId de cada empresa vive em `empresas.onvio_client_id` (migration c5d6e7f8a9b0).
# Aqui ele fica como PADRÃO só para não quebrar quem instancia sem argumento.
REDIS_KEY = "onvio:session"
REDIS_DB = 1  # T1 confirmou: sessão salva em DB 1


class OnvioClient:
    def __init__(self, client_id: str | None = None):
        """`client_id` é a EMPRESA no Onvio. A conta jjesus@conectamais.pro enxerga as
        duas (Eletrônica code 25, Patrimonial code 102) e a listagem devolve só a que for
        pedida — por isso ele é argumento, não constante."""
        self.client_id = client_id or CLIENT_ID
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/1")
        self._redis = redis.from_url(redis_url)
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) Chrome/120.0.0.0",
            }
        )
        self._session_loaded = False

    def _load_session(self) -> None:
        """Lê sessão do Redis. Idempotente — pode chamar múltiplas vezes."""
        if self._session_loaded:
            return
        raw = self._redis.get(REDIS_KEY)
        if not raw:
            raise RuntimeError("Sessão Onvio não encontrada no Redis. Execute: python3 /opt/conecta-pro/onvio_auth.py")
        d = json.loads(raw)

        # Cookies (httpOnly + JS-visible do login OIDC)
        for name, value in d.get("cookies", {}).items():
            self._session.cookies.set(name, value, domain="onvio.com.br")

        # LongToken header (T1 descobriu via Angular bundle)
        long_token = d.get("long_token")
        if not long_token:
            raise RuntimeError("long_token ausente no Redis. Re-execute onvio_auth.py para regenerar.")
        self._session.headers["Authorization"] = f"UDSLongToken {long_token}"
        self._session_loaded = True

    def _get(self, path: str, params: dict | None = None) -> dict:
        self._load_session()
        resp = self._session.get(f"{ONVIO_BASE}{path}", params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def validar_sessao(self) -> bool:
        """
        Valida fazendo request REAL contra o Onvio.
        Retorna False se HTTP != 200 (não apenas se a sessão existe no Redis).
        """
        try:
            self._load_session()
            resp = self._session.get(f"{ONVIO_BASE}/api/security/v1/session-and-bindings", timeout=10)
            return resp.status_code == 200
        except Exception:
            return False

    def listar_documentos(self, page: int = 1, page_size: int = 100) -> dict:
        """Lista documentos do cliente (paginado, API clientcenter)."""
        return self._get(
            "/api/storage/v1/containers/documents",
            {
                "from": page,
                "pageSize": page_size,
                "loadPermission": "true",
                "readByClientUser": "",
                "customFields": json.dumps([{"name": "clientId", "value": self.client_id, "ignoreCase": True}]),
            },
        )

    def listar_todos_documentos(self) -> list:
        """Pagina automaticamente até buscar todos os documentos."""
        todos = []
        page = 1
        while True:
            data = self.listar_documentos(page=page, page_size=100)
            items = data.get("data", {}).get("items", [])
            todos.extend(items)
            has_more = data.get("data", {}).get("hasMore", False)
            if not has_more or not items:
                break
            page += 1
            if page > 50:  # safety cap — 5000 docs máx
                break
        return todos

    def baixar_pdf(self, container_id: str, doc_id: str) -> bytes:
        """
        Baixa PDF pelo containerId + docId.
        Usa containerId (T7 confirmou que é o campo correto).
        NOTA: envia Accept: */* para que o servidor retorne o binário PDF.
              Se Accept: application/json for enviado, o servidor retorna metadata JSON.
        """
        self._load_session()
        resp = self._session.get(
            f"{ONVIO_BASE}/api/storage/v1/Folders/{container_id}/documents/{doc_id}",
            headers={"Accept": "*/*"},
            timeout=60,
        )
        resp.raise_for_status()
        if not resp.content.startswith(b"%PDF"):
            raise ValueError(f"Download de {doc_id} não retornou PDF válido")
        return resp.content

    def get_tree(self) -> dict:
        """Retorna a árvore de pastas do cliente."""
        return self._get(
            "/api/storage/v1/containers/tree",
            {
                "clientId": self.client_id,
                "includeOrphans": "true",
                "countDocuments": "true",
            },
        )
