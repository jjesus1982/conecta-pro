"""
Webhook de status de PIX enviado (Efí) — FastAPI.

Idempotente: a Efí re-tenta a entrega. Cada evento é deduplicado por
(e2eId + status). Reprocessar o mesmo evento é no-op.

SEGURANÇA (validar no painel/doc Efí):
  * A Efí chama seu endpoint com mTLS por padrão. Termine o TLS no seu proxy
    e valide o certificado do cliente ANTES de chegar aqui, OU use o modo
    com ?ignorar-mtls + HMAC. Não confie no corpo sem autenticar a origem.
  * O shape do payload de ENVIO precisa ser confirmado no sandbox — o parser
    abaixo é defensivo e isola a extração em _extrair().
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable

from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

router = APIRouter(prefix="/webhooks/efi", tags=["efi"])


def get_session_factory() -> Callable[[], Session]:  # sobrescreva no app real
    raise NotImplementedError


_STATUS_MAP = {
    "REALIZADO": "LIQUIDADO", "CONCLUIDA": "LIQUIDADO",
    "NAO_REALIZADO": "FALHOU", "REJEITADO": "FALHOU", "DEVOLVIDO": "FALHOU",
}


def _extrair(payload: dict[str, Any]) -> list[dict[str, str]]:
    """Normaliza um ou vários eventos. CONFIRMAR chaves reais no sandbox."""
    itens = payload.get("pix") or payload.get("enviados") or [payload]
    out = []
    for it in itens:
        status = (it.get("status") or "").upper()
        out.append({
            "e2e_id": it.get("e2eId") or it.get("endToEndId"),
            "id_envio": it.get("idEnvio"),
            "status": status,
            "raw": it,
        })
    return out


@router.post("")
async def receber(request: Request, session_factory=Depends(get_session_factory)):
    # TODO: validar mTLS/HMAC da origem aqui antes de qualquer processamento.
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "payload inválido")

    for ev in _extrair(payload):
        if not ev["status"]:
            continue
        destino = _STATUS_MAP.get(ev["status"])
        dedup = f"{ev['e2e_id'] or ev['id_envio']}:{ev['status']}"
        with session_factory() as s:
            # dedup: insere o evento; se já existe, ignora (ON CONFLICT).
            novo = s.execute(text("""
                INSERT INTO folha_efi.webhook_event (dedup_key, e2e_id, id_envio, payload, processado_em)
                VALUES (:k, :e2e, :ide, CAST(:pl AS JSONB), now())
                ON CONFLICT (dedup_key) DO NOTHING
                RETURNING id
            """), {"k": dedup, "e2e": ev["e2e_id"], "ide": ev["id_envio"],
                   "pl": _json(ev["raw"])}).first()
            if novo is None:
                s.rollback()
                continue  # reentrega — já processado
            if destino:
                _aplicar(s, ev, destino)
            s.commit()

    # 200 sempre que processamos/deduplicamos — senão a Efí re-tenta em loop.
    return {"ok": True}


def _aplicar(s: Session, ev: dict, destino: str) -> None:
    where = "e2e_id=:v" if ev["e2e_id"] else "id_envio=:v"
    val = ev["e2e_id"] or ev["id_envio"]
    # Só avança a partir de estados não-terminais (nunca "ressuscita" pagamento).
    row = s.execute(text(f"""
        UPDATE folha_efi.pagamento
           SET status=:dest,
               liquidado_em = CASE WHEN :dest='LIQUIDADO' THEN now() ELSE liquidado_em END,
               updated_at = now()
         WHERE {where} AND status IN ('ENVIANDO','PROCESSANDO')
        RETURNING id
    """), {"dest": destino, "v": val}).first()
    if row:
        s.execute(text("""INSERT INTO folha_efi.pagamento_evento
                          (pagamento_id, de_status, para_status, origem, detalhe)
                          VALUES (:pid,'PROCESSANDO',:dest,'webhook',CAST(:d AS JSONB))"""),
                  {"pid": row[0], "dest": destino, "d": _json(ev["raw"])})


def _json(obj) -> str:
    import json
    return json.dumps(obj, default=str)
