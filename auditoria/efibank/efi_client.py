"""
Adapter Efí — PIX cash-out (envio) via API.

Mesma família do seu adapter Inter: certificado (.p12/.pem) + OAuth2
client_credentials -> Bearer token, com mTLS no transporte.

Endpoints usados (confirmados na doc dev.efipay.com.br/docs/api-pix):
    PUT  /v3/gn/pix/{id_envio}                    -> envia PIX por chave
    GET  /v2/gn/pix/enviados/id-envio/{id_envio}  -> status por idEnvio
    GET  /v2/gn/pix/enviados/{e2e_id}             -> status por e2eId

ATENÇÃO — itens a validar no sandbox antes de produção (ver DESIGN.md):
  * Shape EXATO do corpo de envio e do retorno (nomes de campos).
  * Se existe endpoint de CONSULTA DE CHAVE (DICT). Não achei na doc de envio.
  * Limite/charset de id_envio (assumido [A-Za-z0-9], <=35).
  * Assinatura/mTLS do webhook.
Nada aqui inventa payload: os campos abaixo seguem a doc pública e estão
isolados em métodos pequenos pra você ajustar num ponto só.
"""
from __future__ import annotations

import base64
import time
import threading
from dataclasses import dataclass
from typing import Any, Optional

import httpx


class EfiError(Exception):
    """Erro de transporte/negócio da Efí. `retryavel` orienta o orquestrador."""
    def __init__(self, msg: str, *, status: Optional[int] = None, retryavel: bool = False, corpo: Any = None):
        super().__init__(msg)
        self.status = status
        self.retryavel = retryavel
        self.corpo = corpo


@dataclass(frozen=True)
class EfiConfig:
    base_url: str                 # prod: https://pix.api.efipay.com.br | homolog: https://pix-h.api.efipay.com.br
    client_id: str
    client_secret: str
    cert_path: str                # caminho do certificado (.pem). NUNCA no repo.
    cert_key_path: Optional[str] = None   # se o .pem tiver chave separada
    timeout_s: float = 20.0


class EfiClient:
    """
    Thread-safe. Cacheia o token OAuth até ~60s antes de expirar.
    Uma instância por conta pagadora (por CNPJ).
    """

    def __init__(self, cfg: EfiConfig):
        self._cfg = cfg
        self._token: Optional[str] = None
        self._token_exp: float = 0.0
        self._lock = threading.Lock()
        # mTLS: o certificado vai no transporte de TODAS as chamadas.
        cert = cfg.cert_path if not cfg.cert_key_path else (cfg.cert_path, cfg.cert_key_path)
        self._http = httpx.Client(base_url=cfg.base_url, cert=cert, timeout=cfg.timeout_s)

    # ---- auth ---------------------------------------------------------------
    def _get_token(self) -> str:
        with self._lock:
            if self._token and time.monotonic() < self._token_exp:
                return self._token
            basic = base64.b64encode(
                f"{self._cfg.client_id}:{self._cfg.client_secret}".encode()
            ).decode()
            try:
                r = self._http.post(
                    "/oauth/token",
                    headers={"Authorization": f"Basic {basic}", "Content-Type": "application/json"},
                    json={"grant_type": "client_credentials"},
                )
            except httpx.TransportError as e:
                raise EfiError(f"Falha de transporte no token: {e}", retryavel=True) from e
            if r.status_code != 200:
                raise EfiError(f"OAuth falhou: {r.status_code}", status=r.status_code, corpo=r.text)
            data = r.json()
            self._token = data["access_token"]
            self._token_exp = time.monotonic() + int(data.get("expires_in", 3600)) - 60
            return self._token

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._get_token()}", "Content-Type": "application/json"}

    # ---- envio --------------------------------------------------------------
    def enviar_pix_por_chave(
        self,
        *,
        id_envio: str,
        valor_centavos: int,
        chave_origem: str,
        chave_destino: str,
        info_pagador: str,
    ) -> dict[str, Any]:
        """
        PUT /v3/gn/pix/{id_envio}. id_envio é a idempotency key: reenviar o
        MESMO id_envio não gera pagamento novo (trava de dupla-folha).

        Retorno esperado (validar no sandbox): {idEnvio, e2eId, valor, status}.
        status inicial costuma ser EM_PROCESSAMENTO; o desfecho vem por webhook.
        """
        body = {
            "valor": _centavos_para_str(valor_centavos),   # Efí usa string "150.00"
            "pagador": {"chave": chave_origem, "infoPagador": info_pagador[:140]},
            "favorecido": {"chave": chave_destino},
        }
        try:
            r = self._http.put(f"/v3/gn/pix/{id_envio}", headers=self._headers(), json=body)
        except httpx.TransportError as e:
            # Não sabemos se a Efí recebeu. ERRO_ENVIO -> retry com MESMO id_envio.
            raise EfiError(f"Transporte no envio {id_envio}: {e}", retryavel=True) from e

        if r.status_code in (200, 201, 202):
            return r.json()
        if r.status_code == 429 or r.status_code >= 500:
            raise EfiError(f"Efí {r.status_code} no envio {id_envio}", status=r.status_code,
                           retryavel=True, corpo=r.text)
        # 4xx (exceto 429): erro de negócio, NÃO retry cego (ex.: chave inválida, saldo).
        raise EfiError(f"Efí rejeitou envio {id_envio}: {r.status_code}", status=r.status_code,
                       retryavel=False, corpo=r.text)

    # ---- consulta / reconciliação ------------------------------------------
    def consultar_por_id_envio(self, id_envio: str) -> dict[str, Any]:
        r = self._http.get(f"/v2/gn/pix/enviados/id-envio/{id_envio}", headers=self._headers())
        if r.status_code == 200:
            return r.json()
        if r.status_code == 404:
            raise EfiError("id_envio não encontrado", status=404, retryavel=False)
        raise EfiError(f"Consulta {id_envio}: {r.status_code}", status=r.status_code,
                       retryavel=r.status_code >= 500, corpo=r.text)

    def close(self) -> None:
        self._http.close()


def _centavos_para_str(centavos: int) -> str:
    if centavos <= 0:
        raise ValueError("valor deve ser > 0")
    return f"{centavos // 100}.{centavos % 100:02d}"
