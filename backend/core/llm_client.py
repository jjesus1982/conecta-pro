"""Ponto ÚNICO de criação do cliente LLM — e a telemetria que vem junto.

Dois problemas que este módulo resolve de uma vez, ambos medidos em 23/08/2026:

1. **Trocar de provedor custava 11 edições.** Havia 11 instanciações diretas de
   `AsyncOpenAI` espalhadas (WhatsApp, Sophia, DP, motor do agente), e NENHUMA passava
   `base_url`. Trocar a OpenAI por DeepSeek, Gemini ou um modelo local significava editar
   onze lugares e esquecer um. Aqui é uma variável de ambiente.

2. **Ninguém sabia quanto se gasta.** Não existia nenhuma tabela registrando tokens. Sem
   linha de base, "economizamos com a troca" é opinião. A resposta da API já traz `usage`;
   o que faltava era alguém anotar.

A telemetria é envolvida no próprio cliente, não deixada a cargo de quem chama: telemetria
que depende de o chamador lembrar de chamar é telemetria que não existe. E ela NUNCA
derruba a chamada — falha de gravação vira log, porque perder a resposta do modelo para
salvar uma estatística seria trocar o ouro pelo troco.

Uso:
    from core.llm_client import novo_cliente
    client = novo_cliente(origem="agente.chat")        # async
    client = novo_cliente(origem="sophia", sincrono=True)
"""
from __future__ import annotations

import os
import time
from typing import Any

from core.logging import logger

# Preço por MILHÃO de tokens (entrada, saída) em USD. Fonte: páginas públicas dos
# provedores em agosto/2026. Serve para ORDEM DE GRANDEZA — a fatura é a verdade.
# Modelo desconhecido grava custo NULL em vez de chutar: número inventado numa planilha de
# custo é pior que célula vazia.
PRECOS: dict[str, tuple[float, float]] = {
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
    "deepseek-v4-flash": (0.22, 0.66),
    "deepseek-v4-pro": (0.66, 1.98),
    "gemini-3.7-flash": (0.75, 3.75),
    "claude-haiku-4-5": (1.00, 5.00),
    "glm-5.2": (0.60, 2.20),
    "local": (0.0, 0.0),
}


def _preco(modelo: str) -> tuple[float, float] | None:
    m = (modelo or "").strip().lower()
    if m in PRECOS:
        return PRECOS[m]
    # casa por prefixo: "gpt-5-2026-01-01" cai em "gpt-5"
    for chave, v in sorted(PRECOS.items(), key=lambda kv: -len(kv[0])):
        if m.startswith(chave):
            return v
    return None


# Preço do token que veio do CACHE, por milhão. A DeepSeek cobra ~3% do preço normal em
# cache hit; medido em 23/08/2026, 96% do prompt reaproveitou a partir da 2ª chamada.
# Ignorar isso superestima o custo em mais de 10× e faz a planilha mentir para cima.
PRECO_CACHE: dict[str, float] = {"deepseek": 0.007, "gpt-5": 0.125, "gpt-4o": 1.25}


def _preco_cache(modelo: str) -> float | None:
    m = (modelo or "").strip().lower()
    for chave, v in sorted(PRECO_CACHE.items(), key=lambda kv: -len(kv[0])):
        if m.startswith(chave):
            return v
    return None


def custo_usd(modelo: str, entrada: int, saida: int, cache_hit: int = 0) -> float | None:
    p = _preco(modelo)
    if p is None:
        return None
    pc = _preco_cache(modelo)
    cacheado = min(max(cache_hit, 0), entrada) if pc is not None else 0
    novo = entrada - cacheado
    return round(novo / 1_000_000 * p[0] + cacheado / 1_000_000 * (pc or 0.0)
                 + saida / 1_000_000 * p[1], 6)


def _base_url() -> str | None:
    """Base do provedor. Vazio = OpenAI. É ESTA variável que troca o motor inteiro."""
    return (os.getenv("LLM_BASE_URL") or os.getenv("OPENAI_BASE_URL") or "").strip() or None


def modelo_visao() -> str:
    """Modelo para conteúdo com IMAGEM. Nem todo modelo de chat lê imagem: a
    `deepseek-v4-flash` devolve HTTP 400 "This model does not support image", e a migração
    de 23/08 quebrou leitura de documento por foto até isto existir. Quem manda imagem
    escolhe por aqui, não pelo modelo de texto."""
    return (os.getenv("LLM_MODEL_VISAO") or "").strip() or _modelo_texto()


def modelo_texto() -> str:
    """Modelo de texto do provedor ATUAL. Nome fixo no código quebra na troca de provedor:
    varridos em 23/08, havia 57 referências cravadas em 22 arquivos, e a DeepSeek recusa
    todas com HTTP 400 ("The supported API model names are deepseek-v4-pro, ...")."""
    return (os.getenv("OPENAI_AGENT_MODEL") or os.getenv("LLM_MODEL") or "gpt-5.1").strip()


def modelo_barato() -> str:
    """Para tarefa acessória (resumo de memória, auditoria de conversa): o provedor pode não
    ter um 'mini'. Sem LLM_MODEL_BARATO definido, cai no modelo de texto — melhor pagar um
    pouco mais do que estourar 400 numa rotina de fundo que ninguém vê falhar."""
    return (os.getenv("LLM_MODEL_BARATO") or "").strip() or modelo_texto()


_modelo_texto = modelo_texto  # compat interno


def _base_openai_only() -> str | None:
    """Base para serviços que só a OpenAI oferece (áudio, embedding pago). Vazio = padrão
    da SDK, que já é a OpenAI."""
    return (os.getenv("OPENAI_BASE_URL") or "").strip() or None


def _api_key() -> str | None:
    return (os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip() or None


def _key_openai() -> str | None:
    return (os.getenv("OPENAI_API_KEY") or "").strip() or None


def registrar_uso(*, modelo: str, origem: str, entrada: int, saida: int,
                  duracao_ms: int, ok: bool, erro: str | None = None,
                  provedor: str | None = None, cache_hit: int = 0) -> None:
    """Grava uma linha de consumo. Silencioso em caso de falha, de propósito."""
    try:
        from sqlalchemy import text  # noqa: PLC0415

        # SyncSessionLocal vive no submódulo `session`; o pacote não o reexporta
        from core.database.session import SyncSessionLocal  # noqa: PLC0415

        with SyncSessionLocal() as s:
            s.execute(text("""
                INSERT INTO llm_usage
                    (id, criado_em, provedor, modelo, origem, tokens_entrada, tokens_saida,
                     tokens_total, custo_usd, duracao_ms, ok, erro, tokens_cache)
                VALUES (gen_random_uuid(), now(), :p, :m, :o, :e, :s, :t, :c, :d, :ok, :err,
                        :cache)
            """), {"p": provedor or ("custom" if _base_url() else "openai"),
                   "m": modelo, "o": origem[:120], "e": entrada, "s": saida,
                   "t": entrada + saida, "c": custo_usd(modelo, entrada, saida, cache_hit),
                   "d": duracao_ms, "ok": ok, "err": (erro or "")[:300] or None,
                   "cache": cache_hit})
            s.commit()
    except Exception as e:  # noqa: BLE001
        # WARNING, não DEBUG: telemetria que falha em silêncio vira telemetria inexistente,
        # e foi exatamente assim que o primeiro erro de import passou despercebido.
        logger.warning("llm_telemetria: não gravou (%s: %s)", type(e).__name__, str(e)[:140])


def _cache_do_usage(u: Any) -> int:
    """Tokens de prompt reaproveitados. A DeepSeek expõe `prompt_cache_hit_tokens`; a
    OpenAI, `prompt_tokens_details.cached_tokens`. Ausente = 0, nunca estimado."""
    if u is None:
        return 0
    v = getattr(u, "prompt_cache_hit_tokens", None)
    if isinstance(v, int):
        return v
    det = getattr(u, "prompt_tokens_details", None)
    return int(getattr(det, "cached_tokens", 0) or 0) if det is not None else 0


def _envolver(client: Any, origem: str, assincrono: bool) -> Any:
    """Envolve `chat.completions.create` para anotar o consumo de cada chamada."""
    original = client.chat.completions.create

    if assincrono:
        async def create(*a, **kw):
            t0 = time.perf_counter()
            modelo = kw.get("model") or "?"
            try:
                r = await original(*a, **kw)
            except Exception as e:  # noqa: BLE001
                registrar_uso(modelo=modelo, origem=origem, entrada=0, saida=0,
                              duracao_ms=int((time.perf_counter() - t0) * 1000),
                              ok=False, erro=f"{type(e).__name__}: {e}")
                raise
            u = getattr(r, "usage", None)
            registrar_uso(modelo=getattr(r, "model", modelo), origem=origem,
                          entrada=getattr(u, "prompt_tokens", 0) or 0,
                          saida=getattr(u, "completion_tokens", 0) or 0,
                          cache_hit=_cache_do_usage(u),
                          duracao_ms=int((time.perf_counter() - t0) * 1000), ok=True)
            return r
    else:
        def create(*a, **kw):
            t0 = time.perf_counter()
            modelo = kw.get("model") or "?"
            try:
                r = original(*a, **kw)
            except Exception as e:  # noqa: BLE001
                registrar_uso(modelo=modelo, origem=origem, entrada=0, saida=0,
                              duracao_ms=int((time.perf_counter() - t0) * 1000),
                              ok=False, erro=f"{type(e).__name__}: {e}")
                raise
            u = getattr(r, "usage", None)
            registrar_uso(modelo=getattr(r, "model", modelo), origem=origem,
                          entrada=getattr(u, "prompt_tokens", 0) or 0,
                          saida=getattr(u, "completion_tokens", 0) or 0,
                          cache_hit=_cache_do_usage(u),
                          duracao_ms=int((time.perf_counter() - t0) * 1000), ok=True)
            return r

    client.chat.completions.create = create
    return client


def novo_cliente(*, origem: str, timeout: float | None = None, sincrono: bool = False,
                 api_key: str | None = None, servico: str = "chat") -> Any:
    """Cria o cliente LLM da casa. `origem` identifica quem gastou — sem ela a telemetria
    diz quanto se gastou e não diz onde, que é metade da informação.

    `servico="audio"` ou `"embedding"` fica na OpenAI mesmo quando o chat migra: provedores
    de chat compatíveis (DeepSeek, por exemplo) NÃO têm rota de transcrição nem de
    embedding. Mandar áudio para lá devolveria 404 — erro confuso no lugar de um erro claro.
    """
    from openai import AsyncOpenAI, OpenAI  # noqa: PLC0415

    chave = api_key or (_api_key() if servico == "chat" else (_key_openai() or _api_key()))
    kw: dict[str, Any] = {"api_key": chave}
    base = _base_url() if servico == "chat" else _base_openai_only()
    if base:
        kw["base_url"] = base
    if timeout is not None:
        kw["timeout"] = timeout
    cli = OpenAI(**kw) if sincrono else AsyncOpenAI(**kw)
    return _envolver(cli, origem, assincrono=not sincrono)
