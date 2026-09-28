"""Depois da saída, o app não pede a volta de um almoço que nunca houve.

🔴 MEDIDO EM 28/09/2026, no WISLEY. Ele bateu `entrada` 07:02 e, às 19:08, `saida` por
contingência (a facial recusava). Dezessete segundos depois o botão disparou de novo e o app
gravou **`retorno_almoco` às 19:08:59** — a volta de um almoço que não existiu, no fim de um
turno de doze horas. O dia dele ficou com entrada, saída e um retorno depois da saída.

## A causa, e por que as travas existentes não pegaram

`tipo = seq[feitas]` conta batidas por **POSIÇÃO** e não olha QUAIS tipos já existem. Ele tinha
os tipos 1 e 4 (`entrada`, `saida`); `feitas` valia 2; `seq[2]` é `retorno_almoco`.

⭐ E as duas travas do arquivo **observam a coisa errada**: a primeira pergunta *"quantas horas
desde a saída para o almoço?"* — e ele **não tem batida de almoço**. `horas_desde_almoco` vem
`None`, o `if` é falso, e o tipo errado passa. **Campo ausente falhando ABERTO**, na decisão que
rotula um registro trabalhista.

O fato decisivo nunca foi o almoço: é que a jornada tem abertura E fechamento na janela.

## O que este oráculo trava

1. **Jornada com `entrada` e `saida` posterior devolve `concluido`** — afirmado chamando a
   função de verdade contra o banco de verdade, por PAPEL («alguém com jornada fechada»), nunca
   por nome ou id.
2. **⭐ A `entrada` ANTES da `saida` é obrigatória na regra.** É o que impede a 12x36 de
   quebrar: quem encerra o turno noturno às 07:00 e assume outro às 19:00 tem, na janela de 14h,
   uma `saida` SEM entrada que a preceda — ali a jornada está COMEÇANDO, e a próxima batida dele
   tem de continuar sendo `entrada`. Sem essa exigência, o conserto trocaria um defeito por um
   pior.
3. **Não recusa ninguém.** `concluido` faz a contingência gravar como `extra`; a decisão de
   13/08/2026 (o ANTONIO WALCICLEY — nunca impedir alguém de registrar trabalho que fez)
   continua valendo. Oráculo que transforma conserto em bloqueio é pior que o defeito.

⚠️ READ-ONLY: não insere nem apaga batida nenhuma.
"""

import ast
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

_FONTE = "/app/modules/people_management/employee_portal/controllers/self_service_controller.py"


async def main() -> None:
    with open(_FONTE, encoding="utf-8") as fh:
        src = fh.read()
    ast.parse(src)  # o arquivo tem de importar; sintaxe quebrada aqui derruba o app inteiro

    # 1 — a EXIGÊNCIA da entrada anterior é a metade que protege a 12x36. Afirmada no texto do
    #     SQL porque é ali que ela vive; sem ela o conserto viraria regressão silenciosa.
    assert "jornada_fechada" in src, (
        "a regra «jornada já fechada» desapareceu — o app volta a oferecer `retorno_almoco` "
        "depois da saída, e a volta de um almoço que nunca houve volta a entrar no banco"
    )
    trecho = src[src.index("jornada_fechada") : src.index("jornada_fechada") + 1800]
    assert "ent.punch_timestamp < s.punch_timestamp" in trecho, (
        "a regra deixou de exigir a ENTRADA ANTES da SAÍDA. Sem isso, quem encerra o turno "
        "noturno às 07:00 e assume outro às 19:00 tem a próxima batida rotulada como `extra` "
        "em vez de `entrada` — o conserto viraria um defeito pior que o original"
    )

    from modules.people_management.employee_portal.controllers.self_service_controller import (
        _proxima_batida_info,
    )

    async with async_session_factory() as db:
        # 2 — PAPEL, não pessoa: alguém com jornada fechada na janela de 14h.
        fechada = (
            await db.execute(
                text(
                    "SELECT s.employee_id::text FROM gp_clock_punches s "
                    " WHERE lower(coalesce(s.punch_type,'')) = 'saida' "
                    "   AND s.punch_timestamp > (now() AT TIME ZONE 'America/Manaus') - interval '13 hours' "
                    "   AND EXISTS (SELECT 1 FROM gp_clock_punches e "
                    "        WHERE e.employee_id = s.employee_id "
                    "          AND lower(coalesce(e.punch_type,'')) = 'entrada' "
                    "          AND e.punch_timestamp < s.punch_timestamp "
                    "          AND e.punch_timestamp > (now() AT TIME ZONE 'America/Manaus') - interval '13 hours') "
                    " LIMIT 1"
                )
            )
        ).scalar()
        if not fechada:
            # NÃO VERIFICADO é resultado válido; passar calado não é.
            print("⚠️ NÃO VERIFICADO: ninguém com jornada fechada na janela agora — a asserção "
                  "de comportamento fica sem sujeito nesta rodada. A regra estrutural acima passou.")
        else:
            info = await _proxima_batida_info(db, fechada)
            assert info["concluido"] is True and info["tipo"] == "concluido", (
                f"jornada com entrada e saída devolveu tipo «{info['tipo']}» "
                f"(concluido={info['concluido']}) — se for `retorno_almoco` ou `saida_almoco`, "
                "o app está pedindo uma batida do MEIO do dia depois do fim dele, que foi "
                "exatamente o defeito do WISLEY"
            )
            print(f"OK jornada fechada → tipo «{info['tipo']}», concluido={info['concluido']}")

        # 3 — o conserto não pode ter virado bloqueio: a rota de contingência grava `extra`
        #     quando concluído, e é isso que mantém a decisão do ANTONIO WALCICLEY viva.
        assert '"extra"' in src or "'extra'" in src, (
            "o rótulo `extra` sumiu da contingência: `concluido` voltaria a ser recusa, e "
            "impedir alguém de registrar trabalho que fez é pior que um tipo errado"
        )
        # Nenhuma batida pode ter nascido deste oráculo.
        print("OK o rótulo `extra` segue existindo — concluído NÃO é recusa")

    print("OK a regra exige a ENTRADA antes da SAÍDA (a 12x36 noturna não regride)")
    print("TEST oraculo_jornada_fechada_nao_pede_almoco PASS")


if __name__ == "__main__":
    asyncio.run(main())
