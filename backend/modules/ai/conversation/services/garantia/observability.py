"""Fase 5.2a.3 — Camada de Garantia: OBSERVABILIDADE das chamadas de LLM.

Reusa o Sentry já ativo em `main_production.py` (`sentry_sdk.start_span`) — SEM
dependência nova. `sentry_sdk.start_span` já é seguro mesmo sem
`sentry_sdk.init()` ter sido chamado (vira um span órfão, nunca transmitido,
nunca levanta) — mas aqui envolvemos tudo em try/except mesmo assim, pra
cobrir o caso limite de o pacote `sentry_sdk` nem estar instalado/importável
no processo que chamar isto (ex.: script standalone de teste): nesse caso é
NO-OP puro, o call site nem percebe.
"""
from __future__ import annotations

import contextlib
import logging
import time
from collections.abc import Iterator

logger = logging.getLogger(__name__)


@contextlib.contextmanager
def llm_span(nome: str, **attrs) -> Iterator[None]:
    """Abre um span Sentry `gen_ai.<nome>` e seta `attrs` (modelo, tokens,
    provider, origem, latencia_ms, ...) como `set_data`. Ao sair, registra
    `latencia_ms_total` medido aqui mesmo (independe do call site informar).

    Nunca levanta: qualquer problema com o Sentry (ausente, não inicializado,
    API incompatível) faz o corpo do `with` rodar normalmente, sem span.
    """
    inicio = time.monotonic()
    span_cm = None
    span = None
    try:
        import sentry_sdk

        span_cm = sentry_sdk.start_span(op=f"gen_ai.{nome}", description=nome)
        span = span_cm.__enter__()
        for chave, valor in attrs.items():
            try:
                span.set_data(chave, valor)
            except Exception:  # noqa: BLE001 — attr não serializável etc.
                pass
    except Exception as e:  # noqa: BLE001 — sentry ausente/quebrado: segue sem span
        logger.debug("llm_span(%s): Sentry indisponível (%s) — seguindo sem span", nome, e)
        span_cm = None
        span = None

    try:
        yield
    finally:
        if span is not None:
            try:
                span.set_data("latencia_ms_total", int((time.monotonic() - inicio) * 1000))
            except Exception:  # noqa: BLE001
                pass
        if span_cm is not None:
            try:
                span_cm.__exit__(None, None, None)
            except Exception:  # noqa: BLE001
                pass


# ─────────────────────────────────────────────────────────────────────────────
# TESTE (padrão 5.1: sem pytest, `python observability.py`, só asserts)
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # 1) Sentry instalado mas NÃO inicializado (estado real de um script solto)
    ok_sem_erro = True
    try:
        with llm_span("hermes", origem="executivo", modelo="gpt-5", tokens=123):
            resultado = 1 + 1
        assert resultado == 2
    except Exception as e:  # noqa: BLE001
        ok_sem_erro = False
        print("FALHOU (sem init):", e)
    assert ok_sem_erro, "llm_span não deveria levantar com Sentry não-inicializado"
    print("TESTE 1 (Sentry não inicializado) PASS")

    # 2) Sentry inicializado (dsn=None só pra exercitar o client de verdade)
    ok_com_init = True
    try:
        import sentry_sdk

        sentry_sdk.init(dsn=None)
        with llm_span("consultor", origem="cfo", modelo="gpt-5-mini", provider="openai"):
            resultado = 2 + 2
        assert resultado == 4
    except Exception as e:  # noqa: BLE001
        ok_com_init = False
        print("FALHOU (com init):", e)
    assert ok_com_init, "llm_span não deveria levantar com Sentry inicializado"
    print("TESTE 2 (Sentry inicializado) PASS")

    # 3) exceção DENTRO do bloco `with` deve propagar normalmente (span não a engole)
    propagou = False
    try:
        with llm_span("erro_proposital"):
            raise ValueError("boom")
    except ValueError:
        propagou = True
    assert propagou, "exceção do corpo do with deveria propagar, não ser engolida pelo span"
    print("TESTE 3 (exceção do corpo propaga) PASS")

    print("\nTODOS OS TESTES DE observability.py PASSARAM")
