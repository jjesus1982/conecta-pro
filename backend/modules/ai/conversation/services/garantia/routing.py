"""Fase 5.2a.3 — Camada de Garantia: ROTEAMENTO de custo (tier -> modelo).

Reusa a heurística de TAMANHO já existente em `core.llm_cascade._tier_por_heuristica`
como PISO (prompt grande sobe o tier de partida), e soma uma regra de DOMÍNIO:
origem C-level/financeira/jurídica, ou texto que cita dinheiro/legal, força a
tier 'pesada' — não economizamos em cima de decisão de dinheiro ou risco
jurídico, mesmo que a pergunta em si seja curta ("pode pagar esse boleto?").
"""
from __future__ import annotations

import re

from core.llm_cascade import _tier_por_heuristica

# Origens onde o "custo de errar" é alto o bastante pra sempre ir na pesada,
# independente do tamanho do prompt.
_ORIGENS_PESADAS = {"cfo", "juridico", "ceo", "executivo"}

# Dinheiro/legal no TEXTO da pergunta também força a pesada, mesmo vindo de uma
# origem "leve" (ex.: o Consultor GED sendo perguntado sobre um contrato).
_RE_DINHEIRO_LEGAL = re.compile(r"pagar|pix|folha|processo|contrato|imposto|r\$", re.IGNORECASE)

# Mapa tier -> modelo OpenAI. 'leve' e 'media' caem no MESMO modelo de propósito
# ('gpt-5-mini') — o gpt-5-nano é fraco demais pra síntese de resposta ao
# gestor; só 'pesada' sobe pro gpt-5.
_TIER_MODELO = {
    "leve": "gpt-5-mini",
    "media": "gpt-5-mini",
    "pesada": "gpt-5",
}


def _texto_das_mensagens(messages: list[dict]) -> str:
    return " ".join(str(m.get("content", "")) for m in (messages or []))


def modelo_por_tier(origem: str | None, messages: list[dict]) -> str:
    """Escolhe o modelo OpenAI pela complexidade: piso por TAMANHO (herdado de
    `llm_cascade`) + força 'pesada' por DOMÍNIO (origem C-level/financeira/
    jurídica, ou o texto citando dinheiro/legal). Retorna o id do modelo."""
    tier = _tier_por_heuristica(messages or [], tier_min="media", json_mode=False)

    if (origem or "").strip().lower() in _ORIGENS_PESADAS:
        tier = "pesada"
    elif _RE_DINHEIRO_LEGAL.search(_texto_das_mensagens(messages)):
        tier = "pesada"

    return _TIER_MODELO.get(tier, _TIER_MODELO["pesada"])


# ─────────────────────────────────────────────────────────────────────────────
# TESTE (padrão 5.1: sem pytest, `python routing.py`, só asserts). Precisa
# rodar com `core` no PYTHONPATH (raiz do backend) — dentro do container ou
# com `cd backend && python -m modules.ai.conversation.services.garantia.routing`.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    msgs_trivial = [{"role": "user", "content": "oi"}]
    msgs_dinheiro = [{"role": "user", "content": "pode pagar esse boleto hoje?"}]

    # 1) origem executiva força pesada, mesmo com prompt trivial
    m1 = modelo_por_tier("executivo", msgs_trivial)
    assert m1 == "gpt-5", f"esperado gpt-5, veio {m1}"
    print("TESTE 1 (origem=executivo) PASS:", m1)

    # 2) origem cfo força pesada
    m2 = modelo_por_tier("cfo", msgs_trivial)
    assert m2 == "gpt-5", f"esperado gpt-5, veio {m2}"
    print("TESTE 2 (origem=cfo) PASS:", m2)

    # 3) origem juridico força pesada
    m3 = modelo_por_tier("juridico", msgs_trivial)
    assert m3 == "gpt-5", f"esperado gpt-5, veio {m3}"
    print("TESTE 3 (origem=juridico) PASS:", m3)

    # 4) sem origem + pergunta trivial curta -> piso 'media' -> gpt-5-mini
    m4 = modelo_por_tier(None, msgs_trivial)
    assert m4 == "gpt-5-mini", f"esperado gpt-5-mini, veio {m4}"
    print("TESTE 4 (origem=None, trivial) PASS:", m4)

    # 5) origem "leve" (ex. ged) mas o TEXTO cita dinheiro -> força pesada mesmo assim
    m5 = modelo_por_tier("ged", msgs_dinheiro)
    assert m5 == "gpt-5", f"esperado gpt-5 (texto cita dinheiro), veio {m5}"
    print("TESTE 5 (texto com 'pagar' força pesada) PASS:", m5)

    # 6) prompt GIGANTE (>16000 chars) sobe pesada mesmo sem domínio/origem
    msgs_grande = [{"role": "user", "content": "x" * 17000}]
    m6 = modelo_por_tier(None, msgs_grande)
    assert m6 == "gpt-5", f"esperado gpt-5 (heurística de tamanho), veio {m6}"
    print("TESTE 6 (heurística de tamanho) PASS:", m6)

    print("\nTODOS OS TESTES DE routing.py PASSARAM")
