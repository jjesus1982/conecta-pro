"""Oráculo: o fechamento de turno por ponto é honesto e não inventa falta.

Guarda quatro coisas que, se quebrarem, viram dinheiro errado no holerite:

  1. dry-run NÃO escreve — o padrão do serviço é medir, e tem que continuar sendo
  2. nenhuma hora absurda em turno fechado (negativa, zero, ou acima de 16h)
  3. o serviço NÃO ALTERA `status` — nenhum turno vira completed/partial/missed.
     Esta é a trava mais cara do arquivo. Em 14/08 a primeira versão marcava
     scheduled → completed e isso tirou 68 plantões noturnos de 12 colaboradores
     da folha de agosto (~476h de adicional): `calculo_service.plantoes_noturnos`
     conta com `s.status = 'scheduled'` LITERAL, e o literal aparece em 12+ pontos
     (folha, grade, KPIs, triagem, cobertura). Turno que aconteceu é `scheduled`
     com `actual_start_time` preenchido — convenção que o próprio repo já usava
     em grade_controller.py:442 e em ausentes-hoje.
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
             WHERE actual_start_time IS NOT NULL AND actual_end_time IS NOT NULL
               AND (actual_hours IS NULL OR actual_hours < 0 OR actual_hours > 16)
        """))).scalar() or 0
        assert ruins == 0, f"{ruins} turno(s) com hora absurda"
        faixa = (await db.execute(text(
            "SELECT round(min(actual_hours)::numeric,2), round(max(actual_hours)::numeric,2) "
            "FROM shifts WHERE actual_hours > 0"))).first()
        print(f"OK 2 · horas gravadas dentro da faixa: {faixa[0]}h a {faixa[1]}h")

        # 3 · o serviço NÃO altera status (guarda do bug de folha de 14/08)
        r_ap = await fechar_turnos_por_ponto(db, aplicar=True)
        pos = await _contagem(db)
        assert antes == pos, (
            f"o serviço MEXEU no status: {antes} -> {pos}. "
            "plantoes_noturnos da folha filtra status='scheduled' literal — mudar "
            "status aqui apaga plantão do holerite.")
        novos = {s for s in pos if s not in ("scheduled", "cancelled", "off_day")}
        assert not novos, f"status inesperado em shifts: {novos}"
        print(f"OK 3 · status intocado ({pos}); {r_ap.candidatas_falta} candidata(s) a falta")

        # 4 · idempotente
        r2 = await fechar_turnos_por_ponto(db)
        assert (r2.completed, r2.partial) == (r.completed, r.partial), (
            f"não é idempotente: {r.resumo()} vs {r2.resumo()}")
        print(f"OK 4 · idempotente (completed={r2.completed} partial={r2.partial})")


if __name__ == "__main__":
    asyncio.run(main())
