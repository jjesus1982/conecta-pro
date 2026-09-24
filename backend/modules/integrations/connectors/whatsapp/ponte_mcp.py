"""Ponte do José Luís para as ferramentas do MCP — SÓ LEITURA, e só para quem supervisiona.

O Jordan pediu (23/09/2026) que o José Luís tivesse "as mesmas tools do Conecta PRO MCP do
Claude Cowork". São 277. A tentação era reimplementar as leituras operacionais aqui dentro,
e seria a duplicação que esta casa já pagou três vezes: uma família de código que divergiria
na primeira mudança. O MCP já tem as 277 com classe de risco, nível LGPD, o muro de
`propose` e nove travas de build em cima. Então a ponte **consome**, não copia.

## Três decisões que são a segurança desta ponte

**1. Conector INTERNO, nunca o público.** Medido em 23/09: o mesmo token dá `401` em
`conecta-pro-mcp` (o Cowork, que carrega a identidade do Jordan) e `200` em `mcp-internal`.
A separação de identidade que já existia nos dois conectores é exatamente a porta certa —
o José Luís entra como `mcp-service`, e nunca herda o poder do dono. Se algum dia esta
ponte apontar para o conector público, um funcionário no WhatsApp passa a agir como Jordan.
**É a linha mais importante deste arquivo.**

**2. Só `read`, fail-closed.** Antes de chamar qualquer coisa a ponte pede o CONTRATO da
tool ao próprio MCP (`conecta_pro_capabilities(tool=...)`) e recusa tudo que não seja
`classe == "read"`. Sem contrato, sem resposta, contrato ilegível → recusa. Escrita continua
pelo caminho curado (tools de ação + Central de Rascunhos), onde o humano aprova. Nenhuma
`write_low` e nenhuma das 40 `propose` passa por aqui — e dinheiro que sai, jamais.

**3. Só quem supervisiona alcança.** O gate de QUEM é nosso (`supervisao.papel_de_supervisao`):
Jordan e Orlailson. Sem isso, um agente de portaria perguntando no privado herdaria leitura
sobre a vida de 61 pessoas. A ponte não confia na fala para saber quem pergunta — o papel vem
do telefone, como em todo o resto deste conector.

## Por que duas tools e não 186

186 schemas não cabem num prompt de WhatsApp (o teto é 3000 tokens para o dono, 500 para os
outros). Então o José Luís recebe DUAS: `buscar_capacidade(termo)` descobre o nome, e
`consultar_erp(tool, args)` executa. É o mesmo padrão de busca-e-usa que qualquer agente com
catálogo grande precisa — e tem o efeito lateral de o agente ter de declarar o que procura
antes de tocar em dado.

ponty: sem impersonação nesta volta — sem `x-usuario-token` o MCP usa a conta de serviço
(`operator`, não-admin), que já é escopo menor que o do Jordan. Quando fizer sentido escopar
a leitura à PESSOA (e não ao serviço), o caminho é mintar o JWT dela e mandar no cabeçalho
`x-usuario-token`: o MCP já prefere o token do chamador à conta de serviço (F2).
"""
from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx
from core.logging import logger

#: ⚠️ INTERNO. `conecta-pro-mcp` é o conector do Cowork e carrega a identidade do Jordan.
_URL = os.getenv("JOSE_LUIS_MCP_URL", "http://mcp-internal:8788/mcp")
_TOKEN = os.getenv("JOSE_LUIS_MCP_TOKEN") or os.getenv("MCP_AUTH_TOKEN", "")

_ACCEPT = "application/json, text/event-stream"
_TTL_CATALOGO = 600.0

#: (sessão, validade). FastMCP exige `initialize` + `notifications/initialized` antes de
#: `tools/call`, e devolve a sessão no cabeçalho `mcp-session-id`.
_sessao: tuple[str | None, float] = (None, 0.0)
_catalogo: tuple[list[dict], float] = ([], 0.0)
#: nome -> contrato. Cacheado porque a classe de risco de uma tool não muda entre deploys.
_contratos: dict[str, dict] = {}


def _cabecalhos(sid: str | None = None) -> dict[str, str]:
    h = {"Authorization": f"Bearer {_TOKEN}", "Content-Type": "application/json", "Accept": _ACCEPT}
    if sid:
        h["mcp-session-id"] = sid
    return h


def _corpo(r: httpx.Response) -> dict:
    """Resposta JSON-RPC, venha ela como JSON ou como SSE.

    ⚠️ O Streamable HTTP responde `text/event-stream` quando quer: o corpo vem em linhas
    `data: {...}`. Ler só `r.json()` funciona em teste e falha em produção — foi assim que
    um `curl` meu viu HTTP 200 e não viu o erro JSON-RPC dentro dele.
    """
    txt = r.text or ""
    if txt.lstrip().startswith("{"):
        return r.json()
    import json  # noqa: PLC0415
    for linha in txt.splitlines():
        if linha.startswith("data:"):
            try:
                return json.loads(linha[5:].strip())
            except Exception:  # noqa: BLE001
                continue
    return {}


async def _abrir_sessao(cli: httpx.AsyncClient) -> str | None:
    r = await cli.post(_URL, headers=_cabecalhos(), json={
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                   "clientInfo": {"name": "jose-luis", "version": "1"}}})
    if r.status_code >= 400:
        logger.error("ponte_mcp: initialize %s em %s", r.status_code, _URL)
        return None
    sid = r.headers.get("mcp-session-id")
    if sid:
        await cli.post(_URL, headers=_cabecalhos(sid),
                       json={"jsonrpc": "2.0", "method": "notifications/initialized"})
    return sid


async def _rpc(method: str, params: dict | None = None, *, tentativa: int = 0) -> dict:
    """Uma chamada JSON-RPC ao MCP interno, reabrindo a sessão quando ela expira."""
    global _sessao  # noqa: PLW0603
    if not _TOKEN:
        return {"erro": "ponte sem token — MCP_AUTH_TOKEN ausente no backend"}
    sid, val = _sessao
    async with httpx.AsyncClient(timeout=45.0) as cli:
        if not sid or time.time() > val:
            sid = await _abrir_sessao(cli)
            if not sid:
                return {"erro": "MCP interno não respondeu ao initialize"}
            _sessao = (sid, time.time() + 1800)
        r = await cli.post(_URL, headers=_cabecalhos(sid),
                           json={"jsonrpc": "2.0", "id": 2, "method": method, "params": params or {}})
        # Sessão morta (o MCP reiniciou): uma única retentativa com sessão nova. Sem o teto
        # de tentativa isto vira laço quando o MCP está fora do ar de verdade.
        if r.status_code in (400, 404) and tentativa == 0:
            _sessao = (None, 0.0)
            return await _rpc(method, params, tentativa=1)
        if r.status_code >= 400:
            return {"erro": f"MCP respondeu {r.status_code}"}
        corpo = _corpo(r)
        if "error" in corpo:
            return {"erro": str(corpo["error"])[:300]}
        return corpo.get("result") or {}


def _texto_do_resultado(res: dict) -> Any:
    """Conteúdo útil de um `tools/call`. FastMCP devolve `structuredContent` quando a tool
    retorna dict, e `content[].text` sempre. Prefiro o estruturado — o texto é o mesmo dado
    serializado, e reparsear string é onde se perde tipo."""
    if isinstance(res.get("structuredContent"), dict):
        return res["structuredContent"]
    for bloco in res.get("content") or []:
        if bloco.get("type") == "text":
            import json  # noqa: PLC0415
            t = bloco.get("text") or ""
            try:
                return json.loads(t)
            except Exception:  # noqa: BLE001
                return t
    return res


async def catalogo() -> list[dict]:
    """[{nome, descricao}] das tools do MCP interno. Cache de 10 min."""
    global _catalogo  # noqa: PLW0603
    itens, val = _catalogo
    if itens and time.time() < val:
        return itens
    res = await _rpc("tools/list")
    if "erro" in res:
        logger.error("ponte_mcp: catálogo indisponível (%s)", res["erro"])
        return itens  # o que estava em cache é melhor que nada
    novos = [{"nome": t.get("name", ""), "descricao": (t.get("description") or "").strip()}
             for t in (res.get("tools") or []) if t.get("name")]
    if novos:
        _catalogo = (novos, time.time() + _TTL_CATALOGO)
    return novos or itens


async def contrato(nome: str) -> dict:
    """Contrato da tool pelo próprio MCP: classe de risco, LGPD, se escreve, se sai da empresa."""
    if nome in _contratos:
        return _contratos[nome]
    res = await _rpc("tools/call", {"name": "conecta_pro_capabilities", "arguments": {"tool": nome}})
    if "erro" in res:
        return {"erro": res["erro"]}
    c = _texto_do_resultado(res)
    if isinstance(c, dict) and (c.get("classe") or c.get("classe_de_risco")):
        _contratos[nome] = c
    return c if isinstance(c, dict) else {"erro": "contrato ilegível"}


def _pontuar(termo: str, item: dict) -> int:
    t = termo.lower().strip()
    if not t:
        return 0
    palavras = [p for p in re.split(r"[^a-z0-9á-ú]+", t) if len(p) > 2]
    nome, desc = item["nome"].lower(), item["descricao"].lower()
    p = 0
    for w in palavras:
        if w in nome:
            p += 10
        if w in desc:
            p += 3
    if t in nome:
        p += 20
    return p


async def buscar_capacidade(termo: str, *, limite: int = 12) -> dict:
    """Nomes de ferramentas de LEITURA que casam com `termo`. Descoberta, não execução."""
    itens = await catalogo()
    if not itens:
        return {"erro": "catálogo do MCP indisponível agora"}
    ranked = sorted(((_pontuar(termo, i), i) for i in itens), key=lambda x: -x[0])
    achados = [i for p, i in ranked if p > 0][:limite]
    if not achados:
        return {"achados": [], "dica": f"Nada casou com {termo!r}. Tente outro termo, mais curto."}
    return {"achados": achados, "total_no_catalogo": len(itens),
            "como_usar": "chame consultar_erp(tool=<nome>, args={...}); só leitura passa"}


async def consultar_erp(tool: str, args: dict | None = None) -> dict:
    """Executa uma tool de LEITURA do MCP. Recusa qualquer outra classe, fail-closed.

    A recusa é deliberadamente informativa sobre O QUE seria feito, e deliberadamente
    silenciosa sobre COMO contornar: a resposta que ensina a confirmar é a resposta que
    treina o modelo a burlar.
    """
    nome = (tool or "").strip()
    if not nome:
        return {"erro": "qual ferramenta? use buscar_capacidade(termo) primeiro"}

    c = await contrato(nome)
    if "erro" in c:
        return {"erro": f"não consegui o contrato de {nome!r} — recusado por precaução",
                "detalhe": str(c.get("erro"))[:200]}
    classe = str(c.get("classe") or c.get("classe_de_risco") or "").lower()
    if classe != "read":
        return {"recusado": True, "codigo": "SOMENTE_LEITURA",
                "mensagem": f"{nome} é {classe or 'não classificada'} — o José Luís só lê.",
                "o_que_faria": c.get("o_que_faz") or c.get("descricao"),
                "caminho_certo": ("pedido que muda algo vira rascunho na Central de Aprovações, "
                                  "decidido pelo Jordan ou pelo Orlailson")}

    res = await _rpc("tools/call", {"name": nome, "arguments": args or {}})
    if "erro" in res:
        return {"erro": res["erro"], "tool": nome}
    return {"tool": nome, "lgpd": c.get("lgpd"), "dado": _texto_do_resultado(res)}
