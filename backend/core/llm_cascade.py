"""Cascata de LLM do Conecta PRO — OpenAI primeiro, Anthropic como fallback opcional.

Decisão do dono (2026-07): OpenAI é o provedor pago da casa; a Anthropic só entra
como fallback SE `ANTHROPIC_API_KEY` estiver definida. Se nenhum provedor estiver
disponível/funcionar, as funções retornam None e o call site aplica o seu próprio
fallback honesto (regex, dense, frases prontas) — este módulo NUNCA fabrica resposta.

Uso:
    from core.llm_cascade import chat            # sync
    from core.llm_cascade import achat           # async

    texto = chat(
        messages=[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}],
        model_openai="gpt-5",  # diretriz do dono: melhor modelo da OpenAI em todos os call sites
        model_anthropic="claude-sonnet-4-6",   # opcional; None = sem fallback Anthropic
        max_tokens=1024,
    )

Notas de compatibilidade:
- OpenAI: o texto vem em `response.choices[0].message.content`.
- Anthropic: o texto vem em `response.content[0].text`; mensagens com role
  "system" são extraídas para o parâmetro `system` (a API exige).
- Modelos gpt-5*/o* (reasoning): usam `max_completion_tokens` e não aceitam
  `temperature` custom — o helper trata isso e aplica um piso de tokens para o
  raciocínio não engolir a resposta.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

# Modelos "reasoning" da OpenAI: sem temperature custom + max_completion_tokens
_REASONING_PREFIXES = ("gpt-5", "o1", "o3", "o4")
# Piso de tokens p/ modelos reasoning (o raciocínio conta no orçamento de saída)
_REASONING_MIN_TOKENS = 2000


def _openai_key() -> str | None:
    return os.getenv("OPENAI_API_KEY", "").strip() or None


def _anthropic_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY", "").strip() or None


def _split_system(messages: list[dict]) -> tuple[str | None, list[dict]]:
    """Separa mensagens 'system' (exigência da API Anthropic)."""
    system_parts = [m.get("content", "") for m in messages if m.get("role") == "system"]
    rest = [m for m in messages if m.get("role") != "system"]
    system = "\n\n".join(p for p in system_parts if p) or None
    return system, rest


def _openai_kwargs(
    messages: list[dict],
    model: str,
    max_tokens: int,
    temperature: float | None,
    json_mode: bool,
) -> dict:
    is_reasoning = model.lower().startswith(_REASONING_PREFIXES)
    kwargs: dict = {
        "model": model,
        "messages": messages,
        "max_completion_tokens": max(max_tokens, _REASONING_MIN_TOKENS) if is_reasoning else max_tokens,
    }
    if temperature is not None and not is_reasoning:
        kwargs["temperature"] = temperature
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    return kwargs


def _anthropic_kwargs(
    messages: list[dict],
    model: str,
    max_tokens: int,
    temperature: float | None,
) -> dict:
    system, rest = _split_system(messages)
    kwargs: dict = {"model": model, "max_tokens": max_tokens, "messages": rest}
    if system:
        kwargs["system"] = system
    if temperature is not None:
        kwargs["temperature"] = temperature
    return kwargs


def _extract_openai_text(response) -> str | None:
    try:
        text = response.choices[0].message.content
    except (AttributeError, IndexError):
        return None
    text = (text or "").strip()
    return text or None


def _extract_anthropic_text(response) -> str | None:
    try:
        parts = [b.text for b in response.content if getattr(b, "type", "text") == "text"]
    except (AttributeError, TypeError):
        return None
    text = "".join(parts).strip()
    return text or None


# ── Versões estendidas: retornam (texto, provedor, modelo) ────────────────────


def chat_ex(
    messages: list[dict],
    model_openai: str,
    model_anthropic: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
    json_mode: bool = False,
) -> tuple[str, str, str] | None:
    """Cascata sync: OpenAI → Anthropic. Retorna (texto, provedor, modelo) ou None."""
    # 1) OpenAI (primário)
    api_key = _openai_key()
    if api_key:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=api_key)
            response = client.chat.completions.create(
                **_openai_kwargs(messages, model_openai, max_tokens, temperature, json_mode)
            )
            text = _extract_openai_text(response)
            if text:
                logger.info("llm_cascade: resposta via OpenAI (%s)", model_openai)
                return text, "openai", model_openai
            logger.warning("llm_cascade: OpenAI (%s) retornou vazio — tentando fallback", model_openai)
        except Exception as e:  # noqa: BLE001
            logger.warning("llm_cascade: OpenAI (%s) falhou: %s — tentando fallback", model_openai, e)
    else:
        logger.info("llm_cascade: OPENAI_API_KEY ausente — pulando OpenAI")

    # 2) Anthropic (fallback opcional)
    anth_key = _anthropic_key()
    if model_anthropic and anth_key:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=anth_key)
            response = client.messages.create(
                **_anthropic_kwargs(messages, model_anthropic, max_tokens, temperature)
            )
            text = _extract_anthropic_text(response)
            if text:
                logger.info("llm_cascade: resposta via Anthropic (%s)", model_anthropic)
                return text, "anthropic", model_anthropic
            logger.warning("llm_cascade: Anthropic (%s) retornou vazio", model_anthropic)
        except Exception as e:  # noqa: BLE001
            logger.warning("llm_cascade: Anthropic (%s) falhou: %s", model_anthropic, e)
    elif model_anthropic and not anth_key:
        logger.info("llm_cascade: ANTHROPIC_API_KEY ausente — sem fallback Anthropic")

    logger.warning("llm_cascade: nenhum provedor LLM disponível/funcionou — retornando None")
    return None


async def achat_ex(
    messages: list[dict],
    model_openai: str,
    model_anthropic: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
    json_mode: bool = False,
) -> tuple[str, str, str] | None:
    """Cascata async: OpenAI → Anthropic. Retorna (texto, provedor, modelo) ou None."""
    # 1) OpenAI (primário)
    api_key = _openai_key()
    if api_key:
        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(api_key=api_key)
            response = await client.chat.completions.create(
                **_openai_kwargs(messages, model_openai, max_tokens, temperature, json_mode)
            )
            text = _extract_openai_text(response)
            if text:
                logger.info("llm_cascade: resposta via OpenAI (%s)", model_openai)
                return text, "openai", model_openai
            logger.warning("llm_cascade: OpenAI (%s) retornou vazio — tentando fallback", model_openai)
        except Exception as e:  # noqa: BLE001
            logger.warning("llm_cascade: OpenAI (%s) falhou: %s — tentando fallback", model_openai, e)
    else:
        logger.info("llm_cascade: OPENAI_API_KEY ausente — pulando OpenAI")

    # 2) Anthropic (fallback opcional)
    anth_key = _anthropic_key()
    if model_anthropic and anth_key:
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=anth_key)
            response = await client.messages.create(
                **_anthropic_kwargs(messages, model_anthropic, max_tokens, temperature)
            )
            text = _extract_anthropic_text(response)
            if text:
                logger.info("llm_cascade: resposta via Anthropic (%s)", model_anthropic)
                return text, "anthropic", model_anthropic
            logger.warning("llm_cascade: Anthropic (%s) retornou vazio", model_anthropic)
        except Exception as e:  # noqa: BLE001
            logger.warning("llm_cascade: Anthropic (%s) falhou: %s", model_anthropic, e)
    elif model_anthropic and not anth_key:
        logger.info("llm_cascade: ANTHROPIC_API_KEY ausente — sem fallback Anthropic")

    logger.warning("llm_cascade: nenhum provedor LLM disponível/funcionou — retornando None")
    return None


# ── API principal: retorna só o texto (ou None) ───────────────────────────────


def chat(
    messages: list[dict],
    model_openai: str,
    model_anthropic: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
    json_mode: bool = False,
) -> str | None:
    """Chat completion sync com cascata OpenAI → Anthropic. None se ninguém respondeu."""
    result = chat_ex(
        messages,
        model_openai,
        model_anthropic=model_anthropic,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=json_mode,
    )
    return result[0] if result else None


async def achat(
    messages: list[dict],
    model_openai: str,
    model_anthropic: str | None = None,
    max_tokens: int = 1024,
    temperature: float | None = None,
    json_mode: bool = False,
) -> str | None:
    """Chat completion async com cascata OpenAI → Anthropic. None se ninguém respondeu."""
    result = await achat_ex(
        messages,
        model_openai,
        model_anthropic=model_anthropic,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=json_mode,
    )
    return result[0] if result else None
