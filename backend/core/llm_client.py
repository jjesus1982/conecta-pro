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
    # O nome que a API DEVOLVE não é o que a gente ENVIA: mandamos "deepseek-v4-flash" e o
    # `usage.model` volta "deepseek-flash". O casamento é por prefixo
    # ("deepseek-flash".startswith("deepseek-v4-flash") é False), então nenhum preço casava e
    # `custo_usd` gravava NULL — 132.753 linhas, exatamente o período em que os US$ 20 sumiram.
    # O painel de custo ficou em branco justamente quando havia o que ver. (17/09/2026)
    "deepseek-flash": (0.22, 0.66),
    "deepseek-v4-pro": (0.66, 1.98),
    "deepseek-pro": (0.66, 1.98),
    "gpt-4.1": (2.00, 8.00),
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
    return round(novo / 1_000_000 * p[0] + cacheado / 1_000_000 * (pc or 0.0) + saida / 1_000_000 * p[1], 6)


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


def registrar_uso(
    *,
    modelo: str,
    origem: str,
    entrada: int,
    saida: int,
    duracao_ms: int,
    ok: bool,
    erro: str | None = None,
    provedor: str | None = None,
    cache_hit: int = 0,
) -> None:
    """Grava uma linha de consumo. Silencioso em caso de falha, de propósito."""
    try:
        from sqlalchemy import text  # noqa: PLC0415

        # SyncSessionLocal vive no submódulo `session`; o pacote não o reexporta
        from core.database.session import SyncSessionLocal  # noqa: PLC0415

        with SyncSessionLocal() as s:
            s.execute(
                text("""
                INSERT INTO llm_usage
                    (id, criado_em, provedor, modelo, origem, tokens_entrada, tokens_saida,
                     tokens_total, custo_usd, duracao_ms, ok, erro, tokens_cache)
                VALUES (gen_random_uuid(), now(), :p, :m, :o, :e, :s, :t, :c, :d, :ok, :err,
                        :cache)
            """),
                {
                    "p": provedor or ("custom" if _base_url() else "openai"),
                    "m": modelo,
                    "o": origem[:120],
                    "e": entrada,
                    "s": saida,
                    "t": entrada + saida,
                    "c": custo_usd(modelo, entrada, saida, cache_hit),
                    "d": duracao_ms,
                    "ok": ok,
                    "err": (erro or "")[:300] or None,
                    "cache": cache_hit,
                },
            )
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


# ── FALLBACK LOCAL ────────────────────────────────────────────────────────────────────
# Pedido do Jordan (07/09/2026): "os módulos que dependem de API deveriam buscar dentro do
# sistema". Existe um Ollama com `qwen3.5:4b` no volume `ollama_models` (container
# conecta-pro-ollama, mesma rede). Quando o provedor externo falha por CRÉDITO, COTA,
# AUTENTICAÇÃO ou CONEXÃO — não por erro de pedido — a mesma chamada é refeita no modelo
# local. Telemetria: provedor="ollama-local", origem "<origem>|local". Pedido inválido
# (400) NÃO cai no fallback: refazer um pedido errado noutro modelo só troca o erro.
# Medido antes de ligar: 04–06/09 foram 30.800 chamadas/dia falhando com 402.
_FALLBACK_CACHE: dict[str, Any] = {"ate": 0.0, "ok": False}
_FALLBACK_SAUDE_S = 300


def _fallback_base() -> str | None:
    # DESLIGADO por padrão (07/09/2026): medido com a máquina ociosa, qwen3.5:4b neste VPS
    # gera 0,32 token/s (25 tokens em 76 s; prompt de 6 tokens em 10,8 s) — um fallback que
    # demora 4 minutos por frase é pior que o erro. Fica pronto para ligar (LLM_FALLBACK_LOCAL=1)
    # quando houver modelo local viável (GPU, ou CPU dedicada; hipótese a testar: o limite
    # de 5 GiB do container com o modelo de 3,7 GiB).
    if (os.getenv("LLM_FALLBACK_LOCAL") or "0").strip().lower() in ("0", "false", "nao", "não"):
        return None
    return (os.getenv("LLM_FALLBACK_BASE_URL") or "http://conecta-pro-ollama:11434/v1").strip() or None


def modelo_fallback() -> str:
    return (os.getenv("LLM_FALLBACK_MODEL") or "qwen3.5:4b").strip()


def _erro_de_provedor(e: BaseException) -> bool:
    """Crédito/cota/auth/conexão/timeout: o provedor não serviu. 400 é pedido errado: não."""
    t = f"{type(e).__name__}: {e}".lower()
    if "400" in t or "badrequest" in t:
        return False
    return any(
        k in t
        for k in (
            "402",
            "insufficient",
            "credit",
            "quota",
            "billing",
            "payment",
            "401",
            "authentication",
            "429",
            "rate limit",
            "connection",
            "timeout",
            "timed out",
            "503",
            "502",
            "500",
        )
    )


def _fallback_disponivel() -> bool:
    """`GET /models` no Ollama, com cache de 5 min — não bater no modelo local a cada erro."""
    base = _fallback_base()
    if not base:
        return False
    agora = time.monotonic()
    if agora < _FALLBACK_CACHE["ate"]:
        return bool(_FALLBACK_CACHE["ok"])
    ok = False
    try:
        import urllib.request  # noqa: PLC0415

        with urllib.request.urlopen(base.rstrip("/") + "/models", timeout=3) as r:  # noqa: S310  # nosec B310 - LLM_BASE_URL local
            ok = r.status == 200 and modelo_fallback().split(":")[0] in r.read(4000).decode(errors="replace")
    except Exception as exc:  # noqa: BLE001
        logger.info("llm_fallback: local indisponível (%s: %s)", type(exc).__name__, str(exc)[:80])
    _FALLBACK_CACHE.update(ate=agora + _FALLBACK_SAUDE_S, ok=ok)
    return ok


def _cliente_fallback(assincrono: bool) -> Any:
    from openai import AsyncOpenAI, OpenAI  # noqa: PLC0415

    kw = {"api_key": "ollama", "base_url": _fallback_base(), "timeout": 240.0}
    return AsyncOpenAI(**kw) if assincrono else OpenAI(**kw)


def _kw_fallback(kw: dict) -> dict:
    """Mesmo pedido, modelo local; parâmetros de raciocínio da OpenAI não existem no Ollama."""
    novo = {k: v for k, v in kw.items() if k not in ("reasoning_effort", "max_completion_tokens", "store")}
    if "max_completion_tokens" in kw and "max_tokens" not in kw:
        novo["max_tokens"] = kw["max_completion_tokens"]
    novo["model"] = modelo_fallback()
    return novo


def _refazer_local(a, kw, origem, assincrono):
    """Corpo comum do fallback (sync/async): devolve corrotina ou resultado."""
    t1 = time.perf_counter()

    def _ok(r):
        u = getattr(r, "usage", None)
        registrar_uso(
            modelo=modelo_fallback(),
            origem=origem + "|local",
            entrada=getattr(u, "prompt_tokens", 0) or 0,
            saida=getattr(u, "completion_tokens", 0) or 0,
            duracao_ms=int((time.perf_counter() - t1) * 1000),
            ok=True,
            provedor="ollama-local",
        )
        return r

    def _falhou(e2):
        registrar_uso(
            modelo=modelo_fallback(),
            origem=origem + "|local",
            entrada=0,
            saida=0,
            duracao_ms=int((time.perf_counter() - t1) * 1000),
            ok=False,
            erro=f"{type(e2).__name__}: {e2}",
            provedor="ollama-local",
        )

    if assincrono:

        async def _run():
            try:
                return _ok(await _cliente_fallback(True).chat.completions.create(*a, **_kw_fallback(kw)))
            except Exception as e2:  # noqa: BLE001
                _falhou(e2)
                raise

        return _run()
    try:
        return _ok(_cliente_fallback(False).chat.completions.create(*a, **_kw_fallback(kw)))
    except Exception as e2:  # noqa: BLE001
        _falhou(e2)
        raise


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
                registrar_uso(
                    modelo=modelo,
                    origem=origem,
                    entrada=0,
                    saida=0,
                    duracao_ms=int((time.perf_counter() - t0) * 1000),
                    ok=False,
                    erro=f"{type(e).__name__}: {e}",
                )
                if not (_erro_de_provedor(e) and _fallback_disponivel()):
                    raise
                try:
                    return await _refazer_local(a, kw, origem, True)
                except Exception:  # noqa: BLE001 — o erro que vale é o do provedor principal
                    raise e
            u = getattr(r, "usage", None)
            registrar_uso(
                modelo=getattr(r, "model", modelo),
                origem=origem,
                entrada=getattr(u, "prompt_tokens", 0) or 0,
                saida=getattr(u, "completion_tokens", 0) or 0,
                cache_hit=_cache_do_usage(u),
                duracao_ms=int((time.perf_counter() - t0) * 1000),
                ok=True,
            )
            return r
    else:

        def create(*a, **kw):
            t0 = time.perf_counter()
            modelo = kw.get("model") or "?"
            try:
                r = original(*a, **kw)
            except Exception as e:  # noqa: BLE001
                registrar_uso(
                    modelo=modelo,
                    origem=origem,
                    entrada=0,
                    saida=0,
                    duracao_ms=int((time.perf_counter() - t0) * 1000),
                    ok=False,
                    erro=f"{type(e).__name__}: {e}",
                )
                if not (_erro_de_provedor(e) and _fallback_disponivel()):
                    raise
                try:
                    return _refazer_local(a, kw, origem, False)
                except Exception:  # noqa: BLE001
                    raise e
            u = getattr(r, "usage", None)
            registrar_uso(
                modelo=getattr(r, "model", modelo),
                origem=origem,
                entrada=getattr(u, "prompt_tokens", 0) or 0,
                saida=getattr(u, "completion_tokens", 0) or 0,
                cache_hit=_cache_do_usage(u),
                duracao_ms=int((time.perf_counter() - t0) * 1000),
                ok=True,
            )
            return r

    client.chat.completions.create = create
    return client


def novo_cliente(
    *,
    origem: str,
    timeout: float | None = None,
    sincrono: bool = False,
    api_key: str | None = None,
    servico: str = "chat",
) -> Any:
    """Cria o cliente LLM da casa. `origem` identifica quem gastou — sem ela a telemetria
    diz quanto se gastou e não diz onde, que é metade da informação.

    `servico="audio"` ou `"embedding"` fica na OpenAI mesmo quando o chat migra: provedores
    de chat compatíveis (DeepSeek, por exemplo) NÃO têm rota de transcrição nem de
    embedding. Mandar áudio para lá devolveria 404 — erro confuso no lugar de um erro claro.
    """
    from openai import AsyncOpenAI, OpenAI  # noqa: PLC0415

    # A chave do CHAMADOR só vale quando NÃO há provedor customizado. Um `api_key=` vindo
    # de settings é a chave do provedor ANTIGO: em 23/08 isso mandou a chave da OpenAI para
    # a DeepSeek e produziu 1.110 erros 401 em 3 horas, ~74 a cada 15 minutos, numa rotina
    # agendada que ninguém via falhar. Com base_url próprio, quem manda é LLM_API_KEY.
    if servico == "chat":
        chave = _api_key() if _base_url() else (api_key or _api_key())
    else:
        chave = api_key or _key_openai() or _api_key()
    kw: dict[str, Any] = {"api_key": chave}
    base = _base_url() if servico == "chat" else _base_openai_only()
    if base:
        kw["base_url"] = base
    if timeout is not None:
        kw["timeout"] = timeout
    cli = OpenAI(**kw) if sincrono else AsyncOpenAI(**kw)
    return _envolver(cli, origem, assincrono=not sincrono)
