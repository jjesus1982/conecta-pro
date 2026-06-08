"""
Agente de atendimento WhatsApp — Fase A (COPILOTO).

Le o historico da conversa (cwi_message_log) e GERA uma sugestao de resposta.
NAO envia ao cliente. A sugestao e entregue como:
  - nota PRIVADA na conversa do Chatwoot (private=true; o cliente nao ve), e
  - uma linha em cwi_message_log com direction='drf' (rascunho), para rastreio.

Tudo controlado por env (nada hardcoded). Falhas nunca derrubam o webhook.
"""

import json
import logging
import os

import aiohttp
from sqlalchemy import text

from core.database import async_session_factory

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Você é o assistente de atendimento da Conecta Mais (conectamais.pro), empresa de Manaus/AM especializada em segurança e mão de obra para condomínios, empresas, indústrias e residências. Atende todos esses públicos, mas o foco principal são condomínios — você conversa muito com síndicos e administradoras.

O que a Conecta Mais oferece (duas grandes frentes, igualmente importantes):

1. Mão de obra:
- Agentes de portaria (portaria presencial)
- Auxiliar de serviços gerais
- Artífice e serviços afins

2. Segurança eletrônica e tecnologia:
- Portaria remota / monitoramento 24h (central de monitoramento, vídeo monitoramento, ronda 24h, app próprio)
- CFTV inteligente (câmeras com visão colorida noturna, detecção de intrusão, cerca/linha virtual, alta resolução)
- Controle de acesso (facial sem contato, biometria, QR Code, TAG/RFID veicular, controle de veículos)
- Automação de portões e cancelas (deslizante, pivotante, basculante, cancelas)
- Alarme (central monitorada via nuvem, tempo real)
- Manutenção dos sistemas
- Software de gestão condominial (app com financeiro, moradores, reservas, relatórios, portaria)

Carros-chefe (o que mais vendemos): agentes de portaria, portaria remota e segurança eletrônica.

Seu papel: atender com calor humano, empatia e profissionalismo — como um excelente atendente, nunca como um robô. Seja acolhedor e objetivo, respeitando o tempo de quem decide por muitos.

Sua missão é QUALIFICAR o lead e conduzir para uma visita técnica/comercial. Faça perguntas para entender bem antes de encaminhar:
- Que tipo de solução procura — mão de obra (portaria/serviços) ou segurança eletrônica (câmeras, controle de acesso, portaria remota)?
- É condomínio, empresa, indústria ou residência? Qual o porte (quantas unidades, portarias, acessos)?
- Já possui algum sistema ou portaria hoje? O que motiva a busca agora (segurança, custo, troca de fornecedor)?
- Qual a principal preocupação?

Filtre o máximo possível — quanto melhor você qualificar, melhor nossa equipe atende. Sobre contratos de manutenção, orçamentos e agentes de portaria, você pode e deve responder e aprofundar com perguntas, mas sem comprometer valores.

Regras invioláveis:
- NUNCA informe preços, prazos ou condições comerciais — dependem de avaliação técnica. Se perguntarem, explique que depende de uma visita e ofereça agendá-la.
- NUNCA invente informação técnica ou comercial. Se não souber um detalhe, diga que a equipe técnica esclarece na visita.
- Se perguntarem se você é um robô ou IA, assuma com naturalidade que é o assistente virtual da Conecta Mais e ofereça continuar ajudando ou falar com a equipe.
- Você trata apenas de assuntos da Conecta Mais e seus serviços. Se perguntarem algo fora disso, recuse educadamente e retome o atendimento.

Quando passar para um atendente humano: se o cliente pedir, demonstrar irritação ou urgência, relatar uma emergência de segurança, ou se a questão fugir do que você pode resolver — ofereça encaminhar para a equipe imediatamente.

Conduza sempre a conversa com gentileza e propósito: entender, qualificar, e levar à visita."""


def agent_enabled() -> bool:
    return os.getenv("AGENT_ENABLED", "false").lower() == "true"


async def gerar_resposta(conversation_id: int) -> str | None:
    """Le o historico da conversa e gera uma sugestao de resposta (NAO envia)."""
    if not os.getenv("OPENAI_API_KEY"):
        logger.warning("Agente: OPENAI_API_KEY ausente — sem geracao")
        return None

    model = os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini")
    max_history = int(os.getenv("AGENT_MAX_HISTORY", "20"))
    max_tokens = int(os.getenv("AGENT_MAX_TOKENS", "500"))

    try:
        # 1) Historico (apenas in/out reais; ignora drafts e vazios)
        async with async_session_factory() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT direction, content FROM cwi_message_log "
                        "WHERE chatwoot_conversation_id = :c "
                        "AND direction IN ('in','out') "
                        "AND content IS NOT NULL AND content <> '' "
                        "ORDER BY created_at DESC LIMIT :n"
                    ),
                    {"c": conversation_id, "n": max_history},
                )
            ).fetchall()

        if not rows:
            logger.info("Agente: conv=%s sem historico — nada a gerar", conversation_id)
            return None

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        for direction, content in reversed(rows):  # ordem cronologica
            role = "user" if direction == "in" else "assistant"
            messages.append({"role": role, "content": content})

        # 2) Chamada OpenAI (lazy import; chave vem do env)
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = AsyncOpenAI()
        resp = await client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.7,
        )
        texto = (resp.choices[0].message.content or "").strip()
        usage = getattr(resp, "usage", None)
        logger.info(
            "Agente: resposta gerada conv=%s model=%s tokens_in=%s tokens_out=%s",
            conversation_id,
            model,
            getattr(usage, "prompt_tokens", None),
            getattr(usage, "completion_tokens", None),
        )
        return texto or None
    except Exception as e:  # noqa: BLE001
        logger.error("Agente: falha ao gerar resposta conv=%s: %s", conversation_id, e)
        return None


async def _log_draft(conversation_id: int, phone: str | None, content: str, model: str) -> None:
    """Grava o rascunho em cwi_message_log (direction='drf') para revisao humana."""
    try:
        async with async_session_factory() as db:
            await db.execute(
                text(
                    "INSERT INTO cwi_message_log "
                    "(direction, phone_canonical, chatwoot_conversation_id, content, status) "
                    "VALUES ('drf', :phone, :conv, :content, :status)"
                ),
                {
                    "phone": phone,
                    "conv": conversation_id,
                    "content": content,
                    "status": f"agent:{model}",
                },
            )
            await db.commit()
    except Exception as e:  # noqa: BLE001
        logger.error("Agente: falha ao logar draft conv=%s: %s", conversation_id, e)


async def _post_private_note(conversation_id: int, content: str) -> bool:
    """Posta NOTA PRIVADA na conversa do Chatwoot (cliente NAO ve). Best-effort."""
    base = os.getenv("CHATWOOT_BASE_URL", "http://chatwoot-fazerai:3000").rstrip("/")
    account = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
    token = os.getenv("CHATWOOT_API_TOKEN", "")
    if not token:
        logger.warning("Agente: CHATWOOT_API_TOKEN ausente — nota privada nao postada")
        return False
    url = f"{base}/api/v1/accounts/{account}/conversations/{conversation_id}/messages"
    payload = {
        "content": f"🤖 *Sugestao do assistente (copiloto):*\n\n{content}",
        "message_type": "outgoing",
        "private": True,
    }
    headers = {"api_access_token": token, "Content-Type": "application/json"}
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                url,
                data=json.dumps(payload),
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp,
        ):
            if resp.status in (200, 201):
                return True
            body = (await resp.text())[:200]
            logger.error("Agente: nota privada falhou %s: %s", resp.status, body)
            return False
    except Exception as e:  # noqa: BLE001
        logger.error("Agente: excecao ao postar nota privada conv=%s: %s", conversation_id, e)
        return False


async def processar_incoming(conversation_id: int, phone: str | None = None) -> None:
    """Entrypoint do BackgroundTask: gera a sugestao e entrega em modo COPILOTO.

    NAO envia ao cliente — apenas nota privada (Chatwoot) + rascunho (cwi_message_log).
    """
    texto = await gerar_resposta(conversation_id)
    if not texto:
        return
    model = os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini")
    await _log_draft(conversation_id, phone, texto, model)
    await _post_private_note(conversation_id, texto)
