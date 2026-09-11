"""`request_id` em TODA resposta — item 4 do relatório de campo do Cowork.

Antes disto o `request_id` só aparecia quando o ERP devolvia `x-request-id` num ERRO. Na
prática: quase nunca, e nunca no caminho feliz. Quando algo dava errado, o que sobrava para
investigar era "deu erro às 14h" — e o backend tem centenas de requisições nesse minuto.

O ciclo que este módulo fecha:
  1. gera o id quando a chamada chega;
  2. guarda num ContextVar, de onde `ErpClient.request` o envia ao ERP como `X-Request-ID`
     (sem isso o id seria um número que só existe do lado de cá);
  3. carimba a resposta que volta ao agente.

⭐ CARIMBA AS DUAS REPRESENTAÇÕES. O `ToolResult` do FastMCP carrega o mesmo dado duas
vezes: `structured_content` (dict) e `content` (o JSON em texto). Carimbar só uma faz os
dois leitores discordarem — e "dois escritores, ou dois leitores, para o mesmo fato" é a
família de defeito mais cara desta casa. Se a serialização falhar, o texto fica como estava
e o dict também: melhor os dois sem carimbo do que os dois divergentes.

⚠️ NÃO carimba o que não é objeto JSON. Rota que devolve lista sai como lista; enfiar uma
chave ali mudaria o formato que o agente espera. Nesses casos o id vai no `meta`, que é o
lugar do protocolo para metadado.
"""
from __future__ import annotations

import json
import secrets

try:
    from fastmcp.server.middleware import Middleware as _Base
except Exception:  # noqa: BLE001 — as travas rodam no HOST, sem fastmcp
    _Base = object


def novo_id() -> str:
    return f"req_{secrets.token_hex(8)}"


class CarimboRequestId(_Base):
    """Gera o id da chamada, propaga ao ERP e carimba a resposta."""

    async def on_call_tool(self, context, call_next):  # noqa: ANN001
        from server import _REQ_ID  # noqa: PLC0415 — evita import circular no carregamento

        rid = novo_id()
        marca = _REQ_ID.set(rid)
        try:
            resultado = await call_next(context)
        finally:
            _REQ_ID.reset(marca)

        dado = getattr(resultado, "structured_content", None)
        if isinstance(dado, dict):
            if "request_id" not in dado:
                dado["request_id"] = rid
                self._refazer_texto(resultado, dado)
        else:
            # lista, texto puro, ou nada: o id vai no metadado do protocolo
            meta = getattr(resultado, "meta", None)
            if isinstance(meta, dict):
                meta.setdefault("request_id", rid)
        return resultado

    @staticmethod
    def _refazer_texto(resultado, dado: dict) -> None:
        """Reserializa `content` para bater com o dict. Falhou? desfaz o carimbo.

        Deixar o dict carimbado e o texto sem carimbo seria pior que não carimbar: o agente
        que lê um vê o id, o que lê o outro não, e os dois acham que leram a mesma resposta.
        """
        conteudo = getattr(resultado, "content", None)
        if not conteudo:
            return
        try:
            texto = json.dumps(dado, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            dado.pop("request_id", None)
            return
        for parte in conteudo:
            if getattr(parte, "type", None) == "text":
                try:
                    parte.text = texto
                except Exception:  # noqa: BLE001 — objeto imutável: desfaz e sai
                    dado.pop("request_id", None)
                return


def instalar(mcp) -> bool:
    """Sempre instalado: rastrear não depende de modo nem de identidade."""
    mcp.add_middleware(CarimboRequestId())
    return True
