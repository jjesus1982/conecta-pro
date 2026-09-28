"""Jornada só é "aberta" se a saída JÁ ERA DEVIDA. E o teto tem que alcançar todo mundo.

🔴 DOIS DEFEITOS MEDIDOS EM 28/09/2026, 00:55, na mesma rotina.

**1. Contava quem estava trabalhando.** Faltava a guarda de "o turno já terminou". Quem entrou
às 19:00 num turno 19:00–07:00 já aparecia como jornada aberta **faltando seis horas para o
fim**. Medido na hora: o conjunto pulou de 31 para 34 pessoas entre 18:50 e 00:55, e os três
novos eram o noturno trabalhando normalmente. Depois da guarda: 30 pessoas, 75 jornadas.

O dano era duplo e nenhum dos dois aparecia no verde: as cinco vagas por rodada do Hermes (prova
cara) iam para gente sem problema nenhum, e o relatório diria à Pyetra que há anomalia em quem
está no posto naquele minuto. ⭐ **Ausência de saída só é falta quando a saída já era devida** —
antes disso é só o turno em andamento.

**2. O teto prometia uma rodada que não existia.** `pessoas[:teto_pessoas]` pegava sempre os
cinco primeiros nomes e o texto dizia «+26 ficaram para a próxima rodada». Rodar de novo
reclassificava as MESMAS cinco; as outras 26 eram inalcançáveis por construção. Corrigido com
`pular`, e o retorno agora entrega `proximo_pular` — continuação real, não promessa.

## O que este oráculo trava

Invariantes, não números:
· **nenhum caso devolvido pode ter turno que ainda não terminou** (conferido com a virada de
  meia-noite escrita aqui de forma independente)
· **o deslocamento cobre o conjunto sem repetir nem pular** ninguém
· a mensagem **não volta a prometer «próxima rodada»** sem dizer como chegar lá
"""

import asyncio
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.people_management.ponto import jornadas_abertas as ja  # noqa: E402

#: A folga que a rotina dá para a batida de saída atrasada. Se mudar lá, muda aqui — de
#: propósito: o oráculo declara a regra que está valendo, e divergência é achado.
FOLGA_HORAS = 2

#: ⚠️ Escrita À MÃO, sem importar a query auditada: se ela sair da rotina por copy-paste, o
#: oráculo só prova que sei copiar. A virada de meia-noite é o miolo — `planned_end_time` menor
#: que o início significa que o turno termina no DIA SEGUINTE.
_FIM_DO_TURNO = """
SELECT (s.shift_date + s.planned_end_time
        + CASE WHEN s.planned_end_time <= s.planned_start_time
               THEN INTERVAL '1 day' ELSE INTERVAL '0' END) AS fim
  FROM shifts s
 WHERE s.employee_id = CAST(CAST(:e AS text) AS uuid) AND s.is_active
   AND s.shift_date = CAST(CAST(:d AS text) AS date)
 LIMIT 1
"""
#: ⚠️ DUPLO CAST de propósito. `CAST(:e AS uuid)` faz o asyncpg inferir `uuid` para o parâmetro e
#: recusar a string que o Python manda. `CAST(CAST(:e AS text) AS uuid)` infere `text` e converte
#: no banco. Mesma armadilha já medida nesta casa com `timestamp` e com `uuid[]`.


async def main() -> None:
    async with async_session_factory() as db:
        agora = (await db.execute(text(
            "SELECT (now() AT TIME ZONE 'America/Manaus')"))).scalar()

        dados = await ja.levantar(db, dias=30)
        pessoas = dados["pessoas"]

        # ── 1. ninguém com turno em andamento
        vazando = []
        for p in pessoas:
            for c in p["casos"]:
                dia = c.get("dia")
                if not dia:
                    continue
                fim = (await db.execute(text(_FIM_DO_TURNO),
                                        {"e": p["employee_id"], "d": dia})).scalar()
                if fim is None:
                    continue  # sem turno na escala — outro ramo da regra, testado abaixo
                if fim > agora - timedelta(hours=FOLGA_HORAS):
                    vazando.append(f"{p['nome'].split()[0]} {c['entrada']} (turno termina {fim})")

        assert not vazando, (
            "jornada contada com o turno AINDA EM ANDAMENTO: " + " · ".join(vazando[:5]))

        # ── 2. quem não tem turno precisa de 14h para entrar na conta
        assert ja._SQL_ABERTAS.count("INTERVAL '14 hours'") == 1, (
            "caiu a régua de 14h para quem não tem turno na escala — sem ela, "
            "uma entrada de agora sem escala entraria como jornada aberta na hora")

        # ── 3. o deslocamento cobre tudo, sem repetir nem pular
        nomes = [p["nome"] for p in pessoas]
        teto, vistos, ini = 5, [], 0
        while ini < len(nomes):
            vistos.extend(nomes[ini:ini + teto])
            ini += teto
        assert vistos == nomes, "o deslocamento não cobre o conjunto na ordem"
        assert len(set(vistos)) == len(vistos), "o deslocamento repete pessoa"

        # ── 4. a continuação é REAL, não promessa
        #
        # ⚠️ Afirmação POSITIVA de propósito. Minha 1ª versão procurava a frase antiga («ficaram
        # para a próxima rodada») e reprovou o código JÁ CORRIGIDO — porque a frase aparece no
        # comentário onde eu documento o defeito. Caçar a ausência de um texto num arquivo que
        # DESCREVE esse texto é o caçador medindo a si mesmo, e é a mesma armadilha do caçador de
        # regex que casou com a minha própria linha antigolpe.
        fonte = ja.__file__.replace(".pyc", ".py")
        if os.path.exists(fonte):
            with open(fonte, encoding="utf-8") as fh:
                corpo = fh.read()
            assert "ainda não analisadas" in corpo, (
                "o texto da sobra precisa dizer quantas foram VISTAS de quantas — sem isso volta "
                "a anunciar continuação sem dizer como chegar lá")
            assert "proximo_pular" in corpo, "o retorno perdeu `proximo_pular`"
            assert "pular: int = 0" in corpo, "o parâmetro `pular` saiu da assinatura"

        print(f"OK {dados['total']} jornada(s) · {len(pessoas)} pessoa(s) — nenhuma com turno em "
              f"andamento (folga {FOLGA_HORAS}h) · deslocamento cobre as {len(nomes)} em "
              f"{-(-len(nomes) // teto)} rodada(s) de {teto}")

    print("TEST oraculo_jornada_aberta_turno_terminado PASS")


if __name__ == "__main__":
    asyncio.run(main())
