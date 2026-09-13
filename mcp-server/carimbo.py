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

import json as _json
import secrets

try:
    from fastmcp.server.middleware import Middleware as _Base
except Exception:  # noqa: BLE001 — as travas rodam no HOST, sem fastmcp
    _Base = object


def novo_id() -> str:
    return f"req_{secrets.token_hex(8)}"


def _origem_do_conector() -> str:
    """Como este conector se chama na trilha. Lê o ambiente, não adivinha."""
    import os

    nome = (os.getenv("MCP_AGENTE_NOME") or "").strip()
    escopo = (os.getenv("MCP_ESCOPO") or "").strip()
    if nome and escopo:
        return f"MCP {nome}/{escopo}"
    if nome:
        return f"MCP {nome}"
    # conector público: sem nome nem escopo declarados, serve o catálogo inteiro
    return "MCP publico sem escopo declarado"  # sem parênteses: o `quem` já abre um par


class CarimboRequestId(_Base):
    """Gera o id da chamada, propaga ao ERP e carimba a resposta."""

    async def on_call_tool(self, context, call_next):  # noqa: ANN001
        from server import _REQ_ID  # noqa: PLC0415 — evita import circular no carregamento

        rid = novo_id()
        marca = _REQ_ID.set(rid)

        # ⭐ LOG DE ACESSO A DADO SENSÍVEL — item 3 do Bloco 7. Quem, quando, qual tool e
        # qual `request_id`, consultável depois. Aqui e não em cada tool: são 15 sensíveis
        # hoje e as próximas nasceriam sem log, que é como uma trilha de auditoria fica
        # incompleta justamente no acesso que interessa.
        #
        # ⚠️ Registra a INTENÇÃO (antes de executar), não o sucesso. Tentativa recusada
        # também é acesso tentado, e é o que se procura quando algo dá errado.
        nome_tool = getattr(getattr(context, "message", None), "name", "") or ""
        try:
            import lgpd_escopo as _L  # noqa: PLC0415

            if _L.nivel(nome_tool) == _L.SENSIVEL:
                import server as _srv  # noqa: PLC0415

                await _srv.erp.post("/agente/log-acesso-sensivel", json={
                    "tool": nome_tool, "request_id": rid,
                    "argumentos": str(getattr(getattr(context, "message", None),
                                              "arguments", None) or {})[:400],
                    "autorizado_por_concessao": _L.concessao_vale_para(nome_tool),
                    # ⭐ quem PEDIU, não só sob qual credencial correu. O conector público
                    # usa a identidade do Jordan; sem isto a trilha de LGPD credita a ele
                    # um acesso que foi do assistente.
                    "origem": _origem_do_conector(),
                })
        except Exception:  # noqa: BLE001
            # log que derruba a chamada seria pior que log ausente: o dono perde a
            # capacidade por causa da trilha. Falha aqui é silenciosa de propósito.
            pass
        try:
            resultado = await call_next(context)
        except Exception as exc:  # noqa: BLE001
            # ⭐ REDE POR BAIXO DE TUDO. Auditoria do Cowork (11/09/2026):
            # `obter_contrato("ID-INVALIDO")` devolvia o texto cru
            # "Error calling tool 'obter_contrato': Internal Server Error" — sem envelope,
            # sem código, e a ÚNICA resposta do lote inteiro sem `request_id`. Sem o id não
            # dá para cruzar com o log do servidor, e erro sem rastro é o erro que ninguém
            # conserta. Uma tool que esqueça o try/except passa a cair aqui.
            #
            # ⭐ `__cause__` separa as duas coisas que chegam aqui como ToolError:
            #   · recusa DELIBERADA (gate, identidade) -> `raise ToolError(texto)`, sem
            #     causa. Passa intacta: convertê-la em 500 apagaria a explicação que a
            #     parede escreveu para o dono;
            #   · erro INTERNO que o FastMCP embrulhou -> `ToolError(...) from ErpErro`,
            #     com causa. É este que chegava ao agente como "Error calling tool
            #     'obter_contrato': Internal Server Error", sem código e sem request_id.
            # Distinguir pelo TEXTO ("começa com ⛔") seria frágil: a primeira recusa
            # escrita sem o emoji viraria 500 silenciosamente.
            from fastmcp.exceptions import ToolError  # noqa: PLC0415

            from server import erro_envelope  # noqa: PLC0415

            if isinstance(exc, ToolError) and exc.__cause__ is None:
                raise
            real = exc.__cause__ if isinstance(exc, ToolError) and exc.__cause__ else exc
            envelope = {**erro_envelope(real), "request_id": rid}
            raise ToolError(_json.dumps(envelope, ensure_ascii=False)) from exc
        finally:
            _REQ_ID.reset(marca)

        dado = getattr(resultado, "structured_content", None)
        if isinstance(dado, dict):
            # ISO ao lado do BR (P2). Aqui e não em cada tool: são 271 e as próximas
            # nasceriam sem. O helper só casa data SOZINHA num campo — intervalo e data no
            # meio de texto ficam intocados, então `texto_extraido` não é tocado.
            try:
                from server import _iso_irmaos  # noqa: PLC0415

                enriquecido = _iso_irmaos(dado)
            except Exception:  # noqa: BLE001 — enriquecer não pode derrubar a resposta
                enriquecido = dado
            mudou = enriquecido is not dado and enriquecido != dado
            if mudou:
                dado.clear()
                dado.update(enriquecido)
            if "request_id" not in dado:
                dado["request_id"] = rid
                mudou = True
            # ⭐ 13/09/2026 — TODA resposta carrega `ok`, e o lugar é aqui pelo mesmo motivo
            # que o `request_id`: são 276 tools e as próximas nasceriam sem.
            #
            # O achado do Cowork nas 3 rodadas nunca foi a negativa — `{"existe": false}` é
            # honesto e o agente lê. Foi a resposta SEM `ok` NENHUM: aí ele não consegue
            # distinguir "consultei e não existe" de "a chamada nem chegou". Era o
            # `ver_ficha_cliente` na rodada 2, o `dossie_juridico` na 3, e ainda restavam
            # `briefing_contrato_novo` e `consultar_auditoria`.
            #
            # ⚠️ Só PREENCHE a ausência. `ok: false` que a tool decidiu passa intacto — quem
            # chegou até aqui sem `ok` teve sucesso, porque falha vira exceção e sai pela
            # rede de erro acima, nunca por este caminho.
            #
            # ⚠️⚠️ E NÃO estampa sobre `{"erro": ...}`. Se uma tool devolve erro em campo
            # solto, `ok: true` ao lado seria uma contradição assinada por mim — pior que a
            # ausência que eu estava consertando. Hoje não existe nenhuma (as 7 que havia
            # viraram envelope, e `test_envelope_de_erro.py` reprova o build se voltarem),
            # mas a rede fica: fail-closed é o que faz a próxima nascer protegida.
            if "ok" not in dado and not (dado.keys() & {"erro", "error"}):
                dado = {"ok": True, **dado}
                resultado.structured_content = dado
                mudou = True
            if mudou:
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
            texto = _json.dumps(dado, ensure_ascii=False, default=str)
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
