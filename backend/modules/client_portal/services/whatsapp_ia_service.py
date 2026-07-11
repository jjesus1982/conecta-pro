"""
WhatsApp IA Service — Conecta Mais
Primeiro atendente automático via cascata LLM (OpenAI gpt-5 → Anthropic → frases prontas).
"""

import logging

logger = logging.getLogger(__name__)

MODEL_OPENAI = "gpt-5"
MODEL_ANTHROPIC = "claude-sonnet-4-6"  # fallback opcional (só se ANTHROPIC_API_KEY definida)

# Palavras que disparam escalada para humano (INV-6)
PALAVRAS_ESCALADA = [
    "urgente",
    "emergência",
    "emergencia",
    "preço",
    "preco",
    "valor",
    "orçamento",
    "orcamento",
    "contrato",
    "cancelar",
    "cancelamento",
    "problema grave",
    "acidente",
    "policia",
    "polícia",
    "bombeiro",
    "morte",
    "roubo",
    "invasão",
    "invasao",
]

SYSTEM_PROMPT = """Você é um atendente virtual da Conecta Mais — Segurança e Tecnologia,
empresa especializada em portaria presencial, portaria remota, CFTV e controle de acesso.

REGRAS OBRIGATÓRIAS:
1. Seja cordial, profissional e objetivo
2. NUNCA confirme preços, valores ou condições comerciais
3. NUNCA feche contratos ou faça promessas comerciais
4. Para solicitações de orçamento → informe que um consultor entrará em contato
5. Para emergências operacionais → peça para ligar no 0800 880 4414 opção 1
6. Responda em português brasileiro, de forma clara e concisa
7. Se não souber responder → diga que vai encaminhar para a equipe responsável

SERVIÇOS OFERECIDOS:
- Portaria presencial (agente de portaria no local)
- Portaria remota (monitoramento digital)
- CFTV (câmeras e monitoramento)
- Controle de acesso (cancelas, portões, biometria)

HORÁRIO COMERCIAL: Segunda a Sexta, 8h às 18h (horário de Manaus, AM)

Se a mensagem contiver pedido de preço, valor ou orçamento, responda:
"Vou encaminhar sua solicitação para nosso consultor comercial que entrará em contato em breve."

Seja breve — respostas de no máximo 3 parágrafos curtos."""


def deve_escalar(mensagem: str) -> bool:
    """Verifica se a mensagem deve ser escalada para humano."""
    mensagem_lower = mensagem.lower()
    return any(palavra in mensagem_lower for palavra in PALAVRAS_ESCALADA)


def responder_com_ia(
    mensagem: str,
    historico: list[dict] | None = None,
    cliente_nome: str = "Cliente",
) -> dict:
    """
    Gera resposta automática via cascata LLM (OpenAI → Anthropic → frases prontas).

    Returns:
        dict com keys: resposta (str), escalar (bool), motivo_escalada (str|None)
    """
    # INV-5/6: verificar palavras de escalada antes de chamar IA
    if deve_escalar(mensagem):
        motivo = next((p for p in PALAVRAS_ESCALADA if p in mensagem.lower()), "keyword")
        logger.info("WhatsApp IA: escalando para humano — keyword: %s", motivo)
        return {
            "resposta": (
                "Olá! Vou encaminhar sua mensagem para nossa equipe especializada "
                "que entrará em contato em breve. "
                "Obrigado por contatar a Conecta Mais!"
            ),
            "escalar": True,
            "motivo_escalada": motivo,
        }

    try:
        from core.llm_cascade import chat as llm_chat

        # Montar histórico (últimas 10 mensagens — INV-7)
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if historico:
            for msg in historico[-10:]:
                messages.append(
                    {
                        "role": msg.get("role", "user"),
                        "content": msg.get("content", ""),
                    }
                )
        messages.append({"role": "user", "content": mensagem})

        resposta = llm_chat(
            messages=messages,
            model_openai=MODEL_OPENAI,
            model_anthropic=MODEL_ANTHROPIC,
            max_tokens=400,
        )

        if not resposta:
            logger.warning("WhatsApp IA: nenhum provedor LLM disponível — usando fallback")
            return _fallback()

        return {"resposta": resposta, "escalar": False, "motivo_escalada": None}

    except Exception as exc:
        logger.error("WhatsApp IA: erro na cascata LLM: %s", exc)
        return _fallback()


def _fallback() -> dict:
    return {
        "resposta": (
            "Olá! Recebemos sua mensagem. Nossa equipe entrará em contato em breve. "
            "Obrigado por contatar a Conecta Mais!"
        ),
        "escalar": False,
        "motivo_escalada": None,
    }
