#!/usr/bin/env python3
"""ASO que não prova exame nenhum — e por isso o número de "vencidos" não quer dizer nada.

Origem (13/09/2026): o módulo de Saúde Ocupacional acusava **25 colaboradores ativos com
ASO vencido**. Fui montar a fila de renovação e os 25 tinham a MESMA data de validade
(01/06/2026) e o MESMO tipo (admissional). Olhando a tabela inteira:

    96 dos 97 ASOs assinados por «Dr. Carlos Mendes, CRM-AM 4521»
    3 datas de realização distintas para 96 exames
    0 com clínica preenchida
    0 com documento anexado
    todos criados no mesmo dia: 2026-03-16

Não são 25 exames que venceram. É uma carga de março com datas de enfeite, e nenhuma
pessoa da empresa tem ASO comprovado no sistema. O alerta estava certo por acaso e
errado por construção — "renovar 25" é uma tarefa que não existe; a tarefa real é
carregar os ASOs de verdade.

Isto importa além da tela: o ASO é o que autoriza a pessoa a trabalhar, alimenta o
S-2220 do eSocial e é o primeiro documento que a fiscalização pede.

O que o caçador afirma: um ASO 'realizado' é evidência — tem documento OU (clínica E
médico que não seja o mesmo de todo mundo). Sem isso ele é um registro, não um exame.

    docker exec -e PYTHONPATH=/app conecta-pro-backend \
        python3 /app/scripts/qa/checar_aso_sem_lastro.py

Linha canônica: `TOTAL: <n> ASO(s) sem lastro`. Exit 1 quando há achado.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

#: Acima disso, um único médico assinando a fatia toda deixa de ser "o médico da empresa"
#: e passa a ser assinatura de carga. 96/97 = 0,99 foi o caso que originou o caçador.
FATIA_SUSPEITA = 0.80


async def main() -> int:
    from sqlalchemy import text  # noqa: PLC0415

    from core.database import async_session_factory  # noqa: PLC0415

    if not Path("/app/scripts").is_dir():
        print("RECUSO: roda DENTRO do container (precisa do banco)")
        return 2

    async with async_session_factory() as db:
        total = (await db.execute(text("SELECT count(*) FROM gp_asos"))).scalar() or 0
        if not total:
            print("nenhum ASO cadastrado\n\nTOTAL: 0 ASO(s) sem lastro")
            return 0

        sem_evidencia = (
            await db.execute(
                text(
                    "SELECT count(*) FROM gp_asos "
                    "WHERE coalesce(documento_url,'') = '' "
                    "  AND coalesce(clinica,'') = ''"
                )
            )
        ).scalar() or 0

        medicos = (
            await db.execute(
                text(
                    "SELECT coalesce(nullif(trim(medico),''),'(sem médico)'), "
                    "       coalesce(nullif(trim(crm),''),'(sem CRM)'), count(*), "
                    "       count(DISTINCT data_realizacao) "
                    "FROM gp_asos GROUP BY 1,2 ORDER BY 3 DESC"
                )
            )
        ).all()

        datas = (
            await db.execute(
                text(
                    "SELECT count(DISTINCT data_realizacao), count(DISTINCT data_validade), "
                    "       count(DISTINCT created_at::date) FROM gp_asos"
                )
            )
        ).first()

        # A fila que a tela chama de "renovar": quantos deles são desta carga sem lastro.
        vencidos_sem_lastro = (
            await db.execute(
                text(
                    "WITH ultimo AS (SELECT DISTINCT ON (a.employee_id) a.employee_id, "
                    "                a.data_validade, a.documento_url, a.clinica "
                    "                FROM gp_asos a WHERE a.data_validade IS NOT NULL "
                    "                ORDER BY a.employee_id, a.data_validade DESC) "
                    "SELECT count(*) FROM ultimo u JOIN employees e ON e.id = u.employee_id "
                    "WHERE e.status = 'ativo' AND u.data_validade < current_date "
                    "  AND coalesce(u.documento_url,'') = '' AND coalesce(u.clinica,'') = ''"
                )
            )
        ).scalar() or 0

    print(f"   {total} ASO(s) na base — {sem_evidencia} sem documento E sem clínica")
    print(f"   datas distintas: {datas[0]} de realização, {datas[1]} de validade, "
          f"{datas[2]} dia(s) de cadastro")
    for medico, crm, n, ndatas in medicos[:3]:
        fatia = n / total
        marca = "  ← assinatura de carga" if fatia >= FATIA_SUSPEITA and n > 5 else ""
        print(f"   {medico} ({crm}): {n} ASO(s), {ndatas} data(s) de realização{marca}")
    if vencidos_sem_lastro:
        print(
            f"\n   {vencidos_sem_lastro} pessoa(s) ativa(s) que a tela manda 'renovar exame' "
            "estão nessa carga —"
        )
        print("      renovar o que não foi feito não é renovação: é carregar o ASO real.")

    print(f"\nTOTAL: {sem_evidencia} ASO(s) sem lastro")
    return 1 if sem_evidencia else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
