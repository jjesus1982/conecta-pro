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

Conduza sempre a conversa com gentileza e propósito: entender, qualificar, e levar à visita.

Ferramentas disponíveis: quando o cliente fornecer ou mencionar um CNPJ, use consultar_cnpj para validar e obter os dados oficiais (razão social, situação cadastral, município/UF, CNAE) — NUNCA invente esses dados, use apenas o que a ferramenta retornar. Em seguida use buscar_cliente para verificar se esse CNPJ já é cliente da Conecta Mais: se for (existe:true), acolha a pessoa como CLIENTE já atendido (tom de relacionamento e cuidado, não de prospecção); se não for, siga qualificando como novo lead. Se uma ferramenta retornar erro, não trave nem mencione detalhes técnicos — siga o atendimento normalmente e, se precisar, peça o dado novamente com gentileza. Todos os guard-rails acima continuam valendo (nunca preços, nunca inventar)."""


def agent_enabled() -> bool:
    return os.getenv("AGENT_ENABLED", "false").lower() == "true"


# === TOOLS (function calling — apenas LEITURA) ===

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "consultar_cnpj",
            "description": (
                "Consulta dados públicos de um CNPJ na Receita Federal (via BrasilAPI): "
                "razão social, nome fantasia, situação cadastral, município/UF e CNAE principal. "
                "Use quando o cliente fornecer ou mencionar um CNPJ."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cnpj": {"type": "string", "description": "CNPJ com ou sem máscara (14 dígitos)"},
                },
                "required": ["cnpj"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "buscar_cliente",
            "description": (
                "Verifica se um CNPJ já é cliente da Conecta Mais na base interna. "
                "Retorna existe:true com nome e status se já for cliente; existe:false se não. "
                "Use após obter o CNPJ para adaptar o atendimento."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cnpj": {"type": "string", "description": "CNPJ com ou sem máscara"},
                },
                "required": ["cnpj"],
            },
        },
    },
]


async def _tool_consultar_cnpj(cnpj: str) -> dict:
    """Consulta CNPJ na BrasilAPI (reusa o cliente existente: cache + circuit breaker). Nunca estoura."""
    try:
        from modules.integrations.brasilapi.client import BrasilAPIClient  # noqa: PLC0415
        from modules.integrations.brasilapi.exceptions import (  # noqa: PLC0415
            BrasilAPIInvalidFormatError,
            BrasilAPINotFoundError,
        )

        try:
            resp, _cached = await BrasilAPIClient().get_cnpj(cnpj)
        except (BrasilAPINotFoundError, BrasilAPIInvalidFormatError):
            return {"erro": "CNPJ não encontrado ou inválido"}
        return {
            "razao_social": resp.razao_social,
            "nome_fantasia": resp.nome_fantasia,
            "situacao_cadastral": resp.descricao_situacao_cadastral or resp.situacao_cadastral,
            "municipio": resp.municipio,
            "uf": resp.uf,
            "cnae_principal": resp.cnae_fiscal_descricao,
        }
    except Exception as e:  # noqa: BLE001 — erro/timeout/circuit-open: nunca derruba
        logger.warning("Tool consultar_cnpj falhou cnpj=%s: %s", cnpj, e)
        return {"erro": "não foi possível consultar agora"}


async def _tool_buscar_cliente(cnpj: str) -> dict:
    """Busca cliente por document_number (CNPJ normalizado) — query async própria. Nunca estoura."""
    import re  # noqa: PLC0415

    digits = re.sub(r"\D", "", cnpj or "")
    if not digits:
        return {"erro": "CNPJ inválido"}
    try:
        async with async_session_factory() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT name, status FROM clients "
                        "WHERE regexp_replace(coalesce(document_number, ''), '\\D', '', 'g') = :c "
                        "LIMIT 1"
                    ),
                    {"c": digits},
                )
            ).fetchone()
        if row:
            return {"existe": True, "nome": row[0], "status": str(row[1]) if row[1] is not None else None}
        return {"existe": False}
    except Exception as e:  # noqa: BLE001
        logger.warning("Tool buscar_cliente falhou: %s", e)
        return {"erro": "não foi possível consultar a base agora"}


async def _exec_tool(name: str, args: dict) -> dict:
    """Dispatcher das tools. Qualquer falha vira {erro:...} — nunca derruba o webhook."""
    try:
        if name == "consultar_cnpj":
            return await _tool_consultar_cnpj(str(args.get("cnpj", "")))
        if name == "buscar_cliente":
            return await _tool_buscar_cliente(str(args.get("cnpj", "")))
        return {"erro": f"tool desconhecida: {name}"}
    except Exception as e:  # noqa: BLE001
        logger.error("Tool %s exception: %s", name, e)
        return {"erro": "falha ao executar a ferramenta"}


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

        # 2) Chamada OpenAI com LOOP de tool-calling (lazy import; chave vem do env)
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = AsyncOpenAI()
        max_rounds = int(os.getenv("AGENT_MAX_TOOL_ROUNDS", "3"))
        total_in = total_out = 0
        texto = ""
        rounds = 0

        for rounds in range(1, max_rounds + 1):
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                max_tokens=max_tokens,
                temperature=0.7,
            )
            usage = getattr(resp, "usage", None)
            total_in += getattr(usage, "prompt_tokens", 0) or 0
            total_out += getattr(usage, "completion_tokens", 0) or 0

            msg = resp.choices[0].message
            tool_calls = getattr(msg, "tool_calls", None)
            if not tool_calls:
                texto = (msg.content or "").strip()
                break

            # anexa a mensagem do assistant que pediu as tools
            messages.append(
                {
                    "role": "assistant",
                    "content": msg.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        }
                        for tc in tool_calls
                    ],
                }
            )
            # executa cada tool e anexa o resultado (role=tool)
            for tc in tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:  # noqa: BLE001
                    args = {}
                result = await _exec_tool(tc.function.name, args)
                logger.info(
                    "Agente tool-call conv=%s round=%s tool=%s args=%s -> %s",
                    conversation_id,
                    rounds,
                    tc.function.name,
                    args,
                    result,
                )
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": json.dumps(result, ensure_ascii=False),
                    }
                )
        else:
            # atingiu o teto sem resposta final: ultima chamada SEM tools (forca texto)
            resp = await client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=0.7,
            )
            usage = getattr(resp, "usage", None)
            total_in += getattr(usage, "prompt_tokens", 0) or 0
            total_out += getattr(usage, "completion_tokens", 0) or 0
            texto = (resp.choices[0].message.content or "").strip()

        logger.info(
            "Agente: resposta gerada conv=%s model=%s tool_rounds=%s tokens_in=%s tokens_out=%s",
            conversation_id,
            model,
            rounds,
            total_in,
            total_out,
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
