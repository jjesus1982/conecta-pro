"""Ação FAZER do FISCAL — dar baixa em obrigação, via propor→aprovar.

Única ação de escrita do fiscal no chat: marcar uma obrigação como **cumprida**, anexando o
número do recibo do emissor. O LLM NUNCA executa — cria um rascunho inerte na Central, e a
baixa só acontece quando um humano aprova.

⚠️ **Por que isto é 🟡 e não 🔵.** Baixa não move dinheiro, mas `status` de obrigação é
**coluna compartilhada**: a condição 3 do gate, o oráculo de agosto, o painel de prazos e o
alerta de vencimento leem esse valor. Marcar cumprida por engano não perde dinheiro — apaga
um prazo real da tela de quem precisa pagá-lo, que é pior, porque some em silêncio.
[[feedback_status_compartilhado_tem_consumidor]]

⚠️ **Recibo é obrigatório, e não é burocracia.** A baixa automática que já existe
(`marcar_acessorias`, pelo recibo do Onvio) só dá baixa com recibo DO EMISSOR — "provavelmente
foi entregue" não é baixa. Uma baixa manual sem recibo seria uma porta dos fundos para
exatamente aquilo que a regra automática recusa. Sem recibo, esta ação recusa.

Não emite guia, não transmite declaração, não paga nada. Só muda status, e só depois do
aprovador.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy import text

from .acoes.base import ROLES_MONEY
from .acoes.rascunho import criar_rascunho, registrar_executor
from .agir_dispatcher import registrar_acao

#: Aprovação de baixa fiscal é de DIRETORIA — mesma régua do dinheiro. Quem aprova assume que
#: o prazo foi mesmo cumprido, e é o prazo dele que some da tela.
_ROLES = ROLES_MONEY

_SQL_OBRIGACAO = """
    SELECT o.id::text,
           coalesce(o.tipo, o.nome, '—')                       AS tipo,
           lpad(coalesce(o.competencia_mes, 0)::text, 2, '0')
             || '/' || coalesce(o.competencia_ano, 0)          AS competencia,
           o.data_vencimento::text                             AS vencimento,
           o.status::text                                      AS status,
           coalesce(e.nome_fantasia, e.razao_social, '—')      AS empresa,
           coalesce(o.numero_recibo, '')                       AS recibo_atual
      FROM fiscal_obligations o
      LEFT JOIN empresas e ON e.id = o.empresa_id
     WHERE o.id::text = :id AND o.active
     LIMIT 1
"""


async def _propor_baixa_obrigacao(db, user, scope, *, obrigacao_id: Any = "", id: Any = "",
                                  numero_recibo: str = "", observacao: str = "",
                                  **_) -> dict[str, Any]:
    ref = str(obrigacao_id or id or "").strip()
    if not ref:
        return {"erro": "obrigacao_id é obrigatório. Use a consulta "
                        "`consultar_fiscal` (guias_pendentes ou calendario_obrigacoes) "
                        "para achar a obrigação."}
    recibo = (numero_recibo or "").strip()
    if not recibo:
        return {"erro": "numero_recibo do emissor é obrigatório para dar baixa. "
                        "Baixa sem recibo é 'provavelmente foi entregue', e isso apaga um "
                        "prazo real da tela sem prova de que ele foi cumprido."}

    row = (await db.execute(text(_SQL_OBRIGACAO), {"id": ref})).mappings().first()
    if not row:
        return {"erro": f"obrigação '{ref}' não encontrada (ou inativa)."}
    if (row["status"] or "").lower() == "cumprida":
        return {"status": "nada_a_fazer",
                "motivo": f"{row['tipo']} {row['competencia']} ({row['empresa']}) já está "
                          f"cumprida" + (f", recibo {row['recibo_atual']}."
                                         if row["recibo_atual"] else ".")}

    return await criar_rascunho(
        db, user, tipo="baixar_obrigacao", modulo="fiscal", gate="🟡",
        requires_otp=False, roles_aprovador=_ROLES,
        idempotency_key=f"obrig_baixa:{row['id']}",
        titulo="Dar baixa em obrigação fiscal (rascunho)",
        resumo=f"Aprovar marca **{row['tipo']} {row['competencia']}** de {row['empresa']} "
               f"(vencimento {row['vencimento']}, hoje '{row['status']}') como CUMPRIDA, "
               f"com o recibo {recibo}."
               + (f" Observação: “{observacao[:120]}”." if observacao else "")
               + " O prazo SAI do painel de pendências — confira o recibo antes de aprovar. "
                 "Só a aprovação altera o status.",
        payload={"obrigacao_id": row["id"], "numero_recibo": recibo,
                 "observacao": (observacao or "").strip() or None,
                 "tipo": row["tipo"], "competencia": row["competencia"],
                 "empresa": row["empresa"]},
    )


async def _exec_baixar_obrigacao(db, aprovador_user, payload: dict) -> str:
    """Executa a baixa. Roda SÓ pela Central, depois do aprovador — nunca pelo LLM."""
    oid = str(payload["obrigacao_id"])
    recibo = str(payload["numero_recibo"])
    obs = payload.get("observacao")
    await db.execute(text(
        "UPDATE fiscal_obligations "
        "   SET status = 'cumprida', numero_recibo = :r, "
        "       observacoes = coalesce(observacoes || ' | ', '') || :o, "
        "       updated_at = now() "
        " WHERE id::text = :id AND active"),
        {"id": oid, "r": recibo,
         "o": f"baixa aprovada na Central por {getattr(aprovador_user, 'id', '?')}"
              + (f": {obs}" if obs else "")})
    return oid


registrar_executor("baixar_obrigacao", _exec_baixar_obrigacao)

registrar_acao("fiscal", "baixar_obrigacao",
               "Criar um RASCUNHO p/ dar BAIXA numa obrigação fiscal (marcar CUMPRIDA) na "
               "Central — aprovação = diretoria. dados: obrigacao_id (obrig.), numero_recibo "
               "(obrig., o recibo DO EMISSOR — sem ele recusa), observacao. NÃO dá baixa "
               "agora; o status só muda ao aprovar na Central, e aprovar TIRA o prazo do "
               "painel de pendências. Não paga nem transmite nada.",
               _propor_baixa_obrigacao)
