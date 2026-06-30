"""
Estrategista Agent — Conecta Marketing AI (F2)

Agente de estratégia de marketing. A partir de um OBJETIVO em linguagem natural,
gera um plano de campanha + calendário editorial na voz/contexto da Conecta Mais.
Reaproveita o LLMProvider canônico. Human-in-the-loop: entrega um PLANO para você
aprovar/ajustar — não executa nada.
"""

from __future__ import annotations

import json
import logging
import re

from modules.ai.conversation.services.llm_provider import LLMProvider
from modules.crm.services.copywriter_agent import BRAND_VOICE

logger = logging.getLogger(__name__)


def _system_prompt(dias: int) -> str:
    return (
        BRAND_VOICE + "\n\nVOCÊ É o estrategista de marketing sênior da Conecta Mais. Monte um plano de "
        "marketing PRÁTICO e acionável para uma empresa de segurança patrimonial em Manaus/AM "
        "(portaria remota, vigilância, segurança eletrônica, monitoramento), focada em síndicos "
        "e gestores prediais. Seja específico ao mercado local e ao público.\n\n"
        f"O calendário deve cobrir {dias} dias.\n"
        "RESPONDA APENAS com JSON válido (sem texto fora do JSON), no formato:\n"
        "{\n"
        '  "resumo": "<2-3 linhas com a tese da estratégia>",\n'
        '  "publico_alvo": ["<persona 1>", "<persona 2>"],\n'
        '  "proposta_valor": "<frase de posicionamento>",\n'
        '  "canais": [{"canal": "<ex: Instagram>", "objetivo": "<para que serve>", '
        '"alocacao_pct": <0-100>}],\n'
        '  "calendario": [{"dia": <n>, "canal": "<canal>", "formato": "<ex: Post, Reels, Anúncio>", '
        '"tema": "<tema do conteúdo>", "cta": "<chamada para ação>"}],\n'
        '  "kpis": ["<métrica 1>", "<métrica 2>"],\n'
        '  "proximos_passos": ["<ação 1>", "<ação 2>"]\n'
        "}\n"
        "A soma de alocacao_pct dos canais deve dar ~100. O calendário deve ter de 6 a 12 itens "
        "bem distribuídos no período."
    )


def _extrair_json(texto: str) -> dict | None:
    if not texto:
        return None
    t = re.sub(r"^```(?:json)?|```$", "", texto.strip(), flags=re.MULTILINE).strip()
    try:
        return json.loads(t)
    except Exception:  # noqa: BLE001
        m = re.search(r"\{.*\}", t, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:  # noqa: BLE001
                return None
    return None


async def gerar_plano(
    objetivo: str,
    periodo_dias: int = 30,
    orcamento: str | None = None,
    canais_preferidos: str | None = None,
) -> dict:
    """Gera um plano de campanha + calendário editorial a partir de um objetivo."""
    periodo_dias = max(7, min(int(periodo_dias or 30), 90))
    user = f"OBJETIVO: {objetivo.strip()}\nPERÍODO: {periodo_dias} dias"
    if orcamento:
        user += f"\nORÇAMENTO: {orcamento.strip()}"
    if canais_preferidos:
        user += f"\nCANAIS PREFERIDOS: {canais_preferidos.strip()}"

    provider = LLMProvider()
    resp = await provider.generate(
        messages=[{"role": "user", "content": user}],
        system_prompt=_system_prompt(periodo_dias),
        max_tokens=8000,
        temperature=0.7,
    )

    plano = _extrair_json(resp.content)
    fallback = "local" in (resp.model or "").lower()
    if not plano:
        return {
            "ok": True,
            "fallback": True,
            "modelo": resp.model,
            "plano": {
                "resumo": resp.content.strip(),
                "publico_alvo": [],
                "canais": [],
                "calendario": [],
                "kpis": [],
                "proximos_passos": [],
            },
            "status": "rascunho",
        }
    return {
        "ok": True,
        "fallback": fallback,
        "modelo": resp.model,
        "objetivo": objetivo,
        "periodo_dias": periodo_dias,
        "plano": plano,
        "status": "rascunho",
    }
