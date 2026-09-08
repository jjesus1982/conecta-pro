"""Orquestrador ESCOPADO por usuário (Peça 3): POST /consultores/chat/consultar.

- admin (diretoria) -> delega ao Orquestrador Executivo (Hermes) já deployado.
- demais -> engine in-backend com tools filtradas por user_modules (belt) + escopo
  posto/self (suspenders). Roda com a identidade do próprio usuário (get_current_active_user).

COMPOSIÇÃO EXPLÍCITA DOS TIERS (lição m5 do review da Task 5):
As tools de POSTO (tools_posto.POSTO_TOOLS) declaram module="operacional" — se o conjunto
do GESTOR fosse montado com `tools_for_modules(user_modules(user))` ingenuamente, elas
ENTRARIAM (com post_ids vazio → "aguardando dado": inofensivo, mas confuso) e, no tier
LÍDER, entrariam DUAS vezes (uma por module="operacional", outra pelo add explícito de
POSTO_TOOLS) → nomes de função DUPLICADOS no schema OpenAI. Por isso o conjunto de MÓDULO
(panoramas org-wide) é montado por `_modulo_tools()`, que exclui as tools posto-scoped. O
tier decide o resto:
  - gestor/dev = _modulo_tools(user_modules) (só panoramas org-wide dos módulos permitidos)
  - líder      = _modulo_tools(user_modules) + POSTO_TOOLS + SELF_TOOLS + justificar
  - clt        = SELF_TOOLS + justificar
(As SELF_TOOLS/justificar têm module="self", fora dos módulos canônicos, então
`tools_for_modules` nunca as devolve — não precisam ser excluídas do conjunto de módulo.)
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import get_current_active_user
from core.auth.module_scope import user_modules
from core.database import get_db
from modules.ai.conversation.services.orquestrador import tools_autoconhecimento  # noqa: F401 — registra `o_que_voce_faz` (F4)
from modules.ai.conversation.services.orquestrador import tools_comercial_doc  # noqa: F401 — registra gera-doc comercial (Fase 6 F1)
from modules.ai.conversation.services.orquestrador import tools_read_crm  # noqa: F401 — registra as 8 consultas READ do CRM (Fase 6 VER)
from modules.ai.conversation.services.orquestrador import tools_read_dp  # noqa: F401 — registra as 8 consultas READ do DP/RH (Fase 6 VER)
from modules.ai.conversation.services.orquestrador import tools_read_financeiro  # noqa: F401 — registra as 8 consultas READ do Financeiro (Fase 6 VER)
from modules.ai.conversation.services.orquestrador import tools_read_fiscal  # noqa: F401 — registra as 8 consultas READ do Fiscal (Fase 6 VER, read-only, diretoria)
from modules.ai.conversation.services.orquestrador import tools_read_ged  # noqa: F401 — registra as 5 consultas READ do GED/GEDEON (Fase 6 VER, read-only, fecha o balde VER)
from modules.ai.conversation.services.orquestrador import tools_read_juridico  # noqa: F401 — registra as 4 consultas READ do Jurídico (Fase 6 VER, read-only, fecha o balde VER)
from modules.ai.conversation.services.orquestrador import tools_read_operacional  # noqa: F401 — registra as 8 consultas READ do Operacional (Fase 6 VER, read-only)
from modules.ai.conversation.services.orquestrador import tools_acao_crm  # noqa: F401 — registra as 3 ações FAZER do CRM (Fase 6 FAZER, propor->aprovar)
from modules.ai.conversation.services.orquestrador import tools_acao_dp  # noqa: F401 — registra a ação FAZER do DP (solicitar_ferias) (Fase 6 FAZER-2, propor->aprovar)
from modules.ai.conversation.services.orquestrador import tools_acao_ged  # noqa: F401 — registra a ação FAZER do GED (registrar_evento_kit) (Fase 6 FAZER-2, propor->aprovar)
from modules.ai.conversation.services.orquestrador import tools_acao_financeiro  # noqa: F401 — registra agir_financeiro (registrar_custo_recorrente) (Fase 6 FAZER-3, propor->aprovar)
from modules.ai.conversation.services.orquestrador import tools_financeiro_doc  # noqa: F401 — registra gera-doc financeiro (Fase 6 F3)
from modules.ai.conversation.services.orquestrador import tools_acao_fiscal  # noqa: F401 — registra a ação FAZER do Fiscal (baixar_obrigacao) — propor->aprovar, gate 🟡
from modules.ai.conversation.services.orquestrador import tools_fiscal_calc  # noqa: F401 — registra as 4 calculadoras fiscais (DAS, Lucro Real, comparativo, retenções) — chamam o MESMO controller da tela
from modules.ai.conversation.services.orquestrador import tools_fiscal_doc  # noqa: F401 — registra relatório NFS-e no chat (Fase 6 F8)
from modules.ai.conversation.services.orquestrador import tools_operacional_doc  # noqa: F401 — registra gera-doc operacional (Fase 6 F4)
from modules.ai.conversation.services.orquestrador import tools_rh_doc  # noqa: F401 — registra holerite no chat (Fase 6 F6)
from modules.ai.conversation.services.orquestrador import tools_modulos  # noqa: F401 — registra as tools de módulo
from modules.ai.conversation.services.orquestrador.acoes import (  # noqa: F401 — registra as 6 tools de ação 5.4 (register() a nível de módulo)
    onda_a,
    onda_b,
    onda_c,
)
from modules.ai.conversation.services.orquestrador.engine import OrqScope, run_engine
from modules.ai.conversation.services.orquestrador.agir_dispatcher import montar_acao_dispatchers
from modules.ai.conversation.services.orquestrador.read_dispatcher import montar_read_dispatchers
from modules.ai.conversation.services.orquestrador.tool_registry import ToolDef, tools_for_modules
from modules.ai.conversation.services.orquestrador.tools_ponto import JUSTIFICAR_TOOL
from modules.ai.conversation.services.orquestrador.tools_posto import POSTO_TOOLS
from modules.ai.conversation.services.orquestrador.tools_rh_doc import RH_SELF_TOOLS
from modules.ai.conversation.services.orquestrador.tools_self import SELF_TOOLS
from modules.operacional.scope import get_operational_scope

# Fase 6 VER: após os 3 tools_read_* importados (que fazem registrar_read no import), colapsa
# as ops de leitura em 1 ToolDef consultar_<modulo> por módulo (crm/dp/financeiro). Idempotente.
montar_read_dispatchers()

# Fase 6 FAZER: após tools_acao_crm importado (registrar_acao no import), colapsa as ações
# reversíveis em 1 ToolDef agir_<modulo> por módulo (agir_crm). Idempotente.
montar_acao_dispatchers()

router = APIRouter(prefix="/consultores/chat", tags=["Consultores — Chat escopado"])

# Constituição do orquestrador — funde a SOUL.md do Hermes (regras inegociáveis + contexto
# do negócio + estilo) com o modelo "age-first" da Central de Rascunhos. Fonte única de
# personalidade do chat unificado (ver project_unificacao_hermes_chat_flutuante).
_SYSTEM_BASE = (
    "Você é o ORQUESTRADOR do Conecta PRO — o ERP de segurança patrimonial (vigilância/portaria/"
    "segurança eletrônica) da Conecta Mais — agindo para ESTE usuário, com a identidade real dele. "
    "Você não só responde: AGE. "
    "REGRAS INEGOCIÁVEIS: "
    "(1) SÓ DADO REAL — responda a partir das tools; cite a fonte quando fizer sentido. Se o dado não "
    "existir/vier vazio, diga 'aguardando dado'. NUNCA invente, estime ou preencha com placeholder. "
    "(2) JORDAN é a fonte da verdade organizacional; divergência entre módulos = aponte e pergunte, não "
    "decida sozinho. "
    "(3) AGE POR RASCUNHO — seu padrão para pedido acionável (criar/gerar/registrar/enviar/calcular/ativar) "
    "é CRIAR UM RASCUNHO via agir_<modulo>: inerte, vai para a Central de Aprovações, onde o humano aprova e "
    "SÓ ENTÃO efetiva. Não diga 'não posso' para o que você pode rascunhar — rascunhe e avise. Para CONSULTAR, "
    "use consultar_<modulo>; combine leitura + anexo quando mandarem um documento (busque o outro lado nas "
    "tools antes de dizer que falta base). "
    "(4) DINHEIRO QUE SAI e eSOCIAL = você só PROPÕE; a execução exige OTP humano na aprovação, fora de você. "
    "Nunca tente pagar/transmitir. "
    "(5) READ-ONLY: Operacional (postos/escalas/alocações) e o dossiê Jurídico são curados à mão — só leitura; "
    "divergência vira relatório, nunca alteração. "
    "(6) LGPD: dado pessoal só com finalidade; nunca exponha credencial/segredo. "
    "(7) Erro técnico de tool ≠ falta de permissão — não transforme bug em 'você não tem acesso'. "
    "CONTEXTO: dois CNPJs — Conecta Eletrônica (segurança eletrônica + portaria remota) e Conecta "
    "Patrimonial (mão de obra humanizada); escope pela empresa certa. Base trabalhista = CCT SINDECOMPRESTS "
    "(somos AGENTES DE PORTARIA, não vigilância); nunca invente valor legal. "
    "ESTILO: objetivo, português do Brasil, cite a fonte, honesto quando faltar dado."
)

# As 8 lentes (consultores C-level) da SOUL.md → personas do chat único. Cada lente lê o
# MESMO dado real sob um ângulo; nenhuma autoriza inventar dado nem burlar o gate de dinheiro.
_LENTES = {
    "ceo": "\n\nLENTE ATIVA — CEO: visão executiva consolidada (diagnóstico / números-chave com fonte / riscos / recomendações). Separe por CNPJ quando for financeiro/tributário; 'GRUPO' só como soma explícita.",
    "cfo": "\n\nLENTE ATIVA — CFO: saldo por CNPJ (Inter=Eletrônica, Cora=Patrimonial), recebíveis/pagáveis, conciliação, aging, inadimplência. Só leitura/relatório — nunca paga/transfere; ação decorrente vira rascunho.",
    "fiscal": "\n\nLENTE ATIVA — FISCAL: apuração por CNPJ e regime vigente (Eletrônica=Lucro Real; Patrimonial=Simples Anexo III, DAS integral, INSS em dobro enquanto a liminar não deferir — nunca descrever como zerado). Cruze NFS-e x período; sinalize nota no CNPJ errado.",
    "chro": "\n\nLENTE ATIVA — DP/RH: folha, ponto, admissão/rescisão, férias, eSocial — sobre dado real de hr_payslips/ponto. Cálculos e atos viram rascunho; eSocial/dinheiro só propor.",
    "juridico": "\n\nLENTE ATIVA — JURÍDICO: processos e contratos são READ-ONLY (dossiê curado à mão). Aponte risco/divergência como relatório; nunca altere.",
    "comercial": "\n\nLENTE ATIVA — COMERCIAL: funil, propostas, contratos, cobrança. Ações (criar/enviar proposta, criar/ativar contrato, cobrar) viram rascunho na Central.",
    "operacional": "\n\nLENTE ATIVA — OPERACIONAL: postos/escalas/alocações são READ-ONLY. Posto descoberto → proponha substituição (rascunho), respeitando CCT/12x36; sem candidato elegível, reporte como fato.",
    "ged": "\n\nLENTE ATIVA — GED: documentos, kits, classificação. Nenhum documento se perde nem duplica; ações viram rascunho.",
}
# Entrada da persona (slug do /redesign OU nome da lente) → agente/lente.
_PERSONA_AGENTE = {
    "financeiro": "cfo", "cfo": "cfo", "crm": "comercial", "comercial": "comercial",
    "juridico": "juridico", "fiscal": "fiscal", "operacional": "operacional",
    "departamento-pessoal": "chro", "dp": "chro", "gestao-de-pessoas": "chro", "rh": "chro", "chro": "chro",
    "ged": "ged", "documentos": "ged", "ceo": "ceo", "executivo": "ceo", "aprovacoes": "ceo",
}

# Nudge SÓ do fluxo de anexo: o usuário mandou um documento/foto e muitas vezes quer COMPARAR
# com dados do ERP. O modelo tende a desistir ("não tenho a segunda base"); aqui lembramos que
# ele TEM as tools de consulta e deve buscar o outro lado antes de pedir o dado ao usuário.
_ANEXO_NUDGE = (
    " O usuário ANEXOU um documento/foto. Você TEM ferramentas de consulta ao ERP "
    "(consultar_dp, consultar_financeiro, consultar_crm, consultar_fiscal, etc.). Se a tarefa pede "
    "COMPARAR, CONCILIAR ou CONFERIR o anexo contra dados do sistema (folha, DRE, contratos, NFS-e…), "
    "CHAME as tools para buscar o outro lado ANTES de dizer que falta base — não peça ao usuário um "
    "dado que você mesmo pode obter. Ex.: folha por competência = consultar_dp com consulta='folha_resumo' "
    "e filtros {mes, ano}. Só declare 'aguardando dado' se a tool retornar vazio de fato."
)


class ConsultarIn(BaseModel):
    pergunta: str = Field(..., min_length=3, max_length=2000)
    persona: str | None = Field(None, max_length=40)  # lente/slug ativo (ex.: 'financeiro'→CFO)
    # Modo voz: a resposta vai ser OUVIDA, não lida. Texto longo em voz alta é insuportável —
    # o ouvinte não pode "pular parágrafo". Encurta e tira formatação que não se lê bem.
    voz: bool = False


def _modulo_tools(mods: set[str]) -> list[ToolDef]:
    """Panoramas org-wide dos módulos permitidos (belt), EXCLUINDO as tools escopadas
    (posto/self/cliente) que possam carregar um module canônico (ex.: as posto-scoped
    declaram module="operacional" mas pertencem ao tier LÍDER, não ao gestor). O filtro é
    ESTRUTURAL por scope_kind=="org" — pega qualquer tool posto/self/cliente futura sem
    depender de uma lista de nomes (m13)."""
    return [t for t in tools_for_modules(mods) if t.scope_kind == "org"]


async def _resolver_tier_e_tools(db: AsyncSession, user) -> tuple[OrqScope, list[ToolDef]]:
    """Tools do usuário + a de AUTOCONHECIMENTO (F4), em TODOS os tiers.

    Somada aqui, num ponto só, e não nos quatro `return` abaixo: capacidade que precisa ser
    lembrada em cada ramo é a que fica de fora do ramo novo. Ela não amplia alcance nenhum —
    lê o registro vivo e descreve o que o resolvedor já devolveu, inclusive quando devolveu
    nada (o tier sem escopo continua honesto: ele diz que não alcança).
    """
    from modules.ai.conversation.services.orquestrador.tool_registry import get_tool  # noqa: PLC0415

    scope, tools = await _resolver_tier_e_tools_base(db, user)
    auto = get_tool("o_que_voce_faz")
    return scope, ([*tools, auto] if auto is not None else tools)


async def _resolver_tier_e_tools_base(db: AsyncSession, user) -> tuple[OrqScope, list[ToolDef]]:
    """Decide o tier (gestor/líder/clt) e monta o conjunto de tools escopadas.
    (admin é tratado antes, na rota — delega ao Hermes.)"""
    mods = user_modules(user)
    op = await get_operational_scope(current_user=user, db=db)
    emp = op.employee_id

    # LÍDER: escopado a postos (scope.py já força isso mesmo p/ role admin). É CLT + posto.
    if not op.all_posts and op.post_ids:
        tools = _modulo_tools(mods) + list(POSTO_TOOLS) + list(SELF_TOOLS) + list(RH_SELF_TOOLS) + [JUSTIFICAR_TOOL]
        return OrqScope(tier="lider", employee_id=emp, post_ids=op.post_ids), tools

    # GESTOR/DEV: módulos org-wide (nada de posto/self privilegiado).
    if op.is_manager or mods:
        return OrqScope(tier="gestor", is_manager=True, all_posts=True), _modulo_tools(mods)

    # CLT: só sobre si + a ação de justificar ponto.
    if emp:
        return OrqScope(tier="clt", employee_id=emp), list(SELF_TOOLS) + list(RH_SELF_TOOLS) + [JUSTIFICAR_TOOL]

    # Sem escopo algum: chat honesto sem tools.
    return OrqScope(tier="clt", employee_id=None), []


_MODULO_AGENTE = {
    "financeiro": "cfo", "fiscal": "fiscal", "juridico": "juridico",
    "ged": "ged", "crm": "comercial", "operacional": "operacional", "dp": "chro",
}
_AGENTE_MODULO = {agente: modulo for modulo, agente in _MODULO_AGENTE.items()}


def _lente_permitida(user, agente: str) -> bool:
    """A lente pedida pelo cliente é do módulo do usuário?

    Achado de 11/08/2026 (oráculo RBAC nº 8): `persona` vinha do payload e ninguém a
    checava. O belt de tools segurava o DADO — um CLT nunca recebeu tool de financeiro —
    mas a lente injeta o KB curado daquele domínio no system prompt. Bastava um porteiro
    mandar `persona: "financeiro"` para levar o briefing do CFO: estrutura societária,
    CNPJs, bancos por empresa, regime tributário, playbook de fechamento.

    Escopo é do servidor, nunca do payload. `ceo` é consolidada e não tem módulo próprio:
    só admin. Negar aqui não dá erro — cai no default (conhecimento dos módulos do próprio
    usuário), que é o comportamento de quem não pede lente nenhuma.
    """
    if (getattr(user, "role", "") or "").lower() == "admin":
        return True
    modulo = _AGENTE_MODULO.get(agente)
    return bool(modulo) and modulo in user_modules(user)


_ESTILO_VOZ = (
    "\n\n## MODO VOZ — REGRA QUE SOBREPÕE AS DEMAIS DE FORMATO\n"
    "A resposta será OUVIDA, não lida. Quem ouve não pode pular parágrafo nem reler.\n"
    "\n"
    "**NUNCA LEIA LISTAS.** Se a resposta tem 2 ou mais itens (pessoas, postos, lançamentos),\n"
    "diga só o TOTAL e ofereça a tela. Isto vale mesmo que o usuário pareça pedir a lista.\n"
    "  CERTO:  'São doze ausentes hoje. Quer ver a lista na tela?'\n"
    "  ERRADO: 'Os ausentes são Fulano, Beltrano, Cicrano...' ← nunca faça isso\n"
    "Ler nomes de pessoas em voz alta expõe dado pessoal a quem estiver por perto e ninguém\n"
    "memoriza doze nomes falados. Se o usuário insistir num nome específico, aí sim diga UM.\n"
    "\n"
    "**TAMANHO — REGRA DE OURO: no máximo 25 PALAVRAS na resposta inteira.**\n"
    "Tem que caber numa respiração. Se não couber, você está explicando demais: corte e ofereça\n"
    "o resto ('quer que eu detalhe?'). Isto vale INCLUSIVE para pergunta aberta.\n"
    "  CERTO (12 palavras): 'Temos nove postos ativos, sete cobertos e dois descobertos. Quer ver quais?'\n"
    "  ERRADO: 'O módulo operacional é o cérebro da operação: ele mostra em tempo real...' ← aula, não resposta\n"
    "Pergunta aberta ('me fala sobre X') se responde em UMA frase + pergunta:\n"
    "  'Ele controla postos, escalas e presença em tempo real. Quer ver alguma parte?'\n"
    "\n"
    "- Vá direto ao número/fato. Sem preâmbulo ('claro', 'com certeza', 'vou verificar').\n"
    "- Não repita a pergunta nem diga de onde veio o dado ('segundo o panorama') — só o fato.\n"
    "- Nada de markdown, bullet, tabela, link ou citação de fonte — não se lê em voz alta.\n"
    "- Números por extenso quando ajudar a ouvir ('nove postos', 'mil e duzentos reais').\n"
    "- Pode terminar com UMA pergunta curta ou sugestão de próximo passo, se for útil.\n"
    "- Se faltar dado, diga em uma frase o que falta. Não invente.\n"
)


def _hoje_para_o_prompt() -> str:
    """Que dia é hoje, em Manaus. Sem isto o modelo deduz a data do treino.

    Medido em 24/08/2026, pelo caminho real do chat: um porteiro com 91 batidas no mês
    perguntou "quantas horas eu fiz esse mês" e recebeu "nenhuma batida consta no sistema
    para você" — porque o modelo chamou `meu_ponto` com mes=7, ano=**2025**. A tool estava
    certa (sem argumento devolve 8/2026 → 91); o argumento é que veio de um calendário
    imaginário. Isso é pior que recusar: é um "não existe" confiante sobre o dado de alguém.

    Dia civil de MANAUS, regra canônica de TZ — nunca `utcnow().date()`.
    """
    from datetime import datetime  # noqa: PLC0415
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    d = datetime.now(ZoneInfo("America/Manaus"))
    return (
        f"\n\nHOJE é {d.strftime('%d/%m/%Y')} (horário de Manaus). "
        f"'hoje' = {d.strftime('%d/%m/%Y')}; 'este mês' = {d.month:02d}/{d.year}; "
        f"'mês passado' = {(d.month - 1) or 12:02d}/{d.year if d.month > 1 else d.year - 1}. "
        "NUNCA deduza a data do seu treinamento — ela está errada. Quando a tool aceitar "
        "mês/ano e a pergunta for sobre o período corrente, OMITA os dois: o padrão da tool já "
        "é o mês vigente de Manaus. Só informe mês/ano quando a pessoa pedir outro período."
    )


def _system_for(user, pergunta: str, persona: str | None = None, voz: bool = False) -> str:
    """Constituição + persona. Se uma LENTE for pedida (persona = slug do /redesign ou nome da
    lente), injeta a lente ativa + o conhecimento COMPLETO dela; senão, o conhecimento dos
    módulos do usuário (cap 2). Fail-open."""
    from modules.ai.conversation.services.consultor_conhecimento_service import contexto_para_prompt
    sp = _SYSTEM_BASE + _hoje_para_o_prompt()
    agente = _PERSONA_AGENTE.get((persona or "").strip().lower())
    if agente and not _lente_permitida(user, agente):
        agente = None  # lente fora do escopo do usuário → default, não erro (ver _lente_permitida)
    if agente:
        sp += _LENTES.get(agente, "")
        sp += contexto_para_prompt(agente, pergunta, max_secoes=6)  # completo p/ a persona ativa
    else:
        mods = user_modules(user)
        for ag in list({_MODULO_AGENTE[m] for m in mods if m in _MODULO_AGENTE})[:2]:
            sp += contexto_para_prompt(ag, pergunta)
    if voz:
        sp += _ESTILO_VOZ   # por último: manda no formato, não no conteúdo
    return sp


# Restaurada em 08/09/2026: sem chamador de tela, mas é o endpoint-amostra do gate RBAC (test_oraculos_rbac).
@router.post("/consultar")
async def consultar(
    payload: ConsultarIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    pergunta = payload.pergunta.strip()
    # UNIFICAÇÃO (colapsa o antigo desvio do admin p/ o Hermes-gateway): o dono passa pelo MESMO
    # motor único (run_engine), com a persona EXECUTIVO (lente CEO) por padrão — a menos que uma
    # persona/rota específica seja pedida. Cérebro é gpt-5 nos dois; aqui ganha identidade real +
    # rascunhos + o alcance in-process (U2). Ver project_unificacao_hermes_chat_flutuante.
    is_admin = (getattr(user, "role", "") or "").lower() == "admin"
    persona = payload.persona or ("ceo" if is_admin else None)
    scope, tools = await _resolver_tier_e_tools(db, user)
    out = await run_engine(
        db, user, scope, tools, pergunta,
        system_prompt=_system_for(user, pergunta, persona), origem="consultor_escopado",
    )
    if is_admin:
        out["tier"] = "diretoria"
    return out


@router.post("/executar")
async def executar(
    payload: ConsultarIn,
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """Chat que ENTREGA documentos, para TODOS (admin incluso). Sem o desvio p/ Hermes:
    admin/gestor recebe as tools org-wide de todos os módulos (inclui os gera-doc), cada
    tool ainda aplica seu próprio gate/RBAC pela identidade real. O return traz `documentos`."""
    pergunta = payload.pergunta.strip()
    persona = payload.persona or (("ceo") if (getattr(user, "role", "") or "").lower() == "admin" else None)
    scope, tools = await _resolver_tier_e_tools(db, user)
    return await run_engine(
        db, user, scope, tools, pergunta,
        system_prompt=_system_for(user, pergunta, persona, voz=payload.voz), origem="consultor_executar",
    )


@router.post("/executar-arquivo")
async def executar_arquivo(
    arquivo: UploadFile = File(...),
    pergunta: str = Form(""),
    persona: str = Form(""),
    db: AsyncSession = Depends(get_db),
    user=Depends(get_current_active_user),
):
    """Chat com ANEXO: lê PDF/DOCX/TXT (texto) ou foto (vision) e interpreta, com as MESMAS
    tools/gate/escopo do /executar. Foto vira image_url; documento vira texto na pergunta."""
    from modules.ai.conversation.services.orquestrador.anexos import (
        eh_imagem, extrair_texto_arquivo, imagem_data_url,
    )
    data = await arquivo.read()
    if len(data) > 15 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Arquivo muito grande (máx 15MB).")
    nome = arquivo.filename or "anexo"
    base = (pergunta or "").strip()
    imagens: list[str] = []
    if eh_imagem(nome):
        imagens.append(imagem_data_url(nome, data))
        pergunta_final = base or "Analise e interprete esta imagem/foto anexada; descreva o que for relevante."
    else:
        texto = extrair_texto_arquivo(nome, data)
        if len(texto) < 10:
            raise HTTPException(
                status_code=422,
                detail="Não consegui extrair texto do arquivo (PDF escaneado? Tente mandar como foto/imagem).",
            )
        instr = base or "Analise e interprete este documento anexado; aponte o que for relevante."
        pergunta_final = f'{instr}\n\n[Documento anexado: {nome}]\n"""\n{texto}\n"""'

    persona = persona or ("ceo" if (getattr(user, "role", "") or "").lower() == "admin" else "")
    scope, tools = await _resolver_tier_e_tools(db, user)
    return await run_engine(
        db, user, scope, tools, pergunta_final,
        system_prompt=_system_for(user, pergunta_final, persona) + _ANEXO_NUDGE,
        origem="consultor_executar_arquivo",
        max_tokens=2400,  # comparação/conciliação de anexo gera resposta longa (1200 cortava)
        imagens=imagens or None,
    )
