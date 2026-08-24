"""F2 — o conector para de CUNHAR identidade e passa a ENCAMINHAR a de quem perguntou.

Estado que originou (23/08/2026): toda chamada do conector do agente ia ao ERP com o JWT da
conta de serviço `mcp-service@`. O RBAC do ERP funcionava — e respondia sobre o usuário
errado. Um porteiro perguntando "quantas horas eu fiz esse mês" era atendido com os poderes da
conta de serviço, e a auditoria registrava `mcp-service`, não ele. Era o teto do agente: nunca
poderia atender o time em assunto sensível, que é onde ele valeria mais.

O desenho, em uma frase: **o conector não decide quem é o usuário — ele repassa a prova.**

O que chega no cabeçalho `X-Usuario-Token` é o JWT do PRÓPRIO usuário, emitido e assinado pelo
ERP. O conector não o interpreta, não confia em nome, não deduz papel: encaminha. Quem valida é
o ERP, que é quem emitiu. Por isso o canal é um token e não um `X-Usuario: email` — cabeçalho
com e-mail é forjável por qualquer um que tenha o bearer do conector, e seria a mesma classe de
erro do `confirmar="ACEITAR"`: um controle que o chamador preenche sozinho.

FAIL-CLOSED nas sensíveis. Sem identidade encaminhada, tool sensível NÃO EXECUTA — e sensível
aqui é o DEFAULT: qualquer escrita, e toda leitura que não esteja explicitamente liberada. O
grupo de assunto que carrega dado pessoal/dinheiro. Grupo desconhecido conta como sensível.

⚠️ Consequência medida e aceita: o Hermes **não sabe** mandar cabeçalho por chamada — em
`tools/mcp_tool.py` os headers vêm de `dict(config.get("headers") or {})`, estáticos, resolvidos
uma vez por conexão. Então o Hermes perde as tools sensíveis até que alguém construa esse
repasse. Isso não é regressão: é a primeira vez que o sistema se recusa a responder sobre
dado alheio sem saber de quem é a pergunta. O caminho in-process (`run_engine`) já carrega a
identidade real e não é afetado.
"""
from __future__ import annotations

import os
from contextvars import ContextVar

try:
    from gate_propose import classe_de
except Exception:  # noqa: BLE001
    def classe_de(_n: str) -> str:  # type: ignore[misc]
        return "propose"

#: Só o conector do AGENTE exige repasse. No público (Cowork do Jordan) a conta de serviço É
#: o Jordan, autenticado por Google na entrada: lá não há terceiro sobre quem responder.
MODO_AGENTE = (os.getenv("MCP_MODO") or "").strip().lower() == "agente"

#: Cabeçalho onde o chamador põe o JWT do USUÁRIO (não o bearer do conector).
CABECALHO = "x-usuario-token"

#: Leituras revisadas à mão que NÃO carregam dado de terceiro nem dinheiro. Tudo o mais é
#: sensível — inclusive o que ninguém classificou. Duas listas e nenhum default permissivo.
#:
#: ⚠️ A versão anterior deduzia sensibilidade do GRUPO DE ASSUNTO do `tool_scopes` e foi
#: desmentida na primeira prova ao vivo: `resumo_financeiro` devolveu o MRR sem identidade
#: nenhuma, porque a rota é `/crm/financeiro` e o grupo dela é "comercial". Assunto não é
#: risco — é o mesmíssimo erro que a F1 veio corrigir no manifesto.
SEM_DADO_DE_TERCEIRO: dict[str, str] = {
    "beneficios_cct": "texto da CCT, igual para todos — nenhuma pessoa citada",
    "tabela_salarial_cct": "tabela pública da convenção coletiva",
    "consultar_parametros_precificacao": "parâmetro de cálculo da empresa, não de pessoa",
    "simular_preco": "simulação sobre números enviados na pergunta; não lê cadastro",
    "listar_precos_funcao": "tabela de preço por função, sem pessoa",
    "status_whatsapp": "estado do canal (conectado/não), sem conteúdo",
}

_TOKEN: ContextVar[str | None] = ContextVar("token_do_usuario", default=None)


def token_do_usuario() -> str | None:
    """JWT do usuário desta chamada, ou None quando ninguém se identificou."""
    return _TOKEN.get()


def sensivel(nome: str) -> bool:
    """Sensível é o DEFAULT. Só não é o que foi revisado à mão e liberado por escrito.

    Escreve/propõe → sensível. Lê → sensível, a menos que esteja em `SEM_DADO_DE_TERCEIRO`.
    Tool nova, tool não classificada, tool que ninguém olhou: sensível. Não declarar custa
    fricção, e a fricção é a pressão para declarar.
    """
    if classe_de(nome) != "read":
        return True
    return nome not in SEM_DADO_DE_TERCEIRO


# FastMCP chama o middleware como CALLABLE para despachar cada tipo de requisição; só o
# `on_call_tool` não basta. Classe duck-typed derrubava `initialize` com
# "'GatePropose' object is not callable" — e era ESSA a razão do Hermes ficar parked, não o
# conector fora do ar (meu curl viu HTTP 200 e parou; o 200 trazia erro JSON-RPC no corpo).
# Fallback para `object` quando o fastmcp não está importável: as travas rodam no HOST.
try:
    from fastmcp.server.middleware import Middleware as _Base
except Exception:  # noqa: BLE001
    _Base = object

class ExigeIdentidade(_Base):
    """Captura a identidade da chamada e barra tool sensível quando não veio nenhuma."""

    async def on_call_tool(self, context, call_next):  # noqa: ANN001
        from fastmcp.server.dependencies import get_http_headers  # noqa: PLC0415

        try:
            headers = get_http_headers() or {}
        except Exception:  # noqa: BLE001 — fora de HTTP (stdio) não há cabeçalho
            headers = {}
        token = (headers.get(CABECALHO) or "").strip() or None
        marca = _TOKEN.set(token)
        try:
            nome = getattr(getattr(context, "message", None), "name", "") or ""
            if token is None and sensivel(nome):
                from fastmcp.exceptions import ToolError  # noqa: PLC0415

                raise ToolError(
                    f"⛔ `{nome}` toca dado pessoal ou dinheiro e a chamada chegou SEM "
                    f"identidade. Eu não respondo sobre o dado de alguém sem saber de quem é "
                    f"a pergunta — responder com a conta de serviço seria atender qualquer um "
                    f"com os poderes do sistema.\n\n"
                    f"Quem chama precisa enviar o cabeçalho `{CABECALHO}` com o JWT do próprio "
                    f"usuário (o mesmo que o ERP emitiu no login dele)."
                )
            return await call_next(context)
        finally:
            _TOKEN.reset(marca)


def instalar(mcp) -> bool:
    """Instala a exigência. Devolve False quando o conector NÃO é de agente."""
    if not MODO_AGENTE:
        return False
    mcp.add_middleware(ExigeIdentidade())
    return True
