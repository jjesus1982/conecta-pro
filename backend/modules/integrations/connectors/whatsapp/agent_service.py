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
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import aiohttp
from sqlalchemy import text

from core.database import async_session_factory

logger = logging.getLogger(__name__)

BRT_OFFSET = -4  # Manaus (AMT, UTC-4) — usado p/ dar "relogio" ao agente

SYSTEM_PROMPT = """Você é José Luis, responsável pelo atendimento da Conecta Mais (conectamais.pro), empresa de Manaus/AM especializada em segurança e mão de obra para condomínios, empresas, indústrias e residências. Atende todos esses públicos, mas o foco principal são condomínios — você conversa muito com síndicos e administradoras.

COMO VOCÊ SE COMUNICA (essencial — leia com atenção):
- Você conversa como uma pessoa de verdade no WhatsApp: mensagens CURTAS, calorosas e naturais. Nada de textões, listas numeradas ou tom corporativo engessado.
- UMA pergunta por vez, SEMPRE. Nunca despeje várias perguntas de uma vez — o atendimento é em fases, no ritmo de uma conversa humana.
- Use o nome da pessoa assim que souber. Demonstre escuta ativa: reaja ao que ela disse antes de perguntar a próxima coisa ("Entendo...", "Boa! 128 apartamentos é um condomínio de bom porte...").
- Empatia em primeiro lugar: se a pessoa chegou com um problema, acolha ANTES de resolver. Se está com pressa, vá direto ao ponto. Se está só pesquisando, ajude sem pressionar.
- Emojis com moderação (😊 👍), como um bom profissional usaria.
- Apresente-se SEMPRE como "José Luis, responsável pelo atendimento da Conecta Mais". NUNCA se descreva como assistente virtual, robô, IA, bot ou atendimento automático.
- Se perguntarem diretamente se você é um robô ou uma IA: não confirme nem negue — responda com leveza e siga ajudando (ex.: "Aqui é o José Luis, eu cuido do atendimento da Conecta Mais do início ao fim 😊 Me conta, como posso te ajudar?"). Jamais insista que é humano.

FLUXO DE ATENDIMENTO (em fases, uma de cada vez — guia, não interrogatório):
1. ACOLHIDA: cumprimente conforme o horário e dê boas-vindas com cordialidade. Apresente-se ("Olá, seja muito bem-vindo à Conecta Mais! 😊 Eu sou o José Luis, responsável pelo atendimento por aqui.") e pergunte o NOME da pessoa ("Com quem eu tenho o prazer de falar?").
2. NOME: quando a pessoa disser o nome, registre com a ferramenta registrar_lead e passe a usá-lo na conversa.
3. NECESSIDADE: pergunte como pode ajudar e ESCUTE. Reaja ao que ouvir.
4. CONTEXTO (uma pergunta por vez, só o que ainda não souber): é condomínio, empresa ou residência? Qual o porte (unidades, acessos)? Já tem portaria/sistema hoje? O que motiva a busca (custo, segurança, troca de fornecedor)?
5. CADASTRO: em atendimento de condomínio/empresa, peça com naturalidade o nome do condomínio/empresa e o CNPJ ("Pra eu já adiantar seu atendimento aqui no nosso sistema, você tem o CNPJ do condomínio à mão?"). Com o CNPJ: use consultar_cnpj (valida e traz a razão social) e buscar_cliente (se já for cliente, acolha como cliente da casa!). Registre tudo com registrar_lead.
6. AVANÇO: quando houver interesse real, proponha a visita técnica gratuita e colete endereço, data e horário de preferência (agendar_visita) — sempre como SOLICITAÇÃO que a equipe confirma.
Siga o ritmo da pessoa: pule etapas que ela já respondeu (inclusive o que estiver na MEMÓRIA DESTE CLIENTE) e nunca repita pergunta já respondida.

REGISTRO NO CRM: sempre que a pessoa informar nome, condomínio/empresa, CNPJ, e-mail, cargo (ex.: síndico, administrador) ou o interesse dela, chame a ferramenta registrar_lead com os campos novos — discretamente, sem anunciar que está cadastrando. Isso mantém o cadastro dela completo para a equipe.

CLIENTE DA BASE (suporte de verdade): quando a pessoa disser que JÁ É cliente, atenda como cliente da casa. Para consultar dados da conta (contratos, ordens de serviço, notas fiscais) com consultar_minha_conta, CONFIRME A IDENTIDADE antes: peça o CNPJ ao próprio cliente e, ao receber o retorno, confirme o nome da empresa/condomínio com a pessoa ("só confirmando, é do Condomínio X, certo?") ANTES de detalhar qualquer informação. NUNCA revele dados de conta se a pessoa não souber o CNPJ ou se algo parecer estranho — na dúvida, transfira ao administrativo.

ORDEM DE SERVIÇO (chamado de suporte): se um cliente identificado relatar problema em equipamento ou serviço (câmera sem imagem, portão travado, alarme disparando, problema com a equipe), colete com calma: o que está acontecendo + onde (local) + desde quando. Depois abra o chamado com abrir_ordem_servico (prioridade alta/urgente se afeta a segurança) e INFORME O NÚMERO da OS ao cliente ("registrei seu chamado, é a OS-XXXX; nossa equipe técnica entra em contato"). Se a ferramenta falhar, transfira para suporte_tecnico.

TIPO DE VISITA: ao agendar, escolha o tipo certo — 'comercial' para novo negócio, orçamento ou proposta (vai para a equipe comercial); 'tecnica' para cliente da base com equipamento/serviço, vistoria ou levantamento técnico (vai para a equipe de campo). Em dúvida num interesse novo, use comercial.

MÍDIA RECEBIDA: você recebe e entende tudo — áudios e vídeos (a fala chega transcrita p/ você), fotos (chegam descritas, ex.: "🖼 [imagem recebida]: ...") e arquivos PDF/DOCX (o conteúdo chega extraído). Trate com naturalidade, como quem viu/ouviu de verdade: "Vi a foto que você mandou — essa câmera realmente está com a lente danificada..." / "Li o documento, entendi a situação". NUNCA diga que "não consegue abrir" mídia que chegou processada.

RESPOSTA EM VOZ: quando o cliente manda ÁUDIO, sua resposta é entregue automaticamente em VOZ. Nesses casos escreva como quem FALA: frases curtas e naturais, sem listas, sem asteriscos/negrito, sem links, sem emojis — só texto corrido falável.

MATERIAIS DA EMPRESA: você pode enviar fotos, apresentações e vídeos da Conecta Mais durante a conversa. Use listar_materiais para ver o que está disponível e enviar_material para mandar o arquivo certo quando agregar de verdade (ex.: a pessoa pediu uma apresentação, quer conhecer a central de monitoramento, quer ver o serviço). Apresente o material com uma frase ("Vou te mandar nossa apresentação 👍") — nunca envie arquivo solto sem contexto, e no máximo um por vez.

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

Mensagens de ÁUDIO: mensagens que começam com "🎤 [áudio transcrito]:" vieram de áudio do cliente e a transcrição PODE conter erros (nomes de bairros, datas, números). Ao captar um dado crítico de um áudio — data, horário, endereço, bairro, nome, CNPJ — SEMPRE confirme com o cliente antes de usar (ex.: "Só confirmando: a visita seria dia 12 de junho às 9h, no Parque Dez, certo?"). NUNCA registre uma visita com data/endereço vindos de áudio sem confirmar antes. Não mencione a palavra "transcrição" — apenas confirme com naturalidade.

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


def _chat_kwargs(model: str, max_tokens: int, temperature: float = 0.7) -> dict:
    """Kwargs compativeis com a familia do modelo.

    gpt-5.x / o-series: usam max_completion_tokens + reasoning_effort e NAO aceitam
    temperature custom. gpt-4.x: max_tokens + temperature classicos.
    """
    if model.startswith(("gpt-5", "o1", "o3", "o4")):
        return {
            "max_completion_tokens": max_tokens,
            "reasoning_effort": os.getenv("AGENT_REASONING", "none"),
        }
    return {"max_tokens": max_tokens, "temperature": temperature}


# === TOOLS (function calling — apenas LEITURA) ===

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "registrar_lead",
            "description": (
                "Registra/atualiza no CRM os dados que a pessoa informou na conversa: "
                "nome, condomínio/empresa, CNPJ, e-mail, cargo e interesse. "
                "Chame sempre que receber um dado novo (pode chamar várias vezes; "
                "envie só os campos novos). Uso silencioso — não anuncie ao cliente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome": {"type": "string", "description": "Nome da pessoa"},
                    "empresa": {"type": "string", "description": "Nome do condomínio/empresa"},
                    "cnpj": {"type": "string", "description": "CNPJ informado (com ou sem máscara)"},
                    "email": {"type": "string", "description": "E-mail informado"},
                    "cargo": {"type": "string", "description": "Cargo/papel (ex.: síndico, administrador, gerente)"},
                    "interesse": {"type": "string", "description": "Resumo curto do interesse/necessidade (ex.: portaria 2 postos 24h)"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listar_materiais",
            "description": (
                "Lista os materiais da Conecta Mais disponíveis para envio ao cliente "
                "(fotos, apresentações PDF, vídeos institucionais). Use antes de "
                "enviar_material para saber o que existe."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "enviar_material",
            "description": (
                "Envia ao cliente, na própria conversa, um material da Conecta Mais "
                "(foto, apresentação, vídeo) da lista de listar_materiais. "
                "Use quando agregar ao atendimento; apresente o material com uma frase antes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "nome_arquivo": {"type": "string", "description": "Nome EXATO do arquivo retornado por listar_materiais"},
                },
                "required": ["nome_arquivo"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_minha_conta",
            "description": (
                "Consulta a conta de um CLIENTE DA BASE pelo CNPJ: contratos ativos, "
                "últimas ordens de serviço e últimas notas fiscais. SÓ use após confirmar "
                "a identidade (CNPJ informado pelo próprio cliente + confirmar o nome da "
                "empresa/condomínio com ele). Nunca mostre dados de conta a terceiros."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cnpj": {"type": "string", "description": "CNPJ do cliente (com ou sem máscara)"},
                },
                "required": ["cnpj"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "abrir_ordem_servico",
            "description": (
                "Abre uma ORDEM DE SERVIÇO (chamado de suporte) para um cliente da base, "
                "direto no sistema. Use quando um cliente identificado relatar problema "
                "(equipamento, câmera, portão, alarme, equipe, serviço). Colete antes: "
                "um resumo do problema e o local. Retorna o número da OS para informar ao cliente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "cnpj": {"type": "string", "description": "CNPJ do cliente (identidade já confirmada)"},
                    "titulo": {"type": "string", "description": "Resumo curto do problema (ex.: 'Câmera da garagem sem imagem')"},
                    "descricao": {"type": "string", "description": "Descrição do problema com detalhes relatados"},
                    "prioridade": {
                        "type": "string",
                        "enum": ["baixa", "normal", "alta", "urgente"],
                        "description": "normal por padrão; alta/urgente se afeta segurança ou operação",
                    },
                    "local": {"type": "string", "description": "Endereço/local do problema (opcional)"},
                },
                "required": ["cnpj", "titulo", "descricao"],
            },
        },
    },
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
                "Registra uma SOLICITAÇÃO de visita (a equipe confirma o horário depois). "
                "Use SÓ quando já tiver endereço, data e horário. Não confirme horário ao cliente — é uma solicitação. "
                "tipo_visita: 'comercial' (novo negócio, orçamento, proposta — vai para a equipe comercial) "
                "ou 'tecnica' (cliente da base com equipamento/serviço, vistoria, manutenção — vai para a equipe de campo)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tipo_visita": {
                        "type": "string",
                        "enum": ["comercial", "tecnica"],
                        "description": "comercial = novo negócio/orçamento; tecnica = suporte/equipamento/vistoria em cliente",
                    },
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


async def _tool_registrar_lead(args: dict, conversation_id: int) -> dict:
    """Atualiza o lead da conversa no CRM com os dados coletados na conversa.

    O lead ja existe (criado pelo webhook na 1a mensagem). Atualiza so os campos
    informados; cnpj e interesse sao acrescentados as notas (historico preservado).
    """
    try:
        async with async_session_factory() as db:
            lead_id = await _resolve_lead_id(db, conversation_id)
            if not lead_id:
                return {"ok": False, "motivo": "lead da conversa nao encontrado"}

            sets, params = [], {"id": lead_id}
            nome = (args.get("nome") or "").strip()
            if nome:
                sets.append("name = :nome")
                params["nome"] = nome[:255]
            empresa = (args.get("empresa") or "").strip()
            if empresa:
                sets.append("company = :empresa")
                params["empresa"] = empresa[:255]
            email = (args.get("email") or "").strip()
            if email and "@" in email:
                sets.append("email = :email")
                params["email"] = email[:255]
            cargo = (args.get("cargo") or "").strip()
            if cargo:
                sets.append("position = :cargo")
                params["cargo"] = cargo[:100]

            notas = []
            cnpj = "".join(c for c in str(args.get("cnpj") or "") if c.isdigit())
            if cnpj:
                notas.append(f"CNPJ: {cnpj}")
            interesse = (args.get("interesse") or "").strip()
            if interesse:
                notas.append(f"Interesse: {interesse[:300]}")
            if notas:
                sets.append(
                    "notes = trim(both E'\\n' from coalesce(notes,'') || E'\\n' || :nota)"
                )
                params["nota"] = " | ".join(notas)

            if not sets:
                return {"ok": True, "info": "nenhum campo novo para registrar"}

            sets.append("updated_at = now()")
            await db.execute(
                text(f"UPDATE leads SET {', '.join(sets)} WHERE id = :id"),  # noqa: S608 — colunas fixas, valores parametrizados
                params,
            )
            await db.commit()
        logger.info("Agente registrar_lead: lead=%s campos=%s", lead_id, list(params.keys()))
        return {"ok": True, "registrado": [k for k in params if k != "id"]}
    except Exception as e:  # noqa: BLE001
        logger.error("Agente registrar_lead: falha conv=%s: %s", conversation_id, e)
        return {"ok": False, "motivo": "nao foi possivel registrar agora"}


async def _tool_consultar_minha_conta(args: dict) -> dict:
    """Conta do cliente da base: contratos ativos + ultimas OS + ultimas NFS-e.

    Identidade: o proprio cliente informa o CNPJ e o agente confirma a razao
    social com ele antes de detalhar (instruido no prompt).
    """
    try:
        cnpj = "".join(c for c in str(args.get("cnpj") or "") if c.isdigit())
        if len(cnpj) != 14:
            return {"erro": "CNPJ invalido"}
        async with async_session_factory() as db:
            cli = (
                await db.execute(
                    text(
                        "SELECT id, name FROM clients "
                        "WHERE regexp_replace(coalesce(document_number,''),'\\D','','g') = :c LIMIT 1"
                    ),
                    {"c": cnpj},
                )
            ).first()
            if not cli:
                return {"cliente_da_base": False, "info": "CNPJ nao encontrado na base de clientes"}
            client_id, client_name = str(cli[0]), cli[1]

            contratos = (
                await db.execute(
                    text(
                        "SELECT contract_number, name, status, monthly_value, "
                        "to_char(start_date,'DD/MM/YYYY'), to_char(end_date,'DD/MM/YYYY') "
                        "FROM contracts WHERE client_id = :cid AND is_active = true "
                        "ORDER BY start_date DESC LIMIT 5"
                    ),
                    {"cid": client_id},
                )
            ).fetchall()
            ordens = (
                await db.execute(
                    text(
                        "SELECT order_number, title, status, priority, to_char(created_at,'DD/MM/YYYY') "
                        "FROM service_orders WHERE client_id = :cid AND ativo = true "
                        "ORDER BY created_at DESC LIMIT 3"
                    ),
                    {"cid": client_id},
                )
            ).fetchall()
            notas = (
                await db.execute(
                    text(
                        "SELECT numero_nfse, to_char(data_emissao,'DD/MM/YYYY'), status, valor_servicos "
                        "FROM nfses WHERE regexp_replace(coalesce(tomador_cpf_cnpj,''),'\\D','','g') = :c "
                        "ORDER BY data_emissao DESC NULLS LAST LIMIT 3"
                    ),
                    {"c": cnpj},
                )
            ).fetchall()
        return {
            "cliente_da_base": True,
            "razao_social": client_name,
            "contratos": [
                {"numero": r[0], "servico": r[1], "status": r[2], "valor_mensal": float(r[3] or 0),
                 "inicio": r[4], "fim": r[5] or "indeterminado"}
                for r in contratos
            ],
            "ordens_servico_recentes": [
                {"numero": r[0], "titulo": r[1], "status": r[2], "prioridade": r[3], "aberta_em": r[4]}
                for r in ordens
            ],
            "notas_fiscais_recentes": [
                {"numero": r[0], "emissao": r[1], "status": r[2], "valor": float(r[3] or 0)}
                for r in notas
            ],
        }
    except Exception as e:  # noqa: BLE001
        logger.error("Agente consultar_minha_conta: %s", e)
        return {"erro": "nao foi possivel consultar agora"}


async def _tool_abrir_ordem_servico(args: dict, conversation_id: int) -> dict:
    """Abre uma OS (chamado) p/ cliente da base. Retorna o numero p/ informar."""
    try:
        cnpj = "".join(c for c in str(args.get("cnpj") or "") if c.isdigit())
        titulo = (args.get("titulo") or "").strip()
        descricao = (args.get("descricao") or "").strip()
        if len(cnpj) != 14 or not titulo or not descricao:
            return {"ok": False, "motivo": "faltam dados (cnpj, titulo, descricao)"}
        prioridade = str(args.get("prioridade") or "normal").lower()
        if prioridade not in ("baixa", "normal", "alta", "urgente"):
            prioridade = "normal"
        agora = datetime.now(timezone.utc) + timedelta(hours=BRT_OFFSET)
        numero = f"OS-{agora.strftime('%Y%m%d')}-{uuid4().hex[:6].upper()}"
        async with async_session_factory() as db:
            cli = (
                await db.execute(
                    text(
                        "SELECT id, name, phone FROM clients "
                        "WHERE regexp_replace(coalesce(document_number,''),'\\D','','g') = :c LIMIT 1"
                    ),
                    {"c": cnpj},
                )
            ).first()
            if not cli:
                return {"ok": False, "motivo": "CNPJ nao encontrado na base — confirme com o cliente"}
            # telefone de quem esta falando (da conversa) p/ contato da OS
            tel = (
                await db.execute(
                    text(
                        "SELECT phone_canonical FROM cwi_message_log "
                        "WHERE chatwoot_conversation_id=:cv AND phone_canonical IS NOT NULL "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"cv": conversation_id},
                )
            ).first()
            await db.execute(
                text(
                    "INSERT INTO service_orders (id, order_number, client_id, title, description, "
                    "status, priority, requester_name, requester_phone, location_address, "
                    "internal_notes, extra_metadata, ativo, created_at, updated_at) "
                    "VALUES (gen_random_uuid(), :num, :cid, :tit, :des, 'pendente', :pri, :rnome, "
                    ":rfone, :loc, :nota, '{\"origem\": \"jose-luis-whatsapp\"}'::jsonb, true, now(), now())"
                ),
                {
                    "num": numero,
                    "cid": str(cli[0]),
                    "tit": titulo[:255],
                    "des": descricao[:2000],
                    "pri": prioridade,
                    "rnome": (cli[1] or "")[:255],
                    "rfone": (tel[0] if tel else None),
                    "loc": (args.get("local") or "")[:500] or None,
                    "nota": f"Aberta pelo Jose Luis (WhatsApp) — conversa {conversation_id}",
                },
            )
            await db.commit()
        logger.info("Agente OS criada: %s cliente=%s conv=%s", numero, cli[1], conversation_id)
        return {"ok": True, "numero_os": numero, "prioridade": prioridade,
                "info": "OS registrada; a equipe tecnica entra em contato para agendar"}
    except Exception as e:  # noqa: BLE001
        logger.error("Agente abrir_ordem_servico: %s", e)
        return {"ok": False, "motivo": "nao foi possivel abrir a OS agora — encaminhe ao suporte_tecnico"}


# Biblioteca de materiais (fotos/apresentacoes/videos) — volume montado do host:
# /opt/conecta-pro/uploads/agent_media -> Jordan adiciona arquivos SEM rebuild.
_MEDIA_DIR = "/app/uploads/agent_media"


def _tool_listar_materiais() -> dict:
    """Lista os arquivos da biblioteca de materiais (nome + tipo + tamanho)."""
    try:
        if not os.path.isdir(_MEDIA_DIR):
            return {"materiais": [], "info": "biblioteca vazia"}
        itens = []
        for f in sorted(os.listdir(_MEDIA_DIR)):
            if f.startswith(".") or f.upper().startswith("README") or f.upper().startswith("COMO_"):
                continue
            path = os.path.join(_MEDIA_DIR, f)
            if os.path.isfile(path):
                itens.append({"nome_arquivo": f, "tamanho_kb": os.path.getsize(path) // 1024})
        return {"materiais": itens} if itens else {"materiais": [], "info": "biblioteca vazia"}
    except Exception as e:  # noqa: BLE001
        logger.error("Agente listar_materiais: %s", e)
        return {"erro": "nao foi possivel listar agora"}


async def _post_public_attachment(conversation_id: int, file_name: str, file_bytes: bytes) -> bool:
    """Posta mensagem PUBLICA com anexo (multipart) — Chatwoot entrega via baileys."""
    base = os.getenv("CHATWOOT_BASE_URL", "http://chatwoot-fazerai:3000").rstrip("/")
    account = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
    token = os.getenv("CHATWOOT_API_TOKEN", "")
    if not token:
        return False
    import mimetypes  # noqa: PLC0415

    ctype = mimetypes.guess_type(file_name)[0] or "application/octet-stream"
    url = f"{base}/api/v1/accounts/{account}/conversations/{conversation_id}/messages"
    try:
        form = aiohttp.FormData()
        form.add_field("message_type", "outgoing")
        form.add_field("private", "false")
        form.add_field("attachments[]", file_bytes, filename=file_name, content_type=ctype)
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                url,
                data=form,
                headers={"api_access_token": token},
                timeout=aiohttp.ClientTimeout(total=60),
            ) as resp,
        ):
            if resp.status in (200, 201):
                return True
            logger.error("Agente anexo: HTTP %s (%s)", resp.status, (await resp.text())[:200])
            return False
    except Exception as e:  # noqa: BLE001
        logger.error("Agente anexo: excecao conv=%s: %s", conversation_id, e)
        return False


async def _tool_enviar_material(args: dict, conversation_id: int) -> dict:
    """Envia um material da biblioteca ao cliente (mensagem publica com anexo)."""
    try:
        nome = os.path.basename(str(args.get("nome_arquivo") or "").strip())  # anti path-traversal
        if not nome:
            return {"ok": False, "motivo": "nome_arquivo vazio"}
        path = os.path.join(_MEDIA_DIR, nome)
        if not os.path.isfile(path):
            return {"ok": False, "motivo": f"material '{nome}' nao encontrado — use listar_materiais"}
        if os.path.getsize(path) > 60 * 1024 * 1024:
            return {"ok": False, "motivo": "arquivo grande demais para WhatsApp"}
        with open(path, "rb") as f:
            dados = f.read()
        ok = await _post_public_attachment(conversation_id, nome, dados)
        if ok:
            logger.info("Agente enviar_material: '%s' enviado conv=%s", nome, conversation_id)
            return {"ok": True, "enviado": nome}
        return {"ok": False, "motivo": "falha no envio — siga o atendimento normalmente"}
    except Exception as e:  # noqa: BLE001
        logger.error("Agente enviar_material: %s", e)
        return {"ok": False, "motivo": "falha no envio"}


async def _post_public_audio(conversation_id: int, texto: str) -> bool:
    """Converte a resposta em VOZ (TTS) e envia como audio publico. Best-effort.

    Usado quando o cliente mandou audio (voz responde voz). Falha -> chamador
    cai para resposta em texto (nunca perde a resposta).
    """
    try:
        from openai import AsyncOpenAI  # noqa: PLC0415

        client = AsyncOpenAI()
        try:
            resp = await client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice="onyx",
                input=texto[:900],
                response_format="mp3",
                instructions=(
                    "Voz masculina brasileira, calorosa e profissional, ritmo natural "
                    "de conversa no WhatsApp. Sotaque brasileiro neutro."
                ),
            )
        except Exception:  # noqa: BLE001 — fallback p/ modelo TTS classico
            resp = await client.audio.speech.create(
                model="tts-1", voice="onyx", input=texto[:900], response_format="mp3"
            )
        audio_bytes = getattr(resp, "content", None)
        if audio_bytes is None:
            audio_bytes = await resp.aread()  # type: ignore[attr-defined]
        if not audio_bytes:
            return False
        return await _post_public_attachment(conversation_id, "resposta.mp3", audio_bytes)
    except Exception as e:  # noqa: BLE001
        logger.error("Agente TTS: falha conv=%s: %s", conversation_id, e)
        return False


async def _ultima_entrada_foi_audio(conversation_id: int) -> bool:
    """True se a ultima mensagem de ENTRADA da conversa veio de audio (voz responde voz)."""
    try:
        async with async_session_factory() as db:
            row = (
                await db.execute(
                    text(
                        "SELECT content FROM cwi_message_log "
                        "WHERE chatwoot_conversation_id=:c AND direction='in' "
                        "AND content IS NOT NULL AND content <> '' "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"c": conversation_id},
                )
            ).first()
        return bool(row and "🎤" in (row[0] or "")[:30])
    except Exception:  # noqa: BLE001
        return False


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
                tipo=(
                    TipoVisita.TECNICA
                    if str(args.get("tipo_visita", "")).lower().startswith("tec")
                    else TipoVisita.COMERCIAL
                ),
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
        if name == "registrar_lead":
            return await _tool_registrar_lead(args, conversation_id)
        if name == "consultar_minha_conta":
            return await _tool_consultar_minha_conta(args)
        if name == "abrir_ordem_servico":
            return await _tool_abrir_ordem_servico(args, conversation_id)
        if name == "listar_materiais":
            return _tool_listar_materiais()
        if name == "enviar_material":
            return await _tool_enviar_material(args, conversation_id)
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
            **_chat_kwargs(os.getenv("OPENAI_AGENT_MODEL", "gpt-4o-mini"), 220, 0.2),
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

        # RELOGIO: o modelo nao sabe a data — sem isto, "amanha"/"semana que vem"
        # viram datas erradas (ex.: visita marcada p/ "24 de outubro" em junho).
        try:
            agora = datetime.now(timezone.utc) + timedelta(hours=BRT_OFFSET)
            dias = ("segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
                    "sexta-feira", "sábado", "domingo")
            meses = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
                     "agosto", "setembro", "outubro", "novembro", "dezembro")
            messages.append({
                "role": "system",
                "content": (
                    f"DATA E HORA ATUAIS (Manaus): {dias[agora.weekday()]}, "
                    f"{agora.day} de {meses[agora.month - 1]} de {agora.year}, "
                    f"{agora.strftime('%H:%M')}. Use SEMPRE esta referência para "
                    f"interpretar 'hoje', 'amanhã', dias da semana e datas de visita."
                ),
            })
        except Exception:  # noqa: BLE001
            pass

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
                **_chat_kwargs(model, max_tokens),
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
                **_chat_kwargs(model, max_tokens),
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


async def _toggle_typing(conversation_id: int, on: bool) -> None:
    """Liga/desliga o status 'digitando...' no Chatwoot (baileys propaga ao WhatsApp).

    Best-effort puro — falha e silenciosamente ignorada (e so cosmetico/naturalidade).
    """
    base = os.getenv("CHATWOOT_BASE_URL", "http://chatwoot-fazerai:3000").rstrip("/")
    account = os.getenv("CHATWOOT_ACCOUNT_ID", "1")
    token = os.getenv("CHATWOOT_API_TOKEN", "")
    if not token:
        return
    url = (
        f"{base}/api/v1/accounts/{account}/conversations/{conversation_id}"
        f"/toggle_typing_status"
    )
    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                url,
                json={"typing_status": "on" if on else "off"},
                headers={"api_access_token": token, "Content-Type": "application/json"},
                timeout=aiohttp.ClientTimeout(total=8),
            ) as resp,
        ):
            if resp.status not in (200, 201, 204):
                logger.debug("Agente typing: HTTP %s conv=%s", resp.status, conversation_id)
    except Exception as e:  # noqa: BLE001
        logger.debug("Agente typing: %s", e)


async def processar_incoming(conversation_id: int, phone: str | None = None) -> None:
    """Entrypoint do BackgroundTask: gera a resposta e entrega conforme AGENT_MODE.

    copilot (default): nota privada (humano aprova) + rascunho no log.
    autonomous: responde PUBLICO ao cliente, COM GUARDS — pula grupos e conversas
    com humano atribuido (nesses casos cai para nota privada). Draft SEMPRE logado.
    """
    # naturalidade: cliente ve "digitando..." enquanto a resposta e gerada
    await _toggle_typing(conversation_id, True)
    try:
        texto = await gerar_resposta(conversation_id)
    finally:
        await _toggle_typing(conversation_id, False)
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
        ok = False
        # voz responde voz: se a ultima entrada foi audio e a resposta e "falavel",
        # entrega em AUDIO (TTS). Falha de TTS/envio -> cai para texto normal.
        if len(texto) <= 600 and await _ultima_entrada_foi_audio(conversation_id):
            ok = await _post_public_audio(conversation_id, texto)
            if ok:
                decision = "autonomous_sent_voice"
        if not ok:
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
