"""F1 — a porta por onde o pedido BARRADO do agente chega ao humano.

O gate no conector (`mcp-server/gate_propose.py`) impede que ação de classe `propose`
execute pelo agente. Sem esta rota, ele apenas recusa: o Jordan não fica sabendo que foi
pedido, e o pedido morre na conversa. Aqui ele vira rascunho INERTE na Central de
Aprovações, onde um humano decide com o dedo.

A regra que sustenta o desenho: **quem aprova não pode ser quem pede.** A versão anterior
do `aceitar_proposta` pedia `confirmar="ACEITAR"` e imprimia essa senha na própria resposta
— para humano no Cowork era aviso; para um modelo que lê a resposta era um degrau ensinando
a subir. Aqui não há degrau: o propositor é o AGENTE e a decisão acontece em outra
superfície, por outra pessoa.

O que a tela mostra é a CONSEQUÊNCIA, não o nome da função. "Aprovar aceitar_proposta?" não
é decisão informada; "gera comissão, move o deal e cria contrato" é.

⚠️ Esta rota NUNCA executa a ação. Ela grava o pedido. A execução roda só na aprovação, pelo
executor registrado — que é o mesmo caminho de qualquer rascunho do sistema.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.auth.dependencies import CurrentActiveUser
from core.database import get_db
from core.logging import logger

router = APIRouter(prefix="/agente", tags=["Agente — aprovações"])

# Ações que mexem em DINHEIRO, em ato de governo ou em coisa IRREVERSÍVEL: 🔴 + OTP.
# Lista explícita: herdar isso de heurística de nome é como o manifesto errou por 54 vezes —
# `aceitar_proposta` gera comissão e não tem nome de dinheiro nenhum.
_VERMELHAS = {
    "aceitar_proposta",          # gera COMISSÃO
    "lancar_diaria",             # valor a pagar
    "gerar_lote_diarias_mes",    # lote de pagamento
    "registrar_custo_recorrente",
    "fechar_folha",
    "calcular_folha_todos",
    "calcular_verbas_rescisorias",
    "fechar_mes_ponto",          # o ponto é a BASE do que se paga
    "ativar_contrato",           # tira do rascunho → passa a faturar
    "aprovar_ferias",            # evento de eSocial
    "concluir_admissao",         # evento de eSocial
    "gerar_parecer_juridico",    # peça jurídica autorada por LLM
    "expurgar_documentos_teste", # apaga — não desfaz
}

# Ações revisadas à mão e julgadas SEM efeito de dinheiro/governo/irreversível: aprováveis
# inline em 🟡. Entrar aqui é uma decisão humana registrada, não um default.
_AMARELAS = {
    "enviar_whatsapp", "enviar_nps", "enviar_proposta", "enviar_proposta_completa",
    "enviar_proposta_whatsapp", "followup_whatsapp", "followup_em_lote",
    "inscrever_em_sequencia", "inscrever_lead_em_sequencia",
    "analisar_processo_juridico", "montar_kit_completo", "buscar_documento",
    "solicitar_ferias",
    # `criar_orcamento` (27/08/2026): GRAVA proposta com valor, e por isso passou pela
    # pergunta em vez de nascer 🔵. É 🟡 e não 🔴 porque (a) não sai da empresa — enviar ao
    # cliente é OUTRA aprovação, já listada aqui; (b) não move dinheiro nem fala com o
    # governo; (c) é reversível: proposta em rascunho se apaga. O que ela tem de sério é
    # o VALOR, e o valor aparece no resumo do rascunho antes de quem aprova clicar.
    "criar_orcamento",
    # `mover_estagio_deal` (27/08/2026): muda o FUNIL e a previsão de receita, por isso
    # passou pela pergunta em vez de nascer 🔵. É 🟡 e não 🔴 porque não sai da empresa,
    # não move dinheiro e é reversível — e porque FECHAR venda foi deliberadamente
    # deixado FORA desta ação.
    "mover_estagio_deal",
    # `resolver_propostas` (27/08/2026): registra o desfecho do que JÁ aconteceu — não
    # cria compromisso novo. É 🟡 porque aceitar vira previsão de receita e o resumo
    # mostra o valor de cada uma antes de alguém clicar. Não cria contrato: isso continua
    # sendo `ativar_contrato`, que é 🔴.
    "resolver_propostas",
    # `enviar_proposta_whatsapp` e `cadastrar_whatsapp` (27/08/2026): a primeira SAI DA
    # EMPRESA e é irreversível — usa ROLES_MONEY como aprovador e NOMEIA o destinatário
    # no resumo. É 🟡 e não 🔴 porque `enviar_proposta` (e-mail), com exatamente o mesmo
    # risco, já é 🟡: tratar canal diferente com grau diferente seria arbitrário.
    # A segunda só grava um número no cadastro.
    "cadastrar_whatsapp",
    # `followup_em_lote` (27/08/2026): MAIOR ALCANCE do CRM — fala com a carteira inteira
    # de uma vez. Ficou 🟡 e não 🔴 porque o rascunho carrega o preview REAL (quantos
    # serão tocados) e o texto integral, então quem aprova vê o alcance antes de clicar.
    # ⚠️ Se algum dia esse preview sumir do resumo, isto vira 🔴.
    # `optout_whatsapp`: protege o cliente de receber mensagem — recusar seria pior.
    "optout_whatsapp",
    # `inscrever_em_sequencia` (27/08/2026): inscrever autoriza a RÉGUA INTEIRA de
    # mensagens automáticas, não uma mensagem. É 🟡 porque o resumo diz quantos passos a
    # sequência tem e que as mensagens sairão sem aprovar uma a uma — o aprovador sabe
    # exatamente o que está liberando.
}


def grau_de(acao: str) -> tuple[str, bool]:
    """(gate, exige_otp). DESCONHECIDA sobe para 🔴 + OTP — fail-closed no GRAU.

    A versão anterior fechava a EXISTÊNCIA em dois lugares (`escopos_da_tool` devolve "" e
    tool sem etiqueta vira `propose`) e deixava o grau aberto: ação nova, que ninguém pôs em
    `_VERMELHAS`, caía em 🟡 e era aprovável inline sem OTP. Medido: `estornar_pagamento`
    passava. Aqui, não declarar custa fricção — que é a pressão para declarar.
    """
    if acao in _VERMELHAS or acao not in _AMARELAS:
        return "🔴", True
    return "🟡", False


@router.get("/aprovacoes")
async def listar_aprovacoes_pendentes(
    current_user: CurrentActiveUser,  # noqa: ARG001
    limite: int = 30,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """O que aguarda decisão humana na Central. Só lê — ler não aprova.

    Lacuna apontada pelo Cowork (12/09/2026): a fila é onde a pessoa decide, e o assistente
    não conseguia nem contar quantos itens havia. Sem contador não dá para verificar se um
    teste poluiu a fila, que era justamente o Bloco 9.
    """
    rs = (await db.execute(text(
        "SELECT id::text, tipo, modulo, titulo, left(coalesce(resumo,''), 300) AS resumo, "
        "       gate, requires_otp, coalesce(origem,'producao') AS origem, "
        "       solicitado_por_nome AS pedido_por, "
        "       to_char(created_at,'DD/MM/YYYY HH24:MI') AS quando "
        "  FROM agent_drafts WHERE status = 'rascunho' "
        " ORDER BY created_at DESC LIMIT :lim"), {"lim": min(limite, 100)})).mappings().all()
    itens = [dict(r) for r in rs]
    return {
        "ok": True, "total": len(itens), "aprovacoes": itens,
        "exigem_otp": sum(1 for i in itens if i.get("requires_otp")),
        # ⚠️ se aparecer origem != producao, é teste que vazou para a fila de quem decide
        "de_teste_ou_ensaio": [i["id"] for i in itens if i["origem"] != "producao"],
    }


@router.post("/log-acesso-sensivel")
async def log_acesso_sensivel(
    current_user: CurrentActiveUser,
    payload: dict = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Registra acesso do assistente a dado pessoal SENSÍVEL — item 3 do Bloco 7 (LGPD).

    Quem, quando, qual ferramenta, qual `request_id`. Consultável depois por quem precisar
    responder "quem olhou o holerite de quem, e por quê".

    ⚠️ Registra a INTENÇÃO, antes de a chamada executar. Tentativa recusada também é acesso
    tentado — e é exatamente o que se procura quando algo dá errado.
    """
    quem = (getattr(current_user, "full_name", None)
            or getattr(current_user, "email", None) or "?")
    # ⭐ 12/09/2026 — A TRILHA DIZIA A PESSOA E OMITIA O AGENTE. O conector público carrega
    # a identidade do Jordan, então todo acesso do assistente ficava gravado como se ele
    # tivesse aberto o holerite com as próprias mãos. Para uma trilha de LGPD isso é pior
    # que registro ausente: ela responde "quem olhou" com um nome errado, e com a chancela
    # de uma tabela de auditoria.
    #
    # O conector SABE quem é (MCP_AGENTE_NOME, MCP_ESCOPO) e agora declara em `origem`. Sem
    # coluna nova e sem migração: `quem` é texto e passa a carregar as duas informações —
    # a pessoa sob cuja credencial o acesso correu E o agente que pediu.
    origem = str(payload.get("origem") or "").strip()[:60]
    if origem:
        quem = f"{quem} (via {origem})"
    await db.execute(text(
        "INSERT INTO agente_acesso_sensivel "
        "  (tool, request_id, argumentos, quem, autorizado_por_concessao) "
        "VALUES (:t, :r, :a, :q, :c)"),
        {"t": str(payload.get("tool") or "")[:80],
         "r": str(payload.get("request_id") or "")[:40],
         "a": str(payload.get("argumentos") or "")[:400],
         "q": quem[:160],
         "c": bool(payload.get("autorizado_por_concessao"))})
    await db.commit()
    return {"ok": True, "registrado": True}


@router.post("/pedir-aprovacao")
async def pedir_aprovacao(
    current_user: CurrentActiveUser,
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Recebe do conector uma ação BARRADA e a grava como rascunho inerte.

    Corpo esperado (montado por `gate_propose.payload_de_aprovacao`):
        acao            nome da ferramenta
        vai_acontecer   lista de consequências, em português
        argumentos      o que o agente ia passar
        classe          read | write_low | propose
    """
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import criar_rascunho

    acao = str(payload.get("acao") or "").strip()
    if not acao:
        raise HTTPException(status_code=400, detail="informe a ação barrada")

    consequencias = [str(c) for c in (payload.get("vai_acontecer") or []) if str(c).strip()]
    if not consequencias:
        # Sem consequência declarada não há aprovação informada — e aprovação não informada
        # é assinatura em papel em branco.
        raise HTTPException(
            status_code=422,
            detail=f"a ação `{acao}` chegou sem consequências declaradas; sem elas o "
                   "aprovador decidiria às cegas")

    # 🔴 26/09/2026 — ARGUMENTO VAZIO É APROVAÇÃO DE NADA, pelo MESMO argumento que já vale
    # para `consequencias` dez linhas acima. Medido: **9 rascunhos `agente_*` com
    # `argumentos: {}`**, quatro deles 🔴 (`excluir_campanha`,
    # `definir_parametros_precificacao`, `aceitar_proposta`,
    # `revisar_justificativa_ponto`), todos em `rascunho`, inexecutáveis por construção —
    # `justificar_ponto` exige `justification_id` e `decisao`, e o rascunho não tem nenhum dos
    # dois. Ficavam parados na fila do Jordan e, ao aprovar, davam "sem executor registrado".
    #
    # ⚠️ E se um executor existisse, seria PIOR: rodaria sem argumento, ou o modelo deduziria
    # os argumentos da prosa. O erro seguro aqui é recusar na entrada.
    #
    # ⚠️ Se alguma ação legítima realmente não tiver argumento, ela passa a devolver 422 com
    # este texto — e isso é melhor que nascer rascunho morto na fila de quem decide.
    if not (payload.get("argumentos") or {}):
        raise HTTPException(
            status_code=422,
            detail=f"a ação `{acao}` chegou sem argumentos; um pedido sem argumento não pode "
                   "ser executado depois de aprovado, então não viro rascunho")

    gate, vermelha = grau_de(acao)

    resumo = "O agente pediu esta ação e NÃO a executou. Se aprovada, ela:\n" + "\n".join(
        f"• {c}" for c in consequencias)

    try:
        r = await criar_rascunho(
            db, current_user,
            tipo=f"agente_{acao}",
            modulo=str(payload.get("modulo") or "ai"),
            titulo=f"Aprovação: {acao}",
            resumo=resumo,
            payload={"acao": acao, "argumentos": payload.get("argumentos") or {},
                     "consequencias": consequencias, "origem": "conector-agente"},
            gate=gate,
            requires_otp=vermelha,
            roles_aprovador=("admin",),
            # idempotência: o agente insistindo na mesma ação não vira fila de rascunhos
            idempotency_key=f"agente:{acao}:{sorted((payload.get('argumentos') or {}).items())}",
        )
    except Exception as e:  # noqa: BLE001
        logger.exception("pedir_aprovacao falhou para %s", acao)
        raise HTTPException(status_code=500, detail=f"não consegui registrar o pedido: {e}") from e

    if isinstance(r, dict) and r.get("erro"):
        raise HTTPException(status_code=422, detail=str(r["erro"]))

    return {
        "ok": True,
        "registrado": True,
        "gate": gate,
        "exige_otp": vermelha,
        "rascunho": (r or {}).get("id") if isinstance(r, dict) else None,
        "message": (f"Pedido de `{acao}` registrado na Central de Aprovações "
                    f"({gate}{' · exige OTP' if vermelha else ''}). "
                    "Nada foi executado — um humano decide."),
    }
