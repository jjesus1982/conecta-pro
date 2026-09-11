"""A pesquisa do José Luís: "você está conseguindo bater seu ponto?" (11/09/2026).

Pedido do Jordan: *"quero que o José Luís mande mensagens a fim de pesquisa para saber do
colaborador se ele está conseguindo bater o ponto... se apresente aos funcionários e apenas aos
funcionários como a pessoa responsável por organizar a questão dos pontos, trabalha junto com a
Pyetra Jesus... coletar essas informações e trazer para que sejam resolvidas"*.

O ponto que faz esta pesquisa valer alguma coisa: **a resposta é REGISTRADA**, não só
conversada. Uma pesquisa que vira histórico de chat não é pesquisa — é 53 conversas que
ninguém consegue somar. Aqui cada resposta vira uma linha com nome, se consegue bater e o que
acontece quando não consegue.

Onde grava: `gp_audit_logs`, com `action='ponto.pesquisa_resposta'` — a mesma tabela e o mesmo
padrão do `tentativa_log`, que já guarda as tentativas de bater que falharam. Sem migration
(zona proibida) e no lugar onde os fatos do ponto já moram.

⚠️ QUEM RECEBE. Só funcionário com vínculo, e só quem tem número que EXISTE no WhatsApp —
conferido pelo `checar_telefone_funcionario`. Mandar para número que não existe registra
sucesso e não chega a ninguém: seria fabricar uma pesquisa com respostas que nunca viriam.
Quem não recebe sai nomeado no relatório, porque a ausência dele também é informação.
"""
from __future__ import annotations

import json
import logging
import uuid

logger = logging.getLogger(__name__)

ACAO = "ponto.pesquisa_resposta"

#: O texto aprovado pelo Jordan em 11/09/2026, palavra por palavra.
TEXTO = (
    "Oi, {primeiro}! Aqui é o José Luís, da Conecta Mais. Eu cuido da organização do ponto "
    "junto com a Pyetra Jesus.\n\n"
    "Estou falando com todo mundo um por um para saber de uma coisa só: *você está "
    "conseguindo bater seu ponto normalmente?*\n\n"
    "Se está, é só me responder \"sim\" que eu já anoto.\n"
    "Se não está, me conta o que acontece — se é o rosto que não reconhece, se o app não abre, "
    "se é outra coisa. Pode mandar print se for mais fácil.\n\n"
    "O que você me disser eu levo para resolver. Ninguém vai ficar sem o ponto registrado."
)


async def registrar_resposta(db, employee_id: str, nome: str, consegue: bool | None,
                             detalhe: str, telefone: str | None = None) -> dict:
    """Grava a resposta de UMA pessoa. `consegue=None` = respondeu sem dar para concluir."""
    from sqlalchemy import text as sql

    extra = json.dumps({"consegue_bater": consegue, "detalhe": (detalhe or "").strip()[:1500],
                        "telefone": telefone, "origem": "pesquisa_whatsapp"}, ensure_ascii=False)
    # ⚠️ `gp_audit_logs` tem 11 colunas NOT NULL — incluindo actor_user_id, _role e _module.
    # O `tentativa_log` já documentava isso e eu repeti o erro: o primeiro disparo mandou UMA
    # mensagem e morreu no INSERT. Aqui o ator é o próprio funcionário, que é quem respondeu.
    await db.execute(sql(
        "INSERT INTO gp_audit_logs (id, timestamp, action, entity, entity_id, description, "
        " source_module, actor_user_id, actor_user_name, actor_user_role, actor_user_module, "
        " related_funcionario_id, extra_data) "
        "VALUES (CAST(:i AS uuid), (now() AT TIME ZONE 'America/Manaus'), :a, 'ponto', :e, "
        " :d, 'people_management.ponto', :e, :n, 'funcionario', 'ponto', :e, CAST(:x AS jsonb))"),
        {"i": str(uuid.uuid4()), "a": ACAO, "e": str(employee_id), "n": nome,
         "d": ("consegue bater" if consegue else "NÃO consegue bater" if consegue is False
               else "respondeu sem conclusão") + f": {(detalhe or '')[:200]}",
         "x": extra})
    await db.commit()
    logger.info("pesquisa de ponto: %s consegue=%s", nome, consegue)
    return {"ok": True, "registrado": nome, "consegue_bater": consegue}


async def consolidado(db) -> dict:
    """O que a pesquisa juntou até agora — a lista que a Pyetra e o Jordan precisam ver."""
    from sqlalchemy import text as sql

    linhas = (await db.execute(sql(
        "SELECT DISTINCT ON (related_funcionario_id) "
        "       coalesce(actor_user_name,'—') AS nome, "
        "       extra_data->>'consegue_bater' AS consegue, "
        "       extra_data->>'detalhe' AS detalhe, "
        "       to_char(timestamp,'DD/MM HH24:MI') AS quando "
        "  FROM gp_audit_logs WHERE action = :a "
        " ORDER BY related_funcionario_id, timestamp DESC"), {"a": ACAO})).mappings().all()
    nao = [dict(r) for r in linhas if r["consegue"] == "false"]
    sim = [dict(r) for r in linhas if r["consegue"] == "true"]
    indef = [dict(r) for r in linhas if r["consegue"] not in ("true", "false")]
    return {"responderam": len(linhas), "conseguem": len(sim), "nao_conseguem": len(nao),
            "sem_conclusao": len(indef), "lista_nao_conseguem": nao, "lista_sem_conclusao": indef}
