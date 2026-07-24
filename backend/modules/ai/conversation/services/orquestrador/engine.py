"""Motor do orquestrador escopado: loop de function-calling in-backend.

Executa cada tool-handler com a identidade REAL do usuário (db, user, scope) — o
RBAC/escopo barra na fonte. Groundedness BRANDO (flag, não bloqueia) sobre a fonte
acumulada dos resultados das tools + auditoria append-only. NÃO usa consultor_hub.gerar
(não retorna tool_calls); usa AsyncOpenAI direto, como o molde do whatsapp/agent_service.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from modules.ai.conversation.services.garantia import agent_audit, groundedness

from .tool_registry import ToolDef, openai_schema

logger = logging.getLogger(__name__)

_DISCLAIMER = (
    "Resposta gerada por consultor de IA sobre os SEUS dados (escopo do seu perfil). "
    "Confira antes de agir. Ações que mexem em ponto/folha exigem aprovação humana."
)


def _model() -> str:
    return os.getenv("OPENAI_AGENT_MODEL", "gpt-5.1")


def _chat_kwargs(model: str, max_tokens: int, temperature: float = 0.2) -> dict[str, Any]:
    """gpt-5.x/o-series: max_completion_tokens, sem temperature custom. gpt-4.x: clássico.
    Espelha whatsapp/agent_service._chat_kwargs (315)."""
    m = model.lower()
    if m.startswith(("gpt-5", "o1", "o3", "o4")):
        return {"max_completion_tokens": max_tokens}
    return {"max_tokens": max_tokens, "temperature": temperature}


@dataclass
class OrqScope:
    tier: str  # "gestor" | "lider" | "clt" | "cliente"
    employee_id: str | None = None
    post_ids: list[str] | None = None  # None = todos (gestor); [] = nenhum
    all_posts: bool = False
    is_manager: bool = False
    client_id: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


async def run_engine(
    db: AsyncSession,
    user,
    scope: OrqScope,
    tools: list[ToolDef],
    pergunta: str,
    *,
    system_prompt: str,
    origem: str = "consultor_escopado",
    max_rounds: int = 6,
    max_tokens: int = 1200,
    client=None,
) -> dict[str, Any]:
    if client is None:
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = AsyncOpenAI(timeout=float(os.getenv("AGENT_OPENAI_TIMEOUT", "90")))

    by_name = {t.name: t for t in tools}
    active_tools = [openai_schema(t) for t in tools]
    model = _model()

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": pergunta},
    ]
    tool_results: list[Any] = []  # tudo que as tools retornaram (fonte do groundedness)
    resposta = ""
    provider = "openai"

    for _round in range(1, max_rounds + 1):
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            tools=active_tools if active_tools else None,
            tool_choice="auto" if active_tools else None,
            **_chat_kwargs(model, max_tokens),
        )
        msg = resp.choices[0].message
        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            resposta = (msg.content or "").strip()
            break

        messages.append(
            {
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": tc.id, "type": "function",
                     "function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                    for tc in tool_calls
                ],
            }
        )
        for tc in tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:  # noqa: BLE001
                args = {}
            tool = by_name.get(tc.function.name)
            if tool is None:
                result: Any = {"erro": "tool indisponível no seu escopo"}
            else:
                try:
                    result = await tool.handler(db, user, scope, **args)
                except PermissionError:
                    result = {"erro": "fora do seu escopo — aguardando dado"}
                except Exception as e:  # noqa: BLE001 — tool nunca derruba o loop
                    logger.warning("orq tool %s falhou: %s", tc.function.name, e)
                    result = {"erro": "não consegui obter esse dado agora"}
            tool_results.append(result)
            messages.append(
                {"role": "tool", "tool_call_id": tc.id,
                 "content": json.dumps(result, ensure_ascii=False, default=str)}
            )
    else:
        # teto sem resposta final → última chamada SEM tools (força texto)
        resp = await client.chat.completions.create(
            model=model, messages=messages, **_chat_kwargs(model, max_tokens)
        )
        resposta = (resp.choices[0].message.content or "").strip()

    # GROUNDEDNESS BRANDO: fonte = números reais retornados pelas tools; flag, não bloqueia.
    fonte: dict[str, Any] = {f"tool_{i}": r for i, r in enumerate(tool_results)}
    g = groundedness.verificar(resposta, fonte)
    suspeitos = list(g.get("suspeitos") or [])
    flags: list[str] = []
    grounded = not suspeitos
    if suspeitos:
        flags.append("confira: alguns números não puderam ser verificados contra as tools")
        resposta = resposta + (
            "\n\n[Aviso: alguns números acima não puderam ser verificados automaticamente "
            "contra os dados do ERP — confira antes de decidir.]"
        )

    try:
        await agent_audit.registrar_acao_agente(
            db, origem=origem, pergunta=pergunta, resposta=resposta,
            modelo=model, tier=scope.tier, provider=provider,
            groundedness_ok=grounded, trace_id=f"{origem}.{scope.tier}",
        )
    except Exception as e:  # noqa: BLE001
        logger.warning("orq: falha ao auditar: %s", e)

    return {
        "resposta": resposta or "(sem resposta)",
        "provider": provider, "modelo": model, "grounded": grounded,
        "flags": flags, "origem": origem, "tier": scope.tier, "disclaimer": _DISCLAIMER,
    }
