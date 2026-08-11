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


def _extrair_documentos(tool_results: list[Any]) -> list[dict[str, Any]]:
    """Coleta os artefatos de documento (gera-doc) dos retornos das tools: só dicts
    com arquivo_base64 E nome (recusa/erro não viram documento)."""
    return [
        {"nome": r["nome"], "arquivo_base64": r["arquivo_base64"], "resumo": r.get("resumo", "")}
        for r in tool_results
        if isinstance(r, dict) and r.get("arquivo_base64") and r.get("nome")
    ]


def _extrair_rascunho(tool_results: list[Any]) -> dict[str, Any] | None:
    """Último rascunho criado nesta rodada (criar_rascunho devolve status='rascunho'+draft_id).

    Vai no retorno para o chat poder oferecer a CONFIRMAÇÃO na hora — sem isto o usuário
    precisa sair da conversa e ir à Central de Aprovações. `gate` viaja junto porque decide
    se dá para confirmar ali mesmo ou se o caminho é OTP (dinheiro/eSocial)."""
    for r in reversed(tool_results):
        if isinstance(r, dict) and r.get("status") == "rascunho" and r.get("draft_id"):
            return {"draft_id": str(r["draft_id"]), "titulo": r.get("titulo", ""),
                    "tipo": r.get("tipo", ""), "gate": r.get("gate", "")}
    return None


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
    imagens: list[str] | None = None,
) -> dict[str, Any]:
    if client is None:
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = AsyncOpenAI(timeout=float(os.getenv("AGENT_OPENAI_TIMEOUT", "90")))

    by_name = {t.name: t for t in tools}
    active_tools = [openai_schema(t) for t in tools]
    model = _model()

    # Anexo-foto: content vira lista (texto + image_url) p/ o vision do gpt-5.1 enxergar.
    # `pergunta` (str) segue intacta p/ audit/groundedness abaixo.
    user_content: Any = pergunta
    if imagens:
        user_content = [{"type": "text", "text": pergunta}] + [
            {"type": "image_url", "image_url": {"url": u}} for u in imagens
        ]
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
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
                    # Erro TÉCNICO ≠ falta de permissão: não mascarar como "sem acesso"/"aguardando
                    # dado" (isso fazia bug virar trava percebida). Sinalizar que é técnico + detalhe.
                    result = {"erro": "erro técnico ao executar esta ação (NÃO é falta de permissão nem "
                                      "dado ausente) — pode tentar de novo; se persistir, avise o suporte",
                              "detalhe": str(e)[:200]}
            tool_results.append(result)
            # NÃO devolver o base64 do documento ao LLM: um PDF em base64 tem dezenas de
            # milhares de tokens e estoura o contexto (erro 400 context_length_exceeded).
            # O LLM só precisa saber que o documento saiu; o base64 segue no `documentos`
            # do retorno (para o frontend baixar).
            _llm_result = result
            if isinstance(result, dict) and result.get("arquivo_base64"):
                _llm_result = {k: v for k, v in result.items() if k != "arquivo_base64"}
                _llm_result["documento_gerado"] = result.get("nome") or "documento.pdf"
            messages.append(
                {"role": "tool", "tool_call_id": tc.id,
                 "content": json.dumps(_llm_result, ensure_ascii=False, default=str)}
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
        "documentos": _extrair_documentos(tool_results),
        "rascunho": _extrair_rascunho(tool_results),   # p/ confirmar sem sair da conversa
    }
