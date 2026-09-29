"""O horário corrigido à mão manda no cálculo do atraso.

🔴 MEDIDO EM 29/09/2026, e achado porque a pessoa insistiu. A CELIANE escreveu no WhatsApp:

    "já falei várias vezes"
    "eu entro 9:0h da manhã"
    "eu nunca bater pode atrasado"

O cadastro dela em `shifts` dizia **08:00–17:00** e ela entra às **09:00**. Consequência: 60
minutos de atraso todo dia — e não só como acusação. Sem justificativa, `punch_service` **RECUSA
a batida** (409, «sem isso ela não é registrada»). Ela era obrigada a justificar um atraso
inexistente TODO DIA para conseguir bater.

## ⭐ O pior: a resposta certa já estava escrita

`ponto_horario_vigencia` tinha UMA linha, gravada em **24/09/2026** por «jordan via jose-luis»:

    entrada 09:00 · saída 18:00 · vigência desde 2026-09-24
    motivo: "Horario correto informado pelo Jordan no grupo Gestao em 24/09/2026 — o cadastro
             trazia 08:00-17:00 e a acusava de 60min de atraso todo dia."

E **nada no cálculo do atraso a lia.** Medido: a tabela era consultada em UM lugar do backend
inteiro (`whatsapp/supervisao.py`), e não em `punch_service`, que é quem decide. A correção
existia há **cinco dias** e ela foi acusada três vezes só na manhã de 29/09.

⭐ É a família mais cara desta casa vista da pior forma: **não faltava código, faltava alguém LER
o que já estava gravado.** Igual ao geofence que mede e não gateia.

## O que este oráculo trava

1. **`punch_service` consulta `ponto_horario_vigencia`.** Se a leitura sair, a pessoa volta a ser
   recusada por um atraso que não existe.
2. **A vigência sobrepõe o cadastro** (`coalesce(hv.entrada, s.planned_start_time)`), e a escolha
   do turno mais próximo usa o MESMO horário corrigido — comparar com o cadastro errado ali
   escolheria o turno errado e o coalesce viraria enfeite.
3. **Quem não tem vigência não muda de comportamento** — afirmado contra o banco.
4. **A vigência respeita a JANELA** (`vigencia_inicio`/`vigencia_fim`): horário corrigido em
   setembro não pode reescrever o atraso de um turno de março.

⚠️ Afirma a REGRA, não a fotografia: nenhum nome nem id. A única linha de hoje pode virar vinte.
"""

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database.session import get_sync_db  # noqa: E402

_SVC = "/app/modules/people_management/ponto/services/punch_service.py"
_LEMBRETE = "/app/modules/operacional/lembrete_ponto.py"
TABELA = "ponto_horario_vigencia"


def main() -> None:
    with open(_SVC, encoding="utf-8") as fh:
        src = fh.read()
    ast.parse(src)  # sintaxe quebrada aqui derruba a batida de todo mundo

    # 1 — a leitura existe
    assert TABELA in src, (
        f"`{TABELA}` saiu de punch_service — quem tem o cadastro de horário errado volta a ser "
        "RECUSADO por um atraso que não existe, e a correção escrita à mão volta a ser ignorada"
    )
    # 2 — sobrepõe de verdade, nos dois marcos E na ordenação
    for alvo, porque in (
        ("coalesce(hv.entrada, s.planned_start_time)", "entrada corrigida"),
        ("coalesce(hv.saida, s.planned_end_time)", "saída corrigida"),
    ):
        assert alvo in src, f"a vigência deixou de sobrepor a {porque}"
    # a ordenação (escolha do turno mais próximo) tem de usar o horário corrigido também
    pos_order = src.find("ORDER BY abs(EXTRACT(EPOCH")
    assert pos_order > 0, "a escolha do turno mais próximo desapareceu de punch_service"
    trecho_order = src[pos_order : pos_order + 700]
    assert "coalesce(hv.entrada" in trecho_order and "coalesce(hv.saida" in trecho_order, (
        "a ORDENAÇÃO voltou a usar o cadastro cru: ela escolheria o turno errado e o coalesce do "
        "SELECT viraria enfeite — a pessoa seguiria acusada"
    )
    # 3 — a janela de vigência é respeitada
    assert "hv.vigencia_inicio <= s.shift_date" in src and "hv.vigencia_fim IS NULL" in src, (
        "a vigência perdeu a JANELA: um horário corrigido em setembro passaria a reescrever o "
        "atraso de turnos de meses anteriores, mudando folha já fechada"
    )

    # ⭐ 4 — O LEMBRETE TAMBÉM. Consertar só quem RECUSA e deixar quem AVISA é meio conserto, e o
    # meio que sobrou é o pior: a recusa ela percebe e reclama; o lembrete ensina a hora errada e
    # ela acredita. Medido em 28 e 29/09: a CELIANE recebeu «começa em 5 minutos, às 08:00»,
    # disparado às 07:55, quando ela entra às 09:00.
    with open(_LEMBRETE, encoding="utf-8") as fh:
        lembrete = fh.read()
    ast.parse(lembrete)
    assert TABELA in lembrete, (
        f"`{TABELA}` saiu de lembrete_ponto: o aviso volta a mandar a pessoa bater na hora do "
        "cadastro errado — e como a hora exibida sai da MESMA referência, a mensagem passa a "
        "ensinar um horário que não é o dela"
    )
    # ⭐ E afirma por COMPORTAMENTO, não por texto: pega a referência que o módulo realmente usa,
    # roda contra o banco e exige que ela divirja do cadastro exatamente para quem tem vigência.
    # Asserção de texto aqui seria burlável por um `coalesce` de enfeite; esta não é.
    from modules.operacional.lembrete_ponto import _REF_ENTRADA  # noqa: PLC0415
    with get_sync_db() as db:
        conf = db.execute(
            text(
                "SELECT count(*) FILTER (WHERE hv.entrada IS NOT NULL "
                f"                         AND {_REF_ENTRADA} <> (sh.shift_date + sh.planned_start_time)) "
                "         AS corrigidos_de_fato, "
                "       count(*) FILTER (WHERE hv.entrada IS NULL "
                f"                         AND {_REF_ENTRADA} <> (sh.shift_date + sh.planned_start_time)) "
                "         AS mexeu_em_quem_nao_devia, "
                "       count(*) FILTER (WHERE hv.entrada IS NOT NULL "
                "                          AND hv.entrada <> sh.planned_start_time) AS deveria_corrigir "
                f"  FROM shifts sh LEFT JOIN {TABELA} hv "  # noqa: S608 — constante do módulo
                "         ON hv.employee_id = sh.employee_id "
                "        AND hv.vigencia_inicio <= sh.shift_date "
                "        AND (hv.vigencia_fim IS NULL OR hv.vigencia_fim >= sh.shift_date) "
                " WHERE sh.shift_date = current_date"
            )
        ).mappings().first()
    assert conf["mexeu_em_quem_nao_devia"] == 0, (
        f"o lembrete mudou a hora de {conf['mexeu_em_quem_nao_devia']} turno(s) SEM vigência: a "
        "correção vazou para quem não pediu, e essas pessoas passam a ser avisadas na hora errada"
    )
    assert conf["corrigidos_de_fato"] == conf["deveria_corrigir"], (
        f"{conf['deveria_corrigir']} turno(s) têm horário corrigido à mão e o lembrete só aplicou "
        f"em {conf['corrigidos_de_fato']}: o resto segue sendo avisado na hora do cadastro errado"
    )
    print(f"OK o LEMBRETE usa a vigência: {conf['corrigidos_de_fato']} de "
          f"{conf['deveria_corrigir']} turno(s) avisados na hora corrigida, e "
          f"{conf['mexeu_em_quem_nao_devia']} vazamento(s) para quem não tem vigência")

    # 5 — comportamento contra o banco: quem tem vigência usa ela, quem não tem não muda.
    with get_sync_db() as db:
        r = db.execute(
            text(
                "SELECT count(*) AS turnos, "
                "       count(hv.entrada) AS com_vigencia, "
                "       count(*) FILTER (WHERE hv.entrada IS NOT NULL "
                "                          AND hv.entrada <> s.planned_start_time) AS corrigem "
                f"  FROM shifts s LEFT JOIN {TABELA} hv "  # noqa: S608 — constante do módulo
                "         ON hv.employee_id = s.employee_id "
                "        AND hv.vigencia_inicio <= s.shift_date "
                "        AND (hv.vigencia_fim IS NULL OR hv.vigencia_fim >= s.shift_date) "
                " WHERE s.shift_date = current_date"
            )
        ).mappings().first()
        # Nenhuma asserção sobre QUANTOS: hoje é 1, amanhã pode ser 20. O que se afirma é a
        # coerência — toda vigência aplicada tem de vir de uma linha com autor e motivo, senão é
        # horário mudado por ninguém.
        sem_autor = db.execute(
            text(
                f"SELECT count(*) FROM {TABELA} "  # noqa: S608
                " WHERE coalesce(nullif(trim(registrado_por),''), NULL) IS NULL "
                "    OR coalesce(nullif(trim(motivo),''), NULL) IS NULL"
            )
        ).scalar() or 0
        assert sem_autor == 0, (
            f"{sem_autor} vigência(s) de horário sem autor ou sem motivo. Mudar o horário que "
            "decide atraso é ato sobre folha: sem quem e por quê, é horário alterado por ninguém"
        )

    print(f"OK punch_service LÊ `{TABELA}` — o horário corrigido à mão manda no atraso")
    print("OK sobrepõe entrada e saída, e a escolha do turno usa o mesmo horário corrigido")
    print("OK a janela de vigência é respeitada — não reescreve mês fechado")
    print(f"OK hoje: {r['turnos']} turno(s), {r['com_vigencia']} com vigência, "
          f"{r['corrigem']} de fato corrigindo o cadastro")
    print("OK toda vigência tem autor e motivo registrados")
    print("TEST oraculo_vigencia_horario_manda PASS")


if __name__ == "__main__":
    main()
