"""
Copywriter Agent — Conecta Marketing AI (F2)

Agente de geração de conteúdo na voz da marca Conecta Mais. Reaproveita o
LLMProvider canônico (modules/ai/conversation) com fallback. Human-in-the-loop:
SEMPRE retorna RASCUNHOS para aprovação humana — nunca publica nada.

Formatos suportados: post de Instagram/Facebook, roteiro de Reels, anúncio
(Meta/Google), e-mail e mensagem de WhatsApp.
"""

from __future__ import annotations

import json
import logging
import re

from modules.ai.conversation.services.llm_provider import LLMProvider

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Brand voice — fonte da verdade (espelha /modulos/marketing/brand-voice).
# ---------------------------------------------------------------------------
BRAND_VOICE = """\
MARCA: Conecta Mais — segurança patrimonial (vigilância, portaria remota,
segurança eletrônica e monitoramento) em Manaus/AM.
SLOGAN: "Conecta Mais — Segurança inteligente para quem valoriza o patrimônio".

PERSONALIDADE:
- Profissional: transmite expertise em segurança patrimonial.
- Confiável: dados e resultados comprovados, não promessas.
- Tecnológico: inovação com portaria remota e monitoramento inteligente.
- Próximo: atendimento humanizado, acessível e transparente.

TOM DE VOZ:
- Formal mas acessível — sem jargões excessivos.
- Direto e objetivo — o síndico não tem tempo.
- Orientado a solução — "como resolver", não "o que vender".
- Empático — entendemos as dores do gestor condominial.

PÚBLICO PRINCIPAL: síndicos, gestores prediais e administradoras de condomínios.

NUNCA FAZER:
- Linguagem agressiva ou alarmista.
- Promessas de "segurança 100%".
- Comparação direta com concorrentes.
- Termos técnicos sem explicação.
- Informalidade excessiva (gírias, emojis demais).

FOCO DE CAMPANHA (serviços prioritários — sempre puxar para um destes):
- Portaria remota, portaria híbrida, portaria inteligente, portaria virtual e variações/derivados
  desses nomes. É o carro-chefe da captação atual.

CONCORRENTES EM MANAUS (para posicionamento — NÃO citar pelo nome nos anúncios):
- Atende Portaria (narrativa "nacional", economia "até 50%", prova social de ~800 condomínios, Selo ABF),
  Servis e Porter.
- DIFERENCIAIS da Conecta Mais a explorar: presença e atendimento LOCAL de Manaus (vs. narrativa
  nacional), prova social regional (condomínios daqui), tempo de resposta rápido, integração com
  segurança eletrônica e monitoramento, e foco no decisor (síndico/administradora) com linguagem
  de gestão e responsabilidade. Diferencie pelo valor local — sem atacar concorrente nominalmente.
"""


# ---------------------------------------------------------------------------
# Formatos: cada um define rótulo + instruções específicas (estrutura/limites).
# ---------------------------------------------------------------------------
FORMATOS: dict[str, dict] = {
    "instagram_post": {
        "label": "Post de Instagram",
        "instrucoes": (
            "Legenda de post para feed do Instagram. Gancho forte na 1ª linha, "
            "corpo curto e escaneável, 1 CTA claro ao final e 4-6 hashtags relevantes "
            "(segurança, condomínio, Manaus). No máximo 1-2 emojis, com sobriedade."
        ),
    },
    "facebook_post": {
        "label": "Post de Facebook",
        "instrucoes": (
            "Post para Facebook, um pouco mais explicativo que o Instagram. "
            "Texto que gera confiança, com CTA para falar no WhatsApp."
        ),
    },
    "reel_roteiro": {
        "label": "Roteiro de Reels",
        "instrucoes": (
            "Roteiro de vídeo curto (Reels/TikTok, 20-40s). Estruture em cenas: "
            "[GANCHO 0-3s], [PROBLEMA], [SOLUÇÃO Conecta Mais], [PROVA/CONFIANÇA], "
            "[CTA]. Inclua sugestão de legenda na tela e narração."
        ),
    },
    "anuncio_meta": {
        "label": "Anúncio Meta (Facebook/Instagram Ads)",
        "instrucoes": (
            "Anúncio pago para Meta Ads. Entregue: 3 headlines (até 40 caracteres), "
            "texto principal (até 125 caracteres antes do 'ver mais'), descrição e CTA. "
            "Foco em Click-to-WhatsApp. Respeite as políticas de anúncio da Meta "
            "(sem promessas absolutas, sem alarmismo)."
        ),
    },
    "anuncio_google": {
        "label": "Anúncio Google (Search)",
        "instrucoes": (
            "Anúncio de busca do Google Ads. Entregue: 3 headlines (até 30 caracteres "
            "cada) e 2 descrições (até 90 caracteres cada). Inclua a palavra-chave alvo "
            "e a localização (Manaus) quando fizer sentido."
        ),
    },
    "email": {
        "label": "E-mail",
        "instrucoes": (
            "E-mail de prospecção/relacionamento. Entregue: assunto (até 60 caracteres), "
            "pré-cabeçalho e corpo curto (3-5 parágrafos curtos) com 1 CTA. Tom consultivo."
        ),
    },
    "whatsapp": {
        "label": "Mensagem de WhatsApp",
        "instrucoes": (
            "Mensagem curta de WhatsApp (broadcast com opt-in ou follow-up). "
            "Pessoal, direta, 1 CTA. Sem parecer spam. Máx ~3 linhas."
        ),
    },
}


def formatos_suportados() -> list[dict]:
    return [{"id": k, "label": v["label"]} for k, v in FORMATOS.items()]


def _montar_system_prompt(formato_cfg: dict, n_variacoes: int) -> str:
    return (
        BRAND_VOICE + "\n\nVOCÊ É o copywriter sênior da Conecta Mais. Escreva em português do Brasil, "
        "sempre na voz da marca acima.\n\n"
        f"FORMATO PEDIDO: {formato_cfg['label']}\n"
        f"INSTRUÇÕES DO FORMATO: {formato_cfg['instrucoes']}\n\n"
        f"Gere {n_variacoes} variação(ões) distintas e de alta qualidade.\n"
        "RESPONDA APENAS com JSON válido, sem texto fora do JSON, no formato:\n"
        '{"variacoes": [{"titulo": "<rótulo curto da variação>", '
        '"conteudo": "<o texto pronto para uso, com quebras de linha>", '
        '"observacao": "<dica de uso ou racional, 1 linha>"}]}'
    )


def _extrair_json(texto: str) -> dict | None:
    """Extrai o primeiro objeto JSON do texto do LLM (tolerante a cercas/ruído)."""
    if not texto:
        return None
    t = texto.strip()
    t = re.sub(r"^```(?:json)?|```$", "", t, flags=re.MULTILINE).strip()
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


async def gerar_copy(
    formato: str,
    briefing: str,
    objetivo: str | None = None,
    publico: str | None = None,
    n_variacoes: int = 3,
    temperatura: float = 0.8,
) -> dict:
    """
    Gera rascunhos de conteúdo na voz da marca (human-in-the-loop).

    Retorna {ok, formato, variacoes:[{titulo,conteudo,observacao}], modelo, fallback}.
    """
    formato_cfg = FORMATOS.get(formato)
    if not formato_cfg:
        return {"ok": False, "erro": f"Formato '{formato}' inválido", "formatos": formatos_suportados()}

    n_variacoes = max(1, min(int(n_variacoes or 3), 5))

    brief_user = f"BRIEFING DA PEÇA:\n{briefing.strip()}"
    if objetivo:
        brief_user += f"\n\nOBJETIVO: {objetivo.strip()}"
    if publico:
        brief_user += f"\n\nPÚBLICO-ALVO ESPECÍFICO: {publico.strip()}"

    system_prompt = _montar_system_prompt(formato_cfg, n_variacoes)

    provider = LLMProvider()
    resp = await provider.generate(
        messages=[{"role": "user", "content": brief_user}],
        system_prompt=system_prompt,
        max_tokens=2000,
        temperature=temperatura,
    )

    parsed = _extrair_json(resp.content)
    if parsed and isinstance(parsed.get("variacoes"), list) and parsed["variacoes"]:
        variacoes = [
            {
                "titulo": str(v.get("titulo") or f"Variação {i + 1}"),
                "conteudo": str(v.get("conteudo") or "").strip(),
                "observacao": str(v.get("observacao") or "").strip(),
            }
            for i, v in enumerate(parsed["variacoes"])
            if str(v.get("conteudo") or "").strip()
        ]
    else:
        # Fallback: devolve o texto cru como 1 variação (não perde o trabalho do modelo).
        variacoes = [{"titulo": "Rascunho", "conteudo": resp.content.strip(), "observacao": ""}]

    fallback = "local" in (resp.model or "").lower()
    return {
        "ok": True,
        "formato": formato,
        "formato_label": formato_cfg["label"],
        "variacoes": variacoes,
        "modelo": resp.model,
        "fallback": fallback,
        "status": "rascunho",  # human-in-the-loop: nada é publicado
    }
