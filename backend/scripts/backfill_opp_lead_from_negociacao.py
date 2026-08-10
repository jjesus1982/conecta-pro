#!/usr/bin/env python3
"""Reconcilia `opportunities.lead_id` a partir da tabela-sombra `crm_negociacao_state`.

Task 6 do plano irmão. **A premissa do plano envelheceu:** ele dizia que a sombra
tem `lead_id`+`deal_id` e bastava copiar. Medido em 2026-08-10: as 9 linhas têm
`proposal_id` e `deal_id`, mas **ZERO `lead_id`**. Copiar não reconciliaria nada.

O caminho real é o que o próprio plano aponta em outro parágrafo — resolver o lead
pela PROPOSTA, com `pipeline_sync._lead_id_for_proposal` (casa por telefone
canônico OU e-mail e devolve None se ambíguo). **Não se escreve dedup novo aqui.**

  sombra.proposal_id -> proposta -> _lead_id_for_proposal -> opportunities.lead_id

Idempotente e conservador: só preenche `lead_id` VAZIO, nunca sobrescreve um elo já
curado; divergência entre o que existe e o que foi resolvido é apenas LOGADA — a
decisão é humana.

  docker exec -e PYTHONPATH=/app -w /app conecta-pro-backend \
    python3 scripts/backfill_opp_lead_from_negociacao.py            # preview
  ... python3 scripts/backfill_opp_lead_from_negociacao.py --aplicar
"""

import argparse
import asyncio
import sys

from sqlalchemy import text

from core.database import async_session_factory


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--aplicar", action="store_true", help="sem isto, só mostra o que faria")
    a = ap.parse_args()

    from modules.crm.models.proposal import Proposal
    from modules.crm.services.pipeline_sync import _lead_id_for_proposal

    preenche, ja_ok, conflitos, sem_match = [], [], [], []
    async with async_session_factory() as db:
        antes = (await db.execute(text("SELECT count(*) FROM opportunities WHERE lead_id IS NOT NULL"))).scalar()
        total = (await db.execute(text("SELECT count(*) FROM opportunities"))).scalar()
        print(f"opportunities com lead_id ANTES: {antes} de {total}\n")

        linhas = (
            await db.execute(
                text(
                    "SELECT n.deal_id, n.proposal_id, n.cliente_nome, o.lead_id, o.title "
                    "FROM crm_negociacao_state n JOIN opportunities o ON o.id = n.deal_id "
                    "WHERE n.proposal_id IS NOT NULL"
                )
            )
        ).mappings().all()

        for r in linhas:
            proposta = await db.get(Proposal, r["proposal_id"])
            if not proposta:
                sem_match.append((r["cliente_nome"], "proposta não encontrada"))
                continue
            lead_id = await _lead_id_for_proposal(db, proposta)
            if not lead_id:
                sem_match.append((r["cliente_nome"], "sem match único por telefone/e-mail"))
                continue
            if r["lead_id"] and str(r["lead_id"]) != str(lead_id):
                conflitos.append((r["cliente_nome"], str(r["lead_id"]), str(lead_id)))
                continue
            if r["lead_id"]:
                ja_ok.append(r["cliente_nome"])
                continue
            preenche.append((r["deal_id"], r["title"], r["cliente_nome"], lead_id))

        print(f"{'oportunidade':32} {'lead resolvido pela proposta'}")
        for _deal, title, nome, lead_id in preenche:
            print(f"  PREENCHE  {str(title)[:30]:30} <- {nome} ({lead_id[:8]})")
        for nome in ja_ok:
            print(f"  já ok     {nome}")
        for nome, atual, novo in conflitos:
            print(f"  CONFLITO  {nome}: opp tem {atual[:8]}, sombra resolve {novo[:8]} — NÃO decido, só logo")
        for nome, motivo in sem_match:
            print(f"  sem match {str(nome)[:28]:28} {motivo}")

        if a.aplicar and preenche:
            for deal_id, _t, _n, lead_id in preenche:
                await db.execute(
                    text(
                        "UPDATE opportunities SET lead_id = :l, updated_at = now() "
                        "WHERE id = :d AND lead_id IS NULL"  # só o vazio; corrida não sobrescreve
                    ),
                    {"l": lead_id, "d": deal_id},
                )
            await db.commit()
            depois = (await db.execute(text("SELECT count(*) FROM opportunities WHERE lead_id IS NOT NULL"))).scalar()
            print(f"\nDEPOIS: {depois} de {total} (+{depois - antes})")
        elif not a.aplicar:
            print("\n(preview — nada foi escrito. Repita com --aplicar.)")
        else:
            print("\nNada a preencher.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
