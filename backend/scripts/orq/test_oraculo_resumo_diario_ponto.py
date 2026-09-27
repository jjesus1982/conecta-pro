"""Prova o resumo diário de ponto — e cada asserção aqui é um defeito que eu cometi ao escrevê-lo.

O resumo sai às 08:00 para a Pyetra e o Orlailson decidirem o dia anterior (Jordan, 27/09/2026:
*"assim eles podem diariamente aprovar ou reprovar, não deixando acumular"*). Ele não corrige
nada: lê, organiza e entrega a decisão a quem decide.

Os quatro defeitos travados abaixo aconteceram todos em 27/09, enquanto eu escrevia o módulo:

  1. a regra dos aprovadores devolveu **ZERO pessoas** — eu exigi `status='ativo'` e os dois
     são `pj_ativo`. O resumo montava perfeito e não chegava a ninguém
  2. **quem não bateu NADA passou a contar como "ok"** — calei o texto de quem faltou e o
     teste de "está limpo" olhava o texto, não o fato. 6 casos graves viraram 6 "ok"
  3. **turno de 4 horas acusado de "almoço incompleto"** — CLT art. 71 só exige intervalo
     acima de 6h. Eram 25 pendências em 30 turnos, quase metade invenção minha
  4. **demitido e afastado escalados ficavam escondidos** pelo filtro `status='ativo'` — e são
     exatamente os que mais precisam de decisão (é o caso Keyson)

⚠️ Afirma a REGRA, não a fotografia: não fixa nome de pessoa nem contagem do dia. Usa o dia de
ontem, que é o que o beat usa.
"""

import asyncio
import os
import sys
from datetime import timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from datetime import datetime  # noqa: E402

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

falhas: list[str] = []


async def main() -> None:
    from modules.integrations.connectors.whatsapp.destinatario import resolver
    from modules.people_management.ponto import resumo_diario as rd

    ontem = datetime.now(ZoneInfo("America/Manaus")).date() - timedelta(days=1)

    async with async_session_factory() as db:
        # 1 — ⭐ O RESUMO TEM PARA ONDE IR. Esta é a asserção que pega o pior defeito possível:
        #     tudo funcionando e ninguém recebendo.
        alvos = (await db.execute(text(rd._SQL_APROVADORES),
                                  {"roles": list(rd.ROLES_APROVADOR)})).mappings().all()
        if not alvos:
            falhas.append("a regra de aprovadores devolveu NINGUÉM — o resumo não tem "
                          "destinatário e o silêncio pareceria 'dia limpo'")
        else:
            vivos = []
            for a in alvos:
                r = await resolver(db, a["employee_id"])
                if r.get("ok"):
                    vivos.append(a["nome"])
                else:
                    print(f"  ⚠️ {a['nome']} tem papel de aprovação mas NÃO recebe: "
                          f"{(r.get('motivo') or '')[:70]}")
            if not vivos:
                falhas.append("nenhum aprovador passa pela porta única — ninguém recebe o resumo")
            else:
                print(f"  ok  {len(vivos)} aprovador(es) alcançável(is): {', '.join(vivos)}")

        dados = await rd.montar(db, ontem)
        print(f"  ·   {ontem}: {dados['turnos']} turno(s), {len(dados['problemas'])} com "
              f"pendência, {dados['limpos']} limpo(s)")
        if dados["turnos"] == 0:
            print("  ⚠️ nenhum turno ontem — as asserções de conteúdo não provam nada hoje")
            _veredito()
            return

        # 2 — ⭐ QUEM NÃO BATEU NADA NUNCA É "LIMPO". O fato não pode depender do texto.
        #     Confere contra o banco, independente do módulo (senão prova só que sei copiar).
        # ⚠️ COMPARA NOMES, NÃO CONTAGENS. Minha 1ª versão media
        # `turnos - limpos >= quantos_faltaram` — e passou VERDE com o defeito reintroduzido,
        # porque 18 pendências são ≥ 7 faltosos mesmo quando os 7 faltosos não estão entre elas.
        # Contagem não prova pertencimento: só o conjunto de nomes prova.
        faltaram = {r[0] for r in (await db.execute(text("""
            SELECT e.nome FROM shifts sh JOIN employees e ON e.id = sh.employee_id
             WHERE sh.shift_date = CAST(CAST(:d AS text) AS date)
               AND sh.is_active AND NOT sh.is_off_day
               AND lower(coalesce(sh.status,'')) IN ('scheduled','agendado','ativo')
               AND coalesce(e.is_homologacao,false) = false
               AND NOT EXISTS (SELECT 1 FROM gp_clock_punches c
                                WHERE c.employee_id = e.id
                                  AND c.punch_timestamp BETWEEN
                                      (sh.shift_date + sh.planned_start_time - interval '3 hours')
                                  AND (sh.shift_date + sh.planned_start_time + interval '18 hours'))
        """), {"d": str(ontem)})).fetchall()}
        listados = {p["nome"] for p in dados["problemas"]}
        sumidos = faltaram - listados
        if sumidos:
            falhas.append(f"{len(sumidos)} pessoa(s) sem NENHUMA batida ontem ficaram fora do "
                          f"resumo e contaram como 'ok': {sorted(sumidos)[:4]}")
        elif faltaram:
            print(f"  ok  as {len(faltaram)} pessoa(s) sem batida nenhuma estão todas no resumo")
        else:
            print("  ·   ninguém faltou ontem (controle vazio hoje)")

        # 3 — ⭐ ALMOÇO NÃO SE COBRA DE TURNO CURTO. Jornada ≤6h não tem intervalo (CLT 71).
        curtos = [p for p in dados["problemas"]
                  if "almoço" in " ".join(p["motivos"]).lower()
                  and _duracao_h(p["previsto"]) <= 6]
        if curtos:
            falhas.append(f"{len(curtos)} turno(s) de até 6h acusados de almoço incompleto "
                          f"(ex.: {curtos[0]['nome']} {curtos[0]['previsto']}) — jornada curta "
                          f"não tem intervalo a cumprir")
        else:
            print("  ok  nenhum turno de até 6h acusado de almoço incompleto")

        # 4 — ⭐ DEMITIDO/AFASTADO ESCALADO APARECE. Esconder é o caso Keyson.
        fora = (await db.execute(text("""
            SELECT count(DISTINCT e.id) FROM shifts sh JOIN employees e ON e.id = sh.employee_id
             WHERE sh.shift_date = CAST(CAST(:d AS text) AS date) AND sh.is_active
               AND NOT sh.is_off_day
               AND lower(coalesce(sh.status,'')) IN ('scheduled','agendado','ativo')
               AND lower(coalesce(e.status,'')) NOT LIKE 'ativo%'
        """), {"d": str(ontem)})).scalar() or 0
        listados = sum(1 for p in dados["problemas"] if "vínculo:" in " ".join(p["motivos"]))
        if fora and listados < fora:
            falhas.append(f"{fora} pessoa(s) sem vínculo ativo escalada(s) ontem e só "
                          f"{listados} apareceu(ram) no resumo")
        elif fora:
            print(f"  ok  {fora} escalada(s) sem vínculo ativo, todas no resumo e no topo")
        else:
            print("  ·   nenhuma pessoa sem vínculo ativo escalada ontem (controle vazio hoje)")

        # 5 — CONTROLE: dia sem pendência tem de calar. Sem isto, "manda sempre" passaria verde.
        if rd.texto({"dia": str(ontem), "turnos": 0, "limpos": 0, "problemas": []}) is not None:
            falhas.append("dia sem pendência gerou mensagem — resumo que chega todo dia dizendo "
                          "'nada a fazer' ensina a não abrir o resumo")
        else:
            print("  ok  controle: dia sem pendência não gera mensagem")

        # 6 — a tolerância é a MESMA da parede e do lembrete. Um número, um lugar.
        from modules.operacional.lembrete_ponto import TOLERANCIA_MIN as TOL_LEMBRETE

        if rd.TOLERANCIA_MIN != TOL_LEMBRETE:
            falhas.append(f"tolerância divergente: resumo={rd.TOLERANCIA_MIN} "
                          f"lembrete={TOL_LEMBRETE} — o sistema avisaria num minuto e cobraria "
                          f"noutro")
        else:
            print(f"  ok  tolerância única em toda a casa: {rd.TOLERANCIA_MIN} min")

    _veredito()


def _duracao_h(previsto: str) -> float:
    """'07:00–11:00' -> 4.0, e trata o noturno que cruza a meia-noite."""
    ini, fim = previsto.split("–")
    h = (int(fim[:2]) * 60 + int(fim[3:5]) - int(ini[:2]) * 60 - int(ini[3:5])) / 60
    return h + 24 if h <= 0 else h


def _veredito() -> None:
    if falhas:
        for f in falhas:
            print(f"  ❌ {f}")
        print(f"\nTEST resumo_diario_ponto FAIL ({len(falhas)})")
        sys.exit(1)
    print("\nTEST resumo_diario_ponto PASS")


if __name__ == "__main__":
    asyncio.run(main())
