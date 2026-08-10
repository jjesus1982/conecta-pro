#!/usr/bin/env python3
"""Backfill: leads que a ficha JÁ justifica qualificar, mas que ficaram para trás.

Contexto: até 2026-08-10 o agente não escrevia `leads.status`, então lead nenhum
de WhatsApp virava oportunidade. O fix (`0b7698a4`) vale dali para a frente — só
move o lead quando ele CONVERSA de novo. Quem já estava parado continua parado.
Este script recupera esses.

NÃO reimplementa regra nenhuma: usa exatamente o que o agente usa —
`_status_por_qualificacao` (a decisão), `_telefone_interno` (a trava) e
`ensure_opportunity_for_lead` (o pipeline, idempotente). Se a regra mudar, este
script muda junto, de graça.

A trava importa aqui mais do que no caminho normal: o lead 'Jordan Jesus'
(score 75) QUALIFICA pela regra e é o telefone do dono. Backfill cego botaria o
teste do Jordan no funil comercial.

  # preview (não escreve nada):
  docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
    python3 scripts/backfill_leads_qualificados.py

  # aplicar, nominalmente:
  docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
    python3 scripts/backfill_leads_qualificados.py --aplicar --nome Anderson --nome "Juan Torres"

  # aplicar a todos os elegíveis:
  ... --aplicar --todos
"""

import argparse
import asyncio
import sys

from sqlalchemy import text

from core.database import async_session_factory
from modules.integrations.connectors.whatsapp.agent_service import (
    _status_por_qualificacao,
    _telefone_interno,
)

SQL_CANDIDATOS = """
    SELECT id, name, phone, status,
           qualificacao->>'temperatura' AS temperatura,
           coalesce((qualificacao->>'score_lead')::int, 0) AS score_lead
      FROM leads
     -- 'qualified' entra também: o Anderson já estava qualificado e MESMO ASSIM sem
     -- oportunidade, porque o agente nunca chamou o pipeline. Status certo, elo faltando.
     WHERE is_active AND status IN ('new', 'contacted', 'qualified')
     ORDER BY coalesce((qualificacao->>'score_lead')::int, 0) DESC
"""


async def _conversa_do_lead(db, phone: str | None) -> int | None:
    """conversation_id mais recente do telefone — _telefone_interno pede uma conversa."""
    if not phone:
        return None
    return (
        await db.execute(
            text(
                "SELECT chatwoot_conversation_id FROM cwi_message_log "
                "WHERE phone_canonical = :p AND chatwoot_conversation_id IS NOT NULL "
                "ORDER BY created_at DESC LIMIT 1"
            ),
            {"p": phone},
        )
    ).scalar()


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="sem isto, só mostra o que faria")
    ap.add_argument("--nome", action="append", default=[], help="restringe a estes nomes (repetível)")
    ap.add_argument("--todos", action="store_true", help="todos os elegíveis, não só os --nome")
    a = ap.parse_args()
    if not a.nome and not a.todos:
        print("Escolha --nome <n> (repetível) ou --todos. Preview roda sem --aplicar.")
        return 2

    from modules.crm.models.lead import Lead
    from modules.crm.services.pipeline_sync import ensure_opportunity_for_lead

    movidos, pulados = [], []
    async with async_session_factory() as db:
        for r in (await db.execute(text(SQL_CANDIDATOS))).mappings().all():
            alvo = a.todos or any(n.lower() in (r["name"] or "").lower() for n in a.nome)
            if not alvo:
                continue
            if r["status"] == "qualified":
                # Já qualificado — alguém (humano ou agente) já decidiu. Não reavalia a
                # ficha: só falta o elo do pipeline, que é o que este script existe p/ fechar.
                novo = "qualified"
            else:
                novo = _status_por_qualificacao({"temperatura": r["temperatura"]}, r["score_lead"])
                if novo != "qualified":
                    pulados.append(
                        (r["name"], f"a ficha não qualifica (temp={r['temperatura']!r} score={r['score_lead']})")
                    )
                    continue
            conv = await _conversa_do_lead(db, r["phone"])
            if conv and await _telefone_interno(db, conv):
                pulados.append((r["name"], "telefone INTERNO (dono/time) — não entra no funil"))
                continue
            movidos.append((r["id"], r["name"], r["status"], novo))

        print(f"{'lead':28} {'de':>10} -> {'para':<10} {'oportunidade'}")
        for lead_id, nome, antes, novo in movidos:
            opps = (
                await db.execute(text("SELECT count(*) FROM opportunities WHERE lead_id = :i"), {"i": lead_id})
            ).scalar()
            print(f"  {nome[:26]:26} {antes:>10} -> {novo:<10} {'já tem' if opps else 'ABRE'}")
            if not a.aplicar:
                continue
            if antes != novo:
                await db.execute(
                    text("UPDATE leads SET status = :s, updated_at = now() WHERE id = :i AND status IN ('new','contacted')"),
                    {"s": novo, "i": lead_id},
                )
                await db.commit()
            lead = await db.get(Lead, lead_id)
            if lead and (lead.status or "") == "qualified":
                await ensure_opportunity_for_lead(db, lead)

        if pulados:
            print("\nPULADOS (de propósito):")
            for nome, motivo in pulados:
                print(f"  {nome[:26]:26} {motivo}")

        if a.aplicar:
            print("\nDEPOIS:")
            for lead_id, nome, _a, _n in movidos:
                row = (
                    await db.execute(
                        text(
                            "SELECT l.status, (SELECT count(*) FROM opportunities o WHERE o.lead_id = l.id) "
                            "FROM leads l WHERE l.id = :i"
                        ),
                        {"i": lead_id},
                    )
                ).first()
                print(f"  {nome[:26]:26} status={row[0]:10} oportunidades={row[1]}")
        else:
            print("\n(preview — nada foi escrito. Repita com --aplicar.)")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
