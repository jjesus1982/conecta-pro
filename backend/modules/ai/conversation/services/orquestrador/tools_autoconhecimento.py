"""F4 — o agente responde "o que você faz?" a partir do REGISTRO VIVO, não de prosa.

A pergunta já é oferecida ao usuário: `conversation_engine` sugere "O que posso fazer?" como
quick reply. Até aqui a resposta saía do modelo parafraseando 40 schemas de tool — e paráfrase
de catálogo é onde nasce a promessa que o sistema não cumpre. Esta casa já tem o nome disso:
IA dormente é casca, e a dívida quase nunca é código faltando, é código DESLIGADO.

Então a resposta é DERIVADA: as consultas saem de `read_dispatcher._READ_OPS`, as ações de
`agir_dispatcher._ACOES`, e o conjunto de tools sai do MESMO resolvedor que serve a conversa
(`_resolver_tier_e_tools`) — não de uma reimplementação da regra de tier, que drifaria.

Três decisões que fazem a diferença entre autoconhecimento e propaganda:

1. **Escopado.** Responde o que ESTE usuário alcança, não o catálogo. Dizer a um porteiro que
   "posso fechar a folha" é mentira com sotaque de recurso.
2. **Com o grau junto.** `agir_*` nunca é "eu faço": é "eu PROPONHO e outra pessoa aprova".
   A parede F1 existe para isso; a autodescrição não pode contradizê-la.
3. **Diz o que NÃO alcança.** `nao_alcanco` é a parte incômoda e é a mais útil: é a régua de
   cobertura do Jordan — quanta coisa do dia dele termina sem sair do ERP.

⚠️ De propósito NÃO há aqui nenhuma lista escrita à mão de "o que eu nunca faço". O
Operacional é read-only porque não tem ação registrada — a ausência no registro É a prova.
Uma lista em prosa seria justamente a peça que envelhece e passa a mentir.
"""
from __future__ import annotations

from typing import Any

from .agir_dispatcher import _ACOES
from .read_dispatcher import _READ_OPS
from .tool_registry import ToolDef, register

_SEM_ARGS: dict[str, Any] = {"type": "object", "properties": {}}


async def _o_que_voce_faz(db, user, scope, **_) -> dict[str, Any]:
    # Import tardio: o controller importa este módulo no topo (registra as tools), então
    # importar o controller aqui em cima fecharia o ciclo. Reusar o resolvedor é o ponto —
    # reimplementar a regra de tier faria a autodescrição divergir do que é servido de fato.
    from modules.ai.conversation.controllers.consultor_escopado_controller import (  # noqa: PLC0415
        _resolver_tier_e_tools,
    )

    _, tools = await _resolver_tier_e_tools(db, user)
    nomes = {t.name for t in tools}

    consultar: dict[str, list[str]] = {}
    propor: dict[str, list[str]] = {}
    entrego: list[dict[str, str]] = []

    for t in sorted(tools, key=lambda x: x.name):
        if t.name.startswith("consultar_"):
            mod = t.name[len("consultar_"):]
            consultar[mod] = sorted(_READ_OPS.get(mod, {}))
        elif t.name.startswith("agir_"):
            mod = t.name[len("agir_"):]
            propor[mod] = sorted(_ACOES.get(mod, {}))
        elif t.name != "o_que_voce_faz":
            # gera-doc e tools self/posto: entregam resultado direto
            entrego.append({"tool": t.name, "faz": (t.description or "").split("\n")[0][:150]})

    # O gap: módulo com ops registradas que este usuário NÃO alcança POR NENHUMA VIA. Descontar
    # o módulo declarado das tools importa — o líder recebe tools de posto (module="operacional",
    # scope_kind="posto") sem receber `consultar_operacional`, e listar operacional como
    # inalcançável para ele seria exagerar o buraco. Régua que exagera é régua que se descarta.
    fora = sorted((set(_READ_OPS) | set(_ACOES))
                  - set(consultar) - set(propor) - {t.module for t in tools})

    return {
        "quem_sou": "Orquestrador do Conecta PRO, agindo com a identidade real de quem "
                    "conversa comigo. Consulto na hora; para agir, eu PROPONHO.",
        "seu_alcance": {
            "tier": getattr(scope, "tier", None),
            "tools_disponiveis": len(nomes),
        },
        "consulto_e_respondo_na_hora": consultar or "nenhuma consulta no seu escopo",
        "proponho_e_um_humano_aprova": propor or "nenhuma ação no seu escopo",
        "como_funciona_a_proposta": (
            "Toda ação vira RASCUNHO inerte na Central de Aprovações. Eu não executo o que "
            "proponho — quem aprova não pode ser quem pede. Dinheiro que sai e eSocial "
            "exigem ainda um código OTP na aprovação, fora de mim."
        ),
        "entrego_direto": entrego or "nenhum documento no seu escopo",
        "nao_alcanco": fora or "nada — você alcança todos os módulos com tools registradas",
    }


register(ToolDef(
    "o_que_voce_faz",
    "self",
    "Responde o que VOCÊ (o agente) consegue fazer para ESTE usuário: consultas disponíveis, "
    "ações que você pode propor, documentos que entrega e o que está fora do alcance dele. "
    "Use sempre que perguntarem 'o que você faz/pode fazer', em vez de responder de memória — "
    "esta tool lê o registro vivo e não erra para mais.",
    _SEM_ARGS,
    _o_que_voce_faz,
    scope_kind="self",
))
