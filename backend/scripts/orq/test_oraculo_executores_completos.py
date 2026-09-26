"""Prova que TODO tipo de rascunho esperando aprovação tem executor registrado.

🔴 POR QUE EXISTE — este defeito voltou DUAS VEZES no mesmo lugar:

  · 31/08/2026: `EXECUTORES` tinha **0** entradas no processo do backend. Os oráculos
    importavam `tools_acao_crm` no topo, viam tudo registrado e passavam verde; a Central
    falhava em TODO rascunho de CRM. O Jordan tentava aprovar a proposta da VEGA desde sexta.
  · 26/09/2026: o conserto daquele dia importou **só o CRM**. Medido no processo vivo:
    **24 executores, os 24 de CRM**. O repositório registra 38 tipos em 7 arquivos — DP,
    financeiro, GED e fiscal nunca se registravam. Parados na fila: 52 `pendencia_ponto`,
    21 `financeiro_cobranca`, 15 `escala_pedido`. O Jordan clicou aprovar e recebeu
    «sem executor registrado para tipo 'pendencia_ponto'».

⭐ A LIÇÃO QUE ESTE ORÁCULO ENCARNA: **o alvo deriva da FONTE.** Uma lista fixa de tipos aqui
teria passado verde nas duas vezes — eu escreveria os tipos que conheço, e o defeito é
justamente o tipo que eu não lembrei. Então a lista de tipos a conferir vem de
`agent_drafts`: o que está na fila de verdade é o que precisa ser executável.

⚠️ E o oráculo importa o MESMO caminho que a Central usa (`_garantir_executores`), não os
módulos de ferramentas direto. Importar `tools_acao_*` no topo é exatamente o que fez o
oráculo de agosto ser cúmplice: ele criava o estado que deveria medir.
"""

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

falhas: list[str] = []


async def main() -> None:
    # ⚠️ A ORDEM IMPORTA: primeiro medir o estado NU, como o backend acorda.
    from modules.ai.conversation.services.orquestrador.acoes.rascunho import (
        EXECUTORES,
        _garantir_executores,
    )

    nu = len(EXECUTORES)
    _garantir_executores()
    depois = len(EXECUTORES)
    print(f"  executores: {nu} no import nu → {depois} depois de _garantir_executores()")
    if depois == 0:
        falhas.append("_garantir_executores() não registrou NADA — a Central não aprova nada")

    async with async_session_factory() as db:
        # alvos derivam da FONTE: o que está na fila esperando um humano
        # ⚠️ SEPARA OS DOIS CAMINHOS DE APROVAÇÃO, porque eles não usam a mesma peça:
        #   · `requires_otp = false` → o controller chama o EXECUTOR. Sem executor, erro.
        #   · `requires_otp = true`  → o controller devolve `needsOtp` e RETORNA. Nunca chama
        #     executor nenhum; quem conclui é a tela de OTP, por `action_url_execucao`.
        # Minha primeira versão exigia executor dos dois e acusava 3 rascunhos 🔴 que passam por
        # outro caminho — a trava observando a coisa errada, de novo. O que falta nos 🔴 é a URL.
        fila = (await db.execute(text(
            "SELECT tipo, count(*) AS n FROM agent_drafts "
            " WHERE status IN ('rascunho','aprovado') AND NOT coalesce(requires_otp,false) "
            " GROUP BY 1 ORDER BY 2 DESC"))).mappings().all()

        if not fila:
            # CONTROLE: fila vazia não prova que o registro funciona. Digo isso em voz alta em
            # vez de imprimir PASS sobre tabela vazia.
            print("  ⚠️ nenhum rascunho na fila — nada a afirmar a partir do dado real")
        else:
            orfaos = [(r["tipo"], r["n"]) for r in fila if r["tipo"] not in EXECUTORES]
            for tipo, n in orfaos:
                falhas.append(f"{n} rascunho(s) de '{tipo}' na fila e NENHUM executor — "
                              "aprovar devolve «sem executor registrado»")
            if not orfaos:
                print(f"  ok  {len(fila)} tipo(s) na fila ({sum(r['n'] for r in fila)} "
                      "rascunho(s)), todos com executor")

        # 2 — 🔴 não precisa de executor, mas precisa de DESTINO. Sem `action_url_execucao` o
        #     aprovador recebe "conclua com OTP na tela" e nenhuma tela — beco sem saída, e ele
        #     não tem como saber que o problema não é ele.
        cegos = (await db.execute(text(
            "SELECT tipo, count(*) AS n FROM agent_drafts "
            " WHERE status IN ('rascunho','aprovado') AND coalesce(requires_otp,false) "
            "   AND coalesce(payload->>'action_url_execucao','') = '' "
            " GROUP BY 1 ORDER BY 2 DESC"))).mappings().all()
        if cegos:
            for c in cegos:
                falhas.append(f"{c['n']} rascunho(s) 🔴 de '{c['tipo']}' sem "
                              "`action_url_execucao` — aprovar manda o humano para uma tela que "
                              "não existe")
        else:
            print("  ok  todo rascunho 🔴 na fila tem destino de OTP")

        # 3 — o histórico de FALHA não pode ter "sem executor". Se tem, alguém aprovou e o
        #     sistema perdeu o ato dele; e o rascunho fica decidido sem ter acontecido.
        sem_exec = (await db.execute(text(
            "SELECT count(*) FROM agent_drafts "
            " WHERE status = 'falha' AND coalesce(erro_execucao,'') LIKE '%sem executor%'"))).scalar()
        if sem_exec:
            falhas.append(f"{sem_exec} rascunho(s) em 'falha' por «sem executor» — decisão "
                          "humana registrada e execução perdida; reprocessar")
        else:
            print("  ok  nenhum rascunho em 'falha' por falta de executor")

    # 4 — CONTROLE de caminho feliz: a régua PEGA um tipo inventado? Se não pegar, ela não
    #     estava medindo nada. Sem esta linha um `EXECUTORES` cheio de qualquer coisa passaria.
    if "tipo_que_nunca_existiu_9x7" in EXECUTORES:
        falhas.append("controle falhou: EXECUTORES responde por tipo inventado")
    else:
        print("  ok  controle: tipo inventado NÃO tem executor (a régua discrimina)")

    if falhas:
        for f in falhas:
            print(f"  ❌ {f}")
        print(f"\nTEST executores_completos FAIL ({len(falhas)})")
        sys.exit(1)
    print("\nTEST executores_completos PASS")


if __name__ == "__main__":
    asyncio.run(main())
