"""Central de Rascunhos — primitiva `criar_rascunho` + registry de executores.

Diferença-chave para `base.propor`: aqui o PROPOSITOR é o AGENTE, não o usuário. O
`solicitado_por` é só trilha e NÃO é excluído dos aprovadores → o usuário que pediu no
chat pode ser o mesmo que aprova na Central (é o modelo "o agente cria, eu aprovo"), o
que dissolve o fail-closed de admin único. O controle continua real: rascunho inerte +
revisão humana + OTP para dinheiro/eSocial na aprovação.

`criar_rascunho` NUNCA executa: só grava um AgentDraft (status='rascunho'), audita e toca
o sino ao aprovador. A execução do serviço de domínio roda SÓ na aprovação, via o executor
registrado por `registrar_executor(tipo, fn)` e disparado por `executar_rascunho` (chamado
pelo controller de aprovação, que faz o gate de OTP antes).
"""
from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from typing import Any

from core.logging import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.ai.conversation.models.agent_draft import AgentDraft
from modules.ai.conversation.services.garantia import agent_audit
from modules.notifications.proativo import entrega

from .base import GATES

#: tipo (str) -> executor. fn(db, aprovador_user, payload:dict) -> entity_ref:str|None.
#: O executor chama o SERVIÇO DE DOMÍNIO REAL — é o único ponto que efetiva.
EXECUTORES: dict[str, Callable[[AsyncSession, Any, dict], Awaitable[Any]]] = {}


def _garantir_executores() -> None:
    """Importa os módulos que REGISTRAM executores, no processo que for.

    ⚠️ 31/08/2026 — medido: `EXECUTORES` tinha **0** entradas no processo do backend, e o
    único lugar do repositório que importava `tools_acao_crm` eram os ORÁCULOS. Eles
    importavam no topo, viam tudo registrado e passavam verde; a Central falhava com "sem
    executor registrado" em TODO rascunho de CRM. O Jordan tentava aprovar a proposta da
    VEGA desde sexta.

    É o irmão exato do buraco de `_READ_OPS` consertado em 28/08 — consertei o registro de
    LEITURA e deixei o de EXECUÇÃO com o mesmo defeito, no mesmo módulo.

    A guarda mora AQUI, e não em cada caminho que aprova, porque aqui passa toda aprovação:
    um guard na função compartilhada é menor que um import em cada chamador — e um chamador
    novo amanhã nasceria quebrado de novo.
    """
    import importlib  # noqa: PLC0415
    import sys  # noqa: PLC0415

    nome = "modules.ai.conversation.services.orquestrador.tools_acao_crm"
    try:
        antes = len(EXECUTORES)
        mod = importlib.import_module(nome)
        # ⚠️ 31/08/2026, segunda vez no mesmo dia: um `import` de módulo JÁ carregado é
        # no-op. Depois de um `docker cp` o processo continua com a versão antiga em
        # `sys.modules`, e um executor novo nunca se registra — a Central falha com "sem
        # executor" enquanto um `python3` recém-aberto jura que está tudo certo. Foi
        # exatamente assim que eu verifiquei o processo errado, duas vezes.
        #
        # Se o import não acrescentou nada E o módulo já estava carregado, o arquivo em
        # disco pode ser mais novo que o objeto em memória: recarrega. Só nesse caso —
        # reload por rotina seria efeito colateral sem motivo.
        if len(EXECUTORES) == antes and nome in sys.modules:
            importlib.reload(mod)
            if len(EXECUTORES) > antes:
                logger.warning("executores recarregados do disco (+%d) — o processo estava "
                               "com uma versão antiga de %s", len(EXECUTORES) - antes, nome)
    except Exception:  # noqa: BLE001 — import não pode derrubar a aprovação
        logger.exception("não consegui registrar os executores de domínio")


def registrar_executor(tipo: str, fn: Callable[[AsyncSession, Any, dict], Awaitable[Any]]) -> None:
    EXECUTORES[tipo] = fn


# Quem responde pelo FINANCEIRO. Regra do Jordan: é dele e da Pyetra — o role
# 'admin' cru inclui conta genérica (admin@), robô (mcp-service@) e a conta
# pessoal duplicada da mesma pessoa, virando 5 destinatários para o que é de 2.
_FINANCEIRO_PADRAO = "jjesus@conectamais.pro,pjesus@conectamais.pro"
_MODULOS_FINANCEIROS = ("financeiro", "financial")


def _e_financeiro(modulo: str, tipo: str) -> bool:
    """Rascunho de dinheiro (por módulo OU por prefixo do tipo)."""
    m = (modulo or "").strip().lower()
    t = (tipo or "").strip().lower()
    return m in _MODULOS_FINANCEIROS or t.startswith(("financeiro_", "financial_"))


async def _somente_financeiro(db: AsyncSession, user_ids: list[str]) -> list[str]:
    """Filtra os aprovadores já resolvidos, deixando só quem responde pelo
    financeiro. Env `CONECTA_FINANCEIRO_EMAILS` (csv) sobrepõe o padrão.
    É FILTRO, não fonte: quem não passou no role nunca entra por aqui."""
    if not user_ids:
        return []
    permitidos = [e.strip().lower() for e in os.getenv(
        "CONECTA_FINANCEIRO_EMAILS", _FINANCEIRO_PADRAO).split(",") if e.strip()]
    if not permitidos:
        return user_ids
    rows = (await db.execute(text(
        "SELECT id::text FROM users WHERE id::text = ANY(:ids) "
        "  AND lower(coalesce(email,'')) = ANY(:emails)"),
        {"ids": list(user_ids), "emails": permitidos})).fetchall()
    return [r[0] for r in rows]


async def criar_rascunho(
    db: AsyncSession,
    user,
    *,
    tipo: str,
    modulo: str,
    titulo: str,
    resumo: str,
    payload: dict[str, Any],
    gate: str,
    requires_otp: bool,
    roles_aprovador: tuple[str, ...],
    empresa_id: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Grava um rascunho inerte e o entrega ao aprovador. NUNCA executa."""
    if gate not in GATES:
        return {"erro": f"gate inválido {gate!r} — recusado (fail-closed)"}
    if not roles_aprovador:
        return {"erro": "sem aprovador declarado — rascunho recusado (fail-closed)"}

    # Idempotência: mesma key com rascunho vivo (sino) → não duplica.
    #
    # ⚠️ "VIVO" TEM DE INCLUIR O RASCUNHO, NÃO SÓ A NOTIFICAÇÃO. A chave mora em
    # `communication_notifications`, e o rascunho em `agent_drafts` — duas tabelas. Quando o
    # rascunho é apagado e a notificação fica (foi o que a limpeza de um oráculo meu fez em
    # 25/08/2026), esta consulta seguia devolvendo `duplicado=True` com um `draft_id` que NÃO
    # EXISTE. A tool respondia "já existe um rascunho idêntico", o usuário via sucesso, e nada
    # era criado — **para sempre**, porque a chave nunca mais liberava.
    #
    # Sucesso vazio de novo, com outra roupa: 200, mensagem plausível, e zero efeito.
    if idempotency_key:
        # A chave mora no PRÓPRIO rascunho (payload._idem) e "vivo" = status 'rascunho'. A versão
        # anterior procurava a chave no aviso do sino: quando o aviso não existia (origem cortada,
        # aviso encerrado, entrega que deduplica pela mesma chave), nada era encontrado e o beat
        # de 5 min do RiskMonitor criou 9 rascunhos idênticos em 40 min (07/09/2026).
        ja = (await db.execute(text(
            "SELECT id FROM agent_drafts WHERE status = 'rascunho' "
            "AND payload->>'_idem' = :k ORDER BY created_at LIMIT 1"),
            {"k": idempotency_key})).scalar()
        if ja:
            return {"status": "rascunho", "duplicado": True, "tipo": tipo,
                    "draft_id": str(ja),
                    "mensagem": "Já existe um rascunho idêntico aguardando aprovação."}

    # Aprovadores por role (SEM excluir o solicitante — propositor = agente).
    aprovadores = await entrega.resolver_usuarios_por_roles(db, roles_aprovador)
    # Módulo financeiro NÃO segue o role 'admin' cru: role admin inclui conta
    # genérica (admin@), robô (mcp-service@) e conta pessoal duplicada da mesma
    # pessoa — 5 destinatários para o que é de 2. Regra do Jordan: financeiro é
    # dele e da Pyetra. Allowlist por e-mail, configurável, aplicada como FILTRO
    # (nunca amplia o que o role já autorizou).
    if _e_financeiro(modulo, tipo):
        aprovadores = await _somente_financeiro(db, aprovadores)
    if not aprovadores:
        return {"erro": "nenhum aprovador ativo para este tipo — rascunho recusado (fail-closed)"}

    solicitante = getattr(user, "id", None)
    try:
        draft = AgentDraft(
            tipo=tipo, modulo=modulo, titulo=titulo, resumo=resumo,
            payload={**(payload or {}), **({"_idem": idempotency_key} if idempotency_key else {})},
            status="rascunho", gate=gate,
            requires_otp=bool(requires_otp), roles_aprovador=list(roles_aprovador),
            solicitado_por=solicitante,
            solicitado_por_nome=getattr(user, "nome", None) or getattr(user, "name", None),
            empresa_id=empresa_id,
        )
        db.add(draft)
        await db.flush()  # obtém draft.id
        draft_id = str(draft.id)

        await agent_audit.registrar_proposta_acao(
            db, origem="central_rascunhos",
            tool=f"criar_rascunho:{tipo}", args=payload or {}, dominio=modulo, gate=gate,
            entity_type="agent_draft", entity_id=draft_id,
            aprovadores=aprovadores, proposto_por=str(solicitante),
            trace_id=f"central.{modulo}",
        )

        await entrega.enviar_individual(
            db, user_ids=aprovadores, title=titulo,
            body=(resumo or "") + "  → aprove na Central de Aprovações.",
            familia=modulo, severidade=("critico" if gate == "🔴" else "aviso"),
            correlation_id=idempotency_key or draft_id, action_url="/redesign/aprovacoes",
            reference_type="agent_draft", reference_id=draft_id,
            idempotency_key=idempotency_key or draft_id,
        )
        await db.commit()
    except Exception:
        await db.rollback()
        raise
    return {"status": "rascunho", "draft_id": draft_id, "tipo": tipo, "titulo": titulo,
            "gate": gate,
            "mensagem": ("Criei o rascunho — aprove na Central de Aprovações"
                         + (" (exige seu OTP na aprovação, pois envolve dinheiro/eSocial)."
                            if requires_otp else "."))}


async def executar_rascunho(db: AsyncSession, aprovador_user, draft: AgentDraft) -> str | None:
    """Roda o executor de domínio do tipo e marca o draft como executado. NÃO faz gate de
    OTP (o controller faz antes) nem commita (o controller commita). Levanta se o executor
    falhar — o controller trata o rollback + registro de falha."""
    fn = EXECUTORES.get(draft.tipo) or (_garantir_executores() or EXECUTORES.get(draft.tipo))
    if fn is None:
        raise ValueError(f"sem executor registrado para tipo {draft.tipo!r}")
    entity_ref = await fn(db, aprovador_user, dict(draft.payload or {}))
    draft.status = "executado"
    draft.entity_ref = str(entity_ref) if entity_ref is not None else None
    return draft.entity_ref
