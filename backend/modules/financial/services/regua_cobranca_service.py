"""Régua de cobrança ATIVA (gated) — v1: fila (read-only) + registro de tentativa.

Computa a fila de cobrança (recebíveis vencidos + tier + mensagem pronta via o
collection_negotiator) e registra a tentativa de contato (collection_attempts++,
last_collection_date, next_collection_date, collection_notes) com anti-spam mesmo-dia.

v1 NÃO envia automaticamente a cliente (regra: comms a cliente real = gate humano;
nunca testar caminho feliz). A mensagem pronta é entregue na fila pra o humano
enviar pelo canal dele e registrar aqui. Envio automático (WhatsApp/e-mail) = v2.
"""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import text

from modules.financial.agents.collection_negotiator import _MENSAGENS, _classificar

# Intervalo até o próximo contato, por nível (dias)
_INTERVALO = {"lembrete": 5, "contato_ativo": 5, "notificacao_formal": 7,
              "negativacao_iminente": 5, "juridico": 3}


async def montar_fila_cobranca(db) -> list[dict]:
    """Recebíveis vencidos (due<hoje, não pago/cancelado) com tier, canal e mensagem pronta."""
    rows = (await db.execute(text(
        "SELECT id, coalesce(customer_name,'—'), net_value, due_date, "
        "coalesce(collection_attempts,0), last_collection_date "
        "FROM receivable_accounts "
        "WHERE due_date < current_date AND status NOT IN ('paga','cancelada','recebida') "
        "ORDER BY due_date ASC"))).fetchall()
    hoje = date.today()
    fila = []
    for rid, nome, valor, due, tentativas, ultimo in rows:
        valor = float(valor or 0)
        dias = (hoje - due).days if due else 0
        nivel, prioridade, canal = _classificar(dias)
        msg = _MENSAGENS.get(nivel, "").format(
            nome=nome, valor=valor, vencimento=str(due), dias=dias)
        ja_hoje = ultimo is not None and (ultimo.date() if hasattr(ultimo, "date") else ultimo) == hoje
        fila.append({
            "id": str(rid), "cliente": nome, "valor": round(valor, 2), "vencimento": str(due),
            "dias": dias, "nivel": nivel, "prioridade": prioridade, "canal": canal,
            "mensagem": msg, "tentativas": int(tentativas), "contatado_hoje": ja_hoje,
        })
    return fila


async def registrar_cobranca(db, receivable_id: str, canal: str, quem: str = "") -> dict:
    """Registra uma tentativa de cobrança no recebível (bookkeeping — NÃO envia nem move dinheiro).
    Anti-spam: bloqueia 2º registro no mesmo dia. Só recebível vencido e não pago."""
    row = (await db.execute(text(
        "SELECT coalesce(customer_name,'—'), net_value, due_date, coalesce(status,''), "
        "coalesce(collection_attempts,0), last_collection_date "
        "FROM receivable_accounts WHERE id::text = :id"), {"id": str(receivable_id)})).fetchone()
    if not row:
        return {"ok": False, "message": "Recebível não encontrado."}
    nome, valor, due, status, tentativas, ultimo = row
    if status in ("paga", "cancelada", "recebida"):
        return {"ok": False, "message": f"Recebível já está '{status}' — não há o que cobrar."}
    hoje = date.today()
    if ultimo is not None and (ultimo.date() if hasattr(ultimo, "date") else ultimo) == hoje:
        return {"ok": False, "message": "Já houve um registro de cobrança HOJE para este cliente (anti-spam)."}
    dias = (hoje - due).days if due else 0
    nivel, _prio, _canal = _classificar(dias)
    prox = hoje + timedelta(days=_INTERVALO.get(nivel, 5))
    nota = f"[{hoje}] Cobrança registrada — nível {nivel}, canal {canal or _canal}, por {quem or 'gestor'}."
    await db.execute(text(
        "UPDATE receivable_accounts SET "
        "collection_attempts = coalesce(collection_attempts,0) + 1, "
        "last_collection_date = now(), next_collection_date = :prox, "
        "collection_notes = coalesce(collection_notes,'') || ' | ' || :nota, updated_at = now() "
        "WHERE id::text = :id"), {"prox": prox, "nota": nota, "id": str(receivable_id)})
    await db.commit()
    return {"ok": True, "message": f"Cobrança registrada para {nome} (nível {nivel}, {int(tentativas)+1}ª tentativa). "
            f"Próximo contato sugerido: {prox}."}
