"""
Servico Assistente IA para o Portal do Cliente.

Wrapper do LLMProvider adaptado para o contexto restrito do portal,
respondendo apenas sobre dados do cliente autenticado.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Importacao condicional do LLMProvider
try:
    from modules.ai.conversation.services.llm_provider import LLMProvider

    _LLM_AVAILABLE = True
except ImportError:
    _LLM_AVAILABLE = False
    LLMProvider = None  # type: ignore[misc,assignment]


PORTAL_SYSTEM_PROMPT = """Você é um assistente virtual do Portal do Cliente da Conecta PRO.

CONTEXTO DO CLIENTE:
- client_id: {client_id}

SUAS REGRAS ABSOLUTAS:
1. Responda APENAS sobre dados deste cliente específico (client_id acima).
2. NÃO revele informações de outros clientes — nunca.
3. NÃO execute ações administrativas (criar escalas, demitir funcionários, etc.).
4. Fale só dos dados JÁ MOSTRADOS ao cliente no portal (abaixo). Não invente números
   nem exponha nomes/CPF de funcionários; presença e equipe são em números agregados.
5. Tom: profissional mas amigável, linguagem simples, sem jargão técnico interno.

VOCÊ PODE AJUDAR COM:
- Status e detalhes dos kits documentais do cliente
- Equipe alocada e presença da operação no condomínio (números, não nomes)
- Visitas da gestão Conecta ao condomínio (quando, o que foi feito)
- NFS-e e contrato disponíveis no financeiro
- Certidões e documentos para download
- Abertura e acompanhamento de chamados de suporte
- Explicar como utilizar o portal

DADOS DISPONÍVEIS DO CLIENTE:
{client_context}

Responda de forma clara, direta e útil. Se não souber a resposta, diga honestamente
e sugira abrir um chamado de suporte.
"""

DEFAULT_SUGGESTIONS = [
    "Status dos meus kits",
    "Quando meu próximo kit fica pronto?",
    "Como baixar meus documentos?",
    "Tenho certidões vencendo?",
    "Abrir um chamado",
    "Status dos meus chamados abertos",
]

PLACEHOLDER_RESPONSES = {
    "kit": (
        "Seus kits documentais ficam disponíveis mensalmente. "
        "Acesse a aba 'Meus Kits' para visualizar e baixar seus documentos. "
        "Se precisar de ajuda, posso abrir um chamado de suporte para você."
    ),
    "certid": (
        "Para verificar certidões, acesse a seção 'Meus Kits' e procure documentos "
        "com o tipo 'Certidão'. Documentos próximos do vencimento aparecem destacados."
    ),
    "chamado": (
        "Para abrir um chamado de suporte, acesse a aba 'Chamados' no menu superior. "
        "Nossa equipe responderá em até 24 horas úteis."
    ),
    "document": (
        "Seus documentos estão disponíveis na seção 'Meus Kits'. "
        "Clique em qualquer documento para visualizar ou baixar em PDF."
    ),
    "default": (
        "Olá! Sou o assistente do portal da Conecta PRO. "
        "Posso ajudá-lo com informações sobre seus kits documentais, certidões e chamados de suporte. "
        "Como posso ajudar?"
    ),
}


def _get_placeholder_response(message: str) -> str:
    """Retorna resposta placeholder baseada em palavras-chave."""
    msg_lower = message.lower()
    for key, response in PLACEHOLDER_RESPONSES.items():
        if key != "default" and key in msg_lower:
            return response
    return PLACEHOLDER_RESPONSES["default"]


async def _fetch_client_context(db: AsyncSession, client_id: str) -> str:
    """Busca contexto básico do cliente para enriquecer o prompt."""
    lines: list[str] = []

    # Kits documentais
    try:
        result = await db.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status = 'pending') AS pending,
                    COUNT(*) FILTER (WHERE status = 'approved') AS approved,
                    COUNT(*) FILTER (WHERE status = 'completed') AS completed,
                    COUNT(*) AS total
                FROM ged_document_kits
                WHERE client_id = :cid
                """
            ),
            {"cid": client_id},
        )
        row = result.fetchone()
        if row and row.total:
            lines.append(
                f"Kits documentais: {row.total} total "
                f"({row.pending} pendentes, {row.approved} aprovados, {row.completed} concluídos)"
            )
    except Exception as exc:
        logger.debug("Erro ao buscar kits do cliente %s: %s", client_id, exc)

    # Chamados abertos
    try:
        result = await db.execute(
            text(
                """
                SELECT
                    COUNT(*) FILTER (WHERE status IN ('open', 'in_progress')) AS open_count,
                    COUNT(*) AS total
                FROM client_portal_tickets
                WHERE client_id = :cid
                """
            ),
            {"cid": client_id},
        )
        row = result.fetchone()
        if row and row.total:
            lines.append(f"Chamados: {row.open_count} abertos de {row.total} total")
    except Exception as exc:
        logger.debug("Erro ao buscar chamados do cliente %s: %s", client_id, exc)

    # Operação real do condomínio (equipe, presença, ASOs) — reusa o serviço do portal
    try:
        from modules.client_portal.services import portal_operacao_service as op

        resumo = await op.resumo(db, client_id)
        if isinstance(resumo, dict):
            partes = []
            if resumo.get("equipe_total"):
                partes.append(f"{resumo['equipe_total']} pessoas alocadas")
            if resumo.get("assiduidade_local_pct") is not None:
                partes.append(f"assiduidade no local {resumo['assiduidade_local_pct']}%")
            if resumo.get("asos_vencidos"):
                partes.append(f"{resumo['asos_vencidos']} ASO(s) a vencer")
            if resumo.get("turnover_pct") is not None:
                partes.append(f"turnover 12m {resumo['turnover_pct']}%")
            if partes:
                lines.append("Equipe no condomínio: " + ", ".join(str(p) for p in partes))
    except Exception as exc:
        logger.debug("Contexto operação p/ %s: %s", client_id, exc)

    # Visitas da gestão (últimas) — prova de serviço
    try:
        from modules.client_portal.services import portal_visitas_service as vs

        v = await vs.visitas(db, client_id, limite=3)
        if isinstance(v, dict) and v.get("total_visitas"):
            ult = (v.get("visitas") or [{}])[0]
            lines.append(
                f"Visitas da gestão: {v['total_visitas']} registradas; "
                f"última em {ult.get('data', '?')} ({ult.get('responsavel', 'gestão')})"
            )
    except Exception as exc:
        logger.debug("Contexto visitas p/ %s: %s", client_id, exc)

    # Financeiro (NFS-e/contrato) — resumo
    try:
        from modules.client_portal.services import portal_financeiro_service as fin

        r = await fin.resumo(db, client_id)
        if isinstance(r, dict):
            fpartes = []
            if r.get("notas_total"):
                fpartes.append(f"{r['notas_total']} NFS-e no portal")
            if r.get("contrato_ativo") and r.get("contrato_mensal"):
                fpartes.append(f"contrato mensal R$ {r['contrato_mensal']}")
            if fpartes:
                lines.append("Financeiro: " + ", ".join(str(p) for p in fpartes))
    except Exception as exc:
        logger.debug("Contexto financeiro p/ %s: %s", client_id, exc)

    if not lines:
        return "Nenhum dado adicional disponível no momento."

    return "\n".join(lines)


class PortalAssistantService:
    """
    Serviço de assistente IA para o portal do cliente.

    Utiliza o LLMProvider existente com um system prompt restrito
    ao contexto do cliente autenticado.
    """

    def __init__(self, db: AsyncSession):
        self.db = db
        self._llm: Any = None

        if _LLM_AVAILABLE and LLMProvider is not None:
            try:
                self._llm = LLMProvider()
            except Exception as exc:
                logger.warning("Falha ao inicializar LLMProvider para portal: %s", exc)

    async def get_greeting(self, client_id: str) -> dict:
        """Retorna saudação personalizada para o cliente."""
        hour = datetime.now().hour
        if hour < 12:
            period = "Bom dia"
        elif hour < 18:
            period = "Boa tarde"
        else:
            period = "Boa noite"

        greeting = (
            f"{period}! Sou o assistente virtual da Conecta PRO. "
            "Posso ajudá-lo com informações sobre seus kits documentais, "
            "certidões e chamados de suporte. Como posso ajudar?"
        )

        return {
            "greeting": greeting,
            "suggestions": DEFAULT_SUGGESTIONS,
        }

    async def send_message(
        self,
        client_id: str,
        message: str,
        session_id: str,
    ) -> dict:
        """
        Processa mensagem do cliente e retorna resposta do assistente.

        Args:
            client_id: ID do cliente autenticado.
            message: Mensagem enviada pelo cliente.
            session_id: ID da sessão de chat.

        Returns:
            dict com response, suggestions e session_id.
        """
        message_id = str(uuid.uuid4())

        # Contexto REAL do condomínio (kits, equipe/presença, visitas, financeiro)
        client_context = await _fetch_client_context(self.db, client_id)
        system_prompt = PORTAL_SYSTEM_PROMPT.format(
            client_id=client_id,
            client_context=client_context,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ]

        # Roteador por camadas: tier MEDIA (conversa com contexto), escala sozinho.
        # Última rede = frases prontas (nunca inventa).
        response_text = None
        try:
            from core.llm_cascade import aroute

            response_text = await aroute(messages=messages, tier="media", max_tokens=800)
        except Exception as exc:
            logger.error("Portal assistant: erro no roteador LLM: %s", exc)

        if not response_text:
            logger.info("Portal assistant: sem LLM — usando resposta pronta")
            response_text = _get_placeholder_response(message)

        return {
            "response": response_text,
            "suggestions": DEFAULT_SUGGESTIONS,
            "session_id": session_id,
            "message_id": message_id,
        }

    async def record_feedback(
        self,
        client_id: str,
        message_id: str,
        rating: str,
    ) -> bool:
        """
        Registra feedback do cliente sobre uma resposta.

        Args:
            client_id: ID do cliente.
            message_id: ID da mensagem avaliada.
            rating: 'positive' ou 'negative'.

        Returns:
            True se registrado com sucesso.
        """
        logger.info(
            "Feedback portal: client=%s message=%s rating=%s",
            client_id,
            message_id,
            rating,
        )
        return True
