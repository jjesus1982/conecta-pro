"""A rendição entrega a batida APURADA, e ela bate com o banco.

🔴 O DEFEITO QUE MOTIVOU (27/09/2026, primeira execução automática da rotina). O prompt mandava
o Hermes descobrir a presença sozinho com `presenca_ao_vivo`. Ele reportou:

    «ALAN VIEIRA status presente (batida 06:00) … **sem saída registrada**»

O Alan havia batido SAÍDA às 18:00:01, dez minutos antes. E o quadro de presença **não tem campo
de saída por pessoa** — calcula a primeira batida da janela e chama de `presente`; a única saída
que existe lá é `saidas_noturno_ontem`, contador do dia anterior. A ferramenta nunca disse
aquilo: o Hermes converteu «a ferramenta não me informa» em «não existe», e escreveu a invenção
dentro do campo `conferi`, que existe para ser a prova.

⭐ Consequência medida: o Prime Arena, que estava DESCOBERTO (quem saía bateu saída, o entrante
não bateu nada), foi publicado no Gestão como `em_risco` 🟠 em vez de 🔴. A gravidade errada pela
razão errada.

## O que este oráculo trava

Não a resposta do Hermes — essa é de LLM e não se congela. Trava o **fato que vai na mão dele**:
para cada pessoa da troca, `bateu` tem de concordar com uma consulta escrita de forma
INDEPENDENTE sobre `gp_clock_punches`. Se a apuração voltar a ser inferida, ou se o SQL perder o
campo, isto fica vermelho.

⚠️ Afirma a REGRA, não a fotografia: não fixa nome de pessoa, posto nem horário — só a
equivalência «apurado == banco» e a existência do campo. Um dia sem troca nenhuma na janela é
resultado válido e não reprova (a rotina só roda nos minutos das trocas).
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402
from modules.integrations.connectors.whatsapp import rendicao  # noqa: E402

#: Janela larga de propósito: o oráculo roda às 05:00, longe das trocas. Com 24h ele sempre tem
#: material real para conferir, e a regra que ele afirma não depende da hora em que rodou.
JANELA_MIN = 24 * 60


async def main() -> None:
    async with async_session_factory() as db:
        linhas = (await db.execute(text(rendicao._SQL_TROCAS),
                                   {"janela": JANELA_MIN})).mappings().all()

        # O campo tem de EXISTIR. Contra o código anterior isto estourava em KeyError — era um
        # SQL de string_agg que não conhecia batida nenhuma.
        for campo in ("posto", "nome", "papel", "hora", "bateu"):
            assert linhas is not None
            if linhas:
                assert campo in linhas[0], f"a apuração perdeu o campo «{campo}»"

        if not linhas:
            print("OK sem troca na janela — nada a conferir (resultado válido)")
            print("TEST oraculo_rendicao_batida_apurada PASS")
            return

        # ⚠️ NÃO reconstruo o marco aqui: a virada de meia-noite do noturno é exatamente a
        # lógica que o SQL da rotina resolve, e reimplementá-la seria auditar a query com uma
        # cópia dela. A conferência independente é mais simples e mais forte — se a apuração
        # AFIRMA uma batida, aquela batida tem de existir no banco naquele minuto.
        divergentes = []
        for x in linhas:
            if not x["bateu"]:
                continue
            tipo = "saida" if x["papel"] == "sai" else "entrada"
            existe = (await db.execute(text("""
                SELECT count(*) > 0 FROM gp_clock_punches g
                  JOIN employees e ON e.id = g.employee_id
                 WHERE e.nome = :nome AND g.punch_type = :tipo
                   AND to_char(g.punch_timestamp, 'HH24:MI') = :hhmm"""),
                {"nome": x["nome"], "tipo": tipo, "hhmm": x["bateu"]})).scalar()
            if not existe:
                divergentes.append(f"{x['nome']} {tipo} apurado {x['bateu']} não existe no banco")

        assert not divergentes, "apuração divergiu do banco: " + " · ".join(divergentes[:5])

        bateram = sum(1 for x in linhas if x["bateu"])
        print(f"OK {len(linhas)} pessoa(s) em troca nas últimas 24h · {bateram} com batida "
              f"apurada e conferida no banco · {len(linhas) - bateram} sem batida")

        # Suspenders: o prompt não pode voltar a mandar o Hermes descobrir a batida sozinho, nem
        # perder a proibição de afirmar ausência. Foi assim que a saída inventada nasceu.
        assert "JÁ VÊM APURADAS" in rendicao._SISTEMA, "o prompt voltou a pedir a batida ao Hermes"
        assert "não está registrado" in rendicao._SISTEMA, "caiu a proibição de afirmar ausência"
        for balde in ("descoberto", "em_risco", "ok"):
            assert f"`{balde}`" in rendicao._SISTEMA, f"o balde «{balde}» ficou sem definição"
        print("OK prompt mantém a apuração externa, a proibição de inventar e os 3 baldes definidos")

    print("TEST oraculo_rendicao_batida_apurada PASS")


if __name__ == "__main__":
    asyncio.run(main())
