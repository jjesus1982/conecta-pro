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

SYSTEM_PROMPT = """Você é o assistente virtual da Conecta Mais (conectamais.pro), empresa de Manaus/AM especializada em segurança e mão de obra para condomínios, empresas, indústrias e residências. Atende todos esses públicos, mas o foco principal são condomínios — você conversa muito com síndicos e administradoras.

Transparência: na PRIMEIRA interação de uma conversa, apresente-se brevemente como assistente virtual da Conecta Mais (ex.: "Olá! Sou o assistente virtual da Conecta Mais."). Nas mensagens seguintes da mesma conversa, não repita a apresentação.

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

Ferramentas disponíveis: quando o cliente fornecer ou mencionar um CNPJ, use consultar_cnpj para validar e obter os dados oficiais (razão social, situação cadastral, município/UF, CNAE) — NUNCA invente esses dados, use apenas o que a ferramenta retornar. Em seguida use buscar_cliente para verificar se esse CNPJ já é cliente da Conecta Mais: se for (existe:true), acolha a pessoa como CLIENTE já atendido (tom de relacionamento e cuidado, não de prospecção); se não for, siga qualificando como novo lead. Se uma ferramenta retornar erro, não trave nem mencione detalhes técnicos — siga o atendimento normalmente e, se precisar, peça o dado novamente com gentileza. Todos os guard-rails acima continuam valendo (nunca preços, nunca inventar).

Agendamento de visita: quando o cliente demonstrar real interesse e for o momento de avançar, conduza para AGENDAR uma visita técnica/comercial gratuita. Pergunte o endereço (se já for cliente identificado, confirme o endereço do cadastro) e a preferência de data e horário. Com endereço + data + horário em mãos, use a ferramenta agendar_visita. IMPORTANTE — fraseado: deixe SEMPRE claro que é uma SOLICITAÇÃO de visita e que a equipe confirma o horário depois. NUNCA diga que está "agendada" ou "confirmada". Diga algo como "vou encaminhar sua solicitação de visita para [data] às [horário]; nossa equipe confirma com você em seguida". Se faltar endereço, data ou horário, pergunte com gentileza antes de tentar agendar (nunca registre uma visita incompleta).

Transferência para um humano: tente SEMPRE resolver você mesmo primeiro — transferir é o último recurso. Se você NÃO conseguir resolver a demanda OU se o cliente pedir explicitamente para falar com uma pessoa/atendente, use a ferramenta transferir_conversa com o setor adequado: comercial (orçamento, proposta, cotação, contratar serviço, visita comercial); suporte_tecnico (equipamento com problema, manutenção de CFTV/câmera/alarme/controle de acesso); operacional (portaria, escala, ronda, troca de porteiro/vigilante, posto); administrativo (boleto, nota fiscal, financeiro, contrato, RH, cobrança). SEMPRE avise o cliente ANTES, com gentileza: "vou te encaminhar para o nosso time de [setor], um momento". IMPORTANTE: ao decidir encaminhar, você DEVE chamar a ferramenta transferir_conversa de fato — não basta dizer que vai encaminhar; sem a chamada, ninguém recebe a conversa. Se o cliente pedir para falar com uma pessoa/atendente/humano, chame transferir_conversa (use comercial se o setor não estiver claro).

Triagem antes de transferir um pedido VAGO: se o cliente pedir para falar com uma pessoa mas o assunto não estiver claro, faça UMA pergunta breve de triagem ANTES de chamar transferir_conversa, por exemplo: "Claro! Só pra te direcionar à pessoa certa — é sobre orçamento/visita, um equipamento ou manutenção, portaria/escala, ou financeiro?". Com base na resposta, escolha o setor (suporte_tecnico para equipamento/manutenção; operacional para portaria/escala/posto; administrativo para boleto/nota/financeiro/contrato; comercial para orçamento/visita/cotação). Só transfira para comercial como último recurso se o cliente não quiser especificar o assunto."""


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
    {
        "type": "function",
        "function": {
            "name": "agendar_visita",
            "description": (
                "Registra uma SOLICITAÇÃO de visita técnica/comercial (a equipe confirma o horário depois). "
                "Use SÓ quando já tiver endereço, data e horário. Não confirme horário ao cliente — é uma solicitação."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "data_visita": {"type": "string", "description": "Data desejada no formato YYYY-MM-DD"},
                    "horario_inicio": {"type": "string", "description": "Horário desejado no formato HH:MM (24h)"},
                    "endereco": {
                        "type": "string",
                        "description": "Endereço da visita (rua e número), 5 a 500 caracteres",
                    },
                    "bairro": {"type": "string", "description": "Bairro (opcional)"},
                    "cidade": {"type": "string", "description": "Cidade (opcional)"},
                    "objetivo": {
                        "type": "string",
                        "description": "O que o cliente deseja / motivo da visita (opcional)",
                    },
                    "nome_contato": {"type": "string", "description": "Nome de quem receberá a visita (opcional)"},
                    "telefone_contato": {"type": "string", "description": "Telefone de contato (opcional)"},
                    "cnpj": {
                        "type": "string",
                        "description": "CNPJ do cliente, se já informado, para vincular ao cadastro (opcional)",
                    },
                },
                "required": ["data_visita", "horario_inicio", "endereco"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transferir_conversa",
            "description": (
                "Encaminha a conversa para o time HUMANO do setor certo no Chatwoot. "
                "Use quando NÃO conseguir resolver a demanda OU o cliente pedir explicitamente falar com uma pessoa. "
                "Tente resolver primeiro — transferir é o último recurso. SEMPRE avise o cliente antes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "setor": {
                        "type": "string",
                        "enum": ["comercial", "suporte_tecnico", "operacional", "administrativo"],
                        "description": (
                            "comercial: orçamento, proposta, visita comercial, cotação, contratar serviço. "
                            "suporte_tecnico: equipamento com problema, manutenção de CFTV/câmera/alarme/controle de acesso. "
                            "operacional: portaria, escala, ronda, troca de porteiro/vigilante, posto. "
                            "administrativo: boleto, nota fiscal, financeiro, contrato, RH, cobrança."
                        ),
                    },
                    "motivo": {"type": "string", "description": "Motivo curto do encaminhamento"},
                },
                "required": ["setor"],
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


AGENT_VISITA_RESPONSAVEL_ID = os.getenv("AGENT_VISITA_RESPONSAVEL_ID", "ad9abb59-55fb-444e-a04f-0e1f22541de3")


async def _resolve_lead_id(db, conversation_id: int) -> str | None:
    """Resolve o lead_id da conversa pelo cwi_message_log (a entrada já criou/achou o lead)."""
    try:
        row = (
            await db.execute(
                text(
                    "SELECT lead_id FROM cwi_message_log "
                    "WHERE chatwoot_conversation_id = :c AND lead_id IS NOT NULL "
                    "ORDER BY created_at DESC LIMIT 1"
                ),
                {"c": conversation_id},
            )
        ).first()
        return str(row[0]) if row and row[0] else None
    except Exception:  # noqa: BLE001
        return None


async def _enviar_emails_visita(
    db,
    numero,
    data_visita,
    horario_inicio,
    endereco,
    bairro,
    cidade,
    objetivo,
    nome_contato,
    telefone_contato,
    cliente_id,
    conversation_id,
) -> None:
    """F-VISITA.2 — e-mail(s) de SOLICITAÇÃO de visita. BEST-EFFORT: nunca levanta exceção."""
    try:
        from core.mailer import send_email  # noqa: PLC0415

        data_fmt = data_visita.strftime("%d/%m/%Y")
        hora_fmt = horario_inicio.strftime("%H:%M")
        local = endereco
        if bairro:
            local += f", {bairro}"
        if cidade:
            local += f" - {cidade}"
        origem_txt = "cliente cadastrado" if cliente_id else "prospect (novo lead)"

        # (a) E-MAIL INTERNO — SEMPRE
        corpo_interno = (
            f"<h3>Nova SOLICITAÇÃO de visita — {numero}</h3>"
            f"<p><b>Status:</b> aguardando confirmação da equipe (NÃO confirmada).</p>"
            f"<ul>"
            f"<li><b>Número:</b> {numero}</li>"
            f"<li><b>Data/horário:</b> {data_fmt} às {hora_fmt}</li>"
            f"<li><b>Local:</b> {local}</li>"
            f"<li><b>Objetivo:</b> {objetivo or '-'}</li>"
            f"<li><b>Contato:</b> {nome_contato or '-'} / {telefone_contato or '-'}</li>"
            f"<li><b>Origem:</b> {origem_txt}</li>"
            f"</ul>"
            f"<p>Solicitação gerada pelo assistente de WhatsApp (copiloto). "
            f"A equipe deve <b>confirmar o horário</b> com o solicitante.</p>"
        )
        ok_int = await send_email(
            to_email="jjesus@conectamais.pro",
            subject=f"[Conecta PRO] Nova solicitação de visita {numero}",
            html_body=corpo_interno,
        )
        logger.info("F-VISITA.2 email interno conv=%s numero=%s enviado=%s", conversation_id, numero, ok_int)

        # (b) E-MAIL AO CLIENTE — só se cliente_id e houver email
        if cliente_id:
            row = (await db.execute(text("SELECT email FROM clients WHERE id = :id"), {"id": str(cliente_id)})).first()
            email_cli = (row[0] if row else None) or None
            if email_cli:
                corpo_cli = (
                    f"<p>Olá! Recebemos sua <b>solicitação de visita</b> para "
                    f"<b>{data_fmt}</b> às <b>{hora_fmt}</b>, em {local}.</p>"
                    f"<p>Nossa equipe <b>confirmará o horário</b> com você em breve — esta mensagem é apenas "
                    f"a confirmação de que recebemos sua solicitação (o horário ainda será confirmado).</p>"
                    f"<p>Atenciosamente,<br>Equipe Conecta Mais</p>"
                )
                ok_cli = await send_email(
                    to_email=email_cli,
                    subject="[Conecta Mais] Recebemos sua solicitação de visita",
                    html_body=corpo_cli,
                )
                logger.info("F-VISITA.2 email cliente conv=%s numero=%s enviado=%s", conversation_id, numero, ok_cli)
            else:
                logger.info(
                    "F-VISITA.2 email cliente PULADO conv=%s numero=%s motivo=sem_email", conversation_id, numero
                )
        else:
            logger.info(
                "F-VISITA.2 email cliente PULADO conv=%s numero=%s motivo=sem_cliente_id", conversation_id, numero
            )
    except Exception as e:  # noqa: BLE001 — best-effort: e-mail nunca quebra a visita
        logger.warning("F-VISITA.2 falha no envio de e-mail (best-effort) conv=%s: %s", conversation_id, e)


async def _tool_agendar_visita(args: dict, conversation_id: int) -> dict:
    """Cria uma visita PROPOSTA (status AGENDADA) em modules/campo. Copiloto: humano confirma depois. Nunca estoura."""
    import re  # noqa: PLC0415
    from datetime import datetime  # noqa: PLC0415
    from uuid import UUID  # noqa: PLC0415

    # validação de entrada: sem endereço/data/horário NÃO cria (modelo deve perguntar)
    endereco = (args.get("endereco") or "").strip()
    data_str = (args.get("data_visita") or "").strip()
    hora_str = (args.get("horario_inicio") or "").strip()
    if len(endereco) < 5 or not data_str or not hora_str:
        return {"erro": "faltam dados: preciso de endereço, data (YYYY-MM-DD) e horário (HH:MM)"}
    try:
        data_visita = datetime.strptime(data_str, "%Y-%m-%d").date()
        horario_inicio = datetime.strptime(hora_str, "%H:%M").time()
    except Exception:  # noqa: BLE001
        return {"erro": "data ou horário inválidos (use YYYY-MM-DD e HH:MM)"}

    try:
        from modules.campo.models.visita import OrigemVisita, TipoVisita  # noqa: PLC0415
        from modules.campo.schemas.visita import VisitaCreate  # noqa: PLC0415
        from modules.campo.services.visita_service import VisitaService  # noqa: PLC0415

        responsavel_id = UUID(AGENT_VISITA_RESPONSAVEL_ID)

        async with async_session_factory() as db:
            lead_id = await _resolve_lead_id(db, conversation_id)

            # cliente_id: se o cliente informou CNPJ e ele existe na base
            cliente_id = None
            cnpj_digits = re.sub(r"\D", "", str(args.get("cnpj") or ""))
            if cnpj_digits:
                crow = (
                    await db.execute(
                        text(
                            "SELECT id FROM clients "
                            "WHERE regexp_replace(coalesce(document_number, ''), '\\D', '', 'g') = :c LIMIT 1"
                        ),
                        {"c": cnpj_digits},
                    )
                ).first()
                if crow:
                    cliente_id = crow[0]

            visita_data = VisitaCreate(
                tipo=TipoVisita.COMERCIAL,
                origem=OrigemVisita.LEAD,
                responsavel_id=responsavel_id,
                endereco=endereco[:500],
                bairro=(args.get("bairro") or None),
                cidade=(args.get("cidade") or None),
                data_visita=data_visita,
                horario_inicio=horario_inicio,
                lead_id=UUID(lead_id) if lead_id else None,
                cliente_id=cliente_id,
                is_prospect=cliente_id is None,
                prospect_nome=(args.get("nome_contato") or None),
                prospect_telefone=(args.get("telefone_contato") or None),
                objetivo=(args.get("objetivo") or None),
            )
            visita = await VisitaService(db).criar_visita(visita_data, created_by=responsavel_id)

            # F-VISITA.2 — e-mail(s) de solicitação (best-effort: nunca quebra a criação da visita)
            await _enviar_emails_visita(
                db=db,
                numero=visita.numero,
                data_visita=data_visita,
                horario_inicio=horario_inicio,
                endereco=endereco,
                bairro=args.get("bairro"),
                cidade=args.get("cidade"),
                objetivo=args.get("objetivo"),
                nome_contato=args.get("nome_contato"),
                telefone_contato=args.get("telefone_contato"),
                cliente_id=cliente_id,
                conversation_id=conversation_id,
            )

            return {"ok": True, "numero": visita.numero, "status": "AGENDADA"}
    except Exception as e:  # noqa: BLE001
        logger.warning("Tool agendar_visita falhou conv=%s: %s", conversation_id, e)
        return {"erro": "não foi possível registrar a solicitação de visita agora"}


# Mapa setor -> team_id real do Chatwoot (GET /api/v1/accounts/1/teams, confirmado 2026-06-09)
SETOR_TEAM_ID = {
    "comercial": 1,
    "administrativo": 2,
    "suporte_tecnico": 3,
    "operacional": 4,
}


async def _tool_transferir_conversa(args: dict, conversation_id: int) -> dict:
    """Atribui a conversa ao time do setor no Chatwoot. BEST-EFFORT: nunca derruba o webhook."""
    setor = str(args.get("setor") or "").strip().lower()
    motivo = str(args.get("motivo") or "").strip()
    team_id = SETOR_TEAM_ID.get(setor)
    if not team_id:
        return {"erro": f"setor desconhecido: {setor}"}
    try:
        from modules.integrations.connectors.whatsapp.service import whatsapp_service  # noqa: PLC0415

        res = await whatsapp_service.assign_team(conversation_id, team_id)
        logger.info(
            "Tool transferir_conversa conv=%s setor=%s team=%s motivo=%s -> %s",
            conversation_id,
            setor,
            team_id,
            motivo,
            res.get("status"),
        )
        if res.get("status") == "assigned":
            return {"ok": True, "setor": setor, "mensagem": "conversa encaminhada ao time"}
        return {"erro": "não foi possível encaminhar agora"}
    except Exception as e:  # noqa: BLE001
        logger.warning("Tool transferir_conversa falhou conv=%s: %s", conversation_id, e)
        return {"erro": "não foi possível encaminhar agora"}


async def _exec_tool(name: str, args: dict, conversation_id: int) -> dict:
    """Dispatcher das tools. Qualquer falha vira {erro:...} — nunca derruba o webhook."""
    try:
        if name == "consultar_cnpj":
            return await _tool_consultar_cnpj(str(args.get("cnpj", "")))
        if name == "buscar_cliente":
            return await _tool_buscar_cliente(str(args.get("cnpj", "")))
        if name == "agendar_visita":
            return await _tool_agendar_visita(args, conversation_id)
        if name == "transferir_conversa":
            return await _tool_transferir_conversa(args, conversation_id)
        return {"erro": f"tool desconhecida: {name}"}
    except Exception as e:  # noqa: BLE001
        logger.error("Tool %s exception: %s", name, e)
        return {"erro": "falha ao executar a ferramenta"}


# ============================================================================
# APRENDIZADO (3 capacidades, todas BEST-EFFORT — falha = agente segue como antes)
# 1) Memoria de longo prazo por contato: linhas direction='mem' no cwi_message_log
#    (zero migration; chave = phone_canonical; sempre INSERT -> historico auditavel).
# 2) RAG: base de conhecimento em /app/uploads/agent_knowledge/*.md (volume montado
#    do host ./uploads -> EDITAVEL SEM REBUILD). Embeddings OpenAI com cache por
#    mtime; fallback por palavras-chave se a API falhar.
# 3) Feedback few-shot: pares (msg do cliente -> resposta REAL da equipe) extraidos
#    do proprio cwi_message_log (out humanos; ecos do bot sao excluidos via match
#    com drafts 'drf' da mesma conversa).
# ============================================================================

_KNOWLEDGE_DIR = "/app/uploads/agent_knowledge"
_KNOWLEDGE_CACHE_FILE = os.path.join(_KNOWLEDGE_DIR, ".cache_embeddings.json")
_EMBED_MODEL = "text-embedding-3-small"


async def _get_contact_memory(conversation_id: int) -> str | None:
    """Ultimo resumo 'mem' do telefone desta conversa (memoria entre conversas)."""
    try:
        async with async_session_factory() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT m.content FROM cwi_message_log m WHERE m.direction='mem' "
                        "AND m.phone_canonical = (SELECT phone_canonical FROM cwi_message_log "
                        "  WHERE chatwoot_conversation_id=:c AND phone_canonical IS NOT NULL "
                        "  ORDER BY created_at DESC LIMIT 1) "
                        "AND m.content IS NOT NULL AND m.content <> '' "
                        "ORDER BY m.created_at DESC LIMIT 1"
                    ),
                    {"c": conversation_id},
                )
            ).first()
        return row[0] if row else None
    except Exception as e:  # noqa: BLE001
        logger.error("Agente memoria: falha ao ler (conv=%s): %s", conversation_id, e)
        return None


async def _update_contact_memory(conversation_id: int, phone: str | None) -> None:
    """Atualiza o resumo do cliente apos um atendimento (INSERT 'mem'). Best-effort."""
    if not phone:
        return
    try:
        anterior = await _get_contact_memory(conversation_id) or "(sem memoria anterior)"
        async with async_session_factory() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT direction, content FROM cwi_message_log "
                        "WHERE chatwoot_conversation_id=:c AND direction IN ('in','out') "
                        "AND content IS NOT NULL AND content <> '' "
                        "ORDER BY created_at DESC LIMIT 12"
                    ),
                    {"c": conversation_id},
                )
            ).fetchall()
        if not rows:
            return
        dialogo = "\n".join(
            f"{'Cliente' if d == 'in' else 'Atendente'}: {c}" for d, c in reversed(rows)
        )
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = AsyncOpenAI()
        resp = await client.chat.completions.create(
            model=os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini"),
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Voce mantem a MEMORIA de atendimento de um cliente da Conecta Mais. "
                        "Atualize o resumo abaixo com o novo dialogo. Maximo 6 linhas, fatos uteis "
                        "para o proximo atendimento: nome, tipo (condominio/empresa/residencia), porte, "
                        "o que procura, preferencias, visitas solicitadas, status. Sem floreios."
                    ),
                },
                {"role": "user", "content": f"RESUMO ANTERIOR:\n{anterior}\n\nNOVO DIALOGO:\n{dialogo}"},
            ],
            max_tokens=220,
            temperature=0.2,
        )
        resumo = (resp.choices[0].message.content or "").strip()
        if not resumo:
            return
        async with async_session_factory() as db:
            await db.execute(
                text(
                    "INSERT INTO cwi_message_log (direction, phone_canonical, "
                    "chatwoot_conversation_id, content, status) "
                    "VALUES ('mem', :phone, :conv, :content, 'memory')"
                ),
                {"phone": phone, "conv": conversation_id, "content": resumo},
            )
            await db.commit()
        logger.info("Agente memoria: atualizada phone=%s (%s chars)", phone, len(resumo))
    except Exception as e:  # noqa: BLE001
        logger.error("Agente memoria: falha ao atualizar (conv=%s): %s", conversation_id, e)


def _kb_chunks() -> list[dict]:
    """Le os .md da base de conhecimento e divide em chunks por secao '##'."""
    chunks = []
    try:
        if not os.path.isdir(_KNOWLEDGE_DIR):
            return []
        for fname in sorted(os.listdir(_KNOWLEDGE_DIR)):
            if not fname.endswith(".md") or fname.startswith("."):
                continue
            path = os.path.join(_KNOWLEDGE_DIR, fname)
            try:
                with open(path, encoding="utf-8") as f:
                    raw = f.read()
            except Exception:  # noqa: BLE001
                continue
            mtime = os.path.getmtime(path)
            partes = raw.split("\n## ")
            for i, parte in enumerate(p.strip() for p in partes):
                if len(parte) < 40:
                    continue
                texto = parte if i == 0 else f"## {parte}"
                chunks.append({"id": f"{fname}:{i}", "mtime": mtime, "text": texto[:1600]})
    except Exception as e:  # noqa: BLE001
        logger.error("Agente RAG: falha ao ler base: %s", e)
    return chunks


def _cosine(a: list[float], b: list[float]) -> float:
    s = sum(x * y for x, y in zip(a, b, strict=False))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(x * x for x in b) ** 0.5
    return s / (na * nb) if na and nb else 0.0


async def _search_knowledge(query: str, top_k: int = 3) -> str | None:
    """Top-k chunks relevantes da base. Embeddings c/ cache; fallback keyword."""
    try:
        chunks = _kb_chunks()
        if not chunks or not (query or "").strip():
            return None
        # cache de embeddings por (id, mtime)
        cache: dict = {}
        try:
            with open(_KNOWLEDGE_CACHE_FILE, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:  # noqa: BLE001
            cache = {}
        try:
            from openai import AsyncOpenAI  # noqa: PLC0415

            client = AsyncOpenAI()
            faltantes = [c for c in chunks if cache.get(c["id"], {}).get("mtime") != c["mtime"]]
            if faltantes:
                emb = await client.embeddings.create(
                    model=_EMBED_MODEL, input=[c["text"] for c in faltantes]
                )
                for c, e in zip(faltantes, emb.data, strict=False):
                    cache[c["id"]] = {"mtime": c["mtime"], "vec": e.embedding}
                try:
                    with open(_KNOWLEDGE_CACHE_FILE, "w", encoding="utf-8") as f:
                        json.dump(cache, f)
                except Exception:  # noqa: BLE001
                    pass  # cache em disco e otimizacao, nao requisito
            qe = await client.embeddings.create(model=_EMBED_MODEL, input=[query[:1000]])
            qv = qe.data[0].embedding
            pontuados = [
                (_cosine(qv, cache[c["id"]]["vec"]), c) for c in chunks if c["id"] in cache
            ]
            pontuados.sort(key=lambda t: t[0], reverse=True)
            top = [c for score, c in pontuados[:top_k] if score >= 0.25]
        except Exception as e:  # noqa: BLE001
            # fallback sem API: score por sobreposicao de palavras
            logger.warning("Agente RAG: embeddings indisponiveis (%s) — fallback keyword", e)
            q_words = {w for w in query.lower().split() if len(w) > 3}
            pontuados = [
                (len(q_words & set(c["text"].lower().split())), c) for c in chunks
            ]
            pontuados.sort(key=lambda t: t[0], reverse=True)
            top = [c for score, c in pontuados[:top_k] if score >= 2]
        if not top:
            return None
        return "\n\n---\n\n".join(c["text"] for c in top)
    except Exception as e:  # noqa: BLE001
        logger.error("Agente RAG: falha na busca: %s", e)
        return None


async def _few_shot_examples(conversation_id: int, limit: int = 3) -> str | None:
    """Pares reais (cliente -> resposta da EQUIPE) de outras conversas.

    Ecos do bot autonomo sao excluidos: um 'out' cujo conteudo coincide com um
    'drf' da mesma conversa e resposta do proprio agente, nao da equipe.
    """
    try:
        async with async_session_factory() as db:
            rows = (
                await db.execute(
                    text(
                        "SELECT o.chatwoot_conversation_id, o.content, "
                        "  (SELECT i.content FROM cwi_message_log i "
                        "   WHERE i.chatwoot_conversation_id = o.chatwoot_conversation_id "
                        "   AND i.direction='in' AND i.created_at < o.created_at "
                        "   AND i.content IS NOT NULL AND i.content <> '' "
                        "   ORDER BY i.created_at DESC LIMIT 1) AS pergunta "
                        "FROM cwi_message_log o "
                        "WHERE o.direction='out' AND length(coalesce(o.content,'')) > 40 "
                        "AND o.chatwoot_conversation_id <> :c "
                        "AND NOT EXISTS (SELECT 1 FROM cwi_message_log d "
                        "  WHERE d.direction='drf' "
                        "  AND d.chatwoot_conversation_id = o.chatwoot_conversation_id "
                        "  AND d.content = o.content) "
                        "ORDER BY o.created_at DESC LIMIT :n"
                    ),
                    {"c": conversation_id, "n": limit},
                )
            ).fetchall()
        pares = [(p, r) for _, r, p in rows if p]
        if not pares:
            return None
        return "\n\n".join(
            f"Cliente: {p[:300]}\nResposta da equipe: {r[:400]}" for p, r in pares
        )
    except Exception as e:  # noqa: BLE001
        logger.error("Agente few-shot: falha (conv=%s): %s", conversation_id, e)
        return None


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

        # APRENDIZADO (best-effort): RAG + memoria do cliente + exemplos da equipe.
        # Qualquer falha em qualquer um -> simplesmente nao injeta (agente segue normal).
        ultima_in = next((c for d, c in rows if d == "in"), "") or ""
        kb = await _search_knowledge(ultima_in)
        if kb:
            messages.append({
                "role": "system",
                "content": "CONHECIMENTO DA EMPRESA relevante para esta conversa "
                "(use como fonte de verdade; nao invente alem disso):\n\n" + kb,
            })
        memoria = await _get_contact_memory(conversation_id)
        if memoria:
            messages.append({
                "role": "system",
                "content": "MEMORIA DESTE CLIENTE (conversas anteriores — personalize o "
                "atendimento e NAO repita perguntas ja respondidas):\n" + memoria,
            })
        exemplos = await _few_shot_examples(conversation_id)
        if exemplos:
            messages.append({
                "role": "system",
                "content": "EXEMPLOS REAIS de respostas da nossa equipe (espelhe o tom e "
                "o estilo, sem copiar literalmente):\n\n" + exemplos,
            })

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
                result = await _exec_tool(tc.function.name, args, conversation_id)
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


def agent_mode() -> str:
    """Modo do agente: 'copilot' (default seguro) | 'autonomous'.

    Kill-switch: setar AGENT_MODE=copilot no .env (ou remover) + recreate do backend.
    """
    mode = os.getenv("AGENT_MODE", "copilot").strip().lower()
    return mode if mode in ("copilot", "autonomous") else "copilot"


async def _get_conversation_info(conversation_id: int) -> dict | None:
    """Consulta a conversa no Chatwoot p/ os GUARDS do modo autonomo. Best-effort.

    Retorna {'is_group': bool, 'assignee': str|None} ou None (falha -> chamador
    deve ser CONSERVADOR e cair para copiloto).
    """
    base = os.getenv("CHATWOOT_BASE_URL", "http://chatwoot-fazerai:3000").rstrip("/")
    account = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
    token = os.getenv("CHATWOOT_API_TOKEN", "")
    if not token:
        return None
    url = f"{base}/api/v1/accounts/{account}/conversations/{conversation_id}"
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.get(
                url,
                headers={"api_access_token": token},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp,
        ):
            if resp.status != 200:
                logger.warning("Agente: GET conversa %s -> HTTP %s", conversation_id, resp.status)
                return None
            data = await resp.json()
        meta = data.get("meta") or {}
        sender = meta.get("sender") or {}
        assignee = meta.get("assignee") or None
        identifier = str(sender.get("identifier") or "")
        phone = sender.get("phone_number") or ""
        # GRUPO (criterio CONSERVADOR): @g.us no identifier OU sem telefone individual
        # -> se nao da pra garantir 1:1, trata como grupo (nao responde publico).
        is_group = ("@g.us" in identifier) or (not phone)
        return {"is_group": is_group, "assignee": (assignee or {}).get("name") if assignee else None}
    except Exception as e:  # noqa: BLE001
        logger.error("Agente: excecao ao consultar conversa %s: %s", conversation_id, e)
        return None


async def _post_public_reply(conversation_id: int, content: str) -> bool:
    """Posta resposta PUBLICA (cliente RECEBE no WhatsApp via Chatwoot->baileys).

    Best-effort: em falha, FALLBACK para nota privada (nao perde o trabalho do LLM).
    O eco desta mensagem volta no webhook como outgoing -> direction 'out' -> NAO
    redispara o agente (anti-loop garantido pelo gate direction=='in').
    """
    base = os.getenv("CHATWOOT_BASE_URL", "http://chatwoot-fazerai:3000").rstrip("/")
    account = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
    token = os.getenv("CHATWOOT_API_TOKEN", "")
    if not token:
        logger.warning("Agente: CHATWOOT_API_TOKEN ausente — resposta publica nao enviada")
        return False
    url = f"{base}/api/v1/accounts/{account}/conversations/{conversation_id}/messages"
    payload = {"content": content, "message_type": "outgoing", "private": False}
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
            logger.error("Agente: resposta publica falhou %s: %s", resp.status, body)
            return False
    except Exception as e:  # noqa: BLE001
        logger.error("Agente: excecao ao postar resposta publica conv=%s: %s", conversation_id, e)
        return False


async def processar_incoming(conversation_id: int, phone: str | None = None) -> None:
    """Entrypoint do BackgroundTask: gera a resposta e entrega conforme AGENT_MODE.

    copilot (default): nota privada (humano aprova) + rascunho no log.
    autonomous: responde PUBLICO ao cliente, COM GUARDS — pula grupos e conversas
    com humano atribuido (nesses casos cai para nota privada). Draft SEMPRE logado.
    """
    texto = await gerar_resposta(conversation_id)
    if not texto:
        return
    model = os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini")
    await _log_draft(conversation_id, phone, texto, model)

    decision = "copilot_note"
    if agent_mode() == "autonomous":
        info = await _get_conversation_info(conversation_id)
        if info is None:
            decision = "copilot_note_info_fail"  # conservador: sem certeza -> copiloto
        elif info["is_group"]:
            decision = "skipped_group"
        elif info["assignee"]:
            decision = "skipped_assigned"
        else:
            decision = "autonomous_sent"

    if decision == "autonomous_sent":
        ok = await _post_public_reply(conversation_id, texto)
        if not ok:
            decision = "copilot_note_send_fail"  # fallback: nao perde o trabalho
            await _post_private_note(conversation_id, texto)
    else:
        await _post_private_note(conversation_id, texto)

    logger.info("Agente: decisao=%s conv=%s mode=%s", decision, conversation_id, agent_mode())

    # Memoria de longo prazo: atualiza o perfil do cliente apos o atendimento.
    # Best-effort e por ultimo — nunca atrasa/derruba a entrega da resposta.
    await _update_contact_memory(conversation_id, phone)
