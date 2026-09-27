"""Prova que o agente sabe registrar cobertura de posto e batida em hora informada — sem mentir.

🔴 O DIA QUE PRODUZIU ISTO — 27/09/2026.

O dono, ao sair: *"a kelly patricia que estava escalada não foi ao posto… quem rendeu o jonilson
foi o rilen que não é do posto… consegui um diarista novo, Erlon… em portaria é comum esses
atrasos, faltas, rotatividade acontecerem e termos que chamar quem nunca foi da empresa. nosso
hermes agent e o josé luis precisam aprender e se adaptar a essas circunstâncias"*.

E os dados diziam o mesmo ANTES dele falar: das 6 conversas que o `hermes_ponte` marcou como
`falhou`, duas eram exatamente isto e nenhuma tinha tool — *"Dona Ericka chegou atrasada"* e
*"Se eu detectei esse problema é porque eu já assumi o posto"*.

## ⭐ E o pior defeito do dia: o agente fez uma coisa e contou outra

O JONILSON perguntou como fechar a saída. O agente chamou `abrir_pendencia_dp` — razoável, era a
única tool que servia — e respondeu **"Registrado, Jonilson: saída de hoje às 08:38"**. A
pendência nasceu; a BATIDA não existia. A jornada dele ficou **15 horas aberta**.

A causa não foi esperteza do modelo. Foi o que a casa DIZ: `pendencia_dp` devolvia
*"Registrei aqui…"*, e "registrei" sem objeto, numa conversa sobre ponto, vira "registrei a
batida". Mesma família do Tangerino.

E faltava capacidade de verdade: `registrar_batida_contingencia` carimbava AGORA. Para quem já
saiu às 08:38 e fala 09:20, não existia caminho certo.

Este oráculo trava as quatro paredes que nasceram disso.
"""

import asyncio
import datetime as dt
import inspect
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from core.database import async_session_factory  # noqa: E402

falhas: list[str] = []


async def main() -> None:
    from modules.ai.conversation.services.orquestrador.acoes import rascunho as R
    from modules.operacional import cobertura_posto as cob
    from modules.people_management.ponto import pendencia_dp as pdp
    from modules.people_management.ponto.atendimento_funcionario import (
        _hora_informada,
        registrar_contingencia,
    )

    # 1 — ⭐ A HORA INFORMADA TEM PAREDE. Hora vinda de modelo sem trava é fabricação.
    agora = dt.datetime.now(ZoneInfo("America/Manaus")).replace(tzinfo=None)
    daqui_a_pouco = (agora + dt.timedelta(hours=2)).strftime("%H:%M")
    fut = _hora_informada(daqui_a_pouco)
    if fut and fut > agora:
        falhas.append(f"aceitou hora NO FUTURO ({daqui_a_pouco} → {fut}) — eu mesmo deixei uma "
                      "batida de teste às 19:40 num banco às 07:01")
    else:
        print("  ok  hora no futuro nunca vira batida no futuro")

    for ruim in ("blabla", "25:99", "", None):
        if _hora_informada(ruim) is not None:
            falhas.append(f"aceitou hora inválida {ruim!r} — deveria devolver None e carimbar agora")
    else:
        print("  ok  hora ilegível/inválida recusa e cai para 'agora'")

    # noturno: hora que ainda não chegou hoje pertence a ONTEM
    tarde = (agora + dt.timedelta(hours=6)).strftime("%H:%M")
    r_tarde = _hora_informada(tarde)
    if r_tarde is not None and r_tarde.date() != (agora.date() - dt.timedelta(days=1)):
        falhas.append(f"hora futura de hoje ({tarde}) não virou ONTEM — o noturno cruza a "
                      "meia-noite e `TIME + 24h` dá a volta em vez de avançar o dia")
    else:
        print("  ok  hora que ainda não chegou hoje é lida como de ONTEM (noturno)")

    # a assinatura EXPÕE o parâmetro — sem ele a capacidade não existe para o agente
    if "quando" not in inspect.signature(registrar_contingencia).parameters:
        falhas.append("`registrar_contingencia` perdeu o parâmetro `quando` — volta a carimbar "
                      "sempre AGORA, e quem já saiu do posto fica sem caminho certo")
    else:
        print("  ok  `registrar_contingencia` aceita a hora informada pela pessoa")

    # 2 — ⭐ A TOOL QUE NÃO GRAVA NÃO PODE DIZER QUE GRAVOU.
    #     Afirma a REGRA (o retorno desmente a batida), não a frase exata.
    # ⚠️ Procura a ATRIBUIÇÃO, não a prosa. Minha 1ª versão buscava "Registrei aqui" no
    # `getsource` inteiro e ficou VERMELHA por causa do comentário que documenta o defeito —
    # o caçador casando com a própria explicação, como o regex antigolpe que casou com a minha
    # linha antigolpe em 25/09. O que importa é o que a função DEVOLVE.
    src = inspect.getsource(pdp.abrir)
    if '"msg": "Registrei aqui' in src or "'msg': 'Registrei aqui" in src:
        falhas.append("`pendencia_dp.abrir` voltou a devolver 'Registrei aqui' — foi essa "
                      "palavra que virou 'Registrado: saída às 08:38' para o Jonilson")
    elif "diga_a_pessoa" not in src:
        falhas.append("o retorno de `pendencia_dp.abrir` perdeu o `diga_a_pessoa` — é ele que "
                      "instrui o agente a não anunciar batida que não existe")
    elif "NÃO lança batida" not in src and "não lança batida" not in src.lower():
        falhas.append("o retorno de `pendencia_dp.abrir` não NEGA explicitamente ter lançado "
                      "batida — proibir sem alternativa deixa o modelo preencher a lacuna")
    else:
        print("  ok  a pendência diz em voz alta que NÃO lança batida")

    # 3 — a cobertura recusa o que não pode afirmar
    async with async_session_factory() as db:
        amb = await cob.registrar(db, faltou="ANTONIO")
        if amb.get("ok") or "AMBÍGUO" not in (amb.get("motivo") or ""):
            falhas.append(f"nome ambíguo NÃO foi recusado: {amb.get('motivo')} — há cinco "
                          "ANTONIO nesta casa e escolher é o erro Jair→Antonio Carlos")
        else:
            print("  ok  cobertura recusa nome ambíguo")

        nada = await cob.registrar(db, faltou="NOME_QUE_NUNCA_EXISTIU_9X7")
        if nada.get("ok"):
            falhas.append("nome inventado foi aceito — a régua diz sim para qualquer coisa")
        else:
            print("  ok  controle: nome inexistente recusa")

        # ⭐ quem BATEU PONTO não faltou. Sem esta parede o agente marcaria falta de quem
        #    trabalhou, e o fato mais forte (a batida) perderia para o relato.
        bateu = (await db.execute(__import__("sqlalchemy").text(
            "SELECT e.nome FROM gp_clock_punches g JOIN employees e ON e.id=g.employee_id "
            " JOIN shifts s ON s.employee_id=e.id AND s.shift_date=g.punch_timestamp::date "
            " WHERE g.punch_type='entrada' AND g.punch_timestamp::date >= current_date - 1 "
            "   AND s.is_active LIMIT 1"))).scalar()
        if bateu:
            r = await cob.registrar(db, faltou=bateu)
            if r.get("ok"):
                falhas.append(f"{bateu} TEM batida e mesmo assim foi aceito como falta")
            else:
                print(f"  ok  quem tem batida no turno não é aceito como falta ({bateu.split()[0]})")
        else:
            print("  ·   ninguém com batida+turno para o controle hoje")

    # 4 — ⭐ RASCUNHO SEM EXECUTOR É BOTÃO QUE FALHA NA MÃO DE QUEM APROVA.
    #     Em 26/09 havia 17 tipos assim, e a Central dizia "sem executor registrado".
    R._garantir_executores()
    if "cobertura_posto" not in R.EXECUTORES:
        falhas.append("o tipo `cobertura_posto` não tem executor — o rascunho nasce e a "
                      "aprovação falha na Central")
    else:
        print(f"  ok  executor de `cobertura_posto` registrado ({len(R.EXECUTORES)} no total)")

    if falhas:
        for f in falhas:
            print(f"  ❌ {f}")
        print(f"\nTEST cobertura_e_hora_informada FAIL ({len(falhas)})")
        sys.exit(1)
    print("\nTEST cobertura_e_hora_informada PASS")


if __name__ == "__main__":
    asyncio.run(main())
