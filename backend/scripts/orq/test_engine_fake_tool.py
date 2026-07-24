"""Prova o loop de function-calling com um AsyncOpenAI FAKE (determinístico, sem OpenAI real).

Roteiro: round 1 o 'LLM' pede a tool fake; round 2 responde com o número que a tool devolveu.
Verifica: a tool foi executada com (db, user, scope, **args) e o número flui para a resposta,
e groundedness aprova (o número tem lastro no resultado da tool)."""
import asyncio
import json
from types import SimpleNamespace

from modules.ai.conversation.services.orquestrador import tool_registry as tr
from modules.ai.conversation.services.orquestrador.engine import OrqScope, run_engine

_chamou = {"n": 0, "scope_tier": None}


async def _fake_handler(db, user, scope, **args):
    _chamou["n"] += 1
    _chamou["scope_tier"] = scope.tier
    return {"postos_ativos": 7}


class _FakeCompletions:
    def __init__(self):
        self._round = 0

    async def create(self, **kwargs):
        self._round += 1
        if self._round == 1:
            tc = SimpleNamespace(
                id="call_1", type="function",
                function=SimpleNamespace(name="fake_postos", arguments=json.dumps({})),
            )
            msg = SimpleNamespace(content="", tool_calls=[tc])
        else:
            msg = SimpleNamespace(content="Você tem 7 postos ativos.", tool_calls=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)


class _FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeCompletions())


async def main() -> None:
    tr.register(tr.ToolDef(
        "fake_postos", "operacional", "Conta postos ativos",
        {"type": "object", "properties": {}}, _fake_handler,
    ))
    out = await run_engine(
        db=None, user=SimpleNamespace(id="u", role="gerente_operacional", permissions=["module:operacional"]),
        scope=OrqScope(tier="gestor", is_manager=True, all_posts=True),
        tools=[tr.get_tool("fake_postos")],
        pergunta="quantos postos ativos?",
        system_prompt="teste", client=_FakeClient(),
    )
    assert _chamou["n"] == 1, f"handler deveria rodar 1x, rodou {_chamou['n']}"
    assert _chamou["scope_tier"] == "gestor"
    assert "7 postos" in out["resposta"], out["resposta"]
    assert out["grounded"] is True, out
    print("OK loop executou a tool e ancorou o número:", out["resposta"])
    print("TEST engine_fake_tool PASS")


if __name__ == "__main__":
    asyncio.run(main())
