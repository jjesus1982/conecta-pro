"""Fase 5.3 — Redator: o cérebro SÓ escreve o texto de uma condição já detectada.

A regra (SQL) já decidiu o disparo/destinatário/severidade. Aqui o consultor_hub
redige 1-2 frases no tom certo. Groundedness: os NÚMEROS do template têm que
aparecer no texto do LLM, senão cai no template determinístico. LLM off → template.
NUNCA tool-calling aqui (é só redação; origem != 'executivo' p/ não acionar Hermes).
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_SYS = (
    "Você redige alertas curtos e diretos para um ERP de segurança patrimonial. "
    "Escreva NO MÁXIMO 2 frases, tom objetivo, português do Brasil. Use EXATAMENTE "
    "os números fornecidos — não invente nem arredonde. Não proponha ações; só informe."
)


def _numeros(texto: str) -> set[str]:
    """Tokens numéricos 'de conteúdo' (ignora números <=0 dígitos triviais)."""
    return set(re.findall(r"\d[\d.,]*", texto))


async def redigir(regra, achado, *, gerar_fn=None):
    tpl_title, tpl_body = regra.template(achado.dados)
    # Severidade dinâmica: pendência das reviews T1/T2 — o achado pode carregar
    # uma severidade per-instância (ex. vencida=critico vs a vencer=atencao) que
    # sobrescreve a severidade estática da regra.
    severidade = achado.dados.get("severidade", regra.severidade)
    if gerar_fn is None:
        from modules.ai.conversation.services.consultor_hub import gerar as gerar_fn  # noqa: N806

    try:
        prompt = (
            f"Condição detectada (família {regra.familia}, severidade {severidade}). "
            f"Texto-base a reescrever no seu tom: \"{tpl_body}\". "
            f"Dados exatos: {achado.dados}."
        )
        texto, _meta = await gerar_fn(
            messages=[{"role": "user", "content": prompt}],
            system_prompt=_SYS, max_tokens=180, temperature=0.2,
            origem=None, direct=True,
        )
        texto = (texto or "").strip()
        # Groundedness: todos os números do template devem estar no texto do LLM.
        alvo = _numeros(tpl_body)
        if texto and alvo.issubset(_numeros(texto)):
            return tpl_title, texto
        logger.info("[proativo] redator sem groundedness (%s) → template", regra.nome)
    except Exception as exc:  # noqa: BLE001 — degradação graciosa
        logger.info("[proativo] redator LLM off (%s: %s) → template", regra.nome, exc)
    return tpl_title, tpl_body


if __name__ == "__main__":
    import asyncio

    from modules.notifications.proativo.regras import REGISTRY, Achado

    async def main() -> None:
        regra = REGISTRY["posto_descoberto"]
        achado = Achado(correlation_id="posto_descoberto:x",
                        dados={"post_id": "x", "posto": "Portaria Central",
                               "faltam": 2, "req": 3, "cur": 1})
        tpl_title, tpl_body = regra.template(achado.dados)

        # 1) LLM "bom" cita o número → usa o texto do LLM no body
        async def gerar_ok(**kw):
            return ("O posto Portaria Central está com 2 vaga(s) descoberta(s); acione cobertura.", {})
        title, body = await redigir(regra, achado, gerar_fn=gerar_ok)
        assert title == tpl_title            # título sempre determinístico
        assert "2" in body                   # groundedness: número presente
        assert "descoberta" in body.lower()

        # 2) LLM "alucina" (não cita o número) → cai no template
        async def gerar_ruim(**kw):
            return ("Tudo certo por aqui, sem novidades.", {})
        _, body2 = await redigir(regra, achado, gerar_fn=gerar_ruim)
        assert body2 == tpl_body

        # 3) LLM explode → fallback template
        async def gerar_boom(**kw):
            raise RuntimeError("sem OPENAI_API_KEY")
        _, body3 = await redigir(regra, achado, gerar_fn=gerar_boom)
        assert body3 == tpl_body

        # 4) severidade dinâmica: achado.dados["severidade"] sobrescreve regra.severidade
        #    (usa certidao_vencendo, que carrega severidade per-achado)
        regra_cert = REGISTRY["certidao_vencendo"]
        achado_vencida = Achado(
            correlation_id="certidao:y:2026-01-01",
            dados={"cert_id": "y", "nome": "CND Federal", "dias": -5,
                   "expiry": "2026-01-01", "vencida": True, "severidade": "critico"},
        )
        assert regra_cert.severidade == "atencao"  # estática da regra
        capturado = {}

        async def gerar_captura(**kw):
            capturado["prompt"] = kw["messages"][0]["content"]
            raise RuntimeError("força fallback p/ não desviar do teste de severidade")
        await redigir(regra_cert, achado_vencida, gerar_fn=gerar_captura)
        assert "severidade critico" in capturado["prompt"], capturado["prompt"]
        assert "severidade atencao" not in capturado["prompt"]

        print("OK redator — groundedness + fallback + severidade dinâmica")

    asyncio.run(main())
