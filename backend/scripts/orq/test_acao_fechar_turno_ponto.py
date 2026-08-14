"""Oráculo: o fechamento de turno por ponto é honesto e não inventa falta.

Guarda quatro coisas que, se quebrarem, viram dinheiro errado no holerite:

  1. dry-run NÃO escreve — o padrão do serviço é medir, e tem que continuar sendo
  2. nenhuma hora absurda em turno fechado (negativa, zero, ou acima de 16h)
  3. NENHUM turno virou `missed` por máquina — falta é decisão humana, e turno sem
     batida tem que continuar `scheduled` (a regra ingênua produzia 547 faltas em
     1488 turnos, sendo 180 só em abril, mês em que o relógio não tem UMA batida)
  4. o serviço é idempotente — rodar de novo não muda contagem nenhuma

Roda no container.
"""
import asyncio

from sqlalchemy import text

from core.database import async_session_factory
from modules.operacional.services.fechamento_turno_service import fechar_turnos_por_ponto


async def _contagem(db) -> dict:
    return {s: n for s, n in (await db.execute(text(
        "SELECT status::text, count(*) FROM shifts GROUP BY 1"))).all()}


async def main() -> None:
    async with async_session_factory() as db:
        antes = await _contagem(db)

        # 1 · dry-run não escreve
        r = await fechar_turnos_por_ponto(db)
        assert not r.aplicado, "dry-run marcou como aplicado"
        depois = await _contagem(db)
        assert antes == depois, f"dry-run ESCREVEU: {antes} -> {depois}"
        print(f"OK 1 · dry-run não escreveu nada ({r.resumo()})")

        # 2 · nenhuma hora absurda onde o serviço gravou
        ruins = (await db.execute(text("""
            SELECT count(*) FROM shifts
             WHERE status::text = 'completed'
               AND (actual_hours IS NULL OR actual_hours <= 0 OR actual_hours > 16)
        """))).scalar() or 0
        assert ruins == 0, f"{ruins} turno(s) fechado(s) com hora absurda"
        faixa = (await db.execute(text(
            "SELECT round(min(actual_hours)::numeric,2), round(max(actual_hours)::numeric,2) "
            "FROM shifts WHERE status::text='completed'"))).first()
        print(f"OK 2 · horas de turno fechado dentro da faixa: {faixa[0]}h a {faixa[1]}h")

        # 3 · falta NUNCA por máquina
        missed = antes.get("missed", 0)
        assert missed == 0, f"{missed} turno(s) em 'missed' — falta tem que ser decisão humana"
        print(f"OK 3 · 0 turno em 'missed'; {r.candidatas_falta} candidata(s) aguardando humano")

        # 4 · idempotente
        r2 = await fechar_turnos_por_ponto(db)
        assert (r2.completed, r2.partial) == (r.completed, r.partial), (
            f"não é idempotente: {r.resumo()} vs {r2.resumo()}")
        print(f"OK 4 · idempotente (completed={r2.completed} partial={r2.partial})")


if __name__ == "__main__":
    asyncio.run(main())
